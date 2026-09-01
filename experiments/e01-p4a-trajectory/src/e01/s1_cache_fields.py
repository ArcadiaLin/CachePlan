"""阶段 1（闸门）：cache 字段可用性核查。

在这一步给出结论之前，**任何基于 cache 命中率的分析都不得进行**
（见 docs/experiments/p4a.md 的使用边界）。

本脚本只回答一件事：`inputCacheRead` / `inputCacheCreation` 这两个字段
在全语料里是否恒为 0。若恒为 0，则真实命中率不可得，下游必须改用
重建流上的前缀重叠量，并且**只能标注为估计量，不得称作命中率**。

产物：data/processed/e01/s1_cache_fields.json

用法：
    uv run -m e01.s1_cache_fields [--verify-source]
"""

from __future__ import annotations

import argparse
from collections import Counter

from . import provenance, wire

SCRIPT = "e01/s1_cache_fields.py"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-source", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    manifest = {
        r["sid"]: r
        for r in provenance.read_jsonl(provenance.open_out("s0_manifest.jsonl"))
    }

    n_sessions = 0
    n_records = 0
    nonzero_read = 0
    nonzero_create = 0
    nonzero_sessions: list[str] = []
    missing_field = 0
    sum_input = 0
    sum_output = 0
    per_family = Counter()

    for sdir in wire.session_dirs()[: args.limit or None]:
        m = manifest.get(sdir.name)
        if m is not None and not m["included"]:
            continue
        s = wire.load(sdir, with_segments=False)
        if not s.usage:
            continue
        n_sessions += 1
        per_family[s.family] += 1
        hit = False
        for u in s.usage:
            n_records += 1
            sum_input += u.input_other
            sum_output += u.output
            if not u.has_cache_fields:
                missing_field += 1
            if u.cache_read:
                nonzero_read += 1
                hit = True
            if u.cache_creation:
                nonzero_create += 1
                hit = True
        if hit:
            nonzero_sessions.append(s.sid)

    identically_zero = (nonzero_read == 0 and nonzero_create == 0)
    if missing_field == n_records and n_records:
        verdict = "field_absent"      # harness 根本没上报，与「上报了零」不同
    elif identically_zero:
        verdict = "identically_zero"  # 上报了，值确实恒为零
    else:
        verdict = "has_nonzero"

    payload = {
        "verdict": verdict,
        "gate_open_for_hit_rate": not identically_zero,
        "n_sessions_checked": n_sessions,
        "n_usage_records": n_records,
        "n_records_with_nonzero_cache_read": nonzero_read,
        "n_records_with_nonzero_cache_creation": nonzero_create,
        "sessions_with_any_nonzero": nonzero_sessions[:50],
        "n_sessions_with_any_nonzero": len(nonzero_sessions),
        "records_missing_cache_field": missing_field,
        "records_reporting_cache_field": n_records - missing_field,
        "scope": "full_corpus" if args.limit is None else f"first_{args.limit}",
        "sum_input_other_tokens": sum_input,
        "sum_output_tokens": sum_output,
        "per_family_sessions": dict(per_family),
        "consequence": (
            "两个 cache 字段在全语料恒为 0，真实命中率不可得。下游一律改用重建流上的"
            "前缀重叠量，并必须标注为估计量，不得称作命中率。"
            if identically_zero else
            "存在非零记录，命中率分析的闸门打开；但需先核实非零记录的分布是否代表全语料。"
        ),
    }

    hdr = provenance.header(SCRIPT, {"limit": args.limit},
                            verify_source=args.verify_source)
    path = provenance.write_json("s1_cache_fields.json", hdr, payload)

    scope = "全语料" if args.limit is None else f"前 {args.limit} 份（非全量）"
    print(f"[s1] 判定：{payload['verdict']}（范围：{scope}）")
    print(f"[s1] 检查 {n_sessions} 份 session / {n_records} 条 usage 记录，"
          f"其中上报了 cache 字段的 {n_records - missing_field} 条")
    print(f"[s1] 非零 cache_read: {nonzero_read}，非零 cache_creation: {nonzero_create}")
    print(f"[s1] 本范围累计 prefill: {sum_input:,} tokens；累计 output: {sum_output:,} tokens")
    print(f"[s1] → {path}")
    if identically_zero:
        print("[s1] 闸门结论：命中率不可得。下游只能用前缀重叠估计量。")


if __name__ == "__main__":
    main()
