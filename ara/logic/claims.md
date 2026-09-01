# Claims

十二条 claim。

> **没有任何一条 claim 由本项目的实验支撑，因为本项目至今没有做过实验。**
> 标 `supported` 的几条，依据来自**继承观测**（P4A 工程过程产生的实测）、**代码事实**
> （可在本仓库内直接验证的代码路径）或**已入库文献**（一手核实的外部论文），
> 不是来自 E-series。每条 claim 的 **依据类型**
> 字段说明它站在哪一种依据上。见 [`inherited-observations.md`](inherited-observations.md)
> 与 [`experiments.md`](experiments.md)。

**Status 的含义**：

- `supported` — 有可核实的依据支撑，可在内部使用。**但请同时读 依据类型**：支撑它的
  可能是继承观测或代码事实，而非本项目的实验。
- `staged` — 来自 `references/papers/*/close-read.md`。**精读稿由 agent 生成、未经人工评审，
  且对应的 `refs.bib` 条目已于 commit `c6ece08` 被移除。** 这类 claim 在本 artifact 中
  只作为已记录的推理痕迹存在，**不可对外引用，也不得用来支撑任何决定**。
  规则出处：`references/README.md:38`。
- `hypothesis` — 尚无任何证据。

**依据类型 的含义**：

- `继承观测` — P4A 自身工程过程产生的实测，或本项目对其的一次性复核（B01/B02）。真实但
  无对照、无预注册，只能支撑动机与量级。
- `代码事实` — 通过阅读本仓库代码即可验证的断言，不需要实验。
- `方法论约定` — 定义/取舍层面的 claim，其"正确性"体现在是否让后续实验指向正确的变量。
- `已入库文献` — 在 `references/refs.bib` 中有条目、且**由本项目一手读原文核实**的外部论文。
  与 `staged 文献` 的区别是核实路径，不是权威性：这里的每个数字都能回到 PDF 的页码与小节
  逐字复核。它支撑的是"外部世界确实如此"，仍**不能**支撑"本项目的方法有效"。
- `staged 文献` — 见上。
- `无` — 假设。

---

## C01 — ReAct 的成本由轮数驱动，而不是由最终上下文规模驱动

**Statement**
在每步重发全部历史的执行结构下，一次任务的累计计费 input 随交互轮数呈**二次累积**，
而任务真正需要的信息量只由最终上下文决定。因此这类执行的成本主要是**执行结构的函数，
而不是任务复杂度的函数**——同一个任务，多绕几轮就要多付一倍钱，而产出并不因此变多。

**Conditions**
测于单一 workload（P4A 论文资源抽取）、单一 agent runtime（kimi-code CLI）、单一模型
（`qwen3.6-35b-a3b`）。未测：其他 runtime 是否做上下文裁剪/压缩；轮数与任务难度是否
本身相关（若难任务天然轮数多，则"结构的函数"与"难度的函数"部分共线，本证据无法分离）。

**Falsification criteria**
在同一 workload 上把交互轮数压到 1/k 而保持最终产出等价，若累计计费 input 不下降到
接近 1/k 量级，则本 claim 的机制描述错误。反向证伪：若在轮数分布上做分层，发现放大倍数
与轮数无关而与论文长度相关，则成本主因不是执行结构。

**Evidence basis**
现网中位：累计计费 input ~140 万 token vs 最终真实上下文 8–11 万 token，放大 10–18 倍；
单条 session 独立复现给出 1,893,916 / 121,499 = 15.6x，落在该区间内。同一实测还指出
agent 的多轮性对最终产出贡献有限——最终仍是一次 `Write` 写出完整结果，之后只做定点小修。

**Proof**: B01（n=1 复核）+ `refractor.md` 的抽样（n=80 token / n=3 逐事件解剖）

**待做**: E01 阶段 2 把它扩到全量分布，并检验放大倍数究竟与轮数还是与论文长度相关。

**依据类型**: 继承观测 —— 数字真实，但产自 P4A 的工程过程，无对照、无预注册。

**Status**: supported

**Sources**
- 140 万 / 8–11 万 / 10–18 倍 ← `experiments/p4a/refractor.md:253` «token：抽样 80 篇 `agent_usage.json`，累计计费 input 中位 140 万；3 个会话逐事件解剖显示最终真实上下文仅 8–11 万，放大 10–18 倍来自 ReAct 每步重发历史。» [result]
- 归因于每步重发历史 ← `experiments/p4a/refractor.md:21` «慢和贵的根因不是某个工具（外部核验单次仅几百 token、几秒），而是 **ReAct 循环每步重发全部历史**：input 计费被放大 10–18 倍；且 agent 的多轮性对最终产出贡献有限——实测 agent 最终也是一次 `Write` 写出完整 `agent_judgment.json`，之后只做定点小修。» [result]
- 1,893,916 / 121,499 / 15.6x ← `docs/experiments/p4a.md:20` «19 轮对话，累计计费 input 1,893,916 token，最终真实上下文 121,499 token，放大倍数 15.6x，与 `refractor.md` 里给出的整体统计一致。» [result]

