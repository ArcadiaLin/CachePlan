"""Generate the E06 fixture manifest from the user-exported P4A case bundle.

The export under data/raw/ stays immutable. This script validates it, records
source digests, and emits a manifest for a later materializer that will create
per-run workspaces with fixture-local paths.

Usage:
    python3 experiments/e06-static-prefix/src/build_fixture_manifest.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

SCRIPT = "e06/build_fixture_manifest.py"
REPO_ROOT = Path(__file__).resolve().parents[3]
REQUIRED_SOURCE_FILES = (
    "paper.md",
    "input_bundle.json",
    "references.jsonl",
    "citation_contexts.jsonl",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON {path}: {error}") from error


def validate_jsonl(path: Path) -> None:
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if line.strip():
                    json.loads(line)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSONL {path}: {error}") from error


def relative(path: Path) -> str:
    # 产物目录允许落在仓库之外 —— `make verify-stdlib` 就把全部派生产物导向临时
    # 目录，以免自检改写 data/processed/e06/。此时记绝对路径，不崩。
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def fixture_bundle(paper_id: str) -> dict[str, str]:
    return {
        "paper_id": paper_id,
        "markdown_path": "input/paper.md",
        "references_jsonl": "input/references.jsonl",
        "cite_contexts_jsonl": "input/citation_contexts.jsonl",
        "output_dir": "output",
        "agent_judgment_output": "output/agent_judgment.json",
    }


def build(cases_path: Path, export_root: Path) -> dict[str, object]:
    cases_config = load_json(cases_path)
    if not isinstance(cases_config, dict) or cases_config.get("schema_version") != 1:
        raise ValueError(f"unsupported cases config: {cases_path}")
    cases = cases_config.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("E06 requires exactly 24 configured cases")

    export_manifest_path = export_root / "manifest.json"
    export_manifest = load_json(export_manifest_path)
    if not isinstance(export_manifest, list):
        raise ValueError(f"export manifest is not a list: {export_manifest_path}")
    exported = {entry.get("paper_id"): entry for entry in export_manifest if isinstance(entry, dict)}

    seen_case_ids: set[str] = set()
    seen_paper_ids: set[str] = set()
    fixture_cases = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case entry is not an object")
        case_id = case.get("case_id")
        paper_id = case.get("paper_id")
        if not isinstance(case_id, str) or not isinstance(paper_id, str):
            raise ValueError(f"case is missing case_id or paper_id: {case}")
        if case_id in seen_case_ids or paper_id in seen_paper_ids:
            raise ValueError(f"duplicate case_id or paper_id: {case_id}, {paper_id}")
        seen_case_ids.add(case_id)
        seen_paper_ids.add(paper_id)

        exported_entry = exported.get(paper_id)
        if exported_entry is None:
            raise ValueError(f"paper not exported: {paper_id}")
        statuses = exported_entry.get("files")
        if not isinstance(statuses, dict) or any(statuses.get(name) != "ok" for name in REQUIRED_SOURCE_FILES):
            raise ValueError(f"required export artifact missing for {paper_id}")

        source_dir = export_root / paper_id
        source_files = {name: source_dir / name for name in REQUIRED_SOURCE_FILES}
        for name, path in source_files.items():
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"missing or empty {name} for {paper_id}")

        source_bundle = load_json(source_files["input_bundle.json"])
        if not isinstance(source_bundle, dict) or source_bundle.get("paper_id") != paper_id:
            raise ValueError(f"input bundle paper_id mismatch for {paper_id}")
        validate_jsonl(source_files["references.jsonl"])
        validate_jsonl(source_files["citation_contexts.jsonl"])

        fixture_cases.append(
            {
                **case,
                "source": {
                    "export_dir": relative(source_dir),
                    "files": {
                        name: {
                            "path": relative(path),
                            "bytes": path.stat().st_size,
                            "sha256": sha256(path),
                        }
                        for name, path in source_files.items()
                    },
                    "input_bundle_sha256": sha256(source_files["input_bundle.json"]),
                },
                "fixture": {
                    "root": f"fixtures/{case_id}",
                    "input_bundle": fixture_bundle(paper_id),
                    "layout": {
                        "paper": "input/paper.md",
                        "references": "input/references.jsonl",
                        "citation_contexts": "input/citation_contexts.jsonl",
                        "judgment_contract": "input/judgment_contract.json",
                        "evidence_dir": "input/evidence",
                        "agent_judgment": "output/agent_judgment.json",
                    },
                    "evidence_status": "pending",
                    "quality_target_status": "pending",
                },
            }
        )

    return {
        "_provenance": {
            "script": SCRIPT,
            "generated_at": datetime.now(UTC).isoformat(),
            "cases": {"path": relative(cases_path), "sha256": sha256(cases_path)},
            "export_manifest": {
                "path": relative(export_manifest_path),
                "sha256": sha256(export_manifest_path),
            },
        },
        "schema_version": 1,
        "selection_version": cases_config["selection_version"],
        "n_cases": len(fixture_cases),
        "n_smoke": sum(case["split"] == "smoke" for case in fixture_cases),
        "n_evaluation": sum(case["split"] == "evaluation" for case in fixture_cases),
        "cases": fixture_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=REPO_ROOT / "experiments/e06-static-prefix/cases.json",
    )
    parser.add_argument(
        "--export-root",
        type=Path,
        default=REPO_ROOT / "data/raw/export/p4a_cases_2025",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data/processed/e06/fixture_manifest.json",
    )
    args = parser.parse_args()

    manifest = build(args.cases.resolve(), args.export_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"[e06] wrote {args.output}: "
        f"{manifest['n_cases']} cases "
        f"({manifest['n_smoke']} smoke, {manifest['n_evaluation']} evaluation)"
    )


if __name__ == "__main__":
    main()
