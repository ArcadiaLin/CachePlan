#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/references/update_reference_record.py /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/<paper_id>/references.jsonl --paper-id <paper_id> --record-file /tmp/<paper_id>.json
"""Replace one paper record in a reference JSONL result file.

Agents should use this after manually repairing a paper's references. The input
record must be a complete JSON object with the same ``paper_id``.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_record(path: Path | None) -> dict[str, Any]:
    if path is None:
        raw = input()
    else:
        raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise SystemExit("Replacement record must be a JSON object.")
    return value


def replace_record(
    jsonl_path: Path,
    paper_id: str,
    replacement: dict[str, Any],
    append: bool,
) -> tuple[int, bool]:
    if replacement.get("paper_id") != paper_id:
        raise SystemExit(
            f"Replacement paper_id {replacement.get('paper_id')!r} does not match {paper_id!r}."
        )
    if not jsonl_path.exists():
        raise SystemExit(f"Target JSONL file does not exist: {jsonl_path}")

    replaced = False
    total = 0
    output_lines: list[str] = []
    replacement_line = json.dumps(replacement, ensure_ascii=False, separators=(",", ":")) + "\n"

    with jsonl_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSON on line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise SystemExit(f"Line {line_number} is not a JSON object.")
            if record.get("paper_id") == paper_id:
                output_lines.append(replacement_line)
                replaced = True
            else:
                output_lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            total += 1

    if not replaced:
        if not append:
            raise SystemExit(f"Paper {paper_id!r} not found in {jsonl_path}. Use --append to add it.")
        output_lines.append(replacement_line)
        total += 1

    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{jsonl_path.name}.",
        suffix=".tmp",
        dir=jsonl_path.parent,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.writelines(output_lines)
        os.replace(tmp_name, jsonl_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)

    return total, replaced


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace one paper record in a JSONL result file.")
    parser.add_argument("jsonl", type=Path, help="Target JSONL result file to update in place.")
    parser.add_argument("--paper-id", required=True, help="Paper id to replace.")
    parser.add_argument(
        "--record-file",
        type=Path,
        help="JSON file containing the full replacement record. Defaults to one JSON line on stdin.",
    )
    parser.add_argument("--append", action="store_true", help="Append the record if paper-id is absent.")
    args = parser.parse_args()

    replacement = load_record(args.record_file)
    total, replaced = replace_record(args.jsonl, args.paper_id, replacement, args.append)
    action = "replaced" if replaced else "appended"
    print(f"{action} {args.paper_id} in {args.jsonl} ({total} records)")


if __name__ == "__main__":
    main()
