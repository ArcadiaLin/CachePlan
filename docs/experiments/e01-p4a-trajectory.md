# E01 — P4A 历史 session 轨迹的全量观测

首个实验。代码：[`experiments/e01-p4a-trajectory/`](../../experiments/e01-p4a-trajectory/)；运行方式和环境见该目录 README。

- 性质：**观测**。对象是既有、不可变的 4083 份日志；只读，不运行 agent，不修改 P4A。
- 边界：P4A 数据只用于诊断和动机，不能作为 CachePlan 有效性的对照基线（见 [`p4a.md`](p4a.md) 第 4 节）。
- 状态：语料分组已完成，观测集固定为 **961 份**；执行轨迹的观测在这一组上进行。

## 推进方式的变化（2026-09-03）

原先按 s0→s5 的线性阶段推进，隐含假设是「4083 份是一个可以整体统计的语料」。这个假设不成立：session 之间的差异在 systemPrompt 拼接处就已经出现，跨组的共享前缀从 token 0 断裂，把它们混在一起算出来的任何前缀量都没有意义。

所以推进方式改为：**先把语料按前缀分歧的来源切开，选定一个同质组，此后的观测都在组内做。** 已有脚本仍然是产出者，但不再作为进度的骨架。

| 脚本 | 回答什么 | 状态 |
|---|---|---|
| `s0_manifest.py` | 语料清单与纳入过滤 | 完成 |
| `s0b_prompt_blocks.py` | systemPrompt 分块，六轴的类标签 | 完成 |
| `s1_cache_fields.py` | 现成 cache 字段是否可用 | 完成；不可用 |
| `s2_session_stats.py` | 放大倍数分布与归因 | 完成 |
| `s3_render.py` | 还原每步进入模型的 token 序列 | 完成；逐步 Δ=0 |
| `s3_dump.py` | 导出某份 session 的逐步上下文 | 完成 |
| `s4_divergence.py` | 前缀分歧位置和 token 代价 | 完成 |

分析入口是 `notebooks/`：`00_corpus.ipynb`（语料形状）、`01_session_classes.ipynb`（分组与观测变量选择）。notebook 只切脚本产出的表，不产生被引用的数字。

---

## 1. 语料与分组

### 1.1 纳入过滤

4083 份 session 中纳入 3999 份（extract 3762、repair 237），覆盖 3321 篇论文。单机单工作目录顺序执行，无并发混淆。

排除 84 份，理由见 `s0_summary.json`。注意 `excluded_by_reason` 是**按理由计数**，一份 session 可同时撞上多条，四项相加 94 > 84：

| 理由 | 计数 | 说明 |
|---|---:|---|
| `aborted` | 73 | 已开始但没有完整 step；作为观测量，`abort_rate()` 单列 |
| `operator_chat` | 12 | 非 extract/repair 的人工会话；其中单独只是此项的仅 2 份 |
| `no_steps` | 5 | 没有 LLM 调用 |
| `multi_turn` | 4 | 多轮用户输入或 harness auto-continue |

### 1.2 前缀分歧的六条轴

systemPrompt 不是一整块，而是若干生命周期不同的块拼起来的。跨 run 前缀共享到哪个字节，取决于这些块里最靠前的那个不同的块。`s0b_prompt_blocks.py` 按 `#`/`##` 标题切块，记下每块的 md5、字符数与**起始偏移**，聚出六条轴：

| 轴 | 含义 | 位置（字符偏移 p50） | 取值数 |
|---|---|---:|---:|
| A | 工具配置 | systemPrompt 之前，约 18,700 tok | 18 |
| B | harness 版本 | 前半 405–7843 与尾部 | 3 |
| C | 时间戳 | 9,343 | 4074 |
| D | 项目目录树 | 9,598 | 10 |
| E | 投递形态 | 首条 user message | 2 |
| F | 路径布局 | 首条 user message | 2 |

全语料 16 个块中只有 6 个是逐字通用的。三点结论：

