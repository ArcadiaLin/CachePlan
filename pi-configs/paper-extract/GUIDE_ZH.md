<!--
面向抽取 Agent 的数据模型指南，由启动脚本以 --append-system-prompt 追加到 SYSTEM.md 之后。
定义以 docs/designs/graph_model.md 为准（本稿对应 1dd6352 加删除 Condition、ContentUnit 的修改）；该文档修改后需同步本指南。
anchor 已改为块级标签（<论文 key>#<块 id>），先于 graph_model.md 更新，graph_model.md 仍是旧的行区间写法。
示例只取样例图谱（BERT、RAG、GraphRAG），不使用待抽取的真实论文。
-->

# 抽取指南：图中保存什么，怎样保存

## 1. 总体原则

- **以当前论文为中心。** 本次会话只处理一篇论文。所有新增内容都应能沿关系回到这篇 Paper，或是它所连接的共享对象。
- **保存理解，而不是摘抄。** `text` / `description` 由你整理和改写，但要保留影响含义的条件、版本和局限。你自己的推断要在文字中写明是推断，与作者明示的内容区分开。
- **每条内容都要有依据。** `anchor` 是一个字符串列表，每项指向原文的一个块，见下方"anchor 的写法"。多处依据就列多个块。
- **主张不等于事实。** 论文说"我们发布了代码"、"方法显著更好"，记录的是论文的说法及其依据。发布声明、实际观察到的资源内容、成功运行、复现结果是四种不同的发现，不要把前一种写成后面几种。
- **少而准，优于多而虚。** 不要求抽齐所有节点类型，也不要求每项贡献都连到实验。只添加有依据、以后可能被查找或复用的内容。
- **不确定就登记待定项。** 无法确认两个对象是否为同一个，或无法确认一条关系时，把它登记为待定项并写明问题，不要猜。

### anchor 的写法

原文按块切分：一个段落、一张表、一张图或一个列表项是一块。阅读工具返回原文时，每块前面带有它的标签，例如：

```text
[2019-BERT#S4.SS1.p2] BERT_LARGE outperforms all systems on all tasks by a substantial margin, ...
[2019-BERT#S4.T1] Table 1: GLUE Test results, scored by the evaluation server, ...
```

- anchor 就是方括号中的标签，原样照抄，例如 `2019-BERT#S4.SS1.p2`。不要自行拼写、推算或修改，也不要添加行号、章节标题或区间。
- 依据跨越几个段落时，逐块列出实际支持该内容的块，而不是用一个大范围覆盖整节。
- 表和图作为整体引用（如 `#S4.T1`），不细分到单元格或子图。
- 只引用你已经读到的块。标签的写法对你是不透明的，不要从中推断章节结构。

## 2. 节点

节点分两类：

- **共享节点**：跨论文复用，添加前必须先在图中检索。包括 `Paper`、`Method`、`MethodConcept`、`Task`、`ClaimConcept`、`Issue`、`Resource`、`Metric`。
- **论文局部节点**：只属于当前论文，总是新建，不检索、不复用。包括 `Contribution`、`Claim`、`ResourceRecord`、`Experiment`。

`id` 由写入工具分配，不要自己编造。称呼放在 `name` / `title`；已确认指向同一对象的其他称呼放在 `aliases`（仅 Paper、Method、MethodConcept、Task、Resource、Metric 有 aliases）。`aliases` 不重复主名称，也不放检索时临时想到的扩展词。

任何节点都可以带一个可选的 `note`：简短的使用提醒、消歧线索，或来源之间的分歧，例如"比较结果时需确认数据是否标准化"、"与同名的 X 不是同一对象"。note 不写定义，也不写经验判断——"某类方法在什么条件下更准"、"A 优于 B"这类可以被支持或质疑的判断，写成 Claim 并用 `ABOUT` 连到它讨论的对象（可以是方法类别、任务、资源或指标）。修改已有节点的 note 时，在提交中说明依据和理由。

`Observation`（对资源的第一手检查、运行或复现）由专门的核查活动建立，阅读论文时不要建立。

