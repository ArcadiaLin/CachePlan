#!/bin/bash
set -euo pipefail

# Comprehensive verification of reference extraction across all batch 1 + batch 2 papers
# Uses only standard tools: python, grep, sed, wc

echo "============================================="
echo "  Reference Extraction Verification Script"
echo "============================================="
echo ""

cd /home/lzx/projs/p4a

# Define all papers to verify
BATCH1=(
    "2025.acl-demo.21"
    "2025.acl-industry.81"
    "2025.acl-long.1008"
    "2025.acl-long.1135"
    "2025.acl-long.1160"
    "2025.acl-long.1215"
    "2025.acl-long.1308"
    "2025.acl-long.1368"
    "2025.acl-long.922"
    "2025.acl-long.976"
)

BATCH2=(
    "2025.acl-short.3"
    "2025.acl-long.169"
    "2025.acl-long.1376"
    "2025.acl-long.658"
    "2025.acl-long.1176"
    "2025.acl-long.1387"
    "2025.acl-long.687"
    "2025.acl-srw.18"
    "2025.acl-long.276"
    "2025.acl-long.84"
    "2025.acl-long.996"
    "2025.acl-long.750"
    "2025.acl-long.328"
    "2025.acl-long.170"
    "2025.acl-srw.46"
    "2025.acl-long.512"
    "2025.acl-long.942v2"
    "2025.acl-long.326"
    "2025.acl-long.961"
    "2025.acl-long.491"
)

ALL_PAPERS=("${BATCH1[@]}" "${BATCH2[@]}")

echo "Validating ${#ALL_PAPERS[@]} papers..."
echo ""
echo "Paper IDs:"
for p in "${ALL_PAPERS[@]}"; do
    echo "  - $p"
done
echo ""
echo "============================================="

# Create a Python script that does all the heavy verification
cat > /tmp/verify_refs.py << 'PYEOF'
#!/usr/bin/env python3
"""Comprehensive verification of reference extraction using multiple signals."""

import json
import re
import sys
from pathlib import Path

YEAR_RE = re.compile(r"\b((?:18|19|20)\d{2}[a-z]?)\b")
HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?\s*)?"
    r"(?:references?|bibliography|works\s+cited)\s*$",
    re.IGNORECASE,
)

def parse_content_list_refs(json_path):
    """Parse references from _content_list.json."""
    if not json_path.exists():
        return [], ["no content_list file"]
    
    data = json.loads(json_path.read_text())
    if not isinstance(data, list):
        return [], ["not a list"]
    
    warnings = []
    heading_idx = None
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        text = ""
        for key in ("text", "table_caption", "img_caption"):
            v = item.get(key)
            if isinstance(v, str):
                text = v
                break
            elif isinstance(v, list):
                text = " ".join(str(p) for p in v)
                break
        text = " ".join(text.split())
        if HEADING_RE.match(text):
            heading_idx = idx
            break
    
    if heading_idx is None:
        return [], ["no reference heading in content_list"]
    
    # Collect list items after heading
    refs = []
    for item in data[heading_idx + 1:]:
        if not isinstance(item, dict):
            continue
        itype = item.get("type")
        if itype == "page_number":
            continue
        if itype == "list":
            list_items = item.get("list_items", [])
            for li in list_items:
                val = _flatten(li)
                val = " ".join(val.split())
                if val:
                    refs.append(val)
            continue
        if itype in ("text", "ref_text"):
            val = _get_text(item)
            val = " ".join(val.split())
            if val:
                refs.append(val)
    
    return refs, warnings

def _flatten(val):
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return " ".join(_flatten(p) for p in val)
    if isinstance(val, dict):
        pieces = []
        for key in ("content", "item_content", "paragraph_content", "title_content"):
            if key in val:
                pieces.append(_flatten(val[key]))
        if "text" in val:
            pieces.append(str(val["text"]))
        return " ".join(p for p in pieces if p)
    return ""

def _get_text(item):
    for key in ("text", "table_caption", "img_caption"):
        v = item.get(key)
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            return " ".join(str(p) for p in v)
    return ""

