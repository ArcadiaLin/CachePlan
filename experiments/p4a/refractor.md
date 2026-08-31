# Layer4 抽取流程重构方案（v2）

> 修订说明：本版在初稿基础上，依据 2026-07-09 对现网流水线的实测数据（1071 篇已完成 acl-long、3 个 Kimi 会话逐事件解剖）修订。
> 主要变更：基线数字更新为优化后现状；调用 1 改为全文直喂、证据召回降级为超长论文的 fallback；引文链路从可选增强提升回主流程（软门禁）；补齐 arXiv 匹配 / HF 模糊搜索 / source_artifacts / agent_callable 四处职责归属；新增编排与失败语义、缓存 key 设计、带通过线的评估标准。

## 1. 要解决的问题

现在的 Layer4 是"每篇论文启动一个 Kimi ReAct Agent"。agent 读 skill、分块读全文、查 arXiv/GitHub/HuggingFace、下载文件、判断资源、写 JSON、跑验证脚本。

实测现状（经 prefix-cache 与代理优化后，2026-07-08 之后的批次）：

| 指标 | 实测值（中位） |
|---|---|
| 单篇会话耗时 | 144 s（全周期 172.5 s） |
| 工具调用 | 26 次 / 16 步 |
| 累计计费 input | **约 140 万 token** |
| 最终一步真实上下文 | 仅 8–11 万 token |
| output | 1.1 万 token |
| 吞吐 | 19.7 篇/h（串行，GPU 占空比约 52%） |

慢和贵的根因不是某个工具（外部核验单次仅几百 token、几秒），而是 **ReAct 循环每步重发全部历史**：input 计费被放大 10–18 倍；且 agent 的多轮性对最终产出贡献有限——实测 agent 最终也是一次 `Write` 写出完整 `agent_judgment.json`，之后只做定点小修。

另一个实测问题：抽样 50 篇的资源 `checked_by` 分布中 `none`/`agent`/`paper` 占大半，**agent 经常没有真正核验资源**。集中式程序验证同时是提速和一致性修复。

重构目标不变——换职责分工，不减少抽取内容：

- 程序做批处理、索引、下载、缓存、验证和 YAML 生成。
- LLM 做语义判断：是不是资源、资源类型、introduced/used/evaluated。
- 主流程只依赖 PDF；LaTeX、arXiv 源码、补充材料、多源融合为可选增强。

## 2. 新主流程

```Plain Text
PDF
  -> 2.1 PDF 解析 (MinerU)
  -> 2.2 引文链路 (软门禁: 失败降级不阻塞)
  -> 2.3 文档预处理 (索引 / 图表注压缩 / URL 清单 / 全文拼装)
  -> 2.4 LLM 候选抽取 (调用1: 全文直喂, guided decoding)
  -> 2.5 外部验证缓存 (程序, 无 LLM)
  -> 2.6 LLM 最终裁判 (调用2)
  -> 2.7 生成 YAML 和质量报告 (复用 apply/validate)
```

模型环境：本地 vLLM `qwen3.6-35b-a3b`，上下文 262K，prefix caching 已启用（实测命中率 89%）。论文 Markdown 全文 p50≈21K / p90≈37K / max≈43K token，全文进单次调用没有上下文压力。

### 2.1 PDF 解析

用 MinerU 把 PDF 转成结构化文本（现有批处理已覆盖，不在单篇关键路径上）。

产物：`parsed_document.md`、`parsed_document.json`、`parse_report.json`（对应现有 MinerU 输出，不重做）。

### 2.2 引文链路（从可选提升回主流程，软门禁）

主流程 schema 的 `citation_functions` 依赖引用上下文，因此引文链路必须留在主流程；但从**硬门禁改为软门禁**：

- 正常路径：复用现有 `extract_and_verify_references` → `repair_references` → `run_cite_contexts` 子链，产物 `verified_or_repaired.jsonl`、`cite_contexts.jsonl` 不变。
- 降级路径：子链失败（现状会标记 `blocked_reference_mismatch`，累计 65 篇）时，程序直接从 MinerU 文本抽取引用句上下文生成降级版 `cite_contexts.degraded.jsonl`，在 `run_report.json` 打 `citation_source: degraded` 标记，论文**继续走主流程，不再 blocked**。
- 降级版的 `citation_functions` 允许更保守（更多 `unknown`），质量报告单独统计降级篇目比例。