**轴 B、轴 E 与 family 完全混淆。** 用户在 06-22 一次性换掉了 harness、任务投递方式和任务类型：

| | inline | pointer |
|---|---:|---:|
| V1（06-12 → 06-22） | 237 | 2 |
| V2（06-22 → 07-09） | 0 | 3700 |
| V3（07-09） | 0 | 60 |

三者无法分离，只能整体固定。另注意 `wire.classify_family()` 判 family 用的就是投递形态的两个前缀，所以现在的 `family` 标签同时编码了「任务是什么」和「任务怎么送进上下文」两件事。

**轴 B 的三块是同一件事的三个侧面。** `axis_harness`、AGENTS.md（`Project Information`）、skills 清单（`Available skills`）各有 3 个取值且划分一致（交叉表验证，不靠大小相同推断）。版本号 V1/V2/V3 按首次出现时间排定，写在 `s0b` 产物的 `harness_version` 列里。V3 新增 `Language` 与 `Context Management` 两个块，移除 `What are skills?` 与 `How to use skills`。

**轴 C 是唯一免费的。** 时间戳块位于 systemPrompt 的 62% 处（第 9,343 字符，均长 15,101），其后的目录树、AGENTS.md、skills 清单、Ultimate Reminders 在同一类里跨 run 逐字稳定，却因排在时间戳之后而无法复用，p50 有 5,699 字符。把时间戳移到 systemPrompt 末尾即可回收，语义不变。轴 B/D/E/F 的分歧要改动 workload 才能消除。

**`sysprompt_chars` 就是精确的类标签。** (B, AGENTS.md, skills, D) 四轴联合有 10 个类，与 `sysprompt_chars` 的 10 个取值是双射（两个方向都 1:1，由 `s0b` 断言）。s0 早就在记这一列，下游不必重扫语料。

前缀类记为三元组：

$$
\text{class} = \bigl(\underbrace{\text{tools\_}\Delta}_{18},\ \underbrace{\text{sysprompt\_chars}}_{10\,=\,B \times D},\ \underbrace{\text{delivery}}_{2}\bigr)
$$

实际出现 40 个类，最大 961 份，单份类 14 个。

### 1.3 观测集：961 份

固定轴 B = V2、轴 E = pointer 之后剩 3700 份（占纳入集 92.5%），落在 22 个 (轴 A × 轴 D) 单元，前 7 个覆盖 3561 份：

| 工具 Δ | 目录树 | `sysprompt_chars` | 份数 | 日期 |
|---:|---|---:|---:|---|
| **−3882** | **fb389653** | **15015** | **961** | **07-05 → 07-08** |
| −4043 | 83a5abfa | 15042 | 621 | 06-25 → 07-01 |
| −2669 | 83a5abfa | 15042 | 558 | 06-24 → 06-29 |
| −3882 | 83a5abfa | 15042 | 530 | 07-02 → 07-03 |
| −2669 | 40dd3104 | 15024 | 376 | 06-23 → 06-24 |
| −2498 | 1eed914a | 15054 | 281 | 07-08 → 07-09 |
| −4219 | 445e3f30 | 15009 | 234 | 06-23 |

**观测集取 961 那一组。** 它是最大的同质单元：单一工具配置、单一目录树、连续 4 天、全部为 extract/pointer，覆盖 952 篇不同论文。它同时是 s4 第 B 部分那个 −3882 区块（1538 份）内三个 systemPrompt 变体中最大的一个，也就是说 s4 分析里 L2（目录树归一）在这一组里**按构造已经满足**。

组内画像：

| 指标 | p10 | p50 | p90 | max |
|---|---:|---:|---:|---:|
| LLM 调用步数 | 10 | 14 | 23 | 46 |
| 工具调用数 | 18 | 24 | 35 | 58 |
| 峰值上下文 | 79,538 | 103,930 | 134,713 | 205,573 |
| 单 run 累计 prefill | 695,504 | 1,203,142 | 2,204,409 | 4,536,638 |
| 放大倍数 | 8 | 11 | 18 | 39 |
| 外部检索次数 | 2 | 5 | 10 | 31 |

