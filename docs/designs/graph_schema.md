# 论文理解经验 Graph Model

本稿以已有抽取内容为起点，保留**论文（Paper）、自述贡献（Contribution）、方法（Method）、主张（Claim）、实验（Experiment）和资源（Resource）**之间的联系。

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

设计草案，尚未实施。抽取内容依据 [Layer4 v3](../discussions/2026-09-13-layer4-schema-proposal.yml)，实验范围沿用 [实验抽取设计](experiments.md)。
下文 Node 和 Relationship 使用 Cypher pattern 展示结构，Query 使用完整查询语句；所有取值仅为示意，空字符串、空列表与示例布尔值均不是默认值。

## Node

Node 表示对象或记录，Label 描述其类别，Property 描述其属性。例如 `(:Paper {title: "", abstract: ""})` 中，`Paper` 是 Label，`title` 和 `abstract` 是 Property。

- 研究撰写相关：`Paper`、`Contribution`、`Method`、`Claim`。
- 实验描述相关：`Experiment`、`Metric`、`Condition`。
- 使用资源相关：`Resource`、`ResourceRecord`。
- 原文内容相关：`ContentUnit`。

### Paper

一篇论文在某次抽取中的记录，也是访问该次论文理解结果的入口。`paper_id` 标识论文，`id` 区分抽取修订。

```cypher
(:Paper {
    id: "<record_set_id>::<paper_id>",
    paper_id: "<paper_id>",
    source_type: "paper",
    title: "",
    authors: ["<author>"],
    year: "2025",                         // STRING，沿用抽取格式
    venue: "",
    abstract: "",
    arxiv_id: "",
    acl_id: "",
    doi: "",
    url: "",
    ss_id: "",                            // 可选，有外部来源时填写

    paper_type: "benchmark",
    research_problem: "",
    target_domain: ["<domain>"],
    limitations_json: "[]",               // 保留条目与各自证据
    future_work_json: "[]",

    section_outline_json: "[]",
    has_appendix: true,
    has_supplementary_material: false,
    citation_context_json: "[]",           // 原始逐上下文标注
    unresolved_references_json: "[]",      // 库外或尚未解析的引文
    cites_references_total: 61,
    cites_anchored: 22,
    cites_resolved_in_corpus: 1,

    input_format: "pdf",                  // pdf / latex / html
    pdf_path: "<path>/paper.pdf",
    markdown_path: "<path>/paper.md",      // MinerU 生成的原文定位基准
    markdown_sha256: "<sha256>",          // 固定这份 Markdown 的内容版本
    content_list_path: "<path>/content_list.json",
    source_artifacts_json: "{}",           // 元数据及材料下载记录
    extracted_from: ["<paper_id>"],
    last_checked: "<ISO 8601>"
})
```

### Contribution

作者明确声明的一项贡献，来自摘要、引言、结论等位置。保存作者说法，不由抽取器补写贡献，也不将新颖性声明视为已验证事实。

```cypher
(:Contribution {
    id: "<record_set_id>::atomic_extracts.contributions[0]",
    text: "We introduce ...",
    position: 0                           // INTEGER，原列表顺序，从 0 开始
})
```

Contribution 回答“作者声明了什么贡献”；Claim 承接需要关联支持依据的主张。二者可以语义重叠，分别保留抽取条目；不因文字相似合并，也不要求每项贡献关联实验。

### Method

论文中描述的一项具名方法，保持篇内记录粒度。

```cypher
(:Method {
    id: "<record_set_id>::<method_id>",
    method_id: "<paper_id>::method::1",
    name: "<method name>",
    aliases: ["<alias>"]
})
```

同名方法不自动跨论文合并；本文提出、沿用或比较该方法，由 `HAS_METHOD.role` 表达。

### Claim

论文的一条主张，来源定位与支持实验分别保存。

```cypher
(:Claim {
    id: "<record_set_id>::<claim_id>",
    claim_id: "<paper_id>::claim::1",
    text: "<claim text>",
    support_strength: "partial"           // direct / partial / claimed_only
})
```

`support_strength` 是整条主张的总体判断，判断来源保留在 `field_status_json`；不能复制到每条 `SUPPORTED_BY` 并解释为逐实验评分。

### Experiment

论文报告的一项实验活动，将资源、指标、条件和结果位置组织到同一实验范围内。

```cypher
(:Experiment {
    id: "<record_set_id>::<experiment_id>",
    experiment_id: "<paper_id>::exp::1",
    task: "<experimental task>",
    subjects_json: "[]",                  // 被测模型、系统或方法的原始描述
    baselines_json: "[]"                  // 对照对象的原始描述
})
```

