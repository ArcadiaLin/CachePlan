#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/mineru/process_pdf_with_mineru.py /srv/datasets/p4a/data/raw/acl/2026/pdf/acl/2026.acl-demo.0.pdf --output-dir /srv/datasets/p4a/data/processed/mineru
import argparse
import json
import os
from glob import glob
from pathlib import Path

from PIL import Image
from mineru_vl_utils import MinerUClient


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SERVER_URL = "http://127.0.0.1:8004"


def load_project_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def configured_data_root() -> Path:
    value = os.environ.get("P4A_DATA_ROOT")
    if value:
        return Path(value)
    value = os.environ.get("DATA_ROOT") or os.environ.get("DATASET_ROOT")
    if value:
        root = Path(value)
        return root if root.name == "data" else root / "data"
    return Path("/srv/datasets/p4a/data")


load_project_env()
DEFAULT_DATA_ROOT = configured_data_root()
DEFAULT_OUTPUT_DIR = str(DEFAULT_DATA_ROOT / "processed/mineru")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render PDF pages to images and parse them with a local MinerU HTTP service."
    )
    parser.add_argument(
        "input",
        help="PDF file, directory containing PDFs, or glob pattern such as '/data/pdfs/*.pdf'.",
    )
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-concurrency", type=int, default=16)
    parser.add_argument("--image-analysis", action="store_true")
    parser.add_argument(
        "--pattern",
        default="*.pdf",
        help="Pattern used only when input is a directory.",
    )
    return parser.parse_args()


def require_pymupdf():
    try:
        import fitz
    except ImportError as exc:
        raise SystemExit(
            "PyMuPDF is required to render PDFs. Install it in this project env:\n"
            "  /root/lzx/projs/p4a/.venv/bin/python -m pip install pymupdf"
        ) from exc
    return fitz


def resolve_pdf_paths(input_path: str, pattern: str) -> list[Path]:
    path = Path(input_path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.glob(pattern))
    return [Path(item) for item in sorted(glob(input_path))]


def render_pdf_pages(pdf_path: Path, dpi: int):
    fitz = require_pymupdf()
    doc = fitz.open(pdf_path)
    try:
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            yield page_index + 1, image
    finally:
        doc.close()


def write_pdf_result(output_dir: Path, pdf_path: Path, pages: list[dict]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{pdf_path.stem}.mineru.json"
    payload = {
        "pdf": str(pdf_path),
        "page_count": len(pages),
        "pages": pages,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def process_pdf(
    client: MinerUClient,
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    batch_size: int,
    image_analysis: bool,
) -> Path:
    pages: list[dict] = []
    page_numbers: list[int] = []
    page_images: list[Image.Image] = []

    def flush_batch() -> None:
        if not page_images:
            return
        results = client.batch_two_step_extract(
            page_images,
            image_analysis=image_analysis,
        )
        for page_number, blocks in zip(page_numbers, results):
            pages.append({"page": page_number, "blocks": list(blocks)})
        page_numbers.clear()
        page_images.clear()

    for page_number, image in render_pdf_pages(pdf_path, dpi):
        page_numbers.append(page_number)
        page_images.append(image)
        if len(page_images) >= batch_size:
            flush_batch()

    flush_batch()
    return write_pdf_result(output_dir, pdf_path, pages)


def main() -> None:
    args = parse_args()
    pdf_paths = resolve_pdf_paths(args.input, args.pattern)
    pdf_paths = [path for path in pdf_paths if path.suffix.lower() == ".pdf"]
    if not pdf_paths:
        raise SystemExit(f"No PDF files found for input: {args.input}")

    output_dir = Path(args.output_dir)
    client = MinerUClient(
        backend="http-client",
        server_url=args.server_url,
        max_concurrency=args.max_concurrency,
        image_analysis=args.image_analysis,
    )

    for index, pdf_path in enumerate(pdf_paths, start=1):
        print(f"[{index}/{len(pdf_paths)}] Processing {pdf_path}")
        output_path = process_pdf(
            client=client,
            pdf_path=pdf_path,
            output_dir=output_dir,
            dpi=args.dpi,
            batch_size=args.batch_size,
            image_analysis=args.image_analysis,
        )
        print(f"  -> {output_path}")


if __name__ == "__main__":
    main()