累计 prefill 1,288,789,277 tok，占纳入集的 **23.0%**。

**首步 prompt 在 961 份之间只差 5 个 token**（22,134 → 22,139）。这是这组同质性的直接证据，也暴露了轴 C 的性质：时间戳每 run 都变，但 token 数几乎不变——它不改变前缀长度，只在第 9,343 字符处切断前缀。

其余各组作为对照保留。上表里 `(−3882, 83a5abfa)` 那 530 份是两个方向的交点：固定目录树变工具配置（558 / 621 / 530）隔离轴 A，固定工具配置变目录树（961 / 530 / 47）隔离轴 D，两个方向都有几百份，不需额外采样。

**V3 那 60 份是校准集，不是观测集。** 它们是唯一带 `llm.tools_snapshot` 的，工具 schema 逐字已知，可用来验证 Δ oracle 和 s3 复现器。但只有一天，57 份共用同一个工具配置，组内几乎没有可观察的变化，且属于另一个 harness 版本，结论不能外推。s3 报的 98.3% 逐字命中率**只在 V3 上验过**，其余 4023 份未验证——引用该数字时必须带上这个限定。

## 2. 已完成结果

### 2.1 历史 cache 字段不可用

| 指标 | 值 |
|---|---|
| 判定 | `identically_zero`：字段存在但值恒为 0 |
| 语料 / usage 记录 | 3999 / 62,649 |
| 非零 `inputCacheRead` / `inputCacheCreation` | 0 / 0 |
| 累计 prefill | 5,604,823,657 tokens |

原因是上报缺陷，不是缓存未命中：服务端当时启用了 `--enable-prefix-caching`，在 vLLM 0.21.0 上，重复前缀请求的 `/metrics` 命中率为 $2112/2443=86.5\%$；但非流式响应的 `prompt_tokens_details` 为 `null`，流式响应甚至没有该字段。`kimi-code` 的 `extractUsage`（`packages/kosong/src/providers/openai-common.ts:204`）取不到 `cached_tokens` 时记为 0；`inputCacheCreation` 也在 openai provider 路径中硬编码为 0（同文件 `:230`）。

因此历史语料无法恢复真实命中率。下游一律改用复现序列上的前缀重叠量，标为**结构性度量**，不得称作命中率。

未来运行已验证的处置：使用 vLLM 0.22.1 和 `--enable-prompt-tokens-details`。同一请求、同一前缀在非流式和流式路径均得到与 `/metrics` 增量一致的 `cached_tokens: 2112`：

| 版本 / 路径 | `/metrics` | 响应 usage | kimi-code 记录 |
|---|---:|---|---:|
| 0.21.0 非流式 | 2112 / 2443 | `prompt_tokens_details: null` | 0 |
| 0.21.0 流式 | 2112 / 2443 | 无该 key | 0 |
| 0.22.1 非流式 | 2112 / 2443 | `cached_tokens: 2112` | 2112 |
| 0.22.1 流式 | 2112 / 2443 | `cached_tokens: 2112` | 2112 |

`cached_tokens` 是服务端实测值，故 E02 可逐请求归因，无需对 `/metrics` 做差，也不再要求请求串行或服务器无其他流量。四次测量均为 $2112/2443=86.5\%$，即 132 个 16-token block；理论公共前缀约 2440 token，331 token 的确定性残差尚未解释。镜像已从 `vllm/vllm-openai:latest` 钉为 `:v0.22.1`（`experiments/p4a/infra/vllm/docker-compose-qwen36-35B.yml`）；版本变更必须复验上报。

> `inputOther = prompt_tokens - cached`。历史数据中 cached 恒为 0，故 `inputOther` 是完整 prompt；新数据中它只表示未命中部分。跨新旧比较必须使用 `inputOther + inputCacheRead`。

