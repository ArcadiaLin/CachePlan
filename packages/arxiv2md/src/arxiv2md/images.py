"""Download remote images referenced in Markdown and rewrite links to local paths."""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from arxiv2md.config import ARXIV2MD_FETCH_TIMEOUT_S, ARXIV2MD_USER_AGENT
from arxiv2md.utils.logging_config import get_logger

logger = get_logger(__name__)

# Alt text may contain backslash-escaped brackets (see markdown._escape_markdown_alt).
_MD_IMAGE_RE = re.compile(r"!\[((?:\\.|[^\\\]])*)\]\((https?://[^)\s]+)\)")
_SAFE_FILENAME_RE = re.compile(r"[^\w.\-]+")


async def localize_images(markdown: str, images_dir: Path, *, link_prefix: str | None = None) -> str:
    """Download every remote ``![](http...)`` image into ``images_dir`` and rewrite its link.

    Links are rewritten to ``<link_prefix>/<filename>``; ``link_prefix`` defaults to
    the directory's name, which assumes the Markdown file sits next to it. An
    image that fails to download keeps its remote URL and is logged; it does
    not abort the conversion.
    """
    urls: list[str] = []
    for match in _MD_IMAGE_RE.finditer(markdown):
        if match.group(2) not in urls:
            urls.append(match.group(2))
    if not urls:
        return markdown

    images_dir.mkdir(parents=True, exist_ok=True)
    prefix = link_prefix if link_prefix is not None else images_dir.name

    url_to_local: dict[str, str] = {}
    used_names: set[str] = set()
    timeout = httpx.Timeout(ARXIV2MD_FETCH_TIMEOUT_S)
    headers = {"User-Agent": ARXIV2MD_USER_AGENT}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        for url in urls:
            name = _image_filename(url, used_names)
            try:
                response = await client.get(url)
                response.raise_for_status()
                (images_dir / name).write_bytes(response.content)
            except (httpx.HTTPError, OSError) as exc:
                logger.warning("Image download failed, keeping remote URL {}: {}", url, exc)
                continue
            url_to_local[url] = f"{prefix}/{name}"

    failed = len(urls) - len(url_to_local)
    if failed:
        logger.warning("{} of {} images kept their remote URL", failed, len(urls))

    def _sub(match: re.Match) -> str:
        url = match.group(2)
        return f"![{match.group(1)}]({url_to_local.get(url, url)})"

    return _MD_IMAGE_RE.sub(_sub, markdown)


def _image_filename(url: str, used_names: set[str]) -> str:
    """Derive a filesystem-safe, collision-free filename from an image URL."""
    name = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] or "image"
    name = _SAFE_FILENAME_RE.sub("_", name)
    stem, dot, ext = name.rpartition(".")
    if not stem:
        stem, dot, ext = ext, "", ""
    candidate, counter = name, 2
    while candidate in used_names:
        candidate = f"{stem}-{counter}{dot}{ext}" if dot else f"{name}-{counter}"
        counter += 1
    used_names.add(candidate)
    return candidate
