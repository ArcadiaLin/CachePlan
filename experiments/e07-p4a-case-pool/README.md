# E07 — P4A 候选池：为叙事案例寻找构造已知 ground truth 的论文池

状态：计划已商定，p0（语料筛选复制）已实现，其余阶段未开始。

## 背景与目标

承接 [`docs/experiments/2026-09-11-p4a-motivating-case-search.md`](../../docs/experiments/2026-09-11-p4a-motivating-case-search.md)：
P4A 叙事需要真实、可核查的案例，展示论文的相关材料（代码、benchmark、
dataset、引文上下文）如何改变论文发现与候选判断。此前 Kimi 提供的案例建议
（见 [`docs/experiments/2026-09-11-p4a-case-suggestions-kimi.md`](../../docs/experiments/2026-09-11-p4a-case-suggestions-kimi.md)）
都是外部论文，线索作用依赖事后推测。本实验换一个思路：**用 p4a v1 完整处理
过的论文构造候选池**，池内每篇论文的全文、references、citation contexts 和
Layer4 资源记录都在本地，"线索是否改变了判断"可以拿真实数据核查。

用户提出的构造方案（2026-09-11 确认）：

1. 从 961 观测集（952 篇 ACL 2026 论文）中选出种子集；
2. 加第一批噪声：同 venue、表面相关但不满足需求的论文（挑战性负例）；
3. 从 ACL 扩展出去：沿共享 GitHub 仓库 / 共享数据集 / 引文关系连到其他论文；
4. 加第二批噪声：扩展捎带的不相关论文；
5. 从候选池中筛选有"选择转折"的代表性案例。

## 边界（与用户对齐）

- **动机性分析，不是基线评测**。继承 p4a 数据的使用边界：候选池用于寻找和
  核查叙事案例，不作为"P4A 方法是否有效"的对照。
- **layer4 为核心层**；layer4_v2 已从数据副本中移除（原始 tar.gz 未动）。
- **p4a v1 结果不可直接信任**（用户声明，全文见
  [`data/raw/p4a-v1/README.md`](../../data/raw/p4a-v1/README.md)）：
  `resource_records.yml` 中对仓库 / dataset / benchmark 的描述字段是
  **待核查线索**，进入案例证据表前必须复核。这也意味着种子筛选只能用
  结构性信号（资源数量、类型、URL 有无），不能依赖描述字段的语义正确性。
- 语料外论文（扩展边指向但不在 3321 篇内的）默认只记为"线索指向"，
  只对最终选中的案例补做核查。
- 需求标尺先复用案例寻找文档中的候选 A / B，允许从池子里长出新需求。

## 数据基础

源：`data/raw/p4a-v1/`（1.3 GB，3321 篇 ACL 2025+2026 论文的
mineru / layer4 / cite 三层产物，覆盖率见该目录 README）。

p0 产物：`data/processed/e07/corpus/<paper_id>/{mineru,layer4,cite}/`，
即 961 观测集 952 篇论文的三层数据子集。种子与噪声都从池内选，
因此候选池的一切判断材料都是本地的、可复查的。

## 阶段计划

| | 回答什么 | 状态 |
|---|---|---|
| p0 | 把 952 篇观测集论文的数据从全量副本中筛出、复制、校验 | 已实现 |
| p1 | 资源关联表：从 952 篇的 resource_records 抽出 (paper, resource_url, kind) 边，构建"共享资源"图 | 未开始 |
| p2 | 种子集与噪声 1：按结构性信号选种子；同 venue/track 内取挑战性负例 | 未开始 |
| p3 | 扩展：沿共享资源边 + cite_contexts 引文边连出候选，附第二批噪声 | 未开始 |
| p4 | 案例筛选：用候选 A/B 的需求条件逐条对照，产出证据表与案例叙述 | 未开始 |

p2–p4 的具体规则（种子阈值、噪声比例、扩展边优先级）在 p1 的图结构
看清楚之后再定，不在本计划里提前写死。

## 运行

```bash
cd experiments/e07-p4a-case-pool
make setup    # 委派给仓库根
make p0       # 筛选复制 952 篇（幂等：先清空再复制，带不变量校验）
make verify   # 重跑 p0 校验
```

## 环境

仓库根 uv workspace 成员，`dependencies = []`，与 e01 同一条约定。
**不要在本目录直接跑 `uv sync`**，用 `make setup`。
