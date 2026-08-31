#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4/validate_layer4_outputs.py --paper-id <paper_id> --layer4-root /srv/datasets/p4a/data/processed/layer4/2026/acl
"""Validate MinerU Layer 4 paper/resource outputs for one paper directory."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import (
    ACCESS_TYPES,
    ARTIFACT_STATUSES,
    AVAILABILITY_STATUSES,
    CITATION_FUNCTIONS,
    DEFAULT_LAYER4_ROOT,
    PAPER_TYPES,
    RELATION_TYPES,
    RESOURCE_KINDS,
    WRAPPING_DIFFICULTIES,
    ensure_paper_record_defaults,
    read_yaml,
    repo_relative,
    write_yaml,
    write_json,
)


def issue(path: str, message: str, suggested_fix: str = "") -> dict[str, str]:
    return {"path": path, "message": message, "suggested_fix": suggested_fix}


def get(root: Any, dotted: str) -> Any:
    current = root
    for part in dotted.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def require_type(root: Any, dotted: str, expected: type, issues: list[dict[str, str]]) -> None:
    value = get(root, dotted)
    if value is None:
        issues.append(issue(dotted, "missing required field", f"add `{dotted.split('.')[-1]}`"))
        return
    if not isinstance(value, expected):
        issues.append(issue(dotted, f"expected {expected.__name__}, got {type(value).__name__}"))


def enum_value(value: Any, allowed: set[str], dotted: str, issues: list[dict[str, str]]) -> None:
    if value is None or value == "":
        return
    if value not in allowed:
        issues.append(issue(dotted, f"invalid enum value {value!r}", f"use one of {sorted(allowed)}"))


def validate_source_artifacts(data: Any, issues: list[dict[str, str]]) -> None:
    artifacts = get(data, "paper_record.source_artifacts")
    if artifacts is None:
        issues.append(issue("paper_record.source_artifacts", "missing required field", "run validate with --update-template"))
        return
    if not isinstance(artifacts, dict):
        issues.append(issue("paper_record.source_artifacts", "must be a mapping"))
        return

    arxiv = artifacts.get("arxiv")
    arxiv_metadata_available = False
    if not isinstance(arxiv, dict):
        issues.append(issue("paper_record.source_artifacts.arxiv", "must be a mapping"))
    else:
        for key in ("arxiv_id", "version", "url", "metadata_status", "metadata_checked_by", "title", "authors", "submitted", "updated", "primary_category", "categories", "abstract", "notes"):
            if key not in arxiv:
                issues.append(issue(f"paper_record.source_artifacts.arxiv.{key}", "missing arXiv metadata field"))
        enum_value(arxiv.get("metadata_status"), ARTIFACT_STATUSES, "paper_record.source_artifacts.arxiv.metadata_status", issues)
        arxiv_metadata_available = arxiv.get("metadata_status") == "available"
        if "authors" in arxiv and not isinstance(arxiv.get("authors"), list):
            issues.append(issue("paper_record.source_artifacts.arxiv.authors", "must be a list"))
        if "categories" in arxiv and not isinstance(arxiv.get("categories"), list):
            issues.append(issue("paper_record.source_artifacts.arxiv.categories", "must be a list"))

    for artifact_key in ("html_downloaded", "tex_source_downloaded"):
        artifact = artifacts.get(artifact_key)
        if not isinstance(artifact, dict):
            issues.append(issue(f"paper_record.source_artifacts.{artifact_key}", "must be a mapping"))
            continue
        for key in ("exists", "status", "path", "url", "checked_by", "notes"):
            if key not in artifact:
                issues.append(issue(f"paper_record.source_artifacts.{artifact_key}.{key}", "missing artifact field"))
        if "exists" in artifact and not isinstance(artifact.get("exists"), bool):
            issues.append(issue(f"paper_record.source_artifacts.{artifact_key}.exists", "must be a boolean"))
        enum_value(artifact.get("status"), ARTIFACT_STATUSES, f"paper_record.source_artifacts.{artifact_key}.status", issues)
        if artifact.get("exists") and not (artifact.get("path") or artifact.get("url")):
            issues.append(issue(f"paper_record.source_artifacts.{artifact_key}.path", "downloaded artifact requires path or url"))
        if artifact.get("status") == "unfetched" and artifact.get("exists"):
            issues.append(issue(f"paper_record.source_artifacts.{artifact_key}.exists", "unfetched artifact cannot have exists=true"))
        if arxiv_metadata_available and artifact.get("status") == "unfetched":
            issues.append(
                issue(
                    f"paper_record.source_artifacts.{artifact_key}.status",
                    "arXiv metadata is available, so artifact fetch should be attempted; use available, missing, failed, or unknown with notes",
                )
            )


def validate_paper_record(data: Any, paper_id: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(data, dict) or "paper_record" not in data:
        return [issue("$", "paper_record.yml must contain a paper_record mapping")]

    for dotted, expected in {
        "paper_record.paper_id": str,
        "paper_record.source_type": str,
        "paper_record.metadata": dict,
        "paper_record.metadata.title": str,
        "paper_record.metadata.authors": list,
        "paper_record.content_units": dict,
        "paper_record.source_artifacts": dict,
        "paper_record.content_units.section_outline": list,
        "paper_record.atomic_extracts": dict,
        "paper_record.atomic_extracts.intent": dict,
        "paper_record.atomic_extracts.contributions": list,
        "paper_record.atomic_extracts.claims": list,
        "paper_record.atomic_extracts.experiments": list,
        "paper_record.atomic_extracts.citation_context": dict,
        "resources_introduced": list,
        "resources_used": list,
        "cites": list,
        "cited_by": list,
    }.items():
        require_type(data, dotted, expected, issues)

    expected_paper_id = f"paper::{paper_id}"
    actual_paper_id = get(data, "paper_record.paper_id")
    if actual_paper_id != expected_paper_id:
        issues.append(issue("paper_record.paper_id", f"expected {expected_paper_id!r}, got {actual_paper_id!r}"))

    enum_value(get(data, "paper_record.atomic_extracts.intent.paper_type"), PAPER_TYPES, "paper_record.atomic_extracts.intent.paper_type", issues)
    validate_source_artifacts(data, issues)

    citations = get(data, "paper_record.atomic_extracts.citation_context.cite") or []
    if not isinstance(citations, list):
        issues.append(issue("paper_record.atomic_extracts.citation_context.cite", "must be a list"))
    else:
        for idx, citation in enumerate(citations):
            if not isinstance(citation, dict):
                issues.append(issue(f"paper_record.atomic_extracts.citation_context.cite[{idx}]", "citation must be mapping"))
                continue
            for key in ("context_id", "raw_citation", "reference_indices", "context", "section"):
                if key not in citation:
                    issues.append(issue(f"paper_record.atomic_extracts.citation_context.cite[{idx}].{key}", "missing citation field"))
            if "cite_key" in citation and not citation.get("context_id"):
                issues.append(issue(f"paper_record.atomic_extracts.citation_context.cite[{idx}]", "MinerU records should use context_id, not only cite_key"))
            if not isinstance(citation.get("reference_indices", []), list):
                issues.append(issue(f"paper_record.atomic_extracts.citation_context.cite[{idx}].reference_indices", "must be a list"))
            enum_value(citation.get("citation_function", ""), CITATION_FUNCTIONS, f"paper_record.atomic_extracts.citation_context.cite[{idx}].citation_function", issues)

    claims = get(data, "paper_record.atomic_extracts.claims") or []
    if isinstance(claims, list) and len(claims) > 2:
        issues.append(issue("paper_record.atomic_extracts.claims", "claims should contain at most 2 abstract-derived items"))
    return issues


def resource_records(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("resource_records.yml must be a YAML list")
    return data


def validate_resource_records(data: Any) -> tuple[list[dict[str, str]], set[str], dict[str, int]]:
    issues: list[dict[str, str]] = []
    ids: set[str] = set()
    kind_counts: dict[str, int] = {}
    try:
        records = resource_records(data)
    except ValueError as exc:
        return [issue("$", str(exc))], ids, kind_counts

    for idx, wrapper in enumerate(records):
        path = f"resource_records[{idx}]"
        if not isinstance(wrapper, dict) or "resource_record" not in wrapper:
            issues.append(issue(path, "each item must contain resource_record"))
            continue
        record = wrapper["resource_record"]
        if not isinstance(record, dict):
            issues.append(issue(f"{path}.resource_record", "must be a mapping"))
            continue

        resource_id = record.get("resource_id")
        if not isinstance(resource_id, str) or "::" not in resource_id:
            issues.append(issue(f"{path}.resource_record.resource_id", "resource_id must look like kind::slug"))
        else:
            if resource_id in ids:
                issues.append(issue(f"{path}.resource_record.resource_id", f"duplicate resource_id {resource_id!r}"))
            ids.add(resource_id)

        kind = record.get("kind")
        enum_value(kind, RESOURCE_KINDS, f"{path}.resource_record.kind", issues)
        if isinstance(kind, str):
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if not record.get("name"):
            issues.append(issue(f"{path}.resource_record.name", "resource name is required"))

        relation = record.get("paper_relation") or {}
        if not isinstance(relation, dict):
            issues.append(issue(f"{path}.resource_record.paper_relation", "paper_relation must be mapping"))
            relation = {}
        enum_value(relation.get("relation_type"), RELATION_TYPES, f"{path}.resource_record.paper_relation.relation_type", issues)
        if relation.get("relation_type") in {"introduced", "used", "evaluated", "extended"} and not relation.get("evidence"):
            issues.append(issue(f"{path}.resource_record.paper_relation.evidence", "non-trivial relation requires paper evidence"))

        access = record.get("access") or {}
        if not isinstance(access, dict):
            issues.append(issue(f"{path}.resource_record.access", "access must be mapping"))
            access = {}
        enum_value(access.get("access_type"), ACCESS_TYPES, f"{path}.resource_record.access.access_type", issues)

        availability = record.get("availability_check") or {}
        if not isinstance(availability, dict):
            issues.append(issue(f"{path}.resource_record.availability_check", "availability_check must be mapping"))
            availability = {}
        enum_value(availability.get("status"), AVAILABILITY_STATUSES, f"{path}.resource_record.availability_check.status", issues)

        agent_callable = record.get("agent_callable") or {}
        if not isinstance(agent_callable, dict):
            issues.append(issue(f"{path}.resource_record.agent_callable", "agent_callable must be mapping"))
            agent_callable = {}
        enum_value(
            agent_callable.get("estimated_wrapping_difficulty"),
            WRAPPING_DIFFICULTIES,
            f"{path}.resource_record.agent_callable.estimated_wrapping_difficulty",
            issues,
        )

        url = str(access.get("url") or access.get("original_url") or "")
        repo = record.get("repository")
        if "github.com" in url.lower():
            if not isinstance(repo, dict):
                issues.append(issue(f"{path}.resource_record.repository", "GitHub resource requires repository verification block"))
            else:
                verification = repo.get("verification") or {}
                if verification.get("checked_by") != "github_mcp":
                    issues.append(issue(f"{path}.resource_record.repository.verification.checked_by", "GitHub resources should be checked by github_mcp"))
                if not repo.get("canonical_url"):
                    issues.append(issue(f"{path}.resource_record.repository.canonical_url", "canonical GitHub URL is required"))

        hf_url = "huggingface.co" in url.lower()
        checked_by = str(availability.get("checked_by") or "")
        if hf_url and checked_by not in {"pending_huggingface_mcp", "huggingface_mcp", "hf-readonly"}:
            issues.append(issue(f"{path}.resource_record.availability_check.checked_by", "HuggingFace resources must be marked pending_huggingface_mcp or checked by hf-readonly/huggingface_mcp"))
        if checked_by == "pending_huggingface_mcp" and not hf_url:
            issues.append(issue(f"{path}.resource_record.availability_check.checked_by", "pending_huggingface_mcp is only valid for huggingface.co URLs"))

    return issues, ids, kind_counts


def validate_json_file(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return [issue(repo_relative(path), "missing JSON file")]
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [issue(repo_relative(path), f"invalid JSON: {exc}")]
    return []


def validate_directory(paper_dir: Path, paper_id: str, update_template: bool = False) -> dict[str, Any]:
    paper_path = paper_dir / "paper_record.yml"
    resources_path = paper_dir / "resource_records.yml"
    issues: list[dict[str, str]] = []
    schema_updates: list[str] = []

    if not paper_path.exists():
        issues.append(issue(repo_relative(paper_path), "missing paper_record.yml"))
        paper_data = {}
    else:
        try:
            paper_data = read_yaml(paper_path)
            if update_template and isinstance(paper_data, dict):
                schema_updates = ensure_paper_record_defaults(paper_data)
                if schema_updates:
                    write_yaml(paper_path, paper_data)
            issues.extend(validate_paper_record(paper_data, paper_id))
        except Exception as exc:  # noqa: BLE001
            paper_data = {}
            issues.append(issue(repo_relative(paper_path), f"could not parse YAML: {exc}"))

    if not resources_path.exists():
        issues.append(issue(repo_relative(resources_path), "missing resource_records.yml"))
        resource_ids: set[str] = set()
        kind_counts: dict[str, int] = {}
    else:
        try:
            resources_data = read_yaml(resources_path)
            resource_issues, resource_ids, kind_counts = validate_resource_records(resources_data)
            issues.extend(resource_issues)
        except Exception as exc:  # noqa: BLE001
            resource_ids = set()
            kind_counts = {}
            issues.append(issue(repo_relative(resources_path), f"could not parse YAML: {exc}"))

    for field in ("resources_introduced", "resources_used"):
        for resource_id in get(paper_data, field) or []:
            if resource_id not in resource_ids:
                issues.append(issue(field, f"{resource_id!r} is not present in resource_records.yml"))

    issues.extend(validate_json_file(paper_dir / "resource_verification_report.json"))
    issues.extend(validate_json_file(paper_dir / "run_report.json"))

    github_checked_count = 0
    if (paper_dir / "resource_verification_report.json").exists():
        try:
            report = json.loads((paper_dir / "resource_verification_report.json").read_text(encoding="utf-8"))
            checks = report.get("checks") or report.get("resources") or []
            if isinstance(checks, list):
                github_checked_count = sum(
                    1
                    for item in checks
                    if isinstance(item, dict)
                    and re.search(r"github", str(item.get("method") or item.get("checked_by") or ""), re.I)
                )
        except Exception:
            pass

    return {
        "paper_id": paper_id,
        "ok": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "resource_count": len(resource_ids),
        "resource_kind_counts": kind_counts,
        "github_checked_count": github_checked_count,
        "schema_updates": schema_updates,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate MinerU Layer 4 outputs for one paper.")
    parser.add_argument("--paper-id", help="Paper id. Defaults to the paper directory name.")
    parser.add_argument("--paper-dir", type=Path, help="Layer 4 paper directory.")
    parser.add_argument("--layer4-root", type=Path, default=DEFAULT_LAYER4_ROOT)
    parser.add_argument("--report", type=Path, help="Quality report JSON path. Defaults to <paper-dir>/quality_report.json.")
    parser.add_argument("--update-template", action="store_true", help="Add missing forward-compatible template fields before validating.")
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

    report = validate_directory(paper_dir, paper_id, update_template=args.update_template)
    report_path = args.report or (paper_dir / "quality_report.json")
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
