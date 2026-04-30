# Field-design rubric for tools

This rubric was distilled from the 2026-04-29 MCP usability audit
(`docs/superpowers/specs/2026-04-29-mcp-usability-audit.md`). Apply
when adding a new tool, modifying an existing tool's response schema, or
reviewing a tool change.

A tool's response schema passes the rubric iff:

- [ ] **Field examples are real KG values** — not placeholders, not stubs,
      not "TBD", not known-bad strings. The example a reader sees
      in `Field(description="... (e.g. ...)")` is a *prediction* of what real
      values look like; placeholder examples train the LLM to expect them.
- [ ] **Presence-only fields say so** — and name the drill-down tool that
      surfaces content. `annotation_types` was the canonical anti-example:
      a list of source names that does *not* predict term content
      informativeness, but the original description was silent on the
      limitation.
- [ ] **Coarse-summary fields signpost the drill-down tool by name** in the
      field description. The DM fields on `gene_overview` show the model:
      `"Use to route to genes_by_{kind}_metric drill-downs"`.
- [ ] **Tool docstring includes downstream direction** — "after this, drill
      into Y to get Z" — not just upstream callers ("use after X"). Pattern
      model: `gene_details` docstring naming `list_organisms`,
      `gene_homologs`, `gene_ontology_terms` for the relevant axes.
- [ ] **Response rows are typed Pydantic models** — not `list[dict]` —
      whenever the row shape is known. Untyped dict erodes self-
      documentation; the LLM can only discover field names by sampling.
- [ ] **Empty-result shapes are unambiguous** — `not_found` ≠ `not_matched`
      ≠ `no_groups` ≠ `out_of_pipeline_scope`, and each is documented in
      the envelope schema. When two zero-row outcomes have different
      meaning, surface the distinction structurally.
- [ ] **Field name predicts shape** — `gene_count` should describe a count
      of genes; if the field is a row count summed across timepoints,
      name it `cumulative_row_count`. Misleading names need explicit
      description disclaimers.
- [ ] **No Cypher-syntax jargon** in user-facing descriptions — `g{.*}`,
      APOC function names, etc. belong in builder docstrings, not in
      Pydantic field text.

When applying the rubric to an existing tool, run a local audit against
its Pydantic model + docstring and file a separate spec for any failing
clauses; do not bundle rubric-driven cleanup into unrelated tool work.
