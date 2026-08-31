#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4_v2/run_candidate_extraction.py --paper-id <paper_id> \
#     --cite-contexts-jsonl <per_paper>/cite_contexts.jsonl
"""LLM call 1: extract semantic candidates from the prepared paper inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common_v2 import DEFAULT_LAYER4_V2_ROOT, find_jsonl_record, normalize_ws, read_json, write_json
from llm_client import VllmJsonClient
from prompts import CANDIDATE_SYSTEM, candidate_user_prompt
from schemas import SEMANTIC_CANDIDATES_SCHEMA

MAX_CITATION_CONTEXTS = 200
MAX_CONTEXT_CHARS = 700


def load_citation_contexts(paper_id: str, cite_contexts_jsonl: Path, paper_dir: Path) -> tuple[list[dict[str, Any]], str]:
    """Return (contexts, citation_source). Falls back to the degraded file."""
    if cite_contexts_jsonl.exists() and cite_contexts_jsonl.stat().st_size > 0:
        record = find_jsonl_record(cite_contexts_jsonl, paper_id)
        return list(record.get("citation_contexts") or []), "verified"
    degraded_path = paper_dir / "optional" / "cite_contexts.degraded.jsonl"
    if degraded_path.exists():
        record = json.loads(degraded_path.read_text(encoding="utf-8").splitlines()[0])
        return list(record.get("citation_contexts") or []), "degraded"
    return [], "missing"


def citation_block(contexts: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for context in contexts[:MAX_CITATION_CONTEXTS]:
        context_id = context.get("context_id", "")
        section = normalize_ws(str(context.get("section") or ""))
        text = normalize_ws(str(context.get("paragraph") or context.get("sentence") or ""))[:MAX_CONTEXT_CHARS]
        raw = normalize_ws(str(context.get("raw_citation") or ""))
        lines.append(f"- context_id: {context_id}\n  section: {section}\n  citation: {raw}\n  text: {text}")
    return "\n".join(lines) if lines else "(no citation contexts available)"


def url_mentions_block(url_mentions: dict[str, Any]) -> str:
    parts: list[str] = []
    if url_mentions.get("urls"):
        parts.append("URLs: " + ", ".join(url_mentions["urls"][:80]))
    if url_mentions.get("github_repos"):
        parts.append("GitHub repos: " + ", ".join(url_mentions["github_repos"][:40]))
    if url_mentions.get("huggingface_repos"):
        parts.append("HuggingFace repos: " + ", ".join(url_mentions["huggingface_repos"][:40]))
    if url_mentions.get("footnote_snippets"):
        parts.append(
            "Footnote/annotation sentences with URLs (absent from the text below; treat as "
            "paper text):\n" + "\n".join("- " + s for s in url_mentions["footnote_snippets"][:40])
        )
    return "\n".join(parts) if parts else "(no URLs detected)"


def captions_block(captions: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in captions:
        for text in item.get("captions") or []:
            lines.append(f"- {text}")
    return "\n".join(lines[:120]) if lines else "(no captions extracted)"


def run_extraction(
    *,
    paper_id: str,
    paper_dir: Path,
    cite_contexts_jsonl: Path,
    client: VllmJsonClient,
) -> dict[str, Any]:
    index = read_json(paper_dir / "paper_index.json")
    url_mentions = read_json(paper_dir / "url_mentions.json")
    captions = read_json(paper_dir / "captions.json")
    fulltext = (paper_dir / "fulltext_for_llm.md").read_text(encoding="utf-8")
    contexts, citation_source = load_citation_contexts(paper_id, cite_contexts_jsonl, paper_dir)

    user = candidate_user_prompt(
        paper_id=paper_id,
        title=str(index.get("title") or ""),
        venue="ACL 2026",
        url_mentions_block=url_mentions_block(url_mentions),
        captions_block=captions_block(captions),
        citation_block=citation_block(contexts),
        fulltext=fulltext,
    )
    # thinking off: call 1 is literal extraction; thinking costs ~10K hidden
    # tokens per call and pushes long papers past the output budget.
    result, telemetry = client.json_call(
        system=CANDIDATE_SYSTEM,
        user=user,
        schema=SEMANTIC_CANDIDATES_SCHEMA,
        thinking=False,
    )
    result["paper_id"] = paper_id
    result["citation_source"] = citation_source
    result["telemetry"] = telemetry
    write_json(paper_dir / "semantic_candidates.json", result)
    return {
        "paper_id": paper_id,
        "candidate_count": len(result.get("resource_candidates") or []),
        "citation_source": citation_source,
        **telemetry,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Layer4 v2 LLM call 1: candidate extraction.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--cite-contexts-jsonl", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_LAYER4_V2_ROOT)
    parser.add_argument("--max-tokens", type=int, default=16384)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = VllmJsonClient(max_tokens=args.max_tokens)
    summary = run_extraction(
        paper_id=args.paper_id,
        paper_dir=args.output_root / args.paper_id,
        cite_contexts_jsonl=args.cite_contexts_jsonl,
        client=client,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
