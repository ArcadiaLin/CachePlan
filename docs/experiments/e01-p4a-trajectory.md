# E01 — P4A 历史 session 轨迹的全量观测

首个实验。代码：[`experiments/e01-p4a-trajectory/`](../../experiments/e01-p4a-trajectory/)；运行方式和环境见该目录 README。

- 性质：**观测**。对象是既有、不可变的 4083 份日志；只读，不运行 agent，不修改 P4A。
- 边界：P4A 数据只用于诊断和动机，不能作为 CachePlan 有效性的对照基线（见 [`p4a.md`](p4a.md) 第 4 节）。
- 状态：s0–s4 完成；s5 尚未实现。

| 阶段 | 脚本 | 目标 | 状态 |
|---|---|---|---|
| s0 | `s0_manifest.py` | 语料清单与纳入过滤 | 完成 |
| s1 | `s1_cache_fields.py` | cache 字段闸门 | 完成；现成字段不可用 |
| s2 | `s2_session_stats.py` | 放大倍数分布与归因 | 完成 |
| s3 | `s3_render.py` | 还原每步进入模型的 token 序列 | 完成；逐步 Δ=0 |
| s3 | `s3_dump.py` | 导出某份 session 的逐步上下文供查阅 | 完成 |
| s4 | `s4_divergence.py` | 前缀分歧位置和 token 代价 | 完成 |
| s5 | `s5_behavior.py` | 轨迹、router 条件和 agency 统计 | 计划 |

---

## 1. 语料

4083 份 session 中纳入 3999 份（extract 3762、repair 237），覆盖 3321 篇论文。单机单工作目录顺序执行，无并发混淆。

排除 84 份；理由见 `data/processed/e01/s0_summary.json`：

| 理由 | 数量 | 说明 |
|---|---:|---|
| `aborted` | 73 | 已开始但没有完整 step；作为观测量，`abort_rate()` 单列 |
| `operator_chat` | 12 | 非 extract/repair 的人工会话 |
| `no_steps` | 5 | 没有 LLM 调用 |
| `multi_turn` | 4 | 多轮用户输入或 harness auto-continue |

## 2. 已完成结果

### s1：历史 cache 字段不可用

| 指标 | 值 |
|---|---|
| 判定 | `identically_zero`：字段存在但值恒为 0 |
| 语料 / usage 记录 | 3999 / 62,649 |
| 非零 `inputCacheRead` / `inputCacheCreation` | 0 / 0 |
| 累计 prefill | 5,604,823,657 tokens |

原因是上报缺陷，不是缓存未命中：服务端当时启用了 `--enable-prefix-caching`，在 vLLM 0.21.0 上，重复前缀请求的 `/metrics` 命中率为 $2112/2443=86.5\%$；但非流式响应的 `prompt_tokens_details` 为 `null`，流式响应甚至没有该字段。`kimi-code` 的 `extractUsage`（`packages/kosong/src/providers/openai-common.ts:204`）取不到 `cached_tokens` 时记为 0；`inputCacheCreation` 也在 openai provider 路径中硬编码为 0（同文件 `:230`）。

因此历史语料无法恢复真实命中率。s3 之后应根据复现出的 token 序列计算前缀重叠量，并标为**结构性度量**，不能称作命中率。

未来运行已验证的处置：使用 vLLM 0.22.1 和 `--enable-prompt-tokens-details`。同一请求、同一前缀在非流式和流式路径均得到与 `/metrics` 增量一致的 `cached_tokens: 2112`：

| 版本 / 路径 | `/metrics` | 响应 usage | kimi-code 记录 |
|---|---:|---|---:|
| 0.21.0 非流式 | 2112 / 2443 | `prompt_tokens_details: null` | 0 |
| 0.21.0 流式 | 2112 / 2443 | 无该 key | 0 |
| 0.22.1 非流式 | 2112 / 2443 | `cached_tokens: 2112` | 2112 |
| 0.22.1 流式 | 2112 / 2443 | `cached_tokens: 2112` | 2112 |

