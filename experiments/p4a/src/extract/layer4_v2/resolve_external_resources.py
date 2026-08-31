#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/layer4_v2/resolve_external_resources.py --paper-id <paper_id>
"""Program-side external verification with global caches (Layer4 v2 stage 2.5).

Verifies GitHub repos, HuggingFace repos, arXiv title matches, and generic URLs
for the candidates in semantic_candidates.json. No LLM involved. Results are
cached globally so repeated resources (GSM8K, MMLU, ...) are only checked once.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse, parse_qsl, urlencode

import httpx

from common_v2 import (
    DEFAULT_LAYER4_V2_ROOT,
    DEFAULT_V2_CACHE_ROOT,
    PROXY_URL,
    normalize_ws,
    now_iso,
    read_json,
    write_json,
)

README_SNIPPET_CHARS = 2500
ABSTRACT_SNIPPET_CHARS = 1200
_ATOM = "{http://www.w3.org/2005/Atom}"


class JsonlCache:
    """Append-only JSONL cache with an in-memory index. Thread-safe."""

    def __init__(self, path: Path, *, refresh: bool = False) -> None:
        self.path = path
        self.refresh = refresh
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    self._data[row["key"]] = row["value"]
                except Exception:
                    continue

    def get(self, key: str) -> Any | None:
        if self.refresh:
            return None
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"key": key, "value": value, "checked_at": now_iso()}, ensure_ascii=False) + "\n")


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}

    def wait(self, domain: str, interval: float) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                last = self._last.get(domain, 0.0)
                if now - last >= interval:
                    self._last[domain] = now
                    return
                sleep_for = interval - (now - last)
            time.sleep(sleep_for)


_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref"}


def normalize_url(url: str) -> str:
    url = url.strip().rstrip(".,;:!?)]}")
    parsed = urlparse(url if "://" in url else "https://" + url)
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in _TRACKING_PARAMS])
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def classify_url(url: str) -> tuple[str, str]:
    """Return (kind, key) where kind in {github, huggingface, arxiv, url}."""
    parsed = urlparse(url if "://" in url else "https://" + url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    if host.endswith("github.com"):
        parts = path.split("/")
        if len(parts) >= 2:
            return "github", f"{parts[0]}/{re.sub(r'\\.git$', '', parts[1])}"
    if host.endswith("huggingface.co") or host.endswith("hf.co"):
        parts = path.split("/")
        if parts and parts[0] in {"datasets", "spaces"} and len(parts) >= 3:
            return "huggingface", f"{parts[0]}/{parts[1]}/{parts[2]}"
        if len(parts) >= 2 and parts[0] not in {"papers", "blog", "docs", "collections"}:
            return "huggingface", f"models/{parts[0]}/{parts[1]}"
    if host.endswith("arxiv.org"):
        return "arxiv_link", normalize_url(url)
    return "url", normalize_url(url)


class ExternalResolver:
    def __init__(self, *, cache_root: Path, refresh: bool = False, timeout_s: float = 30.0) -> None:
        cache_root.mkdir(parents=True, exist_ok=True)
        self.caches = {
            "github": JsonlCache(cache_root / "github.jsonl", refresh=refresh),
            "huggingface": JsonlCache(cache_root / "huggingface.jsonl", refresh=refresh),
            "hf_search": JsonlCache(cache_root / "hf_search.jsonl", refresh=refresh),
            "github_search": JsonlCache(cache_root / "github_search.jsonl", refresh=refresh),
            "arxiv": JsonlCache(cache_root / "arxiv.jsonl", refresh=refresh),
            "url": JsonlCache(cache_root / "url_status.jsonl", refresh=refresh),
        }
        self.limiter = RateLimiter()
        self.github_token = os.environ.get("GITHUB_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        # External hosts go through the local forward proxy; arXiv API is tried direct first.
        self._proxied = httpx.Client(proxy=PROXY_URL, timeout=timeout_s, follow_redirects=True, trust_env=False)
        self._direct = httpx.Client(timeout=timeout_s, follow_redirects=True, trust_env=False)

    # ---------------- GitHub ----------------

    def github(self, owner_repo: str) -> dict[str, Any]:
        key = owner_repo.lower()
        cached = self.caches["github"].get(key)
        if cached is not None:
            return cached
        interval = 0.3 if self.github_token else 2.5
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "p4a-layer4-v2/1.0"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        result: dict[str, Any] = {"kind": "github", "input": owner_repo}
        try:
            self.limiter.wait("github", interval)
            response = self._proxied.get(f"https://api.github.com/repos/{owner_repo}", headers=headers)
            result["status_code"] = response.status_code
            if response.status_code == 200:
                data = response.json()
                result.update(
                    {
                        "status": "available",
                        "canonical_url": data.get("html_url") or f"https://github.com/{data.get('full_name')}",
                        "full_name": data.get("full_name"),
                        "description": normalize_ws(str(data.get("description") or ""))[:500],
                        "license": ((data.get("license") or {}).get("spdx_id") or "") if isinstance(data.get("license"), dict) else "",
                        "archived": bool(data.get("archived")),
                        "stars": data.get("stargazers_count"),
                    }
                )
                self.limiter.wait("github", interval)
                readme = self._proxied.get(
                    f"https://api.github.com/repos/{result['full_name']}/readme",
                    headers={**headers, "Accept": "application/vnd.github.raw"},
                )
                if readme.status_code == 200:
                    result["readme_snippet"] = normalize_ws(readme.text[:README_SNIPPET_CHARS * 2])[:README_SNIPPET_CHARS]
            elif response.status_code == 404:
                result["status"] = "missing"
            else:
                result["status"] = "unknown"
                result["error"] = response.text[:200]
        except Exception as exc:  # noqa: BLE001
            result["status"] = "unknown"
            result["error"] = str(exc)[:200]
        self.caches["github"].put(key, result)
        return result

    # ---------------- HuggingFace ----------------

    def huggingface(self, typed_id: str) -> dict[str, Any]:
        """typed_id: models/org/name | datasets/org/name | spaces/org/name."""
        key = typed_id.lower()
        cached = self.caches["huggingface"].get(key)
        if cached is not None:
            return cached
        repo_type, _, repo_id = typed_id.partition("/")
        api_path = {"models": "models", "datasets": "datasets", "spaces": "spaces"}.get(repo_type, "models")
        url_prefix = {"models": "", "datasets": "datasets/", "spaces": "spaces/"}.get(repo_type, "")
        result: dict[str, Any] = {"kind": "huggingface", "input": typed_id}
        try:
            self.limiter.wait("huggingface", 0.5)
            response = self._proxied.get(f"https://huggingface.co/api/{api_path}/{repo_id}")
            result["status_code"] = response.status_code
            if response.status_code == 200:
                data = response.json()
                card = data.get("cardData") or {}
                result.update(
                    {
                        "status": "available",
                        "canonical_url": f"https://huggingface.co/{url_prefix}{data.get('id') or repo_id}",
                        "repo_id": data.get("id") or repo_id,
                        "repo_type": repo_type,
                        "license": str(card.get("license") or ""),
                        "downloads": data.get("downloads"),
                        "likes": data.get("likes"),
                        "tags": (data.get("tags") or [])[:12],
                        "gated": data.get("gated", False),
                        "private": data.get("private", False),
                    }
                )
            elif response.status_code in (404, 401):
                result["status"] = "missing" if response.status_code == 404 else "restricted"
            else:
                result["status"] = "unknown"
        except Exception as exc:  # noqa: BLE001
            result["status"] = "unknown"
            result["error"] = str(exc)[:200]
        self.caches["huggingface"].put(key, result)
        return result

    def hf_search(self, query: str, *, limit: int = 3) -> dict[str, Any]:
        key = normalize_ws(query).lower()
        cached = self.caches["hf_search"].get(key)
        if cached is not None:
            return cached
        result: dict[str, Any] = {"kind": "hf_search", "query": query, "models": [], "datasets": []}
        for repo_type in ("models", "datasets"):
            try:
                self.limiter.wait("huggingface", 0.5)
                response = self._proxied.get(
                    f"https://huggingface.co/api/{repo_type}",
                    params={"search": query, "limit": limit, "sort": "downloads", "direction": -1},
                )
                if response.status_code == 200:
                    for item in response.json()[:limit]:
                        result[repo_type].append(
                            {
                                "id": item.get("id"),
                                "downloads": item.get("downloads"),
                                "likes": item.get("likes"),
                                "tags": (item.get("tags") or [])[:8],
                            }
                        )
            except Exception as exc:  # noqa: BLE001
                result.setdefault("errors", []).append(f"{repo_type}: {str(exc)[:150]}")
        self.caches["hf_search"].put(key, result)
        return result

    def github_search(self, query: str, *, limit: int = 3) -> dict[str, Any]:
        """Repository search for candidates without a URL (v1's agent found many
        paper-released repos this way; the URL is often absent from the paper text)."""
        key = normalize_ws(query).lower()
        cached = self.caches["github_search"].get(key)
        if cached is not None:
            return cached
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "p4a-layer4-v2/1.0"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        result: dict[str, Any] = {"kind": "github_search", "query": query, "repositories": []}
        try:
            # search API has its own, much tighter rate limit (30/min with token)
            self.limiter.wait("github_search", 2.5 if self.github_token else 8.0)
            response = self._proxied.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "per_page": limit},
                headers=headers,
            )
            result["status_code"] = response.status_code
            if response.status_code == 200:
                for item in (response.json().get("items") or [])[:limit]:
                    result["repositories"].append(
                        {
                            "full_name": item.get("full_name"),
                            "html_url": item.get("html_url"),
                            "description": normalize_ws(str(item.get("description") or ""))[:300],
                            "stars": item.get("stargazers_count"),
                            "license": ((item.get("license") or {}).get("spdx_id") or "") if isinstance(item.get("license"), dict) else "",
                            "pushed_at": item.get("pushed_at"),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)[:200]
        self.caches["github_search"].put(key, result)
        return result

    # ---------------- arXiv ----------------

    @staticmethod
    def _norm_title(title: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()

    def arxiv_by_title(self, title: str) -> dict[str, Any]:
        key = self._norm_title(title)
        cached = self.caches["arxiv"].get(key)
        if cached is not None:
            return cached
        result: dict[str, Any] = {"kind": "arxiv", "query_title": title, "matched": False}
        query = f'ti:"{title}"'
        params = {"search_query": query, "max_results": "5"}
        api = "https://export.arxiv.org/api/query"
        response = None
        for client_name, client in (("direct", self._direct), ("proxy", self._proxied)):
            try:
                self.limiter.wait("arxiv", 3.0)
                response = client.get(api, params=params)
                if response.status_code == 200:
                    result["via"] = client_name
                    break
            except Exception as exc:  # noqa: BLE001
                result["error"] = str(exc)[:200]
                response = None
        if response is not None and response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                want = self._norm_title(title)
                for entry in root.findall(f"{_ATOM}entry"):
                    entry_title = normalize_ws(entry.findtext(f"{_ATOM}title") or "")
                    if self._norm_title(entry_title) != want:
                        continue
                    id_url = entry.findtext(f"{_ATOM}id") or ""
                    match = re.search(r"abs/([^v]+)(v\d+)?$", id_url)
                    result.update(
                        {
                            "matched": True,
                            "arxiv_id": match.group(1) if match else "",
                            "version": (match.group(2) or "") if match else "",
                            "url": id_url,
                            "title": entry_title,
                            "authors": [
                                normalize_ws(a.findtext(f"{_ATOM}name") or "")
                                for a in entry.findall(f"{_ATOM}author")
                            ][:20],
                            "submitted": entry.findtext(f"{_ATOM}published") or "",
                            "updated": entry.findtext(f"{_ATOM}updated") or "",
                            "primary_category": (
                                entry.find("{http://arxiv.org/schemas/atom}primary_category").get("term")
                                if entry.find("{http://arxiv.org/schemas/atom}primary_category") is not None
                                else ""
                            ),
                            "categories": [c.get("term") for c in entry.findall(f"{_ATOM}category")][:8],
                            "abstract": normalize_ws(entry.findtext(f"{_ATOM}summary") or "")[:ABSTRACT_SNIPPET_CHARS],
                        }
                    )
                    break
            except ET.ParseError as exc:
                result["error"] = f"atom parse: {exc}"
        self.caches["arxiv"].put(key, result)
        return result

    # ---------------- generic URL ----------------

    def url_probe(self, url: str) -> dict[str, Any]:
        key = normalize_url(url)
        cached = self.caches["url"].get(key)
        if cached is not None:
            return cached
        result: dict[str, Any] = {"kind": "url", "input": url}
        try:
            self.limiter.wait("url", 0.5)
            response = self._proxied.head(key, headers={"User-Agent": "p4a-layer4-v2/1.0"})
            if response.status_code in (403, 405, 501):
                self.limiter.wait("url", 0.5)
                response = self._proxied.get(
                    key, headers={"User-Agent": "p4a-layer4-v2/1.0", "Range": "bytes=0-20000"}
                )
            result["status_code"] = response.status_code
            result["final_url"] = str(response.url)
            result["status"] = "available" if response.status_code < 400 else (
                "missing" if response.status_code in (404, 410) else "unknown"
            )
            content_type = response.headers.get("content-type", "")
            result["content_type"] = content_type.split(";")[0]
            if "html" in content_type and response.request.method == "GET":
                match = re.search(r"<title[^>]*>(.*?)</title>", response.text[:20000], re.I | re.S)
                if match:
                    result["title"] = normalize_ws(match.group(1))[:200]
        except Exception as exc:  # noqa: BLE001
            result["status"] = "unknown"
            result["error"] = str(exc)[:200]
        self.caches["url"].put(key, result)
        return result

    # ---------------- per-paper driver ----------------

    def resolve_paper(self, *, paper_id: str, paper_dir: Path) -> dict[str, Any]:
        candidates = read_json(paper_dir / "semantic_candidates.json")
        index = read_json(paper_dir / "paper_index.json")

        resolution: dict[str, Any] = {
            "paper_id": paper_id,
            "resolved_at": now_iso(),
            "arxiv": {},
            "resources": [],
            "search_results": {},
        }

        title = str(index.get("title") or "")
        if title:
            resolution["arxiv"] = self.arxiv_by_title(title)

        seen_searches: set[str] = set()
        for candidate in candidates.get("resource_candidates") or []:
            name = candidate.get("name") or ""
            url = str(candidate.get("url") or "").strip()
            entry: dict[str, Any] = {"name": name, "url": url}
            if url:
                kind, key = classify_url(url)
                if kind == "github":
                    entry["resolution"] = self.github(key)
                elif kind == "huggingface":
                    entry["resolution"] = self.huggingface(key)
                elif kind == "arxiv_link":
                    entry["resolution"] = {"kind": "arxiv_link", "status": "available", "note": "arxiv link, not probed"}
                else:
                    entry["resolution"] = self.url_probe(key)
            else:
                hints = [h for h in (candidate.get("search_hints") or [name]) if h][:2]
                for hint in hints:
                    normalized = normalize_ws(hint).lower()
                    if normalized in seen_searches:
                        continue
                    seen_searches.add(normalized)
                    resolution["search_results"][hint] = {
                        "hf_search": self.hf_search(hint),
                        "github_search": self.github_search(hint),
                    }
                entry["resolution"] = {"kind": "none", "status": "unknown", "note": "no URL; see search_results"}
            resolution["resources"].append(entry)

        write_json(paper_dir / "external_resolution.json", resolution)
        return {
            "paper_id": paper_id,
            "arxiv_matched": bool((resolution["arxiv"] or {}).get("matched")),
            "resource_count": len(resolution["resources"]),
            "search_count": len(resolution["search_results"]),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Layer4 v2 external verification (no LLM).")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_LAYER4_V2_ROOT)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_V2_CACHE_ROOT)
    parser.add_argument("--refresh-cache", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    resolver = ExternalResolver(cache_root=args.cache_root, refresh=args.refresh_cache)
    summary = resolver.resolve_paper(paper_id=args.paper_id, paper_dir=args.output_root / args.paper_id)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
