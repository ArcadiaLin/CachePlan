#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pymupdf>=1.24"]
# ///
"""Prepare a local-paper workspace from a PDF.

Run with uv so the PDF dependency is resolved automatically, with no system
packages and no virtualenv to manage:

    uv run scripts/prepare_local_pdf.py paper.pdf out-dir/

PyMuPDF handles text extraction, embedded-image extraction and page rendering,
so poppler (pdftotext / pdfimages / pdftoppm) is no longer required. If the
script is run with a bare interpreter that lacks PyMuPDF, it falls back to
poppler when present and otherwise reports what is missing instead of failing.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Embedded images below this pixel size are decorative (rules, logos, glyph
# fragments) and only add noise to the index. Filter on dimensions only, never
# on encoded byte size: line-art figures and plots compress to very few bytes.
MIN_IMAGE_PIXELS = 120
PAGE_RENDER_DPI = 200


def load_pymupdf():
    """Return the pymupdf module, or None when it is unavailable."""
    try:
        import pymupdf  # type: ignore

        return pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore  # PyMuPDF < 1.24 name

            return pymupdf
        except ImportError:
            return None


def which(name: str) -> str | None:
    return shutil.which(name)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --- PyMuPDF path ----------------------------------------------------------


def extract_text_pymupdf(doc, output_txt: Path) -> str:
    """Write the full text with page markers, so claims stay citable by page."""
    chunks = []
    for number, page in enumerate(doc, start=1):
        chunks.append(f"\n\n===== [page {number}] =====\n\n")
        chunks.append(page.get_text("text"))
    text = "".join(chunks).strip()
    if not text:
        return "text: pymupdf found no text layer (likely a scanned PDF; OCR needed)"
    write_text(output_txt, text + "\n")
    return f"text: extracted with pymupdf ({len(doc)} pages, page markers included)"


def render_pages_pymupdf(doc, images_dir: Path, dpi: int) -> list[str]:
    entries = []
    for number, page in enumerate(doc, start=1):
        name = f"page-{number:03d}.png"
        page.get_pixmap(dpi=dpi).save(images_dir / name)
        entries.append(f"- `{name}`: rendered page {number} @ {dpi}dpi")
    return entries


def extract_images_pymupdf(pymupdf, doc, images_dir: Path, dpi: int) -> tuple[str, list[str]]:
    """Render every page, then add whatever embedded rasters are actually usable.

    Page renders are the reliable artifact. Embedded-image extraction is only a
    supplement, because in a typical CS paper the figures are vector art: the
    objects `get_images()` reports are then just the soft masks and shading
    layers behind that art, and `extract_image()` hands back a base layer that
    opens as solid black. Such images are composited with their mask here, and
    dropped when the result carries no detail.
    """
    entries = render_pages_pymupdf(doc, images_dir, dpi)
    page_count = len(entries)

    seen: set[int] = set()
    kept = 0
    skipped_flat = 0

    for number, page in enumerate(doc, start=1):
        for info in page.get_images(full=True):
            xref, smask_xref = info[0], info[1]
            if xref in seen:  # the same image can be placed on several pages
                continue
            seen.add(xref)
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if smask_xref:  # re-attach transparency, else the art reads as black
                    pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, smask_xref))
            except Exception:  # noqa: BLE001 - a broken xref must not abort the run
                continue
            if pix.width < MIN_IMAGE_PIXELS or pix.height < MIN_IMAGE_PIXELS:
                continue
            if pix.is_unicolor:  # a bare mask or a solid fill: no figure in there
                skipped_flat += 1
                continue
            name = f"img-{kept:03d}.png"
            pix.save(images_dir / name)
            entries.append(f"- `{name}`: page {number}, {pix.width}x{pix.height}px (embedded)")
            kept += 1

    status = (
        f"images: rendered {page_count} pages @ {dpi}dpi + kept {kept} embedded rasters"
    )
    if skipped_flat:
        status += f" (dropped {skipped_flat} mask-only/flat images)"
    return status, entries


# --- poppler fallback ------------------------------------------------------


def extract_text_poppler(pdf_path: Path, output_txt: Path) -> str:
    pdftotext = which("pdftotext")
    if not pdftotext:
        return "text: no extractor available (install uv and run this script with `uv run`)"
    result = run([pdftotext, str(pdf_path), "-"])
    if result.returncode == 0 and result.stdout.strip():
        write_text(output_txt, result.stdout)
        return "text: extracted with pdftotext (fallback; no page markers)"
    return f"text: pdftotext failed ({result.stderr.strip() or 'no stderr'})"


def extract_images_poppler(pdf_path: Path, images_dir: Path) -> str:
    pdfimages = which("pdfimages")
    if pdfimages:
        result = run([pdfimages, "-all", str(pdf_path), str(images_dir / "img")])
        if result.returncode == 0:
            return "images: extracted with pdfimages (fallback)"
        return f"images: pdfimages failed ({result.stderr.strip() or 'no stderr'})"

    pdftoppm = which("pdftoppm")
    if pdftoppm:
        result = run([pdftoppm, "-png", str(pdf_path), str(images_dir / "page")])
        if result.returncode == 0:
            return "images: rendered pages with pdftoppm (fallback)"
        return f"images: pdftoppm failed ({result.stderr.strip() or 'no stderr'})"

    return "images: no extractor available (install uv and run this script with `uv run`)"


def build_index_from_dir(images_dir: Path) -> list[str]:
    files = sorted(p for p in images_dir.iterdir() if p.is_file() and p.name != "index.md")
    return [f"- `{item.name}`" for item in files]


def write_index(images_dir: Path, entries: list[str]) -> None:
    lines = ["# Image Index", ""]
    if entries:
        lines.extend(entries)
        lines.extend(
            [
                "",
                "为每张计划使用的图补上：对应图号（Fig./Table）、建议用途、是否进正文。",
            ]
        )
    else:
        lines.append("- No extracted images or rendered pages were created.")
    write_text(images_dir / "index.md", "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a local-paper workspace from a PDF (run via `uv run`).",
    )
    parser.add_argument("pdf", help="Path to the source PDF")
    parser.add_argument("output_dir", help="Directory to populate")
    parser.add_argument(
        "--dpi",
        type=int,
        default=PAGE_RENDER_DPI,
        help=f"Page render resolution (default: {PAGE_RENDER_DPI})",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not pdf_path.exists():
        print(f"error: PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    copied_pdf = output_dir / "source.pdf"
    shutil.copy2(pdf_path, copied_pdf)

    pymupdf = load_pymupdf()
    if pymupdf is not None:
        with pymupdf.open(copied_pdf) as doc:
            backend = f"backend: pymupdf {pymupdf.__doc__ or ''}".strip()
            text_status = extract_text_pymupdf(doc, output_dir / "paper.txt")
            image_status, entries = extract_images_pymupdf(pymupdf, doc, images_dir, args.dpi)
    else:
        backend = "backend: poppler fallback (PyMuPDF unavailable — prefer `uv run`)"
        text_status = extract_text_poppler(copied_pdf, output_dir / "paper.txt")
        image_status = extract_images_poppler(copied_pdf, images_dir)
        entries = build_index_from_dir(images_dir)

    write_index(images_dir, entries)

    report = "\n".join(
        [
            f"source_pdf: {copied_pdf}",
            backend,
            text_status,
            image_status,
        ]
    )
    write_text(output_dir / "prep_status.txt", report + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
