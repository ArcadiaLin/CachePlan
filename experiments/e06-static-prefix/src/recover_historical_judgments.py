"""Recover selected historical P4A agent judgments without modifying raw sessions.

The recovered files are comparison baselines, not agent input and not unexamined gold
labels.  The replayer applies successful Write and Edit calls targeting
agent_judgment.json in wire order.  A pre-existing judgment may be recovered from a
successful Read only when no Write has occurred.

Usage:
    python3 experiments/e06-static-prefix/src/recover_historical_judgments.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT = "e06/recover_historical_judgments.py"
REPO_ROOT = Path(__file__).resolve().parents[3]
NUMBERED_READ_LINE = re.compile(r"^\d+\t(.*)$")
EXPECTED_TOP_LEVEL = frozenset(
    {"paper_id", "paper_record", "resources", "verification_checks", "warnings"}
)


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


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def load_manifest_workdirs(path: Path) -> dict[str, str]:
    workdirs: dict[str, str] = {}
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
    return workdirs


def target_path(args: object) -> bool:
    return isinstance(args, dict) and Path(str(args.get("path", ""))).name == "agent_judgment.json"


def parse_numbered_read(output: object) -> str | None:
    if not isinstance(output, str):
        return None
    lines: list[str] = []
    for line in output.splitlines():
        if line.startswith("<system>"):
            continue
        match = NUMBERED_READ_LINE.fullmatch(line)
        if match is None:
            return None
        lines.append(match.group(1))
    return "\n".join(lines) + "\n" if lines else None


def failed(result: object) -> bool:
    return isinstance(result, dict) and bool(result.get("isError"))


def replay(wire_path: Path) -> tuple[str | None, list[dict[str, Any]], list[str]]:
    pending: dict[str, tuple[int, dict[str, Any]]] = {}
    operations: list[dict[str, Any]] = []
    issues: list[str] = []
    content: str | None = None
    source = ""

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
                if isinstance(tool_call_id, str) and event.get("name") in {"Write", "Edit", "Read"} and target_path(event.get("args")):
                    pending[tool_call_id] = (line_number, event)
                continue
            if event.get("type") != "tool.result":
                continue
            tool_call_id = event.get("toolCallId")
            if not isinstance(tool_call_id, str):
                continue
            call_data = pending.pop(tool_call_id, None)
            if call_data is None:
                continue
            call_line, call = call_data
            name = str(call["name"])
            args = call.get("args", {})
            result = event.get("result")
            operation = {"tool": name, "call_line": call_line, "step": call.get("step")}
            if failed(result):
                operation["status"] = "failed"
                operations.append(operation)
                continue
            if name == "Write":
                value = args.get("content") if isinstance(args, dict) else None
                if not isinstance(value, str):
                    issues.append(f"Write at line {call_line} lacks string content")
                    operation["status"] = "invalid"
                else:
                    content, source = value, "write_replay"
                    operation["status"] = "applied"
                operations.append(operation)
                continue
            if name == "Edit":
                if content is None:
                    issues.append(f"Edit at line {call_line} has no preceding target content")
                    operation["status"] = "missing_base"
                else:
                    old = args.get("old_string") if isinstance(args, dict) else None
                    new = args.get("new_string") if isinstance(args, dict) else None
                    replace_all = bool(args.get("replace_all", False)) if isinstance(args, dict) else False
                    occurrences = content.count(old) if isinstance(old, str) else 0
                    if not isinstance(old, str) or not isinstance(new, str) or occurrences == 0:
                        issues.append(f"Edit at line {call_line} cannot be applied")
                        operation["status"] = "unapplied"
                    elif not replace_all and occurrences != 1:
                        issues.append(f"Edit at line {call_line} matches {occurrences} locations")
                        operation["status"] = "ambiguous"
                    else:
                        content = content.replace(old, new) if replace_all else content.replace(old, new, 1)
                        operation["status"] = "applied"
                        operation["replace_all"] = replace_all
                operations.append(operation)
                continue
            if content is None:
                read_content = parse_numbered_read(result.get("output") if isinstance(result, dict) else None)
                if read_content is None:
                    issues.append(f"Read at line {call_line} is not a complete numbered file")
                    operation["status"] = "unusable"
                else:
                    content, source = read_content, "preexisting_read"
                    operation["status"] = "adopted"
            else:
                operation["status"] = "observed"
            operations.append(operation)

    if pending:
        issues.append(f"unpaired target calls: {', '.join(sorted(pending))}")
    return content, operations, issues + ([] if source else ["no recoverable target content"])


def contract_errors(value: object, paper_id: str, contract: dict[str, Any]) -> list[str]:
    if not isinstance(value, dict):
        return ["output is not an object"]
    errors: list[str] = []
    if set(value) != EXPECTED_TOP_LEVEL:
        errors.append(f"top-level keys are {sorted(value)}")
    if value.get("paper_id") != paper_id:
        errors.append(f"paper_id is {value.get('paper_id')!r}")
    paper_record = value.get("paper_record")
    if not isinstance(paper_record, dict):
        return errors + ["paper_record is not an object"]
    enums = contract["enums"]
    intent = paper_record.get("intent")
    if not isinstance(intent, dict) or intent.get("paper_type") not in enums["paper_type"]:
        errors.append("invalid paper_type")
    citations = paper_record.get("citation_functions")
    if not isinstance(citations, list) or any(
        not isinstance(item, dict) or item.get("citation_function") not in enums["citation_function"]
        for item in citations
    ):
        errors.append("invalid citation_functions")
    resources = value.get("resources")
    if not isinstance(resources, list):
        return errors + ["resources is not a list"]
    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            errors.append(f"resource {index} is not an object")
            continue
        access = resource.get("access")
        availability = resource.get("availability")
        callable_info = resource.get("agent_callable")
        if resource.get("kind") not in enums["resource_kind"]:
            errors.append(f"resource {index} has invalid kind")
        if resource.get("relation_type") not in enums["relation_type"]:
            errors.append(f"resource {index} has invalid relation_type")
        if not isinstance(access, dict) or access.get("access_type") not in enums["access_type"]:
            errors.append(f"resource {index} has invalid access_type")
        if not isinstance(availability, dict) or availability.get("status") not in enums["availability_status"]:
            errors.append(f"resource {index} has invalid availability")
        if not isinstance(callable_info, dict) or callable_info.get("estimated_wrapping_difficulty") not in enums["wrapping_difficulty"]:
            errors.append(f"resource {index} has invalid wrapping difficulty")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "experiments/e06-static-prefix/cases.json")
    parser.add_argument("--session-manifest", type=Path, default=REPO_ROOT / "data/processed/e01/s0_manifest.jsonl")
    parser.add_argument("--sessions-root", type=Path, default=REPO_ROOT / "data/raw/kimi-p4a-sessions/.kimi-code/sessions")
    parser.add_argument("--contract", type=Path, default=REPO_ROOT / "experiments/e06-static-prefix/contracts/agent_judgment.json")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "data/processed/e06/expected")
    parser.add_argument("--overwrite", action="store_true", help="replace the generated output root only")
    args = parser.parse_args()

    cases_path = args.cases.resolve()
    session_manifest_path = args.session_manifest.resolve()
    sessions_root = args.sessions_root.resolve()
    contract_path = args.contract.resolve()
    output_root = args.output_root.resolve()
    cases_config = load_json(cases_path)
    contract = load_json(contract_path)
    cases = cases_config.get("cases") if isinstance(cases_config, dict) else None
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("E06 requires exactly 24 configured cases")
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ValueError("unsupported judgment contract")
    if output_root.exists():
        if not args.overwrite:
            raise ValueError(f"refusing to overwrite existing expected root: {output_root}")
        shutil.rmtree(output_root)
    workdirs = load_manifest_workdirs(session_manifest_path)

    summaries = []
    for case in cases:
        case_id, paper_id, session_id = (case.get(key) for key in ("case_id", "paper_id", "session_id"))
        if not all(isinstance(value, str) for value in (case_id, paper_id, session_id)):
            raise ValueError(f"missing case identity: {case}")
        workdir = workdirs.get(session_id)
        if workdir is None:
            raise ValueError(f"session absent from E01 manifest: {session_id}")
        wire_path = sessions_root / workdir / session_id / "agents/main/wire.jsonl"
        content, operations, recovery_issues = replay(wire_path)
        judgment: object | None = None
        if content is not None:
            try:
                judgment = json.loads(content)
            except json.JSONDecodeError as error:
                recovery_issues.append(f"final JSON invalid: {error.msg}")
        validation_errors = contract_errors(judgment, paper_id, contract) if judgment is not None else []
        usable = judgment is not None and not recovery_issues and not validation_errors
        expected_path = output_root / f"{case_id}.json"
        if usable:
            atomic_write_json(expected_path, judgment)
        summaries.append(
            {
                "case_id": case_id,
                "paper_id": paper_id,
                "session_id": session_id,
                "source_wire": {"path": relative(wire_path), "sha256": sha256(wire_path)},
                "recovery": "usable" if usable else "unusable",
                "recovery_source": next((op["status"] for op in operations if op["tool"] == "Read" and op["status"] == "adopted"), "write_replay"),
                "operations": operations,
                "recovery_issues": recovery_issues,
                "contract_errors": validation_errors,
                "expected_path": relative(expected_path) if usable else "",
            }
        )
    summary = {
        "_provenance": {
            "script": SCRIPT,
            "generated_at": datetime.now(UTC).isoformat(),
            "cases": {"path": relative(cases_path), "sha256": sha256(cases_path)},
            "session_manifest": {"path": relative(session_manifest_path), "sha256": sha256(session_manifest_path)},
            "contract": {"path": relative(contract_path), "sha256": sha256(contract_path)},
        },
        "schema_version": 1,
        "n_cases": len(summaries),
        "n_usable": sum(item["recovery"] == "usable" for item in summaries),
        "cases": summaries,
    }
    atomic_write_json(output_root / "summary.json", summary)
    print(f"[e06] recovered {summary['n_usable']}/{len(summaries)} usable historical judgments at {output_root}")


if __name__ == "__main__":
    main()
