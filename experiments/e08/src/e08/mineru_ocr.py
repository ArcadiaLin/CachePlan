"""
使用 vllm 部署的 openai completion 兼容的 mineru 服务进行 ocr。

两级 API：

- `aocr_pdf(pdf)` —— 只要 Markdown，不落盘、不留图。
- `aocr_bundle(pdf, out_root)` —— 完整产出目录：md + blocks.json + images/ + meta.json。
  图块的像素只在服务端抽取时于内存里裁过一次（mineru_vl_utils 不写任何文件），
  这里按同样的 bbox 自己裁一遍存下来，并把逐页 block 与溯源信息一并落盘。
"""


from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from functools import lru_cache
from importlib.metadata import version as _pkg_version
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

# image / chart 块默认不送抽取（mineru_client.py 的 skip_list），那样图既没有像素也没有
# 描述，md 里连占位符都不会留。要"完整产出"就得打开它：打开后 flowchart → mermaid、
# chart → markdown 表、pure_table → HTML、natural_image → caption。
DEFAULT_IMAGE_ANALYSIS = True

# 落盘裁图的块类型。表格也裁：抽出来的 HTML 可能错，裁图是核对用的证据。
CROP_TYPES = ("image", "chart", "table")
# 在 md 里直接插 ![]() 的类型；table 的正文保留 HTML，裁图用注释指路，免得表格被图盖住。
MD_INLINE_TYPES = ("image", "chart")

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
    # mutool 不会替我们建目录；调用方给的可能是临时目录下的子目录。
    outdir.mkdir(parents=True, exist_ok=True)
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _mutool_version() -> str:
    """渲染器版本进 meta：换了 mupdf 版本，页图可能有像素级差异。"""
    proc = subprocess.run(["mutool", "-v"], capture_output=True, text=True)
    return (proc.stderr or proc.stdout).strip().splitlines()[0] if (proc.stderr or proc.stdout) else "unknown"


def _crop_block(page: Image.Image, bbox: list[float], angle: int | None) -> Image.Image:
    """按归一化 bbox 从页图裁块。bbox 与 dpi 无关，所以裁图可以用比 OCR 更高的 dpi。"""
    width, height = page.size
    x1, y1, x2, y2 = bbox
    box = (
        max(0, int(x1 * width)),
        max(0, int(y1 * height)),
        min(width, int(x2 * width) + 1),
        min(height, int(y2 * height) + 1),
    )
    crop = page.crop(box)
    # 与 mineru_vl_utils 送抽取时的处理一致（table_image_processor._rotate_image_by_angle）。
    if angle in (90, 180, 270):
        crop = crop.rotate(angle, expand=True)
    return crop


def _blocks_to_md(blocks: list[dict], crops: dict[int, str]) -> str:
    """把一页的 block 拼成 Markdown。

    不自己实现拼接：改写 content 后交给 mineru_vl_utils 的 `json2md`，这样 `merge_prev`
    （跨栏续写的段落合并）等行为与只要 md 的路径完全一致。改写在副本上做，
    `blocks.json` 里保留服务返回的原样。
    """
    patched: list[dict] = []
    for idx, block in enumerate(blocks):
        block = dict(block)
        rel = crops.get(idx)
        if rel is not None:
            content = block.get("content") or ""
            if block.get("type") in MD_INLINE_TYPES:
                alt = block.get("sub_type") or block.get("type") or "image"
                block["content"] = f"![{alt}]({rel})" + (f"\n\n{content}" if content else "")
            else:
                block["content"] = (content + f"\n\n<!-- crop: {rel} -->").strip()
        patched.append(block)
    return json2md(patched)


async def _aextract_pages(
    pdf: Path,
    workdir: Path,
    *,
    url: str,
    dpi: int,
    concurrency: int,
    http_timeout: int,
    image_analysis: bool,
) -> tuple[list[Path], list[list[dict]]]:
    """渲染 + 抽取。返回 (页图路径, 逐页 block)。抽取完就关掉页图，裁图时再按需重开。"""
    client = _client(url, concurrency, http_timeout)
    pages = _render_pages(pdf, workdir, dpi)
    images = [Image.open(path).convert("RGB") for path in pages]
    try:
        results = await client.aio_batch_two_step_extract(images, image_analysis=image_analysis)
    finally:
        for im in images:
            im.close()
    return pages, [list(result) for result in results]