### 2.2 放大倍数主要由轨迹长度驱动

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

> 这张表是全语料口径，混了不可比的组。分组之后每组的画像不同——961 组的 p50 步数是 14，比 extract 全体的 15 略低。作为量级参考仍然有效，做组间比较则必须重算。

### 2.3 逐字还原成立

还原链条分两段：`context_builder.py` 把 `wire.jsonl` 回放成每一步的 messages 数组，`render.py` 走 `chat_template.jinja` 加分词器。在 V3 那 60 份带 `llm.tools_snapshot` 的 session 上逐步验收：**1142 个校验点中 1123 个 Δ=0（98.34%）**。

三处必须逐字一致，任一处错掉都对不上：

| | 正确做法 | 错了的代价 |
|---|---|---|
| 工具项 JSON 形状 | 包成 `{"type":"function","function":{…}}` | 用日志里的扁平形状稳定偏低 401 tok |
| `tojson` | `json.dumps(ensure_ascii=False)` | jinja2 自带的会把 `<` `>` `&` `'` 转义 |
| 空白处理 | `trim_blocks` 与 `lstrip_blocks` 均开 | 与 transformers 不一致 |

工具结果的渲染规则同样是照抄而非试出：日志存的是事实（`output` / `isError` / `note`），模型看到的文本由 `agent-core/src/agent/context/tool-result-render.ts` 生成——`isError` 无条件前置 `<system>ERROR: …</system>`，空输出换占位符，`note` 换行追加。只补 `note` 时 11 步里仅对 6 步；漏 `isError` 差 12 tok。

唯一未解释的偏差：`session_3024e2ea` 在 step 7 跳变 −25 tok，后续 19 步带同一偏差。已排除消息条数不符、50000 字符持久化预览、同名调用 dedup、MCP 文本预算四种成因。该 session 标 `exact=false`，不进入逐字分析。

**Δ oracle。** 用它解出每份 session 真实工具块的 token 数（不需知道内容）：

$$
\Delta(\text{候选}) = \text{渲染}(\text{真 systemPrompt} + \text{真 messages} + \text{候选工具}) - \text{inputOther}
= \text{tok}(\text{候选工具块}) - \text{tok}(\text{真工具块})
$$

判定 4005 份（跳过 78 份，全部是 s0 已排除者，纳入集无遗漏），得 **18 种工具配置（下界）**，即轴 A。四个已知候选只覆盖 V3 那 60 份，另外 3945 份对不上任何一个——其余 4023 份来自旧 build，工具 schema 与新 build 不同，原文无从恢复。分组按时间排成基本互不重叠的连续区块：一个月里配置在演进。少数组在时间上重叠且恰好相差 1384 tok（hf-readonly 的 5 个工具），那才是 MCP 启动超时造成的变体。

附带确认：全语料 `content.part` 只有 `text` 一种类型，没有 `think`。这不是日志缺失——若当时把 reasoning 回传给模型，重建值会系统性偏低，而实测每一步精确相等。故这些 run 没有把推理内容放回上下文；`usage.record` 的 `output` 与还原出的 assistant 消息之差即被丢弃的推理长度，单步最多 994 tok。

### 2.4 前缀失效的两个来源，量级差 35 倍

#### A 会话内注入：204,579,397 tok，占全语料 prefill 的 3.65%

模板用 `loop.index0 > ns.last_query_index` 决定 assistant 消息保不保留 `<think>`；`ns.last_query_index` 是最后一条非 `<tool_response>` 的 `role=user` 消息下标（工具结果是 `role=tool`，不参与）。harness 每注入一条这样的消息，该下标前移，此前所有 assistant 消息的 `<think>` 被**回溯性剥掉**——上下文中段被改写，不再是纯追加。

存活前缀恰好是「上一次注入之后那一步」的完整上下文，于是不必渲染即可精确计算：

$$
\text{作废} = \text{inputOther}[\text{注入前最后一步}] - \text{inputOther}[\text{上次注入后第一步}] + 2
$$

