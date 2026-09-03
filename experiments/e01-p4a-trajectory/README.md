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
| s0b | `s0b_prompt_blocks.py` | systemPrompt 分块，给出各轴的类标签 | 已实现 |
| s1 | `s1_cache_fields.py` | cache 字段是否可用 | 已实现；结论：不可用 |
| s2 | `s2_session_stats.py` | 放大倍数的全量分布与分层归因 | 已实现 |
| s3 | `s3_render.py` | 复现每步真正进入模型的 token 序列 | 第一步已实现：还原器自检 + 工具集判定 |
| s4 | `s4_divergence.py` | 前缀在哪儿断、断掉多少 token（会话内注入 / 跨 run 首步） | 已实现 |
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
make setup         # 委派给仓库根：建共享 .venv 并装 git 过滤器
make all           # s0 -> s0b -> s1 -> s2
make s0b           # systemPrompt 分块与类标签（约 10 秒）
make smoke         # 只扫前 50 份，改完代码后的快速自检
make verify        # 带来源 md5 核算（约 350MB，数秒）
make verify-stdlib # 在无第三方依赖的隔离环境里跑主线，不动共享 .venv 也不动产物

make s3            # 还原器自检 + 全语料工具集判定（约 3 分钟）
make s4            # 前缀失效的两个来源各自量化（约 6 分钟）
make dump SID=2d549e55   # 导出某份 session 的逐步上下文，供肉眼看原文
```

产物落在仓库根的 `data/processed/e01/`（已被根 `.gitignore` 忽略）。每个产物
文件的第一行/顶层是 `_provenance`，记录脚本名、git rev、生成时间、Python 版本、
来源指纹与调用参数。

## Notebook

脚本产出产物，notebook 读产物 —— 这条分工见 `AGENTS.md` →
Notebooks are the exploration surface。notebook 里**不允许**出现某个被引用数字的
唯一来源；口径要改就改 `src/e01/` 下的脚本。

```bash
make -C ../.. lab      # 起 JupyterLab（共享 .venv，仓库根统一环境）
```

| | 读什么 | 回答什么 |
|---|---|---|
| `notebooks/00_corpus.ipynb` | s0 | 语料形状：纳入/排除、流产率、时间结构 |
| `notebooks/01_session_classes.ipynb` | s0b + s3 | 六条划分依据，逐轴的定义与分布 |
| `notebooks/02_trajectory.ipynb` | 宽表 | 961 份观测集上的执行轨迹 |

`notebooks/nbio.py` 是共用的读入层：`load(stage)` 给逐 session 的 DataFrame，
`summary(stage)` 给脚本已算好的聚合量，`wide()` 把 s0×s2×s3×s4 按 `sid` join 成
一张 4083 行的宽表。每本 notebook 的第一个 cell 都调 `nbio.banner()`，把在场产物的
git rev、生成时间、来源指纹摊开 —— 并在检出 `--limit` 产物时明确报警（`make smoke`
和 `verify-stdlib` 写的是与全量同名的文件，被覆盖过的产物只有前 50 份）。

`00_corpus.ipynb` 末尾会逐条复算 `docs/experiments/e01-p4a-trajectory.md` 第 1 节
引用的 10 个数，对不上就 assert 失败。

## 环境与依赖

本实验是**仓库根 uv workspace 的成员**（见 `AGENTS.md` → Environment and
Notebooks）。环境只有一个：根目录的 `.venv`，由根的 `make setup` 建立，锁文件
是根的 `uv.lock`。本目录不再有自己的 `.venv` / `uv.lock`。

> **不要在本目录直接跑 `uv sync`。** 那会把 e01 当作活动项目，顺手把根
> `[dependency-groups]` 里的 jupyter / pandas 从共享环境里剪掉。用 `make setup`，
> 它委派给根。

`experiments/p4a/` 仍是独立的自包含项目，被排除在 workspace 外——它钉了
`vllm<0.22.0` 和整套 mineru，与本项目给后续实验定的 vLLM 0.22.1 装不进同一个
环境，而且它对我们是只读的历史项目。

**主线阶段（s0–s2、s4–s5）依然只用标准库**，`pyproject.toml` 里 `dependencies = []`。
这是刻意的：整条流水线必须能在没有网络、没有模型下载的机器上原样复现。统计量
宁可自己写十几行（见 `stats.py`），也不为分位数引入 numpy/pandas。

共享 .venv 里现在装着 tokenizers 和 pandas，所以 **`make smoke` 通过已不能证明
这条性质**。证明它的是 `make verify-stdlib`：在 uv 的临时隔离环境里只装 e01
自身（其依赖为空）跑 s0–s2，既不碰共享 .venv，也不覆盖已有产物（`--limit` 写的
是与全量同名的文件，故该目标会先备份后还原）。

### 分词器（仅 s3 需要）

s3 要逐字复现进入模型的 token 序列，必须用与服务端相同的 chat template 和
分词器。**没有字符级的退化路径** —— 缺依赖时 s3 直接退出，不产出估计值：

根的 `make setup` 已经 `--all-extras`，所以装好环境就有；`make setup-render`
保留为 `setup` 的别名，仅为兼容既有习惯。

两者都在 `references/repos/qwen3.6-35b-a3b-tokenizer/`（未纳入版本管理）。
换模型必须换这个目录，并重跑 `make s3` 的自检。

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