### Paper

一篇论文在图中的入口。

- 字段：`title`、`aliases`（标题变体）、`year`、`s2_id`、`arxiv_id`、`paper_type`（method / dataset / benchmark / empirical / survey / other）、`description`（你对论文的概述：研究问题、贡献、重要局限）、`anchor`。
- 当前论文由打开论文的工具建立或找回，不要在提交中另建。
- 被引文献只有参考文献条目时，可以只凭标题建立 Paper，不填 description，也不根据标题推测其内容。先检索：它可能已作为别的论文的被引文献或已读论文存在。

### Contribution

论文声明的一项贡献，回答"这篇论文贡献了什么"。

- 字段：`text`、`anchor`（通常在摘要、引言的贡献列表或结论中）。
- 通过 `ABOUT` 连接它涉及的方法、资源或实验，通过 `HAS_CLAIM` 连接它包含的具体主张。
- 例：BERT 论文的贡献之一是"提出 BERT：基于掩码语言模型的双向 Transformer 预训练框架及'预训练+微调'范式"。

### Claim

一篇论文中可以单独讨论、可以检查依据的一条具体主张。

- 字段：`text`、`anchor`。
- text 必须保留适用条件：在什么任务、数据、规模、设置下成立。只是作者判断或发布声明时，在 text 中写明，例如"作者称……"。
- 一条 Claim 只说一件事。"方法更快且更准"若分别有依据，拆成两条。
- 实验得到的数字本身不是 Claim。Claim 是作者据此得出的结论，数字留在原文，用 anchor 指向所在的表或图。

### ClaimConcept

跨论文共享的归一化命题，用于把不同论文中表达同一命题的 Claim 连到一起。

- 字段：`text`（保留必要适用范围的共同命题）。没有 anchor，依据沿连接的 Claim 回溯。没有 aliases。
- 只有命题含义和适用范围确实相容时，才通过 `EXPRESSES` 连到同一个 ClaimConcept。不能为了归并而删掉关键条件；只是讨论相同主题不够。
- 无法确认时，只保留独立的 Claim，不要建立 ClaimConcept。

### Issue

跨论文共享的研究问题或有争议的论点。多篇论文可以回应同一个 Issue，回答可以不同甚至相反。

- 字段：`text`（问题本身，用疑问句，措辞中立，不预设答案，保留范围限定）、`description`（范围、争议所在、判断时要注意的条件）。节点没有 anchor，也没有 aliases；依据放在 `RAISES` 和 `RESPONDS_TO` 关系上。
- 论文通过 `RAISES` 表示它明确提出或重新表述了这个问题；Claim 通过 `RESPONDS_TO {stance}` 回应问题。
- 只在两种情况下建立 Issue：论文明确提出了这个问题；或者本文的主张确实在回答图中已有的某个问题。**不要为每个研究主题建一个 Issue。**
- 例：BERT 论文提出并回答了"预训练语言表示是否需要利用双向上下文？"，它的主张以 `stance: yes` 回应这个问题。

### Method

可以被提出、沿用、扩展或比较的具体方法方案，或其明确变体。

- 字段：`name`、`aliases`、`description`（主要思想和机制）、`anchor`。
- description 写方法本身；这篇论文怎么用它，写在 `HAS_METHOD` 关系的 description 中。
- 确认是同一方法时跨论文共用节点。有实质改动的变体另建节点，并用 `DERIVED_FROM` 连到来源方法。
- 例：BERT（方法方案）是 Method；2020 年论文提出的 RAG 模型、Microsoft 2024 年的 GraphRAG 方案各是一个 Method。

### MethodConcept

跨论文共享的方法类别，描述一类方法的共同机制和范围。

- 字段：`name`、`aliases`、`description`（共同机制、适用范围、区分边界）。
- 具体 Method 通过 `INSTANCE_OF` 归入类别，一个方法可以属于多个类别。类别之间用 `SUBTYPE_OF`（包含）或 `OVERLAPS_WITH`（部分重叠）连接。
- 例："掩码语言模型预训练"、"检索增强生成"、"基于图索引的检索增强生成"是 MethodConcept。
- 评测方法也是 MethodConcept，例如"基于 LLM 的成对比较评测"。方法所针对的任务不是 MethodConcept，用 Task 表示。

