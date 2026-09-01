# Concepts

本项目自有的术语。只收录**在本仓库里被赋予了特定含义**的词——通用术语（ReAct、KV cache、
GRPO 等）不在此列。

---

## data-intensive / data-processing agent workflow

本项目研究的 workload 类别。判据是五条**同时**成立：

1. **fixed procedural knowledge** — 一份长而稳定的 Skill / agent prompt，对每个输入编码
   同一套流程；
2. **input-parallel repetition** — 同一流程跑在一个同构但不相同的输入语料上，每个输入一次
   独立 run；
3. **long-horizon tool-augmented execution** — 多轮 read / extract / search / merge，
   跨本地脚本与外部来源；
4. **validation and repair** — run 不在首次产出时结束；结果对 schema 或 checker 校验，
   失败触发重新调查或定点修复；
5. **structured end-to-end output** — 交付物是结构化记录，不是对话式回答。

**与 "data analysis agent" 的区别是 load-bearing 的**：后者强调任务语义（在分析什么），
前者强调固定过程被重复了多少次。只有后者决定跨 run 前缀复用的空间。

来源：`AGENTS.md:33-39`

## fixed procedural knowledge

在一批 run 之间**逐字相同**的那部分 prompt——Skill、agent 指令、算子文档、schema 定义。
它是跨 run 共享前缀的**上界**：任何 run 之间可复用的 KV 都必须落在这部分之内（且还要求
它排在前面，见 *cache-hostile ordering*）。

## token amplification factor

一次 run 的**累计计费 input** 除以该 run **最终一步的真实上下文**。度量的是"每步重发全部
历史"这个执行结构造成的重复计费。在 P4A 现网实测中位于 10–18 倍。

注意它**不是** cache 命中率的倒数——见 *billed input vs prefill*。

## billed input vs prefill（两种成本口径）

本项目最关键的区分。

| 口径 | 计的是什么 | 由谁决定 | 出现在哪 |
|---|---|---|---|
| **billed input** | 这一步送进去的完整 token 序列长度 | agent 的执行结构（轮数、上下文管理） | agent 侧 usage 日志、API 账单 |
| **actual prefill** | 这些 token 里真正需要重新计算 KV 的部分 | serving engine 的 prefix cache | serving engine 指标，**通常不回传给 agent** |

两者**互不蕴含**。在 P4A 上同时观测到 serving 侧命中率 89% 与 agent 日志 cache 字段全 0。
后果：**未经 cache 折算的 token 计数不能用来比较不同执行范式**，因为它对步数多的风格
高估更严重。详见 [`solution/cache-accounting.md`](solution/cache-accounting.md)。

## cross-run prefix reuse

本项目真正关心的复用层次。需要与另外两层区分开——三者名字相近但省的是完全不同的东西：

| 层次 | 复用对象 | 省下的是 |
|---|---|---|
| **算子/中间产物前缀复用**（intra-run，语义层） | 已物化的中间结果 | executor 的重算时间，**与 KV 无关** |
| **KV / token 前缀复用**（intra-run） | 同一 run 内 append-only 的历史 | 本 run 内后续步的 prefill |
| **跨 run 前缀复用** | 多个独立 run 之间逐字相同的前缀 | 整个语料上每个 run 的 prefill |

第一层与本项目**无关**，只是名字相同；混淆这两层是引用外部工作时最容易犯的错误。

## cache-hostile ordering

一段跨 run 逐字相同的内容被排在 per-run 可变内容**之后**的 prompt 结构。此时该内容对
跨 run 前缀复用的贡献为零，尽管它"完全相同"。修复是纯重排，代价为零。

推论：**共享前缀的可用量由排序决定，不由相同内容的总量决定。**

## agency level / autonomy ladder

四级阶梯，是 open question 的实验骨架：Static Workflow / Workflow + LLM Nodes /
Workflow + Repair Agent / Full ReAct-Coding Agent。定义见
[`solution/autonomy-ladder.md`](solution/autonomy-ladder.md)。

## behavioral statistics（行为统计）

指实际交互轮数分布、repair 触发率、回溯/重读发生频率、开放工具调用比例这一组量。

本项目把它定为 autonomy 对比实验的**一等指标**，理由是：没有这组统计，"这个 agent 确实
用上了它的自主性"这句话在实验内部无法验证——一个 full-agent 臂完全可能实际上退化成了
一轮直出的 workflow，而只看最终质量指标看不出来。这条是从外部工作的方法论缺口反推出来的
（staged 来源，见 C06）。

## staged evidence

本 artifact 特有的证据状态。指由 agent 生成、**尚未经人工评审**的精读稿及其结论。

规则（出自 `references/README.md:38`）：精读稿落在 gitignored 的暂存区，必须经人工评审
确认结论可信之后，才决定以什么形式进入 `docs/`；未经评审的内容不进 `docs/`，`refs.bib`
的 note 字段也不写它的结论。

在本 artifact 中，staged 的 claim 被完整记录（因为它们是真实发生过的推理轨迹），但**不
承担论证责任、不可对外引用、不得用来支撑决定**。

## 先决核查项（blocking precheck）

一条被显式标记为"未做之前不得下结论"的核查。当前唯一一条是 **E01 阶段 1**：批量核实全部 session 的
`inputCacheRead` / `inputCacheCreation` 是否恒为 0。它阻塞的是**一切基于 cache 命中率的
结论**，不只是某一条 claim。
