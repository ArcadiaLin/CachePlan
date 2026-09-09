# 协议

## **Living Review 协议**

Agent\-native Review 应该是什么样的结构？

### **分类树 **

（最宏观，最直接的价值）

面向用户使用的资源聚合形态

Agent api \| 问答 \| 关键字、领域查询

给读者的价值体现是: 直观的给出哪一类有哪些论文。分类树可以同时维护**多个 view**（按方法 / 按产出 / 按训练方式/ 按领域）；同一论文在不同 view 下挂载到不同 branch

每个 view 是一棵树，叶子指向 paper 或 method\_cluster。例如

```YAML
view_id: view::by-information-source
name: "按信息来源分类"
source_survey: 2507.01903 §5.1
root: idea-mining
tree:
  - branch: idea-mining-from-internal-knowledge
    description: "仅利用 LLM 内部参数化知识，无外部检索"
    members:
      - paper::meincke-2024
      - paper::haarmann-2024
      - paper::liu-2024-climate
      - paper::chen-2024-ecm

  - branch: idea-mining-from-external-signal
    sub_branches:
      - branch: from-external-knowledge
        description: "通过 KG/citation network/literature 注入外部知识"
        members:
          - paper::wang-2024-scimon       # ← 同一论文
          - paper::li-2024-coi
          - paper::gu-2024
          - paper::yang-2024-moose-chem   # ← 同一论文
      - branch: from-external-environment-feedback
        description: "通过实验反馈/环境闭环"
        members:
          - paper::lu-2024-ai-scientist
          - paper::bran-2023-chemcrow
          - paper::schmidgall-2024-agent-lab

  - branch: idea-mining-from-team-discussion
    sub_branches:
      - branch: ai-ai-collaboration
        sub_branches:
          - branch: feedback-guided
            members:
              - paper::lu-2024-ai-scientist  # ← 跨分支
              - paper::zhou-2024
              - paper::baek-2024-researchagent
          - branch: team-discussion-guided
            members:
              - paper::su-2024-virsci         # ← 同一论文
              - paper::yang-2024-moose-chem   # ← 跨分支
              - paper::li-2024-coi
      - branch: human-ai-collaboration
        members:
          - paper::radensky-2024-scideator
          - paper::garikaparthi-2024-iris
```



```YAML
view_id: view::by-method-paradigm
name: "按方法范式分类"
source_survey: 2505.04651 §4
root: hypothesis-generation
tree:
  - branch: knowledge-driven           # §4.1
    description: "知识图谱 / 网络 / 本体推理"
    members:
      - paper::sybrandt-moliere
      - paper::ghafarollahi-sciagents   # ← 同一论文
  - branch: data-driven-integration    # §4.2
    members: [...]
  - branch: ai-driven-exploration      # §4.3 (RAG + RL)
    members:
      - paper::chen-2024-chemist-x
      - paper::ghafarollahi-sciagents   # ← 跨分支
      - paper::wang-2024-scimon         # ← 跨视角对应
  - branch: text-and-concept-mining    # §4.4
    members:
      - paper::tyagin-dyport
  - branch: simulation-and-modeling    # §4.5
  - branch: interactive-collaborative  # §4.6
  - branch: causal-inference           # §4.7
  - branch: dynamic-adaptive-knowledge # §4.8
  - branch: multi-agent-systems        # §4.9
    members:
      - paper::su-2024-virsci           # ← 在 view A 是 team-discussion-guided
      - paper::baek-2024-researchagent
      - paper::liu-2024-tais
      - paper::ghafarollahi-sciagents   # ← 跨分支
```



**关键观察**：上面两个 view 来自两篇真实综述。同一篇 SciAgents 论文：

- 在 view::by\-information\-source 下被分类到 `external-knowledge`（因为它用 KG）