`20 prominent LLMs` 这样的集合表述保持原文，不据此生成 20 个 Node。具名被测对象完成对齐后的 Relationship 另行定义。

### Resource

可供跨论文连接的资源身份；具体画像与观察存入 ResourceRecord。

```cypher
(:Resource {
    id: "<resolved_resource_id>",
    resource_id: "<resolved_resource_id>",
    name: "<display name>"                // 可选显示名
})
```

未完成对齐时使用带论文／记录集作用域的局部 ID。名称、规范名或仓库 URL 相同均不足以单独判定同一资源；同一仓库可能同时提供数据、代码和工具。

### ResourceRecord

某次抽取或观察对资源的描述，经 `DESCRIBES` 连接 Resource。同一资源可以有来自不同论文、仓库快照或观察时间的多份记录。

```cypher
(:ResourceRecord {
    id: "<record_set_id>::resource_records[0]",
    resource_id_raw: "<resource_id from extraction>",
    name: "<name in source>",
    name_normalized: "<normalized name>",
    aliases: ["<alias>"],
    kind: "dataset",                      // dataset / benchmark / code / model / tool
    description: "",

    anchor_github: "<owner>/<repo>",
    anchor_huggingface: "<type>/<org>/<name>",
    anchor_doi: "",
    anchor_url: "",

    profile_task: "",
    profile_domain: ["<domain>"],
    profile_languages: ["en"],
    profile_scale: "<scale in source>",
    profile_splits_json: '[{"name":"test","size":100}]',
    profile_evaluation_metrics: ["<metric name>"],
    profile_scoring: "program",           // program / llm_judge / human / mixed / unknown
    profile_prerequisites: ["<prerequisite>"],

    access_type: "public",                // public / request_only / restricted / missing / unknown
    access_url: "",
    access_license: "",

    material_repo_exists: true,
    material_repo_non_empty: true,
    material_has_readme: true,
    material_has_dependency_manifest: true,
    material_has_entrypoint: true,
    material_declared_license: "",
    material_last_commit_at: "<ISO 8601>",
    material_observed_by: "github_api",
    material_observed_at: "<ISO 8601>",
    material_notes: "",

    availability_status: "available",     // available / partial / missing / broken / empty / unknown
    availability_source: "external_observation", // paper_claim / external_observation / inferred
    availability_observed_by: "github_api",
    availability_observed_at: "<ISO 8601>",
    availability_notes: "",

    extracted_from: ["<paper_id>"],
    registry_entry: "<registry entry>",
    registry_status: "matched",           // matched / split_by_spelling / needs_context / unregistered
    last_checked: "<ISO 8601>"
})
```

`profile_splits_json` 描述资源有哪些切分；本次实验用了哪个切分、子集和版本，属于 `USES` 的 Property。ResourceRecord 不等同于资源版本。

`access_license` 与 `material_declared_license` 分别保留论文／获取信息与仓库声明。材料检查和可获得性各自保留来源、观察者与时间；发现仓库或入口不表示成功执行或复现。

### Metric

实验或资源画像使用的指标身份；同名指标须确认定义和口径一致后才能共享。

```cypher
(:Metric {
    id: "<resolved_or_scoped_metric_id>",
    name: "<metric name>",
    aliases: ["<alias>"]
})
```

### Condition

具体实验的一项自由名值条件，保留独立来源定位。

```cypher
(:Condition {
    id: "<record_set_id>::<experiment_id>::conditions[0]",
    dimension: "context_length",
    values: "4k / 8k / 16k / 32k / 64k / 128k" // STRING，保留原文
})
```

不同实验的同名条件分别保存；不建立全局维度实体，也不拆分 `8 × A100` 等自由取值。

### ContentUnit

实验结果所指向的原文表或图。`label` Property 是论文中的表图编号，与 Node 的 Label 不同。

```cypher
(:ContentUnit {
    id: "<record_set_id>::<table_id>",
    unit_id: "<table_id>",
    kind: "table",
    label: "Table 2",
    caption: "<caption>",
    section_id: "sec-4",
    paragraph_index: 58,
    parsed: true,                         // 仅表示表体已解析为行列
    body_kind: "html",                    // html / markdown / image
    md_span: [412, 455]                    // v3 的 Markdown 行区间，非字符区间
})

(:ContentUnit {
    id: "<record_set_id>::<figure_id>",
    unit_id: "<figure_id>",
    kind: "figure",
    label: "Figure 1",
    caption: "<caption>",
    section_id: "sec-1",
    paragraph_index: 12,
    parsed: false,                        // 当前只登记图题与路径
    image_path: "<path>/images/fig1.jpg"
})
```

