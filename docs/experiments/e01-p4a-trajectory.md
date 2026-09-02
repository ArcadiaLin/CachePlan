# E01 — P4A 历史 session 轨迹的全量观测

首个实验。代码：[`experiments/e01-p4a-trajectory/`](../../experiments/e01-p4a-trajectory/)；运行方式和环境见该目录 README。

- 性质：**观测**。对象是既有、不可变的 4083 份日志；只读，不运行 agent，不修改 P4A。
- 边界：P4A 数据只用于诊断和动机，不能作为 CachePlan 有效性的对照基线（见 [`p4a.md`](p4a.md) 第 4 节）。
- 状态：s0–s2 完成；s3–s5 尚未实现。

| 阶段 | 脚本 | 目标 | 状态 |
|---|---|---|---|
| s0 | `s0_manifest.py` | 语料清单与纳入过滤 | 完成 |
| s1 | `s1_cache_fields.py` | cache 字段闸门 | 完成；现成字段不可用 |
| s2 | `s2_session_stats.py` | 放大倍数分布与归因 | 完成 |
| s3 | `s3_render.py` | 还原每步进入模型的 token 序列 | 计划 |
| s4 | `s4_divergence.py` | 前缀分歧位置和 token 代价 | 计划 |
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

## 3. 侦察：s3 可以精确复现

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

### 3.4 未解决的复现问题

- 仅 60/4083 session 有 `llm.tools_snapshot` / `llm.request`；其余 4023 份须由 Δ oracle 判定工具集变体。
- 多轮用户输入会触发模板剥离先前所有 assistant `<think>` 内容，使前缀从 step 1 起失效；E02 应保持单轮。
- `context.append_message` 的 `todo_list_reminder`（全语料 2625 条）插入上下文中段；当前 `wire.py` 忽略它，s3 必须重建。

## 4. 后续阶段

s3 未通过验收前不进入 s4；否则无法给观察到的行为分歧定价。

### s3：精确复现器

重建每步 token 序列，以 `inputOther` 验收。

首项任务：对全部 4083 份 session，以 4 个候选 snapshot 分别渲染，按

$$
\lvert \text{复现} - \text{inputOther} \rvert
$$

最小者判定工具集变体；输出“变体 × session 数 × Δ 分布”。四种候选均不匹配的 session 必须逐条列出，它们代表未发现的变体或复现缺陷，不能静默归类。

已知先验：step-1 `inputOther` 的 22–23k 众数桶有 1545 份，21–24k 共约 3638 份；27–28k 的 77 份对应 `aca0350b`。现有标定点多为 $n=1$，不能据此定论。

验收交付物：完整 Δ 分布、$\lvert\Delta\rvert\le\text{阈值}$ 的 step 占比、无法判定的 session 清单。依赖：`tokenizers` 由 optional 改为必需；`wire.py` 重建 `context.append_message`。

### s4：前缀分歧图谱

以精确 token 序列计算 run 对之间的公共前缀断点，并归因于时间戳、目录树、todo 注入、工具集变体、工具调用顺序或措辞。交付每类分歧对应的可避免 prefill 账。

### s5：轨迹统计与可视化

按工具调用序列聚类，识别 router 条件和可归约分支，统计被赋予的 agency 实际行使程度。是否采纳归约建议由 s4 的 token 账决定。可视化倾向交互式 artifact（轨迹泳道与分歧热力）。

## 5. 风险

| 风险 | 影响 | 处置 |
|---|---|---|
| 4023 份 session 无工具集记录 | 98.5% 语料无法直接复现 | Δ oracle 判定；不能判定者显式剔除 |
| `micro_compaction = true` | 触发后消息列表被重写 | Δ oracle 捕获；核查压缩事件 |
| kimi-code 截断或改写工具结果 | 复现值偏高 | Δ 分布暴露 |
| 4 种工具集和至少 2 种 system prompt | 混合统计无意义 | 分组统计；是否只保留主变体待定 |

## 6. 对 E02 的约束

E01 不依赖 vLLM 或 MCP，但 E02 必须：

1. 固化 MCP schema，或至少 fail-fast。远程 schema 可变且位于 prompt 前缀；启动失败会静默改变前缀并削弱能力。
2. 固定 vLLM 0.22.1 并开启 `--enable-prompt-tokens-details`。`wire.jsonl` 可直接提供逐请求真实命中数；版本变更必须复验。
3. 保持单轮，避免 `<think>` 剥离使前缀失效。

## 数据来源

- `data/processed/e01/s0_summary.json`、`s1_cache_fields.json`、`s2_summary.json`：gitignored，可由 `make all` 重建，均含 `_provenance`。
- 源数据：`data/raw/kimi-p4a-sessions.tar.gz`，md5 `9cfa1d2400d2fe283c0850a14804940b`。
- 第 3 节为一次性侦察，尚无脚本；s3 实现后应以脚本产出替换。