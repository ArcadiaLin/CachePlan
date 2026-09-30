# 代表性 Intent 分解：统一检索面上的数据模型与组合操作

> **目的：** 从研究任务所需的信息出发，共同设计对象划分、检索接口和操作表达，使外部 Agent 能够检索、关联和理解积累的论文衍生知识。
>
> **本稿状态：** 六类 intent 有外部任务依据；三类对象、统一字段和操作契约是本轮提出的 v2 方案，不是已实现或已验证的系统。文中任务为来源需求的具体化，尚未绑定最终语料与 benchmark。

设计方法与责任边界见 [研究顶层设计](research_design_v2.md)。本文先列信息需求，再给出可用于展开任务的模型候选，随后通过完整的数据流检查模型和操作是否配合。**相对稳定的是 intent 与必要信息；节点粒度、类别和操作组合可以一起修改。**

## 1. 代表性 Intent 与相对稳定的信息需求

### 1.1 任务来源及采用范围

| Intent | 来源直接支持的任务 | 本文采用的范围 |
| --- | --- | --- |
| **I1 发现适合当前需求的工作与方法** | PaperFindingBench：根据包含内容和元数据条件的自然语言描述找论文集合。[S1] | 将候选论文进一步联系到方法及其前提；资源适用性判断由 Agent 完成 |
| **I2 理解方法的机制、条件与细节** | QASPER：NLP 从业者提出全文信息需求，回答者给出答案及证据。[S2] | 取得具体问题所需的知识和材料；允许长尾信息仍在原文中 |
| **I3 组织实验结果并判断比较口径** | TDMS-IE：抽取任务、数据集、指标和分数以构建 leaderboard。[S3] | 结果整理有直接依据；条件对照和可比性判断是本文扩展 |
| **I4 综合同一问题下的路线与发现** | ScholarQA-CS：多论文综合回答；ArxivDIGESTables：生成文献比较表。[S4][S5] | 组织跨论文信息与引用，不把发现原创研究问题作为数据库操作 |
| **I5 核查主张的依据与成立范围** | QASPER 的证据问答；SciFact 的支持/反驳证据及理由识别。[S2][S6] | SciFact 仅支撑任务形式，其生物医学内容不能直接证明 CS 场景覆盖度 |
| **I6 找到资源并判断能否作为实验起点** | CORE-Bench 的代码与数据执行任务；PaperBench 对代码、执行和结果匹配的不同要求。[S7][S8] | 采用资源、配置和核验信息需求；资源发现是本文补充的前置步骤，实际执行交给外部 Agent |

这六类覆盖候选集合、细节答案、实验对照、文献综合、证据判断和资源准备六种信息产物。它们可以组合：方法选择可以包含 I1–I3，解释异常结果可以调用 I3、I5。这里主张**有任务依据的代表性**，不主张频率代表性或对全部研究行为的完备覆盖。来源证明需求存在，不证明本文模型或混合检索优越。

### 1.2 先确定信息，再决定放在哪种节点中

| Intent | 完成任务必须取得的信息 | 必须保留的区别 |
| --- | --- | --- |
| I1 | 工作/方法候选、用途、前提、来源 | 相关不等于适用；方法不等于同名代码或模型 |
| I2 | 机制、数据与资源要求、设置、原文位置 | 对象定义与某次具体使用不同；未记录不等于不存在 |
| I3 | 被测对象、数据、指标、结果、实验条件 | 方法与实验、数值与条件一一对应到实际记录；同数据集不等于同口径 |
| I4 | 共同问题、各项回答、方法区别、具体发现和引用 | 同一问题可有不同回答；共同认识不能覆盖来源差异 |
| I5 | 待核查说法、相关主张、支持/限定/反驳材料 | 主题相关不等于同一命题；已存判断不等于本次验证 |
| I6 | 资源身份、版本、配置、论文声明、检查记录 | 论文声称公开、找到实现、成功运行、结果复现分别记录 |

这些信息可以保存为属性、独立内容单元或带依据的关系。例如，实验结果可以先作为一份实验报告中的内容，也可以在需要独立访问时拆成结果记录；**信息要求不随这种拆分自动改变，但访问路径和操作粒度会改变。**

## 2. v2 候选模型：按可共享的检索契约组织对象

### 2.1 三类对象，一套公共字段

本稿提出 `Entity / Concept / Content` 三类候选。分类依据是身份与语义作用，不沿用 v1 每个业务类型一个独立结构的前提。

| 类别 family | 回答什么问题 | 候选 kind | 同一性与来源规则 |
| --- | --- | --- | --- |
| **Entity** | 这是哪个可引用、获取或使用的对象？ | `paper`、`dataset`、`code`、`model`、`benchmark`、`tool` | 以对象指称为核心；标题、名称和 URL 命中只是线索，版本与身份由显式记录和外部确认确定 |
| **Concept** | 这是哪个定义、研究对象或待回答的问题？ | `method`、`method_family`、`task`、`metric`、`issue`、`proposition` | 以定义、含义与适用范围为核心；共同问题与共同命题通过 kind 和关系区别 |
| **Content** | 某个来源具体说了什么、报告了什么或观察了什么？ | `claim`、`experiment`、`resource_use`、`observation`、`contribution` | 以来源绑定的记录为核心；内容相近不自动合并不同来源或不同次检查 |

**Paper 与 Dataset、Code、Model 使用相同 Entity 结构。** Paper 的节点表达书目身份及可发现性，论文中的主张、实验等信息由相关 Content 承载，方法等对象由 Concept 表达。一篇论文的信息因此分布在多个对象上，不再由 Paper 节点类型包办。

将 Issue 与共同命题归入 Concept，是因为它们可以共用名称/描述检索、定义确认与语义关系访问；跨论文聚合由关系表达。本轮没有为它们另设检索家族的必要。问题不等于命题，统一结构不取消这一区别。

Content 也不叫“论文内部证据单元”：Observation 可以来自代码检查或新实验，Claim 只是有来源的说法，并不自动具有证据效力。证据作用需要通过来源、关系和核查说明。

