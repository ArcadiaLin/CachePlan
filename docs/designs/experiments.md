# Experiments 抽取设计

日期：2026-09-20。状态：设计稿，未实施，未改 `schemas.py`。

本文档只管一件事：**把论文的实验条件与结果，组织成可跨论文筛选与比对的形态。**
总体设计在 `docs/designs/main.md`，本文档是其第 4 节在 experiments 这一块的落地。

## 出发点与基线

基线是 `docs/discussions/2026-09-13-layer4-schema-proposal.yml`（Layer4 schema v3 提议稿），
不是更早的 `p4a-v1-protocol.md`。v3 已经解决的，本文档不重复，只登记沿用：

| v3 已有 | 在总体设计中的对应 |
| --- | --- |
| `evidence: {origin, section_id, paragraph_index, char_span, quote}` | 第 6 节的 locator 与内容锚；第 8 节跨度级失效判定的前提 |
| `field_status.absence: not_applicable / not_found / not_checked` | 第 4 节的不完备信息三态 |
| `field_status.source: paper_claim / external_observation / inferred` | 第 7 节 Q5 的 `evidence_tier`（**命名待对齐，见下**） |
| `provenance: {inputs_digest, model, prompt_version, last_checked}` | 第 1 节"派生可确定重算"的前提；第 6 节写入时间 |
| `experiments[].{task, resources_used[].role, metrics[].scoring, result_refs}` | Q7 的资源角色；Q4 的指标口径 |

v3 未解决、本文档处理的两处：

1. `conditions: [{dimension, values}]` 的 `dimension` 是自由字符串、`values` 是原文串
   （`"4k / 8k / 16k / 32k / 64k / 128k"`）。**跨论文筛选做不了**，Q1 / Q6 落空。
   `subjects[].name`（`"20 prominent LLMs"`）是同一个问题。
2. **没有 result 记录。** `result_refs` 只指到表，没有数值。Q1 是"结果可比性"，
   没有 result 就无从谈起。

## 设计

### 已定：维度是数据，不是 schema 常量（2026-09-20）

维度集不写死在 schema 里，而是库中的一类记录，跨论文共享，有版本、有归属：

```yaml
dimension:
  name: hardware
  version: v1
  subfields:                          # 可为空（如 metric 这类扁平枚举）
  - {name: model, domain: enum}       # A100 | H100 | V100 | TPUv4 | ...
  - {name: mem,   domain: quantity}   # 数值 + 单位
  - {name: link,  domain: enum}       # PCIe | NVLink | ...
  - {name: count, domain: int}
  promoted_by: [Q1, Q6]               # 升格依据：哪个探针要筛它
  归属 + 三元时间
```

新增一个维度 = 写一条记录 + 对已有语料**回填一次派生**，不是改 schema。
回填成本是可报出的数字（第 9 节的构建与维护成本），不是不可控的迁移。

**升格规则**：维度由 `main.md` 第 1 节已接受的 intent、第 7 节的探针倒推——探针要筛什么，
什么就升格。不另建负载记录设施。首轮种子维度由我们按探针清单人工指定，**是人定的，
不包装成自动导出**。

升格与降级都不丢信息：原文串照样原样保留在 `raw` 里。因此这是纯粹的可查询性决策，
不是语义承诺，可以错、可以反悔，代价只有派生成本。

### 已定：取值是带可选子字段的受限记录，粒度差即子字段缺失（2026-09-20）

不同论文报告条件的粒度天然不同。不做归一，也不建本体树，而是让粒度差表现为**子字段缺失**：

| 原文报告 | 派生取值 |
| --- | --- |
| `A100` | `{model: A100}` |
| `A100 40G PCIe` | `{model: A100, mem: 40G, link: PCIe}` |
| `single GPU` | `{count: 1}` |
| `8×A100 80G NVLink` | `{model: A100, mem: 80G, link: NVLink, count: 8}` |

缺的子字段**不写记录**，其含义就是 `not_checked`（论文没报）。查过确认论文明确不报、
或该属性不适用，才显式写 `not_found` / `not_applicable`。

比对逐子字段做，落回三态：

- `A100 40G` vs `A100 80G` → `mem` 冲突 → 可判定地不同，这是有判别力的部分
- `A100` vs `single GPU` → 子字段不相交 → 一致与冲突都判不出，如实报"至少一方未报告"
- `A100` vs `A100 40G PCIe` → `model` 一致，其余一方未报告 → 不冲突，但不敢说相同

三条理由：**不需要维护领域本体**（偏序/subsumption 树是长期债务，子字段缺失能表达同样的
东西且是纯结构的）；**复用已有三态**，不新造设施；**落在可确定重算的一侧**——子字段值域
受限，符合 `main.md` 第 1 节"收紧输出空间后可确定重算"，而原文串照样保留，不可重算的部分
不碰。

代价：子字段集合也会漏。漏了 `quantization`，两篇量化不同的工作会被判成"未报告"而不是
"冲突"——**漏报，不是误报**。方向是对的，漏掉的子字段按同一条升格规则补上并回填。

### 已定：evidence 落到子字段粒度（2026-09-20）

