#!/usr/bin/env python3
"""
加载 LaTeX 论文与资源抽取脚本配置。

默认配置:
    scripts/config/*.yml

用途:
    把枚举、模板默认值、agent 合并白名单、LaTeX 模板识别规则、资源抽取规则
    从脚本逻辑中分离出来，方便后续扩展。

直接调用:
    不建议直接运行；由其他脚本 import。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


CONFIG_PATH = Path(__file__).resolve().parent / "config" / "layer4_config.yml"


@lru_cache(maxsize=1)
def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else CONFIG_PATH
    yaml = YAML(typ="safe")
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"config root must be a mapping: {config_path}")
    return data


def get_config_section(name: str) -> dict[str, Any]:
    section = load_config().get(name, {})
    if not isinstance(section, dict):
        raise ValueError(f"config section must be a mapping: {name}")
    return section
