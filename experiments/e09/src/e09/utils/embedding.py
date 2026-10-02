"""向量：Qwen3-Embedding-8B（vLLM，infra/vllm-qwen3-embed/，与 e08 共用同一服务）。

写入侧不加任务说明，查询侧由算子加。`embedding`、`embedding_key` 是检索用的派生属性，不属于 graph_model_v2 的内容属性。

向量的输入文本按类别固定（intents_decompose.md §6.2 "类内相同通道使用同一预处理和编码配置"）：
名称、由 NameKey 装配的 alias，以及该类的文本字段（Entity：description；Concept：definition、scope_note）。
名称与 alias 也编进向量，是为了只给称呼、不给说明文字时语义阶段仍有可比的内容。note 不参与。
"""

import hashlib
import os

import httpx

from ..config import NEO4J_DB
from .graph import driver, q
from .schema import TEXT_FIELDS

EMBED_URL = os.environ.get("EMBED_URL", "http://192.168.163.112:8002/v1/embeddings")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "qwen3-embedding-8b")
EMBED_DIM = 4096
EMBED_BATCH = 32

VECTOR_INDEXES = {"entity_vectors": "Entity", "concept_vectors": "Concept"}   # 名称 -> 主 Label


def ensure_vector_indexes():
    for name, label in VECTOR_INDEXES.items():
        driver.execute_query(
            f"CREATE VECTOR INDEX {name} IF NOT EXISTS FOR (n:{label}) ON n.embedding "
            f"OPTIONS {{indexConfig: {{`vector.dimensions`: {EMBED_DIM}, `vector.similarity_function`: 'cosine'}}}}",
            database_=NEO4J_DB)
    driver.execute_query("CALL db.awaitIndexes(300)", database_=NEO4J_DB)


def embed(texts: list[str]) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        r = httpx.post(EMBED_URL, json={"model": EMBED_MODEL, "input": texts[i:i + EMBED_BATCH]}, timeout=120)
        r.raise_for_status()
        out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
    if any(len(v) != EMBED_DIM for v in out):
        raise ValueError(f"向量维度不是 {EMBED_DIM}")
    return out


def embedding_text(family: str, name: str, aliases: list[str], props: dict) -> str:
    parts = [name]
    if aliases:
        parts.append("Also known as: " + ", ".join(aliases))
    parts += [props[f].strip() for f in TEXT_FIELDS[family] if props.get(f)]
    return "\n".join(parts)


def embedding_key(text: str) -> str:
    return hashlib.sha1(f"{EMBED_MODEL}\n{text}".encode()).hexdigest()[:16]


def sync_embeddings() -> int:
    """给缺向量或向量过期（文本改过、换了模型）的对象补算；返回补算的个数。每次写入图谱后调用。"""
    fields = sorted({f for fs in TEXT_FIELDS.values() for f in fs})
    rows = q(f"""MATCH (n:Entity|Concept)
                 OPTIONAL MATCH (k:NameKey)-[:NAMES]->(n) WHERE k.raw <> n.name
                 WITH n, k ORDER BY k.raw
                 RETURN n.id AS id, CASE WHEN n:Entity THEN 'Entity' ELSE 'Concept' END AS family, n.name AS name,
                        collect(k.raw) AS aliases, n.embedding_key AS key,
                        n {{{', '.join('.' + f for f in fields)}}} AS props
                 ORDER BY id""")
    todo = []
    for r in rows:
        text = embedding_text(r["family"], r["name"], r["aliases"], r["props"])
        if r["key"] != embedding_key(text):
            todo.append({"id": r["id"], "family": r["family"], "text": text, "key": embedding_key(text)})
    for row, v in zip(todo, embed([t["text"] for t in todo])):
        row["v"] = v
    for family in VECTOR_INDEXES.values():
        rows = [{k: t[k] for k in ("id", "key", "v")} for t in todo if t["family"] == family]
        if rows:
            driver.execute_query(f"""UNWIND $rows AS row MATCH (n:{family} {{id: row.id}})
                                     CALL db.create.setNodeVectorProperty(n, 'embedding', row.v)
                                     SET n.embedding_key = row.key""", rows=rows, database_=NEO4J_DB)
    return len(todo)


def main() -> int:
    """建向量索引并补算向量（make embed）；重跑只补算文本变过的对象。"""
    ensure_vector_indexes()
    print(f"{EMBED_MODEL} @ {EMBED_URL}：补算 {sync_embeddings()} 个对象")
    driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
