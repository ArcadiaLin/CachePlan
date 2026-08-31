#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/references/build_reference_index.py /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_verified_plus_repaired.jsonl --output /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_reference_index.jsonl --summary /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_reference_index_summary.json
"""Build a cross-paper index of unique references from extraction JSONL."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from extract_mineru_references import parse_reference


MIN_TITLE_KEY_LENGTH = 8
KEY_RANK = {"title": 0, "doi": 1, "arxiv": 2, "url": 3, "raw": 4}


def normalize_identifier(value: str) -> str:
    value = value.strip().rstrip(".,;)")
    return value.lower()


def canonical_title(title: str) -> str:
    title = title.strip()
    title = title.replace("\u00ad", "")
    title = re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "", title)
    title = title.replace("“", '"').replace("”", '"').replace("’", "'")
    title = title.replace("–", "-").replace("—", "-")
    title = title.lower()
    title = re.sub(r"&", " and ", title)
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def canonical_raw(raw: str) -> str:
    raw = raw.strip().lower()
    raw = re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "", raw)
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def sorted_counter_values(counter: Counter[str], limit: int) -> list[str]:
    return [value for value, _count in counter.most_common(limit)]


def extract_reference_fields(reference: dict[str, Any]) -> dict[str, Any]:
    raw = str(reference.get("raw") or "")
    parsed = None
    title = str(reference.get("title") or "").strip()
    authors = str(reference.get("authors") or "").strip()
    year = str(reference.get("year") or "").strip()

    if not title or not authors or not year:
        parsed = parse_reference(int(reference.get("index") or 0), raw, "index")
        title = title or parsed.title
        authors = authors or parsed.authors
        year = year or parsed.year

    arxiv_ids = [str(value) for value in reference.get("arxiv_ids") or []]
    dois = [str(value) for value in reference.get("dois") or []]
    urls = [str(value) for value in reference.get("urls") or []]
    if parsed is not None:
        arxiv_ids = arxiv_ids or parsed.arxiv_ids
        dois = dois or parsed.dois
        urls = urls or parsed.urls

    return {
        "raw": raw,
        "title": title,
        "authors": authors,
        "year": year,
        "arxiv_ids": arxiv_ids,
        "dois": dois,
        "urls": urls,
        "confidence": str(reference.get("confidence") or ""),
        "warnings": list(reference.get("warnings") or []),
    }


def evidence_keys(fields: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    dois = sorted({normalize_identifier(str(value)) for value in fields["dois"] if str(value).strip()})
    arxiv_ids = sorted(
        {normalize_identifier(str(value)) for value in fields["arxiv_ids"] if str(value).strip()}
    )
    urls = sorted({normalize_identifier(str(value)) for value in fields["urls"] if str(value).strip()})

    # Multiple identifiers in one extracted reference often means two or more
    # references were accidentally fused. Do not let those identifiers bridge
    # unrelated works in the global index.
    if len(dois) == 1:
        keys.append(f"doi:{dois[0]}")
    if len(arxiv_ids) == 1:
        keys.append(f"arxiv:{arxiv_ids[0]}")
    if len(urls) == 1:
        keys.append(f"url:{urls[0]}")

    title_key = canonical_title(str(fields["title"]))
    if len(title_key) >= MIN_TITLE_KEY_LENGTH:
        keys.append(f"title:{title_key}")

    if not keys:
        raw_key = canonical_raw(str(fields["raw"]))
        if raw_key:
            keys.append(f"raw:{raw_key}")
    return list(dict.fromkeys(keys))


def grouping_key(fields: dict[str, Any]) -> str:
    title_key = canonical_title(str(fields["title"]))
    if len(title_key) >= MIN_TITLE_KEY_LENGTH:
        return f"title:{title_key}"

    fallback_keys = [key for key in evidence_keys(fields) if not key.startswith("title:")]
    if fallback_keys:
        return preferred_key(fallback_keys)

    raw_key = canonical_raw(str(fields["raw"]))
    return f"raw:{raw_key}"


def key_type(key: str) -> str:
    return key.split(":", 1)[0]


def preferred_key(keys: list[str]) -> str:
    return sorted(keys, key=lambda key: (KEY_RANK.get(key_type(key), 99), key))[0]


def empty_group(key: str, key_type: str) -> dict[str, Any]:
    return {
        "key": key,
        "key_type": key_type,
        "all_keys": set(),
        "titles": Counter(),
        "canonical_titles": Counter(),
        "authors": Counter(),
        "years": Counter(),
        "dois": Counter(),
        "arxiv_ids": Counter(),
        "urls": Counter(),
        "raws": Counter(),
        "confidence": Counter(),
        "warning_count": 0,
        "occurrences": [],
    }


def add_reference(
    groups: dict[str, dict[str, Any]],
    paper: dict[str, Any],
    reference: dict[str, Any],
    group_key: str,
    keys: list[str],
) -> None:
    fields = extract_reference_fields(reference)
    group = groups.setdefault(group_key, empty_group(group_key, key_type(group_key)))
    group["all_keys"].update(keys)

    title = str(fields["title"]).strip()
    if title:
        group["titles"][title] += 1
        canonical = canonical_title(title)
        if canonical:
            group["canonical_titles"][canonical] += 1

    authors = str(fields["authors"]).strip()
    year = str(fields["year"]).strip()
    raw = str(fields["raw"]).strip()
    confidence = str(fields["confidence"]).strip()
    if authors:
        group["authors"][authors] += 1
    if year:
        group["years"][year] += 1
    if raw:
        group["raws"][raw] += 1
    if confidence:
        group["confidence"][confidence] += 1

    for value in fields["dois"]:
        group["dois"][normalize_identifier(str(value))] += 1
    for value in fields["arxiv_ids"]:
        group["arxiv_ids"][normalize_identifier(str(value))] += 1
    for value in fields["urls"]:
        group["urls"][normalize_identifier(str(value))] += 1

    group["warning_count"] += len(fields["warnings"])
    group["occurrences"].append(
        {
            "paper_id": paper.get("paper_id"),
            "source_dir": paper.get("source_dir"),
            "reference_index": reference.get("index"),
            "source": paper.get("source"),
            "confidence": confidence,
        }
    )


def group_to_jsonable(group: dict[str, Any]) -> dict[str, Any]:
    occurrences = group["occurrences"]
    citing_paper_ids = sorted({str(item["paper_id"]) for item in occurrences})
    title = group["titles"].most_common(1)[0][0] if group["titles"] else ""
    canonical = group["canonical_titles"].most_common(1)[0][0] if group["canonical_titles"] else ""

    return {
        "key": group["key"],
        "key_type": group["key_type"],
        "all_keys": sorted(group["all_keys"], key=lambda key: (KEY_RANK.get(key_type(key), 99), key)),
        "title": title,
        "canonical_title": canonical,
        "mention_count": len(occurrences),
        "citing_paper_count": len(citing_paper_ids),
        "citing_paper_ids": citing_paper_ids,
        "years": sorted_counter_values(group["years"], 10),
        "authors_samples": sorted_counter_values(group["authors"], 5),
        "identifiers": {
            "dois": sorted_counter_values(group["dois"], 10),
            "arxiv_ids": sorted_counter_values(group["arxiv_ids"], 10),
            "urls": sorted_counter_values(group["urls"], 10),
        },
        "confidence_counts": dict(group["confidence"]),
        "warning_count": group["warning_count"],
        "sample_raws": sorted_counter_values(group["raws"], 3),
        "occurrences": occurrences,
    }


def read_papers(path: Path) -> list[dict[str, Any]]:
    papers: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise SystemExit(f"Line {line_number} is not a JSON object.")
            papers.append(value)
    return papers


def build_index(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for paper in papers:
        for reference in paper.get("references") or []:
            if isinstance(reference, dict):
                fields = extract_reference_fields(reference)
                group_key = grouping_key(fields)
                if group_key == "raw:":
                    continue
                keys = sorted(
                    set(evidence_keys(fields) + [group_key]),
                    key=lambda key: (KEY_RANK.get(key_type(key), 99), key),
                )
                add_reference(groups, paper, reference, group_key, keys)

    records = [group_to_jsonable(group) for group in groups.values()]
    return sorted(
        records,
        key=lambda record: (
            -int(record["mention_count"]),
            str(record["key_type"]),
            str(record["title"] or record["key"]),
        ),
    )


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_summary(papers: list[dict[str, Any]], records: list[dict[str, Any]], path: Path) -> None:
    key_type_counts = Counter(str(record["key_type"]) for record in records)
    mention_count = sum(len(paper.get("references") or []) for paper in papers)
    records_with_title = [record for record in records if record.get("canonical_title")]
    duplicate_groups = [record for record in records if int(record["mention_count"]) > 1]
    repeated_across_papers = [record for record in records if int(record["citing_paper_count"]) > 1]

    payload = {
        "paper_count": len(papers),
        "reference_mentions": mention_count,
        "unique_reference_count": len(records),
        "unique_title_count": len({record["canonical_title"] for record in records_with_title}),
        "references_without_title_count": sum(1 for record in records if not record.get("canonical_title")),
        "key_type_counts": dict(key_type_counts),
        "duplicate_group_count": len(duplicate_groups),
        "repeated_across_papers_count": len(repeated_across_papers),
        "top_repeated_references": [
            {
                "key": record["key"],
                "key_type": record["key_type"],
                "title": record["title"],
                "mention_count": record["mention_count"],
                "citing_paper_count": record["citing_paper_count"],
                "citing_paper_ids": record["citing_paper_ids"][:20],
            }
            for record in repeated_across_papers[:50]
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deduplicated cross-paper reference index.")
    parser.add_argument("input", type=Path, help="Reference extraction JSONL.")
    parser.add_argument("--output", required=True, type=Path, help="Unique reference index JSONL.")
    parser.add_argument("--summary", required=True, type=Path, help="Summary JSON.")
    args = parser.parse_args()

    papers = read_papers(args.input)
    records = build_index(papers)
    write_jsonl(records, args.output)
    write_summary(papers, records, args.summary)


if __name__ == "__main__":
    main()
