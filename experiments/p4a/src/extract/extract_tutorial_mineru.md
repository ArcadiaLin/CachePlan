# MinerU/PDF Layer 4 提取教程

本文说明如何基于 MinerU/PDF 解析结果整理 Layer 4 论文记录与资源记录。它参考
`src/extract/extract_tutorial_latex.md` 的目标模板，但不再依赖 LaTeX cite key 或 arXiv source
package。当前 PDF 管线已经统一整理了 ACL 2025 的引用目录与引用上下文，后续重点是让
Kimi agent 阅读 MinerU Markdown、已整理引用、引用上下文和论文表格，抽取并校验 reusable
resources，例如 GitHub 仓库、项目页、dataset、benchmark、model、tool、API、protocol 等。

## 当前已完成输入

引用与引用上下文位于：

```text
data/processed/extracted/cite/
  acl2025_verified_plus_repaired.jsonl
  acl2025_cite_contexts.jsonl
  acl2025_cite_contexts_summary.json
```

其中：

- `acl2025_verified_plus_repaired.jsonl`：每篇论文一行，包含已修复且可直接使用的 reference list。
- `acl2025_cite_contexts.jsonl`：每篇论文一行，包含正文引用上下文、段落/句子位置、匹配到的 reference index，以及按 reference 聚合的引用次数。
- `acl2025_cite_contexts_summary.json`：全量抽取汇总。

这些文件应作为 MinerU Layer 4 的固定输入，不需要每篇论文重新让 agent 修引用。Agent 只需要在
这些 citation contexts 上补充 `citation_function`，或者在资源抽取时把 cite context 当作证据和兜底索引使用。

## 目标产物

每篇论文都应在 `data/processed/layer4/` 下生成一个独立目录：

```text
data/processed/layer4/<paper_id>/
  input_bundle.json
  agent_prompt.md
  agent_judgment.json
  agent_response.md
  agent.log
  paper_record.base.yml
  paper_record.yml
  resource_records.base.yml
  resource_records.yml
  resource_verification_report.json
  run_report.json
  quality_report.json
```

推荐可选产物：

```text
  github_verification.json
  dataset_benchmark_notes.md
```

核心文件含义：

- `agent_judgment.json`：agent 手工构造的语义判断中间产物。
- `paper_record.base.yml`、`resource_records.base.yml`：脚本生成的干净模板，供 merge 使用。
- `paper_record.yml`：脚本合并后生成的论文级记录，包含 metadata、内容结构、语义抽取、引用上下文、资源关系。
- `resource_records.yml`：脚本合并后生成的资源级记录列表，每个条目描述一个可复用资源。
- `agent_prompt.md`：正式交给 Kimi 的 prompt。批量运行时应保留，方便复查。
- `agent_response.md`：Kimi 原始回答。不要只保留最终结构化产物；原始回答是审计材料。
- `resource_verification_report.json`：对 GitHub/项目页/数据集等外部资源的校验结论。
- `run_report.json`：本次整理过程的状态、输入文件、输出文件、警告和失败原因。

## MinerU 输入约定

单篇论文的 MinerU 目录通常如下：

```text
data/processed/mineru/acl/<year>/<venue>/<paper_id>/vlm/
  <paper_id>.md
  <paper_id>_content_list.json
  <paper_id>_content_list_v2.json
  <paper_id>_origin.pdf
  <paper_id>_layout.pdf
  <paper_id>_middle.json
  <paper_id>_model.json
```

必需输入：

- Markdown：`<paper_id>.md`
- 引用目录：`acl2025_verified_plus_repaired.jsonl` 中该 `paper_id` 对应行
- 引用上下文：`acl2025_cite_contexts.jsonl` 中该 `paper_id` 对应行

推荐输入：

- `content_list_v2.json`：用于核对表格、图片、caption、参考文献边界。
- `origin.pdf`：当 Markdown 表格错位或资源声明不清晰时人工/agent 兜底查看。
- `layout.pdf`：当 caption 和正文附近内容需要定位时使用。

## 论文记录模板

MinerU 版 `paper_record.yml` 以旧模板为基础，但 citation 使用 PDF 管线已经生成的
`context_id` 和 `reference_indices`，不再使用 LaTeX `cite_key`。