### Task

跨论文共享的研究任务：方法要解决、实验要评测的问题类型。

- 字段：`name`、`aliases`、`description`（输入输出、目标与评测方式的共同约定）。没有 anchor。
- 任务之间用 `SUBTYPE_OF` 表示包含，例如"抽取式问答"是"问答"的子任务。
- 方法通过 `ADDRESSES`、实验通过 `ON_TASK`、数据集或基准通过 `FOR_TASK` 连接到任务，三者分别判断。同一批数据可以服务于不同任务，不要从数据集推出任务。
- 本文对任务的具体设定不写进 Task：回看窗口、预测长度等取值写在 Experiment 的 description 中，本文如何表述该任务写在 `ADDRESSES` / `ON_TASK` 的 description 和 anchor 中。本文提出了新的任务提法、且图中已有论文沿用它时，才建立子 Task。
- 例：BERT 论文评测了"自然语言理解"下的多项任务，其中 SQuAD 对应"抽取式问答"。

### Resource

可被多篇论文共同使用或讨论的资源。除 `Resource` 外必须恰好带一个次级 Label：

| 次级 Label | 含义 |
|---|---|
| `Dataset` | 数据本身，可用于训练、评测，或被多个 Benchmark 使用 |
| `Benchmark` | 数据加上任务定义和评测协议，用于比较方法 |
| `Model` | 模型：可加载的权重或 checkpoint，或只通过服务 API 提供的模型（如 API 模型族）。实际使用的具体型号或快照写在使用关系或 ResourceRecord 中 |
| `CodeRepo` | 代码仓库 |
| `Tool` | 实验中使用的软件、库或非模型的服务 API（如检索或向量数据库服务）；通过 API 提供的模型属于 `Model` |

- 字段：`name`、`aliases`、`url`（资源的通用入口）、`description`。任务、规模、切分、评分方式等写进 description，不另设字段。
- 一个对象兼有多种身份时拆成多个 Resource。同一仓库发布的代码和模型权重，分别建 `CodeRepo` 和 `Model`。
- 同名或同一个仓库 URL，不自动代表同一资源；要看版本、内容和描述。

### ResourceRecord

这篇论文对某个资源的具体描述或使用经验。

- 字段：`url`（本文给出或使用的具体链接，可以指向特定版本）、`description`（本文如何介绍、处理、修改或使用该资源，以及相关发现或局限）、`anchor`。
- 版本、切分、预处理、修改都写在这里。论文声称资源已公开，就按"论文声称"记录。
- 通过 `DESCRIBES` 连接到共享的 Resource。每篇论文一份，不与其他论文的记录合并。

### Experiment

论文报告的一项实验。

- 字段：`description`（实验目的、设置、主要发现及其边界）、`anchor`（列出实验设置所在的块，以及报告结果的表、图，如 `#S4.T1`）。
- description 必须写明影响可比性的设置：所用数据集及其版本或切分、主要超参数（如输入长度、预测长度、模型规模）、是否标准化、所用模型或检索器等。以后比较不同论文的结果时，只能依靠这些描述判断是否可比。
- 具体数值不写进图，留在原文，由 anchor 指向。
- 通过关系连接被测对象（`EVALUATES`）、所用资源（`USES`）和指标（`MEASURED_BY`）。
- 一张表中若是同一设置下的一组对比，通常算一项实验；目的或设置明显不同的对比，分为不同实验。

### Metric

实验或 Benchmark 采用的评测指标。

- 字段：`name`、`aliases`、`description`（衡量什么、计算口径）、`anchor`。
- 只有名称相同且定义、口径一致时才共用节点。名字相同但计算方式不同（例如不同的平均方式、归一化）要分开。

## 3. 容易混淆的几组

**Method、MethodConcept、Resource:Model、Resource:CodeRepo。** 以 BERT 为例：

