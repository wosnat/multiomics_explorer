# kegg_module_completeness

## What it does

Report how complete each KEGG module is per organism (KEGG Mapper bands; KO + EC); rows = organism x module, a step covered.

Use for what a strain can run or lacks; 'complete' = every step annotated, not shown to run; no edge != no genes.
Filters: organism, module_ids (classes expand), status, module_type.
Returns: by_status, by_class, top_organisms, top_modules (cap 20), no_edge_count; one row = (organism, module, status, missing_kos).
docs://tools/kegg_module_completeness. Routing: missing_kos to genes_by_function; genes: genes_by_ontology(ontology='kegg_module', min_gene_set_size=1).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| list[string] \| None | None | One organism, a list (each entry word-matched and may expand to several strains), or omit for all organisms. A single string must resolve to ONE organism. See list_organisms. |
| module_ids | list[string] \| None | None | KEGG module IDs (e.g. 'kegg.module:M00531'; bare 'M00531' accepted). A class, subclass or type ID expands to every module under it. None = all modules. |
| status | list[string ('complete', 'one_step_missing', 'two_steps_missing', 'partial')] \| None | None | Keep rows in these bands. Filters rows and band counts, never the no-edge counts. Values: list_filter_values with filter_type kegg_module_status. |
| module_type | string ('pathway', 'signature') \| None | pathway | 'pathway' (default; routes) or 'signature' (marker sets such as drug resistance); None = both. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's full page, docs://tools/{tool}/full. |
| limit | int | 50 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### What can one strain run — complete pathway modules by class

```python
kegg_module_completeness(organism="Prochlorococcus MED4", status=["complete"], summary=True)
```

## Response sketch

```expected-keys
total_entries, total_matching, returned, truncated, offset, organism_name, organisms_in_scope, modules_in_scope, by_status, no_edge_count, by_class, top_organisms, top_modules, not_found_modules, not_matched_modules, not_found_organisms, warnings, results
```

Result row: `organism_name, module_id, module_name, module_type, module_class, status, steps_total, steps_present, steps_present_via_ec, missing_step_indices, missing_kos`

## Common mistakes

- No edge does not mean no genes. A strain has an edge to a module only when at least one step is covered, and a one-step complex module needs every subunit: Synechococcus elongatus PCC 7942 carries 5 of the 6 Photosystem II (M00161) subunit KOs, but psbD (K02706) has no KO, so the single step is uncovered and there is no row. Check `genes_by_ontology(ontology='kegg_module', term_ids=[...], organism=..., min_gene_set_size=1)` before calling a module absent (the default size floor of 5 drops most single-genome module gene sets).

- `complete` means every step has an annotated gene (KO, or the EC fallback), not that the route runs — expression, regulation and enzyme activity are not tested.

- One KO from `missing_kos` may not complete a step: the list flattens every KO named in the missing steps, and a `+` complex needs all its subunits while `,` alternatives need only one. Read `missing_step_definitions` (verbose) for the step's formula. A missing step that refers to another module contributes no KO.

## Chaining patterns

- list_organisms (per-row `complete_pathway_module_count`) → kegg_module_completeness(organism=..., status=['complete']) for the modules behind the count
- search_ontology(search_text=..., ontology='kegg_module') → kegg_module_completeness(module_ids=[...]) — module ids from a search
- kegg_module_completeness → genes_by_ontology(ontology='kegg_module', term_ids=[module_id], organism=..., min_gene_set_size=1) for the genes behind the KO-covered steps
- kegg_module_completeness (`missing_kos`) → genes_by_function / resolve_gene / gene_ontology_terms to look for an unannotated candidate; `kegg.orthology:{ko}` → ontology_term_details for what the KO is
- ontology_term_details(term_ids=[module_id], organism=...) gives one organism's status on one module (`organism_module_status`) without a call here
- pathway_enrichment(ontology='kegg_module', level=3) → kegg_module_completeness(organism=..., module_ids=[enriched term_ids]) — is the enriched module's route complete in the genome?

Full reference (all examples, full response format, verbose fields): `docs://tools/kegg_module_completeness/full`
