#!/usr/bin/env python3
"""
机械抽取论文中的显式资源链接候选。

功能:
    - 抽取 LaTeX 源码中显式写出的 URL 链接。
    - 所有机械链接候选统一标记为 kind=resource。
    - 不再用正文正则猜 dataset / benchmark / model 名称；这些资源由 agent
      阅读论文后通过 resource_judgments 补充 kind、description 和用途判断。

边界:
    不访问链接，不验证资源可用性，不做跨论文资源消歧。

扩展规则:
    URL 抽取正则来自 scripts/config/layer4_config.yml 的 resources 段。

直接调用:
    不建议直接运行；请通过 parse_one.py 或 parse_batch.py 使用。
"""

from __future__ import annotations

import re
from typing import Any

from common import make_id, strip_tex_comments
from script_config import load_config


def _resource_config() -> dict[str, Any]:
    return load_config().get("resources", {})


def extract_resource_mentions(package: dict[str, Any], structure: dict[str, Any]) -> dict[str, Any]:
    text = strip_tex_comments(package.get("assembled_tex") or package.get("main_tex") or "")
    resources: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    resource_config = _resource_config()
    url_re = re.compile(resource_config.get("url_pattern", r"(?:https?://|www\.)[^\s{}\\]+"), re.IGNORECASE)

    for raw_url in url_re.findall(text):
        url = raw_url.rstrip(").,;]")
        kind = resource_config.get("default_url_kind", "resource")
        name = url
        key = (kind, url)
        if key in seen:
            continue
        seen.add(key)
        resources.append(
            {
                "resource_id": make_id(kind if kind != "resource" else "resource", name),
                "kind": kind,
                "name": name,
                "url": url,
                "description": "",
                "source": "url",
            }
        )

    return {"resources": resources}
