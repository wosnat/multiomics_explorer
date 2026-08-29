# Docs review pass (Phase 1b)

A reviewer pass over every served doc surface, run once per release (not
per KG rebuild — `absorb-kg-rebuild` covers the mechanical part there).
The lints (`tests/unit/test_docs_lint.py`, `test_docs_kg_claims.py`,
`test_about_examples.py`) catch identifiers, vocab values, numbers, links,
example responses. This pass catches what they cannot: sentences that were
true about a previous build, routing advice that no longer matches the
tools, and pages that explain the wrong thing well.

## Surfaces (one reviewer agent each; run in parallel, read-only)

| # | Surface | Reads against |
|---|---|---|
| 1 | `references/guide/*.md` (start_here, conventions, concepts, python_api) | CLAUDE.md tool table, `ONTOLOGY_CONFIG`, live `kg_release_info` |
| 2 | `references/tools/*.md` — discovery + gene tools | Pydantic models in `mcp_server/tools.py`; run each `call:` |
| 3 | `references/tools/*.md` — ontology + enrichment + trust tools | same + `docs://analysis/annotation_evidence` |
| 4 | `references/tools/*.md` — DE / DM / cluster / chemistry / assay tools | same |
| 5 | `references/ontologies/*.md` + `inputs/ontologies/*.yaml` | live KG (`search_ontology`, `ontology_term_details`, `run_cypher`) |
| 6 | `references/analysis/*.md` + `examples/*.py` + `tools.py` docstrings + CLAUDE.md | the code they describe; run the examples |

## Reviewer checklist (each finding: file:line, quote, what is wrong, fix, severity P1–P3)

1. **Stale behaviour** — does the sentence describe how the KG / tool
   behaved in an earlier build? Verify live; do not trust the doc.
2. **Routing** — "use X for Y" claims: is X still the right tool, and does
   the named param / envelope key exist (`kg_schema`, Pydantic model)?
3. **Defaults** — every stated default matches the `Field(default=…)`.
4. **Examples** — every example call runs and the response makes the point
   the surrounding prose makes.
5. **Duplication** — the same fact explained in >1 place with different
   wording; keep one canonical home and link.
6. **Pitfalls** — the "common mistakes" reflect mistakes the tool can still
   make (not ones a since-shipped fix removed).
7. **Length** — CLAUDE.md rows are routing one-liners; a tool page under
   ~150 lines unless it is the canonical home of a concept.

## Output

Findings go to the session scratchpad as `docs_review_<date>.md` grouped by
surface and severity. Then:

- P1/P2 with a mechanical fix → fix now (YAML / tools.py / analysis md),
  regenerate (`build_about_content.py`), rerun the lints, commit
  `docs(review): …`.
- Anything not fixed → `docs/backlog.md` (one line, size, origin
  `docs-review <date>`).
- KG-side → `docs/kg-specs/<date>-*-asks.md`.
- Any sentence that asserts KG behaviour and survived → a
  `inputs/lint/kg_claims.yaml` entry.
- One CHANGELOG `[Unreleased]` line: "Docs review <date>: N findings, M fixed".
