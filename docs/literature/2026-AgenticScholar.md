---
citekey: 2026-AgenticScholar
title: "AgenticScholar: Agentic Data Management with Pipeline Orchestration for Scholarly Corpora"
venue: "Proc. ACM Manag. Data (SIGMOD)"
year: 2026
url: https://doi.org/10.1145/3802008
relates-to: open-questions/Necessity-of-agentic-execution.md
status: read
verdict: "我们 workload 类的第三个独立实例：'预定义计划库 + 动态生成兜底 + 验证自纠错'把规划开销降 >90%（Table 8），骨干消融显示换模型只动成本不动效果（Table 11）——智能的载体从模型转移到计划与数据结构。但缓存在计划/结果层，不涉及 prompt/KV 层；评测规模小且裁判与骨干同源，只能作旁证。"
---

## 它说了什么

把学术语料分析组织成 DBMS 三段式：taxonomy-anchored 知识图谱（表示层）→ 混合 LLM 规划（预定义计划选择，置信度 >90% 才复用，否则动态生成 + 确定性验证 + 调试式自纠错）→ 算子化 DAG 执行（含结果缓存与并行）。与 OQ1 相关的量化证据：

- **Table 8**：预定义计划命中时，规划输入 0.41K vs 4.08K token、时延 0.96s vs 15.17s——开销降 >90%。
- **Table 9**：动态生成路径 62.5% 零修复，全部 16 条查询 ≤3 次自纠错收敛——兜底机制有效且开销有界。
- **Table 6**：四类 Tier-3 查询的规划固定 410 token、检索 0 token（走本地 KG），成本几乎全在真正需要生成的 reasoning 段。
- **Table 11**：固定 pipeline 换 8 个骨干，效果 std ±4~5% vs 成本 std ±107%。

精读稿：`references/papers/2026-AgenticScholar/close-read.md`。

## 我们采信什么

- "重复性规划可以前置为可复用结构，在线 LLM 调用压到接近零"这一方向，Table 6/8 是同骨干、按阶段拆解的干净口径，可采信为方向性证据。
- 作为 OQ1 的第三个 workload 实例（P4A、2026-ARA 之后），证明"固定过程 + 输入并行"负载类在工业系统里以混合规划形态存在。
- 它的混合形态本身（静态计划保效率、动态生成 + 验证保能力）是"有限 agency"设计的一个已验证先例。

## 边界与差异

- **缓存层次不同**：它复用的是计划与结果，不是 prompt/KV 前缀——全文无 cache 口径的 token 分析，不能直接当 cache 证据引用（同 DeepPrep 的教训）。
- 评测弱：语料小（Tier-1 仅 237 篇）、Tier-3 裁判 GPT-5 与被测系统骨干同源且无方差/显著性；KG 构建成本不入账，效率优势含"本地预建 KG vs 联网搜索"的任务定义不对等。
- 未做 autonomy-level 消融（没有"全动态规划"对照臂），不能当 OQ1 的答案。

## 对我们的启示

- **A3 的形态参考**：它验证了"固定骨架 + 槽位填充式 agency"的设计——预定义计划 ≈ 稳定可缓存的轨迹前缀，动态兜底保能力。E06 之后设计 A3（cache-aware planning）时这是最直接的设计先例。
- 骨干消融（效果不动、成本剧变）提示：结构化基础设施足够强时，"缓存友好的规划"可能比"更强的模型"更值得优先投入。
