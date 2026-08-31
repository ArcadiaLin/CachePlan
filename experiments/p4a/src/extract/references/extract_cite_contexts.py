#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/references/extract_cite_contexts.py /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_verified_plus_repaired.jsonl --output /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_cite_contexts.jsonl --summary /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_cite_contexts_summary.json
"""Extract citation contexts from MinerU Markdown and repaired references.

The input reference JSONL contains one paper per line. Each paper points to a
MinerU Markdown file through either ``markdown_path`` or ``source_dir``. This
script scans the body text before the References/Bibliography section, locates
author-year and numeric citation mentions, and links them back to reference
indexes when a conservative rule match is available.
"""

from __future__ import annotations

import argparse
import bisect
import difflib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]


def load_project_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def configured_data_root() -> Path:
    value = os.environ.get("P4A_DATA_ROOT")
    if value:
        return Path(value)
    value = os.environ.get("DATA_ROOT") or os.environ.get("DATASET_ROOT")
    if value:
        root = Path(value)
        return root if root.name == "data" else root / "data"
    return Path("/srv/datasets/p4a/data")


load_project_env()
DEFAULT_DATA_ROOT = configured_data_root()
DEFAULT_REFERENCES_JSONL = DEFAULT_DATA_ROOT / "processed/cite/2026/acl/acl2026_verified_plus_repaired.jsonl"
DEFAULT_OUTPUT_JSONL = DEFAULT_DATA_ROOT / "processed/cite/2026/acl/acl2026_cite_contexts.jsonl"
DEFAULT_SUMMARY_JSON = DEFAULT_DATA_ROOT / "processed/cite/2026/acl/acl2026_cite_contexts_summary.json"

REFERENCE_HEADING_RE = re.compile(
    r"(?im)^(?:#{1,6}\s*)?(references|bibliography|reference)\s*$"
)
HEADING_RE = re.compile(r"(?m)^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
PAREN_CITE_RE = re.compile(r"\((?P<inner>[^()\n]{0,700}(?:19|20)\d{2}[a-z]?[^()\n]{0,700})\)")
TEXTUAL_CITE_RE = re.compile(
    r"\b(?P<author>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+(?:et\s+al\.|and\s+"
    r"[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+))?)\s*\((?P<years>(?:19|20)\d{2}[a-z]?"
    r"(?:\s*[,;/]\s*(?:19|20)?\d{0,4}[a-z]?|\s*(?:and|&)\s*(?:19|20)\d{2}[a-z]?)*)\)"
)
NUMERIC_CITE_RE = re.compile(r"(?<!\!)\[(?P<numbers>\d+(?:\s*(?:,|-|–)\s*\d+)*)\]")
AUTHOR_YEAR_RE = re.compile(
    r"\b(?P<author>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+)(?:\s+et\s+al\.)?"
    r"(?:\s+and\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+)?\s*,?\s*"
    r"(?P<year>(?:19|20)\d{2}[a-z]?)"
)
YEAR_RE = re.compile(r"\b(?P<year>(?:19|20)\d{2}[a-z]?)\b")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9#])")


@dataclass(frozen=True)
class Paragraph:
    index: int
    text: str
    start: int
    end: int
    section: str


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(value: str) -> str:
    value = value.strip().replace("’", "'")
    value = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ'-]+", " ", value)
    return value.strip().lower()


def citation_author_surname(value: str) -> str:
    normalized = normalize_name(value)
    normalized = re.sub(r"\bet\s+al\b\.?", "", normalized).strip()
    normalized = re.sub(r"\b(?:and|&)\b.*$", "", normalized).strip()
    normalized = re.sub(r"'s$", "", normalized)
    tokens = normalized.split()
    return tokens[0] if tokens else ""


def first_author_surname(reference: dict[str, Any]) -> str:
    authors = str(reference.get("authors") or "").strip()
    raw = str(reference.get("raw") or "")
    source = authors or raw
    first = re.split(r"\s+(?:and|&)\s+|;", source, maxsplit=1)[0]
    first = first.split(",")[0]
    tokens = normalize_name(first).split()
    return tokens[-1] if tokens else ""


def base_year(year: str) -> str:
    year = year.strip().lower()
    match = re.match(r"((?:19|20)\d{2})", year)
    return match.group(1) if match else year


def has_year_suffix(year: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)\d{2}[a-z]", year.strip().lower()))


def build_reference_lookup(
    references: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], list[int]], dict[tuple[str, str], list[int]], dict[str, set[str]], set[int]]:
    exact_lookup: dict[tuple[str, str], list[int]] = {}
    base_lookup: dict[tuple[str, str], list[int]] = {}
    surnames_by_base_year: dict[str, set[str]] = {}
    numeric: set[int] = set()
    for ref in references:
        try:
            index = int(ref.get("index"))
        except (TypeError, ValueError):
            continue
        numeric.add(index)
        surname = first_author_surname(ref)
        if not surname:
            continue
        year = str(ref.get("year") or "").strip().lower()
        if not year:
            continue
        base = base_year(year)
        exact_lookup.setdefault((surname, year), []).append(index)
        base_lookup.setdefault((surname, base), []).append(index)
        surnames_by_base_year.setdefault(base, set()).add(surname)
    return exact_lookup, base_lookup, surnames_by_base_year, numeric


