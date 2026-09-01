# E01 — P4A 历史 session 轨迹的全量观测

**本项目的第一个实验。** 代码在 [`experiments/e01-p4a-trajectory/`](../../experiments/e01-p4a-trajectory/)，
运行方式与环境约定见该目录的 README。

- 性质：**观测，不是干预**。对象是已存在且不可变的 4083 份日志，只读、不跑 agent、不改 p4a 代码。
- 边界：P4A 数据只能做诊断性/动机性分析，**不能**作为「CachePlan 方法是否有效」的对照基线
  （见 [`p4a.md`](p4a.md) 第 4 节）。本页所有数字都受这条约束。
- 状态：**s0–s2 已完成；s3–s5 处于计划阶段，尚未实现。**

| 阶段 | 脚本 | 目标 | 状态 |
|---|---|---|---|
| s0 | `s0_manifest.py` | 语料清单与纳入过滤 | 已完成 |
| s1 | `s1_cache_fields.py` | 闸门：cache 字段是否可用 | 已完成（闸门关闭） |
| s2 | `s2_session_stats.py` | 放大倍数的全量分布与分层归因 | 已完成 |
| s3 | `s3_render.py` | **精确复现器**：还原每步真实进入模型的 token 序列 | 计划 |
| s4 | `s4_divergence.py` | 前缀分歧图谱：共享前缀在哪断、每类分歧值多少 token | 计划 |
| s5 | `s5_behavior.py` | 轨迹统计与可视化：router 条件、agency 行使程度 | 计划 |

---

## 1. 语料

4083 份 session，纳入 **3999**（extract 3762 / repair 237），覆盖 **3321** 篇不同论文。
单机单工作目录顺序执行，无并发混淆。

排除 84 份，理由逐条可统计（`data/processed/e01/s0_summary.json`）：

| 理由 | 份数 | 说明 |
|---|---|---|
| `aborted` | 73 | 起了步但一步没跑完。**是观测量而非噪声**，`abort_rate()` 单独统计 |
| `operator_chat` | 12 | 非 extract/repair 家族的人工会话 |
| `no_steps` | 5 | 一个 LLM 调用都没发生 |
| `multi_turn` | 4 | 多轮用户输入或 harness auto-continue |

---

## 2. 已完成阶段的结论

### s1（闸门）：cache 字段恒为零 — 闸门关闭，但**原因已查明**

| | |
|---|---|
| 判定 | `identically_zero`（字段上报了，值确实是零，**不是字段缺失**） |
| 范围 | 全语料 3999 份 / **62,649** 条 usage 记录 |
| 非零 `inputCacheRead` / `inputCacheCreation` | 0 / 0 |
| 全语料累计 prefill | **5,604,823,657 tokens** |

**归因（2026-09-01 补充，此前记为「原因未知」）**：零值是**上报缺陷，不是缓存未命中**。

- 服务端**当时开着** `--enable-prefix-caching`（`experiments/p4a/infra/vllm/docker-compose-qwen36-35B.yml`）。
- 对同一台服务（vLLM **0.21.0**）实测：重复前缀请求的服务端命中率为 **86.5%**
  （`/metrics` 的 `prefix_cache_hits_total` / `queries_total`），但响应体里
  非流式返回 `prompt_tokens_details: null`、流式**连这个 key 都没有**。
- kimi-code 的 `extractUsage`（`packages/kosong/src/providers/openai-common.ts:204`）
  取不到 `cached_tokens` 就记 0，于是日志里恒为零。
- `inputCacheCreation` 在 openai provider 路径上是**硬编码常量 0**（同文件 `:230`），
  不携带任何信息，**不应作为证据使用**。

**后果（对下游仍是硬约束）**：历史语料的真实命中率**不可恢复**，加任何 vLLM 参数都救不回来。
s3 之后一律基于复现出的 token 序列计算前缀重叠量，且必须标注为**结构性度量**，不得称作命中率。

**对未来运行的处置：已完成并验证（2026-09-01）。**

升级到 vLLM **0.22.1** 并加 `--enable-prompt-tokens-details` 后，用同一脚本、同一前缀复测，
**非流式与流式各验一次**（kimi-code 实际走流式，此前两条路径行为不一致，必须分别验）：

