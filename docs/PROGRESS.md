# Research Progress

本文档是本仓库的主线追踪文档，记录当前研究方向的进展，以及 `docs/open-questions/` 中各问题的解决状态。

**给 agent 的约定**：一个 open-question 一旦在下表中被标记为 `RESOLVED`，其对应的原始文档已经是历史记录，**不要在未被用户明确要求的情况下读取它** —— 只需参考下表中的 Resolution 摘要即可。这是为了避免已收敛的长篇讨论反复被拉入上下文。仅当用户明确要求查看某个已解决问题的完整讨论过程时，才去读取原文档。

## Current direction

见 [`AGENTS.md`](../AGENTS.md)：cache-aware planning and execution in LLM agents（研究方向仍在演进中，以 AGENTS.md 中的描述为准）。

**Workload 命名（2026-08-31 更正）**：本项目研究的 workload 类别是 **data-intensive / data-processing agent workflows**，不是 "Data Analysis Agent"。P4A 的核心特征不是"分析数据"，而是 Agent 依据固定的 procedural knowledge（Skill），对大量不同输入反复执行同一个长程、工具增强、带 validation 与 repair 的 E2E workflow。完整定义见 [`AGENTS.md` → Workload Under Study](../AGENTS.md#workload-under-study)。这一命名对研究是 load-bearing 的：跨 run 的**固定过程 + 大量重复**才是 cache 复用空间的来源，"data analysis" 强调的是任务语义，指向了错误的属性。

**P4A 的定位（2026-09-01 确认）**：P4A 是**让这个问题被看见的起点**，同时是下一个实验要去观测的**数据来源**。它**不是本项目的核心实验，不是对照臂，也不产生本项目的结果**。

由此确认一件必须如实呈现的事：**本项目至今没有完成过任何实验。** P4A 工程过程产生的已完成记录（单 session 逐事件解剖、layer4_v2 的 200 篇对照评估）属于**继承观测**，它们能支撑"这个现象存在、量级值得关注"这一动机，但不能支撑任何研究结论——按 [`experiments/p4a.md`](experiments/p4a.md) 第 4 节的使用边界，P4A 数据只能做诊断性/动机性分析，不能作为"CachePlan 方法是否有效"的对照基线。

这条区分在 `ara/` 里落成了结构：继承观测记为 B-series（[`ara/logic/inherited-observations.md`](../ara/logic/inherited-observations.md)），本项目自己的实验记为 E-series（[`ara/logic/experiments.md`](../ara/logic/experiments.md)，当前全部未开始）。

## Current Work

> **本章节的维护规范**（仅适用于本章节）：这里只记录**当前正在进行的工作**，保持简短。**不对历史进行维护**——每次更新本章节都是**整节完整重写**，直接覆盖旧内容，不追加、不保留历史条目、不写变更记录。仅当用户显式要求"只调整某一处"时才做局部修改。需要留存的历史属于 Open Questions / Decisions / Experiments 各表，不属于这里。

**当前状态：本项目已完成的实验数为 0。** 下面第一条是下一步要做的事。

- **下一步（第一个实验，E01）：拿 P4A 的历史 session 轨迹做全量观测研究。** 性质是观测而非干预——对象是已存在且不可变的日志，只读、不跑 agent、不改 p4a 代码，分析必须落成脚本。五个测量目标：
  1. **cache 字段可用性核查**（即下方原「先决核查项」，现为本实验的阶段 1，是闸门）；
  2. 放大倍数的**全量分布与分层归因**（把现有的 n=80 抽样扩到全量，检验它究竟与轮数还是与论文长度相关）；
  3. **跨 run 前缀重叠结构**——从事件流重建 token 序列，实测共享前缀有多长、在哪里断；
  4. **轨迹分叉点**——语义等价但措辞不同的行为在何处首次产生不同 token；
  5. **行为统计**——被赋予的 agency 有多少真的被行使（轮数分布、repair 触发率、回溯频率、开放工具调用比例）。
  产物入 `data/processed/`（gitignored）并标注来源 tar.gz 版本、脚本、日期。详见 [`ara/logic/experiments.md`](../ara/logic/experiments.md) 的 E01。
- 已把研究 workload 定名为 data-intensive / data-processing agent workflows（见上节），`AGENTS.md`、本文档、open-question 文档三处术语已对齐。
- 已确认 P4A 的定位为起点而非实验（见上节），并据此重组了 `ara/` 的实验层与 claim 依据表述。
- 研究记录已按 ARA 标准落成 [`ara/`](../ara/)：11 条 claim、5 个未开始的实验、2 条继承观测、19 个轨迹节点、10 张证据表。**没有任何一条 claim 由本项目的实验支撑**——每条 claim 显式标注「依据类型」（继承观测 / 代码事实 / 方法论约定 / staged 文献 / 无）。
- 文献管理规范已建立（`references/` + `docs/literature/`，见下方 Literature 节），骨架就位但**尚无任何文献入库**。两篇已精读论文的 `refs.bib` 条目已于 `c6ece08` 移除，精读稿留在 gitignored 暂存区，其结论一律 staged、不可引用。
- 待办：验证 open question「Is agentic execution necessary」——构造不同 autonomy level 的 P4A 实现做 controlled comparison。**注意 `experiments/p4a/src/extract/layer4_v2/` 已存在一个 L2–L3 实现且跑过 200 篇评估**（见下方 Experiments 节），但它是 P4A 自己的工程验收，不能直接当作本实验的一臂——如何处理待定。
- 待办：`refs.bib` 在 prompt/KV cache 系统方向上完全为空，这是当前 related work 层最大的缺口，优先级高于两篇 staged 精读稿的评审。

## Open Questions

| Question | Status | Doc | Refs | Resolution |
|---|---|---|---|---|
| Is agentic execution necessary for data-intensive workloads (P4A)? | OPEN | [open-questions/Necessity-of-agentic-execution.md](open-questions/Necessity-of-agentic-execution.md) | — | — |

`Refs` 列填支撑该问题的文献 citekey（见 [Literature](#literature)）；一个问题在有文献支撑之前被 RESOLVED，应当在 Resolution 里说明结论是纯实验得出的。

## Decisions

问题被解决后，在此追加一行，并可选地在 `docs/decisions/` 下补充完整推导过程。下表也记录**不由 open question 触发**的研究级决定（这类行的 Doc 列指向 `ara/` 的轨迹节点）。

**尚无任何 open question 被 RESOLVED。**

| Decision | Date | Doc | Rationale (short) |
|---|---|---|---|
| workload 定名为 data-intensive / data-processing agent workflows | 2026-08-31 | [`AGENTS.md` → Workload Under Study](../AGENTS.md#workload-under-study)；ara 节点 `n8-workload-naming` | 跨 run 的固定过程 + 大量重复才是 cache 复用空间的来源；按任务语义命名指向错误的属性 |
| P4A 定位为起点而非实验；确认本项目零实验 | 2026-09-01 | 上方 Current direction；ara 节点 `n17-repositioning` | 把 P4A 的工程记录编号进 E-series 并标「已完成」会让研究记录看起来已有实验产出，是失真的。继承观测与本项目实验的证据地位不同，必须分开 |

## Experiments

**本项目已完成的实验：0。** 下面第一项是本项目的实验计划，其余两项是 P4A 这个历史项目的记录（继承观测，只支撑动机，不支撑结论）。

- **计划中** — [`ara/logic/experiments.md`](../ara/logic/experiments.md)：E01（P4A 轨迹全量观测，下一步）、E02（四级 autonomy 受控对比）、E03（前缀重排与发现固化 micro-benchmark）、E04/E05（两篇精读稿的人工评审）。全部未开始。
- [`experiments/p4a.md`](experiments/p4a.md) — P4A 项目实验记录（含数据资产与使用边界）
- **`experiments/p4a/src/extract/layer4_v2/`** — `refractor.md` 重构方案的完整实现：程序批处理 + 两次纯文本 LLM 调用 + 轻量修补 + v1 agent 兜底，替代 v1 的「每篇一个 ReAct agent」。按 autonomy ladder 落在 L2–L3，其 README 称已完成 200 篇 v1/v2 对照评估、裁定召回 96.1% 通过。

  **本文档此前从未记录它的存在**（2026-09-01 补记）。它记为继承观测 B02，**不能直接结案上面那条 open question**，原因有四：(1) 原始报告 `reports/layer4_v2_eval200.md` 不在本仓库，数字未经核实；(2) v1 是参照系而非独立对照臂，而 v1 自身已知有质量问题（抽样的 `checked_by` 分布显示 agent 经常没真正核验资源）；(3) 两臂不独立——v2 失败会回退到 v1 的 agent；(4) 完全没有本项目定为一等指标的行为统计与双口径成本。

  **待裁定**：(a) 补齐上述四点后正式纳为 E02 的一臂；(b) 视作 p4a 的工程决定、与 E02 无关；(c) 先取回并核实那份报告再定。详见 ara 节点 `n11-docs-code-drift`。

## Literature

- 索引与笔记规范：[`literature/README.md`](literature/README.md)
- 文献元数据（唯一来源）：[`../references/refs.bib`](../references/refs.bib)
- PDF 等外部材料：`references/papers/`（gitignored，靠 `refs.bib` 里的 url 取回）
