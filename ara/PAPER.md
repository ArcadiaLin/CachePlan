---
title: "CachePlan: Cache-Aware Planning and Execution in LLM Agents"
authors:
  - ArcadiaLin
year: 2026
venue: "Unpublished — ongoing research program"
doi: null
ara_version: "1.0"
domain: "LLM agents / inference systems / prompt & KV cache"
keywords:
  - prompt caching
  - KV cache reuse
  - cross-run prefix reuse
  - agent planning
  - ReAct
  - data-intensive agent workflows
  - agency level
status: "in-progress — no research question resolved yet"
claims_summary: >
  十一条 claim。五条由本仓库自有的实测数据与代码支撑：ReAct 逐步重发历史造成计费 input
  一个数量级的放大（C01）；计费口径与 serving 侧 KV 复用是两个互不蕴含的量，因此日志
  token 数不是有效成本指标（C02）；workload 的 load-bearing 属性是"固定过程 + 大量重复"
  而非任务语义（C03）；通过工具读入的固定知识对跨 run 前缀复用贡献为零，而 P4A v1 自身
  就是这个反模式的实例（C10）；跨 run 前缀设计已被本仓库的 layer4_v2 自觉采用，但采用它
  的实现同样不测量它（C11）。五条来自两篇论文的精读稿，**精读稿未经人工评审、对应
  refs.bib 条目已被移除**，因此一律标 staged，不可引用（C04–C08）。一条是尚无任何证据的
  hypothesis（C09：cache-aware 与 agency-reduction 可能是同一个动作）。**没有任何一条
  claim 由本项目的实验支撑 —— 本项目至今没有做过实验**；supported 的依据是继承自 P4A
  的观测或可直接核实的代码事实。整个研究程序的前置 open question "这类 workload 需要
  多少 agency" 仍为 OPEN。
abstract: >
  本 artifact 记录 CachePlan 研究程序截至 2026-09-01 的状态。**本项目尚未开始实验**，
  因此这里没有 results。研究起点是一个在 P4A（对全量 ACL 2025 主会论文做批量资源抽取的
  历史项目）上观测到的现象：ReAct 循环每步重发全部历史，使单篇论文的累计计费 input
  达到最终真实上下文的 10–18 倍。P4A 是这个起点，也是第一个实验（E01）要去观测的数据
  来源，但它本身不是本项目的实验、不是对照臂。由此形成的
  研究问题是：能否在不明显牺牲 agent 能力的前提下，组织 agent 的规划与执行以提高
  prompt/KV cache 的复用率。研究刻意先不假设 "ReAct 是正确的执行抽象"，而是把
  "这类 workload 究竟需要多少 agency" 作为必须先用实验回答的前置问题。目前该问题
  OPEN，且有一个未完成的先决核查项（全量 12,801 个 session 的 cache 字段是否恒为 0）
  阻塞着一切基于 cache 命中率的结论。两篇外部论文已完成精读但尚未通过人工评审，其结论
  在本 artifact 中全部以 staged 状态记录，不承担论证责任。
---

# CachePlan: Cache-Aware Planning and Execution in LLM Agents

> **这是一个进行中的研究程序的 artifact，不是一篇论文的编译产物。**
> 它没有 results section，因为**一个实验都还没做**。它记录的是：问题从哪来、已经知道
> 什么、这些"知道"分别站在什么依据上、哪些结论被明确禁止提前下、以及下一步要做什么。
>
> **关于 P4A 的定位**（2026-09-01 确认，见 trace `n17-repositioning`）：P4A 是让这个
> 问题被看见的**起点**，同时是第一个实验要去观测的**数据来源**。它不是本项目的核心实验，
> 不是对照臂，也不产生本项目的结果。P4A 自己产生的已完成记录归入
> [`logic/inherited-observations.md`](logic/inherited-observations.md) 的 B-series，
> 与 E-series 严格分开。

## What this artifact is compiled from

| 来源 | 路径 | 角色 |
|---|---|---|
| 研究方向与 workload 定义 | `AGENTS.md` | 一级来源 |
| 主线追踪 | `docs/PROGRESS.md` | 一级来源 |
| 前置 open question | `docs/open-questions/Necessity-of-agentic-execution.md` | 一级来源（OPEN） |
| P4A 实验记录与使用边界 | `docs/experiments/p4a.md` | 一级来源 |
| P4A 现网实测与重构方案 | `experiments/p4a/refractor.md` | 一级来源（**实测数字的出处**） |
| P4A 流水线 | `experiments/p4a/src/pipeline.md` | 一级来源 |
| 两篇论文精读稿 | `references/papers/*/close-read.md` | **staged，未评审，不可引用** |
| 文献规范 | `references/README.md`, `docs/literature/README.md` | 约束来源 |

## Layer Index

### `logic/` — 认知层