### 2.2 检索面与描述面

所有类别采用同一逻辑封装，**至少同类、并尽量跨类共享检索字段和索引方式**：

```text
KnowledgeObject = {
  id, revision, family, kind,
  name, aliases, description,
  metadata,
  sources
}
```

| 字段 | 统一含义 | 使用方式 |
| --- | --- | --- |
| `id`, `revision` | 稳定对象标识与记录修订号 | 精确取得记录、关联和追踪；修订号不是论文/模型的版本名 |
| `family`, `kind` | 对象家族与语义子类 | 确定性范围约束，不承载领域推理 |
| `name` | 对象称呼或内容单元的短标题 | 同一名称全文索引；不是唯一身份键 |
| `aliases` | 已确认的其他称呼；没有时为空列表 | 同一别名匹配规则；不能将临时扩展词当作别名写入 |
| `description` | 供发现和区分该对象的独立描述 | 所有 kind 使用同一全文检索与语义编码入口 |
| `metadata` | 允许异构的描述性属性或完整内容 | 返回给 Agent 阅读、解释与判断；不隐式参与数据库筛选 |
| `sources` | 统一格式的来源与材料定位信息 | 系统负责定位与读取，Agent 判断其支持什么 |

`id/revision/family/kind/name/description` 使用声明过的标量类型，`aliases` 为字符串列表，`metadata` 为可异构的结构值，`sources` 为 SourceRef 列表。一个对象在本轮候选模型中只有一个 family 和一个 kind；跨角色对象可以用关系连接，不能让标签顺序决定类型。缺失名称用空串、无别名用空列表；缺失 description 显式标记为不可执行描述检索，不将空文本当作正常向量。

**检索面包括**统一的索引字段、类型/标识约束和下节的关系契约；**描述面是**任务解释所需的异构内容。两面按操作职责划分，允许重叠：Agent 也会阅读 `description`，系统也会存取 `metadata`，但系统不解释其领域含义。

若某个 metadata 字段将来需要数据库直接过滤、排序或关联，应明确提升为有类型和语义的检索字段或关系，并同时修改查询契约。不能保持它异构不透明，却在查询中偷偷使用 `WHERE metadata.split = ...`。

**description 的共同职责：** 描述对象是什么、处理什么问题，以及发现和区分它所需的关键特征。Paper 可以直接采用摘要作为 description；Dataset、Code、Model 使用用途与内容介绍，无需改名为 abstract。原始摘要或 README 可在 metadata/来源中保留。若需生成检索描述，由外部构建过程完成并记录依据；中间件不调用 Agent 改写。描述缺失时标记通道不可用，不凭空补写。

Content 的 description 应表达具体发现与条件，不能仅为“实验 1”；Concept 应保留定义与范围。文本职责一致，不表示文本长度、风格和相关性分布天然一致，后续仍要评价摘要直用与规范化描述的效果。

### 2.3 异构 metadata 不妨碍公共检索

以下只示意封装，不预设所有对象必须包含这些描述字段：

```text
Entity(kind=paper):
  name = 论文标题
  description = 摘要
  metadata = {authors, venue, doi, publication_version, ...}

Entity(kind=dataset):
  name = 数据集名称
  description = 数据内容、用途与主要特征
  metadata = {splits, license, release, preprocessing, ...}

Concept(kind=method):
  name = 方法名称
  description = 机制、用途和定义范围
  metadata = {components, assumptions, implementation_notes, ...}

Content(kind=experiment):
  name = 本次实验的短标题
  description = 实验目的、关键设置和主要发现
  metadata = {settings, reported_results, limitations, ...}
```

`metadata.reported_results` 可以是文字、表格摘录或有局部结构的内容；它不是一个已统一的数值查询接口。只要任务需要比较，Agent 就必须识别实际对象、条件、指标与数值的对应关系。

### 2.4 关系、来源和记录粒度

统一节点字段之外，还需要显式对应关系。暂用同一 Link 结构，关系类别的语义分别定义：

```text
Link = {id, from_id, to_id, relation, role, description, metadata, sources}
SourceRef = {entity_id, entity_revision, material_ref, locator}
```

`relation/role/方向` 是系统可直接消费的结构字段；关系上的描述和异构细节交给 Agent。`SourceRef` 中的 `material_ref` 指向不可变材料副本或带内容版本的读取句柄，`locator` 定位其内部位置；仅有书目记录修订号不够固定原文。读不到对应材料时返回状态，不能将失效定位默认为当前版本内容。检查日志可以由 `Entity(kind=artifact)` 表示；因此来源不被限制为论文。

| relation 与方向 | 端点约定 | 表达的事实或已保存判断 |
| --- | --- | --- |
| `FROM`：内容 → 来源对象 | Content → Entity | 该内容记录来自哪个材料或检查产物 |
| `ABOUT`：内容 → 被讨论对象 | Content → Entity/Concept | 该内容讨论什么，不自动表示支持 |
| `ADDRESSES`：方法 → 任务 | Concept(method) → Concept(task) | 方法针对的任务 |
| `EVALUATES`：实验 → 被测对象 | Content(experiment) → Concept(method)/Entity(model) | `role` 区分 target、baseline 等参与角色 |
| `USES`：实验 → 资源 | Content(experiment) → Entity | `role` 区分 training_data、evaluation_data、tooling 等 |
| `MEASURED_BY`：实验 → 指标 | Content(experiment) → Concept(metric) | 实验采用的指标，不直接表示每个数值的行列对应 |
| `EXPRESSES`：具体主张 → 共同命题 | Content(claim) → Concept(proposition) | 经外部确认的同一命题表达 |
| `RESPONDS_TO`：具体主张 → 问题 | Content(claim) → Concept(issue) | 对共同问题的回答；立场与条件在描述面 |
| `SUPPORTED_BY`：主张 → 实验/观察 | Content(claim) → Content(experiment/observation) | 已记录的依据关系，仍需核查支持范围 |
| `SUPPORTS / CHALLENGES / QUALIFIES`：作用方 → 被作用方 | Content(claim) → Content(claim) | 有方向的支持、质疑或限定判断 |
| `IMPLEMENTS`：实现资源 → 方法 | Entity(code/model) → Concept(method) | 有依据的实现对应，不由共同论文来源推出 |
| `OBSERVES`：检查记录 → 被检查对象 | Content(observation) → Entity | 具体检查目标，版本和时间保留在描述面 |
| `CHECKS`：检查记录 → 被核查说法 | Content(observation) → Content | 检查针对哪一条声明，判断结果在描述面 |

