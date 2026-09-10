# Papers for Agents：讨论与备忘

## 前期讨论备忘（截至 2026-09-10）

1. **目标与边界。** 面向已发表论文及代码、dataset、benchmark、模型等材料，方便 Agent 发现、判断、选择并使用研究资源。暂定 SIGMOD 系统论文方向；不要求作者采用新出版协议，也不能恢复未公开的研究过程。
2. **当前叙事。** 以 Agent 的渐进研究案例串起需求、gap、系统回应和评测。核心问题是将分散材料加工为可复用的研究知识。时间、上下文和准确性收益待验证；“值得读”指对当前需求的适用性，不是通用学术价值评分。
3. **资源组织。** [原始 P4A schema](p4a-v1-protocol.md) 可提供资源身份、描述、入口和来源。用户偏好 Agent 生成的 community 摘要，不以复杂知识图谱为中心；community 留到系统设计部分，当前 Introduction 不引入。检测机制需专门设计并与 GraphRAG 具体比较，重叠、层级及互补性均未定。
4. **方法与参照。** 推理式抽取服务于资源库构建，不预设多 Agent、模型训练或通用算子框架。借鉴 AgenticScholar 的案例—问题—设计—评测结构及 ARA 的消费端视角，但它们不替 P4A 证明贡献；已有资源抽取、组织与检索工作需具体比较。
5. **质量与评测。** 核查语义正确性，保留来源、版本、条件和未知状态；区分论文声称、材料观察、执行成功与复现。独立制定任务和质量标准，在等价信息访问及预算下比较合理工具组合，同时评价知识质量、下游行动与构建成本，不仅依赖模型裁判或流畅回答。
6. **待办与工作范围。** 核查真实案例和现有方法缺口，明确构建、组织、访问机制，再商定 benchmark。当前仅推进讨论与中英文 Introduction，未启动实现或实验。后文保留原始意见、AgenticScholar storytelling 骨架及本轮叙事细化；草稿位于 `paper/introduction.zh.md` 和 `paper/main.tex`。

## 意见跟进

当前的 introduction 不太满足一个合适的 introduction 该有的形式，我们应该着重思考这些问题

现状与我们设定的某种理想情况存在什么 gap

单篇论文，零散的数据和信息，并不能很好的支持 Agent 进行学术研究和阅读，（ARA）提出了论文 PDF 压缩了大量论文相关信息。

论文越来越多，什么论文更加值得读（被引量高，与我论文相关），什么论文更加值得跟进（后续工作推进，比如代码库维护），哪些资源可以服务于我的idea验证（benchmark、datasets），论文间的关系（例如 DSPY 与后期的 textgrad 论文有很密切的关系）等问题。

从上下文角度来说， Agent 如果需要了解一篇论文的工作，需要从 pdf 或者其他格式获取原文，提取其中文本，大量重复工作被进行。论文、benchmark 等资源需要检索和阅读，如果我们将这些工作汇总在一个资源库中，将极大加速这一流程，节省时间和上下文。还能提升准确性

datasets benchmark 等资源越来越被频繁提出，如果能够让其与论文关联起来，系统还能够为“我的论文适合在哪些benchmark上评测”提供支撑，此外，一些benchmark的使用方法也值得摘要，例如 SWE 这一 bench 经过并发式的使用，就能为 cache 优化、负载提供支撑

例如本仓库以前加入了两篇论文来支撑question，但其实那两篇论文与我当时的兴趣方向并不相关:

````
Challenge: Research Intent Is Not Fully Captured by Conventional Paper Metadata

A fundamental challenge in scholarly retrieval is that the conceptual intent of a research work is often not explicitly represented in its conventional metadata. Paper titles, abstracts, and author-provided keywords typically describe the high-level contribution from the perspective of the authors, but may omit the broader system context, practical implications, and reusable artifacts that define the actual scope and impact of the work.