def _prepare(pdf: str | Path, server_url: str | None, env_file: str | Path | None) -> tuple[Path, str, str]:
    pdf = Path(pdf)
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    if shutil.which("mutool") is None:
        raise RuntimeError("找不到 mutool（PDF 渲染）：Debian/Ubuntu 装 mupdf-tools")
    url, origin = resolve_server_url(server_url, Path(env_file) if env_file else None)
    return pdf, url, origin


async def aocr_pdf(
    pdf: str | Path,
    *,
    server_url: str | None = None,
    env_file: str | Path | None = None,
    dpi: int = DEFAULT_DPI,
    concurrency: int = DEFAULT_CONCURRENCY,
    http_timeout: int = DEFAULT_HTTP_TIMEOUT,
    image_analysis: bool = DEFAULT_IMAGE_ANALYSIS,
) -> str:
    """OCR 一篇 PDF，返回 Markdown，不落盘。异步版，可在 notebook 里直接 await。

    图块只留描述（image_analysis 的产物），不留像素 —— 要图文件用 `aocr_bundle`。
    """
    pdf, url, _origin = _prepare(pdf, server_url, env_file)
    with tempfile.TemporaryDirectory(prefix="mineru_") as td:
        _pages, pages_blocks = await _aextract_pages(
            pdf, Path(td), url=url, dpi=dpi, concurrency=concurrency,
            http_timeout=http_timeout, image_analysis=image_analysis,
        )
    # 空页（无 block，或整页只有被丢弃的块）不参与拼接，否则尾部会灌一串空行。
    parts = [_blocks_to_md(blocks, {}) for blocks in pages_blocks]
    return "\n\n".join(part for part in parts if part.strip())


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


