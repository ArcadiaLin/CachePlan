# v2 未定模型问题与写路径

创建：2026-10-01。状态：开放讨论。本文汇总 v2 读路径设计收敛后仍未确定的数据模型与写入问题，给出候选方案、倾向及 TODO。**倾向不等于决定**，各项需与用户讨论确认后再写入设计文档。

承接：

- 已收敛的设计：`docs/designs/v2/research_design_v2.md`、`docs/designs/v2/intents_decompose.md`。
- 已退役或大部分解决的问题：`docs/open-questions/` 下三份文档（见各文档顶部的 2026-10-01 更新）。
- 主张分层与 Agent 调用点分类：`docs/progress.md` 备忘。

## 1. 总体判断

读路径（访问契约、组合、外部 Agent 算子）已基本闭合；数据模型大部分收敛，但散落在 `intents_decompose.md` 中，`docs/designs/v2/graph_model_v2.md` 仍为空。未定部分集中在一个问题上：

> **经验怎样写进去，又怎样保持有效。**

这正是主张 A（学术理解经验的复用）的核心。若只复用论文作者的说法，而不复用 Agent 读后形成的判断，或无法判断旧判断是否仍成立，核心贡献就不完整。

| 编号 | 未定问题 | 与主张的关系 | 依赖 |
| --- | --- | --- | --- |
| Q1 | Agent 判断的持久化表示 | A 的核心对象 | Q2 |
| Q2 | 修订与版本模型 | 维护与有效性追踪的前提 | — |
| Q3 | 写路径：提交契约与维护 | A 的构建与维护成本；AGENTS.md 中“维护”主张 | Q1、Q2 |
| Q4 | 身份修正：合并与拆分 | 构建正确性；Resolve 假设的兜底 | Q2 |
| Q5 | Content kind 列表 | 访问角色与写入校验的前提 | — |
| Q6 | 三分类的两条轴 | 检索契约是否类内统一 | — |
| Q7 | v1 关系回补 | I1、I3 的正确性 | — |
| Q8 | embedding 计算位置 | 实现边界 | — |

## 2. Q1：Agent 判断的持久化表示

**问题。** `A_pred` 产出的 `PredRow` 目前默认只是任务变量。Agent 读完两篇论文后得出“测试切分不同，不可直接比较”，这条判断不属于任何一篇论文，也不是 Observation（没有运行或复现）。它需要能被后续任务检索、复用和复核。

**候选方案。**

| 方案 | 做法 | 问题 |
| --- | --- | --- |
| 沿用 Claim | Claim 增加来源类型：作者主张 / Agent 判断 | Claim 是来源局部的表达，按“来自哪篇论文”组织；跨论文判断的依据跨多篇材料，容易被误归给某篇论文 |
| 新 Content kind：`assessment` | 持久化的 `PredRow`：`{subjects, condition_id, value, basis_refs, rule_ref 或 agent call, scope / applicability, made_by, made_at}` | 增加一个 kind；需要定义何时值得持久化 |

**倾向：新 kind `assessment`。** 理由：

- `PredRow` 已有完整结构，持久化只是把临时值提交为记录，不必重新设计；
- 作者主张与 Agent 判断的来源责任不同，分开后来源查询不会混淆；
- `basis_refs` 固定到 `{id, revision}`，正好支持 Q3 的有效性追踪。

**待定细节。**

- 哪些判断值得持久化：全部 `A_pred` 输出，还是仅经确认、且 `value` 为 $T$ 或 $F$ 的判断？$U$ 是否也记录，以避免重复判断？
- 复用条件：仅当 `basis_refs` 的修订均仍有效、且请求的 `condition_id` 与 scope 一致时，才可在 router 中直接采用。
- 与 Proposition 的关系：Agent 综合出的新命题（不是对指定条件的判断）是否另走 Concept，见 Q6。

## 3. Q2：修订与版本模型

**问题。** 记录被纠正、论文出新版本、alias 被修正时，旧引用和依赖它的判断如何处理？v2 已规定 `ref={id, revision}`，但没有规定修订怎样产生。

| 方案 | 做法 | 适用 |
| --- | --- | --- |
| 原地修改 + revision 计数 | 同一节点，属性更新，revision 递增，历史另存 | 实现简单；旧修订的内容需要从历史中取回 |
| 不可变记录 + `SUPERSEDES` | 新修订是新记录，指向被取代的记录 | 旧引用始终可解析；依赖追踪直接 |

