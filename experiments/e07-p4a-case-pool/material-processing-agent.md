# 材料加工 Agent：关联材料的通用加工与消歧算子设计

状态：2026-09-12 讨论定稿的设计备忘。源于本轮资源消歧实践
（`registry/resource_disambiguation.yml`）与 KATS 消歧机制的对照阅读。
尚未实现；实现时以本文为准核对接口。

## 定位

项目叙事：将论文及其关联材料转化为**可核查、可复用的研究产物**
（agent-ready artifacts），评价它们对后续研究行动的帮助。datasets 是当前
可识别、可加工的第一类关联材料；其消歧方式是通用材料加工方式的一部分，
由 Agent 借助工具完成，而非离线清洗脚本。

消歧算子在系统中的角色：文献资源库构建管线里的**实体消解环节**——
判定一条材料提及应"挂靠既有库存条目"还是"新建条目"。同一算子骨架后续
复用到 model、code repo 乃至论文身份（引文消解）。

## 库存（inventory）：系统的持久状态

每个条目是一个 agent-ready artifact 的雏形：

```
material:
  identity:    规范名 + 类型 + 别名表        # 消歧的产物
  evidence:    一手来源链接 + 核查状态        # "可核查"的载体
  boundaries:  版本/子集/访问条件/适用场景     # "适用边界"的载体
  relations:   subset_of / version_of / distinct_from / introduced_by
  provenance:  谁（agent/人）何时依据什么建立或修改
```

`registry/resource_disambiguation.yml` 是库存的 v0 手工快照。叙事与字段的
对应：可核查 = evidence + 必填 sources 的返回契约；适用边界 = boundaries
（如 MATH-500 ⊂ MATH、LoCoMo 公开版仅 10 段对话）；对后续行动的帮助 =
下游选择是否被改变，接回案例池的"选择转折"。

## Agent 工具面

- `lookup(name)` / `find_candidates(mention)`：先查库存再查外部；已有决策
  （含负例日志，见下）直接复用。
- `read_mention_contexts(paper_id, name)`：本地证据判读，不花外部调用
  （PRISM 同名异源就是这样解决的）。
- `web_search(query)` / `fetch_page(url)`：取一手来源（论文、官方仓库、
  HF 页面）。
- `add_material / add_alias / mark_relation / flag_uncertain`：所有写入带
  provenance，落为版本化、可 git diff review 的条目；**不允许静默合并**。

## 加工循环（单个材料提及）

1. 库存命中？→ 命中则补别名/关系；
2. 未命中 → 本地证据判读；
3. 仍存疑 → web 核查（一手来源优先）；
4. 决策：新建 / 挂靠 / 拆分 / 标 uncertain；
5. 确定性校验器把守入库：schema、id 唯一、对语料的覆盖校验、与上一版 diff。

消歧 = 步骤 1–4 中"命中还是新建"的判定。

## 两种运行形态，同一套工具契约

- **批量构建态**：编排者分诊（频次分层、知名资源免核查——预算控制在此），
  存疑材料扇出给并行 worker（agent swarm），裁决者收拢入库。worker 任务
  自包含：原始名字 + 语料证据片段 + 具体问题；返回结构化记录
  （canonical_name/year/org/urls/relations/confidence/sources），sources
  必填。单项失败不阻塞批次，查不到标 uncertain。
- **增量维护态**：新论文进来，单 agent 携同一套工具跑加工循环。

批量态攒下的库存（含负例日志）直接是增量态的先验。

## 从 KATS 借入与有意保持的差异

对照 `references/repos/KATS`（graph/dataset_merger.py）：

借入：
- **负例决策日志**：判过"不同"的点对随库存版本化持久化，重跑/增量不重判；
- **增量 API 是一等公民**（对应其 merge_new_datasets）；
- **裁判失败向保守方向降级**（失败 = 不合并）。

有意保持的差异：
- KATS 裁判限定 "based ONLY on the information provided"，无法纠正抽取
  错误；本算子允许出界 web 核查（MATH-500 出处、Minerva Math = OCWCourses
  等发现依赖于此）；
- 身份粒度是**显式可配策略**：KATS 把版本/子集判为不同实体；我们实体保持
  粗粒度、版本留在 usage 记录。算子化时做成参数而非写死；
- 召回通道：KATS 用 embedding blocking，能抓到无语词重叠的别名；我们先用
  词法归一化 + 前缀近重复（本批语料已够），embedding 通道留作可选 blocker；
- 可审查性：KATS 合并进并查集后无 review 面，false positive 沿传递闭包
  扩散；我们要求合并决策落在可 diff 的 YAML 上。

## 待定的显式参数

- 分诊阈值（本次手工实践拍的：≥3 篇进核查层、26 项送 swarm）；
- "知名资源免核查"白名单的来源与维护方式；
- 裁决阶段的人工 review 界面（当前 = YAML + git diff）。

## 下一步（已提议，待批准）

以现有 registry 为库存 v0，实现最小工具集（lookup / read_mention_contexts /
web_search / fetch_page / 写入提案），用 2 篇提及的未注册名
（govreport、mlebench、orbench……）回测：agent 能否独立把它们加工成合格
库存条目。既是原型验证，也直接扩充库存。
