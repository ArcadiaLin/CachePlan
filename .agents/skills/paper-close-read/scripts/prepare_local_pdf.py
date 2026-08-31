#!/usr/bin/env python3
"""Prepare a local-paper workspace from a PDF with graceful fallbacks."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def which(name: str) -> str | None:
    return shutil.which(name)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def build_index(images_dir: Path) -> None:
    files = sorted(p for p in images_dir.iterdir() if p.is_file() and p.name != "index.md")
    lines = ["# Image Index", ""]
    if not files:
        lines.append("- No extracted images or rendered pages were created.")
    else:
        for item in files:
            lines.append(f"- `{item.name}`")
    write_text(images_dir / "index.md", "\n".join(lines) + "\n")


def extract_text(pdf_path: Path, output_txt: Path) -> str:
    pdftotext = which("pdftotext")
    if pdftotext:
        result = run([pdftotext, str(pdf_path), "-"])
        if result.returncode == 0 and result.stdout.strip():
            write_text(output_txt, result.stdout)
            return "text: extracted with pdftotext"
        return f"text: pdftotext failed ({result.stderr.strip() or 'no stderr'})"
    return "text: no extractor available"


def extract_images(pdf_path: Path, images_dir: Path) -> str:
    images_dir.mkdir(parents=True, exist_ok=True)

    pdfimages = which("pdfimages")
    if pdfimages:
        prefix = images_dir / "img"
        result = run([pdfimages, "-all", str(pdf_path), str(prefix)])
        if result.returncode == 0:
            build_index(images_dir)
            return "images: extracted with pdfimages"
        return f"images: pdfimages failed ({result.stderr.strip() or 'no stderr'})"

    pdftoppm = which("pdftoppm")
    if pdftoppm:
        prefix = images_dir / "page"
        result = run([pdftoppm, "-png", str(pdf_path), str(prefix)])
        if result.returncode == 0:
            build_index(images_dir)
            return "images: rendered pages with pdftoppm"
        return f"images: pdftoppm failed ({result.stderr.strip() or 'no stderr'})"

    build_index(images_dir)
    return "images: no extractor available"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a local-paper workspace from a PDF.")
    parser.add_argument("pdf", help="Path to the source PDF")
    parser.add_argument("output_dir", help="Directory to populate")
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

    text_status = extract_text(copied_pdf, output_dir / "paper.txt")
    image_status = extract_images(copied_pdf, images_dir)

    report = "\n".join(
        [
            f"source_pdf: {copied_pdf}",
            text_status,
            image_status,
        ]
    )
    write_text(output_dir / "prep_status.txt", report + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
