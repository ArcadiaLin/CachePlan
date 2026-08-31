# paper-latex-resource-extract 提取教程

本文说明 `projs/p4a/skill/paper-latex-resource-extract` 这个 skill 最终导向的资源模板结构，以及从 arXiv LaTeX 源码包提取论文与资源记录的步骤。

## 目标产物

该 skill 的目标不是只收集 URL，而是把一篇 arXiv LaTeX 论文包整理成可审计的论文记录与可复用资源记录。一次单篇解析会在输出目录中生成：

```text
<run-output-dir>/<arxiv_id>/
  paper_record.yml
  resource_records.yml
  structure.json
  figures/
  figure_manifest.json
  citations.json
  resources.json
  lint_report.json
  run_report.json
  agent_edit_hints.json
```

其中最重要的最终模板有两类：

- `paper_record.yml`：论文级记录，包含论文元数据、内容单元、原子化语义抽取、论文引入/使用的资源 id 列表、引用关系等。
- `resource_records.yml`：资源级记录列表，每个条目描述一个可复用资源，例如 dataset、benchmark、code、model、tool、skill、protocol 或 generic resource。

机械 parser 先生成草稿。agent 阅读论文证据后，把语义判断写入 `agent_judgment.yml`，再通过 `apply_agent_judgment.py` 合并成：

```text
paper_record.agent.yml
resource_records.agent.yml
agent_merge_report.json
agent_merge_edit_hints.json
```

通过 lint 后，`*.agent.yml` 才应被视为补充语义后的最终候选记录。

## 论文记录模板结构

`paper_record.yml` 的根结构如下：

```yaml
paper_record:
  paper_id: paper::<arxiv_id>
  source_type: paper
  metadata:
    title: ""
    authors: []
    year: unknown
    venue: arXiv <arxiv_id>
    arxiv_id: ""
    doi: ""
    url: ""
  content_units:
    abstract: ""
    section_outline: []
    has_appendix: false
    has_supplenmentart_material: false
    figures: []
    tables: []
  atomic_extracts:
    intent:
      paper_type: unknown
      research_problem: ""
      target_domain: []
    contributions: []
    claims: []
    experiments: []
    limitations: []
    future_work: []
    citation_context:
      cite: []
      cited_by: []
resources_introduced: []
resources_used: []
cites: []
cited_by: []
source paper: ""
comparsion: ""
```

各部分含义：

- `metadata`：论文元数据。由 parser 从 arXiv metadata 或 LaTeX 结构中生成，通常不由 agent 直接覆盖。
- `content_units`：论文内容单元，包括摘要、章节大纲、是否有 appendix/supplement、图表记录。图像文件会复制到 `figures/`，图像清单写入 `figure_manifest.json`。
- `atomic_extracts.intent`：论文意图，包括 `paper_type`、`research_problem`、`target_domain`。这些是语义字段，需要 agent 阅读论文后补充。
- `atomic_extracts.contributions`：作者声明的贡献，按论文顺序记录。
- `atomic_extracts.claims`：只记录 1-2 条摘要层面的核心 claim，不带 evidence。
- `atomic_extracts.experiments`：对复现或资源复用重要的实验记录，包括 task、dataset/benchmark ids、metrics、baselines、hyperparameters 和 evidence。
- `atomic_extracts.limitations`、`future_work`：只记录论文明确陈述的限制和未来工作。
- `atomic_extracts.citation_context.cite`：引用上下文。parser 提供 cite key、reference title、context 和 evidence；agent 只补充 `citation_function`。
- `resources_introduced`：本文引入、发布、提出或公开的资源 id。
- `resources_used`：本文方法或实验实际使用的资源 id。
- `cites`、`cited_by`：论文级引用索引。`cites` 可由 bibliography 中显式 arXiv id 推出，`cited_by` 默认留空。

### 图像记录结构

`paper_record.content_units.figures[]` 中的图像记录通常包含：

```yaml
- figure_id: fig::<id>
  label: ""
  caption: ""
  files: []
  caption_source:
    tex_file: ""
    line: null
  description: ""
  agent_review:
    status: unreviewed
    notes: ""
```

parser 负责 `figure_id`、`label`、`caption`、`files`、`caption_source`。agent 只应补充：

- `description`：基于 caption 和附近正文说明该图在论文中的作用。
- `agent_review.status`：`ok`、`parser_mismatch` 或 `uncertain`。
- `agent_review.notes`：对 review 状态的简短解释。

### 实验记录结构

`paper_record.atomic_extracts.experiments[]` 的结构如下：

```yaml
- experiment_id: exp::main
  task: ""
  dataset_ids: []
  benchmark_ids: []
  metrics: []
  baselines: []
  hyperparameters:
    status: missing
    values: {}
  evidence:
    section: ""
```

`hyperparameters.status` 的合法值是 `available`、`partial`、`missing`、`not_applicable`。`dataset_ids` 和 `benchmark_ids` 不应悬空：如果 parser 没有生成对应资源，agent 需要同时在 `resource_judgments` 中补充资源记录。

## 资源记录模板结构

`resource_records.yml` 是一个列表，每个元素以 `resource_record` 为根：

