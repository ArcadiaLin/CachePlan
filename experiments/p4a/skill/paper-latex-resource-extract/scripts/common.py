#!/usr/bin/env python3
"""
LaTeX 论文与资源抽取脚本公共工具函数。

用途:
    被其他脚本 import，提供 arXiv id 提取、TeX 文本清洗、括号匹配、
    JSON 写入等通用能力。

直接调用:
    不建议直接运行；请通过 parse_one.py / parse_batch.py / yaml_linter.py 使用。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ARXIV_ID_RE = re.compile(r"(?P<id>\d{4}\.\d{4,5})(?:v\d+)?")


def arxiv_id_from_path(path: str | Path) -> str:
    match = ARXIV_ID_RE.search(Path(path).name)
    return match.group("id") if match else Path(path).stem.replace(".tar", "")


def strip_tex_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
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


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def read_balanced_braces(text: str, open_brace: int) -> tuple[str, int] | None:
    if open_brace >= len(text) or text[open_brace] != "{":
        return None
    depth = 0
    out: list[str] = []
    i = open_brace
    while i < len(text):
        ch = text[i]
        escaped = i > 0 and text[i - 1] == "\\"
        if ch == "{" and not escaped:
            depth += 1
            if depth > 1:
                out.append(ch)
        elif ch == "}" and not escaped:
            depth -= 1
            if depth == 0:
                return "".join(out), i + 1
            out.append(ch)
        else:
            out.append(ch)
        i += 1
    return None


def find_command_arg(text: str, command: str) -> str:
    match = re.search(rf"\\{re.escape(command)}(?:\[[^\]]*\])?\s*\{{", text, re.DOTALL)
    if not match:
        return ""
    parsed = read_balanced_braces(text, match.end() - 1)
    return parsed[0] if parsed else ""


def find_environment(text: str, env: str) -> str:
    match = re.search(
        rf"\\begin\{{{re.escape(env)}\}}(?P<body>.*?)\\end\{{{re.escape(env)}\}}",
        text,
        re.DOTALL,
    )
    return match.group("body") if match else ""


def tex_to_text(text: str) -> str:
    text = text or ""
    replacements = [
        (r"\\href\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\2 (\1)"),
        (r"\\url\s*\{([^{}]*)\}", r"\1"),
        (r"\\texttt\s*\{([^{}]*)\}", r"\1"),
        (r"\\textbf\s*\{([^{}]*)\}", r"\1"),
        (r"\\emph\s*\{([^{}]*)\}", r"\1"),
        (r"\\textit\s*\{([^{}]*)\}", r"\1"),
        (r"\\textcolor\s*\{[^{}]*\}\s*\{([^{}]*)\}", r"\1"),
    ]
    previous = None
    while previous != text:
        previous = text
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text, flags=re.DOTALL)
    text = re.sub(r"\$+", "", text)
    text = re.sub(r"~", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"\\.", " ", text)
    text = text.replace("{", "").replace("}", "")
    return collapse_ws(text)


def make_id(prefix: str, name: str) -> str:
    slug = tex_to_text(name).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"{prefix}::{slug or 'unknown'}"


def write_json(path: Path, data: Any) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
