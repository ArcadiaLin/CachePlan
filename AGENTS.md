# AGENTS.md

## Overview

This repository is a research codebase created to support an ongoing research project.

The tentative publication target is **SIGMOD**. The current research direction
(updated 2026-09-05) is:

> **Cache-aware execution of agentic data-maintenance workflows (tentative)**

The motivating application is a literature data-management system maintained by
agents: incoming papers trigger extraction, resource verification, entity linking,
validation, repair, and publication of structured records. P4A v1 is the starting
point for this workload, not the final system or benchmark.

The candidate role of **CachePlan** is the execution optimizer within that system.
An agent run can be a physical execution instance of a logical data-processing
operator; an end-to-end paper-ingestion job can contain several such operators.
CachePlan explores how to schedule ready work and manage reusable inference state
across these executions. Literature management supplies the real data-management
requirements; building a feature-complete application is not itself the research
contribution.

The tentative research question is:

> Can progressively revealed workflow dependencies and context-reuse information
> guide operator scheduling and KV-cache retention/eviction to improve the cost,
> throughput, and latency of data maintenance under limited cache capacity,
> without compromising task quality or data correctness?

**SGLang is the planned inference backend.** LRU is an important baseline;
application-informed retention/eviction and its interaction with scheduling are
candidate mechanisms, not settled algorithms. Scheduling can change when reuse
occurs, while cache residency changes the benefit of that schedule. Backend
capabilities must be checked against a pinned version; do not assume that priority
hints provide hard GPU pinning or arbitrary prefix deletion.

The initial observation about semantically equivalent agent utterances producing
different token prefixes remains historical motivation. The current scope is
broader: execution organization, prompt construction, access order, and cache
lifetime jointly determine whether reuse is possible and realized.

This is a tentative research framing, not an established novelty or effectiveness
claim. The operator interface, optimization policy, and mini-benchmark remain to
be agreed and validated. Targeting SIGMOD requires a substantive data-management
contribution, not merely renaming agent runs as database operators.

## Workload Under Study

The workload class this project studies is **data-intensive / data-processing agent workflows**, not "data analysis agents".

P4A v1 (see `docs/experiments/p4a.md`) repeatedly applies a fixed Skill to many
papers using long, tool-augmented sessions. The proposed workload evolves this
into **incremental ingestion and maintenance of structured literature data**.
Its defining properties are:

- **repeated procedural knowledge** — stable, versioned Skills and operator contracts applied across many non-identical inputs;
- **persistent data products** — paper records, resource entities, and evidence links with provenance and versions, rather than conversational answers;
- **multi-input execution** — repeated work across papers and cohorts, potentially interacting with shared corpus state; runs need not be independent;
- **long-horizon, tool-augmented operators** — an operator may involve multiple model calls and tool waits, not just one LLM request;
- **progressively revealed dependencies** — extracted candidates, provider choices, and validation diagnostics can reveal subsequent work at runtime;
- **validation and repair** — explicit completion conditions and bounded repair, with independent task-quality evaluation beyond schema checks.

The optimizer needs visible scheduling boundaries and dependencies, not advance
knowledge of every internal agent action. A whole-paper black-box session remains
a useful boundary case, but is not the required execution unit. Operator
abstraction does **not** imply that operations are deterministic, freely
reorderable, or side-effect-free: scheduling must respect data dependencies,
input versions, and conflicts over shared state.

Repeated procedural knowledge creates *potential* reuse, not a guaranteed shared
KV prefix. Under prefix caching, reuse requires the same ordered token prefix and
compatible inference configuration, plus resident or recoverable KV state.
Semantic similarity, a shared operator name, or a common document alone is not
enough. Both the available prefix structure and its temporal reuse must be measured.

P4A v1 is an inherited trajectory source and workload-mining input, **not a
CachePlan method-effectiveness benchmark**. Its early private inputs, long-session
layout, and lack of independent quality evaluation limit what it can establish.
See `docs/PROGRESS.md` for evidence status and `docs/open-questions/Multi-run-workloads.md`
for the current workload-design questions; the proposed mini-benchmark is not yet
a validated evaluation protocol.

