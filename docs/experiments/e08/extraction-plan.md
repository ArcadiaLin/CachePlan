# E08 · 已准备论文的增量抽取计划

日期：2026-09-27。状态：材料准备已完成；本文规划下一步抽取。`aliases` 已写入 Graph Model；工具接口和具体运行配置尚待落实。

目标是从真实论文形成有原文依据的理解，并在逐篇阅读过程中复用、补充已有知识图谱。首先观察实体身份、实验条件、证据和跨论文关系能否被正确保存，再将稳定的操作整理为扩展知识库的 operator。本轮属于数据与工具准备，不将抽取 Agent 本身预设为论文贡献，也不据此确定正式 benchmark。

## 1. 已有材料与本轮范围

材料入口为 [papers.yml](../../../data/raw/e08-paper-knowledge/papers.yml) 和 [status.yml](../../../data/raw/e08-paper-knowledge/status.yml)，准备流程见 [05_data_prepare.ipynb](../../../experiments/e08/notebooks/05_data_prepare.ipynb)。截至本次验收，六篇均为 `ready: true`，共有 301 条 S2 参考文献记录和 56 张本地图片。301 是各篇记录数之和，不是去重后的论文数。

| 材料 key | 固定 arXiv 版本 | S2 references | HTML 文末参考文献 |
| --- | --- | ---: | ---: |
| `2023-DLinear` | `2205.13504v2` | 36 | 29 |
| `2023-PatchTST` | `2211.14730v2` | 46 | 43 |
| `2024-GraphRAG` | `2404.16130v2` | 57 | 79 |
| `2025-LightRAG` | `2410.05779v1` | 21 | 21 |
| `2024-HippoRAG` | `2405.14831v1` | 97 | 80 |
| `2025-HippoRAG2` | `2502.14802v1` | 44 | 39 |

每篇材料位于 `data/raw/e08-paper-knowledge/papers/<key>/`：

- `s2/paper.yml`：S2 元数据及请求来源。
- `s2/references.yml`、`s2/references_pages/`：参考文献聚合结果与原始分页响应。
- `source.html`、`source.yml`：固定版本的官方 HTML、来源和哈希。
- `paper.md`、`document.yml`：转换后的正文、章节目录、版本与哈希。
- `images/`、`images.yml`：本地图片与来源映射。

上述材料由数据准备阶段统一获取，不代表已经阅读或入图。S2 的记录可能整合不同版本，其 references 与所选 HTML 的文末条目不能直接视为一一对应。正文抽取以固定版本的 Markdown、HTML 和图片为依据；S2 用于文献身份、元数据和引用候选，二者的来源分别保留。

本轮沿用以下边界：

1. **只关注 references。** 不获取或展开 citations（施引文献）；早期准备留下的施引文件不参与抽取和验收。
2. **按需选择被引论文。** 获取 references 不等于全部入图。优先处理解释当前方法来源、实验基线、关键资源或后续阅读需求所必需的文献。
3. **区分占位与理解。** 被选中的文献可先建立只有已知身份信息的 `Paper`，必要时连接 `CITES`；不能仅凭题名或 S2 简介生成已读全文的理解子图。
4. **逐篇积累知识。** 全部材料可以提前准备，但抽取时按阅读顺序推进，持续查询和更新此前形成的图谱。
5. **按内容单元提交。** 不先生成覆盖整批论文的大 YAML；一篇内部也可多次提交有依据的小块增量。

## 2. 第一步：确定抽取约定与更新语义

以 [Graph Model](../../designs/graph_model.md) 为节点、关系含义的依据。先明确身份、依据、复用和更新规则，再包装写入工具，避免将模型输出直接当作最终节点身份。

### 2.1 程序、LLM 与 Agent 的职责

程序负责读取材料、定位原文、查询候选、验证结构和执行事务。LLM 在给定片段中提出带依据的理解。Agent 负责选择继续阅读的位置、检索已有图谱、核对候选身份，并综合多个片段或多篇论文作判断。

首轮由一个 pi Agent 完成阅读、判断和工具调用，不另建多 Agent 流程；下表中“LLM”的工作也由该 Agent 在阅读时完成。工具内部不引入无状态 LLM 调用：需要判断的交给 Agent，可机械完成的交给脚本，避免在工具中隐藏一次模型推理，导致无法区分效果来自 Agent 推理、工具内模型还是检索。用另一模型核查主张与原文是否相符属于复核层，不作为抽取工具。