`cached_tokens` 是服务端实测值，故 E02 可逐请求归因，无需对 `/metrics` 做差，也不再要求请求串行或服务器无其他流量。四次测量均为 $2112/2443=86.5\%$，即 132 个 16-token block；理论公共前缀约 2440 token，331 token 的确定性残差尚未解释。镜像已从 `vllm/vllm-openai:latest` 钉为 `:v0.22.1`（`experiments/p4a/infra/vllm/docker-compose-qwen36-35B.yml`）；版本变更必须复验上报。

> `inputOther = prompt_tokens - cached`。历史数据中 cached 恒为 0，故 `inputOther` 是完整 prompt；新数据中它只表示未命中部分。跨新旧比较必须使用 `inputOther + inputCacheRead`。

### s2：放大倍数主要由轨迹长度驱动

放大倍数：

$$
\frac{\sum_{\text{step}} \text{inputOther}}
{\max_{\text{step}} \text{inputOther}}
$$

分子是 run 的累计 prefill；分母是会话内前缀完全复用时，每个 token 仅处理一次的总量。该解释依赖上下文单调增长；3999/3999 session 的最后一步均为峰值。它衡量**会话内**重复 prefill，不衡量跨 run 复用。

| 指标 | extract (n=3762) | repair (n=237) |
|---|---:|---:|
| LLM 调用步数 | p50 15，p10 10，p90 23，max 52 | p50 8，p90 19 |
| 工具调用数 | p50 25，p90 37 | p50 10 |
| 峰值上下文 | p50 106,416，p90 147,375 tok | p50 85,042 tok |
| 单 run 累计 prefill | p50 1,285,334 tok | p50 559,591 tok |
| 放大倍数 | p50 12.0，p90 18.8，max 40.9 | p50 6.7，max 44.4 |

extract 子集 Pearson 相关：`n_steps` ↔ `sum_input` 为 0.882，`peak_input` ↔ `sum_input` 为 0.690，`n_steps` ↔ `peak_input` 为 0.345。累计成本的主要驱动因素是轨迹长度，而非输入体量；前者可干预，论文长度不可干预。

### s2 附带：第 2 个工具调用开始分叉

| 调用位置 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|
| 去重工具数 | 1 | 7 | 7 | 8 | 9 | 10 |
| 众数占比 | Read 100.0% | Read 54.5% | 79.5% | 97.8% | 98.6% | 90.3% |

首个动作完全一致；第二个动作的众数占比降至 54.5%。这是工具名级别的粗粒度分歧，s4 将定位 token 级断点。

### s3：逐字还原成立，但语料不是一套工具配置

还原链条分两段：`context_builder.py` 把 `wire.jsonl` 回放成每一步的 messages 数组，`render.py` 走 `chat_template.jinja` 加分词器。在 60 份带 `llm.tools_snapshot` 的 session 上逐步验收：**1142 个校验点中 1123 个 Δ=0（98.34%）**。

三处必须逐字一致，任一处错掉都对不上：

| | 正确做法 | 错了的代价 |
|---|---|---|
| 工具项 JSON 形状 | 包成 `{"type":"function","function":{…}}` | 用日志里的扁平形状稳定偏低 401 tok |
| `tojson` | `json.dumps(ensure_ascii=False)` | jinja2 自带的会把 `<` `>` `&` `'` 转义 |
| 空白处理 | `trim_blocks` 与 `lstrip_blocks` 均开 | 与 transformers 不一致 |

工具结果的渲染规则同样是照抄而非试出：日志存的是事实（`output` / `isError` / `note`），模型看到的文本由 `agent-core/src/agent/context/tool-result-render.ts` 生成——`isError` 无条件前置 `<system>ERROR: …</system>`，空输出换占位符，`note` 换行追加。只补 `note` 时 11 步里仅对 6 步；漏 `isError` 差 12 tok。

唯一未解释的偏差：`session_3024e2ea` 在 step 7 跳变 −25 tok，后续 19 步带同一偏差。已排除消息条数不符、50000 字符持久化预览、同名调用 dedup、MCP 文本预算四种成因。该 session 标 `exact=false`，不进入逐字分析。

