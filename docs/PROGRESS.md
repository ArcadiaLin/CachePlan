# Research Progress

本文档是本仓库的主线追踪文档，记录当前研究方向的进展，以及 `docs/open-questions/` 中各问题的解决状态。

**给 agent 的约定**：一个 open-question 一旦在下表中被标记为 `RESOLVED`，其对应的原始文档已经是历史记录，**不要在未被用户明确要求的情况下读取它** —— 只需参考下表中的 Resolution 摘要即可。这是为了避免已收敛的长篇讨论反复被拉入上下文。仅当用户明确要求查看某个已解决问题的完整讨论过程时，才去读取原文档。

## Current direction

见 [`AGENTS.md`](../AGENTS.md)：cache-aware planning and execution in LLM agents（研究方向仍在演进中，以 AGENTS.md 中的描述为准）。

**Workload 命名（2026-08-31 更正）**：本项目研究的 workload 类别是 **data-intensive / data-processing agent workflows**，不是 "Data Analysis Agent"。其关键是固定 procedural knowledge 驱动大量不同输入的重复、长程、工具增强 workflow；不是任务的业务语义。

**P4A 的定位（2026-09-05 更新）**：P4A v1 是让问题被看见的继承性轨迹来源和动态边界案例，不是 CachePlan 的方法效果 benchmark。它的早期私有输入和“每篇论文一条长 session”形态限制了跨 run 共享结构；已有 schema validation 也不等于独立任务质量评测。P4A 记录可支撑诊断与 workload mining，不能支撑策略有效性结论。

**研究视角的转向（暂定）**：从“同义措辞或静态前缀失效”扩展为“执行组织方式决定哪些内容能成为共享前缀”。候选对象是逐阶段显露、可部分编排的 workflow；这不是已被实验证实的方法主张。详见 [OQ3](open-questions/Multi-run-workloads.md) 与讨论记录 [Paper-for-Agents workload](discussions/2026-09-04-paper-for-agents-workload.md)。

## Current Work

> **本章节的维护规范**（仅适用于本章节）：这里只记录**当前正在进行的工作**，保持简短。每次更新整节完整重写；历史属于 Open Questions、Decisions 与 Experiments。

**当前状态：尚无完成验收的 CachePlan 方法效果实验。** 已有的工作不是“只有计划”：轨迹观测已有结果；一个受控 pilot 已运行但不可解释；方法效果仍未确证。

- **E01 — 继承性轨迹观测已有可用结果。** 它确认历史 cache 字段失效、配置异质性会从 token 0 切断跨组前缀，并观测到稳定主干、provider 分叉、validator 后 repair 与异常委派。结构性重叠不能直接解释为实际节省；E01 是 OQ3 的 workload-mining 输入，不是方法比较实验。见 [`experiments/e01-p4a-trajectory.md`](experiments/e01-p4a-trajectory.md)。
- **E06 — 已关闭。** 3 臂 × 4 case pilot 表明最高 hit ratio 可以同时对应最高折算成本；又受 thinking 配置、bootstrap 记账和缺少独立质量评测混杂。P4A v1 不再作为直接方法评估对象，既不重试也不扩样。见 [`experiments/e06-static-prefix.md`](experiments/e06-static-prefix.md)。
- **下一步是讨论 OQ3，不是启动新实验。** 先固定真实 task family、独立质量 contract、离线 fixture 边界和 root/cohort/length/arrival 的结构刻画；再判断是否存在超出同信息内容强静态对照的动态复用空间。
- **文献不再为空。** 已有 Helium、CoDec、AgenticScholar、AlignedServe 四篇笔记；各自结论见 [`literature/README.md`](literature/README.md)。

## Open Questions