```yaml
paper_record:
  paper_id: paper::2025.acl-demo.16
  source_type: paper
  metadata:
    title: ""
    authors: []
    year: unknown
    venue: ""
    arxiv_id: ""
    acl_id: "2025.acl-demo.16"
    doi: ""
    url: ""
    pdf_path: "data/processed/mineru/acl/2025/acl/2025.acl-demo.16/vlm/2025.acl-demo.16_origin.pdf"
    markdown_path: "data/processed/mineru/acl/2025/acl/2025.acl-demo.16/vlm/2025.acl-demo.16.md"

  content_units:
    abstract: ""
    section_outline: []
    has_appendix: false
    has_supplementary_material: false
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
source_paper: ""
comparison: ""
```

### `citation_context.cite[]`

`citation_context.cite[]` 从 `acl2025_cite_contexts.jsonl` 迁入，agent 只补充
`citation_function`，不要重写引用上下文本身。

```yaml
- context_id: 2025.acl-demo.16::cite::1
  raw_citation: "(Touvron et al., 2023)"
  reference_indices: [14]
  reference_titles:
    - "Llama 2: Open foundation and fine-tuned chat models"
  context: "Models like Meta's Llama series..."
  section: "1 Introduction"
  paragraph_index: 5
  sentence: "Models like Meta's Llama series..."
  citation_function: ""
```

`citation_function` 建议使用粗粒度标签：

```text
background
method_source
dataset_source
benchmark_source
baseline
tool_source
model_source
claim_support
comparison
contrast
related_work
other
unknown
```

如果 citation context 与资源抽取有关，例如某篇 reference 是 dataset 或 benchmark 来源，agent 应在
resource record 的 `provenance.evidence` 中引用对应 `context_id` 或 `reference_indices`。

## 资源记录模板

MinerU/PDF 管线的 resource schema 需要比原 LaTeX 版更强，因为 Kimi + GitHub MCP 能提供仓库迁移、
维护状态、许可证、语言、commit 活跃度、benchmark/dataset split 等信息。

```yaml
- resource_record:
    resource_id: code::venusfactory2
    kind: code
    name: VenusFactory2
    aliases:
      - VenusFactory
      - ai4protein/VenusFactory
    description: ""
    domain: []

    paper_relation:
      relation_type: introduced
      evidence:
        - section: ""
          quote: ""
          context_id: ""
          reference_indices: []

    access:
      url: "https://github.com/ai4protein/VenusFactory2"
      original_url: "https://github.com/ai4protein/VenusFactory"
      access_type: public
      license: ""
      size: ""

    repository:
      provider: github
      owner: ai4protein
      repo: VenusFactory2
      canonical_url: "https://github.com/ai4protein/VenusFactory2"
      original_url_status: migrated_or_missing
      latest_commit_at: ""
      latest_release: ""
      primary_language: ""
      topics: []
      stars: null
      forks: null
      open_issues: null
      activity_status: unknown
      verification:
        checked_at: ""
        checked_by: github_mcp
        notes: ""

    dataset_benchmark:
      task_category: ""
      source_reference_indices: []
      train_size: null
      valid_size: null
      test_size: null
      metric: ""
      table_or_section: ""

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
        - paper::2025.acl-demo.16
      extraction_confidence: medium
      last_checked: ""
      evidence:
        - section: ""
          quote: ""
```

### 资源类型

`kind` 合法值：

```text
dataset
benchmark
code
model
tool
skill
protocol
resource
```

使用边界：

- `dataset`：语料、样本集合、训练/验证/测试集、标注集。
- `benchmark`：评测套件、任务集合、leaderboard、有明确评价协议的数据集。
- `code`：源码仓库、脚本、notebook、实现代码。
- `model`：模型权重、checkpoint、预训练模型、公开系统模型。
- `tool`：可运行软件、平台、API、框架、环境、服务。
- `protocol`：可复用流程、提示模板、评测协议、数据生成流程。
- `skill`：明确可包装成 agent skill/workflow 的资源。
- `resource`：无法确定类型但明显是可复用实体时使用。

### 论文关系

`paper_relation.relation_type` 建议使用：

```text
introduced
used
evaluated
extended
cited_only
unknown
```

