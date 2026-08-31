#!/usr/bin/env python3
"""Adjudicate compare_v1_v2 misses: fuzzy-name & URL rescue, then categorize."""
import json, re, sys, yaml
from pathlib import Path
from collections import Counter

V1 = Path("/srv/datasets/p4a/data/processed/layer4/2026/acl")
V2 = Path("/srv/datasets/p4a/data/processed/layer4_v2/2026/acl")

def load(root, pid):
    p = root / pid / "resource_records.yml"
    if not p.exists():
        return []
    return [
        {"name": str(r.get("name") or ""),
         "url": str((r.get("access") or {}).get("url") or "").rstrip("/").lower()}
        for w in (yaml.safe_load(p.read_text()) or [])
        for r in [w.get("resource_record") or {}]
    ]

# Superscript/subscript digits → plain digits, so "Re² Bench" and "Re^2 Bench"
# normalize to the same token instead of "rebench" vs "re2bench".
_SUP_SUB = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉", "01234567890123456789")


def norm(s):
    s = s.translate(_SUP_SUB).lower()
    s = re.sub(r"\b(framework|series|dataset|benchmark|corpus|model)\b", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)

GENERIC = {"vllm", "deepspeed", "transformers", "huggingfacetransformers", "scikitlearn",
           "spacy", "langchain", "ollama", "bun", "ethersjsv6", "anvilfoundry", "umap",
           "stopes", "lme4", "ggplot2", "bm25", "openface", "autogen", "sam2",
           "groundingdino", "clip", "aizynthfinder", "askcos", "molscore",
           "gpt4ominitts", "nltk", "pytorch", "numpy"}
ARTIFACTS = {"re3", "re2bench", "cap", "bioproproject",
             "awesomemultimodalmathematicalreasoningperceptionalignmentreasoning"}

rep = json.load(open(sys.argv[1]))
counts = Counter()
other_real = []
for p in rep["papers"]:
    if not p["missing_in_v2"]:
        continue
    pid = p["paper_id"]
    v2all = load(V2, pid)
    v1all = load(V1, pid)
    v2norms = [norm(r["name"]) for r in v2all]
    v2urls = {r["url"] for r in v2all if r["url"]}
    for m in p["missing_in_v2"]:
        parts = [norm(x) for x in re.split(r"[/,()]| and ", m["name"]) if norm(x)]
        if any(len(pt) >= 4 and (pt in vn or vn in pt)
               for pt in parts for vn in v2norms if vn):
            counts["rescued_fuzzy_name"] += 1
            continue
        v1rec = next((r for r in v1all if r["name"] == m["name"]), None)
        if v1rec and v1rec["url"] and v1rec["url"] in v2urls:
            counts["rescued_url"] += 1
            continue
        n = norm(m["name"])
        if n in ARTIFACTS:
            counts["artifact_verified_in_v2"] += 1
        elif n in GENERIC:
            counts["generic_dep_by_design"] += 1
        elif n.startswith(("gpt4", "gpt35", "o3mini", "o4mini", "commandr",
                           "qwenturbo", "claude3")):
            counts["closed_api_model_naming"] += 1
        else:
            counts["real_miss"] += 1
            other_real.append((pid, m["kind"], m["name"], m["relation"]))

total = rep["summary"]["v1_resources"]
matched = sum(p["matched"] for p in rep["papers"])
real = counts["real_miss"]
print(json.dumps({
    "papers": rep["summary"]["papers"],
    "v1_resources": total,
    "v2_resources": rep["summary"]["v2_resources"],
    "raw_matched": matched,
    "raw_recall": round(matched / total, 3),
    "miss_buckets": dict(counts),
    "adjudicated_recall": round((total - real) / total, 3),
    "real_miss_relations": dict(Counter(r for _, _, _, r in other_real)),
}, indent=2, ensure_ascii=False))
print("\n-- real misses (introduced first) --")
for pid, k, n, r in sorted(other_real, key=lambda x: (x[3] != "introduced", x[0])):
    print(f"{r:11s} {pid}  {k}/{n}")