**语料不同质，程度远超侦察时的判断。** 用 Δ oracle 解出每份 session 真实工具块的 token 数（不需知道内容）：

$$
\Delta(\text{候选}) = \text{渲染}(\text{真 systemPrompt} + \text{真 messages} + \text{候选工具}) - \text{inputOther}
= \text{tok}(\text{候选工具块}) - \text{tok}(\text{真工具块})
$$

判定 4005 份（跳过 78 份，全部是 s0 已排除者，纳入集 3999 份无遗漏），得 **18 种不同工具配置（下界）**。四个已知候选**只覆盖 60 份**，另外 3945 份对不上任何一个。

原因：带 `llm.request` / `llm.tools_snapshot` / `mcp.tools_discovered` 的正是**时间上最末尾的连续 60 份**（2026-07-09 15:25 之后），其余 4023 份来自旧 build，工具 schema 与新 build 不同，原文无从恢复。

按时间排序的分组基本是互不重叠的连续区块，即一个月里配置在演进：

| 相对参照的工具块 tok | 份数 | 时间段 | 已知候选 |
|---:|---:|---|---|
| −5593 | 209 | 06-12 → 06-23 | |
| −8409 | 62 | 06-12 → 06-15 | |
| −4219 | 234 | 06-23 01:57 → 12:31 | |
| −2669 | 935 | 06-23 → 06-29 | |
| −4043 | 621 | 06-25 → 07-01 | |
| **−3882** | **1540** | **07-02 → 07-09** | 最大区块 |
| −2498 | 281 | 07-08 → 07-09 | = −3882 + hf 那 5 个工具 |
| ±0 | 57 | 07-09 15:25 → | `aca0350b`（44 工具）|

另有 10 个小组各 1–37 份。少数组在时间上重叠且恰好相差 1384 tok（hf-readonly 的 5 个工具），那才是 MCP 启动超时造成的变体；其余是版本演进。**跨区块的共享前缀从 token 0 断裂，前缀分析必须限定在区块内做。**

附带确认：全语料 `content.part` 只有 `text` 一种类型，没有 `think`。这不是日志缺失——若当时把 reasoning 回传给模型，重建值会系统性偏低，而实测每一步精确相等。故这些 run 没有把推理内容放回上下文；`usage.record` 的 `output` 与还原出的 assistant 消息之差即被丢弃的推理长度，单步最多 994 tok。

### s4：前缀失效的两个来源，量级差 35 倍

#### A 会话内注入：204,579,397 tok，占全语料 prefill 的 3.65%

模板用 `loop.index0 > ns.last_query_index` 决定 assistant 消息保不保留 `<think>`；`ns.last_query_index` 是最后一条非 `<tool_response>` 的 `role=user` 消息下标（工具结果是 `role=tool`，不参与）。harness 每注入一条这样的消息，该下标前移，此前所有 assistant 消息的 `<think>` 被**回溯性剥掉**——上下文中段被改写，不再是纯追加。

存活前缀恰好是「上一次注入之后那一步」的完整上下文，于是不必渲染即可精确计算：

$$
\text{作废} = \text{inputOther}[\text{注入前最后一步}] - \text{inputOther}[\text{上次注入后第一步}] + 2
$$

常数 2 是生成提示词的边界修正。公式先在 60 份 ground truth 上标定（`make s4` 含 `--check`），核对两件事：误差为常数（57 份为 0，另一份是上述 −25 异常 session），且**注入点集合 == 实际改写点集合**——后者说明注入是非追加式增长的唯一成因，`micro_compaction` 在这批语料里没有触发过。

| | |
|---|---:|
| 出现过注入的 session | 2444 / 3999（61.1%）|
| 注入次数分布 | 0 次 1555；1 次 2241；2 次 187；3 次 13；4 次 3 |
| 首次注入在 step 11 | 2318 份 |
| 作废 token 总量 | **204,579,397** |
| 占全语料累计 prefill | **3.65%** |
| 受影响 session 每份 | p10 54,724；**p50 80,204**；p90 118,583；max 183,679 |
| extract / repair | 2391 份 201,790,234 tok / 53 份 2,789,163 tok |