---

## C02 — 计费 token 与 KV 复用是两个互不蕴含的量，因此日志 token 数不是有效的成本指标

**Statement**
"这一步送进去多少 token" 与 "这些 token 里有多少被 serving 端复用了 KV" 是两条独立的
账。前者由 agent 的执行结构决定并被计费口径记录，后者由 serving engine 决定且**通常不
出现在 agent 侧日志里**。因此把 agent 日志的 input token 计数当成成本代理，会系统性地
**高估步数多的执行风格**，且高估幅度与该风格的步数正相关——这使得未经 cache 折算的
token 数无法用于比较不同执行范式。

**Conditions**
在 P4A 这一侧，两个量的分离是**观测到的**（serving 报 89% 命中，agent 日志报 0）；但
"日志字段恒为 0" 只在一条 session 上验证过（B01，n=1），是否为全量普遍现象**未核实**
（E01 阶段 1）。若发现字段非恒零，则本 claim 的前半部分（分离存在）仍然成立，但 P4A 这个具体实例
会从"字段未被采集"改写为"字段可用"，结论方向不变而证据来源改变。

**Falsification criteria**
若能证明某个 agent runtime 的计费 input 字段本身已按 cache 命中折算（即计费 token 数
随 serving 侧命中率变化），则在该 runtime 下两个量不再独立，本 claim 不适用于它。

**Evidence basis**
同一批 P4A 运行中，vLLM 侧 prefix cache 命中率 89%、KV 占用 2.8%、0 抢占；而抽样
session 的全部 19 条 `usage.record` 的 `inputCacheRead` / `inputCacheCreation` 均为 0。
两个数字在同一个系统里同时成立，只能解释为两条独立的账。

一个**方向一致的外部观察**（staged，不承担论证责任）：LongDA 精读稿指出，该 benchmark
用未经 cache 折算的原始 token 计数论证效率并据此做缩放拟合，而按其自身数据推算，
最省与最费两个模型之间 20.8× 的输入 token 差距在完美前缀缓存下会压缩到约 1.65×。

**Proof**: B01（口径分离的观测，n=1）

**待做**: E01 阶段 1 —— 这是本项目的**先决核查闸门**，在它完成前不得基于 cache 命中率
下任何结论。

**依据类型**: 继承观测（P4A 侧的分离现象）+ staged 文献（外部佐证，不承担论证责任）

**Status**: supported（P4A 侧的分离现象）；全量普遍性**未核实**；外部佐证部分 staged

**Sources**
- 89% / 2.8% / 0 抢占 ← `experiments/p4a/refractor.md:256` «vLLM：`qwen3.6-35b-a3b`，max_model_len 262144；prefix cache 命中率 89%，KV 占用 2.8%，0 抢占。» [result]
- 日志字段恒为 0 且未核实 ← `docs/experiments/p4a.md:21` «该 session 全部 19 条 `usage.record` 的 `inputCacheRead` / `inputCacheCreation` 均为 0——尚未确认是全量数据的普遍现象还是这条样本的个例，见第 4 节的先决核查项。» [result]
- 20.8× → 1.65× ← `references/papers/anon2026longda/close-read.md:503` «**Table 2 里 GPT-5 与 GLM-4.7 之间 20.8× 的输入 token 差距，在完美前缀缓存下会压缩到约 1.65×。**» [result, staged]
- token 列不是有效成本指标 ← `references/papers/anon2026longda/close-read.md:505` «**Table 2 的 token 列在没有 cache 口径的前提下不是一个有效的成本指标**» [result, staged]

---

## C03 — workload 的可优化性由"过程固定 + 重复次数"决定，与任务语义无关

**Statement**
决定一类 agent workload 有多少 cache 复用空间的，是**同一份 procedural knowledge 被
重复执行了多少次**，不是这些执行在语义上做什么。按任务语义给 workload 命名
（"data analysis agent"）会把注意力引向一个与可优化性无关的属性；按"固定过程 +
input-parallel 重复"命名才对齐到真正的自变量。

