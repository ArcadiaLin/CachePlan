# P4A 候选案例清单 I–M：Kimi 来源

状态：2026-09-11 按[候选池构造主线](README.md)重新整理，统一使用七项描述。原 C/D/E/F/G 依次编号为 I/J/K/L/M；原文对轨迹复用的补强已合并至[案例 A](README.md#case-a)。

来源是 Kimi Code CLI 在 2026-09-11 开展的公开网络检索与页面抓取。原记录报告核对过部分论文身份和仓库内容，未执行代码或正式对照检索。本次整合保留这些取证入口与观察，未新增核查；尚未形成满足候选池要求的版本化证据与 query 标签。

除 A 的用户经历外，本文各项均为可构造的研究需求，不写成已发生的检索过程。原建议优先推荐记忆评测与 Judge 榜单，其次 RAG；认为长上下文有效长度与数学评测中，资源的增量可能偏更新和细节。保留这些初判，最终按本地种子、扩展路径和选择转折决定推进顺序。

<a id="case-i"></a>

## I：Agent 记忆系统的评测口径

**来源与状态：** Kimi 原候选 C，原建议推荐度最高；已有论文与仓库线索，尚未完成案例取证和正负例核查。

**研究需求 / query：** 为跨会话个人助理寻找记忆系统研究及评测，判断候选支持哪些记忆能力、使用什么数据版本，以及报告结果是否可比较。

**已有候选与材料：**

- [MemGPT](https://arxiv.org/abs/2310.08560)、[MemoryBank](https://arxiv.org/abs/2305.10250)、[Mem0](https://arxiv.org/abs/2504.19413)、[A-MEM](https://arxiv.org/abs/2502.12110)，以及 [LoCoMo](https://arxiv.org/abs/2402.17753)、[LongMemEval](https://arxiv.org/abs/2410.10813)。
- [snap-research/locomo](https://github.com/snap-research/locomo) README Note 与 `locomo10.json`：原记录称公开的 10 段对话来自初版 50 段的子集，需结合版本与论文设置核查。
- [mem0ai/mem0 的 evaluation 目录](https://github.com/mem0ai/mem0/tree/main/evaluation)：原记录称 MemoryBank / MemGPT 的部分基线数字来自该项目自有 harness 重跑。
- LongMemEval 数据 schema、以 `_abs` 结尾的题目与检索评测过滤逻辑，以及 2025-09 清洗版线索。
- A-MEM 主库与论文实验仓库的分工；MemGPT 仓库迁至 letta-ai/letta 的身份延续线索。

**五步路线中的入口：** 从 v1 的长期记忆、对话 Agent 或上述基准使用论文中找种子；加入同 venue、任务或评测条件不匹配的候选；沿共享数据与评测代码、引用向外扩展，保留只共用“memory”名称或任务环境的干扰项。

**预期选择转折：** 从按名称或分数选择论文，转向核对记忆能力、数据子集和评测实现后重新确定可比较工作；必要时沿数据关系发现更合适的评测论文。

**核查重点：** 区分系统论文与 benchmark 论文的角色。MemoryBank 作为系统候选不能仅因其不是 benchmark 而排除；只有当前子问题要求基准时才按基准条件判断。公开子集与论文分数的对应关系需逐篇确认；自有 harness 重跑需要标明条件，不能仅据此降低可信度。`_abs` 过滤在检索评测还是最终 QA 中生效要分清。Mem0 判分 bug 与 Zep 等争议仅保留为单方报告线索，未独立复现；Mem0 venue 等元数据待一手核查。

**可复用记录与限度：** 保存资源角色、数据子集与版本、能力覆盖、评测器和结果来源。记忆系统的基本定位通常可以由正文判断；资源增量应落实到具体配置差异，不能从个别线索推出所有 LoCoMo 数字不可比较。

<a id="case-j"></a>

## J：LLM-as-a-Judge 的榜单版本与抗刷榜能力

**来源与状态：** Kimi 原候选 D，原建议优先推荐；版本变化与具体数字尚未形成可复核证据表。

**研究需求 / query：** 为指令微调模型寻找成本可接受、与人类判断相关、能抵抗简单投机策略的自动评测研究，并判断已有榜单结果是否适用。

**已有候选与材料：**

- [Judging LLM-as-a-Judge / MT-Bench](https://arxiv.org/abs/2306.05685)、[tatsu-lab/alpaca_eval](https://github.com/tatsu-lab/alpaca_eval)。
- [Length-Controlled AlpacaEval](https://arxiv.org/abs/2404.04475)、[Cheating Automatic LLM Benchmarks](https://arxiv.org/abs/2410.07137)。
- AlpacaEval README 与 evaluator 元榜单：原记录涉及 1.0 → 2.0 的基线变化、raw win rate 与 length-controlled 指标、相关性 0.93 → 0.98，以及 `longest` 基线的 62.2% 一致率。
- FastChat 仓库 `fastchat/llm_judge/` 下 judge prompt 模板与评测配置。

**五步路线中的入口：** 从 v1 中使用 MT-Bench、AlpacaEval 或相关 judge 的论文找种子；加入同 venue、指标或版本不匹配的候选；沿评测器、配置和引用扩展到偏差及投机策略研究，保留只共享 judge 模型而不满足需求的候选。

**预期选择转折：** 发现名义相同的分数对应不同参考模型或指标，修正比较对象；或从 evaluator 的简单基线发现初始候选中没有的抗刷榜研究。

**核查重点：** 定位各版本默认模型、指标、judge prompt 与切换日期，确认论文是否已经报告这些条件。原记录“某分数的版本永远无法从正文查到”“两次静默切换”等说法不作为事实沿用。AlpacaEval 原始资源的引用对象与后续论文要分开，不能将“仓库是原始引用对象”扩大为从未有相关论文。所有相关性与一致率数字需核对数据、指标和分母。

**可复用记录与限度：** 保存评测器、参考模型、prompt、指标版本和已知投机基线。偏差机制与 length control 可能由论文直接说明；外部材料的增量集中在版本对应、配置和发现路径。

<a id="case-k"></a>

## K：RAG 评测中的同名资源、使用条件与数据修订

**来源与状态：** Kimi 原候选 E，原建议更适合展示修正判断；具体工件状态与本地入口待核查。

**研究需求 / query：** 为 RAG 方法寻找适合当前任务与人工标注预算的评测研究，确认候选是方法、数据集还是评测框架，并核查版本与使用条件。

**已有候选与材料：**

- [RGB](https://arxiv.org/abs/2309.01431)、[RAGAS](https://arxiv.org/abs/2309.15217)、[ARES](https://arxiv.org/abs/2311.09476)。
- [Corrective Retrieval Augmented Generation](https://arxiv.org/abs/2401.15884)及 [HuskyInSalt/CRAG](https://github.com/HuskyInSalt/CRAG)，与另一项 [Comprehensive RAG Benchmark](https://arxiv.org/abs/2406.04744)的 CRAG 名称碰撞。
- [ARES README](https://github.com/stanford-futuredata/ARES)：原记录提及至少 50 条、理想数百条人工标注三元组及 GPU 等运行条件，具体适用流程待核查。
- [RGB 仓库](https://github.com/chen700564/RGB) News 中 `en.json` / `zh.json` 的修订线索。
- [FreshLLMs / FreshQA](https://arxiv.org/abs/2310.03214)：论文名与资源名的对应，以及答案随数据快照更新的线索。

**五步路线中的入口：** 从 v1 的 RAG、评测或上述资源使用论文中找种子；加入同 venue、角色或条件不满足需求的候选；沿同名资源的具体 URL、共享评测数据和引用扩展，保留错误名称匹配或泛 RAG 关联带入的干扰项。

**预期选择转折：** 将同名方法与 benchmark 正确对应，核对标注与运行条件后调整论文选择；通过数据修订和 FreshQA 的资源入口，发现或重新判断相关工作。

**核查重点：** 标题与摘要能否完成初步消歧；Corrective RAG 的实际评测数据是否来自 Self-RAG；ARES 的人工数据要求对应哪个步骤，不能据此把“Automated”直接判为失实；RGB 修订适用哪个版本；FreshQA 的更新频率与所用快照是否一致。

**可复用记录与限度：** 保存实体身份、资源角色、使用条件、勘误和时间快照。能力维度通常可由正文理解；需要用实际选择过程确认资源对消歧、门槛与时效性的增量。

<a id="case-l"></a>

## L：长上下文的声称长度与有效能力

**来源与状态：** Kimi 原候选 F，原建议指出其资源增量偏更新与深化。与[案例 B](README.md#case-b)共享部分论文，保留为不同需求。

**研究需求 / query：** 为长上下文应用寻找能反映实际任务能力的评测研究，区分可接受输入长度与在特定任务、设置下的有效能力，判断哪些结果可用于当前模型选择。

**已有候选与材料：**

- [RULER](https://arxiv.org/abs/2404.06654)、[HELMET](https://arxiv.org/abs/2410.02694)、[NoLiMa](https://arxiv.org/abs/2502.05167)、[Lost in the Middle](https://arxiv.org/abs/2307.03172)。
- [NVIDIA/RULER](https://github.com/NVIDIA/RULER)与 [adobe-research/NoLiMa](https://github.com/adobe-research/NoLiMa) 的 README、更新后的模型结果和实验配置。
- RULER 的 haystack 来源与 Kamradt NIAH 仓库的可能关系；HELMET 的结果表及排名相关性 notebook。
- 原记录提及 Llama 4 Scout 的 10M 声称长度与 NoLiMa 下 1K 有效长度、HELMET 的 59 模型结果；这些是待核查的任务特定数字。

**五步路线中的入口：** 从 v1 中使用长上下文模型或相关 benchmark 的论文找种子；加入同 venue、能力指标不匹配的候选；沿共享数据来源、评测代码与引文扩展，保留只共享长度标签但任务不同的论文。

**预期选择转折：** 新结果或配置细节改变对评测适用性和论文跟进优先级的判断；是否能够帮助发现新的目标论文仍需验证。

**核查重点：** 长度单位、模型版本、任务、阈值和日期，不能将某 benchmark 的有效长度当作普遍能力上限。数据来源共享不等于分布或任务完全相同，不能直接推出整个 NIAH 家族同质。区分“存在可复算 notebook”和“已经成功复算”；RULER 等 venue 元数据待一手核查。

**可复用记录与限度：** 保存任务设置、长度定义、动态结果快照和数据谱系。原建议已指出部分核心结论在摘要中可见；如无实际选择转折，应作为更新和细节补充，不夸大论文外资源作用。

<a id="case-m"></a>

## M：数学推理评测的污染与数据版本谱系

**来源与状态：** Kimi 原候选 G，合并 Claude 在 HumanEval / EvalPlus 案例中提到的 GSM8K → GSM1k 类比。污染、版本修订和检索困难均需进一步取证。

**研究需求 / query：** 为数学推理方法寻找评测研究，区分对已有题目的扰动鲁棒性、对新题的泛化与潜在训练污染，选择能够支持当前研究判断的数据和论文。

**已有候选与材料：**

- GSM8K、[GSM-Symbolic](https://arxiv.org/abs/2410.05229)、[GSM-Plus](https://arxiv.org/abs/2402.19255)、[GSM1k](https://arxiv.org/abs/2405.00332)。
- [apple/ml-gsm-symbolic](https://github.com/apple/ml-gsm-symbolic) README、数据样例中的 `original_id`、canary GUID 与生成器发布状态。原记录称模板源于 GSM8K test 的 100 题。
- GSM-Plus 的题目派生关系与公开数据范围；GSM-Symbolic §2 对 GSM1k 的引文上下文。
- GSM1k 的“最多下降 13%”、Phi / Mistral 系列的过拟合解释，以及后续修订为 8% 的线索；原记录明确后者仅来自二手来源，需核对 arXiv 各版原文。

**五步路线中的入口：** 从 v1 的数学推理或 GSM 系列评测论文中找种子；加入同 venue、同题源但不能回答当前需求的困难候选；沿题目派生关系、共享数据与引文向外扩展，保留只共享数学任务却不满足判定条件的候选。

**预期选择转折：** 核查题源后改变对某基准能支持何种结论的判断；沿引文或数据谱系发现初始候选之外的评测论文。

**核查重点：** 派生题能支持什么鲁棒性或泛化判断，不能直接由派生关系判定训练污染；新题也不自动保证无污染。核对 `original_id`、canary 与生成器状态的版本。GSM1k 数字修订、GSM-Symbolic 的 venue 归属等先回一手材料；“标题缺少 contamination/benchmark 所以关键词难命中”需要检索记录验证。

**可复用记录与限度：** 保存题目来源、转换方式、数据版本、修订和论文间关系。部分关键结论在摘要或正文中已可得，资源增量应落实到可审计样例、版本和发现过程；不把潜在污染解释写成已确认事实。