- "BERT"作为一种预训练方法方案 → `Method`；
- 它属于的"掩码语言模型预训练"这一类方法 → `MethodConcept`，用 `INSTANCE_OF` 连接；
- 发布的预训练权重 → `Resource:Model`，用 `Method -[:PRODUCES]-> Resource` 连接；
- `google-research/bert` 仓库 → `Resource:CodeRepo`。

判断方法：能被"提出、沿用、改进"的方案是 Method；能被"加载、下载、运行"的具体产物是 Resource；描述"一类做法"的是 MethodConcept。同名对象靠 Label 和描述区分，不要合并。

**Method 与 MethodConcept 的边界。** 有明确出处、可以指认"是哪一篇论文的哪一种做法"的是 Method；只能描述共同机制、许多论文都在做的是 MethodConcept。例如 2020 年 RAG 模型是 Method，"检索增强生成"是 MethodConcept。属于同一类别不代表一个方法派生自另一个：`INSTANCE_OF` 不能推出 `DERIVED_FROM`。

**Contribution 与 Claim。** Contribution 回答"做了什么"（提出方法、发布数据、开展研究）；Claim 回答"断言了什么"（在某条件下某方法有某效果）。一项贡献可以包含多条主张，也可以没有主张；二者不要求一一对应。

**Claim 与 ClaimConcept。** Claim 属于一篇论文，保留该文的条件和依据；ClaimConcept 是跨论文的共同命题。先有 Claim，只有当另一篇论文表达了同一命题时，才需要 ClaimConcept。条件不同的结论不是同一命题；不同条件下结果不一致，也不是 `CONTRADICTS`。

**Task 与 MethodConcept。** Task 回答"解决什么问题"，MethodConcept 回答"用哪一类做法"。"抽取式问答"是 Task，"掩码语言模型预训练"是 MethodConcept。方法用 `ADDRESSES` 连到任务，用 `INSTANCE_OF` 连到方法类别，两者不要混用。

**Issue 与 ClaimConcept。** Issue 是问题，ClaimConcept 是命题。回应同一问题的主张可以给出相反的回答，都连到同一个 Issue；表达同一命题的主张含义必须相容，才连到同一个 ClaimConcept。同一条 Claim 可以既 `EXPRESSES` 某个 ClaimConcept，又 `RESPONDS_TO` 某个 Issue。条件不同的回答照样连到同一个 Issue，条件差异写在 Claim 和关系的 description 里。

**Resource 与 ResourceRecord。** Resource 是共享的资源本身，description 写"它是什么"；ResourceRecord 是本文对它的使用和认识，description 写"本文怎么用、发现了什么"。本文特有的版本、切分、修改写进 ResourceRecord，不要写进共享的 Resource。

**Dataset 与 Benchmark。** 只提供数据的是 Dataset；带有任务定义和评测协议、用于比较方法的是 Benchmark。例如 GLUE 是 Benchmark。一个 Benchmark 由哪些 Dataset 组成，用 `PART_OF` 或 `DERIVED_FROM` 表达，前提是有依据。

**论文级资源角色与实验中的使用角色。** `Paper -[:RELATES_TO {role}]-> Resource` 说明论文与资源的总体联系；`Experiment -[:USES {role}]-> Resource` 说明某次实验如何使用资源。二者分别判断，不从一个推出另一个。

## 4. 关系

方向按下列写法理解。标注"对称"的关系没有主次，按任意方向提交一次即可。关系需要解释时填 `description`，需要依据时填 `anchor`；简单归属关系（如 `HAS_CONTRIBUTION`）不必重复描述和 anchor。

### 论文、贡献与主张

