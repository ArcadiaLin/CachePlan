#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4_v2/compare_v1_v2.py --paper-id-file <ids.txt>
"""Compare Layer4 v2 outputs against v1 for the same papers (refractor.md §8).

Resource matching is name-based (normalized); reports v1-recall, v2 extras,
and kind/relation agreement on matched resources.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common_v2 import DEFAULT_DATA_ROOT, DEFAULT_LAYER4_V2_ROOT, read_json, write_json

DEFAULT_LAYER4_V1_ROOT = DEFAULT_DATA_ROOT / "processed/layer4/2026/acl"


def norm_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"\((?:model|dataset|benchmark|code|tool)\)", "", name)
    name = re.sub(r"\b(framework|series|dataset|benchmark|corpus|model)\b", "", name)
    return re.sub(r"[^a-z0-9]+", "", name)


def load_resources(paper_dir: Path) -> list[dict[str, Any]]:
    import yaml

    path = paper_dir / "resource_records.yml"
    if not path.exists():
        return []
    records = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    result = []
    for wrapper in records:
        record = wrapper.get("resource_record") or {}
        result.append(
            {
                "name": str(record.get("name") or ""),
                "kind": str(record.get("kind") or ""),
                "relation": str((record.get("paper_relation") or {}).get("relation_type") or ""),
                "url": str((record.get("access") or {}).get("url") or ""),
            }
        )
    return result


def compare_paper(paper_id: str, v1_root: Path, v2_root: Path) -> dict[str, Any]:
    v1 = load_resources(v1_root / paper_id)
    v2 = load_resources(v2_root / paper_id)
    v2_by_name = {norm_name(r["name"]): r for r in v2 if norm_name(r["name"])}

    matched, missing = [], []
    kind_agree = relation_agree = 0
    for r1 in v1:
        key = norm_name(r1["name"])
        r2 = v2_by_name.get(key)
        if r2 is None:
            missing.append(r1)
            continue
        matched.append({"name": r1["name"], "v1": (r1["kind"], r1["relation"]), "v2": (r2["kind"], r2["relation"])})
        if r1["kind"] == r2["kind"]:
            kind_agree += 1
        if r1["relation"] == r2["relation"]:
            relation_agree += 1
    v1_keys = {norm_name(r["name"]) for r in v1}
    extras = [r for r in v2 if norm_name(r["name"]) not in v1_keys]
    return {
        "paper_id": paper_id,
        "v1_count": len(v1),
        "v2_count": len(v2),
        "matched": len(matched),
        "recall_of_v1": round(len(matched) / len(v1), 3) if v1 else None,
        "kind_agree": kind_agree,
        "relation_agree": relation_agree,
        "missing_in_v2": missing,
        "extra_in_v2": extras,
        "matched_pairs": matched,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare Layer4 v1 vs v2 resource outputs.")
    parser.add_argument("--paper-id", action="append")
    parser.add_argument("--paper-id-file", type=Path)
    parser.add_argument("--v1-root", type=Path, default=DEFAULT_LAYER4_V1_ROOT)
    parser.add_argument("--v2-root", type=Path, default=DEFAULT_LAYER4_V2_ROOT)
    parser.add_argument("--report", type=Path, help="Write full JSON report here.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    paper_ids = list(args.paper_id or [])
    if args.paper_id_file:
        paper_ids += [l.strip() for l in args.paper_id_file.read_text().splitlines() if l.strip()]
    if not paper_ids:
        raise SystemExit("no papers given")

    rows = [compare_paper(pid, args.v1_root, args.v2_root) for pid in paper_ids]
    total_v1 = sum(r["v1_count"] for r in rows)
    total_matched = sum(r["matched"] for r in rows)
    total_kind = sum(r["kind_agree"] for r in rows)
    total_rel = sum(r["relation_agree"] for r in rows)
    summary = {
        "papers": len(rows),
        "v1_resources": total_v1,
        "v2_resources": sum(r["v2_count"] for r in rows),
        "recall_of_v1": round(total_matched / total_v1, 3) if total_v1 else None,
        "kind_agreement_on_matched": round(total_kind / total_matched, 3) if total_matched else None,
        "relation_agreement_on_matched": round(total_rel / total_matched, 3) if total_matched else None,
        "extra_in_v2_total": sum(len(r["extra_in_v2"]) for r in rows),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for r in rows:
        if r["missing_in_v2"]:
            print(f"\n{r['paper_id']} missing in v2:")
            for m in r["missing_in_v2"]:
                print(f"  - {m['kind']}/{m['name']} ({m['relation']})")
    if args.report:
        write_json(args.report, {"summary": summary, "papers": rows})


if __name__ == "__main__":
    main()
