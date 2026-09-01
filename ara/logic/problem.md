# Problem

## 1. 触发观测

CachePlan 不是从文献 gap 立项的，是从一次运维观测立项的。P4A（`experiments/p4a/`）用
kimi-code CLI 对全量 ACL 2025 主会论文做批量资源抽取，每篇论文起一个 ReAct agent。在
prefix-cache 与代理优化都已生效之后的批次上，实测中位数是：

| 量 | 实测值 |
|---|---|
| 单篇会话耗时 | 144 s（全周期 172.5 s） |
| 工具调用 | 26 次 / 16 步 |
| 累计计费 input | 约 140 万 token |
| 最终一步真实上下文 | 8–11 万 token |
| output | 1.1 万 token |
| 吞吐 | 19.7 篇/h（串行，GPU 占空比约 52%） |

**Sources**
- 全表 ← `experiments/p4a/refractor.md:12-19` «| 单篇会话耗时 | 144 s（全周期 172.5 s） |»…«| 吞吐 | 19.7 篇/h（串行，GPU 占空比约 52%） |» [result]
- 140 万 / 8–11 万 / 10–18 倍的采样口径 ← `experiments/p4a/refractor.md:253` «token：抽样 80 篇 `agent_usage.json`，累计计费 input 中位 140 万；3 个会话逐事件解剖显示最终真实上下文仅 8–11 万，放大 10–18 倍来自 ReAct 每步重发历史。» [result]

关键的一句归因（原文）：

> 慢和贵的根因不是某个工具（外部核验单次仅几百 token、几秒），而是 **ReAct 循环每步重发
> 全部历史**：input 计费被放大 10–18 倍

**Sources**
- ← `experiments/p4a/refractor.md:21` «慢和贵的根因不是某个工具（外部核验单次仅几百 token、几秒），而是 **ReAct 循环每步重发全部历史**：input 计费被放大 10–18 倍» [result]

单条 session 的独立复现（2026-08-31，随机抽样 `session_0b334391-...`，对应论文
`2025.acl-long.114`）与上述整体统计一致：19 轮、累计计费 input 1,893,916 token、最终
真实上下文 121,499 token、放大 15.6x。

**Sources**
- 1,893,916 / 121,499 / 15.6x ← `docs/experiments/p4a.md:20` «19 轮对话，累计计费 input 1,893,916 token，最终真实上下文 121,499 token，放大倍数 15.6x，与 `refractor.md` 里给出的整体统计一致。» [result]

## 2. 一个立刻出现的口径矛盾

同一批数据里有两个互相矛盾的信号：

- serving 侧：本地 vLLM `qwen3.6-35b-a3b`，**prefix caching 已启用，实测命中率 89%**，
  KV 占用 2.8%，0 抢占。
- 日志侧：抽样那条 session 的全部 19 条 `usage.record`，`inputCacheRead` /
  `inputCacheCreation` **均为 0**。

**Sources**
- 89% / 2.8% / 0 抢占 ← `experiments/p4a/refractor.md:256` «vLLM：`qwen3.6-35b-a3b`，max_model_len 262144；prefix cache 命中率 89%，KV 占用 2.8%，0 抢占。» [result]
- 恒为 0 ← `docs/experiments/p4a.md:21` «该 session 全部 19 条 `usage.record` 的 `inputCacheRead` / `inputCacheCreation` 均为 0——尚未确认是全量数据的普遍现象还是这条样本的个例，见第 4 节的先决核查项。» [result]

这不是数据错误，而是**两个不同的量**：计费/日志里的 "input token" 计的是这一步送进去的
完整历史，与 serving engine 是否复用了这段历史的 KV **互不蕴含**。这个区分后来变成本项目
方法论的核心（见 [`solution/cache-accounting.md`](solution/cache-accounting.md)）。

## 3. Gap

1. **跨 run 的前缀复用没有被当成一个变量。** P4A 的 Skill 对每篇论文逐字相同，跑了上千次；
   这是一个巨大的 *a priori* 共享前缀。但语义等价而措辞不同的 agent 行为
   （"I will first read the skill." / "Let me read the skill first."）会产生不同的
   token 序列，侵蚀这个前缀。没人测量过这块空间有多大。
