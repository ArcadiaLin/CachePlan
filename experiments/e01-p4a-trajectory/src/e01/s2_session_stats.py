"""阶段 2：会话级统计与放大倍数的分层归因。

回答 E01 的第二个测量目标：把原先 n=80 的抽样扩到全量，检验放大倍数
究竟与轮数相关还是与论文长度相关。

这里的「放大倍数」定义写死为：

    amplification = Σ_step inputOther / max_step inputOther

分子是这一次 run 实际付出的 prefill 总量，分母是理想情况下（会话内前缀
缓存完全命中）只需付出一次的那部分。它衡量的是**会话内**重复 prefill，
与跨 run 复用是两回事，不要混。

产物：data/processed/e01/s2_session_stats.jsonl（逐 session）
      data/processed/e01/s2_summary.json（汇总）

用法：
    uv run -m e01.s2_session_stats
"""

from __future__ import annotations

import argparse
from collections import Counter

from . import provenance, stats, wire

SCRIPT = "e01/s2_session_stats.py"

# 需要走网络/外部服务的工具。用于「外部检索是否是轨迹分叉主因」这一问。
EXTERNAL_TOOL_PREFIXES = ("mcp__", "FetchURL")


def is_external(name: str) -> bool:
    return name.startswith(EXTERNAL_TOOL_PREFIXES)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-source", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    manifest = {
        r["sid"]: r
        for r in provenance.read_jsonl(provenance.open_out("s0_manifest.jsonl"))
    }

    rows = []
    for sdir in wire.session_dirs()[: args.limit or None]:
        m = manifest.get(sdir.name)
        if m is not None and not m["included"]:
            continue
        s = wire.load(sdir, with_segments=False)
        if not s.usage:
            continue
        peak = s.peak_input
        tools = s.tool_seq
        rows.append(
            {
                "sid": s.sid,
                "family": s.family,
                "paper_id": s.paper_id,
                "n_steps": s.n_steps,
                "n_tools": s.n_tools,
                "sum_input": s.sum_input,
                "peak_input": peak,
                "first_step_input": s.usage[0].input_other,
                "sum_output": sum(u.output for u in s.usage),
                "amplification": (s.sum_input / peak) if peak else None,
                "n_external": sum(1 for t in tools if is_external(t)),
                "n_bash": tools.count("Bash"),
                "n_read": tools.count("Read"),
                "n_edit": tools.count("Edit") + tools.count("Write"),
                "n_todo": tools.count("TodoList"),
                "finish_reasons": s.finish_reasons,
                "tool_seq": tools,
                "tool_steps": [t[0] for t in s.tool_calls],
                "ttft_ms": s.ttft_ms,
                "stream_ms": s.stream_ms,
            }
        )

    hdr = provenance.header(SCRIPT, {"limit": args.limit},
                            verify_source=args.verify_source)
    provenance.write_jsonl("s2_session_stats.jsonl", hdr, rows)

    # ---- 汇总 ----
    summary: dict = {"n_sessions": len(rows), "by_family": {}}
    for fam in sorted({r["family"] for r in rows}):
        grp = [r for r in rows if r["family"] == fam]
        amps = [r["amplification"] for r in grp if r["amplification"]]
        summary["by_family"][fam] = {
            "n": len(grp),
            "n_steps": stats.quantiles([r["n_steps"] for r in grp]),
            "n_tools": stats.quantiles([r["n_tools"] for r in grp]),
            "peak_input": stats.quantiles([r["peak_input"] for r in grp]),
            "sum_input": stats.quantiles([r["sum_input"] for r in grp]),
            "amplification": stats.quantiles(amps),
            "n_external": stats.quantiles([r["n_external"] for r in grp]),
            "sessions_with_zero_external": sum(1 for r in grp if r["n_external"] == 0),
        }

    # 放大倍数的归因：轮数 vs 上下文规模
    ex = [r for r in rows if r["family"] == "extract"]
    steps = [r["n_steps"] for r in ex]
    summary["attribution_extract"] = {
        "note": "peak_input 是论文长度/输入体量的代理；n_steps 是轮数。",
        "corr_steps_vs_sum_input": stats.pearson(steps, [r["sum_input"] for r in ex]),
        "corr_peak_vs_sum_input": stats.pearson(
            [r["peak_input"] for r in ex], [r["sum_input"] for r in ex]),
        "corr_steps_vs_peak_input": stats.pearson(
            steps, [r["peak_input"] for r in ex]),
        "corr_external_vs_steps": stats.pearson(
            [r["n_external"] for r in ex], steps),
        "first_step_input": stats.quantiles([r["first_step_input"] for r in ex]),
    }

    # 工具画像：按轮数分位分层
    ex_sorted = sorted(ex, key=lambda r: r["n_steps"])
    bands = {
        "shortest_10pct": ex_sorted[: max(1, len(ex) // 10)],
        "middle_20pct": ex_sorted[len(ex) * 2 // 5: len(ex) * 3 // 5],
        "longest_10pct": ex_sorted[-max(1, len(ex) // 10):],
    }
    summary["tool_profile_by_length"] = {}
    for label, grp in bands.items():
        c = Counter()
        for r in grp:
            c.update(r["tool_seq"])
        summary["tool_profile_by_length"][label] = {
            "n": len(grp),
            "mean_steps": sum(r["n_steps"] for r in grp) / len(grp),
            "calls_per_run": {k: round(v / len(grp), 2) for k, v in c.most_common(10)},
        }

    # 全语料工具频次
    c = Counter()
    for r in rows:
        c.update(r["tool_seq"])
    summary["tool_frequency"] = dict(c.most_common())

    # 逐位置的工具去重数：轨迹在第几个调用处开始分叉
    seqs = [r["tool_seq"] for r in ex if r["tool_seq"]]
    pos_rows = []
    for i in range(20):
        cc = Counter(s[i] for s in seqs if len(s) > i)
        if not cc:
            break
        top, n = cc.most_common(1)[0]
        pos_rows.append({
            "position": i + 1,
            "coverage": sum(cc.values()),
            "distinct_tools": len(cc),
            "mode": top,
            "mode_share": n / sum(cc.values()),
        })
    summary["tool_position_divergence"] = pos_rows

    provenance.write_json("s2_summary.json", hdr, summary)

    # ---- 控制台摘要 ----
    print(f"[s2] {len(rows)} 份 session → data/processed/e01/")
    for fam, d in summary["by_family"].items():
        print(f"-- {fam} (n={d['n']}) --")
        print(stats.fmt(d["n_steps"], "n_steps"))
        print(stats.fmt(d["n_tools"], "n_tools"))
        print(stats.fmt(d["peak_input"], "peak_input(tok)"))
        print(stats.fmt(d["sum_input"], "sum_input(tok)"))
        q = d["amplification"]
        if q:
            print(f"  amplification: p10={q['p10']:.1f} p50={q['p50']:.1f} "
                  f"p90={q['p90']:.1f} max={q['max']:.1f}")
    a = summary["attribution_extract"]
    print("[s2] 放大倍数归因（extract）:")
    print(f"  corr(n_steps,  sum_input) = {a['corr_steps_vs_sum_input']:.3f}")
    print(f"  corr(peak_in,  sum_input) = {a['corr_peak_vs_sum_input']:.3f}")
    print(f"  corr(n_steps,  peak_in)   = {a['corr_steps_vs_peak_input']:.3f}")
    print("[s2] 轨迹分叉（前 6 个工具调用位置）:")
    for p in summary["tool_position_divergence"][:6]:
        print(f"  pos {p['position']:2d}: 去重 {p['distinct_tools']:3d} 种, "
              f"众数 {p['mode']} {p['mode_share'] * 100:.1f}%")


if __name__ == "__main__":
    main()
