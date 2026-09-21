"""单篇 PDF → Markdown。

给别的实验调用的一个函数：传入一个 PDF，拿回 OCR 出来的 Markdown 字符串。
不落盘、不批处理、不记账 —— 输出写到哪、怎么记溯源，由调用方按自己的实验决定。

一篇的内部流程：
  1. `mutool draw` 按 DPI 把整篇渲染成 PNG（临时目录，用完即删）
  2. MinerUClient 两步抽取（版面检测 + 逐块内容），页间并发由 concurrency 控制
  3. 每页 json2md，页与页之间用空行拼接

服务地址默认从 experiments/utils/mineru/.env 的 mineru_service 读，见 service.py。
导入名是 utils.mineru（见 pyproject 里关于命名空间包的说明）。
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

# mineru_vl_utils 默认把 loguru 开在 DEBUG，逐块抽取会刷屏；导入它之前先压到 INFO。
from loguru import logger as _loguru_logger

_loguru_logger.remove()
_loguru_logger.add(lambda m: print(m, file=sys.stderr, flush=True), level="INFO")

from PIL import Image  # noqa: E402
from mineru_vl_utils import MinerUClient  # noqa: E402
from mineru_vl_utils.post_process import json2md  # noqa: E402

from .service import resolve_server_url  # noqa: E402

MODEL = "mineru"
DEFAULT_DPI = 200
DEFAULT_CONCURRENCY = 24
DEFAULT_HTTP_TIMEOUT = 900


@lru_cache(maxsize=8)
def _client(server_url: str, concurrency: int, http_timeout: int) -> MinerUClient:
    """按参数缓存客户端：构造时会向服务端核对模型名，连着跑多篇不必每篇握手一次。"""
    try:
        return MinerUClient(
            backend="http-client",
            server_url=server_url,
            model_name=MODEL,
            image_analysis=False,
            max_concurrency=concurrency,
            use_tqdm=False,
            http_timeout=http_timeout,
        )
    except Exception as exc:
        raise RuntimeError(f"连不上 MinerU 服务 {server_url}：{exc!r}") from exc


def _render_pages(pdf: Path, outdir: Path, dpi: int) -> list[Path]:
    # 用列表参数直接 exec，不过 shell：论文文件名里常有空格、冒号、括号。
    cmd = ["mutool", "draw", "-q", "-r", str(dpi), "-o", str(outdir / "pg-%04d.png"), str(pdf)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mutool 渲染 {pdf.name} 失败（退出码 {proc.returncode}）："
                           f"{proc.stderr.strip()[:300]}")
    pages = sorted(outdir.glob("pg-*.png"))
    if not pages:
        raise RuntimeError(f"mutool 没有从 {pdf.name} 渲染出任何页面")
    return pages


async def aocr_pdf(
    pdf: str | Path,
    *,
    server_url: str | None = None,
    env_file: str | Path | None = None,
    dpi: int = DEFAULT_DPI,
    concurrency: int = DEFAULT_CONCURRENCY,
    http_timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> str:
    """OCR 一篇 PDF，返回 Markdown。异步版，可在 notebook 里直接 await。"""
    pdf = Path(pdf)
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    if shutil.which("mutool") is None:
        raise RuntimeError("找不到 mutool（PDF 渲染）：Debian/Ubuntu 装 mupdf-tools")

    url, _origin = resolve_server_url(server_url, Path(env_file) if env_file else None)
    client = _client(url, concurrency, http_timeout)

    with tempfile.TemporaryDirectory(prefix="mineru_") as td:
        pages = _render_pages(pdf, Path(td), dpi)
        images = [Image.open(p).convert("RGB") for p in pages]
        try:
            results = await client.aio_batch_two_step_extract(images)
        finally:
            for im in images:
                im.close()

    return "\n\n".join(json2md(r) for r in results)


def ocr_pdf(pdf: str | Path, **kwargs) -> str:
    """OCR 一篇 PDF，返回 Markdown。同步版，参数同 `aocr_pdf`。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(aocr_pdf(pdf, **kwargs))
    raise RuntimeError(
        "当前已在事件循环里（Jupyter 就是），asyncio.run 会失败："
        "改用 `md = await aocr_pdf(pdf)`"
    )