| | 服务端实测 `/metrics` | 响应体 usage | kimi-code 会记 | |
|---|---|---|---|---|
| 0.21.0 非流式 | 2112 / 2443 = 86.5% | `prompt_tokens_details: null` | 0 | ❌ |
| 0.21.0 流式 | 2112 / 2443 = 86.5% | **连这个 key 都没有** | 0 | ❌ |
| 0.22.1 非流式 | 2112 / 2443 = 86.5% | `prompt_tokens_details: {cached_tokens: 2112}` | **2112** | ✅ |
| 0.22.1 流式 | 2112 / 2443 = 86.5% | `prompt_tokens_details: {cached_tokens: 2112}` | **2112** | ✅ |

三点结论：

1. **流式风险解除。** 0.22.1 下两条路径返回的 usage 逐字相同。
2. **上报值 = 服务端实测值，非估算。** `cached_tokens` 与 `/metrics` 的
   `prefix_cache_hits_total` 增量精确相等。因此**可以丢掉 `/metrics` 做差那套**——
   它要求请求串行且服务器上无其他流量；有了这个字段，并发运行也能逐请求归因。
   这对 E02 是实打实的解绑。
3. **命中率 86.5% 四次测量完全稳定**（升级前后各两次，均为 2112/2443，恰好 132 × 16-token block）。
   理论公共前缀约 2440 tok，未命中的约 331 tok 尚无解释，但它是**确定性残差而非噪声**；
   若日后影响结论再单独查。

**镜像版本已钉死**：`experiments/p4a/infra/vllm/docker-compose-qwen36-35B.yml` 从
`vllm/vllm-openai:latest` 改为 `:v0.22.1`，并在文件内注明成因。同一个 `:latest` tag
在两天内改变了上报语义——结论一旦依赖它，`latest` 就是复现性隐患。
**任何版本变更都必须重跑一次上报验证。**

> ⚠️ **跨新旧数据的字段陷阱**：`inputOther = prompt_tokens - cached`。历史语料 cached 恒为 0，
> 故 `inputOther` **等于完整 prompt_tokens**；上报修好后 `inputOther` 只剩未命中部分。
> **跨新旧对比必须用 `inputOther + inputCacheRead`**，否则会得到看似合理的错误数字。

### s2：放大倍数由**轮数**决定，不由输入体量决定

放大倍数定义写死为 `Σ_step inputOther / max_step inputOther`：分子是这次 run 实际付出的
prefill 总量，分母是会话内前缀缓存完全命中时只需付一次的部分。
**它衡量会话内重复 prefill，与跨 run 复用是两回事。**
（分母的合法性依赖上下文单调增长，已验证：3999/3999 的末步即峰值。）

| | extract (n=3762) | repair (n=237) |
|---|---|---|
| LLM 调用步数 | p50 **15**，p10 10，p90 23，max 52 | p50 8，p90 19 |
| 工具调用数 | p50 **25**，p90 37 | p50 10 |
| 峰值上下文 | p50 **106,416** tok，p90 147,375 | p50 85,042 |
| 单 run 累计 prefill | p50 **1,285,334** tok | p50 559,591 |
| 放大倍数 | p50 **12.0**，p90 18.8，max 40.9 | p50 6.7，max 44.4 |

归因（extract 子集，Pearson）：`n_steps` ↔ `sum_input` = **0.882**；
`peak_input` ↔ `sum_input` = 0.690；`n_steps` ↔ `peak_input` = 0.345。

**结论**：成本增长的驱动因素是**轨迹长度**，不是**输入大小**。这对研究方向有利——
轨迹是可干预的，论文长度不是。

### s2 附带：轨迹分叉从第 2 个工具调用开始

| 调用位置 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| 去重工具数 | 1 | 7 | 7 | 8 | 9 | 10 |
| 众数占比 | Read **100.0%** | Read 54.5% | 79.5% | 97.8% | 98.6% | 90.3% |

第一个动作在全部 run 里完全一致，第二个动作就跌到 54.5%。这是 s4 要精确定位的分叉点的
**粗粒度版本**——工具名级别，尚未下到 token 级别。

---

## 3. 侦察发现（2026-09-01）——s3 计划变更的依据

README 原先记载 s3 只能做**代理指标**，理由是「工具 schema 不可得、拼装模板未知」。
这条判断**已被推翻**。侦察确认 `wire.jsonl` 里存在三类此前未使用的事件：

| 事件 | 内容 | 作用 |
|---|---|---|
| `config.update` | **完整 systemPrompt 原文**（15–21K 字符） | 无需从 TS 源码复原 |
| `llm.tools_snapshot` | **完整 tool schema JSON**（88K 字符）+ `hash` | 无需从 TS 源码复原 |
| `llm.request` | `systemPromptHash` / `toolsHash` / `messageCount` | 现成的一致性校验 |

