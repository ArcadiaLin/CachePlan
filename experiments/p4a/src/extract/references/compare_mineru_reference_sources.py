#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/references/compare_mineru_reference_sources.py /srv/datasets/p4a/data/processed/mineru/acl/2026/acl --trusted-output /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_verified_references.jsonl --mismatch-output /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_reference_mismatches.jsonl --summary /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_reference_comparison_summary.json
"""Compare MinerU reference extraction from content_list JSON and Markdown.

This audit script treats Markdown as an independent verifier for the primary
``*_content_list.json`` extraction. A paper is trusted only when both sources
produce the same repaired reference sequence after conservative normalization.
Mismatches are written separately for manual analysis.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from extract_mineru_references import (
    DEFAULT_ROOT,
    Reference,
    display_path,
    extract_candidates_from_content_list,
    extract_candidates_from_markdown,
    find_related_files,
    iter_vlm_dirs,
    normalize_text,
    parse_reference,
    split_and_repair_references,
)


MAX_DIFF_SAMPLES = 5


@dataclass
class SourceExtraction:
    source: str
    path: str | None
    candidates_count: int
    reference_count: int
    references: list[Reference]
    warnings: list[str] = field(default_factory=list)


@dataclass
class FirstDifference:
    content_index: int | None
    markdown_index: int | None
    content: str | None
    markdown: str | None


@dataclass
class ComparisonRecord:
    paper_id: str
    source_dir: str
    status: str
    content_list: SourceExtraction
    markdown: SourceExtraction
    warnings: list[str] = field(default_factory=list)
    first_difference: FirstDifference | None = None
    content_only: list[str] = field(default_factory=list)
    markdown_only: list[str] = field(default_factory=list)


def canonical_reference(text: str) -> str:
    """Normalize harmless rendering differences before source comparison."""
    text = normalize_text(text)
    text = text.replace("\\", "")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([([{])\s+", r"\1", text)
    text = re.sub(r"\s+([)\]}])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().rstrip()


def extract_source(
    source: str,
    path: Path | None,
    extractor,
) -> tuple[SourceExtraction, list[str]]:
    warnings: list[str] = []
    candidates: list[str] = []

    if path is None:
        warnings.append(f"missing {source} file")
    else:
        candidates, warnings = extractor(path)

    raw_entries, repair_warnings = split_and_repair_references(candidates)
    warnings.extend(repair_warnings)
    references = [
        parse_reference(idx, raw, source) for idx, raw in enumerate(raw_entries, start=1)
    ]
    source_warnings = warnings.copy()
    for reference in references:
        for warning in reference.warnings:
            source_warnings.append(f"reference {reference.index}: {warning}")

    return (
        SourceExtraction(
            source=source,
            path=display_path(path) if path else None,
            candidates_count=len(candidates),
            reference_count=len(references),
            references=references,
            warnings=source_warnings,
        ),
        raw_entries,
    )


def find_first_difference(content: list[str], markdown: list[str]) -> FirstDifference | None:
    max_len = max(len(content), len(markdown))
    for idx in range(max_len):
        content_value = content[idx] if idx < len(content) else None
        markdown_value = markdown[idx] if idx < len(markdown) else None
        if content_value != markdown_value:
            return FirstDifference(
                content_index=idx + 1 if content_value is not None else None,
                markdown_index=idx + 1 if markdown_value is not None else None,
                content=content_value,
                markdown=markdown_value,
            )
    return None


def unmatched_samples(left: list[str], right: list[str]) -> list[str]:
    matcher = difflib.SequenceMatcher(a=left, b=right, autojunk=False)
    samples: list[str] = []
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag in {"delete", "replace"}:
            samples.extend(left[i1:i2])
        if len(samples) >= MAX_DIFF_SAMPLES:
            break
    return samples[:MAX_DIFF_SAMPLES]


def compare_paper(vlm_dir: Path) -> ComparisonRecord:
    paper_id, content_path, md_path = find_related_files(vlm_dir)
    content_source, content_raw = extract_source(
        "content_list", content_path, extract_candidates_from_content_list
    )
    markdown_source, markdown_raw = extract_source(
        "markdown", md_path, extract_candidates_from_markdown
    )

    content_keys = [canonical_reference(raw) for raw in content_raw]
    markdown_keys = [canonical_reference(raw) for raw in markdown_raw]
    warnings: list[str] = []
    status = "match"
    first_difference = None
    content_only: list[str] = []
    markdown_only: list[str] = []

    if not content_keys:
        status = "missing_content_list_references"
        warnings.append("content_list produced no references")
    if not markdown_keys:
        status = "missing_markdown_references"
        warnings.append("markdown produced no references")
    if content_keys and markdown_keys and content_keys != markdown_keys:
        status = "mismatch"
        if len(content_keys) != len(markdown_keys):
            warnings.append(
                f"reference count differs: content_list={len(content_keys)}, markdown={len(markdown_keys)}"
            )
        first_difference = find_first_difference(content_keys, markdown_keys)
        content_only = unmatched_samples(content_keys, markdown_keys)
        markdown_only = unmatched_samples(markdown_keys, content_keys)

    return ComparisonRecord(
        paper_id=paper_id,
        source_dir=display_path(vlm_dir),
        status=status,
        content_list=content_source,
        markdown=markdown_source,
        warnings=warnings,
        first_difference=first_difference,
        content_only=content_only,
        markdown_only=markdown_only,
    )


def comparison_to_jsonable(record: ComparisonRecord, include_references: bool) -> dict:
    payload = asdict(record)
    if not include_references:
        payload["content_list"].pop("references", None)
        payload["markdown"].pop("references", None)
    return payload


def trusted_record(record: ComparisonRecord) -> dict:
    references = record.content_list.references
    return {
        "paper_id": record.paper_id,
        "source_dir": record.source_dir,
        "source": "content_list_verified_by_markdown",
        "references": [asdict(reference) for reference in references],
        "reference_count": len(references),
        "content_list_path": record.content_list.path,
        "markdown_path": record.markdown.path,
        "content_list_warnings": record.content_list.warnings,
        "markdown_warnings": record.markdown.warnings,
    }


def write_jsonl(rows: Iterable[dict], path: Path | None) -> None:
    stream = path.open("w", encoding="utf-8") if path else sys.stdout
    try:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        if path:
            stream.close()


def write_summary(records: list[ComparisonRecord], path: Path) -> None:
    status_counts: dict[str, int] = {}
    for record in records:
        status_counts[record.status] = status_counts.get(record.status, 0) + 1

    mismatches = [record for record in records if record.status != "match"]
    issue_category_counts: dict[str, int] = {}
    problem_papers = []
    for record in mismatches:
        category = classify_issue(record)
        issue_category_counts[category] = issue_category_counts.get(category, 0) + 1
        problem_papers.append(
            {
                "paper_id": record.paper_id,
                "status": record.status,
                "issue_category": category,
                "content_list_count": record.content_list.reference_count,
                "markdown_count": record.markdown.reference_count,
                "warnings": record.warnings,
                "first_difference": asdict(record.first_difference)
                if record.first_difference
                else None,
            }
        )

    payload = {
        "paper_count": len(records),
        "trusted_count": status_counts.get("match", 0),
        "status_counts": status_counts,
        "issue_category_counts": issue_category_counts,
        "problem_paper_ids": [record.paper_id for record in mismatches],
        "problem_papers": problem_papers,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def classify_issue(record: ComparisonRecord) -> str:
    if record.status != "mismatch":
        return record.status

    first_difference = record.first_difference
    markdown = first_difference.markdown if first_difference else ""
    content = first_difference.content if first_difference else ""
    markdown = markdown or ""
    content = content or ""

    if any(token in markdown for token in ("Figure ", "Table ", "Algorithm ", "Appendix ", "A Appendix")):
        return "markdown_absorbed_non_reference_blocks"
    if record.content_list.reference_count != record.markdown.reference_count:
        return "reference_count_diff"
    if content.replace("- ", "") == markdown or content.replace(" ", "") == markdown.replace(" ", ""):
        return "hyphenation_or_spacing_only"
    return "text_diff_other"


def resolve_input(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path
    repo_relative = Path(__file__).resolve().parents[3] / path
    if repo_relative.exists():
        return repo_relative
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify MinerU content_list reference extraction against Markdown extraction."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help="ACL MinerU root, a paper directory, a vlm directory, or one MinerU file.",
    )
    parser.add_argument(
        "--trusted-output",
        type=Path,
        help="Write trusted content_list records whose Markdown extraction matches.",
    )
    parser.add_argument(
        "--mismatch-output",
        type=Path,
        help="Write non-matching comparison records as JSONL. Defaults to stdout.",
    )
    parser.add_argument("--summary", type=Path, help="Write aggregate comparison summary JSON.")
    parser.add_argument("--limit", type=int, help="Only process the first N vlm directories.")
    parser.add_argument("--paper-id", action="append", help="Only process this paper id. May be repeated.")
    parser.add_argument(
        "--include-references",
        action="store_true",
        help="Include full parsed references in mismatch JSONL.",
    )
    parser.add_argument(
        "--all-comparisons",
        action="store_true",
        help="Write all comparison records to mismatch-output/stdout, not just non-matches.",
    )
    args = parser.parse_args()

    input_path = resolve_input(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {args.input}")

    paper_ids = set(args.paper_id or [])
    vlm_dirs: list[Path] = []
    for vlm_dir in iter_vlm_dirs(input_path):
        paper_id = vlm_dir.parent.name
        if paper_ids and paper_id not in paper_ids:
            continue
        vlm_dirs.append(vlm_dir)
        if args.limit and len(vlm_dirs) >= args.limit:
            break

    records = [compare_paper(vlm_dir) for vlm_dir in vlm_dirs]
    trusted = [record for record in records if record.status == "match"]
    selected = records if args.all_comparisons else [record for record in records if record.status != "match"]

    if args.trusted_output:
        args.trusted_output.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl((trusted_record(record) for record in trusted), args.trusted_output)

    if args.mismatch_output:
        args.mismatch_output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(
        (comparison_to_jsonable(record, args.include_references) for record in selected),
        args.mismatch_output,
    )

    if args.summary:
        write_summary(records, args.summary)


if __name__ == "__main__":
    main()
