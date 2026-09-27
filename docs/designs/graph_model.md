# 论文理解经验 Graph Model

本稿设计一个面向研究 Agent 的论文知识图：保存阅读后形成的理解，通过论文引用、共享方法、资源和命题连接不同论文，让后续研究能够查找、比较和复用已有经验。

采用 Neo4j 的 Labeled Property Graph 模型，统一使用 `Node`、`Relationship`、`Label`、`Type`、`Property` 描述。概念依据见 [Neo4j 图模型](https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/)。

```text
Graph Model
│
├── Node
│    ├── Label
│    └── Property
│
├── Relationship
│    ├── Type
│    └── Property
│
└── Query
     ├── Pattern matching
     ├── Traversal
     └── Path query
```

以下为概念设计，Cypher 仅用于展示结构与查询意图，尚未实施。

## 设计思路

- **保留研究对象及其关系。** 论文中的贡献、主张、方法、实验和依据，以及跨论文联系，共同构成可复用的理解。
- **简化 Property。** 节点保留必要名称、Agent 描述和原文锚点；不以减少节点或关系类型作为精简目标。
- **用 Agent 撰写的描述保存理解。** 图中保留元数据和加工后的理解；已获取的原文整理成 Markdown，摘要、正文和表格等原始内容通过工具按需读取。
- **从论文及其引用逐步入图。** 被引文献尚未获取全文时，可以先凭已知标题建立 Paper 和引用关系，后续再补充材料与理解。
- **围绕跨论文联系组织图。** 同一方法、资源或命题可以连接多篇论文；各论文中的具体说法和使用经验分别保留。
- **按需展开篇内内容。** 不要求每篇论文建立完整内部子图，也不要求抽齐所有节点类型。

Node 按其表达的内容分为：

- 论文与研究内容：`Paper`、`Contribution`、`Method`、`MethodConcept`、`Claim`、`ClaimConcept`。
- 任务与问题：`Task`、`Issue`。
- 第一手检查：`Observation`。
- 实验与评测：`Experiment`、`Metric`。
- 资源与使用经验：`Resource`、`ResourceRecord`。Resource 另带一个次级 Label 区分种类。

## Property 的共同约定

每个 Node 有一个 `id` 用于引用，Paper 示例显式列出，其余示例省略。`id` 由写入工具分配，是不带语义的图内标识，例如 `res_0005`；前缀仅便于阅读日志，不参与身份判断。对象的称呼、种类和来源分别由 `name` / `aliases`、Label 与内容属性表达，不编码进 `id`；名称修改或判断修订时 `id` 保持不变。

内容属性主要是：

- `text` / `description`：Agent 整理后的主张或描述，可以概括和改写，保留影响含义的条件、版本和局限；Agent 自己的推断在文字中说明。
- `anchor`：指向已处理 Markdown 的原文位置，统一采用 `<文件路径::章节::start:end>`。区间沿用 Markdown 读取工具的定位口径；多处依据可列出多个锚点，示例统一用列表表示。

原文的文字、表格和图片所在位置均使用同一种锚点。来源可沿已连接节点回溯时，不必重复存放。示例文字仅展示表达方式，不代表已有研究结论。

跨论文共享、需要按称呼查找的 Node 另有 `aliases`：`Paper`、`Method`、`MethodConcept`、`Task`、`Resource`、`Metric`。

- `aliases`：字符串列表，保存已确认指向同一对象的其他称呼，如缩写、写法变体、标题变体；不重复主名称 `name` / `title`，查找时二者一并检索。
- alias 不是唯一键，同一个称呼可以出现在多个节点上，命中后仍需按定义、来源和版本消歧。检索时临时生成的扩展词不写入 aliases。
- 确认为同一对象后才追加，只追加并去重，不覆盖已有值。每个 alias 的出处（所在论文、anchor、判断理由）记录在抽取增量中，不作为图属性展开。

`ClaimConcept`、`Issue` 与论文局部的 Node 不设 aliases：命题或问题的不同说法通过 `EXPRESSES` / `RESPONDS_TO` 连接的 Claim 保存，并保留各自的条件和依据。

所有 Node 可带可选的 `note`：一段简短文字，保存读到或使用该节点时值得一并看到的提醒。note 与其他内容的分工：

| 内容 | 位置 |
|---|---|
| 对象是什么（定义、身份、机制） | `description` / `text` |
| 使用提醒、消歧线索、核对中发现的来源分歧 | `note` |
| 某篇论文如何描述、使用该对象 | 关系、`ResourceRecord` 等论文局部节点 |
| 经验判断与效果结论（何时更准、谁优于谁） | `Claim` / `ClaimConcept`，经 `ABOUT` 连到所讨论的对象 |
| 第一手检查、运行、复现的结果 | `Observation` |

