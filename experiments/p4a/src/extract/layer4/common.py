#!/usr/bin/env python3
"""Shared helpers for MinerU Layer 4 extraction scripts."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")


def configured_data_root() -> Path:
    value = os.environ.get("P4A_DATA_ROOT")
    if value:
        return Path(value)
    value = os.environ.get("DATA_ROOT") or os.environ.get("DATASET_ROOT")
    if value:
        root = Path(value)
        return root if root.name == "data" else root / "data"
    return Path("/srv/datasets/p4a/data")


DEFAULT_DATA_ROOT = configured_data_root()
DEFAULT_REFERENCES_JSONL = DEFAULT_DATA_ROOT / "processed/cite/2026/acl/acl2026_verified_plus_repaired.jsonl"
DEFAULT_CITE_CONTEXTS_JSONL = DEFAULT_DATA_ROOT / "processed/cite/2026/acl/acl2026_cite_contexts.jsonl"
DEFAULT_LAYER4_ROOT = DEFAULT_DATA_ROOT / "processed/layer4/2026/acl"

RESOURCE_KINDS = {"dataset", "benchmark", "code", "model", "tool", "skill", "protocol", "resource"}
RELATION_TYPES = {"introduced", "used", "evaluated", "extended", "cited_only", "unknown"}
ACCESS_TYPES = {"public", "request_only", "restricted", "missing", "unknown"}
AVAILABILITY_STATUSES = {"available", "partial", "missing", "broken", "empty", "unknown"}
ARTIFACT_STATUSES = {"available", "missing", "failed", "unfetched", "unknown"}
WRAPPING_DIFFICULTIES = {"low", "medium", "high", "unknown"}
PAPER_TYPES = {"survey", "empirical", "benchmark", "dataset", "method", "theory", "position", "unknown"}
CITATION_FUNCTIONS = {
    "",
    "background",
    "method_source",
    "dataset_source",
    "benchmark_source",
    "baseline",
    "tool_source",
    "model_source",
    "claim_support",
    "comparison",
    "contrast",
    "related_work",
    "other",
    "unknown",
}


def require_yaml() -> Any:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "PyYAML is required. Run with the project environment, for example: "
            ".venv/bin/python src/extract/layer4/<script>.py ..."
        ) from exc
    return yaml


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


def find_jsonl_record(path: Path, paper_id: str) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            if value.get("paper_id") == paper_id:
                return value
    raise SystemExit(f"Paper {paper_id!r} not found in {path}")


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def stable_data_path(path: Path) -> str:
    """Return paths for generated data artifacts using the configured data root."""
    path = path.resolve() if path.exists() else path
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


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


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "unknown"


def resource_id(kind: str, name: str) -> str:
    return f"{kind}::{slugify(name)}"


def default_source_artifacts() -> dict[str, Any]:
    return {
        "arxiv": {
            "arxiv_id": "",
            "version": "",
            "url": "",
            "metadata_status": "unfetched",
            "metadata_checked_by": "",
            "title": "",
            "authors": [],
            "submitted": "",
            "updated": "",
            "primary_category": "",
            "categories": [],
            "abstract": "",
            "notes": "",
        },
        "html_downloaded": {
            "exists": False,
            "status": "unfetched",
            "path": "",
            "url": "",
            "checked_by": "",
            "notes": "",
        },
        "tex_source_downloaded": {
            "exists": False,
            "status": "unfetched",
            "path": "",
            "url": "",
            "checked_by": "",
            "notes": "",
        },
    }


def ensure_paper_record_defaults(data: dict[str, Any]) -> list[str]:
    updates: list[str] = []
    paper_record = data.setdefault("paper_record", {})
    if not isinstance(paper_record, dict):
        return updates

    metadata = paper_record.setdefault("metadata", {})
    if isinstance(metadata, dict):
        for key, default in {
            "arxiv_id": "",
            "acl_id": "",
            "doi": "",
            "url": "",
            "pdf_path": "",
            "markdown_path": "",
            "content_list_path": "",
        }.items():
            if key not in metadata:
                metadata[key] = default
                updates.append(f"paper_record.metadata.{key}")

    defaults = default_source_artifacts()
    artifacts = paper_record.setdefault("source_artifacts", {})
    if not isinstance(artifacts, dict):
        paper_record["source_artifacts"] = default_source_artifacts()
        updates.append("paper_record.source_artifacts")
        return updates

    for artifact_key, artifact_default in defaults.items():
        current = artifacts.setdefault(artifact_key, {})
        if not isinstance(current, dict):
            artifacts[artifact_key] = artifact_default
            updates.append(f"paper_record.source_artifacts.{artifact_key}")
            continue
        for field, default_value in artifact_default.items():
            if field not in current:
                current[field] = default_value
                updates.append(f"paper_record.source_artifacts.{artifact_key}.{field}")
    return updates


def markdown_path_for_reference(record: dict[str, Any]) -> Path:
    markdown_path = record.get("markdown_path")
    if markdown_path:
        path = resolve_data_path(str(markdown_path))
        if path.exists():
            return path
    source_dir = record.get("source_dir")
    paper_id = record.get("paper_id")
    if source_dir and paper_id:
        path = resolve_data_path(str(source_dir)) / f"{paper_id}.md"
        if path.exists():
            return path
    raise SystemExit(f"Markdown path not found for {record.get('paper_id')}")


def content_list_path(markdown_path: Path) -> Path | None:
    stem = markdown_path.with_suffix("")
    for suffix in ("_content_list_v2.json", "_content_list.json"):
        candidate = Path(str(stem) + suffix)
        if candidate.exists():
            return candidate
    return None


def pdf_path(markdown_path: Path) -> Path | None:
    stem = markdown_path.with_suffix("")
    candidate = Path(str(stem) + "_origin.pdf")
    return candidate if candidate.exists() else None


def first_heading(markdown: str) -> str:
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return normalize_ws(match.group(1))
    return ""


def section_outline(markdown: str) -> list[dict[str, Any]]:
    outline: list[dict[str, Any]] = []
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        title = normalize_ws(match.group(2))
        if title.lower() in {"references", "bibliography", "reference"}:
            break
        outline.append({"level": len(match.group(1)), "title": title, "line": line_number})
    return outline


def section_text(markdown: str, heading_pattern: str) -> str:
    pattern = re.compile(rf"(?im)^#+\s*{heading_pattern}\s*$")
    match = pattern.search(markdown)
    if not match:
        return ""
    next_heading = re.search(r"(?m)^#+\s+", markdown[match.end() :])
    end = match.end() + next_heading.start() if next_heading else len(markdown)
    return normalize_ws(markdown[match.end() : end])


def abstract_from_markdown(markdown: str) -> str:
    return section_text(markdown, r"abstract")


def year_from_paper_id(paper_id: str) -> str:
    match = re.match(r"((?:19|20)\d{2})", paper_id)
    return match.group(1) if match else "unknown"


def venue_from_paper_id(paper_id: str) -> str:
    parts = paper_id.split(".")
    if len(parts) >= 2 and re.fullmatch(r"(?:19|20)\d{2}", parts[0]):
        return f"{parts[1].upper()} {parts[0]}"
    return ""


def write_yaml(path: Path, data: Any) -> None:
    yaml = require_yaml()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(data, stream, allow_unicode=True, sort_keys=False, width=120)


def read_yaml(path: Path) -> Any:
    yaml = require_yaml()
    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
