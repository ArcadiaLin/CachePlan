#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4/launch_kimi_layer4.py --paper-id <paper_id> --references-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/<paper_id>/verified_or_repaired.jsonl --cite-contexts-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/<paper_id>/cite_contexts.jsonl --output-root /srv/datasets/p4a/data/processed/layer4/2026/acl --concurrency 1
"""Launch multiple Kimi agents for MinerU Layer 4 resource extraction."""

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import DEFAULT_CITE_CONTEXTS_JSONL, DEFAULT_LAYER4_ROOT, DEFAULT_REFERENCES_JSONL, REPO_ROOT, load_jsonl, read_yaml, repo_relative, write_json
from prepare_mineru_layer4 import main as _prepare_main  # imported only to ensure script dependencies are importable


FALLBACK_KIMI_BIN = Path("~/.kimi-code/bin/kimi").expanduser()
# arxiv.org 直连限速 ~10KB/s, huggingface.co 直连不通; 统一走本地代理,
# 本地服务(vLLM/MinerU)与 export.arxiv.org(直连更快)除外.
KIMI_PROXY = "http://127.0.0.1:7899"
KIMI_NO_PROXY = "127.0.0.1,localhost,192.168.163.112,export.arxiv.org"
PREPARE_SCRIPT = Path(__file__).resolve().parent / "prepare_mineru_layer4.py"
APPLY_SCRIPT = Path(__file__).resolve().parent / "apply_agent_judgment.py"
VALIDATE_SCRIPT = Path(__file__).resolve().parent / "validate_layer4_outputs.py"
SESSION_ID_RE = re.compile(r"\bsession_[0-9a-fA-F-]{36}\b")


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

    raise RuntimeError(f"Unable to find Kimi CLI. Tried KIMI_BIN, kimi-code, kimi, and {FALLBACK_KIMI_BIN}.")


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


def attempt_suffix(attempt: int) -> str:
    return "" if attempt == 1 else f".attempt_{attempt}"


def extract_session_id(text: str) -> str:
    matches = SESSION_ID_RE.findall(text)
    return matches[-1] if matches else ""


def find_kimi_session_dir(session_id: str) -> Path | None:
    if not session_id:
        return None
    sessions_root = Path("~/.kimi-code/sessions").expanduser()
    for candidate in sessions_root.glob(f"**/{session_id}"):
        if candidate.is_dir():
            return candidate
    return None


def compact_tool_event(obj: dict[str, Any]) -> dict[str, Any] | None:
    event = obj.get("event") if obj.get("type") == "context.append_loop_event" else obj
    if not isinstance(event, dict):
        return None
    event_type = str(event.get("type") or "")
    if event_type == "tool.call":
        return {
            "type": "tool.call",
            "time": obj.get("time") or event.get("time"),
            "tool_call_id": event.get("toolCallId"),
            "name": event.get("name"),
            "description": event.get("description"),
            "args": event.get("args"),
            "display": event.get("display"),
        }
    if event_type == "tool.result":
        result = event.get("result")
        output = ""
        if isinstance(result, dict):
            output = str(result.get("output") or result.get("stdout") or result.get("stderr") or "")
        elif result is not None:
            output = str(result)
        return {
            "type": "tool.result",
            "time": obj.get("time") or event.get("time"),
            "tool_call_id": event.get("toolCallId"),
            "parent_uuid": event.get("parentUuid"),
            "output_chars": len(output),
            "output_preview": output[:2000],
        }
    return None