常数 2 是生成提示词的边界修正。公式先在 60 份 ground truth 上标定（`make s4` 含 `--check`），核对两件事：误差为常数（57 份为 0，另一份是上述 −25 异常 session），且**注入点集合 == 实际改写点集合**——后者说明注入是非追加式增长的唯一成因，`micro_compaction` 在这批语料里没有触发过。

| | 全语料 | 961 组 |
|---|---:|---:|
| 出现过注入的 session | 2444 / 3999（61.1%） | 608 / 961（63.3%） |
| 作废 token 总量 | 204,579,397 | 48,274,671 |
| 占该范围累计 prefill | 3.65% | 3.75% |
| 受影响 session 每份 p50 | 80,204 | — |
| 首次注入集中在 | step 11（2318 份） | step 11（586 份） |

2661 次注入里 **2617 次是同一条** `<system-reminder>`：*The TodoList tool has not been updated recently…*。首次注入高度集中在 step 11，是定时器而非偶发。这条提醒与 P4A 的任务无关，却让每次触发作废一个已涨到七八万 token 的上下文。961 组的比例与全语料一致，说明这是 workload 层面的性质，不是某一组的特例。

#### B 跨 run 首步前缀：四级反事实

在 −3882 区块（1538 份纳入，工具块 18,696 tok，首步平均 22,138 tok）上做累进归一。工具块在区块内逐字相同且渲染在最前，故只比较其后一段再把工具块 token 数加回。

| 层级 | 共享前缀 | 占首步 | 每 run 浪费 | 区块合计 |
|---|---:|---:|---:|---:|
| L0 原样 | 20,652 | 93.3% | 1,486 | 2,286,177 |
| L1 + 时间戳归一 | 20,974 | 94.7% | 1,164 | 1,790,941 |
| L2 + 工作目录树归一 | 21,944 | 99.1% | 194 | 299,081 |
| L3 + 首条用户消息不含论文对象 | 22,014 | 99.4% | 124 | 191,421 |

大头不是毫秒级时间戳（322 tok），而是 kimi-code 注入 `systemPrompt` 的**工作目录树**（970 tok，占可回收量的 71%）——时间戳归一后区块内仍剩 3 种 `systemPrompt`，差异全在那棵树上，而 P4A 自己在运行中往 `data/processed/` 写文件，等于自己破坏自己的前缀。论文对象移出首条用户消息只值 70 tok：它导致的是后续轨迹分叉，不是前缀分叉。

> 这三种 `systemPrompt` 正是 §1.3 表里 −3882 那三行（961 / 530 / 47）。取 961 组作为观测集，等价于把 L2 变成构造性成立——组内首步 prompt 只差 5 个 token。

不改 harness 代码也有一条：**按 `systemPrompt` 变体分组调度**，同变体内共享前缀即达 99.3%，区块合计浪费从 2,286,177 降至 254,213（−89%），接近 L2。

#### 两者的量级

| 来源 | tokens | 占全语料 prefill |
|---|---:|---:|
| 会话内注入作废 | 204,579,397 | 3.65% |
| 首步跨 run 分歧（按区块外推）| 约 5.9M | 约 0.11% |

注入问题比首步前缀问题大约 35 倍，且更易修（`preserve_thinking`，或把提醒改为 `role=tool` 注入）。首步那 1,486 tok/run 虽刺眼，每 run 只付一次；注入每次作废的是已经很大的上下文。

## 3. 当前推进：961 份上的执行轨迹观测

前缀层面的问题已经问完了：分歧来自哪几条轴、各值多少 token、哪些能免费回收，§1 和 §2 都有答案。剩下的问题在**轨迹**——同一份固定的 Skill 跑 961 篇不同论文，agent 实际走出来的步骤有多少是共通的、从哪里开始分叉、分叉是被输入逼出来的还是可归约的措辞差异。这一层的答案决定 CachePlan 有没有可干预的空间。

