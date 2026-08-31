#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/acl-mirror/create_mirror.py --to /srv/datasets/p4a/data/raw/acl/2026 /path/to/acl-anthology/data/xml/2026.acl*.xml
"""Vendored ACL Anthology mirror downloader.

Adapted from /root/Repos/acl-anthology/bin/create_mirror.py.

Changes from the upstream script in the local checkout:
- Replace the missing legacy anthology.utils import with a local CRC32 helper.
- Keep the documented --only-papers behavior: PDFs only, no attachments.
"""

from __future__ import annotations

import logging as log
import json
import os
import re
import shutil
import sys
import tempfile
import warnings
import zlib
from urllib.request import urlretrieve

warnings.filterwarnings("ignore", category=SyntaxWarning, module="docopt")

from docopt import docopt
from lxml import etree


USAGE = """Usage: create_mirror.py [--source=SRC] [--to=DIR] [--report=FILE] [--debug] [--dry-run] [--only-papers] XMLFILE...

Mirrors ACL Anthology PDFs and attachments referenced by Anthology XML files.

XMLFILE: data file from the anthology data dir to fetch data for. Use data/xml/*.xml to
fetch everything.

Options:
  --source=SRC             Where to fetch the files from. [default: https://aclanthology.org]
  --to=DIR                 Directory to write files to. [default: build/anthology-files]
  --report=FILE            Optional JSON report path for failures and checksum mismatches.
  --only-papers            Do not mirror attachments, only papers.
  --debug                  Output debug-level log messages.
  -n, --dry-run            Do not actually download, use with --debug to see what would happen.
  -h, --help               Display this helpful text.
"""


NEW_ID_RE = re.compile(r"^(\d{4})\.([a-zA-Z\d]+)-")
OLD_ID_RE = re.compile(r"^([A-Za-z])(\d{2})-")


def compute_hash_from_file(filename: str) -> str:
    checksum = 0
    with open(filename, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum = zlib.crc32(chunk, checksum)
    return f"{checksum & 0xFFFFFFFF:08x}"


def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


class SeverityTracker(log.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.max_level = log.NOTSET

    def emit(self, record: log.LogRecord) -> None:
        self.max_level = max(self.max_level, record.levelno)


class ACLMirrorer:
    def __init__(self, args) -> None:
        self.hash_mismatches: list[dict[str, str]] = []
        self.not_downloadable: list[str] = []
        self.args = args
        self.source = args["--source"].rstrip("/")
        self.to = args["--to"]
        self.is_dry_run = args["--dry-run"]
        self.only_papers = args["--only-papers"]

    def download_file(self, fname: str, checksum: str, file_type: str) -> None:
        if file_type == "pdf":
            remote_url = self.source + "/" + fname
        elif file_type == "attachment":
            remote_url = self.source + "/attachments/" + fname
        else:
            log.error("unrecognized type: " + file_type)
            sys.exit(1)

        tmpfd, tmp_target = tempfile.mkstemp(prefix="aclmirrorer_", suffix=".download")
        os.close(tmpfd)
        local_target = ""
        match = NEW_ID_RE.match(fname)
        if match:
            local_target = os.path.join(self.to, file_type, match.groups()[1], fname)
        else:
            match = OLD_ID_RE.match(fname)
            if match:
                local_target = os.path.join(
                    self.to,
                    file_type,
                    match.groups()[0],
                    match.groups()[0] + match.groups()[1],
                    fname,
                )
            else:
                log.error("unrecognized format for " + fname)
                sys.exit(1)

        if os.path.exists(local_target):
            existing_hash = compute_hash_from_file(local_target)
            if existing_hash == checksum:
                log.debug("File %s already up to date, not downloading again", local_target)
                os.remove(tmp_target)
                return
            log.debug("File %s changed, redownloading ...", local_target)
        else:
            log.debug("Downloading %s from %s ...", local_target, remote_url)

        if self.is_dry_run:
            os.remove(tmp_target)
            return

        local_path = os.path.dirname(local_target)
        os.makedirs(local_path, exist_ok=True)
        try:
            urlretrieve(remote_url, tmp_target)
        except Exception:
            log.error("could not download " + remote_url)
            self.not_downloadable.append(remote_url)
            os.remove(tmp_target)
            return

        new_hash = compute_hash_from_file(tmp_target)
        if new_hash == checksum:
            shutil.move(tmp_target, local_target)
        else:
            log.error(
                "Hash mismatch for file %s, downloaded from %s. was %s should be %s",
                local_target,
                remote_url,
                new_hash,
                checksum,
            )
            os.makedirs(os.path.dirname(local_target), exist_ok=True)
            shutil.move(tmp_target, local_target)
            self.hash_mismatches.append(
                {
                    "url": remote_url,
                    "target": local_target,
                    "name": fname,
                    "type": file_type,
                    "actual_hash": new_hash,
                    "expected_hash": checksum,
                }
            )

    def download_files(self, xmlfname: str) -> None:
        xml = etree.parse(xmlfname)
        proceedings = xml.findall(".//volume/meta/url[@hash]")
        frontmatter = xml.findall(".//frontmatter/url[@hash]")
        papers = xml.findall(".//paper/url[@hash]")
        attachments = xml.findall(".//paper/attachment[@hash]")
        revisions = xml.findall(".//paper/revision[@hash]")
        errata = xml.findall(".//paper/erratum[@hash]")
        log.info("processing %s papers from %s ...", len(papers), xmlfname)
        for collection in [proceedings, frontmatter, papers, revisions, errata]:
            for entry in collection:
                checksum = entry.attrib["hash"]
                if "href" in entry.attrib:
                    fname = entry.attrib["href"]
                else:
                    fname = entry.text
                self.download_file(fname + ".pdf", checksum, "pdf")
        if not self.only_papers:
            for entry in attachments:
                checksum = entry.attrib["hash"]
                fname = entry.text
                self.download_file(fname, checksum, "attachment")


def main() -> int:
    args = docopt(USAGE)
    log_level = log.DEBUG if args["--debug"] else log.INFO
    log.basicConfig(format="%(levelname)-8s %(message)s", level=log_level)
    tracker = SeverityTracker()
    log.getLogger().addHandler(tracker)
    mirrorer = ACLMirrorer(args)
    for filename in args["XMLFILE"]:
        log.info("processing %s ...", filename)
        mirrorer.download_files(filename)

    eprint("\nFiles that could not be downloaded")
    eprint("==================================")
    for elem in mirrorer.not_downloadable:
        eprint(elem)
    eprint("\n\nFiles with checksum mismatch")
    eprint("============================")
    for elem in mirrorer.hash_mismatches:
        eprint(
            "{url} target={target} was={actual_hash} should={expected_hash}".format(
                **elem
            )
        )
    if args["--report"]:
        report_path = args["--report"]
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "not_downloadable": mirrorer.not_downloadable,
                    "hash_mismatches": mirrorer.hash_mismatches,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
    # Match the upstream mirror script's behavior: individual 404s, network
    # hiccups, or checksum mismatches are reported above, but they should not
    # make the whole yearly export crash after doing useful work.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
