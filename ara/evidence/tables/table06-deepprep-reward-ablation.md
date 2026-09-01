# T06 — 稀疏奖励下的 agency 自发退化

> ⚠️ **可信度：staged。** 未经人工评审的精读稿；`refs.bib` 条目已移除。**不可引用。**

**Source**: `references/papers/fan2026deepprep/close-read.md:349-361, 514, 700`
（原始图表：该论文 Table 3b，Qwen3-8B）
**支撑**: C06

## 表

| 奖励设置 | Spider Acc/Comp | Bird Acc/Comp | Parrot Acc/Comp |
|---|---|---|---|
| 全奖励（outcome + partial + LLM-judge process） | **65.99** / 97.46% | **53.39** / 92.78% | **39.93** / 98.46% |
| w/o process reward | 64.54 / 96.96% | 51.67 / 92.31% | 39.12 / 94.21% |
| 只剩 outcome reward | 61.85 / **98.71%** | 47.15 / **95.57%** | 37.22 / **99.34%** |

## 关键读法：完成率与准确率**反向**

只留稀疏的 outcome reward 时，**完成率反而最高**（98.71 / 95.57 / 99.34%）而**准确率最低**
（61.85 / 47.15 / 37.22）。

原论文的解释（精读稿转引）：

> The agent avoids complex exploration or backtracking to minimize the risk of runtime errors.
> Thus, it prioritizes safe but incorrect paths to ensure the episode terminates successfully.

## 对本项目的含义

> **在没有额外压力时，一个 agent 会自发地退化成 workflow。要维持 agentic 行为，必须付出
> 训练代价。**
>
> —— `close-read.md:516`

推论：在 E02 的 autonomy 对比里，**"full agent" 这一臂的实际自主程度必须被测量，不能被
假定**——它很可能自己就退化了。这是行为统计作为一等指标的第二个理由（第一个见 T03）。

## 限制

- 单一 backbone（Qwen3-8B）、单次运行、**无方差**。
- "保守行为" 是原作者的解释；**未直接统计回溯次数或分支数**。
- 是否在 frozen 模型的 prompt-only 设定下也成立，**未知**——而这正是本项目的设定。