2. **成本口径普遍不区分计费 token 与实际 prefill。** 报告未经 cache 折算的原始 token
   计数，会系统性高估步数多的执行风格的成本。
3. **"agent 是否是这类任务的正确执行抽象" 从未被验证过。** 直接去优化 ReAct 的 cache
   locality，可能是在优化一种并非必要的执行方式。

## 4. 核心 insight

> workload 的可优化性来自 **固定过程 + 大量重复**，不来自任务语义。

因此本项目研究的对象被明确定名为 **data-intensive / data-processing agent workflows**，
而不是 "data analysis agents"：后者强调任务在分析什么，前者强调同一份 procedural
knowledge 被重复执行了多少次——只有后者决定跨 run 前缀复用的空间有多大。

**Sources**
- ← `AGENTS.md:39` «because the procedural knowledge is fixed and the runs are many, there is a large *a priori* shared prefix across runs, and any divergence in how the agent phrases or orders its steps is what erodes reuse of that prefix» [input]
- ← `docs/PROGRESS.md:11` «这一命名对研究是 load-bearing 的：跨 run 的**固定过程 + 大量重复**才是 cache 复用空间的来源，"data analysis" 强调的是任务语义，指向了错误的属性。» [input]

## 5. 研究问题

主问题（`AGENTS.md`）：

> Can agent planning and execution be designed to improve cache reuse without
> significantly reducing agent capability or task performance?

**但这个问题被一个前置问题挡住**（`docs/open-questions/Necessity-of-agentic-execution.md`）：

> **How much agency is actually necessary for end-to-end data-intensive processing
> tasks such as P4A?**

**Sources**
- ← `docs/open-questions/Necessity-of-agentic-execution.md:13` «**How much agency is actually necessary for end-to-end data-intensive processing tasks such as P4A?**» [input]

两种结果导向两条不同的路：

- 若 Full ReAct 与强 workflow baseline 任务质量基本相当 → 优化 ReAct 的 cache locality
  是在优化一种非必要的执行方式，方向应转向 **cache-aware execution of LLM workflows**。
- 若 workflow 在困难/开放/不确定的样本上明显掉 recall，而 agent 能靠动态调查补回来 →
  研究前提成立：**Agency is useful, but expensive. Cache-aware planning and execution
  aims to make necessary agency cheaper.**

**Sources**
- ← `docs/open-questions/Necessity-of-agentic-execution.md:19` «此时继续优化 ReAct execution 的 cache locality 可能是在优化一种并非必要的执行方式，研究方向可能更适合转向 **cache-aware execution of LLM workflows**。» [input]
- ← `docs/open-questions/Necessity-of-agentic-execution.md:23` «**Agency is useful, but expensive. Cache-aware planning and execution aims to make necessary agency cheaper.**» [input]

## 6. 当前假设（未验证，标明为假设）

| # | 假设 | 状态 |
|---|---|---|
| A1 | 模型是 frozen 的，本项目不训练模型 | 工作假设，未在任何文档中被质疑 |
| A2 | P4A 类 workload 的 agency 需求是非均匀的：普通样本可 workflow 化，困难样本需要 adaptive reasoning | 假设，正是 OQ 要验证的 |
| A3 | 跨 run 前缀复用的空间足够大到值得优化 | **未测量**，被先决核查项阻塞 |
| A4 | P4A 的轨迹结构可推广到其他批量 agent workload | 明确被标为需要第二个 workload 才能支撑 |

## 7. 明确的"不能下的结论"

- 在先决核查项完成之前，**不得基于 cache 命中率下任何结论**。
- P4A 数据**不能**作为 "CachePlan 方法是否有效" 的对照组基线，只能做诊断性/动机性分析。
- 两篇已精读论文的结论**未经人工评审**，不可引用。

详见 [`solution/constraints.md`](solution/constraints.md)。
