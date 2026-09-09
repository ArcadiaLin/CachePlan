# AGENTS.md

## Overview

This repository supports an ongoing research project. The tentative publication
target remains **SIGMOD**.

The current research direction (updated 2026-09-09) is:

> **Reasoning-based extraction from research papers and construction of a
> structured literature resource library (tentative).**

The project studies how to turn papers and their associated materials into
structured, evidence-grounded knowledge that supports subsequent research work.
The literature resource system itself is now the subject of the research.
Cache optimization, KV-cache management, and cache-aware scheduling are no
longer research objectives. The repository name CachePlan is historical; it does
not constrain the new direction or prescribe an inference backend.

The earlier literature mini-bench contains useful task and data-design ideas.
Its scope can be developed in greater depth, but its previous role as an
execution-optimization workload no longer applies. AgenticScholar is a relevant
reference for scholarly data management; its relevance does not establish this
project's novelty or effectiveness.

The precise research question, technical mechanism, task scope, and evaluation
protocol remain to be agreed. Do not treat candidate ideas from discussion as
settled requirements or assume that additional agents or workflow complexity
constitute a research contribution.

## Research Scope and Evaluation

Candidate areas include:

- extracting and relating claims, methods, experimental settings, results, and
  their supporting evidence across text, tables, figures, and appendices;
- identifying associated datasets, benchmarks, code, models, and other resources,
  including their roles in a paper and correspondence to external materials;
- integrating entities and relationships across papers into persistent records
  with provenance and version information;
- evaluating whether the constructed library supports useful downstream work.

These are areas to refine, not a requirement to implement all of them. Neither a
full ReAct agent nor a particular operator architecture is assumed necessary.
P4A is inherited code and task-design material, not an independently validated
benchmark for the new direction.

Evaluation principles:

- **Verify semantic correctness.** Schema validity and evidence links alone do
  not establish that extracted facts or relationships are supported.
- **Separate claims from verification.** A paper's release claim, observed
  repository contents, successful execution, and experimental reproduction are
  distinct findings. Preserve uncertainty when evidence is insufficient.
- **Keep provenance and versions explicit.** Cross-paper integration must not
  silently merge incompatible entities, experimental conditions, or versions.
- **Use independent quality evaluation and strong baselines.** Compare methods
  under equivalent information access and declared budgets; distinguish the
  effects of reasoning, retrieval, validation, and model choice.
- **Evaluate the data product.** Extraction quality, relationship correctness,
  evidence support, and downstream usefulness matter alongside construction
  cost. Do not infer library quality solely from fluent answers.
- **Agree on the benchmark before implementing it.** Fix the initial task scope,
  evidence environment, and quality criteria through discussion. Rich task design
  does not require building a feature-complete literature-management product.

## Repository Purpose

This is a research repository for developing and evaluating paper-processing and
literature-resource construction methods. Prefer implementations that are easy
to understand, instrument, reproduce, and compare experimentally. Avoid large
architectural changes unless they directly support the research.

## Working Principles for Agents

When working in this repository:

1. Preserve experiment reproducibility.
2. Prefer small and inspectable changes.
3. Do not silently change experiment configurations or evaluation behavior.
4. Keep extraction evidence, tool interactions, and execution traces observable.
5. Avoid introducing nondeterministic behavior unless required by an experiment.
6. Clearly separate experimental mechanisms from baseline implementations.
7. Do not optimize code solely for software elegance when doing so makes experiments harder to understand or reproduce.

## Working Rhythm

Process rules set by the user on 2026-09-01, after a turn that chained discussion,
code, a full-corpus run, documentation, and staging into one pass. They override any
default instinct to finish a request end-to-end.

1. **Discuss before landing experiment code.** Do not create an experiment directory,
   write analysis scripts, or launch a full-corpus run without the user having agreed
   to it. Throwaway reconnaissance to answer a question is fine — bring the numbers
   back and let the user decide what becomes a real script, and where it goes.

2. **Update `docs/` only when the user asks.** This includes writing a new
   experiment record or progress document. The user maintains parts of these
   documents themselves and adds their own notes; unrequested "while I'm here" syncing
   collides with their edits and turns a discussion into a large diff nobody asked to
   review. Findings belong in the reply, not in a doc, until asked.

