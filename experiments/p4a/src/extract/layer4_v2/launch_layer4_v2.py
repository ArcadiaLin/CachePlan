#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4_v2/launch_layer4_v2.py --limit 10 --llm-concurrency 8
"""Layer4 v2 batch orchestrator: program stages + two LLM calls per paper.

Per-paper chain (idempotent; finished stages are skipped on rerun):

  cite chain (reuse v1 scripts, soft gate) -> prepare (v1 script, templates)
  -> build inputs -> LLM call 1 -> external verification -> LLM call 2
  -> apply + validate (v1 scripts) -> repair call x2 -> ReAct-agent fallback
  -> blocked_v2_manual

State machine per paper in <paper_dir>/v2_state.json; batch reports in
<output_root>/batch_report.json / batch_failures.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from common_v2 import (
    DEFAULT_DATA_ROOT,
    DEFAULT_LAYER4_V2_ROOT,
    DEFAULT_V2_CACHE_ROOT,
    REPO_ROOT,
    load_state,
    now_iso,
    read_json,
    save_state,
    set_stage,
    write_json,
)
from build_paper_inputs import build_inputs, degraded_cite_contexts, strip_references
from llm_client import VllmJsonClient
from prompts import REPAIR_SYSTEM, repair_user_prompt
from resolve_external_resources import ExternalResolver
from run_candidate_extraction import run_extraction
from run_final_judgment import run_judgment

_LAYER4_DIR = Path(__file__).resolve().parents[1] / "layer4"
if str(_LAYER4_DIR) not in sys.path:
    sys.path.insert(0, str(_LAYER4_DIR))
from launch_kimi_layer4 import is_probable_front_matter  # noqa: E402

DEFAULT_REFERENCES_JSONL = DEFAULT_DATA_ROOT / "processed/cite/2026/acl/acl2026_verified_plus_repaired.jsonl"
DEFAULT_CITE_CONTEXTS_JSONL = DEFAULT_DATA_ROOT / "processed/cite/2026/acl/acl2026_cite_contexts.jsonl"
CITE_PER_PAPER_ROOT = DEFAULT_DATA_ROOT / "processed/cite/2026/acl/per_paper"
MINERU_ROOT = DEFAULT_DATA_ROOT / "processed/mineru/acl/2026/acl"


def run_cmd(cmd: list[str], *, timeout: float = 1800.0) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s: {' '.join(cmd[:4])}"
    output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    return completed.returncode == 0, output.strip()[-4000:]


def nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


class PaperWorker:
    def __init__(self, args: argparse.Namespace, shared: dict[str, Any]) -> None:
        self.args = args
        self.output_root: Path = args.output_root
        self.client: VllmJsonClient = shared["client"]
        self.resolver: ExternalResolver = shared["resolver"]
        self.llm_sem: threading.Semaphore = shared["llm_sem"]
        self.net_sem: threading.Semaphore = shared["net_sem"]
        self.fallback_sem: threading.Semaphore = shared["fallback_sem"]

    # ---------- cite chain (soft gate) ----------

    def ensure_cite_inputs(self, paper_id: str, paper_dir: Path, state: dict[str, Any]) -> tuple[Path, Path]:
        """Return (references_jsonl, cite_contexts_jsonl) for this paper, building
        them with the existing v1 scripts when missing; degrade instead of blocking."""
        per_paper = CITE_PER_PAPER_ROOT / paper_id
        refs = per_paper / "verified_or_repaired.jsonl"
        cites = per_paper / "cite_contexts.jsonl"
        if nonempty(refs) and nonempty(cites):
            state["citation_source"] = "verified"
            return refs, cites

        mineru_dir = MINERU_ROOT / paper_id
        markdown = mineru_dir / "vlm" / f"{paper_id}.md"
        if not markdown.exists():
            raise RuntimeError(f"missing MinerU markdown: {markdown}")

        if not self.args.skip_cite_chain:
            per_paper.mkdir(parents=True, exist_ok=True)
            ok, _ = run_cmd(
                [
                    sys.executable,
                    "src/extract/references/extract_mineru_references.py",
                    str(mineru_dir),
                    "--output",
                    str(per_paper / "references.jsonl"),
                    "--summary",
                    str(per_paper / "references_summary.json"),
                ]
            )
            if ok:
                ok, _ = run_cmd(
                    [
                        sys.executable,
                        "src/extract/references/compare_mineru_reference_sources.py",
                        str(mineru_dir),
                        "--trusted-output",
                        str(per_paper / "verified_references.jsonl"),
                        "--mismatch-output",
                        str(per_paper / "reference_mismatches.jsonl"),
                        "--summary",
                        str(per_paper / "reference_comparison_summary.json"),
                    ]
                )
            if ok and nonempty(per_paper / "verified_references.jsonl"):
                refs.write_text((per_paper / "verified_references.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
            elif ok and self.args.repair_references:
                run_cmd(
                    [
                        sys.executable,
                        "src/extract/references/launch_kimi_reference_repairs.py",
                        "--summary",
                        str(per_paper / "reference_comparison_summary.json"),
                        "--mismatch-jsonl",
                        str(per_paper / "reference_mismatches.jsonl"),
                        "--primary-jsonl",
                        str(per_paper / "references.jsonl"),
                        "--verified-jsonl",
                        str(per_paper / "verified_references.jsonl"),
                        "--repaired-jsonl",
                        str(per_paper / "references_repaired.jsonl"),
                        "--verified-plus-jsonl",
                        str(refs),
                        "--repair-summary",
                        str(per_paper / "repair_summary.json"),
                        "--repairs-dir",
                        str(per_paper / "repairs"),
                        "--paper-id",
                        paper_id,
                        "--concurrency",
                        "1",
                        "--no-build-index",
                    ],
                    timeout=1800,
                )
            if nonempty(refs):
                ok, _ = run_cmd(
                    [
                        sys.executable,
                        "src/extract/references/extract_cite_contexts.py",
                        str(refs),
                        "--output",
                        str(cites),
                        "--summary",
                        str(per_paper / "cite_contexts_summary.json"),
                    ]
                )
                if ok and nonempty(cites):
                    state["citation_source"] = "verified"
                    return refs, cites

        # Soft gate: degrade instead of blocking (v1 would mark blocked_reference_mismatch).
        optional_dir = paper_dir / "optional"
        optional_dir.mkdir(parents=True, exist_ok=True)
        degraded_refs = optional_dir / "references.degraded.jsonl"
        degraded_refs.write_text(
            json.dumps({"paper_id": paper_id, "markdown_path": str(markdown), "references": []}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        degraded_cites = optional_dir / "cite_contexts.degraded.jsonl"
        markdown_text = markdown.read_text(encoding="utf-8", errors="replace")
        degraded = degraded_cite_contexts(paper_id, strip_references(markdown_text))
        degraded_cites.write_text(json.dumps(degraded, ensure_ascii=False) + "\n", encoding="utf-8")
        state["citation_source"] = "degraded"
        return degraded_refs, degraded_cites

    # ---------- repair / fallback ----------

    def repair_judgment(self, paper_id: str, paper_dir: Path, errors: str) -> bool:
        judgment_path = paper_dir / "agent_judgment.json"
        document = judgment_path.read_text(encoding="utf-8")
        with self.llm_sem:
            repaired, _ = self.client.json_call(
                system=REPAIR_SYSTEM,
                user=repair_user_prompt(document_json=document, errors_block=errors[:4000]),
                schema={"type": "object"},
                max_retries=1,
            )
        if repaired.get("paper_id") != paper_id:
            repaired["paper_id"] = paper_id
        write_json(judgment_path, repaired)
        return True

    def apply_and_validate(self, paper_id: str, paper_dir: Path) -> tuple[bool, str]:
        ok, output = run_cmd(
            [
                sys.executable,
                "src/extract/layer4/apply_agent_judgment.py",
                "--paper-id",
                paper_id,
                "--paper-dir",
                str(paper_dir),
            ]
        )
        if not ok:
            return False, f"apply failed:\n{output}"
        ok, output = run_cmd(
            [
                sys.executable,
                "src/extract/layer4/validate_layer4_outputs.py",
                "--paper-id",
                paper_id,
                "--paper-dir",
                str(paper_dir),
            ]
        )
        if not ok:
            issues = ""
            quality = paper_dir / "quality_report.json"
            if quality.exists():
                try:
                    issues = json.dumps(read_json(quality).get("issues") or [], ensure_ascii=False, indent=1)
                except Exception:
                    issues = output
            return False, f"validate failed:\n{issues or output}"
        return True, ""

    def fallback_agent(self, paper_id: str, refs: Path, cites: Path) -> tuple[bool, str]:
        with self.fallback_sem:
            return run_cmd(
                [
                    sys.executable,
                    "src/extract/layer4/launch_kimi_layer4.py",
                    "--paper-id",
                    paper_id,
                    "--references-jsonl",
                    str(refs),
                    "--cite-contexts-jsonl",
                    str(cites),
                    "--output-root",
                    str(self.output_root),
                    "--concurrency",
                    "1",
                    "--timeout",
                    str(self.args.fallback_timeout),
                    "--overwrite-prepare",
                    "--no-skip-existing",
                ],
                timeout=self.args.fallback_timeout + 300,
            )

    # ---------- per-paper pipeline ----------

    def process(self, paper_id: str) -> dict[str, Any]:
        paper_dir = self.output_root / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        state = load_state(paper_dir, paper_id)

        if not self.args.force and state.get("status") == "merged":
            return {"paper_id": paper_id, "status": "skipped_merged"}

        try:
            # cite chain (soft gate)
            started = time.monotonic()
            refs, cites = self.ensure_cite_inputs(paper_id, paper_dir, state)
            set_stage(state, "cite_chain", status="done", seconds=time.monotonic() - started,
                      citation_source=state.get("citation_source"))
            save_state(paper_dir, state)

            # prepare (v1 templates: base ymls, input_bundle, agent_prompt for fallback)
            if self.args.force or not (paper_dir / "paper_record.base.yml").exists():
                started = time.monotonic()
                ok, output = run_cmd(
                    [
                        sys.executable,
                        "src/extract/layer4/prepare_mineru_layer4.py",
                        "--paper-id",
                        paper_id,
                        "--references-jsonl",
                        str(refs),
                        "--cite-contexts-jsonl",
                        str(cites),
                        "--output-root",
                        str(self.output_root),
                        "--max-citations",
                        str(self.args.max_citations),
                        "--overwrite",
                    ]
                )
                if not ok:
                    raise RuntimeError(f"prepare failed: {output[:500]}")
                set_stage(state, "prepared", status="done", seconds=time.monotonic() - started)
                save_state(paper_dir, state)

            # inputs
            if self.args.force or not (paper_dir / "fulltext_for_llm.md").exists():
                started = time.monotonic()
                summary = build_inputs(
                    paper_id=paper_id,
                    references_jsonl=refs,
                    cite_contexts_jsonl=cites,
                    output_dir=paper_dir,
                )
                set_stage(state, "inputs_built", status="done", seconds=time.monotonic() - started, detail=summary)
                save_state(paper_dir, state)

            # LLM call 1
            if self.args.force or not (paper_dir / "semantic_candidates.json").exists():
                started = time.monotonic()
                with self.llm_sem:
                    summary = run_extraction(
                        paper_id=paper_id,
                        paper_dir=paper_dir,
                        cite_contexts_jsonl=cites,
                        client=self.client,
                    )
                set_stage(state, "candidates_done", status="done", seconds=time.monotonic() - started, detail=summary)
                save_state(paper_dir, state)

            # external verification
            if self.args.force or not (paper_dir / "external_resolution.json").exists():
                started = time.monotonic()
                with self.net_sem:
                    summary = self.resolver.resolve_paper(paper_id=paper_id, paper_dir=paper_dir)
                set_stage(state, "verified", status="done", seconds=time.monotonic() - started, detail=summary)
                save_state(paper_dir, state)

            # LLM call 2 + assembly
            if self.args.force or not (paper_dir / "agent_judgment.json").exists():
                started = time.monotonic()
                with self.llm_sem:
                    summary = run_judgment(paper_id=paper_id, paper_dir=paper_dir, client=self.client)
                set_stage(state, "judged", status="done", seconds=time.monotonic() - started, detail=summary)
                save_state(paper_dir, state)

            # apply + validate, with repair retries
            started = time.monotonic()
            ok, message = self.apply_and_validate(paper_id, paper_dir)
            repairs = 0
            while not ok and repairs < self.args.max_repairs:
                repairs += 1
                try:
                    self.repair_judgment(paper_id, paper_dir, message)
                except Exception as exc:  # noqa: BLE001
                    message = f"repair call failed: {exc}"
                    break
                ok, message = self.apply_and_validate(paper_id, paper_dir)
            if ok:
                set_stage(state, "merged", status="done", seconds=time.monotonic() - started, repairs=repairs)
                save_state(paper_dir, state)
                return {"paper_id": paper_id, "status": "merged", "repairs": repairs,
                        "citation_source": state.get("citation_source")}

            # ReAct-agent fallback
            if self.args.no_fallback:
                state["status"] = "blocked_v2_manual"
                set_stage(state, "blocked_v2_manual", status="failed", error=message[:2000])
                save_state(paper_dir, state)
                return {"paper_id": paper_id, "status": "blocked_v2_manual", "message": message[:500]}

            set_stage(state, "fallback_agent", status="running", error=message[:2000])
            state["status"] = "fallback_agent"
            save_state(paper_dir, state)
            started = time.monotonic()
            ok, output = self.fallback_agent(paper_id, refs, cites)
            if ok:
                ok, message = self.apply_and_validate(paper_id, paper_dir)
            if ok:
                set_stage(state, "merged", status="done", seconds=time.monotonic() - started, via="fallback_agent")
                state["fallback"] = "react_agent"
                save_state(paper_dir, state)
                return {"paper_id": paper_id, "status": "merged_via_fallback"}
            state["status"] = "blocked_v2_manual"
            set_stage(state, "blocked_v2_manual", status="failed", error=(message or output)[:2000])
            save_state(paper_dir, state)
            return {"paper_id": paper_id, "status": "blocked_v2_manual", "message": (message or output)[:500]}

        except Exception as exc:  # noqa: BLE001
            state["status"] = "error"
            set_stage(state, "error", status="failed", error=f"{exc}\n{traceback.format_exc()[-1500:]}")
            save_state(paper_dir, state)
            return {"paper_id": paper_id, "status": "error", "message": str(exc)[:500]}


def selected_paper_ids(args: argparse.Namespace) -> list[str]:
    explicit = list(args.paper_id or [])
    for path in args.paper_id_file or []:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                explicit.append(value)
    if explicit:
        return explicit[: args.limit] if args.limit else explicit

    ids: list[str] = []
    with args.references_jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            record = json.loads(line)
            paper_id = record.get("paper_id")
            if not paper_id:
                continue
            if args.skip_front_matter and is_probable_front_matter(record):
                continue
            ids.append(paper_id)
    if args.venue_filter:
        ids = [pid for pid in ids if args.venue_filter in pid]
    if args.limit:
        ids = ids[: args.limit]
    return ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Layer4 v2 batch orchestrator.")
    parser.add_argument("--references-jsonl", type=Path, default=DEFAULT_REFERENCES_JSONL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_LAYER4_V2_ROOT)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_V2_CACHE_ROOT)
    parser.add_argument("--paper-id", action="append", help="Limit to one paper id; repeatable.")
    parser.add_argument("--paper-id-file", action="append", type=Path)
    parser.add_argument("--venue-filter", default="", help="Substring filter on paper ids, e.g. acl-long.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=12, help="Per-paper pipeline workers.")
    parser.add_argument("--llm-concurrency", type=int, default=8)
    parser.add_argument("--net-concurrency", type=int, default=4)
    parser.add_argument("--max-citations", type=int, default=200)
    parser.add_argument("--max-repairs", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--fallback-timeout", type=int, default=3600)
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--skip-cite-chain", action="store_true", help="Never run v1 cite scripts; degrade directly.")
    parser.add_argument("--repair-references", action="store_true", default=True)
    parser.add_argument("--no-repair-references", dest="repair_references", action="store_false")
    parser.add_argument("--skip-front-matter", action="store_true", default=True)
    parser.add_argument("--include-front-matter", dest="skip_front_matter", action="store_false")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--force", action="store_true", help="Redo all stages even when products exist.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    paper_ids = selected_paper_ids(args)
    if not paper_ids:
        raise SystemExit("no papers selected")
    print(f"selected {len(paper_ids)} papers; workers={args.workers} llm={args.llm_concurrency}", flush=True)

    shared = {
        "client": VllmJsonClient(max_tokens=args.max_tokens),
        "resolver": ExternalResolver(cache_root=args.cache_root, refresh=args.refresh_cache),
        "llm_sem": threading.Semaphore(args.llm_concurrency),
        "net_sem": threading.Semaphore(args.net_concurrency),
        "fallback_sem": threading.Semaphore(1),
    }
    worker = PaperWorker(args, shared)

    results: list[dict[str, Any]] = []
    batch_started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(worker.process, paper_id): paper_id for paper_id in paper_ids}
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            print(f"[{index}/{len(paper_ids)}] {result['paper_id']} -> {result['status']}", flush=True)

    elapsed = time.monotonic() - batch_started
    by_status: dict[str, int] = {}
    for result in results:
        by_status[result["status"]] = by_status.get(result["status"], 0) + 1
    summary = {
        "generated_at": now_iso(),
        "paper_count": len(results),
        "elapsed_seconds": round(elapsed, 1),
        "papers_per_hour": round(len(results) / elapsed * 3600, 1) if elapsed > 0 else None,
        "status_counts": by_status,
        "llm_concurrency": args.llm_concurrency,
        "workers": args.workers,
        "results": results,
    }
    write_json(args.output_root / "batch_report.json", summary)
    failures = [r for r in results if r["status"] not in {"merged", "merged_via_fallback", "skipped_merged"}]
    write_json(args.output_root / "batch_failures.json", {"failures": failures})
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