**Conditions**
这是一条方法论/定义层面的 claim，其"正确性"体现在它是否让后续实验设计指向正确的变量，
而不是体现在某个测量值上。它假定 cache 复用的收益主要来自跨 run 的共享前缀；若某个
workload 的主要收益来自 run 内部（如极长单次上下文），本 claim 的取舍依据不适用。

**Falsification criteria**
构造两个任务语义相同、但过程固定度/重复次数差异很大的 workload，若它们的可达 cache
复用率相近，则"重复次数"不是主导变量，本 claim 的取舍就是错的。

**Evidence basis**
`AGENTS.md` 给出五条判据（fixed procedural knowledge / input-parallel repetition /
long-horizon tool-augmented execution / validation and repair / structured end-to-end
output），并明确说明是"固定的过程被重复很多次"产生了 *a priori* 共享前缀，而
"data analysis agent" 这个叫法强调的是任务语义。此更名已在 `AGENTS.md`、
`docs/PROGRESS.md`、open-question 文档三处对齐。

**Proof**: E02（本 claim 决定 E02 的分层维度：按过程固定度而非任务语义分层）

**依据类型**: 方法论约定 —— 这不是一条经验命题，它的价值在于让后续实验指向正确的自变量。

**Status**: supported（作为已收敛的 decision）

**Sources**
- 五条判据 ← `AGENTS.md:33-37` «- **fixed procedural knowledge** — a long, stable Skill / agent prompt that encodes the same procedure for every input;»…«- **structured end-to-end output** — the deliverable is a structured record, not a conversational answer.» [input]
- 命名理由 ← `AGENTS.md:39` «Terms like "data analysis agent" put the emphasis on the wrong property (the semantics of the task) rather than on the repetition of a fixed procedure, which is the property the research actually depends on.» [input]
- 三处已对齐 ← `docs/PROGRESS.md:32` «已把研究 workload 定名为 data-intensive / data-processing agent workflows（见上节），`AGENTS.md`、本文档、open-question 文档三处术语已对齐。» [input]

---

## C04 — 在开放性被消除的动作空间里，极窄的 agency 信封足以完成带 validation/repair 的 E2E 流程

**Statement**
当一个数据处理任务的动作空间可以被闭合成带类型签名的算子集合、且终止条件是可判定谓词时，
完成"探索—失败—修正—收敛"这整套行为所需的自主性，可以窄到只剩两个局部决策：
**回溯点的选择** 与 **动作及其参数的提议**。其余环节（状态维护、执行、错误记录、路径抽取、
终止判定）都是确定性程序逻辑。这意味着 agency 的需求量是**动作空间开放程度的函数**，
而不是任务长度或 validation 复杂度的函数。

**Conditions**
证据来自一个动作空间**可闭合**的领域（表数据准备：31 个算子 + 1 个代码逃生口，探索预算
最多 5 轮，环境里只有一个本地 Python executor，无外部检索）。P4A 的动作空间**不可闭合**
（shell、脚本、GitHub/HuggingFace/arXiv 检索），因此本 claim **不能外推到 P4A**——它
恰好消掉了 P4A 里最难消的那部分。此外该来源从未报告实际交互轮数、回溯频率或代码逃生口
的使用比例，因此"树式回溯确实被用上了"在其内部无法验证。

**Falsification criteria**
在一个动作空间可闭合的任务上，构造只保留这两个局部决策的实现，若它在困难样本上相对
full agent 出现显著的 recall/成功率下降，则"两个局部决策足够"为假。

**Evidence basis**
见 `evidence/tables/table05-deepprep-structure-vs-training.md`。

**Proof**: E04

**依据类型**: staged 文献

**Status**: **staged** — 未评审，不可引用

**Sources**
- agency 只落在两个局部决策上 ← `references/papers/fan2026deepprep/close-read.md:510` «**树式推理的"树"是一个固定的控制结构，不是 agency；agency 只落在"回溯点选择"和"算子/参数提议"这两个局部决策上。**» [result, staged]
- 5 轮预算与工具面 ← `references/papers/fan2026deepprep/close-read.md:451` «**最多 5 轮探索**（page 10）。在 pipeline 长度可达 28 的任务上只给 5 轮 plan/expand/execute» [result, staged]
- 不可外推的理由 ← `references/papers/fan2026deepprep/close-read.md:583` «所以它能证明"在动作空间可闭合时，少量 agency 够用"，不能证明"在动作空间不可闭合时也够用"。» [result, staged]

---

## C05 — 收益的大头在"更固定、更专门"，不在"更自主"