初版不预建数值 Result；`RESULT_AT` 指向表图，按需抽取数值的回写方式待定。

### 公共 Property：身份与抽取记录

所有 Node 都有非空字符串 `id`。除可共享的 Resource、Metric 外，上述 Node 均属于具体 `record_set_id`，并具有以下公共 Property；各 Label 示例不再重复列出。

```cypher
(n {
    id: "<record_set_id>::<local id or item path>",
    record_set_id: "<immutable record set id>",
    schema_version: "<extraction schema version>",
    pipeline_run_id: "<run id>",
    extraction_path: "<path in extraction output>",
    model: "<extraction model>",
    prompt_version: "<prompt version>",
    inputs_digest: "sha256:<digest>",
    record_written_at: "<ISO 8601>",
    observed_at: "<ISO 8601>",
    source_version_at: "<ISO 8601>",
    unresolved_refs_json: "[]"             // 尚未解析的非引文引用：字段路径与原值
})
```

`n` 是变量，不是新增 Label。`record_set_id` 区分输入快照、运行和修订；同一输入的不同抽取不能共用记录 ID。刷新追加记录，旧记录不覆盖；不使用 Neo4j 内部 ID 作业务引用。

时间沿用 ISO 8601 字符串，比较时解析；观察时间、来源版本时间、写入时间分别填写，未知时省略。`model` 与 `prompt_version` 不代替材料观察者。

### 公共 Property：原文定位与状态

论文抽取出的记录及语义 Relationship 使用相同的来源 Property。下面以 Claim 展示；结构性归属由 `record_set_id` 和 `extraction_path` 回溯。

```cypher
(:Claim {
    evidence_origin: "paper",              // paper / repository / model_card / dataset_card / external_page
    evidence_source_uri: "<path>/paper.md",
    evidence_source_version: "<OCR artifact version>",
    evidence_source_digest: "sha256:<markdown sha256>",
    evidence_section_id: "sec-4",
    evidence_paragraph_index: 55,
    evidence_char_span: [88, 332],          // v3 原有的段内字符区间
    evidence_md_span: [1200, 1444],         // 补充：最终 Markdown 全文字符区间
    evidence_quote: "<verbatim source text>",
    evidence_locator: "<external locator, when applicable>",
    evidence_refs_json: "[]"               // 多证据项；各自保留适用字段、来源、版本、定位和时间
})
```

`evidence_md_span` 约定为最终 Markdown 解码文本的 Unicode 码点区间，从 0 开始、左闭右开；不得直接复制 v3 的段内 `char_span` 或表体行区间。定位须绑定文档摘要，OCR 重建后重新对齐；该全文偏移映射尚待实现。

Resource 的论文来源通过 ResourceRecord 回溯；外部观察指向实际材料快照。ResourceRecord 的画像来源使用以下 Property，与论文角色 Relationship 的正文依据分别保存：

```cypher
(:ResourceRecord {
    profile_evidence_origin: "repository",
    profile_evidence_source_uri: "<repository snapshot URI>",
    profile_evidence_source_version: "<commit>",
    profile_evidence_source_digest: "sha256:<digest>",
    profile_evidence_locator: "README.md#L12-L30",
    profile_evidence_quote: "<verbatim source text>",
    profile_evidence_source_version_at: "<ISO 8601>",
    profile_evidence_refs_json: "[]"
})
```

画像来自论文时，同样使用 `profile_evidence_section_id`、`profile_evidence_paragraph_index`、`profile_evidence_char_span`、`profile_evidence_md_span` 定位。

Paper 与 ResourceRecord 完整保留原始字段状态；子 Node 与 Relationship 通过 `extraction_path` 回查。

```cypher
(:Paper {
    field_status_json: '{"metadata.doi":{"absence":"not_found","observed_by":"arxiv_api"}}'
})

(:ResourceRecord {
    field_status_json: '{"availability.status":{"source":"external_observation","observed_by":"github_api"}}'
})
```

`source` 沿用 `paper_claim / external_observation / inferred`；`absence` 沿用 `not_checked / not_found / not_applicable`。缺值省略 Property 并保留状态，`false + not_applicable` 也省略布尔值；`not_found` 仅表示在已声明范围内未找到。

Property 使用标量或同类型简单值列表；嵌套结构展开为 Property、转换为 Node／Relationship，或存入 `*_json` 字符串。JSON 内容不作为普通图查询谓词；类型限制见 [Neo4j Property 类型](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/)。

## Relationship