note 不写定义，也不承载需要追溯来源、可被支持或质疑的判断；这类判断即使需要随节点一并读到，也由查询沿 `ABOUT` 取回相关 Claim。note 的每次写入和修改记录在增量中（原内容、依据、理由），不在节点属性中展开来源。

抽取模型、提示词、运行记录等需要复现时保存在实验日志中，本图暂不展开这些工程字段。

## Node

### Paper

一篇论文在图中的入口，可以先只有已知元数据，再随材料获取和阅读补充理解。阅读概述由 Agent 撰写，可包含研究问题、贡献和重要局限。

```cypher
(:Paper {
    id: "<paper_id>",
    title: "<论文标题>",
    aliases: ["<标题变体>"],
    year: 2026,
    s2_id: "<Semantic Scholar ID>",
    paper_type: "method",
    description: "<Agent 对论文的概述>",
    markdown_path: "<文件路径>",
    anchor: ["<文件路径::引言::start:end>"],
    arxiv_id: ""
})
```

`id` 是图内论文标识，不依赖是否已获取全文、S2 或 arXiv 记录。`s2_id`、`arxiv_id` 等元数据已知时填写；`paper_type` 可先使用 method / dataset / benchmark / empirical / survey / other。概述中需要核对的内容可通过 `anchor` 定位。

从引用条目中仅获得标题时，也可以先建立节点：

```cypher
(:Paper {
    id: "<paper_id>",
    title: "<引用条目中的论文标题>"
})
```

此时不要求填写 `description`、`markdown_path` 或其他未知属性，也不据标题生成全文阅读结论。标题用于发现和匹配文献，不直接作为唯一 ID；后续确认对应文献并获得材料时，在同一节点上补充信息，保持 `id` 不变。引用条目、S2 与正式版本中的标题写法不一致时，保留一个 `title`，其余写法作为 aliases 追加。

### Contribution

论文声明的一项贡献，由 Agent 整理其内容与意义，并连接它涉及的方法、资源、实验和具体主张。

```cypher
(:Contribution {
    text: "<Agent 整理后的贡献描述>",
    anchor: ["<文件路径::引言::start:end>"]
})
```

Contribution 回答“这篇论文贡献了什么”；Claim 表达其中可以单独讨论或检查依据的具体主张。例如，“提出方法 M 并改善任务表现”可以连接方法 M，以及描述其效果的 Claim。一项贡献不必同时关联所有类型，也不要求一定有实验支持。

### Method

可以被提出、沿用、扩展或比较的具体方法方案或明确变体。描述保存其主要思想和机制；某篇论文如何使用它，由该论文与方法的关系说明。

```cypher
(:Method {
    name: "<方法名称>",
    aliases: ["<缩写或其他称呼>"],
    description: "<Agent 对方法机制与用途的描述>",
    anchor: ["<文件路径::方法::start:end>"]
})
```

确认指向同一方法时，跨论文共用节点；有实质变化的方法可另建节点并关联其来源。方法方案与可下载的模型权重、代码仓库分别表示，后者属于 Resource（`Model`、`CodeRepo`）。

### MethodConcept

跨论文共享的方法类别，描述一类方法的共同机制和范围。具体 Method 通过 `INSTANCE_OF` 连接到类别，类别之间通过关系表达层级或重叠。

```cypher
(:MethodConcept {
    name: "<方法类别名称>",
    aliases: ["<其他称呼>"],
    description: "<该类别的共同机制、适用范围与区分边界>"
})
```

例如，“检索增强生成”和“基于图索引的检索增强生成”可作为 MethodConcept；某篇论文提出的具体 RAG 或 GraphRAG 方案属于 Method。评测方法同样按方法类别表示，例如“基于 LLM 的成对比较评测”。方法所针对的任务不作为 MethodConcept，由 `Task` 表示。类别归属由定义与方法内容确定，可以有多个类别，不要求组织成单一树形。

MethodConcept 的类别层级与 Method 的沿用谱系分别表达：属于同类不自动表示直接改进自另一方法。方法类别和共同命题也有不同含义：

| 具体内容 | 归一化概念 | 两层之间的关系 |
|---|---|---|
| `Method`：具体方案或变体，多篇论文可沿用同一方案 | `MethodConcept`：具有定义的方法类别 | `INSTANCE_OF`：方案属于该类别 |
| `Claim`：某篇论文的具体主张，保留条件和依据 | `ClaimConcept`：跨论文共同表达的完整命题 | `EXPRESSES`：具体说法表达该命题 |