**Statement**
在同一任务上把执行范式从线性 agent 换成带回溯的结构化 agent，与把同一套固定协议拿去做
专门化（针对该协议训练模型），两者的收益不在一个量级：前者是个位数点，后者是两位数点。
这说明**执行结构的自主程度不是这类任务的主要杠杆**，把流程固定下来并针对它专门化才是。

**Conditions**
证据来自单一领域（表数据准备）、单一数据集族，且"专门化"的具体手段是训练模型——本项目
的工作假设 A1 是 frozen 模型，因此**这条收益在本项目的设定下不可直接兑现**。在 frozen
设定下能借到的只有那个个位数的结构收益。分解本身也是从两组数字外推的，来源论文并未把它
组织成对照实验，也没给方差；结构与专门化之间存在交互，不能严格线性拆分。

**Falsification criteria**
在 frozen 模型上做同一对照，若结构变更的收益与专门化的收益量级相当，则本 claim 的量级
断言为假。

**Evidence basis**
见 `evidence/tables/table05-deepprep-structure-vs-training.md`。另有一条方向翻转的观察：
在强 backbone 上零 agency 的一次性代码生成可以打赢线性 agent，而在弱 backbone 上完全
反过来——即"agency 是否值得"是 backbone 能力的函数，不是恒定答案。

**Proof**: E04

**依据类型**: staged 文献

**Status**: **staged** — 未评审，不可引用

**Sources**
- 结构 +4.73 vs 训练 +26.79 ← `references/papers/fan2026deepprep/close-read.md:698` «**在 frozen 模型上把线性 agent 升级成带回溯的树式 agent 只值 +4.73（gpt-5-mini 上 67.03 → 71.76），而把同一套固定协议拿去做专门训练值 +26.79（Qwen3-14B 上 ReAct 40.39 → DeepPrep 67.18）。收益的大头不在"更自主"，而在"更固定、更专门"。**» [result, staged]
- 粗略分解与其不确定性 ← `references/papers/fan2026deepprep/close-read.md:539` «**26.79 里大约只有 4~5 点归于 agentic 结构，其余 22 点左右归于"针对这个固定协议做专门训练"。**（这是一个粗略分解 —— 结构与训练之间存在交互，小模型可能更依赖结构约束才能被训起来，所以不能严格线性拆分。» [result, staged]
- 方向随 backbone 翻转 ← `references/papers/fan2026deepprep/close-read.md:543` «**"加上 agency 是否有帮助"在这里是 backbone 能力的函数，而不是恒定为真。**» [result, staged]

---

## C06 — agentic 行为不是默认状态，缺乏专门激励时会自发退化为 workflow

**Statement**
探索与回溯不是 agent 的自然倾向，而是必须被专门维持的性质。当只按最终对错给信号时，
agent 会自发学会"少折腾、跑通就交卷"——**完成率反而上升、准确率下降**。这把
"这类任务需不需要 agency" 和 "agency 会不会自己出现" 分成了两个问题，而后者的答案偏否定。
其直接后果是：**一个没有被专门激励去 repair 的 agent，行为上会自动接近 workflow**，
因此在任何 autonomy 对照实验里，"full agent" 这一臂的实际自主程度必须被测量而不是假定。

**Conditions**
观测来自训练设定下的奖励消融（稀疏 outcome-only vs 混合奖励），单一 backbone、单次运行、
无方差。"保守行为"是来源论文的解释，其未直接统计回溯次数或分支数。是否在 frozen 模型的
prompt-only 设定下也成立，**未知**。

**Falsification criteria**
在 frozen 模型上给同一 agent 两种提示（一种明确要求验证与修复，一种不要求），若两者的
repair 触发率与回溯频率无显著差异，则"agency 需要专门维持"在 prompt-only 设定下为假。

**Evidence basis**
见 `evidence/tables/table06-deepprep-reward-ablation.md`。

**Proof**: E04

**依据类型**: staged 文献

**Status**: **staged** — 未评审，不可引用

**Sources**
- 完成率升、准确率降 ← `references/papers/fan2026deepprep/close-read.md:700` «Table 3b 显示，只用 outcome reward 训练时，agent 的**完成率反而最高（98.71%）而准确率最低（61.85）** —— 它自发学会了"少探索、少回溯、跑通就交卷"。**agency 不是默认状态，是要专门花训练代价维持的性质。**» [result, staged]
- 对实验设计的推论 ← `references/papers/fan2026deepprep/close-read.md:516` «**在没有额外压力时，一个 agent 会自发地退化成 workflow。要维持 agentic 行为，必须付出训练代价（这里是 partial reward + LLM-judge process reward）。**» [result, staged]

---

## C07 — 在文档密集型分析任务上，增加推理深度与增加步数都不换来准确率

