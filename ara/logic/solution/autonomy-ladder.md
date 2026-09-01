# Autonomy Ladder

前置 open question 的实验骨架。四级执行范式，在**相同输入**上做 controlled comparison。

来源：`docs/open-questions/Necessity-of-agentic-execution.md`（Status: **OPEN**）

## 四级

| 级别 | 控制流 | LLM 的职责 | 何时启动自主判断 |
|---|---|---|---|
| **L1 Static Workflow** | 全固定 | 尽可能不用 | 从不 |
| **L2 Workflow + LLM Nodes** | 全固定 | 仅局部步骤（语义抽取、分类） | 从不——LLM 是节点，不是控制器 |
| **L3 Workflow + Repair Agent** | 以确定性 workflow 为主路径 | 局部步骤 + 修复 | 仅在 validation failure / 低置信度 / 异常输入时 |
| **L4 Full ReAct-Coding Agent** | 由 agent 决定 | 全部 | 始终 |

**Sources**
- ← `docs/open-questions/Necessity-of-agentic-execution.md:15` «例如，可以考虑 Static Workflow、Workflow + LLM Nodes、Workflow + Repair Agent 和 Full ReAct/Coding Agent 等不同执行范式。Static Workflow 尽可能将数据读取、解析、检索、合并和验证过程固定化；Workflow + LLM Nodes 保持整体控制流固定，仅将语义抽取、分类等局部步骤交给 LLM；Workflow + Repair Agent 以确定性 workflow 为主要执行路径，只在 validation failure、低置信度或异常输入出现时启动 Agent；Full ReAct/Coding Agent 则保留当前 P4A 的高度自主执行方式» [input]

## 哪些环节确定性、哪些不可约

open question 的核心论证是：P4A 的相当一部分操作**本身就是确定性的**，原则上可以用传统
workflow 可靠实现，并不天然需要 ReAct agent。

**确定性的**（可 workflow 化）：读取固定目录和输入文件、解析论文及引用信息、调用已有
extractor、按既定 schema 合并结果、执行 validator、根据明确的 validation error 重新运行
某个处理步骤。

**可能不可约的**（真正体现 agency 价值）：判断论文中哪些实体属于值得抽取的资源；区分
dataset / benchmark / model / tool / repository；判断现有论文与引用信息是否足够；决定是否
进一步搜索 GitHub / Hugging Face / arXiv；在多个候选之间做实体消歧；根据当前抽取结果主动
判断是否存在遗漏并重读论文相关区域。

**共同特点**：下一步操作无法完全由预定义的静态规则确定，而依赖于当前任务状态和之前获得的
observation。

**Sources**
- ← `docs/open-questions/Necessity-of-agentic-execution.md:9` «这些行为的共同特点是：下一步操作无法完全由预定义的静态规则确定，而依赖于当前任务状态和之前获得的 observation。» [input]

## 一个来自现网的经验信号（不是实验结论）

P4A 现网的实测行为本身对 L4 的必要性提出了两点疑问，但**它们是观察，不是对照实验**：

1. **多轮性对最终产出贡献有限**——实测 agent 最终也是一次 `Write` 写出完整结果，之后只做
   定点小修。这在行为上更接近 L3 而非 L4。
2. **agent 经常没有真正核验资源**——抽样 50 篇的 `checked_by` 分布中 `none`/`agent`/`paper`
   占大半。即被赋予的自主核验能力，实际上大面积没有被行使。

第 2 点尤其值得注意：它说明**"给了 agency" 与 "行使了 agency" 是两回事**，这正是把行为统计
定为一等指标的直接理由。

**Sources**
- 多轮性贡献有限 ← `experiments/p4a/refractor.md:21` «且 agent 的多轮性对最终产出贡献有限——实测 agent 最终也是一次 `Write` 写出完整 `agent_judgment.json`，之后只做定点小修。» [result]
- checked_by 分布 ← `experiments/p4a/refractor.md:255` «验证一致性：抽样 50 篇 `checked_by` 分布 `none` 142 / `github_mcp` 42 / `agent` 40 / `hf-readonly` 34 / 其他 12。» [result]
- agent 经常没核验 ← `experiments/p4a/refractor.md:23` «另一个实测问题：抽样 50 篇的资源 `checked_by` 分布中 `none`/`agent`/`paper` 占大半，**agent 经常没有真正核验资源**。» [result]

## 评测维度

不应只看最终任务质量。必须同时看：

- **质量**：resource extraction precision/recall、validation pass rate、hard-case success rate
- **成本**：tool calls、LLM token consumption、runtime、cost
- **结构**：trajectory length
- **行为统计**（本项目追加，见 `../concepts.md`）：实际交互轮数分布、repair 触发率、
  回溯/重读发生频率、开放工具调用比例

**且必须按任务难度与不确定性分层分析**，因为预期结果不是"Agent 优于 Workflow"或反之，
而是**不同任务区域需要不同程度的 agency**。

**Sources**
- ← `docs/open-questions/Necessity-of-agentic-execution.md:17` «尤其需要按照任务难度和不确定性进行分析，因为最终结果很可能不是简单的 “Agent 优于 Workflow” 或 “Workflow 优于 Agent”，而是不同任务区域需要不同程度的 agency。» [input]

## 两条出口

实验结果决定研究方向本身：

| 若 | 则 |
|---|---|
| Full ReAct 与强 workflow baseline 任务质量基本相当 | 当前以 agent planning 为核心的动机需重新审视；优化 ReAct 的 cache locality 可能是在优化一种非必要的执行方式；方向转向 **cache-aware execution of LLM workflows** |
| workflow 在简单任务上高效，但在困难/开放/不确定任务上明显掉 recall，而 agent 能靠动态规划与调查补回来 | 研究前提成立：**Agency is useful, but expensive. Cache-aware planning and execution aims to make necessary agency cheaper.** 问题升级为：能否在保留必要 agency 的任务质量收益的同时，组织 agent 的规划与执行以提高推理 cache locality |

**这个前置问题必须在设计任何具体的 cache-aware planning algorithm 或 scheduler 之前
得到实验验证。**

**Sources**
- ← `docs/open-questions/Necessity-of-agentic-execution.md:27` «**Can we preserve the task-quality benefits of necessary agency while organizing agent planning and execution to improve inference cache locality?**» [input]
- ← `docs/open-questions/Necessity-of-agentic-execution.md:29` «这一前置问题应当在设计具体的 cache-aware planning algorithm 或 scheduler 之前得到实验验证。» [input]

## 与外部工作的对齐（staged，不承担论证责任）

一个可直接借用的对照形式：**在 frozen 模型上只换执行范式、固定其他一切**。staged 来源
表明这种"只换结构"的对比能做出干净数字，且**很可能差距不大**——应预期到差距在个位数点
量级，并据此设计足够的样本量。

**Sources**
- ← `references/papers/fan2026deepprep/close-read.md:587` «**OQ 实验设计可以直接借它的对照 A 形式**：在 frozen 模型上，只换执行范式（Static Workflow / Workflow+LLM Nodes / Workflow+Repair / Full ReAct），固定其他一切。»«我们应该预期到"差距是个位数点"这个量级，并据此设计足够的样本量。» [result, staged]