不要只因为 URL 出现在论文中就标记为 `introduced`。需要证据，例如：

- "we release ..."
- "our code/data/model is available ..."
- "we introduce a benchmark ..."
- "we use/evaluate on ..."
- 实验设置表格、dataset section、benchmark section、implementation details。

## Kimi Agent 正式 Prompt 工作流

本管线不再以规则脚本作为 resource 判断主体。规则数据只负责提供输入材料；每篇论文由 Kimi agent
生成可审计的 `agent_judgment.json`。所有 YAML 都由本地脚本生成、合并和校验，不允许 agent 直接写
`paper_record.yml` 或 `resource_records.yml`。

## 控制脚本

MinerU Layer 4 的控制脚本位于：

```text
src/extract/layer4/
  prepare_mineru_layer4.py
  apply_agent_judgment.py
  launch_kimi_layer4.py
  validate_layer4_outputs.py
  common.py
  README.md
```

它们的职责是把 agent 工作限制在可控文件边界内：

- `prepare_mineru_layer4.py`：为单篇论文生成 `input_bundle.json`、`paper_record.base.yml`、`resource_records.base.yml`、`agent_prompt.md` 和初始 `run_report.json`。
- `apply_agent_judgment.py`：读取 agent 产出的 `agent_judgment.json`，由脚本生成 `paper_record.yml`、`resource_records.yml`、`resource_verification_report.json` 和 `run_report.json`。
- `launch_kimi_layer4.py`：参照 reference repair launcher 的模式，批量准备单篇目录、启动多个 Kimi CLI、捕获 stdout/stderr 到日志、保存 agent 原始输出、合并 JSON judgment、运行校验并汇总批处理报告。
- `validate_layer4_outputs.py`：校验 agent 完成后的 YAML/JSON，检查必需字段、枚举、资源 id 引用关系、GitHub 校验状态、HuggingFace pending 状态，并写入 `quality_report.json`。
- `common.py`：共享路径、枚举、JSONL 查找、Markdown 元信息抽取、YAML 读写工具。

这些脚本需要 PyYAML。当前项目 `.venv` 中已包含 PyYAML，推荐用：

```bash
cd /home/lzx/projs/p4a
.venv/bin/python src/extract/layer4/prepare_mineru_layer4.py --paper-id 2025.acl-demo.16
.venv/bin/python src/extract/layer4/apply_agent_judgment.py --paper-id 2025.acl-demo.16
.venv/bin/python src/extract/layer4/validate_layer4_outputs.py --paper-id 2025.acl-demo.16
```

正式批量启动推荐直接使用 launcher。它不会把完整 prompt 塞进命令行参数，而是传一个很短的 bootstrap
prompt，让 Kimi 自己读取每篇论文目录下的 `agent_prompt.md`，避免引用上下文过长时再次遇到
`Argument list too long`。Prompt 会明确要求 Kimi 先读取并遵循
`skill/paper-mineru-resource-extract/SKILL.md`。如果 merge 或 validate 失败，launcher 会生成
`agent_repair_prompt.md`，带着错误信息让 Kimi 只修 `agent_judgment.json`；默认 `--max-retries 2`，
也就是首轮失败后最多两次兜底修复：

```bash
cd /home/lzx/projs/p4a

# 只准备输入包和 prompt，不启动 Kimi，适合先检查单篇模板。
.venv/bin/python src/extract/layer4/launch_kimi_layer4.py \
  --paper-id 2025.acl-demo.16 \
  --prepare-only \
  --no-skip-existing \
  --overwrite-prepare

# 单篇正式启动 Kimi。
.venv/bin/python src/extract/layer4/launch_kimi_layer4.py \
  --paper-id 2025.acl-demo.16 \
  --concurrency 1 \
  --timeout 3600 \
  --no-skip-existing

# 全量批处理。默认读取 data/processed/extracted/cite/acl2025_verified_plus_repaired.jsonl。
.venv/bin/python src/extract/layer4/launch_kimi_layer4.py \
  --concurrency 4 \
  --timeout 3600
```

如果 Kimi CLI 需要更高权限模式，可以显式追加：

```bash
--permission-mode auto
```

或在确认风险后使用：

```bash
--permission-mode yolo
```

