#!/usr/bin/env python3
"""
从 arXiv API 获取基础论文元数据。

功能:
    根据 arXiv id 获取 title、authors、abstract、year、doi、primary category、URL。

边界:
    只补基础元数据；不获取引用网络，不做资源验证。网络失败时返回 ok=false，
    parse_one.py 会继续使用本地 LaTeX 解析结果。

直接调用:
    不建议直接运行；请通过 parse_one.py 或 parse_batch.py 使用。
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import requests

from script_config import load_config


def fetch_arxiv_metadata(arxiv_id: str, timeout: float = 20.0, delay: float = 1.0) -> dict[str, Any]:
    if delay > 0:
        time.sleep(delay)
    try:
        api_url = load_config().get("defaults", {}).get("arxiv_api_url", "https://export.arxiv.org/api/query")
        response = requests.get(api_url, params={"id_list": arxiv_id}, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc), "arxiv_id": arxiv_id}

    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        return {"ok": False, "error": f"invalid xml: {exc}", "arxiv_id": arxiv_id}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return {"ok": False, "error": "no arxiv entry", "arxiv_id": arxiv_id}

    def text(path: str) -> str:
        node = entry.find(path, ns)
        return re.sub(r"\s+", " ", node.text or "").strip() if node is not None else ""

    authors = [
        re.sub(r"\s+", " ", author.findtext("atom:name", default="", namespaces=ns)).strip()
        for author in entry.findall("atom:author", ns)
    ]
    doi = text("arxiv:doi")
    published = text("atom:published")
    category = entry.find("arxiv:primary_category", ns)
    return {
        "ok": True,
        "arxiv_id": arxiv_id,
        "title": text("atom:title"),
        "authors": [author for author in authors if author],
        "abstract": text("atom:summary"),
        "year": int(published[:4]) if published[:4].isdigit() else None,
        "published": published,
        "doi": doi,
        "primary_category": category.attrib.get("term", "") if category is not None else "",
        "url": f"https://arxiv.org/abs/{arxiv_id}",
    }