```yaml
- resource_record:
    resource_id: code::example-repo
    kind: code
    name: ExampleRepo
    description: ""
    domain: []
    access:
      url: ""
      access_type: unknown
      license: ""
      size: ""
    agent_callable:
      skill_candidate: false
      skill_wrapped: false
      callable_interface: null
      required_environment: []
      estimated_wrapping_difficulty: unknown
    availability_check:
      status: unknown
      checked_at: ""
      checked_by: agent
      notes: ""
      files: []
      documentation: ""
      input_format: ""
      output_format: ""
      evaluation_metrics: []
    reverse_index:
      introduced_by: ""
      used_by: []
      evaluated_by: []
      extended_by: []
    provenance:
      extracted_from:
        - paper::<arxiv_id>
      extraction_confidence: medium
      last_checked: ""
```

字段说明：

- `resource_id`：资源稳定 id。agent 未显式提供时，merge 脚本会按 `kind::slug(name)` 派生。
- `kind`：资源类型，合法值为 `dataset`、`benchmark`、`code`、`model`、`tool`、`skill`、`protocol`、`resource`。
- `name`：论文或链接中出现的规范资源名。
- `description`：一句话说明资源是什么，以及它和当前论文的关系。
- `domain`：领域标签，例如 `image generation`、`multimodal reasoning`。
- `access`：访问入口和显式可见的 license/size 信息。除非用户要求验证阶段，否则不要联网验证。
- `agent_callable`：判断该资源是否适合未来包装成 agent 可调用 skill/tool，以及接口和包装难度。
- `availability_check`：可用性验证信息。默认保留 unknown；只有执行验证阶段后才补充。
- `reverse_index`：跨论文反向索引。默认留空，不在本 skill 的机械解析阶段推断。
- `provenance`：资源记录来源与抽取置信度。

机械 parser 只从 LaTeX 中显式 URL 抽取 generic `resource` 候选，不会自动判断一个链接是代码、数据集、模型还是 benchmark。语义类型、描述、领域、introduced/used 关系都应由 agent 基于论文证据补齐。

## Agent 判断文件结构

agent 不应直接改写机械生成的 `paper_record.yml` 和 `resource_records.yml`。语义补充写入同目录下的 `agent_judgment.yml`：

```yaml
paper_record:
  content_units:
    figures:
      - figure_id: fig::example
        description: "Caption/context-based role of this figure in the paper."
        agent_review:
          status: ok
          notes: ""
  atomic_extracts:
    intent:
      paper_type: empirical
      research_problem: "..."
      target_domain: ["..."]
    contributions:
      - contribution_id: contrib::1
        text: "..."
        evidence:
          section: Introduction
          page: null
          quote: "..."
    claims:
      - claim_id: claim::1
        text: "..."
        claim_type: empirical
    experiments:
      - experiment_id: exp::main
        task: "..."
        dataset_ids: []
        benchmark_ids: []
        metrics: []
        baselines: []
        hyperparameters:
          status: partial
          values: {}
        evidence:
          section: Experiments
    limitations:
      - text: "..."
        evidence:
          section: Limitations
          quote: "..."
    future_work:
      - text: "..."
        evidence:
          section: Conclusion
          quote: "..."
    citation_context:
      cite:
        - cite_key: example2026
          citation_function: background
resources_introduced:
  - code::examplerepo
resources_used:
  - dataset::exampleset
resource_judgments:
  - kind: code
    name: ExampleRepo
    aliases: ["project repository"]
    access:
      url: "https://example.com/repo"
      access_type: public
    description: "..."
    domain: ["..."]
    evidence:
      - section: Abstract
        quote: "..."
```

`apply_agent_judgment.py` 只接受白名单字段：

- 可整体替换：`intent`、`contributions`、`claims`、`experiments`、`limitations`、`future_work`、`resources_introduced`、`resources_used`。
- citation 只合并 `citation_function`。
- figure 只合并 `description` 和 `agent_review`。
- resource 只从 `resource_judgments` 或 `resources` 中合并允许字段。

## 提取步骤

### 1. 环境检查

从 skill 目录执行命令：

```bash
cd /home/lzx/projs/p4a/skill/paper-latex-resource-extract
pwd
test -f scripts/parse_one.py
uv --version
uv run python --version
```

该 skill 要求使用 `uv run python ...`。如果 `uv` 不可用，应先停止并修复环境，不要静默切换到系统 Python。

### 2. 解析单个 arXiv LaTeX 包

```bash
TARBALL="<arxiv-source.tar.gz>"
RUN_ROOT="<run-output-dir>"
METADATA="${METADATA:-online}"

uv run python scripts/parse_one.py \
  --input "$TARBALL" \
  --output-dir "$RUN_ROOT" \
  --metadata "$METADATA" \
  --supplements auto
```

`--metadata online` 会访问 arXiv API；如果网络或依赖安装失败，可以改用 `--metadata offline`，但论文 title/authors/year/abstract 等 metadata 可能更不完整。

### 3. 检查 parser 输出

根据命令输出中的 `output_dir` 找到单篇目录。推荐按以下顺序检查：

