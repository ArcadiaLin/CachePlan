#!/usr/bin/env python3
"""
校验论文与资源 YAML 输出格式。

用法:
    uv run python "$SCRIPTS_DIR/yaml_linter.py" \
      <run-output-dir>/2604.28123/paper_record.yml

    uv run python "$SCRIPTS_DIR/yaml_linter.py" \
      <run-output-dir>/2604.28123/paper_record.yml --json

输出:
    - OK: 文件路径
    - 或 path + line + message + suggested_fix 的错误说明

说明:
    使用 ruamel.yaml 保留行号，帮助 agent 在格式校验后用 edit 工具定位修改。
    枚举值、必需字段、claim/citation/figure 阶段规则和字段类型来自
    scripts/config/*.yml。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from script_config import load_config


TYPE_MAP = {
    "str": str,
    "list": list,
    "dict": dict,
    "bool": bool,
    "int": int,
    "float": float,
}


def _line_for(container: Any, key: Any | None = None) -> int | None:
    try:
        if isinstance(container, CommentedMap) and key is not None:
            return container.lc.key(key)[0] + 1
        if hasattr(container, "lc"):
            return container.lc.line + 1
    except Exception:
        return None
    return None


def _issue(path: str, line: int | None, message: str, suggested_fix: str) -> dict[str, Any]:
    return {
        "path": path,
        "line": line,
        "message": message,
        "suggested_fix": suggested_fix,
    }


def _get(root: Any, path: str) -> Any:
    current = root
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _container_for(root: Any, path: str) -> tuple[Any, str] | tuple[None, str]:
    parts = path.split(".")
    current = root
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return None, parts[-1]
        current = current.get(part)
    return current, parts[-1]


def _require(root: Any, path: str, typ: type | tuple[type, ...], issues: list[dict[str, Any]]) -> None:
    container, key = _container_for(root, path)
    value = _get(root, path)
    if value is None:
        issues.append(_issue(path, _line_for(container, key), "missing required field", f"add `{key}`"))
        return
    if not isinstance(value, typ):
        issues.append(
            _issue(
                path,
                _line_for(container, key),
                f"expected {getattr(typ, '__name__', typ)}, got {type(value).__name__}",
                "keep the template field but use the expected type",
            )
        )


def _enum(root: Any, path: str, allowed: set[str], issues: list[dict[str, Any]]) -> None:
    container, key = _container_for(root, path)
    value = _get(root, path)
    if value is None or value == "":
        return
    if value not in allowed:
        issues.append(
            _issue(path, _line_for(container, key), f"invalid enum value `{value}`", f"use one of: {sorted(allowed)}")
        )


def _configured_required_fields(config: dict[str, Any], record_type: str) -> list[tuple[str, type]]:
    fields = config.get("lint", {}).get(f"{record_type}_required_fields", {})
    result: list[tuple[str, type]] = []
    for path, type_name in fields.items():
        if type_name not in TYPE_MAP:
            raise ValueError(f"unknown lint type `{type_name}` for {path}")
        result.append((path, TYPE_MAP[type_name]))
    return result


def _configured_enum_fields(config: dict[str, Any]) -> dict[str, set[str]]:
    enum_values = config.get("enums", {})
    enum_fields = config.get("lint", {}).get("enum_fields", {})
    result: dict[str, set[str]] = {}
    for path, enum_name in enum_fields.items():
        values = enum_values.get(enum_name)
        if not isinstance(values, list):
            raise ValueError(f"unknown enum `{enum_name}` for {path}")
        result[path] = set(values)
    return result


def lint_data(data: Any, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    issues: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return [_issue("$", 1, "YAML root must be a mapping", "make the file start with paper_record or resource_record")]

    if "paper_record" in data:
        for path, typ in _configured_required_fields(config, "paper"):
            _require(data, path, typ, issues)
        for path, allowed in _configured_enum_fields(config).items():
            if path.startswith("paper_record."):
                _enum(data, path, allowed, issues)
        hyperparameter_statuses = set(config.get("enums", {}).get("hyperparameter_status", []))
        claims = _get(data, "paper_record.atomic_extracts.claims") or []
        if isinstance(claims, list):
            if len(claims) > 2:
                issues.append(
                    _issue(
                        "paper_record.atomic_extracts.claims",
                        _line_for(_get(data, "paper_record.atomic_extracts"), "claims"),
                        "claims must contain at most 2 abstract-derived items",
                        "keep only 1-2 core claims from the abstract",
                    )
                )
            claim_types = set(config.get("enums", {}).get("claim_type", []))
            for idx, claim in enumerate(claims):
                if not isinstance(claim, dict):
                    issues.append(_issue(f"paper_record.atomic_extracts.claims[{idx}]", None, "claim must be mapping", "use claim object"))
                    continue
                if "evidence" in claim:
                    issues.append(
                        _issue(
                            f"paper_record.atomic_extracts.claims[{idx}].evidence",
                            _line_for(claim, "evidence"),
                            "claims are abstract-derived and must not carry evidence",
                            "remove evidence from claim",
                        )
                    )
                claim_type = claim.get("claim_type", "")
                if claim_type not in claim_types:
                    issues.append(
                        _issue(
                            f"paper_record.atomic_extracts.claims[{idx}].claim_type",
                            _line_for(claim, "claim_type"),
                            f"invalid enum value `{claim_type}`",
                            f"use one of: {sorted(claim_types)}",
                        )
                    )
        citations = _get(data, "paper_record.atomic_extracts.citation_context.cite") or []
        for idx, citation in enumerate(citations):
            if isinstance(citation, dict) and "local_claim_id" in citation:
                issues.append(
                    _issue(
                        f"paper_record.atomic_extracts.citation_context.cite[{idx}].local_claim_id",
                        _line_for(citation, "local_claim_id"),
                        "citation records must not bind local claims in Layer 4",
                        "remove local_claim_id",
                    )
                )
        figure_statuses = set(config.get("enums", {}).get("figure_review_status", []))
        figures = _get(data, "paper_record.content_units.figures") or []
        for idx, figure in enumerate(figures):
            if not isinstance(figure, dict):
                issues.append(_issue(f"paper_record.content_units.figures[{idx}]", None, "figure must be mapping", "use figure object"))
                continue
            for key, typ in {
                "figure_id": str,
                "label": str,
                "caption": str,
                "files": list,
                "caption_source": dict,
                "description": str,
                "agent_review": dict,
            }.items():
                if key not in figure:
                    issues.append(_issue(f"paper_record.content_units.figures[{idx}].{key}", _line_for(figure, key), "missing figure field", f"add `{key}`"))
                elif not isinstance(figure[key], typ):
                    issues.append(_issue(f"paper_record.content_units.figures[{idx}].{key}", _line_for(figure, key), f"expected {typ.__name__}, got {type(figure[key]).__name__}", "keep the expected figure field type"))
            status = ((figure.get("agent_review") or {}).get("status"))
            if status not in figure_statuses:
                issues.append(
                    _issue(
                        f"paper_record.content_units.figures[{idx}].agent_review.status",
                        _line_for(figure.get("agent_review"), "status"),
                        f"invalid enum value `{status}`",
                        f"use one of: {sorted(figure_statuses)}",
                    )
                )
        for idx, experiment in enumerate(_get(data, "paper_record.atomic_extracts.experiments") or []):
            if not isinstance(experiment, dict):
                issues.append(_issue(f"paper_record.atomic_extracts.experiments[{idx}]", None, "experiment must be mapping", "use experiment object"))
                continue
            status = ((experiment.get("hyperparameters") or {}).get("status"))
            if status not in hyperparameter_statuses:
                issues.append(
                    _issue(
                        f"paper_record.atomic_extracts.experiments[{idx}].hyperparameters.status",
                        _line_for(experiment.get("hyperparameters"), "status"),
                        f"invalid enum value `{status}`",
                        f"use one of: {sorted(hyperparameter_statuses)}",
                    )
                )
    elif "resource_record" in data:
        for path, typ in _configured_required_fields(config, "resource"):
            _require(data, path, typ, issues)
        for path, allowed in _configured_enum_fields(config).items():
            if path.startswith("resource_record."):
                _enum(data, path, allowed, issues)
    else:
        issues.append(_issue("$", 1, "missing paper_record or resource_record", "emit one of the known paper/resource records"))
    return issues


def lint_file(path: Path) -> dict[str, Any]:
    yaml = YAML()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle)
    except Exception as exc:
        mark = getattr(exc, "problem_mark", None)
        return {
            "ok": False,
            "file": str(path),
            "issues": [
                _issue(
                    "$",
                    mark.line + 1 if mark else None,
                    f"YAML parse error: {exc}",
                    "fix YAML syntax at the reported line",
                )
            ],
        }
    issues = lint_data(data)
    return {"ok": not issues, "file": str(path), "issues": issues}


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint paper/resource YAML output")
    parser.add_argument("yaml_file", type=Path)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args()
    report = lint_file(args.yaml_file)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if report["ok"]:
        print(f"OK: {args.yaml_file}")
    else:
        for issue in report["issues"]:
            line = issue["line"] if issue["line"] is not None else "?"
            print(f"{issue['path']} line {line}: {issue['message']} ({issue['suggested_fix']})")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