**Statement**
当任务的瓶颈是"在长文档里定位到那几个关键决策"而不是逻辑推理时，两种通常被当作能力
代理的东西都失效：**打开显式推理会让准确率持平甚至下降而墙钟时间大涨**；**步数更多的
执行风格准确率更低**。这指向一个与直觉相反的结构：在这类任务上，效率与效果**同向**而
非权衡——把多个子任务合并进一次更粗粒度的执行，同时更省也更准。

**Conditions**
全部是**跨模型的观察性对比，没有一条是受控实验**：步数与模型能力完全共线（没有固定模型
只改执行粒度的实验），单次运行无方差（−0.25pp 这类差值不可解读）。且该来源**没有任何
非 agent 基线**——11 个模型跑的是同一个 ReAct 脚手架，因此它无法回答"这个任务是否需要
agent"。只能作方向性旁证。

**Falsification criteria**
固定模型、只改执行粒度（把 k 次细粒度工具调用合并成 1 次批量执行），若准确率不升反降，
则"粗粒度批量执行同时更省更准"为假。

**Evidence basis**
见 `evidence/tables/table07-longda-main-results.md` 与
`evidence/tables/table08-longda-tool-ablation.md`。

**Proof**: E05

**依据类型**: staged 文献

**Status**: **staged** — 未评审，不可引用

**Sources**
- 三条一致但均非受控 ← `references/papers/anon2026longda/close-read.md:451` «三条证据一致指向"这类 workload 不需要深度自治"——推理深度没用、步数越多越差、工具面可以收窄——但**没有一条是受控实验**，且都缺方差（单次运行，−0.25pp 这种差值不可解读）。**能作为方向性旁证，不能作为答案。**» [result, staged]
- 无非 agent 基线 ← `references/papers/anon2026longda/close-read.md:411` «**先说最重要的结论：没有非 agent 对照。**» [result, staged]
- 效率与效果同向 ← `references/papers/anon2026longda/close-read.md:249` «GPT-5 用 **5.50** 平均步数、**6.40M** 总 token、**3.58h** 拿到最高的 69.16%；GLM-4.7 用 **81.17** 步、**120.01M** token、**8.42h** 只拿到 19.18%。» [result, staged]
- 共线，不可当证据 ← `references/papers/anon2026longda/close-read.md:445` «步数与模型能力**完全共线**——GPT-5 既批量执行、又更聪明，没有任何实验固定模型只改执行粒度。» [result, staged]

---

## C08 — prompt 模板把跨 run 不变的部分排在可变部分之后，是一个零成本可修复的结构性缺陷

**Statement**
共享前缀的可用量不由"有多少内容是相同的"决定，而由"相同的内容有没有排在最前面"决定。
一段在所有 run 之间**逐字相同**的 procedural knowledge，只要被放在 per-run 变量之后，
它对跨 run 前缀复用的贡献就是零。修复是纯粹的重排、代价为零。这类缺陷的存在本身比它的
token 收益更有信息量：它说明 prompt 结构的 cache 友好性目前不在这个社区的默认视野里。

**Conditions**
观测到的实例只有一个（一篇 benchmark 论文的 prompt 模板），且其固定块很短，绝对收益
可忽略。"这是普遍的设计习惯"是从单个实例外推的，**未做任何跨论文的模板结构调查**。
此外该实例的重复次数只有 30，量级本身就小。

**Falsification criteria**
系统地调查一批 agent 系统/benchmark 的 prompt 模板，若多数已经把不变块前置，则
"这是社区的普遍盲区"为假（而"排序决定可用前缀"这条机制仍然成立，因为它是定义性的）。

**Evidence basis**
该模板的顺序为：`Task`（固定，约 15 token）→ `Survey`/`qa_block`/`Data Files`/`Doc Files`
（全部 per-block 可变，且 `qa_block` 最长）→ `Instructions`（固定，5 节 17 条，约
250–300 token，是最长的固定块）。跨 30 个 block 的朴素共享前缀因此只有第一行。真实 trace
逐字印证了这个顺序。

**Proof**: E03

**依据类型**: staged 文献

**Status**: **staged** — 未评审，不可引用

**Sources**
- 模板顺序 cache-hostile ← `references/papers/anon2026longda/close-read.md:509` «这里有一个很干净的发现——**Fig. 9 的模板顺序是 cache-hostile 的**» [result, staged]
- 纯粹是位置放错 ← `references/papers/anon2026longda/close-read.md:522` «**这里连措辞都没变，纯粹是位置放错了**。修复是平凡的（把 Instructions 提到 `{survey}` 之前），代价为零» [result, staged]
- 收益可忽略但暴露设计习惯 ← `references/papers/anon2026longda/close-read.md:524` «真正有价值的不是这几百个 token，而是**这个模板顺序暴露的设计习惯**——在一个把"上下文极长"当作卖点的 benchmark 里，作者仍然把不变量放在了变量之后。» [result, staged]

