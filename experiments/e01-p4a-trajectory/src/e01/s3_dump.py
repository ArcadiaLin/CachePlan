"""把指定 session 的逐步上下文导出成可读文件，用来**肉眼看内容**。

统计量之外还是要能直接读原文 —— 那两处关键发现（时间戳把跨 run 前缀切断、
注入回溯改写历史）都是导出后一眼看出来的，不是统计出来的。

产物落在 data/processed/e01/dumps/：

    <sid>.final.txt   末步的完整上下文，即这次 run 结束时模型看到的全部内容
    <sid>.steps.txt   逐步对照表（复现 vs 实测 vs Δ），后接每一步**新增**的原文

「新增」是与上一步的公共前缀之后的部分。纯追加的步里它就是新来的消息；
若某一步的新增量突然接近整个上下文，说明**中段被改写**了，那正是要看的地方。

只对有 `llm.tools_snapshot` 的那 60 份可用 —— 其余 session 的工具 schema 原文
不在日志里（见 s3_render.py）。

用法：
    uv run --extra render -m e01.s3_dump <sid 片段> [<sid 片段> ...]
"""

from __future__ import annotations

import sys

from . import context_builder, provenance, render, wire

OUT = provenance.OUT_ROOT / "dumps"


def _common_prefix(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def dump(sid_fragment: str) -> None:
    matches = [d for d in wire.session_dirs() if sid_fragment in d.name]
    if not matches:
        raise SystemExit(f"找不到 session：{sid_fragment}")
    sd = matches[0]

    ctx = context_builder.build(sd)
    if ctx.tools is None:
        raise SystemExit(
            f"{sd.name} 的日志里没有 llm.tools_snapshot，工具 schema 原文不可得，"
            "无法逐字还原。只有 60 份带快照的 session 可导出。")

    w = render.wrap_tools(ctx.tools)
    texts = [render.render(context_builder.messages_for(ctx, s), w) for s in ctx.steps]
    counts = [render.count(t) for t in texts]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{sd.name}.final.txt").write_text(texts[-1], encoding="utf-8")

    head = [
        f"# {sd.name}",
        f"# 工具集 {ctx.tools_hash[:8]}（{len(ctx.tools)} 个工具），{len(ctx.steps)} 步",
        f"# 末步上下文 {counts[-1]:,} tokens / {len(texts[-1]):,} 字符",
        "",
        "step | 复现tokens | 实测tokens |    Δ | 本步新增字符 | 纯追加",
        "-----|-----------|-----------|------|-------------|-------",
    ]
    blocks = []
    for i, st in enumerate(ctx.steps):
        prev = texts[i - 1] if i else ""
        j = _common_prefix(prev, texts[i])
        m = st.prompt_tokens
        head.append(
            f"{st.step:>4} | {counts[i]:>9} | {m if m is not None else '-':>9} | "
            f"{(counts[i] - m) if m is not None else 0:>4} | "
            f"{len(texts[i]) - j:>11} | {'是' if j == len(prev) else '否 <<<'}")
        blocks.append(
            f"\n{'-' * 78}\n--- step {st.step}  新增 {len(texts[i]) - j:,} 字符"
            f"{'' if j == len(prev) else '（非纯追加：中段被改写）'}\n{'-' * 78}\n"
            + texts[i][j:])

    body = head + ["", "=" * 78,
                   "以下是每一步新增的原文（第 1 步即完整的首个 prompt）",
                   "=" * 78] + blocks
    (OUT / f"{sd.name}.steps.txt").write_text("\n".join(body), encoding="utf-8")

    print(f"{sd.name}: {len(ctx.steps)} 步，末步 {counts[-1]:,} tokens")
    print(f"  {OUT / (sd.name + '.final.txt')}")
    print(f"  {OUT / (sd.name + '.steps.txt')}")


def main() -> None:
    if not render.available():
        raise SystemExit("还原器不可用。先 make setup-render")
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for frag in sys.argv[1:]:
        dump(frag)


if __name__ == "__main__":
    main()
