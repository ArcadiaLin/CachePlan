# Parser Extension Guide

Read this only when parser output is clearly wrong or a source package needs template-specific handling.

## First Collect Evidence

For the failing package, inspect:

- `run_report.json`
- `agent_edit_hints.json`
- `structure.json`
- `citations.json`
- `resources.json`

Record the tarball path, selected main TeX file, expected main TeX file if known, citation/resource examples, and the exact validation issues.

## Prefer Config Repairs

Change the YAML file under `scripts/config/` before changing Python code when the issue is:

- Main TeX file selection.
- New section command.
- New figure/table caption environment.
- New citation command.
- New enum, validation rule, or agent merge allowlist.

After editing config, rerun the same package and lint the generated YAML.

## Supplement Patches

Use `scripts/agent_supplement.d/` only when config cannot express the repair, such as:

- A template hides title, abstract, or sections behind custom macros.
- Bibliography content is not parseable as normal `.bib` or `.bbl`.
- Explicit resource URLs are generated through custom macros or tables.
- Citation context requires template-specific source normalization.

Patch files must:

- Use a numeric prefix, for example `10_custom_template_patch.py`.
- Explain trigger condition, repair behavior, inputs/outputs, why config is insufficient, and verified examples in the top docstring.
- Implement `applies(context: dict) -> bool` and `apply(context: dict) -> dict`.
- Modify only parse context data such as `structure`, `citations`, `resources`, `metadata`, or `notes`.
- Never write final YAML directly.

Register patches in `scripts/agent_supplement.d/manifest.yml`.

## Verification

From the skill directory:

```bash
uv run python -m compileall scripts
uv run python scripts/parse_one.py \
  --input <tarball> \
  --output-dir <run-output-dir> \
  --metadata offline \
  --supplements auto
uv run python scripts/yaml_linter.py <run-output-dir>/<arxiv_id>/paper_record.yml --json
```

If the repair affects agent resource judgments, also rerun `scripts/apply_agent_judgment.py` and inspect `agent_merge_edit_hints.json`.
