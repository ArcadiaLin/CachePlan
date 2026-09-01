# Related Work

> **本层的特殊状态。** `references/refs.bib` 当前只有一条入库文献（RW03，`liu2026ara`），
> 它是**一手读原文核实**的，可引用。RW01 / RW02 两篇的条目已于 commit `c6ece08`
> （2026-09-01）被移除，其**精读稿存在但处于 gitignored 的暂存区，未经人工评审**，
> `docs/literature/` 的索引表仍是"尚无笔记"。
>
> 因此 RW01 / RW02 记录的是**已发生的调研轨迹**，不是本项目已采信的文献基础；两条都标了
> `Status: staged`，其结论不可引用。规则出处：`references/README.md:38`
> «未经评审的内容不进 `docs/`，`refs.bib` 的 note 字段也不写它的结论。»

---

## RW01 — DeepPrep: An LLM-Powered Agentic System for Autonomous Data Preparation

- **Citekey**: `fan2026deepprep`（**条目已从 refs.bib 移除**）
- **Venue**: PVLDB Vol. 19, No. 1 (2026); arXiv:2602.07371v1
- **Type**: `bounds` — 它给本项目的 open question 划了一条**边界条件**，而不是提供支持或反驳
- **Status**: **staged**，未评审
- **本地材料**: `references/papers/fan2026deepprep/`（gitignored）

**它对我们说了什么**
一个动作空间可闭合（31 个带类型签名的算子 + 1 个代码逃生口）、探索预算最多 5 轮、环境里
只有本地 Python executor 的系统，足以完成带 validation 与 repair 的端到端数据准备。其
workload 形态与本项目定义的五条判据高度吻合（固定 procedural knowledge、input-parallel
重复、validation/repair、结构化输出），只在"长程"一条上部分吻合——**长在产物上，不在
轨迹上**。

**它给出的边界**
它消掉的恰恰是 P4A 里最难消的部分：开放工具面、外部检索、模糊判定标准。所以它能证明
"动作空间可闭合时少量 agency 够用"，**不能**证明"动作空间不可闭合时也够用"。

**关于 cache：明确正交，不可作为 cache 证据引用**
它说的"复用"是**物化中间表的算子前缀复用**（省 executor 重算），与 KV 无关，只是名字相同。
跨 run 前缀复用一字未提，尽管其 31 算子文档 + 4-tag 协议对数千条 case 逐字相同。成本口径
是闭源 token 计价 vs 开源 GPU 墙钟折算，全文零 token 统计。**能引的只有它的沉默**——作为
"跨 run 复用是当前 agent 系统论文盲区"的方法论反例；借的是它的沉默，不是它的数字。

**支撑的 claim**: C04, C05, C06（全部 staged）

**Sources**
- ← `references/papers/fan2026deepprep/close-read.md:18` «**与 cache 主线正交，不可作为 cache 证据引用**：它说的「复用」是物化中间表的算子前缀复用（省 executor 重算，与 KV 无关），跨 run 前缀复用一字未提；成本口径是闭源 token 计价 vs 开源墙钟折算，全文零 token 统计。能引的只有它的沉默 —— 作为「跨 run 复用是当前 agent 系统论文盲区」的方法论反例。» [result, staged]
- ← `references/papers/fan2026deepprep/close-read.md:577` «**结论：中等强度的间接证据，方向上支持"这类 workload 不需要 full ReAct"，但不构成对 OQ 的回答。**» [result, staged]

---

## RW02 — LongDA: Benchmarking LLM Agents for Long-Document Data Analysis

- **Citekey**: `anon2026longda`（**条目已从 refs.bib 移除**）
- **Venue**: ACL 2026 submission, under review（匿名）
- **Type**: `baseline` + `bounds` — 提供了一个形态相近的 workload 与一整套基线数字，同时
  暴露了本项目必须避开的方法论坑
- **Status**: **staged**，未评审
- **本地材料**: `references/papers/anon2026longda/`（gitignored）

**它对我们说了什么**
三条方向一致的观察：显式推理零增益甚至负增益、粗粒度批量执行同时更省更准、七个工具里
只有关键词搜索一个承重。三条都指向"这类 workload 不需要深度自治"。

**它给出的边界**
**没有任何非 agent 基线**——11 个模型跑的全是同一个 ReAct 脚手架，因此它无法回答"这个
任务是否需要 agent"。三条观察全是跨模型的观察性对比，步数与模型能力完全共线，单次运行
无方差。只能作方向性旁证。

**它对本项目方法论的直接贡献（两条，都是负面教材）**
1. 它用**未经 cache 折算的原始 token 计数**论证效率并据此做缩放拟合。按其自身数据推算，
   最省与最费模型之间 20.8× 的 token 差距在完美前缀缓存下会压缩到约 1.65×。这直接催生了
   本项目的 *billed input vs prefill* 区分（C02）。
2. 它的 prompt 模板把跨 30 个 block 逐字相同的最长固定块排在了所有 per-block 变量之后
   （C08）——一个零成本可修复的 cache-hostile ordering 实例。

**作为第二 workload 的可行性**
受限。主要障碍：**数据未发布**（query 与 ground truth 未公开）、重复次数只有 30、输入
异构。可能可行的是取其中输入真正同构的子集当受控 micro-benchmark（见 E03）。

**支撑的 claim**: C02（外部佐证部分）、C07, C08, C09（staged）

**Sources**
- ← `references/papers/anon2026longda/close-read.md:24` «全部是跨模型的观察性对比、没有任何非 agent 基线、没有受控的 autonomy-level 消融、单次运行无方差、且全文不涉及 prompt cache 口径，因此只能作为中等偏弱的旁证，不能当作我们 open question 的答案；作为第二个 workload 则受限于数据未发布与 30 个 block 的小样本。» [result, staged]
- 全文不涉及 cache 概念 ← `references/papers/anon2026longda/close-read.md:391` «**论文全文没有出现 prompt cache / KV cache / prefix reuse 任何一个概念**（已 grep 确认）» [result, staged]

