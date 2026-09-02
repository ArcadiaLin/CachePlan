# E01 — P4A 历史 session 轨迹的全量观测

本项目的**第一个实验**。性质是**观测，不是干预**：对象是已经存在且不可变的
4083 份 agent 执行日志，只读、不跑 agent、不改 `experiments/p4a/` 下任何东西、
不重跑任何流水线。

对应的研究记录见 [`docs/PROGRESS.md`](../../docs/PROGRESS.md) 的 Current Work。
P4A 数据的使用边界见 [`docs/experiments/p4a.md`](../../docs/experiments/p4a.md)
第 4 节 —— 一句话：**只能做诊断性/动机性分析，不能作为「CachePlan 方法是否
有效」的对照基线。**

## 输入

```
data/raw/kimi-p4a-sessions.tar.gz                     365,841,989 B
  md5 9cfa1d2400d2fe283c0850a14804940b
data/raw/kimi-p4a-sessions/.kimi-code/sessions/
  wd_p4a_aa908ecb9359/session_<uuid>/                 4083 份
    state.json                                        会话元数据
    agents/main/wire.jsonl                            主 agent 完整事件流（1.4 GB）
    agents/agent-N/wire.jsonl                         子 agent（p90 = 0 个）
    logs/, agents/main/{tool-results,tasks,plans}/    旁路产物
```

来源指纹写死在 `src/e01/provenance.py`。换数据集时必须同步更新，否则
`make verify` 会报错退出。这是防止分析悄悄换了输入而无人察觉。

### 已知的数据卫生问题（在 s0 里显式处理，不静默丢弃）

| 现象 | 数量 | 处置 |
|---|---|---|
| `state.json` 的 `lastPrompt`/`title` 被 redact | 1671 | **不从 state.json 取 prompt**，改用 `wire.jsonl` 的 `turn.prompt`（未 redact）。改用 wire 之后 paper_id 的定位率从 2696/4083 升到 3997/3999（纳入集） |
| 流产的 run：`step.begin` 发了、`step.end` 没到（形态一致为 n_steps=1 / n_tools=0 / model=None） | 73 | 排除，理由 `aborted`。**不并入 `no_usage`** —— 它的发生率是这个 workload 的一个观测量，不是噪声：extract 1/3765 (0.03%)，repair **68/306 (22.2%)** |
| 操作者本人的交互（"Say ok only."、"继续你的工作"、空 prompt 等） | 12 | 排除，理由 `operator_chat`，清单里保留原文前 200 字备查 |
| 零步会话 | 5 | 排除，理由 `no_steps` |
| 不止一轮：用户多次输入，或 harness auto-continue（`turnId` 有多个值但只有一条 `turn.prompt`） | 4 | 排除，理由 `multi_turn`。auto-continue 那两份在 workload 语义上仍是一次 run，但上下文里多了一段只有它才有的注入文本，前缀结构不再与其余 run 可比 |

纳入 3999 份（extract 3762 / repair 237），覆盖 3321 篇不同论文。

## 阶段

阶段之间只通过 `data/processed/e01/` 下的产物传递，可以单独重跑。

| | 脚本 | 回答什么 | 状态 |
|---|---|---|---|
| s0 | `s0_manifest.py` | 语料清单与纳入过滤 | 已实现 |
| s1 | `s1_cache_fields.py` | cache 字段是否可用 | 已实现；结论：不可用 |
| s2 | `s2_session_stats.py` | 放大倍数的全量分布与分层归因 | 已实现 |
| s3 | `s3_render.py` | 复现每步真正进入模型的 token 序列 | 未实现 |
| s4 | `s4_divergence.py` | 轨迹分叉点：语义等价的行为在何处首次产生不同 token | 未实现 |
| s5 | `s5_behavior.py` | 行为统计：被赋予的 agency 有多少真的被行使 | 未实现 |

s1 已给出结论且不会再变：全语料 `inputCacheRead` / `inputCacheCreation` 恒为 0，
成因是 vLLM 0.21.0 的上报缺陷而非缓存未命中（服务端实测命中率 86.5%）。
**历史语料的真实命中率不可得**，s3 之后一律改用复现序列上的前缀重叠量，标为
结构性度量，不得称作命中率。完整归因见
[`docs/experiments/e01-p4a-trajectory.md`](../../docs/experiments/e01-p4a-trajectory.md)
第 2 节。

