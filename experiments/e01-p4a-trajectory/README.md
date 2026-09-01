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
| `state.json` 的 `lastPrompt`/`title` 被 redact | 1671 | **不从 state.json 取 prompt**，改用 `wire.jsonl` 的 `turn.prompt`（未 redact）。改用 wire 之后 paper_id 的定位率从 2696/4083 升到 3999/4001（纳入集） |
| 流产的 run：`step.begin` 发了、`step.end` 没到（形态一致为 n_steps=1 / n_tools=0 / model=None） | 73 | 排除，理由 `aborted`。**不并入 `no_usage`** —— 它的发生率是这个 workload 的一个观测量，不是噪声：extract 1/3765 (0.03%)，repair **68/306 (22.2%)** |
| 操作者本人的交互（"Say ok only."、"继续你的工作"、空 prompt 等） | 12 | 排除，理由 `operator_chat`，清单里保留原文前 200 字备查 |
| 零步会话 | 5 | 排除，理由 `no_steps` |

纳入 4001 份（extract 3764 / repair 237），覆盖 3323 篇不同论文。

## 阶段

阶段之间只通过 `data/processed/e01/` 下的产物传递，可以单独重跑。

| | 脚本 | 回答什么 | 状态 |
|---|---|---|---|
| s0 | `s0_manifest.py` | 语料清单与纳入过滤 | 已实现 |
| s1 | `s1_cache_fields.py` | **闸门**：cache 字段是否可用 | 已实现 |
| s2 | `s2_session_stats.py` | 放大倍数的全量分布与分层归因 | 已实现 |
| s3 | `s3_prefix.py` | 跨 run 前缀重叠结构：共享前缀有多长、在哪里断 | 未实现 |
| s4 | `s4_divergence.py` | 轨迹分叉点：语义等价的行为在何处首次产生不同 token | 未实现 |
| s5 | `s5_behavior.py` | 行为统计：被赋予的 agency 有多少真的被行使 | 未实现 |

s1 是闸门：**在它给出结论之前，任何基于 cache 命中率的分析都不得进行。**

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

s3 的跨 run 前缀重叠要给出可比的数字，需要 token 级切分。它是**可选依赖**：

```bash
uv sync --extra tokenize
```

未装时 s3 仍可产出字符级结果，但**只能作为量级参考**。原因：观测到的
system prompt 是 15042 字符，而首步 prefill 的 `inputOther` 中位数是 22137
tokens —— 差出来的部分不在日志里（推断为 27 个工具的 schema，见下），
所以字符数与 token 数之间没有稳定的换算比。

## 重建流的边界（务必先读）

`wire.py` 的 `context_stream()` 把 segments 拼成一条字节流。**它不是发给模型
的真实 prompt**，有两处已知缺口：

1. **工具 schema 不在日志里。** 全语料 `n_active_tools` 恒为 27，但 schema 正文
   没有落盘。首步 prefill 22137 tokens 减去 system prompt（15042 字符）与用户
   prompt（约 411 字符）之后，仍有约 18K tokens 无法归因，推断即为工具 schema。
2. **段间模板/分隔符未知。** harness 如何把 system prompt、工具声明、消息序列
   拼成最终请求，日志里看不到。

因此重建流只保证「同一 harness 下、跨 run 之间可比」，不保证与真实 prompt
逐字相同。前缀分析只依赖前者。**工具声明与 system prompt 谁在前，会让跨 run
不变前缀的估计相差一个数量级**，这一点在拿到 harness 的组装逻辑之前，s3 必须
同时报告上下界，不得只报一个数。
