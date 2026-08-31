---
name: paper-latex-resource-extract
description: Use only when the user explicitly asks for this skill to extract reusable paper and resource records from arXiv LaTeX source packages using bundled scripts for parsing, YAML validation with line hints, agent judgment merging, resource deduplication, and parser repair.
---

# Paper LaTeX Resource Extract

Use this skill to turn an arXiv LaTeX source package into an auditable draft record plus resource candidates. The bundled `scripts/` directory is the tool source of truth. Do not inspect or modify script code during normal extraction; run the documented commands and use the reports they produce.

## Core Rules

- Run commands from this skill directory, or set your shell working directory to this skill directory before using relative `scripts/...` paths.
- First confirm a usable Python environment with `uv`; use `uv run python ...` for every tool command.
- Treat parser output as candidates and evidence, not final review judgment.
- Treat resource extraction as semantic entity extraction, not URL collection: record reusable datasets, benchmarks, code, models, tools, skills, and protocols introduced or used by the paper, even when no URL is provided.
- Read `references/field_guide.md` before filling semantic fields such as paper type, problem, contributions, abstract-derived claims, experiment meaning, figure description/review, limitations, citation function, resource description, and wrapping difficulty.
- Put semantic additions in `agent_judgment.yml`; do not directly rewrite generated YAML before linting and merge reports are clean.
- Use edit tools only after validation gives exact `path`, `line`, `message`, and `suggested_fix` feedback.

## Tools

- `scripts/parse_one.py`: parse one `.tar.gz` source package and write a draft record, resources, citations, structure, copied figure assets, lint report, and run report.
- `scripts/yaml_linter.py`: validate YAML structure, types, enums, and report edit-friendly line hints.
- `scripts/apply_agent_judgment.py`: merge agent semantic judgments and resource judgments into parser output.
- `scripts/parse_batch.py`: parse a directory of `.tar.gz` packages without stopping on single-package failure.
- `scripts/config/*.yml`: parser configuration for enums, validation rules, TeX rules, resource candidate rules, and merge allowlists.
- `scripts/agent_supplement.d/`: optional parser repair patches for templates or source layouts configuration cannot handle.

## References

Normal single-package parsing does not require reading references.

- Read `references/field_guide.md` before writing `agent_judgment.yml`.
- Read `references/workflow.md` when you are unsure which fields are parser candidates versus agent judgments, or how to interpret output files.
- Read `references/parser_extension_guide.md` only when parsing fails, the selected main TeX file is wrong, citations/resources are obviously missing, or a new template needs repair rules.

## Environment Check

From the skill directory:

```bash
pwd
test -f scripts/parse_one.py
uv --version
uv run python --version
```

If `uv` is unavailable, stop and report the missing environment. Do not silently switch to system Python.

Runtime dependencies and network: run scripts with `uv run python ...` so `uv` resolves the Python package dependencies from this skill/project environment. `--metadata online` is the default and calls the arXiv API; if the user did not explicitly choose an environment or metadata mode and dependency installation or arXiv network access fails, stop and ask whether to retry with network/proxy fixes, switch to `--metadata offline`, or use a user-provided environment.

## Parse One Package

```bash
TARBALL="<arxiv-source.tar.gz>"
RUN_ROOT="<run-output-dir>"
METADATA="${METADATA:-online}"

uv run python scripts/parse_one.py \
  --input "$TARBALL" \
  --output-dir "$RUN_ROOT" \
  --metadata "$METADATA" \
  --supplements auto
```

Find the paper directory from the command output `output_dir`. If needed, infer it from the tarball basename:

```bash
ARXIV_ID="$(basename "$TARBALL" .tar.gz)"
PAPER_DIR="$RUN_ROOT/$ARXIV_ID"
test -f "$PAPER_DIR/run_report.json"
```

Expected outputs:

```text
paper_record.yml
resource_records.yml
structure.json
figures/
figure_manifest.json
citations.json
resources.json
lint_report.json
run_report.json
agent_edit_hints.json
```

## Inspect Outputs

```bash
uv run python scripts/yaml_linter.py "$PAPER_DIR/paper_record.yml" --json
```

Inspect in this order:

