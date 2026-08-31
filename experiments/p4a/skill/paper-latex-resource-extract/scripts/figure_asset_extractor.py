#!/usr/bin/env python3
"""
抽取 LaTeX figure 记录和图片资产。

功能:
    - 解析 figure/figure* 环境中的 \\caption、\\label、\\includegraphics 和 overpic。
    - 解析 \\graphicspath 的图片搜索目录。
    - 将源码包中的图片资产原样复制到输出目录 figures/。
    - 生成 figure_manifest.json 所需的结构化记录。

边界:
    不做图片格式转换，不读取图片视觉内容，不从图中抽取数值或结论。
    agent 后续只能基于 caption 和正文上下文补 description / agent_review。

直接调用:
    不建议直接运行；请通过 parse_one.py 或 parse_batch.py 使用。
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

from common import make_id, read_balanced_braces, tex_to_text
from script_config import load_config


LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")


def _strip_comments_keep_source_markers(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("% BEGIN included from") or stripped.startswith("% END included from"):
            lines.append(line)
            continue
        cut = len(line)
        for match in re.finditer("%", line):
            slash_count = 0
            i = match.start() - 1
            while i >= 0 and line[i] == "\\":
                slash_count += 1
                i -= 1
            if slash_count % 2 == 0:
                cut = match.start()
                break
        lines.append(line[:cut])
    return "\n".join(lines)


def _tex_config() -> dict[str, Any]:
    return load_config().get("tex", {})


def _figure_config() -> dict[str, Any]:
    return load_config().get("figures", {})


def _caption_env_re() -> re.Pattern[str]:
    envs = _tex_config().get("caption_environments", ["figure", "figure*", "table", "table*"])
    figure_envs = [env for env in envs if str(env).startswith("figure")]
    env_pattern = "|".join(re.escape(env) for env in figure_envs) or "figure\\*?"
    return re.compile(
        rf"\\begin\{{(?P<kind>{env_pattern})\}}(?P<body>.*?)\\end\{{(?P=kind)\}}",
        re.DOTALL,
    )


def _caption_arg(body: str) -> str:
    match = re.search(r"\\caption(?:\[[^\]]*\])?\s*\{", body, re.DOTALL)
    if not match:
        return ""
    parsed = read_balanced_braces(body, match.end() - 1)
    return parsed[0] if parsed else ""


def _graphics_re() -> re.Pattern[str]:
    commands = _tex_config().get("graphics_commands", ["includegraphics"])
    command_pattern = "|".join(re.escape(command) for command in commands)
    return re.compile(
        rf"\\(?P<cmd>{command_pattern})(?:\s*\[[^\]]*\])?\s*\{{(?P<path>[^{{}}]+)\}}",
        re.DOTALL,
    )


def _overpic_re() -> re.Pattern[str]:
    return re.compile(r"\\begin\{overpic\}(?:\s*\[[^\]]*\])?\s*\{(?P<path>[^{}]+)\}", re.DOTALL)


def _source_markers(text: str) -> list[tuple[int, str]]:
    markers = [(0, "")]
    for match in re.finditer(r"% BEGIN included from (?P<name>[^\n]+)", text):
        markers.append((match.start(), match.group("name").strip()))
    markers.sort(key=lambda item: item[0])
    return markers


def _source_at(markers: list[tuple[int, str]], pos: int, main_tex_name: str) -> str:
    current = main_tex_name
    for marker_pos, source in markers:
        if marker_pos <= pos:
            current = source or main_tex_name
        else:
            break
    return current


def _graphicspaths(text: str) -> list[str]:
    commands = _tex_config().get("graphicspath_commands", ["graphicspath"])
    paths: list[str] = []
    for command in commands:
        for match in re.finditer(rf"\\{re.escape(command)}\s*\{{", text, re.DOTALL):
            parsed = read_balanced_braces(text, match.end() - 1)
            if not parsed:
                continue
            raw = parsed[0]
            for path_match in re.finditer(r"\{([^{}]+)\}", raw):
                value = path_match.group(1).strip()
                if value:
                    paths.append(value)
    return paths


def _find_asset(
    raw_path: str,
    source_tex: str,
    asset_files: dict[str, bytes],
    graphicspaths: list[str],
    allowed_extensions: list[str],
) -> str:
    raw_path = raw_path.strip()
    candidates: list[str] = []
    source_dir = str(PurePosixPath(source_tex).parent)
    search_dirs = [""]
    if source_dir and source_dir != ".":
        search_dirs.append(source_dir)
    search_dirs.extend(path.strip("./") for path in graphicspaths if path)

    raw_has_suffix = PurePosixPath(raw_path).suffix != ""
    path_variants = [raw_path] if raw_has_suffix else [f"{raw_path}{ext}" for ext in allowed_extensions]
    for directory in search_dirs:
        for variant in path_variants:
            candidate = str(PurePosixPath(directory) / variant) if directory else variant
            candidates.append(candidate.strip("./"))

    normalized_assets = {name.strip("./"): name for name in asset_files}
    for candidate in candidates:
        if candidate in normalized_assets:
            return normalized_assets[candidate]
    basename = PurePosixPath(raw_path).name
    basename_variants = [basename] if raw_has_suffix else [f"{basename}{ext}" for ext in allowed_extensions]
    matches = [name for name in asset_files if PurePosixPath(name).name in basename_variants]
    return matches[0] if len(matches) == 1 else ""


def _safe_output_name(index: int, figure_id: str, source_path: str) -> str:
    slug = figure_id.split("::", 1)[-1] or f"figure-{index}"
    suffix = PurePosixPath(source_path).suffix or ".asset"
    return f"fig_{index:03d}_{slug}{suffix}"


def extract_figure_assets(package: dict[str, Any], paper_dir: Path) -> dict[str, Any]:
    text = _strip_comments_keep_source_markers(package.get("assembled_tex") or package.get("main_tex") or "")
    main_tex_name = package.get("main_tex_name") or ""
    asset_files: dict[str, bytes] = package.get("asset_files", {})
    allowed_extensions = [ext.lower() for ext in _figure_config().get("allowed_extensions", [])]
    graphicspaths = _graphicspaths(text)
    markers = _source_markers(text)
    output_dir = paper_dir / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    figures: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    copied = 0
    missing = 0

    for index, match in enumerate(_caption_env_re().finditer(text), start=1):
        body = match.group("body")
        label_match = LABEL_RE.search(body)
        label = label_match.group(1) if label_match else ""
        caption = tex_to_text(_caption_arg(body))
        source_tex = _source_at(markers, match.start(), main_tex_name)
        figure_id = make_id("fig", label or f"figure-{index}")
        files: list[dict[str, Any]] = []

        graphic_matches = list(_graphics_re().finditer(body)) + list(_overpic_re().finditer(body))
        graphic_matches.sort(key=lambda item: item.start())
        for graphic_index, graphic_match in enumerate(graphic_matches, start=1):
            raw_path = graphic_match.group("path").strip()
            source_path = _find_asset(raw_path, source_tex, asset_files, graphicspaths, allowed_extensions)
            status = "missing"
            output_path = ""
            missing_reason = ""
            if source_path and source_path in asset_files:
                output_path = str(PurePosixPath("figures") / _safe_output_name(index, figure_id, source_path))
                (paper_dir / output_path).write_bytes(asset_files[source_path])
                status = "copied"
                copied += 1
            else:
                missing += 1
                missing_reason = f"unable to resolve includegraphics path `{raw_path}`"

            file_record = {
                "path": output_path,
                "source_path": source_path or raw_path,
                "role": "primary" if graphic_index == 1 else "subfigure",
                "status": status,
            }
            if missing_reason:
                file_record["missing_reason"] = missing_reason
            files.append(file_record)

        if not files:
            missing += 1
            files.append(
                {
                    "path": "",
                    "source_path": "",
                    "role": "unknown",
                    "status": "missing",
                    "missing_reason": "no includegraphics command found in figure environment",
                }
            )

        record = {
            "figure_id": figure_id,
            "label": label,
            "caption": caption,
            "files": files,
            "caption_source": {
                "environment": match.group("kind"),
                "command": "caption" if caption else "",
                "source_tex": source_tex,
            },
            "description": "",
            "agent_review": {"status": "unreviewed", "notes": ""},
            "agent_interpretation_required": True,
        }
        figures.append(record)
        manifest.append(record)

    return {
        "figures": figures,
        "manifest": manifest,
        "figure_count": len(figures),
        "figure_asset_count": copied,
        "missing_figure_asset_count": missing,
    }
