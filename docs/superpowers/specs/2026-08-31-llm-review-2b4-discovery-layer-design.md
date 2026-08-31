# LLM-review 2b.4 — discovery layer — design

Backlog 2b.4 (pre-cut, after 2b.5). Makes the docs surface discoverable and cheap to
enter: an index with sizes, brief tool pages by default, guides trimmed to their
canonical homes. Nothing is deleted — full content moves behind explicit URIs.
Absorbs backlog 3.15 (chemistry sections out of conventions) and 3.14 (expression
analysis page).

Measured on `main` 2026-08-31 (post-2b.5, `95fbf0f`): tool pages 232k tok / 42 files
(bulk = `Few-shot examples`, e.g. genes_by_ontology 8.9k of 14.5k; `Response format`
~2k each); guide 28.7k (conventions 11.8k, concepts 6.2k, python_api 5.4k,
start_here 5.2k); analysis 25.4k / 4; ontologies 34.9k / 18; examples 4 scripts
2.2–9.3k tok, no TOC. The backlog's "kg_schema 26k → ~1k" is stale — 2b.2 already
got it to ~1.7k.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | New generated `docs://index` (~600 tok): every resource URI with token size and a one-line "read when…", grouped guide / tools / analysis / ontologies / examples. Built by `build_about_content.py` from the files themselves; registered first. | Sizes never go stale; an agent can budget before reading. |
| D2 | `docs://tools/{name}` becomes the BRIEF page (~1–1.5k tok): What it does / Parameters / one capped example (call + ~10-line envelope-key sketch) / top mistakes / chaining / pointer "full page: `docs://tools/{name}/full`". Full current content moves to `docs://tools/{name}/full`. Generator writes `references/tools/{name}.md` + `references/tools/full/{name}.md`. | Decided 2026-08-31: the default URI must be the cheap one. Brief surface ≈ 50k tok vs 232k. The envelope-key sketch matters more since 2b.5 dropped `outputSchema`. |
| D3 | `conventions` diet to a ≤5k cross-tool core: chemistry sections (transport trust ladder, direction-agnosticism, metabolite ID forms, ~1.3k) → `docs://analysis/metabolites` (absorbs 3.15); annotation-trust section (~1.3k) → `docs://analysis/annotation_evidence`. One-paragraph pointers remain. | Canonical homes; conventions is read early and often. |
| D4 | `start_here`: keep the family table + 16-shape decision tree; add cross-feeding and DE-by-functional-class recipes and "step 0 for enrichment: `ontology_landscape`"; trim the rest (target ≤4k). | The two recipes are the review's named gaps; the tree already routes well. Reconcile routing prose with the 2b.5 five-slot descriptions (deferred item from 2b.5). |
| D5 | Server `instructions` rewritten: first-call habit (`kg_release_info`), `docs://index` as the entry point, the `summary=True` habit, per-family size hints. Guides registered before tools in the resource list. | The instructions are the only text every session sees; today they enumerate URIs without costs. |
| D6 | New hand-authored `docs://analysis/expression`: DE tools + `response_matrix` / `gene_set_compare` reference (~140 lines moved from `guide/python_api`, pointer left). Absorbs 3.14. | Decided 2026-08-31: same canonical-homes motif, python_api is open anyway. |
| D7 | Scenario TOC comment block at the top of each `examples/*.py` (and mirrored in the `docs://index` line for each). | 9.3k-tok scripts are unskimmable without one. |

Out of scope: any tool/parameter/response change (2b.5 closed that surface); ontology
pages (already sized sanely); deleting content (everything moves, nothing dies);
2b.6/2b.6a.

## Mechanics

- **Generator** (`scripts/build_about_content.py`): per tool emit brief + full from
  the same YAML/Pydantic inputs. Brief example = the YAML's first example's call +
  a generated envelope-key sketch (top-level keys + one compact row, elided with
  `…`); brief mistakes = first 3 `mistakes` bullets; chaining kept whole. Full page
  = today's output, unchanged, written to `references/tools/full/{name}.md`.
  `docs://index` generated last from the emitted files (`len(bytes)//4` per file).
- **Registration** (`mcp_server/server.py`): `_DOC_DIRS` gains
  `docs://tools/{stem}/full` from `references/tools/full/`; registration order:
  index, guide, tools (brief), tools full, analysis, ontologies, examples.
- **Hand-authored moves** (D3, D4, D6): edited directly in
  `references/guide/*.md` / `references/analysis/*.md`; the moved text lands
  verbatim first, then is tightened in place. `analysis/expression.md` is new and
  hand-authored (update rule: CLAUDE.md analysis-docs section).
- **Lints**: `--lint` gains (a) index-freshness — every registered md file has an
  index row and no row points at a missing file; (b) brief-size — every brief page
  ≤ 2k tok; (c) existing lints run over the new `tools/full/` dir too.
- **Tests**: unit tests pin — index exists, covers all files, sizes within 20% of
  actual; every tool has brief + full resources registered; brief page contains the
  five section heads + the `/full` pointer; conventions ≤ 5k tok; instructions
  mention `docs://index`.

## Verification

Unit suite + new lints green; `refresh_examples.py --check` unaffected (it checks the
YAML `response:` blocks, which do not move); docs
regenerated; `-m kg` untouched surfaces only (no query changes, so the named
selections from 2b.5 are not rerun); manual read of index + 3 brief pages + the two
recipe additions. Live check rides the same post-restart `/mcp` pass as 2b.5.

Backlog rows closed by this work: 2b.4, 3.14, 3.15 (delete on ship).