---

## C09 — 把 agentic 的发现步骤固化成前缀知识，同时是 cache 优化与 agency 削减

**Statement**
当一批 run 共享同一份底层材料时，agent 在每个 run 里重复做的"发现"工作（找到哪个变量、
哪个权重、哪个字段）既是 agency 的消耗，也是前缀发散的来源。把这份发现结果物化成
prompt 前部的固定知识，**一次动作同时降低两者**：跨 run 前缀变长（cache 收益），并且
原本需要自主判断的步骤被降级为查表（agency 削减）。这意味着本项目的两条线索——cache
复用与 agency 必要性——在实现层面可能不是两个独立的优化目标，而是同一个设计动作的两个
侧面。

**Conditions**
**目前没有任何测量支持这条。** 它是从一个具体场景外推出来的设计推想：某数据集中 9 个
run 共用一份 57k token 的文档语料，同样的变量发现被重复了 9 次。是否真的能同时改善两者、
以及固化会不会损害对未见输入的适应性，**完全未测**。

**Falsification criteria**
在一个受控设定下把发现步骤固化成前缀，若 (a) cache 命中率提升但任务质量下降，或
(b) 任务质量保持但前缀复用无提升，则"同一个动作同时改善两者"为假。任一条成立即证伪。

**Evidence basis**
无自有证据。启发来源见 Sources。

**Proof**: E03（本 claim 是 E03 的设计假设，尚待该实验产生第一份证据）

**依据类型**: 无 —— 这是本 artifact 里唯一一条纯假设。

**Status**: **hypothesis** — 无证据

**Sources**
- 启发来源 ← `references/papers/anon2026longda/close-read.md:526` «这既是 cache 优化，也正好是"把 agentic 的发现步骤降级为固定知识"的一次实例——**cache-aware 与 agency-reduction 在这里是同一个动作**» [result, staged]
- 重复发现的规模 ← `references/papers/anon2026longda/close-read.md:467` «最大的簇是 **NHANES：9 个 block、99 条 query（占全部 query 的 19.6%）共用同一份 57k token 的文档语料**»«**同样的变量发现工作被重复了 9 次**。» [result, staged]

---

## C10 — 通过工具读入的固定知识对跨 run 前缀复用贡献为零，无论它有多大、多相同

**Statement**
当 agent runtime 让模型**用工具去读**那份固定的 procedural knowledge，而不是把它内联进
prompt 前部时，这份知识虽然跨 run 逐字相同，但它在上下文里的位置必然落在触发该次读取的
per-run 内容之后。因此它对跨 run 前缀复用的贡献是 **0**——共享前缀在第一个 per-run
token 处就断了。这说明 C08 描述的 cache-hostile ordering 不只是模板排版失误，还是
**"让 agent 自己去取知识"这种设计的必然结果**：把知识变成一个动作，就把它挪到了变量之后。

**Conditions**
观测自本仓库自有的 P4A v1 实现（kimi-code CLI + `launch_kimi_layer4.py`）。结论依赖上下文
是 append-only 且工具结果按发生顺序入列——若某 runtime 会重排消息或把常读文件提升到系统
提示，则不适用。**本 claim 是从代码路径推断的，没有对实际 token 序列做过测量**——
`data/raw/kimi-p4a-sessions/` 里的 `context.append_message` / `tool.result` 事件可以直接
验证它，尚未做（**E01 阶段 3 就是为此设计的**）。

**Falsification criteria**
从 session 日志重建任意两个 run 的实际 token 序列，若二者的公共前缀长度已经覆盖了 Skill
内容，则本 claim 为假（说明该 runtime 做了本 claim 未预期的提升或重排）。

**Evidence basis**
v1 的编排器传给 CLI 的是一句指向**逐篇生成**的 `agent_prompt.md` 的指令，再由 agent 按
prompt 里的 skill 名去读 `SKILL.md`。那份 MinerU Skill 是 460 行 / 21,014 字节，是 P4A
里最大的固定前缀候选。详见 `../src/artifacts.md` §2。

**Proof**: 代码路径（见 Sources，可在本仓库内直接核实）

**待做**: E01 阶段 3（从日志重建 token 序列，实测共享前缀断点）、E02（L4 臂的前缀测量）。
E01 阶段 3 同时是本 claim 的证伪通道。