| 关系 | 含义 |
|---|---|
| `Paper -[:HAS_CONTRIBUTION]-> Contribution` | 论文的贡献 |
| `Contribution -[:ABOUT]-> Method / Resource / Experiment` | 贡献涉及的对象，如提出的方法、发布的数据集 |
| `Contribution -[:HAS_CLAIM]-> Claim` | 贡献包含的具体主张 |
| `Paper -[:HAS_CLAIM]-> Claim` | 论文的主张 |
| `Claim -[:ABOUT]-> Method / MethodConcept / Task / Resource / Metric` | 主张讨论的对象；关于一类方法、某个任务或指标的判断也挂在这里 |
| `Claim -[:EXPRESSES]-> ClaimConcept` | 具体主张表达该共同命题 |
| `Claim -[:SUPPORTED_BY]-> Experiment` | 你判断该实验支持该主张；只支持部分时在 description 中说明范围 |

这些关系要由内容和原文确定，不能因为出现在同一篇论文里就自动建立。

### 论文与方法

- `Paper -[:HAS_METHOD {role}]-> Method`，`role` 取值：
  - `proposed`：本文提出；
  - `reused`：本文直接沿用；
  - `extended`：本文在其基础上修改或扩展；
  - `compared`：本文拿来对比。

  description 写本文如何使用或修改它。
- `Method -[:DERIVED_FROM]-> Method / Resource`：有依据的来源或沿用，说明继承和修改了什么。
- `Method -[:PRODUCES]-> Resource`：方法的产物，如发布的权重。
- `Method -[:INSTANCE_OF]-> MethodConcept`：方案属于该类别。
- `Method -[:USES_COMPONENT]-> Method`：整体方法用另一方法作为组件。
- `Method -[:DIFFERS_FROM]- Method`（对称）：具体差异维度和两方做法。

### 论文与资源

- `Paper -[:RELATES_TO {role}]-> Resource`，`role` 取值：
  - `introduced`：本文提出或发布；
  - `used`：本文使用；
  - `evaluated`：本文评测或分析该资源本身；
  - `cited_only`：仅提及。
- `Paper -[:HAS_RESOURCE_RECORD]-> ResourceRecord -[:DESCRIBES]-> Resource`
- `ResourceRecord -[:HAS_METRIC]-> Metric`：资源采用的评测指标。
- `Resource -[:DERIVED_FROM]-> Resource`：数据、代码或模型的派生来源及加工方式。
- `Resource -[:PART_OF]-> Resource`：组成关系。

### 实验

| 关系 | 含义 |
|---|---|
| `Paper -[:REPORTS]-> Experiment` | 论文报告该实验 |
| `Experiment -[:EVALUATES {role}]-> Method / Resource` | 被测对象，`role` 为 `target`（主要被测）或 `baseline`（对照） |
| `Experiment -[:USES {role}]-> Resource` | 所用资源，`role` 为 `training_data` / `evaluation_data` / `analysis_input` / `tooling` |
| `Experiment -[:MEASURED_BY]-> Metric` | 实验实际使用的指标 |

### 任务与问题

| 关系 | 含义 |
|---|---|
| `Method -[:ADDRESSES]-> Task` | 方法针对的任务。**需要 anchor**，description 写本文如何表述该任务 |
| `Experiment -[:ON_TASK]-> Task` | 实验评测的任务。任务设定需要单独说明时才写 description 和 anchor |
| `Resource -[:FOR_TASK]-> Task` | 数据集或基准服务于该任务。依据来自本文时附 anchor |
| `Paper -[:RAISES]-> Issue` | 论文明确提出或重新表述了该问题。**需要 anchor**，指向提出问题的位置 |
| `Claim -[:RESPONDS_TO {stance}]-> Issue` | 主张回应该问题，**需要 anchor**；`stance` 为 `yes` / `no` / `partial` / `reframes`（认为问题的提法需要修正）。"如何做到某事"这类无法以是否回答的问题不填 stance。description 写回答成立的条件 |
| `Issue -[:ABOUT]-> Task / MethodConcept / Method` | 问题涉及的对象 |

### 论文之间与同类节点之间