### 单篇目录准备

```bash
PAPER_ID="2025.acl-demo.16"
OUT_DIR="data/processed/layer4/${PAPER_ID}"
mkdir -p "$OUT_DIR"
```

建议先构造 `input_bundle.json`，包含：

```json
{
  "paper_id": "2025.acl-demo.16",
  "markdown_path": "data/processed/mineru/acl/2025/acl/2025.acl-demo.16/vlm/2025.acl-demo.16.md",
  "content_list_path": "data/processed/mineru/acl/2025/acl/2025.acl-demo.16/vlm/2025.acl-demo.16_content_list_v2.json",
  "pdf_path": "data/processed/mineru/acl/2025/acl/2025.acl-demo.16/vlm/2025.acl-demo.16_origin.pdf",
  "references_jsonl": "data/processed/extracted/cite/acl2025_verified_plus_repaired.jsonl",
  "cite_contexts_jsonl": "data/processed/extracted/cite/acl2025_cite_contexts.jsonl",
  "output_dir": "data/processed/layer4/2025.acl-demo.16"
}
```

### Prompt 模板

每篇论文生成 `agent_prompt.md`，内容应自包含，并明确要求 Kimi 使用
`paper-mineru-resource-extract` skill：手工构造 `agent_judgment.json`，再运行本地脚本生成 YAML。
不得让 Kimi 手工写入任何 `.yml`/`.yaml` 文件。

```markdown
# MinerU Layer 4 Resource Judgment

You are extracting semantic judgments for one PDF/MinerU paper.

Repository root: /home/lzx/projs/p4a

Paper id: 2025.acl-demo.16

Input files:
- Markdown: data/processed/mineru/acl/2025/acl/2025.acl-demo.16/vlm/2025.acl-demo.16.md
- Content list: data/processed/mineru/acl/2025/acl/2025.acl-demo.16/vlm/2025.acl-demo.16_content_list_v2.json
- PDF: data/processed/mineru/acl/2025/acl/2025.acl-demo.16/vlm/2025.acl-demo.16_origin.pdf
- Repaired references: data/processed/extracted/cite/acl2025_verified_plus_repaired.jsonl
- Citation contexts: data/processed/extracted/cite/acl2025_cite_contexts.jsonl

Output directory:
data/processed/layer4/2025.acl-demo.16

Tasks:
1. Read the Markdown and the matching records from repaired references and citation contexts.
2. Use GitHub MCP when a GitHub repository or project page points to GitHub.
3. Write exactly one machine-readable file: agent_judgment.json.
4. Do not write, edit, or overwrite any .yml/.yaml file.

Resource extraction rules:
- Do not record generic concepts, ordinary metrics, losses, equations, or broad research areas.
- Record datasets, benchmarks, code, models, tools, protocols, APIs, repositories, project pages, and released artifacts.
- A single URL may support multiple resources.
- A named dataset/benchmark/model without URL should still be recorded if the paper clearly uses or introduces it.
- Every resource must include evidence from the paper when possible.
- Do not invent license, size, split, metrics, or availability.

Citation rules:
- Do not repair references or citation contexts; they are already provided.
- Use citation context ids and reference indices from the prepared input.
- Only add citation_function when useful.

Required file to write:
- agent_judgment.json

The local script apply_agent_judgment.py will generate YAML and reports.

Return a concise status summary after writing the files.
```

### 调用 Kimi

优先使用 prompt file，避免长 prompt 超过命令行长度：

```bash
python3 ~/.codex/skills/use-kimi-agent/scripts/run_kimi.py \
  --cwd /home/lzx/projs/p4a \
  --prompt-file "data/processed/layer4/${PAPER_ID}/agent_prompt.md"

.venv/bin/python src/extract/layer4/apply_agent_judgment.py \
  --paper-id "${PAPER_ID}"

.venv/bin/python src/extract/layer4/validate_layer4_outputs.py \
  --paper-id "${PAPER_ID}"
```

如果直接调用 Kimi CLI，注意当前 CLI 只有 `--prompt`，不一定支持 `--prompt-file`。这种情况下应传短
bootstrap prompt，让 agent 自己读取 `agent_prompt.md`：