## 运行

```bash
cd experiments/e01-p4a-trajectory
make setup     # 建 .venv
make all       # s0 -> s1 -> s2
make smoke     # 只扫前 50 份，改完代码后的快速自检
make verify    # 带来源 md5 核算（约 350MB，数秒）
```

产物落在仓库根的 `data/processed/e01/`（已被根 `.gitignore` 忽略）。每个产物
文件的第一行/顶层是 `_provenance`，记录脚本名、git rev、生成时间、Python 版本、
来源指纹与调用参数。

## 环境与依赖

沿用 `experiments/p4a/` 的做法：**每个实验是一个自包含的 uv 项目**，有自己的
`pyproject.toml` / `uv.lock` / `.python-version`。不共用仓库级环境，因为各实验
的依赖差别很大（p4a 拖着 vllm 和 mineru，本实验一个都不需要），共用会让
「复现这个实验」变成「装上另一个实验的全部依赖」。

**主线阶段（s0–s2、s4–s5）只用标准库**，`dependencies = []`。这是刻意的：
整条流水线必须能在没有网络、没有模型下载的机器上原样复现。统计量宁可自己
写十几行（见 `stats.py`），也不为分位数引入 numpy/pandas。

### 分词器（仅 s3 需要）

s3 要复现进入模型的 token 序列，必须用与服务端相同的分词器。目前登记为
**可选依赖**，s3 落地时转为必需：

```bash
uv sync --extra tokenize
```

分词器与 chat template 在 `references/repos/qwen3.6-35b-a3b-tokenizer/`（未纳入
版本管理）。**不存在字符数到 token 数的换算比**，字符级结果不可作为替代。

## 重建流的边界（务必先读）

`wire.py` 的 `context_stream()` 把 segments 拼成一条字节流。**它不是发给模型的
真实 prompt** —— 它只保证「同一 harness 下、跨 run 之间可比」。s2 之前的分析
只依赖这个性质；s3 起改为逐字复现，不再使用它。

s3 逐字复现是可行的，2026-09-01 的侦察已证实（完整记录见
[`docs/experiments/e01-p4a-trajectory.md`](../../docs/experiments/e01-p4a-trajectory.md)
第 3 节）。三件事必须先知道：

1. **工具 schema 在日志里，但只有 60/4083 份带。** 事件是 `llm.tools_snapshot`。
   这 60 份里有 **4 个不同快照**，工具数分别为 27 / 32 / 39 / 44，差异只在两个
   远程 MCP（`github-readonly`、`hf-readonly`）是否在 `startupTimeoutMs: 30000`
   内就绪；24 个内置工具与本地的 `arxiv-mcp` 在四者中逐字相同。其余 4023 份的
   变体要靠 Δ oracle 判定（下条）。
2. **`tools.set_active_tools` 不是发给模型的工具集，不能拿它判定变体。** 它在
   全语料恒为同一份 27 名单（哈希 `2a4c24f3`），而那恰好等于最小快照
   `5e110149` —— 说明它记的是会话初始化时已注册的本地工具，远程 MCP 那时还没
   握手完。s0 汇总里的 `n_active_tools_values: {27: 4083}` 是这个意思，不代表
   语料同质。
3. **Δ oracle。** 每条 `step.end` 的 `usage.inputOther` 就是服务端算出的
   `prompt_tokens`（历史数据 cached 恒为 0，见上），全语料 62,649 个独立校验点。
   复现对不对不靠推断，逐条比对即可。

已知的组装顺序（来自 `chat_template.jinja`）：**工具先渲染进第一条 system 消息，
`config.update` 里的 systemPrompt 逐字附在其后**。原型复现单份 session 首步的
结果是 Δ = −73 / 27251（0.27%），其中工具占 22575 tokens（83%）。之前「工具与
system prompt 谁在前会差一个数量级、s3 必须报上下界」的说法就此作废 —— 顺序
已确定，s3 报单值。
