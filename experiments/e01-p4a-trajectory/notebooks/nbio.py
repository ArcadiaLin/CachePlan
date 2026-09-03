"""E01 notebook 的产物读入层。

notebook 是探索面，不是流水线（见 AGENTS.md → Notebooks are the exploration
surface）。本模块只做一件事：把 `data/processed/e01/` 下 s0–s4 生成的产物读成
DataFrame，并把该产物的 `_provenance` 摆到明面上 —— 让每本 notebook 开篇就声明
自己在读哪一版产物。

它**不计算任何会被引用的量**。那些必须由 `src/e01/` 下的脚本产出。

用法：

    import nbio
    nbio.banner()              # 第一个 cell：这次读的是哪一版，是否被 --limit 污染
    s0 = nbio.load("s0")       # -> DataFrame，一行一份 session
    summ = nbio.summary("s0")  # -> dict，脚本已算好的聚合量
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# notebooks/ -> e01-p4a-trajectory -> experiments -> 仓库根
REPO_ROOT = Path(__file__).resolve().parents[3]
OUT = REPO_ROOT / "data" / "processed" / "e01"

# 阶段 -> (逐 session 的 jsonl, 聚合 json)。s1 只有结论，没有逐 session 表。
STAGES: dict[str, tuple[str | None, str]] = {
    "s0": ("s0_manifest.jsonl", "s0_summary.json"),
    "s0b": ("s0b_prompt_blocks.jsonl", "s0b_summary.json"),
    "s1": (None, "s1_cache_fields.json"),
    "s2": ("s2_session_stats.jsonl", "s2_summary.json"),
    "s3": ("s3_render.jsonl", "s3_render_summary.json"),
    "s4": ("s4_divergence.jsonl", "s4_summary.json"),
}


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def summary(stage: str) -> dict:
    """脚本已经算好的聚合量。原样返回，不重算。"""
    return _read_json(OUT / STAGES[stage][1])


def provenance(stage: str) -> dict:
    return summary(stage)["_provenance"]


def load(stage: str) -> pd.DataFrame:
    """逐 session 的表。jsonl 的第一行是 `_provenance`，跳过。"""
    name = STAGES[stage][0]
    if name is None:
        raise KeyError(f"{stage} 没有逐 session 产物，只有 summary")
    path = OUT / name
    with open(path, encoding="utf-8") as f:
        first = json.loads(f.readline())
        assert "_provenance" in first, f"{path} 首行不是 _provenance，产物格式变了"
        rows = [json.loads(line) for line in f]
    return pd.DataFrame(rows)


def banner(stages: list[str] | None = None) -> pd.DataFrame:
    """把在场产物的来源摊开。放在每本 notebook 的第一个 cell。

    两件事必须一眼看见：
    1. 各阶段是不是同一个 git rev 下跑出来的 —— 不是的话交叉分析可能不自洽；
    2. 有没有产物是 `--limit` 跑出来的 —— `make smoke` 与 `verify-stdlib` 写的是
       与全量同名的文件，被覆盖过的产物只有前 50 份，任何结论都不成立。
    """
    stages = stages or list(STAGES)
    rows = []
    for st in stages:
        path = OUT / STAGES[st][1]
        if not path.exists():
            rows.append({"stage": st, "状态": "缺失"})
            continue
        p = provenance(st)
        limit = p.get("params", {}).get("limit")
        rows.append(
            {
                "stage": st,
                "脚本": p["script"],
                "git_rev": p["git_rev"],
                "生成时间": p["generated_at"],
                "limit": limit,
                "源字节数": p["source"]["bytes"],
            }
        )
    df = pd.DataFrame(rows)

    present = df[df.get("git_rev").notna()] if "git_rev" in df else df
    revs = sorted(set(present["git_rev"].dropna())) if len(present) else []
    if len(revs) > 1:
        print(f"⚠ 各阶段产物来自不同 git rev：{revs}，交叉分析前先确认口径一致")
    limited = present[present["limit"].notna()] if "limit" in present else []
    if len(limited):
        print(f"⛔ 这些阶段是 --limit 跑出来的，不是全语料：{list(limited['stage'])}")
    return df


def wide() -> pd.DataFrame:
    """s0 × s2 × s3 × s4 按 sid 合成的一张宽表。

    四个阶段各自只看自己那一层，跨层的问题（某个工具配置的注入浪费、放大倍数
    与前缀失效的关系）必须 join 之后才能问。合并键是 sid；以 s0 的全部 4083 份
    为左表，未纳入的 session 在右侧各列为 NaN。
    """
    df = load("s0")
    for st, cols in (
        ("s0b", ["sid", "harness_version", "axis_harness", "axis_tree", "axis_agents",
                 "axis_skills", "axis_timestamp", "timestamp_offset",
                 "poisoned_tail_chars",
                 "delivery", "prompt_chars", "pointer_layout", "pid_year"]),
        ("s2", None),
        ("s3", ["sid", "prompt_tokens", "tools_tok_rel_ref", "tools_hash", "exact"]),
        ("s4", ["sid", "n_injections", "invalidated_tokens", "first_injection_step"]),
    ):
        right = load(st)
        if cols:
            right = right[[c for c in cols if c in right.columns]]
        right = right.drop(columns=[c for c in right.columns if c != "sid" and c in df.columns])
        df = df.merge(right, on="sid", how="left", suffixes=("", f"_{st}"))
    return df
