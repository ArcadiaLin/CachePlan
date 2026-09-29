"""find_entities：按原文称呼查找已有的共享节点（Paper、Method、MethodConcept、Task、Resource、Metric）。

Stage 1 标识解析命中的置顶；Stage 2 三路召回按 RRF 融合。只返回候选与证据，不做判断。

    uv run python -m e08.operator.find_entities ETTh1
    uv run python -m e08.operator.find_entities RevIN -d "reversible instance normalization ..." -t Method
"""

import argparse
import json

from .utils.embedding import embed
from .utils.fusion import POOL, TOP_N, fuse, normalize, tokens
from .utils.graph import SHARED, q

ENTITY_INSTRUCT = ("Instruct: Given a mention of a dataset, method, task or metric in a research paper, "
                   "retrieve the entry that refers to the same object\nQuery:")
TYPE_FILTER = "($type IS NULL OR $type IN labels(node))"


def _identifier(mention, entity_type, pool):
    rows = q(f"""CYPHER 25
                 WITH toLower(trim($m)) AS m, $mn AS mn
                 MATCH (node:{SHARED}) WHERE {TYPE_FILTER}
                 WITH node, m, mn, coalesce(node.name, node.title) AS nm, coalesce(node.aliases, []) AS al
                 WITH node, CASE
                     WHEN toLower(trim(nm)) = m THEN 'name'
                     WHEN ANY(a IN al WHERE toLower(trim(a)) = m) THEN 'alias'
                     WHEN mn <> '' AND string.regexReplace(toLower(nm), '[^a-z0-9]', '') = mn THEN 'name (normalized)'
                     WHEN mn <> '' AND ANY(a IN al WHERE string.regexReplace(toLower(a), '[^a-z0-9]', '') = mn)
                         THEN 'alias (normalized)'
                 END AS match
                 WHERE match IS NOT NULL
                 RETURN node.id AS id, match ORDER BY match, id LIMIT $pool""",
             m=mention, mn=normalize(mention), type=entity_type, pool=pool)
    return [{"id": r["id"], "match": r["match"]} for r in rows]


def _fulltext(index, query, entity_type, pool):
    if not query:
        return []
    return q(f"""CALL db.index.fulltext.queryNodes('{index}', $query) YIELD node, score
                 WHERE {TYPE_FILTER}
                 RETURN node.id AS id, score ORDER BY score DESC LIMIT $pool""",
             query=query, type=entity_type, pool=pool)


def _semantic(text, entity_type, pool):
    v = embed([ENTITY_INSTRUCT + text])[0]
    # 类型过滤在索引之后做，所以先多取一些
    return q(f"""CYPHER 25
                 MATCH (node) SEARCH node IN (VECTOR INDEX entity_vectors FOR $v LIMIT $k) SCORE AS score
                 WITH node, score WHERE {TYPE_FILTER}
                 RETURN node.id AS id, score ORDER BY score DESC LIMIT $pool""",
             v=v, k=pool * 5, type=entity_type, pool=pool)


def recall_channels(mention, description=None, entity_type=None, pool=POOL) -> dict[str, list[dict]]:
    """召回：Stage 1 的 identifier 与 Stage 2 的三个通道，各自的有序结果 [{id, score | match}, ...]。"""
    return {
        "identifier": _identifier(mention, entity_type, pool),
        "lexical_name": _fulltext("entity_names", " ".join(f"{t} {t}* {t}~" for t in tokens(mention)), entity_type, pool),
        "lexical_text": _fulltext("entity_texts", " ".join(tokens(description or "")), entity_type, pool),
        "semantic": _semantic(f"{mention}: {description}" if description else mention, entity_type, pool),
    }


def entity_info(ids: list[str]) -> dict:
    """候选的定义与一跳邻接关系（箭头表示方向）。"""
    rows = q("""MATCH (node) WHERE node.id IN $ids
                OPTIONAL MATCH (node)-[r]-(other)
                RETURN node.id AS id, labels(node) AS labels, coalesce(node.name, node.title) AS name,
                       node.aliases AS aliases, node.description AS description, node.note AS note,
                       [x IN collect(CASE WHEN r IS NULL THEN null
                                          WHEN startNode(r) = node THEN type(r) + ' → ' + coalesce(other.name, other.title, other.id)
                                          ELSE type(r) + ' ← ' + coalesce(other.name, other.title, other.id) END)
                        WHERE x IS NOT NULL] AS neighbors""", ids=ids)
    return {r["id"]: r for r in rows}


def find_entities(mention: str, description: str | None = None, entity_type: str | None = None,
                  n: int = TOP_N) -> list[dict]:
    """召回 → 融合 → 截断。返回前 n 个候选，每个带实体信息与 evidence；不给置信度。"""
    top = fuse(recall_channels(mention, description, entity_type))[:n]
    info = entity_info([i for i, _, _ in top])
    return [{**info[i], "evidence": ev} for i, ev, _ in top]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("mention")
    p.add_argument("-d", "--description")
    p.add_argument("-t", "--type", dest="entity_type")
    p.add_argument("-n", type=int, default=TOP_N)
    a = p.parse_args()
    print(json.dumps(find_entities(a.mention, a.description, a.entity_type, a.n), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
