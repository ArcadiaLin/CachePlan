#!/usr/bin/env python3
"""
将 agent 阅读论文后的语义判断合并进机械生成的 paper_record.yml。

用法:
    uv run python "$SCRIPTS_DIR/apply_agent_judgment.py" \
      --base <run-output-dir>/2604.28123/paper_record.yml \
      --judgment <run-output-dir>/2604.28123/agent_judgment.yml \
      --output <run-output-dir>/2604.28123/paper_record.agent.yml

    uv run python "$SCRIPTS_DIR/apply_agent_judgment.py" \
      --base <run-output-dir>/2604.28123/paper_record.yml \
      --resource-records <run-output-dir>/2604.28123/resource_records.yml \
      --judgment <run-output-dir>/2604.28123/agent_judgment.yml \
      --output <run-output-dir>/2604.28123/paper_record.agent.yml \
      --resource-output <run-output-dir>/2604.28123/resource_records.agent.yml

    # 覆盖原文件前建议先输出到新文件，lint 通过后再由 agent 使用 edit 工具定点修改原文件。

agent_judgment.yml 推荐结构:
    paper_record:
      atomic_extracts:
        intent:
          paper_type: empirical
          research_problem: "..."
          target_domain: [ai_for_science]
        contributions: []
        claims: []  # 1-2 abstract-derived claims, without evidence
        experiments: []
        limitations: []
        future_work: []
        citation_context:
          cite:
            - cite_key: xxx
              citation_function: background
      content_units:
        figures:
          - figure_id: fig::example
            description: "Caption/context-based figure role."
            agent_review:
              status: ok
              notes: ""
    resource_judgments:
      - kind: code
        name: "PRISM"
        aliases: ["Project repository"]
        access:
          url: "https://github.com/XIAO4579/PRISM"
        description: "Code, data, and model checkpoint entry mentioned in the abstract."
        domain: [multimodal_reasoning]
        evidence:
          - section: Abstract
            quote: "Our code, data, and model checkpoints are publicly available..."

边界:
    只允许合并语义字段白名单；metadata、abstract、section_outline、机械引用上下文、
    figure caption/files/source 等由机械脚本负责，默认拒绝通过本脚本覆盖。
    资源记录合并不自动推断 resources_introduced/resources_used；这些纸面用途列表
    只接受 agent 明确写入的语义判断。

配置:
    可合并字段白名单和 citation 可补充字段来自
    scripts/config/*.yml 的 agent_judgment 段。
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from script_config import load_config
from yaml_linter import lint_file


def _load_yaml(path: Path) -> Any:
    yaml = YAML()
    with path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle)


def _write_yaml(path: Path, data: Any) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 120
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


def _slug(text: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return slug or "unknown"


def _get(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set(data: Any, path: str, value: Any) -> None:
    current = data
    parts = path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = deepcopy(value)


def _record_body(record: dict[str, Any]) -> dict[str, Any]:
    if "resource_record" in record and isinstance(record["resource_record"], dict):
        return record["resource_record"]
    return record


def _resource_url(resource: dict[str, Any]) -> str:
    access = resource.get("access")
    if isinstance(access, dict):
        return str(access.get("url") or "")
    return str(resource.get("url") or "")


def _resource_id(resource: dict[str, Any]) -> str:
    if resource.get("resource_id"):
        return str(resource["resource_id"])
    kind = resource.get("kind") or "resource"
    name = resource.get("name") or _resource_url(resource) or "unknown"
    return f"{kind}::{_slug(name)}"


def _resource_keys(resource: dict[str, Any], dedupe_keys: list[str]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for key_name in dedupe_keys:
        if key_name == "resource_id":
            rid = resource.get("resource_id")
            if rid:
                keys.append(("resource_id", str(rid)))
        elif key_name == "url":
            url = _resource_url(resource)
            if url:
                keys.append(("url", url.lower().rstrip("/")))
        elif key_name == "kind_name":
            kind = resource.get("kind")
            name = resource.get("name")
            if kind and name:
                keys.append(("kind_name", f"{kind}::{_slug(name)}"))
    return keys


def _normalize_agent_resource(resource: dict[str, Any], paper_id: str, source_label: str) -> dict[str, Any]:
    normalized = deepcopy(resource)
    normalized["resource_id"] = _resource_id(normalized)
    normalized.setdefault("kind", "resource")
    normalized.setdefault("name", normalized["resource_id"].split("::", 1)[-1])
    normalized.setdefault("description", "")
    normalized.setdefault("domain", [])
    normalized.setdefault("access", {})
    if not isinstance(normalized["access"], dict):
        normalized["access"] = {"url": str(normalized["access"])}
    normalized["access"].setdefault("url", "")
    normalized["access"].setdefault("access_type", "unknown")
    normalized["access"].setdefault("license", "")
    normalized["access"].setdefault("size", "")
    normalized.setdefault("agent_callable", {})
    normalized["agent_callable"].setdefault("skill_candidate", False)
    normalized["agent_callable"].setdefault("skill_wrapped", False)
    normalized["agent_callable"].setdefault("callable_interface", None)
    normalized["agent_callable"].setdefault("required_environment", [])
    normalized["agent_callable"].setdefault("estimated_wrapping_difficulty", "unknown")
    normalized.setdefault("availability_check", {})
    normalized["availability_check"].setdefault("status", "unknown")
    normalized["availability_check"].setdefault("checked_at", "")
    normalized["availability_check"].setdefault("checked_by", "agent")
    normalized["availability_check"].setdefault("notes", "")
    normalized["availability_check"].setdefault("files", [])
    normalized["availability_check"].setdefault("documentation", "")
    normalized["availability_check"].setdefault("input_format", "")
    normalized["availability_check"].setdefault("output_format", "")
    normalized["availability_check"].setdefault("evaluation_metrics", [])
    normalized.setdefault("reverse_index", {})
    normalized["reverse_index"].setdefault("introduced_by", "")
    normalized["reverse_index"].setdefault("used_by", [])
    normalized["reverse_index"].setdefault("evaluated_by", [])
    normalized["reverse_index"].setdefault("extended_by", [])
    normalized.setdefault("provenance", {})
    normalized["provenance"].setdefault("extracted_from", [paper_id])
    normalized["provenance"].setdefault("extraction_confidence", "medium")
    normalized["provenance"].setdefault("last_checked", "")
    sources = normalized.setdefault("sources", [])
    if isinstance(sources, list) and source_label not in sources:
        sources.append(source_label)
    return normalized


def _merge_resource_body(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    prefer_agent_fields: set[str],
    list_fields: set[str],
) -> dict[str, Any]:
    merged = deepcopy(existing)
    for field, value in incoming.items():
        if field in list_fields:
            current = merged.get(field, [])
            if not isinstance(current, list):
                current = [current]
            incoming_values = value if isinstance(value, list) else [value]
            for item in incoming_values:
                if item not in current:
                    current.append(item)
            merged[field] = current
        elif field in prefer_agent_fields:
            if value not in (None, "", [], {}):
                if isinstance(value, dict) and isinstance(merged.get(field), dict):
                    nested = deepcopy(merged[field])
                    nested.update(value)
                    merged[field] = nested
                else:
                    merged[field] = deepcopy(value)
        elif field not in merged or merged[field] in (None, "", [], {}):
            merged[field] = deepcopy(value)
    return merged


def _agent_resource_judgments(judgment: dict[str, Any], paths: list[str]) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for path in paths:
        value = _get(judgment, path)
        if isinstance(value, list):
            resources.extend(item for item in value if isinstance(item, dict))
    return resources


def merge_resource_judgments(
    resource_records: Any,
    judgment: dict[str, Any],
    paper_id: str,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resource_config = config.get("agent_judgment", {}).get("resource_merge", {})
    judgment_paths = config.get("agent_judgment", {}).get("resource_judgment_paths", [])
    dedupe_keys = resource_config.get("dedupe_keys", ["resource_id", "url", "kind_name"])
    prefer_agent_fields = set(resource_config.get("prefer_agent_fields", []))
    list_fields = set(resource_config.get("list_fields", []))
    source_label = resource_config.get("agent_source_label", "agent_judgment")

    records = resource_records if isinstance(resource_records, list) else []
    bodies = [_record_body(record) for record in records if isinstance(record, dict)]
    index: dict[tuple[str, str], int] = {}
    merged_bodies: list[dict[str, Any]] = []
    notes: list[str] = []

    for body in bodies:
        body = deepcopy(body)
        body["resource_id"] = _resource_id(body)
        idx = len(merged_bodies)
        merged_bodies.append(body)
        for key in _resource_keys(body, dedupe_keys):
            index[key] = idx

    for agent_resource in _agent_resource_judgments(judgment, judgment_paths):
        normalized = _normalize_agent_resource(agent_resource, paper_id, source_label)
        keys = _resource_keys(normalized, dedupe_keys)
        match_idx = next((index[key] for key in keys if key in index), None)
        if match_idx is None:
            match_idx = len(merged_bodies)
            merged_bodies.append(normalized)
            notes.append(f"added resource {normalized['resource_id']}")
        else:
            merged_bodies[match_idx] = _merge_resource_body(
                merged_bodies[match_idx],
                normalized,
                prefer_agent_fields,
                list_fields,
            )
            notes.append(f"merged resource {normalized['resource_id']} into {merged_bodies[match_idx]['resource_id']}")
        for key in _resource_keys(merged_bodies[match_idx], dedupe_keys):
            index[key] = match_idx

    wrapped = [{"resource_record": body} for body in merged_bodies]
    return wrapped, {
        "merged": notes,
        "count": len(wrapped),
        "dedupe_keys": dedupe_keys,
        "judgment_paths": judgment_paths,
    }


def _merge_citation_semantics(base: dict[str, Any], judgment: dict[str, Any], semantic_fields: set[str]) -> list[str]:
    notes: list[str] = []
    judged_cites = _get(judgment, "paper_record.atomic_extracts.citation_context.cite") or []
    if not judged_cites:
        return notes
    base_cites = _get(base, "paper_record.atomic_extracts.citation_context.cite") or []
    by_key = {item.get("cite_key"): item for item in base_cites if isinstance(item, dict) and item.get("cite_key")}
    for judged in judged_cites:
        if not isinstance(judged, dict):
            notes.append("ignored non-mapping citation judgment")
            continue
        key = judged.get("cite_key")
        if not key or key not in by_key:
            notes.append(f"ignored citation judgment without matching cite_key: {key}")
            continue
        target = by_key[key]
        for field in semantic_fields:
            if field in judged:
                target[field] = judged[field]
        notes.append(f"merged citation semantics for cite_key={key}")
    return notes


def _figure_key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("figure_id") or ""), str(item.get("label") or "")


def _merge_figure_semantics(base: dict[str, Any], judgment: dict[str, Any], semantic_fields: set[str]) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    rejected: list[str] = []
    judged_figures = _get(judgment, "paper_record.content_units.figures") or []
    if not judged_figures:
        return notes, rejected
    base_figures = _get(base, "paper_record.content_units.figures") or []
    by_id = {item.get("figure_id"): item for item in base_figures if isinstance(item, dict) and item.get("figure_id")}
    by_label = {item.get("label"): item for item in base_figures if isinstance(item, dict) and item.get("label")}
    mechanical_fields = {"caption", "files", "caption_source", "label", "figure_id", "agent_interpretation_required"}
    for judged in judged_figures:
        if not isinstance(judged, dict):
            rejected.append("paper_record.content_units.figures[]")
            continue
        figure_id, label = _figure_key(judged)
        target = by_id.get(figure_id) if figure_id else None
        if target is None and label:
            target = by_label.get(label)
        if target is None:
            rejected.append(f"paper_record.content_units.figures[{figure_id or label or '?'}]")
            notes.append(f"ignored figure judgment without matching figure_id/label: {figure_id or label}")
            continue
        for field in judged:
            if field in mechanical_fields:
                if judged.get(field) != target.get(field):
                    rejected.append(f"paper_record.content_units.figures[{figure_id or label}].{field}")
                continue
            if field in semantic_fields:
                target[field] = deepcopy(judged[field])
            else:
                rejected.append(f"paper_record.content_units.figures[{figure_id or label}].{field}")
        notes.append(f"merged figure semantics for {figure_id or label}")
    return notes, rejected


def merge_agent_judgment(
    base: dict[str, Any],
    judgment: dict[str, Any],
    config: dict[str, Any] | None = None,
    resource_records: Any | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    config = config or load_config()
    judgment_config = config.get("agent_judgment", {})
    allowed_replace_paths = set(judgment_config.get("allowed_replace_paths", []))
    citation_semantic_fields = set(judgment_config.get("citation_semantic_fields", []))
    figure_semantic_fields = set(judgment_config.get("figure_semantic_fields", []))
    resource_judgment_paths = set(judgment_config.get("resource_judgment_paths", []))
    merged = deepcopy(base)
    notes: list[str] = []
    rejected: list[str] = []

    def walk(prefix: str, value: Any) -> None:
        if prefix in resource_judgment_paths:
            return
        if prefix == "paper_record.content_units.figures":
            return
        if prefix == "paper_record.atomic_extracts.citation_context.cite":
            return
        if prefix in allowed_replace_paths:
            _set(merged, prefix, value)
            notes.append(f"replaced {prefix}")
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_prefix = f"{prefix}.{key}" if prefix else key
                walk(child_prefix, child)
        elif prefix:
            rejected.append(prefix)

    walk("", judgment)
    notes.extend(_merge_citation_semantics(merged, judgment, citation_semantic_fields))
    figure_notes, figure_rejected = _merge_figure_semantics(merged, judgment, figure_semantic_fields)
    notes.extend(figure_notes)
    rejected.extend(figure_rejected)
    resource_report = None
    merged_resources = None
    if resource_records is not None:
        paper_id = _get(merged, "paper_record.paper_id") or ""
        merged_resources, resource_report = merge_resource_judgments(resource_records, judgment, paper_id, config)
    merged.setdefault("_agent_merge_report", {})
    merged["_agent_merge_report"] = {
        "merged": notes,
        "rejected": rejected,
        "allowed_replace_paths": sorted(allowed_replace_paths),
        "resources": resource_report,
    }
    return merged, merged_resources


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge agent semantic judgment into paper_record YAML")
    parser.add_argument("--base", required=True, type=Path, help="mechanically generated paper_record.yml")
    parser.add_argument("--resource-records", type=Path, default=None, help="mechanically generated resource_records.yml")
    parser.add_argument("--judgment", required=True, type=Path, help="agent semantic judgment YAML")
    parser.add_argument("--output", required=True, type=Path, help="merged YAML output path")
    parser.add_argument("--resource-output", type=Path, default=None, help="merged resource_records YAML output path")
    parser.add_argument("--report-json", type=Path, default=None, help="optional merge report JSON path")
    parser.add_argument("--edit-hints-json", type=Path, default=None, help="optional agent edit hints JSON path")
    args = parser.parse_args()

    base = _load_yaml(args.base)
    judgment = _load_yaml(args.judgment)
    resource_records = _load_yaml(args.resource_records) if args.resource_records else None
    merged, merged_resources = merge_agent_judgment(base, judgment, resource_records=resource_records)
    report = merged.pop("_agent_merge_report")
    _write_yaml(args.output, merged)
    if args.resource_output and merged_resources is not None:
        _write_yaml(args.resource_output, merged_resources)
    lint_report = lint_file(args.output)
    resource_lint_reports = []
    if args.resource_output and merged_resources is not None:
        for idx, record in enumerate(merged_resources):
            tmp_path = args.resource_output.parent / f".resource_record_{idx}.lint.yml"
            _write_yaml(tmp_path, record)
            resource_lint_reports.append(lint_file(tmp_path))
            tmp_path.unlink(missing_ok=True)
    resource_lint_ok = all(item["ok"] for item in resource_lint_reports)
    edit_hints = {
        "ok": lint_report["ok"] and resource_lint_ok,
        "files": {
            "paper_record": str(args.output),
            "resource_records": str(args.resource_output) if args.resource_output else "",
            "judgment": str(args.judgment),
        },
        "issues": lint_report.get("issues", []),
        "resource_issues": [
            {
                "resource_index": idx,
                "file": report.get("file", ""),
                "issues": report.get("issues", []),
            }
            for idx, report in enumerate(resource_lint_reports)
            if not report.get("ok")
        ],
        "merge_rejected": report.get("rejected", []),
        "merge_notes": report.get("merged", []),
        "resource_merge": report.get("resources"),
    }
    final_report = {
        "ok": lint_report["ok"] and resource_lint_ok,
        "merge": report,
        "lint": lint_report,
        "resource_lint": resource_lint_reports,
        "agent_edit_hints": edit_hints,
    }
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.edit_hints_json:
        args.edit_hints_json.parent.mkdir(parents=True, exist_ok=True)
        args.edit_hints_json.write_text(json.dumps(edit_hints, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(final_report, ensure_ascii=False, indent=2))
    if not final_report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
