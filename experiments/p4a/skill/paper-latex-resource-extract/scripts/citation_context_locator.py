#!/usr/bin/env python3
"""
定位论文正文中的引用上下文。

功能:
    - 匹配 \\cite / \\citep / \\citet / parencite / textcite 等命令。
    - 将 cite key 对齐到已解析的 bib/bbl 条目。
    - 机械截取引用所在句子和 section。

边界:
    只做位置和上下文抽取，不推断 citation_function，不关联本地 claim。

直接调用:
    不建议直接运行；请通过 parse_one.py 或 parse_batch.py 使用。
"""

from __future__ import annotations

import re
from typing import Any

from common import collapse_ws, strip_tex_comments, tex_to_text
from script_config import load_config


def _cite_re() -> re.Pattern[str]:
    commands = load_config().get("tex", {}).get("citation_commands", ["cite"])
    command_pattern = "|".join(re.escape(command) for command in commands)
    return re.compile(
        rf"\\(?P<cmd>{command_pattern})(?:\s*\[[^\]]*\]){{0,2}}\s*\{{(?P<keys>[^{{}}]+)\}}",
        re.DOTALL,
    )


def _section_re() -> re.Pattern[str]:
    levels = load_config().get("tex", {}).get("section_levels", ["section", "subsection", "subsubsection"])
    level_pattern = "|".join(re.escape(level) for level in levels)
    return re.compile(rf"\\(?P<level>{level_pattern})\*?(?:\[[^\]]*\])?\s*\{{(?P<title>[^{{}}]+)\}}")


def _section_at(text: str, pos: int) -> str:
    current = ""
    for match in _section_re().finditer(text, 0, pos):
        current = tex_to_text(match.group("title"))
    return current


def _sentence_context(text: str, start: int, end: int) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind("\n\n", 0, start), text.rfind("; ", 0, start))
    right_candidates = [idx for idx in (text.find(". ", end), text.find("\n\n", end), text.find("; ", end)) if idx != -1]
    left = 0 if left == -1 else left + 1
    right = min(right_candidates) + 1 if right_candidates else min(len(text), end + 240)
    return tex_to_text(text[left:right])


def locate_citation_contexts(package: dict[str, Any], references: dict[str, Any]) -> dict[str, Any]:
    text = strip_tex_comments(package.get("assembled_tex") or package.get("main_tex") or "")
    entries = references.get("entries", {})
    cited: list[dict[str, Any]] = []
    for index, match in enumerate(_cite_re().finditer(text), start=1):
        keys = [key.strip() for key in match.group("keys").split(",") if key.strip()]
        context = _sentence_context(text, match.start(), match.end())
        section = _section_at(text, match.start())
        for key in keys:
            ref = entries.get(key, {})
            cited.append(
                {
                    "index": index,
                    "cite_key": key,
                    "cite_command": match.group("cmd"),
                    "cited_paper_id": f"paper::{ref.get('arxiv_id')}" if ref.get("arxiv_id") else "",
                    "reference": ref,
                    "context": collapse_ws(context),
                    "section": section,
                    "raw": match.group(0),
                }
            )
    return {
        "cited_references": cited,
        "citing_papers": [],
        "reference_source": references.get("source", ""),
        "reference_count": len(entries),
    }