For example, when searching for research on agent execution traces, many retrieved papers focus on trace visualization, debugging, or context compression. Although these works share similar terminology, they do not necessarily address the intended research question: how execution histories can be represented, organized, and reused as system-level knowledge. The mismatch occurs because the underlying intent of a research contribution may be reflected not only in its textual description, but also in associated resources, such as datasets, benchmarks, code repositories, experimental pipelines, and the relationships among them.

Existing scholarly search systems primarily index and rank papers based on document-level signals. However, research contributions increasingly extend beyond papers themselves into a broader ecosystem of artifacts. A dataset may reveal the actual task formulation, a code repository may expose the implemented system abstraction, and experimental resources may clarify the intended application scenarios. Without modeling these artifacts and their relationships, retrieval systems may identify papers with similar terminology while missing works that share the same underlying research intent.
````

````
结合原文（54 页版 §1、§2、§7、§8）看，AgenticScholar 的叙事是一条非常典型的、而且执行得很工
   整的 SIGMOD 系统论文故事线，可以拆成七幕：                                                 
                                                                                              
   1. 开篇升华：把领域问题改写成"数据管理问题"                                                
   引言第一句就定调："The exponential growth of scholarly corpora represents one of today's   
   most complex data management challenges"（p. 2）。注意它不说"检索难"或"LLM 应用"，而是强调 
   语料是多模态、半结构化的"ecosystem"，并挂上"democratizing knowledge and promoting          
   evidence-based research"的价值。这一步的作用是把论文的身份从 NLP/应用论文锚定成数据库论文。
                                                                                              
   2. 用一个具体例子当叙事主线                                                                
   Fig. 1 的"vector search 渐进式会话"是全文的叙事脊柱：一个研究者从开放问题 "How has research
   on vector search been evolving…" 出发，沿 Q1（趋势）→Q2（检索）→Q3（里程碑）→Q4（性能比较与
   局限）→Q5（研究想法）逐步深入，并分叉出 Intent 1/2/3 三条路径。这个例子不是装饰——后面所有东
   西都从它推导出来。                                                                         
                                                                                              
   3. 从例子归纳"查询特征"，再推出"现有系统做不到"                                            
   引言从 Fig. 1 直接观察到学术查询的四条性质：start open-ended and evolve diverse intents /  
   require multi-step semantic reasoning / depend on multi-modal evidence / require           
   context-aware knowledge generation。然后一句话完成转折："they cannot autonomously          
   orchestrate a complete analytical pipeline – from trend analysis (Q1) through … research   
   idea exploration (Q5)"（p. 2）。§2.2 的 Table 1（8 个系统 × 三层查询的能力矩阵）把这个 gap 
   物化成一张表——它是全文动机的"反派"。                                                       
                                                                                              
   4. 四个 Challenge，与架构一一对应                                                          
   这是全文最工整的叙事装置：Challenge 1（语义表示）→ 知识表示层（§3）；Challenge 2（复杂流水 
   线规划）→ LLM 混合规划层（§4）；Challenge 3（通用性与可扩展性）→ 统一执行层                
   （§5）；Challenge 4（可解释可追溯）→ 由执行层物化计划和 lineage 顺带解决。贡献列表里每一条 
   都写着 "To address Challenge X"——读者几乎不需要自己建立问题和方案的映射。                  
                                                                                              
   5. DBMS 类比作为解释框架                                                                   
   全文反复把系统部件对应到数据库概念：传统优化器"built for fixed relational schemas"不够用   
   （Challenge 2）；可解释性要 "materialized and inspectable, akin to query execution plans in
   DBMSs"（Challenge 4）；算子集 + DAG 执行 + result cache 就是执行引擎。这个类比让 SIGMOD 读 
   者用熟悉的心智模型接收一个 LLM 系统。                                                      
                                                                                              
   6. 三层查询分类法做设计与评测的共同骨架                                                    
   Fig. 3 的 Tier-1 检索 / Tier-2 抽取与综合（单篇/多篇）/ Tier-3 发现与生成，在 §2.1 定义后  
   ，§5 的算子设计从它出发，§6 的实验也按它分三套评测，最后 case study 再重演一遍 Fig. 1 的渐 
   进会话。故事的结构和评测的结构是同一个结构。                                               
                                                                                              
   7. 收尾：Lessons 示人以诚 + "first system" 优先权声明                                      
   §7 罕见地承认构建质量是软肋（"prone to occasional errors in entity extraction, relation    
   detection… that can propagate through downstream components"，p. 23）、多模态数值抽取不可靠
   、成本权衡；§8 结论则以 "To the best of our knowledge and evaluation, AgenticScholar is the
   first system to execute agentic reasoning over multi-modal scholarly data through DAG-based
   plans"（p. 24）收束，并自限评测只覆盖 CS 部分领域。                                        
                                                                                              
   一句话概括它的 storytelling：用一个研究者的渐进式探索会话作为叙事脊柱，把"学术查询"重述为" 
   查询处理问题"，用四 Challenge ↔ 三层架构的一一映射制造工整感，再用三层查询分类法把动机、设 
   计和评测缝成同一副骨架——叙事完成度很高。需要留意的是（重读笔记也指出），这个故事的说服力大 
   量依赖 Table 1 这类作者自标的能力矩阵和"first system"这类自我声明，叙事上的闭环不等于证据上
   的闭环。
