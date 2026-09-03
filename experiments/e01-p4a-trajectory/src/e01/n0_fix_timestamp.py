"""归一化 n0：把观测集里每 run 都变的时间戳固定成一个常量。

s0b 查明 systemPrompt 由若干生命周期不同的块拼成，其中只有 `## Date and Time`
是**每 run 必变**的。观测集（见下方 GROUP）已经把其余各轴钉死，因此只要把这一个
时间戳换成常量，全组的 systemPrompt 就逐字相同 —— 之后观察到的任何前缀分歧都只
可能来自轨迹，不再来自时钟。

**只做这一件事。** 产物与来源逐字节相同，只差 systemPrompt 里那 24 个字符：

- 非 `config.update` 的行原样透传，既不解析也不重新序列化；
- 流里其余像时间戳的东西是**内容**不是时钟（arXiv 的 `published`、GitHub 的
  commit date、论文的 `submitted` 字段），一律不动；
- `state.json` 的 `createdAt` 不动 —— 它不进上下文，改了会毁掉时序；
- 子 agent 的 wire 各有一个自己的时间戳，同样替换。

只复制 `wire.jsonl` 与 `state.json`：上下文流全部来自前者，`logs/`、`tool-results/`、
`tasks/` 是旁路产物，复制它们要多花 1.8 GB 换不到信息。

产物：
    data/processed/e01/n0_fixed_time/            与原始语料同构的归一化副本
    data/processed/e01/n0_fixed_time.jsonl       一行一份 session，记原时间戳
    data/processed/e01/n0_fixed_time_summary.json

用法：
    uv run -m e01.n0_fix_timestamp [--limit N] [--out-root DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
from pathlib import Path

from . import provenance, wire

SCRIPT = "e01/n0_fix_timestamp.py"

NAME = "n0_fixed_time"

# 观测集判据。四条轴各取一个值，叠加 s0 的纳入过滤，得到 961 份。
# 选它的理由见 docs/experiments/e01-p4a-trajectory.md §1.3。
# 改这里就是换观测集 —— notebook 从本模块 import，判据只有这一处定义。
GROUP = {
    "tools_tok_rel_ref": -3882,      # 轴 A 工具配置
    "axis_tree": "fb389653",         # 轴 D 项目目录树
    "delivery": "pointer",           # 轴 E 投递形态
    "harness_version": "V2",         # 轴 B harness 版本
}
GROUP_SIZE = 961

# 与原值等长（24 字符），落在本组 2026-07-05..07-08 的窗口内。等长是刻意的：
# 归一化前后的字符偏移量因此可比，s0b 量过的块偏移不用重算。
FIXED_TS = "2026-07-07T00:00:00.000Z"

# systemPrompt 里的时间戳带反引号，这把它与正文中偶然出现的日期区分开。
TS = re.compile(r"`(20\d\d-\d\d-\d\dT[\d:.]+Z)`")

# 每份 session 需要的列，分别来自哪个上游产物。
NEEDED = {
    "s0_manifest.jsonl": ["wd", "included", "family", "paper_id", "created_at"],
    "s0b_prompt_blocks.jsonl": ["axis_tree", "delivery", "harness_version"],
    "s3_render.jsonl": ["tools_tok_rel_ref"],
}


def select() -> list[dict]:
    """从上游产物里按 GROUP 选出观测集。stdlib 版的 join，键是 sid。"""
    rows: dict[str, dict] = {}
    for fname, cols in NEEDED.items():
        path = provenance.OUT_ROOT / fname
        if not path.exists():
            raise SystemExit(f"缺少上游产物 {path}，先跑 make all 与 make s3")
        n = 0
        for o in provenance.read_jsonl(path):
            n += 1
            r = rows.setdefault(o["sid"], {"sid": o["sid"]})
            for c in cols:
                r[c] = o.get(c)
        print(f"[n0] 读 {fname}: {n} 行")

    sel = [
        r for r in rows.values()
        if r.get("included") and all(r.get(k) == v for k, v in GROUP.items())
    ]
    sel.sort(key=lambda r: r["sid"])
    return sel


def fix_wire(src: Path, dst: Path) -> tuple[str, str]:
    """逐行复制一份 wire.jsonl，只把 systemPrompt 里的时间戳换成常量。

    返回 (原时间戳, 替换后 systemPrompt 的 md5)。这里的断言都是**产物正确性**的
    前提，不是防御性检查：多于一处替换、长度不等、找不到时间戳，任何一条成立都
    说明「只改 24 个字符」这个承诺不再成立，必须停下来而不是继续写。
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    orig = sp_md5 = None
    with open(src, encoding="utf-8", newline="") as fi, \
         open(dst, "w", encoding="utf-8", newline="") as fo:
        for line in fi:
            if '"config.update"' in line:
                o = json.loads(line)
                if o.get("type") == "config.update" and o.get("systemPrompt"):
                    assert orig is None, f"{src}: 不止一条带 systemPrompt 的 config.update"
                    m = TS.search(o["systemPrompt"])
                    assert m, f"{src}: systemPrompt 里没有时间戳"
                    orig = m.group(1)
                    assert len(orig) == len(FIXED_TS), \
                        f"{src}: 时间戳长度 {len(orig)}，与常量不等长"
                    assert line.count(orig) == 1, \
                        f"{src}: 该行里时间戳出现 {line.count(orig)} 次，逐字替换不安全"
                    line = line.replace(orig, FIXED_TS)
                    sp_md5 = hashlib.md5(
                        o["systemPrompt"].replace(orig, FIXED_TS).encode()
                    ).hexdigest()
            fo.write(line)
    assert orig is not None, f"{src}: 没找到 systemPrompt"
    return orig, sp_md5