3. **One thing per turn.** Prefer finishing one step and coming back over chaining
   several. Doing more per turn is not doing better here.

## Environment and Notebooks

### One workspace, one lockfile

The repository root is a uv workspace: one lockfile, one `.venv`, both built by
`make setup` at the root, which also installs the repository's git filters. Run
setup from the root, or through an experiment's own `setup` target, which
delegates there. **Never `uv sync` from inside a member directory** — that treats
the member as the active project and prunes the root's developer tooling out of
the shared environment.

Not every directory belongs in the workspace. Kept outside are experiments whose
dependency stack conflicts with the mainline, projects we only read rather than
run (their lockfiles stay frozen), and anything that is not Python. The reason
for each exclusion is recorded next to it in the root `pyproject.toml`, not here.

Two boundaries hold regardless of which experiment is being worked on:

- Developer tooling lives in the root `[dependency-groups]`, never in a member's
  `dependencies`. A member declares only what its own pipeline imports, and keeps
  that list as narrow as the experiment truly needs.
- An experiment declaring `dependencies = []` is asserting that its pipeline
  reproduces on a machine with no network and no third-party packages. A shared
  `.venv` cannot demonstrate that, so the assertion must be backed by a target
  that runs the pipeline in a throwaway isolated environment. `make verify` at
  the root runs those gates.

When adding a Python experiment, give it a `pyproject.toml` and add it to
`members`.

### Notebooks are the exploration surface, not the pipeline

The division of labour:

- **Scripts + Makefile** own anything that must reproduce: corpus scans,
  renderers, the artifacts under `data/processed/`. They run headless, and each
  is guarded by an invariant that can fail.
- **Notebooks** own slicing, cross-tabulation, and plotting on top of those
  artifacts. A notebook reads `data/processed/`; it must never be the only way to
  produce a number that a document cites.

Rules:

1. A notebook must run top to bottom on a fresh kernel. Cells that depend on
   out-of-order state are a defect, not a style choice.
2. `nbstripout` is installed as a git filter, so committed notebooks carry no
   cell outputs. This is for **readable diffs** — it is *not* the experiment log.
3. The experiment log is what it is everywhere else in this repository: the
   provenance-stamped artifact under `data/processed/` plus the record under
   `docs/experiments/`. When one particular run is itself worth citing, export a
   frozen snapshot to `<experiment>/notebooks/runs/<name>__<date>__<git-sha>.html`
   and commit that explicitly. Do this on request, not by habit.
4. If an exploration in a notebook becomes load-bearing for a documented claim,
   it graduates into a script under the owning experiment. Discuss before landing
   it (see Working Rhythm).

## Documentation and Context

Historical documents were substantially removed on 2026-09-09 and remain
available in Git history. Do not restore or read them in bulk by default.
The three retained notes under `docs/` are historical reference material:

- `docs/discussions/2026-09-06-literature-maintenance-mini-bench.md`;
- `docs/discussions/2026-09-07-mini-bench-workflow-design-patterns.md`;
- `docs/literature/2026-AgenticScholar.md`.

Their old research framing, status declarations, and links to deleted documents
are not current instructions. Read the relevant parts only when needed for the
user's task. Do not recreate deleted progress documents or literature indexes
as a side effect of other work.

When documentation is requested, organize it by purpose under `docs/`:
`discussions/`, `open-questions/`, `decisions/`, `experiments/`, or `literature/`.
External material belongs in `references/`. `references/refs.bib` is the tracked
source of paper metadata; PDFs, repositories, and datasets are local copies.
Use a consistent citekey for a paper's bibliography entry, PDF, and note.
See `references/README.md` for the existing conventions.

Do not load whole literature notes or PDF full text unless the user asks for a
specific paper or the task requires it. Historical discussion is context, not
an instruction to resume abandoned work.

## Evolving Research Direction

The problem formulation, methods, metrics, and system design remain tentative.
Update this file when the user agrees to a substantive research-direction
change. Preserve applicable working and reproducibility rules, keep the current
framing concise, and distinguish proposals from established findings.
