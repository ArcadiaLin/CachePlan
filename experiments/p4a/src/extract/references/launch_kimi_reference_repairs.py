#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/references/launch_kimi_reference_repairs.py --summary /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_reference_comparison_summary.json --mismatch-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_reference_mismatches.jsonl --primary-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_references.jsonl --verified-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_verified_references.jsonl --verified-plus-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/acl2026_verified_plus_repaired.jsonl --repairs-dir /srv/datasets/p4a/data/processed/cite/2026/acl/repairs
"""Launch Kimi agents to manually repair problematic ACL reference records."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from extract_mineru_references import DEFAULT_DATA_ROOT, display_path, parse_reference


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPT_DIR / "results"
REPAIRS_DIR = RESULTS_DIR / "repairs"
PROMPTS_DIR = REPAIRS_DIR / "prompts"
LOGS_DIR = REPAIRS_DIR / "logs"
RECORDS_DIR = REPAIRS_DIR / "records"

FALLBACK_KIMI_BIN = Path("~/.kimi-code/bin/kimi").expanduser()
COMPARISON_SUMMARY = RESULTS_DIR / "acl2025_reference_comparison_summary.json"
MISMATCH_JSONL = RESULTS_DIR / "acl2025_reference_mismatches.jsonl"
PRIMARY_JSONL = RESULTS_DIR / "acl2025_references.jsonl"
VERIFIED_JSONL = RESULTS_DIR / "acl2025_verified_references.jsonl"
REPAIRED_JSONL = RESULTS_DIR / "acl2025_references_repaired.jsonl"
VERIFIED_PLUS_REPAIRED_JSONL = RESULTS_DIR / "acl2025_verified_plus_repaired.jsonl"
REPAIR_SUMMARY = RESULTS_DIR / "acl2025_repair_summary.json"
FAILURES_JSON = REPAIRS_DIR / "repair_failures.json"
UPDATE_SCRIPT = SCRIPT_DIR / "update_reference_record.py"
INDEX_SCRIPT = SCRIPT_DIR / "build_reference_index.py"
REPAIRED_INDEX_JSONL = RESULTS_DIR / "acl2025_repaired_reference_index.jsonl"
REPAIRED_INDEX_SUMMARY = RESULTS_DIR / "acl2025_repaired_reference_index_summary.json"


REQUIRED_REFERENCE_FIELDS = [
    "index",
    "raw",
    "authors",
    "year",
    "title",
    "arxiv_ids",
    "dois",
    "urls",
    "confidence",
    "warnings",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def configure_repair_dirs(repairs_dir: Path) -> None:
    global REPAIRS_DIR, PROMPTS_DIR, LOGS_DIR, RECORDS_DIR, FAILURES_JSON
    REPAIRS_DIR = repairs_dir
    PROMPTS_DIR = REPAIRS_DIR / "prompts"
    LOGS_DIR = REPAIRS_DIR / "logs"
    RECORDS_DIR = REPAIRS_DIR / "records"
    FAILURES_JSON = REPAIRS_DIR / "repair_failures.json"


def jsonl_by_paper_id(path: Path) -> dict[str, dict[str, Any]]:
    return {row["paper_id"]: row for row in load_jsonl(path)}


def ensure_dirs() -> None:
    for path in (PROMPTS_DIR, LOGS_DIR, RECORDS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def problem_papers(
    summary_path: Path,
    mismatch_jsonl: Path,
    paper_ids: set[str] | None,
) -> list[dict[str, Any]]:
    summary = load_json(summary_path)
    problems = summary.get("problem_papers") or []
    if not isinstance(problems, list):
        raise ValueError(f"{summary_path} does not contain a list problem_papers")
    mismatch_rows = jsonl_by_paper_id(mismatch_jsonl)
    enriched = []
    for problem in problems:
        paper_id = str(problem.get("paper_id"))
        row = mismatch_rows.get(paper_id, {})
        enriched_problem = dict(problem)
        if "source_dir" not in enriched_problem and row.get("source_dir"):
            enriched_problem["source_dir"] = row["source_dir"]
        if "content_list" not in enriched_problem and row.get("content_list"):
            enriched_problem["content_list"] = row["content_list"]
        if "markdown" not in enriched_problem and row.get("markdown"):
            enriched_problem["markdown"] = row["markdown"]
        enriched.append(enriched_problem)
    problems = enriched
    if paper_ids is not None:
        problems = [problem for problem in problems if problem.get("paper_id") in paper_ids]
    return problems


def related_paths(problem: dict[str, Any]) -> dict[str, str | None]:
    source_dir = resolve_data_path(str(problem["source_dir"]))
    paper_id = str(problem["paper_id"])
    candidates = {
        "content_list": source_dir / f"{paper_id}_content_list.json",
        "content_list_v2": source_dir / f"{paper_id}_content_list_v2.json",
        "markdown": source_dir / f"{paper_id}.md",
        "origin_pdf": source_dir / f"{paper_id}_origin.pdf",
        "layout_pdf": source_dir / f"{paper_id}_layout.pdf",
        "middle_json": source_dir / f"{paper_id}_middle.json",
        "model_json": source_dir / f"{paper_id}_model.json",
    }
    return {
        key: display_path(path) if path.exists() else None
        for key, path in candidates.items()
    }


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


def repair_record_path(paper_id: str) -> Path:
    return RECORDS_DIR / f"{paper_id}.json"


def prompt_path(paper_id: str) -> Path:
    return PROMPTS_DIR / f"{paper_id}.txt"


def log_path(paper_id: str) -> Path:
    return LOGS_DIR / f"{paper_id}.log"


def build_prompt(
    problem: dict[str, Any],
    current_record: dict[str, Any] | None,
    output_path: Path,
) -> str:
    paper_id = str(problem["paper_id"])
    paths = related_paths(problem)
    current_payload = current_record or {
        "paper_id": paper_id,
        "source_dir": problem.get("source_dir"),
        "source": "missing_current_record",
        "references": [],
        "reference_count": 0,
        "warnings": ["current record was not found"],
    }

    metadata = {
        "paper_id": paper_id,
        "source_dir": problem.get("source_dir"),
        "status": problem.get("status"),
        "issue_category": problem.get("issue_category"),
        "content_list_count": problem.get("content_list_count"),
        "markdown_count": problem.get("markdown_count"),
        "warnings": problem.get("warnings"),
        "first_difference": problem.get("first_difference"),
        "paths": paths,
        "repair_record_output": display_path(output_path),
    }

    return f"""You are repairing one ACL 2025 reference-extraction record.

