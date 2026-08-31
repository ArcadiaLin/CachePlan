#!/usr/bin/env python3
"""
解析单个 arXiv LaTeX 包，生成论文与资源解析草稿。

用法:
    uv run python "$SCRIPTS_DIR/parse_one.py" \
      --input <arxiv-source.tar.gz> \
      --output-dir <run-output-dir> \
      --metadata online

    uv run python "$SCRIPTS_DIR/parse_one.py" \
      --input <arxiv-source.tar.gz> \
      --output-dir <run-output-dir> \
      --metadata offline

输出目录:
    <run-output-dir>/<arxiv_id>/

输出文件:
    paper_record.yml       机械生成的 YAML 草稿
    resource_records.yml   资源候选 YAML
    structure.json         LaTeX 结构抽取结果
    figures/               从 LaTeX 包复制出的图片资产
    figure_manifest.json   图片、caption source 和抽取状态清单
    citations.json         引用条目和上下文
    resources.json         资源候选
    lint_report.json       YAML 校验结果
    run_report.json        单篇运行摘要
    agent_edit_hints.json  面向 agent edit 工具的 path/line/message/suggested_fix 汇总

边界:
    不做 claim/contribution/limitation/future_work 或图片视觉理解等语义判断；
    这些字段由 agent 阅读论文后通过 apply_agent_judgment.py 合并。
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

from arxiv_metadata_client import fetch_arxiv_metadata
from bib_reference_resolver import resolve_references
from citation_context_locator import locate_citation_contexts
from common import write_json
from figure_asset_extractor import extract_figure_assets
from latex_structure_parser import parse_latex_structure
from latex_unpack import load_latex_package
from resource_mention_extractor import extract_resource_mentions
from supplement_runner import run_supplements
from yaml_emitter import build_paper_record, build_resource_records, write_yaml
from yaml_linter import lint_file


def parse_package(
    input_path: Path,
    output_dir: Path,
    metadata_mode: str = "online",
    metadata_timeout: float = 8.0,
    metadata_delay: float = 1.0,
    supplements: str = "auto",
) -> dict[str, Any]:
    package = load_latex_package(str(input_path))
    paper_dir = output_dir / package["arxiv_id"]
    paper_dir.mkdir(parents=True, exist_ok=True)

    metadata: dict[str, Any] = {"ok": False, "arxiv_id": package["arxiv_id"]}
    if metadata_mode == "online":
        metadata = fetch_arxiv_metadata(package["arxiv_id"], timeout=metadata_timeout, delay=metadata_delay)
        if not metadata.get("ok"):
            metadata = {"ok": False, "arxiv_id": package["arxiv_id"], "error": metadata.get("error", "")}
    elif metadata_mode == "offline":
        metadata = {"ok": False, "arxiv_id": package["arxiv_id"]}
    else:
        raise ValueError("--metadata must be online or offline")

    structure = parse_latex_structure(package)
    figure_assets = extract_figure_assets(package, paper_dir)
    structure["figures"] = figure_assets["figures"]
    references = resolve_references(package)
    citations = locate_citation_contexts(package, references)
    resources = extract_resource_mentions(package, structure)
    context = {
        "package": package,
        "metadata": metadata,
        "structure": structure,
        "references": references,
        "citations": citations,
        "resources": resources,
        "notes": [],
    }
    context, supplement_report = run_supplements(context, supplements)
    metadata = context.get("metadata", metadata)
    structure = context.get("structure", structure)
    references = context.get("references", references)
    citations = context.get("citations", citations)
    resources = context.get("resources", resources)
    figure_assets["figures"] = structure.get("figures", figure_assets["figures"])
    figure_assets["manifest"] = structure.get("figures", figure_assets["manifest"])

    paper_record = build_paper_record(
        arxiv_id=package["arxiv_id"],
        metadata=metadata if metadata.get("ok") else {"arxiv_id": package["arxiv_id"]},
        structure=structure,
        citations=citations,
        resources=resources,
    )
    resource_records = build_resource_records(arxiv_id=package["arxiv_id"], resources=resources)

    write_json(
        paper_dir / "structure.json",
        {
            "main_tex_name": package.get("main_tex_name"),
            "included_files": package.get("included_files", []),
            "title": structure.get("title", ""),
            "authors": structure.get("authors", []),
            "abstract": structure.get("abstract", ""),
            "section_outline": structure.get("section_outline", []),
            "figures": structure.get("figures", []),
            "tables": structure.get("tables", []),
        },
    )
    write_json(paper_dir / "figure_manifest.json", figure_assets.get("manifest", []))
    write_json(paper_dir / "citations.json", citations)
    write_json(paper_dir / "resources.json", resources)
    write_yaml(paper_dir / "paper_record.yml", paper_record)
    write_yaml(paper_dir / "resource_records.yml", resource_records)

    lint_report = lint_file(paper_dir / "paper_record.yml")
    write_json(paper_dir / "lint_report.json", lint_report)
    agent_edit_hints = {
        "ok": lint_report["ok"] and not any(item.get("error") for item in supplement_report.get("patches", [])),
        "files": {
            "paper_record": str(paper_dir / "paper_record.yml"),
            "resource_records": str(paper_dir / "resource_records.yml"),
            "figure_manifest": str(paper_dir / "figure_manifest.json"),
            "supplement_manifest": str(Path(__file__).resolve().parent / "agent_supplement.d" / "manifest.yml"),
        },
        "issues": lint_report.get("issues", []),
        "supplements": supplement_report,
        "notes": context.get("notes", []),
    }
    write_json(paper_dir / "agent_edit_hints.json", agent_edit_hints)
    run_report = {
        "ok": lint_report["ok"],
        "input": str(input_path),
        "arxiv_id": package["arxiv_id"],
        "output_dir": str(paper_dir),
        "metadata_mode": metadata_mode,
        "metadata_timeout": metadata_timeout,
        "metadata_delay": metadata_delay,
        "supplements": supplements,
        "supplement_report": supplement_report,
        "metadata_ok": bool(metadata.get("ok")),
        "metadata_error": metadata.get("error", ""),
        "main_tex_name": package.get("main_tex_name"),
        "tex_file_count": len(package.get("tex_files", {})),
        "bib_file_count": len(package.get("bib_files", {})),
        "bbl_file_count": len(package.get("bbl_files", {})),
        "reference_count": citations.get("reference_count", 0),
        "citation_count": len(citations.get("cited_references", [])),
        "resource_count": len(resources.get("resources", [])),
        "figure_count": figure_assets.get("figure_count", len(structure.get("figures", []))),
        "figure_asset_count": figure_assets.get("figure_asset_count", 0),
        "missing_figure_asset_count": figure_assets.get("missing_figure_asset_count", 0),
        "figure_manifest": str(paper_dir / "figure_manifest.json"),
        "lint_issue_count": len(lint_report.get("issues", [])),
        "agent_edit_hints": str(paper_dir / "agent_edit_hints.json"),
    }
    write_json(paper_dir / "run_report.json", run_report)
    return run_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse one arXiv LaTeX package into paper/resource artifacts")
    parser.add_argument("--input", required=True, type=Path, help="path to arXiv .tar.gz source package")
    parser.add_argument("--output-dir", default=Path("paper_resource_runs"), type=Path)
    parser.add_argument("--metadata", choices=["online", "offline"], default="online")
    parser.add_argument("--metadata-timeout", type=float, default=8.0)
    parser.add_argument("--metadata-delay", type=float, default=1.0)
    parser.add_argument("--supplements", choices=["auto", "off", "required"], default="auto")
    parser.add_argument("--traceback", action="store_true")
    args = parser.parse_args()
    try:
        report = parse_package(
            args.input,
            args.output_dir,
            args.metadata,
            args.metadata_timeout,
            args.metadata_delay,
            args.supplements,
        )
    except Exception as exc:
        if args.traceback:
            traceback.print_exc()
        print(json.dumps({"ok": False, "input": str(args.input), "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
