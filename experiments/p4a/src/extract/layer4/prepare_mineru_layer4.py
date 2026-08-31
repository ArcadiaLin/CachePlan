#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4/prepare_mineru_layer4.py --paper-id <paper_id> --references-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/<paper_id>/verified_or_repaired.jsonl --cite-contexts-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/<paper_id>/cite_contexts.jsonl
"""Prepare a controlled MinerU Layer 4 input bundle and templates for one paper."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    DEFAULT_CITE_CONTEXTS_JSONL,
    DEFAULT_LAYER4_ROOT,
    DEFAULT_REFERENCES_JSONL,
    REPO_ROOT,
    abstract_from_markdown,
    content_list_path,
    default_source_artifacts,
    find_jsonl_record,
    first_heading,
    markdown_path_for_reference,
    pdf_path,
    repo_relative,
    section_outline,
    stable_data_path,
    venue_from_paper_id,
    write_json,
    write_yaml,
    year_from_paper_id,
)


def reference_title_map(reference_record: dict[str, Any]) -> dict[int, str]:
    result: dict[int, str] = {}
    for reference in reference_record.get("references") or []:
        try:
            index = int(reference.get("index"))
        except (TypeError, ValueError):
            continue
        result[index] = str(reference.get("title") or reference.get("raw") or "")
    return result


def citation_items(cite_record: dict[str, Any], reference_record: dict[str, Any], limit: int | None) -> list[dict[str, Any]]:
    title_by_index = reference_title_map(reference_record)
    contexts = cite_record.get("citation_contexts") or []
    if limit is not None:
        contexts = contexts[:limit]
    items: list[dict[str, Any]] = []
    for context in contexts:
        indices = [int(index) for index in context.get("matched_reference_indices") or []]
        items.append(
            {
                "context_id": context.get("context_id", ""),
                "raw_citation": context.get("raw_citation", ""),
                "reference_indices": indices,
                "reference_titles": [title_by_index.get(index, "") for index in indices],
                "context": context.get("paragraph", "") or context.get("sentence", ""),
                "section": context.get("section", ""),
                "paragraph_index": context.get("paragraph_index"),
                "sentence": context.get("sentence", ""),
                "citation_function": "",
            }
        )
    return items


def build_paper_template(
    *,
    paper_id: str,
    markdown_path: Path,
    reference_record: dict[str, Any],
    cite_record: dict[str, Any],
    max_citations: int | None,
) -> dict[str, Any]:
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
    origin_pdf = pdf_path(markdown_path)
    content_list = content_list_path(markdown_path)
    title = first_heading(markdown)
    return {
        "paper_record": {
            "paper_id": f"paper::{paper_id}",
            "source_type": "paper",
            "metadata": {
                "title": title,
                "authors": [],
                "year": year_from_paper_id(paper_id),
                "venue": venue_from_paper_id(paper_id),
                "arxiv_id": "",
                "acl_id": paper_id,
                "doi": "",
                "url": "",
                "pdf_path": stable_data_path(origin_pdf) if origin_pdf else "",
                "markdown_path": stable_data_path(markdown_path),
                "content_list_path": stable_data_path(content_list) if content_list else "",
            },
            "content_units": {
                "abstract": abstract_from_markdown(markdown),
                "section_outline": section_outline(markdown),
                "has_appendix": "appendix" in markdown.lower(),
                "has_supplementary_material": "supplementary" in markdown.lower(),
                "figures": [],
                "tables": [],
            },
            "atomic_extracts": {
                "intent": {
                    "paper_type": "unknown",
                    "research_problem": "",
                    "target_domain": [],
                },
                "contributions": [],
                "claims": [],
                "experiments": [],
                "limitations": [],
                "future_work": [],
                "citation_context": {
                    "cite": citation_items(cite_record, reference_record, max_citations),
                    "cited_by": [],
                },
            },
            "source_artifacts": default_source_artifacts(),
        },
        "resources_introduced": [],
        "resources_used": [],
        "cites": [],
        "cited_by": [],
        "source_paper": "",
        "comparison": "",
    }


def build_resource_template() -> list[dict[str, Any]]:
    return []


def build_input_bundle(
    *,
    paper_id: str,
    markdown_path: Path,
    references_jsonl: Path,
    cite_contexts_jsonl: Path,
    output_dir: Path,
) -> dict[str, Any]:
    content_list = content_list_path(markdown_path)
    origin_pdf = pdf_path(markdown_path)
    return {
        "paper_id": paper_id,
        "repository_root": str(REPO_ROOT),
        "markdown_path": stable_data_path(markdown_path),
        "content_list_path": stable_data_path(content_list) if content_list else "",
        "pdf_path": stable_data_path(origin_pdf) if origin_pdf else "",
        "references_jsonl": stable_data_path(references_jsonl),
        "cite_contexts_jsonl": stable_data_path(cite_contexts_jsonl),
        "output_dir": stable_data_path(output_dir),
        "agent_judgment_output": stable_data_path(output_dir / "agent_judgment.json"),
        "paper_record_output": stable_data_path(output_dir / "paper_record.yml"),
        "resource_records_output": stable_data_path(output_dir / "resource_records.yml"),
        "resource_verification_report_output": stable_data_path(output_dir / "resource_verification_report.json"),
        "run_report_output": stable_data_path(output_dir / "run_report.json"),
    }


def build_agent_prompt(bundle: dict[str, Any]) -> str:
    paper_id = bundle["paper_id"]
    output_dir = bundle["output_dir"]
    return f"""# Use Skill: paper-mineru-resource-extract