- 在 view::by\-method\-paradigm 下被分类到 \`knowledge\-driven\` **以及** \`ai\-driven\-exploration\` **以及** \`multi\-agent\-systems\`（一篇论文出现在同一 view 的三个分支）

在经典Survey中类似的图示:





#### **1\.1 实现思路与难度**

在于如何构建 **Canonical Taxonomy**

1. 理想情况: 直接从现有的Review中Extract并结构化。而现实是这样的精品论文很少，在前沿领域就更少了\(而这正是需求最旺盛的领域\)。其次是，Survey中的分类可能会过时会分得不好。我们最终还是要迈向Agentic **Taxonomy **构建。这也是最近的前沿研究问题之一。

2. 不那么理想，但有一些资源的情况: 要考虑 **Canonical Taxonomy 本体对齐**

多篇综述对同一批论文给出了不同的分类体系，且这些体系之间存在三类矛盾

|矛盾类型|例子|
|---|---|
|**同义异名**：同一组论文，不同综述给了不同 branch 名|AI4Research 的 \`team\-discussion\-guided\` = 2505综述的 \`multi\-agent\-systems\`（指向几乎相同的论文集合）|
|**粒度不一致**：一个综述的一个 branch 对应另一个综述的多个 branch|2505 的 `ai-driven-exploration`（含 RAG \+ RL \+ ML）在 AI4Research 里被拆成两个独立 branch|
|**正交维度混用**：同一个 view 内，不同 branch 其实属于不同维度||

3. 最常见，也最不理想的情况: 根本没有现成的 Survey 的分类树可用，需要从头构建本体。

4. **时间因素**的问题: 我们的卖点之一是growing, 随着技术的变化，新论文和新技术的涌入会改变现有的分类树，其分支，枝叶需要随时间演化，根据新加入的论文进行调整，（又是一个研究问题，类似于*动态知识图谱构建*）



### **Contribution Genealogy**

规模化后形成

cite\_graph \| cluster \| domain contribution \| 时序影响力

做一个https://arxiv\.org/abs/2604\.28158: Intern\-Atlas 类似的事情。agent对这篇论文的分析在: [Intern\-Atlas 的启发](https://w0rjakfqsmm.feishu.cn/docx/LFP9dP9b6oU8iLxmET5c35jFnSg?from=from_copylink)

例如

```YAML
cluster_id: method::retrieval-augmented-ideation
name: "Retrieval-Augmented Ideation (RAG-based hypothesis generation)"
canonical_form: >
  使用外部检索（文献/KG/数据）注入到 LLM 生成过程，
  以产生比纯参数化生成更具地基性的假设。
  
  
                 contribution3
                      |          
    某领域------------------------------------>
              |               |
         contribution1        |
                          contribution2

# 这个 cluster 由哪些论文实例化
member_papers:
  - paper_id: paper::wang-2024-scimon
    role: foundational      # foundational / extension / hybrid
    contribution: "提出 inspiration element 粒度的检索"
  - paper_id: paper::li-2024-coi
    role: extension
    contribution: "把检索结果组织为 chain 结构"
  - paper_id: paper::gu-2024
    role: extension
    contribution: "跨域检索 + 结构化组合过程"
  - paper_id: paper::chen-2024-chemist-x
    role: domain-adaptation
    contribution: "RAG 应用到化学反应路径"

# 这个 cluster 和其他 cluster 的关系（谱系图的边）
relations:
  - target: method::pure-llm-ideation
    type: improves_upon
    evidence: "SciMON 论文 §5.2 显示比 zero-shot prompting 高 12% novelty"
  - target: method::multi-agent-debate
    type: hybridizes_with
    evidence: "SciAgents 同时使用检索和多 agent，列入两个 cluster"
  - target: method::knowledge-graph-driven
    type: shares_principles_with
    evidence: "两者都使用结构化外部知识，但 KG 用图 traversal、RAG 用 embedding 检索"

# 时间序与影响力
emergence_year: 2023
peak_activity: 2024
status: active        # active / mature / declining

# 局限（来自论文自述 + LLM 综合）
known_limitations:
  - "检索质量上限决定假设质量上限"
  - "embedding 距离作为 novelty score 对概念重命名不鲁棒"

# 增量监控
monitor:
  arxiv_keywords: ["retrieval-augmented ideation", "RAG hypothesis"]
  citation_threshold: cited_by_count > 50 within 6 months
  trigger_review: when_new_member_paper_added