在 961 组上做，理由见 §1.3：前缀已构造性同质，观察到的任何分叉都归因于轨迹本身，而不是掺了组间差异。

先记一个已经能看到的迹象。s2 在全语料上报过「第 2 个工具调用开始分叉，众数 Read 占 54.5%」；在 961 组内重算：

| 调用位置 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| 去重工具数 | 1 | 6 | 6 | 6 | 7 | 6 |
| 众数占比 | Read 100% | **Glob 51.3%** | Read 74.5% | Read 98.2% | Read 98.9% | Read 93.5% |

众数从 Read 变成了 Glob。全语料那个数字是把不可比的组混在一起算的，组内重算才有意义——这本身就说明分组是必要的前置步骤，不是可选的精细化。

### 待定的问题

1. **事件表的粒度与列定义。** 轨迹观测需要一张比 session 更细的表（step 或 segment 粒度）。此前拟的列定义有三处未定：`task_spec` 是否单列为一类路径、`tokens_resid` 的阈值取 0 还是先看残差分布、Bash 行的 `path_class` 是否留空并由 `bash_kind` 承载。倾向先在 961 的采样上探列，列定死之后再落成脚本。
2. **分叉的归因。** 需要区分「输入逼出来的分叉」（这篇论文确实没有 GitHub 链接）与「措辞/顺序造成的分叉」（同样的意图写成不同的话）。只有后者是可干预的。判据尚未定。
3. **`n_external` 的角色。** 961 组内 p10=2、p90=10、max=31，外部检索次数跨度很大且与步数相关（全语料 0.461）。它可能是分叉的主要驱动，也可能只是结果。

### 暂不推进

- **恢复旧 build 的工具 schema 原文。** 工具描述是 kimi-code 源码里的静态 `.md`，仓库历史完整，18 个区块边界与发版日期对得上，Δ oracle 是完美验收器。但 961 组的工具块 token 数已精确已知且组内逐字相同，轨迹观测不需要工具原文。除非后续要做工具块内部的干预，否则不做。
- **`session_3024e2ea` 的 −25 tok 偏差。** 已排除四种成因，只影响 60 份校准集里的 1 份。除非它代表某种系统性规则，否则不追。

## 4. 侦察记录（2026-09-01，多数已被脚本结果取代）

> 本节是脚本落地前的一次性侦察，保留以记录判断依据。

原先认为工具 schema 和拼装模板不可得，只能使用代理指标。`wire.jsonl` 中实际有 `config.update`（完整 `systemPrompt`）、`llm.tools_snapshot`（完整 tool schema JSON 和 hash）、`llm.request`（各种 hash，用于一致性校验）。结合 `references/repos/qwen3.6-35b-a3b-tokenizer/` 的 `chat_template.jinja`，可以精确重建 token 序列。

被后续脚本**修正**的三条：

- 原型手工渲染单份 session 首步的 Δ 是 −73 / 27251（0.27%），当时归因于 `permission_mode` 注入和 JSON 序列化。真实成因是工具项的 JSON 形状——vLLM 把每个工具 `model_dump()` 成 `{"type":"function","function":{…}}` 再交给模板，而日志里记的是扁平形状。改用包装形状后 Δ 精确为 0。
- 原以为全语料只有 4 种工具集，差异来自三台远程 MCP 是否在 `startupTimeoutMs: 30000` 内连上。实际那四种只覆盖 V3 那 60 份；Δ oracle 判定后得到至少 18 种，主因是一个月里的版本演进，MCP 启动超时只解释其中少数几组。另注意 `tools.set_active_tools` 全语料恒为同一份 27 名单，但**那不是发给模型的工具集**（它等于最小快照变体），不能据它判断语料同质。
- 原以为「多轮用户输入」才会触发 `<think>` 回溯剥离。实际任何 `role=user` 的注入都会触发，代价已由 §2.4 精确定价。