这是支持本轮任务的候选关系集合。对称关系、层级或方法组成关系可按任务增加，不把所有联系压成没有语义的“相关”。单条关系只说明它声明的事实，不允许把一个实验的多个方法、数据、指标边自动展开成数值组合。

来源与修订有共同约束：内容记录必须有来源或明确标记来源缺失；跨来源相似记录保留各自身份；检索描述改变时更新其派生索引。当前任务在固定图快照中读一个对象的一项选定修订；历史保存与事务协议另行设计，不将快照约定冒充已实现的版本系统。

## 3. 共同操作：数据系统消费检索面，外部 Agent 消费描述面

### 3.1 同一混合检索，按 family/kind 限定候选

```text
Retrieve(q, family, kinds, purpose, scope, k) -> RankedCandidates
```

- `q = {mention?, description}`：可选称呼与需求/定义文本；至少一项非空。
- `purpose = lookup | relevant`：查找所指对象/概念，或发现对需求有帮助的记录。
- `scope`：固定图快照和允许的记录范围；`k` 为返回深度。
- 返回对象引用、类型、公共描述、可读取的 metadata/sources，以及逐通道召回记录。

**Entity、Concept、Content 不使用不同的字段拼接方案。** 同一模型从所有对象的 `description` 编码向量，名称和别名走同一词面通道；共享分词、索引配置及融合规则。family/kind 约束候选集合，不触发按 Paper、Dataset、Claim 分别编写的检索器。物理上可以按 family 分区，但必须保持字段与构建规则一致。跨多个 family 查询时分别保留候选及预算，若要生成一个全局排序，需明确融合规则，不假定不同分区的原始分数天然可比。

```text
C = scope 中满足 family/kinds 的记录
L_name = 对 q.mention（若有）在 name + aliases 上全文召回 b 条
L_text = 对 q.description（若有）在 description 上全文召回 b 条
L_vec  = 对 q.description（仅有 mention 时用 mention）编码，召回 b 条
exact  = lookup 且有 mention 时，按统一名称/别名匹配规则取候选

按 ID 合并各路；按 RRF(x) = Σ_c 1/(κ + rank_c(x)) 融合
若采用 exact 优先策略，对所有 family 使用同一声明规则
同分按 ID 排序，返回前 k 条，并保留各路名次、匹配方式和分数
```

RRF 的 c 仅指非空的名称、描述全文与向量排行，名次从 1 开始、κ 为正数；exact 是独立的匹配标记，不重复计入融合分数。检索 trace 记录“为何召回”，sources 记录“内容来自哪里”，二者不能互相替代。

所有通道在逻辑上使用同一 C；物理实现若先近似召回再过滤，需返回实际候选数与截断信息，不能保证固定倍数超取等于范围内 top-k。RRF 是已有方法 [S9]，本研究不将其作为新贡献。

`lookup` 与 `relevant` 的查询指令可以不同，但在同一 purpose 内跨 kind 共享。相同 pipeline 不代表相关性判断相同：Entity 的 lookup 关注同一对象，Concept 关注同一定义或问题，Content 的相关检索关注能否回答问题。相似 Content 不因此被合并。已知有效 ID 时直接 `Get`，不再做近似检索。

这继承 v1 的多路召回、类型约束、名次融合与候选解释，但**不再把 v1 的两个函数及其节点分组作为接口边界**。描述和检索目的改变后需要重建派生索引、重新评价召回；复用机制不等于复用原有检索质量结论。

### 3.2 确定性读取、关联与材料访问

| 操作 | 输入 → 输出 | 契约 |
| --- | --- | --- |
| `Get(refs)` | 对象引用 → 对象记录及缺失状态 | 同时返回检索面、metadata 与 sources；不是语义确认 |
| `Expand(refs, relations, direction, target?, roles?)` | 起点及显式关系约束 → `(seed, link, neighbor)` 行 | 保留起点、方向、角色、关系描述和来源；无边时保留未匹配状态 |
| `ReadEvidence(source_refs)` | 材料位置 → 内容与逐项可用状态 | 只读取，不推断其支持关系；返回材料版本与位置 |
| `Group/Join/Filter/Project` | 已有记录及明确字段条件 → 记录 | 只按 ID、relation、role 等已定义字段运算；不能解释异构 metadata |

`Bundle` 是普通记录变量，可包含某对象的节点、关系和已读材料，不是新的持久节点或隐式语义算子。多个入口命中同一对象时可按 ID 合并候选，但仍保留不同路径、关系和来源。

预算、分页和范围属于共同契约：下文先在限定的 G 上表达完整匹配；实际查询超过预算时返回可续取标记，不能静默丢弃后宣称信息完整。图范围约束必须落实到每一步关联及材料访问，而不仅是最初的检索。

### 3.3 Agent 作为显式运算元素

```text
A[目标 → 输出类型](用户需求 u, 输入变量, 描述信息与证据) -> 结果
```

A 由外部执行者调用，可出现在检索之间，而不必只放在任务首尾。中间件接收由外部确定的查询、参数或更新内容，**不主动调度 A，也不在 Cypher 内调用 A**。

