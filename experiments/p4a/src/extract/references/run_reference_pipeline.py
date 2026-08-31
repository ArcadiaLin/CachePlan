#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/references/run_reference_pipeline.py --stage pre-repair --year 2026 --venue acl
"""Run the deterministic parts of the MinerU reference pipeline.

The pipeline intentionally separates automatic extraction/verification from
Kimi-based repair. Run ``pre-repair`` first, inspect the mismatch queue, then
run ``repair`` or ``merge-repairs`` when repair records are ready.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run P4A MinerU reference pipeline stages.")
    parser.add_argument(
        "--stage",
        choices=("pre-repair", "repair", "merge-repairs", "cite", "all"),
        default="pre-repair",
        help="Pipeline stage to run. all means pre-repair followed by cite.",
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--top", default="acl", help="Top-level collection under processed/mineru.")
    parser.add_argument("--year", default="2026")
    parser.add_argument("--venue", default="acl")
    parser.add_argument("--prefix", help="Output file prefix. Defaults to <top><year>, e.g. acl2025.")
    parser.add_argument("--limit", type=int, help="Limit papers for extract/verify/cite smoke runs.")
    parser.add_argument("--paper-id", action="append", help="Limit to one paper id. Repeatable.")
    parser.add_argument("--concurrency", type=int, default=32, help="Kimi repair concurrency.")
    parser.add_argument("--timeout", type=int, default=3600, help="Kimi repair timeout per paper.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    return parser


def run(cmd: list[str], *, dry_run: bool) -> None:
    display = " ".join(str(part) for part in cmd)
    print(f"+ {display}", flush=True)
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)


def selected_args(args: argparse.Namespace) -> list[str]:
    extra: list[str] = []
    if args.limit:
        extra.extend(["--limit", str(args.limit)])
    for paper_id in args.paper_id or []:
        extra.extend(["--paper-id", paper_id])
    return extra


def paths(args: argparse.Namespace) -> dict[str, Path]:
    prefix = args.prefix or f"{args.top}{args.year}"
    cite_dir = args.data_root / "processed" / "cite" / args.year / args.venue
    return {
        "mineru_root": args.data_root / "processed" / "mineru" / args.top / args.year / args.venue,
        "cite_dir": cite_dir,
        "primary": cite_dir / f"{prefix}_references.jsonl",
        "primary_summary": cite_dir / f"{prefix}_references_summary.json",
        "verified": cite_dir / f"{prefix}_verified_references.jsonl",
        "mismatches": cite_dir / f"{prefix}_reference_mismatches.jsonl",
        "comparison_summary": cite_dir / f"{prefix}_reference_comparison_summary.json",
        "primary_index": cite_dir / f"{prefix}_reference_index.jsonl",
        "primary_index_summary": cite_dir / f"{prefix}_reference_index_summary.json",
        "verified_index": cite_dir / f"{prefix}_verified_reference_index.jsonl",
        "verified_index_summary": cite_dir / f"{prefix}_verified_reference_index_summary.json",
        "repaired": cite_dir / f"{prefix}_references_repaired.jsonl",
        "verified_plus": cite_dir / f"{prefix}_verified_plus_repaired.jsonl",
        "repair_summary": cite_dir / f"{prefix}_repair_summary.json",
        "repairs_dir": cite_dir / "repairs",
        "repaired_index": cite_dir / f"{prefix}_repaired_reference_index.jsonl",
        "repaired_index_summary": cite_dir / f"{prefix}_repaired_reference_index_summary.json",
        "cite_contexts": cite_dir / f"{prefix}_cite_contexts.jsonl",
        "cite_contexts_summary": cite_dir / f"{prefix}_cite_contexts_summary.json",
    }


def pre_repair(args: argparse.Namespace, p: dict[str, Path]) -> None:
    if not args.dry_run:
        p["cite_dir"].mkdir(parents=True, exist_ok=True)
    extra = selected_args(args)
    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "extract_mineru_references.py"),
            str(p["mineru_root"]),
            "--output",
            str(p["primary"]),
            "--summary",
            str(p["primary_summary"]),
            *extra,
        ],
        dry_run=args.dry_run,
    )
    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "compare_mineru_reference_sources.py"),
            str(p["mineru_root"]),
            "--trusted-output",
            str(p["verified"]),
            "--mismatch-output",
            str(p["mismatches"]),
            "--summary",
            str(p["comparison_summary"]),
            *extra,
        ],
        dry_run=args.dry_run,
    )
    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "build_reference_index.py"),
            str(p["primary"]),
            "--output",
            str(p["primary_index"]),
            "--summary",
            str(p["primary_index_summary"]),
        ],
        dry_run=args.dry_run,
    )
    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "build_reference_index.py"),
            str(p["verified"]),
            "--output",
            str(p["verified_index"]),
            "--summary",
            str(p["verified_index_summary"]),
        ],
        dry_run=args.dry_run,
    )


def repair(args: argparse.Namespace, p: dict[str, Path], *, merge_only: bool) -> None:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "launch_kimi_reference_repairs.py"),
        "--summary",
        str(p["comparison_summary"]),
        "--mismatch-jsonl",
        str(p["mismatches"]),
        "--primary-jsonl",
        str(p["primary"]),
        "--verified-jsonl",
        str(p["verified"]),
        "--repaired-jsonl",
        str(p["repaired"]),
        "--verified-plus-jsonl",
        str(p["verified_plus"]),
        "--repair-summary",
        str(p["repair_summary"]),
        "--repairs-dir",
        str(p["repairs_dir"]),
        "--repaired-index-jsonl",
        str(p["repaired_index"]),
        "--repaired-index-summary",
        str(p["repaired_index_summary"]),
        "--concurrency",
        str(args.concurrency),
        "--timeout",
        str(args.timeout),
        *selected_args(args),
    ]
    if merge_only:
        cmd.append("--merge-only")
    run(cmd, dry_run=args.dry_run)


def cite(args: argparse.Namespace, p: dict[str, Path]) -> None:
    references = p["verified_plus"] if p["verified_plus"].exists() else p["verified"]
    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "extract_cite_contexts.py"),
            str(references),
            "--output",
            str(p["cite_contexts"]),
            "--summary",
            str(p["cite_contexts_summary"]),
            *selected_args(args),
        ],
        dry_run=args.dry_run,
    )


def main() -> None:
    args = build_parser().parse_args()
    p = paths(args)
    if args.stage in {"pre-repair", "all"}:
        pre_repair(args, p)
    if args.stage == "repair":
        repair(args, p, merge_only=False)
    if args.stage == "merge-repairs":
        repair(args, p, merge_only=True)
    if args.stage in {"cite", "all"}:
        cite(args, p)


if __name__ == "__main__":
    main()
