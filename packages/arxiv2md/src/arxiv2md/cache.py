"""Cache eviction and cleanup utilities."""

from __future__ import annotations

import shutil
from pathlib import Path

from arxiv2md.config import (
    ARXIV2MD_CACHE_MAX_SIZE_MB,
    ARXIV2MD_CACHE_PATH,
    ARXIV2MD_CACHE_TTL_SECONDS,
)
from arxiv2md.utils.logging_config import get_logger

logger = get_logger(__name__)


def _get_cache_subdirs() -> list[Path]:
    """Return all immediate subdirectories in the cache directory."""
    if not ARXIV2MD_CACHE_PATH.is_dir():
        return []
    return [p for p in ARXIV2MD_CACHE_PATH.iterdir() if p.is_dir()]


def _dir_size_bytes(path: Path) -> int:
    """Return total size of all files in a directory tree."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _dir_mtime(path: Path) -> float:
    """Return the most recent mtime of any file in the directory."""
    mtimes = [f.stat().st_mtime for f in path.rglob("*") if f.is_file()]
    return max(mtimes) if mtimes else 0.0


def get_cache_size_bytes() -> int:
    """Return the total size of the cache directory in bytes."""
    return sum(_dir_size_bytes(d) for d in _get_cache_subdirs())


def purge_expired_entries() -> int:
    """Remove cache entries older than the configured TTL.

    Returns the number of entries removed.
    """
    if ARXIV2MD_CACHE_TTL_SECONDS <= 0:
        return 0

    import time

    now = time.time()
    removed = 0

    for subdir in _get_cache_subdirs():
        mtime = _dir_mtime(subdir)
        if mtime > 0 and (now - mtime) > ARXIV2MD_CACHE_TTL_SECONDS:
            shutil.rmtree(subdir, ignore_errors=True)
            removed += 1

    if removed:
        logger.info("Purged %d expired cache entries", removed)
    return removed


def evict_if_needed() -> int:
    """Evict oldest cache entries until total size is under the configured max.

    Returns the number of entries removed.
    """
    max_bytes = ARXIV2MD_CACHE_MAX_SIZE_MB * 1024 * 1024
    if max_bytes <= 0:
        return 0

    subdirs = _get_cache_subdirs()
    total_size = sum(_dir_size_bytes(d) for d in subdirs)

    if total_size <= max_bytes:
        return 0

    # Sort by mtime ascending (oldest first)
    subdirs.sort(key=_dir_mtime)

    removed = 0
    for subdir in subdirs:
        if total_size <= max_bytes:
            break
        entry_size = _dir_size_bytes(subdir)
        shutil.rmtree(subdir, ignore_errors=True)
        total_size -= entry_size
        removed += 1

    if removed:
        logger.info(
            "Evicted %d cache entries to stay under %dMB limit",
            removed,
            ARXIV2MD_CACHE_MAX_SIZE_MB,
        )
    return removed


def cleanup_cache() -> None:
    """Run a full cache cleanup: purge expired entries, then evict by size."""
    purge_expired_entries()
    evict_if_needed()
