"""阶段 3 第一步：还原器自检 + 全语料工具集判定。

s3 的目标是逐字还原进入模型的 token 序列。动手之前必须先回答一个问题：
**每份 session 当时挂的是哪一套工具？** 工具块先于 systemPrompt 渲染进第一条
system 消息，占首步 prompt 的八成以上；工具集判错，后面每个数都是错的。

## 两件事

1. **自检。** 60 份 session 带 `llm.tools_snapshot`（工具 schema 全文）。把它们
   的**每一步**都还原出来，token 数与服务端记录的 `prompt_tokens` 比对。

   只验首步不够：首步只覆盖 system + tools + 用户消息，验不到 assistant 消息、
   tool_calls 和工具结果的渲染规则（后者尤其容易错，见 context_builder.py）。

   精确率低于 95% 直接退出 —— 那说明还原链条本身坏了（模板、分词器或渲染规则
   被动过），下游判定全部无效。个别异常不停，但逐条打印并在产物里标注
   `exact=false`，那些 session 不得进入逐字分析。

   当前实测 1123/1142 步精确（98.34%），唯一的偏差是一份 session 在 step7 处
   跳变 −25 token，成因未查明，已排除该 session。

2. **判定。** 另外那 4000 多份没有快照。但还原器既然是精确的：

       Δ(候选) = 渲染(真 systemPrompt + 真 messages + 候选工具) - 实测 prompt_tokens
               = tokens(候选工具块) - tokens(真工具块)

   于是真工具块的 token 数可以**精确解出**，不必知道它的内容。按这个数分组，
   就得到语料里到底存在几套工具配置。

## 产物

    s3_render.jsonl          逐 session：解出的工具块 token 数、所属分组
    s3_render_summary.json   自检结果、分组表（含时间跨度）、建议的分析队列

## 用法

    uv sync --extra render
    uv run -m e01.s3_render [--limit N] [--verify-source]
"""

from __future__ import annotations

import argparse
import datetime
from collections import defaultdict

from . import context_builder, provenance, render, wire

SCRIPT = "e01/s3_render.py"

# 参照候选：工具最多的那一套。所有 token 数都表示为「相对它的差」，
# 这样一份 session 只需渲染一次，不必对四个候选各渲染一遍。
REF_HASH_PREFIX = "aca0350b"


