# Open Question 3：什么样的 Paper-for-Agents workload 能检验动态跨 run 复用？

> **一句话**：若静态 `system prompt` 已覆盖固定 Skill，什么样的真实、可验证且可复现的多 run workload 仍会留下可由 cache-aware planning 利用的复用结构？
>
> 这不是“再找一个 benchmark”的问题。workload 必须同时给出真实业务依赖、独立的质量判据、可观测的复用结构和可控的 batch 条件；否则测到的只会是静态前缀、结果缓存，或网络/调度噪声中的某一种。

提出日期：2026-09-04。状态见 [`PROGRESS.md` → Open Questions](../PROGRESS.md#open-questions)。

## 1. 问题

P4A v1 让我们看到了一个真实的 data-intensive agent workload：固定 Skill 驱动大量论文输入，agent 读论文、检索资源、写结构化记录并调用 validation。但它不适合作为本项目方法有效性的主 benchmark：

1. **执行单位过于单一。** 一篇论文基本是一条长 ReAct session；输入私有内容很早进入上下文，跨 run 的 prompt/KV 复用主要退化为一个固定开头。
2. **质量评测不充分。** v1 产出带 schema validation，却没有能客观裁定论文理解、资源判断和证据归因质量的完整评测体系；不能只以“脚本通过”代替任务效果。
3. **历史轨迹不能反事实重放。** 它只能诊断已经发生的前缀、分叉和 token 放大，不能作为改变规划/调度策略后的质量与成本对照。

因此问题不是“如何让同一篇论文跑四个 task”，而是：

> 如何构造一个 **Paper-for-Agents workload family**，让多个相互有关但不相同的 run 围绕论文、cohort 和 corpus state 真实发生；并能区分 prompt/KV reuse、artifact/result reuse 与 plan reuse，在受控 batch 环境中检验 cache-aware planning 相对强静态 baseline 的增量？

## 2. 先分清三种“复用”

“不同 run 共享中间执行状态”不是一个单一机制。若不分开，benchmark 会把不同系统层的收益混在一起。

| 复用层 | 被复用的对象 | 正确性条件 | 对 CachePlan 的含义 |
|---|---|---|---|
| **prompt / KV reuse** | 同一有序 token prefix 的 KV state | 完整前缀逐 token 相同；KV 在调用间仍驻留或可恢复 | 本项目主要关心的 inference reuse；需要 root、时间邻近和 batch 调度 |
| **artifact / result reuse** | 已验证的 paper fact、evidence edge、entity link、provider lookup 结果 | 输入、版本和 provenance 一致；算子满足确定性/可缓存条件 | 有价值，但应单独记账；不能冒充 KV cache 收益 |
| **plan reuse** | stage template、算子图、provider routing policy | task intent 匹配、输入/输出 schema 兼容 | 降低规划开销，并使后续 KV reuse 的结构可见 |

例如，一篇论文的 `resource_records` 被后续“跨论文比较”调用读取，通常是 artifact reuse；两个 `VerifyGitHubResource` 调用共享同一 provider contract 和 schema prompt，才可能是 prompt/KV reuse。两者可以叠加，但必须分别测量。
provider routing 在运行中才被选择，至多证明**调用选择**是动态的；它不自动证明共享上下文必须动态构造。每个候选动态 root 都必须给出反事实强对照：若编排器选择预写的、同信息内容的 provider/stage 模板即可产生相同 prompt、质量和复用，那么模板选择就是应先打败的静态策略，而非 CachePlan 的增量。只有选择之后才由可审计中间工件决定、且不能预先列成等价静态模板的共享内容，才构成这里所说的动态构造。


同样地，一个 LLM 调用只能沿一条因果 prefix path 复用 KV；“多 root”不是将任意 KV state 拼接，而是一个 batch 中的不同 ready calls 落在 prefix forest 的不同路径，调度器选择哪些路径物化、pin 和相邻执行。

## 3. 候选业务单位：论文编译的增量 ingestion

本 OQ 暂不规定最终产品 schema 或 scholarly database。可供讨论的最小业务承诺是：

> 将论文及关联材料持续编译成可供后续 agent 检索、引用、比较、调用和验证的版本化工件。

它自然有三个层级：

- **paper-local**：正文规范化、资源/事实/实验候选抽取、证据定位、provider 核验；
- **cohort-level**：同 venue、格式、任务/方法/数据集族、规则包或 provider 的论文批次；
- **corpus-level**：实体归一、跨论文关系、索引或其他可查询状态的更新。

一个候选 template 不是单一长 session，而是逐阶段展开的 workflow：

```text
paper package
  → normalize / parse
  → local candidate and evidence extraction
  ├─ bibliography resolution
  ├─ provider-specific resource verification
  └─ experiment / claim extraction
  → typed artifact assembly
  → deterministic validation
  ├─ pass → publish paper-local artifacts
  ├─ typed diagnostic → bounded repair / re-verification
  └─ unresolved exception → dynamic agent or manual fallback
  → cohort / corpus linking
```

候选数量、实体匹配和 repair 是否被激活会在运行中显露；实例图可以随后展开为 DAG。真正无法预先展开的开放调查应隔离在 fallback 内，而不应把整个主路径退回长 ReAct session。

## 4. benchmark 必须满足的约束

### 4.1 业务相关性：不能为了重复而复制任务

每个 run 必须服务于可说明的下游 agent 使用，而非将同一 prompt 改写数次制造共享。例如可讨论的任务族是：

- 对新增论文生成带证据的 paper-local artifacts；
- 将一批论文链接到共享资源、任务或数据集实体；
- 基于已验证 artifacts 生成比较、追溯或更新请求所需的 evidence pack；
- 对 validation diagnostic 做有限的定点修复。

这些 task 之间可共享输入、工件和规则，但输出、依赖和质量目标不同。最终纳入哪些 task，取决于其真实消费者与可验证性，尚未决定。

### 4.2 质量：必须先于 cache 指标成立

每个 operator 或端到端任务都需要独立于被测模型的 quality contract，例如：

- 资源/实体/关系的人工标注 precision、recall、F1，或双人裁定集；
- claim 与 evidence span 的 grounding / attribution 正确率；
- schema、provenance、版本一致性和 provider evidence 的确定性 validator；
- 跨论文任务的可审计输入、预期集合、排序或比较判据；
- fallback rate 与人工复核率。

结构化校验是必要条件，不能单独充当质量评测。若某个 task 没有可接受的质量 contract，它不能成为“策略不降能力”的证据。

### 4.3 复用结构：事前声明并在运行后核验

每个 workload release 应显式记录：

- stage / role / schema / provider / corpus-state 的版本；
- 每个 ready call 所属的内容 root 与 prefix 长度；
- cohort 大小、root 的调用次数、调用到达时间和依赖边；
- paper-private 输入长度、预期 decode 长度或其可观察代理；
- artifact cache key、有效期、determinism 与 provenance；
- 分支激活率、repair 次数和 fallback 率。

原始 corpus 数量不是主要设计变量。50–100 篇论文只有在每个预期复用 cohort 仍有足够重复调用、并能产生所需 root/length/arrival 分布时才有意义。一个“大而浅”的语料或“少而单根”的语料都不能回答本 OQ。

### 4.4 可重复性：外部世界必须被区分、冻结和记账

GitHub、HuggingFace、arXiv、论文附件和网页状态会随时间变化。评估主路径应尽量使用带版本和 hash 的 offline fixture；fixture 中保留原始响应、时间、许可/访问状态与证据定位。

外部访问可以作为单独的 realism / freshness 评估，但不能与 cache-aware planning 的主对照混在一起。否则网络延迟、provider 失败、限流和工具 schema 漂移会掩盖调度收益。P4A v1 的真实外部轨迹仍有诊断价值，但不提供这种反事实控制。

### 4.5 batch shape：内容共享与长度对齐要分别操纵

[Helium](../literature/2026-Helium.md) 说明全局 workflow 结构可以将共享前缀变为可调度收益；[AlignedServe](../literature/2026-AlignedServe.md) 则说明相同 decode batch 内 KV 长度悬殊会产生 iteration bubble。二者正交。

因此 future workload 的每个 batch 至少应能描述为：

$$
B = (\text{stage},\ \text{content root},\ \text{current-KV-length bucket},\ \text{arrival/dependency state}).
$$

只按 root 聚类可能将长、短 private context 混在一个 decode batch；只按长度对齐又会打散内容共享。benchmark 应允许分别观察和操纵这两个维度，而不是预设 joint batching 一定获益。

## 5. 需要回答的可证伪子问题

OQ3 不是要预先承诺一个方法，而是要求 workload 设计能回答下列问题：

1. **强静态策略是否已足够？** 在完整 canonical procedure、stage/provider contract 与易变块均以 static-first 顺序注入的同信息内容对照上，是否仍存在大量、可重复且不由 artifact cache 解释的动态 prefix reuse？
2. **结构何时显露？** 在哪些 stage 后，cohort、provider、实体或 repair diagnostic 才足以使后续调用形成可调度的 root cluster？提前等待形成 micro-batch 的排队代价是什么？
3. **什么被复用？** 观察到的成本下降中，prompt/KV、artifact/result、plan 三层各占多少？若只剩 artifact reuse，则问题应转交给数据/查询缓存，而不是宣称 CachePlan 有效。
4. **batch shape 是否抵消收益？** root-aware batching 相对默认/FCFS 是否造成 decode length skew、KV pressure 或公平性恶化？length-aware batching 是否损害内容 locality？
5. **能力边界在哪里？** 主干 workflow、有限 repair 与 dynamic fallback 的质量、fallback rate 和成本如何随策略变化？

任何一个否定结果都同样有价值：若强静态策略吃掉了动态空间、cohort 重复不足，或 KV reuse 的收益被排队/length bubble 抵消，则该 workload 不应被包装为 CachePlan 的正面证据。

## 6. 最小证据协议：先刻画，再干预

在创建新实验或全量运行前，需要先讨论并固定协议。一个最小的顺序是：

1. **业务与质量设计**：确定有限 task family、下游使用者、artifact schema、质量 contract 与 fixture 边界；
2. **workload characterization**：只运行/重放基线，测 root/cohort 分布、实例 DAG、依赖、length shape、arrival、artifact reuse 和 fallback；
3. **受控干预**：在同一模型、fixture、工具 schema、batch budget 和质量协议下，比较强静态策略与后续动态策略；策略名称必须描述注入内容与构造方式，不能跨实验复用漂移的臂编号；
4. **分层报告**：分别报告命中/未命中 prefill、decode、KV 占用、队列等待、wall time、吞吐/尾延迟和任务质量。

第 2 步的通过条件不是“看起来有很多调用”，而是能明确给出：哪些 root 在何时有多少 ready calls、其 private-length 分布如何、理论可节省的 prefill 有多少、以及为何该重复来自业务依赖而不是人为复制。

## 7. 与现有记录的关系

- [E01](../experiments/e01-p4a-trajectory.md) 与其 [`02_trajectory.ipynb`](../../experiments/e01-p4a-trajectory/notebooks/02_trajectory.ipynb) 第 5 节提供 P4A v1 的继承性轨迹观测：稳定主干、provider 分叉、validator 后 repair 和异常委派。它们是 workload mining 的输入，不是方法比较实验。
- [OQ2：可复用上下文放置](Placement-of-reusable-context.md) 给出强静态策略的必要条件：完整、同信息内容的 procedure 必须以 static-first 布局注入。后续策略只能报告相对该策略的增量，不能沿用其他实验的 `A2` / `A3` 编号。
- OQ1 已 DEFERRED：OQ3 不重新询问“agent 是否必要”，而是讨论在存在动态 agent 尾部时，什么 workload 能让 agency、复用与质量的 trade-off 可测。
- [AgenticScholar](../literature/2026-AgenticScholar.md) 是“固定计划骨架 + 动态生成兜底 + 验证”的业务形态先例，但其缓存层次是计划/结果而不是 prompt/KV。
- Helium 代表完全可编译、全局结构可见的端点；OQ3 更关心结构逐阶段显露但主干仍可观察和编排的中间区域。

## 8. 当前不作出的决定

本文不决定：

- Paper-for-Agents 的最终用户、query interface、taxonomy / graph 或 artifact schema；
- 论文数、任务数、cohort 数、并发度、KV 预算或具体模型；
- 是否采用 Helium 风格全局编译、AlignedServe 风格 length-aware batching，或任何 joint policy；
- 具体受控实验的名称、臂编号、规模、并发度或 KV 预算；
- P4A v1 历史数据或代码的修改、重跑或作为方法效果基线。

在业务 contract、质量评测和 workload characterization 尚未讨论完成前，OQ3 只是开放问题，不是新 benchmark 的实现任务。
