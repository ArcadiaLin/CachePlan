# Research overview draft

Suggested caption: External research agents interpret papers and associated
materials, make semantic judgments, and submit explicit operations to a
knowledge middleware. A semantic data model connects shared objects,
conditioned claims, experiments, and evidence while retaining identity,
provenance, and versions. Query, composition, and update operations support
reuse in later research tasks and continued accumulation from new readings and
checks. The diagram illustrates the proposed scope; task examples are not a
fixed benchmark, and no performance or effectiveness results are claimed.

The two agent boxes represent reading and later-use roles, not a requirement
for separate agents. Graph links illustrate stored relationships rather than
inferences performed inside the middleware. The graph is illustrative, not a
complete schema. The left return arrow supplies stored records for reading and
integration; the right return loop represents explicit agent-submitted updates.

## Rendering and checks

- Python/matplotlib only; 183 × 108 mm, editable PDF/SVG, PNG at 600 dpi.
- Minimum rendered PDF font: 5.2 pt; text audit passed.
- Rendered collision audit: 0 failures, 0 warnings. Contained text inside
  record and agent boxes is intentional.
- Alignment: one continuous schematic on one axes; panel alignment is not
  applicable, as recorded in the alignment JSON.
- Visual inspection: sources, interpretation, central model, later-use role,
  and update loop inspected; labels are readable and connectors are clear.
- Static preflight: no failures. The two warnings concern absent TIFF and
  unresolved static width. PNG is the preview and PDF/SVG are the vector
  deliverables; the script explicitly sets 183 × 108 mm.
- No numerical data, statistical estimates, or third-party figure assets.
- Draft for research discussion; exact venue submission compliance is not
  asserted.

Re-render from the repository root with an environment containing matplotlib:

```bash
python paper/figures/research-overview/draw.py
```

Rendering environment: Python 3.12.14, matplotlib 3.11.2; collision checks used
PyMuPDF 1.28.2. Dependencies were installed in a temporary isolated environment;
the repository dependency declarations and lockfile were not changed.