**倾向：按类别分开。**

- **Content（claim、experiment、observation、assessment）：不可变记录 + `SUPERSEDES`。** 它们是判断的依据，`basis_refs` 必须能解析到当时的内容。
- **Entity、Concept：原地修改元数据 + revision 计数。** 身份变化（合并、拆分）不走普通修改，走 Q4 的显式操作，并保留重定向。
- **材料版本**：沿用 SourceRef 中的 `material_ref`，书目记录的 revision 不替代原文版本（已定）。

## 4. Q3：写路径

写入分三件事，现状不同：

| 环节 | 要回答的问题 | 现状 |
| --- | --- | --- |
| 对齐 | 新对象是已有的哪个，还是新的 | **已有机制**：`Resolve` 写模式、作用域 alias 唯一约束、alias 注册 |
| 提交 | 一次写入长什么样，中间件检查什么 | v1 有结构检查（`experiments/e08/src/e08/operator/utils/schema.py`），v2 写入契约未定 |
| 维护 | 修订、撤回、合并之后，依赖它的东西怎么办 | 未设计 |

**提交契约的候选内容。**

- 增量格式：新建 / 关联 / 修订 / 撤回，每项带依据（SourceRef 或 `basis_refs`）与提交者（作者抽取 / Agent 判断 / 人工）。
- 中间件检查：类型与端点；作用域唯一键（冲突默认拒绝，见第 9 节小修项）；必填来源与锚点；结果行粒度声明；引用的修订存在。
- 返回：写入结果、冲突对象、被拒原因、变更记录引用。

**维护的候选机制：已存判断的有效性追踪。** 读路径已经留下抓手：`PredRow` 的 `basis_refs`、`rule_ref`，`value_source`，coverage 调用链。

- 某条记录被 `SUPERSEDES`、某条规则或 alias 被修订时，沿 `basis_refs` / `rule_ref` 找到依赖它的 `assessment`，标为 `stale`，不删除。
- router 复用已存判断前检查有效性；`stale` 的判断按 $U$ 处理并保留历史。
- 这是确定性工作，不需要中间件调用 LLM；是否重新判断由外部决定。

**推进方式：** 不单独开写路径设计线。以第一个真实 I3 实例的入库作为写路径的第一个用例：入库必然产出结果行、锚点、alias 与对齐判断，并能量到主张 A 的构建成本。入库后人为制造一次变更（修正一个 alias，或把一条结果改绑到另一个切分），演练维护。

## 5. Q4：身份修正（合并与拆分）

来自 `docs/open-questions/2026-09-28-entity-lookup-and-identity.md` 的遗留项。D3 采用“alias 准确”的假设后，身份修正就是这一假设失败时的兜底。

| 操作 | 候选做法 |
| --- | --- |
| 合并 | 被并入对象保留为重定向（`MERGED_INTO`），关系迁移到保留对象，alias 合并后重新检查唯一键；依赖两者的 `assessment` 标为 `stale` |
| 拆分 | 无法自动迁移：每条关系、每个 alias 归属哪个新对象由外部 Agent 逐项决定；未决的关系保留在原对象并标记 |

合并与拆分都是显式写操作，带依据与提交者，并产生变更记录。

## 6. Q5–Q7：模型细节

### Q5 Content kind 列表

当前只出现过 claim、experiment、observation。候选列表：

| kind | 含义 | 来源责任 |
| --- | --- | --- |
| `claim` | 论文作者的主张 | 作者，经抽取 |
| `experiment` | 论文报告的实验，下含结果行 | 作者，经抽取 |
| `usage` | 论文对某资源的描述或使用经验（v1 的 ResourceRecord） | 作者，经抽取 |
| `observation` | 对资源或说法的一次第一手检查 | 检查执行者 |
| `assessment` | Agent 对指定条件的判断（Q1） | Agent，经确认 |
| `contribution` | 论文自述的贡献（v1 的 Contribution），是否保留待定 | 作者，经抽取 |

`Context` 的 `usage / descriptions` 角色需按此列表重新对齐。

### Q6 三分类的两条轴

Proposition、Issue 因跨来源共享被归入 Concept，但它们没有名称和别名，按含义匹配，检索方式更接近 Content。分类实际混用了“指称类型”和“是否跨来源共享”两条轴。

