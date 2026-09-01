# Cache Accounting

本项目方法论的核心：**成本口径的三层区分**。这不是一个技术方案，而是一套记账规则——
它决定了哪些数字可以拿来比较，哪些不能。

对应 claim C02。

---

## 1. 两种 token 账，互不蕴含

| 口径 | 计的是什么 | 由谁决定 | 在哪能看到 |
|---|---|---|---|
| **billed input** | 这一步送进模型的完整 token 序列长度 | agent 的执行结构：轮数、上下文管理策略 | agent 侧 usage 日志、API 账单 |
| **actual prefill** | 其中真正需要重算 KV 的部分 | serving engine 的 prefix cache | serving engine 指标，**通常不回传给 agent** |

**P4A 上同时观测到的两个数字**：

- serving 侧：本地 vLLM，prefix caching 已启用，**实测命中率 89%**，KV 占用 2.8%，0 抢占。
- agent 侧：抽样 session 全部 19 条 `usage.record` 的 `inputCacheRead` /
  `inputCacheCreation` **均为 0**。

这两个数字在同一个系统里同时成立。它们不矛盾，因为记的是两本账。

**Sources**
- ← `experiments/p4a/refractor.md:256` «vLLM：`qwen3.6-35b-a3b`，max_model_len 262144；prefix cache 命中率 89%，KV 占用 2.8%，0 抢占。» [result]
- ← `docs/experiments/p4a.md:21` «该 session 全部 19 条 `usage.record` 的 `inputCacheRead` / `inputCacheCreation` 均为 0» [result]

### 直接后果

**未经 cache 折算的 token 计数不能用来比较不同执行范式。**

偏差不是随机的，而是**系统性偏向**：步数越多的执行风格，其 billed input 被高估得越厉害
（因为它重发历史的次数更多，而这些重发恰恰是最容易命中 cache 的部分）。所以用原始 token
数比较"细粒度多步"与"粗粒度批量"两种风格，会夸大前者的成本劣势。

一个量化的例子（**staged，不承担论证责任**）：某 benchmark 中最省与最费两个模型之间
**20.8×** 的输入 token 差距，按其自身数据推算，在完美前缀缓存下会压缩到约 **1.65×**。

**Sources**
- ← `references/papers/anon2026longda/close-read.md:503` «**Table 2 里 GPT-5 与 GLM-4.7 之间 20.8× 的输入 token 差距，在完美前缀缓存下会压缩到约 1.65×。**» [result, staged]

---

## 2. 三层复用，只有一层是本项目的目标

三个层次名字相近，省的东西完全不同。**混淆它们是引用外部工作时最容易犯的错误。**

| 层次 | 复用对象 | 省下的是 | 本项目关心吗 |
|---|---|---|---|
| **算子/中间产物前缀复用**（intra-run，语义层） | 已物化的中间结果 | executor 的重算时间，**与 KV 完全无关** | ❌ 只是名字相同 |
| **KV / token 前缀复用**（intra-run） | 同一 run 内 append-only 的历史 | 本 run 内后续步的 prefill | ⚠️ 已被 serving 自动处理 |
| **跨 run 前缀复用** | 多个独立 run 之间逐字相同的前缀 | 整个语料上每个 run 的 prefill | ✅ **这是目标** |

第一层是外部工作最常宣传的"复用"。一篇 workload 形态与本项目高度吻合的系统论文把它作为
卖点，而**对第三层一字未提**——尽管其固定协议对数千条独立 case 逐字相同。

**Sources**
- ← `references/papers/fan2026deepprep/close-read.md:603` «回溯到 $n_2$ 意味着不必重跑 Deduplicate / ValueTransform —— 省的是**执行器的重算**，不是 prefill。**这与 KV cache 无关，只是名字相同。**» [result, staged]

---

## 3. 一条需要修正的直觉：树式/回溯式 agent 未必对 cache 不友好

一个常见的直觉是"agent 一回溯，KV 前缀就失效了"。这**取决于实现方式**：

- **把树线性化进内容里的实现**：树只活在一条线性 token 流的*内容*中，回溯表现为在新一轮
  里写一句"从节点 X 展开"，token 序列**只增不删**。KV 前缀从不失效。它付出的代价是另一种：
  上下文里堆满失败分支和反复重排的中间状态——**问题是 context 冗余膨胀，不是 cache 失配**。
- **真正做上下文回卷（rewind）的实现**：才会有前缀失效问题。

这个区分对本项目的意义：判断一个 agent 设计是否 cache-friendly，**必须先看它的上下文管理
是不是 append-only**，不能从它的控制结构（线性/树/图）直接推断。

**Sources**
- ← `references/papers/fan2026deepprep/close-read.md:613` «**问题是 context 冗余膨胀，不是 cache 失配。** 这个区分对我们很重要：它说明"树式 agent 对 cache 不友好"这个直觉需要先看实现方式 —— 把树线性化进内容里的实现（DeepPrep 这种）是 append-only 的；只有真正做上下文回卷（rewind）的实现才会有前缀失效问题。» [result, staged]

---

## 4. 记账规则（本项目自用）

任何报告成本的地方，必须满足：

1. **同时报两个口径**，或明确声明只有一个可得及其原因。
2. 若只有 billed input 可得，且 serving 侧 cache 指标不可得（P4A 的当前处境），则退回
   **基于 prompt 前缀 token 重叠度的代理指标**，并**明确标注为估算值而非真实命中率**。
3. **不比较跨 serving 环境的成本数字**。不同量纲（token 计价 vs GPU 秒租金）不可直接比较；
   并发度会线性缩放按墙钟折算的每单位成本，未报告并发度的数字不可复现。
4. 报告 cache 相关数字时，必须说明它属于第 2 节三层中的哪一层。

规则 1–2 的强制来源是先决核查项（见 `constraints.md` 第 2 节）。规则 3 是从外部工作的
口径缺陷反推出来的（staged）。

**Sources**
- 规则 2 ← `docs/experiments/p4a.md:38` «若恒为零：说明该字段在这套 openai 兼容 provider 下未被正确采集，只能退回基于 prompt 前缀 token 重叠度的**代理指标**，报告中必须明确标注这是估算值而非真实命中率。» [input]
- 规则 3 ← `references/papers/fan2026deepprep/close-read.md:628-629` «**两边不同量纲，且恰好抹掉了我们想测的量**。闭源是 token 计价（对 prompt 长度线性敏感，含 cache 折扣），开源是 GPU 秒租金（对 prompt 长度只通过 prefill 时间间接敏感）。»«**并发度未报告**。» [result, staged]

---

## 5. 共享前缀的可用量由排序决定

一条定义性的推论，但实践中被反复违反：

> 跨 run 可复用的前缀 = 从 prompt 开头起，连续逐字相同的那一段。
>
> 因此一段跨 run 完全相同的内容，只要被排在任何 per-run 变量**之后**，它对跨 run 前缀
> 复用的贡献就是 **0**。

修复是纯粹的重排，代价为零。已观测到的实例见 C08——一段跨 30 个 run 逐字相同、且是模板里
**最长**的固定块，被放在了全部 per-run 变量之后，导致朴素共享前缀只剩第一行。

这条也给出了 cache-aware prompt 设计的第一条可操作规则：**不变量前置，变量后置**。