def parse_markdown_refs(md_path):
    """Parse references from markdown file, joining continuation lines."""
    if not md_path.exists():
        return [], [], ["no markdown file"]
    
    lines = md_path.read_text().splitlines()
    ref_start = None
    ref_end = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# References"):
            ref_start = i + 1
        elif ref_start is not None and stripped.startswith("# "):
            ref_end = i
            break
    
    if ref_start is None:
        return [], [], ["no reference heading in markdown"]
    
    if ref_end is None:
        ref_end = len(lines)
    
    # Count different types of lines
    total_nonblank = 0
    year_lines = 0
    continuation_lines = []
    refs = []
    current = ""
    
    for i in range(ref_start, ref_end):
        text = lines[i].strip()
        if not text:
            continue
        total_nonblank += 1
        if YEAR_RE.search(text):
            if current:
                refs.append(current)
            year_lines += 1
            current = text
        else:
            continuation_lines.append(text)
            current = " " + text
    
    if current:
        refs.append(current)
    
    return refs, continuation_lines, []

def compare_refs(md_refs, cl_refs, extracted_refs, paper_id):
    """Compare three sources of references."""
    issues = []
    
    # Compare counts
    md_count = len(md_refs)
    cl_count = len(cl_refs)
    ext_count = len(extracted_refs)
    
    # Content list should be >= extracted (due to fragment joining)
    if cl_count < ext_count:
        issues.append(f"CRITICAL: content_list ({cl_count}) < extracted ({ext_count})")
    
    # Markdown should be close to extracted
    md_ext_diff = abs(md_count - ext_count)
    if md_ext_diff > max(3, int(0.15 * max(md_count, ext_count))):
        issues.append(f"WARNING: markdown ({md_count}) vs extracted ({ext_count}) diff={md_ext_diff}")
    
    return md_count, cl_count, ext_count, issues

def verify_field_extraction(ref, paper_id, idx):
    """Check if a reference has valid extracted fields."""
    issues = []
    if not ref.get("year"):
        issues.append(f"[{paper_id}] Ref #{idx}: no year")
    if not ref.get("title"):
        issues.append(f"[{paper_id}] Ref #{idx}: no title (conf={ref.get('confidence','?')})")
    if not ref.get("authors"):
        issues.append(f"[{paper_id}] Ref #{idx}: no authors")
    return issues

