# Layer4 Schema 改造：一份意见稿

状态：**提议，未商定，未实施。** 本文记录 Agent 对 Layer4 schema 的看法，供讨论与否决。
没有任何字段改动被落地，`experiments/p4a/src/extract/layer4_v2/schemas.py` 与
`skill/paper-mineru-resource-extract/SKILL.md` 保持原样。

依据材料：

- 研究方向与研究行动：[Papers for Agents：讨论与备忘](2026-09-09-paper-for-agents.md)（第 12、13 节）
- 原始协议：[P4A v1 协议](p4a-v1-protocol.md)（Layer4 与 4-3 过渡契约）
- 抽取实现：`experiments/p4a/refractor.md`、`experiments/p4a/src/extract/layer4_v2/schemas.py`、
  `experiments/p4a/skill/paper-mineru-resource-extract/SKILL.md`
- **主要对照语料**：`data/processed/e07/corpus/`（952 篇，全部 ACL 2026）
- **次要对照**：`data/raw/p4a-v1/`（3318 篇，ACL 2025 1968 + 2026 1350）

本文只覆盖 Layer4（单篇论文的抽取契约），不提出 Layer3 的构建方法。

## 0. 测量口径

第 2 节的数字由一次性脚本在上述两份副本上统计得到，脚本未入库（需要长期引用时再讨论
是否落为 `experiments/` 下的脚本）。

三条口径限制必须先说清楚：

1. **只描述结构与完备性，不描述语义正确性。** 字段是否存在、是否为空、枚举取值分布、
   id 是否一致、证据串能否在原文定位——这些可程序判定。至于 description 是否准确、
   relation 是否判对、`status: available` 的仓库是否真的可用，本文一概未评价；
   `data/raw/p4a-v1/README.md` 的可信度声明继续适用。
2. **e07 不是随机样本。** 它来自 `data/processed/e01/n0_fixed_time.jsonl` 的 961 观测集，
   而该观测集在 e01 的纳入过滤里排除了流产 run、操作者交互和多轮会话。筛选依据是
   run 的形态而非产出质量，但它仍然是"正常完成的 run"的子集。因此 e07 的数字应读作
   **流水线的较好情形**，不是它的平均水平。
3. 与既有记录的一处出入：`refractor.md` 依据 50 篇抽样给出的 `checked_by` 分布
   （`none` 142 / `github_mcp` 42 / `agent` 40 / `hf-readonly` 34 / 其他 12）
   与两份全量统计都对不上（`none` 在全语料仅 22 例，`agent` 占 54.2%）。
   结论方向一致——过半资源未经外部核验——但标签本身不稳定，这正是问题的一部分（见 2.4）。

## 1. 判断原则：由留存的 Layer3 产物反推 Layer4 字段

v1 协议是自底向上写的：Layer4 抽什么 → 4-3 过渡 → 分类树与谱系。它的
`layer3_processing_contract` 列出 7 个下游产物，Layer4 的字段集是这 7 个的并集。

新方向只承认四类研究行动（发现/筛选、理解/判断、寻找资源并判断用途、选择与使用准备）。
建议先收敛 Layer3 的产物集合，再决定 Layer4 抽什么——否则 Layer4 会继续为没有下游的
字段付出抽取成本和核验债务。第 2 节的恒空字段清单说明这不是假想风险，已经发生了。

| v1 Layer3 产物 | 建议处置 | 理由 |
|---|---|---|
| `resource_relations` | 保留，作为主线 | 直接支撑资源用途判断与使用准备 |
| `important_citation_mining` | 保留但收窄到资源来源、基线、方法来源 | 支撑"还有什么相关"与"与谁比较" |
| `taxonomy_construction` | 不实现 | 多 view、本体对齐、随时间演化是独立研究问题；v1 自述最常见情形是没有现成分类树可用；无唯一正确划分，评测不可落地 |
| `contribution_genealogy` | 不实现，只在 Layer4 保留原料 | 同上，收益链条长 |
| `reproducibility` | 大幅精简为"材料完备性" | 只保留程序可核验部分，删除完整复现与分领域验证 |
| `social_discussion` | 删除 | 取证不可核查、不可稳定复现 |
| `domain_verification` | 删除 | 另一个课题 |

砍掉 taxonomy 与 genealogy 不等于放弃跨论文组织。它们需要的原料（方法具名、资源使用、
引用角色）仍由 Layer4 产出，只是系统不承诺产出分类体系本身。

