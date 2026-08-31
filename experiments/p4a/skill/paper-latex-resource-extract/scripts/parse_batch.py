#!/usr/bin/env python3
"""
批量解析 arXiv LaTeX 包，生成论文与资源解析草稿。

用法:
    uv run python "$SCRIPTS_DIR/parse_batch.py" \
      --input-dir <directory-with-tar-gz> \
      --output-dir <run-output-dir> \
      --metadata online \
      --limit 20

    uv run python "$SCRIPTS_DIR/parse_batch.py" \
      --input-dir <directory-with-tar-gz> \
      --output-dir <run-output-dir> \
      --metadata offline

输出:
    每篇论文输出到 <output-dir>/<arxiv_id>/，包括 paper/resource YAML、
    structure/citation/resource JSON、figures/、figure_manifest.json；批量汇总写入
    <output-dir>/batch_report.json。

说明:
    单篇失败不会中断全批处理；失败原因会写入 batch_report.json。
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

from common import write_json
from parse_one import parse_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch parse arXiv LaTeX packages into paper/resource artifacts")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("paper_resource_runs"), type=Path)
    parser.add_argument("--metadata", choices=["online", "offline"], default="online")
    parser.add_argument("--metadata-timeout", type=float, default=8.0)
    parser.add_argument("--metadata-delay", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--traceback", action="store_true")
    args = parser.parse_args()

    packages = sorted(args.input_dir.glob("*.tar.gz"))
    if args.limit is not None:
        packages = packages[: args.limit]

    reports: list[dict[str, Any]] = []
    for index, package in enumerate(packages, start=1):
        print(f"[{index}/{len(packages)}] {package.name}", flush=True)
        try:
            reports.append(
                parse_package(
                    package,
                    args.output_dir,
                    args.metadata,
                    metadata_timeout=args.metadata_timeout,
                    metadata_delay=args.metadata_delay,
                )
            )
        except Exception as exc:
            if args.traceback:
                traceback.print_exc()
            reports.append({"ok": False, "input": str(package), "error": str(exc)})

    summary = {
        "ok": all(report.get("ok") for report in reports),
        "input_dir": str(args.input_dir),
        "output_dir": str(args.output_dir),
        "metadata_mode": args.metadata,
        "total": len(reports),
        "succeeded": sum(1 for report in reports if report.get("ok")),
        "failed": sum(1 for report in reports if not report.get("ok")),
        "reports": reports,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "batch_report.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "reports"}, ensure_ascii=False, indent=2))
    if not summary["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
