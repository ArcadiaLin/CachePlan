"""阶段 1：cache 字段可用性核查。**结论已定，此处只保留复现路径。**

结论（见 docs/experiments/e01-p4a-trajectory.md 第 2 节）：全语料
`inputCacheRead` / `inputCacheCreation` 恒为 0，判定 `identically_zero`。
成因是上报缺陷而非未命中 —— 服务端当时开着 `--enable-prefix-caching`，
实测命中率 86.5%，但 vLLM 0.21.0 的响应体不带 `prompt_tokens_details`，
kimi-code 的 `extractUsage` 取不到 `cached_tokens` 便记 0。

**历史语料的真实命中率不可得，且不会再变**（语料冻结、不可重跑）。下游
一律改用 s3 复现序列上的前缀重叠量，并标为**结构性度量**，不得称作命中率。
新数据不受此限：vLLM 0.22.1 + `--enable-prompt-tokens-details` 已验证可逐
请求上报真实命中数。

本脚本保留的唯一理由，是让文档里那几个数字可被 `make all` 原样重建。

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
        # 成因是上报缺陷（vLLM 0.21.0 不返回 prompt_tokens_details），不是未命中；
        # 服务端当时实测命中率 86.5%。语料冻结，这条结论不会再变。
        "cause": "vllm_0.21.0_does_not_report_prompt_tokens_details",
        "consequence": (
            "历史语料真实命中率不可得。下游改用 s3 复现序列上的前缀重叠量，"
            "标为结构性度量，不得称作命中率。"
            if identically_zero else
            "出现了非零记录 —— 与已定谳的结论矛盾，说明输入语料不是 P4A 那份，"
            "或读取逻辑被改坏了。先查这个，不要直接采信。"
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
        print("[s1] 与已定谳结论一致：历史命中率不可得（上报缺陷，非未命中）。")
    else:
        print("[s1] ⚠ 出现非零 cache 记录，与已定谳结论矛盾 —— 先查输入语料与读取逻辑。")


if __name__ == "__main__":
    main()
