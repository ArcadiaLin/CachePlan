#!/usr/bin/env python3
"""Shared paths, state helpers, and constants for Layer4 v2 (program + two LLM calls)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LAYER4_DIR = Path(__file__).resolve().parents[1] / "layer4"
if str(_LAYER4_DIR) not in sys.path:
    sys.path.insert(0, str(_LAYER4_DIR))

from common import (  # noqa: E402
    ACCESS_TYPES,
    ARTIFACT_STATUSES,
    AVAILABILITY_STATUSES,
    CITATION_FUNCTIONS,
    DEFAULT_DATA_ROOT,
    PAPER_TYPES,
    RELATION_TYPES,
    REPO_ROOT,
    RESOURCE_KINDS,
    WRAPPING_DIFFICULTIES,
    default_source_artifacts,
    find_jsonl_record,
    markdown_path_for_reference,
    content_list_path,
    normalize_ws,
    section_outline,
    write_json,
)

__all__ = [
    "ACCESS_TYPES",
    "ARTIFACT_STATUSES",
    "AVAILABILITY_STATUSES",
    "CITATION_FUNCTIONS",
    "DEFAULT_DATA_ROOT",
    "PAPER_TYPES",
    "RELATION_TYPES",
    "REPO_ROOT",
    "RESOURCE_KINDS",
    "WRAPPING_DIFFICULTIES",
    "default_source_artifacts",
    "find_jsonl_record",
    "markdown_path_for_reference",
    "content_list_path",
    "normalize_ws",
    "section_outline",
    "write_json",
    "DEFAULT_LAYER4_V2_ROOT",
    "DEFAULT_V2_CACHE_ROOT",
    "VLLM_BASE_URL",
    "PROXY_URL",
    "V2_STATUSES",
    "load_state",
    "save_state",
    "set_stage",
    "now_iso",
    "read_json",
    "est_tokens",
]

DEFAULT_LAYER4_V2_ROOT = DEFAULT_DATA_ROOT / "processed/layer4_v2/2026/acl"
DEFAULT_V2_CACHE_ROOT = DEFAULT_DATA_ROOT / "processed/layer4_v2/cache"

VLLM_BASE_URL = "http://192.168.163.112:8003/v1"
PROXY_URL = "http://127.0.0.1:7899"

# 状态机: prepared -> inputs_built -> candidates_done -> verified -> judged -> merged
# 失败态: repairing / fallback_agent / blocked_v2_manual
V2_STATUSES = [
    "prepared",
    "inputs_built",
    "candidates_done",
    "verified",
    "judged",
    "merged",
    "fallback_agent",
    "blocked_v2_manual",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def est_tokens(text: str) -> int:
    """Rough token estimate for English/Markdown (bytes/4)."""
    return len(text.encode("utf-8")) // 4


def state_path(paper_dir: Path) -> Path:
    return paper_dir / "v2_state.json"


def load_state(paper_dir: Path, paper_id: str) -> dict[str, Any]:
    path = state_path(paper_dir)
    if path.exists():
        try:
            value = read_json(path)
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    return {"paper_id": paper_id, "status": "", "stages": {}, "updated_at": ""}


def save_state(paper_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    write_json(state_path(paper_dir), state)


def set_stage(
    state: dict[str, Any],
    stage: str,
    *,
    status: str,
    seconds: float | None = None,
    **extra: Any,
) -> None:
    entry: dict[str, Any] = {"status": status, "at": now_iso()}
    if seconds is not None:
        entry["seconds"] = round(seconds, 2)
    entry.update(extra)
    state.setdefault("stages", {})[stage] = entry
    if status == "done" and stage in V2_STATUSES:
        state["status"] = stage