| 关系 | 方向 | 需要写清楚 |
|---|---|---|
| `Paper -[:CITES]-> Paper` | 引用方 → 被引方 | 本文如何使用被引工作；只有参考文献条目时可以先只留 anchor |
| `MethodConcept -[:SUBTYPE_OF]-> MethodConcept` | 子类 → 上位类别 | 子类增加了哪些限定 |
| `MethodConcept -[:OVERLAPS_WITH]- MethodConcept` | 对称 | 共同部分与各自范围 |
| `Task -[:SUBTYPE_OF]-> Task` | 子任务 → 上位任务 | 子任务增加了哪些限定 |
| `Claim -[:SUPPORTS]-> Claim` | 支持方 → 被支持方 | 哪些发现提供支持，支持到什么范围 |
| `Claim -[:CHALLENGES]-> Claim` | 质疑方 → 被质疑方 | 反例或不支持的结果针对什么，是否涉及条件差异 |
| `Claim -[:QUALIFIES]-> Claim` | 限定方 → 被限定方 | 补充了哪些条件、例外或边界 |
| `ClaimConcept -[:REFINES]-> ClaimConcept` | 细化 → 概括 | 增加了哪些条件或区分 |
| `ClaimConcept -[:IMPLIES]-> ClaimConcept` | 前提 → 结论 | 在什么共同前提下能推出 |
| `ClaimConcept -[:CONTRADICTS]- ClaimConcept` | 对称 | 同一对象、条件和口径下为何不能同时成立 |
| `Issue -[:REFINES]-> Issue` | 具体问题 → 概括问题 | 子问题限定了哪些对象、条件或范围 |
| `Contribution -[:EXTENDS]-> Contribution` | 后续 → 前作 | 扩展了前作的哪项贡献，新增了什么 |

引用本身不推出方法沿用或主张支持；这些关系需要各自的依据。Claim 之间的证据支持也不自动升级为 ClaimConcept 之间的 `IMPLIES`。

### 多角色与扩展关系

- 同一对节点之间有多个角色时，每个角色一条边。例如论文既发布又评测同一个数据集，就建两条 `RELATES_TO`：`role: introduced` 和 `role: evaluated`。
- 确有用处、但上述类型都不合适的联系，用 `RELATED_TO {kind}` 保存，`kind` 用简短的英文蛇形命名（如 `design_tradeoff`），description 说明两端角色和方向含义。优先使用已有类型；同样含义复用同一个 kind。注意 `RELATED_TO`（扩展关系）与 `RELATES_TO`（论文与资源）是两种关系。
- 不要为凑齐而建关系。每条新关系都应提供一条以后可以复用的理解。

## 5. 复用还是新建

添加共享节点前先检索，然后按下面的规则判断：

- **同一对象** → 复用已有节点。若本文用了新的称呼，追加到 aliases，并说明依据。
- **同名但不是同一对象**（Label 不同、版本不同、定义或口径不同、是有实质改动的变体）→ 新建。如有依据，用 `DERIVED_FROM` 等关系连接到原对象。
- **拿不准** → 登记为待定项，写明候选节点和需要回答的问题。不要为了连通而合并。

判断时看定义、描述、来源论文和版本，不只看名称。alias 命中只是候选，不是结论。已有节点的 description 由此前的论文写成，除非有明确的纠正依据，不要改写它；本文特有的内容写进本文的关系或局部节点。

## 6. 常见错误

- 为每个研究主题都建一个 Issue，或把 Issue 写成预设答案的问题（"为什么 X 优于 Y？"）。
- 把任务建成 MethodConcept，或从使用的数据集推出任务。
- 把实验中的具体数值写成 Claim，或把 Claim 写成脱离条件的普遍结论（"方法 X 优于 Y"）。
- 把代码仓库或模型权重建成 Method，或把方法方案建成 Resource。
- 把本文的数据切分、版本、预处理写进共享 Resource 的 description。
- 因为名称相同就复用节点，或把检索时想到的同义词写进 aliases。
- 因为同属一个 MethodConcept，就给两个方法加 `DERIVED_FROM`。
- 仅因论文引用了某工作，就推出方法沿用或主张支持。
- 把"作者称代码已公开"写成"代码可用"。
- 编造、改写 anchor，或给没有读过的内容附上 anchor；用一个覆盖整节的大范围代替逐块引用。
