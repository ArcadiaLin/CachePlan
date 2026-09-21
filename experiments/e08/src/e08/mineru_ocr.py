"""
使用 vllm 部署的 openai completion 兼容的 mineru 服务进行 ocr
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
import os

ENV_KEY = "MINERU_SERVICE"
PKG_ROOT = Path(__file__).resolve().parents[2]  # experiments/e08

_loguru_logger.remove()
_loguru_logger.add(lambda m: print(m, file=sys.stderr, flush=True), level="INFO")

from PIL import Image  # noqa: E402
from mineru_vl_utils import MinerUClient  # noqa: E402
from mineru_vl_utils.post_process import json2md  # noqa: E402

MODEL = "mineru"
DEFAULT_DPI = 200
DEFAULT_CONCURRENCY = 24
DEFAULT_HTTP_TIMEOUT = 900

def parse_env_file(path: Path) -> dict[str, str]:
    """极简 KEY=VALUE 解析：跳过空行与 # 注释，剥掉可选引号。"""
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        out[key.strip()] = value.strip().strip("\"'")
    return out


def env_file_candidates(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    return [Path.cwd() / ".env", PKG_ROOT / ".env"]


def resolve_server_url(explicit: str | None = None, env_file: Path | None = None) -> tuple[str, str]:
    """返回 (服务地址, 来源说明)。来源说明进日志，便于事后确认跑的是哪个服务。"""
    if explicit:
        return explicit.rstrip("/"), "server_url 参数"

    for key in (ENV_KEY.upper(), ENV_KEY.lower()):
        if os.environ.get(key):
            return os.environ[key].rstrip("/"), f"环境变量 {key}"

    for path in env_file_candidates(env_file):
        if not path.is_file():
            continue
        # 键名在文件里不区分大小写：两侧都小写后再比，别让 ENV_KEY 的写法决定成败。
        values = {k.lower(): v for k, v in parse_env_file(path).items()}
        if values.get(ENV_KEY.lower()):
            return values[ENV_KEY.lower()].rstrip("/"), str(path)

    tried = ", ".join(str(p) for p in env_file_candidates(env_file))
    raise RuntimeError(
        f"找不到 MinerU 服务地址：server_url= 未给，环境变量 {ENV_KEY} 未设，"
        f"下列 .env 里也没有 {ENV_KEY}= —— {tried}"
    )



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