## 2. 对照实际产物

v1 协议的 Layer4 示例取自 `2025.acl-long.803`，那一篇的产物与协议基本一致。
把它当作全语料的代表则不成立。

### 2.0 e07 与全语料的质量差异：分两类，结论相反

**执行层缺陷在 e07 里基本消失，schema 层缺陷在 e07 里原样存在、部分更差。**
这是本节最重要的一条：e07 更干净，恰恰说明剩下的问题不能归因于批次事故。

| 指标 | e07（952，全 2026） | 全语料（3318） | 类别 |
|---|---|---|---|
| `contributions` 空 | **2.0%** | 25.9% | 执行 |
| `claims` 空 | **0.1%** | 23.3% | 执行 |
| `experiments` 空 | **3.5%** | 28.8% | 执行 |
| `limitations` 空 | **3.2%** | 27.2% | 执行 |
| `future_work` 空 | 18.3% | 38.1% | 执行 |
| 五项全空的论文 | **1 篇** | 761 篇 | 执行 |
| 合并丢失（judgment 有、YAML 空） | **0** | 799（全部在 2025 批） | 执行 |
| 恒空字段数 | 9 个 | 9 个 | schema |
| `checked_by` 不同取值 | **29 个** | 25 个以上 | schema |
| `checked_by: agent`（未核验） | **58.9%** | 54.2% | schema |
| 有外部工具核验的资源 | **26.2%** | 32.7% | schema |
| `available` 中无外部核验 | **49.8%** | 42.6% | schema |
| `access.license` 空 | **86.6%** | 82.5% | schema |
| `access.url` 空 | **57.1%** | 51.7% | schema |
| `relation_type: extended` | **2 条 / 4758** | 2 条 / 15996 | schema |
| 同名多 id 的资源名 | 7.6% | 10.1% | schema |
| evidence 可定位（严格 / 放宽） | 83.6% / 93.4% | 76.2% / 91.0% | schema |

引用层同样干净：952 篇 `reference_status` 全部 `verified`，
`reference_comparison` 全部 `match`，0 条 mismatch（1 篇 `pipeline_status` 为 `failed`）。

**所以答案是：这批质量与全语料不一致，好在执行，差在同样的地方。**
下面各小节以 e07 为准，括号内给出全语料数值作对照。

### 2.1 恒空字段：协议写了、数据里从来没有

以 e07 的 952 篇计：

| 字段 | e07 空值率 | 说明 |
|---|---|---|
| `metadata.authors` | 100% | 协议注释已提到"author 抽取好像存在点问题"；但 `source_artifacts.arxiv.authors` 有 67% 填了值——同一事实存在两处，规范位置恒空 |
| `content_units.figures` / `tables` | 100% | 从未实现 |
| `cites` / `cited_by` | 100% | 协议说明来自外部 API，流水线从未接 |
| `atomic_extracts.citation_context.cited_by` | 100% | 同上 |
| `source_paper` / `comparison` | 100% | 协议示例里就是空串，语义从未定义 |
| `availability_check.checked_at` | 100% | 与 `provenance.last_checked`（100% 有值）功能重复，留了死的那个 |
| `metadata.doi` | **100%**（全语料 99.7%） | — |

九个字段恒空，且 e07 这批一个都没好转。它们不是"暂时留空"，是没有产出路径。
协议说 Layer4"允许字段留空"，这句话把"还没抽到"和"根本不抽"混在了一起，
于是没人需要为恒空负责。

另有几个高空值但有产出路径的字段：`metadata.arxiv_id` 空 33.0%、`metadata.url` 空 19.3%
——这批 2026 论文有三分之一没匹配到 arXiv，`source_artifacts` 的三组状态随之
`unfetched`（arXiv 元数据 312 / HTML 315 / TeX 315）。这属于外部事实，不是缺陷。

### 2.2 批次间不一致与合并层的数据丢失（e07 不受影响）

这一条对 e07 不适用，但必须留档，因为它决定了别的批次能不能混进来。

全语料里 `atomic_extracts` 五个列表字段的空值率分两批完全不同（2025 批 contributions
42.5% 空 vs 2026 批 1.6%）。逐篇比对 `agent_judgment.json` 后可定位原因：
**2025 批有 799 篇（40.6%）的 agent 确实抽出了 contributions，但 YAML 里是空列表**；
2026 批 0 篇，e07 这 952 篇 0 篇。这是合并层的数据丢失，不是抽取失败。

