# Evidence

## 为什么本 artifact 没有图片

标准 ARA 要求每个编号的 Table/Figure 同时存 markdown 转写与截图 PNG。**本 artifact 一张
图片都没有存**，这是一个刻意的决定，理由如下：

1. **源材料里没有编号图表。** 本 artifact 编译自一个研究仓库的 markdown 文档与代码，不是
   一篇论文。`docs/` 与 `experiments/p4a/*.md` 里的表格本身就是 markdown 源文本——它们的
   "原始形态"就是文本，截图只会得到一张渲染后的同一份文本，不增加任何信息。
2. **来自论文的图表不能进版本库。** T05–T09 的底层图片确实存在（两篇论文的图区渲染，在
   `references/papers/<citekey>/figures/`），但该路径是 **gitignored** 的，理由是**体积与
   版权**（`references/README.md`）。把它们复制进 `ara/` 会绕过这条规则，把受版权保护的
   论文图形提交进一个可能公开发布的目录。**不做。**
3. 需要看原图时，路径在每个 T05–T09 文件的 `Source` 字段里，取回方式见
   `../src/environment.md` §3。

`figures/` 目录保留为空占位。

## 证据清单

| ID | 内容 | 来源类型 | 支撑 |
|---|---|---|---|
| [T01](tables/table01-p4a-current-throughput.md) | P4A 现网实测：耗时/工具调用/token/吞吐 | **自有实测** | C01 |
| [T02](tables/table02-p4a-session-repro.md) | 单 session 逐事件复现与 cache 字段 | **自有实测** | C01, C02 |
| [T03](tables/table03-p4a-checked-by.md) | 抽样 50 篇的 `checked_by` 分布 | **自有实测** | autonomy-ladder |
| [T04](tables/table04-v2-pass-criteria.md) | refractor.md §8 的评估通过线 | **自有设计** | B02 |
| [T05](tables/table05-deepprep-structure-vs-training.md) | 结构收益 vs 专门化收益的分解 | **staged** | C04, C05 |
| [T06](tables/table06-deepprep-reward-ablation.md) | 稀疏奖励下的 agency 自发退化 | **staged** | C06 |
| [T07](tables/table07-longda-main-results.md) | 11 模型的准确率/步数/token/时间 | **staged** | C07 |
| [T08](tables/table08-longda-tool-ablation.md) | 工具消融 | **staged** | C07 |
| [T09](tables/table09-longda-prefix-ceiling.md) | 块内前缀命中率上限的推算 | **staged（且为二次推导）** | C02 |
| [T10](tables/table10-layer4v2-eval200.md) | layer4_v2 的 200 篇对照评估 | **自有，但报告不在库内 → 未核实** | C11, B02 |

## 三级可信度

本 artifact 的证据分三级，**每个文件的头部都标了级别**：

| 级别 | 含义 | 可以用来做什么 |
|---|---|---|
| **自有实测** | 数字出自本仓库内可打开的文件，已逐条核对 | 内部论证 |
| **未核实** | 数字转引自本仓库内的文件，但其**原始报告不在本仓库** | 记录，不论证 |
| **staged** | 出自未经人工评审的 agent 精读稿，且 `refs.bib` 条目已被移除 | **仅记录推理痕迹，不可引用、不可支撑决定** |

staged 规则出处：`references/README.md:38`。

## 未转写的源对象及理由

| 源对象 | 为何不单独立文件 |
|---|---|
| `refractor.md` §2.4 / §2.6 的 prompt token 预算表 | 是**设计目标**不是测量值；已在 `../src/artifacts.md` §3 里以设计意图的形式引用 |
| `refractor.md` §5 的目录结构 | 结构说明，非证据 |
| `pipeline.md` 的全部命令示例 | 操作手册，已在 `../src/environment.md` 与 `artifacts.md` 中索引 |
| 两篇精读稿里未被任何 claim 使用的表 | 按"只保留承重证据"的原则不转写；原稿路径见 T05–T09 的 `Source` |
| `layer4_v2/README.md` 的参数表与状态机 | 操作细节，已在 `../src/artifacts.md` §3 索引 |