### Task

跨论文共享的研究任务，即方法要解决、实验要评测的问题类型。任务之间可以有包含关系。

```cypher
(:Task {
    name: "<任务名称>",
    aliases: ["<其他称呼>"],
    description: "<任务的输入输出、目标与评测方式的共同约定>"
})
```

例如“时序预测”与其子类“长期时序预测”，“问答”与其子类“多跳问答”。Task 回答“解决什么问题”，MethodConcept 回答“用哪一类做法”：长期时序预测是 Task，季节—趋势分解是 MethodConcept。同一批数据可以服务于不同任务，例如用于预测，也用于表示学习后的迁移，因此任务不从数据集推出，而由方法、实验和资源分别连接。

Task 不另设论文级记录。某篇论文对任务的具体设定分两处保存：实验层面的取值（如回看窗口、预测长度）写在 Experiment 的 description 中；论文如何表述该任务写在 `ADDRESSES`、`ON_TASK` 关系的 description 与 anchor 中。论文提出的新任务提法被后续工作沿用时，建立为子 Task，并通过 `SUBTYPE_OF` 连接上位任务。

### Claim

Agent 根据一篇论文整理的一条具体主张，保留其适用条件与原文依据。它可以被后续论文的主张参照，也可以连接所讨论的方法、资源及支持实验。

```cypher
(:Claim {
    text: "在本文考察的多跳检索任务中，结构化记忆改善了回答质量。",
    anchor: ["<文件路径::实验结果::start:end>"]
})
```

每篇论文的具体说法分别保存；只有论文的发布声明或作者判断时，在 text 中明确写出。原文锚点支持回看，不单独代表主张已被验证。

### ClaimConcept

跨论文共享的归一化命题，用来关联表达同一命题的 Claim。其 text 由 Agent 归纳，依据通过关联的 Claim 回溯。

```cypher
(:ClaimConcept {
    text: "<保留必要适用范围的共同命题>"
})
```

归并要求命题含义与适用范围相容，不能通过删掉关键条件来制造一致性。仅仅讨论相同主题，不足以连接到同一个 ClaimConcept；无法确认时先保留独立 Claim。

本稿中 ClaimConcept 表示“共同命题”；对同一问题给出不同回答的主张，通过 Issue 聚合。

### Issue

跨论文共享的研究问题或有争议的论点。多篇论文可以回应同一个 Issue，回答可以不同甚至相反。

```cypher
(:Issue {
    text: "Transformer 架构对长期时序预测是否有效？",
    description: "<问题的范围、争议所在及判断时需要注意的条件>"
})
```

Issue 是问题，ClaimConcept 是命题：前者聚合回应同一问题的主张，回答可以相反；后者聚合表达同一命题的主张，含义必须相容。同一条 Claim 可以既表达某个 ClaimConcept，又回应某个 Issue。

只有论文明确提出某个问题，或两篇以上论文的主张确实在回答同一问题时，才建立 Issue；仅仅讨论相同主题不足以建立。text 的措辞保持中立，不预设答案，并保留范围限定。条件不同的回答仍连接到同一 Issue，条件差异在各自 Claim 与关系描述中说明。

### Resource

可被多篇论文共同使用或讨论的资源。每个 Resource 除 `Resource` 外恰好带一个次级 Label，表示资源种类：

```cypher
(:Resource:Benchmark {
    name: "<资源名称>",
    aliases: ["<其他称呼>"],
    url: "<资源地址>",
    description: "<Agent 对资源内容与用途的简要描述>"
})
```

| 次级 Label | 含义与边界 |
|---|---|
| `Dataset` | 数据本身，可被训练、评测或多个 Benchmark 使用 |
| `Benchmark` | 数据加上任务定义与评测协议，用于比较方法 |
| `Model` | 可加载的模型权重或 checkpoint |
| `CodeRepo` | 代码仓库 |
| `Tool` | 实验中使用的软件、库或服务 API |

种类属于资源身份的一部分，不设其他按种类区分的属性；任务、规模、切分、评分方式等信息写在 description 中。一个对象兼有多种身份时拆成多个 Resource，例如同一仓库发布的代码与模型权重分别建立 `CodeRepo` 与 `Model`，按需用关系连接。