````


### 12. 以研究行动为主线的叙事修订（2026-09-10）

#### 调整原因与当前立意

上一版过早以 community 和摘要检索为中心，将 P4A 收窄成一种集合检索方案。用户希望继续强调方便 Agent 发现和使用研究资源，以研究过程中的行动组织故事，并在 Introduction 中总论式介绍贡献。

当前候选主旨：将已发表论文及其关联材料中的分散信息，加工和组织为可复用的研究知识，支持 Agent 从研究需求出发发现材料、判断适用性、选择资源并准备后续使用。

Gap 不应仅表述为 PDF 解析或文本获取的重复。需要研究的是理解资源背景、用途、设置和使用条件等加工结果如何保存并跨任务复用。节省时间、上下文及提高准确性是待验证收益；已公开材料的加工不能恢复未公开的研究过程。

#### 借鉴 storytelling 的方式

借鉴所附 AgenticScholar 骨架中“渐进案例 → 需求特征 → 问题 → 系统回应 → 评测”的对应关系。案例负责展示需求，相关工作比较与实际观察负责证明缺口，实验负责验证设计。不能通过案例直接推断现有系统普遍失败，也不复制能力矩阵中的自我声明、first-system 主张或固定架构。

数据管理定位来自对资源知识的构建、持久化、组织、访问与复用，不依靠额外引入规划器或执行引擎来建立。

#### 贯穿案例（说明性，待真实材料核查）

研究者开发一种提升长上下文指令遵循能力的方法，请 Agent 调研相关工作并准备实验。

| 请求 | Agent 行动 | 希望得到的结果 |
| --- | --- | --- |
| Q1：哪些工作相关，哪些值得优先读？ | 发现、筛选 | 有相关性依据的阅读候选 |
| Q2：这些工作的研究问题和实验条件与我的设想有何区别？ | 理解、判断 | 支持选择的差异说明 |
| Q3：哪些 benchmark 和数据适合检验我的方法，已有研究如何使用它们？ | 寻找资源、判断用途 | 有适用性依据的评测候选 |
| Q4：有哪些实现与评测工具可以采用，使用前需要检查什么？ | 选择、准备使用 | 入口、使用说明与待核查事项 |

案例终点是有依据的选择与使用准备，不承诺自动实验或完整复现。行动可反复发生：Q2 可改变检索方向，Q4 的检查可促使重新选择 Q3 的资源。这些行动不是强制流水线，也不是预设难度递增的 benchmark 层级。

#### 从案例到挑战与系统责任

案例提出三个需求特征：相关性依赖使用者的研究需求；判断依据跨越论文与外部材料；部分理解具有跨问题、跨任务复用的机会。应区分作者原始用途、后续研究实际用法和针对新需求的适用性判断；后者不能作为无条件事实提前写入资源记录。

