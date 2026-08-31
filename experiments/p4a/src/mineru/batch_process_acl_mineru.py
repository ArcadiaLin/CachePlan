#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/mineru/batch_process_acl_mineru.py --year 2026 --venue acl
"""Batch process ACL Anthology PDFs with a running MinerU VLM HTTP service."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_project_env() -> None:
    env_path = PROJECT_ROOT / ".env"
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
DEFAULT_RAW_ROOT = DEFAULT_DATA_ROOT / "raw"
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA_ROOT / "processed" / "mineru"
DEFAULT_SERVER_URL = "http://127.0.0.1:8004"
DEFAULT_YEAR = "2026"
VOLUME_PDF_RE = re.compile(r"^\d{4}\..+-\d+$")


@dataclass(frozen=True)
class PaperTask:
    top: str
    year: str
    venue: str
    pdf_path: Path
    output_parent: Path
    paper_output_dir: Path

    @property
    def paper_id(self) -> str:
        return self.pdf_path.stem

    @property
    def key(self) -> str:
        return f"{self.top}/{self.year}/{self.venue}/{self.paper_id}"

    @property
    def expected_md(self) -> Path:
        return self.paper_output_dir / "vlm" / f"{self.paper_id}.md"

    @property
    def expected_content_list(self) -> Path:
        return self.paper_output_dir / "vlm" / f"{self.paper_id}_content_list.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Process data/raw/acl/<year>/pdf/**/*.pdf with MinerU and keep "
            "restartable status under data/processed/mineru/_status."
        )
    )
    parser.add_argument("--year", default=DEFAULT_YEAR, help="ACL year to process.")
    parser.add_argument("--top", default="acl", help="Top-level raw collection name.")
    parser.add_argument("--venue", help="Only process one venue, e.g. abjadnlp.")
    parser.add_argument("--paper-id", action="append", help="Only process this paper id. May be repeated.")
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument(
        "--mineru-bin",
        type=Path,
        default=PROJECT_ROOT / ".venv" / "bin" / "mineru",
    )
    parser.add_argument("--backend", default="vlm-http-client")
    parser.add_argument("--image-analysis", default="true", choices=["true", "false"])
    parser.add_argument(
        "--client-side-output-generation",
        default="true",
        choices=["true", "false"],
        help="Let MinerU generate md/content_list/images locally from server results.",
    )
    parser.add_argument("--timeout", type=int, default=1800, help="Seconds per PDF.")
    parser.add_argument("--limit", type=int, help="Process at most N PDFs this run.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess even when expected MinerU outputs already exist.",
    )
    parser.add_argument(
        "--include-volumes",
        action="store_true",
        help="Also process volume/proceedings PDFs such as 2026.abjadnlp-1.pdf.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected tasks without invoking MinerU.",
    )
    parser.add_argument(
        "--skip-server-check",
        action="store_true",
        help="Do not check the MinerU/vLLM HTTP server before starting.",
    )
    return parser.parse_args()


def load_status(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_status(path: Path, status: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def append_attempt(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def discover_tasks(args: argparse.Namespace) -> list[PaperTask]:
    pdf_root = args.raw_root / args.top / args.year / "pdf"
    if args.venue:
        pdf_root = pdf_root / args.venue
    if not pdf_root.exists():
        raise SystemExit(f"PDF root does not exist: {pdf_root}")

    selected_paper_ids = set(args.paper_id or [])
    tasks: list[PaperTask] = []
    for pdf_path in sorted(pdf_root.rglob("*.pdf")):
        if selected_paper_ids and pdf_path.stem not in selected_paper_ids:
            continue
        if not args.include_volumes and VOLUME_PDF_RE.match(pdf_path.stem):
            continue

        try:
            relative = pdf_path.relative_to(args.raw_root)
            top, year, kind, venue, *_ = relative.parts
        except ValueError as exc:
            raise SystemExit(f"PDF is outside raw root: {pdf_path}") from exc
        except Exception as exc:
            raise SystemExit(f"Unexpected raw PDF path shape: {pdf_path}") from exc

        if top != args.top or year != args.year or kind != "pdf":
            continue

        output_parent = args.output_root / top / year / venue
        tasks.append(
            PaperTask(
                top=top,
                year=year,
                venue=venue,
                pdf_path=pdf_path,
                output_parent=output_parent,
                paper_output_dir=output_parent / pdf_path.stem,
            )
        )
    return tasks


def has_complete_output(task: PaperTask) -> bool:
    return task.expected_md.exists() and task.expected_content_list.exists()


def order_tasks(
    tasks: list[PaperTask],
    status: dict[str, dict[str, Any]],
    force: bool,
) -> list[PaperTask]:
    def priority(task: PaperTask) -> tuple[int, str]:
        if not force and has_complete_output(task):
            return (99, task.key)
        state = status.get(task.key, {}).get("status")
        if state in {"failed", "running"}:
            return (0, task.key)
        if state in {None, "pending"}:
            return (1, task.key)
        if state == "done":
            return (2 if force else 99, task.key)
        return (3, task.key)

    selected = [task for task in tasks if force or not has_complete_output(task)]
    return sorted(selected, key=priority)


def check_server(server_url: str, timeout: int = 10) -> None:
    url = server_url.rstrip("/") + "/v1/models"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status >= 400:
                raise RuntimeError(f"{url} returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"MinerU VLM server is reachable, but {url} returned HTTP {exc.code}.\n"
            f"Response body:\n{body}\n"
            "The MinerU vlm-http-client requires /v1/models to return exactly one model.\n"
            "Restart the vLLM server with:\n"
            "  cd /home/lzx/projs/p4a\n"
            "  src/mineru/serve_mineru_vllm.sh"
        ) from exc
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        raise SystemExit(
            f"MinerU VLM server is not reachable at {url}.\n"
            "Start it first, for example:\n"
            "  cd /home/lzx/projs/p4a\n"
            "  src/mineru/serve_mineru_vllm.sh\n"
            "Or rerun with --skip-server-check only if the endpoint is intentionally hidden."
        ) from exc


def build_mineru_command(args: argparse.Namespace, task: PaperTask) -> list[str]:
    return [
        str(args.mineru_bin),
        "-p",
        str(task.pdf_path),
        "-o",
        str(task.output_parent),
        "-b",
        args.backend,
        "-u",
        args.server_url,
        "--image-analysis",
        args.image_analysis,
        "--client-side-output-generation",
        args.client_side_output_generation,
    ]


def mineru_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env.setdefault("NUMEXPR_NUM_THREADS", "1")
    return env


def run_task(args: argparse.Namespace, task: PaperTask) -> subprocess.CompletedProcess[str]:
    task.output_parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        build_mineru_command(args, task),
        cwd=str(PROJECT_ROOT),
        env=mineru_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=args.timeout,
        check=False,
    )


def tail(text: str, max_chars: int = 8000) -> str:
    return text[-max_chars:] if len(text) > max_chars else text


def main() -> None:
    args = parse_args()
    if not args.mineru_bin.exists():
        raise SystemExit(f"MinerU binary does not exist: {args.mineru_bin}")

    status_dir = args.output_root / "_status"
    status_path = status_dir / f"{args.top}_{args.year}_mineru_status.json"
    attempts_path = status_dir / f"{args.top}_{args.year}_mineru_attempts.jsonl"

    if not args.skip_server_check and not args.dry_run:
        check_server(args.server_url)

    status = load_status(status_path)
    tasks = discover_tasks(args)
    selected = order_tasks(tasks, status, args.force)
    if args.limit:
        selected = selected[: args.limit]

    done_count = sum(1 for task in tasks if has_complete_output(task))
    print(f"Discovered {len(tasks)} PDFs for {args.top}/{args.year}.")
    print(f"Already complete: {done_count}. Selected this run: {len(selected)}.")

    if args.dry_run:
        for task in selected:
            state = status.get(task.key, {}).get("status", "pending")
            print(f"{state:>8} {task.pdf_path} -> {task.paper_output_dir}")
        return

    for index, task in enumerate(selected, start=1):
        previous = status.get(task.key, {})
        attempts = int(previous.get("attempts", 0)) + 1
        started_at = utc_now()
        status[task.key] = {
            **previous,
            "status": "running",
            "attempts": attempts,
            "pdf": str(task.pdf_path),
            "output_dir": str(task.paper_output_dir),
            "started_at": started_at,
            "updated_at": started_at,
        }
        save_status(status_path, status)

        print(f"[{index}/{len(selected)}] {task.key}")
        start_time = time.monotonic()
        try:
            result = run_task(args, task)
            elapsed = round(time.monotonic() - start_time, 2)
            complete = has_complete_output(task)
            if result.returncode == 0 and complete:
                record = {
                    **status[task.key],
                    "status": "done",
                    "returncode": result.returncode,
                    "elapsed_seconds": elapsed,
                    "finished_at": utc_now(),
                    "updated_at": utc_now(),
                }
                print(f"  done -> {task.paper_output_dir}")
            else:
                record = {
                    **status[task.key],
                    "status": "failed",
                    "returncode": result.returncode,
                    "elapsed_seconds": elapsed,
                    "finished_at": utc_now(),
                    "updated_at": utc_now(),
                    "error": "MinerU command failed or expected outputs are missing.",
                    "stdout_tail": tail(result.stdout),
                    "stderr_tail": tail(result.stderr),
                    "expected_outputs": [
                        str(task.expected_md),
                        str(task.expected_content_list),
                    ],
                }
                print(f"  failed returncode={result.returncode}")

            status[task.key] = record
            save_status(status_path, status)
            append_attempt(attempts_path, record)
        except Exception as exc:
            elapsed = round(time.monotonic() - start_time, 2)
            record = {
                **status.get(task.key, {}),
                "status": "failed",
                "elapsed_seconds": elapsed,
                "finished_at": utc_now(),
                "updated_at": utc_now(),
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            }
            status[task.key] = record
            save_status(status_path, status)
            append_attempt(attempts_path, record)
            print(f"  failed {exc!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