| Question | Status | Doc | Refs | Resolution |
|---|---|---|---|---|
| OQ2：可复用上下文（Skill）应该放在哪？"全部写进 system prompt" 是不是已经够用？ | **OPEN** | [open-questions/Placement-of-reusable-context.md](open-questions/Placement-of-reusable-context.md) | `2026-Helium`; `2026-CoDec` | 强静态对照的原则已明确：必须用完整、同信息内容的 canonical procedure 与适用 contract 作 static-first injection；Skill 摘要不是等价对照。P4A v1 不再承载该问题的直接方法评估；该原则由 OQ3 的 future workload 承接。 |
| OQ3：什么样的 Paper-for-Agents workload 能检验动态跨 run 复用？ | **OPEN** | [open-questions/Multi-run-workloads.md](open-questions/Multi-run-workloads.md) | `2026-Helium`; `2026-CoDec`; `2026-AgenticScholar`; `2026-AlignedServe` | 当前中心问题。必须先证明动态构造超出“编排器选择静态模板”的强对照：固定业务依赖、独立质量 contract、版本化 fixture，并刻画 root/cohort/length/arrival。分别记账 prompt/KV、artifact/result 与 plan reuse。 |
| OQ1：Is agentic execution necessary for data-intensive workloads (P4A)? | **DEFERRED** | [open-questions/Necessity-of-agentic-execution.md](open-questions/Necessity-of-agentic-execution.md) | `2026-ARA` | 2026-09-01：**未被回答，被降级。** `2026-ARA` 的 agent-skill 工作流提供同类 workload 的独立实例，排除了“优化一种没人真在用的执行方式”的 strawman 风险；需要多少 agency 仍未回答。 |

`Refs` 列填支撑该问题的文献 citekey（见 [Literature](#literature)）；一个问题在有文献支撑之前被 RESOLVED，应当在 Resolution 里说明结论是纯实验得出的。

`Status` 取值：`OPEN` / `RESOLVED` / `DEFERRED`。**`DEFERRED` 不是 `RESOLVED` 的弱化版**：它表示问题本身没有被回答，但其阻塞作用被消解。

## Decisions

| Decision | Date | Doc | Rationale (short) |
|---|---|---|---|
| workload 定名为 data-intensive / data-processing agent workflows | 2026-08-31 | [`AGENTS.md` → Workload Under Study](../AGENTS.md#workload-under-study) | 固定过程与输入并行重复才是 cache 复用空间的来源。 |
| P4A 定位为起点而非方法效果实验 | 2026-09-01 | 上方 Current direction | 继承观测与本项目方法实验的证据地位不同，必须分开。 |
| OQ「agentic execution 是否必要」降级为 DEFERRED | 2026-09-01 | 上方 Open Questions 表 | 同类 workload 已有独立实例；问题仍开放，但不再阻塞主线。 |
| 关闭 P4A-derived E06，先解决 workload 选择 | 2026-09-05 | [`experiments/e06-static-prefix.md`](experiments/e06-static-prefix.md)；[OQ3](open-questions/Multi-run-workloads.md) | P4A v1 的早期私有输入、单条长 session 与缺少独立质量评测使其不适合继续评估动态跨 run 复用；pilot 也无法归因。 |

## Experiments

**已完成验收的 CachePlan 方法效果实验：0。**

- [`experiments/e01-p4a-trajectory.md`](experiments/e01-p4a-trajectory.md) — 继承性轨迹观测；已有诊断结果，不能作方法对照。
- [`experiments/e06-static-prefix.md`](experiments/e06-static-prefix.md) — 已关闭的 P4A-derived WIDI 重执行；pilot 仅提供设计教训，不形成效果结论。
- E02/E03 与 ARA 快照中的历史计划均不在当前执行队列；任何新实验须先完成 OQ3 的讨论与 workload characterization。
- [`experiments/p4a.md`](experiments/p4a.md) 与 `experiments/p4a/src/extract/layer4_v2/` — P4A 历史工程记录；不纳入 CachePlan 方法效果证据。

## Literature

- 索引与笔记规范：[`literature/README.md`](literature/README.md)
- 文献元数据（唯一来源）：[`../references/refs.bib`](../references/refs.bib)
- PDF 等外部材料：`references/papers/`（gitignored，靠 `refs.bib` 里的 URL 取回）
- 已有可依赖笔记：`2026-Helium`、`2026-CoDec`、`2026-AgenticScholar`、`2026-AlignedServe`。文献只为当前判断服务；它们不构成 CachePlan 方法有效性证据。
