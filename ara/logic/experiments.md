# Experiments

> **本项目至今没有完成过任何实验。下面 E01–E05 全部未开始。**

这不是一个遗漏，而是当前的真实状态，artifact 必须如实呈现它。P4A **不是本项目的实验**：
它是让这个问题被看见的**起点**，同时也是 E01 要去观测的**数据来源**。P4A 自身产生的、
已完成的记录在 [`inherited-observations.md`](inherited-observations.md)（B01、B02）——
那是背景，不是结果。

`solution/constraints.md` 第 1 条对此有硬约束：**P4A 数据只能做诊断性/动机性分析，
不能作为"CachePlan 方法是否有效"的对照基线。** E01 是诊断性观测，符合该约束；任何要
回答"方法有效性"的实验都必须自建对照。

| ID | 性质 | 主题 | 状态 |
|---|---|---|---|
| **E01** | 观测研究 | P4A 历史轨迹的全量观测 | **未开始 —— 下一步** |
| E02 | 受控实验 | 四级 autonomy 在相同输入上的对比 | 未开始 |
| E03 | 受控实验 | 前缀重排与"发现固化"的联合效应 | 未开始 |
| E04 | 文献评审 | DeepPrep 精读稿的人工评审 | 未做 |
| E05 | 文献评审 | LongDA 精读稿的人工评审 | 未做 |

---

## E01 — P4A 历史轨迹的全量观测研究（**本项目的第一个实验**）

**Verifies**: C01（把抽样量级扩到全量）、C02（cache 口径是否可用）、C10（把代码路径推断
换成 token 序列实测）

**性质**
**观测研究，不是干预实验。** 对象是已经存在、不可变的 P4A session 日志；本实验不运行
agent、不改动 P4A 的任何代码或数据，只读取与统计。它的产出是**一张关于"这类执行长什么样"
的地图**，用来把目前靠抽样与推断支撑的几条 claim 换成全量证据，并确定后续干预实验该测
什么、能用什么指标。

**Setup**
数据源为 `data/raw/kimi-p4a-sessions.tar.gz`（本仓库内但 gitignored）中的全部 session。
逐 session 读 `agents/main/wire.jsonl` 的事件流（`usage.record`、
`context.append_message`、`tool.result`）。

**Procedure**
分五个测量目标，其中阶段 1 是闸门。

1. **cache 字段可用性核查（先决核查项，闸门）**
   批量核实每条 `usage.record` 的 `inputCacheRead` / `inputCacheCreation` 是否恒为 0，
   统计非零比例与分布。**在这一步完成之前，不得基于 cache 命中率下任何结论。**
   两种互斥结果各自决定后续能用什么指标：
   - **非恒零** → 可以计算真实 cache 命中率分布，作为强证据使用。
   - **恒为零** → 该字段在这套 openai 兼容 provider 下未被正确采集；只能退回基于 prompt
     前缀 token 重叠度的**代理指标**，且此后每处报告都必须标注为估算值而非真实命中率。

2. **放大倍数的全量分布**
   把 B01 的 n=1 与 `refractor.md` 的抽样，扩成全量分布：不只报中位数，还要报尾部形状，
   并按论文长度、轮数、是否触发 repair 分层，检验放大倍数究竟与哪个变量相关。这直接检验
   C01 的 Falsification criteria 里那条反向证伪路径。

3. **跨 run 前缀重叠结构**
   从事件流重建每个 run 的实际 token 序列，两两（或对齐到一个共同起点）计算公共前缀长度：
   共享前缀实际有多长、在**哪个位置**断掉、断在什么内容上。这是把 C10 从"代码路径推断"
   升级为实测的唯一途径，也是 A3（"跨 run 前缀复用的空间足够大到值得优化"）第一次被真正
   测量。

4. **轨迹分叉点**
   定位语义等价但措辞不同的行为在何处首次产生不同 token（立项时的那个观察：
   "I will first read the skill." / "Let me read the skill first."）。统计分叉发生的位置
   分布与分叉后是否再收敛。这决定"cache-aware planning"到底要约束什么。

5. **行为统计**
   实际交互轮数分布、repair 触发率、回溯/重读发生频率、开放工具（外部检索）调用比例。
   这一项独立于 cache：它测的是**被赋予的 agency 有多少真的被行使**，是前置 open question
   的直接输入，也是 E02 里"full agent 臂的自主程度必须被测量而非假定"的方法来源。

**Constraints**
- **只读。** 不得修改原始日志，不得修改或重跑 `experiments/p4a/` 的流水线代码。
- 分析必须落成**脚本**放在 CachePlan 自己的路径下（修补 B01 留下的可复现性缺口）。
- 汇总产物写入 `data/processed/`（gitignored），并标注来源 tar.gz 版本、生成脚本、生成日期。

**Expected outcome**
方向性预期：阶段 1 更可能落到"恒为零"分支，因而后续以代理指标为主；阶段 3 更可能显示
共享前缀在很靠前的位置就断掉（若 C10 成立，断点应出现在第一个 per-run token 处，早于
Skill 内容进入上下文）；阶段 5 更可能显示实际行使的 agency 显著低于被赋予的 agency。
**任一项与预期相反都是有价值的结果**——尤其阶段 3，若共享前缀已经覆盖了固定知识，则 C10
被证伪，本项目的一条核心机制描述需要重写。

**Status**: **未开始**。这是下一步要做的事。

**Evidence**: 待产出

**Depends on**: 无。这是链条的起点，且不被任何未决事项阻塞。

---

## E02 — 四级 autonomy 在相同输入上的受控对比

**Verifies**: C03（提供分层维度）、C10（L4 臂的前缀测量）；直接回答前置 open question