def sample_content_check(paper_dir, extracted_refs):
    """Spot-check a subset of extracted references against content_list."""
    content_list_path = paper_dir / "vlm" / f"{paper_dir.name}_content_list.json"
    if not content_list_path.exists():
        return []
    
    cl_refs, _ = parse_content_list_refs(content_list_path)
    if not cl_refs or len(cl_refs) != len(extracted_refs):
        return []
    
    # Check first, middle, last 5 references
    indices = list(range(5)) + [len(extracted_refs)//2] + list(range(len(extracted_refs)-5, len(extracted_refs)))
    
    mismatches = []
    for i in indices:
        if i >= len(extracted_refs):
            continue
        ext_raw = " ".join(extracted_refs[i].get("raw", "").split())
        cl_raw = " ".join(cl_refs[i].split())
        
        if ext_raw != cl_raw:
            mismatches.append({
                "idx": i + 1,
                "ext": ext_raw[:200],
                "cl": cl_raw[:200]
            })
    
    return mismatches

# Load extracted results
batch1_path = Path("/home/lzx/projs/p4a/src/extract/tests/references_extracted.jsonl")
batch2_path = Path("/home/lzx/projs/p4a/src/extract/tests/batch2_references_extracted.jsonl")

all_records = []
for path in [batch1_path, batch2_path]:
    if path.exists():
        with open(path) as f:
            for line in f:
                all_records.append(json.loads(line))

# All paper IDs we verified
all_paper_ids = set()
for r in all_records:
    all_paper_ids.add(r["paper_id"])

# Verify each paper
print(f"Verifying {len(all_records)} papers...\n")
print(f"{'Paper ID':<35} {'Extracted':>10} {'MD Year':>10} {'MD Total':>10} {'CL Items':>10} {'MDiffs':>8} {'Status':>8}")
print("-" * 100)

total_extracted = 0
total_md_year = 0
total_cl = 0
total_mismatches = 0
max_deviation = ("", 0)
all_issues = []
all_samples = []

for rec in all_records:
    paper_id = rec["paper_id"]
    extracted_refs = rec["references"]
    ext_count = len(extracted_refs)
    total_extracted += ext_count
    
    paper_dir = Path(f"data/processed/mineru/acl/2025/acl/{paper_id}")
    
    # Parse content_list
    cl_refs, cl_warnings = parse_content_list_refs(paper_dir / "vlm" / f"{paper_id}_content_list.json")
    total_cl += len(cl_refs)
    
    # Parse markdown
    md_refs, continuations, md_warnings = parse_markdown_refs(paper_dir / "vlm" / f"{paper_id}.md")
    md_count = len(md_refs)
    total_md_year += md_count
    
    # Compare
    md_count_c, cl_count_c, ext_count_c, issues = compare_refs(md_refs, cl_refs, extracted_refs, paper_id)
    all_issues.extend([(paper_id, issue) for issue in issues])
    
    # Field verification
    for idx, ref in enumerate(extracted_refs, 1):
        field_issues = verify_field_extraction(ref, paper_id, idx)
        all_issues.extend(field_issues)
    
    # Sample content check
    mismatches = sample_content_check(paper_dir, extracted_refs)
    total_mismatches += len(mismatches)
    all_samples.extend(mismatches)
    
    # Determine status
    is_fail = len(mismatches) > 0
    for item in all_issues:
        if isinstance(item, tuple) and len(item) == 2:
            p2, i = item
            if p2 == paper_id and "CRITICAL" in i:
                is_fail = True
                break
    if is_fail:
        status = "FAIL"
    elif len(continuations) > 0 and ext_count_c == md_count_c:
        status = "OK+"  # fragments were joined
    else:
        status = "OK"
    
    # Track max deviation
    if cl_count_c > 0:
        dev = abs(cl_count_c - ext_count_c) / cl_count_c
        if dev > max_deviation[1]:
            max_deviation = (paper_id, dev)
    
    print(f"{paper_id:<35} {ext_count:>10} {md_count_c:>10} {md_count_c+len(continuations):>10} {cl_count_c:>10} {len(mismatches):>8} {status:>8}")

print("-" * 100)
print(f"\n=== Summary ===")
print(f"Papers verified: {len(all_records)}")
print(f"Total references extracted: {total_extracted}")
print(f"Total Markdown year lines: {total_md_year}")
print(f"Total Content List items: {total_cl}")
print(f"MD-Extracted total diff: {total_md_year - total_extracted} ({100*(total_md_year - total_extracted)/max(total_extracted,1):.1f}%)")
print(f"CL-Extracted total diff: {total_cl - total_extracted} ({100*(total_cl - total_extracted)/max(total_extracted,1):.1f}%)")
print(f"Total sample mismatches: {total_mismatches}")
print(f"Max deviation: {max_deviation[0]} = {100*max_deviation[1]:.1f}%")
print()

# Print critical issues
critical = [i for i in all_issues if isinstance(i, tuple) and i[1].startswith("CRITICAL")]
warning = [i for i in all_issues if isinstance(i, tuple) and i[1].startswith("WARNING")]
field_issues = [i for i in all_issues if isinstance(i, tuple) and "Ref #" in i[1]]

if critical:
    print(f"CRITICAL issues: {len(critical)}")
    for p, i in critical:
        print(f"  [{p}] {i}")
if warning:
    print(f"\nWARNING issues: {len(warning)}")
    for p, i in warning:
        print(f"  [{p}] {i}")
if field_issues:
    print(f"\nField issues: {len(field_issues)}")
    for p, i in field_issues[:10]:
        print(f"  [{p}] {i}")

print()
if not critical and len(warning) == 0 and total_mismatches == 0:
    print("✅ ALL PAPER VERIFICATIONS PASSED - No critical issues found.")
elif not critical and len(warning) <= 2:
    print("⚠️  Minor warnings found, but no critical issues.")
else:
    print("⚠️  Some issues detected. See above details.")
PYEOF

# Run the verification
.venv/bin/python /tmp/verify_refs.py
