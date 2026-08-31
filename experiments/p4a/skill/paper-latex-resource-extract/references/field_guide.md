# Field Guide

Read this before writing `agent_judgment.yml`. This guide covers fields the agent may write, what they mean, where to look, and what not to infer.

## What This Skill Is

This skill is a reusable workflow plus scripts for turning one arXiv LaTeX source package into auditable paper/resource extraction artifacts. Scripts do mechanical extraction only: metadata, structure, explicit links, figures, citations, and YAML scaffolds. Agent judgment fills semantic fields after reading evidence.

A Codex skill is a self-contained directory of instructions, scripts, and references that teaches an agent how to perform one repeatable task. In this case, the skill standardizes LaTeX paper parsing and the handoff from mechanical parser output to agent-written semantic judgment.

Parser-owned fields are evidence and candidates. Do not overwrite `metadata`, `abstract`, `section_outline`, raw citation context, figure caption/files/source, or parser-generated resource records directly.

## Judgment Shape

Write semantic additions in this shape:

```yaml
paper_record:
  content_units:
    figures: []
  atomic_extracts:
    intent: {}
    contributions: []
    claims: []
    experiments: []
    limitations: []
    future_work: []
    citation_context:
      cite: []
resources_introduced: []
resources_used: []
resource_judgments: []
```

Only include fields you are intentionally adding or correcting. Omit parser-owned fields unless they are needed as a merge key, such as `figure_id`, `label`, or `cite_key`.

## `paper_record.content_units.figures[]`

Agent may write only `description` and `agent_review`. Use `figure_id` or `label` to identify the target figure.

- `figure_id`: merge key from `paper_record.yml` or `figure_manifest.json`. Prefer this over label.
- `label`: fallback merge key when `figure_id` is unavailable.
- `description`: one short explanation of the figure's role in the paper. Base it on the extracted caption, nearby source text, and sentences that reference the figure. Do not describe visual details by inspecting pixels; this is not image understanding.
- `agent_review.status`: `ok`, `parser_mismatch`, or `uncertain`.
- `agent_review.notes`: concise reason for the status. Use an empty string for ordinary `ok`.

Use `ok` when caption, label, source location, and asset path look consistent. Use `parser_mismatch` only when the parser output clearly disagrees with the source, for example caption is truncated, asset path points to another figure, or source tex is wrong. Use `uncertain` when evidence is ambiguous.

Do not write or overwrite `caption`, `files`, `caption_source`, or `agent_interpretation_required`.

## `paper_record.atomic_extracts.intent`

- `paper_type`: classify the paper as `survey`, `empirical`, `benchmark`, `dataset`, `method`, `theory`, `position`, or `unknown`. Use abstract, introduction, and experiment structure. Prefer the most operational type: a new benchmark with experiments is `benchmark`; a new method evaluated empirically is `empirical` or `method` depending on local convention.
- `research_problem`: one sentence naming the concrete problem or gap the paper addresses. Use abstract/introduction/problem setup. Avoid generic field summaries.
- `target_domain`: list of stable domain tags, lower-case phrases or project-local labels. Use domains needed for downstream reuse, such as `diffusion generative models`, `image generation`, or `ai_for_science`.

Do not put claims, contributions, or resource names here unless they define the target domain.

## `paper_record.atomic_extracts.contributions[]`

Use this for author-stated contributions, not your derived analysis.

- `contribution_id`: stable id such as `contrib::1`, in paper order.
- `text`: concise contribution statement. Prefer "Proposes...", "Introduces...", "Shows...", "Releases...".
- `evidence.section`: section where the contribution is stated.
- `evidence.page`: page number if available; otherwise `null`.
- `evidence.quote`: short paper quote that directly supports the contribution.

Look in abstract, introduction, contribution bullets, conclusion, and project/release statements. Do not turn every experiment result into a contribution.

## `paper_record.atomic_extracts.claims[]`

Use this for the paper's central abstract-level claims only.

- `claim_id`: stable id such as `claim::1`.
- `text`: 1 sentence rewritten from the abstract. Keep 1-2 claims total.
- `claim_type`: `empirical`, `theoretical`, `methodological`, `survey`, or `resource`.