```bash
kimi --output-format text --prompt \
"Read data/processed/layer4/${PAPER_ID}/agent_prompt.md and follow it exactly. Write all required files, then return a short status summary."
```

批量运行时必须保存 Kimi stdout/stderr：

```text
data/processed/layer4/<paper_id>/agent_response.md
data/processed/layer4/<paper_id>/agent.log
```

## 单篇整理步骤

### 1. 收集输入

确认以下文件存在：

```bash
PAPER_ID="2025.acl-demo.16"
test -f "data/processed/mineru/acl/2025/acl/${PAPER_ID}/vlm/${PAPER_ID}.md"
test -f data/processed/extracted/cite/acl2025_verified_plus_repaired.jsonl
test -f data/processed/extracted/cite/acl2025_cite_contexts.jsonl
```

如果是非 ACL 2025 论文，引用目录和 citation contexts 需要先按同一格式补齐，再进入 Layer 4。

### 2. 准备 prompt

把该论文的路径、引用文件、输出目录写入 `agent_prompt.md`。Prompt 必须要求 agent 写文件到
`data/processed/layer4/<paper_id>/`，不要只输出 Markdown 说明。

### 3. Kimi 生成草稿

Agent 生成：

```text
paper_record.yml
resource_records.yml
resource_verification_report.json
run_report.json
```

其中 `paper_record.yml` 可以包含论文语义字段，但本阶段重点是资源：

- `resources_introduced`
- `resources_used`
- `resource_records.yml`
- `resource_verification_report.json`

### 4. GitHub MCP 校验

遇到 GitHub 仓库时，agent 应使用 GitHub MCP 获取或核实：

- repository 是否存在。
- 原论文 URL 是否迁移、重命名、归档或消失。
- canonical URL。
- license。
- primary language。
- topics。
- latest commit / latest release。
- stars/forks/issues 等可用元数据。
- README 中是否有安装、数据、模型、demo、API 文档。

校验结果写入：

```yaml
repository:
  provider: github
  owner: ""
  repo: ""
  canonical_url: ""
  original_url_status: ""
  latest_commit_at: ""
  latest_release: ""
  primary_language: ""
  topics: []
  stars: null
  forks: null
  open_issues: null
  activity_status: active
  verification:
    checked_at: ""
    checked_by: github_mcp
    notes: ""
```

如果仓库已迁移，例如论文写 `VenusFactory`，实际为 `VenusFactory2`，保留两者：

```yaml
access:
  url: "https://github.com/ai4protein/VenusFactory2"
  original_url: "https://github.com/ai4protein/VenusFactory"
repository:
  canonical_url: "https://github.com/ai4protein/VenusFactory2"
  original_url_status: migrated_or_missing
```

### 5. Dataset / Benchmark 整理

Kimi 需要阅读正文、表格和 citation contexts，整理：

- 数据集/benchmark 名称。
- 任务类别。
- train/valid/test split。
- metric。
- 来源论文或 reference index。
- 是否是本文引入，还是本文使用/评测。
- 证据位置：section、table、quote。

示例：

```yaml
- resource_record:
    resource_id: benchmark::deeploc2multi
    kind: benchmark
    name: DeepLoc2Multi
    aliases: [DL2M]
    description: "Protein localization benchmark used for evaluation."
    domain: ["protein localization"]
    paper_relation:
      relation_type: evaluated
      evidence:
        - section: "Experiments"
          quote: "..."
          reference_indices: []
    dataset_benchmark:
      task_category: Localization
      source_reference_indices: []
      train_size: 21948
      valid_size: 2744
      test_size: 2744
      metric: f1_max
      table_or_section: "Table 8"
```

### 6. 校验输出

至少做这些检查：

- YAML 能被解析。
- `paper_record.paper_id` 与目录 paper id 一致。
- `resources_introduced`、`resources_used` 中的 id 都存在于 `resource_records.yml`。
- 每个 resource 有 `kind`、`name`、`paper_relation.relation_type`。
- `introduced` 必须有明确 release/introduce evidence。
- GitHub 资源必须有 `repository.verification.checked_by: github_mcp`，或在 notes 中说明未校验原因。
- HuggingFace 等暂未配置 MCP 的资源不能写成已验证，只能 `unknown` 或 `pending_verification`。

