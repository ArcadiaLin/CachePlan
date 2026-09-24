"""Tests for image localization (download + link rewriting)."""

from __future__ import annotations

import asyncio

from arxiv2md import images as images_mod
from arxiv2md.images import _image_filename, localize_images


def test_image_filename_sanitizes_and_dedupes() -> None:
    used: set[str] = set()
    assert _image_filename("https://x.org/a/fig.png", used) == "fig.png"
    assert _image_filename("https://x.org/b/fig.png", used) == "fig-2.png"
    assert _image_filename("https://x.org/a/fig 1.png?v=3", used) == "fig_1.png"
    assert _image_filename("https://x.org/a/", used) == "a"  # falls back to last path segment


class _FakeResponse:
    content = b"PNG-BYTES"

    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    def __init__(self, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url: str) -> _FakeResponse:
        return _FakeResponse()


def test_localize_images_downloads_and_rewrites(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(images_mod.httpx, "AsyncClient", _FakeClient)
    md = "![a](https://arxiv.org/html/x/fig1.png)\n![b](https://arxiv.org/html/x/fig2.svg)"
    images_dir = tmp_path / "paper.images"

    out = asyncio.run(localize_images(md, images_dir, link_prefix="paper.images"))

    assert (images_dir / "fig1.png").read_bytes() == b"PNG-BYTES"
    assert (images_dir / "fig2.svg").exists()
    assert "![a](paper.images/fig1.png)" in out
    assert "![b](paper.images/fig2.svg)" in out


def test_localize_images_noop_without_remote_images(tmp_path) -> None:
    md = "![local](paper.images/fig.png)\nplain text"
    out = asyncio.run(localize_images(md, tmp_path / "paper.images"))
    assert out == md
    assert not (tmp_path / "paper.images").exists()


def test_localize_images_handles_escaped_brackets_in_alt(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(images_mod.httpx, "AsyncClient", _FakeClient)
    md = "![Figure 3: see Section C.1 for $\\[0,1\\]$.](https://arxiv.org/html/x/fig3.png)"

    out = asyncio.run(localize_images(md, tmp_path / "paper.images", link_prefix="paper.images"))

    assert out == "![Figure 3: see Section C.1 for $\\[0,1\\]$.](paper.images/fig3.png)"


class _FlakyClient(_FakeClient):
    async def get(self, url: str) -> _FakeResponse:
        if "bad" in url:
            raise images_mod.httpx.ConnectError("boom")
        return _FakeResponse()


def test_localize_images_keeps_remote_url_on_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(images_mod.httpx, "AsyncClient", _FlakyClient)
    md = "![a](https://arxiv.org/html/x/good.png)\n![b](https://arxiv.org/html/x/bad.png)"

    out = asyncio.run(localize_images(md, tmp_path / "paper.images", link_prefix="paper.images"))

    assert "![a](paper.images/good.png)" in out
    assert "![b](https://arxiv.org/html/x/bad.png)" in out
