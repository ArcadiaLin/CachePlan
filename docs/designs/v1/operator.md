# 查询算子

日期：2026-09-28。状态：原型已在 `experiments/e08/notebooks/06_extract_prepare.ipynb` 第二节实现，参数为暂定值；查询质量的系统测试待六篇论文入库后进行。

抽取 Agent 在写入图谱前，先用查询算子查找图中是否已有同一对象，据此复用已有节点并连边，或新建节点。本文记录两个算子的输入、输出与内部机制。数据模型见 [graph_model.md](graph_model.md)；检索算子在论文中的定位见 [查询算子：候选查找的定位与实体身份问题](../open-questions/2026-09-28-entity-lookup-and-identity.md)。

| 算子 | 查找对象 | 查询输入 |
|---|---|---|
| `find_entities` | 有名称的共享节点：Paper、Method、MethodConcept、Task、Resource、Metric | 原文中的称呼 |
| `find_statements` | ClaimConcept、Issue，以及各论文的 Claim（只查不复用） | 一句命题或一个问题 |

Contribution、ResourceRecord、Experiment、Observation 属于当前论文，总是新建，不做复用检索。

## 共同约定

- **逻辑接口与物理实现分离。** Agent 只提供查询内容和可选的类型；使用哪些索引、如何组合，由算子内部决定，对 Agent 不可见。
- **只提供候选，不做判断。** 返回排好序的候选及其证据，不给置信度，不设阈值。是否为同一对象，由 Agent 结合定义、来源、版本和邻接关系判断。
- **多路召回，按名次融合。** 各通道分别召回，用 Reciprocal Rank Fusion（RRF）合并。只用名次，不比较各通道量纲不同的原始分数（BM25 分数没有上界，向量分数是映射到 $[0, 1]$ 的 cosine）。
- **证据随候选返回。** 每个候选附带召回它的每个通道的名次和原始分数，并带定义、`note` 和一跳邻接关系，供 Agent 对照。
- **`note` 不参与检索，但随候选返回。** 排序回答的是"是不是查询所指的对象"，依据名称和定义；note 写的是"不是什么、使用时注意什么"。若参与排序，写着"不要与 X 合并"的节点在查询 X 时反而会被提前。区分用的提醒只有在 Agent 看候选时出现才起作用。

参数暂定值：

| 参数 | 值 | 含义 |
|---|---|---|
| `POOL` | 20 | 每个通道召回的条数 |
| `RRF_K` | 10 | RRF 的平滑常数。每路只有 20 条，常用的 60 会让名次几乎不起作用，排序只剩"被几个通道召回" |
| `TOP_N` | 5 | 融合后返回的候选数 |

## `find_entities`

### 输入

```python
find_entities(mention, description=None, entity_type=None, n=5)
```

| 参数 | 说明 |
|---|---|
| `mention` | 原文中的称呼，如 `ETTh1`、`gpt-3.5-turbo-1106`、`RevIN` |
| `description` | 可选。Agent 读原文后写的一句说明，与节点的 `description` 是同一种文字，如 RevIN → `reversible instance normalization applied to model inputs and outputs`。只给称呼时，只能依靠名称和整体语义查找，区分度较低 |
| `entity_type` | 可选。主 Label 或次级 Label，如 `Method`、`Dataset`、`Model` |

### 内部机制

**Stage 1：标识解析。** 将 mention 与节点的 `name` / `title` / `aliases` 比较，命中即为强证据：

| 命中方式 | 规则 | 例子 |
|---|---|---|
| `name` / `alias` | 去首尾空白、转小写后相等 | `LTSF` 命中 Long-term time series forecasting 的 alias |
| `name (normalized)` / `alias (normalized)` | 只保留字母和数字的小写串相等 | `Llama 3 8B Instruct` 命中 `Llama-3-8B-Instruct` |