You are one Kimi worker launched by the batch script for a single MinerU/PDF paper.
Do not launch other agents. Complete this paper yourself.

Repository root: {bundle["repository_root"]}
Kimi working directory: {bundle["repository_root"]}
Paper id: {paper_id}
Output directory: {output_dir}

Path rules:
- The Kimi process is launched from the repository root above, not from `/srv`.
- Relative paths in this prompt are relative to the repository root.
- Absolute paths such as `/srv/datasets/p4a/...` are shared dataset paths; use them exactly as written.
- If any path shown here differs from `<output_dir>/input_bundle.json`, trust `input_bundle.json`.

Use this skill:
- skill name: paper-mineru-resource-extract
- skill file: skill/paper-mineru-resource-extract/SKILL.md

The batch launcher has already prepared the fixed inputs and base templates.
Follow the skill workflow exactly:
1. Read the skill file.
2. Read the prepared input bundle and paper files.
3. Read the MinerU Markdown, references, and citation contexts.
4. Investigate reusable resources. Use GitHub MCP when a GitHub repository or GitHub project page is involved. Use hf-readonly MCP for HuggingFace links, datasets, models, and Spaces. Use arxiv-mcp for arXiv metadata and source artifacts.
5. Write agent_judgment.json.
6. Run the local apply script described by the skill to generate YAML from agent_judgment.json.
7. Optionally run validation and fix agent_judgment.json if needed.

Important semantic reminders:
- Claims should be 1-2 concise claims summarized from the abstract, not detailed sentence-level rhetorical judgments.
- The resource kind "skill" is only for a reusable agent skill/workflow introduced by the paper itself.
- The extraction skill paper-mineru-resource-extract is not a paper resource and must never be recorded as a resource.
- If arXiv HTML or TeX source is not fetched, keep source_artifacts status as unfetched; do not fabricate files.
- Use only enum values documented by the skill; invalid values will make the merge script fail.

Prepared files:
- Input bundle: {output_dir}/input_bundle.json
- Base paper YAML: {output_dir}/paper_record.base.yml
- Base resource YAML: {output_dir}/resource_records.base.yml