```



**关键设计原则**：

\- **方法 cluster 由 LLM \+ 综述描述 \+ 引用关系共同生成**

\- **同一篇论文可属于多个 cluster**（例如 SciAgents 同时是 retrieval\-augmented 和 multi\-agent）

\- **边是有类型的**，至少区分：inherits / improves\_upon / hybridizes / contradicts / shares\_principles\_with



#### **2\.1 实现思路与难度**



### **信息深度整合**

论文资源的整合与联系

资源关联 resources\_relation \| intent \| 重要引用发掘 \| 社媒讨论 \| 可验证性\(分领域 CS、economics、medicine\)

在论文关键信息抽取之后,挖掘 关键论文的引用和被引，**Paper–Resource **的关系构建

本质上是我们的 Agent 代工先去整合

```YAML
paper_id: paper::wang-2024-scimon
resource_relations: # introduced | evaluated_on | uses | extends | ...
  - resource_id: dataset::iclr-neurips-ideas
    relation: uses
  - resource_id: benchmark::scimon-bench
    relation: introduced
intent: # 归纳总结
  paper_type: empirical # survey | empirical | benchmark | dataset | method | theory | position
 

social_discusstion:
    platform: x | reddit | huggingface | xiaohongshu
    dicussion: ""

reproducibility： #深度复现: **验证论文可行性+真实性 分领域**
     # 综述：验证引用文章 claim 是否一致 + 领域总结是否严谨
     # 实证：提供资源是否完整： github 是否为空；数据集提供是否完整；超参数；
     #     * 实验规划 + 研究范式/流程设计（用户想要知道其他人如何做的，如何参考；可以同同一作者的多个同范式研究入手解析） -> 规模化预期成果 用户直接检索到相关实验设计 + 形成可总结的研究范式
     #    究入手解析数据）?autoresearch+
     #    * 完整复现
**  参数,....**

provenance:
  mentioned_in_surveys: [2507.01903, 2505.04651]
  extraction_confidence: high
```

**关键设计选择**：

Paper 和 Resource 之间的关系不是平的，至少区分以下四种：

|关系类型|含义|例子|
|---|---|---|
|`introduced`|这篇论文首次发布了这个资源|VirSci 代码由 Su et al\. 2024 发布|
|`evaluated_on`|这篇论文用这个 benchmark 评测自己|AI Scientist 在 NLP\-Idea\-Bench 上汇报分数|
|`uses`|这篇论文使用了这个数据集作为训练/输入数据|SciMON 使用 ICLR\-NeurIPS Ideas Dataset|
|`extends`|这篇论文对已有资源做了扩展或二次标注|某论文在 HypoBench 上加了新维度|

这四种关系在协议中表示为：

```YAML
paper_id: paper::wang-2024-scimon
resource_relations:
  - resource_id: dataset::iclr-neurips-ideas
    relation: uses
  - resource_id: benchmark::scimon-bench
    relation: introduced
