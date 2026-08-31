# MinerU Reference Pipeline

这个目录只放引用抽取、校验、修复、引用上下文抽取的脚本。后续新跑出来的数据不建议再写到
`src/extract/references/results/`，而是统一写到共享数据目录：

```text
/srv/datasets/p4a/data/processed/cite/<year>/<venue>/
```

建议在项目根目录保留兼容软链：

```bash
cd /home/lzx/projs/p4a
ln -s /srv/datasets/p4a/data data
```

这样历史 JSONL 里保存的 `data/...` 相对路径仍然能被后续脚本解析到真实 MinerU 文件。

## Flow

```text
MinerU OCR
  -> data/processed/mineru/<top>/<year>/<venue>/<paper_id>/vlm/
     - <paper_id>.md
     - <paper_id>_content_list.json
     - <paper_id>_origin.pdf

References pre-repair
  -> extract_mineru_references.py
     - <prefix>_references.jsonl
     - <prefix>_references_summary.json
  -> compare_mineru_reference_sources.py
     - <prefix>_verified_references.jsonl
     - <prefix>_reference_mismatches.jsonl
     - <prefix>_reference_comparison_summary.json

References repair gate
  -> launch_kimi_reference_repairs.py
     - repairs/prompts/
     - repairs/logs/
     - repairs/records/
     - <prefix>_references_repaired.jsonl
     - <prefix>_verified_plus_repaired.jsonl
     - <prefix>_repair_summary.json

Citation contexts for Layer4
  -> extract_cite_contexts.py
     - <prefix>_cite_contexts.jsonl
     - <prefix>_cite_contexts_summary.json

Layer4
  -> src/extract/layer4/*
     - input: <prefix>_verified_plus_repaired.jsonl
     - input: <prefix>_cite_contexts.jsonl
     - output: data/processed/layer4/<year>/<venue>/
```

`prefix` 默认是 `<top><year>`，例如 ACL 2025 是 `acl2025`。

## Runner

新增的 `run_reference_pipeline.py` 用来串起确定性步骤，默认数据根是
`/srv/datasets/p4a/data`，也可以用 `P4A_DATA_ROOT` 或 `--data-root` 覆盖。

### 1. MinerU OCR 后的自动抽取和比对

```bash
cd /home/lzx/projs/p4a

.venv/bin/python src/extract/references/run_reference_pipeline.py \
  --stage pre-repair \
  --year 2025 \
  --venue acl
```

这一步会生成 primary references、verified references、mismatch queue，以及 primary/verified 两份全局 reference index。

小样本检查：

```bash
.venv/bin/python src/extract/references/run_reference_pipeline.py \
  --stage pre-repair \
  --year 2025 \
  --venue acl \
  --limit 5
```

只看命令不执行：

```bash
.venv/bin/python src/extract/references/run_reference_pipeline.py \
  --stage pre-repair \
  --year 2025 \
  --venue acl \
  --dry-run
```

### 2. 修复 mismatch queue

先看队列：

```bash
less data/processed/cite/2025/acl/acl2025_reference_comparison_summary.json
```

批量启动 Kimi 修复：

```bash
.venv/bin/python src/extract/references/run_reference_pipeline.py \
  --stage repair \
  --year 2025 \
  --venue acl \
  --concurrency 32
```

如果 `repairs/records/` 里已经有修复记录，只想合并，不想再启动 Kimi：

```bash
.venv/bin/python src/extract/references/run_reference_pipeline.py \
  --stage merge-repairs \
  --year 2025 \
  --venue acl
```

单篇重跑：

```bash
.venv/bin/python src/extract/references/run_reference_pipeline.py \
  --stage repair \
  --year 2025 \
  --venue acl \
  --paper-id 2025.acl-demo.16 \
  --concurrency 1
```

### 3. 生成 Layer4 需要的 citation contexts

```bash
.venv/bin/python src/extract/references/run_reference_pipeline.py \
  --stage cite \
  --year 2025 \
  --venue acl
```

`cite` 会优先使用 `<prefix>_verified_plus_repaired.jsonl`；如果不存在，则退回到
`<prefix>_verified_references.jsonl`。给 Layer4 的正式输入应该优先使用 repaired 后的版本：

```text
data/processed/cite/2025/acl/acl2025_verified_plus_repaired.jsonl
data/processed/cite/2025/acl/acl2025_cite_contexts.jsonl
```

Layer4 推荐显式传入这两个文件：

```bash
.venv/bin/python src/extract/layer4/launch_kimi_layer4.py \
  --references-jsonl data/processed/cite/2025/acl/acl2025_verified_plus_repaired.jsonl \
  --cite-contexts-jsonl data/processed/cite/2025/acl/acl2025_cite_contexts.jsonl \
  --output-root data/processed/layer4/2025/acl
```

## Keep Or Rebuild

长期保留：

- `<prefix>_verified_plus_repaired.jsonl`
- `<prefix>_cite_contexts.jsonl`
- `<prefix>_repair_summary.json`
- `<prefix>_reference_comparison_summary.json`
- `repairs/records/`, 如果需要审计每篇人工修复

可重新生成或按需清理：

- `<prefix>_references.jsonl`
- `<prefix>_verified_references.jsonl`
- `<prefix>_reference_mismatches.jsonl`
- `*_reference_index*.jsonl`
- `repairs/prompts/`
- `repairs/logs/`

源码目录里的 `results/` 是历史 ACL 2025 中间产物和对照材料。新流程跑通后，可以把它当归档看待，不再作为
Layer4 的输入源。