v3 的 `evidence` 挂在 `conditions[]` 条目上。这不够：同一个 `hardware` 里，`model` 常来自
setup 节、`count` 常来自表格脚注，**locator 不同**。因此 evidence 下沉到子字段。

由此顺带解决"论文级默认"：全文说"实验在 A100 上跑"、Table 3 又说"该组用 8 卡"时，
**不建继承链，落盘一律扁平，来源由 locator 自然区分**——继承来的取值其 locator 指向
setup 节，局部报告的指向表格附近。

好处三条：查询路径上没有继承解析；忠实性不丢（看 locator 指哪儿）；**第 8 节白赚一条**——
论文改版时 setup 那段被改，所有 locator 指向那段的派生取值一次性全被标待复核，跨 setting
生效，不需要额外的父节点失效传播。

代价：同一句话被多条取值引用，失效时一次标一片。它们确实全都该复核。

### 已定：新增 result 记录（2026-09-20）

v3 的缺口。最小形态：

```yaml
results:
- result_id: 2025.acl-long.803::result::1
  experiment_id: 2025.acl-long.803::exp::1
  subject: {name: GPT-4o, version: ''}        # 哪个被测对象
  metric: {name: IFS, scoring: program}       # 指标与打分方式，沿用 v3 词表
  value: 42.1
  unit: ''
  condition_overrides:                        # 相对所属 experiment 的局部条件
  - {dimension: context_length, subfield: value, value: 128k}
  evidence:
    origin: paper
    table_id: 2025.acl-long.803::tab::2       # 表格来源需要 cell 级定位
    cell: [row, col]
    quote: ''
```

**范围限制（首轮）**：只抽论文在正文里明确陈述的关键数值，以及对应表格的单元定位；
**不做全表逐单元抽取**。理由是成本与错误率——v3 附录 C 第 1 条已经警告过新字段比旧字段
难核验。全表抽取是否值得，留待试抽数据回答。

`evidence` 需要从 v3 的 `{section_id, paragraph_index, char_span}` 扩出表格分支
（`table_id` + `cell`）。这是 v3 `result_refs` 的细化，不是另起炉灶。

## 落到 v3 YAML 上的改动

以 `2025.acl-long.803` 为例。

**改动前（v3）：**

```yaml
conditions:
- dimension: context_length
  values: 4k / 8k / 16k / 32k / 64k / 128k
subjects:
- name: 20 prominent LLMs
  version: ''
```

**改动后：**

```yaml
conditions:
- dimension: context_length@v1            # 指向维度注册表，带版本
  raw: 'six length intervals (4k to 128k)'   # 原文串照抄，永不归一
  values:
  - subfield: min
    value: 4k
    evidence: {origin: paper, section_id: sec-1, paragraph_index: 9, char_span: [...], quote: '...'}
  - subfield: max
    value: 128k
    evidence: {origin: paper, section_id: sec-1, paragraph_index: 9, char_span: [...], quote: '...'}
subjects:
- dimension: model_under_test@v1
  raw: '20 prominent LLMs'
  values:
  - {subfield: count, value: 20, evidence: {...}}
  # model 子字段此处不写：论文摘要未逐一列出 → 含义即 not_checked
```

抽取产物保持这种嵌套形态（好抽、好读、好核）。入库后是否展开为
`(setting, dimension, subfield) → value + locator` 的三元组存储，是实现选择，
本文档不定；展开是确定的，因为 evidence 已经逐子字段齐备。

## 待确认：与 v3 的两处词表冲突

1. **三态命名不一致。** `main.md` 第 4 节写的是 `unchecked` / `absent` / `not_applicable`，
   v3 写的是 `not_checked` / `not_found` / `not_applicable`。同一组概念，两套名字。
   建议统一采用 v3 的命名（更接近产物与代码），并回改 `main.md`。

2. **`field_status.source` 与 `evidence_tier` 不是同一个轴。**
   v3 的 `paper_claim | external_observation | inferred` 混了两件事：前两者是**证据强度**，
   `inferred` 是**派生方式**。而 `main.md` 第 7 节 Q5 要的三层是"作者声称 / 仓库静态观察 /
   复现结果"——v3 没有"复现结果"这一档。建议拆成两个字段：
   `evidence_tier: paper_claim | external_observation | reproduction`（证据强度，Q5 用）
   与 `derivation: extracted | inferred`（派生方式，服务可确定重算的划线）。

这两条都不是本文档能单方面定的，需在总体设计侧确认后同步修改两边。

## 未解决

- 首轮种子维度清单具体是哪些（按探针清单人工指定，尚未列出）。
- 维度注册表的存放位置与形态：单独文件、还是 Layer3 侧的一类记录。
- 回填的触发与成本：新增维度后重跑哪些论文、代价多少，需要试抽数据。
- 表格 cell 级定位依赖 MinerU `content_list` 的表结构解析质量，未验证。
- v3 附录 C 第 1 条的风险在此同样成立：`conditions` / `results` 若没有独立小样本标注，
  很可能只是变长的自由文本。试抽后若某子字段抽不稳定，直接删该子字段，不留空占位。