| 用法 | 输出 | 在表达式中的作用 |
| --- | --- | --- |
| 判断 `A_pred` | `T / F / U`（成立/不成立/未知）、理由、引用 | 判断同一性、适用性或可比性，再按结果选取记录 |
| 解释/抽取 `A_map` | 带对象引用和来源的结构化值、未解决项 | 把异构设置、表格或描述转为本次任务需要的临时变量 |
| 决策 `A_policy` | 下一步动作及参数，或停止及原因 | 选择补充检索、读取材料或结束；外部执行者执行所选动作 |

例如，`[(a,b) for a in X for b in Y if A_pred(可比,u,a,b)=T]` 表达带智能判断的配对。实际执行时保存每对的判断记录，将 U 单独保留；不把 U 当成 F，也不把这个运算当成可随意下推到索引的普通等号。

A 的含义由本次任务和所见证据限定。即使输出是“同一”，也不能未经确认就据此做传递闭包或合并节点；`更适合` 也不自动成为稳定全序。对显式数值的普通大小比较可以用普通运算，对条件是否允许这种比较才使用 A。外部运行需记录输入引用、模型/提示配置、输出和依据，便于区分 Agent 判断质量与数据执行正确性。

## 4. 六类 intent 的完整数据流

**共同前提：** 以下使用固定快照 G、允许的材料集合和声明预算 B（检索、关联结果、材料读取与 Agent 调用/配对次数）；数据库中的语义关系均为既有外部判断。`ids(X)` 取得快照内的对象 ID，`neighbors(E)` 取得 Expand 行中的非空邻点；`⊎` 合并记录并保留来源。每个 A 调用显式给出目标和结果，不承担隐藏的数据检索。

名称消歧统一写作：`candidates = Retrieve(..., lookup)`，再由 `A_pred` 判断，得到 `confirmed_refs` 与 `unresolved`。未确认时返回待澄清项，不强行挑选 top-1。以下给定 ID 的输入均假设已确认。

### I1 发现适合需求的工作与方法

> 我只有少量领域标注，想找到可用于专业文献检索的适配方法，并弄清还需要哪些语料、模型或计算资源。

**来源与改写：** [S1] 支撑按需求发现工作；方法级输出和资源前提检查是本文改写。输入为需求 u，输出为候选方法/论文、适用性判断及依据，而非保证穷尽的方法清单。

**必要信息 → 表示：** 论文身份进入 Entity(paper)，方法定义进入 Concept(method)，具体资源前提进入 Content 或对象 metadata；它们共同服务于同一 intent。

```text
plan = A_map[解析任务、资源限制与检索描述](u)
    -> {method_query, paper_query, constraints}
M = Retrieve(plan.method_query, Concept, {method}, relevant, scope, k)
P = Retrieve(plan.paper_query, Entity, {paper}, relevant, scope, k)
C = Expand(ids(P), {FROM}, in, target=Content)
L = Expand(ids(neighbors(C)), {ABOUT}, out, target=Concept(method))
method_refs = ids(M) ∪ ids(neighbors(L))

D = Get(method_refs)
R = Expand(method_refs, {ABOUT,EVALUATES}, in, target=Content)
K = Expand(ids(neighbors(R)), {USES,MEASURED_BY,FROM}, out)
bundles = 按方法 ID 组织 D、R、K，保留两步路径与来源
J = A_pred[逐个判断是否符合资源与任务约束](u, plan.constraints, bundles)

对需要关键证据的 U 项，在 B 内：
    action = A_policy[选择需读取的已有 source_refs 或补检 query](u, bundles, J)
    外部执行 ReadEvidence 或 Retrieve，所得记录加入 bundles
    重新判断受影响项；到达预算或无新材料时停止
返回 {候选及 T/F/U, 理由与引用, 检索范围, 未解决项}
```

**检查要求：** 没有记录额外依赖不等于不需要；从论文进入的 Content 只能提供线索，相关方法需有明确关系或再由 A 确认。直接方法检索与论文路径互补，不要求全部方法都已有完整结构化上下文。

**模式：** 同一 Retrieve 分别作用于 Entity 与 Concept；图扩展连接描述上下文；适用性筛选由外部谓词完成。

### I2 理解机制、条件与论文细节

> 我已经找到方法 M，想知道其“少样本”设置实际用了什么标注、额外语料与教师模型。

**来源与改写：** [S2] 直接支撑带证据的细节问答。输入为已确认的方法引用 m 与问题 u；输出为带来源的细节答案和未知项。

**必要信息 → 表示：** M 的定义用 Concept，某篇论文如何使用 M 用 Content。无需为每种标注数量、预处理步骤建立独立节点；如果这些信息只在 metadata 或原文中，则由 A 消费。

```text
M = Get({m})
R = Expand({m}, {ABOUT,EVALUATES}, in, target=Content)
S = Expand(ids(neighbors(R)), {FROM}, out, target=Entity)
K = Expand(ids(neighbors(R)), {USES,MEASURED_BY}, out)
E = Retrieve({description:u}, Content, {claim,experiment,resource_use},
             relevant, scope=本次允许且与 M 来源有关的记录范围, k)
records = M ⊎ R ⊎ S ⊎ K ⊎ E
needed = A_map[选取回答 u 所需、现有描述尚不足的来源位置](u, records)
materials = ReadEvidence(needed.source_refs，受 B 限制)
answer = A_map[逐项解释细节并对应原文，缺失则写未知](u, records, materials)
返回 {answer.fields, answer.citations, answer.unresolved}
```

检索补充分支中的来源范围由 S 的实体引用与已确认链接构成；若范围为空，允许外部按预算选择扩大范围，但要明确记录。宽范围检索命中后，不能自动宣称内容属于 M。

**检查要求：** 返回细节是否对应正确方法、论文版本与实验？答案是否真正由 metadata 或所读原文支持？统一 description 是检索入口，不保证包含答案。

**模式：** 内容级检索与关系读取结合；同一 Content 检索结构容纳异构论文细节，再由 A_map 转为答案字段。

### I3 组织结果并判断可比性

> 我想比较方法 A、B 在数据集 D 上的结果，确认切分、候选集合和重排序设置是否一致。