| Node | 形成依据与主要职责 | 复用范围与 aliases |
| --- | --- | --- |
| `Paper` | 程序读取 S2 身份；Agent 根据原文写概述和论文类型 | 按外部标识符核对身份；标题变体记入 `aliases`，题名不作唯一键 |
| `Contribution` | LLM 提取贡献陈述，Agent 核对涉及的内容 | 属于具体论文，不跨论文合并 |
| `Method` | LLM 整理机制；Agent 联读引用、方法描述并消歧 | 设 `aliases`；同一方案复用，实质变体另建 |
| `MethodConcept` | Agent 根据方法机制与现有定义归类 | 设 `aliases`；对齐类别定义和范围 |
| `Claim` | LLM 提取具体主张、限定条件和依据；Agent 核对 | 属于具体论文；不同论文的相似说法分别保存 |
| `ClaimConcept` | Agent 比较已有 Claim，归纳共同命题 | 按命题含义与条件对齐，不设 aliases |
| `Resource` | 程序发现链接；LLM 判断用途；Agent 核对身份 | 设 `aliases`；结合类型、入口、版本判断，不能只看名称或 URL |
| `ResourceRecord` | LLM 整理本文如何介绍、处理或使用资源 | 保留论文与使用情境，不跨论文合并 |
| `Experiment` | LLM 整理目的、设置和结果；Agent 联读正文、表格及附录 | 属于具体论文，按可独立解释的实验组织 |
| `Metric` | LLM 提取名称与定义；Agent 核对计算口径 | 设 `aliases`；同名但口径不同不直接复用 |
| `Condition` | LLM 提取条件；Agent 补齐影响结论的限定 | 属于具体实验，不按条件名称全局合并 |
| `ContentUnit` | 程序定位表、图、段落；LLM 补充用途说明 | 按论文版本及原文位置复用 |

关系的生成职责如下；简单归属边也必须以已确认的所属关系为前提，不能仅凭同篇共现创建。

| Relationship | 生成与核对方式 |
| --- | --- |
| `CITES` | S2 提供候选；Agent 按需选取并核对正文条目和上下文。未核对时保留 S2 来源，不伪造正文 anchor 或引用意图 |
| `HAS_CONTRIBUTION`、`HAS_CLAIM`、`HAS_RESOURCE_RECORD`、`REPORTS`、`HAS_CONTENT`、`HAS_CONDITION` | 抽取结果明确所属对象后，由程序连接 |
| `ABOUT`、`DESCRIBES`、`HAS_METHOD`、`RELATES_TO` | LLM 判断对象及角色；Agent 完成端点消歧 |
| `EVALUATES`、`USES`、`HAS_METRIC`、`MEASURED_BY`、`RESULT_AT` | 从实验或资源说明中提取；Agent 核对设置、结果位置与角色 |
| `SUPPORTED_BY` | Agent 判断实验支持主张的具体范围，不因二者同处结果章节就连接 |
| `DERIVED_FROM`、`USES_COMPONENT`、`PRODUCES`、`PART_OF`、`EXTENDS` | LLM 提出候选；Agent 核查来源、组成或产出依据，引用本身不推出这些关系 |
| `INSTANCE_OF`、`SUBTYPE_OF`、`OVERLAPS_WITH` | Agent 比较具体机制与类别定义 |
| `EXPRESSES`、`REFINES`、`IMPLIES`、`CONTRADICTS` | Agent 比较完整命题与条件；不同条件下的结果差异不直接构成矛盾 |
| `DIFFERS_FROM`、`SUPPORTS`、`CHALLENGES`、`QUALIFIES` | Agent 联读双方依据，说明差异、支持或限定的范围 |
| `RELATED_TO` | 确有用途且已有类型不能表达时使用，说明 `kind`、端点角色、方向和依据 |

作者明示与 Agent 归纳在描述中区分。跨论文判断需要能够回看双方依据；证据不足的联系留在待核对记录中，不为了连接图谱而强行建立。

### 2.2 实体查找与确认

实体复用遵循以下顺序：

