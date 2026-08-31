# Research Progress

本文档是本仓库的主线追踪文档，记录当前研究方向的进展，以及 `docs/open-questions/` 中各问题的解决状态。

**给 agent 的约定**：一个 open-question 一旦在下表中被标记为 `RESOLVED`，其对应的原始文档已经是历史记录，**不要在未被用户明确要求的情况下读取它** —— 只需参考下表中的 Resolution 摘要即可。这是为了避免已收敛的长篇讨论反复被拉入上下文。仅当用户明确要求查看某个已解决问题的完整讨论过程时，才去读取原文档。

## Current direction

见 [`AGENTS.md`](../AGENTS.md)：cache-aware planning and execution in LLM agents（研究方向仍在演进中，以 AGENTS.md 中的描述为准）。

## Open Questions

| Question | Status | Doc | Resolution |
|---|---|---|---|
| Is agentic execution necessary for data-intensive workloads (P4A)? | OPEN | [open-questions/Necessity-of-agentic-execution.md](open-questions/Necessity-of-agentic-execution.md) | — |

## Decisions

尚无已收敛的决定。问题被解决后，在此追加一行，并可选地在 `docs/decisions/` 下补充完整推导过程。

| Decision | Date | Doc | Rationale (short) |
|---|---|---|---|

## Experiments

- [`experiments/p4a.md`](experiments/p4a.md) — P4A 项目实验记录
