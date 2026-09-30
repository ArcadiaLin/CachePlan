"""e08 论文知识库的候选操作与算子，设计见 docs/designs/operator.md。

一个操作一个脚本，可在 notebook 中导入，也可在命令行运行：

    uv run python -m e08.operator.find_entities ETTh1
    uv run python -m e08.operator.find_statements "..." --kind Issue

目录下只放直接作为算子的脚本；共用的基础设施在 utils/：
    utils/graph.py      连接、节点类型、约束与全文索引
    utils/embedding.py  向量计算、向量索引与补算
    utils/ids.py        id 分配
    utils/fusion.py     分词、归一化与 RRF 融合
    utils/schema.py     graph_model 的结构约束（写入前检查）
    utils/anchor.py     原文锚点的解析、检查与读取

包放在 e08 下而不是顶层：顶层的 `operator` 会遮蔽标准库同名模块。
"""