Source is fixed to the abstract, so do not add `evidence`, `section`, `quote`, or `table_or_figure`. Do not mine claims from experiment tables or discussion sections at Layer 4.

## `paper_record.atomic_extracts.experiments[]`

Use this for experiments that matter for reproducing or reusing the paper.

- `experiment_id`: stable id such as `exp::imagenet` or `exp::main`.
- `task`: what is evaluated, including setting and objective.
- `dataset_ids`: resource ids for datasets actually used in the experiment. Add matching `resource_judgments` when the parser did not create the id.
- `benchmark_ids`: benchmark ids when the paper evaluates on a named benchmark or suite. Add matching `resource_judgments` when the parser did not create the id.
- `metrics`: metric names exactly as the paper uses them when possible.
- `baselines`: baseline methods/models/systems compared against.
- `hyperparameters.status`: `available`, `partial`, `missing`, or `not_applicable`.
- `hyperparameters.values`: only explicit values from the paper, not guesses from linked repos.
- `evidence.section`: experiment/config/result section where this record is grounded.

Group repeated tables under one experiment when they share task, data, and setup. Split experiments when task/domain/dataset changes materially.

Do not leave dangling ids: every id in `dataset_ids` or `benchmark_ids` should be present in parser output or added through `resource_judgments`.

## `paper_record.atomic_extracts.limitations[]`

Use this for paper-stated limitations or direct risks grounded in limitations/discussion/conclusion.

- `text`: concise limitation or risk.
- `evidence.section`: source section.
- `evidence.quote`: short quote when available.

Do not invent generic risks. If the paper has no explicit limitation, leave empty unless there is a clearly stated caveat elsewhere.

## `paper_record.atomic_extracts.future_work[]`

Use this for explicit future directions.

- `text`: concise next-step direction.
- `evidence.section`: source section.
- `evidence.quote`: short quote when available.

Do not convert your own improvement ideas into future work.

## `paper_record.atomic_extracts.citation_context.cite[]`

Agent may write only citation function and must identify records by `cite_key`.

- `cite_key`: exact key from `citations.json` / `paper_record.yml`.
- `citation_function`: one of the local coarse labels, such as `background`, `baseline`, `method_source`, `dataset_source`, `claim_support`, or `contrast`.

Use the parser context plus surrounding text. Do not add `local_claim_id`; Layer 4 does not bind citations to local claims. Do not rewrite `context`, `reference_title`, or evidence fields.

## `resources_introduced` and `resources_used`

These are paper-level resource id lists.

- `resources_introduced`: ids for resources the paper introduces, releases, proposes, or publishes with the paper.
- `resources_used`: ids for resources used by the method or experiments.

Use ids already present in `resource_records.yml` from explicit links or ids you add through `resource_judgments`. Do not add cross-paper reverse links here.

Mechanical parsing leaves both lists empty. Do not infer introduced/used status from URL host, repository name, or resource kind; fill these lists only after reading statements such as "we release", "we use", "trained on", or experiment setup text.

## What Counts As A Resource

Extract resources as reusable entities, not as links or arbitrary named things.

A resource is usually worth recording when it is one of these:

- A dataset, benchmark, evaluation suite, task collection, leaderboard, or protocol used or released by the paper.
- Code, repository, package, library, tool, framework, API, simulator, environment, or script collection that implements or supports the paper.
- A model, checkpoint, pretrained weight, prompt set, agent skill, workflow, or protocol that the paper introduces, releases, uses, or evaluates.
- A project page or repository when it is the only explicit entry point for released code/data/model artifacts.

Where to look:

- Abstract and introduction release statements such as "we release", "code and data are available", "we introduce a benchmark", or "we publish".
- Contribution bullets and method overview for newly introduced datasets, tools, protocols, or systems.
- Dataset/benchmark sections, experiment setup, implementation details, table captions, appendix data descriptions, and ethics/impact statements for resources used.
- URL candidates from `resources.json`, but do not stop there; many named datasets and benchmarks have no URL in the paper.

Use these boundaries:

