#!/usr/bin/env python3
"""
将解析结果写入论文与资源 YAML 草稿。

功能:
    - 按当前 YAML 结构生成 paper_record。
    - 写入增强后的 figure 记录，包括图片路径、caption source 和 agent
      可补充的 description / agent_review 占位。
    - 生成 resource_records.yml，记录机械识别到的资源候选。
    - resources_introduced/resources_used 保持为空，等待 agent 依据论文语义填写。
    - resource reverse_index 保持空默认值，不把显式 URL 自动判为论文引入资源。
    - 保留空字段和 unknown，避免机械脚本编造 agent 才能判断的语义字段。

直接调用:
    不建议直接运行；请通过 parse_one.py 或 parse_batch.py 使用。

配置:
    默认值和输出截断上限来自 scripts/config/*.yml。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from script_config import load_config


def _defaults(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("defaults", {})


def _emitter_config(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("emitter", {})


def build_paper_record(
    *,
    arxiv_id: str,
    metadata: dict[str, Any],
    structure: dict[str, Any],
    citations: dict[str, Any],
    resources: dict[str, Any],
) -> dict[str, Any]:
    config = load_config()
    defaults = _defaults(config)
    unknown = defaults.get("unknown_value", "unknown")
    max_citations = int(defaults.get("max_citation_contexts_in_yaml", 200))
    paper_id = f"paper::{arxiv_id}"
    title = metadata.get("title") or structure.get("title") or ""
    authors = metadata.get("authors") or structure.get("authors") or []
    year = metadata.get("year") or unknown
    abstract = metadata.get("abstract") or structure.get("abstract") or ""
    cite_items = []
    for citation in citations.get("cited_references", [])[:max_citations]:
        ref = citation.get("reference", {})
        cite_items.append(
            {
                "cited_paper_id": citation.get("cited_paper_id", ""),
                "cite_key": citation.get("cite_key", ""),
                "reference_title": ref.get("title", ""),
                "context": citation.get("context", ""),
                "citation_function": "",
                "evidence": {
                    "section": citation.get("section", ""),
                    "quote": citation.get("context", ""),
                },
            }
        )

    if not cite_items:
        cite_items = []

    return {
        "paper_record": {
            "paper_id": paper_id,
            "source_type": "paper",
            "metadata": {
                "title": title,
                "authors": authors,
                "year": year,
                "venue": f"arXiv {arxiv_id}" if arxiv_id else "",
                "arxiv_id": arxiv_id,
                "doi": metadata.get("doi", ""),
                "url": metadata.get("url") or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""),
            },
            "content_units": {
                "abstract": abstract,
                "section_outline": structure.get("section_outline", []),
                "has_appendix": bool(structure.get("has_appendix", False)),
                "has_supplenmentart_material": bool(structure.get("has_supplementary_material", False)),
                "figures": structure.get("figures", []),
                "tables": structure.get("tables", []),
            },
            "atomic_extracts": {
                "intent": {
                    "paper_type": unknown,
                    "research_problem": "",
                    "target_domain": [metadata.get("primary_category", "")] if metadata.get("primary_category") else [],
                },
                "contributions": [],
                "claims": [],
                "experiments": [
                    {
                        "experiment_id": "exp::1",
                        "task": "",
                        "dataset_ids": [],
                        "benchmark_ids": [],
                        "metrics": [],
                        "baselines": [],
                        "hyperparameters": {
                            "status": defaults.get("missing_hyperparameters_status", "missing"),
                            "values": {},
                        },
                        "evidence": {"section": ""},
                    }
                ],
                "limitations": [],
                "future_work": [],
                "citation_context": {"cite": cite_items, "cited_by": []},
            },
        },
        "resources_introduced": [],
        "resources_used": [],
        "cites": [
            item.get("cited_paper_id")
            for item in cite_items
            if item.get("cited_paper_id")
        ],
        "cited_by": [],
        "source paper": "",
        "comparsion": "",
    }


def build_resource_records(
    *,
    arxiv_id: str,
    resources: dict[str, Any],
) -> list[dict[str, Any]]:
    config = load_config()
    emitter = _emitter_config(config)
    records = []
    for item in resources.get("resources", []):
        kind = item.get("kind") or "resource"
        records.append(
            {
                "resource_record": {
                    "resource_id": item.get("resource_id", ""),
                    "kind": kind,
                    "name": item.get("name", ""),
                    "description": item.get("description", ""),
                    "domain": [],
                    "access": {
                        "url": item.get("url", ""),
                        "access_type": emitter.get("default_resource_access_type", "unknown"),
                        "license": "",
                        "size": "",
                    },
                    "agent_callable": {
                        "skill_candidate": False,
                        "skill_wrapped": False,
                        "callable_interface": None,
                        "required_environment": [],
                        "estimated_wrapping_difficulty": emitter.get("default_wrapping_difficulty", "unknown"),
                    },
                    "availability_check": {
                        "status": emitter.get("default_availability_status", "unknown"),
                        "checked_at": "",
                        "checked_by": emitter.get("checked_by", "agent"),
                        "notes": "",
                        "files": [],
                        "documentation": "",
                        "input_format": "",
                        "output_format": "",
                        "evaluation_metrics": [],
                    },
                    "reverse_index": {
                        "introduced_by": "",
                        "used_by": [],
                        "evaluated_by": [],
                        "extended_by": [],
                    },
                    "provenance": {
                        "extracted_from": [f"paper::{arxiv_id}"],
                        "extraction_confidence": emitter.get("default_extraction_confidence", "medium"),
                        "last_checked": "",
                    },
                }
            }
        )
    return records


def write_yaml(path: Path, data: Any) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 120
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle)
