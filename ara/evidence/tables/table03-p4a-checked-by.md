# T03 — 抽样 50 篇的资源 `checked_by` 分布

**可信度**：自有实测
**Source**: `experiments/p4a/refractor.md:255`；解读见 `:23`
**支撑**: `logic/solution/autonomy-ladder.md`（"给了 agency" ≠ "行使了 agency"）

## 表

| `checked_by` | 计数 |
|---|---|
| `none` | 142 |
| `github_mcp` | 42 |
| `agent` | 40 |
| `hf-readonly` | 34 |
| 其他 | 12 |
| **合计** | **270** |

（样本为 50 篇论文，合计 270 条资源记录。）

## 为什么这条重要

原文的解读是运维视角：

> 另一个实测问题：抽样 50 篇的资源 `checked_by` 分布中 `none`/`agent`/`paper` 占大半，
> **agent 经常没有真正核验资源**。集中式程序验证同时是提速和一致性修复。
>
> —— `experiments/p4a/refractor.md:23`

对本项目它是另一件事的证据：**agent 被赋予了自主核验的能力，但这个能力大面积没有被行使**
——`none` 一项独占 142/270（52.6%），真正走外部工具核验（`github_mcp` + `hf-readonly`）
只有 76/270（28.1%）。

这是把**行为统计定为 autonomy 对比实验一等指标**的直接理由：只看最终质量指标，看不出
一个"full agent"臂实际退化到了什么程度。

> 百分比（52.6% / 28.1%）是本 artifact 从上表计数算出的派生值，非原文数字。
