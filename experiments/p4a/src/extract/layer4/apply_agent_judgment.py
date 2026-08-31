#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4/apply_agent_judgment.py --paper-id <paper_id> --layer4-root /srv/datasets/p4a/data/processed/layer4/2026/acl
"""Merge MinerU Layer 4 agent JSON judgment into controlled YAML outputs."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    ACCESS_TYPES,
    AVAILABILITY_STATUSES,
    CITATION_FUNCTIONS,
    DEFAULT_LAYER4_ROOT,
    PAPER_TYPES,
    RELATION_TYPES,
    RESOURCE_KINDS,
    WRAPPING_DIFFICULTIES,
    ARTIFACT_STATUSES,
    default_source_artifacts,
    ensure_paper_record_defaults,
    read_yaml,
    repo_relative,
    resource_id,
    slugify,
    write_json,
    write_yaml,
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def enum_or(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")]


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str):
            result.append({"text": item})
    return result


def bool_or(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return True
        if text in {"false", "0", "no", "n", ""}:
            return False
    return default


def enum_error(path: str, value: Any, allowed: set[str]) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text in allowed:
        return None
    return f"{path}: invalid enum value {text!r}; use one of {sorted(allowed)}"


def validate_judgment(judgment: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    paper = judgment.get("paper_record") or {}
    if isinstance(paper, dict):
        source_artifacts = paper.get("source_artifacts") or {}
        if isinstance(source_artifacts, dict):
            arxiv = source_artifacts.get("arxiv") or paper.get("arxiv") or {}
            if isinstance(arxiv, dict):
                error = enum_error(
                    "paper_record.source_artifacts.arxiv.metadata_status",
                    arxiv.get("metadata_status"),
                    ARTIFACT_STATUSES,
                )
                if error:
                    errors.append(error)
            for artifact_key in ("html_downloaded", "tex_source_downloaded"):
                artifact = source_artifacts.get(artifact_key) or paper.get(artifact_key) or {}
                if isinstance(artifact, dict):
                    error = enum_error(
                        f"paper_record.source_artifacts.{artifact_key}.status",
                        artifact.get("status"),
                        ARTIFACT_STATUSES,
                    )
                    if error:
                        errors.append(error)
        intent = paper.get("intent") or {}
        if isinstance(intent, dict):
            error = enum_error("paper_record.intent.paper_type", intent.get("paper_type"), PAPER_TYPES)
            if error:
                errors.append(error)
        for idx, citation in enumerate(list_of_dicts(paper.get("citation_functions"))):
            error = enum_error(
                f"paper_record.citation_functions[{idx}].citation_function",
                citation.get("citation_function"),
                CITATION_FUNCTIONS,
            )
            if error:
                errors.append(error)

    for idx, resource in enumerate(list_of_dicts(judgment.get("resources"))):
        for path, value, allowed in (
            (f"resources[{idx}].kind", resource.get("kind"), RESOURCE_KINDS),
            (f"resources[{idx}].relation_type", resource.get("relation_type") or resource.get("paper_relation"), RELATION_TYPES),
        ):
            error = enum_error(path, value, allowed)
            if error:
                errors.append(error)
        access = resource.get("access") if isinstance(resource.get("access"), dict) else {}
        error = enum_error(f"resources[{idx}].access.access_type", access.get("access_type"), ACCESS_TYPES)
        if error:
            errors.append(error)
        availability = resource.get("availability") or resource.get("availability_check") or {}
        if isinstance(availability, dict):
            error = enum_error(f"resources[{idx}].availability.status", availability.get("status"), AVAILABILITY_STATUSES)
            if error:
                errors.append(error)
            checked_by = str(availability.get("checked_by") or "").strip()
            url = ""
            if isinstance(access, dict):
                url = str(access.get("url") or resource.get("url") or "")
            if checked_by == "pending_huggingface_mcp" and "huggingface.co" not in url.lower():
                errors.append(
                    f"resources[{idx}].availability.checked_by: pending_huggingface_mcp is only valid for huggingface.co URLs"
                )
        agent_callable = resource.get("agent_callable") if isinstance(resource.get("agent_callable"), dict) else {}
        error = enum_error(
            f"resources[{idx}].agent_callable.estimated_wrapping_difficulty",
            agent_callable.get("estimated_wrapping_difficulty"),
            WRAPPING_DIFFICULTIES,
        )
        if error:
            errors.append(error)
    return errors


def evidence_text(value: Any) -> str:
    if isinstance(value, dict):
        section = str(value.get("section") or "").strip()
        quote = str(value.get("quote") or value.get("text") or "").strip()
        if section and quote:
            return f"{section}: {quote}"
        return quote or section
    return str(value or "").strip()


def merge_mapping(target: dict[str, Any], update: dict[str, Any], allowed_keys: set[str]) -> None:
    for key in allowed_keys:
        if key in update and update.get(key) is not None:
            target[key] = update.get(key)


def normalize_artifact_update(update: Any, defaults: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(defaults)
    if not isinstance(update, dict):
        return result
    for key, default_value in defaults.items():
        if key not in update:
            continue
        value = update.get(key)
        if key == "exists":
            result[key] = bool_or(value, bool(default_value))
        elif key in {"authors", "categories"}:
            result[key] = list_of_strings(value)
        elif key in {"status", "metadata_status"}:
            result[key] = enum_or(value, ARTIFACT_STATUSES, str(default_value))
        else:
            result[key] = str(value or "")
    return result


def apply_source_artifact_judgment(paper_record: dict[str, Any], agent_paper: dict[str, Any]) -> None:
    ensure_paper_record_defaults({"paper_record": paper_record})
    artifacts = paper_record.setdefault("source_artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = default_source_artifacts()
        paper_record["source_artifacts"] = artifacts

    agent_artifacts = agent_paper.get("source_artifacts") if isinstance(agent_paper.get("source_artifacts"), dict) else {}
    defaults = default_source_artifacts()

    arxiv_update = {}
    if isinstance(agent_artifacts, dict):
        arxiv_update = agent_artifacts.get("arxiv") if isinstance(agent_artifacts.get("arxiv"), dict) else {}
    if not arxiv_update and isinstance(agent_paper.get("arxiv"), dict):
        arxiv_update = agent_paper.get("arxiv") or {}
    if isinstance(arxiv_update, dict):
        current = artifacts.setdefault("arxiv", {})
        if not isinstance(current, dict):
            current = {}
            artifacts["arxiv"] = current
        normalized = normalize_artifact_update(arxiv_update, defaults["arxiv"])
        merge_mapping(current, normalized, set(defaults["arxiv"].keys()))

        metadata = paper_record.setdefault("metadata", {})
        if isinstance(metadata, dict):
            if normalized.get("arxiv_id"):
                metadata["arxiv_id"] = normalized["arxiv_id"]
            if normalized.get("url"):
                metadata["url"] = normalized["url"]

    for artifact_key in ("html_downloaded", "tex_source_downloaded"):
        artifact_update = {}
        if isinstance(agent_artifacts, dict) and isinstance(agent_artifacts.get(artifact_key), dict):
            artifact_update = agent_artifacts.get(artifact_key) or {}
        elif isinstance(agent_paper.get(artifact_key), dict):
            artifact_update = agent_paper.get(artifact_key) or {}
        if not isinstance(artifact_update, dict):
            continue
        current = artifacts.setdefault(artifact_key, {})
        if not isinstance(current, dict):
            current = {}
            artifacts[artifact_key] = current
        normalized = normalize_artifact_update(artifact_update, defaults[artifact_key])
        merge_mapping(current, normalized, set(defaults[artifact_key].keys()))


def apply_paper_judgment(base: dict[str, Any], judgment: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(base)
    ensure_paper_record_defaults(output)
    paper_record = output.setdefault("paper_record", {})
    atomic = paper_record.setdefault("atomic_extracts", {})
    agent_paper = judgment.get("paper_record") or {}
    if not isinstance(agent_paper, dict):
        agent_paper = {}

    metadata = paper_record.setdefault("metadata", {})
    agent_metadata = agent_paper.get("metadata") or {}
    if isinstance(metadata, dict) and isinstance(agent_metadata, dict):
        merge_mapping(
            metadata,
            agent_metadata,
            {"arxiv_id", "acl_id", "doi", "url", "pdf_path", "markdown_path", "content_list_path"},
        )

    apply_source_artifact_judgment(paper_record, agent_paper)

    intent = atomic.setdefault("intent", {})
    agent_intent = agent_paper.get("intent") or {}
    if isinstance(agent_intent, dict):
        if "paper_type" in agent_intent:
            intent["paper_type"] = enum_or(agent_intent.get("paper_type"), PAPER_TYPES, "unknown")
        if "research_problem" in agent_intent:
            intent["research_problem"] = str(agent_intent.get("research_problem") or "")
        if "target_domain" in agent_intent:
            intent["target_domain"] = list_of_strings(agent_intent.get("target_domain"))

    for field in ("contributions", "experiments", "limitations", "future_work"):
        if field in agent_paper:
            atomic[field] = list_of_dicts(agent_paper.get(field))

    if "claims" in agent_paper:
        atomic["claims"] = list_of_dicts(agent_paper.get("claims"))[:2]

    citation_by_context = {
        str(item.get("context_id") or ""): item
        for item in list_of_dicts(agent_paper.get("citation_functions"))
        if item.get("context_id")
    }
    citation_context = atomic.setdefault("citation_context", {})
    citations = citation_context.setdefault("cite", [])
    if isinstance(citations, list):
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            context_id = str(citation.get("context_id") or "")
            update = citation_by_context.get(context_id)
            if not update:
                continue
            citation["citation_function"] = enum_or(update.get("citation_function"), CITATION_FUNCTIONS, "")

    return output


def normalize_resource(item: dict[str, Any], paper_id: str) -> dict[str, Any]:
    kind = enum_or(item.get("kind"), RESOURCE_KINDS, "resource")
    name = str(item.get("name") or item.get("title") or "unknown").strip() or "unknown"
    rid = str(item.get("resource_id") or resource_id(kind, name))
    if "::" not in rid:
        rid = f"{kind}::{slugify(rid)}"

    relation_type = enum_or(item.get("relation_type") or item.get("paper_relation"), RELATION_TYPES, "unknown")
    evidence = item.get("evidence") or {}
    access = item.get("access") if isinstance(item.get("access"), dict) else {}
    availability = item.get("availability") or item.get("availability_check") or {}
    if not isinstance(availability, dict):
        availability = {}
    repository = item.get("repository") if isinstance(item.get("repository"), dict) else {}
    agent_callable = item.get("agent_callable") if isinstance(item.get("agent_callable"), dict) else {}

    checked_by = str(availability.get("checked_by") or "agent")
    url = str(access.get("url") or item.get("url") or "")
    if "huggingface.co" in url.lower() and checked_by == "agent":
        checked_by = "pending_huggingface_mcp"

    return {
        "resource_record": {
            "resource_id": rid,
            "kind": kind,
            "name": name,
            "aliases": list_of_strings(item.get("aliases")),
            "description": str(item.get("description") or ""),
            "paper_relation": {
                "relation_type": relation_type,
                "evidence": evidence_text(evidence),
                "section": str(evidence.get("section") or item.get("section") or "") if isinstance(evidence, dict) else "",
                "citation_context_ids": list_of_strings(
                    item.get("citation_context_ids")
                    or (evidence.get("citation_context_ids") if isinstance(evidence, dict) else [])
                ),
            },
            "access": {
                "access_type": enum_or(access.get("access_type"), ACCESS_TYPES, "unknown"),
                "url": url,
                "license": str(access.get("license") or item.get("license") or ""),
            },
            "availability_check": {
                "status": enum_or(availability.get("status"), AVAILABILITY_STATUSES, "unknown"),
                "checked_by": checked_by,
                "checked_at": str(availability.get("checked_at") or ""),
                "notes": str(availability.get("notes") or ""),
            },
            "repository": {
                "canonical_url": str(repository.get("canonical_url") or (url if "github.com" in url.lower() else "")),
                "verification": {
                    "checked_by": str((repository.get("verification") or {}).get("checked_by") or ("github_mcp" if "github.com" in url.lower() else "")),
                    "status": str((repository.get("verification") or {}).get("status") or "unknown"),
                    "notes": str((repository.get("verification") or {}).get("notes") or ""),
                },
            },
            "agent_callable": {
                "can_wrap": bool(agent_callable.get("can_wrap", False)),
                "estimated_wrapping_difficulty": enum_or(
                    agent_callable.get("estimated_wrapping_difficulty"),
                    WRAPPING_DIFFICULTIES,
                    "unknown",
                ),
                "notes": str(agent_callable.get("notes") or ""),
            },
            "provenance": {
                "extracted_from": [paper_id],
                "extraction_confidence": str(item.get("confidence") or "medium"),
                "last_checked": datetime.now(timezone.utc).isoformat(),
            },
        }
    }


def dedupe_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for wrapper in resources:
        record = wrapper["resource_record"]
        key = str(record.get("resource_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(wrapper)
    return result


def apply_resources(paper_data: dict[str, Any], judgment: dict[str, Any], paper_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output = deepcopy(paper_data)
    resources = dedupe_resources([normalize_resource(item, paper_id) for item in list_of_dicts(judgment.get("resources"))])

    introduced: list[str] = []
    used: list[str] = []
    for wrapper in resources:
        record = wrapper["resource_record"]
        rid = str(record["resource_id"])
        relation = (record.get("paper_relation") or {}).get("relation_type")
        if relation == "introduced":
            introduced.append(rid)
        elif relation in {"used", "evaluated", "extended"}:
            used.append(rid)

    output["resources_introduced"] = introduced
    output["resources_used"] = used
    output.setdefault("cites", [])
    output.setdefault("cited_by", [])
    output.setdefault("source_paper", "")
    output.setdefault("comparison", "")
    return output, resources


def build_verification_report(paper_id: str, judgment: dict[str, Any], resources: list[dict[str, Any]]) -> dict[str, Any]:
    checks = list_of_dicts(judgment.get("verification_checks"))
    for wrapper in resources:
        record = wrapper["resource_record"]
        availability = record.get("availability_check") or {}
        repository = record.get("repository") or {}
        checks.append(
            {
                "resource_id": record.get("resource_id"),
                "name": record.get("name"),
                "method": (repository.get("verification") or {}).get("checked_by") or availability.get("checked_by") or "agent",
                "status": availability.get("status", "unknown"),
                "url": (record.get("access") or {}).get("url", ""),
                "notes": availability.get("notes", ""),
            }
        )
    return {
        "paper_id": paper_id,
        "status": "merged",
        "checks": checks,
        "warnings": list_of_strings(judgment.get("warnings")),
        "errors": [],
    }


def build_run_report(paper_id: str, judgment_path: Path, resources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "status": "merged",
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "agent_judgment": repo_relative(judgment_path),
        "resource_count": len(resources),
        "github_checked_count": sum(
            1
            for wrapper in resources
            if ((wrapper["resource_record"].get("repository") or {}).get("verification") or {}).get("checked_by") == "github_mcp"
        ),
        "warnings": [],
        "errors": [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply MinerU Layer 4 agent JSON judgment to YAML outputs.")
    parser.add_argument("--paper-id", help="Paper id. Defaults to the paper directory name.")
    parser.add_argument("--paper-dir", type=Path, help="Layer 4 paper directory.")
    parser.add_argument("--layer4-root", type=Path, default=DEFAULT_LAYER4_ROOT)
    parser.add_argument("--judgment", type=Path, help="agent_judgment.json path. Defaults to <paper-dir>/agent_judgment.json.")
    parser.add_argument("--base-paper", type=Path, help="Base paper YAML. Defaults to <paper-dir>/paper_record.base.yml.")
    parser.add_argument("--output-paper", type=Path, help="Output paper YAML. Defaults to <paper-dir>/paper_record.yml.")
    parser.add_argument("--output-resources", type=Path, help="Output resource YAML. Defaults to <paper-dir>/resource_records.yml.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.paper_dir:
        paper_dir = args.paper_dir
        paper_id = args.paper_id or paper_dir.name
    elif args.paper_id:
        paper_id = args.paper_id
        paper_dir = args.layer4_root / paper_id
    else:
        raise SystemExit("Provide --paper-id or --paper-dir")

    judgment_path = args.judgment or (paper_dir / "agent_judgment.json")
    base_paper_path = args.base_paper or (paper_dir / "paper_record.base.yml")
    if not base_paper_path.exists():
        base_paper_path = paper_dir / "paper_record.yml"
    output_paper_path = args.output_paper or (paper_dir / "paper_record.yml")
    output_resources_path = args.output_resources or (paper_dir / "resource_records.yml")

    judgment = load_json(judgment_path)
    judgment_errors = validate_judgment(judgment)
    if judgment_errors:
        write_json(
            paper_dir / "agent_merge_report.json",
            {
                "paper_id": paper_id,
                "status": "failed",
                "errors": judgment_errors,
            },
        )
        raise SystemExit("agent_judgment.json failed validation:\n" + "\n".join(judgment_errors))

    base_paper = read_yaml(base_paper_path)
    if not isinstance(base_paper, dict):
        raise SystemExit(f"{base_paper_path} must contain a YAML mapping")

    paper_data = apply_paper_judgment(base_paper, judgment)
    paper_data, resources = apply_resources(paper_data, judgment, paper_id)

    write_yaml(output_paper_path, paper_data)
    write_yaml(output_resources_path, resources)
    write_json(paper_dir / "resource_verification_report.json", build_verification_report(paper_id, judgment, resources))
    write_json(paper_dir / "run_report.json", build_run_report(paper_id, judgment_path, resources))
    write_json(
        paper_dir / "agent_merge_report.json",
        {
            "paper_id": paper_id,
            "status": "merged",
            "resource_count": len(resources),
            "outputs": {
                "paper_record": repo_relative(output_paper_path),
                "resource_records": repo_relative(output_resources_path),
            },
        },
    )
    print(f"merged {paper_id}: {len(resources)} resources")


if __name__ == "__main__":
    main()
