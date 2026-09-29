"""neo4j-e08 的连接、节点类型、约束与全文索引。"""

import os

from neo4j import GraphDatabase, RoutingControl

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "password"))
NEO4J_DB = os.environ.get("NEO4J_DATABASE", "neo4j")

# 空库时查不存在的属性键会收到 UNRECOGNIZED 类提示，关掉
driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH, notifications_disabled_classifications=["UNRECOGNIZED"])

LABELS = ["Paper", "Contribution", "Method", "MethodConcept", "Task", "Claim", "ClaimConcept", "Issue",
          "Resource", "ResourceRecord", "Experiment", "Metric", "Observation"]   # graph_model.md 的 13 种 Node
SHARED = "Paper|Method|MethodConcept|Task|Resource|Metric"                      # 带 aliases、按名称查找的共享节点
STATEMENTS = "ClaimConcept|Issue|Claim"                                          # 按陈述文本查找；Claim 只查不复用

# 全文索引：名称 -> (节点, 字段, 分词方式)
FULLTEXT = {
    "entity_names": (SHARED, ["name", "title", "aliases"], "standard-no-stop-words"),
    "entity_texts": (SHARED, ["description"], "english"),
    "statement_texts": (STATEMENTS, ["text", "description"], "english"),
}
SCHEMA = [
    *(f"CREATE CONSTRAINT {l.lower()}_id IF NOT EXISTS FOR (n:{l}) REQUIRE n.id IS UNIQUE" for l in LABELS),
    *(f"CREATE FULLTEXT INDEX {name} IF NOT EXISTS FOR (n:{labels}) ON EACH [{', '.join('n.' + f for f in fields)}] "
      f"OPTIONS {{indexConfig: {{`fulltext.analyzer`: '{analyzer}'}}}}"
      for name, (labels, fields, analyzer) in FULLTEXT.items()),
]


def q(cypher: str, **params) -> list[dict]:
    """只读查询的简写。"""
    records, _, _ = driver.execute_query(cypher, params, database_=NEO4J_DB, routing_=RoutingControl.READ)
    return [r.data() for r in records]


def ensure_schema():
    """建约束与全文索引；覆盖的 Label、字段或分词方式与声明不一致的全文索引先删再重建。"""
    existing = {r["name"]: (sorted(r["labels"]), r["properties"], r["analyzer"]) for r in
                q("SHOW FULLTEXT INDEXES YIELD name, labelsOrTypes, properties, options "
                  "RETURN name, labelsOrTypes AS labels, properties, options.indexConfig.`fulltext.analyzer` AS analyzer")}
    for name, (labels, fields, analyzer) in FULLTEXT.items():
        want = (sorted(labels.split("|")), fields, analyzer)
        if name in existing and existing[name] != want:
            print(f"重建 {name}：{existing[name]} -> {want}")
            driver.execute_query(f"DROP INDEX {name}", database_=NEO4J_DB)
    for stmt in SCHEMA:
        driver.execute_query(stmt, database_=NEO4J_DB)
    driver.execute_query("CALL db.awaitIndexes(300)", database_=NEO4J_DB)   # 新建或重建的索引填充完再往下走