**依据类型**: 代码事实 —— 不需要实验即可核实，但"实际 token 序列确实如此"尚未实测。

**Status**: supported（代码路径已确证；token 序列未实测）

**Sources**
- 传路径而非内联 ← `experiments/p4a/src/extract/layer4/launch_kimi_layer4.py:423` «"Read this UTF-8 prompt file and follow its instructions exactly:\n"» [input]
- 传的是逐篇路径 ← `experiments/p4a/src/extract/layer4/launch_kimi_layer4.py:424` «f"{repo_relative(prompt_path)}\n\n"» [input]
- 让模型按名字去找 skill ← `experiments/p4a/src/extract/layer4/launch_kimi_layer4.py:425` «"Use the named skill from the prompt. Construct or repair agent_judgment.json, "» [input]
- 让 agent 自己读 skill 文件 ← `experiments/p4a/src/extract/layer4/launch_kimi_layer4.py:555-556` «- Before repairing, read and follow this skill file:\n  skill/paper-mineru-resource-extract/SKILL.md» [input]
- `agent_prompt.md` 逐篇生成 ← `experiments/p4a/src/extract/layer4/prepare_mineru_layer4.py:319` «(output_dir / "agent_prompt.md").write_text(build_agent_prompt(bundle), encoding="utf-8")» [input]

---

## C11 — 跨 run 前缀设计已被自发采用，但采用它的实现同样不测量它

**Statement**
"把静态块保持字节级一致以吃 prefix cache" 这个手段，不需要本项目去发明——它已经被工程
直觉独立采用了。但采用它的实现**只采集 token 计数、不采集任何 cache 字段**。因此
**采用与验证之间存在系统性缺口**：这个杠杆有多大，至今没有数字，*即使在已经使用这个杠杆
的系统里*。这把 C07 的"盲区"论述从"没人想到"精确成了更强的一条——**想到了、做了、依然
没测**，说明缺的不是意识而是**口径**（见 C02）。

**Conditions**
观测到一个实例（本仓库的 `layer4_v2`）。"这是普遍现象"是从这一个实例加上两篇 staged
来源的沉默外推的，**未做任何跨项目调查**。另需注意：该实现有一份 200 篇评估报告，但
**报告本身不在本仓库内**，本 artifact 无法核实其中是否含 cache 测量——因此"没测"这个
断言在报告这一侧是**未核实的**。

**Falsification criteria**
取回 `reports/layer4_v2_eval200.md`，若其中含前缀复用率或 cache 命中率的测量，则本 claim
的后半部分为假。

**Evidence basis**
`prompts.py` 的模块 docstring 明确写了该设计意图；`llm_client.py` 的 usage 采集只有
`prompt_tokens` / `completion_tokens` 两个字段。详见 `../src/artifacts.md` §3。

**Proof**: 代码事实（`prompts.py` 的设计意图 + `llm_client.py` 的采集字段，见 Sources）；
背景见 B02。

**待做**: 取回 `reports/layer4_v2_eval200.md` 核实其中是否含 cache 测量（本 claim 后半部分
的证伪通道）。

**依据类型**: 代码事实。注意 B02 的评估**结论**未核实，但本 claim 不依赖那份结论——
它只依赖"代码里写了这个意图"与"代码里没采集这个字段"两件可直接验证的事。

**Status**: supported（设计意图与采集字段已确证）；"报告中也没测"部分**未核实**

**Sources**
- 设计意图 ← `experiments/p4a/src/extract/layer4_v2/prompts.py:4-5` «The static blocks must stay byte-identical across papers so vLLM prefix\ncaching turns them into a shared cached prefix.» [input]
- 同一意图在 README ← `experiments/p4a/src/extract/layer4_v2/README.md:25` «- **两次 LLM 调用**都打到本地 vLLM（见 §5），字节级一致的静态前缀以吃 prefix cache。» [input]
- 采集字段 ← `experiments/p4a/src/extract/layer4_v2/llm_client.py:138-139` «"prompt_tokens": getattr(usage, "prompt_tokens", None),\n                "completion_tokens": getattr(usage, "completion_tokens", None),» [input]

---

## C12 — 这个 workload 形态是被独立收敛到的，不是 P4A 的偶然工程选择

**Statement**
当一个领域需要把大量既有材料机械地转成结构化产物时，独立团队会各自收敛到同一种执行
形态：把过程知识写成一份跨输入逐字不变的自然语言规格，装进通用 coding agent 的上下文，
对同构输入逐个重复执行，并用结构校验器闭环修复直到通过。这个形态因此不是某个项目的实现
偏好，而是该任务类别的**收敛解**——C03 界定的可优化空间（过程固定 × 重复次数）随之是一个
具有外部有效性的研究对象，而不是单实例的特例。

