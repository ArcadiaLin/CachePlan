"""阶段 0：语料清单与纳入过滤。

把 4083 份 session 逐一登记，并**显式**判定纳入或排除。排除必须带理由，
理由必须可统计 —— 下游任何一张表都能回答「这个数字是在哪些 session 上算的」。

产物：data/processed/e01/s0_manifest.jsonl

用法：
    uv run -m e01.s0_manifest [--verify-source] [--limit N]
"""

from __future__ import annotations

import argparse
from collections import Counter

from . import provenance, wire

SCRIPT = "e01/s0_manifest.py"

# 纳入判据。每条都是排除理由的名字，写进产物的 exclude 字段。
EXCLUDE_NO_WIRE = "no_wire"            # 没有 main/wire.jsonl
EXCLUDE_NO_STEPS = "no_steps"          # 一步都没起（空会话）
EXCLUDE_ABORTED = "aborted"            # 起了步但没有任何一步跑完
EXCLUDE_NO_USAGE = "no_usage"          # 有完成的步但仍无 usage，属异常，需单独看
EXCLUDE_OPERATOR = "operator_chat"     # 操作者本人的交互，不是 workload 的一次运行

# `aborted` 不是坏数据，是**流产的 run**：观测到的形态一致为
# n_steps=1 / n_tools=0 / model=None —— step.begin 发了，step.end 没到。
# 它必须与「日志损坏」分开，因为它的发生率本身是这个 workload 的一个特征
# （见下方 abort_rate_by_family），把它并进 no_usage 会把一个观测量记成噪声。


def build(limit: int | None = None):
    rows = []
    for sdir in wire.session_dirs()[: limit or None]:
        s = wire.load(sdir, with_segments=False)

        excludes = []
        if "wire.jsonl missing" in s.errors:
            excludes.append(EXCLUDE_NO_WIRE)
        if s.n_steps == 0:
            excludes.append(EXCLUDE_NO_STEPS)
        elif not s.usage:
            # 起了步、没有任何一步跑完 → 流产，而非日志缺失
            excludes.append(EXCLUDE_ABORTED if s.n_tools == 0 else EXCLUDE_NO_USAGE)
        if s.family == "other":
            # 已知的 6 份是操作者手打的对话（"继续你的工作" 等）。归为 operator_chat
            # 而不是静默丢弃：清单里保留原文前 200 字，便于事后复核这个判断。
            excludes.append(EXCLUDE_OPERATOR)

        rows.append(
            {
                "sid": s.sid,
                "wd": sdir.parent.name,
                "included": not excludes,
                "exclude": excludes,
                "family": s.family,
                "paper_id": s.paper_id,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "model": s.model,
                "thinking": s.thinking,
                "n_active_tools": len(s.active_tools),
                "sysprompt_chars": len(s.system_prompt or ""),
                "user_prompt_chars": len(s.user_prompt or ""),
                "n_user_prompts": s.n_user_prompts,
                "n_subagent_dirs": s.n_subagent_dirs,
                "n_steps": s.n_steps,
                "n_turns": len(s.turns),
                "n_tools": s.n_tools,
                "errors": s.errors,
                # 排除项留证据，纳入项不留（省体积）
                "prompt_head": (s.user_prompt or "")[:200] if excludes else None,
            }
        )
    return rows


def abort_rate(rows) -> dict:
    """流产率：起了步却一步都没跑完的 run 占该家族发起总数的比例。

    分母是「发起过的 run」（排除 operator_chat 与无 wire 的），不是纳入集 ——
    流产的 run 恰恰不在纳入集里，用纳入集当分母会算出 0。
    """
    out = {}
    for fam in sorted({r["family"] for r in rows}):
        launched = [r for r in rows
                    if r["family"] == fam
                    and EXCLUDE_OPERATOR not in r["exclude"]
                    and EXCLUDE_NO_WIRE not in r["exclude"]]
        if not launched:
            continue
        aborted = [r for r in launched if EXCLUDE_ABORTED in r["exclude"]]
        out[fam] = {
            "launched": len(launched),
            "aborted": len(aborted),
            "rate": len(aborted) / len(launched),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-source", action="store_true",
                    help="核算来源 tar.gz 的 md5（约 350MB，数秒）")
    ap.add_argument("--limit", type=int, default=None, help="只扫前 N 份，用于冒烟测试")
    args = ap.parse_args()

    rows = build(limit=args.limit)
    hdr = provenance.header(SCRIPT, {"limit": args.limit},
                            verify_source=args.verify_source)
    path = provenance.write_jsonl("s0_manifest.jsonl", hdr, rows)

    inc = [r for r in rows if r["included"]]
    provenance.write_json("s0_summary.json", hdr, {
        "n_sessions": len(rows),
        "n_included": len(inc),
        "excluded_by_reason": dict(Counter(e for r in rows for e in r["exclude"])),
        "included_by_family": dict(Counter(r["family"] for r in inc)),
        "distinct_papers": len({r["paper_id"] for r in inc if r["paper_id"]}),
        "included_without_paper_id": sum(1 for r in inc if not r["paper_id"]),
        "abort_rate_by_family": abort_rate(rows),
        "n_active_tools_values": dict(Counter(r["n_active_tools"] for r in rows)),
        "sysprompt_chars_values": dict(Counter(r["sysprompt_chars"] for r in rows)),
    })
    print(f"[s0] 扫描 {len(rows)} 份 session → {path}")
    print(f"[s0] 纳入 {len(inc)}，排除 {len(rows) - len(inc)}")
    exc = Counter(e for r in rows for e in r["exclude"])
    for k, v in exc.most_common():
        print(f"       排除理由 {k}: {v}")
    print(f"[s0] 纳入集的 family 分布: {dict(Counter(r['family'] for r in inc))}")
    fam_paper = Counter(r["paper_id"] is not None for r in inc)
    print(f"[s0] 纳入集中能定位 paper_id 的: {fam_paper.get(True, 0)}/{len(inc)}")
    print(f"[s0] 纳入集覆盖的不同 paper 数: "
          f"{len({r['paper_id'] for r in inc if r['paper_id']})}")
    print("[s0] 流产率（起了步但一步没跑完 / 发起总数）:")
    for fam, d in abort_rate(rows).items():
        print(f"       {fam}: {d['aborted']}/{d['launched']} = {d['rate'] * 100:.1f}%")


if __name__ == "__main__":
    main()