**来源与改写：** [S3] 支撑结果整理，条件匹配与可比性为本文扩展。输入已确认的方法 a/b 与数据集 d；输出按实际实验组织的数值、设置、证据和比较判断。

**必要信息 → 表示：** 方法和指标为 Concept，数据集为 Entity，实验报告为 Content；具体分数与设置允许先在 metadata/原文中。这里不沿用“v1 数值只能在锚点中”的限制，也不假定它们已成为数据库可排序字段。

```text
R = 实验关联查询({a,b}, d)                  # §5.3 给出 Cypher
X = Get(R 中 e 列的实验 ID 集合)
K = Expand(ids(X), {USES,MEASURED_BY,FROM}, out)
needed = A_map[选择提取结果所需的材料位置](u, X, K)
materials = ReadEvidence(needed.source_refs，受 B 限制)
V = A_map[解析实际实验结果行及设置，不制造组合](u, R, X, K, materials)
    -> [{experiment_ref, method_ref, dataset_ref, metric,
         value, conditions, source_ref}, ...] + unresolved
Pairs = V 中 method_ref=a 的记录与 method_ref=b 的记录的配对集合
J = A_pred[每对是否满足用户要求的比较口径](u, Pairs)
对 J=T 且数值与指标方向明确的记录执行普通数值比较；超出配对预算的记录为未判定
返回 {V, 每对的 T/F/U 与理由, 可比较结果, 未解决项}
```

**检查要求：** 同一实验中的多个方法、数据、指标边不提供分数的笛卡尔积。A_map 必须保留实际表格行列对应；共享数据集引用也不足以确认版本、切分一致。值可读但指标含义不明时仍不能比较。

**模式：** 确定的结构 Join 与 Agent 配对谓词组合。若将来需要大量数据库内数值操作，可将结果拆为 Content(result) 或提升统一结果字段，届时连同查询表达一起修改。

### I4 综合问题下的路线与发现

> 我想知道少量领域标注下的检索适配有哪些路线，它们改变哪些环节、各有哪些发现与局限，并整理为比较表。

**来源与改写：** [S4][S5] 支撑多论文综合和按维度制表。输入研究问题 u 与可选维度；输出带来源和范围的综合结果，不能宣称识别了全部研究空白。

**必要信息 → 表示：** 共同问题是 Concept(issue)，各篇的具体回答是 Content(claim)，方法是 Concept(method)，来源论文为 Entity。Issue 是可选的持久聚合入口，不要求先构造完整语义空间。

```text
I = Retrieve({description:u}, Concept, {issue}, lookup, scope, k)
J = A_pred[是否与 u 是同一问题范围](u, I)
R = Expand(ids(J=T 的 Issue), {RESPONDS_TO}, in, target=Content(claim))
C = Retrieve({description:u}, Content, {claim,experiment}, relevant, scope, k)
records = neighbors(R) ⊎ C
objects = Expand(ids(records), {ABOUT,EVALUATES,USES,MEASURED_BY,FROM}, out)
needed = A_map[确定比较维度与需要核对的位置](u, records, objects)
    -> {dimensions, source_refs}
materials = ReadEvidence(needed.source_refs，受 B 限制)
table = A_map[按维度整理方法、发现、条件和引用，缺项留空并说明](
    u, needed.dimensions, records, objects, materials)
返回 {table, 带引用综合, 覆盖范围, 未解决项}
```

**检查要求：** 同一 issue 下的回答可以相反；同一 proposition 表达的命题则需含义与条件相容。两者共用结构与检索方式，但 A 及关系契约不能混淆其语义。没有聚合节点时，仍通过 Content 检索继续。

**模式：** 对 Concept 和 Content 使用统一检索；按关系聚合来源化记录；最终语义分组由 A_map 完成。

### I5 核查说法的依据、限定和反例

> “困难负样本能改善检索效果”这个说法有什么依据，在哪些条件下成立，是否存在不同发现？

**来源与改写：** [S2][S6] 支撑证据核查形式；本文使用 CS 主张替换 SciFact 的原领域。输入待核查说法 u；输出证据集合与支持范围判断，而不是数据库自动判定真假。

**必要信息 → 表示：** 共同命题为 Concept(proposition)，具体说法和实验/观察为 Content，来源为 Entity；来源不同的相似 Claim 仍分开保留。

```text
P = Retrieve({description:u}, Concept, {proposition}, lookup, scope, k)
J = A_pred[是否为同一命题，且保留相同适用范围](u, P)
C1 = Expand(ids(J=T 的 Proposition), {EXPRESSES}, in, target=Content(claim))
C2 = Retrieve({description:u}, Content, {claim}, relevant, scope, k)
claims = neighbors(C1) ⊎ C2
relations = Expand(ids(claims), {SUPPORTS,CHALLENGES,QUALIFIES}, both,
                   target=Content(claim))
all_claims = claims ⊎ neighbors(relations)
evidence = Expand(ids(all_claims), {SUPPORTED_BY,FROM,ABOUT}, out)
needed = A_map[选择支持、限定与相反发现的核查位置](u, all_claims, relations, evidence)
materials = ReadEvidence(needed.source_refs，受 B 限制)
judgment = A_map[逐项说明支持范围、差异条件与未知](
    u, all_claims, relations, evidence, materials)
返回 {judgment, evidence_refs, 覆盖范围, unresolved}
```

若只有同义陈述而缺少反例覆盖，外部 A_policy 可选择改写为共同问题或反向说法，再调用同一个 Retrieve；这种补查与停止规则受 B 约束并记录。一次低相关性召回失败不是“没有反例”的证据。

**检查要求：** 双向读取只扩大关系发现范围，解释时必须保留真实方向；`SUPPORTED_BY` 是已有判断，仍需核对原文。没有实验边也不排除文字或其他证据支持。

**模式：** 同一检索机制作用于概念和内容；来源及有方向的语义关系支撑核查，而非相似度代替论证。

### I6 准备资源并解释已有核验状态

