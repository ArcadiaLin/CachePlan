#!/usr/bin/env python3
"""
读取 arXiv LaTeX 源码包并识别主 TeX 文件。

功能:
    - 解包 .tar.gz 中的 .tex / .bib / .bbl / 00README.json 和图片资产。
    - 优先使用 00README.json 中 usage=toplevel 的文件。
    - 如果没有 README，则根据 \\documentclass / \\begin{document} 等特征打分。
    - 递归展开 \\input / \\include，生成 assembled_tex 供后续机械解析。
    - 将配置允许扩展名的图片文件以 bytes 放入 package["asset_files"]，供 figure
      抽取器原样复制到输出目录。

扩展规则:
    主文件打分、可读取扩展名、include 命令来自
    scripts/config/layer4_config.yml 的 tex 段。

直接调用:
    不建议直接运行；请通过 parse_one.py 或 parse_batch.py 使用。
"""

from __future__ import annotations

import json
import re
import tarfile
from pathlib import PurePosixPath
from typing import Any

from common import arxiv_id_from_path
from script_config import load_config


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_member(tf: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    fileobj = tf.extractfile(member)
    if fileobj is None:
        return ""
    return _decode(fileobj.read())


def _read_member_bytes(tf: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    fileobj = tf.extractfile(member)
    if fileobj is None:
        return b""
    return fileobj.read()


def _find_by_name(names: list[str], wanted: str) -> str | None:
    wanted_norm = wanted.strip("./")
    for name in names:
        if name.strip("./") == wanted_norm:
            return name
    wanted_base = PurePosixPath(wanted_norm).name
    matches = [name for name in names if PurePosixPath(name).name == wanted_base]
    return matches[0] if len(matches) == 1 else None


def _read_readme(files: dict[str, str]) -> dict[str, Any]:
    readme_filename = load_config().get("tex", {}).get("readme_filename", "00README.json").lower()
    for name, content in files.items():
        if PurePosixPath(name).name.lower() == readme_filename.lower():
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"_parse_error": "invalid 00README.json"}
    return {}


def _main_from_readme(readme: dict[str, Any], tex_files: dict[str, str]) -> str | None:
    top_level_usage = load_config().get("tex", {}).get("top_level_usage", "toplevel")
    names = list(tex_files)
    for source in readme.get("sources", []) if isinstance(readme, dict) else []:
        if source.get("usage") != top_level_usage:
            continue
        filename = source.get("filename")
        if not filename:
            continue
        matched = _find_by_name(names, filename)
        if matched:
            return matched
    return None


def _score_tex(name: str, content: str) -> int:
    scoring = load_config().get("tex", {}).get("main_file_scoring", {})
    score = 0
    for marker, weight in scoring.get("content_markers", {}).items():
        if marker in content:
            score += int(weight)
    basename = PurePosixPath(name).name.lower()
    score += int(scoring.get("preferred_basenames", {}).get(basename, 0))
    score -= name.count("/") * int(scoring.get("path_depth_penalty", 3))
    for keyword, penalty in scoring.get("negative_name_keywords", {}).items():
        if keyword.lower() in name.lower():
            score -= int(penalty)
    return score


def _main_by_score(tex_files: dict[str, str]) -> str | None:
    if not tex_files:
        return None
    return max(tex_files, key=lambda name: _score_tex(name, tex_files[name]))


def _include_re() -> re.Pattern[str]:
    commands = load_config().get("tex", {}).get("include_commands", ["input", "include"])
    joined = "|".join(re.escape(command) for command in commands)
    return re.compile(rf"\\(?:{joined})\s*\{{([^{{}}]+)\}}")


def _resolve_include(current: str, include_name: str, tex_files: dict[str, str]) -> str | None:
    include_name = include_name.strip()
    if not include_name.endswith(".tex"):
        include_name = f"{include_name}.tex"
    current_dir = str(PurePosixPath(current).parent)
    candidates = []
    if current_dir and current_dir != ".":
        candidates.append(str(PurePosixPath(current_dir) / include_name))
    candidates.append(include_name)
    for candidate in candidates:
        matched = _find_by_name(list(tex_files), candidate)
        if matched:
            return matched
    return None


def assemble_tex(name: str, tex_files: dict[str, str], seen: set[str] | None = None) -> tuple[str, list[str]]:
    seen = seen or set()
    if name in seen:
        return "", []
    seen.add(name)
    content = tex_files.get(name, "")
    included: list[str] = []

    def repl(match: re.Match[str]) -> str:
        resolved = _resolve_include(name, match.group(1), tex_files)
        if not resolved:
            return match.group(0)
        sub_text, sub_included = assemble_tex(resolved, tex_files, seen)
        included.append(resolved)
        included.extend(sub_included)
        return f"\n% BEGIN included from {resolved}\n{sub_text}\n% END included from {resolved}\n"

    return _include_re().sub(repl, content), included


def load_latex_package(path: str) -> dict[str, Any]:
    extensions = tuple(load_config().get("tex", {}).get("file_extensions_to_read", [".tex", ".bib", ".bbl", ".json"]))
    asset_extensions = tuple(ext.lower() for ext in load_config().get("figures", {}).get("allowed_extensions", []))
    files: dict[str, str] = {}
    asset_files: dict[str, bytes] = {}
    all_files: list[str] = []
    with tarfile.open(path, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            all_files.append(member.name)
            lower = member.name.lower()
            if lower.endswith(extensions):
                files[member.name] = _read_member(tf, member)
            if asset_extensions and lower.endswith(asset_extensions):
                asset_files[member.name] = _read_member_bytes(tf, member)

    tex_files = {name: value for name, value in files.items() if name.lower().endswith(".tex")}
    bib_files = {name: value for name, value in files.items() if name.lower().endswith(".bib")}
    bbl_files = {name: value for name, value in files.items() if name.lower().endswith(".bbl")}
    readme = _read_readme(files)
    main_tex_name = _main_from_readme(readme, tex_files) or _main_by_score(tex_files)
    main_tex = tex_files.get(main_tex_name, "") if main_tex_name else ""
    assembled_tex, included_files = assemble_tex(main_tex_name, tex_files) if main_tex_name else ("", [])

    return {
        "input_path": path,
        "arxiv_id": arxiv_id_from_path(path),
        "all_files": all_files,
        "asset_files": asset_files,
        "readme": readme,
        "tex_files": tex_files,
        "bib_files": bib_files,
        "bbl_files": bbl_files,
        "main_tex_name": main_tex_name,
        "main_tex": main_tex,
        "assembled_tex": assembled_tex,
        "included_files": included_files,
    }
