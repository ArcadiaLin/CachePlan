# Environment

复现所需的环境。分三块：本仓库、P4A 现网（历史，已停止但数据保留）、数据资产。

---

## 1. 本仓库 CachePlan

- 仓库根：`/home/ArcadiaLin/projs/CachePlan`
- 平台：Linux 6.6.87.2-microsoft-standard-WSL2
- **CachePlan 自身的方法代码尚不存在。** 目前仓库里只有 P4A 这个历史项目的代码
  （`experiments/p4a/`）与文档。

目录结构：

```
CachePlan/
  AGENTS.md            研究方向、workload 定义、工作原则（CLAUDE.md 仅 @ 引用它）
  docs/
    PROGRESS.md        主线追踪：方向、当前工作、open questions / decisions / experiments 表
    open-questions/    未解决的研究问题
    decisions/         已收敛结论（ADR 风格）—— 目录尚不存在，无已收敛条目
    experiments/       实验记录
    literature/        我们对文献的判断（当前索引为空）
  experiments/p4a/     P4A 历史项目代码（只读，见 constraints.md 第 1 节）
  references/
    refs.bib           文献元数据唯一来源（当前为空）
    papers/            PDF 与精读稿暂存区（gitignored）
  data/raw/            外部数据（gitignored）
  ara/                 本 artifact
```

**gitignored 的关键路径**（`.gitignore:2,7`）：`/references/papers/`、`/data/raw/`、
`/data/processed/`、`/data/cache/`。所以本 artifact 引用的 P4A session 日志与两篇精读稿
**在 clone 后都不存在**，需要按下面第 3 节重新取回。

---

## 2. P4A 现网环境（历史，产生了本项目的全部实测数据）

### Agent runtime

- **kimi-code CLI**，每篇论文起一个独立的 ReAct agent session
- agent 读 skill → 分块读全文 → 查 arXiv/GitHub/HuggingFace → 下载文件 → 判断资源 →
  写 JSON → 跑验证脚本

**Sources**
- ← `experiments/p4a/refractor.md:8` «现在的 Layer4 是"每篇论文启动一个 Kimi ReAct Agent"。agent 读 skill、分块读全文、查 arXiv/GitHub/HuggingFace、下载文件、判断资源、写 JSON、跑验证脚本。» [input]

### 模型与 serving

| 项 | 值 |
|---|---|
| 模型 | `qwen3.6-35b-a3b` |
| serving | 本地 vLLM |
| `max_model_len` | 262144（上下文 262K） |
| prefix caching | **已启用**，实测命中率 89% |
| KV 占用 | 2.8%，0 抢占 |

**Sources**
- ← `experiments/p4a/refractor.md:44` «模型环境：本地 vLLM `qwen3.6-35b-a3b`，上下文 262K，prefix caching 已启用（实测命中率 89%）。» [input]
- ← `experiments/p4a/refractor.md:256` «vLLM：`qwen3.6-35b-a3b`，max_model_len 262144；prefix cache 命中率 89%，KV 占用 2.8%，0 抢占。» [result]

> ⚠️ 该 usage 日志里的 cache 字段被观测为 0，与此处的 89% 是两本账。见
> [`../logic/solution/cache-accounting.md`](../logic/solution/cache-accounting.md)。

### 网络约束（现网踩坑固化）

- `arxiv.org` / `huggingface.co` / `github.com` 出口**一律走 `http://127.0.0.1:7899` 代理**
- 本地服务（`127.0.0.1`、`192.168.163.112`）**绝不走代理**

**Sources**
- ← `experiments/p4a/refractor.md:105` «网络约束（现网踩坑固化）：arxiv.org / huggingface.co / github.com 出口一律走 `http://127.0.0.1:7899` 代理；本地服务（127.0.0.1、192.168.163.112）绝不走代理。» [input]

### Python 环境（`experiments/p4a/pyproject.toml`）