2661 次注入里 **2617 次是同一条** `<system-reminder>`：*The TodoList tool has not been updated recently…*。首次注入高度集中在 step 11，是定时器而非偶发。这条提醒与 P4A 的任务无关，却让每次触发作废一个已涨到七八万 token 的上下文。

#### B 跨 run 首步前缀：四级反事实

在最大区块 −3882（1538 份纳入，工具块 18,696 tok，首步平均 22,138 tok）上做累进归一。工具块在区块内逐字相同且渲染在最前，故只比较其后一段再把工具块 token 数加回。

| 层级 | 共享前缀 | 占首步 | 每 run 浪费 | 区块合计 |
|---|---:|---:|---:|---:|
| L0 原样 | 20,652 | 93.3% | 1,486 | 2,286,177 |
| L1 + 时间戳归一 | 20,974 | 94.7% | 1,164 | 1,790,941 |
| L2 + 工作目录树归一 | 21,944 | 99.1% | 194 | 299,081 |
| L3 + 首条用户消息不含论文对象 | 22,014 | 99.4% | 124 | 191,421 |

大头不是毫秒级时间戳（322 tok），而是 kimi-code 注入 `systemPrompt` 的**工作目录树**（970 tok，占可回收量的 71%）——时间戳归一后区块内仍剩 3 种 `systemPrompt`，差异全在那棵树上，而 P4A 自己在运行中往 `data/processed/` 写文件，等于自己破坏自己的前缀。论文对象移出首条用户消息只值 70 tok：它导致的是后续轨迹分叉，不是前缀分叉。

不改 harness 代码也有一条：**按 `systemPrompt` 变体分组调度**，同变体内共享前缀即达 99.3%，区块合计浪费从 2,286,177 降至 254,213（−89%），接近 L2。

#### 两者的量级

| 来源 | tokens | 占全语料 prefill |
|---|---:|---:|
| 会话内注入作废 | 204,579,397 | 3.65% |
| 首步跨 run 分歧（按区块外推）| 约 5.9M | 约 0.11% |

注入问题比首步前缀问题大约 35 倍，且更易修（`preserve_thinking`，或把提醒改为 `role=tool` 注入）。首步那 1,486 tok/run 虽刺眼，每 run 只付一次；注入每次作废的是已经很大的上下文。

## 3. 侦察记录（2026-09-01，部分已被 s3/s4 取代）

> 本节是脚本落地前的一次性侦察，保留以记录判断依据。其中 3.1 的误差、3.3 的“四种工具集覆盖全语料”均已被上节的脚本结果**修正**；3.2 的采样估计已被 s4 的精确值取代。

原先认为工具 schema 和拼装模板不可得，只能使用代理指标。`wire.jsonl` 中实际有：

| 事件 | 内容 | 用途 |
|---|---|---|
| `config.update` | 完整 `systemPrompt`（15–21K 字符） | 无需从 TS 源码复原 |
| `llm.tools_snapshot` | 完整 tool schema JSON（88K 字符）和 hash | 无需从 TS 源码复原 |
| `llm.request` | `systemPromptHash`、`toolsHash`、`messageCount` | 一致性校验 |

结合 `references/repos/qwen3.6-35b-a3b-tokenizer/` 中的 `chat_template.jinja`，可以精确重建 token 序列。

### 3.1 原型误差

手工渲染一个 session 的 step 1：

```
tools 段（含模板头尾）   22575 tok
systemPrompt 段          4483 tok
user 段                   109 tok
生成引导                     5 tok
复现 = 27178；观测 inputOther = 27251；Δ = -73（0.27%）
```

tools 占 83%。未调参；残差可能来自未计入的 `permission_mode` 注入和 JSON 序列化。每个 `step.end` 的 `inputOther` 都是服务端 `prompt_tokens`，因此 62,649 个 step 可直接构成复现器的 Δ 分布验收。

> **已修正**：残差的真实成因是工具项的 JSON 形状——vLLM 把每个工具 `model_dump()` 成 `{"type":"function","function":{…}}` 再交给模板，而日志里记的是扁平的 `{name, description, parameters}`。改用包装形状后 Δ 精确为 0，与 `permission_mode` 和 JSON 序列化都无关。