def collect_kimi_wire_artifacts(*, paper_dir: Path, captured_text: str, attempt: int) -> dict[str, Any]:
    session_id = extract_session_id(captured_text)
    suffix = attempt_suffix(attempt)
    summary: dict[str, Any] = {
        "session_id": session_id,
        "session_dir": "",
        "wire_copied": False,
        "tool_call_count": 0,
        "tool_result_count": 0,
        "tool_counts": {},
        "usage_records": [],
        "usage_totals": {},
        "warnings": [],
    }
    session_dir = find_kimi_session_dir(session_id)
    if not session_dir:
        if session_id:
            summary["warnings"].append(f"session directory not found for {session_id}")
        else:
            summary["warnings"].append("session id not found in Kimi output")
        return summary

    summary["session_dir"] = str(session_dir)
    wire_path = session_dir / "agents/main/wire.jsonl"
    state_path = session_dir / "state.json"
    if state_path.exists():
        shutil.copy2(state_path, paper_dir / f"agent_kimi_state{suffix}.json")
    if not wire_path.exists():
        summary["warnings"].append(f"wire log not found: {wire_path}")
        return summary

    copied_wire = paper_dir / f"agent_wire{suffix}.jsonl"
    tool_events_path = paper_dir / f"agent_tool_events{suffix}.jsonl"
    shutil.copy2(wire_path, copied_wire)
    summary["wire_copied"] = True
    summary["wire_log"] = repo_relative(copied_wire)
    summary["tool_events"] = repo_relative(tool_events_path)

    usage_totals: dict[str, float] = {}
    usage_records: list[dict[str, Any]] = []
    tool_counts: dict[str, int] = {}
    with wire_path.open("r", encoding="utf-8", errors="replace") as source, tool_events_path.open("w", encoding="utf-8") as tool_stream:
        for line in source:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") == "usage.record":
                usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
                record = {
                    "time": obj.get("time"),
                    "model": obj.get("model"),
                    "usage_scope": obj.get("usageScope"),
                    "usage": usage,
                }
                usage_records.append(record)
                for key, value in usage.items():
                    if isinstance(value, (int, float)):
                        usage_totals[key] = usage_totals.get(key, 0) + float(value)

            compact = compact_tool_event(obj)
            if compact:
                tool_stream.write(json.dumps(compact, ensure_ascii=False) + "\n")
                if compact["type"] == "tool.call":
                    summary["tool_call_count"] = int(summary["tool_call_count"]) + 1
                    name = str(compact.get("name") or "unknown")
                    tool_counts[name] = tool_counts.get(name, 0) + 1
                elif compact["type"] == "tool.result":
                    summary["tool_result_count"] = int(summary["tool_result_count"]) + 1

    summary["usage_records"] = usage_records
    summary["usage_totals"] = usage_totals
    summary["tool_counts"] = tool_counts
    return summary


def is_probable_front_matter(record: dict[str, Any]) -> bool:
    paper_id = str(record.get("paper_id") or "")
    warnings = " ".join(str(item).lower() for item in record.get("warnings") or [])
    if "front-matter" in warnings or "front matter" in warnings:
        return True
    if "not a research paper" in warnings:
        return True
    # ACL anthology volume/proceedings records often look like 2025.acl-demo
    # while paper records have a numeric final component, e.g. 2025.acl-demo.16.
    if not paper_id.rsplit(".", 1)[-1].isdigit():
        return True
    return False


def selected_paper_ids(
    references_jsonl: Path,
    paper_ids: list[str] | None,
    paper_id_files: list[Path] | None,
    limit: int | None,
    skip_front_matter: bool,
) -> list[str]:
    ids: list[str] = []
    if paper_id_files:
        for paper_id_file in paper_id_files:
            for line in paper_id_file.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    ids.append(line)
    if paper_ids:
        ids.extend(paper_ids)
    if ids:
        ids = list(dict.fromkeys(ids))
    else:
        records = load_jsonl(references_jsonl)
        if skip_front_matter:
            records = [row for row in records if not is_probable_front_matter(row)]
        ids = [str(row["paper_id"]) for row in records]
    if limit is not None:
        ids = ids[:limit]
    return ids


