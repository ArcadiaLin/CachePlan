---
name: paper-mineru-resource-extract
description: Process one frozen P4A Layer-4 fixture into agent_judgment.json using only its prepared local evidence. This E06 skill is shared byte-for-byte by all placement arms.
---

# P4A Layer-4 resource judgment

You process exactly one prepared P4A paper-resource fixture. The user task names the case directory, required input paths, and output path. Read those paths before making a judgment.

This is an offline, fixture-backed workflow. Do not access the network, invoke MCP, launch another agent, inspect unrelated workspace files, or use project context. Do not repair source inputs. The fixture contains the paper text, repaired references, citation contexts, and any external evidence that the original P4A workflow would have obtained from GitHub, HuggingFace, or arXiv.

## Output contract

Write only the requested `agent_judgment.json`. Do not manually write YAML or alter any generated artifact. The later fixed merge and validation tools own YAML generation, schema normalization, resource ids, and validation.

The judgment must be valid JSON. Read `input/judgment_contract.json`, copy its `output_template`, replace `<paper_id>`, and add `resource_template`-derived records to `resources`.

`judgment_contract.json` is an instruction artifact, not output. Do not retain its `resource_template`, `enums`, or `instructions` fields in `agent_judgment.json`. Use only the contract's declared enum values and required defaults. Preserve fields for which evidence is unavailable with their prescribed empty or `unknown` values; do not invent data to make a record appear complete.

## Procedure

1. Read `input_bundle.json` and `input/judgment_contract.json`. Confirm the paper id, input paths, output path, required fields, and enum values.
2. Read the paper Markdown. Read the prepared references and citation contexts named by the bundle when deciding resource identity, relation, or citation function.
3. Identify reusable artifacts materially introduced, used, evaluated, or required by the paper: datasets, benchmarks, code, models, tools, skills, protocols, APIs, project pages, and released artifacts.
4. Read fixture-local evidence only when it is relevant to an identified artifact. Treat it as verification evidence, not as a replacement for paper evidence.
5. Write `agent_judgment.json` once all required fields can be supported by the prepared evidence.

## Semantic rules

Use only these paper types:

```text
survey, empirical, benchmark, dataset, method, theory, position, unknown
```

Use only these resource kinds:

```text
dataset, benchmark, code, model, tool, skill, protocol, resource
```

Use only these citation functions:

```text
background, method_source, dataset_source, benchmark_source, baseline,
tool_source, model_source, claim_support, comparison, contrast,
related_work, other, unknown
```

A resource is a reusable external or paper-introduced artifact. Record it when the paper introduces, releases, substantially extends, uses, evaluates, or requires it for the reported system or resource-building workflow. Do not record ordinary metrics, equations, losses, broad research areas, generic tasks, or every cited paper.

For each resource:

- Choose `relation_type` from the fixture schema and support it with paper evidence.
- Keep `evidence.quote` grounded in the paper; local frozen evidence may enrich access and availability but does not replace paper evidence.
- Use a canonical URL, license, availability, and `checked_by` value only when the fixture supplies supporting evidence.
- When evidence is insufficient, retain the schema's `unknown`, empty, or unfetched value and add a concise warning when required.
- Split one URL into separate resources only when the paper makes distinct reusable artifacts explicit.

Extract one or two concise claims from the abstract when the fixture schema requests claims. Do not overfit claims to incidental table details. If the abstract has no clear claim, use the prescribed empty list.

## Invariants

- The same prepared inputs must lead to the same output contract in every E06 arm; do not add arm-specific behavior.
- Keep tool output and reasoning bounded: read only relevant sections and do not enumerate unrelated files.
- Do not invoke an external service even if the paper mentions an unresolved URL.
- Do not use shell commands, edit YAML, or bypass the supplied output path.
- If required fixture input is absent or malformed, stop and report the missing path rather than substituting a network lookup or unrelated local file.