```

反向索引挂在 Resource 上：

```YAML
resource_id: benchmark::scimon-bench
introduced_by: paper::wang-2024-scimon          # 唯一，最多一篇首发论文
evaluated_by: [paper::gu-2024, paper::li-2024-coi, ...]  # 使用此 benchmark 评测的后续论文
used_by: [...]
```

## 4\-3 过渡

由 4 深入加工成为 3 需要进行加工过渡层

1、补全 layer 4 的缺失字段

2、layer 4 字段消歧

4、构建关联

```YAML
layer3_processing_contract:
  resource_relations:
    required_layer4_inputs:
      - evidence_edges where predicate in [introduced, uses, evaluated_on, extends]
      - resource_records
      - paper_records.resources_mentioned
    output:
      - paper_resource_graph
      - resource_reverse_index

  important_citation_mining:
    required_layer4_inputs:
      - paper_records.citation_contexts
      - evidence_edges where predicate in [cites, supports, contrasts, extends]
      - citation_api_metadata
    output:
      - important_references
      - citation_roles
      - claim_alignment_candidates

  contribution_genealogy:
    required_layer4_inputs:
      - paper_records.contributions
      - paper_records.methods
      - citation_contexts
      - evidence_edges
      - resource_relations
    output:
      - method_cluster
      - contribution_lineage
      - typed_cluster_edges

  taxonomy_construction:
    required_layer4_inputs:
      - paper.intent
      - paper.methods
      - paper.contributions
      - paper.resources_used
      - survey_branch_mentions
    output:
      - canonical_taxonomy
      - multi_view_classification
      - ontology_alignment

  reproducibility:
    required_layer4_inputs:
      - experiments
      - methods
      - resource_records.availability_check
      - code.agent_callable
      - hyperparameters
      - evaluation_metrics
    output:
      - artifact_completeness_score
      - reproduction_plan
      - reproducibility_risk

  social_discussion:
    required_layer4_inputs:
      - observation_records where observation_type = social_discussion
    output:
      - discussion_summary
      - controversy_points
      - adoption_signal

  domain_verification:
    required_layer4_inputs:
      - claims
      - experiments
      - methods
      - datasets
      - citation_contexts
    output:
      - cs_verification
      - economics_verification
      - medicine_verification