> 我准备采用方法 M，想找到对应代码和模型、必要配置，并确认已有记录究竟验证到了哪一步。

**来源与改写：** [S7][S8] 支撑资源执行与分级验证要求；资源发现是本文前置扩展。输入已确认的方法 m 或资源称呼及用途 u；输出资源对应、配置依据、验证历史与需重查项。

**必要信息 → 表示：** Paper、Code、Model、Dataset 都进入 Entity；论文声明、使用经验和第一手检查都进入 Content，但 kind 与来源不同。检查时间、目标版本、状态等可保留为异构 metadata，由 A 解释。

```text
M = Get({m})
R1 = Expand({m}, {IMPLEMENTS}, in, target=Entity)
q = A_map[根据 M 与用途组织资源检索描述](u, M)
R2 = Retrieve(q, Entity, {code,model,dataset}, relevant, scope, k)
resources = neighbors(R1) ⊎ R2
J = A_pred[资源是否对应所需方法及用途，需版本信息则保留 U](u, M, resources)
selected = J=T 或需进一步核查的 U 资源
records = Expand(ids(selected), {ABOUT,OBSERVES}, in, target=Content)
checks = Expand(ids(neighbors(records)), {CHECKS,FROM}, out)
needed = A_map[选择配置和核验结论所需材料](u, selected, records, checks)
materials = ReadEvidence(needed.source_refs，受 B 限制)
plan = A_map[区分论文声明、仓库检查、执行、结果匹配及目标版本](
    u, selected, records, checks, materials)
返回 {resources, setup_facts, verification_history, needs_recheck}
```

给定资源称呼时，先对 Entity 执行 lookup 并确认，跳过方法入口。对资源发现候选，若没有明确实现关系或材料依据，不能仅凭名称将它标成方法实现。

**检查要求：** CORE-Bench 的代码输出问答与 PaperBench 的论文结果匹配分别保留；旧版本执行成功不代表当前可用。新运行属于外部任务；新发现可由外部提交为 Content(observation)，数据库只执行显式写入。

**模式：** 同一实体检索接口覆盖论文及其他资源；同一内容检索/访问契约承载不同描述信息，核验语义由 A 消化。

## 5. 属性图与 Cypher 表达：同一操作覆盖不同 kind

### 5.1 物理映射与精确读取

一种直接实现是所有节点使用 `:Knowledge`，通过 `family/kind` 属性区分语义；所有边使用 `:Link`，通过 `relation/role` 区分操作契约。逻辑层的三类对象不要求三个不同的物理字段集合。

```text
(:Knowledge {
  id, revision, family, kind, name, aliases, description,
  metadata_json, sources_json
})
-[:Link {
  id, relation, role, description, metadata_json, sources_json
}]->
(:Knowledge {...})
```

这里的 `metadata_json/sources_json` 是序列化存储的示意，接口返回时解码为逻辑值。Neo4j 属性不能直接保存任意嵌套 map [S11]；不得把上文逻辑封装误当成可原样存入的属性。sources 的定位格式、关系端点与 role 的结构有效性由系统按契约检查，领域支持关系由外部判断。

以下片段在任务的固定 G 上解释，每个 id 在该快照只对应一项选定 revision。若使用包含更大范围的共享库，需将 scope 条件加入所有节点和关系访问，不能只约束入口。示例用于表达方案，未执行数据库验证。

**Get：** 已知 ID 时统一读取，缺失仍保留请求行。

```cypher
UNWIND $ids AS requested_id
OPTIONAL MATCH (n:Knowledge {id: requested_id})
RETURN requested_id, n
```

n 的 family/kind 无论是 Entity/paper 还是 Content/experiment，返回结构相同。数据库执行标识匹配，不解释 metadata。

### 5.2 Expand：统一关联操作

`direction` 为 out/in/both；可选列表参数为 null 表示不施加该项约束，为空列表表示不允许任何匹配。

```cypher
UNWIND $seed_ids AS seed_id
OPTIONAL MATCH (s:Knowledge {id: seed_id})
OPTIONAL MATCH (s)-[r:Link]-(t:Knowledge)
WHERE r.relation IN $relations
  AND ($direction = 'both'
       OR ($direction = 'out' AND startNode(r) = s)
       OR ($direction = 'in' AND endNode(r) = s))
  AND ($target_families IS NULL OR t.family IN $target_families)
  AND ($target_kinds IS NULL OR t.kind IN $target_kinds)
  AND ($roles IS NULL OR r.role IN $roles)
RETURN seed_id, s, r, t,
       startNode(r).id AS from_id, endNode(r).id AS to_id
```

无边时返回 null 对应的未匹配状态，接口不能把它当作“对象不存在”。I4 使用 `RESPONDS_TO/in/Content/claim`，I6 使用 `OBSERVES/in/Content/observation`，改变的是参数及关系含义，而不是节点字段和查询模板。

### 5.3 I3 的实验关联查询

```cypher
MATCH (m:Knowledge)
WHERE m.family = 'Concept' AND m.kind = 'method'
  AND m.id IN $method_ids
MATCH (e:Knowledge)-[tested:Link]->(m)
WHERE e.family = 'Content' AND e.kind = 'experiment'
  AND tested.relation = 'EVALUATES'
MATCH (e)-[used:Link]->(d:Knowledge)
WHERE d.family = 'Entity' AND d.kind = 'dataset'
  AND d.id = $dataset_id
  AND used.relation = 'USES' AND used.role = 'evaluation_data'
RETURN m, tested, e, used, d
```

该查询只保证返回图中明确连接的参与对象、实验和评测数据，保留 `tested.role`；不返回假想的统一 `score/split` 字段。后续 A_map 从 metadata 与证据中取得本次比较所需的值与条件，A_pred 决定是否可比。

### 5.4 全文与向量索引使用相同输入字段

所有 kind 共用以下索引字段契约，可实现为共享索引，或采用同配置的 family 分区：