Primary input files:
- Markdown: {bundle["markdown_path"]}
- Content list: {bundle["content_list_path"]}
- PDF: {bundle["pdf_path"]}
- Repaired references: {bundle["references_jsonl"]}
- Citation contexts: {bundle["cite_contexts_jsonl"]}

Required outputs after your run:
- {output_dir}/agent_judgment.json
- {output_dir}/paper_record.yml
- {output_dir}/resource_records.yml
- {output_dir}/resource_verification_report.json
- {output_dir}/run_report.json

Important boundary:
- You may construct and update agent_judgment.json.
- You may run the local scripts documented by the skill.
- Do not manually edit generated YAML. YAML should be generated by scripts from agent_judgment.json.

Return a concise status summary after finishing this paper.
"""


def build_run_report(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "paper_id": bundle["paper_id"],
        "status": "prepared",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "markdown": bundle["markdown_path"],
            "references": bundle["references_jsonl"],
            "citation_contexts": bundle["cite_contexts_jsonl"],
        },
        "outputs": {
            "paper_record": bundle["paper_record_output"],
            "resource_records": bundle["resource_records_output"],
            "resource_verification_report": bundle["resource_verification_report_output"],
        },
        "resource_count": 0,
        "github_checked_count": 0,
        "warnings": [],
        "errors": [],
        "source_artifacts": {
            "html_downloaded": "unfetched",
            "tex_source_downloaded": "unfetched",
        },
    }


def build_resource_verification_report(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "paper_id": bundle["paper_id"],
        "status": "prepared",
        "checks": [],
        "warnings": [],
        "errors": [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare MinerU Layer 4 templates and Kimi prompt for one paper.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--references-jsonl", type=Path, default=DEFAULT_REFERENCES_JSONL)
    parser.add_argument("--cite-contexts-jsonl", type=Path, default=DEFAULT_CITE_CONTEXTS_JSONL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_LAYER4_ROOT)
    parser.add_argument("--max-citations", type=int, default=200)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    reference_record = find_jsonl_record(args.references_jsonl, args.paper_id)
    cite_record = find_jsonl_record(args.cite_contexts_jsonl, args.paper_id)
    markdown_path = markdown_path_for_reference(reference_record)
    output_dir = args.output_root / args.paper_id
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_outputs = [
        output_dir / "paper_record.yml",
        output_dir / "paper_record.base.yml",
        output_dir / "resource_records.yml",
        output_dir / "resource_records.base.yml",
        output_dir / "input_bundle.json",
        output_dir / "agent_prompt.md",
    ]
    if not args.overwrite and any(path.exists() for path in existing_outputs):
        raise SystemExit(f"{output_dir} already contains prepared files; pass --overwrite to replace templates.")

    bundle = build_input_bundle(
        paper_id=args.paper_id,
        markdown_path=markdown_path,
        references_jsonl=args.references_jsonl,
        cite_contexts_jsonl=args.cite_contexts_jsonl,
        output_dir=output_dir,
    )
    paper_template = build_paper_template(
        paper_id=args.paper_id,
        markdown_path=markdown_path,
        reference_record=reference_record,
        cite_record=cite_record,
        max_citations=args.max_citations,
    )

    write_json(output_dir / "input_bundle.json", bundle)
    write_yaml(output_dir / "paper_record.base.yml", paper_template)
    write_yaml(output_dir / "paper_record.yml", paper_template)
    write_yaml(output_dir / "resource_records.base.yml", build_resource_template())
    write_yaml(output_dir / "resource_records.yml", build_resource_template())
    (output_dir / "agent_prompt.md").write_text(build_agent_prompt(bundle), encoding="utf-8")
    write_json(output_dir / "resource_verification_report.json", build_resource_verification_report(bundle))
    write_json(output_dir / "run_report.json", build_run_report(bundle))
    print(f"prepared {args.paper_id} in {repo_relative(output_dir)}")


if __name__ == "__main__":
    main()