```

### **Resources**

论文提到的、可直接抽取的资源

layer 4 关注单篇文献的提取，允许提取的信息不完整、字段暂时留空

已经完成了 layer4 的 2025 acl 抽取，目前正在进行 acl 2026 抽取，本文档继续丰富模板示例

详细过程和经验参见 

#### 资源结构设计

##### 4\.1 文献资源

摘要 \| 元数据 \| 章节结构 \| 核心观点 Claim \| 术语 \| 实验描述（Method \+ 流程图）\| future work \| contributions \| Cites \+ context

- `contributions` 是论文自述的核心贡献，不是 v0\.1 那种结构化的 \`key\_mechanism\`。后者是**派生的**，应在 Layer 3 构建。

- `cites` / `cited_by` 来自外部 API，不是 LLM 抽取。

- 以下为最新版本数据实例，paper\_record\.yml，

```YAML
paper_record:    # 论文元数据信息
  paper_id: paper::2025.acl-long.803    # 由 ACL 分配的论文 ID 直接生成
  source_type: paper
  metadata:
    title: 'LIFBENCH: Evaluating the Instruction Following Performance and Stability of Large Language Models in Long-Context
      Scenarios'
    authors: []    # author 抽取好像存在点问题
    year: '2025'
    venue: ACL-LONG 2025    # acl 论文组
    arxiv_id: '2411.07037'    # agent 使用 arxiv_mcp 获取，但是有大量论文实际上没有arxiv，或者说arxiv上改过名字，因此检索不到
    acl_id: 2025.acl-long.803
    doi: ''
    url: https://arxiv.org/abs/2411.07037
    pdf_path: data/processed/mineru/acl/2025/acl/2025.acl-long.803/vlm/2025.acl-long.803_origin.pdf
    markdown_path: data/processed/mineru/acl/2025/acl/2025.acl-long.803/vlm/2025.acl-long.803.md
    content_list_path: data/processed/mineru/acl/2025/acl/2025.acl-long.803/vlm/2025.acl-long.803_content_list_v2.json
  content_units:    # 内容抽取集合
    abstract: 'As Large Language Models (LLMs) evolve in natural language processing (NLP), their ability to stably follow
      instructions in long-context inputs has become critical for real-world applications. However, existing benchmarks seldom
      focus on instruction-following in long-context scenarios or stability on different inputs. To bridge this gap, we introduce
      LIFBENCH, a scalable dataset designed to evaluate LLMs'' instruction-following capabilities and stability across long
      contexts. LIFBENCH comprises three long-context scenarios and eleven diverse tasks, featuring 2,766 instructions generated
      through an automated expansion method across three dimensions: length, expression, and variables. For evaluation, we
      propose LIFEVAL, a rubric-based assessment method that enables precise, automated scoring of complex LLM responses without
      reliance on LLM-assisted assessments or human judgment. This method allows for a comprehensive analysis of model performance
      and stability from multiple perspectives. We conduct detailed experiments on 20 prominent LLMs across six length intervals.
      Our work contributes LIFBENCH and LIFEVAL as robust tools for assessing LLM performance in complex and long-context
      settings, offering valuable insights to guide future advancements in LLM development. $^{1}$'
    section_outline:    # 篇章结构
    - level: 1
      title: 'LIFBENCH: Evaluating the Instruction Following Performance and Stability of Large Language Models in Long-Context
        Scenarios'
      line: 1
    ...
    has_appendix: true
    has_supplementary_material: false
    figures: []
    tables: []
  atomic_extracts:
    intent:    # 意图，由agent抽取
      paper_type: benchmark
      research_problem: Evaluating LLM instruction-following capabilities and stability in long-context scenarios.
      target_domain:
      - Natural Language Processing
      - Long-context LLMs
      - Instruction Following
    contributions:    # agent 抽取论文自述的贡献
    - text: We introduce LIFBENCH, a benchmark designed to evaluate instruction-following capabilities in long-context scenarios,
        containing 11 tasks across three scenarios.
    - text: We develop methods for dataset expansion across three perspectives, enabling high scalability in both the quantity
        and length of instructions.
    - text: We propose LIFEVAL, an automatic evaluation method for accurately and comprehensively assessing the quality and
        stability of LLMs' complex responses.
    - text: We conduct extensive experiments across six length intervals, which evaluate and analyze the instruction-following
        capabilities and stability of 20 well-known LLMs.
    claims:    # agent 从摘要中抽取
    - text: LIFBENCH is introduced as a scalable benchmark to evaluate LLM instruction-following capabilities and stability
        across long contexts, comprising three scenarios and eleven diverse tasks with 2,766 instructions.
    - text: LIFEVAL is proposed as a rubric-based automated scoring method that enables precise, automated evaluation of complex
        LLM responses without relying on LLM-assisted assessments or human judgment.
    experiments:    # agent 生成的实验描述
    - text: Evaluated 20 prominent LLMs across six context length intervals (4k to 128k tokens).
    - text: 'Analyzed performance and stability across three perspectives: length, expression, and instruction variables.'
    - text: 'Assessed six core capabilities: Ori, Num, Spat, Fmt, Logic, Recog.'
    limitations:    # agent 抽取的限制
    - text: Programmatic validation constraints limit support for semantic constraints in task scenarios.
    - text: Inference for very long inputs requires significant computational resources and time, limiting dataset scale.
    - text: LIFEVAL reliability depends heavily on scoring rubric design and evaluation program implementation, requiring
        significant manual effort.
    future_work:    # agent 抽取的论文自述 future_work
    - text: Improving programmatic validation to support semantic constraints.
    - text: Expanding the evaluation set using the proposed protocol for more extensive analysis.
    - text: Automating or reducing manual effort in rubric design and evaluation program implementation.
    citation_context:    # 从 mineru ocr 结果获取引用，并获取上下文
      cite:
      - context_id: 2025.acl-long.803::cite::1    # 根据引用次序生成的 id
        raw_citation: (Achiam et al., 2023; Chowdhery et al., 2023; Brown, 2020)
        reference_indices:
        - 1
        - 6
        - 11
        reference_titles:
        - Gpt-4 technical report
        - Language models are few-shot learners
        - 'Palm: Scaling language modeling with pathways'
        context: As Large Language Models (LLMs) continue to make significant strides across practical applications (Achiam
          et al., 2023; Chowdhery et al., 2023; Brown, 2020), their performance in natural language processing (NLP) tasks
          has reached unprecedented levels. These tasks span text generation (Que et al., 2024; Tan et al., 2024; Zhang et
          al., 2024b), complex reasoning (Parmar et al.,
        section: 1 Introduction
        paragraph_index: 6
        sentence: As Large Language Models (LLMs) continue to make significant strides across practical applications (Achiam
          et al., 2023; Chowdhery et al., 2023; Brown, 2020), their performance in natural language processing (NLP) tasks
          has reached unprecedented levels.
        citation_function: background
      ...
      cited_by: []    # 被引用，需要 semantic scholar 来补全
   source_artifacts:    # 论文的源材料，主要从 arxiv 获取，
    arxiv:
      arxiv_id: '2411.07037'    # 首先包括了 arxiv 上的元数据
      version: v3
      url: https://arxiv.org/abs/2411.07037
      metadata_status: available
      metadata_checked_by: arxiv-mcp
      title: 'LIFBench: Evaluating the Instruction Following Performance and Stability of Large Language Models in Long-Context
        Scenarios'
      authors:
      - Xiaodong Wu
      - Minhao Wang
      - Yichen Liu
      - Xiaoming Shi
      - He Yan
      - Xiangju Lu
      - Junmin Zhu
      - Wei Zhang
      submitted: '2024-11-11'
      updated: ''
      primary_category: cs.CL
      categories:
      - cs.CL
      abstract: 'As Large Lan...'
    html_downloaded:    # 如果 arxiv 提供了该论文 html 版本会尝试下载
      exists: true
      status: available
      path: data/processed/layer4/2025.acl-long.803/arxiv/html/2411.07037.html
      url: https://arxiv.org/html/2411.07037
      checked_by: curl
      notes: HTML downloaded successfully via curl from arxiv.org/html/2411.07037.
    tex_source_downloaded:    # 如果 arxiv 提供了改论文的 latex 源码也会尝试下载
      exists: true
      status: available
      path: data/processed/layer4/2025.acl-long.803/arxiv/src/2411.07037.tar.gz
      url: https://arxiv.org/src/2411.07037
      checked_by: curl
      notes: TeX source downloaded successfully as gzip-compressed tar archive. Contains latex/ directory with figures, tables,
        and style files.
resources_introduced: # 论文引入的 resource，详见 resouces_record.yml
- benchmark::lifbench
- tool::lifeval
resources_used: []
cites: []
cited_by: []
source_paper: ''
comparison: ''
```



##### 4\.2 实验资源：

dataset \| benchmark \| code \| model \| tool \| protocol \| skill

```YAML
- resource_record:
    resource_id: benchmark::lifbench
    name: LIFBENCH
    kind: benchmark # dataset | benchmark | code | model | tool | protocol | skill
    aliases:
    - Long-context Instruction Following Benchmark
    description: A scalable benchmark for evaluating LLM instruction-following capabilities and stability in long-context
      scenarios. Comprises three scenarios (List, MultiDoc, OneDoc) with eleven diverse tasks and 2,766 instructions generated
      through automated expansion across length, expression, and variable dimensions.
    paper_relation:
      relation_type: introduced
      evidence: 'Abstract: we introduce LIFBENCH, a scalable dataset designed to evaluate LLMs'' instruction-following capabilities
        and stability across long contexts. LIFBENCH comprises three long-context scenarios and eleven diverse tasks, featuring
        2,766 instructions generated through an automated expansion method.'
      section: Abstract
      citation_context_ids:
      - 2025.acl-long.803::cite::3
    access:
      access_type: public
      url: https://github.com/SheldonWu0327/LIFBench-2024
      license: ''
    availability_check:
      status: available
      checked_by: github_mcp
      checked_at: ''
      notes: GitHub repository SheldonWu0327/LIFBench-2024 verified via GitHub MCP. Python project, 7 stars, last updated
        2025-08-03.
    repository:
      canonical_url: https://github.com/SheldonWu0327/LIFBench-2024
      verification:
        checked_by: github_mcp
        status: available
        notes: Repository exists and is accessible. Described as 'A comprehensive benchmark and evaluation toolkit for assessing
          instruction-following capabilities and stability of LLMs in long-context scenarios.'
    agent_callable:
      can_wrap: false
      estimated_wrapping_difficulty: unknown
      notes: Benchmark dataset and evaluation toolkit; not an agent-wrappable resource.
    provenance:
      extracted_from:
      - 2025.acl-long.803
      extraction_confidence: high
      last_checked: '2026-06-30T18:33:11.498512+00:00'
- resource_record:
    resource_id: tool::lifeval
    kind: tool
    name: LIFEVAL
    aliases:
    - LIFEval
    description: A rubric-based automated scoring and evaluation method for assessing LLM long-context instruction-following
      capabilities. Includes Automated Rubric-based Scoring (ARS), Score-Capability Mapping, and Instruction Following Stability
      (IFS) metrics. Provides programmatic evaluation pipelines for 11 tasks across 3 scenarios.
    paper_relation:
      relation_type: introduced
      evidence: 'Abstract: we propose LIFEVAL, a rubric-based assessment method that enables precise, automated scoring of
        complex LLM responses without reliance on LLM-assisted assessments or human judgment.'
      section: Abstract
      citation_context_ids: []
    access:
      access_type: public
      url: https://github.com/SheldonWu0327/LIFBench-2024
      license: ''
    availability_check:
      status: available
      checked_by: github_mcp
      checked_at: ''
      notes: LIFEVAL evaluation programs and rubrics are part of the LIFBench GitHub repository (SheldonWu0327/LIFBench-2024),
        which is publicly accessible.
    repository:
      canonical_url: https://github.com/SheldonWu0327/LIFBench-2024
      verification:
        checked_by: github_mcp
        status: available
        notes: The LIFEVAL evaluation programs are bundled with the LIFBench code release on the same GitHub repository.
    agent_callable:
      can_wrap: false
      estimated_wrapping_difficulty: unknown
      notes: Evaluation methodology with programmatic scoring; serves as the evaluation component of the benchmark release.
    provenance:
      extracted_from:
      - 2025.acl-long.803
      extraction_confidence: high
      last_checked: '2026-06-30T18:33:11.498535+00:00'

```

##### 4\.3 AgentCallable：该论文是否能够被 Agent 以 Skill 的方式使用（暂时没有可抽取的）

```YAML
resource_id: code::virsci
kind: code
name: VirSci (Virtual Scientist multi-agent system)
description: 模拟研究团队的多 agent 系统，迭代提出和批评 idea
language: Python
repo: https://github.com/...  # 由 skill 自动验证 URL 可达
released_with_paper: paper::su-2024-virsci
skill_wrapped: false        # 关键：还没被包装为 agent-callable skill
skill_candidate: true       # 但应被纳入包装候选
```

**资源描述的最小字段**：\`kind\` / \`name\` / \`domain\` / \`access\` / \`evaluation\_metrics\`（对 dataset/benchmark）/ \`skill\_wrapped\`（对 code）。用户强调"基本的描述"——这就是基本盘。

#### 实施方案

Agent \+ Skill 自动化抽取，集中在单篇论文，不做多篇论文的关联、不做对code、benchmark、dataset等的可访问性验证与名称消歧

只抽取单篇信息，可留空字段

引用相关

```YAML
citation_contexts:
  cited_references: []  # 如果解析失败可空
  citing_papers: []     # 初抽阶段必须允许为空
```





**另一个维度：时间**



除了刚刚提到的分类树更新，还有一个最基本的问题是: **如何高效的找到相关论文**，从Deep 和 Wide 两个层面，即找得全，找得深。这是典型的Deep Search问题

如果遇到的论文是非全文可获取的怎么办

在方法提取和一些深入构建的过程，读取Survey中每一篇论文的消耗也很大，怎么做

### Ref

https://aixiv\.science/explore : https://arxiv\.org/pdf/2508\.15126

---

综述:

https://github\.com/RUCAIBox/awesome\-agent\-harness https://openreview\.net/forum?id=nM5tDHrQsx （从综述入手做核心/高质量/清晰分类/领域专一论文）

https://openreview\.net/pdf?id=eONq7FdiHa： https://picrew\.github\.io/LLM\-Harness  \(awesome h\-enginer 资源）

Code as Agent Harness https://arxiv\.org/abs/2605\.18747

Intern\-Atlas: https://arxiv\.org/abs/2604\.28158

假设生成: https://arxiv\.org/pdf/2505\.04651, https://arxiv\.org/pdf/2507\.01903 

ai for biotech（有盈利期望）

#### Tools

1. Deepxiv\-skill \[单篇论文解读\]