**Setup**
构造四种执行范式的实现，在**相同输入**上比较：Static Workflow / Workflow + LLM Nodes /
Workflow + Repair Agent / Full ReAct-Coding Agent。定义见
[`solution/autonomy-ladder.md`](solution/autonomy-ladder.md)。

B02（`layer4_v2`）提供了 L2–L3 臂的**先例与脚手架**，不提供结果：要作为本实验的一臂使用，
必须补上独立 ground truth、去掉 v1 兜底造成的两臂污染，并加上下面的一等指标。

**Procedure**
1. 固定模型、固定 serving 环境、固定输入集合，只改执行范式。
2. 按任务难度与不确定性分层报告，而不是只报总体均值。
3. **行为统计必须作为一等指标采集**（方法沿用 E01 阶段 5），否则"agent 用上了 agency"
   这句话无法验证。

**Expected outcome**
结果不预期是单调的"Agent 优于 Workflow"或反之，而是**不同任务区域需要不同程度的
agency**：结构规则、信息充分的普通样本上 workflow 可能以更低成本取得相近结果；资源描述
模糊、引用缺失、实体歧义、需要跨来源调查的困难样本上 agent 的 adaptive reasoning 可能
产生明显收益。方向性预期是差距在**个位数点**量级，需据此设计样本量。

**Metrics**
- 质量：resource extraction precision/recall、validation pass rate、hard-case success rate
- 成本：tool calls、LLM token consumption（**必须同时报计费口径与 cache 折算口径**，见 C02）、
  runtime、cost
- 结构：trajectory length
- **行为统计（一等指标，不可省）**：实际交互轮数分布、repair 触发率、回溯/重读发生频率、
  开放工具（外部检索）的调用比例

**Status**: 未开始

**Evidence**: 待产出

**Depends on**: E01 阶段 1（决定成本用真实命中率还是代理指标）、E01 阶段 5（行为统计的
测量方法）。B02 的报告核实是可选前置——若其数字可信，可用来标定样本量。

---

## E03 — 前缀重排与"发现固化"的联合效应 micro-benchmark

**Verifies**: C08, C09

**Setup**
在一个输入同构、且有客观可自动判定 ground truth 的小规模任务集上，做两个正交的干预：
(a) 把跨 run 不变的 procedural knowledge 从模板末尾移到最前；(b) 把 agent 每个 run 都要
重做一遍的"发现"结果（变量/字段/权重的定位）物化成 prompt 前部的固定知识。

**Procedure**
1. 基线：不做任何干预，记录跨 run 前缀复用率、成本、任务质量。
2. 干预 (a)：仅重排，不改内容。测量共享前缀长度的变化。
3. 干预 (b)：固化发现结果。同时测量 cache 指标**与**任务质量。
4. 交叉：(a)+(b)。

**Expected outcome**
(a) 预期是**收益方向正确但绝对量可忽略**——其价值在于确认机制，不在于省下的 token。
(b) 是真正的检验点：若 cache 指标与任务质量同向改善，则 C09 获得第一份证据；若质量下降，
则"固化损害对未见输入的适应性"这条代价被量化。

**Status**: 未开始

**Evidence**: 待产出

**Depends on**: E05（判定用哪个任务集）、E01 阶段 1（判定用真实命中率还是代理指标）。

---

## E04 — DeepPrep 精读稿的人工评审与结论可迁移性判定

**Verifies**: C04, C05, C06（全部为 staged，本评审的作用是决定它们能否升级）

**性质**：文献评审，不是实验。列在此处是因为它是几条 claim 的状态闸门。

**Setup**
`references/papers/fan2026deepprep/close-read.md` 已由 agent 完成精读，但**未经人工评审**，
且其 `refs.bib` 条目已被移除。按 `references/README.md` 的规范，未经评审的结论不进 `docs/`。

**Procedure**
1. 人工核对精读稿中作为 C04/C05/C06 依据的数字是否确实出自原文，尤其是**由笔记作者自行
   推导而非论文声明**的那部分（结构收益与训练收益的分解）。
2. 判定其结论能外推到什么程度——重点是动作空间可闭合性这一边界条件。
3. 通过则提炼成一篇判断笔记进入 `docs/literature/`，并回填 `refs.bib` 与 PROGRESS 的
   `Refs` 列；不通过则明确记录否决理由。

**Expected outcome**
两种可能：结论可信但适用边界很窄（因其消除了 P4A 里最难消的开放工具面），或结论的关键
分解站不住（因来源论文未做该对照实验、无方差）。任一结果都改变 C04–C06 的 status。

**Status**: 未做。精读稿处于 staged。

**Evidence**: `evidence/tables/table05-*.md`, `evidence/tables/table06-*.md`（均标 staged）

---

## E05 — LongDA 精读稿的人工评审与第二 workload 可行性判定

**Verifies**: C07（staged）

**性质**：文献评审 + 可行性判定，不是实验。

**Setup**
同 E04，针对 `references/papers/anon2026longda/close-read.md`。此外该来源被考虑作为
P4A 之外的第二个 workload。

**Procedure**
1. 人工评审精读稿结论。
2. 单独判定第二 workload 的可行性，已知的主要障碍是**数据未发布**（query 与 ground
   truth 未公开），以及重复次数偏小、输入异构。
3. 若不自建，记录"先观望、接收后再取"的决定与理由。

**Expected outcome**
预期结论是：作为方向性旁证可用，作为完整第二 workload 不可用；可能可行的是取其中输入
真正同构的子集做受控 micro-benchmark（即 E03 的任务集）。

**Status**: 未做。精读稿处于 staged。

**Evidence**: `evidence/tables/table07-*.md`, `evidence/tables/table08-*.md`,
`evidence/tables/table09-*.md`（均标 staged）
