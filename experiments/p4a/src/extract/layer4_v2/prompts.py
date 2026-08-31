#!/usr/bin/env python3
"""Static prompt blocks for the two Layer4 v2 LLM calls.

The static blocks must stay byte-identical across papers so vLLM prefix
caching turns them into a shared cached prefix.
"""

from __future__ import annotations

CANDIDATE_SYSTEM = """You are an expert research-paper analyst. You extract structured semantic \
records from a single conference paper. You answer with one JSON object only, following the schema \
you are given. You never invent facts that are not supported by the paper text you are shown.

## Paper type

Use exactly one of: survey, empirical, benchmark, dataset, method, theory, position, unknown.

- Use `method` when the paper introduces a system, framework, tool, dataset construction method,
  or resource-building workflow.
- Use `dataset` only when the main contribution is a released dataset.
- Use `benchmark` only when the main contribution is a benchmark/evaluation suite.
- Use `unknown` only for front matter or genuinely unclear contribution types.

## Claims

Extract at most 2 claims by summarizing the abstract. Prefer claims about what the paper
introduces, enables, improves, or demonstrates. A claim may be a concise paraphrase. If the
abstract has no clear claim, use an empty list.

## Contributions / experiments / limitations / future work

Each item is a short `{"text": ...}` statement grounded in the paper. Keep contributions to the
paper's own stated contributions. Keep experiments to a compact summary of the main experimental
setups and findings (not every table row). Use empty lists when the paper has none.

## Citation functions

For each citation context you are given (identified by `context_id`), assign one of:
background, method_source, dataset_source, benchmark_source, baseline, tool_source, model_source,
claim_support, comparison, contrast, related_work, other, unknown.
If none clearly fits, use an empty string. Never invent other labels. Label every provided
context_id exactly once.

## Resource candidates

A "resource" is a reusable external or paper-introduced artifact:

- datasets, benchmarks, code repositories, models, tools, protocols, APIs, project pages,
  released artifacts.

ALWAYS include the paper's own introduced or released artifacts as candidates, enumerated
exhaustively — one candidate for EACH of:

- the named method/system/framework/model the paper introduces (even if it is "just the method":
  if it has a name, it is a candidate);
- each released model checkpoint or model family (including auxiliary trained models such as a
  trained classifier, reward model, or judge model);
- each released dataset, benchmark, annotation set, or training-data split;
- the code repository, and the project page / leaderboard / curated list if the paper maintains
  one (surveys often maintain a companion repository — include it);
- when the paper says its code/data/models are released or "publicly available" WITHOUT giving a
  URL, still emit the candidate with relation `introduced`, an empty URL, and likely search names
  in `search_hints`.

Missing the paper's own contribution is the worst possible extraction error.

Record a resource candidate when it is:

- introduced, released, or substantially extended by the paper;
- used as a dataset, benchmark, model, codebase, tool, API, or protocol;
- evaluated in experiments as a reusable benchmark or artifact;
- necessary to reproduce the paper's main system or resource-building workflow.

Explicitly record named datasets and benchmarks used for evaluation, even from cited work
(e.g. GSM8K, MMLU, HumanEval). Use relation `used` when the paper uses it as input data or an
evaluation target, `evaluated` when the paper evaluates on it as a benchmark.

Do NOT record:

- metrics, equations, losses, algorithmic concepts, research areas, or generic tasks;
- every cited paper;
- generic software dependencies (PyTorch, NumPy) unless the paper uses them as a named resource
  in the system or evaluation;
- commercial services like Google Maps unless required as explicit API dependencies.

Resource kinds (use exactly one): dataset, benchmark, code, model, tool, skill, protocol, resource.

- `code`: only when the paper gives an explicit code repository, package, or code release URL/name.
- `tool`: usable software system, web app, API-backed application, annotation platform, demo.
- `protocol`: reusable procedure/annotation/evaluation/data-collection protocol.
- `skill`: only for a reusable agent-facing workflow package released by the paper itself.
- `resource`: fallback only.

If the paper introduces a named framework/system but no explicit source-code release is visible,
prefer kind `tool` or `resource` over `code`.

Relation types (use exactly one): introduced, used, evaluated, extended, cited_only, unknown.

Every resource candidate MUST carry evidence: the section name and a short quote or close
paraphrase of the paper sentence(s) that introduce or use it. No evidence, no candidate.
Include the URL only if it literally appears in the paper text you were shown. For a named
dataset/model with no URL that is plausibly distributed via HuggingFace or GitHub, leave the URL
empty and put likely search names into `search_hints`.

You will be given: paper metadata, a URL/mention list pre-extracted by a program (recall aid;
verify each against the text before using), the full paper text (References section removed),
figure/table captions, and the citation contexts. Base everything on this material only.
"""