配合 `references/repos/qwen3.6-35b-a3b-tokenizer/`（含 `chat_template.jinja`），
**精确复现是可行的**。三条关键侦察结果：

### 3.1 复现原型：首次尝试误差 0.27%

手工按 chat template 渲染某 session 的 step 1：

```
tools 段（含模板头尾）   22575 tok   ← 占 83%
systemPrompt 段          4483 tok
user 段                   109 tok
生成引导                     5 tok
复现 = 27178   观测 inputOther = 27251   Δ = -73  (0.27%)
```

零调参。残差大概率来自未计入的 `permission_mode` 注入消息与 JSON 序列化细节。

**免费的验证 oracle**：每个 `step.end` 都记了 `inputOther` = 服务端算的 `prompt_tokens`。
全语料 **62,649** 个 step 各是一次独立打分。复现器正确与否**不需要论证，跑一遍看 Δ 分布即可**。

### 3.2 渲染顺序：tools 在前（83%），systemPrompt 在后且**每 run 都变**

`chat_template.jinja` 把 tools 渲染进**第一条 system 消息的最前面**，systemPrompt 接在其后。
而 systemPrompt 里嵌了两样每次都变的东西：

- **毫秒精度的 ISO 时间戳**（`The current date and time in ISO format is ...`）
- **工作目录树**——P4A 自己跑的时候还在往里写文件，所以树本身在变

300 份采样的 systemPrompt 跨 run 公共前缀：**中位长度 3270 tok，公共前缀仅 1952 tok（60%）**。
即真实跨 run 公共前缀 ≈ 22575 + 1952 ≈ **24.5K tok 后断裂**，其后约 1318 tok 纯属白算。

直接损失不大（≈ 1318 × 4083 ≈ 540 万 token，只影响每个 session 的首次请求），
但**因果链完全可见，适合作为整套测量装置的标定样例**，也是一个可直接 A/B 的干预
（把易变块挪到 systemPrompt 末尾或首条 user 消息）。

### 3.3 语料**不同质**：4 个工具集变体，源头是 MCP 启动成败

全语料扫描发现 4 个 `toolsHash`，其工具清单恰好是三台 MCP 服务器的启动结果组合。
**24 个内置工具在四个变体里逐字相同**，差异 100% 来自远程 MCP 在
`startupTimeoutMs: 30000` 内有没有连上：

| toolsHash | 工具数 | arxiv(3) | github(12) | hf(5) | 标定 step1 `inputOther` |
|---|---|---|---|---|---|
| `aca0350b` | 44 | ✅ | ✅ | ✅ | 27258 (n=57) |
| `fd590e4c` | 39 | ✅ | ✅ | ❌ | 25867 (n=1) |
| `8bbbefcb` | 32 | ✅ | ❌ | ✅ | 24281 (n=1) |
| `98480f75` | 27 | ✅ | ❌ | ❌ | 22890 (n=1) |

四个变体**全都有 `llm.tools_snapshot`**，因此复现不依赖任何外部服务，离线可跑。
（MCP 配置只起解释作用；重跑 workload 才需要它，见第 6 节。）

**这条本身就是一个研究发现**：tools 段在最前面且占 83%，所以
> 一次与任务无关的网络抖动（github MCP 启动超时），使该 run 的跨 run 公共前缀
> **从第 0 个 token 就断裂**，摧毁 100% 的前缀复用。

**同时是一个质量混淆变量**：`8bbbefcb` / `98480f75` 两批 run 手上没有 github 工具，
根本查不了 GitHub 上的 resource。既然这批数据用于 motivation，此点必须随结论一并声明。

### 3.4 其他待处理的观测

- `llm.tools_snapshot` / `llm.request` **只存在于 60/4083 份 session**（kimi-code 版本差异），
  其余 4023 份没有任何工具集记录——这是 s3 第一步要解决的问题（见 4.1）。
- chat template 的 `loop.index0 > ns.last_query_index` 决定是否保留 `<think>`。
  单轮 session 全程保留（与观测到的前缀单调一致）；**但只要出现第二轮用户输入，
  之前所有 assistant 的思考内容会被整体剥掉，前缀从 step 1 起全废**。多轮 = 缓存归零。
  这条影响 E02 的设计。
- `context.append_message` 的 `todo_list_reminder` 注入（全语料 2625 条）插在上下文中段，
  其后所有内容位移。`wire.py` 现在**忽略** `context.append_message`，s3 必须补上。

---

## 4. 计划