原因是形状不稳定：抽样 800 份 `agent_judgment.json`，`contributions` 至少四种形状
——`list[str]`（约 79%）、`list[{text}]`（约 19%）、`list[{text, evidence}]`、
`list[{contribution_id, text, evidence}]`。合并脚本对形状敏感，修复后 2026 批正常，
2025 批未回溯重跑。

三个结论：

1. v2 用 guided decoding 约束输出形状是对的，这批数据是它的实证理由。
2. **2025 批约 800 篇的语义字段可以零 LLM 成本恢复**——`agent_judgment.json` 还在，
   重跑合并即可。与 schema 改造独立，可单独决定。
3. e07 现在干净，但 e07 的计划第 3 步要沿引文和共享资源向外扩展；
   一旦 2025 批论文进入候选池，就会带进这 40.6% 的空值。扩展前应先做第 2 条。

它同时证明了空值三态的必要性：一个空列表同时表示"论文里没有"、"agent 没抽出"、
"合并丢了"三件事，事后只能靠比对 JSON 才能分辨。e07 里 19 篇 contributions 为空的论文，
就属于第二种，但数据本身没写。

### 2.3 枚举名不副实

`availability_check.checked_by` 在协议里像枚举（`github_mcp` / `hf-readonly` / `arxiv-mcp`），
实际是自由文本。e07 这 4758 条资源里出现 **29 个**不同取值：

```
agent 2803 (58.9%) | github_mcp 1041 (21.9%) | pending_huggingface_mcp 413 (8.7%)
paper 180 | hf-readonly 135 | arxiv-mcp 58 | paper_evidence 45 | unknown 25
+ curl / paper_derived / external_url / paper_record / manual / paper_claimed /
  pending_github_mcp / http / paper_only / unfetched / web_fetch / external / fetch /
  manual_fetch / github / paper_assertion / arxiv_mcp / paper_url / author_knowledge /
  paper_and_reference / url
```

后面一长串同义标签（`paper` / `paper_evidence` / `paper_derived` / `paper_claimed` /
`paper_only` / `paper_assertion` / `paper_url` / `paper_and_reference`）表达的是同一件事：
没查，只是论文这么写。

归成"外部工具核验"与"自述"两类后：

- 有外部工具核验的资源 **1247 / 4758 = 26.2%**（全语料 32.7%）；
- `status: available` 的 2392 条里，**1192 条（49.8%）没有任何外部核验**（全语料 42.6%）。

**这两项 e07 比全语料更差。** 也就是说，即便在执行最干净的一批里，一半的"可用"
是模型自己说的。"区分论文声称与材料观察"这条评测原则不是要新增，是**已经失效**了。

### 2.4 实际死掉的枚举值（e07）

| 枚举 | e07 分布 | 判断 |
|---|---|---|
| `relation_type` | used 53.3% / introduced 25.3% / evaluated 20.2% / cited_only 1.2% / **extended 2 条** / unknown 0 | 六值实际是三值；`extended` 在 4758 条里只有 2 条，与全语料 15996 条里的 2 条是同一批 |
| `kind` | benchmark 38.5% / dataset 23.5% / tool 13.2% / code 12.1% / model 11.2% / **resource 50 条 / protocol 17 条 / skill 2 条** | 八值实际是五值 |
| `paper_type` | **method 77.1%** / benchmark 11.9% / empirical 7.1% / dataset 2.2% / survey 7 篇 / position 5 篇 / theory 3 篇 / unknown 1 篇 | 比全语料（70.9%）更集中，筛选价值很低 |
| `extraction_confidence` | high 82.5% / medium 17.3% / low 0.2% | 模型自评，无区分度 |
| `agent_callable.can_wrap` | False 91.4% | 见第 5 节 |
| `agent_callable.estimated_wrapping_difficulty` | unknown 90.8%（notes 另有 65.5% 为空） | 同上 |

`extended` 值得单独说：v1 协议把它列为四种核心关系之一，还给了例子（"某论文在 HypoBench
上加了新维度"）。两份语料里它都只有 2 条——说明要么定义不清，要么它本该是
"使用记录里的一个字段（改动了什么）"，而不是与 used 并列的关系类型。这是 6.2 的依据。

### 2.5 资源身份把不稳定的 kind 编进了 id

`resource_id` 形如 `<kind>::<slug>`。kind 判断本身不稳定，于是**同一资源在跨论文聚合时
天然分裂**。e07 这批：

