# T10 — layer4_v2 的 200 篇对照评估

> ⚠️ **可信度：未核实。** 下面的数字转引自本仓库内的一个 README，但**其原始报告
> `reports/layer4_v2_eval200.md` 不在本仓库**（它在 p4a 工作副本 `/home/lzx/projs/p4a_v2`）。
> 本 artifact **无法核实**这个数字，也无法看到它的分项、样本构成与失败模式。

**Source**: `experiments/p4a/src/extract/layer4_v2/README.md:162-163`
**支撑**: C11, B02
**通过线**: 见 [T04](table04-v2-pass-criteria.md)

## 转引原文

> §8 通过线（详见评估报告）：v1 召回≥95%、kind/relation 一致率≥90%、schema 100%、
> 兜底率≤5%、≤60s/篇。
> **200 篇评估裁定召回 96.1% 通过。** **注意**：全新数据（v1 没做过的 venue/年份）没有
> v1 对照，只能报管线健康度（merged/schema/兜底率），无法给召回对照。
>
> —— `experiments/p4a/src/extract/layer4_v2/README.md:162-163`

## 表

| 项 | 值 | 状态 |
|---|---|---|
| 对照集规模 | 200 篇（从 1071 篇已完成 acl-long 抽样） | 来自 T04 的设计 |
| 裁定召回 | **96.1%**（通过线 ≥95%） | ✅ 转引，未核实 |
| kind / relation 一致率 | — | ❓ 报告不在库内 |
| schema 通过率 | — | ❓ |
| 兜底率 | — | ❓ |
| 单篇耗时 | — | ❓ |
| 单篇 token | — | ❓ |
| **任何 cache 指标** | — | ❌ **通过线里就没有这一项**（T04） |

## 这份评估在 autonomy ladder 上的位置

被评估的 v2 大致落在 **L2–L3 之间**：控制流固定（程序批处理 + 状态机），LLM 只做两次纯
文本调用（语义抽取 + 最终裁判），validation 失败时走轻量修补，再失败才回退 agent。
对照臂 v1 是 **L4**（Full ReAct Agent）。

**这是本项目手上唯一一份触及 open question 的真实数据。**

## 三条使它不能结案 open question 的限制

1. **报告不在本仓库**，数字未经核实。
2. **v1 被当作参照系而非对照臂。** "裁定召回 96.1%" 是 v2 相对 **v1 结果**的召回，不是两臂
   各自相对独立 ground truth 的质量。而 v1 自身已知有质量问题——见 [T03](table03-p4a-checked-by.md)，
   抽样 50 篇中 `checked_by=none` 占 52.6%，agent 经常没真正核验资源。
   **因此"追平 v1"与"任务质量相当"不是同一件事。**
3. **两臂不独立。** v2 的失败路径会回退到 v1 的 ReAct agent（终态 `merged_via_fallback`），
   所以 v2 臂里混入了一部分 v1 执行。兜底率必须作为协变量报告，而它恰好是报告里我们看不到
   的分项之一。

## 它没有覆盖的（E02 要求的一等指标）

- **行为统计**：实际交互轮数分布、repair 触发率、回溯/重读频率、外部检索调用比例
- **双口径成本**：只有计费 token（通过线写的是 `input ≤80K`），无任何 cache 折算口径
- **按任务难度分层**：只有总体召回，没有困难样本子集的表现

## 与 `docs/` 的不一致（**已部分修复；处置仍需用户裁定**）

编译本 artifact 时发现：`docs/` 全文从未提到过 `layer4_v2` 的存在，而
`experiments/p4a/src/extract/layer4_v2/` 里已经有一个完整实现并跑过 200 篇对照评估。

**2026-09-01 已修复记录缺失的那一半**：`docs/PROGRESS.md` 的 Experiments 节现在记录了
`layer4_v2` 的存在、它的 200 篇评估、以及它为什么不能直接结案 open question。
`docs/PROGRESS.md:36` 仍把 controlled comparison 列为待办——这是正确的，因为本评估不构成
那个受控实验。

**仍待裁定的是处置方式**（见下方三个选项）。**本 artifact 不擅自把 open question 判为
RESOLVED**——按上面三条限制，它也确实不够格结案；但这处不一致本身需要被处理。
记录在 `../../trace/exploration_tree.yaml` 的 `n11-docs-code-drift`。