def quality_ok(paper_dir: Path) -> bool:
    merge_report_path = paper_dir / "agent_merge_report.json"
    if merge_report_path.exists():
        try:
            merge_report = json.loads(merge_report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        if str(merge_report.get("status") or "").lower() == "failed":
            return False

    report_path = paper_dir / "quality_report.json"
    if not report_path.exists():
        return False
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not bool(report.get("ok")):
        return False

    run_report_path = paper_dir / "run_report.json"
    if not run_report_path.exists():
        return False
    try:
        run_report = json.loads(run_report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return str(run_report.get("status") or "").lower() not in {"", "prepared"}


def quality_failed(paper_dir: Path) -> bool:
    report_path = paper_dir / "quality_report.json"
    return report_path.exists() and not quality_ok(paper_dir)


def run_prepare(
    *,
    paper_id: str,
    references_jsonl: Path,
    cite_contexts_jsonl: Path,
    output_root: Path,
    max_citations: int,
    overwrite: bool,
) -> None:
    cmd = [
        sys.executable,
        str(PREPARE_SCRIPT),
        "--paper-id",
        paper_id,
        "--references-jsonl",
        str(references_jsonl),
        "--cite-contexts-jsonl",
        str(cite_contexts_jsonl),
        "--output-root",
        str(output_root),
        "--max-citations",
        str(max_citations),
    ]
    if overwrite:
        cmd.append("--overwrite")
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True, capture_output=True, text=True)


def run_validate(*, paper_id: str, paper_dir: Path, output_root: Path, update_template: bool = False) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        str(VALIDATE_SCRIPT),
        "--paper-id",
        paper_id,
        "--paper-dir",
        str(paper_dir),
        "--layer4-root",
        str(output_root),
    ]
    if update_template:
        cmd.append("--update-template")
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    report = {}
    report_path = paper_dir / "quality_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
    schema_updates = report.get("schema_updates") if isinstance(report, dict) else []
    update_message = ""
    if isinstance(schema_updates, list) and schema_updates:
        update_message = f"; schema_updates={len(schema_updates)}"
    if completed.returncode == 0:
        return True, "validation passed" + update_message
    message = completed.stdout.strip() or completed.stderr.strip()
    if update_message:
        message = (message + update_message).strip()
    return False, message[-1000:] if message else "validation failed"


def run_apply(*, paper_id: str, paper_dir: Path, output_root: Path) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        str(APPLY_SCRIPT),
        "--paper-id",
        paper_id,
        "--paper-dir",
        str(paper_dir),
        "--layer4-root",
        str(output_root),
    ]
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if completed.returncode == 0:
        return True, "agent judgment merged"
    message = completed.stdout.strip() or completed.stderr.strip()
    return False, message[-1000:] if message else "merge failed"


def quality_issues(paper_dir: Path) -> list[dict[str, Any]]:
    report_path = paper_dir / "quality_report.json"
    if not report_path.exists():
        return []
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    issues = report.get("issues")
    return [issue for issue in issues if isinstance(issue, dict)] if isinstance(issues, list) else []


def has_source_artifact_fetch_issue(paper_dir: Path, message: str = "") -> bool:
    issues = quality_issues(paper_dir)
    for item in issues:
        path = str(item.get("path") or "")
        text = str(item.get("message") or "")
        if path.startswith("paper_record.source_artifacts.") and "artifact fetch should be attempted" in text:
            return True
    return "paper_record.source_artifacts" in message and "artifact fetch should be attempted" in message


def arxiv_id_from_paper_record(paper_dir: Path) -> str:
    try:
        data = read_yaml(paper_dir / "paper_record.yml")
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(data, dict):
        return ""
    paper_record = data.get("paper_record") or {}
    if not isinstance(paper_record, dict):
        return ""
    source_artifacts = paper_record.get("source_artifacts") or {}
    if isinstance(source_artifacts, dict):
        arxiv = source_artifacts.get("arxiv") or {}
        if isinstance(arxiv, dict) and arxiv.get("arxiv_id"):
            return str(arxiv.get("arxiv_id"))
    metadata = paper_record.get("metadata") or {}
    if isinstance(metadata, dict):
        return str(metadata.get("arxiv_id") or "")
    return ""