---

## RW03 — The Last Human-Written Paper: Agent-Native Research Artifacts

- **Citekey**: `liu2026ara`（**已入库**）
- **Venue**: arXiv:2604.24658v3 [cs.LG], 19 May 2026
- **Type**: `extends` — 它提供本项目 workload 类别的**第二个独立实例**，把研究对象从单实例
  扩成一个类别
- **Status**: **read（一手核实）**。本项目**第一篇可引用的文献**。
- **本地材料**: `references/papers/liu2026ara.pdf`（gitignored）；已编译 artifact
  `github.com/AmberLJC/ara-paperbench`；代码 `github.com/AmberLJC/Agent-Native-Research-Artifact`

**它对我们说了什么**
它的三个机制之一 **ARA Compiler（§4）** 把 legacy PDF 与仓库编译成结构化 artifact，而这个
编译器**是一份 agent skill，不是一条 pipeline**：~482 行自然语言规格载入 host agent 上下文，
驱动 coding agent 分四阶段执行，用 Seal Level 1 做在环校验、迭代 2–3 轮直到通过。这在
`workload-definition.md` 的五条判据上逐条落位——**这就是本项目定义的那类 workload，由另一个
团队独立造出来的**。支撑 C12。

**它最硬的一个数字**
23 篇 PaperBench + 7 篇 RE-Bench，**首轮通过率 0/30**，全部 artifact 都至少需要一轮反馈。
"validation-and-repair" 因此不是这类 workload 的边缘分支，而是**实测常态**——这一点比 P4A
一侧的证据更干净，因为它是在一个独立系统上、以通过率形式直接报出来的。

**它给出的边界**
- **规模是纲领而非事实。** "把 legacy 文献大规模导入"是它第 6 节的生态论述；已实际编译的
  是几十篇量级。引用时必须区分方向与已达成规模，否则就是把它的愿景当成它的结果。
- **它不回答 agency 是否必要。** 它没有做 autonomy-level 消融，把 agent 形态当作设计前提。
  因此它能证明"这个 workload 的**部署形态**是 agentic"，**不能**证明"agentic 是必要的"。
  这正是它与 OQ1 的关系：它让 OQ1 从**阻塞项**降为**背景问题**，而不是回答了 OQ1。
- **它不谈 cache。** 与 RW01 / RW02 一样，跨 run 前缀复用不在它的视野里——尽管它那 ~482 行
  规格对每一篇输入逐字相同，正是一个教科书式的 *a priori* 共享前缀。这使它成为 C07 "盲区"
  论述的**第三个独立佐证**，且是唯一一个可引用的。

**支撑的 claim**: C12（主）；C03（外部有效性）；C07（盲区论述的可引用佐证）

**Sources**
- 三机制之一 ← `references/papers/liu2026ara.pdf` p1 摘要 «an ARA Compiler that translates legacy PDFs and repos into ARAs» [input]
- 是 agent skill ← `references/papers/liu2026ara.pdf` p7 §4 «we introduce the ARA Compiler, an agent skill that translates any combination of legacy research sources into a» [input]
- 首轮通过率 ← `references/papers/liu2026ara.pdf` p44 «First-iteration pass rate is 0/30; all artifacts require at least one feedback round, confirming that Level 1 is a non-trivial filter rather than a rubber stamp.» [result]

---

## 经 RW01 / RW02 浮现、值得追但尚未取回的工作

这些名字出现在上面两篇精读稿的相关工作里。**本项目尚未读过任何一篇**，列在这里是为了
不丢线索，不代表任何判断。

| 工作 | 为什么值得追 | 依赖类型（预判） |
|---|---|---|
| Parrot / Text-to-Pipeline (Ge et al. 2025, arXiv:2505.15874) | RW01 里唯一的**外部** ADP benchmark，也是其优势收窄最明显的那个评测集 | `baseline` |
| MontePrep (Ge et al. 2025, arXiv:2509.17553) | MCTS 式的树搜索对照，与 RW01 的定位差异是"标量价值估计 vs 结构化执行反馈" | `bounds` |
| DeepAnalyze (Zhang et al. 2025, arXiv:2510.16872) | agentic 数据科学 LLM，与本项目的 workload 定义关系最近 | `imports` |
| Auto-Tables (Li et al. VLDB 2023) | 规则式逆算子合成，RW01 数据合成方法的直接前作 | `imports` |

**Sources**
- ← `references/papers/fan2026deepprep/close-read.md:688-692` «- **相关工作中值得追的**：»…«- Auto-Tables（Li et al. VLDB 2023）—— 规则式逆算子合成，本文数据合成的直接前作» [result, staged]

---

## 本项目自己的 related work 缺口（诚实记录）

本项目的核心主张涉及 prompt caching / KV cache reuse 的系统侧工作（如 prefix caching
调度、cache-aware serving、prompt 结构优化），而 **`refs.bib` 对这一整块仍然是空的**。
现有三篇没有一篇是 cache 方向的——RW01 明确正交，RW02 全文不出现 cache 概念，RW03 同样
不谈跨 run 前缀复用。

**三篇论文在 cache 上的共同沉默恰恰是 C07 的证据**，但沉默只能证明盲区存在，不能替代
本项目在这条主线上的文献工作。**本项目在自己的主线方向上仍未做过任何文献工作**——这是
当前 related work 层最大的缺口，优先级高于两篇 staged 论文的评审。