- 4758 条实例对应 3552 个不同 id；
- 3275 个规范化资源名中，**248 个（7.6%）对应多个 id**（全语料 10.1%）；
- `benchmark::math-500` 28 次与 `benchmark::math500` 20 次并存，另有 `dataset::math-500`；
- GPT-4o 散成 `benchmark::gpt-4o` / `model::gpt-4o` / `resource::gpt-4o` / `tool::gpt-4o`；
- LLaMA-Factory 散成 `code::llama-factory` / `code::llamafactory` /
  `tool::llama-factory` / `tool::llamafactory`——kind 和写法两个维度同时分裂。

v1 协议说 Layer4 不做跨论文消歧，这没错。但 id 的构造方式决定了 Layer3 能不能补救：
把一个易错的语义判断编进主键，等于把错误固化进身份。这是本文新增的一条改造（6.6），
优先级不低于实验设定结构化；对 e07 的下一步（p1 建 paper–resource 边）尤其直接。

篇内引用完整性没问题：全语料 `resources_introduced` / `resources_used` 引用的 15837 个 id
全部能在同篇 `resource_records.yml` 找到，0 悬空。

### 2.6 "使用准备"目前几乎没有字段支撑

| 字段 | e07 空值率 | 全语料 |
|---|---|---|
| `access.license` | 86.6% | 82.5% |
| `access.url` | 57.1% | 51.7% |
| `repository.canonical_url` | 74.3% | 73.1% |
| `repository.verification.notes` | 79.8% | 80.3% |
| `access_type: unknown` | 48.0% | 43.3% |
| `paper_relation.citation_context_ids` | 35.6% | 33.4% |

**每一项 e07 都不比全语料好。** 一半以上资源没有 URL、近九成没有许可。
Q4（入口、使用说明与待核查事项）现在基本无从谈起。

### 2.7 证据字段不可程序校验

`paper_relation.evidence` 是自由文本，且是复合串——常见形态是把 section 标题和引文拼在
一起，有时是转述，**且论文内证据与外部材料证据混在同一个字段**。e07 抽样 500 条与论文
markdown 比对：严格滑窗匹配可定位 **83.6%**，放宽后（去 section 前缀、40 字窗、
三分之一命中即算）**93.4%**；`section` 字符串能在正文出现的比例 89.5%。

未命中样本说明了混用问题——例如 `2026.acl-long.1490` 的
`model::macco-pretrained-checkpoints`，证据写的是 `readme.md: the pretrained checkpoints
... available at https://huggingface.co/...`，来自仓库 README 而非论文。
这类证据永远无法在正文定位，但现在和论文证据占用同一个字段。

引文侧：e07 共 39,433 条 citation context（每篇中位 40 条，最多 200 条），
`citation_function` 有 20.5% 是空串，`background`（20.1%）+ `method_source`（19.3%）
占掉四成。逐条标注的成本与它的区分度不匹配。

## 3. 现状对四类研究行动的缺口（以 e07 为准）

| 研究行动 | 当前承载字段 | 判断 |
|---|---|---|
| 发现、筛选 | `intent`、`contributions` | 完备性好（contributions 空 2.0%），但 `paper_type` 77.1% 是 `method`，几乎不能用于筛选 |
| 理解、判断差异 | `experiments: [{text}]`、`limitations` | **最大缺口**：自由文本不可比较、不可过滤；e07 的 `experiments` 中位 3 条，都是句子 |
| 寻找资源、判断用途 | `resource.description`、`kind`、`relation_type` | **第二缺口**：v1 承诺的 `domain` / `evaluation_metrics` 从未落地；id 分裂使跨论文聚合不可靠 |
| 选择、使用准备 | `access`、`availability_status`、`repository`、`agent_callable` | **实测几乎为空**（2.6），且 `available` 中 49.8% 未经核验 |

## 4. 建议实现（v1 写过但没落地）

1. **资源用途画像。** `resource_record` 增加任务、领域、评测指标、规模、语言、许可、
   使用前置条件。只在论文有证据或外部卡片（README / HF card）可观察时填写。
   这是 v1"资源描述的最小字段"承诺过、schema 里缺失的部分。
2. **方法具名实体。** 当前只有 `contributions` 自由文本，没有"本文提出的方法或系统
   叫什么、有哪些别名"。缺它则跨论文关联只能靠标题模糊匹配。成本极低。