1. `run_report.json`：主 TeX 文件、metadata 状态、figure/citation/resource 数量、lint 状态。
2. `agent_edit_hints.json`：结构校验问题、补丁状态和可编辑提示。
3. `structure.json`：title、abstract、section outline、figures、tables。
4. `figure_manifest.json` 和 `figures/`：图像资产、caption 来源和缺失资产。
5. `citations.json`：cite keys、reference titles、局部引用上下文。
6. `resources.json` 和 `resource_records.yml`：显式 URL 资源候选。
7. `paper_record.yml`：最终要被语义补充的论文记录草稿。

可单独运行 lint：

```bash
PAPER_DIR="$RUN_ROOT/<arxiv_id>"
uv run python scripts/yaml_linter.py "$PAPER_DIR/paper_record.yml" --json
```

### 4. 阅读论文证据并写 agent_judgment.yml

在 `$PAPER_DIR/agent_judgment.yml` 中只写 agent 负责的语义字段。重点从以下位置找证据：

- abstract、introduction、contribution bullets、conclusion：论文类型、研究问题、贡献、核心 claim。
- method、dataset/benchmark、experiment setup、implementation details：实验任务、数据集、benchmark、metrics、baselines、超参数。
- limitations、discussion、ethics/impact：限制和风险。
- release statements、project links、appendix data description：引入或使用的可复用资源。
- caption 和图像附近正文：figure description 和 parser review。

注意边界：

- 不要把普通 URL 当成最终资源类型；需要判断它代表 code、dataset、model、benchmark 等哪种实体。
- 没有 URL 的命名数据集、benchmark、模型或协议也可以成为资源记录。
- 一个 URL 可以对应多个语义资源，例如同一个 repo 同时发布代码和 benchmark。
- claim 只来自 abstract，最多 1-2 条，不带 evidence。
- contribution、limitation、future_work、resource_judgments 应尽量带 `section` 和短 `quote` 证据。

### 5. 合并 agent 判断

```bash
uv run python scripts/apply_agent_judgment.py \
  --base "$PAPER_DIR/paper_record.yml" \
  --resource-records "$PAPER_DIR/resource_records.yml" \
  --judgment "$PAPER_DIR/agent_judgment.yml" \
  --output "$PAPER_DIR/paper_record.agent.yml" \
  --resource-output "$PAPER_DIR/resource_records.agent.yml" \
  --report-json "$PAPER_DIR/agent_merge_report.json" \
  --edit-hints-json "$PAPER_DIR/agent_merge_edit_hints.json"
```

合并逻辑：

- `paper_record` 的白名单语义字段会替换到 base 记录。
- citation 通过 `cite_key` 定位，只合并 `citation_function`。
- figure 通过 `figure_id` 或 `label` 定位，只合并 `description` 和 `agent_review`。
- resource 会按 `resource_id`、URL、`kind/name` 去重；agent 字段优先覆盖机械候选中的空泛字段。
- 被拒绝合并的路径会出现在 `agent_merge_edit_hints.json` 的 `merge_rejected` 中。

### 6. 校验最终记录

```bash
uv run python scripts/yaml_linter.py "$PAPER_DIR/paper_record.agent.yml" --json
```

资源记录会在 merge 脚本中逐条 lint。若失败，优先查看：

- `agent_merge_edit_hints.json`
- `agent_merge_report.json`
- lint 输出中的 `path`、`line`、`message`、`suggested_fix`

只修改最小相关位置，然后重新运行 merge 和 lint。

### 7. 批量解析

对一批 `.tar.gz` 包可使用：

```bash
INPUT_DIR="<directory-with-tar-gz>"
RUN_ROOT="<run-output-dir>"

uv run python scripts/parse_batch.py \
  --input-dir "$INPUT_DIR" \
  --output-dir "$RUN_ROOT" \
  --metadata online \
  --limit 20
```

先用 `--limit` 小批量检查失败模式，再决定是否去掉限制。批量运行后读取 `$RUN_ROOT/batch_report.json`。

## 常见修复路径

如果 parsing 明显错误，例如主 TeX 文件选错、citation/resource 大量缺失、figure caption 错位：

1. 收集 `run_report.json`、`agent_edit_hints.json`、`structure.json`、`figure_manifest.json`、`citations.json`、`resources.json`。
2. 阅读 `references/parser_extension_guide.md`。
3. 优先修改 `scripts/config/layer4_config.yml` 中可配置的 main-file scoring、section/caption/citation commands、URL pattern 等规则。
4. 只有配置无法表达时，再添加 `scripts/agent_supplement.d/` 补丁。
5. 重新运行 `parse_one.py --supplements auto`；如果补丁失败必须中止，使用 `--supplements required`。

## 最终报告建议

完成一篇论文后，报告应至少包含：

- 输入 tarball 和输出目录。
- metadata 模式：`online` 或 `offline`。
- 选中的主 TeX 文件。
- citation/resource/figure 数量。
- lint 是否通过。
- 新增或修正的语义字段。
- 新增或合并的 resource judgments。
- 是否做过 config 或 supplement 修复。
