#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/references/extract_mineru_references.py /srv/datasets/p4a/data/processed/mineru/acl/2026/acl --output /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_references.jsonl --summary /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_references_summary.json
"""Extract ACL-style references from MinerU outputs.

The extractor is intentionally conservative:

1. Prefer ``*_content_list.json`` because MinerU preserves reference-list
   structure there as ``type=list, sub_type=ref_text`` with ``list_items``.
2. Stop at the next top-level heading after ``References``/``Bibliography`` so
   appendices are not mixed into the bibliography.
3. Use Markdown only as a fallback and as a count-level cross-check.

The output is JSONL by default, one paper record per line.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


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


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


load_project_env()
DEFAULT_DATA_ROOT = configured_data_root()
DEFAULT_ROOT = DEFAULT_DATA_ROOT / "processed/mineru/acl/2026/acl"

HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?\s*)?"
    r"(?:references?|bibliography|works\s+cited)\s*$",
    re.IGNORECASE,
)
NEXT_SECTION_RE = re.compile(r"^\s*(?:appendix|appendices|[A-Z]\b|[A-Z]\s+|[0-9]+(?:\.[0-9]+)*\s+)")
YEAR_RE = re.compile(r"\b((?:18|19|20)\d{2}[a-z]?)\b")
REFERENCE_START_RE = re.compile(
    r"^\s*(?:\[\d+\]\s*|\d+\.\s*)?"
    r"(?:[A-Z]\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'`’.-]+|[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'`’.-]+|[A-Z]\.|[a-z][A-Za-z.-]*\.)"
)
URL_RE = re.compile(r"https?://[^\s,;)>\]]+")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
ARXIV_RE = re.compile(r"\barXiv\s*[:：]?\s*(\d{4}\.\d{4,5}(?:v\d+)?)\b", re.IGNORECASE)


@dataclass
class Reference:
    index: int
    raw: str
    authors: str = ""
    year: str = ""
    title: str = ""
    arxiv_ids: list[str] = field(default_factory=list)
    dois: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    confidence: str = "medium"
    warnings: list[str] = field(default_factory=list)


@dataclass
class PaperExtraction:
    paper_id: str
    source_dir: str
    source: str
    references: list[Reference]
    markdown_reference_count: int | None = None
    warnings: list[str] = field(default_factory=list)


def normalize_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"\\([_*#])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def join_fragments(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]-$", left) and re.match(r"^[a-zà-öø-ÿ]", right):
        return left[:-1] + right
    return f"{left} {right}"


def is_reference_heading(text: str) -> bool:
    return bool(HEADING_RE.match(normalize_text(text).rstrip(".:")))


def is_top_heading(item: dict[str, Any]) -> bool:
    level = item.get("text_level")
    return item.get("type") == "text" and (level == 1 or level == "1")


def is_next_section_heading(item: dict[str, Any]) -> bool:
    if not is_top_heading(item):
        return False
    text = normalize_text(str(item.get("text") or ""))
    if not text or is_reference_heading(text):
        return False
    return bool(NEXT_SECTION_RE.match(text)) or len(text.split()) <= 8


def text_from_content_list_item(item: dict[str, Any]) -> str:
    for key in ("text", "table_caption", "img_caption"):
        value = item.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return " ".join(str(part) for part in value)
    return ""


def iter_list_items(item: dict[str, Any]) -> Iterable[str]:
    list_items = item.get("list_items")
    if isinstance(list_items, list):
        for value in list_items:
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                yield flatten_content(value)

    content = item.get("content")
    if isinstance(content, dict):
        for value in content.get("list_items") or []:
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                yield flatten_content(value)


def flatten_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(flatten_content(part) for part in value)
    if isinstance(value, dict):
        pieces: list[str] = []
        for key in ("content", "item_content", "paragraph_content", "title_content"):
            if key in value:
                pieces.append(flatten_content(value[key]))
        if "text" in value:
            pieces.append(str(value["text"]))
        return " ".join(piece for piece in pieces if piece)
    return ""


def extract_candidates_from_content_list(path: Path) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return [], [f"{path.name} is not a list"]

    heading_indexes = [
        idx
        for idx, item in enumerate(data)
        if isinstance(item, dict) and is_reference_heading(text_from_content_list_item(item))
    ]
    if not heading_indexes:
        return [], ["content_list: no References/Bibliography heading"]
    if len(heading_indexes) > 1:
        warnings.append(f"content_list: {len(heading_indexes)} reference headings found; using the first")

    start = heading_indexes[0] + 1
    stop = len(data)
    for idx in range(start, len(data)):
        item = data[idx]
        if isinstance(item, dict) and is_next_section_heading(item):
            stop = idx
            break

    candidates: list[str] = []
    for item in data[start:stop]:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "page_number":
            continue
        if item_type == "list":
            values = [normalize_text(value) for value in iter_list_items(item)]
            candidates.extend(value for value in values if value)
            continue
        if item_type in {"text", "ref_text"}:
            value = normalize_text(text_from_content_list_item(item))
            if value and not is_reference_heading(value):
                candidates.append(value)

    if not candidates:
        warnings.append("content_list: reference section found but no text candidates extracted")
    return candidates, warnings


def extract_candidates_from_markdown(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    starts = [idx for idx, line in enumerate(lines) if is_reference_heading(line)]
    warnings: list[str] = []
    if not starts:
        return [], ["markdown: no References/Bibliography heading"]
    if len(starts) > 1:
        warnings.append(f"markdown: {len(starts)} reference headings found; using the first")

    body_lines: list[str] = []
    for line in lines[starts[0] + 1 :]:
        stripped = line.strip()
        if stripped.startswith("#") and not is_reference_heading(stripped):
            break
        if stripped.startswith("!") or stripped.startswith("<table"):
            continue
        body_lines.append(line)

    # Blank lines are weak separators. Most ACL MinerU markdown has one
    # reference per physical line; when a long reference wraps, the repair pass
    # below joins fragments again.
    candidates = [normalize_text(line) for line in body_lines if normalize_text(line)]
    if not candidates:
        warnings.append("markdown: reference section found but no text candidates extracted")
    return candidates, warnings


def looks_like_reference_start(text: str) -> bool:
    if not REFERENCE_START_RE.match(text):
        return False
    return bool(YEAR_RE.search(text) or URL_RE.search(text[:240]))


def looks_like_author_fragment(text: str) -> bool:
    """Detect the first half of a long author list split before the year."""
    if not REFERENCE_START_RE.match(text):
        return False
    prefix = text[:180]
    return "," in prefix or " and " in prefix or " et al" in prefix


def looks_complete_reference(text: str) -> bool:
    text = text.rstrip()
    if not YEAR_RE.search(text):
        return False
    return bool(re.search(r'(?:[.!?。]|[.)\]"])\s*$', text))


def split_and_repair_references(candidates: Iterable[str]) -> tuple[list[str], list[str]]:
    entries: list[str] = []
    warnings: list[str] = []
    current = ""
    joined_fragments = 0

    for raw in candidates:
        text = normalize_text(raw)
        if not text:
            continue
        starts_new_after_complete = looks_complete_reference(current) and (
            looks_like_reference_start(text) or looks_like_author_fragment(text)
        )
        if current and starts_new_after_complete:
            entries.append(current.strip())
            current = text
        elif current:
            if not looks_complete_reference(current):
                joined_fragments += 1
            current = join_fragments(current, text)
        else:
            current = text

    if current.strip():
        entries.append(current.strip())

    cleaned: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        entry = normalize_text(entry)
        if not entry or entry in seen:
            continue
        seen.add(entry)
        cleaned.append(entry)

    if joined_fragments:
        warnings.append(f"joined {joined_fragments} probable cross-line/cross-page fragments")
    return cleaned, warnings


def parse_reference(index: int, raw: str, source: str) -> Reference:
    raw = normalize_text(raw)
    year_match = YEAR_RE.search(raw)
    warnings: list[str] = []
    authors = ""
    year = ""
    title = ""

    if year_match:
        year = year_match.group(1)
        authors = raw[: year_match.start()].strip(" .,:;")
        rest = raw[year_match.end() :].strip(" .,:;")
        title = parse_title(rest)
    else:
        warnings.append("no_year")

    arxiv_ids = sorted(set(match.group(1) for match in ARXIV_RE.finditer(raw)))
    dois = sorted(set(match.group(0).rstrip(".") for match in DOI_RE.finditer(raw)))
    urls = sorted(set(match.group(0).rstrip(".") for match in URL_RE.finditer(raw)))

    confidence = "high"
    if source.endswith("fallback"):
        confidence = "medium"
    if not year or not title:
        confidence = "low"
    if not authors:
        warnings.append("no_authors")
    if not title:
        warnings.append("no_title")

    return Reference(
        index=index,
        raw=raw,
        authors=authors,
        year=year,
        title=title,
        arxiv_ids=arxiv_ids,
        dois=dois,
        urls=urls,
        confidence=confidence,
        warnings=warnings,
    )


def parse_title(rest: str) -> str:
    if not rest:
        return ""
    boundaries = [
        ". In ",
        "? In ",
        ". Preprint",
        "? Preprint",
        ". arXiv",
        "? arXiv",
        ". In:",
        ". Proceedings",
        ". Transactions",
        ". Journal",
        ". Association for Computational Linguistics",
    ]
    cut_positions = [rest.find(boundary) for boundary in boundaries if rest.find(boundary) > 0]
    if cut_positions:
        return rest[: min(cut_positions)].strip(" .")
    parts = re.split(r"\.\s+", rest, maxsplit=1)
    return parts[0].strip(" .")


def find_related_files(vlm_dir: Path) -> tuple[str, Path | None, Path | None]:
    paper_id = vlm_dir.parent.name
    md = vlm_dir / f"{paper_id}.md"
    content = vlm_dir / f"{paper_id}_content_list.json"
    if not md.exists():
        matches = sorted(vlm_dir.glob("*.md"))
        md = matches[0] if matches else None
    if not content.exists():
        matches = sorted(vlm_dir.glob("*_content_list.json"))
        content = matches[0] if matches else None
    return paper_id, content if content and content.exists() else None, md if md and md.exists() else None


def iter_vlm_dirs(input_path: Path) -> Iterable[Path]:
    if input_path.is_file():
        yield input_path.parent
        return
    if (input_path / "vlm").is_dir():
        yield input_path / "vlm"
        return
    if any(input_path.glob("*_content_list.json")) or any(input_path.glob("*.md")):
        yield input_path
        return
    yield from sorted(path for path in input_path.glob("*/vlm") if path.is_dir())


def extract_paper(vlm_dir: Path) -> PaperExtraction:
    paper_id, content_path, md_path = find_related_files(vlm_dir)
    warnings: list[str] = []
    source = "content_list"
    candidates: list[str] = []

    if content_path:
        candidates, content_warnings = extract_candidates_from_content_list(content_path)
        warnings.extend(content_warnings)
    else:
        warnings.append("missing content_list json")

    md_count: int | None = None
    if md_path:
        md_candidates, md_warnings = extract_candidates_from_markdown(md_path)
        md_entries, _ = split_and_repair_references(md_candidates)
        md_count = len(md_entries)
        if not candidates:
            candidates = md_candidates
            source = "markdown_fallback"
            warnings.extend(md_warnings)
        elif md_count and abs(md_count - len(candidates)) > max(5, int(0.25 * md_count)):
            warnings.append(
                f"content_list candidate count {len(candidates)} differs from markdown repaired count {md_count}"
            )
    else:
        warnings.append("missing markdown")

    raw_entries, repair_warnings = split_and_repair_references(candidates)
    warnings.extend(repair_warnings)

    references = [parse_reference(idx, raw, source) for idx, raw in enumerate(raw_entries, start=1)]
    if not references:
        warnings.append("no references extracted")
    return PaperExtraction(
        paper_id=paper_id,
        source_dir=display_path(vlm_dir),
        source=source,
        references=references,
        markdown_reference_count=md_count,
        warnings=warnings,
    )


def paper_to_jsonable(paper: PaperExtraction) -> dict[str, Any]:
    payload = asdict(paper)
    payload["reference_count"] = len(paper.references)
    return payload


def write_jsonl(records: Iterable[PaperExtraction], output: Path | None) -> None:
    stream = output.open("w", encoding="utf-8") if output else sys.stdout
    try:
        for record in records:
            stream.write(json.dumps(paper_to_jsonable(record), ensure_ascii=False) + "\n")
    finally:
        if output:
            stream.close()


def write_summary(records: list[PaperExtraction], output: Path) -> None:
    total_refs = sum(len(record.references) for record in records)
    warned = [record for record in records if record.warnings]
    low_conf = sum(
        1
        for record in records
        for reference in record.references
        if reference.confidence == "low" or reference.warnings
    )
    payload = {
        "paper_count": len(records),
        "reference_count": total_refs,
        "papers_with_warnings": len(warned),
        "low_confidence_references": low_conf,
        "empty_papers": [record.paper_id for record in records if not record.references],
        "warning_samples": [
            {"paper_id": record.paper_id, "warnings": record.warnings[:5]} for record in warned[:50]
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract structured references from MinerU ACL outputs."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help="ACL MinerU root, a paper directory, a vlm directory, or one MinerU file.",
    )
    parser.add_argument("--output", "-o", type=Path, help="Write JSONL records here. Defaults to stdout.")
    parser.add_argument("--summary", type=Path, help="Write aggregate extraction summary JSON.")
    parser.add_argument("--limit", type=int, help="Only process the first N vlm directories.")
    parser.add_argument("--paper-id", action="append", help="Only process this paper id. May be repeated.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print a single selected record instead of JSONL.",
    )
    args = parser.parse_args()

    input_path = args.input
    if not input_path.exists() and not input_path.is_absolute():
        repo_relative = REPO_ROOT / input_path
        if repo_relative.exists():
            input_path = repo_relative
    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {args.input}")

    paper_ids = set(args.paper_id or [])
    vlm_dirs = []
    for vlm_dir in iter_vlm_dirs(input_path):
        paper_id = vlm_dir.parent.name
        if paper_ids and paper_id not in paper_ids:
            continue
        vlm_dirs.append(vlm_dir)
        if args.limit and len(vlm_dirs) >= args.limit:
            break

    records = [extract_paper(vlm_dir) for vlm_dir in vlm_dirs]
    if args.pretty:
        if len(records) != 1:
            raise SystemExit("--pretty requires exactly one selected paper")
        print(json.dumps(paper_to_jsonable(records[0]), ensure_ascii=False, indent=2))
    else:
        write_jsonl(records, args.output)

    if args.summary:
        write_summary(records, args.summary)


if __name__ == "__main__":
    main()
