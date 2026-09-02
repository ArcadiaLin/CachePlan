"""阶段 4：前缀失效的两个来源，各自量化。

s3 证明了上下文可以逐字还原。本阶段回答「前缀在哪儿断、断掉多少 token」。
来源有两个，量级差 35 倍，容易只盯着后一个：

  A. **会话内**：harness 中途注入一条 role=user 消息，**回溯性改写**此前的
     全部历史，把已经涨到七八万 token 的上下文缓存一次性作废。
  B. **跨 run**：两次 run 的首步 prompt 在什么位置分叉。每 run 只付一次。

## A 的机制

chat template 里这一行决定 assistant 消息保不保留 `<think>`：

    {%- if ... or (loop.index0 > ns.last_query_index) %}

`ns.last_query_index` 是**最后一条非 tool_response 的 role=user 消息**的下标
（工具结果是 role=tool，不参与）。每追加一条 role=user 消息，它就前移一次，
于是此前所有 assistant 消息一起掉出保留区间，`<think>...</think>` 被剥掉 ——
上下文中段被改写，不再是纯追加。

存活前缀 = messages[0..i_prev] 加上生成提示词的头几个字符。而
messages[0..i_prev] 恰好是**紧接上一次注入之后那一步**的完整上下文（那一步
的上下文正好以第 i_prev 条消息结尾）。于是不必渲染也能算：

    作废 tokens = inputOther[注入前最后一步] − inputOther[上一次注入后的第一步] + c

`c` 是生成提示词的边界修正：存活的是 `<|im_start|>assistant\\n<t`，而
inputOther 里是完整的 `<|im_start|>assistant\\n<think>\\n`。

这个公式必须先验后用。`--check` 在有 ground truth 的 session 上逐步精确渲染，
核对两件事：(1) 公式与精确值只差一个常数；(2) 注入次数 == 实际发生改写的
次数（即注入是非追加式增长的唯一成因）。实测 c = +2，两条都成立。

全语料不能逐步渲染 —— 累计 56 亿 token —— 但 inputOther 每一步都有。

## B 的四个层级

工具块在同一配置区块内逐字相同且渲染在最前，所以只比较**工具块之后**那一段，
再把区块已知的工具块 token 数加回去。这样没有工具 schema 原文的区块也能算。

    L0  原样
    L1  + systemPrompt 里的会话启动时间戳归一
    L2  + 工作目录树归一（systemPrompt 完全一致）
    L3  + 首条用户消息不含论文对象

L2 那一级是 kimi-code 注入 systemPrompt 的工作目录树 —— P4A 自己在运行中往
里写文件，等于自己破坏自己的前缀。

## 产物

    s4_divergence.jsonl     逐 session：注入次数、作废 token、首次注入步号
    s4_summary.json         A 的全语料汇总、B 的层级表、自检结果

## 用法

    make setup-render
    uv run --extra render -m e01.s4_divergence [--check] [--group N]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter

from . import context_builder, provenance, render, wire

SCRIPT = "e01/s4_divergence.py"

# 生成提示词的边界修正，由 --check 标定。改动渲染链条后必须重新标定。
BOUNDARY = 2

ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
# 工具块与 systemPrompt 的分界。模板里工具块以这个标记收尾。
TOOLS_END = "</IMPORTANT>"


# --------------------------------------------------------------------------
# A：会话内注入
# --------------------------------------------------------------------------

def _is_tool_response(text: str) -> bool:
    """模板不把纯 tool_response 的 user 消息当作 query。"""
    t = text.strip()
    return t.startswith("<tool_response>") and t.endswith("</tool_response>")


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in (content or []) if isinstance(p, dict))


def scan_injections(sdir):
    """轻量扫描：每步 inputOther + 首步之后追加的 role=user 消息。

    不保留消息正文 —— 长会话里那是全部工具结果，全语料扫描扛不住。
    """
    steps: dict[int, int | None] = {}
    injections: list[tuple[int, str]] = []
    started = False
    pending: list[str] = []

    with open(sdir / "agents" / "main" / "wire.jsonl",
              encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("type")

            if t == "context.append_message":
                if not started:
                    continue      # 首步之前的那两条是初始消息，不算注入
                m = o.get("message") or {}
                if m.get("role") != "user":
                    continue
                s = _message_text(m.get("content"))
                if _is_tool_response(s):
                    continue
                pending.append(s.strip()[:120])
            elif t == "context.append_loop_event":
                e = o.get("event") or {}
                et = e.get("type")
                if et == "step.begin":
                    started = True
                    for s in pending:
                        injections.append((e.get("step"), s))
                    pending = []
                elif et == "step.end":
                    steps[e.get("step")] = (e.get("usage") or {}).get("inputOther")
    return steps, injections


def invalidated(steps: dict, injections: list) -> tuple[int, list]:
    """按公式算这份 session 因注入而作废的 token 总量。"""
    anchor = 1          # 上一次「注入后的第一步」，初始为首步
    total = 0
    detail = []
    for step, _head in injections:
        prev, base = steps.get(step - 1), steps.get(anchor)
        if prev is None or base is None:
            continue
        v = prev - base + BOUNDARY
        if v > 0:
            total += v
            detail.append({"before_step": step, "invalidated": v})
        anchor = step
    return total, detail


def self_check() -> dict:
    """在有 ground truth 的 session 上标定公式。见模块文档。"""
    tok = render._tokenizer()
    diffs = Counter()
    count_mismatch = []
    n_sessions = 0

    for sd in wire.session_dirs():
        ctx = context_builder.build(sd)
        if ctx.tools is None or not ctx.system_prompt:
            continue
        n_sessions += 1
        w = render.wrap_tools(ctx.tools)
        ids = [tok.encode(render.render(context_builder.messages_for(ctx, s), w),
                          add_special_tokens=False).ids for s in ctx.steps]

        # 精确值：逐步比 token 级公共前缀，前缀短于上一步即发生改写
        exact = {}
        for i in range(1, len(ids)):
            a, b = ids[i - 1], ids[i]
            k = 0
            while k < min(len(a), len(b)) and a[k] == b[k]:
                k += 1
            if k < len(a) - 3:      # 容忍生成提示词的边界差
                exact[ctx.steps[i].step] = len(a) - k

        steps, inj = scan_injections(sd)
        _total, detail = invalidated(steps, inj)
        pred = {d["before_step"]: d["invalidated"] for d in detail}

        if set(exact) != set(pred):
            count_mismatch.append({"sid": ctx.sid,
                                   "exact_steps": sorted(exact),
                                   "predicted_steps": sorted(pred)})
        for s, v in pred.items():
            if s in exact:
                diffs[exact[s] - v] += 1

    return {
        "n_ground_truth_sessions": n_sessions,
        "formula_error_histogram": {str(k): v for k, v in sorted(diffs.items())},
        "boundary_constant_used": BOUNDARY,
        # 注入点集合与实际改写点集合必须完全一致，否则说明还有别的改写机制
        "sessions_with_step_set_mismatch": count_mismatch,
    }


# --------------------------------------------------------------------------
# B：跨 run 首步前缀
# --------------------------------------------------------------------------

def _lcp(seqs: list[list[int]]) -> int:
    if not seqs:
        return 0
    n = min(len(s) for s in seqs)
    first = seqs[0]
    for k in range(n):
        v = first[k]
        for s in seqs[1:]:
            if s[k] != v:
                return k
    return n


def cross_run_levels(group_key: int, rows: list[dict]) -> dict:
    tok = render._tokenizer()

    cands: dict[str, list[dict]] = {}
    for sd in wire.session_dirs():
        r = wire.first_request(sd)
        if r.tools is not None and r.tools_hash:
            cands.setdefault(r.tools_hash[:8], r.tools)
    wrapped = render.wrap_tools(cands["aca0350b"])

    # 参照工具块本身有多少 token（渲染一份探针再截到分界处）
    probe = render.render([{"role": "system", "content": "s"},
                           {"role": "user", "content": "x"}], wrapped)
    ref_tools_tok = render.count(probe[: probe.index(TOOLS_END) + len(TOOLS_END)])
    tools_tok = ref_tools_tok + group_key      # 分组键就是相对参照的工具块 token 差

    def tail(sysprompt: str, msgs: list[dict]) -> str:
        t = render.render([{"role": "system", "content": sysprompt}] + msgs, wrapped)
        return t[t.index(TOOLS_END) + len(TOOLS_END):]

    sids = {r["sid"] for r in rows
            if r["tools_tok_rel_ref"] == group_key and r["included"]}
    recs = []
    for sd in wire.session_dirs():
        if sd.name not in sids:
            continue
        r = wire.first_request(sd)
        if not r.system_prompt or not r.messages or r.prompt_tokens is None:
            continue
        recs.append((r.system_prompt,
                     [{"role": m.get("role"), "content": m.get("content")}
                      for m in r.messages],
                     r.prompt_tokens))
    if not recs:
        return {"group": group_key, "n": 0}

    n = len(recs)
    mean_first = sum(x[2] for x in recs) / n
    # L2 的「归一后的 systemPrompt」取区块内最常见的那一份
    canon = Counter(ISO_TS.sub("X", sp) for sp, _, _ in recs).most_common(1)[0][0]
    generic = [{"role": "user",
                "content": [{"type": "text", "text": "<task placeholder>"}]}]

    builders = {
        "L0_原样": lambda sp, ms: tail(sp, ms),
        "L1_时间戳归一": lambda sp, ms: tail(ISO_TS.sub("X", sp), ms),
        "L2_工作目录树归一": lambda sp, ms: tail(canon, ms),
        "L3_首条用户消息不含论文": lambda sp, ms: tail(canon, generic + ms[1:]),
    }

    levels = []
    for name, build in builders.items():
        ids = [tok.encode(build(sp, ms), add_special_tokens=False).ids
               for sp, ms, _ in recs]
        shared = _lcp(ids) + tools_tok
        waste = mean_first - shared
        levels.append({
            "level": name,
            "shared_prefix_tokens": shared,
            "share_of_first_prompt": round(shared / mean_first, 4),
            "waste_per_run": round(waste, 1),
            "waste_total": round(waste * n),
        })

    # 不改任何代码的替代方案：按 systemPrompt 变体分组调度
    by_variant: dict[str, list] = {}
    for sp, ms, pt in recs:
        by_variant.setdefault(ISO_TS.sub("X", sp), []).append((sp, ms, pt))
    grouped_waste = 0.0
    variants = []
    for v, items in sorted(by_variant.items(), key=lambda kv: -len(kv[1])):
        ids = [tok.encode(tail(ISO_TS.sub("X", sp), ms), add_special_tokens=False).ids
               for sp, ms, _ in items]
        shared = _lcp(ids) + tools_tok
        mf = sum(x[2] for x in items) / len(items)
        grouped_waste += (mf - shared) * len(items)
        variants.append({"n": len(items), "shared_prefix_tokens": shared,
                         "waste_per_run": round(mf - shared, 1)})

    return {
        "group": group_key,
        "n_sessions": n,
        "tools_block_tokens": tools_tok,
        "mean_first_prompt_tokens": round(mean_first, 1),
        "n_distinct_systemprompts": len(set(sp for sp, _, _ in recs)),
        "n_distinct_systemprompts_after_ts_norm": len(by_variant),
        "levels": levels,
        "scheduling_by_systemprompt_variant": {
            "variants": variants, "waste_total": round(grouped_waste),
            "note": "只做 L1、但把同变体的 run 排在一起跑，不改 harness 代码。",
        },
    }


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-source", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="在 ground truth 上重新标定公式（慢，约 3 分钟）")
    ap.add_argument("--group", type=int, default=None,
                    help="跨 run 分析用哪个工具配置区块，默认取最大的那个")
    args = ap.parse_args()

    if not render.available():
        raise SystemExit("还原器不可用。先 make setup-render")

    manifest = {r["sid"]: r for r in provenance.read_jsonl(
        provenance.open_out("s0_manifest.jsonl"))}
    s3_rows = list(provenance.read_jsonl(provenance.open_out("s3_render.jsonl")))

    check = self_check() if args.check else None
    if check:
        hist = check["formula_error_histogram"]
        print(f"[s4] 公式标定：{check['n_ground_truth_sessions']} 份 ground truth，"
              f"误差分布 {hist}")
        if check["sessions_with_step_set_mismatch"]:
            print(f"[s4] ⚠ {len(check['sessions_with_step_set_mismatch'])} 份 session 的"
                  "注入点与实际改写点不一致 —— 说明还有别的改写机制，公式不完备。")
        else:
            print("[s4] 注入点集合 == 实际改写点集合，注入是非追加式增长的唯一成因。")

    # ---- A ----
    rows = []
    total_invalid = total_prefill = 0
    kinds = Counter()
    first_step = Counter()
    n_inj_hist = Counter()

    for sd in wire.session_dirs():
        m = manifest.get(sd.name)
        if not m or not m["included"]:
            continue
        steps, inj = scan_injections(sd)
        total_prefill += sum(v for v in steps.values() if v)
        n_inj_hist[len(inj)] += 1
        total, detail = invalidated(steps, inj)
        total_invalid += total
        for step, head in inj:
            kinds[re.sub(r"\s+", " ", head)[:70]] += 1
        if inj:
            first_step[inj[0][0]] += 1
        rows.append({
            "sid": sd.name,
            "family": m["family"],
            "n_injections": len(inj),
            "invalidated_tokens": total,
            "first_injection_step": inj[0][0] if inj else None,
            "detail": detail,
        })

    affected = [r for r in rows if r["n_injections"]]
    vals = sorted(r["invalidated_tokens"] for r in affected)

    def q(p: float) -> int:
        return vals[min(len(vals) - 1, int(len(vals) * p))] if vals else 0

    part_a = {
        "n_sessions": len(rows),
        "n_sessions_with_injection": len(affected),
        "injection_count_histogram": dict(sorted(n_inj_hist.items())),
        "first_injection_step_histogram": dict(first_step.most_common(15)),
        "injected_reminder_kinds": dict(kinds.most_common(10)),
        "invalidated_tokens_total": total_invalid,
        "corpus_prefill_total": total_prefill,
        "share_of_corpus_prefill": round(total_invalid / total_prefill, 6)
        if total_prefill else None,
        "per_affected_session": {"p10": q(.1), "p50": q(.5), "p90": q(.9),
                                 "max": vals[-1] if vals else 0},
        "by_family": {
            fam: {"n_affected": sum(1 for r in affected if r["family"] == fam),
                  "invalidated_tokens": sum(r["invalidated_tokens"]
                                            for r in affected if r["family"] == fam)}
            for fam in sorted({r["family"] for r in rows})
        },
    }

    # ---- B ----
    if args.group is not None:
        group = args.group
    else:
        c = Counter(r["tools_tok_rel_ref"] for r in s3_rows if r["included"])
        group = c.most_common(1)[0][0]
    part_b = cross_run_levels(group, s3_rows)

    hdr = provenance.header(SCRIPT, {"check": args.check, "group": group},
                            verify_source=args.verify_source)
    provenance.write_jsonl("s4_divergence.jsonl", hdr, rows)
    payload = {"self_check": check, "part_a_injection": part_a,
               "part_b_cross_run": part_b}
    path = provenance.write_json("s4_summary.json", hdr, payload)

    # ---- 控制台 ----
    a = part_a
    print(f"\n[s4] A 会话内注入：{a['n_sessions_with_injection']}/{a['n_sessions']} 份"
          f"（{a['n_sessions_with_injection']/a['n_sessions']*100:.1f}%）出现过注入")
    print(f"     首次注入步号 top5: {dict(list(a['first_injection_step_histogram'].items())[:5])}")
    print(f"     作废 {a['invalidated_tokens_total']:,} tokens = 全语料 prefill 的 "
          f"{a['share_of_corpus_prefill']*100:.2f}%")
    p = a["per_affected_session"]
    print(f"     受影响 session 每份: p10={p['p10']:,} p50={p['p50']:,} "
          f"p90={p['p90']:,} max={p['max']:,}")

    b = part_b
    print(f"\n[s4] B 跨 run 首步前缀（区块 {b['group']:+d}，{b['n_sessions']} 份，"
          f"工具块 {b['tools_block_tokens']:,} tokens）")
    print(f"     systemPrompt 去重：{b['n_distinct_systemprompts']} 种，"
          f"时间戳归一后 {b['n_distinct_systemprompts_after_ts_norm']} 种")
    print(f"     {'层级':<26}{'共享前缀':>10}{'占首步':>9}{'每run浪费':>11}{'区块合计':>12}")
    for lv in b["levels"]:
        print(f"     {lv['level']:<26}{lv['shared_prefix_tokens']:>10,}"
              f"{lv['share_of_first_prompt']*100:>8.1f}%{lv['waste_per_run']:>11,.0f}"
              f"{lv['waste_total']:>12,}")
    g = b["scheduling_by_systemprompt_variant"]
    print(f"     按 systemPrompt 变体分组调度：区块合计浪费 {g['waste_total']:,}")
    print(f"\n[s4] → {path}")


if __name__ == "__main__":
    main()
