"""Freeze external-tool results from selected historical P4A sessions.

The historical sessions remain read-only. This script copies only external tool
calls and their paired results into data/processed/e06/evidence/, where a later
fixture materializer can place them under each case's input/evidence/ directory.

Usage:
    python3 experiments/e06-static-prefix/src/extract_external_evidence.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT = "e06/extract_external_evidence.py"
REPO_ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_TOOL_NAMES = frozenset({"WebSearch", "FetchURL"})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON {path}: {error}") from error


def load_manifest_workdirs(path: Path) -> dict[str, str]:
    workdirs: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if line_number == 1 and "_provenance" in row:
                    continue
                sid, workdir = row.get("sid"), row.get("wd")
                if isinstance(sid, str) and isinstance(workdir, str):
                    workdirs[sid] = workdir
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read session manifest {path}: {error}") from error
    return workdirs


def is_external_tool(name: object) -> bool:
    return isinstance(name, str) and (name.startswith("mcp__") or name in EXTERNAL_TOOL_NAMES)


def extract(wire_path: Path) -> list[dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, Any]] = []
    with wire_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            record = json.loads(line)
            if record.get("type") != "context.append_loop_event":
                continue
            event = record.get("event")
            if not isinstance(event, dict):
                continue
            if event.get("type") == "tool.call":
                tool_call_id = event.get("toolCallId")
                if isinstance(tool_call_id, str) and is_external_tool(event.get("name")):
                    calls[tool_call_id] = event
                continue
            if event.get("type") != "tool.result":
                continue
            tool_call_id = event.get("toolCallId")
            if not isinstance(tool_call_id, str):
                continue
            call = calls.pop(tool_call_id, None)
            if call is None:
                continue
            result = event.get("result")
            if not isinstance(result, dict):
                result = {"raw": result}
            evidence.append(
                {
                    "source_line": line_number,
                    "step": call.get("step"),
                    "tool_call_id": tool_call_id,
                    "tool": call["name"],
                    "arguments": call.get("args", {}),
                    "result": result,
                }
            )
    if calls:
        missing = ", ".join(sorted(calls))
        raise ValueError(f"unpaired external tool calls in {wire_path}: {missing}")
    return evidence


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=REPO_ROOT / "experiments/e06-static-prefix/cases.json",
    )
    parser.add_argument(
        "--session-manifest",
        type=Path,
        default=REPO_ROOT / "data/processed/e01/s0_manifest.jsonl",
    )
    parser.add_argument(
        "--sessions-root",
        type=Path,
        default=REPO_ROOT / "data/raw/kimi-p4a-sessions/.kimi-code/sessions",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "data/processed/e06/evidence",
    )
    args = parser.parse_args()

    cases_path = args.cases.resolve()
    session_manifest_path = args.session_manifest.resolve()
    sessions_root = args.sessions_root.resolve()
    output_root = args.output_root.resolve()
    cases_config = load_json(cases_path)
    if not isinstance(cases_config, dict) or cases_config.get("schema_version") != 1:
        raise ValueError(f"unsupported cases config: {cases_path}")
    cases = cases_config.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("E06 requires exactly 24 configured cases")
    workdirs = load_manifest_workdirs(session_manifest_path)

    summaries = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case entry is not an object")
        case_id, paper_id, session_id = (case.get(key) for key in ("case_id", "paper_id", "session_id"))
        if not all(isinstance(value, str) for value in (case_id, paper_id, session_id)):
            raise ValueError(f"missing case identity: {case}")
        workdir = workdirs.get(session_id)
        if workdir is None:
            raise ValueError(f"session absent from E01 manifest: {session_id}")
        wire_path = sessions_root / workdir / session_id / "agents/main/wire.jsonl"
        if not wire_path.is_file():
            raise ValueError(f"wire missing: {wire_path}")

        events = extract(wire_path)
        by_tool = Counter(event["tool"] for event in events)
        failed = sum(bool(event["result"].get("isError")) for event in events)
        payload = {
            "_provenance": {
                "script": SCRIPT,
                "generated_at": datetime.now(UTC).isoformat(),
                "source_wire": {"path": relative(wire_path), "sha256": sha256(wire_path)},
            },
            "schema_version": 1,
            "case_id": case_id,
            "paper_id": paper_id,
            "session_id": session_id,
            "events": events,
        }
        output_path = output_root / f"{case_id}.json"
        atomic_write_json(output_path, payload)
        summaries.append(
            {
                "case_id": case_id,
                "paper_id": paper_id,
                "session_id": session_id,
                "path": relative(output_path),
                "event_count": len(events),
                "failed_event_count": failed,
                "by_tool": dict(sorted(by_tool.items())),
            }
        )

    summary = {
        "_provenance": {
            "script": SCRIPT,
            "generated_at": datetime.now(UTC).isoformat(),
            "cases": {"path": relative(cases_path), "sha256": sha256(cases_path)},
            "session_manifest": {
                "path": relative(session_manifest_path),
                "sha256": sha256(session_manifest_path),
            },
        },
        "schema_version": 1,
        "n_cases": len(summaries),
        "n_cases_with_evidence": sum(summary["event_count"] > 0 for summary in summaries),
        "n_events": sum(summary["event_count"] for summary in summaries),
        "n_failed_events": sum(summary["failed_event_count"] for summary in summaries),
        "cases": summaries,
    }
    atomic_write_json(output_root / "summary.json", summary)
    print(
        f"[e06] wrote {len(summaries)} evidence files: "
        f"{summary['n_events']} events, {summary['n_failed_events']} failed events"
    )


if __name__ == "__main__":
    main()
