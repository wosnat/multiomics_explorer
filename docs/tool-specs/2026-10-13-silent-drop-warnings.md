# Silent-drop warnings: genes_by_ontology, metabolites_by_gene, list_metabolites

Mode B (cross-tool small change), backlog 2c.3 / 2c.4. (2c.5, the `list_metabolites` transport-reach caveat, was dropped from this spec on 2026-10-13: it waits on a KG precompute of most-specific transport reach per organism.) Origin: the 2026-10-06 Pro
N-import coculture analysis (`multiomics_analysis/analyses/2026-10-06-pro_n_import_coculture/gaps_and_friction.md`).

**Problem:** two filters drop data without saying so. The caller can't tell from the envelope
that the answer is incomplete. Every number below was verified against the live KG on 2026-10-13.

## 1. `genes_by_ontology`: size-filtered terms (2c.3)

**Today:** `min_gene_set_size=5` / `max_gene_set_size=500` (defaults tuned for enrichment) drop
terms in the Cypher. `filtered_out` lists only input `term_ids`, so in `level` mode nothing reports
the loss. Live: `genes_by_ontology('brite', organism='MED4', level=2, tree='transporters')` →
16 genes / 3 terms by default vs 57 genes / 23 terms with `min_gene_set_size=1,
max_gene_set_size=None`. `warnings` and `filtered_out` are both empty.

**Change:**
- New envelope field **`size_filtered_terms: int`**, always present: the number of terms that pass
  every other filter but fall outside [min, max]. It is 0 when nothing is dropped, and 0 without
  an extra query when the size filters are no-ops (`min_gene_set_size <= 1` and
  `max_gene_set_size is None`).
- New envelope field **`size_filtered_genes: int`**: distinct genes that appear *only* in the
  dropped terms (genes lost from `total_genes`).
- **Warning** when `size_filtered_terms > 0`: `"{n} terms ({g} genes not otherwise covered) fell
  outside min_gene_set_size={min} / max_gene_set_size={max} and were dropped. The defaults suit
  enrichment; to enumerate every gene pass min_gene_set_size=1, max_gene_set_size=None."`
- **Cost:** one extra aggregate (the per-term + per-gene query with size filters disabled). It
  runs only when a size filter is active. The API diffs it against the filtered result.
- **Not changed:** the defaults, `filtered_out`, and the enrichment tools (where dropping by size
  is intended and documented).

## 2. `metabolites_by_gene(metabolite_elements=…)` and `list_metabolites(elements=…)`: no-formula metabolites (2c.4)

**Today:** metabolites with no formula have empty `m.elements`, so they never match an element
filter. This is documented in the param text, but nothing reports the count. KG-wide, 374 of 3,356
metabolites (11%) have no formula, mostly generic classes: "amino acid", "dipeptide", "Polyamine",
cytochromes, "Lipopolysaccharide". In the analysis this silently removed 249 MED4 transport
metabolites (4,105 rows), including N-bearing classes.

**Change (both tools):**
- New envelope field **`no_formula_excluded`**. It is present only when the element filter is set
  (absent = not applicable).
  - `metabolites_by_gene`: rows (and distinct metabolites, `no_formula_excluded_metabolites`) that
    pass every other filter but have empty `m.elements`.
  - `list_metabolites`: metabolites that pass every other filter but have empty `m.elements`.
- **Warning** when > 0: `"{n} metabolites have no formula and can never match an element filter
  (often generic classes such as 'amino acid' or 'dipeptide'). Re-run without
  {metabolite_elements|elements} to inspect them."`
- **Cost:** one extra count query when the filter is set. It uses the tool's existing condition
  builder with the element condition swapped for `size(coalesce(m.elements, [])) = 0`.

## Docs

`inputs/tools/{genes_by_ontology,metabolites_by_gene,list_metabolites}.yaml`: one `mistakes`
entry each, pointing at the new field or warning. Regenerate about-content. Add the new envelope
fields to the Pydantic response models. Add a CHANGELOG entry under Fixed/Changed.

## Implementation notes (frozen)

- **2c.3:** in `api.genes_by_ontology`, when `min_gene_set_size > 1 or max_gene_set_size is not None` and per_term is not short-circuited, re-run the existing `build_genes_by_ontology_per_term` + `build_genes_by_ontology_per_gene` with `min_gene_set_size=0, max_gene_set_size=None` (all other args identical). `size_filtered_terms = len(unfiltered_per_term) - len(per_term)`; `size_filtered_genes = len(unfiltered_per_gene) - len(per_gene)`. No new builder. Otherwise both are 0 and no extra query runs. Response model `GenesByOntologyResponse` gains both `int` fields (default 0).
- **2c.4:** new builders `build_metabolites_by_gene_no_formula_count(...)` (same signature as `build_metabolites_by_gene_summary` minus nothing; it ignores `metabolite_elements` and requires `size(coalesce(m.elements, [])) = 0` in both arms; RETURN `rows`, `metabolites` (count DISTINCT m)) and `build_list_metabolites_no_formula_count(...)` (same filters as `build_list_metabolites_summary`; reuses `_list_metabolites_where` with `elements=None` plus the empty-elements condition; RETURN `metabolites`). The API calls them only when the element filter is set (non-empty after normalisation). Envelope: `metabolites_by_gene` gains `no_formula_excluded` (rows) + `no_formula_excluded_metabolites`; `list_metabolites` gains `no_formula_excluded` (metabolites). Both are absent when the filter is unset (Pydantic `int | None = None`, sparse/omitted per the absent-vs-null convention used by that response model).
- Warnings are appended to the existing `warnings` list. Exact text as in §1 / §2 (`{metabolite_elements|elements}` = the tool's own param name).

## Tests

- Unit: builder tests for the new count queries. API tests for each field (present / absent / 0)
  and each warning (fires / doesn't fire), with no extra query when the filter is a no-op. Wrapper
  tests for the new fields.
- `-m kg`: BRITE transporters level=2 MED4 → `size_filtered_terms == 20`,
  `warnings` non-empty. `list_metabolites(elements=['N'])` → `no_formula_excluded > 0` (metabolites with no formula pass the other filters); `metabolites_by_gene(MED4 transporter genes, metabolite_elements=['N'])` → `no_formula_excluded > 0`.
- Regression goldens: the new fields appear in affected cases (`--force-regen`, classified diff).
- Edge-case scenarios: the existing ones cover these tools. Confirm the new fields hold up on
  degenerate inputs (empty term set, no element match).
