# Workflow Details

Read this only when the main skill instructions do not answer which output to inspect or which fields the agent should supplement.

## Output Files

- `paper_record.yml`: generated draft record. Keep it as the parser baseline until merge and validation pass.
- `resource_records.yml`: generated generic resource candidates from explicit URLs only.
- `structure.json`: title, authors, abstract, section outline, appendix flag, enriched figures, and tables.
- `figures/`: copied figure assets from the LaTeX package. Files are copied as-is, with no format conversion.
- `figure_manifest.json`: figure ids, labels, captions, copied asset paths, source paths, caption source, and missing asset notes.
- `citations.json`: cite keys, parsed references, and local citation contexts.
- `resources.json`: raw explicit URL candidates, all mechanically typed as generic `resource`.
- `run_report.json`: selected main TeX file, parse counts, metadata status, supplement status, and failure summary.
- `agent_edit_hints.json`: validation issues and repair hints with path/line/message/suggested_fix.

## Parser Candidates

The scripts may fill or propose:

- Paper id, source type, arXiv id, URL, title, authors, year, DOI, abstract.
- Section outline, appendix/supplement flags, figure/table captions, copied figure assets, and figure manifest records.
- Citation cite keys, reference titles, local context text, evidence section/quote.
- Explicit URL resource candidates. The parser does not infer code/dataset/model/baseline kinds or introduced/used status from names or hosts.
- Cited paper ids when the bibliography has explicit arXiv ids.

These fields can be incomplete or wrong when the TeX template is unusual. Treat them as auditable starting points.

## Agent Judgments

The agent must read paper evidence before adding:

- Paper type, research problem, and target domain.
- Contributions, abstract-derived claims, limitations, and future work.
- Experiment task, dataset/benchmark ids, metrics, baselines, and whether candidates are truly used.
- Figure descriptions and parser review tags based on captions and nearby text.
- Citation function only; do not link citations to local claims.
- Resource descriptions, domains, skill candidacy, wrapping difficulty, and semantic resource corrections.

Resource judgment should use paper evidence beyond URL candidates: check abstract release statements, contribution bullets, method overviews, dataset/benchmark sections, experiment setup, table captions, appendix data descriptions, and ethics/impact statements.

Every contribution, limitation, future work item, and resource judgment should carry section/quote evidence when possible. Claims come from the abstract only, are limited to 1-2 items, and must not carry evidence.

## Leave Empty For Later

Do not fill availability checks, downloaded files, documentation status, input/output formats, reverse indexes, cross-paper relations, or external reachability unless the user explicitly asks for a verification stage.

## Reading Order

1. `run_report.json`
2. `agent_edit_hints.json`
3. `structure.json`
4. `figure_manifest.json` and `figures/`
5. `citations.json`
6. `resources.json` and `resource_records.yml`
7. `references/field_guide.md`
8. Paper source/PDF text as needed for semantic judgment
9. `paper_record.yml`

Then write `agent_judgment.yml`, merge, lint, and edit only the smallest required final locations.