1. 带上节点类型、论文中的名称、上下文和已知外部标识符查询候选。
2. 工具先检查标识符与名称/aliases，再用文本检索召回可能匹配项；是否增加语义检索由首轮遗漏情况决定。精确匹配与全文索引两层查找已在 04_neo4j 的样例图谱上演示。
3. 候选返回 ID、类型、定义、来源、版本线索和命中原因，Agent 按需查看关联原文。
4. Agent 决定复用、另建或暂不确定，记录判断依据；新增 ID 由工具分配，后续名称变化不改变身份。
5. 确认同一对象后追加 alias，出处（论文、anchor、判断理由）写入本次增量记录；字段约定见 Graph Model。

这一流程只用于共享节点（Method、MethodConcept、Resource、Metric、ClaimConcept 及被引 Paper）。Contribution、Claim、Experiment、Condition、ContentUnit、ResourceRecord 属于当前论文，总是新建，不做相似检索。

alias 不是唯一键，同一缩写可以命中多个对象。搜索时生成的扩展词也不自动成为 alias。未消歧的提及可先留在抽取暂存记录中，不把不确定性隐藏在共享节点里。同一 benchmark 的不同切分通常需要分别保存使用记录和实验条件；是否属于不同 Resource，则根据资源身份判断。

### 2.3 原文锚点与增量更新

anchor 由读取工具返回，Agent 不自行猜测区间。首轮实施前固定 `start:end` 的单位、起点和区间边界，并验证“读取—返回 anchor—再次读取”能得到同一内容。材料版本及 Markdown 哈希写入运行记录；表图依据还应能沿 anchor 打开本地图片或对应表格。

[04_neo4j.ipynb](../../../experiments/e08/notebooks/04_neo4j.ipynb) 已演示 `plan_batch → apply_plan → 复核`，但真实抽取前需处理以下差别：

- 现有 `SET +=` 会整体替换给定属性值；aliases 和依据列表需要追加去重，不能误覆盖旧值。
- 现有关系统一按 `(from, type, to)` 识别。已确定同端点的每个角色各为一条关系，分别带 description 和 anchor：带 `role` 的关系按 `(from, type, to, role)` 识别，`RELATED_TO` 按 `(from, type, to, kind)` 识别。例如论文发布并评测同一数据集，是两条 `RELATES_TO`，而非一条带角色列表的关系。
- 共享描述的修订需要保存修改前后内容与依据；各论文独立的 Claim、ResourceRecord 不因后读论文而被覆盖。
- 写入前核对 label、关系端点、角色、原文位置和已引用 ID；同一增量重放不产生重复节点或关系，事务失败不留下半块子图。

这些更新规则落实后，才将 notebook 中的写入逻辑接到 Agent 工具。结构校验与写入幂等性不代表语义已经正确。

## 3. 第二步：准备专用 pi 配置与最小工具

拟在 `pi-configs/` 下新增专用配置，例如 `paper-extract/`，沿用 [现有配置约定](../../../pi-configs/README.md)。目录名、模型与调用预算在实施时确定，并记录到每次运行中。图谱使用与人工示例可区分的独立运行范围，避免伪造 anchor 或示例知识被当成已验证经验。

### 3.1 工具划分

抽取过程以论文为中心：Agent 先用工具建立或找回当前 Paper，再阅读原文，围绕它逐块添加有依据的节点和关系；添加共享节点前先检索图谱中是否已有同一对象。

该配置禁用 pi 内置的 `bash`、`grep`、`find`、`ls`、`read`、`write`、`edit`，只保留下列专用工具。读取只经工具进行，保证 anchor 由工具生成；写入只有 `submit` 一个入口，保证每次修改都经过校验并留下记录。名称为暂定。

| 工具 | 作用 | 返回 |
| --- | --- | --- |
| `open_paper(key)` | 核对材料 `ready` 与哈希；按 `s2_id`、`arxiv_id`、title/aliases 找回已有 Paper（含早先作为被引文献建立的占位节点）并补全元数据，找不到才新建；开启本篇运行记录 | Paper ID、元数据、带 anchor 的章节目录、图表清单、参考文献概况 |
| `read_paper(section \| anchor)` | 按章节或 anchor 读取原文；指向图片时返回本地图片 | 带精确 anchor 的文本片段或图片 |
| `search_paper(query)` | 在当前论文内按关键词定位，代替 grep；也用于查参考文献条目及对应的 S2 候选 | 命中片段及 anchor |
| `find_entities(mention, label?, context?)` | 身份检索：名称/aliases 精确匹配，未命中再全文召回 | 候选 ID、Label、名称、aliases、描述、相连论文、命中原因 |
| `inspect_node(id)` | 查看节点周围的已有经验：属性、关系、相连的 Claim、ResourceRecord、Experiment；可选择解析 anchor 为原文 | 节点邻域摘要 |
| `submit(subgraph)` | 提交一次增量：新建、复用、追加 alias、新建关系、修改属性、登记暂不确定项 | 成功返回回执；失败返回逐条错误，不写入任何内容 |
| `finish_paper(summary)` | 结束本篇，记录覆盖范围与未解决问题，快照图谱状态 | 本篇新增、复用、修订的对象统计 |