async def aocr_bundle(
    pdf: str | Path,
    out_root: str | Path,
    *,
    server_url: str | None = None,
    env_file: str | Path | None = None,
    dpi: int = DEFAULT_DPI,
    crop_dpi: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    http_timeout: int = DEFAULT_HTTP_TIMEOUT,
    image_analysis: bool = DEFAULT_IMAGE_ANALYSIS,
    keep_page_renders: bool = False,
    overwrite: bool = False,
) -> Path:
    """OCR 一篇 PDF，把完整产出写进 `out_root/<pdf 主名>/`，返回该目录。

        <stem>.md      正文；image/chart 处插 ![](images/...)，table 的裁图用注释指路
        blocks.json    逐页 block 原样（type/bbox/angle/content/sub_type）+ 本页裁图清单
        images/        image/chart/table 块的裁图（见 CROP_TYPES）
        pages/         整页渲染，仅当 keep_page_renders=True
        meta.json      溯源：pdf sha256、页数、dpi、服务地址、模型、版本、耗时、计数

    `crop_dpi` 缺省同 `dpi`；给更大的值会为裁图单独重渲一遍页面（bbox 归一化，与 dpi 无关）。
    目录已存在且非空时抛 `FileExistsError`，除非 `overwrite=True` —— 重跑一篇要花几分钟，
    不默认覆盖。
    """
    pdf, url, origin = _prepare(pdf, server_url, env_file)
    bundle = Path(out_root) / pdf.stem
    if bundle.exists() and any(bundle.iterdir()) and not overwrite:
        raise FileExistsError(f"产出目录已存在且非空：{bundle}（要重跑请给 overwrite=True）")

    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with tempfile.TemporaryDirectory(prefix="mineru_") as td:
        work = Path(td)
        pages, pages_blocks = await _aextract_pages(
            pdf, work / "ocr", url=url, dpi=dpi, concurrency=concurrency,
            http_timeout=http_timeout, image_analysis=image_analysis,
        )

        # 裁图源：同 dpi 就复用 OCR 用过的页图，否则单独重渲一遍。
        effective_crop_dpi = crop_dpi or dpi
        crop_pages = pages if effective_crop_dpi == dpi else _render_pages(pdf, work / "crop", effective_crop_dpi)
        if len(crop_pages) != len(pages):
            raise RuntimeError(
                f"裁图用的渲染页数（{len(crop_pages)}）与 OCR 用的（{len(pages)}）不一致，"
                f"拒绝按序号对应"
            )

        images_dir = bundle / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        page_records: list[dict] = []
        md_parts: list[str] = []
        type_counts: dict[str, int] = {}
        crop_count = 0

        for page_no, (blocks, crop_src) in enumerate(zip(pages_blocks, crop_pages), start=1):
            crops: dict[int, str] = {}
            crop_records: list[dict] = []
            visual = [(idx, b) for idx, b in enumerate(blocks) if b.get("type") in CROP_TYPES]
            if visual:
                with Image.open(crop_src) as page_img:
                    page_img = page_img.convert("RGB")
                    for idx, block in visual:
                        crop = _crop_block(page_img, block["bbox"], block.get("angle"))
                        name = f"p{page_no:03d}-b{idx:02d}-{block['type']}.png"
                        crop.save(images_dir / name)
                        rel = f"images/{name}"
                        crops[idx] = rel
                        crop_records.append({
                            "block": idx,
                            "type": block["type"],
                            "sub_type": block.get("sub_type"),
                            "bbox": block["bbox"],
                            "angle": block.get("angle"),
                            "path": rel,
                            "size": list(crop.size),
                        })
                        crop.close()
            crop_count += len(crop_records)

            for block in blocks:
                btype = block.get("type", "unknown")
                type_counts[btype] = type_counts.get(btype, 0) + 1

            page_records.append({"page": page_no, "blocks": blocks, "crops": crop_records})
            md_parts.append(_blocks_to_md(blocks, crops))

        if keep_page_renders:
            pages_dir = bundle / "pages"
            pages_dir.mkdir(parents=True, exist_ok=True)
            for page_no, src in enumerate(crop_pages, start=1):
                shutil.copyfile(src, pages_dir / f"p{page_no:03d}.png")

    md_path = bundle / f"{pdf.stem}.md"
    md_path.write_text("\n\n".join(part for part in md_parts if part.strip()) + "\n", encoding="utf-8")

    (bundle / "blocks.json").write_text(
        json.dumps({"pdf": pdf.name, "page_count": len(page_records), "pages": page_records},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    meta = {
        "pdf": {"name": pdf.name, "path": str(pdf.resolve()),
                "bytes": pdf.stat().st_size, "sha256": _sha256(pdf)},
        "page_count": len(page_records),
        "params": {
            "dpi": dpi,
            "crop_dpi": crop_dpi or dpi,
            "image_analysis": image_analysis,
            "concurrency": concurrency,
            "http_timeout": http_timeout,
            "crop_types": list(CROP_TYPES),
            "keep_page_renders": keep_page_renders,
        },
        "service": {"server_url": url, "url_origin": origin, "model": MODEL},
        "versions": {
            "mineru_vl_utils": _pkg_version("mineru-vl-utils"),
            "mutool": _mutool_version(),
            "python": platform.python_version(),
        },
        "run": {"started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "elapsed_s": round(time.monotonic() - started, 1)},
        "counts": {"blocks": sum(len(r["blocks"]) for r in page_records),
                   "by_type": dict(sorted(type_counts.items())),
                   "crops": crop_count},
        "outputs": {"md": md_path.name, "md_sha256": _sha256(md_path),
                    "blocks": "blocks.json", "images": crop_count,
                    "pages": "pages/" if keep_page_renders else None},
        # 口径：OCR 结果是机器抽取的文本，不是事实；图的描述同理。核对要回 PDF 原文。
        "caveat": "machine-extracted; verify numbers against the PDF",
    }
    (bundle / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return bundle


def ocr_bundle(pdf: str | Path, out_root: str | Path, **kwargs) -> Path:
    """写完整产出目录。同步版，参数同 `aocr_bundle`。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(aocr_bundle(pdf, out_root, **kwargs))
    raise RuntimeError(
        "当前已在事件循环里（Jupyter 就是），asyncio.run 会失败："
        "改用 `bundle = await aocr_bundle(pdf, out_root)`"
    )
