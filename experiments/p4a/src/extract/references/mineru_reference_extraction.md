# MinerU References Extraction

This directory contains the ACL 2025 reference extraction workflow and its current outputs.

For the current shared-dataset workflow, start with `PIPELINE.md`. The historical
`results/` files documented below are useful as an ACL 2025 archive, but new
generated JSONL/summary files should be written under
`/srv/datasets/p4a/data/processed/cite/<year>/<venue>/`.

## Files

- `extract_mineru_references.py`: primary extractor. It prefers `*_content_list.json` and uses Markdown only as fallback/count cross-check.
- `compare_mineru_reference_sources.py`: verifier. It extracts references independently from `content_list.json` and Markdown, then compares repaired reference sequences.
- `build_reference_index.py`: title-first global deduper. It groups reference mentions by normalized title, falling back to DOI/arXiv/URL/raw only when no title is available.
- `launch_kimi_reference_repairs.py`: batch launcher/merger for Kimi manual repairs of `problem_papers`.
- `update_reference_record.py`: repair helper. Use it to replace one paper record in a JSONL result file after manual correction.
- `results/`: generated outputs for the current ACL 2025 MinerU batch.

## Results Directory

`results/acl2025_references.jsonl`

- One record per processed `vlm` directory.
- Produced by the primary content-list extractor.
- Contains all extracted references, including records that still need review.

`results/acl2025_references_summary.json`

- Summary for the primary extractor.
- Includes total paper/reference counts, empty papers, warning samples, and low-confidence reference count.

`results/acl2025_verified_references.jsonl`

- Only papers where Markdown extraction and content-list extraction agree exactly after repair/normalization.
- These records are the safest batch to use directly.

`results/acl2025_reference_mismatches.jsonl`

- Papers where Markdown and content-list extraction disagree, plus papers where neither source found references.
- Each line includes counts, warnings, first difference, and small content-only/markdown-only samples.

`results/acl2025_reference_comparison_summary.json`

- Summary for the verifier.
- Important fields:
  - `trusted_count`: number of verified records.
  - `status_counts`: count by match/mismatch/missing status.
  - `issue_category_counts`: rough category counts.
  - `problem_paper_ids`: complete list of papers needing review.
  - `problem_papers`: complete per-paper review queue with status, category, counts, warnings, and first difference.

Current verifier summary:

```text
paper_count: 2056
trusted_count: 1862
mismatch: 175
missing_markdown_references: 19
problem papers: 194
```

Issue categories:

```text
markdown_absorbed_non_reference_blocks: 144
missing_markdown_references: 19
text_diff_other: 16
reference_count_diff: 12
hyphenation_or_spacing_only: 3
```

Use `problem_papers` in `acl2025_reference_comparison_summary.json` as the source of truth for exactly which papers need manual repair.

`results/acl2025_reference_index.jsonl`

- Global title-first deduplicated reference index from `acl2025_references.jsonl`.
- One record per deduplicated reference group.
- Each record includes `mention_count`, `citing_paper_count`, `citing_paper_ids`, sample authors/raw strings, identifiers, and all occurrences.

`results/acl2025_reference_index_summary.json`

- Summary for the global index.
- Current full-batch counts:

```text
reference_mentions: 103604
unique_reference_count: 45233
unique_title_count: 44981
repeated_across_papers_count: 12851
```

`results/acl2025_verified_reference_index.jsonl`

- Same index, but built only from `acl2025_verified_references.jsonl`.

`results/acl2025_verified_reference_index_summary.json`

- Summary for the verified-only index.
- Current verified counts:

```text
reference_mentions: 94756
unique_reference_count: 42316
unique_title_count: 42110
repeated_across_papers_count: 11821
```

`results/repairs/`

- Staging area for Kimi manual repairs.
- `prompts/`: one prompt per problem paper.
- `logs/`: Kimi stdout/stderr logs.
- `records/`: one repaired JSON object per paper.
- `repair_failures.json`: failed or invalid repair tasks.