| 方案 | 做法 | 代价 |
| --- | --- | --- |
| Concept 内设两种检索子契约 | 术语型（Method、Task、Metric、Protocol）与陈述型（Proposition、Issue） | 违背“类内统一检索契约”，需说明这是有限例外 |
| 陈述型移入 Content | 以 `shared` 标记跨来源共享 | Content 的“来源化”含义被稀释 |
| 增加第四类 | 共享陈述单独成类 | 分类变多，需重新论证 |

暂无倾向，建议在做 I4 / I5 实例时裁决。

### Q7 v1 关系回补

| v1 关系 | 需要它的 intent | 建议 |
| --- | --- | --- |
| `EVALUATES.role`（target / baseline） | I3（区分目标方法与被复现的基线） | 立即回补；同时修 §6.1 `matched` 分支 |
| `ON_TASK` | I3（可比性需要任务设定） | 立即回补 |
| Paper–Method 的角色（proposed / reused / extended / compared） | I1（论文提出的方法与比较的方法） | 回补，表示方式待定：Paper 到 Method 的带角色关系，或 `contribution` 内容 ABOUT 方法 |
| `CITES`、`USES_COMPONENT`、Method `DERIVED_FROM` Resource | I1 资源前提、I4 路线 | 按实例需要再回补 |

## 7. 与读路径设计的衔接

- `assessment` 持久化后，`A_pred` 前应先查询适用的已存判断：命中且有效则以 `value_source=stored` 直接采用。这是“开放判断”类调用点被压缩的主要途径（见 `docs/progress.md` 调用点分类）。
- `Resolve` 的写模式、alias 唯一约束、入库锚点已在 `intents_decompose.md` §5.1.4 写路径前置约定中；本文的提交契约是其展开。

## 8. Q8：embedding 计算位置

AGENTS.md 仍将其列为开放实现边界。现有原型在服务内调用 Qwen3-Embedding-8B。本问题不影响语义判断的责任归属，优先级低；在实现最小原型前定下即可。

## 9. TODO

按顺序推进，一次做一项。

| # | 任务 | 负责 | 依赖 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 提交当前 v2 设计检查点 | 用户 | — | `intents_decompose.md`、`research_design_v2.md` 等改动入库 |
| 2 | `intents_decompose.md` 小修：alias 冲突默认拒绝；声明并版本化规范化函数；`Resolve` 的 type / kind 分开并增加 `none` 状态；§6.1 `matched` 分支加回被测对象与 EVALUATES；I6.2 资源说法来源显式化；回补 `EVALUATES.role`、`ON_TASK`（Q7 前两项） | Codex | 1 | 对应条目在文中可查，`docs/progress.md` 中待决问题可勾销 |
| 3 | 在 e08 现有图与语料中探查 I3 实例候选（两种方法、一个数据集、2–4 篇论文） | Claude（只读） | — | 带回候选组合及各自能测的项，由用户选定 |
| 4 | 讨论确定 Q5（Content kind）与 Q1（`assessment`）的最小版本 | 用户 + Claude | — | 结论写入本文“已定”小节 |
| 5 | 讨论确定 Q2 修订模型的最小版本 | 用户 + Claude | 4 | 同上 |
| 6 | 起草 v2 最小写入契约（新建 / 关联 / 修订，带校验与返回） | Codex | 4、5 | 写入设计文档，覆盖 I3 实例入库所需的操作 |
| 7 | I3 实例入库并手工执行 I3.1–I3.7 | 待定 | 3、6 | 记录主张 B 的四项测量（粒度、条件、Resolve 三级命中、锚点）与主张 A 的“不复用、每次重读”对照数据 |
| 8 | 维护演练：修正一个 alias、改绑一条结果的切分，检查有效性追踪 | 待定 | 7 | `stale` 标记与复用行为符合 Q3 设计 |
| 9 | 用 I4 / I5 实例裁决 Q6 | 待定 | 7 | 选定三分类方案 |
| 10 | 把散落的模型内容收拢到 `docs/designs/v2/graph_model_v2.md`，作为唯一来源 | Codex | 4、5、9 | `intents_decompose.md` 只引用模型，不再重复定义 |
| 11 | 确定 embedding 计算位置 | 用户 | — | 写入 AGENTS.md 或设计文档 |

任务 3、4 可以并行；任务 7 之前不建实验目录、不写正式脚本，探查结果先带回讨论（AGENTS.md 工作节奏第 1 条）。

## 10. 已定

（尚无。讨论确定的事项移到这里，并注明日期。）
