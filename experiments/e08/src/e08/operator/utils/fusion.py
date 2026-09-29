"""检索算子共用：参数、分词、归一化与 RRF 融合。"""

import re

POOL = 20      # 每个通道召回的条数
RRF_K = 10     # 每路只有 POOL 条，常用的 60 会让名次几乎不起作用
TOP_N = 5


def tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def normalize(s: str) -> str:
    """Stage 1 的宽松比较：只保留字母和数字的小写串。与 Cypher 里的 string.regexReplace 同一规则。"""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def fuse(channels: dict[str, list[dict]], k=RRF_K) -> list[tuple[str, dict, float]]:
    """融合：identifier 命中的在前，其余按其他通道的 RRF。

    channels 必须含 "identifier"（可为空）。返回 [(id, evidence, rrf)]，evidence = {通道: {rank, score | match}}。
    """
    evidence = {}
    for ch, rows in channels.items():
        for rank, r in enumerate(rows, 1):
            evidence.setdefault(r["id"], {})[ch] = {"rank": rank, **{k_: r[k_] for k_ in ("score", "match") if k_ in r}}
    rrf = {i: sum(1 / (k + e["rank"]) for ch, e in ev.items() if ch != "identifier") for i, ev in evidence.items()}
    pinned = [r["id"] for r in channels["identifier"]]
    rest = sorted((i for i in evidence if i not in pinned), key=lambda i: (-rrf[i], i))
    return [(i, evidence[i], rrf[i]) for i in pinned + rest]
