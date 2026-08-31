#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4_v2/run_final_judgment.py --paper-id <paper_id>
"""LLM call 2 (final judge) + deterministic assembly of agent_judgment.json.

The LLM only judges resources (keep/drop, kind, relation, URL splits, fuzzy-match
confidence). paper_record semantics come from call 1; metadata/source_artifacts
and checked_by literals are filled programmatically from external_resolution.json
so they stay consistent with what apply/validate expect.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common_v2 import (
    DEFAULT_LAYER4_V2_ROOT,
    default_source_artifacts,
    now_iso,
    read_json,
    write_json,
)
from llm_client import VllmJsonClient
from prompts import JUDGE_SYSTEM, judge_user_prompt
from schemas import JUDGED_RESOURCES_SCHEMA

ARTIFACT_DEFER_NOTE = "fetch deferred to the optional batch artifact stage (layer4_v2 main flow does not download)"


def build_source_artifacts(arxiv_resolution: dict[str, Any]) -> dict[str, Any]:
    artifacts = default_source_artifacts()
    if arxiv_resolution.get("matched"):
        artifacts["arxiv"].update(
            {
                "arxiv_id": arxiv_resolution.get("arxiv_id") or "",
                "version": arxiv_resolution.get("version") or "",
                "url": arxiv_resolution.get("url") or "",
                "metadata_status": "available",
                "metadata_checked_by": "arxiv_api",
                "title": arxiv_resolution.get("title") or "",
                "authors": arxiv_resolution.get("authors") or [],
                "submitted": arxiv_resolution.get("submitted") or "",
                "updated": arxiv_resolution.get("updated") or "",
                "primary_category": arxiv_resolution.get("primary_category") or "",
                "categories": arxiv_resolution.get("categories") or [],
                "abstract": arxiv_resolution.get("abstract") or "",
                "notes": "matched by title via arXiv API",
            }
        )
        # validate_layer4_outputs rejects status=unfetched once arXiv metadata is
        # available; the main flow defers downloads, so mark them unknown.
        for key in ("html_downloaded", "tex_source_downloaded"):
            artifacts[key]["status"] = "unknown"
            artifacts[key]["checked_by"] = "arxiv_api"
            artifacts[key]["notes"] = ARTIFACT_DEFER_NOTE
    else:
        artifacts["arxiv"]["metadata_status"] = "missing" if arxiv_resolution else "unfetched"
        artifacts["arxiv"]["metadata_checked_by"] = "arxiv_api" if arxiv_resolution else ""
        if arxiv_resolution:
            artifacts["arxiv"]["notes"] = "no confident arXiv title match"
    return artifacts


def _resolution_by_url(resolution: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for entry in resolution.get("resources") or []:
        url = str(entry.get("url") or "")
        info = entry.get("resolution") or {}
        if url:
            mapping[url] = info
        canonical = str(info.get("canonical_url") or "")
        if canonical:
            mapping[canonical] = info
    return mapping


def checked_by_for(url: str, info: dict[str, Any]) -> str:
    lowered = url.lower()
    if "github.com" in lowered:
        return "github_mcp"
    if "huggingface.co" in lowered or "hf.co" in lowered:
        return "hf-readonly" if info.get("status") == "available" else "pending_huggingface_mcp"
    if url:
        return "external"
    return "agent"


def assemble_judgment(
    *,
    paper_id: str,
    candidates: dict[str, Any],
    resolution: dict[str, Any],
    judged: dict[str, Any],
) -> dict[str, Any]:
    paper = candidates.get("paper_record") or {}
    arxiv_resolution = resolution.get("arxiv") or {}
    by_url = _resolution_by_url(resolution)

    resources: list[dict[str, Any]] = []
    warnings = [str(w) for w in (candidates.get("warnings") or [])] + [
        str(w) for w in (judged.get("warnings") or [])
    ]

    for item in judged.get("resources") or []:
        url = str(item.get("url") or "").strip()
        info = by_url.get(url, {})
        status = str(item.get("availability_status") or "unknown")
        if info.get("status") == "missing" and status == "available":
            status = "missing"
            warnings.append(f"resource {item.get('name')!r}: judge said available but probe returned missing; downgraded")
        checked_by = checked_by_for(url, info)
        notes = str(item.get("availability_notes") or "")

        resource: dict[str, Any] = {
            "kind": item.get("kind"),
            "name": item.get("name"),
            "aliases": item.get("aliases") or [],
            "description": item.get("description") or "",
            "relation_type": item.get("relation_type"),
            "evidence": {
                "section": item.get("evidence_section") or "",
                "quote": item.get("evidence_quote") or "",
                "citation_context_ids": item.get("citation_context_ids") or [],
            },
            "access": {
                "url": url,
                "access_type": item.get("access_type") or "unknown",
                "license": item.get("license") or str(info.get("license") or ""),
            },
            "availability": {
                "status": status,
                "checked_by": checked_by,
                "checked_at": now_iso() if url else "",
                "notes": notes,
            },
            "agent_callable": item.get("agent_callable")
            or {"can_wrap": False, "estimated_wrapping_difficulty": "unknown", "notes": ""},
            "confidence": item.get("confidence") or "medium",
        }
        if "github.com" in url.lower():
            resource["repository"] = {
                "canonical_url": str(info.get("canonical_url") or url),
                "verification": {
                    "checked_by": "github_mcp",
                    "status": str(info.get("status") or status),
                    "notes": str(info.get("description") or "")[:300],
                },
            }
        resources.append(resource)

    metadata = {"arxiv_id": "", "url": ""}
    if arxiv_resolution.get("matched"):
        metadata["arxiv_id"] = arxiv_resolution.get("arxiv_id") or ""
        metadata["url"] = arxiv_resolution.get("url") or ""

    return {
        "paper_id": paper_id,
        "paper_record": {
            "intent": paper.get("intent") or {},
            "contributions": paper.get("contributions") or [],
            "claims": (paper.get("claims") or [])[:2],
            "experiments": paper.get("experiments") or [],
            "limitations": paper.get("limitations") or [],
            "future_work": paper.get("future_work") or [],
            "citation_functions": paper.get("citation_functions") or [],
            "metadata": metadata,
            "source_artifacts": build_source_artifacts(arxiv_resolution),
        },
        "resources": resources,
        "verification_checks": [],
        "warnings": warnings,
    }


def run_judgment(*, paper_id: str, paper_dir: Path, client: VllmJsonClient) -> dict[str, Any]:
    candidates = read_json(paper_dir / "semantic_candidates.json")
    resolution = read_json(paper_dir / "external_resolution.json")

    slim_candidates = {
        "resource_candidates": candidates.get("resource_candidates") or [],
        "warnings": candidates.get("warnings") or [],
    }
    user = judge_user_prompt(
        paper_id=paper_id,
        candidates_json=json.dumps(slim_candidates, ensure_ascii=False, indent=1),
        resolution_json=json.dumps(resolution, ensure_ascii=False, indent=1),
    )
    # thinking on: keep/drop, kind and fuzzy-match confidence benefit from
    # reasoning; budget ~10K hidden reasoning tokens on top of the JSON.
    judged, telemetry = client.json_call(
        system=JUDGE_SYSTEM,
        user=user,
        schema=JUDGED_RESOURCES_SCHEMA,
        thinking=True,
        max_tokens=24576,
    )
    write_json(paper_dir / "judged_resources.json", {**judged, "telemetry": telemetry})

    judgment = assemble_judgment(
        paper_id=paper_id,
        candidates=candidates,
        resolution=resolution,
        judged=judged,
    )
    write_json(paper_dir / "agent_judgment.json", judgment)
    return {
        "paper_id": paper_id,
        "resource_count": len(judgment["resources"]),
        "warning_count": len(judgment["warnings"]),
        **telemetry,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Layer4 v2 LLM call 2: final judgment + assembly.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_LAYER4_V2_ROOT)
    parser.add_argument("--max-tokens", type=int, default=16384)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = VllmJsonClient(max_tokens=args.max_tokens)
    summary = run_judgment(paper_id=args.paper_id, paper_dir=args.output_root / args.paper_id, client=client)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