def run_kimi(
    *,
    paper_id: str,
    paper_dir: Path,
    prompt_path: Path,
    attempt: int,
    timeout: int,
    permission_mode: str,
) -> tuple[bool, str]:
    suffix = attempt_suffix(attempt)
    response_path = paper_dir / f"agent_response{suffix}.md"
    log_path = paper_dir / ("agent.log" if attempt == 1 else f"agent_attempt_{attempt}.log")
    usage_path = paper_dir / f"agent_usage{suffix}.json"
    if not prompt_path.exists():
        return False, f"missing prompt: {prompt_path}"

    prompt_arg = (
        "Read this UTF-8 prompt file and follow its instructions exactly:\n"
        f"{repo_relative(prompt_path)}\n\n"
        "Use the named skill from the prompt. Construct or repair agent_judgment.json, "
        "then run the local scripts described by the skill. Do not manually edit YAML files. "
        "Do not summarize the prompt. "
        "After completing the task, return only a concise status summary."
    )
    cmd = [resolve_kimi_bin()]
    if permission_mode == "yolo":
        cmd.append("--yolo")
    elif permission_mode == "auto":
        cmd.append("--auto")
    cmd.extend(["--output-format", "text", "--prompt", prompt_arg])

    started = time.time()
    captured_output: list[str] = []
    timed_out = False
    returncode: int | str | None = None

    with log_path.open("w", encoding="utf-8") as log:
        log.write(
            "\n".join(
                [
                    f"paper_id: {paper_id}",
                    "status: running",
                    f"attempt: {attempt}",
                    f"prompt_file: {prompt_path}",
                    f"command: {shlex.join(cmd[:3] + ['--prompt', '<prompt omitted from log>'])}",
                    f"cwd: {REPO_ROOT}",
                    f"kimi_bin: {cmd[0]}",
                    "",
                    "## STREAM stdout+stderr",
                    "",
                ]
            )
        )
        log.flush()

        kimi_env = os.environ.copy()
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            kimi_env[key] = KIMI_PROXY
        for key in ("NO_PROXY", "no_proxy"):
            kimi_env[key] = KIMI_NO_PROXY
        process = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
            env=kimi_env,
        )
        assert process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
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
        finally:
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

    response_path.write_text("".join(captured_output), encoding="utf-8")
    wire_summary = collect_kimi_wire_artifacts(
        paper_dir=paper_dir,
        captured_text="".join(captured_output),
        attempt=attempt,
    )
    write_json(usage_path, wire_summary)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n## KIMI SESSION ARTIFACTS\n")
        log.write(json.dumps(wire_summary, ensure_ascii=False, indent=2) + "\n")

    if timed_out:
        return False, f"timeout after {timeout}s"
    if returncode != 0:
        return False, f"kimi exited with {returncode}"
    return True, "kimi completed"


def write_repair_prompt(*, paper_id: str, paper_dir: Path, failure_stage: str, message: str) -> Path:
    prompt_path = paper_dir / "agent_repair_prompt.md"
    quality_report = paper_dir / "quality_report.json"
    merge_report = paper_dir / "agent_merge_report.json"
    content = f"""# MinerU Layer 4 Resource Judgment Repair

You are repairing a previous Kimi extraction for one MinerU/PDF paper.
Do not launch other agents. Complete this repair yourself.

Repository root: {REPO_ROOT}
Paper id: {paper_id}
Output directory: {repo_relative(paper_dir)}

Skill instructions:
- Use skill name: paper-mineru-resource-extract
- Before repairing, read and follow this skill file:
  skill/paper-mineru-resource-extract/SKILL.md
- This skill is for you, the Kimi agent.

Important boundary:
- You may edit only: {repo_relative(paper_dir / "agent_judgment.json")}
- Do not write, edit, or overwrite any .yml/.yaml file.
- Local scripts will regenerate YAML from agent_judgment.json after you finish.

Failure stage:
{failure_stage}

Failure message:
```text
{message}
```

Relevant files to inspect:
- Original prompt: {repo_relative(paper_dir / "agent_prompt.md")}
- Current judgment JSON: {repo_relative(paper_dir / "agent_judgment.json")}
- Merge report, if present: {repo_relative(merge_report)}
- Quality report, if present: {repo_relative(quality_report)}
- Input bundle: {repo_relative(paper_dir / "input_bundle.json")}

Repair task:
1. Read the skill and current agent_judgment.json.
2. Fix agent_judgment.json so that local merge and validation can pass.
3. Preserve useful resource extraction work from the previous judgment.
4. Run the local apply script documented by the skill.
5. Return a concise status summary.
"""
    prompt_path.write_text(content, encoding="utf-8")
    return prompt_path


