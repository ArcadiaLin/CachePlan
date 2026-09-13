"""p1：从 p0 语料建立可追溯的 paper–resource 边，并整理引文锚点入口。

输入（只读）：
  data/processed/e07/corpus/<paper_id>/layer4/{resource_records,paper_record}.yml
  data/processed/e07/corpus/<paper_id>/cite/{references,cite_contexts}.jsonl
  experiments/e07-p4a-case-pool/registry/resource_disambiguation.yml

输出（--out-root 下）：
  p1/resource_edges.jsonl      每行一条 paper–resource 边
  p1/cite_anchors.jsonl        每行一条带锚点（arxiv/doi/url）的引用入口
  p1/unregistered_names.jsonl  未注册资源名清单（回喂 registry，本脚本不改 registry）
  p1_summary.json              对账与统计报告

口径（与 registry 口径声明一致）：
  - registry 只做"名字 -> 规范身份"消歧；relation_type 是 v1 线索，原样保留
    并标 unverified，本阶段不核查关系语义；
  - url_key 只是附加锚点，不做跨 norm_key 的静默合并；撞 key 现象只进报告；
  - registry 未覆盖的名字一律 self_identity 通过；split 规则按原始拼写拆，
    拼写未命中（如 prism 的 _by_context）标 split_unresolved 供人工确认；
  - 语料内引文匹配只做 arxiv id / aclanthology URL 精确匹配，不做模糊匹配。

不变量（任一不满足即失败退出）：
  - 语料论文数恰为 952（--limit 时为前 N 篇）；
  - 每篇论文 resource_records.yml / references.jsonl / cite_contexts.jsonl
    可解析；
  - 对账：资源记录总数 == 边数 + 噪声剔除数。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import yaml

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "data/processed/e07"
REGISTRY = REPO / "experiments/e07-p4a-case-pool/registry/resource_disambiguation.yml"

EXPECTED_PAPERS = 952
ACLAN_RE = re.compile(r"aclanthology\.org/(?:[^/]+/)*(\d{4}\.[a-z0-9-]+)", re.I)
ARXIV_VER_RE = re.compile(r"v\d+$")


def git_rev() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def norm_name(s: str) -> str:
    """与 registry 的 corpus_keys 口径一致：小写、去非字母数字。"""
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def norm_arxiv(a: str) -> str:
    return ARXIV_VER_RE.sub("", a.strip().lower())


def url_key(url: str) -> str:
    """URL 归一化锚点：去 scheme、www.、尾部斜杠与 .git；只作信号，不做合并依据。"""
    u = (url or "").strip()
    if not u:
        return ""
    try:
        parts = urlsplit(u if "//" in u else f"//{u}")
        host = (parts.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = parts.path.rstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return f"{host}{path}" if host else ""
    except ValueError:
        return ""


class Registry:
    """resource_disambiguation.yml 的名字 -> 规范身份映射。"""

    def __init__(self, path: Path) -> None:
        reg = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.key2id: dict[str, str] = {}
        for entry in reg["canonical_resources"]:
            for k in entry.get("corpus_keys", []):
                # 同名异源条目（如 prism 两个身份）允许共享 corpus_key；
                # 它们由 split_within_key 在 key2id 之前拦截，此表保留先见者。
                self.key2id.setdefault(k, entry["id"])
        for k, v in reg["merge_map"].items():
            if k in self.key2id and self.key2id[k] != v:
                raise ValueError(f"registry merge_map 冲突: {k}")
            self.key2id[k] = v
        self.split_rules: dict[str, dict] = reg["split_within_key"]
        self.noise_keys: set[str] = set(reg["noise_keys"])
        self.canonical_ids: set[str] = {e["id"] for e in reg["canonical_resources"]}

    def resolve(self, raw_name: str) -> tuple[str | None, str]:
        """返回 (canonical_id, match_status)；噪声返回 (None, 'noise_dropped')。"""
        key = norm_name(raw_name)
        if key in self.noise_keys:
            return None, "noise_dropped"
        rule = self.split_rules.get(key)
        if isinstance(rule, dict):
            if raw_name in rule:
                return rule[raw_name], "split_resolved"
            # _by_context 等无拼写命中：不猜身份，留人工确认。
            return key, "split_unresolved"
        if key in self.key2id:
            return self.key2id[key], "registry_hit"
        return key, "self_identity"


def load_jsonl_single(path: Path) -> dict:
    """cite 层每文件一行一个 JSON 对象。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(x) for x in lines if x.strip()]
    if len(rows) != 1:
        raise ValueError(f"{path}: 期望 1 行 JSON，实际 {len(rows)}")
    return rows[0]