三个阶段严格按序，**s3 不通过验收不进 s4**。理由：没有精确 token 序列，s5 观察到的
分歧无法定价，会导致我们去优化一个其实不值钱的分歧。

### 4.1 s3 — 精确复现器（`s3_render.py`）

把「每步真实进入模型的 token 序列」还原出来，并用 `inputOther` 全量验收。

**第一步（异质语料判定任务，本轮不做）**

> 用 Δ oracle 给全部 4083 份 session 判定工具集变体：拿 4 个候选 snapshot 分别渲染，
> 取 `|复现 − inputOther|` 最小者。输出一张 **(变体 × session 数 × Δ 分布)** 表。
>
> **四个候选都对不上的必须显式列出**——那说明存在第五个未见过的变体，或复现器本身有问题。
> 这两种情况都不得糊过去。

已知的先验：step-1 `inputOther` 分箱中，众数桶 22–23k（1545 份）落在 27 工具那一档，
21–24k 合计约 3638 份；27–28k（77 份）对应上表 `aca0350b`。但标定点多为 n=1，
**不足以下结论，须由 oracle 判定**。

**验收条件**：给出 Δ 的全量分布；报告 |Δ| ≤ 阈值的 step 占比；判不出变体的 session 逐条列出。
**不设「差不多就行」的通过标准——分布本身就是交付物。**

**依赖变更**：`tokenizers` 从 optional 提升为**必需依赖**；`wire.py` 补上
`context.append_message` 的重建。

### 4.2 s4 — 前缀分歧图谱（`s4_divergence.py`）

有了精确 token 序列，对 run 两两（或按组）计算公共前缀断点，并**给每个断点归因**：
时间戳 / 目录树 / todo 注入 / 工具集变体 / 工具调用顺序 / 措辞差异。

**交付物**：一张「每类分歧造成多少可避免 prefill」的账。这是对研究问题的正面回答。

### 4.3 s5 — 轨迹统计与可视化（`s5_behavior.py`）

以工具调用序列为字母表做聚类，找出典型 router 条件与可归约的分支；
统计被赋予的 agency 有多少真的被行使。

**归约建议是否采纳，取决于 s4 给出的 token 账**，不由观感决定。
可视化倾向做成交互式 artifact（轨迹泳道 + 分歧点热力），静态图信息量不足。

---

## 5. 风险

| 风险 | 影响 | 处置 |
|---|---|---|
| 4023 份 session 无工具集记录 | 复现不了 98.5% 的语料 | 由 4.1 的 Δ oracle 判定；判不出的显式剔除并说明 |
| `micro_compaction = true`（`experiments/p4a/infra/kimi/config.toml`） | 压缩若触发则消息列表被重写，复现静默偏离 | Δ oracle 会捕获（复现值将显著高于观测值）；需专门核查是否有压缩事件 |
| kimi-code 对工具结果的截断/改写 | 复现值偏高 | 同上，由 Δ 分布暴露 |
| 语料异质（4 变体 + ≥2 个 systemPrompt 变体） | 混在一起统计会得到无意义的均值 | 分组统计；是否只保留主变体待定 |

---

## 6. 与 E02 的接口

本实验是**离线观测**，不依赖 vLLM 或 MCP。但其发现对 E02（受控重跑）有三条硬性输入：

1. **固化 MCP schema**。两台远程 MCP（`api.githubcopilot.com`、`huggingface.co`）的 schema
   由他人维护、随时会变，而它就在 prompt 最前面。启动失败是**静默降级**——run 照样成功，
   只是换了个前缀、少了一半能力。应本地供给 snapshot，或至少改为 fail-fast。
2. **cache 上报已就绪**（2026-09-01 完成）：镜像钉死 `v0.22.1` + `--enable-prompt-tokens-details`，
   非流式与流式均已验证。E02 可以直接从 `wire.jsonl` 读逐请求真实命中数，
   不必再在外面套一层 `/metrics` 测量装置。变更版本时须重跑验证。
3. **单轮**。多轮会因 `<think>` 剥离导致前缀从 step 1 起全废（3.4）。

---

## 附：本页数据来源

- `data/processed/e01/s0_summary.json`、`s1_cache_fields.json`、`s2_summary.json`
  （gitignored，由 `make all` 重建，均带 `_provenance` 头）
- 源数据 `data/raw/kimi-p4a-sessions.tar.gz`，md5 `9cfa1d2400d2fe283c0850a14804940b`
- 第 3 节的侦察数字为一次性探查所得，**尚未落成脚本**；s3 实现后应由脚本重新产出并覆盖本节。