Resource 与 Method 分别表示：名为 BERT 的方法方案是 Method，其预训练权重是 `Resource:Model`，`google-research/bert` 仓库是 `Resource:CodeRepo`。同名对象通过 Label 与描述区分。

确认是同一资源时共用节点；同名或共用仓库 URL 不自动视为同一资源。

### ResourceRecord

某篇论文对一个资源的具体描述或使用经验。它将论文中的说法连接到共同资源，保留不同论文对该资源的用法和认识。

```cypher
(:ResourceRecord {
    url: "<本记录对应的资源链接>",
    description: "<本文如何介绍、处理或使用该资源，以及相关发现或局限>",
    anchor: ["<文件路径::数据与设置::start:end>"]
})
```

`url` 保留该记录中出现或使用的资源地址，可以是论文给出的仓库、版本或数据下载链接；Resource 的 `url` 保存资源的通用入口，两者可以相同，也可以不同。

影响理解的版本、切分和修改写在 description 中。论文声称资源公开时，按声明保存；对资源的外部检查或实际运行结果不写入 ResourceRecord，而由 Observation 记录并与之对照。

### Experiment

论文报告的一项实验，连接被测对象、所用资源和指标，并作为相关主张的依据。描述概括实验目的、设置、主要发现和局限。

```cypher
(:Experiment {
    description: "<Agent 对实验设置、主要发现及其边界的总结>",
    anchor: [
        "<文件路径::实验设置::start:end>",
        "<文件路径::实验结果::start:end>"
    ]
})
```

实验设置不单独建节点，写在 description 中，且必须写明影响可比性的设置：所用数据集及其版本或切分、主要超参数（如回看窗口、预测长度）、是否标准化、所用模型或检索器等。不同论文的实验能否比较，由 Agent 读各自的 description 判断；这类判断本身是经验，写成 Claim。

结果所在的表、图直接用块级 anchor 引用（如某篇论文的表 2），不单独建节点；具体数值按需沿 anchor 读取原文，不写入图中。

### Metric

实验或资源评测使用的指标。共享指标可以帮助查找采用相同评测口径的工作。

```cypher
(:Metric {
    name: "<指标名称>",
    aliases: ["<其他称呼>"],
    description: "<指标衡量什么及其计算口径>",
    anchor: ["<文件路径::评测指标::start:end>"]
})
```

同名且定义、口径一致时才共用节点；具体实验如何使用指标可在关系描述中说明。

### Observation

对资源或论文说法的一次第一手检查，例如查看代码仓库内容、实际运行代码、复现实验结果。它的依据来自检查本身而非论文，因此与论文的发布声明、使用记录分开保存。

```cypher
(:Observation {
    kind: "repo_inspection",
    description: "<检查了什么、看到了什么、结论及局限>",
    observed_at: "2026-09-27",
    target: "https://github.com/<owner>/<repo>@<commit>",
    evidence: ["<检查日志或产物路径>"]
})
```

`kind` 可使用 repo_inspection / execution / reproduction，分别对应查看内容、成功运行与复现实验结果这三种不同强度的发现。`target` 记录被检查对象的具体版本，`evidence` 指向检查日志或产物，作用相当于论文依据的 anchor。

Observation 具有时效：同一资源再次检查时新建 Observation，保留此前的记录，维护状况等随时间变化的情况由此体现。

## Relationship

Relationship 表达对象间的联系。需要解释关系含义时使用 `description`；需要原文依据时使用 `anchor`，与 Node 沿用相同约定。简单归属关系不必重复附加描述和锚点。

### 论文、贡献与具体内容

```cypher
(:Paper)-[:HAS_CONTRIBUTION]->(:Contribution)
(:Contribution)-[:ABOUT]->(:Method)
(:Contribution)-[:ABOUT]->(:Resource)
(:Contribution)-[:ABOUT]->(:Experiment)
(:Contribution)-[:HAS_CLAIM]->(:Claim)
```

`ABOUT` 说明贡献涉及哪个对象：例如提出方法、发布数据集或开展一项实验研究。`HAS_CLAIM` 连接该贡献包含的具体主张，进一步可沿 Claim 查看实验依据。

这些联系由贡献内容及原文依据确定，不因出现在同一篇论文中就自动建立；Contribution 与 Claim 也不要求一一对应。

### 论文与主张

```cypher
(:Paper)-[:HAS_CLAIM]->(:Claim)
(:Claim)-[:EXPRESSES]->(:ClaimConcept)
(:Claim)-[:ABOUT]->(:Method)
(:Claim)-[:ABOUT]->(:MethodConcept)
(:Claim)-[:ABOUT]->(:Task)
(:Claim)-[:ABOUT]->(:Resource)
(:Claim)-[:ABOUT]->(:Metric)
```

