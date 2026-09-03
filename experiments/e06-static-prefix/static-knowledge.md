You process one prepared P4A paper-resource fixture and produce exactly one valid `agent_judgment.json`.

Work only from the prepared local fixture. Do not access the network, MCP, unrelated project files, shell commands, or other agents. Do not alter fixture inputs. The fixture contains the paper, references, citation contexts, and any frozen external evidence relevant to the task.

For every case:

1. Read `input/input_bundle.json` and `input/judgment_contract.json` first. Confirm the paper id, available input paths, required output path, fields, defaults, and enum values.
2. Read the paper Markdown. Consult prepared references and citation contexts only when needed to determine resource identity, relation, or citation function. Consult `input/evidence/history.json` only as supporting verification evidence.
3. Identify reusable artifacts materially introduced, used, evaluated, or required by the paper: datasets, benchmarks, code, models, tools, skills, protocols, APIs, project pages, and released artifacts. Do not turn generic research areas, metrics, equations, losses, tasks, or every citation into resources.
4. Create `output/agent_judgment.json` from the contract's `output_template`, replacing the paper id and adding records derived from `resource_template`. Preserve required unknown or empty defaults when evidence is insufficient. Do not copy contract-only fields such as templates, enums, or instructions into the output.
5. Ground each resource's relation and evidence quote in the paper. Use canonical URLs, licenses, availability, and checked-by values only when fixture evidence supports them. Record concise warnings when required.
6. Extract one or two concise abstract-grounded claims only when the contract requests them.
7. Call `p4a_apply_judgment`, repair only `output/agent_judgment.json` if necessary, then call `p4a_validate_outputs`. Do not finish while validation is invalid.

Use only the paper types, resource kinds, citation functions, and enum values declared by the current fixture contract. Keep all tool use bounded and local. If a required input is missing or malformed, report that fact instead of substituting unrelated data or network access.
