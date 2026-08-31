#!/usr/bin/env python3
"""
解析 BibTeX / bbl 引用条目。

功能:
    - 解析 .bib 中的 key、title、author、year、venue、doi、arXiv id。
    - 当 .bib 不可用时，尝试从 .bbl 的 \\bibitem 中做 best-effort 解析。
    - 不做引用消歧，不请求外部 API，不判断引用关系语义。

直接调用:
    不建议直接运行；请通过 parse_one.py 或 parse_batch.py 使用。
"""

from __future__ import annotations

import re
from typing import Any

from common import ARXIV_ID_RE, collapse_ws, tex_to_text


ENTRY_START_RE = re.compile(r"@(?P<type>\w+)\s*\{\s*(?P<key>[^,]+),", re.DOTALL)
FIELD_RE = re.compile(r"(?P<name>\w+)\s*=\s*(?P<value>\{|\")", re.DOTALL)
BBL_RE = re.compile(
    r"\\bibitem(?:\[[^\]]*\])?\{(?P<key>[^{}]+)\}(?P<body>.*?)(?=\\bibitem|\\end\{thebibliography\})",
    re.DOTALL,
)


def _balanced_value(text: str, start: int, opener: str) -> tuple[str, int]:
    if opener == '"':
        i = start + 1
        out = []
        while i < len(text):
            if text[i] == '"' and text[i - 1] != "\\":
                return "".join(out), i + 1
            out.append(text[i])
            i += 1
        return "".join(out), i
    depth = 1
    i = start + 1
    out = []
    while i < len(text):
        ch = text[i]
        if ch == "{" and text[i - 1] != "\\":
            depth += 1
        elif ch == "}" and text[i - 1] != "\\":
            depth -= 1
            if depth == 0:
                return "".join(out), i + 1
        out.append(ch)
        i += 1
    return "".join(out), i


def _parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    pos = 0
    while True:
        match = FIELD_RE.search(body, pos)
        if not match:
            break
        value, pos = _balanced_value(body, match.end("value") - 1, match.group("value"))
        fields[match.group("name").lower()] = tex_to_text(value)
    return fields


def parse_bib(content: str) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    pos = 0
    while True:
        match = ENTRY_START_RE.search(content, pos)
        if not match:
            break
        depth = 1
        i = match.end()
        while i < len(content) and depth > 0:
            if content[i] == "{" and content[i - 1] != "\\":
                depth += 1
            elif content[i] == "}" and content[i - 1] != "\\":
                depth -= 1
            i += 1
        body = content[match.end() : i - 1]
        fields = _parse_fields(body)
        all_values = " ".join(fields.values())
        arxiv = ARXIV_ID_RE.search(all_values)
        key = match.group("key").strip()
        entries[key] = {
            "key": key,
            "type": match.group("type").lower(),
            "title": fields.get("title", ""),
            "authors": fields.get("author", ""),
            "year": fields.get("year", ""),
            "venue": fields.get("journal") or fields.get("booktitle", ""),
            "doi": fields.get("doi", ""),
            "arxiv_id": arxiv.group("id") if arxiv else "",
        }
        pos = i
    return entries


def parse_bbl(content: str) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for match in BBL_RE.finditer(content):
        key = match.group("key").strip()
        body = tex_to_text(match.group("body"))
        year = re.search(r"\b(19|20)\d{2}\b", body)
        arxiv = ARXIV_ID_RE.search(body)
        title = ""
        parts = [collapse_ws(p) for p in re.split(r"\.|\n", body) if collapse_ws(p)]
        if len(parts) > 1:
            title = parts[1]
        entries[key] = {
            "key": key,
            "type": "unknown",
            "title": title,
            "authors": parts[0] if parts else "",
            "year": year.group(0) if year else "",
            "venue": "",
            "doi": "",
            "arxiv_id": arxiv.group("id") if arxiv else "",
        }
    return entries


def resolve_references(package: dict[str, Any]) -> dict[str, Any]:
    entries: dict[str, dict[str, str]] = {}
    source = ""
    for name, content in package.get("bib_files", {}).items():
        parsed = parse_bib(content)
        if parsed:
            entries.update(parsed)
            source = source or name
    if not entries:
        for name, content in package.get("bbl_files", {}).items():
            parsed = parse_bbl(content)
            if parsed:
                entries.update(parsed)
                source = source or name
    return {"source": source, "entries": entries}