The open question of *how much agency* this workload class actually requires is tracked separately in `docs/PROGRESS.md`; nothing here presumes that a full ReAct agent is the right execution abstraction for it.

## Research and Evaluation Boundaries

- **Separate reuse layers.** Prompt/KV reuse, artifact/result reuse, and plan reuse have different validity conditions and must be accounted for separately. KV eviction is not deletion or invalidation of a published data record.
- **Use strong baselines.** Keep complete, same-information canonical procedures and applicable contracts in the static-prefix baseline. If static template selection or simple locality scheduling explains the benefit, do not attribute it to dynamic planning.
- **Separate interventions.** Distinguish operator scheduling, backend request scheduling, cache retention/eviction, and prompt restructuring. Use controlled comparisons to identify individual and joint effects.
- **Optimize useful work, not hit ratio alone.** Evaluate end-to-end cost, throughput, latency, queueing, and cache pressure under independent quality and data-correctness checks. A higher hit ratio is not by itself an improvement.
- **Keep the first benchmark bounded.** Agree on the task family, operator contracts, versioned external fixtures, and quality evaluation before implementing a mini-benchmark. Do not manufacture repeated work solely to create cache hits or expand into a full literature-management product without agreement.

## Repository Purpose

This repository is primarily intended for research experimentation, including:

- building experimental agent data-maintenance workloads and observable operator runtimes;
- collecting and analyzing agent execution trajectories;
- measuring prompt-cache behavior and inference cost;
- experimenting with cache-aware operator scheduling and inference-state retention/eviction;
- evaluating trade-offs among cache efficiency, latency, inference cost, and task quality.

This is a **research repository rather than a production application**.

When modifying the codebase, prefer implementations that are:

- easy to understand;
- easy to instrument;
- easy to reproduce;
- easy to compare experimentally.

Avoid unnecessary abstractions or large architectural changes unless they directly support the research.

## Working Principles for Agents

When working in this repository:

1. Preserve experiment reproducibility.
2. Prefer small and inspectable changes.
3. Do not silently change experiment configurations or evaluation behavior.
4. Keep cache-related instrumentation and execution traces observable.
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

2. **Update `docs/` only when the user asks.** This includes `docs/PROGRESS.md`, and
   it includes writing a new experiment record. The user maintains parts of these
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

## Documentation Conventions

Research questions, discussions, and experiment records accumulate under `docs/`, organized by kind rather than dropped flat into `docs/`:

- `docs/open-questions/` — unresolved research questions or hypotheses that need experimental validation before the project can proceed on an assumption.
- `docs/decisions/` — conclusions reached once an open question is resolved, with the rationale (ADR-style). Cross-link back to the originating open-question doc.
- `docs/experiments/` — records of specific experiments (setup, results, logs).
- `docs/literature/` — our *judgement* on external papers: one note per paper that actually supports a question, plus the index of those notes. Not the papers themselves.
- `docs/PROGRESS.md` — the mainline tracking document. It lists current research direction, current work, and the resolution status of every open question (OPEN / RESOLVED), with a short resolution summary once resolved.

External material lives outside `docs/`, in `references/`: `references/refs.bib` is the single tracked source of paper metadata, while `references/papers/` (PDFs), `references/repos/`, and `references/datasets/` are gitignored local copies. A paper is bound across all three places by one **citekey** (`author2024keyword`) used as its bib entry name, PDF filename, and note filename. Conventions: [`references/README.md`](references/README.md) and [`docs/literature/README.md`](docs/literature/README.md).

**Agent rule (settled discussions)**: once an open question is marked `RESOLVED` in `docs/PROGRESS.md`, treat its original doc under `docs/open-questions/` as historical — do not read the full doc back into context unless the user explicitly asks for it. Rely on the short resolution summary in `docs/PROGRESS.md` instead. This keeps converged, long-form discussions from being repeatedly pulled into context once they're settled.