| 挑战 | 系统责任 |
| --- | --- |
| 获得支撑研究选择的信息 | 从论文及关联材料构建有来源的资源知识 |
| 支持不同研究需求 | 组织、检索和呈现背景、用途及差异 |
| 支持已有理解的后续使用 | 保留来源、适用条件与材料状态，支持返回原材料检查 |

这些责任可以跨模块实现。Community 在设计章节中作为组织方式讨论，不在 Introduction 中先行定义。具体检测、摘要及访问机制仍待设计。

#### Introduction 与贡献的安排

当前顺序：研究 Agent 的需求 → Q1–Q4 案例 → 需求特征及 gap → 三项系统责任 → P4A 总体定位 → 贡献方向与评测。

贡献暂以三个位置组织：面向研究行动的资源知识组织、资源库构建与访问机制、面向发现与使用的系统评价。初稿采用研究议程和拟开展工作的表述；后续必须用具体设计及实证结果补实，不能当作已成立的新颖性或已完成的贡献。

评测可覆盖发现筛选、适用性判断与资源选择、使用准备及整体成本。任务与质量标准应独立于系统输出，并比较同等材料访问条件下的合理工具组合。贯穿案例展示能力如何连接，不能代替独立评测。Community 检测及摘要等机制的分析可在这一总体框架下开展。

本次同步修订 `paper/introduction.zh.md` 与 `paper/main.tex`，编译预览；不启动实现或实验。下一步需要选定并核查真实案例，明确相邻方法留下的具体缺口，再完善机制与贡献。


### 13. 评测方案讨论：构建质量与 Agent 支持能力（2026-09-10）

本节记录候选评测结构，不确定 benchmark、任务规模、评分阈值或实施计划。总体思路是：**构建质量和支撑 Agent 的能力分开设计与评价，再通过端到端实验连接。** 端到端描述评测范围，LLM-as-Judge 描述评分方式，两者并不互斥。

#### 两类评价与系统边界

| | 构建质量 | Agent 支持能力 |
| --- | --- | --- |
| 对象 | 资源记录、用途说明、摘要和组织结果 | Agent 的发现、判断、选择与使用准备 |
| 输入 | 固定版本的论文及关联材料 | 研究需求、资源库与访问工具 |
| 核心问题 | 知识是否正确、充分、有依据 | 是否帮助完成任务并作出合理选择 |
| 主要依据 | 独立事实标注、原始证据、人工审查 | 任务条件、交付成果、有限执行结果 |
| 成本 | 构建、检查与更新 | 查询、阅读、推理与执行 |

资源库正确不保证对任务有用；Agent 也可能重新读取原文修复坏记录，使任务成功掩盖构建错误。因此，不能仅依赖端到端分数判断建库质量。

分开评价仍需共享明确的信息范围：正确性由材料证据决定，覆盖哪些信息由目标研究行动决定，实际价值由下游任务验证。候选系统边界是构建部分交付固定版本的资源库，访问部分支持检索、查看记录、定位来源与继续使用。固定库可比较访问方式，固定访问方式可比较构建方法；查询时补全尚未确定，初期可先使用固定快照。

#### 三组候选实验

1. **构建质量实验：** 不依赖下游 Agent，检查资源身份、用途、版本、适用条件、摘要事实与来源的一致性，评价重要信息遗漏和不确定性处理，并记录构建成本。区分作者声称、外部观察、执行成功与复现。
2. **Agent 支持能力实验：** 固定下游 Agent，在明确的资源库与访问配置下评价各项行动；比较访问机制时固定库，比较知识构建时固定访问机制。
3. **端到端实验：** 从研究需求到资源选择和使用准备，比较完整 P4A 与具有同等原始材料访问能力的合理基线，衡量结果及总成本。任务成功不等于论文完整复现。

Community 摘要可单独检查来源支持、成员差异和遗漏；暂不要求唯一正确的 community 划分，组织方式的实用性可通过替换机制后的下游表现检验。

