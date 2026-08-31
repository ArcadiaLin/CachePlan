# AGENTS.md

## Overview

This repository is a research codebase created to support an ongoing research project.

The current research direction is tentatively focused on:

> **Cache-aware planning and execution in LLM agents (tentative)**

At the current stage, the project explores how agent behavior, planning trajectories, prompt construction, and tool execution interact with LLM inference mechanisms such as **prompt caching / KV cache reuse**.

One initial observation motivating this research is that semantically equivalent agent behaviors may produce different prompt prefixes or execution trajectories. For example:

- `I will first read the skill.`
- `Let me read the skill first.`
- `I'll start by checking the skill instructions.`

Although these actions are functionally equivalent, their different token sequences may reduce prompt-cache reuse across repeated agent runs.

A tentative research question is:

> Can agent planning and execution be designed to improve cache reuse without significantly reducing agent capability or task performance?

Both the research question and the technical approach are subject to change as the project develops.

## Workload Under Study

The workload class this project studies is **data-intensive / data-processing agent workflows**, not "data analysis agents".

The distinction is load-bearing. What characterizes P4A (see `docs/experiments/p4a.md`) is not that the agent *analyzes data*; it is that the agent repeatedly executes **one long-horizon, tool-augmented, end-to-end workflow over many different inputs, driven by a fixed body of procedural knowledge (a Skill)**. Concretely, an instance of this workload class has:

- **fixed procedural knowledge** — a long, stable Skill / agent prompt that encodes the same procedure for every input;
- **input-parallel repetition** — the same procedure is run over a corpus of homogeneous but non-identical inputs (in P4A: every ACL 2025 main-conference paper), one independent run per input;
- **long-horizon tool-augmented execution** — many turns of read / extract / search / merge, over local scripts and external sources;
- **validation and repair** — the run does not end at first output; results are validated against a schema or checker, and failures trigger re-investigation or targeted fixes;
- **structured end-to-end output** — the deliverable is a structured record, not a conversational answer.

This framing is what makes the workload interesting for cache research: because the procedural knowledge is fixed and the runs are many, there is a large *a priori* shared prefix across runs, and any divergence in how the agent phrases or orders its steps is what erodes reuse of that prefix. Terms like "data analysis agent" put the emphasis on the wrong property (the semantics of the task) rather than on the repetition of a fixed procedure, which is the property the research actually depends on.

The open question of *how much agency* this workload class actually requires is tracked separately in `docs/PROGRESS.md`; nothing here presumes that a full ReAct agent is the right execution abstraction for it.

## Repository Purpose

This repository is primarily intended for research experimentation, including:

- building experimental agent runtimes and workloads;
- collecting and analyzing agent execution trajectories;
- measuring prompt-cache behavior and inference cost;
- experimenting with cache-aware planning or execution strategies;
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

## Documentation Conventions

Research questions, discussions, and experiment records accumulate under `docs/`, organized by kind rather than dropped flat into `docs/`:

- `docs/open-questions/` — unresolved research questions or hypotheses that need experimental validation before the project can proceed on an assumption.
- `docs/decisions/` — conclusions reached once an open question is resolved, with the rationale (ADR-style). Cross-link back to the originating open-question doc.
- `docs/experiments/` — records of specific experiments (setup, results, logs).
- `docs/PROGRESS.md` — the mainline tracking document. It lists current research direction and the resolution status of every open question (OPEN / RESOLVED), with a short resolution summary once resolved.

**Agent rule**: once an open question is marked `RESOLVED` in `docs/PROGRESS.md`, treat its original doc under `docs/open-questions/` as historical — do not read the full doc back into context unless the user explicitly asks for it. Rely on the short resolution summary in `docs/PROGRESS.md` instead. This keeps converged, long-form discussions from being repeatedly pulled into context once they're settled.

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