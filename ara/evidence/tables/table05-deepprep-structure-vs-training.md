# T05 — 结构收益 vs 专门化收益的分解

> ⚠️ **可信度：staged。** 出自 agent 生成、**未经人工评审**的精读稿，且对应的 `refs.bib`
> 条目已于 commit `c6ece08` 移除。**不可引用、不可支撑决定。** 规则：`references/README.md:38`。
>
> ⚠️ 且下表本身**不是原论文的实验**——是精读稿作者从两处分散数字做的推导，原论文未把它
> 组织成对照实验，也没给方差。

**Source**: `references/papers/fan2026deepprep/close-read.md:524-539, 698`
（原始图表：该论文 Fig. 1 / Table 2 / §6.2；图片在 `references/papers/fan2026deepprep/figures/`，gitignored）
**支撑**: C04, C05

## 对照 A：frozen 模型，只换推理结构（最干净，但非论文的实验）

| 设置 | Synth-Spider Acc. |
|---|---|
| 线性 agent (ReAct) on gpt-5-mini | 67.03 |
| 树式 agent (DeepPrep) on gpt-5-mini | **71.76** |
| **Δ（结构的净收益）** | **+4.73** |
| 线性 agent on claude-sonnet-4 | 69.92 |
| 树式 agent on claude-sonnet-4 | ≈73.5（读图值） |
| **Δ** | **≈+3.6** |

## 对照 B：结构 + 专门化训练（论文的 headline，混淆两个变量）

| 设置（Qwen3-14B / Synth-Spider） | Acc. |
|---|---|
| ReAct | 40.39 |
| DeepPrep | **67.18** |
| **Δ** | **+26.79** |

## 分解

> **26.79 里大约只有 4~5 点归于 agentic 结构，其余 22 点左右归于"针对这个固定协议做专门
> 训练"。**（这是一个粗略分解——结构与训练之间存在交互，小模型可能更依赖结构约束才能被
> 训起来，所以不能严格线性拆分。）
>
> —— `close-read.md:539`

## 对照 C：零 agency vs 线性 agency（方向随 backbone 翻转）

| | Synth-Spider | Synth-Bird | Parrot |
|---|---|---|---|
| **Qwen3-14B** CodeGen（零 agency） | **45.47** | **29.48** | 30.83 |
| **Qwen3-14B** ReAct（线性 agent） | 40.39 | 16.04 | 30.80 |
| **Qwen3-8B** CodeGen | 6.27 | — | — |
| **Qwen3-8B** ReAct | **29.63** | — | — |

即 **"加上 agency 是否有帮助" 是 backbone 能力的函数，不是恒定为真**。

## 对本项目适用性的两条硬边界

1. **A1 冲突**：那 +26.79 的手段是**训练模型**，本项目工作假设是 frozen 模型。在 frozen
   设定下能借到的只有 +4.73。
2. **动作空间**：该论文的动作空间可闭合（31 算子 + 1 代码逃生口、探索预算 ≤5 轮、无外部
   检索）。P4A 的不可闭合。**它恰好消掉了 P4A 里最难消的部分。**