### 3.2 system prompt 损失跨 run 前缀

模板将 tools 放在首条 system message 的最前面，再接 `systemPrompt`。后者包含毫秒级 ISO 时间戳和工作目录树；P4A 运行时目录树也在变化。

300 份采样中，`systemPrompt` 跨 run 的公共前缀中位数为 1952 / 3270 token（60%）。真实跨 run 公共前缀约在 $22575+1952\approx24.5k$ token 处断裂，约 1318 token 无法复用。它只影响每个 session 的首次请求，直接损失约 $1318\times4083\approx540$ 万 token；但因果明确，可作为测量装置标定样例，也可 A/B 测试将易变块后移至 `systemPrompt` 末尾或首条 user 消息。

### 3.3 MCP 启动导致四种工具集

全语料有 4 个 `toolsHash`。24 个内置工具逐字相同；差异完全来自三台远程 MCP 是否在 `startupTimeoutMs: 30000` 内连上：

| toolsHash | 工具数 | arxiv(3) | github(12) | hf(5) | step-1 `inputOther` |
|---|---:|---|---|---|---:|
| `aca0350b` | 44 | ✅ | ✅ | ✅ | 27258 (n=57) |
| `fd590e4c` | 39 | ✅ | ✅ | ❌ | 25867 (n=1) |
| `8bbbefcb` | 32 | ✅ | ❌ | ✅ | 24281 (n=1) |
| `98480f75` | 27 | ✅ | ❌ | ❌ | 22890 (n=1) |

所有变体均有 `llm.tools_snapshot`，故复现不依赖外部服务。因为 tools 段位于 prompt 开头且占 83%，github MCP 启动超时会使跨 run 公共前缀从 token 0 断裂。缺少 GitHub 工具的 `8bbbefcb` 和 `98480f75` 也构成质量混淆变量，作为动机数据使用时必须声明。

> **已修正**：这四种只覆盖末尾那 60 份带快照的 session。s3 用 Δ oracle 判定后得到**至少 18 种**工具配置，另外 3945 份与四者均不匹配；分组按时间排成连续区块，主因是一个月里的版本演进，MCP 启动超时只解释其中少数几组。另注意 `tools.set_active_tools` 全语料恒为同一份 27 名单，但**那不是发给模型的工具集**（它等于最小快照变体），不能据它判断语料同质。

### 3.4 未解决的复现问题

- 仅 60/4083 session 有 `llm.tools_snapshot` / `llm.request`；其余 4023 份须由 Δ oracle 判定工具集变体。
- 多轮用户输入会触发模板剥离先前所有 assistant `<think>` 内容，使前缀从 step 1 起失效；E02 应保持单轮。
- `context.append_message` 的 `todo_list_reminder`（全语料 2625 条）插入上下文中段；当前 `wire.py` 忽略它，s3 必须重建。

> **已处理**：第一条见上节的 18 种配置判定；后两条实为同一机制，且不限于“多轮用户输入”——任何 `role=user` 的注入都会触发，代价已由 s4 精确定价（2 亿 token，3.65%）。`context_builder.py` 已重建这些消息。注入计数以 s4 的口径为准：首步之后、非 `<tool_response>` 的 `role=user` 注入共 2661 次，其中 2617 次是 TodoList 提醒。

## 4. 后续阶段

### s5：轨迹统计与可视化

按工具调用序列聚类，识别 router 条件和可归约分支，统计被赋予的 agency 实际行使程度。是否采纳归约建议由 s4 的 token 账决定。可视化倾向交互式 artifact（轨迹泳道与分歧热力）。

必须限定在单一工具配置区块内做——跨区块的共享前缀从 token 0 断裂。最大区块 −3882 有 1538 份纳入 session，量足够。

两条可选的深入方向，尚未决定是否值得：