跨论文的关联检索暂不单设工具：例如读到后一篇在某数据集上的结果时，先用 `find_entities` 找到该 Resource，再用 `inspect_node` 查看此前论文在其上的使用记录、实验和主张。若首轮发现不经共享实体相连的主张被遗漏，再考虑增加 Claim 文本检索。

材料虽然全部在本地，单篇抽取仍只以当前论文（阅读类工具只作用于 `open_paper` 打开的论文）与此前已形成的图谱为主要上下文。若需要追读其他论文，显式记录阅读动作与顺序。拟为每篇开启新的 pi session，以观察跨篇理解是否通过图谱复用，而非依赖保留全部前文的对话上下文；工具不默认注入尚未阅读论文的全文或抽取结果。

### 3.2 `submit` 的参数结构

参数是一块以当前论文为中心的小子图，由 Agent 按 JSON Schema 填写对象，工具将其保存为运行记录中的 YAML 后执行入库。除 `paper`、`intent` 外各部分均可省略。

```ts
{
  paper:  string,        // 当前论文 ID，须与 open_paper 返回的一致
  intent: string,        // 一句话说明本次提交的内容
  new_nodes:     NewNode[],
  reuse:         Reuse[],
  relationships: Rel[],
  updates:       Update[],
  pending:       Pending[]
}

NewNode = {
  ref: "$m1",                        // 临时引用，本次提交内唯一；ID 由工具分配
  label: "Method",                   // 12 种主 Label 之一
  resource_kind?: "Dataset",         // 仅 Resource 必填：Dataset / Benchmark / Model / CodeRepo / Tool
  properties: {...},                 // 允许与必填的键按 Label 校验；不得写 id
  decision?: {                       // 共享节点必填
    candidates: string[],            // 看过但不复用的候选，须为本会话 find_entities 返回过的 ID，可为空
    reason: string
  }
}

Reuse = { id: string, reason: string, add_aliases?: string[] }

Rel = {
  from: "$ref" | "<id>", type: string, to: "$ref" | "<id>",
  properties?: { role?, kind?, description?, anchor? }
}

Update = { id: string, set: {...}, reason: string, anchor?: string[] }

Pending = { mention: string, label_guess?: string, anchor: string[],
            candidates?: string[], question: string }
```

各部分的约定：

- **`reuse`**：关系中引用的已有节点须在此声明并说明为何是同一对象；当前 Paper 及本篇已建的局部节点除外。`add_aliases` 追加去重，不覆盖已有值。
- **`relationships`**：端点 Label 按 Graph Model 的端点表校验，`role`、`kind` 按枚举校验。关系身份见 2.3；重复提交完全相同的关系不产生变化，身份相同而描述不同则报错，须改用 `updates`。
- **`updates`**：只允许修改 `description`、`text`、`name` 及 Paper 元数据；anchor 只能追加，aliases 只经 `add_aliases` 修改。工具自动记录修改前的值：原值为空视为补全，原值非空视为修订，须说明理由。
- **`pending`**：只写入运行记录，不进图，供后续确认时找回原始问题。
- **规模**：不设硬上限，单次超过约 20 个节点时给出提示。

例如提交 DLinear 的主方法：