After Kimi repair merging, these extra outputs are produced:

- `results/acl2025_references_repaired.jsonl`: original primary result with repaired problem-paper records.
- `results/acl2025_verified_plus_repaired.jsonl`: verified records plus Kimi repaired/confirmed problem papers.
- `results/acl2025_repair_summary.json`: repair counts, repaired/empty paper IDs, and output line counts.
- `results/acl2025_repaired_reference_index.jsonl`: global title-first index from repaired results.
- `results/acl2025_repaired_reference_index_summary.json`: summary for the repaired index.

## Regenerate Outputs

Run from the repository root:

```bash
python3 src/extract/references/extract_mineru_references.py \
  data/processed/mineru/acl/2025/acl \
  --output src/extract/references/results/acl2025_references.jsonl \
  --summary src/extract/references/results/acl2025_references_summary.json
```

Then run the verifier:

```bash
python3 src/extract/references/compare_mineru_reference_sources.py \
  data/processed/mineru/acl/2025/acl \
  --trusted-output src/extract/references/results/acl2025_verified_references.jsonl \
  --mismatch-output src/extract/references/results/acl2025_reference_mismatches.jsonl \
  --summary src/extract/references/results/acl2025_reference_comparison_summary.json
```

Then build the global reference index:

```bash
python3 src/extract/references/build_reference_index.py \
  src/extract/references/results/acl2025_references.jsonl \
  --output src/extract/references/results/acl2025_reference_index.jsonl \
  --summary src/extract/references/results/acl2025_reference_index_summary.json
```

Build the verified-only reference index:

```bash
python3 src/extract/references/build_reference_index.py \
  src/extract/references/results/acl2025_verified_references.jsonl \
  --output src/extract/references/results/acl2025_verified_reference_index.jsonl \
  --summary src/extract/references/results/acl2025_verified_reference_index_summary.json
```

## Batch Kimi Repair

Run all problem-paper repairs with 32 Kimi agents:

```bash
python3 src/extract/references/launch_kimi_reference_repairs.py \
  --concurrency 32
```

Kimi Code 0.14.1 rejects `--prompt` combined with `--yolo` or `--auto`, so
the launcher defaults to prompt mode without an explicit permission flag. If a
future Kimi version supports it, pass `--permission-mode yolo`.

Run or rerun one paper:

```bash
python3 src/extract/references/launch_kimi_reference_repairs.py \
  --paper-id 2025.acl-demo.2 \
  --concurrency 1
```

Merge existing repair records without launching Kimi:

```bash
python3 src/extract/references/launch_kimi_reference_repairs.py \
  --merge-only
```

The launcher never asks Kimi agents to edit shared JSONL files. Each agent writes
one JSON record under `results/repairs/records/`, then the launcher validates all
records and serially applies them to the repaired output files.

## Repair Workflow For Agents

1. Open `results/acl2025_reference_comparison_summary.json`.
2. Pick a paper from `problem_papers`.
3. Read the original paper/MinerU files under the paper's `source_dir`.
4. Prepare one complete replacement JSON record for that `paper_id`.
5. Update the target result JSONL with `update_reference_record.py`.

Example:

```bash
python3 src/extract/references/update_reference_record.py \
  src/extract/references/results/acl2025_references.jsonl \
  --paper-id 2025.acl-demo.2 \
  --record-file /tmp/2025.acl-demo.2.fixed.json
```

To add the repaired record to a separate curated file if it is absent:

```bash
python3 src/extract/references/update_reference_record.py \
  src/extract/references/results/acl2025_verified_references.jsonl \
  --paper-id 2025.acl-demo.2 \
  --record-file /tmp/2025.acl-demo.2.fixed.json \
  --append
```

The replacement record must be a full JSON object and its `paper_id` must match `--paper-id`.