def resolve_data_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    repo_path = REPO_ROOT / path
    if repo_path.exists():
        return repo_path
    parts = path.parts
    if parts and parts[0] == "data":
        return DEFAULT_DATA_ROOT.joinpath(*parts[1:])
    return repo_path


def markdown_path_for_record(record: dict[str, Any]) -> Path | None:
    markdown_path = record.get("markdown_path")
    if markdown_path:
        path = resolve_data_path(str(markdown_path))
        if path.exists():
            return path
    source_dir = record.get("source_dir")
    paper_id = record.get("paper_id")
    if source_dir and paper_id:
        path = resolve_data_path(str(source_dir)) / f"{paper_id}.md"
        if path.exists():
            return path
    return None


def body_before_references(markdown: str) -> str:
    match = REFERENCE_HEADING_RE.search(markdown)
    if match:
        return markdown[: match.start()]
    return markdown


def line_starts(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    return starts


def line_number(starts: list[int], char_index: int) -> int:
    return bisect.bisect_right(starts, char_index)


def paragraphs_with_spans(text: str) -> list[Paragraph]:
    headings = list(HEADING_RE.finditer(text))
    heading_idx = 0
    current_section = ""
    paragraphs: list[Paragraph] = []
    for index, match in enumerate(re.finditer(r"\S(?:.*?(?:\n\s*\n|$))", text, flags=re.DOTALL), start=1):
        start, end = match.span()
        while heading_idx < len(headings) and headings[heading_idx].start() <= start:
            current_section = normalize_ws(headings[heading_idx].group("title"))
            heading_idx += 1
        raw = match.group(0).strip()
        if not raw or raw.startswith("#"):
            continue
        paragraphs.append(Paragraph(index=len(paragraphs) + 1, text=raw, start=start, end=end, section=current_section))
    return paragraphs


def sentence_for_span(paragraph: str, start: int, end: int) -> str:
    boundaries = [0]
    boundaries.extend(match.end() for match in SENTENCE_BOUNDARY_RE.finditer(paragraph))
    boundaries.append(len(paragraph))
    sent_start = 0
    sent_end = len(paragraph)
    for left, right in zip(boundaries, boundaries[1:]):
        if left <= start < right:
            sent_start = left
            sent_end = right
            break
    if end > sent_end:
        sent_end = min(len(paragraph), end + 240)
    return normalize_ws(paragraph[sent_start:sent_end])


def match_author_year(
    author: str,
    year: str,
    exact_lookup: dict[tuple[str, str], list[int]],
    base_lookup: dict[tuple[str, str], list[int]],
    surnames_by_base_year: dict[str, set[str]],
) -> tuple[list[int], str, str]:
    surname_key = citation_author_surname(author)
    year_key = year.strip().lower()
    base = base_year(year_key)
    if not surname_key or not base:
        return [], "unresolved", surname_key

    if has_year_suffix(year_key):
        exact_matches = exact_lookup.get((surname_key, year_key), [])
        if exact_matches:
            return sorted(set(exact_matches)), "exact_author_year", surname_key

    base_matches = base_lookup.get((surname_key, base), [])
    if base_matches:
        method = "base_year_fallback" if has_year_suffix(year_key) else "base_author_year"
        return sorted(set(base_matches)), method, surname_key

    if len(surname_key) >= 5:
        close_surnames = difflib.get_close_matches(
            surname_key,
            sorted(surnames_by_base_year.get(base, set())),
            n=3,
            cutoff=0.9,
        )
        fuzzy_matches: list[int] = []
        for close_surname in close_surnames:
            fuzzy_matches.extend(base_lookup.get((close_surname, base), []))
        if fuzzy_matches:
            return sorted(set(fuzzy_matches)), "fuzzy_author_base_year", ",".join(close_surnames)

    return [], "unresolved", surname_key


def parse_parenthetical(
    inner: str,
    exact_lookup: dict[tuple[str, str], list[int]],
    base_lookup: dict[tuple[str, str], list[int]],
    surnames_by_base_year: dict[str, set[str]],
) -> tuple[list[int], list[dict[str, Any]], list[dict[str, Any]]]:
    matched: list[int] = []
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    last_author = ""
    for part in re.split(r";", inner):
        part = part.strip()
        if not part:
            continue
        local_matches = list(AUTHOR_YEAR_RE.finditer(part))
        if local_matches:
            for match in local_matches:
                author = match.group("author")
                year = match.group("year")
                last_author = author
                indexes, method, matched_author = match_author_year(
                    author, year, exact_lookup, base_lookup, surnames_by_base_year
                )
                if indexes:
                    matched.extend(indexes)
                    resolved.append(
                        {
                            "author": author,
                            "year": year,
                            "matched_author": matched_author,
                            "reference_indices": indexes,
                            "match_method": method,
                        }
                    )
                else:
                    unresolved.append({"author": author, "year": year, "normalized_author": matched_author})
            tail_start = local_matches[-1].end()
            tail = part[tail_start:]
            for year_match in YEAR_RE.finditer(tail):
                year = year_match.group("year")
                indexes, method, matched_author = (
                    match_author_year(last_author, year, exact_lookup, base_lookup, surnames_by_base_year)
                    if last_author
                    else ([], "unresolved", "")
                )
                if indexes:
                    matched.extend(indexes)
                    resolved.append(
                        {
                            "author": last_author,
                            "year": year,
                            "matched_author": matched_author,
                            "reference_indices": indexes,
                            "match_method": method,
                        }
                    )
                else:
                    unresolved.append({"author": last_author, "year": year, "normalized_author": matched_author})
        elif last_author:
            for year_match in YEAR_RE.finditer(part):
                year = year_match.group("year")
                indexes, method, matched_author = match_author_year(
                    last_author, year, exact_lookup, base_lookup, surnames_by_base_year
                )
                if indexes:
                    matched.extend(indexes)
                    resolved.append(
                        {
                            "author": last_author,
                            "year": year,
                            "matched_author": matched_author,
                            "reference_indices": indexes,
                            "match_method": method,
                        }
                    )
                else:
                    unresolved.append({"author": last_author, "year": year, "normalized_author": matched_author})
    return sorted(set(matched)), resolved, unresolved


def parse_textual(
    match: re.Match[str],
    exact_lookup: dict[tuple[str, str], list[int]],
    base_lookup: dict[tuple[str, str], list[int]],
    surnames_by_base_year: dict[str, set[str]],
) -> tuple[list[int], list[dict[str, Any]], list[dict[str, Any]]]:
    author = match.group("author")
    years = [year_match.group("year") for year_match in YEAR_RE.finditer(match.group("years"))]
    matched: list[int] = []
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for year in years:
        indexes, method, matched_author = match_author_year(
            author, year, exact_lookup, base_lookup, surnames_by_base_year
        )
        if indexes:
            matched.extend(indexes)
            resolved.append(
                {
                    "author": author,
                    "year": year,
                    "matched_author": matched_author,
                    "reference_indices": indexes,
                    "match_method": method,
                }
            )
        else:
            unresolved.append({"author": author, "year": year, "normalized_author": matched_author})
    return sorted(set(matched)), resolved, unresolved


def expand_numeric_citation(numbers: str, valid_indices: set[int]) -> list[int]:
    matched: set[int] = set()
    for part in re.split(r"\s*,\s*", numbers.strip()):
        if not part:
            continue
        range_match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
        if range_match:
            left, right = int(range_match.group(1)), int(range_match.group(2))
            if left <= right and right - left <= 50:
                matched.update(index for index in range(left, right + 1) if index in valid_indices)
            continue
        try:
            value = int(part)
        except ValueError:
            continue
        if value in valid_indices:
            matched.add(value)
    return sorted(matched)


def should_keep_citation(raw: str, matched_indices: list[int], unresolved: list[dict[str, str]]) -> bool:
    if matched_indices:
        return True
    if unresolved and len(raw) <= 500:
        return True
    return False


def make_context(
    *,
    paper_id: str,
    paragraph: Paragraph,
    mention_index: int,
    style: str,
    raw: str,
    relative_start: int,
    relative_end: int,
    matched_indices: list[int],
    resolved: list[dict[str, Any]],
    unresolved: list[dict[str, str]],
    starts: list[int],
) -> dict[str, Any]:
    absolute_start = paragraph.start + relative_start
    absolute_end = paragraph.start + relative_end
    before = paragraph.text[max(0, relative_start - 240) : relative_start]
    after = paragraph.text[relative_end : min(len(paragraph.text), relative_end + 240)]
    return {
        "context_id": f"{paper_id}::cite::{mention_index}",
        "mention_index": mention_index,
        "citation_style": style,
        "raw_citation": raw,
        "matched_reference_indices": matched_indices,
        "resolved_citation_keys": resolved,
        "unresolved_citation_keys": unresolved,
        "section": paragraph.section,
        "paragraph_index": paragraph.index,
        "char_start": absolute_start,
        "char_end": absolute_end,
        "line_start": line_number(starts, absolute_start),
        "line_end": line_number(starts, absolute_end),
        "relative_start": relative_start,
        "relative_end": relative_end,
        "before": normalize_ws(before),
        "after": normalize_ws(after),
        "sentence": sentence_for_span(paragraph.text, relative_start, relative_end),
        "paragraph": normalize_ws(paragraph.text),
    }


def build_reference_contexts(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_reference: dict[int, dict[str, Any]] = {}
    for context in contexts:
        for reference_index in context.get("matched_reference_indices", []):
            bucket = by_reference.setdefault(
                int(reference_index),
                {
                    "reference_index": int(reference_index),
                    "citation_count": 0,
                    "context_ids": [],
                    "mention_indices": [],
                    "raw_citations": [],
                },
            )
            bucket["citation_count"] += 1
            bucket["context_ids"].append(context["context_id"])
            bucket["mention_indices"].append(context["mention_index"])
            bucket["raw_citations"].append(context["raw_citation"])
    return [by_reference[index] for index in sorted(by_reference)]


def extract_contexts_for_record(record: dict[str, Any]) -> dict[str, Any]:
    paper_id = str(record.get("paper_id"))
    references = record.get("references") or []
    markdown_path = markdown_path_for_record(record)
    result: dict[str, Any] = {
        "paper_id": paper_id,
        "source_dir": record.get("source_dir"),
        "markdown_path": display_path(markdown_path) if markdown_path else "",
        "reference_count": len(references),
        "citation_context_count": 0,
        "citation_contexts": [],
        "reference_contexts": [],
        "warnings": [],
    }
    if not markdown_path:
        result["warnings"].append("markdown file not found")
        return result

    markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
    body = body_before_references(markdown)
    starts = line_starts(body)
    exact_lookup, base_lookup, surnames_by_base_year, valid_numeric_indices = build_reference_lookup(references)
    contexts: list[dict[str, Any]] = []
    mention_index = 0

    for paragraph in paragraphs_with_spans(body):
        occupied: list[tuple[int, int]] = []
        for match in TEXTUAL_CITE_RE.finditer(paragraph.text):
            matched, resolved, unresolved = parse_textual(match, exact_lookup, base_lookup, surnames_by_base_year)
            if not should_keep_citation(match.group(0), matched, unresolved):
                continue
            mention_index += 1
            occupied.append(match.span())
            contexts.append(
                make_context(
                    paper_id=paper_id,
                    paragraph=paragraph,
                    mention_index=mention_index,
                    style="textual_author_year",
                    raw=match.group(0),
                    relative_start=match.start(),
                    relative_end=match.end(),
                    matched_indices=matched,
                    resolved=resolved,
                    unresolved=unresolved,
                    starts=starts,
                )
            )

        for match in PAREN_CITE_RE.finditer(paragraph.text):
            if any(left <= match.start() < right for left, right in occupied):
                continue
            matched, resolved, unresolved = parse_parenthetical(
                match.group("inner"), exact_lookup, base_lookup, surnames_by_base_year
            )
            if not should_keep_citation(match.group(0), matched, unresolved):
                continue
            mention_index += 1
            contexts.append(
                make_context(
                    paper_id=paper_id,
                    paragraph=paragraph,
                    mention_index=mention_index,
                    style="parenthetical_author_year",
                    raw=match.group(0),
                    relative_start=match.start(),
                    relative_end=match.end(),
                    matched_indices=matched,
                    resolved=resolved,
                    unresolved=unresolved,
                    starts=starts,
                )
            )

        for match in NUMERIC_CITE_RE.finditer(paragraph.text):
            if any(left <= match.start() < right for left, right in occupied):
                continue
            matched = expand_numeric_citation(match.group("numbers"), valid_numeric_indices)
            if not matched:
                continue
            mention_index += 1
            contexts.append(
                make_context(
                    paper_id=paper_id,
                    paragraph=paragraph,
                    mention_index=mention_index,
                    style="numeric",
                    raw=match.group(0),
                    relative_start=match.start(),
                    relative_end=match.end(),
                    matched_indices=matched,
                    resolved=[
                        {
                            "author": "",
                            "year": "",
                            "matched_author": "",
                            "reference_indices": matched,
                            "match_method": "numeric_reference_index",
                        }
                    ],
                    unresolved=[],
                    starts=starts,
                )
            )

    contexts.sort(key=lambda row: (row["char_start"], row["char_end"]))
    for index, context in enumerate(contexts, start=1):
        context["mention_index"] = index
        context["context_id"] = f"{paper_id}::cite::{index}"
    result["citation_contexts"] = contexts
    result["citation_context_count"] = len(contexts)
    result["reference_contexts"] = build_reference_contexts(contexts)
    result["cited_reference_count"] = len(result["reference_contexts"])
    if not contexts and references:
        result["warnings"].append("no citation contexts found before references section")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract citation contexts from MinerU Markdown.")
    parser.add_argument("references_jsonl", type=Path, nargs="?", default=DEFAULT_REFERENCES_JSONL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_JSON)
    parser.add_argument("--paper-id", action="append", help="Limit to one paper id; repeatable.")
    parser.add_argument("--limit", type=int, help="Process only the first N selected records.")
    return parser


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    args = build_parser().parse_args()
    selected_ids = set(args.paper_id or []) if args.paper_id else None
    records = load_jsonl(args.references_jsonl)
    if selected_ids is not None:
        records = [record for record in records if record.get("paper_id") in selected_ids]
    if args.limit:
        records = records[: args.limit]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    with args.output.open("w", encoding="utf-8") as stream:
        for index, record in enumerate(records, start=1):
            result = extract_contexts_for_record(record)
            results.append(result)
            stream.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
            print(
                f"[{index}/{len(records)}] {result['paper_id']} contexts={result['citation_context_count']}",
                flush=True,
            )

    context_count = sum(row["citation_context_count"] for row in results)
    matched_mentions = sum(
        1 for row in results for context in row["citation_contexts"] if context["matched_reference_indices"]
    )
    unresolved_mentions = sum(
        1 for row in results for context in row["citation_contexts"] if context["unresolved_citation_keys"]
    )
    summary = {
        "paper_count": len(results),
        "papers_with_contexts": sum(1 for row in results if row["citation_context_count"]),
        "citation_context_count": context_count,
        "matched_mentions": matched_mentions,
        "unresolved_mentions": unresolved_mentions,
        "output": display_path(args.output),
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
