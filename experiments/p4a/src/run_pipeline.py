#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/run_pipeline.py --year 2026 --venue acl --limit 10 --prepare-layer4-only
# run all
# cd /home/lzx/projs/p4a
# .venv/bin/python src/run_pipeline.py --year 2026 --venue acl --permission-mode none
"""Run the P4A data pipeline one paper at a time.

Each paper gets its own small reference/citation JSONL files so Layer 4 can
start as soon as that paper is ready. Batch-level JSONL/index files can still be
rebuilt later for audit and search, but they are no longer required to unblock
Layer 4.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


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


@dataclass(frozen=True)
class PaperPaths:
    paper_id: str
    raw_pdf: Path
    mineru_paper_dir: Path
    cite_paper_dir: Path
    references_jsonl: Path
    references_summary: Path
    verified_jsonl: Path
    mismatches_jsonl: Path
    comparison_summary: Path
    selected_references_jsonl: Path
    cite_contexts_jsonl: Path
    cite_contexts_summary: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MinerU -> references -> cite contexts -> Layer 4 per paper.")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--top", default="acl")
    parser.add_argument("--year", default="2026")
    parser.add_argument("--venue", default="acl")
    parser.add_argument("--paper-id", action="append", help="Process one paper id. Repeatable.")
    parser.add_argument("--paper-id-file", type=Path, action="append", help="Read newline-delimited paper ids.")
    parser.add_argument("--limit", type=int, help="Process at most N papers after filtering.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8004")
    parser.add_argument("--mineru-timeout", type=int, default=1800)
    parser.add_argument("--layer4-timeout", type=int, default=3600)
    parser.add_argument("--max-citations", type=int, default=200)
    parser.add_argument("--permission-mode", choices=("none", "auto", "yolo"), default="none")
    parser.add_argument("--skip-mineru", action="store_true")
    parser.add_argument("--skip-layer4", action="store_true")
    parser.add_argument("--prepare-layer4-only", action="store_true")
    parser.add_argument("--repair-references", action="store_true", help="Launch Kimi for a paper when reference verification mismatches.")
    parser.add_argument(
        "--allow-unverified-references",
        action="store_true",
        help="Continue to cite/Layer4 with primary extraction when content_list and Markdown disagree.",
    )
    parser.add_argument("--force-mineru", action="store_true")
    parser.add_argument("--overwrite-layer4-prepare", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print commands and planned file actions.")
    parser.add_argument("--verbose-commands", action="store_true", help="Print child process commands during real runs.")
    return parser


def load_paper_ids(args: argparse.Namespace) -> set[str] | None:
    selected = set(args.paper_id or [])
    for path in args.paper_id_file or []:
        for line in path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                selected.add(value)
    return selected or None


def discover_papers(args: argparse.Namespace) -> list[tuple[str, Path]]:
    pdf_root = args.data_root / "raw" / args.top / args.year / "pdf" / args.venue
    if not pdf_root.exists():
        raise SystemExit(f"PDF root does not exist: {pdf_root}")
    selected_ids = load_paper_ids(args)
    papers = []
    for pdf_path in sorted(pdf_root.glob("*.pdf")):
        paper_id = pdf_path.stem
        if selected_ids and paper_id not in selected_ids:
            continue
        papers.append((paper_id, pdf_path))
    if args.limit:
        papers = papers[: args.limit]
    return papers


def paper_paths(args: argparse.Namespace, paper_id: str, raw_pdf: Path) -> PaperPaths:
    mineru_paper_dir = args.data_root / "processed" / "mineru" / args.top / args.year / args.venue / paper_id
    cite_paper_dir = args.data_root / "processed" / "cite" / args.year / args.venue / "per_paper" / paper_id
    return PaperPaths(
        paper_id=paper_id,
        raw_pdf=raw_pdf,
        mineru_paper_dir=mineru_paper_dir,
        cite_paper_dir=cite_paper_dir,
        references_jsonl=cite_paper_dir / "references.jsonl",
        references_summary=cite_paper_dir / "references_summary.json",
        verified_jsonl=cite_paper_dir / "verified_references.jsonl",
        mismatches_jsonl=cite_paper_dir / "reference_mismatches.jsonl",
        comparison_summary=cite_paper_dir / "reference_comparison_summary.json",
        selected_references_jsonl=cite_paper_dir / "verified_or_repaired.jsonl",
        cite_contexts_jsonl=cite_paper_dir / "cite_contexts.jsonl",
        cite_contexts_summary=cite_paper_dir / "cite_contexts_summary.json",
    )


def run(cmd: list[str], *, dry_run: bool, verbose: bool = False) -> None:
    if dry_run or verbose:
        print("+ " + " ".join(str(part) for part in cmd), flush=True)
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)


def nonempty_jsonl(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as stream:
        return any(line.strip() for line in stream)


def copy_file(src: Path, dst: Path, *, dry_run: bool) -> None:
    if dry_run:
        print(f"+ copy {src} -> {dst}", flush=True)
    if dry_run:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write_json(path: Path, payload: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        print(f"+ write {path}", flush=True)
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mineru_complete(paths: PaperPaths) -> bool:
    vlm_dir = paths.mineru_paper_dir / "vlm"
    return (
        (vlm_dir / f"{paths.paper_id}.md").exists()
        and (vlm_dir / f"{paths.paper_id}_content_list.json").exists()
    )


def run_mineru(args: argparse.Namespace, paths: PaperPaths) -> None:
    if args.skip_mineru:
        return
    if mineru_complete(paths) and not args.force_mineru:
        print(f"[skip mineru] {paths.paper_id} already has MinerU outputs", flush=True)
        return
    check_mineru_server(args)
    cmd = [
        sys.executable,
        "src/mineru/batch_process_acl_mineru.py",
        "--year",
        args.year,
        "--top",
        args.top,
        "--venue",
        args.venue,
        "--paper-id",
        paths.paper_id,
        "--raw-root",
        str(args.data_root / "raw"),
        "--output-root",
        str(args.data_root / "processed" / "mineru"),
        "--server-url",
        args.server_url,
        "--timeout",
        str(args.mineru_timeout),
    ]
    if args.force_mineru:
        cmd.append("--force")
    run(cmd, dry_run=args.dry_run, verbose=args.verbose_commands)


def extract_and_verify_references(args: argparse.Namespace, paths: PaperPaths) -> str:
    if not args.dry_run:
        paths.cite_paper_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "src/extract/references/extract_mineru_references.py",
            str(paths.mineru_paper_dir),
            "--output",
            str(paths.references_jsonl),
            "--summary",
            str(paths.references_summary),
        ],
        dry_run=args.dry_run,
        verbose=args.verbose_commands,
    )
    run(
        [
            sys.executable,
            "src/extract/references/compare_mineru_reference_sources.py",
            str(paths.mineru_paper_dir),
            "--trusted-output",
            str(paths.verified_jsonl),
            "--mismatch-output",
            str(paths.mismatches_jsonl),
            "--summary",
            str(paths.comparison_summary),
        ],
        dry_run=args.dry_run,
        verbose=args.verbose_commands,
    )
    if args.dry_run:
        return "dry_run"
    if nonempty_jsonl(paths.verified_jsonl):
        copy_file(paths.verified_jsonl, paths.selected_references_jsonl, dry_run=False)
        return "verified"
    return "needs_repair"


def repair_references(args: argparse.Namespace, paths: PaperPaths) -> bool:
    repaired = paths.cite_paper_dir / "references_repaired.jsonl"
    verified_plus = paths.selected_references_jsonl
    repair_summary = paths.cite_paper_dir / "repair_summary.json"
    repairs_dir = paths.cite_paper_dir / "repairs"
    run(
        [
            sys.executable,
            "src/extract/references/launch_kimi_reference_repairs.py",
            "--summary",
            str(paths.comparison_summary),
            "--mismatch-jsonl",
            str(paths.mismatches_jsonl),
            "--primary-jsonl",
            str(paths.references_jsonl),
            "--verified-jsonl",
            str(paths.verified_jsonl),
            "--repaired-jsonl",
            str(repaired),
            "--verified-plus-jsonl",
            str(verified_plus),
            "--repair-summary",
            str(repair_summary),
            "--repairs-dir",
            str(repairs_dir),
            "--paper-id",
            paths.paper_id,
            "--concurrency",
            "1",
            "--no-build-index",
        ],
        dry_run=args.dry_run,
        verbose=args.verbose_commands,
    )
    return args.dry_run or nonempty_jsonl(verified_plus)


def prepare_reference_input(args: argparse.Namespace, paths: PaperPaths, status: str) -> str:
    if status == "verified" or status == "dry_run":
        return status
    if args.repair_references:
        return "repaired" if repair_references(args, paths) else "repair_failed"
    if args.allow_unverified_references:
        copy_file(paths.references_jsonl, paths.selected_references_jsonl, dry_run=args.dry_run)
        return "unverified_allowed"
    return "blocked_reference_mismatch"


def run_cite_contexts(args: argparse.Namespace, paths: PaperPaths) -> None:
    run(
        [
            sys.executable,
            "src/extract/references/extract_cite_contexts.py",
            str(paths.selected_references_jsonl),
            "--output",
            str(paths.cite_contexts_jsonl),
            "--summary",
            str(paths.cite_contexts_summary),
        ],
        dry_run=args.dry_run,
        verbose=args.verbose_commands,
    )


def run_layer4(args: argparse.Namespace, paths: PaperPaths) -> None:
    if args.skip_layer4:
        return
    layer4_root = args.data_root / "processed" / "layer4" / args.year / args.venue
    cmd = [
        sys.executable,
        "src/extract/layer4/launch_kimi_layer4.py",
        "--paper-id",
        paths.paper_id,
        "--references-jsonl",
        str(paths.selected_references_jsonl),
        "--cite-contexts-jsonl",
        str(paths.cite_contexts_jsonl),
        "--output-root",
        str(layer4_root),
        "--concurrency",
        "1",
        "--timeout",
        str(args.layer4_timeout),
        "--max-citations",
        str(args.max_citations),
        "--permission-mode",
        args.permission_mode,
    ]
    if args.prepare_layer4_only:
        cmd.append("--prepare-only")
    if args.overwrite_layer4_prepare:
        cmd.append("--overwrite-prepare")
        cmd.append("--no-skip-existing")
    run(cmd, dry_run=args.dry_run, verbose=args.verbose_commands)


def check_mineru_server(args: argparse.Namespace) -> None:
    if args.skip_mineru or args.dry_run:
        return
    url = args.server_url.rstrip("/") + "/v1/models"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 400:
                raise RuntimeError(f"{url} returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"MinerU VLM server is reachable, but {url} returned HTTP {exc.code}.\n"
            f"Response body:\n{body}\n"
            "The MinerU vlm-http-client requires /v1/models to return exactly one model.\n"
            "Restart it from the repository root:\n"
            "  cd /home/lzx/projs/p4a\n"
            "  src/mineru/serve_mineru_vllm.sh\n"
            "Then rerun src/run_pipeline.py."
        ) from exc
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        raise SystemExit(
            f"MinerU VLM server is not reachable at {url}.\n"
            "Start it first from the repository root:\n"
            "  cd /home/lzx/projs/p4a\n"
            "  src/mineru/serve_mineru_vllm.sh\n"
            "Then rerun src/run_pipeline.py."
        ) from exc


def run_one_paper(args: argparse.Namespace, paper_id: str, raw_pdf: Path) -> dict[str, Any]:
    paths = paper_paths(args, paper_id, raw_pdf)
    started_at = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {
        "paper_id": paper_id,
        "raw_pdf": str(raw_pdf),
        "started_at": started_at,
        "status": "running",
    }
    try:
        run_mineru(args, paths)
        if not args.dry_run and not mineru_complete(paths):
            raise RuntimeError(f"MinerU output is incomplete for {paper_id}")
        reference_status = extract_and_verify_references(args, paths)
        reference_status = prepare_reference_input(args, paths, reference_status)
        result["reference_status"] = reference_status
        if reference_status in {"blocked_reference_mismatch", "repair_failed"}:
            result["status"] = reference_status
            return result
        run_cite_contexts(args, paths)
        run_layer4(args, paths)
        result["status"] = "dry_run" if args.dry_run else "done"
        return result
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        result["error"] = str(exc)
        return result
    finally:
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(paths.cite_paper_dir / "pipeline_status.json", result, dry_run=args.dry_run)


def main() -> None:
    args = build_parser().parse_args()
    papers = discover_papers(args)
    check_mineru_server(args)
    print(f"Selected {len(papers)} papers from {args.data_root}/raw/{args.top}/{args.year}/pdf/{args.venue}", flush=True)
    results = []
    for index, (paper_id, raw_pdf) in enumerate(papers, start=1):
        print(f"[paper {index}/{len(papers)}] {paper_id}", flush=True)
        result = run_one_paper(args, paper_id, raw_pdf)
        results.append(result)
        print(f"[paper {index}/{len(papers)}] {paper_id} -> {result['status']}", flush=True)
    summary = {
        "top": args.top,
        "year": args.year,
        "venue": args.venue,
        "paper_count": len(results),
        "status_counts": {
            status: sum(1 for row in results if row["status"] == status)
            for status in sorted({row["status"] for row in results})
        },
        "results": results,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    report = args.data_root / "processed" / "pipeline" / args.year / args.venue / "pipeline_report.json"
    write_json(report, summary, dry_run=args.dry_run)
    print(json.dumps(summary["status_counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