`EXPRESSES` 将具体说法关联到共同命题；`ABOUT` 标明主张讨论的对象，可以是具体方法、方法类别、任务、资源或指标。关于一类方法或某项指标的经验判断由此挂到对应节点，查看该节点时一并取回。共享 ClaimConcept 提供跨论文查找入口，各 Claim 的条件和依据仍需分别阅读。

### 任务与问题

```cypher
(:Method)
    -[:ADDRESSES {
        description: "<本文如何表述该方法针对的任务>",
        anchor: ["<文件路径::引言::start:end>"]
    }]->
(:Task)
(:Experiment)-[:ON_TASK]->(:Task)
(:Resource)-[:FOR_TASK]->(:Task)

(:Paper)
    -[:RAISES {
        description: "<本文如何提出或重新表述该问题>",
        anchor: ["<文件路径::引言::start:end>"]
    }]->
(:Issue)
(:Claim)
    -[:RESPONDS_TO {
        stance: "no",
        description: "<该主张如何回应问题，以及回答成立的条件>",
        anchor: ["<文件路径::实验结果::start:end>"]
    }]->
(:Issue)
(:Issue)-[:ABOUT]->(:Task)
(:Issue)-[:ABOUT]->(:MethodConcept)
(:Issue)-[:ABOUT]->(:Method)
```

`ADDRESSES` 表示方法针对的任务，`ON_TASK` 表示实验评测的任务，`FOR_TASK` 表示数据集或基准服务于哪个任务；三者分别判断，不相互推出。

Task 与 Issue 是共享概念，节点本身不带 anchor；依据放在连接它们的关系上。`RAISES`、`RESPONDS_TO`、`ADDRESSES` 需要 anchor；`ON_TASK` 仅在任务设定需要单独说明时附加，否则沿 Experiment 的 anchor 回溯；`FOR_TASK` 来自论文时附 anchor，来自预置种子时出处记录在种子增量中；`Issue -[:ABOUT]->` 与 `Task -[:SUBTYPE_OF]->` 属于概念之间的关系，不附 anchor。

`RAISES` 表示论文明确提出或重新表述了该问题。`RESPONDS_TO.stance` 可使用 yes / no / partial / reframes，reframes 表示认为问题本身的提法需要修正；“如何做到某事”这类无法以是否回答的问题不填 stance，只写 description。

### 论文与方法

```cypher
(:Paper)
    -[:HAS_METHOD {
        role: "reused",
        description: "<本文如何使用或修改该方法>",
        anchor: ["<文件路径::方法::start:end>"]
    }]->
(:Method)

(:Method)-[:DERIVED_FROM]->(:Method)
(:Method)-[:DERIVED_FROM]->(:Resource)
(:Method)-[:PRODUCES]->(:Resource)
(:Method)-[:INSTANCE_OF]->(:MethodConcept)
```

`HAS_METHOD.role` 可使用 proposed / reused / extended / compared。`DERIVED_FROM` 表达有依据的来源或沿用，`PRODUCES` 表达方法的资源产物，`INSTANCE_OF` 表达具体方案的类别归属；具体联系通过关系描述与锚点解释。

### 论文与资源经验

```cypher
(:Paper)-[:HAS_RESOURCE_RECORD]->(:ResourceRecord)
(:ResourceRecord)-[:DESCRIBES]->(:Resource)
(:ResourceRecord)-[:HAS_METRIC]->(:Metric)

(:Paper)
    -[:RELATES_TO {
        role: "used",
        description: "<本文与该资源的联系>",
        anchor: ["<文件路径::数据与设置::start:end>"]
    }]->
(:Resource)
```

`RELATES_TO.role` 可使用 introduced / used / evaluated / cited_only，表示论文与资源的直接联系；ResourceRecord 保存具体描述和使用经验。多篇论文的记录可以指向同一 Resource，从而并列查看不同认识。

`HAS_METRIC` 连接资源所采用的评测指标；某次实验实际使用的指标则由该 Experiment 的 `MEASURED_BY` 表达。

### 实验与依据

```cypher
(:Paper)-[:REPORTS]->(:Experiment)
(:Claim)-[:SUPPORTED_BY]->(:Experiment)
(:Experiment)-[:MEASURED_BY]->(:Metric)

(:Experiment)-[:EVALUATES {role: "target"}]->(:Method)
(:Experiment)-[:EVALUATES {role: "baseline"}]->(:Method)
(:Experiment)-[:EVALUATES {role: "target"}]->(:Resource)
(:Experiment)-[:EVALUATES {role: "baseline"}]->(:Resource)

(:Experiment)-[:USES {role: "evaluation_data"}]->(:Resource)
```

