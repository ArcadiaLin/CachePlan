# Literature

本目录存放**我们对文献的判断**，不是文献本身。PDF 与元数据在 [`references/`](../../references/)，三者用同一个 citekey 绑定（约定见 [`references/README.md`](../../references/README.md)）。

**给 agent 的约定**：默认只读下面索引表的行，以及需要时读某篇笔记的 `verdict` 字段。**不要把 PDF 全文或整篇笔记拉进上下文**，除非用户明确要求某一篇。这与 `PROGRESS.md` 中"已 RESOLVED 的 open-question 不回读原文"是同一条原则：已经收敛成结论的长文本不该反复占用上下文。

## 索引

这是**唯一手工维护的文献清单**。写了笔记就在这里加一行；只进 `refs.bib` 而没写笔记的文献不出现在这里。

| citekey | Title | Relates to | Status |
|---|---|---|---|
| 2026-Helium | Efficient LLM Serving for Agentic Workflows: A Data Systems Perspective | OQ2 | read |
| 2026-CoDec | CoDec: Prefix-Shared Decoding Kernel for LLMs | OQ2 | read |
| 2026-AgenticScholar | AgenticScholar: Agentic Data Management with Pipeline Orchestration for Scholarly Corpora | OQ1 | read |
| 2026-AlignedServe | AlignedServe: Orchestrating Prefix-aware Batching to Build a High-throughput and Computing-efficient LLM Serving System | OQ2 | read |

`Status`：`queued`（已入库待读）/ `skimmed`（略读，够用即可）/ `read`（精读，结论可依赖）。

## 笔记规范

1. **只为真正起支撑作用的论文写笔记。** 读过但用不上的，留在 `refs.bib` 里即可，不必写。
2. **不写论文摘要，写判断**：它对我们的哪个问题说了什么；我们采信它的哪一部分；它的实验条件与我们的差异在哪，因此结论能外推到什么程度。摘要将来随时能重新生成，判断不能——笔记的价值全在后者。
3. **引用方向是单向的**：由 open-question / decision / experiment 文档引用笔记（`[citekey](../literature/citekey.md)`），笔记**不**反过来维护"我被谁引用了"的列表。双向引用会失同步。
4. 新笔记从 [`_template.md`](_template.md) 复制，文件名为 `<citekey>.md`。
