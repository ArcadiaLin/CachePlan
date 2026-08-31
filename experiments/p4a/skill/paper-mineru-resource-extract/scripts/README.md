# MinerU Layer 4 Script Index

The executable scripts for this skill live in:

```text
src/extract/layer4/
```

Use these commands from the repository root:

```bash
cd /home/lzx/projs/p4a

.venv/bin/python src/run_pipeline.py --year 2026 --venue acl --paper-id <paper_id> --prepare-layer4-only

.venv/bin/python src/extract/layer4/prepare_mineru_layer4.py \
  --paper-id <paper_id> \
  --references-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/<paper_id>/verified_or_repaired.jsonl \
  --cite-contexts-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/<paper_id>/cite_contexts.jsonl \
  --output-root /srv/datasets/p4a/data/processed/layer4/2026/acl

.venv/bin/python src/extract/layer4/apply_agent_judgment.py \
  --paper-id <paper_id> \
  --layer4-root /srv/datasets/p4a/data/processed/layer4/2026/acl

.venv/bin/python src/extract/layer4/validate_layer4_outputs.py \
  --paper-id <paper_id> \
  --layer4-root /srv/datasets/p4a/data/processed/layer4/2026/acl
```

Boundary: agents write `agent_judgment.json` only. The scripts generate all YAML.
