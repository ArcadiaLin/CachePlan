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

**当前状态：本项目已完成的实验数为 0。** 主线顺序是 E01 → E06 → E02/E03。

- **进行中（E01，第一个实验）：P4A 历史 session 轨迹的全量观测。** 详见 [`experiments/e01-p4a-trajectory.md`](experiments/e01-p4a-trajectory.md)。**s0–s4 完成，s5（轨迹统计与可视化）待做。**

  s3 的闸门已通过：逐步还原在 60 份带 ground truth 的 session 上 **1142 个校验点中 1123 个 Δ=0**，不是估计量。同时推翻了「语料同质」的前提——Δ oracle 判定出**至少 18 种工具配置**，按时间排成连续区块（一个月里 harness 在演进），已知工具 schema 原文只覆盖末尾 60 份。**跨区块共享前缀从 token 0 断裂，此后一切前缀分析必须在区块内做**（最大区块 1538 份）。

  s4 给前缀失效定了价，两个来源量级差 35 倍：

  | 来源 | tokens | 占全语料 prefill |
  |---|---:|---:|
  | **会话内注入**：一条 `role=user` 的 TodoList 提醒回溯性剥掉此前所有 `<think>`，改写上下文中段 | **204,579,397** | **3.65%** |
  | 首步跨 run 分歧（时间戳 + 工作目录树） | 约 5.9M | 约 0.11% |

  前者 61.1% 的 session 中招、首次触发高度集中在 step 11，且**可直接消除**（`preserve_thinking`，或改用 `role=tool` 注入）。后者的大头是 kimi-code 注入 `systemPrompt` 的工作目录树而非时间戳，且不改代码也能靠按变体分组调度回收 89%。

  **OQ2 的交付物尚未完成**：s4 精确给出了静态前缀那一段（区块内 20,652–22,014 tok），但**每输入私有内容 / 生成轨迹**两段还没拆。三段齐了才能给 E06 的 baseline 上界定价，这是 s5 的前置任务，优先于可视化。

- **下一个（E06）：A2 静态前缀 baseline —— "把可复用指令全部写进 system prompt"。** 由 [OQ2](open-questions/Placement-of-reusable-context.md) 提出，排在 E01 之后。这是本项目**必须先打败的第一个 baseline**，审稿人一定会问 *Why don't you simply put the reusable instructions into the system prompt?*

  四臂：A0 现状（两跳动态加载）／A1 天真拼接（验证"追加到易变块之后 = 缓存不到"这个陷阱真实存在）／**A2 static-first layout（工具集固化 + `tools → skill → 易变块`，要打败的就是它）**／A3 本项目方法叠加其上。

  两条硬约束：**贡献报告为 $A3-A2$，不是 $A3-A0$**；代价模型必须含命中/未命中 prefill、KV 占用、decode 侧成本、任务质量四项，否则 A2 白嫖指标。多 skill（$N \gg 2$）场景 P4A 给不出，需另造。E02 的 infra 约束（vLLM 0.22.1 + `--enable-prompt-tokens-details`、单轮、MCP 固化）同样适用。

- E02（四级 autonomy 对比）保留、设计不变，排在 E06 之后；已非阻塞项。E03 的干预 (a) 是 E06 在 micro-benchmark 上的缩小版，其"收益方向正确但绝对量可忽略"的预期需按 OQ2 重估——若 skill 确实落在跨 run 分叉点之后，重排的绝对量未必可忽略。

- 待办：`refs.bib` 在 prompt/KV cache 系统方向上**仍然完全为空**。三篇现有文献（含 `2026-ARA`）无一是 cache 方向——它们在 cache 上的共同沉默是 C07 的证据，但不能替代主线文献工作。这是 related work 层最大的缺口，优先级高于两篇 staged 精读稿的评审。
- 待办：`experiments/p4a/src/extract/layer4_v2/` 的处置（见下方 Experiments 节）。随 E02 降级，此项也不再紧急。

## Open Questions

| Question | Status | Doc | Refs | Resolution |
|---|---|---|---|---|
| OQ2：可复用上下文（Skill）应该放在哪？"全部写进 system prompt" 是不是已经够用？ | **OPEN** | [open-questions/Placement-of-reusable-context.md](open-questions/Placement-of-reusable-context.md) | — | 2026-09-02 提出。本项目**必须先打败的第一个 baseline**：若每个 run 都必用同一份 Skill，静态注入天然形成稳定可缓存前缀，还省掉读 skill 的 step 与轨迹不稳定。已核实 P4A 现状是两跳动态加载、且第一个 assistant 动作即含论文 id，故 skill 落在跨 run 分叉点之后。**2026-09-02 更新**：E01 s4 已给出三分解中的静态前缀一段——最大区块内跨 run 共享前缀 20,652 tok（占首步 93.3%），把时间戳与工作目录树归一后可达 21,944 tok（99.1%），即 A2 布局的天花板已经很接近现状，静态前缀本身没剩多少空间。**但另两段（每输入私有内容 / 生成轨迹）尚未拆**，仍无法定价。s4 另有一个与本问题直接相关的发现：真正的大头不在首步前缀（约 0.11% prefill），而在会话内注入导致的回溯改写（3.65%），后者与 skill 放在哪里无关，A2 布局解决不了。贡献须报告为 $A3-A2$（对静态布局强 baseline）而非 $A3-A0$。 |
| OQ1：Is agentic execution necessary for data-intensive workloads (P4A)? | **DEFERRED** | [open-questions/Necessity-of-agentic-execution.md](open-questions/Necessity-of-agentic-execution.md) | `2026-ARA` | 2026-09-01：**未被回答，被降级。** 该问题原本挡路的理由是"可能在优化一种没人真在用的执行方式"。`2026-ARA` 的 ARA Compiler（§4）是本 workload 类别的第二个独立实例，由第三方以 **agent skill** 形态部署——~482 行自然语言规格载入 coding agent 上下文，Seal Level 1 在环校验迭代 2–3 轮，23+7 篇输入上首轮通过率 0/30。研究对象的真实性因此不再依赖本问题的答案，strawman 风险排除。**"需要多少 agency"仍完全开放**：RW03 未做 autonomy-level 消融。E02 保留、设计不变，但从阻塞项降为设计余量的探究。见 `ara/logic/claims.md` C12。 |

