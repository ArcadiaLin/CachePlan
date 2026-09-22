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

from . import mineru_assemble as assemble  # noqa: E402

MODEL = "mineru"
DEFAULT_DPI = 200
DEFAULT_CONCURRENCY = 24
DEFAULT_HTTP_TIMEOUT = 900

# image / chart 块默认不送抽取（mineru_client.py 的 skip_list），那样图既没有像素也没有
# 描述，md 里连占位符都不会留。要"完整产出"就得打开它：打开后 flowchart → mermaid、
# chart → markdown 表、pure_table → HTML、natural_image → caption。
DEFAULT_IMAGE_ANALYSIS = True

# 裁哪些块、md 怎么插图、caption 怎么配对，全在 mineru_assemble 里（移植自官方
# mineru 的 block → middle_json → md 那条链）。这里只管服务侧的参数。

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
    # 走同一套装配（含 caption 归属、版面附属物分流、标题与公式的规范化），
    # 只是没有裁图可引用，所以图块只留 <details> 里的描述。
    return assemble.to_markdown(assemble.assemble(pages_blocks), crop_paths={})


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

        <stem>.md          正文：caption 在图旁、模型读图的描述在 <details> 里、
                           标题带 #、公式用 $ / $$、页眉页脚不在正文
        blocks.json        服务返回的逐页 block 原样，不做任何改写
        content_list.json  装配后的扁平清单（官方 content_list 形态）：img_path、
                           content、*_caption、*_footnote、sub_type、sub_images、bbox
        images/            每个视觉主体一张裁图（多图容器裁整图，不裁碎片）
        pages/             整页渲染，仅当 keep_page_renders=True
        meta.json          溯源：pdf sha256、页数、dpi、服务地址、模型、版本、耗时、计数

    装配逻辑在 `mineru_assemble`，移植自官方 mineru（见该模块 docstring 的参照位置）。
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

        pages_assembled = assemble.assemble(pages_blocks)
        plan = assemble.crop_plan(pages_assembled)

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

        crop_paths: dict[tuple[int, int], str] = {}
        crop_records: list[dict] = []
        by_page: dict[int, list[dict]] = {}
        for entry in plan:
            by_page.setdefault(entry["page"], []).append(entry)

        for page_no, entries in sorted(by_page.items()):
            with Image.open(crop_pages[page_no - 1]) as page_img:
                page_img = page_img.convert("RGB")
                for entry in entries:
                    crop = _crop_block(page_img, entry["bbox"], entry.get("angle"))
                    crop.save(images_dir / entry["name"])
                    rel = f"images/{entry['name']}"
                    crop_paths[(page_no, entry["block"])] = rel
                    crop_records.append({**{k: entry[k] for k in ("page", "block", "type", "bbox", "angle")},
                                         "path": rel, "size": list(crop.size)})
                    crop.close()

        if keep_page_renders:
            pages_dir = bundle / "pages"
            pages_dir.mkdir(parents=True, exist_ok=True)
            for page_no, src_path in enumerate(crop_pages, start=1):
                shutil.copyfile(src_path, pages_dir / f"p{page_no:03d}.png")

    md_path = bundle / f"{pdf.stem}.md"
    md_path.write_text(assemble.to_markdown(pages_assembled, crop_paths), encoding="utf-8")

    # 原样：任何清洗都不写回这里，它是回溯用的基准。
    (bundle / "blocks.json").write_text(
        json.dumps({"pdf": pdf.name, "page_count": len(pages_blocks),
                    "pages": [{"page": i, "blocks": blocks}
                              for i, blocks in enumerate(pages_blocks, start=1)],
                    "crops": crop_records},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    content_list = assemble.to_content_list(pages_assembled, crop_paths)
    (bundle / "content_list.json").write_text(
        json.dumps(content_list, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    assembled_counts = assemble.counts(pages_assembled)
    meta = {
        "pdf": {"name": pdf.name, "path": str(pdf.resolve()),
                "bytes": pdf.stat().st_size, "sha256": _sha256(pdf)},
        "page_count": len(pages_blocks),
        "params": {
            "dpi": dpi,
            "crop_dpi": effective_crop_dpi,
            "image_analysis": image_analysis,
            "concurrency": concurrency,
            "http_timeout": http_timeout,
            "keep_page_renders": keep_page_renders,
        },
        "service": {"server_url": url, "url_origin": origin, "model": MODEL},
        "versions": {
            "mineru_vl_utils": _pkg_version("mineru-vl-utils"),
            "mutool": _mutool_version(),
            "python": platform.python_version(),
            "assemble_ref": "MinerU 3.4.0 (references/repos/MinerU)",
        },
        "run": {"started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "elapsed_s": round(time.monotonic() - started, 1)},
        "counts": {
            "raw_blocks": sum(len(b) for b in pages_blocks),
            "raw_by_type": _count_types(pages_blocks),
            "crops": len(crop_records),
            **assembled_counts,
        },
        "outputs": {"md": md_path.name, "md_sha256": _sha256(md_path),
                    "blocks": "blocks.json", "content_list": "content_list.json",
                    "images": len(crop_records),
                    "pages": "pages/" if keep_page_renders else None},
        # 口径：OCR 结果是机器抽取的文本，不是事实；<details> 里的图表描述更是模型读图的
        # 产物，不可当实验数据引用。核对要回 PDF 原文。
        "caveat": "machine-extracted; figure/chart descriptions are model readings of the image",
    }
    (bundle / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return bundle


def _count_types(pages_blocks: list[list[dict]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for blocks in pages_blocks:
        for block in blocks:
            btype = block.get("type", "unknown")
            counts[btype] = counts.get(btype, 0) + 1
    return dict(sorted(counts.items()))


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
