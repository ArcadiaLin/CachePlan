"""Materialize isolated E06 case workspaces from the derived fixture manifest.

Only generated data/processed/e06/fixtures/ is written. The raw P4A export and
historical sessions remain untouched. Each workspace receives copied input bytes,
a rewritten relative-path input bundle, and frozen historical external evidence.

Usage:
    python3 experiments/e06-static-prefix/src/materialize_fixtures.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT = "e06/materialize_fixtures.py"
REPO_ROOT = Path(__file__).resolve().parents[3]
INPUT_FILES = ("paper.md", "references.jsonl", "citation_contexts.jsonl")
CONTRACT_PATH = REPO_ROOT / "experiments/e06-static-prefix/contracts/agent_judgment.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON {path}: {error}") from error


def atomic_write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def resolve_source(case: dict[str, Any], name: str) -> Path:
    source = case.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"missing source section for {case.get('case_id')}")
    files = source.get("files")
    if not isinstance(files, dict) or not isinstance(files.get(name), dict):
        raise ValueError(f"missing source file metadata {name} for {case.get('case_id')}")
    path = REPO_ROOT / files[name]["path"]
    expected_hash = files[name]["sha256"]
    if not path.is_file() or sha256(path) != expected_hash:
        raise ValueError(f"source digest mismatch for {path}")
    return path


def materialize_contract(contract: dict[str, Any], paper_id: str) -> dict[str, Any]:
    copied = json.loads(json.dumps(contract))
    template = copied.get("output_template")
    if not isinstance(template, dict) or template.get("paper_id") != "<paper_id>":
        raise ValueError("invalid judgment contract output_template")
    template["paper_id"] = paper_id
    return copied


def materialize_case(
    case: dict[str, Any],
    evidence_root: Path,
    workspace_root: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    case_id = case.get("case_id")
    paper_id = case.get("paper_id")
    session_id = case.get("session_id")
    fixture = case.get("fixture")
    if not all(isinstance(value, str) for value in (case_id, paper_id, session_id)):
        raise ValueError(f"missing case identity: {case}")
    if not isinstance(fixture, dict):
        raise ValueError(f"missing fixture section for {case_id}")
    bundle = fixture.get("input_bundle")
    if not isinstance(bundle, dict) or bundle.get("paper_id") != paper_id:
        raise ValueError(f"invalid fixture input bundle for {case_id}")

    destination = workspace_root / case_id
    input_dir = destination / "input"
    evidence_dir = input_dir / "evidence"
    output_dir = destination / "output"
    input_dir.mkdir(parents=True)
    evidence_dir.mkdir()
    output_dir.mkdir()

    copied = {}
    for name in INPUT_FILES:
        source = resolve_source(case, name)
        target = input_dir / name
        shutil.copyfile(source, target)
        digest = sha256(target)
        if digest != sha256(source):
            raise ValueError(f"copy verification failed for {case_id}/{name}")
        copied[name] = {"bytes": target.stat().st_size, "sha256": digest}

    evidence_source = evidence_root / f"{case_id}.json"
    evidence = load_json(evidence_source)
    if not isinstance(evidence, dict) or evidence.get("case_id") != case_id or evidence.get("paper_id") != paper_id:
        raise ValueError(f"evidence identity mismatch for {case_id}")
    evidence_target = evidence_dir / "history.json"
    shutil.copyfile(evidence_source, evidence_target)
    copied["evidence/history.json"] = {
        "bytes": evidence_target.stat().st_size,
        "sha256": sha256(evidence_target),
    }

    atomic_write_json(input_dir / "input_bundle.json", bundle)
    copied["input_bundle.json"] = {
        "bytes": (input_dir / "input_bundle.json").stat().st_size,
        "sha256": sha256(input_dir / "input_bundle.json"),
    }
    fixture_contract = materialize_contract(contract, paper_id)
    atomic_write_json(input_dir / "judgment_contract.json", fixture_contract)
    copied["judgment_contract.json"] = {
        "bytes": (input_dir / "judgment_contract.json").stat().st_size,
        "sha256": sha256(input_dir / "judgment_contract.json"),
    }
    case_metadata = {
        "schema_version": 1,
        "case_id": case_id,
        "split": case["split"],
        "stratum": case["stratum"],
        "paper_id": paper_id,
        "session_id": session_id,
        "historical": case["historical"],
        "input_bundle": "input/input_bundle.json",
        "output": "output/agent_judgment.json",
        "judgment_contract": "input/judgment_contract.json",
        "evidence_status": fixture["evidence_status"],
        "quality_target_status": fixture["quality_target_status"],
    }
    atomic_write_json(destination / "case.json", case_metadata)

    return {
        "case_id": case_id,
        "paper_id": paper_id,
        "workspace": relative(destination),
        "files": copied,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-manifest",
        type=Path,
        default=REPO_ROOT / "data/processed/e06/fixture_manifest.json",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=REPO_ROOT / "data/processed/e06/evidence",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "data/processed/e06/fixtures",
    )
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace the generated output root only",
    )
    args = parser.parse_args()

    fixture_manifest_path = args.fixture_manifest.resolve()
    evidence_root = args.evidence_root.resolve()
    output_root = args.output_root.resolve()
    manifest = load_json(fixture_manifest_path)
    contract_path = args.contract.resolve()
    contract = load_json(contract_path)
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ValueError(f"unsupported judgment contract: {contract_path}")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError(f"unsupported fixture manifest: {fixture_manifest_path}")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or manifest.get("n_cases") != len(cases) or len(cases) != 24:
        raise ValueError("fixture manifest must contain exactly 24 cases")

    if output_root.exists():
        if not args.overwrite:
            raise ValueError(f"refusing to overwrite existing fixture root: {output_root}")
        shutil.rmtree(output_root)

    output_root.mkdir(parents=True)
    materialized = [materialize_case(case, evidence_root, output_root, contract) for case in cases]
    summary = {
        "_provenance": {
            "script": SCRIPT,
            "generated_at": datetime.now(UTC).isoformat(),
            "fixture_manifest": {
                "path": relative(fixture_manifest_path),
                "sha256": sha256(fixture_manifest_path),
            },
            "judgment_contract": {"path": relative(contract_path), "sha256": sha256(contract_path)},
        },
        "schema_version": 1,
        "n_cases": len(materialized),
        "cases": materialized,
    }
    atomic_write_json(output_root / "manifest.json", summary)
    print(f"[e06] materialized {len(materialized)} fixture workspaces at {output_root}")


if __name__ == "__main__":
    main()