`EVALUATES` 连接被测方法或模型等资源，区分 target / baseline；`USES` 连接所用数据、工具等，role 可使用 training_data / evaluation_data / analysis_input / tooling。

`MEASURED_BY` 表达实验采用的指标。Experiment 的 anchor 同时列出实验设置与报告结果的表、图所在的块。

`SUPPORTED_BY` 表达 Agent 对支持关系的理解；若只支持部分内容，在关系 description 中说明，并给出对应 anchor。论文级资源角色不直接推作实验中的使用角色。

### 第一手检查

```cypher
(:Observation)-[:OBSERVES]->(:Resource)
(:Observation)
    -[:CHECKS {
        verdict: "inconsistent",
        description: "<对照论文说法后的一致之处与差异>"
    }]->
(:ResourceRecord)
(:Observation)-[:CHECKS {verdict: "partial"}]->(:Claim)
```

`OBSERVES` 连接被检查的资源。`CHECKS` 把检查结果与论文的说法对照，`verdict` 可使用 consistent / inconsistent / partial / inconclusive。例如论文声称代码仓库实现了所提方法，检查发现仓库内容与论文不符且长期未维护：ResourceRecord 保留论文的声明，Observation 记录检查时间、版本与所见，并以 `verdict: inconsistent` 连到该 ResourceRecord。

### 论文互相参照

```cypher
(:Paper)
    -[:CITES {
        description: "沿用该论文的评测任务，并增加跨领域测试。",
        anchor: ["<引用方文件路径::实验设置::start:end>"]
    }]->
(:Paper)
```

`CITES` 保留引用事实，description 解释引用方如何使用被引工作。引用本身不自动推出主张支持或方法沿用关系。

尚无全文的 Paper 也可以作为 `CITES` 的终点。关系的 `anchor` 指向引用方 Markdown 中的引用上下文或参考文献条目；只有引用条目时，先保留引用和定位，待有足够依据后再补充关系描述。

### 同类 Node 之间的关系

同类节点可以直接表达沿用、组成、支持、限制、差异和层级关系。下表列出关系的端点、方向及需要在 description 与依据中表达清楚的内容。

| 同类节点 | Relationship Type | 方向 | 需要表达清楚的内容 |
|---|---|---|---|
| `Paper` | `CITES` | 引用方 → 被引论文 | 如何引用和使用被引工作 |
| `Method` | `DERIVED_FROM` | 派生方法 → 来源方法 | 改进或沿用的来源，以及继承、修改了哪些机制 |
| `Method` | `USES_COMPONENT` | 整体方法 → 组件方法 | 使用了哪个方法作为组件，以及组件承担什么作用 |
| `Method` | `DIFFERS_FROM` | 语义对称 | 具体差异维度及两方做法，例如索引结构、检索方式或构建成本 |
| `MethodConcept` | `SUBTYPE_OF` | 子类 → 上位类别 | 类别包含关系：子类保留哪些共同特征，又增加了哪些限定 |
| `MethodConcept` | `OVERLAPS_WITH` | 语义对称 | 类别的共同部分与各自范围，部分重叠不等于包含 |
| `Task` | `SUBTYPE_OF` | 子任务 → 上位任务 | 子任务增加了哪些限定，例如预测长度或推理跳数 |
| `Claim` | `SUPPORTS` | 提供支持的主张 → 得到支持的主张 | 哪些发现或理由提供支持，以及支持到什么范围 |
| `Claim` | `CHALLENGES` | 提出质疑的主张 → 被质疑的主张 | 反例、不支持的结果或质疑针对什么内容，是否涉及条件差异 |
| `Claim` | `QUALIFIES` | 提供限定的主张 → 被限定的主张 | 补充了哪些适用条件、例外或边界 |
| `ClaimConcept` | `REFINES` | 细化后的命题 → 较概括的命题 | 命题增加了哪些具体条件、对象或区分；细化不自动表示逻辑蕴含 |
| `ClaimConcept` | `IMPLIES` | 前提命题 → 被蕴含命题 | 在什么共同前提下，前者成立足以推出后者 |
| `ClaimConcept` | `CONTRADICTS` | 语义对称 | 同一对象、条件和口径下，两条命题为何不能同时成立 |
| `Issue` | `REFINES` | 更具体的问题 → 较概括的问题 | 子问题限定了哪些对象、条件或范围 |
| `Resource` | `DERIVED_FROM` | 派生资源 → 来源资源 | 数据、代码或模型的派生来源，以及筛选、修改或加工方式 |
| `Resource` | `PART_OF` | 组成资源 → 整体资源 | 资源的组成关系及该部分在整体中的作用 |
| `Contribution` | `EXTENDS` | 后续贡献 → 被扩展的贡献 | 后续工作具体扩展了前作的哪项贡献，以及新增内容 |