Relationship 连接两个 Node，具有方向、一个 Type，以及描述本次联系的 Property。

```cypher
// 格式示意：CITES 是 Type，context、section 是 Property。
(:Paper {title: "BERT"})
    -[:CITES {
        context: "<citation context>",
        section: "introduction"
    }]->
(:Paper {title: "Attention Is All You Need"})
```

### 论文、贡献与方法

```cypher
(:Paper)-[:HAS_CONTRIBUTION]->(:Contribution)

(:Paper)
    -[:HAS_METHOD {
        role: "proposed"                  // proposed / reused / extended / compared
    }]->
(:Method)

(:Method)-[:DERIVED_FROM]->(:Method)
(:Method)-[:DERIVED_FROM]->(:Resource)
(:Method)-[:PRODUCES]->(:Resource)
```

`DERIVED_FROM` 仅连接显式来源；`PRODUCES` 对应方法的资源产物，不表示已检查可用。Contribution 不自动推导到 Method 或 Resource 的语义 Relationship。

### 主张、实验与结果

```cypher
(:Paper)-[:HAS_CLAIM]->(:Claim)
(:Paper)-[:REPORTS]->(:Experiment)
(:Claim)-[:SUPPORTED_BY]->(:Experiment)

(:Experiment)
    -[:HAS_CONDITION {
        position: 0
    }]->
(:Condition)

(:Experiment)
    -[:MEASURED_BY {
        name_raw: "<metric name in source>",
        scoring: "program"                // program / llm_judge / human / mixed / unknown
    }]->
(:Metric)

(:Experiment)-[:RESULT_AT]->(:ContentUnit)
(:Paper)-[:HAS_CONTENT]->(:ContentUnit)
```

`SUPPORTED_BY` 保留抽取记录中的支持判断及其来源；结构连通不代表支持关系已核实。`MEASURED_BY.scoring` 属于本次实验。

### 实验使用资源

```cypher
(:Experiment)
    -[:USES {
        role: "evaluation_target",        // training_data / evaluation_target / analysis_input / tooling / unknown
        split: "test",
        subset: "<subset in source>",
        version: "<version used>",
        resource_record_id: "<resource record id>", // 存在对应描述记录时填写
        mapping_origin: "resources_used"
    }]->
(:Resource)
```

同一实验可以以不同角色、切分或版本多次使用同一 Resource，分别保存 Relationship。版本未知时省略，不填“最新版”；仓库检查时观察到的 commit 不自动成为实验使用版本。

当前沿用 v3 的角色词表；`evaluation_target` 不单独判定资源是评测输入还是被测对象，细分 `EVALUATED_ON`／`EVALUATES` 仍待确定。

### 资源身份、描述与论文角色

```cypher
(:Paper)-[:HAS_RESOURCE_RECORD]->(:ResourceRecord)
(:ResourceRecord)-[:DESCRIBES]->(:Resource)

(:ResourceRecord)
    -[:HAS_METRIC {
        name_raw: "<metric name in profile>"
    }]->
(:Metric)

(:Paper)
    -[:RELATES_TO {
        role: "introduced",               // introduced / used / evaluated / cited_only / unknown
        split: "<split in paper>",
        subset: "<subset in paper>",
        version: "<version in paper>",
        modification: "<modification in source>",
        citation_context_ids: ["<context_id>"],
        resource_record_id: "<resource record id>"
    }]->
(:Resource)
```

`RELATES_TO` 保存论文级联系，`USES` 保存实验级使用；不将论文级角色和条件直接复制到实验。由 `used_in_experiments` 补出的 `USES` 使用 `mapping_origin: "paper_relation"`，角色缺失时为 `unknown`。

以下两份记录描述同一资源，分别保留论文声明与外部观察；它们不是两个资源版本。

```cypher
(:ResourceRecord {id: "rr-paper", availability_source: "paper_claim"})
    -[:DESCRIBES]->
(r:Resource {id: "res-D", resource_id: "res-D"})
    <-[:DESCRIBES]-
(:ResourceRecord {id: "rr-repository", availability_source: "external_observation"})
```

### 论文引用

```cypher
(:Paper)
    -[:CITES {
        reference_index: 12,
        anchor_type: "arxiv",              // arxiv / doi / url / none
        anchor: "<resolved external identifier>",
        context_ids: ["<context_id>"],
        roles: ["benchmark_source"],       // 多个引用上下文的角色汇总
        context: "<citation context>",     // 单一上下文时可展开
        section: "<section title>"         // 单一上下文时可展开
    }]->
(:Paper)
```

