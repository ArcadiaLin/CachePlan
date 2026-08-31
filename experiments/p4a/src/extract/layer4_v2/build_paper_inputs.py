#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4_v2/build_paper_inputs.py --paper-id <paper_id> \
#     --references-jsonl <per_paper>/verified_or_repaired.jsonl \
#     --cite-contexts-jsonl <per_paper>/cite_contexts.jsonl \
#     --output-root /srv/datasets/p4a/data/processed/layer4_v2/2026/acl
"""Build program-side LLM inputs for one paper (Layer4 v2 preprocessing).

Products in <output_root>/<paper_id>/:
  paper_index.json      title/abstract/section outline
  url_mentions.json     URLs + GitHub/HF repo mentions (recall aid for call 1)
  captions.json         figure/table captions compressed from content_list_v2.json
  fulltext_for_llm.md   markdown with the References section removed
  optional/cite_contexts.degraded.jsonl   regex fallback when the cite chain failed
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common_v2 import (
    DEFAULT_LAYER4_V2_ROOT,
    content_list_path,
    est_tokens,
    find_jsonl_record,
    markdown_path_for_reference,
    normalize_ws,
    section_outline,
    write_json,
)

FULLTEXT_TOKEN_BUDGET = 100_000

_URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"'`]+")
_GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.I)
_HF_RE = re.compile(r"huggingface\.co/((?:datasets/|spaces/)?[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.I)
_CITATION_HINT_RE = re.compile(r"\((?:[A-Z][A-Za-zÀ-ɏ'-]+(?: et al\.?)?,? ?\d{4}[a-z]?(?:; ?)?)+\)|\[\d+(?:, ?\d+)*\]")


def strip_references(markdown: str) -> str:
    """Remove the References/Bibliography section but keep appendices after it."""
    lines = markdown.splitlines()
    ref_start = ref_level = None
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        title = normalize_ws(match.group(2)).lower().rstrip(".:")
        title = re.sub(r"^[0-9ivx.\s]+", "", title)
        if ref_start is None and title in {"references", "bibliography", "reference"}:
            ref_start, ref_level = index, len(match.group(1))
            continue
        if ref_start is not None and len(match.group(1)) <= ref_level:
            return "\n".join(lines[:ref_start] + lines[index:])
    if ref_start is not None:
        return "\n".join(lines[:ref_start])
    return markdown


def clean_url(url: str) -> str:
    return url.rstrip(".,;:!?)]}。，")


def extract_url_mentions(markdown: str, extra_snippets: list[str] | None = None) -> dict[str, Any]:
    corpus = markdown if not extra_snippets else markdown + "\n" + "\n".join(extra_snippets)
    urls: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(corpus):
        url = clean_url(match.group(0))
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    github = sorted({m.group(1).rstrip(".") for m in _GITHUB_RE.finditer(corpus)})
    huggingface = sorted({m.group(1).rstrip(".") for m in _HF_RE.finditer(corpus)})
    # URL-bearing sentences that exist only outside the markdown (typically PDF
    # footnotes like "Code and data are available at: <url>" that MinerU drops
    # from the .md rendering) — surfaced to call 1 with their context.
    snippets = [s for s in (extra_snippets or []) if s not in markdown]
    return {"urls": urls, "github_repos": github, "huggingface_repos": huggingface,
            "footnote_snippets": snippets[:40]}


def mine_content_list_url_snippets(markdown_path: Path) -> list[str]:
    """Collect URL-bearing strings from BOTH content_list variants next to the
    markdown. Release URLs often live only in footnotes there."""
    stem = str(markdown_path.with_suffix(""))
    snippets: list[str] = []
    seen: set[str] = set()

    bib_entry = re.compile(r"\.\s*(?:19|20)\d{2}[a-z]?\.\s")

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if _URL_RE.search(value) and not bib_entry.search(value):
                text = normalize_ws(value)[:300]
                if text and text not in seen:
                    seen.add(text)
                    snippets.append(text)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    for suffix in ("_content_list.json", "_content_list_v2.json"):
        path = Path(stem + suffix)
        if not path.exists():
            continue
        try:
            walk(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return snippets


def _collect_caption_strings(value: Any, sink: list[str]) -> None:
    if isinstance(value, str):
        text = normalize_ws(value)
        if text:
            sink.append(text)
    elif isinstance(value, list):
        for item in value:
            _collect_caption_strings(item, sink)
    elif isinstance(value, dict):
        _collect_caption_strings(value.get("content"), sink)


def extract_captions(content_list_file: Path | None) -> list[dict[str, Any]]:
    if content_list_file is None or not content_list_file.exists():
        return []
    try:
        data = json.loads(content_list_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    pages = data if isinstance(data, list) else []
    captions: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages):
        if not isinstance(page, list):
            continue
        for item in page:
            if not isinstance(item, dict):
                continue
            if item.get("type") not in {"image", "table", "chart", "figure"}:
                continue
            content = item.get("content")
            texts: list[str] = []
            if isinstance(content, dict):
                for key, value in content.items():
                    if "caption" in key or "footnote" in key:
                        _collect_caption_strings(value, texts)
            if texts:
                captions.append({"page": page_index, "type": item.get("type"), "captions": texts})
    return captions


def degraded_cite_contexts(paper_id: str, markdown: str, *, limit: int = 100) -> dict[str, Any]:
    """Regex fallback citation contexts when the reference chain failed."""
    contexts: list[dict[str, Any]] = []
    section = ""
    for paragraph_index, block in enumerate(markdown.split("\n\n")):
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", block.strip())
        if heading:
            section = normalize_ws(heading.group(1))
            continue
        text = normalize_ws(block)
        if not text or len(text) < 40:
            continue
        matches = _CITATION_HINT_RE.findall(text)
        if not matches:
            continue
        contexts.append(
            {
                "context_id": f"{paper_id}::cite::{len(contexts) + 1}",
                "raw_citation": matches[0],
                "matched_reference_indices": [],
                "paragraph": text[:1200],
                "sentence": "",
                "section": section,
                "paragraph_index": paragraph_index,
            }
        )
        if len(contexts) >= limit:
            break
    return {"paper_id": paper_id, "citation_contexts": contexts, "citation_source": "degraded"}


def build_inputs(
    *,
    paper_id: str,
    references_jsonl: Path,
    cite_contexts_jsonl: Path,
    output_dir: Path,
) -> dict[str, Any]:
    reference_record = find_jsonl_record(references_jsonl, paper_id)
    markdown_path = markdown_path_for_reference(reference_record)
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace")

    fulltext = strip_references(markdown)
    fulltext_tokens = est_tokens(fulltext)
    truncated = False
    if fulltext_tokens > FULLTEXT_TOKEN_BUDGET:
        # Oversized-paper fallback: keep head + tail within budget instead of section recall.
        budget_bytes = FULLTEXT_TOKEN_BUDGET * 4
        head = fulltext[: budget_bytes * 3 // 4]
        tail = fulltext[-budget_bytes // 4 :]
        fulltext = head + "\n\n[... truncated for length ...]\n\n" + tail
        truncated = True

    title_match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
    title = normalize_ws(title_match.group(1)) if title_match else ""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "fulltext_for_llm.md").write_text(fulltext, encoding="utf-8")

    url_mentions = extract_url_mentions(markdown, mine_content_list_url_snippets(markdown_path))
    write_json(output_dir / "url_mentions.json", url_mentions)

    captions = extract_captions(content_list_path(markdown_path))
    write_json(output_dir / "captions.json", captions)

    index = {
        "paper_id": paper_id,
        "title": title,
        "markdown_path": str(markdown_path),
        "section_outline": section_outline(markdown),
        "fulltext_tokens_est": fulltext_tokens,
        "fulltext_truncated": truncated,
    }
    write_json(output_dir / "paper_index.json", index)

    citation_source = "verified"
    if not cite_contexts_jsonl.exists() or cite_contexts_jsonl.stat().st_size == 0:
        degraded = degraded_cite_contexts(paper_id, fulltext)
        optional_dir = output_dir / "optional"
        optional_dir.mkdir(parents=True, exist_ok=True)
        degraded_path = optional_dir / "cite_contexts.degraded.jsonl"
        degraded_path.write_text(json.dumps(degraded, ensure_ascii=False) + "\n", encoding="utf-8")
        citation_source = "degraded"

    return {
        "paper_id": paper_id,
        "title": title,
        "citation_source": citation_source,
        "fulltext_tokens_est": fulltext_tokens,
        "fulltext_truncated": truncated,
        "url_count": len(url_mentions["urls"]),
        "caption_count": len(captions),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Layer4 v2 LLM inputs for one paper.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--references-jsonl", type=Path, required=True)
    parser.add_argument("--cite-contexts-jsonl", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_LAYER4_V2_ROOT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = build_inputs(
        paper_id=args.paper_id,
        references_jsonl=args.references_jsonl,
        cite_contexts_jsonl=args.cite_contexts_jsonl,
        output_dir=args.output_root / args.paper_id,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