1. `run_report.json`: main TeX file, metadata status, citation/resource counts, parser notes.
2. `agent_edit_hints.json`: validation and repair hints with line numbers.
3. `structure.json`: title, abstract, sections, figures, tables.
4. `figure_manifest.json` and `figures/`: copied assets, caption sources, and missing assets.
5. `citations.json`: cite keys, reference titles, local citation contexts.
6. `resources.json` and `resource_records.yml`: explicit URL candidates only; kind semantics are agent judgment.
7. `paper_record.yml`: generated structure and fields to supplement.

## Add Agent Judgment

Create `$PAPER_DIR/agent_judgment.yml` for semantic additions only:

```yaml
paper_record:
  content_units:
    figures:
      - figure_id: fig::example
        description: "Caption/context-based role of this figure in the paper."
        agent_review:
          status: ok
          notes: ""
  atomic_extracts:
    intent:
      paper_type: empirical
      research_problem: "..."
      target_domain: ["..."]
    contributions:
      - contribution_id: contrib::1
        text: "..."
        evidence:
          section: Introduction
          page: null
          quote: "..."
    claims:
      - claim_id: claim::1
        text: "..."
        claim_type: empirical
    limitations:
      - text: "..."
        evidence:
          section: Limitations
          quote: "..."
    future_work:
      - text: "..."
        evidence:
          section: Conclusion
          quote: "..."
    citation_context:
      cite:
        - cite_key: example2026
          citation_function: background
resources_introduced:
  - code::examplerepo
  - benchmark::examplebench
resources_used:
  - dataset::exampleset
resource_judgments:
  - kind: code
    name: "ExampleRepo"
    aliases: ["project repository"]
    access:
      url: "https://example.com/repo"
      access_type: public
    description: "..."
    domain: ["..."]
    evidence:
      - section: Abstract
        quote: "..."
  - kind: benchmark
    name: "ExampleBench"
    aliases: ["ExampleRepo data release"]
    access:
      url: "https://example.com/repo"
      access_type: public
    description: "..."
    domain: ["..."]
    evidence:
      - section: Experiments
        quote: "..."
```

Resource judgments may add or correct datasets, benchmarks, code, models, tools, skills, protocols, and project pages. A single URL can support multiple semantic resources, such as a repository that releases both code and a benchmark. The merge tool deduplicates by resource id, URL, and kind/name.

## Merge And Validate

```bash
uv run python scripts/apply_agent_judgment.py \
  --base "$PAPER_DIR/paper_record.yml" \
  --resource-records "$PAPER_DIR/resource_records.yml" \
  --judgment "$PAPER_DIR/agent_judgment.yml" \
  --output "$PAPER_DIR/paper_record.agent.yml" \
  --resource-output "$PAPER_DIR/resource_records.agent.yml" \
  --report-json "$PAPER_DIR/agent_merge_report.json" \
  --edit-hints-json "$PAPER_DIR/agent_merge_edit_hints.json"

uv run python scripts/yaml_linter.py "$PAPER_DIR/paper_record.agent.yml" --json
```

If validation fails, read `agent_merge_edit_hints.json`, edit the smallest relevant location, and rerun merge plus lint. Only after validation passes should you apply accepted changes to the final target file.

## Batch Parse

```bash
INPUT_DIR="<directory-with-tar-gz>"
RUN_ROOT="<run-output-dir>"

uv run python scripts/parse_batch.py \
  --input-dir "$INPUT_DIR" \
  --output-dir "$RUN_ROOT" \
  --metadata online \
  --limit 20
```

Read `$RUN_ROOT/batch_report.json`. Remove `--limit` only after a small run has acceptable failure modes.

## Repair Rules

When parsing is obviously wrong:

1. Collect `run_report.json`, `agent_edit_hints.json`, `structure.json`, `figure_manifest.json`, `citations.json`, and `resources.json`.
2. Read `references/parser_extension_guide.md`.
3. Prefer editing the config file for main-file scoring, section/caption/citation commands, and explicit URL extraction patterns.
4. Add a supplement patch only when configuration cannot express the repair.
5. Re-run parsing with `--supplements auto`; use `--supplements required` when patch failure should fail the run.

## Final Report

Report the input package, output directory, metadata mode, selected main TeX file, citation/resource/figure counts, validation status, semantic fields added, resource judgments added, and any config or supplement repairs.