def _ts(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.datetime.fromtimestamp(ms / 1000).isoformat(sep=" ", timespec="seconds")


def collect_candidates(sdirs) -> dict[str, list[dict]]:
    """从带快照的 session 里收集所有不同的工具集。"""
    cands: dict[str, list[dict]] = {}
    for sd in sdirs:
        r = wire.first_request(sd)
        if r.tools is None or not r.tools_hash:
            continue
        cands.setdefault(r.tools_hash[:8], r.tools)
    return cands


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-source", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not render.available():
        raise SystemExit(
            "还原器不可用。s3 不接受字符级退化结果 —— 装齐依赖再来：\n"
            "  uv sync --extra render\n"
            f"并确认分词器在 {render.TOKENIZER_DIR}"
        )

    manifest = {
        r["sid"]: r
        for r in provenance.read_jsonl(provenance.open_out("s0_manifest.jsonl"))
    }

    all_dirs = wire.session_dirs()
    # 候选始终从全语料收集，与 --limit 无关：--limit 只截断被判定的范围。
    cands = collect_candidates(all_dirs)
    if REF_HASH_PREFIX not in cands:
        raise SystemExit(f"参照候选 {REF_HASH_PREFIX} 不在语料里，无法定标")
    wrapped = {h: render.wrap_tools(t) for h, t in cands.items()}
    order = sorted(cands, key=lambda h: len(cands[h]))

    # 各候选工具块的相对大小：用同一份探针消息渲染，差值即工具块 token 差。
    probe = [{"role": "system", "content": "s"}, {"role": "user", "content": "x"}]
    probe_tok = {h: render.count(render.render(probe, wrapped[h])) for h in order}
    rel_size = {h: probe_tok[h] - probe_tok[REF_HASH_PREFIX] for h in order}

    # ---- 1. 自检：带 ground truth 的 session，**每一步**都要 Δ=0 ----
    # 只验首步是不够的：首步只覆盖 system + tools + 用户消息，验不到
    # assistant 消息、tool_calls 和工具结果的渲染规则。
    n_sessions, n_steps, mismatched = 0, 0, []
    inexact_sids: set[str] = set()
    for sd in all_dirs:
        ctx = context_builder.build(sd)
        if ctx.tools is None or not ctx.system_prompt:
            continue
        n_sessions += 1
        wrapped_gt = render.wrap_tools(ctx.tools)
        prev_delta = 0
        for st in ctx.steps:
            if st.prompt_tokens is None:
                continue
            n_steps += 1
            n = render.count(render.render(
                context_builder.messages_for(ctx, st), wrapped_gt))
            d = n - st.prompt_tokens
            if d:
                inexact_sids.add(ctx.sid)
                # 一处偏差会一路带到后面每一步。只记「跳变」——那才是新增的
                # 一处失配，也才是要查的地方。
                mismatched.append({"sid": ctx.sid, "step": st.step, "delta": d,
                                   "jump": d - prev_delta,
                                   "rendered": n, "measured": st.prompt_tokens,
                                   "is_new": d != prev_delta})
            prev_delta = d

    n_exact = n_steps - len(mismatched)
    rate = n_exact / n_steps if n_steps else 0.0
    jumps = [m for m in mismatched if m["is_new"]]

    # 大面积对不上 = 还原链条本身坏了（模板、分词器、渲染规则被改动），
    # 此时下游的判定全部无效，必须停。个别异常不停，但要逐条报出来。
    if rate < 0.95:
        for m in jumps[:10]:
            print(f"  {m['sid']} step{m['step']} 复现 {m['rendered']} "
                  f"实测 {m['measured']} Δ={m['delta']:+d}")
        raise SystemExit(
            f"自检失败：只有 {n_exact}/{n_steps} 步精确（{rate:.1%}）。还原链条不准，"
            "下面的判定结果无效。查 render.py 与 context_builder.py 的模块文档，"
            "那里列了每一处必须逐字一致的地方。"
        )

    print(f"[s3] 自检：{n_sessions} 份 ground-truth session，"
          f"{n_exact}/{n_steps} 步精确（{rate:.2%}）")
    if jumps:
        print(f"[s3] ⚠ {len(inexact_sids)} 份 session 存在未解释的偏差，"
              f"共 {len(jumps)} 处跳变（后续步的偏差是它带下来的）：")
        for m in jumps:
            print(f"     {m['sid']} step{m['step']} 跳变 {m['jump']:+d} "
                  f"(复现 {m['rendered']} 实测 {m['measured']})")
        print("     这些 session 不可用于逐字分析，已在产物里标注 exact=false。")

    # ---- 2. 判定 ----
    dirs = all_dirs[: args.limit] if args.limit else all_dirs
    rows, skipped = [], []
    for sd in dirs:
        r = wire.first_request(sd)
        m = manifest.get(sd.name)
        if r.prompt_tokens is None or not r.system_prompt or not r.messages:
            skipped.append({"sid": sd.name,
                            "reason": "无首步 usage / 无 systemPrompt / 无消息"})
            continue
        text = render.render(wire.openai_messages(r), wrapped[REF_HASH_PREFIX])
        delta = render.count(text) - r.prompt_tokens
        # 真工具块比参照候选大多少 token。这就是分组键。
        group = -delta
        known = [h for h, v in rel_size.items() if v == group]
        rows.append({
            "sid": r.sid,
            "included": bool(m["included"]) if m else None,
            "family": m["family"] if m else None,
            "created_at": _ts(r.created_at_ms),
            "created_at_ms": r.created_at_ms,
            "prompt_tokens": r.prompt_tokens,
            "tools_tok_rel_ref": group,
            "tools_hash": r.tools_hash[:8] if r.tools_hash else None,
            "matches_known_candidate": known[0] if known else None,
            # 仅对有 ground truth 的 60 份有意义：逐步还原是否每一步都 Δ=0。
            # false 表示存在未解释的偏差，不可用于逐字分析。
            "exact": (r.sid not in inexact_sids) if r.tools_hash else None,
        })

    hdr = provenance.header(SCRIPT, {"limit": args.limit, "ref": REF_HASH_PREFIX},
                            verify_source=args.verify_source)
    provenance.write_jsonl("s3_render.jsonl", hdr, rows)

    # ---- 分组表 ----
    groups = defaultdict(list)
    for r in rows:
        groups[r["tools_tok_rel_ref"]].append(r)
    table = []
    for g, grp in sorted(groups.items(), key=lambda kv: min(
            r["created_at_ms"] or 0 for r in kv[1])):
        times = [r["created_at_ms"] for r in grp if r["created_at_ms"]]
        known = [h for h, v in rel_size.items() if v == g]
        table.append({
            "tools_tok_rel_ref": g,
            "n_sessions": len(grp),
            "n_included": sum(1 for r in grp if r["included"]),
            "first_seen": _ts(min(times)) if times else None,
            "last_seen": _ts(max(times)) if times else None,
            "known_candidate": known[0] if known else None,
            "n_tools": len(cands[known[0]]) if known else None,
        })

    matched = sum(t["n_sessions"] for t in table if t["known_candidate"])
    summary = {
        "self_check": {
            "n_ground_truth_sessions": n_sessions,
            "n_steps_verified": n_steps,
            "n_steps_exact": n_exact,
            "exact_rate": round(rate, 6),
            "n_sessions_inexact": len(inexact_sids),
            "unexplained_jumps": jumps,
        },
        "candidates": {h: {"n_tools": len(cands[h]), "tools_tok_rel_ref": rel_size[h]}
                       for h in order},
        "n_classified": len(rows),
        "n_skipped": len(skipped),
        "skipped": skipped[:50],
        "n_distinct_tool_configs": len(table),
        "n_sessions_matching_known_candidate": matched,
        "n_sessions_matching_none": len(rows) - matched,
        "groups": table,
        "note": (
            "分组键是「真工具块 token 数 − 参照候选工具块 token 数」，由 Δ oracle 精确解出。"
            "同一个键不保证工具内容相同（token 数相等仍可能内容不同），但不同的键**必然**"
            "是不同的工具集。因此 n_distinct_tool_configs 是配置数量的下界。"
        ),
    }
    path = provenance.write_json("s3_render_summary.json", hdr, summary)

    print(f"[s3] 判定 {len(rows)} 份，跳过 {len(skipped)} 份")
    print(f"[s3] 不同工具配置：{len(table)} 种（下界）；"
          f"能对上已知候选的 {matched} 份，对不上的 {len(rows) - matched} 份")
    print(f"{'相对token':>10} {'份数':>6} {'纳入':>6}  {'最早':>19}  {'最晚':>19}  候选")
    for t in table:
        k = f"{t['known_candidate']} ({t['n_tools']} 工具)" if t["known_candidate"] else ""
        print(f"{t['tools_tok_rel_ref']:>+10d} {t['n_sessions']:>6d} {t['n_included']:>6d}"
              f"  {t['first_seen']}  {t['last_seen']}  {k}")
    print(f"[s3] → {path}")


if __name__ == "__main__":
    main()
