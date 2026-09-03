---
citekey: 2026-CoDec
title: "CoDec: Prefix-Shared Decoding Kernel for LLMs"
venue: "Proc. ACM Manag. Data (SIGMOD)"
year: 2026
url: https://doi.org/10.1145/3802028
relates-to: open-questions/Placement-of-reusable-context.md
status: read
verdict: "prefix caching 只省 prefill；decode 阶段对共享前缀 KV 的重复读取可在 kernel 层合并（收益≈平均共享度，实测访存平均降 120.85×）。修正我们代价模型中'decode 成本不受 prefix cache 影响'一条：它是 kernel 实现选择，不是物理定律。"
---

## 它说了什么

现有 prefix caching 系统（vLLM APC、SGLang RadixAttention）只复用 prefill 计算；decode 时仍按规则 4D 张量逐请求读 KV cache，共享前缀被读 $n_q$ 次。CoDec 把 decode attention 重写为前缀树上的部分注意力（PAC）+ 可并行树归约（POR），共享前缀 KV 只从全局内存读一次。IO 复杂度差一个加权平均共享度因子 $\bar{n}_q$（理论锚点），实测：kernel 平均 1.9×/最高 3.6×（vs FlashDecoding），访存平均降 120.85×，跨 5 款 GPU 与多个模型稳定。接口兼容 FlashDecoding、布局兼容 PagedAttention，代码开源。精读稿：`references/papers/2026-CoDec/close-read.md`。

## 我们采信什么

- 机制链条扎实：IO 复杂度分析 + 访存 profiling counter + 跨带宽敏感度（A6000 上 15× > H800 上 4.7×）三轴互证，"加速来自合并共享前缀访存"可采信。
- 共享度 $\bar{n}_q$ 在两层都是收益乘子：agent/系统层提高逻辑前缀共享，prefill 侧经 prefix caching 兑现一次，decode 侧经 CoDec 类 kernel 再兑现一次。这加强而非削弱"最大化逻辑前缀共享"的动机。

## 边界与差异

- 它是 kernel 层工作，不看 prompt 内容如何组织——与我们（agent 行为/规划层）和 Helium（调度层）都是乘性叠加关系，不是竞争关系。
- **数字口径不一致（硬伤）**：结论段 "up to 11.56×/150.56×" 与 §7.2 "up to 3.6×、avg 120.85×" 矛盾，疑似沿用 arXiv 旧版（FlashForge）口径。引用一律以摘要与 §7.2 为准。
- 端到端对比用 PyTorch 原型而非完整 vLLM 集成；Fig. 7 在 Ratio=1（无共享）时仍比 vLLM 快约 5×，正文未解释——端到端数字不干净。
- 无共享负载下退化为普通 FlashDecoding 且背 1.3%–2.5% 划分开销。

## 对我们的启示

- **OQ2 代价模型修正**：§4.2 的"decode 侧成本不受 prefix cache 影响"应标注为 kernel-dependent——若 CoDec 类 kernel 进入 serving 栈，A2/S1 的 decode 侧代价和共享前缀的收益都会重估。写代价模型时引用本文防审稿人反驳。
- 它的适用场景清单明确包括"agent 批量跑同一 Skill 流程（固定长前缀 × 输入并行）"，即 P4A 型负载——我们是它声称的目标负载之一。
- E06 用 vLLM 测得的 decode 成本数字，其外部效度受 kernel 层演进制约，讨论部分应承认这一点。