### 2.3 文档预处理（程序，替代原"证据召回"）

程序为每篇论文准备调用 1 的输入。**默认全文直喂，不做证据召回**——召回漏段是质量风险，而本地 vLLM 上省 prefill 的收益很小。

产物：

- `paper_index.json`：标题、摘要、章节大纲、页码（复用 `common.py` 的 `section_outline` 等）。
- `url_mentions.json`：正则/规则抽取的 URL、GitHub/HF 仓库名、疑似资源名清单（给 LLM 当聚焦提示，不替代其判断）。
- `captions.json`：从 `content_list_v2.json`（实测 47K 字符，绝大部分是版式元数据）压缩出的图注/表注文本，约 1–3K token。**原始版式 JSON 不进 prompt**。
- `fulltext_for_llm.md`：Markdown 全文剔除 References 节后的拼装稿。

Fallback：全文超过 100K token 的极端论文才走章节级证据召回（`evidence_pack.json`），并在报告中标记。

### 2.4 LLM 候选抽取（调用 1）

一次纯文本调用，无工具循环。prompt 组成与 token 预算：

| 组成 | 量级 | 说明 |
|---|---|---|
| 静态规则前缀 | 3–5K | SKILL.md 语义规则/枚举/schema 精简版；**所有论文字节级一致**，prefix cache 自动命中 |
| 论文元信息 + URL/资源名清单 | <1K | 程序注入，替代 agent_prompt.md 路径模板 |
| 全文（去 References） | 20–37K | `fulltext_for_llm.md` |
| 图表注 | 1–3K | `captions.json` |
| 引用上下文 + 参考文献 | ~1K | 2.2 产物（或降级版） |
| **合计 input** | **30–45K** | |

输出（**vLLM guided decoding 按 JSON schema 约束**，从根上消灭非法枚举/缺字段）：`semantic_candidates.json`，约 4–5K token：

- `paper_record` 语义部分基本定稿：paper_type、research_problem、contributions、claims（1–2 条，摘要级）、experiments、limitations、future_work、citation_functions。
- 资源候选清单（未核验草稿）：kind、name、relation_type、证据引文、paper 中出现的 URL、以及**无 URL 具名资源的检索线索**（规范名/别名，供 2.5 搜索）。

要求不变：没有证据的资源不能输出；不把概念/指标/loss 当资源；无 URL 的重要 dataset/benchmark/model 仍要抽取。

### 2.5 外部验证缓存（程序，无 LLM）

程序统一核验，替代 agent 的 MCP 循环。**本节同时认领原方案悬空的两处职责：arXiv 标题匹配、无 URL 资源的 HF 模糊搜索。**

验证对象与动作：

- GitHub repo：API 取元数据 + README 头部（~600 token 摘要进结果）。**必须带 token 并限速**（匿名 60 次/h 不够批量用）。
- HuggingFace model/dataset/space：API 取 card 摘要、license、可达性。
- **HF 模糊搜索**：候选里无 URL 的具名 dataset/model，按名搜索取 top-k 候选（含 card 摘要），**匹配置信度交给调用 2 裁决**，程序不做语义决定。
- **arXiv 标题匹配**：按论文标题搜索 arXiv，命中则产出 `metadata.arxiv_id` 与 `source_artifacts.arxiv` 元数据（下载 HTML/LaTeX 仍属可选增强 3.1）。
- 普通 URL / 项目主页 / Zenodo、OSF、Figshare：HEAD/GET 可达性 + 页面标题。

网络约束（现网踩坑固化）：arxiv.org / huggingface.co / github.com 出口一律走 `http://127.0.0.1:7899` 代理；本地服务（127.0.0.1、192.168.163.112）绝不走代理。

产物：`external_resolution.json`（单篇）+ 全局缓存。

缓存设计：

- 位置：`cache/github.jsonl`、`cache/huggingface.jsonl`、`cache/arxiv.jsonl`、`cache/url_status.jsonl`，附内存索引；追加写，进程内单写者。
- key：URL 规范化后（host 小写、去 tracking 参数、跟随重定向后的最终地址）；GitHub 以重定向后的 `owner/name` 为准；HF 以 `type/org/name` 为准；arXiv 搜索以规范化标题为 key。
- 过期：批次内不过期；跨批次跑前可用 `--refresh-cache` 强制重查。命中即跳过网络请求——GSM8K、MMLU 这类高频资源在 2655 篇中反复出现，命中率会很高。

