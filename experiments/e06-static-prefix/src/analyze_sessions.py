"""Summarize persisted WIDI session JSONL files for cache experiments.

Usage:
    python3 experiments/e06-static-prefix/src/analyze_sessions.py <session.jsonl-or-directory> [...]

The reported prompt-cache reuse ratio is token-weighted:
    cached_prompt_tokens / prompt_tokens
where ``prompt_tokens`` is the sum of WIDI's ``input``, ``cacheRead``, and
``cacheWrite`` fields. ``cacheWrite`` remains provider-reported telemetry; it
is not interpreted as a vLLM KV-cache write count.

All token totals cover every persisted message branch. This reflects work the
model actually performed, including branches later rewound; it is not an
active-leaf-only reconstruction.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT = "e06/analyze_sessions.py"
REPO_ROOT = Path(__file__).resolve().parents[3]
METRIC_SCHEMA_VERSION = 1
USAGE_KEYS = ("input", "output", "cacheRead", "cacheWrite", "reasoning", "totalTokens")


def relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def require_record(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} is not an ISO-8601 timestamp: {value!r}") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone: {value!r}")
    return parsed.astimezone(UTC)


def isoformat(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds(), 3)


def token_value(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"usage.{key} must be a non-negative integer")
    return value


def empty_metrics() -> dict[str, Any]:
    return {
        "model_responses": 0,
        "prompt_tokens": 0,
        "uncached_prompt_tokens": 0,
        "cached_prompt_tokens": 0,
        "provider_reported_cache_write_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "usage_total_mismatch_count": 0,
        "tool_calls": 0,
        "tool_errors": 0,
        "providers": Counter(),
        "models": Counter(),
    }


def add_message_metrics(metrics: dict[str, Any], entry: dict[str, Any]) -> None:
    message = entry.get("message")
    if not isinstance(message, dict):
        return

    content = message.get("content")
    if isinstance(content, list):
        metrics["tool_calls"] += sum(
            isinstance(block, dict) and block.get("type") == "toolCall" for block in content
        )

    if message.get("role") == "toolResult" and message.get("isError") is True:
        metrics["tool_errors"] += 1

    if message.get("role") != "assistant" or not isinstance(message.get("usage"), dict):
        return

    usage = message["usage"]
    values = {key: token_value(usage, key) for key in USAGE_KEYS}
    prompt_tokens = values["input"] + values["cacheRead"] + values["cacheWrite"]
    metrics["model_responses"] += 1
    metrics["prompt_tokens"] += prompt_tokens
    metrics["uncached_prompt_tokens"] += values["input"]
    metrics["cached_prompt_tokens"] += values["cacheRead"]
    metrics["provider_reported_cache_write_tokens"] += values["cacheWrite"]
    metrics["output_tokens"] += values["output"]
    metrics["reasoning_tokens"] += values["reasoning"]
    metrics["total_tokens"] += values["totalTokens"]
    if values["totalTokens"] != prompt_tokens + values["output"]:
        metrics["usage_total_mismatch_count"] += 1

    provider = message.get("provider")
    if isinstance(provider, str) and provider:
        metrics["providers"][provider] += 1
    model = message.get("model")
    if isinstance(model, str) and model:
        metrics["models"][model] += 1


def finalize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    prompt_tokens = metrics["prompt_tokens"]
    return {
        key: value
        for key, value in metrics.items()
        if key not in {"providers", "models"}
    } | {
        "prompt_cache_reuse_ratio": (
            None if prompt_tokens == 0 else round(metrics["cached_prompt_tokens"] / prompt_tokens, 8)
        ),
        "providers": dict(sorted(metrics["providers"].items())),
        "models": dict(sorted(metrics["models"].items())),
    }


def load_entries(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"cannot read session file {path}: {error}") from error
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = require_record(json.loads(line), f"{path}:{line_number}")
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON at {path}:{line_number}: {error}") from error
        entries.append(entry)

    if not entries:
        raise ValueError(f"session file is empty: {path}")
    header = entries[0]
    if header.get("type") != "session":
        raise ValueError(f"first entry is not a WIDI session header: {path}")
    return header, entries[1:]


def entry_timestamp(entry: dict[str, Any], label: str) -> datetime | None:
    value = entry.get("timestamp")
    return None if value is None else parse_timestamp(value, label)


def is_orchestrator_dispatch(entry: dict[str, Any]) -> bool:
    message = entry.get("message")
    return (
        entry.get("type") == "message"
        and isinstance(message, dict)
        and message.get("role") == "custom"
        and message.get("customType") == "core:orchestrator_message"
    )


def dispatch_source(entry: dict[str, Any]) -> str | None:
    message = require_record(entry["message"], "orchestrator dispatch message")
    details = message.get("details")
    if not isinstance(details, dict):
        return None
    source = details.get("source")
    if not isinstance(source, dict):
        return None
    kind = source.get("kind")
    return kind if isinstance(kind, str) else None


def analyze_dispatches(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    starts = [index for index, entry in enumerate(entries) if is_orchestrator_dispatch(entry)]
    dispatches: list[dict[str, Any]] = []
    for ordinal, start in enumerate(starts, 1):
        end = starts[ordinal] if ordinal < len(starts) else len(entries)
        segment = entries[start:end]
        start_time = entry_timestamp(segment[0], f"dispatch {ordinal} start")
        timestamps = [
            timestamp
            for index, entry in enumerate(segment)
            if (timestamp := entry_timestamp(entry, f"dispatch {ordinal} entry {index}")) is not None
        ]
        metrics = empty_metrics()
        for entry in segment:
            add_message_metrics(metrics, entry)
        dispatches.append(
            {
                "ordinal": ordinal,
                "source": dispatch_source(segment[0]),
                "started_at": isoformat(start_time),
                "ended_at": isoformat(max(timestamps) if timestamps else None),
                "wall_clock_seconds": seconds_between(start_time, max(timestamps) if timestamps else None),
                "metrics": finalize_metrics(metrics),
            }
        )
    return dispatches


def analyze_session(path: Path) -> dict[str, Any]:
    header, entries = load_entries(path)
    session_start = parse_timestamp(header.get("timestamp"), f"{path} session header")
    timestamps = [
        timestamp
        for index, entry in enumerate(entries, 1)
        if (timestamp := entry_timestamp(entry, f"{path} entry {index}")) is not None
    ]
    model_timestamps: list[datetime] = []
    metrics = empty_metrics()
    entry_types: Counter[str] = Counter()
    for entry in entries:
        entry_type = entry.get("type")
        if isinstance(entry_type, str):
            entry_types[entry_type] += 1
        message = entry.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant" and isinstance(message.get("usage"), dict):
            timestamp = entry_timestamp(entry, f"{path} model response")
            if timestamp is not None:
                model_timestamps.append(timestamp)
        add_message_metrics(metrics, entry)

    session_end = max(timestamps, default=session_start)
    session_id = header.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError(f"{path} session header requires a non-empty id")

    return {
        "source": {"path": relative(path)},
        "session": {
            "id": session_id,
            "version": header.get("version"),
            "cwd": header.get("cwd"),
            "started_at": isoformat(session_start),
            "ended_at": isoformat(session_end),
            "wall_clock_seconds": seconds_between(session_start, session_end),
            "model_first_response_at": isoformat(min(model_timestamps, default=None)),
            "model_last_response_at": isoformat(max(model_timestamps, default=None)),
            "model_response_span_seconds": seconds_between(
                min(model_timestamps, default=None), max(model_timestamps, default=None)
            ),
            "entry_counts": dict(sorted(entry_types.items())),
        },
        "scope": "all_persisted_message_branches",
        "metrics": finalize_metrics(metrics),
        "dispatches": analyze_dispatches(entries),
    }


def discover_session_files(paths: list[Path]) -> list[Path]:
    discovered: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved.is_file():
            if resolved.name != "session.jsonl":
                raise ValueError(f"session file must be named session.jsonl: {resolved}")
            discovered.add(resolved)
        elif resolved.is_dir():
            discovered.update(candidate.resolve() for candidate in resolved.rglob("session.jsonl"))
        else:
            raise ValueError(f"session path does not exist: {resolved}")
    if not discovered:
        raise ValueError("no session.jsonl files found")
    return sorted(discovered)


def summarize_sessions(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    total = empty_metrics()
    for session in sessions:
        metrics = session["metrics"]
        for key in (
            "model_responses",
            "prompt_tokens",
            "uncached_prompt_tokens",
            "cached_prompt_tokens",
            "provider_reported_cache_write_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
            "usage_total_mismatch_count",
            "tool_calls",
            "tool_errors",
        ):
            total[key] += metrics[key]
        total["providers"].update(metrics["providers"])
        total["models"].update(metrics["models"])
    return finalize_metrics(total)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sessions", nargs="+", type=Path, help="session.jsonl file or directory to search recursively")
    parser.add_argument("--output", type=Path, help="write JSON metrics to this path instead of stdout")
    args = parser.parse_args()

    sessions = [analyze_session(path) for path in discover_session_files(args.sessions)]
    report = {
        "schema_version": METRIC_SCHEMA_VERSION,
        "provenance": {"script": SCRIPT},
        "scope": "all_persisted_message_branches",
        "sessions": sessions,
        "totals": summarize_sessions(sessions),
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"[e06] wrote {args.output}: {len(sessions)} session(s)")


if __name__ == "__main__":
    main()