**Conditions**
两个独立实例（本仓库的 P4A；`liu2026ara` 的 ARA Compiler），且**两者同属科学文档处理、
同样跑在 coding-agent 基座上**——形态一致有可能来自这层共同基座而非任务类别本身，本 claim
无法区分这两种解释。"收敛"是从两例的形态一致性读出的，**未做跨项目普查**，也未检验该形态
在文档处理之外是否成立。另需注意两例的**规模差两个量级**：ARA Compiler 一侧已跑过的编译
是几十篇量级，"大规模导入 legacy 文献"在该论文中是纲领方向（§6 的 network 论述），
**不是已达成的规模**——引用时不可把纲领当作已发生的事实。

**Falsification criteria**
找到第三、第四个同类系统（固定过程 + 输入并行重复 + validation/repair）却采用了实质
不同的执行形态——例如把过程知识编译成确定性 pipeline 而不装进 agent 上下文，且任务质量
相当——则"收敛解"为假，两例的形态一致只是巧合。

**Evidence basis**
ARA Compiler 在 `workload-definition.md` 的五条判据上逐条对应：(1) 过程知识是一份
~482 行的自然语言规格，**载入 host agent 上下文**；(2) 输入并行重复，23 篇 PaperBench +
7 篇 RE-Bench；(3) 由 coding agent 多阶段、工具增强地执行；(4) validation-repair 是**常态
而非边缘**——首轮通过率 0/30，全部 artifact 都至少需要一轮反馈；(5) 产出是结构化 artifact
而非对话答案。判据 4 的这个数字比 P4A 一侧更干净：它把"带 repair 的 E2E workflow"从一个
设计选项变成了该 workload 的实测常态。

**Proof**: 已入库文献（`liu2026ara`，一手核实，逐字引用见 Sources）+ 代码事实（本机安装的
compiler skill 文件）。**无本项目实验**。

**依据类型**: 已入库文献。

**Status**: supported（五条判据的对应关系已逐条核实）；"收敛解"的普遍性仅有两个实例，
且共享基座这一混淆项未排除，见 Conditions

**Dependencies**: C03（本 claim 是 C03 的外部有效性检验，不是它的独立重复验证）

**Sources**
- 是 agent skill，不是 pipeline ← `references/papers/liu2026ara.pdf` p7 §4 «we introduce the ARA Compiler, an agent skill that translates any combination of legacy research sources into a» [input]
- 摘要层面的同一表述 ← `references/papers/liu2026ara.pdf` p1 摘要 «an ARA Compiler that translates legacy PDFs and repos into ARAs» [input]
- 由 coding agent 执行 + validation 闭环 ← `references/papers/liu2026ara.pdf` p7 Figure 7 caption «The ARA Compiler accepts any combination of research sources and guides a coding agent through four stages of top-down artifact compilation, iterating 2–3× with in-loop ARA Seal Level 1 validation until the output conforms to the protocol.» [input]
- 固定过程知识的规模与载入方式 ← `references/papers/liu2026ara.pdf` p29 §B.1 «The Compiler skill specification (∼482 lines of natural lan- guage) is structured into five sections. When loaded into a host agent’s context, it provides the full domain knowl- edge needed to produce a schema-conforming ARA.» [input]
- 输入并行重复的实际条数 + repair 是常态 ← `references/papers/liu2026ara.pdf` p44 §Compiler iteration counts «Each of the 23 PaperBench ARAs and the 7 RE-Bench ARAs converges to a Level- 1 pass within ≤3 iterations of the Compiler’s generate– validate–fix loop (§4). First-iteration pass rate is 0/30; all artifacts require at least one feedback round» [result]
- 自然语言规格把通用 agent 专门化 ← `references/papers/liu2026ara.pdf` p30 §C «it is a self-contained natural-language specification that turns a general-purpose coding agent into a domain-specialized system» [input]
- 本机安装的同一 skill，其 validate→fix 闭环 ← `~/.claude/skills/compiler/SKILL.md:58` «4. COVERAGE CHECK loop (max 3 rounds): re-read source → diff against ARA → patch gaps» [input]
- 同上，收敛轮数 ← `~/.claude/skills/compiler/SKILL.md:288` «Typically converges in 2–3 rounds.» [input]

> PDF 引文按页码 + 小节定位（PDF 无稳定行号）。引号内为 PyMuPDF 抽取的原文，
> **保留了跨行断字符**（如 `lan- guage`、`Level- 1`）以便逐字复核。