3. **材料完备性的程序化核验。** 仓库是否非空、有无 README、有无依赖声明与入口、许可、
   最近提交时间。v2 的外部验证阶段已在调用 GitHub / HF API，这些是顺手可得的观察，
   但没有进入 schema——于是出现 2.3 的局面：观察做了一部分，记录不下来。

## 5. 建议精简

以下每条都有 2.x 的实测支撑，不再是偏好问题。

- **`agent_callable`**：e07 里 `can_wrap` False 91.4%、difficulty `unknown` 90.8%、
  notes 空 65.5%。无证据、无区分度、无法核验。建议删除，或降级为第 4 节第 3 条那组
  程序可核验信号。
- **九个恒空字段**（2.1）：`metadata.authors`（或改为从 arXiv 元数据回填）、`figures`、
  `tables`、`cites`、`cited_by`、`citation_context.cited_by`、`source_paper`、`comparison`、
  `availability_check.checked_at`。要么删，要么给出产出路径，不留"看起来已核查"的空壳。
- **`citation_functions` 全量标注**：改为选择性标注，只标
  `dataset_source` / `benchmark_source` / `baseline` / `method_source` /
  `model_source` / `tool_source` / `contrast`，其余留空。
- **`extraction_confidence`（模型自评）**：82.5% 是 `high`，无区分度。
  用"谁观察到的"替代"模型觉得多有把握"（见 6.4）。
- **死枚举值**（2.4）：`kind` 的 `skill` / `protocol` / `resource`、`relation_type` 的
  `extended`。删除，或者写清触发条件并在 prompt 里给正例——现状是两头不落地。
- **`claims` 限 1–2 条、由摘要总结**：摘要已在记录中，这是复述。保留的唯一理由是把
  claim 链接到支持它的实验条件；不做链接就删。
- **v1 的 4.3 AgentCallable（`skill_wrapped` / `skill_candidate`）**：删除。
- **`source_artifacts` 的 HTML / TeX 下载**：v2 已后置为可选增强，保持，不进主流程质量线。

## 6. 建议改造（六条）

YAML 为草图，用于说明字段形态，不是最终 schema。字段过多本身是风险，见第 8 节。

### 6.1 实验设定结构化

`experiments: [{text}]` 改为可比较、可过滤的结构。服务"判断差异"与"判断资源用途"。

```yaml
experiments:
- experiment_id: 2025.acl-long.803::exp::1
  task: long-context instruction following
  resources_used:
  - resource_id: res.lifbench             # 见 6.6：id 不再编码 kind
    role: evaluation_target               # training_data | evaluation_target | analysis_input | unknown
    split: ""
    subset: 11 tasks across 3 scenarios
  subjects:
  - name: 20 prominent LLMs
    version: ""
  conditions:
  - dimension: context_length
    values: 4k / 8k / 16k / 32k / 64k / 128k
  metrics:
  - name: Instruction Following Stability (IFS)
    scoring: program                      # program | llm_judge | human | unknown
  baselines: []
  evidence: {...}                         # 见 6.3
```

### 6.2 资源关系升级为使用记录

`relation_type` 六值实际只用到三值（2.4），而真正决定"我能不能照着做"的信息
——哪个 split、哪个版本、哪个子集、改动了什么——没有位置存放。
`extended` 在两份语料里都只有 2 条，恰好说明它应该是使用记录里的一个字段。

```yaml
paper_relation:
  role: evaluated                # introduced | used | evaluated | cited_only | unknown
  split: test
  subset: ""
  version: ""
  modification: ""               # 取代 relation_type: extended
  evidence: {...}
```

### 6.3 证据定位可程序校验

现状：复合自由文本，e07 抽样 500 条严格匹配 83.6%、放宽 93.4%（2.7）。
改为结构化定位后，"证据是否真在原文"就是一次字符串比对，可以进质量报告的通过线。
同时把外部来源的证据（README、模型卡）与论文证据分开存放，不再混进同一字段——
这是 2.7 未命中样本的主要成因。

```yaml
evidence:
  origin: paper                  # paper | repository | model_card | external_page
  section_id: sec-5
  paragraph_index: 42
  char_span: [1204, 1388]
  quote: '...'
```

代价：`build_paper_inputs.py` 需要给拼装全文加段落编号并送进 prompt。

### 6.4 字段级来源分级

现状是 29 个自由标签、58.9% 写着 `agent`、`available` 中 49.8% 未经核验（2.3）。
这一条不是新增能力，是修复已经失效的区分。

