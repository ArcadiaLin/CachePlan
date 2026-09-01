# Inherited Observations

**这个文件里的东西不是本项目的实验结果。**

它们是 P4A 这个**历史项目**在自己的工程过程中产生的记录，以及本项目为了确认"这个问题是
真的"而对那些记录做的一次性复核。它们的作用是**说明问题为什么值得做**，不是回答本项目的
任何研究问题。

区分它们与 [`experiments.md`](experiments.md) 里的 E-series 是必要的，因为二者的证据地位
完全不同：

| | 继承观测（B-series，本文件） | 本项目实验（E-series） |
|---|---|---|
| 谁做的 | P4A 的工程过程 / 一次性复核 | CachePlan |
| 为什么做 | 为了让 P4A 跑得更快更省 | 为了回答本项目的研究问题 |
| 设计 | 无对照、无假设、无预注册 | 有对照、有可证伪的预期 |
| 能支撑什么 | **动机**：这个现象存在、量级值得关注 | 研究结论 |
| 不能支撑什么 | "CachePlan 的方法是否有效"——见 `solution/constraints.md` 第 1 条 | — |

**当前状态：B-series 有 2 条已完成；E-series 有 0 条已完成。**

---

## B01 — 单 session 的逐事件轨迹解剖（起点观测的复核）

**性质**：一次性人工复核，n=1。**不是实验**——没有对照，没有预先声明的可证伪预期，
目的只是确认 `refractor.md` 里那个 10–18 倍的放大不是转述错误。

**做了什么**
解压 P4A 保留的 kimi-code session 归档，随机取一条完整 session
（`session_0b334391-...`，对应论文 `2025.acl-long.114`），从 `agents/main/wire.jsonl`
逐条读 `usage.record`：累加每 turn 的 input 得到累计计费 input，取最后一 turn 的 input
作为"最终真实上下文"，相除得放大倍数；同时读出每条记录的 `inputCacheRead` /
`inputCacheCreation`。

**结果**
放大倍数落在 `refractor.md` 给出的区间内，确认这不是长尾样本；cache 两个字段在这条
session 上全程为 0。

**日期**：2026-08-31

**证据**：`../evidence/tables/table02-p4a-session-repro.md`

**它支撑什么**：C01 的量级、C02 的口径分离现象。

**它不支撑什么**
n=1。"cache 字段恒为 0" 在这一条上成立，**不能外推到全量**——这正是 E01 阶段 1 存在的
理由。分析逻辑是手工执行的，**没有落成脚本**，目前不可自动重跑；E01 必须把它脚本化，
这是一个已知的可复现性缺口。

**它与 E01 的关系**：B01 是 E01 的 pilot。E01 把这里手工做的一次，变成全量、可脚本重跑、
且测量维度更宽的观测。

---

## B02 — layer4_v2 的 200 篇对照评估（P4A 自己的工程验收）

**性质**：P4A 项目为了验收自己的重构而做的评估。**不是本项目设计的对照实验**，尽管它的
形状恰好接近 E02 想做的事。

**做了什么**
`experiments/p4a/src/extract/layer4_v2/` 是 `refractor.md` 重构方案的完整实现：用
"程序批处理 + 两次纯文本 LLM 调用 + 轻量修补 + v1 agent 兜底" 替代 v1 的"每篇一个 ReAct
agent"。按 [autonomy ladder](solution/autonomy-ladder.md) 它大致落在 **L2–L3 之间**，
对照的 v1 落在 L4。从已完成的 v1 论文里抽 200 篇，用 `compare_v1_v2.py` 逐篇 diff 资源
（name / kind / relation），再用 `adjudicate_compare.py` 做分歧裁定，对照 `refractor.md`
§8 的通过线。

**结果**
README 称 200 篇评估裁定召回通过。

**证据**：`../evidence/tables/table10-layer4v2-eval200.md`（转引，**未核实**）

**它支撑什么**
C11——即"跨 run 前缀设计已被自发采用却不被测量"这件事，`layer4_v2` 的代码是直接证据
（这部分是**代码事实**，可在本仓库内验证，与评估结论无关）。

**为什么它不能结案前置 open question**

1. **报告不在本仓库**。`reports/layer4_v2_eval200.md` 在 p4a 工作副本里，本 artifact 只能
   转引 README 的一句摘要，数字未经核实。
2. **v1 是参照系，不是对照臂**。"裁定召回" 是 v2 相对 v1 结果的召回，不是两臂各自相对
   独立 ground truth 的质量。而 v1 自身已知有质量问题（抽样的 `checked_by` 分布显示
   agent 经常没真正核验资源），因此"追平 v1"与"任务质量相当"不是同一件事。
3. **两臂不独立**。v2 的失败路径会回退到 v1 的 ReAct agent（`merged_via_fallback`），
   所以 v2 臂里混入了一部分 v1 执行，兜底率必须作为协变量。
4. **没有本项目定为一等指标的任何东西**：无行为统计，无双口径成本，无 cache 测量。

**它对 E02 的用处**：作为**先例与脚手架**，不作为结果。它证明 L2–L3 臂是可实现的，并留下
了可复用的 diff/裁定工具；E02 若要用它，必须补上独立 ground truth、去掉兜底污染、加上
行为统计与双口径成本。

**待办**：取回 `reports/layer4_v2_eval200.md` 并核实。这是本项目手上**唯一一份触及前置
open question 的真实数据**，优先级高于 E04/E05 的文献评审。
