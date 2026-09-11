"""E07 notebook 的产物读入层。

notebook 是探索面，不是流水线（见 AGENTS.md → Notebooks are the exploration
surface）。本模块只做一件事：把 `data/processed/e07/` 下 p0 生成的产物读出来，
并把 `_provenance` 摆到明面上 —— 让每本 notebook 开篇就声明自己在读哪一版产物。

它**不计算任何会被引用的量**。那些必须由 `src/e07/` 下的脚本产出。

用法：

    import nbio
    nbio.banner()           # 第一个 cell：这次读的是哪一版产物
    nbio.summary()          # -> dict，p0 已算好的聚合量
    nbio.CORPUS             # -> Path，952 篇论文的只读语料副本
"""

from __future__ import annotations

import json
from pathlib import Path

# notebooks/ -> e07-p4a-case-pool -> experiments -> 仓库根
REPO_ROOT = Path(__file__).resolve().parents[3]
OUT = REPO_ROOT / "data" / "processed" / "e07"
CORPUS = OUT / "corpus"


def summary(name: str = "p0_corpus_summary") -> dict:
    return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))


def banner() -> None:
    s = summary()
    p = s["_provenance"]
    print(f"E07 · {p['script']} @ {p['generated_at']} (git {p['git_rev']})")
    print(f"corpus: {s['n_papers']} 篇 <- {p['source']['p4a_v1_copy']}")
    print(f"observed set: {p['source']['observed_set']}")
    for layer, st in s["layers"].items():
        print(f"  {layer:8s} {st['files']:5d} files, {st['bytes'] / 2**20:8.1f} MiB")