| 索引通道 | 字段与构建规则 | 查询规则 |
| --- | --- | --- |
| 名称全文 | `name`, `aliases`，统一分词配置 | 可选 mention；适用于所有有称呼/短标题的对象 |
| 描述全文 | `description`，统一分词配置 | 需求或定义文本 |
| 描述向量 | `description`，统一编码模型、模板与维度 | 同 purpose 下统一查询编码；只做相似候选召回 |

以描述全文通道为例：

```cypher
CALL db.index.fulltext.queryNodes('knowledge_descriptions', $query_text)
YIELD node, score
WHERE node.family = $family AND node.kind IN $kinds
RETURN node.id AS id, node.revision AS revision, score
ORDER BY score DESC, id
LIMIT $channel_depth
```

`query_text` 是对用户检索词按索引语法处理后的参数，不能把任意自然语言直接当成查询语法。向量索引消费同一 description 的派生向量，索引调用按后端版本落实。[S10] 编码模型、文本修订、预处理配置和编码指令的变化均进入索引构建标识；旧索引不能继续冒充新描述的检索结果。

向量召回、索引融合是数据操作，原文解释是 A 运算，二者不能因都涉及模型而混为一个责任层。嵌入计算部署在系统内还是外部仍可选择，但不改变中间件不调度语义判断 Agent 的边界。

## 6. 从分解提炼 workload，反过来检查分类和粒度

### 6.1 共同访问 workload

| Workload | 参数化需求 | 出现位置 | 对模型与操作的约束 |
| --- | --- | --- | --- |
| **W1 指称/定义定位** | 称呼、说明、类型 → 待确认对象/概念 | I2/I3/I6 入口，I4/I5 聚合入口 | 公共名称与描述，lookup 与确认分离 |
| **W2 需求相关检索** | 自然语言需求、类型和范围 → 相关候选 | I1/I2/I4/I5/I6 | 相同检索面上的词面与语义召回；按任务定义相关性 |
| **W3 明确关系的上下文取得** | ID、方向、relation、role → 关系与记录 | I1–I6 | 同一 Expand，保留方向、角色、来源和缺边状态 |
| **W4 来源化的信息组织** | 已有引用与对应关系 → 按对象/实验/来源组织的记录 | I3/I4/I5/I6 | 精确 Group/Join 与 Agent 语义分组分开，不丢失局部条件 |
| **W5 依据读取** | 版本化位置 → 原文或检查产物 | I1–I6 的核查步骤 | 定位、可用性与证据支持判断分开 |

W1 与 W2 可以共用一个 Retrieve 的不同 purpose，不要求分别建立一组索引。W3–W5 可以直接由查询、文件读取和组合实现，也可以在反复出现的契约稳定后形成工具接口。**算子边界由复用和契约决定，不要求每种 kind 对应一个算子。**

端到端表达式中，A_map、A_pred、A_policy 可以与这些数据操作交替。研究主要评价 W1–W5 的支持与组合语义，同时观察外部 Agent 是否能够有效使用；不把 Agent 推理本身的提高算作中间件的既定贡献。

### 6.2 一个实际的共同调整：实验报告与结果单元

I3 的信息要求是“取得带方法、数据、指标、条件和来源的结果”，并不直接要求一个 Experiment 节点或一个 Result 节点。

| 表示候选 | 相应表达式 | 适用代价与缺口 |
| --- | --- | --- |
| Content(experiment) 保存一份实验报告，metadata 含设置和若干结果 | Retrieve/Expand → A_map 解析结果行 → A_pred 判断口径 | 写入较粗，细节可异构；重复查询可能反复解析，也要检查行列对应 |
| 将可独立引用的实验结果拆为 Content(result)，关联实验上下文 | Retrieve/Expand 定位结果 → Get 上下文 → A_pred 判断口径 | 独立检索与复用更直接；构建、拆分及上下文完整性维护更复杂 |
| 进一步将数值和评测键提升为标准检索字段 | 明确条件的 Join/Filter/排序 → A_pred 处理剩余语义条件 | 支持数据库内数值操作；需新增字段约束和规范化成本，不能继续宣称这些字段完全异构 |

本稿的 I3 使用第一种作为可执行思路；若真实任务反复需要结果级访问，应比较第二种。第三种只有在直接数值查询成为明确 workload 时才引入。这里的“第一种”不约束最终模型，替换时需要同步修改 kind、关系粒度、查询表达和评价成本。

拆分判断的依据是：某部分是否被独立检索/引用，是否有独立来源或修订过程，是否需要与其他对象关联，拆开后能否保留解释所需上下文。不能只因出现一个领域名词就建立新节点。

### 6.3 为什么本轮提出三类，而非固定四层或完全无类型

| 候选组织方式 | 本轮判断 |
| --- | --- |
| 所有记录完全无类型地放入同一池 | 字段简单，但对象身份、共同定义和来源化说法易混淆；可作为对照 |
| 按每个业务对象设计独立字段与检索器 | 描述能力强，但难以复用检索接口；不符合已确定的统一检索面目标 |
| 资源实体 / 研究概念 / 证据单元 / 跨论文语义空间四类 | 可解释领域角色，但“跨论文”不是独立检索字段需求，Observation 也不局限于论文内部 |
| **Entity / Concept / Content 三类，公共检索面，kind 区分语义** | 作为本轮候选：同时保持可引用对象、定义与来源记录的身份区别，并共享检索实现 |

family 是共享身份规则的粗分类，kind 是任务中的语义角色；它们都不直接决定节点大小。一份实验可以对应一个 Content，也可按可引用单元拆成多个 Content，不能从 family/kind 数量推断粒度。

三类不意味着需要三套不同索引算法。即使字段和算法完全相同，family/kind 仍帮助限定候选、验证关系端点和解释身份。类别是否需要进一步合并或拆分，由信息损失、操作复杂度和任务支持情况检验，而非按名称直觉决定。

## 7. 可写入论文的主张、继承范围与验证

### 7.1 论文叙述草案