def write_source_artifact_repair_prompt(*, paper_id: str, paper_dir: Path, message: str) -> Path:
    prompt_path = paper_dir / "agent_repair_prompt.md"
    quality_report = paper_dir / "quality_report.json"
    arxiv_id = arxiv_id_from_paper_record(paper_dir) or "<arxiv_id>"
    output_dir = repo_relative(paper_dir)
    html_path = f"{output_dir}/arxiv/html/{arxiv_id}.html"
    source_path = f"{output_dir}/arxiv/src/{arxiv_id}.tar.gz"
    content = f"""# Focused arXiv Artifact Download Repair

You are repairing a completed MinerU Layer 4 extraction for one paper.
Do not redo paper/resource extraction. Do not launch other agents.

Repository root: {REPO_ROOT}
Paper id: {paper_id}
Output directory: {output_dir}

Skill instructions:
- Use skill name: paper-mineru-resource-extract.
- Read only the arXiv Metadata and Source Artifacts section in:
  skill/paper-mineru-resource-extract/SKILL.md

Important boundary:
- Preserve all existing resource, citation, claim, experiment, and repository-verification content.
- You may edit only the `paper_record.source_artifacts` portion of:
  {repo_relative(paper_dir / "agent_judgment.json")}
- Do not write, edit, or overwrite any .yml/.yaml file by hand.
- Local scripts will regenerate YAML from agent_judgment.json after you finish.

Validation failure:
```text
{message}
```

Relevant files:
- Current judgment JSON: {repo_relative(paper_dir / "agent_judgment.json")}
- Current paper YAML: {repo_relative(paper_dir / "paper_record.yml")}
- Quality report: {repo_relative(quality_report)}
- Input bundle: {repo_relative(paper_dir / "input_bundle.json")}

Repair task:
1. Read the current `paper_record.source_artifacts` from paper_record.yml or agent_judgment.json.
2. If arXiv metadata is available, attempt every HTML/source artifact whose status is `unfetched`.
3. Use real shell downloads. Do not manually create downloaded artifact files.

HTML command pattern:
```bash
mkdir -p {output_dir}/arxiv/html
curl -x http://127.0.0.1:7899 \\
  -L --fail --retry 2 --connect-timeout 20 --max-time 60 \\
  -A "Mozilla/5.0 (compatible; p4a-layer4/1.0)" \\
  -D {output_dir}/arxiv/html/{arxiv_id}.headers.txt \\
  -o {html_path} \\
  https://arxiv.org/html/{arxiv_id}
test -s {html_path}
```

TeX source command pattern:
```bash
mkdir -p {output_dir}/arxiv/src
curl -x http://127.0.0.1:7899 \\
  -L --fail --retry 2 --connect-timeout 20 --max-time 60 \\
  -A "Mozilla/5.0 (compatible; p4a-layer4/1.0)" \\
  -D {output_dir}/arxiv/src/{arxiv_id}.headers.txt \\
  -o {source_path} \\
  https://arxiv.org/src/{arxiv_id}
test -s {source_path}
file {source_path}
tar -tzf {source_path} | head
```

Always pass `-x http://127.0.0.1:7899` when downloading from arxiv.org or huggingface.co; direct connections from this host are throttled or blocked. Never use the proxy for local services.

After each artifact attempt, update only `paper_record.source_artifacts` in agent_judgment.json:
- success: `exists: true`, `status: available`, repository-relative `path`, attempted `url`, `checked_by: bash-curl`, concise notes with file size or verification command.
- failure: `exists: false`, `status: failed` or `missing`, attempted `url`, `checked_by: bash-curl`, notes containing the actual command failure.

Do not leave an artifact as `unfetched` after a confident arXiv match.

Then run:
```bash
.venv/bin/python src/extract/layer4/apply_agent_judgment.py --paper-id {paper_id}
.venv/bin/python src/extract/layer4/validate_layer4_outputs.py --paper-id {paper_id}
```

Return only a concise status summary.
"""
    prompt_path.write_text(content, encoding="utf-8")
    return prompt_path