Repository root: {REPO_ROOT}

Your task is strictly limited to this paper:

```json
{json.dumps(metadata, ensure_ascii=False, indent=2)}
```

Current extracted record:

```json
{json.dumps(current_payload, ensure_ascii=False, indent=2)}
```

Rules:
- Repair ONLY this paper_id: {paper_id}
- Do NOT modify shared JSONL files under src/extract/references/results.
- Write exactly one complete JSON object to:
  {output_path}
- The JSON object must be compatible with acl2025_references.jsonl and must contain:
  paper_id, source_dir, source, references, reference_count, warnings.
- Set source to "kimi_manual_repair".
- reference_count must equal len(references).
- Reference indexes must be 1..N in order.
- Each reference must contain:
  index, raw, authors, year, title, arxiv_ids, dois, urls, confidence, warnings.
- Use confidence "high" when the reference is clear from source material, otherwise "medium" or "low".

How to inspect the source:
- Read the Markdown, content_list, content_list_v2, middle/model JSON if useful.
- If the sources disagree or look corrupted, inspect the original PDF text with:
  mutool draw -F text -o /tmp/{paper_id}.txt <origin_pdf_path>
- Use the actual References/Bibliography section of the paper.
- Exclude Appendix, Supplement, Figure captions, Table captions, Algorithm blocks, prompt templates,
  and any non-reference text accidentally absorbed after the reference section.