def rel_to_repo(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=OUT,
                        help="p0 输出根目录（默认 data/processed/e07），p1 产物写入其 p1/ 子目录")
    parser.add_argument("--limit", type=int, default=None,
                        help="只处理语料前 N 篇（verify-stdlib 小样用）；不设则要求语料恰为 952 篇")
    args = parser.parse_args(argv)

    corpus = args.out_root / "corpus"
    if not corpus.is_dir():
        print(f"FAIL: 语料目录不存在 {corpus}，请先跑 p0", file=sys.stderr)
        return 1
    papers = sorted(p.name for p in corpus.iterdir() if p.is_dir())
    if args.limit is not None:
        papers = papers[: args.limit]
        if not papers:
            print("FAIL: --limit 后语料为空", file=sys.stderr)
            return 1
    elif len(papers) != EXPECTED_PAPERS:
        print(f"FAIL: 语料论文数 {len(papers)} != {EXPECTED_PAPERS}", file=sys.stderr)
        return 1

    registry = Registry(REGISTRY)
    paper_set = set(papers)

    # 语料内论文的 arxiv id 索引，供引文锚点做语料内精确匹配。
    arxiv2pid: dict[str, str] = {}
    for pid in papers:
        rec = yaml.safe_load((corpus / pid / "layer4/paper_record.yml").read_text(encoding="utf-8"))
        arxiv_id = (rec.get("paper_record", {}).get("metadata", {}) or {}).get("arxiv_id") or ""
        if arxiv_id:
            key = norm_arxiv(arxiv_id)
            if key in arxiv2pid and arxiv2pid[key] != pid:
                print(f"FAIL: 语料内 arxiv id 冲突 {arxiv_id}: {arxiv2pid[key]} vs {pid}",
                      file=sys.stderr)
                return 1
            arxiv2pid[key] = pid

    edges: list[dict] = []
    noise_dropped: list[dict] = []
    anchors: list[dict] = []
    n_records = 0
    n_references = 0

    for pid in papers:
        pdir = corpus / pid
        rr_path = pdir / "layer4/resource_records.yml"
        ref_path = pdir / "cite/references.jsonl"
        ctx_path = pdir / "cite/cite_contexts.jsonl"
        for f in (rr_path, ref_path, ctx_path):
            if not f.is_file():
                print(f"FAIL: 缺文件 {rel_to_repo(f)}", file=sys.stderr)
                return 1

        records = yaml.safe_load(rr_path.read_text(encoding="utf-8")) or []
        for item in records:
            r = item.get("resource_record", {})
            n_records += 1
            raw_name = r.get("name") or ""
            canonical_id, status = registry.resolve(raw_name)
            if status == "noise_dropped":
                noise_dropped.append({"paper_id": pid, "raw_name": raw_name,
                                      "resource_id": r.get("resource_id")})
                continue
            relation = r.get("paper_relation", {}) or {}
            access = r.get("access", {}) or {}
            repo = r.get("repository", {}) or {}
            canon_url = repo.get("canonical_url") or ""
            acc_url = access.get("url") or ""
            url, url_source = (canon_url, "repository") if canon_url else (acc_url, "access")
            edges.append({
                "paper_id": pid,
                "resource_id": r.get("resource_id"),
                "kind": r.get("kind"),
                "raw_name": raw_name,
                "norm_key": norm_name(raw_name),
                "canonical_id": canonical_id,
                "match_status": status,
                "relation_type": relation.get("relation_type"),
                "relation_verified": False,
                "evidence_section": relation.get("section"),
                "aliases": r.get("aliases") or [],
                "access_url": acc_url,
                "repository_canonical_url": canon_url,
                "url_key": url_key(url),
                "url_source": url_source if url else "",
                "extraction_confidence": (r.get("provenance", {}) or {}).get("extraction_confidence"),
                "source_path": rel_to_repo(rr_path),
            })

        refs = load_jsonl_single(ref_path).get("references", [])
        n_references += len(refs)
        ctxs = load_jsonl_single(ctx_path).get("citation_contexts", [])
        ref2ctx: dict[int, list[str]] = {}
        ref2sec: dict[int, set[str]] = {}
        for c in ctxs:
            for idx in c.get("matched_reference_indices", []):
                ref2ctx.setdefault(idx, []).append(c.get("context_id"))
                if c.get("section"):
                    ref2sec.setdefault(idx, set()).add(c["section"])

        for ref in refs:
            arxiv_ids = [norm_arxiv(a) for a in ref.get("arxiv_ids") or []]
            dois = ref.get("dois") or []
            urls = ref.get("urls") or []
            if not (arxiv_ids or dois or urls):
                continue
            internal: set[str] = set()
            for a in arxiv_ids:
                if a in arxiv2pid:
                    internal.add(arxiv2pid[a])
            for u in urls:
                m = ACLAN_RE.search(u)
                if m and m.group(1) in paper_set:
                    internal.add(m.group(1))
            idx = ref.get("index")
            anchors.append({
                "paper_id": pid,
                "reference_index": idx,
                "title": ref.get("title"),
                "year": ref.get("year"),
                "arxiv_ids": ref.get("arxiv_ids") or [],
                "dois": dois,
                "urls": urls,
                "internal_paper_ids": sorted(internal),
                "context_ids": ref2ctx.get(idx, []),
                "sections": sorted(ref2sec.get(idx, set())),
                "confidence": ref.get("confidence"),
                "source_path": rel_to_repo(ref_path),
            })

    if n_records != len(edges) + len(noise_dropped):
        print(f"FAIL: 对账不平 {n_records} != {len(edges)} + {len(noise_dropped)}",
              file=sys.stderr)
        return 1

    p1_dir = args.out_root / "p1"
    p1_dir.mkdir(parents=True, exist_ok=True)
    with open(p1_dir / "resource_edges.jsonl", "w", encoding="utf-8") as f:
        for e in edges:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(p1_dir / "cite_anchors.jsonl", "w", encoding="utf-8") as f:
        for a in anchors:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")

    # 未注册名清单：按覆盖论文数排序，回喂 registry 扩充（本脚本不写 registry）。
    unreg: dict[str, dict] = {}
    for e in edges:
        if e["match_status"] != "self_identity":
            continue
        u = unreg.setdefault(e["norm_key"], {"norm_key": e["norm_key"], "papers": set(),
                                             "n_records": 0, "kinds": set(),
                                             "example": e["raw_name"]})
        u["papers"].add(e["paper_id"])
        u["n_records"] += 1
        u["kinds"].add(e["kind"])
    unreg_rows = [
        {"norm_key": u["norm_key"], "n_papers": len(u["papers"]),
         "n_records": u["n_records"], "kinds": sorted(u["kinds"]), "example": u["example"]}
        for u in unreg.values()
    ]
    unreg_rows.sort(key=lambda r: (-r["n_papers"], -r["n_records"], r["norm_key"]))
    with open(p1_dir / "unregistered_names.jsonl", "w", encoding="utf-8") as f:
        for r in unreg_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_status = Counter(e["match_status"] for e in edges)
    by_kind = Counter(e["kind"] for e in edges)
    shared = Counter()
    seen_pair: set[tuple[str, str]] = set()
    for e in edges:
        pair = (e["canonical_id"], e["paper_id"])
        if pair not in seen_pair:
            seen_pair.add(pair)
            shared[e["canonical_id"]] += 1
    n_shared_ge2 = sum(1 for v in shared.values() if v >= 2)
    n_internal = sum(1 for a in anchors if a["internal_paper_ids"])

    summary = {
        "_provenance": {
            "script": "e07/p1_build_edges.py",
            "experiment": "E07",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_rev": git_rev(),
            "python": sys.version.split()[0],
            "source": {
                "corpus": rel_to_repo(corpus),
                "registry": rel_to_repo(REGISTRY),
            },
            "params": {"expected_papers": EXPECTED_PAPERS, "limit": args.limit},
        },
        "n_papers": len(papers),
        "resource_records": n_records,
        "resource_edges": {
            "n_edges": len(edges),
            "by_match_status": dict(sorted(by_status.items())),
            "by_kind": dict(sorted(by_kind.items())),
            "noise_dropped": noise_dropped,
            "shared_canonical_ge2_papers": n_shared_ge2,
            "unregistered_names": rel_to_repo(p1_dir / "unregistered_names.jsonl"),
            "n_unregistered": len(unreg_rows),
        },
        "cite": {
            "n_references": n_references,
            "n_anchors": len(anchors),
            "n_internal_matched": n_internal,
        },
        "checks": {
            "reconciliation": "ok",
            "note": "relation_type 为 v1 线索（relation_verified=false）；"
                    "url_key 仅为锚点信号，未做跨名合并",
        },
    }
    with open(args.out_root / "p1_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    print(f"ok: {len(papers)} papers -> {rel_to_repo(p1_dir)}")
    print(f"  resource: {n_records} records -> {len(edges)} edges "
          f"({dict(sorted(by_status.items()))}), noise dropped {len(noise_dropped)}")
    print(f"  cite: {n_references} references -> {len(anchors)} anchors, "
          f"{n_internal} matched in-corpus")
    print(f"  unregistered names: {len(unreg_rows)} "
          f"(top: {', '.join(r['norm_key'] for r in unreg_rows[:5])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
