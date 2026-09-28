# 手动进展汇总

## 2026/09/27 之前

已有进度：构建 bert、graphrag、rag 三篇作为example 进入 graph 中，结论是当前的数据模型的确能够满足网络构建的需求。

但是问题是 Agent 凭借记忆构建的示例数据无法满足这些情况：

1、示例数据拼接模型预训练的记忆生成，因此无法检验论文理解图谱是否能够帮助 Agent 更好地获取有依据地论文理解和以前的经验
2、无法体现真实数据的复杂性，例如实体消歧
3、直接生成了最终可入库的文件，但是真实工作流中，抽取数据到入库，还有很多复杂的步骤准备

## 2026/09/27

准备了6篇真实的论文，data/raw/e08-paper-knowledge，来进行模拟真实数据抽取、入库

但是这个抽取工作目前不进入我们论文的叙事，因此我们可以比较“方便”而不体系地推进，例如先准备好数据，然后做抽取套件，之后方案固定了，在真实地规范好一个 agent 使用我们设计方案时如何更新图谱

更新了 data model 为 Paper、Method、MethodConcept、Resource、Metric 加上了 aliases property，帮助新数据入库时，agent 进行检索兜底，获取到相似的 node，然后将数据补充或更新到图谱中已有的 node 中，防止新造实体，充当实体消歧，检索兜底的作用。alias 字段进行验证后能够有效的进行检索和兜底保障

### 数据抽取准备

- Resource 改用次级 Label（Dataset、Benchmark、Model、CodeRepo、Tool），不再为不同种类设专属属性。id 改为不带语义、由工具分配。样例数据按此重新入库。
- 新建 pi-configs/paper-extract/：禁用全部内置工具，不加载 AGENTS.md 和 skills；配套 system prompt 草稿与抽取指南 GUIDE_ZH.md。
- 种子概念入图 data/raw/e08-paper-knowledge/seeds/：共 79 个节点，内容用英文；aliases 只收同义称呼，description 不写经验判断，事实按原始出处核对并记录 sources/verified。修正了两处：MultiHop-RAG 的时间范围，以及 Electricity 通用版本的来源。

### 数据模型演进

- 新增：
  - Task，以及 ADDRESSES、ON_TASK、FOR_TASK；
  - Issue，以及 RAISES、RESPONDS_TO {stance}，用来承载论文之间有争议的问题；
  - Observation，以及 OBSERVES、CHECKS {verdict}，把第一手检查与论文声明分开；
  - 可选的 note，只放使用提醒；
  - Claim ABOUT 的终点扩展到 MethodConcept、Task、Metric。
- 删除：Condition 和 ContentUnit。实验设置并入 Experiment 的 description，表和图直接用块级 anchor 定位。
- 现在共 13 类节点，模型暂时冻结；新需求等 DLinear、PatchTST 抽取后再定。
- Resource:Model 包含 API 模型；检索索引加入 Task、Issue 和 note。

### 基础设施

- 新增 infra/neo4j-e08/（端口 7688/7475），与样例库隔离。

## 2026/09/28

### 种子概念重新入图

- id 由全局分配器按“前缀 + 序号”分配（如 task_0001）；按“主 Label + name”判断节点是否已存在，已存在就跳过。
- 重跑时全部跳过，id 保持不变。
- 语义检索支持：用 Qwen3-Embedding-8B（vLLM，部署在 192.168.163.112:8002，4096 维）给节点算向量，并建了 entity_vectors 和 statement_vectors 两个向量索引。
  - sync_embeddings() 按“模型名 + 文本”的哈希只补算缺失或过期的向量，写入图谱后调用一次即可。

### 查询算子

- `find_entities(mention, description, entity_type)`：
  - Stage 1 标识解析：原样匹配和去标点后匹配，命中的固定置顶，不参与排序；
  - Stage 2 三路召回：名称 BM25（带前缀和模糊匹配）、定义 BM25、语义向量，按 RRF（k = 10）融合；
  - 返回前 5 个候选，附各通道的证据、定义、note 和一跳邻接关系，不给置信度。
- `find_statements(text, description, kind)`：在 ClaimConcept、Issue、Claim 上做两路召回并融合。Claim 只查不复用，结果附所属论文。用临时节点做冒烟测试通过。
- 索引调整：
  - 定义和陈述两个全文索引改用 english 分词，名称索引保留默认分词；
  - note 不进索引也不进向量，只随候选返回；
  - Issue 的向量改为用 text + description 计算；
  - ensure_schema() 发现索引的 Label、字段或分词方式与声明不一致时，自动重建。
- 示例效果：
  - ETTh1 能带出 ETT；
  - RevIN 加一句 description 后能命中 Instance normalization；
  - 图里没有的 PatchTST，前 5 名都是它可能要连边的相关概念。

### 基础设施

- 部署 Qwen3-Embedding-8B
- neo4j 索引完善

### 论文草稿

- codex 撰写了一版论文全文雏形已提交；核心机制与评测方案待细化，下一步审阅第 2、4 节
  - 本次因 find_entities 与命题检索的区分，重新审视了数据模型的设计依据及其在研究中的地位。讨论明确：当前模型是面向 Agent 长期研究活动的 semantic data model，其设计由 **研究 intent 中的知识复用需求** ，以及 **科学知识表示的既有研究** 共同支撑，可以构成研究贡献的一部分。
  - 为固定这些理解、锚定研究主线，提前将 paper/introduction.zh.md 扩展为全文草稿，串联“研究活动 → 复用挑战 → 模型设计 → 操作机制 → 效果评价”。已保留原有引言并提交 29914b0。这版草稿用于检查研究叙事是否连贯；核心算法、命题归并与知识维护机制、评测协议仍待细化。下一步优先审阅第 2、4 节，明确哪些设计承担核心贡献、需要什么证据支持

## 正在进行的工作

## 备忘

例如，Agent 阅读两篇论文后判断：

两篇虽然使用同名数据集，但测试切分和候选集合不同，现有结果不足以直接比较方法优劣。

这是很有价值的阅读经验，可能没有任何一篇论文直接说过，也不属于运行或复现产生的 Observation。当前模型对它的容纳还不完全一致。

如果继续用 Claim 承接，我建议明确允许两种来源：整理作者的主张，以及 Agent 基于材料形成的判断。后者要标明是 Agent 归纳，保留双方依据，不能通过 Paper—HAS_CLAIM 误归给某一篇论文；比较实验时，也可以考虑允许 Claim—ABOUT→Experiment。先把这个语义说清楚，不必马上增加节点类型。

另外，两句表述可以稍微放宽：

“只能依靠 description 判断是否可比”应改成“先读 description，必要时沿 anchor 核对”。概括难免遗漏细节。

“具体数值不写进图”适合作为不复制结果表的原则；如果幅度或阈值本身影响结论含义，Claim 中仍应允许保留必要数值。

我认同这次调整的理由，也认为它更贴近你要保存的阅读经验。接下来最关键的是让阅读后形成的新判断有明确的位置，这样模型才能完整表达经验的积累与修订。

建议进度条目：审阅数据模型的新修改，讨论了删除 Condition / ContentUnit、收紧 note、扩展 ABOUT 和引入 Observation 的作用。待明确作者主张与 Agent 归纳判断的归属及证据表达，下一步补齐 Claim 的语义边界。

评测 basline 方案：论文切块的 rag，还有 markdown 文档上的 grep 或者全文索引检索