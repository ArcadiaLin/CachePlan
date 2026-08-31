## Open Question: Is Agentic Execution Necessary for Data-Intensive Workloads?

> 术语说明（2026-08-31 补记）：本文中的 "data-intensive workload" 指 **data-intensive / data-processing agent workflow**——Agent 依据固定 procedural knowledge（Skill），对大量不同输入反复执行同一个长程、工具增强、带 validation 与 repair 的 E2E workflow。它不是 "Data Analysis Agent"，任务语义是否属于"数据分析"与本问题无关。完整定义见 [`AGENTS.md` → Workload Under Study](../../AGENTS.md#workload-under-study)。

在进一步研究 **cache-aware planning and execution in LLM agents** 之前，一个需要优先验证的前置问题是：**对于 P4A 这类 data-intensive end-to-end processing task，是否真的有必要使用 Kimi Code 一类具有自主规划、工具调用和迭代执行能力的 ReAct/coding agent？**

目前 P4A 使用 coding agent，根据较长的 Skill 描述完成论文资源抽取任务。Agent 需要读取输入文件、理解论文内容、识别潜在资源、调用本地脚本及外部工具进行调查、生成结构化结果、执行 validation，并在必要时根据中间结果继续调查或修复输出。这种执行模式天然形成较长的 agent trajectory，也为 prompt/KV cache reuse 提供了潜在的优化空间。然而，这里存在一个更基础的问题：**这些 agentic behaviors 是否确实是完成任务所必需的，还是 P4A 实际上可以退化为一个固定的数据处理 workflow？**

P4A 中相当一部分操作本身具有明显的确定性，例如读取固定目录和输入文件、解析论文及引用信息、调用已有 extractor、按照既定 schema 合并结果、执行 validator，以及根据明确的 validation error 重新运行某个处理步骤。这些操作原则上可以通过传统 workflow 可靠实现，并不天然需要 ReAct agent。真正可能体现 agency 价值的部分，是任务中具有不确定性、开放性和动态决策需求的环节。例如，Agent 可能需要判断论文中哪些实体属于值得抽取的资源，区分 dataset、benchmark、model、tool、repository 等不同类型，判断现有论文和引用信息是否足够，决定是否进一步搜索 GitHub、Hugging Face、arXiv 或其他外部来源，在多个候选结果之间进行实体消歧，以及根据当前抽取结果主动判断是否存在遗漏并重新阅读论文的相关区域。这些行为的共同特点是：下一步操作无法完全由预定义的静态规则确定，而依赖于当前任务状态和之前获得的 observation。

因此，我们不应该预先假设 “ReAct agent 是 P4A 的正确执行方式”，而应该首先回答一个更基础的问题：

**How much agency is actually necessary for end-to-end data-intensive processing tasks such as P4A?**

一个直接的验证方法是构造不同自主程度的 P4A implementation，并在相同输入上进行比较。例如，可以考虑 Static Workflow、Workflow + LLM Nodes、Workflow + Repair Agent 和 Full ReAct/Coding Agent 等不同执行范式。Static Workflow 尽可能将数据读取、解析、检索、合并和验证过程固定化；Workflow + LLM Nodes 保持整体控制流固定，仅将语义抽取、分类等局部步骤交给 LLM；Workflow + Repair Agent 以确定性 workflow 为主要执行路径，只在 validation failure、低置信度或异常输入出现时启动 Agent；Full ReAct/Coding Agent 则保留当前 P4A 的高度自主执行方式，由 Agent 根据 Skill 和中间 observation 自主决定下一步操作。

比较这些方法时，不应只观察最终任务质量，还需要同时考虑 resource extraction precision/recall、validation pass rate、hard-case success rate、tool calls、LLM token consumption、runtime、cost 和 trajectory length 等指标。尤其需要按照任务难度和不确定性进行分析，因为最终结果很可能不是简单的 “Agent 优于 Workflow” 或 “Workflow 优于 Agent”，而是不同任务区域需要不同程度的 agency。例如，对于结构规则、信息充分的普通论文，固定 workflow 可能已经能够以更低成本获得与 Agent 相近的结果；而对于资源描述模糊、引用信息缺失、实体存在歧义、需要跨来源调查或需要根据中间结果反复修正判断的困难样本，Agent 的 adaptive reasoning 和动态工具调用能力可能产生明显收益。

如果实验发现 Full ReAct 与强 workflow baseline 在任务质量上基本相当，那么当前以 agent planning 为核心的研究动机就需要重新审视。这意味着 P4A 并不是一个必须依赖 agentic execution 的 workload，此时继续优化 ReAct execution 的 cache locality 可能是在优化一种并非必要的执行方式，研究方向可能更适合转向 **cache-aware execution of LLM workflows**。

相反，如果实验发现 workflow 在简单任务上具有较高效率，但在困难、开放或具有不确定性的任务上出现明显的 recall 或 task success 下降，而 ReAct/coding agent 能够通过动态规划、调查和修复显著提高这些任务的完成质量，那么就可以建立一个更扎实的研究前提：

**Agency is useful, but expensive. Cache-aware planning and execution aims to make necessary agency cheaper.**

在这种情况下，data-intensive workload 可以被理解为确定性处理与 adaptive reasoning 的混合体：部分执行区域可以稳定地 workflow 化，而另一部分区域由于任务不确定性必须保留 Agent 的自主决策能力。Agentic execution 所带来的动态 planning 和 trajectory diversity 随后又可能降低不同任务之间的 prompt-prefix/KV-cache locality。因此，进一步的研究问题可以从“如何提高 Agent 的 cache hit rate”提升为：

**Can we preserve the task-quality benefits of necessary agency while organizing agent planning and execution to improve inference cache locality?**

这一前置问题应当在设计具体的 cache-aware planning algorithm 或 scheduler 之前得到实验验证。P4A 可以首先作为 case study，通过不同 autonomy level 的执行范式进行 controlled comparison，判断其真正需要多少 agency。该结果随后将决定项目更适合继续研究 full ReAct agent 的 cache-aware planning，还是转向更一般的 hybrid workflow-agent execution / cache-aware LLM workflow optimization。换言之，当前阶段不应将 “Agent 是正确的执行抽象” 作为既定假设，而应将其本身视为一个需要实验回答的研究问题。