> 本研究从六类有文献与公开任务依据的知识利用意图出发，将其分解为候选定位、关系访问、来源化组织与依据读取，并显式分离外部语义判断。为使异构研究知识能够通过一致接口被访问，我们提出具有统一检索面与异构描述面的数据表示：可引用资源、概念对象和来源化内容共享检索字段与混合检索流程，通过类型和关系契约保持身份、条件与来源区别。外部 Agent 在数据操作之间执行解释、比较和决策；中间件只执行显式提交的数据操作。节点粒度与操作表达共同接受任务检查，而非由预设领域 schema 单向决定。

这是候选方法的设计表述，不能替代效果实验或新颖性比较。公共封装和混合检索本身也不自动构成数据库贡献；需要证明其契约、组合或维护机制对所选 workload 的价值。

### 7.2 与 v1 的关系

保留 v1 可用的**机制与语义经验**：名称/别名、词面与向量混合召回、RRF、类型约束、候选解释、证据定位，以及身份确认由外部完成的边界。

重新设计的是**模型分组与接口边界**：Paper 并入 Entity；Method、Issue、共同命题可进入 Concept；Claim、实验和检查等共用 Content 的检索结构；异构内容留在 metadata。旧的 `find_entities/find_statements` 可以提供实现材料，但不是 v2 必须保留的两个接口，原有按类型拼文本方式也需要改造。参见 [v1 算子](../v1/operator.md)。

目前只写设计，不迁移已有图、不更改实验代码和索引。旧实现不能直接证明本文新的统一描述检索或 A 运算组合已经可用。

### 7.3 什么证据能支持设计成立

| 要检验的主张 | 对照或独立检查 |
| --- | --- |
| 分类保留了所需信息 | 对同一任务列出必须取得的信息，与各候选表示和返回结果逐项对应；检查来源、条件、角色损失 |
| 统一检索面足够有效 | 对比统一接口、按 kind 单独设计的检索、无类型统一检索；同时检查各类候选召回及错误类型 |
| 混合检索有收益 | 名称/全文、向量、融合消融；分别标注 lookup 的身份/定义相关性与 relevant 的任务相关性 |
| 描述生成方式合理 | 原摘要/说明直用与外部规范化描述的质量、构建成本、召回和来源保真度比较 |
| 图组合与操作契约有价值 | 在同一知识上比较直接 Cypher、充分说明的查询模板和候选算子；核对结果、交互成本及错误恢复 |
| Agent 运算与数据执行可分开评价 | 固定 A 输出检查数据操作，再固定数据记录评价 A；端到端另外报告意图符合性和答案支持度 |
| 知识积累值得维护 | 计入构建、描述修订、索引重建与反复利用的总成本；不能只报告查询节省 |

变更还要求检索面与描述面不产生静默不一致。例如 metadata 中的方法前提修订后，旧 description 是否仍适用，应由外部构建者确认并显式提交；中间件可以检查修订/索引版本是否匹配，却不能自行判断语义是否一致。更新、撤回与历史查询需另选真实变更序列，本文六类利用 intent 不冒充已完成的更新 benchmark。

**下一步：** 选择少量有真实材料、固定输入和独立参考结果的实例，核对本文分解是否取得全部必要信息，再比较节点粒度与检索配置。文中的伪代码和 Cypher 当前属于设计表达，格式与契约审阅不等于数据库执行验证；benchmark 范围在讨论后确定。

## 来源与可追溯位置

- **[S1] AstaBench**：官方 Literature Understanding Benchmarks 中 PaperFindingBench 的任务定义。[任务说明](https://allenai.org/asta/bench)。
- **[S2] QASPER**：*A Dataset of Information-Seeking Questions and Answers Anchored in Research Papers*，§2–3、Table 1。[论文](https://aclanthology.org/2021.naacl-main.365/)。
- **[S3] TDMS-IE**：*Identification of Tasks, Datasets, Evaluation Metrics, and Numeric Scores for Scientific Leaderboards Construction*。[论文](https://aclanthology.org/P19-1513/)。
- **[S4] ScholarQABench / ScholarQA-CS**：专家研究问题、rubric 和引用评价。[作者介绍](https://allenai.org/blog/openscilm)，[数据与评价代码](https://github.com/AkariAsai/ScholarQABench)。
- **[S5] ArxivDIGESTables**：*Synthesizing Scientific Literature into Tables using Language Models*。[论文](https://aclanthology.org/2024.emnlp-main.538/)。
- **[S6] SciFact**：*Fact or Fiction: Verifying Scientific Claims*。[论文](https://aclanthology.org/2020.emnlp-main.609/)。用于核查任务形式，领域内容与本项目有区别。
- **[S7] CORE-Bench**：使用代码和数据进行计算复现并回答输出问题。[官方说明](https://github.com/siegelz/core-bench)。
- **[S8] PaperBench**：*Evaluating AI's Ability to Replicate AI Research*，§2.2–2.4 的复现阶段与不同要求类型。[论文](https://cdn.openai.com/papers/22265bac-3191-44e5-b057-7aaacd8e90cd/paperbench.pdf)。
- **[S9] RRF**：*Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods*。[论文](https://doi.org/10.1145/1571941.1572114)。
- **[S10] 索引接口**：[Neo4j 全文索引](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/full-text-indexes/)、[向量索引](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)。
- **[S11] 属性类型限制**：[Neo4j Property, structural, and constructed values](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/)。

[S1]: https://allenai.org/asta/bench
[S2]: https://aclanthology.org/2021.naacl-main.365/
[S3]: https://aclanthology.org/P19-1513/
[S4]: https://allenai.org/blog/openscilm
[S5]: https://aclanthology.org/2024.emnlp-main.538/
[S6]: https://aclanthology.org/2020.emnlp-main.609/
[S7]: https://github.com/siegelz/core-bench
[S8]: https://cdn.openai.com/papers/22265bac-3191-44e5-b057-7aaacd8e90cd/paperbench.pdf
[S9]: https://doi.org/10.1145/1571941.1572114
[S10]: https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/
[S11]: https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/