def build(sel: list[dict], corpus: Path) -> list[dict]:
    if corpus.exists():
        shutil.rmtree(corpus)
    out = []
    for r in sel:
        sdir = provenance.RAW_ROOT / r["wd"] / r["sid"]
        ddir = corpus / r["wd"] / r["sid"]
        orig, sp_md5 = fix_wire(sdir / "agents/main/wire.jsonl",
                                ddir / "agents/main/wire.jsonl")
        shutil.copy2(sdir / "state.json", ddir / "state.json")

        subs = {}
        for a in sorted((sdir / "agents").glob("agent-*")):
            if (a / "wire.jsonl").exists():
                subs[a.name] = fix_wire(a / "wire.jsonl",
                                        ddir / "agents" / a.name / "wire.jsonl")[0]

        out.append({
            "sid": r["sid"], "wd": r["wd"], "paper_id": r.get("paper_id"),
            "created_at": r.get("created_at"),
            "orig_timestamp": orig,
            "sysprompt_md5": sp_md5,
            "subagents": subs,
        })
    return out


def verify(rows: list[dict], corpus: Path, sample: int = 20) -> dict:
    """三条自查。任何一条不过就不该有产物，故直接断言而不是记进 summary。"""
    dirs = wire.session_dirs(root=corpus)
    assert len(dirs) == len(rows), f"产物里 {len(dirs)} 份，索引 {len(rows)} 份"

    # 1. 归一化后全组 systemPrompt 必须只剩一个值 —— 这就是本阶段的目的
    md5s = {r["sysprompt_md5"] for r in rows}
    assert len(md5s) == 1, f"归一化后仍有 {len(md5s)} 个不同的 systemPrompt"
    md5 = md5s.pop()

    rnd = random.Random(0)
    picks = rnd.sample(dirs, min(sample, len(dirs)))

    # 2. 除那 24 个字符外没动过：与来源逐字节比对
    for d in picks:
        src = provenance.RAW_ROOT / d.parent.name / d.name / "agents/main/wire.jsonl"
        a, b = src.read_bytes(), (d / "agents/main/wire.jsonl").read_bytes()
        assert len(a) == len(b), f"{d.name}: 长度变了"
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        assert diff and diff[-1] - diff[0] < len(FIXED_TS), \
            f"{d.name}: 差异散布在 {len(diff)} 个字节，不止时间戳那一段"

    # 3. 轨迹本身不受影响
    for d in picks:
        got = wire.load(d).tool_seq
        want = wire.load(provenance.RAW_ROOT / d.parent.name / d.name).tool_seq
        assert got == want, f"{d.name}: 工具调用序列被改动了"

    return {
        "sysprompt_md5_after": md5,
        "n_distinct_sysprompt_before": len({r["orig_timestamp"] for r in rows}),
        "n_distinct_sysprompt_after": 1,
        "byte_parity_sampled": len(picks),
    }


def summarize(rows: list[dict], corpus: Path, checks: dict) -> dict:
    ts = sorted(r["orig_timestamp"] for r in rows)
    subs = [len(r["subagents"]) for r in rows]
    return {
        "group": GROUP,
        "n_sessions": len(rows),
        "n_papers": len({r["paper_id"] for r in rows if r["paper_id"]}),
        "fixed_timestamp": FIXED_TS,
        "orig_timestamp_span": {"min": ts[0], "max": ts[-1]} if ts else None,
        "n_with_subagents": sum(1 for n in subs if n),
        "n_subagent_wires": sum(subs),
        "corpus": corpus.name,
        "corpus_bytes": sum(p.stat().st_size for p in corpus.rglob("*") if p.is_file()),
        "checks": checks,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="只处理观测集的前 N 份（按 sid 排序），用于自检")
    ap.add_argument("--out-root", type=Path, default=None,
                    help="产物根目录，默认 data/processed/e01/。自检时指向临时目录，"
                         "避免用局部结果覆盖全量语料")
    args = ap.parse_args()

    out_root = args.out_root or provenance.OUT_ROOT
    out_root.mkdir(parents=True, exist_ok=True)
    corpus = out_root / NAME

    sel = select()
    print(f"[n0] 观测集 {len(sel)} 份")
    if args.limit is None:
        assert len(sel) == GROUP_SIZE, \
            f"观测集份数不是 {GROUP_SIZE} 而是 {len(sel)}，判据或上游产物变了"
    else:
        sel = sel[: args.limit]
        print(f"[n0] --limit {args.limit}：只处理前 {len(sel)} 份，结论不成立")
    assert sel, "观测集为空"

    rows = build(sel, corpus)
    checks = verify(rows, corpus)
    summ = summarize(rows, corpus, checks)

    header = provenance.header(
        SCRIPT, params={"limit": args.limit, "group": GROUP, "fixed_timestamp": FIXED_TS}
    )
    provenance.write_jsonl(f"{NAME}.jsonl", header, rows, root=out_root)
    provenance.write_json(f"{NAME}_summary.json", header, summ, root=out_root)

    print(f"[n0] {corpus} {summ['n_sessions']} 份 {summ['corpus_bytes'] / 1e6:.0f} MB")
    print(f"[n0] 时间戳 {summ['orig_timestamp_span']['min']} .. "
          f"{summ['orig_timestamp_span']['max']} -> {FIXED_TS}")
    print(f"[n0] ✓ systemPrompt 由 {len(rows)} 个互异值归为 1 个"
          f"（md5 {checks['sysprompt_md5_after'][:8]}）")
    print(f"[n0] ✓ 抽样 {checks['byte_parity_sampled']} 份：字节差异只落在那 24 字符里，"
          f"工具序列不变")


if __name__ == "__main__":
    main()
