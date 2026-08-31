# P4A Data Pipeline

本文档描述从 ACL PDF 镜像到 Layer4 资源抽取的完整流程。当前共享数据根目录是：

```text
/srv/datasets/p4a/data
```

建议所有脚本都从项目根目录运行：

```bash
cd /home/lzx/projs/p4a
```

## 目录约定

```text
raw/acl/<year>/pdf/<venue>/
  原始 ACL PDF 镜像

processed/mineru/acl/<year>/<venue>/<paper_id>/vlm/
  MinerU OCR 输出
  - <paper_id>.md
  - <paper_id>_content_list.json
  - <paper_id>_origin.pdf

processed/cite/<year>/<venue>/per_paper/<paper_id>/
  单篇引用和 citation context 中间产物
  - references.jsonl
  - verified_references.jsonl
  - reference_mismatches.jsonl
  - verified_or_repaired.jsonl
  - cite_contexts.jsonl
  - pipeline_status.json

processed/cite/<year>/<venue>/
  可选的全量汇总、索引、审计产物

processed/layer4/<year>/<venue>/<paper_id>/
  Layer4 输出
```

## 关键设计

旧流程把 `references` 和 `cite_contexts` 先做成全量 JSONL，然后 Layer4 再统一读取。这会导致一个阻塞：必须等所有论文完成引用抽取、修复、合并后，Layer4 才能开始。

新流程改成单篇推进：

```text
one PDF
  -> MinerU OCR
  -> references extract + verify for this paper
  -> optional per-paper repair
  -> cite contexts for this paper
  -> Layer4 for this paper
```

全量 JSONL 仍然可以用 `src/extract/references/run_reference_pipeline.py` 生成，但它现在是审计、统计、索引用途，不再是 Layer4 的前置依赖。

## 一键单篇流水线

ACL 2026 的 PDF 已经在：

```text
/srv/datasets/p4a/data/raw/acl/2026/pdf/acl/
```

先启动 MinerU VLM 服务：

```bash
src/mineru/serve_mineru_vllm.sh
```

然后跑自动化流水线。先建议用小样本和只准备 Layer4 的模式确认路径：

```bash
.venv/bin/python src/run_pipeline.py \
  --year 2026 \
  --venue acl \
  --limit 5 \
  --prepare-layer4-only
```

处理指定论文：

```bash
.venv/bin/python src/run_pipeline.py \
  --year 2026 \
  --venue acl \
  --paper-id 2026.acl-demo.0 \
  --prepare-layer4-only
```

真正启动 Layer4 Kimi：

```bash
.venv/bin/python src/run_pipeline.py \
  --year 2026 \
  --venue acl \
  --paper-id 2026.acl-demo.0 \
  --permission-mode none
```

如果引用双源校验不一致，默认该论文会停在 `blocked_reference_mismatch`，但不会阻塞其它论文。状态写在：

```text
processed/cite/2026/acl/per_paper/<paper_id>/pipeline_status.json
```

需要自动调用 Kimi 修复引用时：

```bash
.venv/bin/python src/run_pipeline.py \
  --year 2026 \
  --venue acl \
  --paper-id 2026.acl-demo.0 \
  --repair-references \
  --prepare-layer4-only
```

如果只是想让 Layer4 先跑起来，并接受未校验一致的 primary references：

```bash
.venv/bin/python src/run_pipeline.py \
  --year 2026 \
  --venue acl \
  --allow-unverified-references \
  --prepare-layer4-only
```

## 分阶段脚本

### ACL 镜像

```bash
.venv/bin/python src/acl-mirror/download_acl_year.py 2026 \
  --output-dir /srv/datasets/p4a/data/raw/acl
```

### MinerU OCR

```bash
.venv/bin/python src/mineru/batch_process_acl_mineru.py \
  --year 2026 \
  --venue acl
```

单篇：

```bash
.venv/bin/python src/mineru/batch_process_acl_mineru.py \
  --year 2026 \
  --venue acl \
  --paper-id 2026.acl-demo.0
```

### 单篇 references

```bash
.venv/bin/python src/extract/references/extract_mineru_references.py \
  /srv/datasets/p4a/data/processed/mineru/acl/2026/acl/2026.acl-demo.0 \
  --output /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/references.jsonl \
  --summary /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/references_summary.json
```

```bash
.venv/bin/python src/extract/references/compare_mineru_reference_sources.py \
  /srv/datasets/p4a/data/processed/mineru/acl/2026/acl/2026.acl-demo.0 \
  --trusted-output /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/verified_references.jsonl \
  --mismatch-output /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/reference_mismatches.jsonl \
  --summary /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/reference_comparison_summary.json
```

### 单篇 citation contexts

```bash
.venv/bin/python src/extract/references/extract_cite_contexts.py \
  /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/verified_or_repaired.jsonl \
  --output /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/cite_contexts.jsonl \
  --summary /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/cite_contexts_summary.json
```

### 单篇 Layer4

```bash
.venv/bin/python src/extract/layer4/launch_kimi_layer4.py \
  --paper-id 2026.acl-demo.0 \
  --references-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/verified_or_repaired.jsonl \
  --cite-contexts-jsonl /srv/datasets/p4a/data/processed/cite/2026/acl/per_paper/2026.acl-demo.0/cite_contexts.jsonl \
  --output-root /srv/datasets/p4a/data/processed/layer4/2026/acl \
  --concurrency 1
```

## 全量汇总和索引

全量汇总仍然有价值，但不再阻塞 Layer4：

```bash
.venv/bin/python src/extract/references/run_reference_pipeline.py \
  --stage pre-repair \
  --year 2026 \
  --venue acl
```

修复完成后：

```bash
.venv/bin/python src/extract/references/run_reference_pipeline.py \
  --stage cite \
  --year 2026 \
  --venue acl
```

这些全量文件适合做审计、全局 reference index 和统计，不建议作为在线推进 Layer4 的唯一入口。