def run_source_artifact_repair(args: argparse.Namespace, paper_id: str, paper_dir: Path, message: str) -> dict[str, Any]:
    prompt_path = write_source_artifact_repair_prompt(paper_id=paper_id, paper_dir=paper_dir, message=message)
    ok, kimi_message = run_kimi(
        paper_id=paper_id,
        paper_dir=paper_dir,
        prompt_path=prompt_path,
        attempt=2,
        timeout=args.timeout,
        permission_mode=args.permission_mode,
    )
    if not ok:
        return {"paper_id": paper_id, "status": "artifact_repair_failed", "attempts": 1, "message": kimi_message}

    ok, apply_message = run_apply(paper_id=paper_id, paper_dir=paper_dir, output_root=args.output_root)
    if not ok:
        return {"paper_id": paper_id, "status": "artifact_repair_failed", "attempts": 1, "message": apply_message}

    ok, validate_message = run_validate(paper_id=paper_id, paper_dir=paper_dir, output_root=args.output_root)
    if ok:
        return {"paper_id": paper_id, "status": "artifact_repaired", "attempts": 1, "message": validate_message}
    return {"paper_id": paper_id, "status": "artifact_repair_failed", "attempts": 1, "message": validate_message}


def run_one_paper(args: argparse.Namespace, paper_id: str) -> dict[str, Any]:
    paper_dir = args.output_root / paper_id
    if args.skip_existing and quality_ok(paper_dir):
        ok, message = run_validate(paper_id=paper_id, paper_dir=paper_dir, output_root=args.output_root, update_template=True)
        if ok:
            return {"paper_id": paper_id, "status": "skipped_existing_validated", "attempts": 0, "message": message}
        if not args.prepare_only and not args.no_validate and has_source_artifact_fetch_issue(paper_dir, message):
            result = run_source_artifact_repair(args, paper_id, paper_dir, message)
            result["status"] = f"skipped_existing_{result['status']}"
            return result
        status = "skipped_existing_validation_failed"
        return {"paper_id": paper_id, "status": status, "attempts": 0, "message": message}

    if (
        args.skip_existing
        and not args.prepare_only
        and not args.no_validate
        and (paper_dir / "agent_judgment.json").exists()
        and has_source_artifact_fetch_issue(paper_dir)
    ):
        result = run_source_artifact_repair(args, paper_id, paper_dir, "previous validation found unfetched arXiv artifacts")
        result["status"] = f"skipped_existing_{result['status']}"
        return result

    attempts = 0
    last_message = ""
    for attempt in range(args.max_retries + 1):
        attempts = attempt + 1
        if attempt == 0:
            try:
                run_prepare(
                    paper_id=paper_id,
                    references_jsonl=args.references_jsonl,
                    cite_contexts_jsonl=args.cite_contexts_jsonl,
                    output_root=args.output_root,
                    max_citations=args.max_citations,
                    overwrite=args.overwrite_prepare
                    or (quality_failed(paper_dir) and not has_source_artifact_fetch_issue(paper_dir))
                    or not (paper_dir / "agent_prompt.md").exists(),
                )
            except subprocess.CalledProcessError as exc:
                message = (exc.stderr or exc.stdout or str(exc)).strip()
                return {"paper_id": paper_id, "status": "failed", "attempts": attempts, "message": f"prepare failed: {message[-1000:]}"}

        if not args.prepare_only:
            prompt_path = paper_dir / ("agent_prompt.md" if attempt == 0 else "agent_repair_prompt.md")
            ok, message = run_kimi(
                paper_id=paper_id,
                paper_dir=paper_dir,
                prompt_path=prompt_path,
                attempt=attempts,
                timeout=args.timeout,
                permission_mode=args.permission_mode,
            )
            last_message = message
            if not ok:
                if attempt < args.max_retries:
                    write_repair_prompt(paper_id=paper_id, paper_dir=paper_dir, failure_stage="kimi", message=message)
                continue

            ok, message = run_apply(paper_id=paper_id, paper_dir=paper_dir, output_root=args.output_root)
            last_message = message
            if not ok:
                if attempt < args.max_retries:
                    write_repair_prompt(paper_id=paper_id, paper_dir=paper_dir, failure_stage="apply_agent_judgment", message=message)
                continue

        if args.no_validate:
            return {"paper_id": paper_id, "status": "completed", "attempts": attempts, "message": last_message or "prepared"}

        ok, message = run_validate(paper_id=paper_id, paper_dir=paper_dir, output_root=args.output_root)
        last_message = message
        if ok:
            return {"paper_id": paper_id, "status": "completed", "attempts": attempts, "message": message}
        if attempt < args.max_retries:
            if has_source_artifact_fetch_issue(paper_dir, message):
                write_source_artifact_repair_prompt(paper_id=paper_id, paper_dir=paper_dir, message=message)
            else:
                write_repair_prompt(paper_id=paper_id, paper_dir=paper_dir, failure_stage="validate_layer4_outputs", message=message)

    return {"paper_id": paper_id, "status": "failed", "attempts": attempts, "message": last_message}


