# T08 — 工具可用性消融

> ⚠️ **可信度：staged。** 未经人工评审的精读稿；`refs.bib` 条目已移除。**不可引用。**

**Source**: `references/papers/anon2026longda/close-read.md:332-342`
（原始图表：该论文 Table 4, page 8）
**支撑**: C07

脚手架共 7 个工具：`prompt` / `read_doc` / `search_doc` / `retriever`(BM25) / `notes` /
`answer` / `save_code`。

| Model | Setting | Coverage % | Match % | Steps | In(M) | Out(M) | Time(h) |
|---|---|---|---|---|---|---|---|
| GPT-5 | Full tools | **91.09** | **69.16** | 5.50 | 5.75 | 0.65 | 3.58 |
| GPT-5 | w/o `search_doc` | 80.20 | 58.30 | 6.03 | 6.09 | 0.65 | 2.84 |
| DeepSeek-V3.2 | Full tools | 67.33 | 53.00 | 66.30 | 68.50 | 0.40 | 5.22 |
| DeepSeek-V3.2 | w/o `retriever` | 66.93 | **54.03** | 65.07 | 67.04 | 0.40 | 5.36 |
| Qwen3-Coder-480B | Full tools | 51.49 | **23.44** | 53.27 | 75.13 | 0.36 | 5.08 |
| Qwen3-Coder-480B | w/o `retriever` | **53.27** | 21.52 | 48.00 | 79.48 | 0.40 | 4.27 |

## 读法

- 拿掉 `search_doc`：GPT-5 的 match 掉 **10.86pp**——全表**唯一**一个大幅度效应。
- 拿掉 `retriever`：DeepSeek **上升 1.03pp**，Qwen3-Coder 下降 1.92pp，coverage 还上升
  1.78pp。**两个方向相反、幅度都在单次运行的噪声量级内。**

→ **七个工具里真正承重的只有 `search_doc` 一个**；BM25 检索器对两个开源模型是净噪声。
这对"这类 workload 需要多大的工具面"是一条直接证据：**工具箱的大部分可以裁掉。**

## 限制

只做了 **3 个模型 × 1 个工具**。`read_doc` / `notes` / `save_code` / `prompt` / `answer`
**都没被消融过**，脚手架的任何超参（BM25 vs 稠密检索、切分粒度、100 步预算）也没被消融。
考虑到该论文的核心结论是"工具使用策略决定成败"，**脚手架本身没被审视是一个结构性弱点**。