### 2.6 LLM 最终裁判（调用 2）

一次纯文本调用。输入：

| 组成 | 量级 |
|---|---|
| 静态裁判规则（status/checked_by/枚举子集） | 0.3–0.8K（共享前缀，缓存命中） |
| 调用 1 的 `semantic_candidates.json` | 4–5K |
| `external_resolution.json`（含 README/card 摘要、HF 搜索 top-k） | 2–6K |
| **合计 input** | **7–12K** |

职责：候选去留；kind 终判；relation 终判（introduced/used/evaluated/extended/cited_only）；一个 URL 是否拆多个资源（依据 README/card 正文）；HF 搜索候选的置信匹配（不确定则 `access_type: unknown` + notes 说明）；描述、confidence、warnings；**`agent_callable`（can_wrap 等）字段**。

输出（guided decoding）：完整 `agent_judgment.json`，schema 与现网完全一致。其中 `source_artifacts.html_downloaded` / `tex_source_downloaded` 主流程一律默认 `unfetched`，由可选增强 3.1 后置更新——`apply_agent_judgment.py` 的字段兼容以此为约定。

### 2.7 生成 YAML 和质量报告（复用现有脚本）

程序运行 `apply_agent_judgment.py` → `validate_layer4_outputs.py`，产物不变：`paper_record.yml`、`resource_records.yml`、`resource_verification_report.json`、`run_report.json`、`quality_report.json`。

validate 失败的处理（对应现网 agent 的"定点 Edit"行为）：

1. **轻量修补调用**：只把报错字段清单 + 当前 judgment 喂给 LLM（~5K token），要求仅修报错字段，最多 2 次。guided decoding 已消灭 schema 类错误，走到这里的应只剩语义类校验。
2. 仍失败 → **回退现有 Kimi ReAct agent** 整篇重跑（旧链路已验证 1000+ 篇，作为兜底保证覆盖率下限），`run_report` 标记 `fallback: react_agent`。
3. 兜底也失败 → `blocked_v2_manual`，进人工清单。

## 3. 可选增强流程

不阻塞主流程，可单独失败。

### 3.1 arXiv / LaTeX / HTML 下载

对 2.5 已匹配到 arXiv 的论文，离线批处理下载 HTML / LaTeX source / supplementary，**后置更新** `source_artifacts` 字段与 `run_report`。走 7899 代理。与会议 PDF 冲突时以会议 PDF 为主并记录差异。

### 3.2 引文抽取增强

LaTeX source / bib 可用时构建更准的引用上下文，替换 2.2 的降级版产物并升级 `citation_source` 标记。

### 3.3 多源融合

同 v1：`fused_document.json` + `fusion_report.json`，PDF 为最终发表版本，source/supplement 补充线索。

## 4. 编排与失败语义

新增批量编排器 `launch_layer4_v2.py`（对位现有 `launch_kimi_layer4.py` 的职责）：

- **选篇与跳过**：复用现有逻辑（从 references JSONL 选 paper id，跳过 front-matter/proceedings）。
- **执行形态**：分阶段批处理。2.3 预处理与 2.5 验证是 CPU/IO 任务，进程池并行；2.4 / 2.6 对 vLLM 发并发请求（continuous batching，起步并发 8，观察 KV 占用后上调；现网实测 KV 占用 2.8%、0 抢占，余量充足）。
- **状态机**（写入 `run_report.status`）：`prepared → candidates_done → verified → judged → merged`；失败态 `fallback_agent`、`blocked_v2_manual`、`blocked_*`（沿用现有前缀语义）。
- **幂等与断点续跑**：每阶段以"产物文件存在且通过 schema 校验"为完成判据，重跑自动跳过已完成阶段；缓存追加写天然幂等。
- **报告**：`batch_report.json` / `batch_failures.json` 字段与现网兼容，新增每阶段耗时与 token 计量（喂给第 7 节评估）。

## 5. 推荐目录结构

与现有布局保持一致（year 在前）：

```Plain Text
processed/layer4_v2/<year>/<venue>/<paper_id>/
  paper_index.json
  url_mentions.json
  captions.json
  fulltext_for_llm.md
  semantic_candidates.json
  external_resolution.json
  agent_judgment.json
  paper_record.yml
  resource_records.yml
  resource_verification_report.json
  run_report.json
  quality_report.json

  optional/
    evidence_pack.json            # 仅超长论文 fallback
    source_discovery.json
    source_artifact_report.json
    references.jsonl / cite_contexts(.degraded).jsonl
    fused_document.json
    fusion_report.json

processed/layer4_v2/cache/
  github.jsonl  huggingface.jsonl  arxiv.jsonl  url_status.jsonl
```