```json
{
  "paper": "pap_0001",
  "intent": "DLinear 主方法、贡献及类别归属",
  "new_nodes": [
    {"ref": "$m1", "label": "Method",
     "properties": {"name": "DLinear", "description": "先做趋势—季节分解，再各用一层线性层……", "anchor": ["<anchor>"]},
     "decision": {"candidates": [], "reason": "find_entities('DLinear') 无命中"}},
    {"ref": "$c1", "label": "Contribution",
     "properties": {"text": "提出极简线性基线 DLinear，质疑 Transformer 在长时预测上的有效性", "anchor": ["<anchor>"]}}
  ],
  "reuse": [{"id": "mcp_0006", "reason": "已有类别的定义覆盖本方法"}],
  "relationships": [
    {"from": "pap_0001", "type": "HAS_METHOD", "to": "$m1", "properties": {"role": "proposed", "anchor": ["<anchor>"]}},
    {"from": "pap_0001", "type": "HAS_CONTRIBUTION", "to": "$c1"},
    {"from": "$c1", "type": "ABOUT", "to": "$m1"},
    {"from": "$m1", "type": "INSTANCE_OF", "to": "mcp_0006"}
  ]
}
```

示例中的 ID、类别与描述仅为示意。成功时回执给出增量编号、临时引用到正式 ID 的映射（如 `{"$m1": "mth_0010"}`），以及新建、复用、修改和追加 alias 的清单。失败时整次提交不写入，逐条返回带位置的错误，例如 `relationships[3]: INSTANCE_OF 的终点须为 MethodConcept，实际为 Method`，Agent 修正后重新提交。

### 3.3 脚本承担的复杂度

Agent 不编写 Cypher，也不接触文件路径，只表达读哪里、是什么、与谁有何关系以及判断理由。以下由固定脚本负责：

- **Cypher**：全部为参数化模板，包括 Label 与关系类型白名单、含 `role`/`kind` 的 MERGE 身份、列表字段追加去重、事务和写后复核。
- **ID 与幂等**：工具分配 ID；对增量计算哈希，重放同一增量不产生重复内容。
- **anchor**：由读取工具生成；`submit` 将 anchor 解析回原文确认存在，并要求它在本会话中被读取过。
- **可机械检查的约束**：关系端点与角色、Resource 恰有一个次级 Label、论文局部节点只挂在当前论文下、新建共享节点附带检索决策且候选确由本会话检索返回（对照会话日志检查，而非只靠提示词）。
- **记录**：材料哈希、读取动作、检索结果、增量与回执自动写入运行目录（见第 7 节）。

系统提示词说明各节点及关系的含义、身份判断规则和证据要求；以上约束由工具强制，不只依赖提示词。结构校验通过不代表语义正确，语义仍由复核检查。

## 4. 第三步：用 DLinear 完成首篇试抽

首篇拟使用 `2023-DLinear`。先确定本次覆盖的内容单元，建议从主方法及一组核心实验结果开始，不预设必须抽齐全文所有细节。

每篇都采用以下循环：

```text
当前论文材料 + 已有图谱
    → 阅读原文并取得 anchor
    → 提出节点、主张和关系候选
    → 查询已有对象、回看证据、消歧
    → 提交一个有意义的小块增量
    → 校验、入图、记录回执
    → 继续阅读或提交修订
    → 完成本篇检查，记录此时的图谱状态
```

具体步骤：

1. 核对材料 `ready`、版本和哈希，查找或补全当前 `Paper`，保留已有图内 ID。
2. 阅读摘要、引言和结论，形成需要进一步核对的贡献与主张候选，不立即把概述当成已验证结论。
3. 阅读方法部分，描述方法机制；对组件、数据和模型资源查找已有对象，按需选择相关被引论文。
4. 联读实验设置、结果表图和必要附录，保留被测对象、基线、资源、指标、条件及原文位置。
5. 核对主张与实验的支持范围，写明作者判断、论文报告结果和 Agent 推断的区别。图中数值必须来自实际查看的图像或文本，不能根据标题、图注或记忆补写。
6. 将一个方法及其联系，或一项主张及支持实验，作为一次可检查的增量提交。需要修正时追加修订记录。
7. 结束本篇，记录抽取覆盖范围、未解决的身份或证据问题，以及新增、复用和修订的对象。

被选中的参考文献若暂不阅读，只补充已知的 Paper 信息与有依据的引用联系。当前论文对外部方法的介绍可以作为当前论文中的理解来源，但不冒充对被引论文全文的阅读结果。

## 5. 第四步：检查首篇，再处理 PatchTST

先独立检查首篇试抽，修正工具或抽取约定，再进入 `2023-PatchTST`。检查者回看原文，而不是仅接受抽取 Agent 的自评；首轮可由人工完成。复核发现的问题和修改过程一并保存。