def build_batch_summary(
    *,
    paper_ids: list[str],
    results: list[dict[str, Any]],
    started_at: str,
    status: str,
    in_progress_ids: list[str] | None = None,
) -> dict[str, Any]:
    in_progress_ids = in_progress_ids or []
    completed_ids = {str(row.get("paper_id")) for row in results}
    pending_ids = [paper_id for paper_id in paper_ids if paper_id not in completed_ids]
    status_counts = {
        item_status: sum(1 for row in results if row.get("status") == item_status)
        for item_status in sorted({str(row.get("status")) for row in results})
    }
    return {
        "status": status,
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "paper_count": len(paper_ids),
        "completed_so_far": len(results),
        "in_progress_count": len(in_progress_ids),
        "in_progress_ids": in_progress_ids,
        "pending_count": len(pending_ids),
        "completed_count": sum(1 for row in results if row.get("status") == "completed"),
        "skipped_existing_count": sum(1 for row in results if str(row.get("status") or "").startswith("skipped_existing")),
        "skipped_existing_validated_count": sum(1 for row in results if row.get("status") == "skipped_existing_validated"),
        "skipped_existing_validation_failed_count": sum(1 for row in results if row.get("status") == "skipped_existing_validation_failed"),
        "artifact_repaired_count": sum(1 for row in results if "artifact_repaired" in str(row.get("status") or "")),
        "artifact_repair_failed_count": sum(1 for row in results if "artifact_repair_failed" in str(row.get("status") or "")),
        "failed_count": sum(1 for row in results if row.get("status") == "failed"),
        "status_counts": status_counts,
        "pending_ids": pending_ids,
        "results": sorted(results, key=lambda row: str(row.get("paper_id"))),
    }


def write_batch_reports(output_root: Path, summary: dict[str, Any]) -> None:
    write_json(output_root / "batch_report.json", summary)
    failures = [row for row in summary["results"] if row.get("status") == "failed"]
    write_json(output_root / "batch_failures.json", failures)