Issue handling:
- markdown_absorbed_non_reference_blocks: trim non-reference appendix/table/figure/algorithm text from references.
- reference_count_diff: split fused references, remove extra non-reference entries, and restore missed entries.
- text_diff_other: use the original paper as truth and keep complete reference text without attached body text.
- hyphenation_or_spacing_only: fix broken words, spacing, and line-wrap artifacts.
- missing_markdown_references: verify whether this is a real paper with references. If no references exist,
  output references=[] and warnings containing "manual repair: no references found in original paper".

After writing the JSON file, validate it with:
python3 -m json.tool {output_path}

Return a short status summary only after the file has been written.
"""


def extract_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    candidates: list[str] = []
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL):
        candidates.append(match.group(1))
    candidates.append(text)

    for candidate in candidates:
        for start_match in re.finditer(r"\{", candidate):
            try:
                value, _end = decoder.raw_decode(candidate[start_match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "paper_id" in value and "references" in value:
                return value
    return None


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def normalize_reference(reference: dict[str, Any], index: int) -> dict[str, Any]:
    raw = str(reference.get("raw") or "").strip()
    if not raw:
        raise ValueError(f"reference {index} has empty raw")

    parsed = parse_reference(index, raw, "kimi_manual_repair")
    normalized = {
        "index": index,
        "raw": raw,
        "authors": str(reference.get("authors") or parsed.authors or "").strip(),
        "year": str(reference.get("year") or parsed.year or "").strip(),
        "title": str(reference.get("title") or parsed.title or "").strip(),
        "arxiv_ids": normalize_list(reference.get("arxiv_ids") or parsed.arxiv_ids),
        "dois": normalize_list(reference.get("dois") or parsed.dois),
        "urls": normalize_list(reference.get("urls") or parsed.urls),
        "confidence": str(reference.get("confidence") or parsed.confidence or "medium").strip(),
        "warnings": normalize_list(reference.get("warnings") or parsed.warnings),
    }
    for field in REQUIRED_REFERENCE_FIELDS:
        normalized.setdefault(field, [] if field in {"arxiv_ids", "dois", "urls", "warnings"} else "")
    return normalized


def validate_and_normalize_record(
    record: dict[str, Any],
    paper_id: str,
    source_dir: str,
) -> dict[str, Any]:
    if record.get("paper_id") != paper_id:
        raise ValueError(f"paper_id mismatch: expected {paper_id}, got {record.get('paper_id')!r}")

    references = record.get("references")
    if not isinstance(references, list):
        raise ValueError("references must be a list")

    normalized_refs = []
    for index, reference in enumerate(references, start=1):
        if not isinstance(reference, dict):
            raise ValueError(f"reference {index} is not a JSON object")
        normalized_refs.append(normalize_reference(reference, index))

    normalized = dict(record)
    normalized["paper_id"] = paper_id
    normalized["source_dir"] = source_dir
    normalized["source"] = "kimi_manual_repair"
    normalized["references"] = normalized_refs
    normalized["reference_count"] = len(normalized_refs)
    normalized["warnings"] = normalize_list(normalized.get("warnings"))
    if not normalized_refs and not any("no references found" in warning for warning in normalized["warnings"]):
        normalized["warnings"].append("manual repair: no references found in original paper")
    return normalized


def load_repair_record(path: Path, paper_id: str, source_dir: str) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError(f"{path} is not a JSON object")
    return validate_and_normalize_record(record, paper_id, source_dir)


def save_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_kimi_bin() -> str:
    candidates: list[str] = []
    env_bin = os.environ.get("KIMI_BIN")
    if env_bin:
        candidates.append(env_bin)
    candidates.extend(["kimi-code", "kimi"])
    if FALLBACK_KIMI_BIN.exists():
        candidates.append(str(FALLBACK_KIMI_BIN))

    for candidate in candidates:
        if os.path.isabs(candidate) or os.sep in candidate:
            path = Path(candidate).expanduser()
            if path.exists() and os.access(path, os.X_OK):
                return str(path)
        else:
            found = shutil.which(candidate)
            if found:
                return found

    raise RuntimeError(
        f"Unable to find Kimi CLI. Tried KIMI_BIN, kimi-code, kimi, and {FALLBACK_KIMI_BIN}."
    )


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def run_kimi_once(
    problem: dict[str, Any],
    current_record: dict[str, Any] | None,
    timeout: int,
    permission_mode: str,
) -> tuple[bool, str]:
    paper_id = str(problem["paper_id"])
    source_dir = str(problem["source_dir"])
    output_path = repair_record_path(paper_id)
    prompt_file = prompt_path(paper_id)
    prompt_file.write_text(build_prompt(problem, current_record, output_path), encoding="utf-8")

    prompt_arg = (
        "Read this UTF-8 prompt file and follow its instructions exactly:\n"
        f"{display_path(prompt_file)}\n\n"
        "The prompt file contains the full task. Do not summarize it back. "
        "After completing the task, return only a short status summary."
    )
    cmd = [resolve_kimi_bin()]
    if permission_mode == "yolo":
        cmd.append("--yolo")
    elif permission_mode == "auto":
        cmd.append("--auto")
    cmd.extend(["--output-format", "text", "--prompt", prompt_arg])

    started = time.time()
    captured_output: list[str] = []
    returncode: int | str | None = None
    timed_out = False

    log_file = log_path(paper_id)
    with log_file.open("w", encoding="utf-8") as log:
        log.write(
            "\n".join(
                [
                    f"paper_id: {paper_id}",
                    "status: running",
                    f"prompt_file: {prompt_file}",
                    f"repair_record_output: {output_path}",
                    f"command: {shlex.join(cmd[:3] + ['--prompt', '<prompt omitted from log>'])}",
                    "",
                    "## STREAM stdout+stderr",
                    "",
                ]
            )
        )
        log.flush()

        process = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

        assert process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)

        while True:
            elapsed = time.time() - started
            if elapsed > timeout:
                timed_out = True
                log.write(f"\n## TIMEOUT\nExceeded timeout after {elapsed:.1f}s; terminating Kimi.\n")
                log.flush()
                terminate_process_group(process)
                break

            events = selector.select(timeout=0.5)
            for key, _event in events:
                line = key.fileobj.readline()
                if line:
                    captured_output.append(line)
                    log.write(line)
                    log.flush()

            if process.poll() is not None:
                remaining = process.stdout.read()
                if remaining:
                    captured_output.append(remaining)
                    log.write(remaining)
                    log.flush()
                break

        selector.close()
        returncode = "timeout" if timed_out else process.returncode
        elapsed = time.time() - started
        log.write(
            "\n".join(
                [
                    "",
                    "## RESULT",
                    f"returncode: {returncode}",
                    f"elapsed_seconds: {elapsed:.1f}",
                    "",
                ]
            )
        )
        log.flush()

    stream_text = "".join(captured_output)
    if timed_out:
        return False, f"timeout after {timeout}s"

    if output_path.exists():
        try:
            normalized = load_repair_record(output_path, paper_id, source_dir)
            save_record(output_path, normalized)
            return True, "record file written and valid"
        except Exception as exc:  # noqa: BLE001
            return False, f"invalid record file: {exc}"

    extracted = extract_json_object(stream_text)
    if extracted is not None:
        try:
            normalized = validate_and_normalize_record(extracted, paper_id, source_dir)
            save_record(output_path, normalized)
            return True, "record recovered from stdout"
        except Exception as exc:  # noqa: BLE001
            return False, f"stdout JSON invalid: {exc}"

    if returncode != 0:
        return False, f"kimi exited with {returncode}"
    return False, "kimi did not write a repair record"


def run_one_problem(
    problem: dict[str, Any],
    current_records: dict[str, dict[str, Any]],
    timeout: int,
    max_retries: int,
    permission_mode: str,
    skip_existing: bool,
) -> dict[str, Any]:
    paper_id = str(problem["paper_id"])
    source_dir = str(problem["source_dir"])
    output_path = repair_record_path(paper_id)

    if skip_existing and output_path.exists():
        try:
            load_repair_record(output_path, paper_id, source_dir)
            return {"paper_id": paper_id, "status": "skipped_existing", "attempts": 0}
        except Exception:
            pass

    attempts = 0
    last_message = ""
    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        ok, message = run_kimi_once(
            problem,
            current_records.get(paper_id),
            timeout,
            permission_mode,
        )
        last_message = message
        if ok:
            return {"paper_id": paper_id, "status": "fixed", "attempts": attempts, "message": message}
    return {"paper_id": paper_id, "status": "failed", "attempts": attempts, "message": last_message}


def launch_repairs(args: argparse.Namespace) -> list[dict[str, Any]]:
    ensure_dirs()
    selected_ids = set(args.paper_id or []) if args.paper_id else None
    problems = problem_papers(args.summary, args.mismatch_jsonl, selected_ids)
    if args.limit:
        problems = problems[: args.limit]
    current_records = jsonl_by_paper_id(args.primary_jsonl)

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        future_to_problem = {
            executor.submit(
                run_one_problem,
                problem,
                current_records,
                args.timeout,
                args.max_retries,
                args.permission_mode,
                args.skip_existing,
            ): problem
            for problem in problems
        }
        for future in concurrent.futures.as_completed(future_to_problem):
            result = future.result()
            results.append(result)
            print(
                f"[{len(results)}/{len(problems)}] {result['paper_id']} "
                f"{result['status']} attempts={result.get('attempts')} {result.get('message', '')}",
                flush=True,
            )

    results.sort(key=lambda row: row["paper_id"])
    failures = [row for row in results if row["status"] == "failed"]
    FAILURES_JSON.write_text(json.dumps(failures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return results


def record_status(record: dict[str, Any]) -> str:
    if record.get("reference_count") == 0:
        return "confirmed_empty"
    return "fixed"


def merge_repairs(args: argparse.Namespace) -> dict[str, Any]:
    selected_ids = set(args.paper_id or []) if args.paper_id else None
    problems = problem_papers(args.summary, args.mismatch_jsonl, selected_ids)
    problem_ids = [str(problem["paper_id"]) for problem in problems]

    repaired_records: dict[str, dict[str, Any]] = {}
    invalid: list[dict[str, str]] = []
    for problem in problems:
        paper_id = str(problem["paper_id"])
        path = repair_record_path(paper_id)
        if not path.exists():
            invalid.append({"paper_id": paper_id, "error": f"missing repair record: {path}"})
            continue
        try:
            repaired_records[paper_id] = load_repair_record(path, paper_id, str(problem["source_dir"]))
        except Exception as exc:  # noqa: BLE001
            invalid.append({"paper_id": paper_id, "error": str(exc)})

    if invalid:
        FAILURES_JSON.write_text(json.dumps(invalid, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(f"{len(invalid)} repair records are missing or invalid; see {FAILURES_JSON}")

    shutil.copy2(args.primary_jsonl, args.repaired_jsonl)
    for paper_id in problem_ids:
        record_file = repair_record_path(paper_id)
        subprocess.run(
            [
                sys.executable,
                str(UPDATE_SCRIPT),
                str(args.repaired_jsonl),
                "--paper-id",
                paper_id,
                "--record-file",
                str(record_file),
            ],
            cwd=str(REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )

    verified_records = jsonl_by_paper_id(args.verified_jsonl)
    full_records = load_jsonl(args.repaired_jsonl)
    verified_plus: list[dict[str, Any]] = []
    for record in full_records:
        paper_id = str(record["paper_id"])
        if paper_id in repaired_records:
            verified_plus.append(repaired_records[paper_id])
        elif paper_id in verified_records:
            verified_plus.append(verified_records[paper_id])

    with args.verified_plus_jsonl.open("w", encoding="utf-8") as stream:
        for record in verified_plus:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    fixed = sorted(
        paper_id for paper_id, record in repaired_records.items() if record_status(record) == "fixed"
    )
    confirmed_empty = sorted(
        paper_id
        for paper_id, record in repaired_records.items()
        if record_status(record) == "confirmed_empty"
    )
    summary = {
        "problem_count": len(problem_ids),
        "repair_record_count": len(repaired_records),
        "fixed_count": len(fixed),
        "confirmed_empty_count": len(confirmed_empty),
        "failed_count": 0,
        "fixed_paper_ids": fixed,
        "confirmed_empty_paper_ids": confirmed_empty,
        "repaired_jsonl": display_path(args.repaired_jsonl),
        "verified_plus_repaired_jsonl": display_path(args.verified_plus_jsonl),
        "repaired_jsonl_line_count": len(full_records),
        "verified_plus_repaired_line_count": len(verified_plus),
    }
    args.repair_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.build_index:
        subprocess.run(
            [
                sys.executable,
                str(INDEX_SCRIPT),
                str(args.repaired_jsonl),
                "--output",
                str(args.repaired_index_jsonl),
                "--summary",
                str(args.repaired_index_summary),
            ],
            cwd=str(REPO_ROOT),
            check=True,
        )

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch Kimi agents for ACL reference repairs.")
    parser.add_argument("--summary", type=Path, default=COMPARISON_SUMMARY)
    parser.add_argument("--mismatch-jsonl", type=Path, default=MISMATCH_JSONL)
    parser.add_argument("--primary-jsonl", type=Path, default=PRIMARY_JSONL)
    parser.add_argument("--verified-jsonl", type=Path, default=VERIFIED_JSONL)
    parser.add_argument("--repaired-jsonl", type=Path, default=REPAIRED_JSONL)
    parser.add_argument("--verified-plus-jsonl", type=Path, default=VERIFIED_PLUS_REPAIRED_JSONL)
    parser.add_argument("--repair-summary", type=Path, default=REPAIR_SUMMARY)
    parser.add_argument("--repairs-dir", type=Path, default=REPAIRS_DIR)
    parser.add_argument("--repaired-index-jsonl", type=Path, default=REPAIRED_INDEX_JSONL)
    parser.add_argument("--repaired-index-summary", type=Path, default=REPAIRED_INDEX_SUMMARY)
    parser.add_argument("--paper-id", action="append", help="Limit to one paper id; repeatable.")
    parser.add_argument("--limit", type=int, help="Process only the first N selected problem papers.")
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument(
        "--permission-mode",
        choices=("none", "yolo", "auto"),
        default="none",
        help="Kimi permission flag. Kimi 0.14.1 cannot combine prompt mode with yolo/auto.",
    )
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    parser.add_argument("--merge-only", action="store_true", help="Only merge existing repair records.")
    parser.add_argument("--no-build-index", dest="build_index", action="store_false")
    parser.set_defaults(build_index=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_repair_dirs(args.repairs_dir)
    ensure_dirs()

    launch_results: list[dict[str, Any]] = []
    if not args.merge_only:
        launch_results = launch_repairs(args)
        failures = [row for row in launch_results if row["status"] == "failed"]
        if failures:
            print(f"{len(failures)} Kimi repair tasks failed; see {FAILURES_JSON}", file=sys.stderr)
            return

    summary = merge_repairs(args)
    if launch_results:
        retried = sorted(row["paper_id"] for row in launch_results if row.get("attempts", 0) > 1)
        summary["retried_count"] = len(retried)
        summary["retried_paper_ids"] = retried
        summary["launch_status_counts"] = {
            status: sum(1 for row in launch_results if row["status"] == status)
            for status in sorted({row["status"] for row in launch_results})
        }
        args.repair_summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