`CITES` 只连接已解析的库内目标记录；库外引用保留在 `unresolved_references_json`。多上下文的文本、位置与角色配对保留在 `citation_context_json`，不能拼成单一 `context` 或将一个锚点广播给上下文内所有参考文献。

目标追加修订时，旧 `CITES` 不静默改指。反向遍历即可查询谁引用了本文，无需另存反向 Relationship。

### 公共 Property：关系身份与来源

每条 Relationship 都有非空 `id`、`record_set_id` 和产生它的 `extraction_path`；语义 Relationship 还携带原文定位 Property。以下使用 `USES` 示意公共字段：

```cypher
(:Experiment)
    -[:USES {
        id: "<record_set_id>::<relationship item path>",
        record_set_id: "<record_set_id>",
        extraction_path: "atomic_extracts.experiments[0].resources_used[0]",
        extraction_paths: ["<path 1>", "<path 2>"], // 多入口对应同一条联系时保留
        evidence_origin: "paper",
        evidence_source_uri: "<path>/paper.md",
        evidence_source_version: "<OCR artifact version>",
        evidence_source_digest: "sha256:<markdown sha256>",
        evidence_section_id: "sec-4",
        evidence_paragraph_index: 55,
        evidence_char_span: [88, 332],
        evidence_md_span: [1200, 1444],
        evidence_quote: "<verbatim source text>",
        evidence_refs_json: "[]"
    }]->
(:Resource)
```

同一产物重复导入按记录 ID 保持幂等，不仅按起点、Type、终点覆盖。篇级资源列表与 `paper_relation` 内容一致时合并入口并保留路径；有冲突时保留差异。实验显式使用条目存在时，不再通过论文级引用重复补建。

来源缺口要补足或登记待补；`extraction_path` 不能代替原文依据。未解析目标留在 `unresolved_refs_json`，不猜测端点；新 Type 需明确端点、方向、语义及依据，不自动生成相似或矛盾关系。

## Query

查询使用参数选择论文记录／记录集；跨修订统计论文数量时按 `paper_id` 去重。以下为读取模式示例，尚未在数据库执行。

### Pattern matching：读取论文自述贡献

```cypher
MATCH (:Paper {id: $paper_record_id})-[:HAS_CONTRIBUTION]->(c:Contribution)
RETURN c.text AS contribution,
       c.evidence_source_uri AS source,
       c.evidence_md_span AS span,
       c.evidence_quote AS quote
ORDER BY c.position
```

### Traversal：沿共享资源找到其他论文的实验

```cypher
MATCH (p1:Paper {id: $paper_record_id})-[:REPORTS]->(e1:Experiment)
      -[u1:USES]->(r:Resource)<-[u2:USES]-(e2:Experiment)
      <-[:REPORTS]-(p2:Paper)
WHERE p1.paper_id <> p2.paper_id
  AND p2.record_set_id IN $record_set_ids
RETURN DISTINCT p2.paper_id AS paper,
       e2.task AS task,
       r.resource_id AS resource,
       u1.role AS source_role, u2.role AS other_role,
       u1.version AS source_version, u2.version AS other_version,
       u1.split AS source_split, u2.split AS other_split,
       u1.subset AS source_subset, u2.subset AS other_subset
```

共享资源提供关联入口，实验是否可比还需结合角色、版本、切分和条件判断。

### Path query：返回主张到结果位置的完整路径

```cypher
MATCH (:Paper {id: $paper_record_id})-[:HAS_CLAIM]->(c:Claim)
MATCH path = (c)-[:SUPPORTED_BY]->(:Experiment)-[:RESULT_AT]->(:ContentUnit)
RETURN c.text AS claim, path
```

沿引用关系查询一至三跳路径，限定允许经过的记录集：

```cypher
MATCH path = (p:Paper {id: $paper_record_id})-[:CITES*1..3]->(cited:Paper)
WHERE all(n IN nodes(path) WHERE n.record_set_id IN $record_set_ids)
RETURN cited.paper_id AS cited_paper, length(path) AS hops, path
```

有界路径语法见 [Neo4j Variable-length paths](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-paths/)。引用可达不表示主张支持或方法沿用。

### 待确定的模型部分

- 发布活动是否需要独立 Release Node，以及 `RELEASES`、`EVALUATES`、`EVALUATED_ON` 的具体语义。
- 资源与指标身份对齐历史、多证据的结构化查询，以及按需数值结果的表示。
- 记录替代、失效与 as-of 选择规则；Neo4j 约束、索引及导入实现。

v3 的示例定位、悬空引用和字段状态下标仍需核对，不能直接作为完整入图测试数据；原文定位存在也不等于抽取语义正确。
