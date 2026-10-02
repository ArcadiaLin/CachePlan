"""graph_model_v2.md 的机器可读部分：kind、命名空间、关系端点与 id 前缀。

与 docs/designs/v2/graph_model_v2.md 不一致时以文档为准，改这里。
目前只覆盖种子用到的部分；Content、ResultUnit 等等入库表单确定后再加。
"""

KINDS = {"Entity": ["Paper", "Dataset", "Split", "Code", "Model", "Benchmark"],         # §2.1
         "Concept": ["Method", "Task", "Metric", "Protocol", "Issue", "Proposition"]}   # §3.1
FAMILY = {k: f for f, ks in KINDS.items() for k in ks}                                 # kind -> 主 Label
SEED_KINDS = {"Entity": {"Dataset", "Model", "Benchmark"}, "Concept": {"Task", "Method", "Metric"}}   # 种子只预置这些
REQUIRED = {"Entity": "description", "Concept": "definition"}
NAMESPACES = {"arxiv": True, "doi": True, "s2": True, "url": False}   # 命名空间 -> 是否唯一（§2.4）
REL_RULES = {   # 种子用到的关系 -> (起点主 Label, 终点主 Label, 终点 kind 限制)；§6
    "BROADER": ("Concept", "Concept", None), "OVERLAPS_WITH": ("Concept", "Concept", None),
    "PART_OF": ("Entity", "Entity", None), "FOR_TASK": ("Entity", "Concept", "Task")}
SYMMETRIC = {"OVERLAPS_WITH"}   # 语义对称，不分方向
FORM_ONLY = {"aliases"}         # 表单字段：注册为 NameKey，不写进对象

# id 形如 <前缀>_<4 位序号>
PREFIX = {"Paper": "paper", "Dataset": "dataset", "Split": "split", "Code": "code", "Model": "model",
          "Benchmark": "bench", "Method": "method", "Task": "task", "Metric": "metric", "Protocol": "protocol",
          "Issue": "issue", "Proposition": "prop"}

# NameKey 不存成对象上的 aliases 列表，正是为了让唯一约束作用在单个字符串上（第 5 节）
CONSTRAINTS = [
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (n:Concept) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT namekey_key IF NOT EXISTS FOR (k:NameKey) REQUIRE k.key IS UNIQUE",
]