语义对称的关系不赋予起点、终点主次含义，读取时可双向遍历。其余关系按表中方向理解，不把类别包含、组件组成和命题蕴含统一成一种“包含”。

关系沿用简洁的 `description + anchor`。description 说明适用范围，并区分作者明示与 Agent 归纳；跨论文判断的依据可以包含两篇论文的锚点。

方法的类别归属与直接沿用需要分别判断，不要求为每条关系计算相似度分数。性能差异通过具体 Claim、Experiment 和条件说明，不建立脱离设置的普遍优劣判断。

Claim 之间的证据支持也不自动升级为 ClaimConcept 之间的逻辑蕴含。例如，“多跳任务中观察到改善”不能直接推出“所有任务都改善”；不同条件下的结果差异也不直接构成 `CONTRADICTS`。

### Agent 扩展关系

Agent 优先使用已有关系类型。遇到确有用途、但尚未归入上述类型的新语义时，可先用 `RELATED_TO` 保存，并通过 `kind` 给出关系名称：

```cypher
(a:Method)
    -[:RELATED_TO {
        kind: "design_tradeoff",
        description: "<二者在哪个设计维度形成取舍、适用范围及判断依据>",
        anchor: [
            "<论文A文件路径::方法::start:end>",
            "<论文B文件路径::方法::start:end>"
        ]
    }]->
(b:Method)
```

扩展关系可用于其他有明确关联的节点，description 同时说明两端角色和方向含义。相同含义复用同一个 kind；反复出现且含义稳定后，再统一为专门的 Relationship Type。`RELATED_TO` 用于扩展语义关系，已有 `RELATES_TO` 仍表示论文与资源的角色联系。

不要求所有同类节点两两相连，也不预先给每种节点配齐同类关系。每条新增关系应提供具体的可复用理解。

## 图的组织方式

篇内保留贡献、具体主张及其依据之间的联系。下图是可能存在的一条路径，不要求每项贡献都具备所有后续节点。

```mermaid
graph LR
    P[Paper] -->|HAS_CONTRIBUTION| C[Contribution]
    C -->|ABOUT| M[Method]
    C -->|HAS_CLAIM| CL[Claim]
    CL -->|ABOUT| M
    CL -->|SUPPORTED_BY| E[Experiment]
    E -->|EVALUATES| M
    E -->|MEASURED_BY| ME[Metric]
```

下图展示两篇论文如何通过共同命题和资源相连，节点之间的路径用于寻找相关经验。

```mermaid
graph LR
    PA[Paper A] -->|HAS_CLAIM| CA[Claim A]
    PB[Paper B] -->|HAS_CLAIM| CB[Claim B]
    CA -->|EXPRESSES| CC[ClaimConcept]
    CB -->|EXPRESSES| CC
    PA -->|HAS_RESOURCE_RECORD| RA[ResourceRecord A]
    PB -->|HAS_RESOURCE_RECORD| RB[ResourceRecord B]
    RA -->|DESCRIBES| R[Resource]
    RB -->|DESCRIBES| R
    PB -->|CITES| PA
```

