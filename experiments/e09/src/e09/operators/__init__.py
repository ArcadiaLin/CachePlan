"""中间件算子：一个算子一个文件，文件名即设计中的算子名（docs/designs/v2/intents_decompose.md §4.1）。

已实现：commit（目前只接受种子增量）。
待实现：resolve、get、search、context、experiments、evidence、implementations，以及 llm_operator.md 的 decide。
"""