不做缩写还原：缩写对应什么只能查对照表，而这张表就是 aliases。Stage 1 精度高、召回低，不参与融合排序，命中的候选固定排在最前。alias 不是唯一键，命中的候选可能不止一个。

**Stage 2：混合召回与融合。** 无论 Stage 1 是否命中都执行：命中后 Agent 仍需要看到相近的节点，例如查 ETTh1 时的 ETT、查某一型号时同系列的其他型号。三个通道各召回 `POOL` 条，每个通道比较的字段不同：

| 通道 | 查询侧 | 节点侧 | 方式 |
|---|---|---|---|
| `lexical_name` | mention 的每个词，同时做原词、前缀（`etth1*`）、模糊（`etth1~`，编辑距离 ≤ 2）匹配 | `name`、`title`、`aliases`（全文索引 `entity_names`） | BM25 |
| `lexical_text` | description 的词；未给 description 时不执行 | `description`（全文索引 `entity_texts`） | BM25 |
| `semantic` | 任务说明 + `mention: description` 的向量 | `name`、`aliases`、`description` 拼成的文本的向量（向量索引 `entity_vectors`） | cosine |

查询侧的任务说明为：

```text
Instruct: Given a mention of a dataset, method, task or metric in a research paper, retrieve the entry that refers to the same object
Query:<mention>: <description>
```

三个通道按 RRF 融合：

$$
\text{rrf}(e) = \sum_{c \in \{\text{lexical\_name},\ \text{lexical\_text},\ \text{semantic}\}} \frac{1}{k + r_c(e)}
$$

$r_c(e)$ 是候选 $e$ 在通道 $c$ 中的名次，未被召回的通道不计。`entity_type` 在各通道内部过滤；向量通道先多取 `POOL × 5` 条再过滤，保证过滤后数量足够。

**截断。** Stage 1 命中的在前，其后按 RRF 降序（同分按 id），取前 `n` 个。

### 输出

候选列表，每个候选：

```json
{
  "id": "mc_0025",
  "labels": ["MethodConcept"],
  "name": "Instance normalization",
  "aliases": null,
  "description": "Normalize each input instance individually using statistics computed from that instance alone ...",
  "note": null,
  "neighbors": [],
  "evidence": {
    "lexical_text": {"rank": 1, "score": 4.793},
    "semantic": {"rank": 1, "score": 0.791}
  }
}
```

- `evidence` 只列出召回该候选的通道。Stage 1 命中时为 `"identifier": {"rank": 1, "match": "alias"}` 这类形式。
- `neighbors` 是一跳关系，箭头表示方向，如 ETTh1 的 `PART_OF → ETT`、ETT 的 `PART_OF ← ETTh1`。它帮助 Agent 分辨层级，并确认已有哪些边。

## `find_statements`

### 输入

```python
find_statements(text, description=None, kind=None, n=5)
```

| 参数 | 说明 |
|---|---|
| `text` | Agent 从原文整理出的一句命题或一个问题 |
| `description` | 可选，只对问题有意义：问题的范围与条件 |
| `kind` | 可选，`ClaimConcept`、`Issue` 或 `Claim` |

### 内部机制

命题没有称呼，因此没有 Stage 1，也没有名称通道，只有两路召回，各取 `POOL` 条，按 RRF 融合后截取前 `n` 个：

| 通道 | 查询侧 | 节点侧 | 方式 |
|---|---|---|---|
| `lexical_text` | text 与 description 的词 | `text`、`description`（全文索引 `statement_texts`） | BM25 |
| `semantic` | 任务说明 + text（+ description）的向量 | ClaimConcept、Claim 的 `text`；Issue 的 `text` + `description`（向量索引 `statement_vectors`） | cosine |

查询侧的任务说明为：

```text
Instruct: Given a claim or research question from a paper, retrieve statements that express the same proposition or ask the same question
Query:<text>
<description>
```

