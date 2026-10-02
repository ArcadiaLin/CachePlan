"""Get(refs)：按对象映射装配视图（intents_decompose.md §4.1）。

只装配对象本身：主 Label、kind、属性、由 NameKey 装配的 aliases 与 identifiers；不展开关系，那是 Context / Search 的事。
对象上不存 aliases 列表（graph_model_v2.md 第 5 节），读取时由 NameKey 拼出：`raw` 与对象 `name` 不同的键就是 alias。
"""

from ..utils.graph import q

DERIVED = ("embedding", "embedding_key")   # 检索用的派生属性，不进视图


def get(refs: list[str]) -> dict:
    """返回 {items: [视图], missing: [库里没有的 ref]}；items 按输入顺序。"""
    rows = q("""UNWIND $refs AS ref
                MATCH (n:Entity|Concept {id: ref})
                OPTIONAL MATCH (k:NameKey)-[:NAMES]->(n)
                WITH n, k ORDER BY k.raw
                RETURN n.id AS ref, labels(n) AS labels, n {.*, embedding: null} AS props,
                       collect(CASE WHEN k IS NULL THEN null
                                    ELSE {raw: k.raw, key: k.key, status: k.status} END) AS name_keys""",
             refs=list(refs))
    found = {}
    for r in rows:
        family = "Entity" if "Entity" in r["labels"] else "Concept"
        props = {k: v for k, v in r["props"].items() if k not in DERIVED}
        name = props.pop("name")
        found[r["ref"]] = {
            "ref": props.pop("id"), "family": family, "kind": next(l for l in r["labels"] if l != family),
            "name": name, "aliases": [k["raw"] for k in r["name_keys"] if k["raw"] != name],
            "identifiers": props.pop("identifiers", []), "properties": props, "name_keys": r["name_keys"],
        }
    return {"items": [found[r] for r in refs if r in found], "missing": [r for r in refs if r not in found]}
