---
citekey: 2026-AlignedServe
title: "AlignedServe: Orchestrating Prefix-aware Batching to Build a High-throughput and Computing-efficient LLM Serving System"
venue: "Proc. ACM Manag. Data (SIGMOD)"
year: 2026
url: https://doi.org/10.1145/3802009
relates-to: open-questions/Placement-of-reusable-context.md
status: read
verdict: "与前缀共享一脉**正交的平行路线**：它利用的是 KV cache 的**长度形态**（对齐组 batch 消除 iteration 级气泡），不是前缀的**内容共享**，作者明确称与 HotPrefix/BatchLLM 类系统可串联（page 23）。不是我们的 baseline，是叙事中必须区分掉的相邻工作。"
---

## 它说了什么

continuous batching 下，同一 decode iteration 内不同请求依赖的 KVCache（论文称之为 prefix，含义 = 输入 + 已生成 token 的全部 KV，与"是否被多请求共享"无关）长度不同，长前缀请求拖慢全体（iteration-level bubble：batch 内仅 6.25% 长 prompt 就把 iteration 延迟拉高约 61%，Fig. 1）。AlignedServe 用 quad-tree + Density First Search 按前缀长度对齐组 batch，配套 CPU KV pool 大候选池与 GPU-Prefetch-For-GPU（NVLink 中转）架构，吞吐最高 1.98×、P99 TPOT 最高降 7.4×。精读稿：`references/papers/2026-AlignedServe/close-read.md`。

## 我们采信什么

- iteration-level bubble 的提出与量化（request/batch/iteration 三级气泡分层）是分析 serving 调度器的有用框架，Fig. 1/3 的动机实验设计干净，可采信。
- "把逻辑前缀共享转化为系统收益需要 batching/调度配合"这一大方向与 KVFlow/Helium 一致，但 AlignedServe 本身**不提供**关于内容共享的证据。

## 边界与差异

- **机制不同**：我们的问题是"跨 run 共享同一内容的前缀"；它的问题是"单 batch 内前缀长度不齐"。对我们的负载（固定 Skill 前缀 + 同构输入，各请求前缀长度天然接近），它的对齐收益会收窄——不适用为对照。
- TTFT 测量关闭了 starvation 机制（开启后无数据）；主实验全是 OPT 系列（无 GQA/MQA 模型，GQA 下 KV 更小、气泡严重度会变化）；未与 Sarathi-Serve 直接对比，7.4× 这类大数字部分来自基线强弱。
- 写作口径瑕疵：§4.4 负载比例疑似笔误、Fig. 14 截断 y 轴、page 18 有断引。

## 对我们的启示

- **文献叙事的区分点**："前缀共享变现"（Helium/KVFlow 线）与"KV 形态感知调度"（AlignedServe 线）是两条平行路线，相关工作中必须分开陈述，否则会被审稿人指出混淆。
- 若未来做端到端系统评估，它的 KV pool + NVLink 预取架构可作为承载共享前缀的底层设施（作者自己提出可串联，未做实验）。
- 反向印证：我们的负载前缀长度同质，意味着 serving 层的 bubble 问题不严重——收益空间确实集中在前缀内容复用上，而不是调度对齐。
