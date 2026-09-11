# Layer4 Schema 改造：一份意见稿

状态：**提议，未商定，未实施。** 本文记录 Agent 对 Layer4 schema 的看法，供讨论与否决。
没有任何字段改动被落地，`experiments/p4a/src/extract/layer4_v2/schemas.py` 与
`skill/paper-mineru-resource-extract/SKILL.md` 保持原样。

依据材料：

- 研究方向与研究行动：[Papers for Agents：讨论与备忘](2026-09-09-paper-for-agents.md)（第 12、13 节）
- 原始协议：[P4A v1 协议](p4a-v1-protocol.md)（Layer4 与 4-3 过渡契约）
- 抽取现状：`experiments/p4a/refractor.md`（v2 方案与 2026-07 实测）、
  `experiments/p4a/src/extract/layer4_v2/schemas.py`（两次 LLM 调用的 guided schema）、
  `experiments/p4a/skill/paper-mineru-resource-extract/SKILL.md`（语义字段规则）

本文的意见只覆盖 Layer4（单篇论文的抽取契约），不提出 Layer3 的构建方法。

## 1. 判断原则：由留存的 Layer3 产物反推 Layer4 字段

v1 协议是自底向上写的：Layer4 抽什么 → 4-3 过渡 → 分类树与谱系。它的
`layer3_processing_contract` 列出 7 个下游产物，Layer4 的字段集是这 7 个的并集。

新方向只承认四类研究行动（发现/筛选、理解/判断、寻找资源并判断用途、选择与使用准备）。
建议先收敛 Layer3 的产物集合，再决定 Layer4 抽什么——否则 Layer4 会继续为没有下游的
字段付出抽取成本和核验债务，而这些字段的正确性最终无人检查。

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

## 2. 现状对四类研究行动的缺口

对照当前 `SEMANTIC_CANDIDATES_SCHEMA` 与 `JUDGED_RESOURCES_SCHEMA`：

| 研究行动 | 当前承载字段 | 判断 |
|---|---|---|
| 发现、筛选 | `intent.{paper_type, research_problem, target_domain}`、`contributions` | 够用。`cited_by` 来自外部 API，本就不属于抽取契约 |
| 理解、判断差异 | `experiments: [{text}]`、`limitations` | **最大缺口**：自由文本不可比较、不可过滤 |
| 寻找资源、判断用途 | `resource.description`、`kind`、`relation_type` 五值 | **第二缺口**：v1 承诺的 `domain` / `evaluation_metrics` 从未落地 |
| 选择、使用准备 | `access`、`availability_status`、`repository`、`agent_callable` | 基本够用，但 `agent_callable` 是无证据的模型猜测 |

## 3. 建议实现（v1 写过但没落地）

1. **资源用途画像。** `resource_record` 增加任务、领域、评测指标、规模、语言、许可、
   使用前置条件。只在论文有证据或外部卡片（README / HF card）可观察时填写。
   这是 v1 "资源描述的最小字段"承诺过、schema 里缺失的部分，也是从"能找到资源"
   到"能判断适不适用"的分界。
2. **方法具名实体。** 当前只有 `contributions` 自由文本，没有"本文提出的方法或系统
   叫什么、有哪些别名"。缺它则任何跨论文关联只能靠标题模糊匹配。成本极低，是
   taxonomy 与 genealogy 延后之后唯一值得保留的原料。
3. **材料完备性的程序化核验。** 仓库是否非空、有无 README、有无依赖声明与入口、许可、
   最近提交时间。v2 的外部验证阶段已在调用 GitHub / HF API，这些是顺手可得的观察，
   但目前没有进入 schema。

## 4. 建议精简

- **`agent_callable`（`can_wrap` / `estimated_wrapping_difficulty`）**：模型猜测，
  无证据、无法核验，与"区分声称与观察"的评测原则直接冲突。建议删除，或降级为
  第 3 节第 3 条那组程序可核验信号。
- **`claims` 限 1–2 条、由摘要总结**：摘要本身已在记录中，这是复述。保留的唯一
  理由是把 claim 链接到支持它的实验条件；不做这个链接就建议删除。
- **`citation_functions` 全量标注**：一篇 50–100 条引用全部打 13 类标签，成本随引用数
  线性增长，而下游只用到少数几类。建议改为选择性标注，只标
  `dataset_source` / `benchmark_source` / `baseline` / `method_source` /
  `model_source` / `tool_source` / `contrast`，其余留空。降成本同时提高一致性。
- **`content_units.figures` / `tables`**：实例中恒为空列表。不填就删字段——空字段会被
  下游误读为"已核查、确实没有"。
- **v1 的 4.3 AgentCallable（`skill_wrapped` / `skill_candidate`）**：删除。新叙事的
  使用准备止于入口、条件与待核查事项，不承诺把资源包装成 skill。
- **`source_artifacts` 的 HTML / TeX 下载**：v2 已后置为可选增强，这个决定保持，
  不纳入主流程质量线。