```toml
requires-python = ">=3.12,<3.14"
dependencies = [
    "arxiv<2", "docopt>=0.6.2", "fastapi<0.137.0", "lxml>=6.1.1",
    "mineru[core,vllm]>=3.3.1,<4.0.0", "starlette<0.52.0",
    "vllm>=0.21.0,<0.22.0",
]
```

用 `uv` 管理（`uv.lock` 在库内，`.python-version` 指定解释器）。脚本一律从项目根目录以
`.venv/bin/python src/...` 运行。

### 外部数据根目录（现网）

```
/srv/datasets/p4a/data
```

P4A 脚本里的路径**硬编码了这个根目录与 `/home/lzx/projs/p4a` 这个工作目录**，在本仓库的
环境下不可直接运行。这是已知的可复现性缺口。

**Sources**
- ← `experiments/p4a/src/pipeline.md:6` «/srv/datasets/p4a/data» [input]
- ← `experiments/p4a/src/run_pipeline.py:5` «# cd /home/lzx/projs/p4a» [input]

---

## 3. 数据资产

### P4A session 日志

- 压缩包：`data/raw/kimi-p4a-sessions.tar.gz`（**gitignored，不进版本库**，约 349 MB）
- 解压后结构：
  `data/raw/kimi-p4a-sessions/.kimi-code/sessions/<workdir_id>/session_<uuid>/`
- 共约 **12,801 个文件**，对应全量 ACL 2025 主会论文的批量运行记录

每个 session 目录包含：

| 文件 | 内容 |
|---|---|
| `state.json` | 任务的原始 prompt（`lastPrompt`）、创建/更新时间 |
| `logs/kimi-code.log` | 每个 turnStep 的模型配置（model、thinkingEffort、systemPromptChars、toolCount）与请求时间戳 |
| `agents/main/wire.jsonl` | 完整 wire 协议轨迹 |

`wire.jsonl` 里与本项目相关的事件类型：

- `usage.record` — 逐 turn 的 input/output/**cache** 字段（B01 的数据源，也是 E01 阶段 1–2 的数据源）
- `context.append_message` — 用户消息与 system-reminder 注入
- `context.append_loop_event` — `tool.call` / `tool.result` / `step.begin` / `step.end` /
  `content.part`，即逐步的工具调用序列与助手输出

**Sources**
- ← `docs/experiments/p4a.md:25-30` «- 压缩包：`data/raw/kimi-p4a-sessions.tar.gz`（已 gitignore，不进版本库）。»…«- 共约 12,801 个文件，对应全量 ACL 2025 主会论文的批量运行记录。» [input]

### 两篇论文的本地材料（gitignored）

```
references/papers/<citekey>/
  source.pdf          原始 PDF
  paper.txt           带 ===== [page N] ===== 标记的全文
  close-read.md       精读稿（staged，未评审）
  evidence_map.md     证据地图
  figures/            按 caption bbox 从 PDF 渲染裁剪的图
  images/             pymupdf 抽出的嵌入图（两篇均基本不可用：矢量图抽出的是 soft-mask，渲染为纯黑）
  pages/              整页渲染
```

**取回方式**：`refs.bib` 当前为空，两个条目已于 `c6ece08` 被移除，因此**无法按仓库规范
从 `refs.bib` 的 url 取回**。可从 commit `c6ece08^` 的 `refs.bib` 恢复元数据。

---

## 4. 本 artifact 的复现状态

| 项 | 可复现性 |
|---|---|
| B01（单 session 解剖，继承观测） | ❌ 分析逻辑未落成脚本 |
| E01（全量轨迹观测，**本项目第一个实验**） | ⏳ 数据在，脚本未写，未开始 |
| P4A 流水线本身 | ❌ 硬编码 `/srv/datasets/p4a/data` 与 `/home/lzx/projs/p4a` |
| 两篇精读稿 | ⚠️ 本地存在但 gitignored；refs.bib 条目已移除 |
| CachePlan 主实验 | — 尚不存在 |