```yaml
field_status:
  source: paper_claim            # paper_claim | external_observation | inferred
  observed_by: github_api        # 仅 external_observation 时有值，受控词表
  observed_at: '2026-06-30T18:33:11Z'
```

不要用模型自评的 confidence 代替它（2.4：82.5% 都是 high）。

### 6.5 空值三态

现状一个空列表同时表示"论文没有""没抽出来""合并丢了"（2.2）。

```yaml
field_status:
  absence: not_checked           # not_applicable | not_found | not_checked，仅在值为空时出现
```

### 6.6 资源身份与 kind 解耦

现状：id 形如 `<kind>::<slug>`，kind 判错即身份分裂；e07 里 7.6% 的资源名对应多个 id，
LLaMA-Factory 因 kind 与写法两个维度同时分裂成四个 id（2.5）。

建议 id 由规范名加可选来源锚（GitHub `owner/name`、HF `type/org/name`、DOI、URL）构成，
kind 降为可修正的属性；同时保留 `name_normalized` 与 `aliases` 供 Layer3 聚合。
Layer4 仍然不做跨论文消歧——它只需要**不把易错判断固化进主键**。

```yaml
resource_id: res.gsm8k                 # 不含 kind
name: GSM8K
name_normalized: gsm8k
aliases: [Grade School Math 8K]
kind: benchmark                        # 属性，可被 Layer3 修正
anchors:
  github: openai/grade-school-math
  huggingface: dataset/openai/gsm8k
```

## 7. 与 v2 流水线的落地成本

6.1 / 6.2 / 6.4 / 6.5 / 6.6 落在现有两次调用之内：调用 1 扩展 schema，
调用 2 扩展资源画像与来源分级。input 基本不变，output 从约 4–5K 升到约 8K。
改动量集中在 schema、prompt 与 `apply_agent_judgment.py` 的合并逻辑。
6.3 额外需要改 `build_paper_inputs.py`。

6.6 有一个只涉及既有数据的轻量版本：不重新抽取，仅在 Layer3 侧按
`name_normalized` + anchors 归并现有 id，把 kind 冲突记为待裁决。
这对 e07 的 p1（建 paper–resource 边）可能比任何新字段都更早需要。

另有一件与 schema 无关、可独立决定的事：2.2 的 2025 批约 800 篇合并丢失，
可以用现存 `agent_judgment.json` 零 LLM 成本恢复。

## 8. 风险与不确定

1. **新字段的正确性比现有字段难核验得多。** 实验设定与资源用途若没有独立小样本标注，
   结果只会是更长的自由文本。第 2 节能给出这么多数字，恰恰因为它们都是结构性指标；
   新字段的价值不在结构层，量不出来。
2. **字段数量本身是风险。** 6.1 的草图接近上限形态；试抽若显示某些子字段抽不稳定
   （如 `baselines`、`subset`），直接删掉而不是留空占位——2.1 的九个恒空字段就是
   "先留着"的结果，e07 这批一个都没好转。
3. **e07 干净，但不能据此推广。** 它是 961 观测集的子集（口径见第 0 节），
   数字应读作较好情形。更要紧的是：一旦按 e07 计划第 3 步向外扩展，
   2025 批论文会带进 40.6% 的合并丢失，池内质量将不再一致。扩展前建议先做 7 节的恢复。
4. **本文未回答**：新字段是否真的改变研究行动的判断结果。这是第 9 节要先验证的。

## 9. 待商定

下一步仍建议是一件事：**在 e07 的少量论文上做一次 schema 试抽**，先做 6.1 与 6.2，
人工核验一小部分，回答两个问题——这些字段能否稳定抽出；有了它们，"判断差异"与
"判断资源用途"的结论是否真的不同。若答案否定，其余改造不应进行。
e07 已有 952 篇的全文、Layer4 记录与引用材料，是现成的试抽底座。

需要用户决定：

- 是否做试抽；先做哪几条；样本量与人工核验规模。
- 6.6 的轻量版（只归并既有 id，不重抽）是否先于试抽做——它直接影响 e07 的 p1。
- 是否重跑 2025 批的合并以恢复约 800 篇语义字段；是否在 e07 向外扩展之前完成。
- 第 2 节的统计是否需要落为可复跑的脚本（当前是一次性统计，脚本未入库）。

未经确认不创建实验目录、不写脚本、不启动批量运行。