## 5. 建议改造（五条）

以下 YAML 为草图，用于说明字段形态，不是最终 schema。凡草图中出现的枚举值都需要在
试抽后复核；字段过多本身就是风险，见第 7 节。

### 5.1 实验设定结构化

`experiments: [{text}]` 改为可比较、可过滤的结构。这一条同时服务"判断差异"与
"判断资源用途"，是把可读摘要升级为可判断依据的关键改造。

```yaml
experiments:
- experiment_id: 2025.acl-long.803::exp::1
  task: long-context instruction following
  resources_used:
  - resource_id: benchmark::lifbench
    role: evaluation_target      # training_data | evaluation_target | analysis_input | unknown
    split: ""
    subset: 11 tasks across 3 scenarios
  subjects:                      # 被评对象
  - name: 20 prominent LLMs
    version: ""
    kind: model
  conditions:                    # 实际变化的实验维度
  - dimension: context_length
    values: 4k / 8k / 16k / 32k / 64k / 128k
  metrics:
  - name: Instruction Following Stability (IFS)
    scoring: program             # program | llm_judge | human | unknown
  baselines: []
  evidence: {...}                # 见 5.3
```

### 5.2 资源关系升级为使用记录

`relation_type` 的五值太粗。同样是 `used`，用的是哪个 split、哪个版本、哪个子集、
是否改动过，决定了后续研究能否照做。反向索引（"已有研究如何使用它"）在 Layer3 聚合，
Layer4 负责产出可聚合的单元。

```yaml
paper_relation:
  role: evaluated                # introduced | used | evaluated | extended | cited_only | unknown
  split: test
  subset: ""
  version: ""
  modification: ""               # 本文对资源做过的改动，无则留空
  evidence: {...}
```

### 5.3 证据定位可程序校验

当前 `evidence = {section, quote}` 是自由文本，无法程序验证引文是否真在原文对应位置。
"支持返回原材料检查"这条系统责任能否被评测，取决于这一改造；否则证据链只能人工抽检。

```yaml
evidence:
  section_id: sec-5
  paragraph_index: 42
  char_span: [1204, 1388]
  quote: '...'
```

代价：`build_paper_inputs.py` 需要给拼装全文加段落编号，并把编号一并送进 prompt。

### 5.4 字段级来源分级

目前只有资源级 `confidence` 与 `availability_check.checked_by`。评测原则要求区分
论文声称、材料观察、执行成功与复现，这个区分必须落在数据里，不能只写在文档里。

```yaml
field_status:
  source: paper_claim            # paper_claim | external_observation | inferred
  confidence: high               # high | medium | low
```

### 5.5 空值三态

v1 说 Layer4"允许字段留空"，但没有区分三种留空。评测要考察不确定性处理，不区分就无法
评分。这也是 v2 实测 `checked_by` 分布里 `none` 占大半那个问题的 schema 层根因。

```yaml
field_status:
  absence: not_checked           # not_applicable | not_found | not_checked，仅在值为空时出现
```

## 6. 与 v2 流水线的落地成本

上述改造大部分落在现有两次调用之内：调用 1 扩展 schema（实验记录、方法具名、使用细节、
证据区间），调用 2 扩展资源画像（用 README / card 做外部观察）。input 基本不变，
output 从约 4–5K 升到约 8K。真正的改动量在 schema、prompt 与 `apply_agent_judgment.py`
的合并逻辑，不在流水线结构。5.3 额外需要改 `build_paper_inputs.py`。

## 7. 风险与不确定

1. **新字段的正确性比现有字段难核验得多。** 实验设定与资源用途两类字段，若没有独立的
   小样本标注，结果只会是更长的自由文本，反而稀释 Layer4 的可信度。
2. **字段数量本身是风险。** 5.1 的草图接近上限形态；试抽若显示某些子字段抽不稳定
   （例如 `baselines`、`subset`），应当直接删掉而不是留空占位。
3. **新旧不可比。** 已完成的批次（`refractor.md` 记录的 2026-07 实测为 1071 篇 acl-long）
   不重跑，新增字段会使新旧结果不可比。对照实验要么限定在新批次，要么接受两套字段集。
4. **本文未回答的**：新字段是否真的改变研究行动的判断结果。这是第 8 节要先验证的事。

## 8. 待商定

建议的下一步是一件事：**在少量已完成论文上做一次 schema 试抽**，只加 5.1 与 5.2 两条，
人工核验其中一小部分，回答两个问题——这些字段能否稳定抽出；有了它们，"判断差异"与
"判断资源用途"的结论是否真的不同。若答案是否定的，第 5 节其余改造不应进行。

需要用户决定：是否做试抽；先做哪几条；样本取自 ACL 2025 已完成批次还是 2026 进行中批次；
样本量与人工核验规模。未经确认不创建实验目录、不写脚本、不启动批量运行。
