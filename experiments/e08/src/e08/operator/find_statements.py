"""find_statements：按命题或问题查找 ClaimConcept、Issue，以及各论文的 Claim（只查不复用）。

两路召回按 RRF 融合，没有标识解析。只返回候选与证据，不做判断。

    uv run python -m e08.operator.find_statements "A simple linear model outperforms ..."
    uv run python -m e08.operator.find_statements "Are Transformers effective ...?" -d "..." -k Issue
"""

import argparse
import json

from .utils.embedding import embed
from .utils.fusion import POOL, TOP_N, fuse, tokens
from .utils.graph import q

STATEMENT_INSTRUCT = ("Instruct: Given a claim or research question from a paper, "
                      "retrieve statements that express the same proposition or ask the same question\nQuery:")
KIND_FILTER = "($kind IS NULL OR $kind IN labels(node))"


def recall_statement_channels(text, description=None, kind=None, pool=POOL) -> dict[str, list[dict]]:
    query_text = f"{text}\n{description}" if description else text
    lexical = q(f"""CALL db.index.fulltext.queryNodes('statement_texts', $query) YIELD node, score
                    WHERE {KIND_FILTER}
                    RETURN node.id AS id, score ORDER BY score DESC LIMIT $pool""",
                query=" ".join(tokens(query_text)), kind=kind, pool=pool) if tokens(query_text) else []
    v = embed([STATEMENT_INSTRUCT + query_text])[0]
    semantic = q(f"""CYPHER 25
                     MATCH (node) SEARCH node IN (VECTOR INDEX statement_vectors FOR $v LIMIT $k) SCORE AS score
                     WITH node, score WHERE {KIND_FILTER}
                     RETURN node.id AS id, score ORDER BY score DESC LIMIT $pool""",
                 v=v, k=pool * 5, kind=kind, pool=pool)
    return {"lexical_text": lexical, "semantic": semantic}


def statement_info(ids: list[str]) -> dict:
    """候选的陈述、所属论文（Claim）与一跳邻接关系；对端没有名称时显示截短的 text。"""
    rows = q("""MATCH (node) WHERE node.id IN $ids
                OPTIONAL MATCH (paper:Paper)-[:HAS_CLAIM]->(node)
                OPTIONAL MATCH (node)-[r]-(other)
                WITH node, collect(DISTINCT paper.id) AS papers, r, other,
                     coalesce(other.name, other.title, left(other.text, 60), other.id) AS other_name
                RETURN node.id AS id, labels(node) AS labels, node.text AS text,
                       node.description AS description, node.note AS note, papers,
                       [x IN collect(CASE WHEN r IS NULL THEN null
                                          WHEN startNode(r) = node THEN type(r) + ' → ' + other_name
                                          ELSE type(r) + ' ← ' + other_name END)
                        WHERE x IS NOT NULL] AS neighbors""", ids=ids)
    return {r["id"]: {**r, "reusable": r["labels"][0] != "Claim"} for r in rows}


def find_statements(text: str, description: str | None = None, kind: str | None = None,
                    n: int = TOP_N) -> list[dict]:
    """两路召回 → RRF 融合 → 截断。Claim 标 reusable=False 并带所属论文；不给置信度。"""
    top = fuse({"identifier": [], **recall_statement_channels(text, description, kind)})[:n]
    info = statement_info([i for i, _, _ in top])
    return [{**info[i], "evidence": ev} for i, ev, _ in top]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("text")
    p.add_argument("-d", "--description")
    p.add_argument("-k", "--kind", choices=["ClaimConcept", "Issue", "Claim"])
    p.add_argument("-n", type=int, default=TOP_N)
    a = p.parse_args()
    print(json.dumps(find_statements(a.text, a.description, a.kind, a.n), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