## 6. 为什么不会降级

保留的能力与 v1 相同（无 URL 资源识别、relation 判断、证据强制、验证不决定语义、增强路径保留）。在此之上，v2 相比现网 agent 有三处**质量提升**而非持平：

- 全文直喂消灭了"证据召回漏段"这一类风险（v1 初稿自认的最大风险项）。
- 集中式程序验证修复 `checked_by` 不一致问题（现网大半资源实际未核验）。
- guided decoding 保证 schema 合法率 100%，消灭 repair 循环的主要来源。

兜底链（轻量修补 → 旧 agent → 人工）保证覆盖率不低于现网。

## 7. 实施步骤

### 第一步：预处理 + 调用 1 旁路

新增 `build_paper_inputs.py`（2.2 降级路径 + 2.3 全部产物）、`run_candidate_extraction.py`（调用 1，guided decoding）。

**在已完成的 1071 篇上直接跑**——它们是免费对照集。比较 `semantic_candidates.json` 对旧结果 `resources` 的覆盖，不需要新标注。

### 第二步：外部验证缓存

新增 `resolve_external_resources.py`（2.5，含缓存与限速）。在同一对照集上确认缓存命中率与验证准确率。

### 第三步：调用 2 + 兼容产物

新增 `run_final_judgment.py`。产出的 `agent_judgment.json` 直接过现有 `apply_agent_judgment.py` + `validate_layer4_outputs.py`，不改这两个脚本。

### 第四步：编排器与兜底

新增 `launch_layer4_v2.py`（第 4 节状态机 + 旧 agent 回退接口）。

### 第五步：可选增强

按收益接入 3.1–3.3，均为离线批处理，单独失败不阻塞。

## 8. 评估标准（带通过线）

对照集：从 1071 篇已完成 acl-long 随机抽 **200 篇**，v2 旁路全量跑通后对比：

| 指标 | 通过线 | 测法 |
|---|---|---|
| resource 召回率 | ≥95%（对旧结果资源清单） | 程序 diff；分歧样本人工裁决归因（旧错/新错/都对） |
| resource 精确率 | 不低于旧流程 | 人工抽检 50 篇 diff |
| kind / relation 一致率 | ≥90%（分歧人工裁决） | 程序 diff + 抽检 |
| citation_function | 抽检无系统性退化；降级篇目单独统计 | 人工抽检 |
| YAML schema 通过率 | 100%（guided decoding 保证） | validate 全量 |
| 单篇端到端耗时 | ≤60 s（并发 8 时的均摊） | batch_report 计量 |
| 单篇 token | input ≤80K、output ≤15K（含修补重试） | batch_report 计量 |
| 兜底率 | fallback_agent ≤5% | batch_report |

预期收益参考：每篇 input 从 ~140 万 → ~5 万 token；GPU 串行时间 ~35–50s/篇；并发 8–16 下吞吐上限 100+ 篇/h（现网 19.7 篇/h）。

**替换策略**：通过线全部达标后，v2 仅用于后续新批次（新 venue/年份）；已完成的 1071+ 篇不重跑。当前进行中的批次按旧流程跑完，不迁移。

## 附：本版修订依据的实测数据

- 吞吐/耗时：2026-07-08 优化后 15 小时窗口，295 篇，中位周期 172.5 s（前置 26.2 + 会话 144.3 + 收尾 3.5）。
- token：抽样 80 篇 `agent_usage.json`，累计计费 input 中位 140 万；3 个会话逐事件解剖显示最终真实上下文仅 8–11 万，放大 10–18 倍来自 ReAct 每步重发历史。
- 论文规模：抽样 40 篇 Markdown，p50 86KB（≈21K token）、p90 147KB（≈37K token）；`content_list_v2.json` 典型 47K 字符。
- 验证一致性：抽样 50 篇 `checked_by` 分布 `none` 142 / `github_mcp` 42 / `agent` 40 / `hf-readonly` 34 / 其他 12。
- vLLM：`qwen3.6-35b-a3b`，max_model_len 262144；prefix cache 命中率 89%，KV 占用 2.8%，0 抢占。