**Agent rule (literature)**: same principle. Default to reading the index table in `docs/literature/README.md` and, where needed, a note's `verdict` field. Do not pull PDF full text or whole notes into context unless the user asks for a specific paper.

When starting new research-direction work, check `docs/PROGRESS.md` first for current status before creating a new doc.

## Evolving Research Direction

This repository supports an **ongoing and evolving research project**. The current problem formulation, hypotheses, metrics, workloads, and system design should not be treated as finalized.

`AGENTS.md` itself should evolve together with the research.

If the research direction changes substantially, this file may and should be updated to reflect:

- the new research question or hypothesis;
- changes in experimental methodology;
- changes in system scope or architecture;
- new evaluation criteria or workloads;
- deprecated assumptions from earlier stages of the project.

Minor implementation changes do not require rewriting the research description. Update this document when there is a **clear research-level change**, rather than normal code evolution.

When making such updates, preserve useful historical or experimental constraints when they are still relevant, and avoid presenting tentative research ideas as established conclusions.

## ARA: agent-native research artifacts

> **Opt-in only (2026-09-01).** Everything in this section runs **only when the user
> explicitly asks for it by name**. Do not invoke any ARA skill on your own initiative,
> and do not maintain `ara/` as a side effect of doing research — not at milestones,
> not at end of turn, not in autonomous runs (loops, heartbeats, long experiments).
>
> The reason is a measured cost/benefit call, not a judgement on the standard: keeping
> the artifact continuously in sync costs several times more editing than the research
> it records, and every edit to `docs/PROGRESS.md` invalidates the artifact's
> `file:line` citations and forces a remapping pass. The mainline research record is
> `docs/` (see Documentation Conventions above); `ara/` is a **frozen snapshot**,
> recompiled on demand rather than maintained per turn.

This project has an `ara/` artifact
(https://github.com/ARA-Labs/Agent-Native-Research-Artifact), last built 2026-09-01.
It is out of sync with `docs/` by design. When — and only when — the user asks:

- `/compiler` — rebuild `ara/` from `docs/` + `experiments/` + `references/`.
  This is the intended way to refresh the artifact: one batch recompile, not
  incremental upkeep.
- `/research-manager` — record recent research events into `ara/`. **Never invoke
  automatically**, including at end of turn; the skill's own text says to run it as a
  per-turn epilogue, and that instruction is overridden here.
- `/research-visualizer <ara-dir>` — inspect the trajectory as an interactive process
  map (`--serve` for a live viewer, `--check` to validate/lint via the `ara` CLI,
  which is **not installed**).
- `/research-foresight <ara-dir> "<question>"` — answer "what should I try next / why
  did this work / what if I change X", grounded in the artifact.
- `/submit-ara <dir>` — publish to the ARA Hub, or submit to a conference.
- `/context-drop <path>` — hand a file or folder to somebody else's agent as one link.

Also installed but not listed above: `/research-fuzzer`, `/rigor-reviewer`. Same rule.

**ARA badge on the paper** — also opt-in; add it only if the user asks. Should they ask,
here is how. Whenever you compile or build this project's paper PDF
(LaTeX, Typst, Markdown-to-PDF — any path that yields the paper), place the ARA badge in the
**top-right corner of the first page**, ~2.2 cm wide (a landscape paper tag), hyperlinked to the artifact's ARA Hub
URL (fall back to https://github.com/ARA-Labs/Agent-Native-Research-Artifact until
`/submit-ara` has produced one). Badge image:
https://raw.githubusercontent.com/ARA-Labs/Agent-Native-Research-Artifact/main/docs/badge/ara-badge.png
— download it next to the paper source. Ready-made LaTeX preamble snippet:
https://raw.githubusercontent.com/ARA-Labs/Agent-Native-Research-Artifact/main/docs/badge/ara-badge.tex
(uses `graphicx` + `eso-pic` + `hyperref`; place it after the venue style package). Do not
cover the title or author block; if the template already fills that corner, shift the badge
down just enough to clear it.
