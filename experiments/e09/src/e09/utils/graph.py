"""neo4j-e09 的连接与约束。"""

from neo4j import GraphDatabase, RoutingControl

from ..config import NEO4J_AUTH, NEO4J_DB, NEO4J_URI
from .schema import CONSTRAINTS

# 空库时查不存在的属性键或 Label 会收到 UNRECOGNIZED 类提示，关掉
driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH, notifications_disabled_classifications=["UNRECOGNIZED"])


def q(cypher: str, **params) -> list[dict]:
    """只读查询的简写。"""
    records, _, _ = driver.execute_query(cypher, params, database_=NEO4J_DB, routing_=RoutingControl.READ)
    return [r.data() for r in records]


def ensure_schema():
    """建约束；全部 IF NOT EXISTS，重跑无副作用。"""
    for stmt in CONSTRAINTS:
        driver.execute_query(stmt, database_=NEO4J_DB)