- **恢复旧 build 的工具 schema 原文。** 工具描述是 kimi-code 源码里的静态 `.md`，仓库有完整历史，tag 密集覆盖 06-02 → 07-14，且 18 个区块的边界与发版日期对得上（−3882 起于 07-02 00:00，`0.22.0`/`0.22.1` 发于 07-02）。抽查 07-08 的 `0.23.3`：24 个内置工具里 20 个描述与 `.md` **逐字节相同**，2 个是静态前缀加运行时拼接（`Agent` 的 subagent 目录、`AskUserQuestion`），2 个（`Bash`、`Read`）单文件对不上。Δ oracle 是完美验收器，故这是带验证的检索问题而非不可解。三个拦路虎：`parameters` 的 JSON schema 由 zod 生成、运行时拼接部分依赖当时机器配置、三个 MCP 的 schema 来自远端。**若 s5 只需工具块之后的部分，此事可不做**——工具块的 token 数已精确已知。
- **`session_3024e2ea` 的 −25 tok 偏差。** 已排除四种成因，成因未明。只影响 1/60 份，除非它代表某种系统性规则，否则不必追。

## 5. 风险

| 风险 | 影响 | 处置 | 状态 |
|---|---|---|---|
| 4023 份 session 无工具集记录 | 无法逐字复现工具块 | Δ oracle 判定 | 已判定 18 种配置；工具块 token 数精确已知，原文仅 60 份可得 |
| `micro_compaction = true` | 触发后消息列表被重写 | Δ oracle 捕获 | 已排除：注入点集合 == 实际改写点集合，压缩未触发过 |
| kimi-code 截断或改写工具结果 | 复现值偏高 | Δ 分布暴露 | 已处理：50000 字符持久化预览与 `tool-result-render.ts` 三条规则均已复刻 |
| 多种工具集和 system prompt | 混合统计无意义 | 分组统计 | 18 种工具配置 × 区块内 3 种 systemPrompt；s5 必须区块内做 |
| 60 份 ground truth 里 1 份逐步偏差未解释 | 逐字分析样本 −1 | 标 `exact=false` 排除 | 见 4 节 |

## 6. 对 E02 的约束

E01 不依赖 vLLM 或 MCP，但 E02 必须：

1. 固化 MCP schema，或至少 fail-fast。远程 schema 可变且位于 prompt 前缀；启动失败会静默改变前缀并削弱能力。
2. 固定 vLLM 0.22.1 并开启 `--enable-prompt-tokens-details`。`wire.jsonl` 可直接提供逐请求真实命中数；版本变更必须复验。
3. **禁止运行期间升级 harness。** P4A 一个月里换出至少 18 种工具配置，每换一次全量共享前缀归零。E02 必须钉死版本并记录。
4. **控制 `role=user` 注入。** 这是 E01 发现的最大单项浪费（2 亿 token，3.65%）。要么关掉与任务无关的定时提醒，要么改用 `role=tool` 注入，要么开 `preserve_thinking` 让模板不再回溯剥离。保持单轮只是这条的一个特例。
5. **稳定 `systemPrompt` 里的易变块。** 会话启动时间戳与工作目录树各自破坏跨 run 前缀；后者影响是前者的三倍。降低时间戳精度、把目录树移到 `systemPrompt` 末尾或首条 user 消息，或至少按变体分组调度。

## 数据来源

- `data/processed/e01/` 下全部产物均 gitignored 且含 `_provenance`：
  - `s0_summary.json`、`s1_cache_fields.json`、`s2_summary.json` — `make all`
  - `s3_render.jsonl`、`s3_render_summary.json` — `make s3`（约 3 分钟）
  - `s4_divergence.jsonl`、`s4_summary.json` — `make s4`（约 6 分钟，含公式标定）
  - `dumps/` — `make dump SID=<片段>`，逐步上下文原文
- 源数据：`data/raw/kimi-p4a-sessions.tar.gz`，md5 `9cfa1d2400d2fe283c0850a14804940b`。
- 分词器与 chat template：`references/repos/qwen3.6-35b-a3b-tokenizer/`，未纳入版本管理。换模型必须换它并重跑 `make s3` 的自检。
- 第 3 节为一次性侦察，已由 s3/s4 的脚本产出取代，保留作判断依据。