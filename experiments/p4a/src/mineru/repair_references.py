#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/mineru/repair_references.py /srv/datasets/p4a/data/processed/mineru/acl/2026/acl/<paper_id>/vlm/<paper_id>.md --json-out /tmp/<paper_id>.references.json
"""Extract and lightly repair references from MinerU Markdown output."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


REFERENCE_HEADING_RE = re.compile(
    r"(?ms)^#\s*(?:References|Bibliography)\s*$\n(?P<body>.*?)(?=^#\s+\S|\Z)"
)
YEAR_RE = re.compile(r"\b(?:18|19|20)\d{2}[a-z]?\.")
START_RE = re.compile(r"^(?:\d{2}\.[A-Z]|[A-Z][\w.'’-]*|[A-Z]\.)", re.UNICODE)


def extract_reference_body(markdown: str) -> str:
    match = REFERENCE_HEADING_RE.search(markdown)
    if not match:
        raise ValueError("No '# References' or '# Bibliography' section found.")
    return match.group("body")


def normalize_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"\s{2,}$", "", line)
    line = re.sub(r"\\([_*])", r"\1", line)
    line = re.sub(r"\s+", " ", line)
    return line


def looks_like_reference_start(line: str) -> bool:
    return bool(START_RE.match(line))


def looks_complete_reference(text: str) -> bool:
    return bool(YEAR_RE.search(text) and re.search(r"[.!?。)]\s*$", text))


def join_reference_lines(left: str, right: str) -> str:
    if not left:
        return right
    # MinerU/OCR may preserve PDF line-end hyphenation: "inher-\nent".
    if re.search(r"[A-Za-z]-$", left) and re.match(r"^[a-z]", right):
        return left[:-1] + right
    return f"{left} {right}"


def split_references(reference_body: str) -> list[str]:
    lines: list[tuple[str, bool]] = []
    for raw_line in reference_body.splitlines():
        line = normalize_line(raw_line)
        lines.append((line, not line))

    entries: list[str] = []
    current = ""
    blank_before = True

    for line, is_blank in lines:
        if is_blank:
            blank_before = True
            continue

        starts_new = bool(current) and looks_like_reference_start(line) and (
            blank_before or looks_complete_reference(current)
        )
        if starts_new:
            entries.append(current.strip())
            current = line
        else:
            current = join_reference_lines(current, line)
        blank_before = False

    if current.strip():
        entries.append(current.strip())

    return [re.sub(r"\s+", " ", entry).strip() for entry in entries]


def parse_reference(entry: str) -> dict[str, str]:
    year_match = YEAR_RE.search(entry)
    if not year_match:
        return {"raw": entry, "authors": "", "year": "", "title": ""}

    authors = entry[: year_match.start()].strip(" .")
    year = year_match.group(0).rstrip(".")
    rest = entry[year_match.end() :].strip()
    title = rest.split(". ", 1)[0].strip(" .") if rest else ""

    return {
        "raw": entry,
        "authors": authors,
        "year": year,
        "title": title,
    }


def format_markdown(entries: Iterable[str]) -> str:
    return "# References\n\n" + "\n\n".join(entries).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract and lightly repair a References section from MinerU Markdown."
    )
    parser.add_argument("markdown", type=Path, help="MinerU-generated Markdown file.")
    parser.add_argument("--json-out", type=Path, help="Write parsed references as JSON.")
    parser.add_argument("--md-out", type=Path, help="Write repaired references as Markdown.")
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print repaired references to stdout.",
    )
    args = parser.parse_args()

    markdown = args.markdown.read_text(encoding="utf-8")
    entries = split_references(extract_reference_body(markdown))
    parsed = [parse_reference(entry) for entry in entries]

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(format_markdown(entries), encoding="utf-8")

    if args.print or not (args.json_out or args.md_out):
        print(format_markdown(entries), end="")

    print(f"Extracted {len(entries)} references.", flush=True)


if __name__ == "__main__":
    main()