具体方法与方法类别分别组织。以下以 RAG 为例展示本模型的分类方式：2020 年论文提出的具体 RAG 模型与 Microsoft 2024 年的 GraphRAG 方案是 Method；“检索增强生成”及其图索引子类是 MethodConcept。方案来源见 [RAG 原始论文](https://arxiv.org/abs/2005.11401)与 [GraphRAG 原始论文](https://arxiv.org/abs/2404.16130)。

```mermaid
graph BT
    M1[Method：2020 RAG 方案] -->|INSTANCE_OF| C1[MethodConcept：检索增强生成]
    M2[Method：Microsoft 2024 GraphRAG 方案] -->|INSTANCE_OF| C2[MethodConcept：基于图索引的检索增强生成]
    C2 -->|SUBTYPE_OF| C1
```

该图仅表达类别归属，不据此推导两个具体方案之间的 `DERIVED_FROM`。复用时可通过共同对象或同类节点关系找到相关记录，再阅读 Agent 描述，必要时沿锚点核对原文。

## Query

以下查询展示模型希望支持的读取方式，尚未在数据库执行。

### 按名称与 aliases 查找候选实体

抽取时先按名称和 aliases 做归一化的精确匹配，并返回命中字段，供 Agent 判断是否复用：

```cypher
WITH toLower(trim($q)) AS q
MATCH (n:Paper|Method|MethodConcept|Resource|Metric)
WHERE toLower(coalesce(n.name, n.title)) = q
   OR ANY(a IN coalesce(n.aliases, []) WHERE toLower(trim(a)) = q)
RETURN n.id AS id, labels(n) AS labels,
       coalesce(n.name, n.title) AS name, n.aliases AS aliases,
       CASE WHEN toLower(coalesce(n.name, n.title)) = q
            THEN 'name' ELSE 'alias' END AS hit
```

精确匹配未命中或需要召回写法相近的候选时，使用覆盖名称、标题和 aliases 的全文索引：

```cypher
CREATE FULLTEXT INDEX entity_names IF NOT EXISTS
FOR (n:Paper|Method|MethodConcept|Resource|Metric)
ON EACH [n.name, n.title, n.aliases];

CALL db.index.fulltext.queryNodes('entity_names', $q) YIELD node, score
RETURN node.id AS id, labels(node) AS labels,
       coalesce(node.name, node.title) AS name, node.aliases AS aliases, score
ORDER BY score DESC LIMIT 10
```

两种查询只返回候选；是否为同一对象仍由 Agent 结合定义、来源和版本判断。二者已在样例图谱上执行（`experiments/e08/notebooks/04_neo4j.ipynb` step9），本地 Neo4j 2026.09 的全文索引可直接索引 aliases 这类字符串列表。

### 从贡献查看具体主张及其结果依据

```cypher
MATCH (:Paper {id: $paper_id})-[:HAS_CONTRIBUTION]->(c:Contribution)
OPTIONAL MATCH (c)-[:HAS_CLAIM]->(cl:Claim)
OPTIONAL MATCH (cl)-[:SUPPORTED_BY]->(e:Experiment)
RETURN c.text AS contribution,
       c.anchor AS contribution_anchor,
       cl.text AS claim,
       cl.anchor AS claim_anchor,
       e.description AS experiment,
       e.anchor AS experiment_anchor
```

### 找到表达共同命题的其他论文

```cypher
MATCH (p1:Paper {id: $paper_id})-[:HAS_CLAIM]->(c1:Claim)
      -[:EXPRESSES]->(concept:ClaimConcept)
      <-[:EXPRESSES]-(c2:Claim)<-[:HAS_CLAIM]-(p2:Paper)
WHERE p1.id <> p2.id
RETURN concept.text AS common_claim,
       c1.text AS source_claim,
       p2.title AS related_paper,
       c2.text AS related_claim,
       c1.anchor AS source_anchor,
       c2.anchor AS related_anchor
```

### 沿共同资源查找其他论文的使用经验

```cypher
MATCH (p1:Paper {id: $paper_id})-[:HAS_RESOURCE_RECORD]->(r1:ResourceRecord)
      -[:DESCRIBES]->(r:Resource)
      <-[:DESCRIBES]-(r2:ResourceRecord)
      <-[:HAS_RESOURCE_RECORD]-(p2:Paper)
WHERE p1.id <> p2.id
RETURN r.name AS resource,
       r1.description AS source_experience,
       p2.title AS related_paper,
       r2.description AS related_experience,
       r2.anchor AS related_anchor
```

按次级 Label 限定资源种类，例如查找两篇论文共同评测过的 Benchmark：

```cypher
MATCH (p1:Paper {id: $paper_id})-[:REPORTS]->(:Experiment)
      -[:USES]->(b:Resource:Benchmark)
      <-[:USES]-(:Experiment)<-[:REPORTS]-(p2:Paper)
WHERE p1.id <> p2.id
RETURN b.name AS benchmark, collect(DISTINCT p2.title) AS other_papers
```

论文与资源的角色也可直接查询：

```cypher
MATCH (p:Paper)-[rel:RELATES_TO]->(r:Resource {id: $resource_id})
RETURN p.title AS paper, rel.role AS role,
       rel.description AS relation, rel.anchor AS anchor
```

这些路径用于发现值得一起阅读和比较的经验。主张归并是否正确、资源是否对齐、关系是否有依据，以及它们是否帮助后续研究，是本模型需要检验的研究问题。