**为什么也查 Claim。** Claim 属于论文局部节点，不复用。但第二篇论文说出与第一篇相同的命题、而图中还没有对应的 ClaimConcept 时，只有查到第一篇的 Claim，Agent 才知道应新建 ClaimConcept，并把两条 Claim 都用 `EXPRESSES` 连上去。

**ClaimConcept 为什么没有 description。** 它的 `text` 就是保留必要适用范围的命题，条件写在命题里。不同论文的说法、条件和依据通过 `EXPRESSES` 连接的 Claim 保存。Issue 的问题文本很短，范围和争议所在写在 description 中，因此 Issue 的向量包含 description。

### 输出

候选列表，每个候选：

```json
{
  "id": "claim_0003",
  "labels": ["Claim"],
  "text": "On nine LTSF benchmarks, a one-layer linear model outperforms existing Transformer-based models ...",
  "description": null,
  "note": null,
  "reusable": false,
  "papers": ["paper_0001"],
  "neighbors": ["EXPRESSES → Simple linear models can match or outperform ...", "HAS_CLAIM ← Are Transformers Effective ..."],
  "evidence": {
    "lexical_text": {"rank": 1, "score": 1.414},
    "semantic": {"rank": 2, "score": 0.906}
  }
}
```

- `reusable`：Claim 为 `false`，ClaimConcept、Issue 为 `true`。
- `papers`：仅 Claim 有值，为经 `HAS_CLAIM` 连接的论文。
- 措辞相近不等于同一命题：条件、对象或口径不同的两条主张不应合并。

## 依赖的索引与派生属性

在 06 notebook 1.2、1.4 中由 `ensure_schema()` 与 `sync_embeddings()` 建立和维护。

| 索引 | 类型 | 覆盖节点 | 字段 | 分词 / 相似度 |
|---|---|---|---|---|
| `entity_names` | 全文 | 共享节点 | `name`、`title`、`aliases` | `standard-no-stop-words` |
| `entity_texts` | 全文 | 共享节点 | `description` | `english` |
| `statement_texts` | 全文 | ClaimConcept、Issue、Claim | `text`、`description` | `english` |
| `entity_vectors` | 向量 | 共享节点 | `embedding` | cosine，4096 维 |
| `statement_vectors` | 向量 | ClaimConcept、Issue、Claim | `embedding` | cosine，4096 维 |

- **分词方式。** 名称索引保留默认分词：名称多是专名和缩写，而且前缀、模糊查询词不经过分词，索引中保留原词形才能对上。定义和陈述索引用 `english`：去掉停用词并做词形还原，减少 to、and、model 等泛用词在长文本上累积的噪声。
- **向量。** Qwen3-Embedding-8B（vLLM，`infra/vllm-qwen3-embed/`），写入侧不加任务说明，查询侧加。每个节点存 `embedding` 和 `embedding_key`（模型名与输入文本的哈希）。`sync_embeddings()` 只为缺少向量或 key 不一致（文本修改、更换模型）的节点补算，每次写入图谱后调用。
- `embedding`、`embedding_key` 是检索用的派生属性，不属于 graph_model 的内容属性。

## 已知问题与待定事项

- **通道之间并不独立。** `lexical_text` 与 `semantic` 都读节点的 description，被两路同时召回的候选有一部分属于重复计数，可能让弱相关候选挤进前 `n`。修法（降权或截断 lexical_text）待有数据后决定。
- **定义通道不使用 mention。** 整体资源的定义往往列出其组成部分，例如 ETT 的定义中有 ETTh1。改为只用 description 后，查询 ETTh1 时 ETT 从第 2 名降到第 4 名；不过 ETTh1 的 `PART_OF → ETT` 仍在邻接关系中可见。
- **只给称呼时，语义通道区分度低。** 需要在 Agent 的工具说明中约定：查询时尽量附上一句 description。
- **待测试。** 漏找率与漏找类型、融合参数、候选数量，都等六篇论文入库后，用抽取运行中记录的真实查询和 Agent 的复用决定来检验。
