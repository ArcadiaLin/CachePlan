#!/usr/bin/env python3
"""
运行 agent_supplement.d 中登记的 repair/supplement 脚本。

用法:
    通常由 parse_one.py 调用：

    uv run python "$SCRIPTS_DIR/parse_one.py" \
      --input <arxiv-source.tar.gz> \
      --output-dir <run-output-dir> \
      --supplements auto

目录:
    scripts/agent_supplement.d/

manifest:
    enabled: true
    patches:
      - 10_example_patch.py

补丁接口:
    applies(context: dict) -> bool
    apply(context: dict) -> dict

输出:
    返回 supplement_report，包含每个补丁的 applied/skipped/error 状态，供 run_report.json
    和 agent_edit_hints 使用。
"""

from __future__ import annotations

import importlib.util
import traceback
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


SUPPLEMENT_DIR = Path(__file__).resolve().parent / "agent_supplement.d"
MANIFEST = SUPPLEMENT_DIR / "manifest.yml"


def _load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    if not path.exists():
        return {"enabled": False, "patches": []}
    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"supplement manifest must be a mapping: {path}")
    data.setdefault("enabled", True)
    data.setdefault("patches", [])
    return data


def _load_patch(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load patch: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_supplements(context: dict[str, Any], mode: str = "auto") -> tuple[dict[str, Any], dict[str, Any]]:
    if mode == "off":
        return context, {"enabled": False, "mode": mode, "patches": []}
    manifest = _load_manifest()
    if not manifest.get("enabled", True):
        return context, {"enabled": False, "mode": mode, "patches": []}

    report: dict[str, Any] = {"enabled": True, "mode": mode, "patches": []}
    for patch_name in manifest.get("patches", []):
        patch_path = SUPPLEMENT_DIR / patch_name
        item = {"patch": patch_name, "path": str(patch_path), "applied": False, "skipped": False, "error": ""}
        try:
            module = _load_patch(patch_path)
            if not hasattr(module, "applies") or not hasattr(module, "apply"):
                raise AttributeError("patch must define applies(context) and apply(context)")
            if not module.applies(context):
                item["skipped"] = True
            else:
                next_context = module.apply(context)
                if next_context is not None:
                    context = next_context
                item["applied"] = True
        except Exception as exc:
            item["error"] = str(exc)
            item["traceback"] = traceback.format_exc()
            if mode == "required":
                report["patches"].append(item)
                raise
        report["patches"].append(item)
    return context, report