def launch(args: argparse.Namespace) -> list[dict[str, Any]]:
    paper_ids = selected_paper_ids(
        args.references_jsonl,
        args.paper_id,
        args.paper_id_file,
        args.limit,
        args.skip_front_matter,
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []
    write_batch_reports(
        args.output_root,
        build_batch_summary(paper_ids=paper_ids, results=results, started_at=started_at, status="running"),
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        next_index = 0
        future_to_id: dict[concurrent.futures.Future[dict[str, Any]], str] = {}

        def submit_next() -> None:
            nonlocal next_index
            if next_index >= len(paper_ids):
                return
            paper_id = paper_ids[next_index]
            next_index += 1
            print(f"[start {next_index}/{len(paper_ids)}] {paper_id}", flush=True)
            future_to_id[executor.submit(run_one_paper, args, paper_id)] = paper_id

        for _ in range(min(args.concurrency, len(paper_ids))):
            submit_next()
        write_batch_reports(
            args.output_root,
            build_batch_summary(
                paper_ids=paper_ids,
                results=results,
                started_at=started_at,
                status="running",
                in_progress_ids=list(future_to_id.values()),
            ),
        )

        while future_to_id:
            done, _pending = concurrent.futures.wait(
                future_to_id,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                paper_id = future_to_id.pop(future)
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    result = {"paper_id": paper_id, "status": "failed", "attempts": 0, "message": str(exc)}
                results.append(result)
                print(
                    f"[{len(results)}/{len(paper_ids)}] {result['paper_id']} "
                    f"{result['status']} attempts={result.get('attempts')} {result.get('message', '')}",
                    flush=True,
                )
                submit_next()
                write_batch_reports(
                    args.output_root,
                    build_batch_summary(
                        paper_ids=paper_ids,
                        results=results,
                        started_at=started_at,
                        status="running",
                        in_progress_ids=list(future_to_id.values()),
                    ),
                )

    results.sort(key=lambda row: row["paper_id"])
    write_batch_reports(
        args.output_root,
        build_batch_summary(paper_ids=paper_ids, results=results, started_at=started_at, status="finished"),
    )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch Kimi agents for MinerU Layer 4 resource extraction.")
    parser.add_argument("--references-jsonl", type=Path, default=DEFAULT_REFERENCES_JSONL)
    parser.add_argument(
        "--cite-contexts-jsonl",
        type=Path,
        default=DEFAULT_CITE_CONTEXTS_JSONL,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_LAYER4_ROOT)
    parser.add_argument("--paper-id", action="append", help="Limit to one paper id; repeatable.")
    parser.add_argument(
        "--paper-id-file",
        type=Path,
        action="append",
        help="Read paper ids from a newline-delimited file; repeatable. Blank lines and # comments are ignored.",
    )
    parser.add_argument("--limit", type=int, help="Process only the first N selected papers.")
    parser.add_argument("--skip-front-matter", action="store_true", default=True)
    parser.add_argument("--include-front-matter", dest="skip_front_matter", action="store_false")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--max-retries", type=int, default=2, help="Repair attempts after the first Kimi extraction.")
    parser.add_argument("--max-citations", type=int, default=200)
    parser.add_argument("--permission-mode", choices=("none", "auto", "yolo"), default="none")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    parser.add_argument("--overwrite-prepare", action="store_true", help="Regenerate templates even if present.")
    parser.add_argument("--prepare-only", action="store_true", help="Only prepare prompts/templates; do not launch Kimi.")
    parser.add_argument("--no-validate", action="store_true", help="Skip validate_layer4_outputs.py after Kimi.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    results = launch(args)
    failures = [row for row in results if row["status"] == "failed"]
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    # Keeps static checkers from treating prepare_mineru_layer4 as unused while still
    # failing early if the local import environment is broken.
    _ = _prepare_main
    main()
