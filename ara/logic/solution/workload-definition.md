# Workload Definition

本项目研究的 workload 类别及其命名理由。这是目前**唯一一个已收敛的 decision**
（2026-08-31），对应 C03。

## 定名

> **data-intensive / data-processing agent workflows**
>
> 不是 "data analysis agents"，不是 "Data Analysis Agent"。

## 五条判据

一个 workload 属于本类别，当且仅当五条同时成立：

| # | 判据 | 在 P4A 中的体现 |
|---|---|---|
| 1 | **fixed procedural knowledge** — 一份长而稳定的 Skill / agent prompt，对每个输入编码同一套流程 | 统一的 skill / `agent_prompt.md`，对每篇论文相同 |
| 2 | **input-parallel repetition** — 同一流程跑在同构但不相同的输入语料上，每输入一次独立 run | 全量 ACL 2025 主会论文，每篇一次独立 run |
| 3 | **long-horizon tool-augmented execution** — 多轮 read / extract / search / merge，跨本地脚本与外部来源 | 分块读全文、查 arXiv/GitHub/HuggingFace、下载文件、跑验证脚本 |
| 4 | **validation and repair** — run 不在首次产出时结束；结果对 schema/checker 校验，失败触发重新调查或定点修复 | `validate_layer4_outputs.py` 失败后 agent 做定点 Edit |
| 5 | **structured end-to-end output** — 交付物是结构化记录，不是对话式回答 | `paper_record.yml` / `resource_records.yml` |

**Sources**
- 五条判据原文 ← `AGENTS.md:33-37` «- **fixed procedural knowledge** — a long, stable Skill / agent prompt that encodes the same procedure for every input;»…«- **structured end-to-end output** — the deliverable is a structured record, not a conversational answer.» [input]
- P4A 的流程 ← `experiments/p4a/refractor.md:8` «现在的 Layer4 是"每篇论文启动一个 Kimi ReAct Agent"。agent 读 skill、分块读全文、查 arXiv/GitHub/HuggingFace、下载文件、判断资源、写 JSON、跑验证脚本。» [input]

## 为什么这个命名是 load-bearing 的

判据 1 与判据 2 联合起来，才是本项目全部研究空间的来源：

> 因为 procedural knowledge 是固定的、run 是大量的，所以跨 run 存在一个大的 *a priori*
> 共享前缀；而 agent 在措辞或步骤顺序上的任何发散，正是侵蚀这个前缀复用的东西。

把它叫作 "data analysis agent" 会把重点放到**错误的属性**上（任务的语义），而不是研究
真正依赖的那个属性（一个固定过程的重复）。

**Sources**
- ← `AGENTS.md:39` «because the procedural knowledge is fixed and the runs are many, there is a large *a priori* shared prefix across runs, and any divergence in how the agent phrases or orders its steps is what erodes reuse of that prefix. Terms like "data analysis agent" put the emphasis on the wrong property (the semantics of the task) rather than on the repetition of a fixed procedure, which is the property the research actually depends on.» [input]
- ← `docs/PROGRESS.md:11` «P4A 的核心特征不是"分析数据"，而是 Agent 依据固定的 procedural knowledge（Skill），对大量不同输入反复执行同一个长程、工具增强、带 validation 与 repair 的 E2E workflow。» [input]

## 这个定义**没有**预设的东西

判据里**不含**"必须由 agent 执行"。这是刻意的：这个类别定义的是 workload 的形状，
而这类 workload 需要多少 agency 是一个**独立的、待实验回答的问题**
（见 [`autonomy-ladder.md`](autonomy-ladder.md)）。

> 这里不预设 full ReAct agent 是这类 workload 的正确执行抽象。

## 判据的实际用法：作为筛选器

五条判据的用途是**筛掉不合格的候选 workload**。已经用它筛过三个候选：

| 候选 | 判据 1 | 2 | 3 | 4 | 5 | 结论 |
|---|---|---|---|---|---|---|
| P4A | ✅ | ✅（上千次） | ✅ | ✅ | ✅ | 主 workload |
| **RW03 的 ARA Compiler** | ✅ ~482 行规格载入上下文 | ✅ 但仅 23+7 篇 | ✅ 四阶段工具增强 | ✅ **首轮通过率 0/30** | ✅ 结构化 artifact | **五条全中**，第二个独立实例（C12）；判据 2 的规模比 P4A 小两个量级 |
| RW01 的 ADP 任务 | ✅ | ✅ | ⚠️ 长在产物不在轨迹（探索预算仅 5 轮） | ✅ | ✅ | 形态吻合但工具面被闭合，不可外推 |
| RW02 的分析任务 | ✅ 但过短 | ⚠️ 仅 30 次且输入异构 | ✅ | ⚠️ 有 validation 无 repair | ✅ | 只能做受限 micro-benchmark |

**筛出的模式**：RW01 / RW02 两个 staged 候选都在判据 2（重复次数）与判据 3（长程）上打折，
而这两条恰恰是 cache 复用空间的直接来源。RW03 是第一个五条全中的外部实例，判据 4 上甚至
比 P4A 一侧的证据更干净（0/30 首轮通过率把 validation-repair 从设计选项变成实测常态）。

**但这不等于泛化前提已满足。** RW03 补上的是 **workload 形态**的第二个实例，不是**轨迹
结构**的第二个观测——我们没有它的任何 session 日志，放大倍数、轮数分布、前缀断点在它身上
全是零观测。约束 5 要求的是后者，因此**仍未满足**（见 `problem.md` 的 A4）。

**Sources（RW03 行）**
- 判据 1 ← `references/papers/liu2026ara.pdf` p29 §B.1 «The Compiler skill specification (∼482 lines of natural lan- guage) is structured into five sections. When loaded into a host agent’s context, it provides the full domain knowl- edge needed to produce a schema-conforming ARA.» [input]
- 判据 2 与 4 ← `references/papers/liu2026ara.pdf` p44 «Each of the 23 PaperBench ARAs and the 7 RE-Bench ARAs converges to a Level- 1 pass within ≤3 iterations of the Compiler’s generate– validate–fix loop (§4). First-iteration pass rate is 0/30; all artifacts require at least one feedback round» [result]
- 判据 3 ← `references/papers/liu2026ara.pdf` p7 Figure 7 caption «The ARA Compiler accepts any combination of research sources and guides a coding agent through four stages of top-down artifact compilation, iterating 2–3× with in-loop ARA Seal Level 1 validation until the output conforms to the protocol.» [input]

**Sources**
- RW01 逐条比对 ← `references/papers/fan2026deepprep/close-read.md:564` «| **long-horizon tool-augmented execution** | ⚠️ **部分吻合** | 算子层面确实长（pipeline 长度 1~28，Fig. 7 分布拖到 20）；但 **agent 交互轮数上限只有 5**。"长"在产物上，不在轨迹上 |» [result, staged]
- RW02 逐条比对 ← `references/papers/anon2026longda/close-read.md:405` «**结论：三条完全符合、两条部分符合。** 它比 P4A 更"窄"（每 block 的产出是一组数字而非一份结构化记录）、重复次数少一个量级（30 vs P4A 的上千），输入的异构程度也高得多。» [result, staged]