#### 任务与评分候选

| 行动 | 示例 | 候选评价 |
| --- | --- | --- |
| 发现 | 为明确研究需求寻找论文和资源 | Precision@k、NDCG@k；标注充分时使用 Recall@k |
| 判断 | 比较候选与当前研究问题、实验条件的匹配 | 条件判断正确率、理由的证据支持、未知状态处理 |
| 选择 | 选择适合的 benchmark、数据和工具 | 必要条件满足、关键条件违反、重要需求遗漏 |
| 使用准备 | 提供入口、版本及后续步骤 | 材料正确性、必要说明覆盖、有限执行检查 |

端到端任务可要求提交资源清单、选择理由、来源和待核查事项，不强制执行 Q1–Q4 的固定路径。答案允许多个正确方案，金标准宜由需求条件、已核查事实与可接受方案组成，不以一篇参考报告作为唯一答案。

同时报告整体通过率和分项结果，预先约定哪些关键错误导致任务不通过，避免其他分数抵消错误选择。加入无完全合适资源或证据不足的任务。分项诊断可提供统一、核查过的上游输入，以区分检索遗漏和理解错误。

开放检索难以穷尽正确答案；可先在固定语料中评测，或汇集多个系统的候选进行独立判断，不能直接将未经标注的新结果判错。

#### 有限的使用验证

可在适合执行的任务子集中，让固定下游 Agent 接收各系统交付的材料，完成获取指定数据版本、读取样例、加载正确划分、调用评测工具或小规模评测。评分依据文件、数值或程序检查。

这检验交付是否支持继续工作，不宣称完整实验复现。若下游 Agent 可重新搜索并修正材料，需要记录额外工作及成本，避免交付缺陷被补救过程隐藏。

#### LLM-as-Judge 与人工、程序的分工

程序适合核对可确定的身份、文件、格式及运行结果；人工和模型裁判可评价语义适用性、证据支持、需求覆盖和使用说明。模型评分不以笼统的“专业性／完整性／实用性 1–10 分”作为唯一依据。

Judge 输入宜包含任务、候选输出、独立准备的原始证据及逐项 rubric，返回满足／不满足／证据不足等判断与对应依据。不能仅依据 P4A 自己生成的摘要审查 P4A。回答正确性、引用支持和需求覆盖分别评价。

用独立人工样本校准并审核 Judge，区分开发校准集和最终审核集，特别检查错误结论被判为正确的情况，以及不同任务和系统上的偏差。匿名化系统来源并固定 Judge 版本与提示；两两比较应交换顺序、允许平局。多模型投票不能替代独立校准。

参考：[ALCE](https://github.com/princeton-nlp/ALCE) 将回答正确性与引用质量分开；[Judging LLM-as-a-Judge](https://arxiv.org/abs/2306.05685) 讨论位置、篇幅和自偏好等偏差。参考这些原则不意味着其评分器已适用于 P4A，仍需本任务上的验证。

#### 对照、成本与独立性

主对照固定研究 Agent，保证原始材料访问条件可比，比较有无 P4A 知识与访问能力。候选包括可搜索和阅读原文、查看资源的工具组合，直接材料检索，逐资源摘要索引，以及后续核查选定的相邻方法。组件实验区分提前加工、摘要、组织和访问机制的作用。

总成本包括建库、维护与各次任务运行成本。报告不同复用次数下的质量、时间和 token 消耗，不将建库投入隐藏在任务外。测试问题、答案与评分材料应与构建过程隔离；构建可以访问约定语料，不应提前获得测试需求。

[AstaBench](https://github.com/allenai/asta-bench) 可作为文献与执行任务采用各自数据和评分器的组织参照，不要求复制完整科学研究流程。

#### 待商定

建议优先讨论带条件的资源发现、benchmark 适用性选择和少量可执行使用准备任务。尚需商定语料与版本、独立需求来源、信息覆盖范围、标注与争议处理、评分阈值、模型和预算、重复运行及统计报告方式，再决定实施。当前仅记录方案。