- Record both introduced resources and used resources. A paper can introduce a new benchmark while also using older datasets and evaluation suites.
- A single URL can support multiple resources. If a repository contains both implementation code and a released dataset/benchmark/model, create separate records with the same URL and different `kind`/`name`.
- A named resource without a URL should still get a record when the paper explicitly uses or introduces it; leave `access.url` empty and `availability_check.status` unknown.
- Baseline methods in comparison tables are not automatically resources. Record them only when the paper clearly uses their code/model/tool as an input artifact or when the resource itself matters for reuse.
- Do not record generic concepts, metrics, losses, equations, ordinary citations, or broad fields as resources.
- Do not verify links, licenses, downloads, or runtime unless the user explicitly asks for a verification stage.

Kind guidance:

- Use `dataset` for sample collections, corpora, training data, image/text/audio/video sets, or released annotation sets.
- Use `benchmark` for named evaluation tasks, suites, leaderboards, challenge datasets with evaluation protocols, or resources the paper calls a benchmark.
- Use `code` for implementation repositories, packages, scripts, notebooks, or released source code.
- Use `model` for checkpoints, pretrained models, weights, model families used as artifacts, or released trained systems.
- Use `tool` for software systems or services intended to be run or invoked, including simulators, APIs, environments, and annotation tools.
- Use `protocol` for reusable procedures, prompts, evaluation protocols, data-generation recipes, or alignment/training workflows when they are described as reusable artifacts rather than just the paper's method.
- Use `skill` only for resources already framed as agent-callable skills or workflows.
- Use generic `resource` only when the paper clearly exposes a reusable artifact but the kind cannot be determined from evidence.

## `resource_judgments[]`

Use this to add or correct resource records from semantic reading. Parser-created URL records are intentionally generic `resource` candidates; agent judgment is responsible for deciding whether a link is code, dataset, model, benchmark, tool, skill, or protocol.

- `resource_id`: optional. If omitted, the merge script derives one from `kind` and `name`.
- `kind`: `dataset`, `benchmark`, `code`, `model`, `tool`, `skill`, `protocol`, or `resource`.
- `name`: canonical resource name from the paper or linked repository.
- `aliases`: alternate names, repo path, abbreviations, or paper-specific names.
- `description`: one sentence explaining what the resource is and why it matters for this paper.
- `domain`: list of relevant domain tags.
- `access.url`: URL explicitly given by the paper or linked text.
- `access.access_type`: `public`, `request_only`, `restricted`, `missing`, or `unknown`. Do not verify online unless running a verification stage.
- `access.license`: only if explicitly stated in the paper or source text.
- `access.size`: only if explicitly stated.
- `agent_callable.skill_candidate`: true when the resource looks useful to wrap as a future agent-callable skill/tool.
- `agent_callable.skill_wrapped`: false unless this project has already wrapped it.
- `agent_callable.callable_interface`: known interface such as CLI, Python API, HTTP API, or `null`.
- `agent_callable.required_environment`: explicit runtime/dependency/hardware requirements.
- `agent_callable.estimated_wrapping_difficulty`: `low`, `medium`, `high`, or `unknown`.
- `evidence[].section`: source section.
- `evidence[].quote`: short supporting quote.
- `notes`: optional concise uncertainty or parser-correction note.
- `source_mentions`: optional snippets or parser candidate references useful for audit.

Leave `availability_check`, downloaded files, documentation status, reverse indexes, and external reachability as parser/default values unless the user asked for a verification stage.

For resources introduced by the current paper, also add the id to `resources_introduced`. For resources used in experiments or method construction, also add the id to `resources_used` and to the relevant experiment `dataset_ids` or `benchmark_ids` when applicable.

## Extraction Order

1. Read `run_report.json` and `agent_edit_hints.json` for parser status.
2. Read `paper_record.yml`, `structure.json`, `citations.json`, `resources.json`, `resource_records.yml`, and `figure_manifest.json`.
3. Read the paper source/PDF sections needed for semantic judgment.
4. Write only agent-owned fields in `agent_judgment.yml`.
5. Run merge and lint; inspect rejected paths before editing final files.
