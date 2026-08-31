#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/acl-mirror/download_acl_year.py 2026 --output-dir /srv/datasets/p4a/data/raw/acl
"""Download ACL Anthology resources for one or more years.

The script reads the official ACL Anthology XML metadata from a local clone and
creates this layout under the output directory:

  <output>/<year>/
    metadata/xml/
    metadata/json/
    bibtex/
    pdf/
    attachments/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ANTHOLOGY_REPO = Path("/root/Repos/acl-anthology")


def load_project_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
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
DEFAULT_OUTPUT_DIR = DEFAULT_DATA_ROOT / "raw/acl"
DEFAULT_SOURCE = "https://aclanthology.org"


@dataclass(frozen=True)
class FileRef:
    kind: str
    acl_id: str
    remote_url: str
    local_path: Path
    checksum: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export ACL Anthology metadata/citations and download PDFs/attachments "
            "for selected years."
        )
    )
    parser.add_argument(
        "years",
        nargs="*",
        help="Years to export, for example: 2026 2025.",
    )
    parser.add_argument(
        "--year",
        action="append",
        dest="year_options",
        default=[],
        help="Year to export. Can be passed multiple times.",
    )
    parser.add_argument(
        "--anthology-repo",
        type=Path,
        default=DEFAULT_ANTHOLOGY_REPO,
        help=f"Local acl-anthology repo. Default: {DEFAULT_ANTHOLOGY_REPO}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output root. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"ACL Anthology URL prefix. Default: {DEFAULT_SOURCE}",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Only write XML, JSON, and BibTeX; do not download files.",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Do not download paper/proceedings/frontmatter PDFs.",
    )
    parser.add_argument(
        "--no-attachments",
        action="store_true",
        help="Do not download paper attachments.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload files even when a local file already exists.",
    )
    parser.add_argument(
        "--refresh-metadata",
        action="store_true",
        help=(
            "Overwrite local metadata/xml copies from the source repo before export. "
            "By default existing local XML copies are preserved so accepted hash "
            "mismatch fixes survive reruns."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without writing or downloading files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Download at most N files per year. Useful for testing.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds. Default: 60.",
    )
    return parser.parse_args()


def normalize_years(args: argparse.Namespace) -> list[str]:
    years = [*args.years, *args.year_options]
    if not years:
        years = ["2026"]
    bad = [year for year in years if not re.fullmatch(r"\d{4}", year)]
    if bad:
        raise SystemExit(f"Invalid year value(s): {', '.join(bad)}")
    return sorted(set(years), reverse=True)


def compact_text(elem: ET.Element | None) -> str:
    if elem is None:
        return ""
    return re.sub(r"\s+", " ", "".join(elem.itertext())).strip()


def child_text(parent: ET.Element, tag: str) -> str:
    return compact_text(parent.find(tag))


def xml_attr(elem: ET.Element | None, name: str) -> str | None:
    if elem is None:
        return None
    return elem.attrib.get(name)


def anthology_id(collection_id: str, volume_id: str, item_id: str) -> str:
    if re.fullmatch(r"[A-Z]\d{2}", collection_id):
        return f"{collection_id}-{volume_id}{int(item_id):03d}"
    return f"{collection_id}-{volume_id}.{item_id}"


def volume_full_id(collection_id: str, volume_id: str) -> str:
    if re.fullmatch(r"[A-Z]\d{2}", collection_id):
        return f"{collection_id}-{volume_id}"
    return f"{collection_id}-{volume_id}"


def safe_filename(name: str) -> str:
    return name.replace("/", "_")


def crc32_file(path: Path) -> str:
    checksum = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum = zlib.crc32(chunk, checksum)
    return f"{checksum & 0xFFFFFFFF:08x}"


def paper_url(source: str, acl_id: str) -> str:
    return f"{source.rstrip('/')}/{acl_id}.pdf"


def attachment_url(source: str, name: str) -> str:
    return f"{source.rstrip('/')}/attachments/{name}"


def person_to_dict(elem: ET.Element) -> dict[str, str | None]:
    return {
        "id": elem.attrib.get("id"),
        "orcid": elem.attrib.get("orcid"),
        "first": child_text(elem, "first"),
        "last": child_text(elem, "last"),
        "affiliation": child_text(elem, "affiliation") or None,
    }


def volume_meta_to_dict(meta: ET.Element | None) -> dict[str, object]:
    if meta is None:
        return {}
    editors = [person_to_dict(editor) for editor in meta.findall("editor")]
    return {
        "booktitle": child_text(meta, "booktitle"),
        "editors": editors,
        "publisher": child_text(meta, "publisher"),
        "address": child_text(meta, "address"),
        "month": child_text(meta, "month"),
        "year": child_text(meta, "year"),
        "venue": child_text(meta, "venue"),
        "isbn": child_text(meta, "isbn"),
        "doi": child_text(meta, "doi"),
        "url": child_text(meta, "url"),
        "url_hash": xml_attr(meta.find("url"), "hash"),
    }


def paper_to_dict(
    paper: ET.Element,
    collection_id: str,
    volume_id: str,
    volume_meta: dict[str, object],
    source: str,
) -> dict[str, object]:
    paper_id = str(paper.attrib["id"])
    acl_id = anthology_id(collection_id, volume_id, paper_id)
    attachments = []
    for attachment in paper.findall("attachment"):
        name = compact_text(attachment)
        attachments.append(
            {
                "name": name,
                "hash": attachment.attrib.get("hash"),
                "url": attachment_url(source, name),
            }
        )
    revisions = []
    for revision in paper.findall("revision"):
        href = revision.attrib.get("href")
        revisions.append(
            {
                "id": revision.attrib.get("id"),
                "href": href,
                "hash": revision.attrib.get("hash"),
                "date": revision.attrib.get("date"),
                "comment": compact_text(revision),
                "pdf_url": paper_url(source, href) if href else None,
            }
        )
    errata = []
    for erratum in paper.findall("erratum"):
        href = erratum.attrib.get("href")
        errata.append(
            {
                "href": href,
                "hash": erratum.attrib.get("hash"),
                "comment": compact_text(erratum),
                "pdf_url": paper_url(source, href) if href else None,
            }
        )
    return {
        "acl_id": acl_id,
        "collection_id": collection_id,
        "volume_id": volume_id,
        "paper_id": paper_id,
        "title": child_text(paper, "title"),
        "authors": [person_to_dict(author) for author in paper.findall("author")],
        "pages": child_text(paper, "pages"),
        "abstract": child_text(paper, "abstract"),
        "url": child_text(paper, "url"),
        "url_hash": xml_attr(paper.find("url"), "hash"),
        "pdf_url": paper_url(source, acl_id),
        "bibkey": child_text(paper, "bibkey"),
        "doi": child_text(paper, "doi"),
        "attachments": attachments,
        "revisions": revisions,
        "errata": errata,
        "volume": volume_meta,
    }


def bib_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def bibtex_type(volume_meta: dict[str, object]) -> str:
    venue = str(volume_meta.get("venue") or "").lower()
    if venue in {"cl", "tacl", "lilt"}:
        return "article"
    return "inproceedings"


def paper_to_bibtex(paper: dict[str, object]) -> str:
    bibkey = str(paper.get("bibkey") or paper["acl_id"])
    volume = paper.get("volume")
    if not isinstance(volume, dict):
        volume = {}
    authors = paper.get("authors")
    author_names = []
    if isinstance(authors, list):
        for author in authors:
            if not isinstance(author, dict):
                continue
            first = str(author.get("first") or "").strip()
            last = str(author.get("last") or "").strip()
            author_names.append(f"{first} {last}".strip())
    fields = {
        "title": str(paper.get("title") or ""),
        "author": " and ".join(author_names),
        "booktitle": str(volume.get("booktitle") or ""),
        "year": str(volume.get("year") or ""),
        "month": str(volume.get("month") or ""),
        "address": str(volume.get("address") or ""),
        "publisher": str(volume.get("publisher") or ""),
        "pages": str(paper.get("pages") or ""),
        "url": str(paper.get("pdf_url") or ""),
        "doi": str(paper.get("doi") or ""),
    }
    if bibtex_type(volume) == "article":
        fields["journal"] = str(volume.get("booktitle") or volume.get("venue") or "")
        fields.pop("booktitle", None)

    lines = [f"@{bibtex_type(volume)}{{{bibkey},"]
    for key, value in fields.items():
        if value:
            lines.append(f'  {key} = "{bib_escape(value)}",')
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")
    return "\n".join(lines)


def iter_collection_data(
    xml_path: Path,
    source: str,
) -> tuple[list[dict[str, object]], list[FileRef]]:
    tree = ET.parse(xml_path)
    collection = tree.getroot()
    collection_id = str(collection.attrib["id"])
    papers: list[dict[str, object]] = []
    files: list[FileRef] = []
    for volume in collection.findall("volume"):
        volume_id = str(volume.attrib["id"])
        meta = volume_meta_to_dict(volume.find("meta"))
        volume_id_full = volume_full_id(collection_id, volume_id)
        meta_url = volume.find("./meta/url")
        if meta_url is not None and meta_url.attrib.get("hash") and compact_text(meta_url):
            acl_id = compact_text(meta_url)
            files.append(
                FileRef(
                    kind="pdf",
                    acl_id=volume_id_full,
                    remote_url=paper_url(source, acl_id),
                    local_path=Path("pdf") / f"{safe_filename(acl_id)}.pdf",
                    checksum=meta_url.attrib.get("hash"),
                )
            )
        for frontmatter in volume.findall("frontmatter"):
            url_elem = frontmatter.find("url")
            if url_elem is None or not url_elem.attrib.get("hash"):
                continue
            acl_id = compact_text(url_elem)
            files.append(
                FileRef(
                    kind="pdf",
                    acl_id=acl_id,
                    remote_url=paper_url(source, acl_id),
                    local_path=Path("pdf") / f"{safe_filename(acl_id)}.pdf",
                    checksum=url_elem.attrib.get("hash"),
                )
            )
        for paper in volume.findall("paper"):
            record = paper_to_dict(paper, collection_id, volume_id, meta, source)
            papers.append(record)
            url_elem = paper.find("url")
            if url_elem is not None and url_elem.attrib.get("hash"):
                acl_id = str(record["acl_id"])
                files.append(
                    FileRef(
                        kind="pdf",
                        acl_id=acl_id,
                        remote_url=paper_url(source, acl_id),
                        local_path=Path("pdf") / f"{safe_filename(acl_id)}.pdf",
                        checksum=url_elem.attrib.get("hash"),
                    )
                )
            for revision in record["revisions"]:
                if not isinstance(revision, dict) or not revision.get("href"):
                    continue
                href = str(revision["href"])
                files.append(
                    FileRef(
                        kind="pdf",
                        acl_id=href,
                        remote_url=paper_url(source, href),
                        local_path=Path("pdf") / f"{safe_filename(href)}.pdf",
                        checksum=str(revision["hash"]) if revision.get("hash") else None,
                    )
                )
            for erratum in record["errata"]:
                if not isinstance(erratum, dict) or not erratum.get("href"):
                    continue
                href = str(erratum["href"])
                files.append(
                    FileRef(
                        kind="pdf",
                        acl_id=href,
                        remote_url=paper_url(source, href),
                        local_path=Path("pdf") / f"{safe_filename(href)}.pdf",
                        checksum=str(erratum["hash"]) if erratum.get("hash") else None,
                    )
                )
            for attachment in record["attachments"]:
                if not isinstance(attachment, dict) or not attachment.get("name"):
                    continue
                name = str(attachment["name"])
                files.append(
                    FileRef(
                        kind="attachment",
                        acl_id=str(record["acl_id"]),
                        remote_url=attachment_url(source, name),
                        local_path=Path("attachments") / safe_filename(name),
                        checksum=(
                            str(attachment["hash"]) if attachment.get("hash") else None
                        ),
                    )
                )
    return papers, files


def write_json(path: Path, payload: object, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY-RUN write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY-RUN write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_xml(
    xml_paths: Iterable[Path],
    xml_output_dir: Path,
    dry_run: bool,
    refresh: bool,
) -> list[Path]:
    targets: list[Path] = []
    for xml_path in xml_paths:
        target = xml_output_dir / xml_path.name
        targets.append(target)
        if target.exists() and not refresh:
            continue
        if dry_run:
            print(f"DRY-RUN copy {xml_path} -> {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(xml_path, target)
    return targets


def download_file(ref: FileRef, year_dir: Path, overwrite: bool, timeout: float) -> str:
    target = year_dir / ref.local_path
    if target.exists() and not overwrite:
        if ref.checksum is None or crc32_file(target) == ref.checksum:
            return "exists"

    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        ref.remote_url,
        headers={"User-Agent": "p4a-acl-downloader/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        target.write_bytes(response.read())

    if ref.checksum is not None:
        actual = crc32_file(target)
        if actual != ref.checksum:
            return f"checksum-mismatch:{actual}!={ref.checksum}"
    return "downloaded"


def download_files(
    refs: list[FileRef],
    year_dir: Path,
    overwrite: bool,
    timeout: float,
    dry_run: bool,
    limit: int | None,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "planned": len(refs),
        "downloaded": 0,
        "exists": 0,
        "failed": [],
        "checksum_mismatch": [],
    }
    selected_refs = refs[:limit] if limit is not None else refs
    for index, ref in enumerate(selected_refs, start=1):
        target = year_dir / ref.local_path
        if dry_run:
            print(f"DRY-RUN download [{index}/{len(selected_refs)}] {ref.remote_url}")
            print(f"        -> {target}")
            continue
        try:
            status = download_file(ref, year_dir, overwrite=overwrite, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"FAILED {ref.remote_url}: {exc}", file=sys.stderr)
            failed = summary["failed"]
            assert isinstance(failed, list)
            failed.append({"url": ref.remote_url, "target": str(target), "error": str(exc)})
            continue
        if status == "downloaded":
            summary["downloaded"] = int(summary["downloaded"]) + 1
        elif status == "exists":
            summary["exists"] = int(summary["exists"]) + 1
        elif status.startswith("checksum-mismatch"):
            mismatches = summary["checksum_mismatch"]
            assert isinstance(mismatches, list)
            mismatches.append(
                {"url": ref.remote_url, "target": str(target), "status": status}
            )
    return summary


def can_use_acl_mirror(args: argparse.Namespace) -> bool:
    if args.limit is not None:
        return False
    if args.no_pdf:
        return False
    if args.overwrite:
        return False
    return True


def run_acl_mirror(
    xml_paths: list[Path],
    year_dir: Path,
    source: str,
    only_papers: bool,
    dry_run: bool,
) -> dict[str, object]:
    mirror_script = Path(__file__).with_name("create_mirror.py")
    report_path = year_dir / "metadata" / "json" / f"mirror-{year_dir.name}.json"
    command = [
        sys.executable,
        str(mirror_script),
        f"--source={source}",
        f"--to={year_dir}",
        f"--report={report_path}",
    ]
    if only_papers:
        command.append("--only-papers")
    if dry_run:
        command.append("--dry-run")
        command.append("--debug")
    command.extend(str(path) for path in xml_paths)

    print("  Using ACL mirror script:")
    print("  " + " ".join(command))
    if dry_run:
        subprocess.run(command, check=True)
    else:
        subprocess.run(command, check=True)
    return {
        "delegated_to": str(mirror_script),
        "mode": "pdf-only" if only_papers else "pdf-and-attachments",
        "xml_files": len(xml_paths),
        "output_dir": str(year_dir),
        "report": str(report_path),
    }


def reported_file_name(elem: ET.Element, file_type: str) -> str | None:
    if file_type == "attachment":
        return compact_text(elem)
    if "href" in elem.attrib:
        return elem.attrib["href"] + ".pdf"
    text = compact_text(elem)
    return f"{text}.pdf" if text else None


def apply_hash_mismatch_overrides(year_dir: Path, report_path: Path) -> int:
    if not report_path.exists():
        return 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    mismatches = report.get("hash_mismatches", [])
    if not isinstance(mismatches, list) or not mismatches:
        return 0

    updates_by_name: dict[tuple[str, str], str] = {}
    for mismatch in mismatches:
        if not isinstance(mismatch, dict):
            continue
        file_type = str(mismatch.get("type") or "")
        name = str(mismatch.get("name") or "")
        actual_hash = str(mismatch.get("actual_hash") or "")
        if file_type and name and actual_hash:
            updates_by_name[(file_type, name)] = actual_hash

    if not updates_by_name:
        return 0

    changed = 0
    xml_dir = year_dir / "metadata" / "xml"
    for xml_path in sorted(xml_dir.glob("*.xml")):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        touched = False
        candidates = [
            (root.findall(".//volume/meta/url[@hash]"), "pdf"),
            (root.findall(".//frontmatter/url[@hash]"), "pdf"),
            (root.findall(".//paper/url[@hash]"), "pdf"),
            (root.findall(".//paper/revision[@hash]"), "pdf"),
            (root.findall(".//paper/erratum[@hash]"), "pdf"),
            (root.findall(".//paper/attachment[@hash]"), "attachment"),
        ]
        for elements, file_type in candidates:
            for elem in elements:
                name = reported_file_name(elem, file_type)
                if name is None:
                    continue
                actual_hash = updates_by_name.get((file_type, name))
                if actual_hash and elem.attrib.get("hash") != actual_hash:
                    elem.set("hash", actual_hash)
                    changed += 1
                    touched = True
        if touched:
            tree.write(xml_path, encoding="UTF-8", xml_declaration=True)
    return changed


def write_year_outputs(
    year: str,
    xml_paths: list[Path],
    output_dir: Path,
    source: str,
    dry_run: bool,
    refresh_metadata: bool,
) -> tuple[list[dict[str, object]], list[FileRef]]:
    year_dir = output_dir / year
    for subdir in (
        year_dir / "metadata" / "xml",
        year_dir / "metadata" / "json",
        year_dir / "bibtex",
        year_dir / "pdf",
        year_dir / "attachments",
    ):
        if dry_run:
            print(f"DRY-RUN ensure directory {subdir}")
        else:
            subdir.mkdir(parents=True, exist_ok=True)
    local_xml_paths = copy_xml(
        xml_paths,
        year_dir / "metadata" / "xml",
        dry_run=dry_run,
        refresh=refresh_metadata,
    )
    parse_xml_paths = xml_paths if dry_run else local_xml_paths

    all_papers: list[dict[str, object]] = []
    all_files: list[FileRef] = []
    for xml_path in parse_xml_paths:
        papers, files = iter_collection_data(xml_path, source=source)
        all_papers.extend(papers)
        all_files.extend(files)

        stem = xml_path.stem
        write_json(
            year_dir / "metadata" / "json" / f"{stem}.json",
            {"source_xml": xml_path.name, "papers": papers},
            dry_run=dry_run,
        )
        bibtex = "\n\n".join(paper_to_bibtex(paper) for paper in papers)
        write_text(year_dir / "bibtex" / f"{stem}.bib", bibtex + "\n", dry_run=dry_run)

    jsonl = "\n".join(
        json.dumps(paper, ensure_ascii=False, sort_keys=True) for paper in all_papers
    )
    write_text(
        year_dir / "metadata" / "json" / f"papers-{year}.jsonl",
        jsonl + ("\n" if jsonl else ""),
        dry_run=dry_run,
    )
    write_json(
        year_dir / "metadata" / "json" / f"summary-{year}.json",
        {
            "year": year,
            "collections": len(xml_paths),
            "papers": len(all_papers),
            "files": {
                "pdf": sum(1 for ref in all_files if ref.kind == "pdf"),
                "attachments": sum(1 for ref in all_files if ref.kind == "attachment"),
            },
        },
        dry_run=dry_run,
    )
    all_bibtex = "\n\n".join(paper_to_bibtex(paper) for paper in all_papers)
    write_text(
        year_dir / "bibtex" / f"anthology-{year}.bib",
        all_bibtex + ("\n" if all_bibtex else ""),
        dry_run=dry_run,
    )
    return all_papers, all_files


def main() -> None:
    args = parse_args()
    years = normalize_years(args)
    data_xml_dir = args.anthology_repo / "data" / "xml"
    if not data_xml_dir.is_dir():
        raise SystemExit(f"ACL Anthology XML directory not found: {data_xml_dir}")

    for year in years:
        xml_paths = sorted(data_xml_dir.glob(f"{year}*.xml"))
        if not xml_paths:
            print(f"No ACL XML files found for year {year}", file=sys.stderr)
            continue

        print(f"Exporting ACL Anthology {year}: {len(xml_paths)} XML file(s)")
        papers, files = write_year_outputs(
            year=year,
            xml_paths=xml_paths,
            output_dir=args.output_dir,
            source=args.source,
            dry_run=args.dry_run,
            refresh_metadata=args.refresh_metadata,
        )
        year_dir = args.output_dir / year
        mirror_xml_paths = (
            xml_paths if args.dry_run else sorted((year_dir / "metadata" / "xml").glob("*.xml"))
        )

        download_refs = files
        if args.no_pdf:
            download_refs = [ref for ref in download_refs if ref.kind != "pdf"]
        if args.no_attachments:
            download_refs = [ref for ref in download_refs if ref.kind != "attachment"]

        summary = {
            "year": year,
            "collections": len(xml_paths),
            "papers": len(papers),
            "files": {
                "pdf": sum(1 for ref in files if ref.kind == "pdf"),
                "attachments": sum(1 for ref in files if ref.kind == "attachment"),
            },
        }
        print(textwrap.indent(json.dumps(summary, ensure_ascii=False, indent=2), "  "))

        if args.skip_download:
            print("  Skipping downloads.")
            continue

        if can_use_acl_mirror(args):
            download_summary = run_acl_mirror(
                xml_paths=mirror_xml_paths,
                year_dir=year_dir,
                source=args.source,
                only_papers=args.no_attachments,
                dry_run=args.dry_run,
            )
            if not args.dry_run:
                report_path = Path(str(download_summary["report"]))
                updated_hashes = apply_hash_mismatch_overrides(year_dir, report_path)
                download_summary["xml_hash_overrides"] = updated_hashes
        else:
            print(f"  Downloading {len(download_refs)} file(s) with fallback downloader...")
            download_summary = download_files(
                refs=download_refs,
                year_dir=year_dir,
                overwrite=args.overwrite,
                timeout=args.timeout,
                dry_run=args.dry_run,
                limit=args.limit,
            )
        if not args.dry_run:
            write_json(
                args.output_dir / year / "metadata" / "json" / f"download-{year}.json",
                download_summary,
                dry_run=False,
            )
        print(textwrap.indent(json.dumps(download_summary, ensure_ascii=False, indent=2), "  "))


if __name__ == "__main__":
    main()
