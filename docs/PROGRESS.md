# Research Progress

本文档是本仓库的主线追踪文档，记录当前研究方向的进展，以及 `docs/open-questions/` 中各问题的解决状态。

**给 agent 的约定**：一个 open-question 一旦在下表中被标记为 `RESOLVED`，其对应的原始文档已经是历史记录，**不要在未被用户明确要求的情况下读取它** —— 只需参考下表中的 Resolution 摘要即可。这是为了避免已收敛的长篇讨论反复被拉入上下文。仅当用户明确要求查看某个已解决问题的完整讨论过程时，才去读取原文档。

## Current direction

见 [`AGENTS.md`](../AGENTS.md)：cache-aware planning and execution in LLM agents（研究方向仍在演进中，以 AGENTS.md 中的描述为准）。

**Workload 命名（2026-08-31 更正）**：本项目研究的 workload 类别是 **data-intensive / data-processing agent workflows**，不是 "Data Analysis Agent"。P4A 的核心特征不是"分析数据"，而是 Agent 依据固定的 procedural knowledge（Skill），对大量不同输入反复执行同一个长程、工具增强、带 validation 与 repair 的 E2E workflow。完整定义见 [`AGENTS.md` → Workload Under Study](../AGENTS.md#workload-under-study)。这一命名对研究是 load-bearing 的：跨 run 的**固定过程 + 大量重复**才是 cache 复用空间的来源，"data analysis" 强调的是任务语义，指向了错误的属性。

## Current Work

> **本章节的维护规范**（仅适用于本章节）：这里只记录**当前正在进行的工作**，保持简短。**不对历史进行维护**——每次更新本章节都是**整节完整重写**，直接覆盖旧内容，不追加、不保留历史条目、不写变更记录。仅当用户显式要求"只调整某一处"时才做局部修改。需要留存的历史属于 Open Questions / Decisions / Experiments 各表，不属于这里。

- 已把研究 workload 定名为 data-intensive / data-processing agent workflows（见上节），`AGENTS.md`、本文档、open-question 文档三处术语已对齐。
- 文献管理规范已建立（`references/` + `docs/literature/`，见下方 Literature 节），骨架就位但**尚无任何文献入库**。
- 进行中：为已有 open question 找支撑文献，读完后按规范写笔记并回填 Open Questions 表的 `Refs` 列。
- 待办：验证 open question「Is agentic execution necessary」——构造不同 autonomy level 的 P4A 实现做 controlled comparison。
- 待办：`docs/experiments/p4a.md` 第 4 节的先决核查项——批量核实 12,801 个 session 的 `inputCacheRead` / `inputCacheCreation` 是否恒为 0，未做之前不得基于 cache 命中率下结论。

## Open Questions

| Question | Status | Doc | Refs | Resolution |
|---|---|---|---|---|
| Is agentic execution necessary for data-intensive workloads (P4A)? | OPEN | [open-questions/Necessity-of-agentic-execution.md](open-questions/Necessity-of-agentic-execution.md) | — | — |

`Refs` 列填支撑该问题的文献 citekey（见 [Literature](#literature)）；一个问题在有文献支撑之前被 RESOLVED，应当在 Resolution 里说明结论是纯实验得出的。

## Decisions

尚无已收敛的决定。问题被解决后，在此追加一行，并可选地在 `docs/decisions/` 下补充完整推导过程。

| Decision | Date | Doc | Rationale (short) |
|---|---|---|---|

## Experiments

- [`experiments/p4a.md`](experiments/p4a.md) — P4A 项目实验记录

## Literature

- 索引与笔记规范：[`literature/README.md`](literature/README.md)
- 文献元数据（唯一来源）：[`../references/refs.bib`](../references/refs.bib)
- PDF 等外部材料：`references/papers/`（gitignored，靠 `refs.bib` 里的 url 取回）
