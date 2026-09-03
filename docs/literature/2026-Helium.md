---
citekey: 2026-Helium
title: "Efficient LLM Serving for Agentic Workflows: A Data Systems Perspective"
venue: "Proc. ACM Manag. Data (SIGMOD)"
year: 2026
url: https://doi.org/10.1145/3802046
relates-to: open-questions/Placement-of-reusable-context.md
status: read
verdict: "在线被动 prefix caching 几乎无收益、编译期结构先验才是主要收益来源的最干净受控证据（Table 4）；同时它的静态模板假设精确划定了我们动态轨迹场景的边界。"
---

## 它说了什么

把批量 agentic workflow 建模为 query plan，LLM 调用作为一等算子：编译期做 plan 重写（pruning + CSE + CacheFetch），用 templated radix tree（TRT）编码全局前缀结构与依赖，再做 cost-based cache-aware 调度与静态前缀 KV 预热（pinning）。全部变换保持语义不变。精读稿：`references/papers/2026-Helium/close-read.md`。

与 OQ2 直接相关的证据：

- **Table 4（关闭所有缓存、只比调度）**：在线前缀感知调度（SGLang LSPF）命中率 37.9%，仅比随机调度（37.1%）高 1.5pp；Helium 的全局 TRT 调度拉到 56.5%。
- **Table 3（消融）**：去掉 plan pruning 退化最大（−23.35%），调度 −17.66%，prompt cache −13.56%，KV 预热 −3.55%——收益来源排序是冗余消除 > 调度 > 结果缓存 > 预热。
- 对最强基线 KVFlow（同样是 workflow-aware 缓存系统）的增量是 1.32×–1.56×；对 vLLM 的 66–100× 是"无 batching 顺序执行"稻草人，不具参考价值。

## 我们采信什么

- "在线/运行时的 cache 感知不够，结构先验才重要"这一核心前提，Table 4 是第三方受控证据，可直接引用（与 E01 s4"按变体分组调度回收 89%"方向一致且互为印证）。
- "批量、模板化负载下，把缓存决策从运行时提前到优化期有系统化收益"成立，量级对最强基线是 1.3×–1.6×，不是数量级。

## 边界与差异

- **Helium 假设工作流模板编译期完全可见**（静态 DAG + greedy sampling + 同一 base LLM + 本地算子）。这等于假设掉了 agency：我们的 workload 里轨迹由模型实时走出，TRT 建不出来。它能覆盖的场景与我们的研究空间以"计划能否编译期化"为界。
- prompt cache/CSE 只对确定性算子有效，温度采样下这条收益路径基本失效，论文未测。
- 最优性验证只在玩具规模（2–4 agents × 2–4 queries）上做；Trading 数据集为作者自建。

## 对我们的启示

- **抬高了 baseline 水位**：它的 proactive KV pinning 就是 OQ2 里 A2 静态布局的系统化版本。E06 除了 A2，值得加一个很便宜的 A2+ 臂（静态前缀预热/pinning），预先回答 "why not Helium-style pinning" 这个审稿问题。
- **实验协议**：E06 必须固定 greedy sampling 并写明，否则缓存命中率结论不可解释。
- **研究问题划界**：CachePlan 的增量场景应明确表述为"计划无法编译期化的动态轨迹"，与 Helium 的 workflow-compiled scheduling 区分开。
- 它的"嵌套序列调度"（内层按 query 复用私有前缀、外层按算子复用静态前缀）可直接借作 E06 的调度臂设计。