`Refs` 列填支撑该问题的文献 citekey（见 [Literature](#literature)）；一个问题在有文献支撑之前被 RESOLVED，应当在 Resolution 里说明结论是纯实验得出的。

`Status` 取值：`OPEN` / `RESOLVED` / `DEFERRED`。**`DEFERRED` 不是 `RESOLVED` 的弱化版，是另一回事**——它表示问题本身没有被回答，但它对主线的**阻塞作用**被消解了，因此不再排在关键路径上。把 DEFERRED 当成"已解决"来引用是错误的：它的 Resolution 栏记的是**为什么可以先不答**，不是答案。

## Decisions

问题被解决后，在此追加一行，并可选地在 `docs/decisions/` 下补充完整推导过程。下表也记录**不由 open question 触发**的研究级决定（这类行的 Doc 列指向 `ara/` 的轨迹节点）。

**尚无任何 open question 被 RESOLVED**（OQ1 是 DEFERRED，含义见上表下方说明，不等于已解决）。

| Decision | Date | Doc | Rationale (short) |
|---|---|---|---|
| workload 定名为 data-intensive / data-processing agent workflows | 2026-08-31 | [`AGENTS.md` → Workload Under Study](../AGENTS.md#workload-under-study)；ara 节点 `n8-workload-naming` | 跨 run 的固定过程 + 大量重复才是 cache 复用空间的来源；按任务语义命名指向错误的属性 |
| P4A 定位为起点而非实验；确认本项目零实验 | 2026-09-01 | 上方 Current direction；ara 节点 `n17-repositioning` | 把 P4A 的工程记录编号进 E-series 并标「已完成」会让研究记录看起来已有实验产出，是失真的。继承观测与本项目实验的证据地位不同，必须分开 |
| OQ「agentic execution 是否必要」降级为 DEFERRED，不再阻塞主线 | 2026-09-01 | 上方 Open Questions 表；`ara/logic/claims.md` C12；ara 节点 `n19-oq1-deferred` | 该 OQ 的阻塞力来自 strawman 风险（优化一种没人真在用的执行方式）。`2026-ARA` 提供了同类 workload 的第二个独立实例且部署形态就是 agent，风险排除。必要性问题本身仍未回答，故记 DEFERRED 而非 RESOLVED |

## Experiments

**本项目已完成的实验：0。** 下面第一项是本项目的实验计划，其余两项是 P4A 这个历史项目的记录（继承观测，只支撑动机，不支撑结论）。

- **计划中** — [`ara/logic/experiments.md`](../ara/logic/experiments.md)：E01（P4A 轨迹全量观测，进行中）、E02（四级 autonomy 受控对比）、E03（前缀重排与发现固化 micro-benchmark）、E04/E05（两篇精读稿的人工评审）。除 E01 外全部未开始。
- **计划中（不在 `ara/` 快照内）** — **E06：A2 静态前缀 baseline**，由 [OQ2](open-questions/Placement-of-reusable-context.md) 提出，排在 E01 之后。编号取 E06 而非插进 E01–E05，是为了避开 2026-09-01 冻结的 `ara/` 快照里已占用的编号；下次 `/compiler` 整体重编译时并入。
- [`experiments/p4a.md`](experiments/p4a.md) — P4A 项目实验记录（含数据资产与使用边界）
- **`experiments/p4a/src/extract/layer4_v2/`** — `refractor.md` 重构方案的完整实现：程序批处理 + 两次纯文本 LLM 调用 + 轻量修补 + v1 agent 兜底，替代 v1 的「每篇一个 ReAct agent」。按 autonomy ladder 落在 L2–L3，其 README 称已完成 200 篇 v1/v2 对照评估、裁定召回 96.1% 通过。

  **本文档此前从未记录它的存在**（2026-09-01 补记）。它记为继承观测 B02，**不能直接结案上面那条 open question**，原因有四：(1) 原始报告 `reports/layer4_v2_eval200.md` 不在本仓库，数字未经核实；(2) v1 是参照系而非独立对照臂，而 v1 自身已知有质量问题（抽样的 `checked_by` 分布显示 agent 经常没真正核验资源）；(3) 两臂不独立——v2 失败会回退到 v1 的 agent；(4) 完全没有本项目定为一等指标的行为统计与双口径成本。

  **待裁定**：(a) 补齐上述四点后正式纳为 E02 的一臂；(b) 视作 p4a 的工程决定、与 E02 无关；(c) 先取回并核实那份报告再定。详见 ara 节点 `n11-docs-code-drift`。

## Literature

- 索引与笔记规范：[`literature/README.md`](literature/README.md)
- 文献元数据（唯一来源）：[`../references/refs.bib`](../references/refs.bib)
- PDF 等外部材料：`references/papers/`（gitignored，靠 `refs.bib` 里的 url 取回）

**已入库**：`2026-ARA`（The Last Human-Written Paper: Agent-Native Research Artifacts, arXiv:2604.24658v3）。支撑 OQ1 的降级与 C12。判断记在 [`ara/logic/related_work.md`](../ara/logic/related_work.md) 的 RW03；尚未在 `docs/literature/` 下单独立笔记——按该目录的规范，笔记只在需要展开判断时才写，当前 RW03 已足够。
