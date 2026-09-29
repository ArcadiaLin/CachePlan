"""向量：Qwen3-Embedding-8B（vLLM，infra/vllm-qwen3-embed/）。写入侧不加任务说明，查询侧由各算子加。"""

import hashlib
import os

import httpx

from .graph import NEO4J_DB, SHARED, STATEMENTS, driver, q

EMBED_URL = os.environ.get("EMBED_URL", "http://192.168.163.112:8002/v1/embeddings")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "qwen3-embedding-8b")
EMBED_DIM = 4096
EMBED_BATCH = 32

VECTOR_SCHEMA = [
    f"CREATE VECTOR INDEX {name} IF NOT EXISTS FOR (n:{labels}) ON n.embedding "
    f"OPTIONS {{indexConfig: {{`vector.dimensions`: {EMBED_DIM}, `vector.similarity_function`: 'cosine'}}}}"
    for name, labels in [("entity_vectors", SHARED), ("statement_vectors", STATEMENTS)]
]


def ensure_vector_indexes():
    for stmt in VECTOR_SCHEMA:
        driver.execute_query(stmt, database_=NEO4J_DB)


def embed(texts: list[str]) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        r = httpx.post(EMBED_URL, json={"model": EMBED_MODEL, "input": texts[i:i + EMBED_BATCH]}, timeout=120)
        r.raise_for_status()
        out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
    assert all(len(v) == EMBED_DIM for v in out)
    return out


def embedding_text(labels: list[str], props: dict) -> str | None:
    """节点用于向量的输入文本；没有可用文本时返回 None。note 不参与。"""
    if labels[0] in STATEMENTS.split("|"):
        parts = [props.get("text"), props.get("description") if labels[0] == "Issue" else None]
        return "\n".join(p.strip() for p in parts if p) or None
    name = props.get("name") or props.get("title")
    if not name:
        return None
    parts = [name]
    if props.get("aliases"):
        parts.append("Also known as: " + ", ".join(props["aliases"]))
    if props.get("description"):
        parts.append(props["description"].strip())
    return "\n".join(parts)


def embedding_key(text: str) -> str:
    return hashlib.sha1(f"{EMBED_MODEL}\n{text}".encode()).hexdigest()[:16]


def sync_embeddings() -> int:
    """给缺向量或向量过期的节点补算；返回补算的节点数。每次写入图谱后调用。"""
    rows = q(f"""MATCH (n) WHERE n:{SHARED} OR n:{STATEMENTS}
                 RETURN n.id AS id, labels(n) AS labels, n.embedding_key AS key,
                        n {{.name, .title, .aliases, .description, .text}} AS props""")
    todo = []
    for r in rows:
        text = embedding_text(r["labels"], r["props"])
        if text and r["key"] != embedding_key(text):
            todo.append({"id": r["id"], "text": text, "key": embedding_key(text)})
    if todo:
        for row, v in zip(todo, embed([t["text"] for t in todo])):
            row["v"] = v
        driver.execute_query("""UNWIND $rows AS row MATCH (n {id: row.id})
                                CALL db.create.setNodeVectorProperty(n, 'embedding', row.v)
                                SET n.embedding_key = row.key""",
                             rows=[{k: t[k] for k in ("id", "key", "v")} for t in todo], database_=NEO4J_DB)
    return len(todo)
