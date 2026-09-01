# T04 — layer4_v2 的评估通过线

**可信度**：自有设计（这是**通过线**，不是测量结果）
**Source**: `experiments/p4a/refractor.md:233-244`
**支撑**: B02

对照集：从 1071 篇已完成 acl-long 随机抽 **200 篇**。

| 指标 | 通过线 | 测法 |
|---|---|---|
| resource 召回率 | ≥95%（对旧结果资源清单） | 程序 diff；分歧样本人工裁决归因（旧错/新错/都对） |
| resource 精确率 | 不低于旧流程 | 人工抽检 50 篇 diff |
| kind / relation 一致率 | ≥90%（分歧人工裁决） | 程序 diff + 抽检 |
| citation_function | 抽检无系统性退化；降级篇目单独统计 | 人工抽检 |
| YAML schema 通过率 | 100%（guided decoding 保证） | validate 全量 |
| 单篇端到端耗时 | ≤60 s（并发 8 时的均摊） | batch_report 计量 |
| 单篇 token | input ≤80K、output ≤15K（含修补重试） | batch_report 计量 |
| 兜底率 | fallback_agent ≤5% | batch_report |

## 预期收益（**预期值，不是实测**）

> 每篇 input 从 ~140 万 → ~5 万 token；GPU 串行时间 ~35–50s/篇；并发 8–16 下吞吐上限
> 100+ 篇/h（现网 19.7 篇/h）。
>
> —— `experiments/p4a/refractor.md:246`

## 对本项目的关键观察

这张通过线表里**一项 cache 指标都没有**。单篇 token 用的是未经 cache 折算的计费口径
（`input ≤80K`），因此即使全部达标，也无法回答"跨 run 前缀复用省了多少"。这与 C11 描述的
缺口一致：**用了这个杠杆的项目，在自己的验收标准里也没有为它留一行。**