第二篇沿用同一读取与写入流程，重点观察以下行为：

- 对遇到的既有方法、资源和指标，先检索再决定复用；记录复用理由和未匹配到的候选。
- 论文特有的 Claim、Experiment、Condition 和 ResourceRecord 分别保存，不因名称相同而合并。
- 比较结果前，核对版本、数据切分、输入或预测设置、指标口径及基线配置；差异依据来自实际原文。
- 若建立 `DIFFERS_FROM`、`QUALIFIES`、`CHALLENGES` 等跨论文关系，明确双方主张、条件和依据，不预设两篇之间一定存在某种关系。
- 将前面仅有元数据的 Paper 补成已读论文时保留同一 ID，并检查既有引用和实体联系仍然可用。

两篇完成后，用具体问题检查图谱是否保存了可复用理解，例如：某项主张依据哪张表、两个同名资源的用法有何区别、哪些实验条件影响结果比较。答案需要返回节点和证据路径，不能仅凭流畅回答判断图谱质量。

## 6. 第五步：扩展到其余论文，整理稳定 operator

首两篇的流程可用后，再逐篇扩展其余材料。一个候选阅读顺序是：

```text
DLinear → PatchTST → LightRAG → GraphRAG → HippoRAG 2 → HippoRAG
```

这模拟从当前关注的工作追读比较对象或前作，不按发表时间强制排序。后四篇的具体顺序可由实际阅读需要调整，并在运行记录中保存；跨论文边是否建立由证据决定，不事先按这条顺序预造关系。

扩展时重点观察：不同称呼能否找到同一对象、占位论文能否补全、共享对象能否保留多篇论文的不同使用经验、后续理解是否需要修订旧描述。记录操作中反复出现的稳定步骤，再整理成后续知识库扩展可复用的 operator。

首轮不要求实现完整的文献管理产品，也不要求给每种关系配齐案例。若某种判断仍依赖临时人工处理，先保留问题和实例，不急于固化为通用算子。

## 7. 过程记录、验收与实施前待定项

抽取产物与 `data/raw/` 的材料分开保存。建议在确定运行方案后使用 `data/processed/e08/extraction/<run_id>/`，以 YAML 保存运行清单、逐次增量、回执和复核记录；pi session 沿用其配置目录的原生记录。模型、提示词、工具版本、材料哈希、阅读顺序与调用成本放在运行记录中，不要求全部展开成图节点属性。

每次增量至少能回溯：读了什么、查过哪些候选、选择复用或新建的理由、修改了什么、依据在哪里、事务是否成功。暂不确定的对象和关系单独记下，后续确认时能找到原始问题。

| 检查层次 | 首轮验收内容 |
| --- | --- |
| 材料与定位 | 固定版本；anchor 可回读；表格与图片可打开；S2 与正文来源不混淆 |
| 实体身份 | 复用与新增有理由；alias 不误合并；论文局部记录和共享对象的边界正确 |
| 语义与证据 | 主张保留关键条件；关系有实际依据；作者声明、Agent 归纳与外部验证可区分 |
| 增量存储 | 小块事务可重放；补全保留 ID；多角色关系和列表追加不丢信息；修订可回溯 |
| 跨篇复用 | 第二篇能通过工具找到已有经验，并保留新论文带来的条件和差异 |

首轮优先复核核心主张及其支持链、实体合并、alias 追加和共享节点修订。记录节点或关系数量用于观察过程，不把数量、Schema 合法性或 anchor 存在本身作为质量结论。正式质量指标、对照方法和预算比较留待 benchmark 讨论，不由本计划预设。

`aliases` 字段约定、同端点多角色关系的表示方式、工具划分与 `submit` 参数结构已确定（见 Graph Model、2.3 与第 3 节）。实施前还需确定三项内容：

1. 首篇覆盖范围、模型和调用预算。
2. anchor 的精确区间口径，以及 `read_paper`、`find_entities`、`inspect_node` 等工具的具体返回格式。
3. 真实数据的图谱运行范围、抽取产物位置与首两篇复核方式。

下一步先落实这些约定和最小工具，再完成 DLinear 的一次有记录的试抽；检查结果后继续 PatchTST，不直接批量运行六篇的抽取。