被**取代**的一条：300 份采样估计 `systemPrompt` 跨 run 公共前缀中位数 60%、总损失约 540 万 token。已由 §2.4 的四级反事实取代。

## 5. 风险

| 风险 | 影响 | 处置 | 状态 |
|---|---|---|---|
| 4023 份 session 无工具集记录 | 无法逐字复现工具块 | Δ oracle 判定 | 已判定 18 种配置；工具块 token 数精确已知，原文仅 60 份可得 |
| 复现器只在 V3 上验过 | 98.3% 命中率不能外推 | 标注限定 | 已标注；961 组的复现正确性未独立验证 |
| `micro_compaction = true` | 触发后消息列表被重写 | Δ oracle 捕获 | 已排除：注入点集合 == 实际改写点集合 |
| kimi-code 截断或改写工具结果 | 复现值偏高 | Δ 分布暴露 | 已处理：50000 字符预览与 `tool-result-render.ts` 三条规则均已复刻 |
| 混合不可比的组做统计 | 结论无意义 | 固定观测集 | 已处理：观测集固定为 961 份；§2.2 的全语料表已加限定 |
| 观测集只覆盖 4 天 | 结论可能是这 4 天的特例 | 其余 6 组作为对照 | 待做：交叉设计已就位（§1.3），尚未执行 |

## 6. 对 E02 的约束

E01 不依赖 vLLM 或 MCP，但 E02 必须：

1. 固化 MCP schema，或至少 fail-fast。远程 schema 可变且位于 prompt 前缀；启动失败会静默改变前缀并削弱能力。
2. 固定 vLLM 0.22.1 并开启 `--enable-prompt-tokens-details`。`wire.jsonl` 可直接提供逐请求真实命中数；版本变更必须复验。
3. **禁止运行期间升级 harness。** P4A 一个月里换出至少 18 种工具配置和 3 个 harness 版本，每换一次全量共享前缀归零。E02 必须钉死版本并记录。
4. **控制 `role=user` 注入。** 这是 E01 发现的最大单项浪费（2 亿 token，3.65%，且在同质组内比例一致）。要么关掉与任务无关的定时提醒，要么改用 `role=tool` 注入，要么开 `preserve_thinking` 让模板不再回溯剥离。保持单轮只是这条的一个特例。
5. **稳定 `systemPrompt` 里的易变块。** 时间戳与工作目录树各自破坏跨 run 前缀，后者影响是前者的三倍。时间戳后移是零成本的（轴 C）；目录树要么冻结工作目录，要么移到 `systemPrompt` 末尾。
6. **不要在运行中往工作目录写文件。** P4A 往 `data/processed/` 写产物，改变了 systemPrompt 里的目录树，等于自己破坏自己的前缀——10 个树状态就是这么来的。

## 数据来源

- `data/processed/e01/` 下全部产物均 gitignored 且含 `_provenance`：
  - `s0_summary.json`、`s0b_summary.json`、`s1_cache_fields.json`、`s2_summary.json` — `make all`
  - `s0b_prompt_blocks.jsonl` — `make s0b`（约 10 秒），含逐 session 的块 md5 / 字符数 / 偏移与六轴类标签
  - `s3_render.jsonl`、`s3_render_summary.json` — `make s3`（约 3 分钟）
  - `s4_divergence.jsonl`、`s4_summary.json` — `make s4`（约 6 分钟，含公式标定）
  - `dumps/` — `make dump SID=<片段>`，逐步上下文原文
- 源数据：`data/raw/kimi-p4a-sessions.tar.gz`，md5 `9cfa1d2400d2fe283c0850a14804940b`。
- 分词器与 chat template：`references/repos/qwen3.6-35b-a3b-tokenizer/`，未纳入版本管理。换模型必须换它并重跑 `make s3` 的自检。
- 分析入口：`experiments/e01-p4a-trajectory/notebooks/`。notebook 只切上述产物，`nbio.banner()` 在每本开头声明读的是哪一版，并在检出 `--limit` 产物时报警。
