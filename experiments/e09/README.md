# E09 · v2 数据模型的真实论文入库

按 [Graph Model V2](../../docs/designs/v2/graph_model_v2.md) 把真实论文入库，检验
[Workload 拆解](../../docs/designs/v2/intents_decompose.md) 中的访问契约。第一个实例是
I3（实验比较）：DLinear 与 PatchTST。

E08 是 v1 图谱，保留不动；E09 用独立的数据目录与 Neo4j 实例。

## 环境

| 组件 | 位置 | 说明 |
| --- | --- | --- |
| Python 环境 | 仓库根的 uv workspace（本目录是成员） | notebook 内核同样用根 `.venv` |
| Neo4j（v2 图谱） | `infra/neo4j-e09/` | bolt 7687，浏览器 7474 |
| Neo4j（v1 图谱） | `infra/neo4j-e08/` | 端口相同，同一时间只起一个 |
| 共同配置 | `src/e09/config.py` | 路径与连接参数，脚本与 notebook 共用 |

    make setup        # 第一次，或依赖变化后
    make neo4j-up     # 不在 docker 组时：make neo4j-up DOCKER="sudo docker"
    make check        # 自检：材料与种子目录、连库、确认不是 v1 库
    make lab          # JupyterLab，工作目录为 notebooks/

## 数据

    data/raw/e09-paper-knowledge/
      papers.yml, status.yml, runs/   # 复制自 e08（2026-10-02），材料准备的原始记录
      papers/<citekey>/paper.md …     # 论文材料，复制自 e08，只读
      seeds/                          # v2 种子（版本管理），格式见 seeds/README.md

`papers/`、`runs/` 等材料不进版本管理，只有 `seeds/` 被跟踪。

## 布局

    notebooks/            探索面：按步骤推进入库与检验
    notebooks/_scratch/   notebook 导出的中间结果，不进版本管理
    src/e09/              共同配置、环境自检；入库流水线确定后提升到这里

## 现在还不是什么

还没有入库流水线。入库表单、编译规则与 `Commit` 校验在讨论确定后再写进
`src/e09/`，并给 Makefile 加上可失败的复现目标。notebook 只读写
`data/raw/e09-paper-knowledge/` 与 neo4j-e09，不能成为文档引用数字的唯一来源（AGENTS.md）。