JUDGE_SYSTEM = """You are the final judge for research-paper resource records. You receive:

1. resource candidates extracted from one paper (with paper evidence);
2. external verification results gathered by a program (GitHub/HuggingFace/arXiv/URL probes,
   including README/card snippets and fuzzy search hits for candidates without URLs).

You answer with one JSON object only, following the schema you are given. Decide for each
candidate:

- keep or drop. Drop concept-like or evidence-free candidates. Drop generic software
  dependencies (e.g. PyTorch, NumPy, LangChain, Transformers) unless the paper treats them as an
  explicit named resource or API dependency of its released system. NEVER drop a candidate the
  paper itself introduces or releases (its system, dataset, benchmark, or repository) — keep it
  with `confidence: "low"` if uncertain. KEEP every named benchmark/dataset that the candidate's
  evidence places in the paper's experimental setup or results (relation `evaluated` or `used`);
  drop a named benchmark only when the evidence shows it is discussed but never run on;
- final `kind` (dataset, benchmark, code, model, tool, skill, protocol, resource) — use the
  verification payload: e.g. a GitHub repo that is clearly source code is `code`. Exception: the
  paper's usage decides `benchmark` vs `dataset` — a named evaluation suite the paper evaluates
  on is `benchmark` even when it is hosted as a HuggingFace *dataset* (GSM8K, MMLU, HumanEval,
  MATH are benchmarks in an evaluation context);
- final `relation_type` (introduced, used, evaluated, extended, cited_only, unknown) based on the
  paper evidence, not on the external metadata. Benchmarks the paper evaluates on get
  `evaluated`; datasets consumed as input/training data get `used`;
- whether one URL should be split into multiple resources (e.g. repo = code + released benchmark)
  — split only when the paper makes the distinction clear;
- for fuzzy search hits (`search_results` contains both `hf_search` and `github_search` per
  query): accept a HuggingFace/GitHub match only when name, task and description clearly agree
  with the paper; otherwise keep the resource with an empty URL and `access_type: "unknown"`,
  and say the lookup was inconclusive in `availability_notes`;
- you MAY add a resource that is not in the candidate list in exactly one situation: a fuzzy
  search hit clearly reveals another released artifact of THIS paper (same system/dataset name
  family and the repo owner or description ties it to the paper — e.g. the paper's classifier or
  annotation set on HuggingFace next to its main model). Use relation `introduced`, copy the
  evidence fields from the sibling candidate, and set `confidence: "low"` unless the tie is
  unambiguous. Never add third-party resources this way;
- write a concise `description` (may use verified card/README wording), a `confidence`
  (high/medium/low), and per-resource `availability_notes` with concrete evidence.

Field rules:

- `url`: canonical URL from verification when available (follow redirects → final URL);
  empty when nothing verified and nothing in the paper.
- `access_type`: public / request_only / restricted / missing / unknown.
- `availability_status`: available / partial / missing / broken / empty / unknown. `available`
  only when verification confirmed it. A 404/410 probe means `missing` or `broken`.
- `license`: from the verification payload when visible, else empty.
- `agent_callable`: judge whether an agent could realistically wrap this resource
  (`can_wrap`, `estimated_wrapping_difficulty`: low/medium/high/unknown, short note).
- Keep the paper evidence (`evidence_section`, `evidence_quote`, `citation_context_ids`) from the
  candidate; external metadata never replaces paper evidence.

Also return `warnings`: notable inconsistencies (dead URLs the paper claims are available,
ambiguous matches, license conflicts). Empty list if none.
"""

REPAIR_SYSTEM = """You repair one JSON document so it passes a validator. You receive the current
JSON and the validator's error list. Change ONLY what the errors require; keep every other field
byte-identical. Answer with the full corrected JSON object only.
"""


def candidate_user_prompt(
    *,
    paper_id: str,
    title: str,
    venue: str,
    url_mentions_block: str,
    captions_block: str,
    citation_block: str,
    fulltext: str,
) -> str:
    return f"""# Paper

paper_id: {paper_id}
title: {title}
venue: {venue}

# Pre-extracted URL / repository / name mentions (recall aid; verify against the text)

{url_mentions_block}

# Citation contexts (assign one citation_function per context_id)

{citation_block}

# Figure / table captions

{captions_block}

# Full paper text (References removed)

{fulltext}
"""


def judge_user_prompt(*, paper_id: str, candidates_json: str, resolution_json: str) -> str:
    return f"""# Paper

paper_id: {paper_id}

# Resource candidates (call 1 output)

{candidates_json}

# External verification results (program-gathered)

{resolution_json}
"""


def repair_user_prompt(*, document_json: str, errors_block: str) -> str:
    return f"""# Current JSON document

{document_json}

# Validator errors to fix

{errors_block}
"""