| 文件 | 内容 |
|---|---|
| [`problem.md`](logic/problem.md) | 触发立项的观测（带数字）、gap、核心 insight、当前假设 |
| [`claims.md`](logic/claims.md) | C01–C11，每条带 Conditions / Falsification criteria / **依据类型** / Proof / Sources |
| [`concepts.md`](logic/concepts.md) | 本项目自有术语的定义（workload 类别、两种成本口径、autonomy 阶梯…） |
| [`experiments.md`](logic/experiments.md) | E01–E05，**全部未开始**。方向性描述，不含精确数字 |
| [`inherited-observations.md`](logic/inherited-observations.md) | B01–B02，P4A 产生的已完成记录 —— **背景，不是本项目的结果** |
| [`related_work.md`](logic/related_work.md) | 两篇已精读论文的依赖类型，以及经它们浮现的待追工作 |
| [`solution/constraints.md`](logic/solution/constraints.md) | 硬约束：P4A 数据的用途边界、先决核查项、staged 文献规则 |
| [`solution/workload-definition.md`](logic/solution/workload-definition.md) | workload 类别的五条判据及其命名理由 |
| [`solution/autonomy-ladder.md`](logic/solution/autonomy-ladder.md) | 四级 autonomy 阶梯，OQ 的实验骨架 |
| [`solution/cache-accounting.md`](logic/solution/cache-accounting.md) | 成本口径的三层区分——本项目方法论的核心 |

### `src/` — 制品层

| 文件 | 内容 |
|---|---|
| [`environment.md`](src/environment.md) | 复现所需的运行环境：P4A 现网、本地 vLLM、数据资产 |
| [`artifacts.md`](src/artifacts.md) | 指向仓库内既有代码与文档的指针索引 |

CachePlan 自身的方法代码**尚不存在**——目前仓库里只有 P4A 这个历史项目的代码。

### `trace/` — 探索图

[`trace/exploration_tree.yaml`](trace/exploration_tree.yaml) — 19 个节点，从"P4A 观测到
token 放大"到当前状态的研究轨迹，含三处已发生的 decision（workload 更名、文献回撤、
P4A 定位）、一处 blocking dead_end（cache 字段不可用）与五个 open 分支。每个节点带
`attribution`（p4a / cacheplan）区分谁做的。

### `evidence/` — 证据层

[`evidence/README.md`](evidence/README.md) — 证据清单与**为什么本 artifact 没有图片**的说明。
10 张表，分三级可信度：T01–T04 自有实测，T05–T09 staged（不可引用），T10 未核实。

## Status board

| 项 | 状态 |
|---|---|
| **本项目已完成的实验** | **0** — E01–E05 全部未开始 |
| **下一步** | **E01：拿 P4A 历史轨迹做全量观测研究**（含先决核查项） |
| 前置 open question（需要多少 agency） | **OPEN** — 但见下方 ⚠️ |
| 先决核查项（12,801 session 的 cache 字段） | **未做**（E01 阶段 1）— 阻塞一切 cache 命中率结论 |
| 主实验（cache-aware 方法有效性） | **未开始** |
| 继承观测（P4A 产生，非本项目实验） | 2（B01、B02） |
| 已入库文献 | **0**（`refs.bib` 为空；两篇精读稿 staged 未评审） |
| 已收敛的 decision | **2**（workload 命名见 C03；P4A 定位见 trace `n17`） |

## ⚠️ 编译时发现的一处 docs/code drift（记录已补，处置待裁定）

编译时 `docs/` 全文没有提到过 `layer4_v2` 的存在，但
`experiments/p4a/src/extract/layer4_v2/` 里有一个**完整实现**——按 autonomy ladder 它
落在 L2–L3，参照的 v1 是 L4——且其 README 称已完成 **200 篇对照评估、裁定召回 96.1%
通过**。

**2026-09-01 已把它补记进 `docs/PROGRESS.md` 的 Experiments 节**（`docs/PROGRESS.md:36`
仍将 controlled comparison 列为待办，这是正确的：B02 不构成那个受控实验）。**剩下的是
处置方式，仍需用户裁定。**

本 artifact **不擅自把 open question 判为 RESOLVED**，因为该评估有三条硬限制（原始报告
不在本仓库、v1 被当作参照系而非独立对照臂、两臂因兜底而不独立），且完全没有覆盖本项目
定为一等指标的行为统计与双口径成本。详见 [T10](evidence/tables/table10-layer4v2-eval200.md)
与 trace 节点 `n11-docs-code-drift`。按 2026-09-01 的定位，这份评估记为 **B02**
（P4A 自己的工程验收），可作为 E02 的先例与脚手架，不作为本项目的结果。

同一处代码还给出了两条本 artifact 自有的新发现：C10（P4A v1 自身就是 cache-hostile
ordering 的实例）与 C11（跨 run 前缀设计已被自觉采用，却从未被测量）。
