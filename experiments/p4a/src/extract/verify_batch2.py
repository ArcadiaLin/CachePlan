#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/extract/verify_batch2.py
r"""Batch 2 引用抽取质量验证脚本。

对 10 篇指定论文执行多维度一致性校验：
1. Markdown 行数校验（年份正则 / 总非空行）
2. Content List 条目校验（type=list 下的非空 item）
3. 字段覆盖率统计（year / title / authors / arxiv / doi / url）
4. Markdown 引文编号匹配（\d+.\s 或 [\d+]\s；MinerU 格式通常无编号，此项仅做格式检测）

所有结果以中文输出表格。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# ── 正则 ──────────────────────────────────────────────────────────────
YEAR_RE = re.compile(r"\b((?:18|19|20)\d{2}[a-z]?)\b")


# ── 目标论文 ──────────────────────────────────────────────────────────
TARGET_PAPERS = [
    "2025.acl-short.3",
    "2025.acl-long.169",
    "2025.acl-long.1376",
    "2025.acl-long.658",
    "2025.acl-long.1176",
    "2025.acl-long.1387",
    "2025.acl-long.687",
    "2025.acl-long.276",
    "2025.acl-long.84",
    "2025.acl-long.996",
]

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_project_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def configured_data_root() -> Path:
    value = os.environ.get("P4A_DATA_ROOT")
    if value:
        return Path(value)
    value = os.environ.get("DATA_ROOT") or os.environ.get("DATASET_ROOT")
    if value:
        root = Path(value)
        return root if root.name == "data" else root / "data"
    return Path("/srv/datasets/p4a/data")


load_project_env()
DEFAULT_DATA_ROOT = configured_data_root()
BASE_DIR = DEFAULT_DATA_ROOT / "processed/mineru/acl/2025/acl"
JSONL_PATH = Path("/home/lzx/projs/p4a/src/extract/tests/batch2_references_extracted.jsonl")


def is_reference_heading(text: str) -> bool:
    norm = re.sub(r"^\s*#+\s*\d*(?:\.\d+)*\.?\s*", "", text).strip().lower()
    return norm in ("references", "bibliography", "works cited")


def find_md_path(paper_dir: Path, paper_id: str) -> Path | None:
    """找到 Markdown 文件路径。"""
    p = paper_dir / f"{paper_id}.md"
    if p.exists():
        return p
    matches = sorted(paper_dir.glob("*.md"))
    return matches[0] if matches else None


def find_cl_path(paper_dir: Path, paper_id: str) -> Path | None:
    """找到 content_list.json 路径。"""
    p = paper_dir / f"{paper_id}_content_list.json"
    if p.exists():
        return p
    matches = sorted(paper_dir.glob("*_content_list.json"))
    return matches[0] if matches else None


def get_md_body_lines(paper_dir: Path, paper_id: str) -> list[str] | None:
    """获取 Markdown 中 References 区域的所有行。"""
    md_path = find_md_path(paper_dir, paper_id)
    if not md_path or not md_path.exists():
        return None

    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    ref_start = None
    for idx, line in enumerate(lines):
        s = line.strip().lower()
        if s.startswith("# references") or s.startswith("#bibliography"):
            ref_start = idx
            break
    if ref_start is None:
        return []

    body_lines: list[str] = []
    for line in lines[ref_start + 1:]:
        stripped = line.strip()
        if stripped.startswith("#"):
            break
        if stripped.startswith("!") or stripped.startswith("<table"):
            continue
        body_lines.append(stripped)
    return body_lines


# ── 1. Markdown 行数校验 ─────────────────────────────────────────────
def verify_markdown_lines(paper_dir: Path, paper_id: str) -> dict:
    body = get_md_body_lines(paper_dir, paper_id)
    if body is None:
        return {"status": "missing_markdown", "year_lines": 0, "total_nonempty": 0,
                "bracket_count": 0, "dot_count": 0}

    nonempty = [l for l in body if l]
    year_lines = sum(1 for l in nonempty if YEAR_RE.search(l))

    # 引文编号统计
    bracket_nums = set()
    dot_nums = set()
    for l in nonempty:
        m = re.search(r"\[(\d+)\]", l)
        if m:
            bracket_nums.add(m.group(1))
        m = re.match(r"^\s*(\d+)\.\s", l)
        if m:
            dot_nums.add(m.group(1))

    all_nums = bracket_nums | dot_nums
    max_num = max(int(x) for x in all_nums) if all_nums else 0

    return {
        "status": "ok",
        "year_lines": year_lines,
        "total_nonempty": len(nonempty),
        "bracket_count": len(bracket_nums),
        "dot_count": len(dot_nums),
        "max_ref_number": max_num,
    }


# ── 2. Content List 条目校验 ─────────────────────────────────────────
def flatten_dict(d: dict) -> str:
    pieces: list[str] = []
    for key in ("content", "item_content", "paragraph_content", "title_content", "text"):
        if key in d:
            v = d[key]
            if isinstance(v, str):
                pieces.append(v)
            elif isinstance(v, list):
                pieces.append(" ".join(str(p) for p in v))
    return " ".join(pieces).strip()


def verify_content_list(paper_dir: Path, paper_id: str) -> dict:
    cl_path = find_cl_path(paper_dir, paper_id)
    if not cl_path or not cl_path.exists():
        return {"status": "missing_content_list", "list_items_count": 0}

    data = json.loads(cl_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return {"status": "invalid_content_list", "list_items_count": 0}

    # 找到 References heading 的索引
    ref_start = None
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        if is_reference_heading(str(item.get("text", ""))):
            ref_start = idx
            break

    if ref_start is None:
        return {"status": "no_references_heading", "list_items_count": 0}

    # 找下一个 top heading
    stop = len(data)
    for idx in range(ref_start + 1, len(data)):
        item = data[idx]
        if not isinstance(item, dict):
            continue
        level = item.get("text_level")
        if item.get("type") == "text" and (level == 1 or level == "1"):
            if not is_reference_heading(str(item.get("text", ""))):
                stop = idx
                break

    # 统计非空条目
    total_items = 0
    for item in data[ref_start + 1 : stop]:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "page_number":
            continue
        if item.get("type") == "list":
            lis = item.get("list_items", [])
            if isinstance(lis, list):
                for value in lis:
                    if isinstance(value, str) and value.strip():
                        total_items += 1
                    elif isinstance(value, dict):
                        if flatten_dict(value).strip():
                            total_items += 1
            continue
        if item.get("type") in ("text", "ref_text"):
            flat = flatten_dict(item)
            if flat.strip() and not is_reference_heading(flat):
                total_items += 1

    return {"status": "ok", "list_items_count": total_items}


# ── 3. 字段覆盖率统计 ────────────────────────────────────────────────
def verify_field_coverage(record: dict) -> dict:
    refs = record.get("references", [])
    n = len(refs)
    if n == 0:
        return {"status": "no_references", "year_cov": 0, "title_cov": 0, "author_cov": 0,
                "arxiv": 0, "doi": 0, "url": 0}

    year_count = sum(1 for r in refs if r.get("year"))
    title_count = sum(1 for r in refs if r.get("title"))
    author_count = sum(1 for r in refs if r.get("authors"))
    arxiv_count = sum(1 for r in refs if r.get("arxiv_ids"))
    doi_count = sum(1 for r in refs if r.get("dois"))
    url_count = sum(1 for r in refs if r.get("urls"))

    return {
        "status": "ok",
        "year_cov": year_count / n * 100,
        "title_cov": title_count / n * 100,
        "author_cov": author_count / n * 100,
        "arxiv": arxiv_count,
        "doi": doi_count,
        "url": url_count,
        "total": n,
    }


# ── 汇总验证结果 ──────────────────────────────────────────────────────
class PaperResult:
    def __init__(self):
        self.paper_id = ""
        self.extracted_count = 0
        self.source = ""
        self.md_year_lines = 0
        self.md_total_nonempty = 0
        self.md_bracket_count = 0
        self.md_dot_count = 0
        self.md_max_ref = 0
        self.md_status = ""
        self.cl_items = 0
        self.cl_status = ""
        self.year_cov = 0.0
        self.title_cov = 0.0
        self.author_cov = 0.0
        self.arxiv_count = 0
        self.doi_count = 0
        self.url_count = 0
        self.warnings: list[str] = []


def run_verification() -> list[PaperResult]:
    # 加载 JSONL
    records = {}
    for line in JSONL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        records[rec["paper_id"]] = rec

    results: list[PaperResult] = []

    for pid in TARGET_PAPERS:
        rec = records.get(pid)
        if rec is None:
            r = PaperResult()
            r.paper_id = pid
            r.md_status = "paper_not_in_jsonl"
            r.warnings.append("JSONL 中不存在该论文")
            results.append(r)
            continue

        paper_dir = BASE_DIR / pid / "vlm"
        ext_count = rec.get("reference_count", len(rec.get("references", [])))

        # Markdown 校验
        md = verify_markdown_lines(paper_dir, pid)
        # Content List 校验
        cl = verify_content_list(paper_dir, pid)
        # 字段覆盖
        fields = verify_field_coverage(rec)

        r = PaperResult()
        r.paper_id = pid
        r.extracted_count = ext_count
        r.source = rec.get("source", "")
        r.md_status = md["status"]
        r.md_year_lines = md["year_lines"]
        r.md_total_nonempty = md["total_nonempty"]
        r.md_bracket_count = md["bracket_count"]
        r.md_dot_count = md["dot_count"]
        r.md_max_ref = md["max_ref_number"]
        r.cl_status = cl["status"]
        r.cl_items = cl["list_items_count"]
        r.year_cov = fields.get("year_cov", 0)
        r.title_cov = fields.get("title_cov", 0)
        r.author_cov = fields.get("author_cov", 0)
        r.arxiv_count = fields.get("arxiv", 0)
        r.doi_count = fields.get("doi", 0)
        r.url_count = fields.get("url", 0)

        # ── 一致性判断 ──
        def check_diff(name, actual, expected, threshold_pct=0.15, min_abs=3):
            diff = actual - expected
            if expected > 0 and abs(diff) > max(min_abs, int(threshold_pct * max(actual, expected))):
                r.warnings.append(f"{name}: {actual} vs 抽取数量{expected}, 偏差{diff:+d}")

        if r.md_status == "ok" and ext_count > 0:
            # 引文编号仅在 Markdown 使用编号格式时有效（MinerU 输出通常无编号）
            if r.md_max_ref > 0:
                check_diff("Markdown引文编号", r.md_max_ref, ext_count)
            check_diff("Markdown年份行", r.md_year_lines, ext_count)
        if r.cl_status == "ok" and ext_count > 0:
            check_diff("Content List条目", r.cl_items, ext_count)

        if fields["status"] == "ok":
            if fields["year_cov"] < 80:
                r.warnings.append(f"年份覆盖率偏低({fields['year_cov']:.1f}%)")
            if fields["title_cov"] < 80:
                r.warnings.append(f"标题覆盖率偏低({fields['title_cov']:.1f}%)")
            if fields["author_cov"] < 80:
                r.warnings.append(f"作者覆盖率偏低({fields['author_cov']:.1f}%)")

        results.append(r)

    return results


# ── 输出 ──────────────────────────────────────────────────────────────
def print_results(results: list[PaperResult]) -> None:
    print("=" * 130)
    print("  Batch 2 引用抽取质量验证报告（正则匹配 + 数量级一致性检查）")
    print("=" * 130)
    print()

    for r in results:
        status = "有偏差" if r.warnings else ("完全一致" if r.extracted_count > 0 else "数据缺失")
        emoji = "⚠️" if status == "有偏差" else ("✅" if status == "完全一致" else "❌")
        sep = "-" * 130
        print(sep)
        print(f"  {emoji} 论文: {r.paper_id}    状态: {status}    来源: {r.source}")
        print(sep)

        # Markdown 数量对比表
        print(f"\n  【1】Markdown 行数校验 & 引文编号匹配")
        print(f"  {'指标':<30} {'值':>8}")
        print(f"  {'引用抽取总数':<30} {r.extracted_count:>8}")
        print(f"  {'Markdown年份行数量':<30} {r.md_year_lines:>8}")
        print(f"  {'Markdown References 总非空行':<30} {r.md_total_nonempty:>8}")
        print(f"  {'Markdown引文编号(最大编号)':<30} {r.md_max_ref:>8}")
        print(f"  {'Markdown引文编号[\\d+]格式':<30} {r.md_bracket_count:>8}")
        print(f"  Markdown引文编号(\\d+.格式):{'':>30} {r.md_dot_count:>8}")

        # Content List 条目
        print(f"\n  【2】Content List 条目校验")
        print(f"  {'指标':<30} {'值':>8}")
        print(f"  {'Content List 非空条目数':<30} {r.cl_items:>8}")

        # 字段覆盖率
        print(f"\n  【3】字段覆盖率统计")
        print(f"  {'指标':<30} {'值':>8}")
        print(f"  {'年份提取覆盖率':<30} {r.year_cov:>7.1f}%")
        print(f"  {'标题提取覆盖率':<30} {r.title_cov:>7.1f}%")
        print(f"  {'作者提取覆盖率':<30} {r.author_cov:>7.1f}%")
        print(f"  {'提取到 arXiv ID 的数量':<30} {r.arxiv_count:>8}")
        print(f"  {'提取到 DOI 的数量':<30} {r.doi_count:>8}")
        print(f"  {'提取到 URL 的数量':<30} {r.url_count:>8}")

        if r.warnings:
            print(f"\n  ⚠ 警告/偏差:")
            for w in r.warnings:
                print(f"    - {w}")
        print()

    # ── 总体汇总 ──
    print("=" * 130)
    print("  总体汇总")
    print("=" * 130)

    total_ext = sum(r.extracted_count for r in results)
    total_md_yr = sum(r.md_year_lines for r in results)
    total_md_ne = sum(r.md_total_nonempty for r in results)
    total_cl = sum(r.cl_items for r in results)
    total_md_num = sum(r.md_max_ref for r in results)
    papers_ok = sum(1 for r in results if not r.warnings and r.extracted_count > 0)
    papers_warn = sum(1 for r in results if r.warnings)
    papers_missing = sum(1 for r in results if r.extracted_count == 0)

    print(f"\n  验证论文数: {len(results)}")
    print(f"    - ✅ 完全一致: {papers_ok}")
    print(f"    - ⚠️  有偏差:   {papers_warn}")
    print(f"    - ❌ 数据缺失: {papers_missing}")

    print(f"\n  {'汇总指标':<30} {'数值':>12}")
    print(f"  {'引用抽取总数':<30} {total_ext:>12}")
    print(f"  {'Markdown年份行总数':<30} {total_md_yr:>12}")
    print(f"  {'Markdown References 总非空行':<30} {total_md_ne:>12}")
    print(f"  {'Content List条目总数':<30} {total_cl:>12}")
    print(f"  {'Markdown引文编号(最大编号)总和':<30} {total_md_num:>12}")

    # 覆盖率汇总
    valid = [r for r in results if r.year_cov > 0]
    if valid:
        print(f"\n  字段覆盖率平均:")
        avg_y = sum(r.year_cov for r in valid) / len(valid)
        avg_t = sum(r.title_cov for r in valid) / len(valid)
        avg_a = sum(r.author_cov for r in valid) / len(valid)
        print(f"    年份: {avg_y:.1f}%  |  标题: {avg_t:.1f}%  |  作者: {avg_a:.1f}%")
        print(f"    arXiv: {sum(r.arxiv_count for r in valid):>4}  |  DOI: {sum(r.doi_count for r in valid):>4}  |  URL: {sum(r.url_count for r in valid):>4}")

    # 偏差较大的论文
    large_dev = [r for r in results if r.warnings]
    print()
    if large_dev:
        print("  偏差较大的论文（偏差项数 >= 2 或绝对偏差 > 10）:")
        for r in large_dev:
            print(f"\n  📄 {r.paper_id} (抽取={r.extracted_count}):")
            for w in r.warnings:
                print(f"     - {w}")
    else:
        print("  ✅ 未发现偏差较大的论文。")
    print()
    print("=" * 130)
    print("  验证完成。")
    print("=" * 130)


# ── 主入口 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    results = run_verification()
    print_results(results)