## 批量整理方案

推荐用 `src/extract/layer4/launch_kimi_layer4.py` 作为批量 orchestrator。它会做以下事情：

1. 遍历目标论文列表。
2. 为每篇论文创建 `data/processed/layer4/<paper_id>/`。
3. 写入 `input_bundle.json` 和 `agent_prompt.md`。
4. 调用 Kimi，让其使用 `paper-mineru-resource-extract` skill，构造 `agent_judgment.json` 并运行本地 apply 脚本。
5. 捕获 `agent_response.md` 和 `agent.log`。
6. 调用 `apply_agent_judgment.py`，由脚本生成 YAML 和报告。
7. 校验 YAML 和 JSON。
8. 如果 merge/validate 失败，写入 `agent_repair_prompt.md` 并让 Kimi 修 `agent_judgment.json`，最多两次兜底。
9. 写入 `run_report.json`。
10. 汇总全局 `data/processed/layer4/batch_report.json`。

同时会写入：

```text
data/processed/layer4/batch_report.json
data/processed/layer4/batch_failures.json
```

可以用 `--paper-id` 重复指定多篇，也可以用 `--limit` 先抽样：

```bash
.venv/bin/python src/extract/layer4/launch_kimi_layer4.py \
  --paper-id 2025.acl-demo.16 \
  --paper-id 2025.acl-demo.23 \
  --concurrency 2

.venv/bin/python src/extract/layer4/launch_kimi_layer4.py \
  --limit 20 \
  --concurrency 4
```

单篇失败不应中止全批。失败目录至少应保留：

```text
agent_prompt.md
agent_judgment.json
agent_repair_prompt.md
agent_response.md
agent.log
run_report.json
```

`run_report.json` 推荐结构：

```json
{
  "paper_id": "2025.acl-demo.16",
  "status": "ok",
  "inputs": {
    "markdown": "",
    "references": "",
    "citation_contexts": ""
  },
  "outputs": {
    "paper_record": "",
    "resource_records": "",
    "resource_verification_report": ""
  },
  "resource_count": 0,
  "github_checked_count": 0,
  "warnings": [],
  "errors": []
}
```

## 与 LaTeX 管线的差异

| 项目 | LaTeX source 管线 | MinerU/PDF 管线 |
| --- | --- | --- |
| 输入 | `.tar.gz` LaTeX 源码包 | MinerU Markdown/content_list/PDF |
| 引用定位 | `\cite{key}` | 已生成 `citation_contexts.jsonl` |
| reference key | BibTeX cite key | reference index + context id |
| 图像资产 | 从 source package 复制 | PDF/MinerU 图像与 caption，可后续补 |
| URL 候选 | LaTeX/README 中显式 URL | Markdown、表格、脚注、GitHub/project links |
| 资源判断 | agent judgment 补语义 | Kimi + GitHub MCP 主导资源抽取和校验 |
| 输出目录 | parse run 目录 | `data/processed/layer4/<paper_id>/` |

## 当前阶段优先级

由于引用目录和 citation contexts 已经统一完成，当前 MinerU Layer 4 的优先级是：

1. GitHub/code repository 抽取与 MCP 校验。
2. Project page、demo、API、documentation 抽取。
3. Dataset/benchmark/model/tool/protocol 资源记录。
4. `resources_introduced` / `resources_used` / `evaluated` 关系判断。
5. resource availability 与迁移状态。
6. 论文语义字段补充：contributions、claims、experiments、limitations、future_work。
7. citation_function 可选补充，不阻塞资源整理。

暂未配置 HuggingFace MCP 时，HuggingFace 资源仍可记录，但状态应保守：

```yaml
availability_check:
  status: unknown
  checked_by: pending_huggingface_mcp
  notes: "URL or model name found in paper, but external availability was not verified."
```

## 最终报告建议

完成一篇论文后，报告应至少包含：

- 输入 MinerU Markdown/PDF 路径。
- 使用的引用目录和引用上下文文件。
- 输出目录。
- 资源数量，按 kind 统计。
- GitHub 校验数量和失败数量。
- introduced/used/evaluated 资源 id。
- 未验证资源列表。
- YAML/JSON 校验状态。
- 需要人工复查的警告。
