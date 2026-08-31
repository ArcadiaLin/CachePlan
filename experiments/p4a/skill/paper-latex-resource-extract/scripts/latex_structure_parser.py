#!/usr/bin/env python3
"""
机械解析 LaTeX 结构信息。

功能:
    从 assembled_tex 中抽取 title、authors、abstract、section outline、
    appendix/supplementary 标记、figure/table caption。
    figure 的图片资产、caption source 和 agent 可写字段由 figure_asset_extractor
    在 parse_one.py 中补强。

输出信息:
    这些字段属于当前阶段可机械化生成的 paper_record.content_units 与
    metadata 候选信息。作者字段是 best-effort；在线 arXiv 元数据成功时优先使用 API。

直接调用:
    不建议直接运行；请通过 parse_one.py 或 parse_batch.py 使用。
"""

from __future__ import annotations

import re
from typing import Any

from common import collapse_ws, find_command_arg, find_environment, read_balanced_braces, strip_tex_comments, tex_to_text
from script_config import load_config


LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")


def _section_re() -> re.Pattern[str]:
    levels = load_config().get("tex", {}).get("section_levels", ["section", "subsection", "subsubsection"])
    level_pattern = "|".join(re.escape(level) for level in levels)
    return re.compile(rf"\\(?P<level>{level_pattern})\*?(?:\[[^\]]*\])?\s*\{{", re.DOTALL)


def _caption_re() -> re.Pattern[str]:
    envs = load_config().get("tex", {}).get("caption_environments", ["figure", "figure*", "table", "table*"])
    env_pattern = "|".join(re.escape(env) for env in envs)
    return re.compile(
        rf"\\begin\{{(?P<kind>{env_pattern})\}}(?P<body>.*?)\\end\{{(?P=kind)\}}",
        re.DOTALL,
    )


def _extract_sections(text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for match in _section_re().finditer(text):
        parsed = read_balanced_braces(text, match.end() - 1)
        if not parsed:
            continue
        raw_title, end = parsed
        sections.append(
            {
                "level": match.group("level"),
                "title": tex_to_text(raw_title),
                "raw_title": raw_title,
                "start": match.start(),
                "end": end,
            }
        )
    return sections


def _extract_captions(text: str, wanted: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for match in _caption_re().finditer(text):
        kind = "figure" if match.group("kind").startswith("figure") else "table"
        if kind != wanted:
            continue
        body = match.group("body")
        caption = find_command_arg(body, "caption")
        label_match = LABEL_RE.search(body)
        items.append(
            {
                "label": label_match.group(1) if label_match else "",
                "caption": tex_to_text(caption),
            }
        )
    return items


def _extract_authors(text: str) -> list[str]:
    raws: list[str] = []
    for match in re.finditer(r"\\author(?:\[[^\]]*\])?\s*\{", text, re.DOTALL):
        parsed = read_balanced_braces(text, match.end() - 1)
        if parsed:
            raws.append(parsed[0])
    authors: list[str] = []
    for raw in raws:
        bold_names = re.findall(r"\\textbf\{([^{}]+)\}", raw)
        if bold_names:
            candidates = bold_names
        else:
            cleaned = re.sub(r"\\affiliation\s*\{.*?\}", " ", raw, flags=re.DOTALL)
            cleaned = re.sub(r"\\email\s*\{.*?\}", " ", cleaned, flags=re.DOTALL)
            cleaned = re.sub(r"\$[^$]*\$", " ", cleaned)
            candidates = re.split(r"\\(?:And|AND|and)|\\quad|\\\\|,", cleaned)
        for candidate in candidates:
            name = tex_to_text(candidate)
            name = re.sub(r"\S+@\S+", "", name)
            name = re.sub(r"\[[^\]]+\]", "", name)
            name = re.sub(r"\b(?:University|Institute|College|School|Department|Laboratory|Inc|Group)\b.*", "", name)
            name = re.sub(r"\b(?:Hong|Kong|Guangzhou|Tsinghua|Nanyang|Renmin|China|Beijing)\b.*", "", name)
            name = collapse_ws(name)
            if len(name.split()) >= 2 and len(name) < 80:
                authors.append(name)
    return list(dict.fromkeys(authors))


def parse_latex_structure(package: dict[str, Any]) -> dict[str, Any]:
    text = strip_tex_comments(package.get("assembled_tex") or package.get("main_tex") or "")
    sections = _extract_sections(text)
    abstract = tex_to_text(find_environment(text, "abstract"))
    title = tex_to_text(find_command_arg(text, "title"))
    authors = _extract_authors(text)
    section_outline = [
        {"level": section["level"], "title": section["title"]}
        for section in sections
        if section["title"]
    ]
    section_titles = [s["title"].lower() for s in sections]
    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "section_outline": section_outline,
        "sections": sections,
        "has_appendix": any("appendix" in title for title in section_titles) or "\\appendix" in text,
        "has_supplementary_material": any(
            "supplement" in title or "supplementary" in title for title in section_titles
        ),
        "figures": _extract_captions(text, "figure"),
        "tables": _extract_captions(text, "table"),
    }
