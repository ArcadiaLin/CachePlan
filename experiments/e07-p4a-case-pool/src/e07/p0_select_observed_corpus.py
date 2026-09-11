"""p0：从 p4a-v1 全量副本中筛出 961 观测集的 952 篇论文，复制成本实验的语料子集。

输入（只读）：
  data/raw/p4a-v1/data/processed_p4a/            p4a v1 流水线产物副本
  data/processed/e01/n0_fixed_time.jsonl         961 观测集清单（权威来源）

输出：
  data/processed/e07/corpus/<paper_id>/{mineru,layer4,cite}/...
  data/processed/e07/p0_corpus_summary.json      覆盖与校验报告

不变量（任一不满足即失败退出，不静默跳过）：
  - 观测集恰为 952 篇不同论文；
  - 每篇都有 mineru 的 <paper_id>.md、layer4 的 paper_record.yml /
    resource_records.yml / agent_judgment.json、cite 的 cite_contexts.jsonl；
  - 复制后逐层文件数与总字节数与源一致，并抽样做 md5 比对。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SRC = REPO / "data/raw/p4a-v1/data/processed_p4a"
N0 = REPO / "data/processed/e01/n0_fixed_time.jsonl"
OUT = REPO / "data/processed/e07"
CORPUS = OUT / "corpus"

EXPECTED_PAPERS = 952
REQUIRED_FILES = {
    "mineru": ["{pid}.md"],
    "layer4": ["paper_record.yml", "resource_records.yml", "agent_judgment.json"],
    "cite": ["cite_contexts.jsonl"],
}
# 源数据已知的缺口，逐个登记、逐个豁免，不泛指。layer4 全语料另缺 3 篇
# 2025 论文（见 data/raw/p4a-v1/README.md），但它们不在 961 观测集内。
KNOWN_MISSING = {
    ("2026.acl-long.165", "layer4/agent_judgment.json"),
}
MD5_SAMPLE = 20


def repo_root() -> Path:
    return REPO


def git_rev() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def load_observed_papers() -> list[str]:
    """961 观测集覆盖的不同 paper_id，保持首次出现次序。"""
    seen: dict[str, None] = {}
    with open(N0) as f:
        for line in f:
            row = json.loads(line)
            pid = row.get("paper_id")
            if pid:
                seen.setdefault(pid)
    return list(seen)


def source_dirs(pid: str) -> dict[str, Path]:
    """按 pipeline.md 的目录约定定位三层来源；2025 的 cite 是聚合文件，无单篇目录。"""
    year = pid.split(".", 1)[0]
    return {
        "mineru": SRC / "mineru/acl" / year / "acl" / pid / "vlm",
        "layer4": SRC / "layer4" / year / "acl" / pid,
        "cite": SRC / "cite" / year / "acl/per_paper" / pid,
    }


def dir_stats(root: Path) -> tuple[int, int]:
    n_files = n_bytes = 0
    for p in root.rglob("*"):
        if p.is_file():
            n_files += 1
            n_bytes += p.stat().st_size
    return n_files, n_bytes


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    papers = load_observed_papers()
    if len(papers) != EXPECTED_PAPERS:
        print(f"FAIL: 观测集论文数 {len(papers)} != {EXPECTED_PAPERS}", file=sys.stderr)
        return 1

    # 复制前先在源侧核对不变量，任一缺失直接失败，不复制半个语料。
    missing: list[str] = []
    for pid in papers:
        for layer, root in source_dirs(pid).items():
            for name in REQUIRED_FILES[layer]:
                rel = f"{layer}/{name.format(pid=pid)}"
                if (pid, rel) in KNOWN_MISSING:
                    continue
                if not (root / name.format(pid=pid)).is_file():
                    missing.append(f"{pid}: {rel}")
    if missing:
        print(f"FAIL: 源侧缺 {len(missing)} 个必需文件，例如:", file=sys.stderr)
        for m in missing[:10]:
            print(f"  {m}", file=sys.stderr)
        return 1

    if CORPUS.exists():
        shutil.rmtree(CORPUS)
    CORPUS.mkdir(parents=True)

    layer_totals: dict[str, dict[str, int]] = {}
    for pid in papers:
        for layer, src_dir in source_dirs(pid).items():
            dst_dir = CORPUS / pid / layer
            shutil.copytree(src_dir, dst_dir)
            s_n, s_b = dir_stats(src_dir)
            d_n, d_b = dir_stats(dst_dir)
            if (s_n, s_b) != (d_n, d_b):
                print(f"FAIL: {pid}/{layer} 复制后不一致 "
                      f"({s_n}f/{s_b}B -> {d_n}f/{d_b}B)", file=sys.stderr)
                return 1
            t = layer_totals.setdefault(layer, {"files": 0, "bytes": 0})
            t["files"] += s_n
            t["bytes"] += s_b

    # 抽样 md5 比对：等距取 MD5_SAMPLE 篇，每篇比对 layer4/paper_record.yml。
    sampled = [papers[i * len(papers) // MD5_SAMPLE] for i in range(MD5_SAMPLE)]
    for pid in sampled:
        src_f = source_dirs(pid)["layer4"] / "paper_record.yml"
        dst_f = CORPUS / pid / "layer4/paper_record.yml"
        if md5_of(src_f) != md5_of(dst_f):
            print(f"FAIL: md5 不一致 {pid}/layer4/paper_record.yml", file=sys.stderr)
            return 1

    summary = {
        "_provenance": {
            "script": "e07/p0_select_observed_corpus.py",
            "experiment": "E07",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_rev": git_rev(),
            "python": sys.version.split()[0],
            "source": {
                "p4a_v1_copy": str(SRC.relative_to(REPO)),
                "observed_set": str(N0.relative_to(REPO)),
            },
            "params": {"expected_papers": EXPECTED_PAPERS, "md5_sample": MD5_SAMPLE,
                       "known_missing": sorted(f"{p}: {r}" for p, r in KNOWN_MISSING)},
        },
        "n_papers": len(papers),
        "corpus": str(CORPUS.relative_to(REPO)),
        "layers": layer_totals,
        "checks": {
            "required_files": "ok",
            "copy_parity_per_paper_per_layer": "ok",
            "md5_sampled": MD5_SAMPLE,
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "p0_corpus_summary.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    total_mb = sum(t["bytes"] for t in layer_totals.values()) / 1e6
    print(f"ok: {len(papers)} papers -> {CORPUS.relative_to(REPO)} ({total_mb:.0f} MB)")
    for layer, t in sorted(layer_totals.items()):
        print(f"  {layer}: {t['files']} files, {t['bytes'] / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
