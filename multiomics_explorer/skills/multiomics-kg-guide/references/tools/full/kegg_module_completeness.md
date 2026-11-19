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

## Response format

### Envelope

```expected-keys
total_entries, total_matching, returned, truncated, offset, organism_name, organisms_in_scope, modules_in_scope, by_status, no_edge_count, by_class, top_organisms, top_modules, not_found_modules, not_matched_modules, not_found_organisms, warnings, results
```

- **total_entries** (int): All organism-module completeness edges in the KG.
- **total_matching** (int): Rows matching every filter.
- **returned** (int): Rows in this response.
- **truncated** (bool): True when total_matching > offset + returned.
- **offset** (int): Offset into the matching rows.
- **organism_name** (string | None): The organism when exactly one is in scope (e.g. 'Prochlorococcus MED4'); null otherwise.
- **organisms_in_scope** (int): Organisms the call covers after resolution.
- **modules_in_scope** (int): Level-3 modules the call covers after module_ids expansion and module_type.
- **by_status** (list[KmcStatusCount]): Rows per band, all four bands in band order (after filters).
- **no_edge_count** (int): (organism, module) pairs in scope with no step covered (no row); independent of status.
- **by_class** (list[KmcByClass]): Complete breakdown per level-1 class with a module in scope: module_count, band counts, no_edge.
- **top_organisms** (list[KmcTopOrganism]): Organisms in scope sorted by complete desc, capped at 20 — compare length with organisms_in_scope; page rows for the full table.
- **top_modules** (list[KmcTopModule]): Modules in scope sorted by complete desc, capped at 20 — compare length with modules_in_scope; organisms_without_edge only when modules_in_scope <= 3.
- **not_found_modules** (list[string]): Input module_ids with no KEGG module node.
- **not_matched_modules** (list[string]): Input module_ids that exist but yield no module under module_type (set module_type='signature' or None).
- **not_found_organisms** (list[string]): Organism list entries matching no organism.
- **warnings** (list[string]): Advisory messages (e.g. not_matched_modules fix).

### Per-result fields

| Field | Type | Description |
|---|---|---|
| organism_name | string | Organism (e.g. 'Prochlorococcus MIT9313'). |
| module_id | string | KEGG module ID (e.g. 'kegg.module:M00531'). |
| module_name | string \| None (optional) | Module name (e.g. 'Assimilatory nitrate reduction, nitrate => ammonia'). |
| module_type | string \| None (optional) | 'pathway' (a route) or 'signature' (a marker set). |
| module_class | string \| None (optional) | Level-1 module class name (e.g. 'Energy metabolism'). |
| status | string | Completeness band: 'complete', 'one_step_missing', 'two_steps_missing', 'partial'. 'complete' = every step has an annotated gene (KO or EC fallback), not that the route is shown to run. |
| steps_total | int \| None (optional) | Steps in the module (optional '--' steps excluded). |
| steps_present | int \| None (optional) | Steps covered in this organism, by KO or EC fallback. |
| steps_present_via_ec | int \| None (optional) | Of steps_present, covered only through EC; KO-covered = steps_present - steps_present_via_ec. |
| missing_step_indices | list[int] (optional) | 1-based indices of uncovered steps; [] when complete. |
| missing_kos | list[string] (optional) | Every KO named in the missing steps, bare as stored (e.g. ['K00367','K00372','K10534']); prefix 'kegg.orthology:' to chain. One KO may not complete a step ('+' complexes need all subunits). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| module_subclass | string \| None (optional) | Level-2 subclass name (e.g. 'Nitrogen metabolism') (verbose only). |
| definition | string \| None (optional) | Module KO formula: space = next step, ',' = alternatives, '+' = complex subunits (verbose only). |
| missing_step_definitions | list[string] \| None (optional) | Formula of each missing step, parallel to missing_step_indices (e.g. ['(K00367,K10534,K00372+K00360)']) (verbose only). |
| ec_filled_step_indices | list[int] \| None (optional) | Steps covered only through EC; [] when none (verbose only). |
| ec_genes | list[string] \| None (optional) | Locus tag filling each EC step, parallel to ec_filled_step_indices; a module ID ('M#####') = a module-reference step completed via EC; [] when none (verbose only). |

## Few-shot examples

### Example 1: What can one strain run — complete pathway modules by class

```example-call
kegg_module_completeness(organism="Prochlorococcus MED4", status=["complete"], summary=True)
```

*`by_class` breaks the complete modules down by KEGG class; drop `summary=True` to list them (rows read in KEGG module order for one organism). `total_matching` equals `list_organisms`' `complete_pathway_module_count`.*

```example-response
{
  "total_entries": 26004,
  "total_matching": 51,
  "returned": 0,
  "truncated": true,
  "offset": 0,
  "organism_name": "Prochlorococcus MED4",
  "organisms_in_scope": 1,
  "modules_in_scope": 382,
  "by_status": [
    {"status": "complete", "count": 51},
    {"status": "one_step_missing", "count": 0},
    {"status": "two_steps_missing", "count": 0},
    ...
  ],
  "no_edge_count": 183,
  "by_class": [
    {
      "class_id": "kegg.module:pathway_modules.amino_acid_metabolism",
      "class_name": "Amino acid metabolism",
      "module_count": 67,
      "complete": 14,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 30
    },
    {
      "class_id": "kegg.module:pathway_modules.biosynthesis_of_other_secondary_metabolites",
      "class_name": "Biosynthesis of other secondary metabolites",
      "module_count": 28,
      "complete": 0,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 23
    },
    {
      "class_id": "kegg.module:pathway_modules.biosynthesis_of_terpenoids_and_polyketides",
      "class_name": "Biosynthesis of terpenoids and polyketides",
      "module_count": 25,
      "complete": 2,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 18
    },
    ...
  ],
  "top_organisms": [
    {
      "organism_name": "Prochlorococcus MED4",
      "complete": 51,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 183
    }
  ],
  "top_modules": [
    {
      "module_id": "kegg.module:M00002",
      "module_name": "Glycolysis, core module involving three-carbon compounds",
      "module_type": "pathway",
      "complete": 1,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 0
    },
    {
      "module_id": "kegg.module:M00004",
      "module_name": "Pentose phosphate pathway (Pentose phosphate cycle)",
      "module_type": "pathway",
      "complete": 1,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 0
    },
    {
      "module_id": "kegg.module:M00005",
      "module_name": "PRPP biosynthesis, ribose-5P => PRPP",
      "module_type": "pathway",
      "complete": 1,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 0
    },
    ...
  ],
  "...": "4 empty fields omitted (not_found_modules, not_matched_modules, not_found_organisms, warnings)",
  "results": []
}
```

### Example 2: One module across every strain — who has it, who lacks it

```example-call
kegg_module_completeness(module_ids=["M00531"], limit=5)
```

*Bare `M00531` is accepted. Rows are only strains with a step covered; strains with no edge are counted in `no_edge_count` and named in `top_modules[0].organisms_without_edge` (names are listed when 3 or fewer modules are in scope).*

```example-response
{
  "total_entries": 26004,
  "total_matching": 82,
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "...": "5 empty fields omitted",
  "organisms_in_scope": 118,
  "modules_in_scope": 1,
  "by_status": [
    {"status": "complete", "count": 56},
    {"status": "one_step_missing", "count": 26},
    {"status": "two_steps_missing", "count": 0},
    ...
  ],
  "no_edge_count": 36,
  "by_class": [
    {
      "class_id": "kegg.module:pathway_modules.energy_metabolism",
      "class_name": "Energy metabolism",
      "module_count": 1,
      "complete": 56,
      "one_step_missing": 26,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 36
    }
  ],
  "top_organisms": [
    {
      "organism_name": "Cyanobium NS01",
      "complete": 1,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 0
    },
    {
      "organism_name": "Cyanobium PCC6307",
      "complete": 1,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 0
    },
    {
      "organism_name": "Cyanobium PCC7001",
      "complete": 1,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 0
    },
    ...
  ],
  "top_modules": [
    {
      "module_id": "kegg.module:M00531",
      "module_name": "Assimilatory nitrate reduction, nitrate => ammonia",
      "module_type": "pathway",
      "complete": 56,
      "one_step_missing": 26,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 36,
      "organisms_without_edge": ["Marinobacter (MarRef v6)", "Prochlorococcus AS9601", "Prochlorococcus EQPAC1", ...]
    }
  ],
  "results": [
    {
      "organism_name": "Cyanobium NS01",
      "module_id": "kegg.module:M00531",
      "module_name": "Assimilatory nitrate reduction, nitrate => ammonia",
      "module_type": "pathway",
      "module_class": "Energy metabolism",
      "status": "complete",
      "steps_total": 2,
      "steps_present": 2,
      "steps_present_via_ec": 0,
      "missing_step_indices": [],
      "missing_kos": []
    },
    {
      "organism_name": "Cyanobium PCC6307",
      "module_id": "kegg.module:M00531",
      "module_name": "Assimilatory nitrate reduction, nitrate => ammonia",
      "module_type": "pathway",
      "module_class": "Energy metabolism",
      "status": "complete",
      "steps_total": 2,
      "steps_present": 2,
      "steps_present_via_ec": 0,
      "missing_step_indices": [],
      "missing_kos": []
    },
    {
      "organism_name": "Cyanobium PCC7001",
      "module_id": "kegg.module:M00531",
      "module_name": "Assimilatory nitrate reduction, nitrate => ammonia",
      "module_type": "pathway",
      "module_class": "Energy metabolism",
      "status": "complete",
      "steps_total": 2,
      "steps_present": 2,
      "steps_present_via_ec": 0,
      "missing_step_indices": [],
      "missing_kos": []
    },
    ...
  ]
}
```

### Example 3: A near-miss — which KOs to look for

```example-call
kegg_module_completeness(organism="Prochlorococcus MIT9313", module_ids=["M00531"], verbose=True)
```

*MIT9313 has nitrite reductase but not nitrate reductase: `missing_kos` lists every KO named in the missing step, and `missing_step_definitions` (verbose) shows how they combine.*

```example-response
{
  "total_entries": 26004,
  "total_matching": 1,
  "returned": 1,
  "truncated": false,
  "offset": 0,
  "organism_name": "Prochlorococcus MIT9313",
  "organisms_in_scope": 1,
  "modules_in_scope": 1,
  "by_status": [
    {"status": "complete", "count": 0},
    {"status": "one_step_missing", "count": 1},
    {"status": "two_steps_missing", "count": 0},
    ...
  ],
  "no_edge_count": 0,
  "by_class": [
    {
      "class_id": "kegg.module:pathway_modules.energy_metabolism",
      "class_name": "Energy metabolism",
      "module_count": 1,
      "complete": 0,
      "one_step_missing": 1,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 0
    }
  ],
  "top_organisms": [
    {
      "organism_name": "Prochlorococcus MIT9313",
      "complete": 0,
      "one_step_missing": 1,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 0
    }
  ],
  "top_modules": [
    {
      "module_id": "kegg.module:M00531",
      "module_name": "Assimilatory nitrate reduction, nitrate => ammonia",
      "module_type": "pathway",
      "complete": 0,
      "one_step_missing": 1,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 0,
      "organisms_without_edge": []
    }
  ],
  "...": "4 empty fields omitted (not_found_modules, not_matched_modules, not_found_organisms, warnings)",
  "results": [
    {
      "organism_name": "Prochlorococcus MIT9313",
      "module_id": "kegg.module:M00531",
      "module_name": "Assimilatory nitrate reduction, nitrate => ammonia",
      "module_type": "pathway",
      "module_class": "Energy metabolism",
      "status": "one_step_missing",
      "steps_total": 2,
      "steps_present": 1,
      "steps_present_via_ec": 0,
      "missing_step_indices": [1],
      "missing_kos": ["K00367", "K00372", "K10534"],
      "module_subclass": "Nitrogen metabolism",
      "definition": "(K00367,K10534,(K00372-K00360)) (K00366,K17877,(K26139+K26138),K00361)",
      "missing_step_definitions": ["(K00367,K10534,(K00372-K00360))"],
      "ec_filled_step_indices": [],
      "ec_genes": []
    }
  ]
}
```

### Example 4: A class sweep across chosen strains

```example-call
kegg_module_completeness(organism=["Prochlorococcus MED4", "Prochlorococcus MIT9313", "Synechococcus WH8102"], module_ids=["kegg.module:pathway_modules.energy_metabolism.nitrogen_metabolism"])
```

*A class or subclass id expands to every module under it. `top_organisms[*].no_edge` counts the modules in scope with no step covered in each strain.*

```example-response
{
  "total_entries": 26004,
  "total_matching": 2,
  "returned": 2,
  "truncated": false,
  "offset": 0,
  "...": "5 empty fields omitted",
  "organisms_in_scope": 3,
  "modules_in_scope": 7,
  "by_status": [
    {"status": "complete", "count": 1},
    {"status": "one_step_missing", "count": 1},
    {"status": "two_steps_missing", "count": 0},
    ...
  ],
  "no_edge_count": 19,
  "by_class": [
    {
      "class_id": "kegg.module:pathway_modules.energy_metabolism",
      "class_name": "Energy metabolism",
      "module_count": 7,
      "complete": 1,
      "one_step_missing": 1,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 19
    }
  ],
  "top_organisms": [
    {
      "organism_name": "Synechococcus WH8102",
      "complete": 1,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 6
    },
    {
      "organism_name": "Prochlorococcus MED4",
      "complete": 0,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 7
    },
    {
      "organism_name": "Prochlorococcus MIT9313",
      "complete": 0,
      "one_step_missing": 1,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 6
    }
  ],
  "top_modules": [
    {
      "module_id": "kegg.module:M00531",
      "module_name": "Assimilatory nitrate reduction, nitrate => ammonia",
      "module_type": "pathway",
      "complete": 1,
      "one_step_missing": 1,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 1
    },
    {
      "module_id": "kegg.module:M00528",
      "module_name": "Nitrification, ammonia => nitrite",
      "module_type": "pathway",
      "complete": 0,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 3
    },
    {
      "module_id": "kegg.module:M00529",
      "module_name": "Denitrification, nitrate => nitrogen",
      "module_type": "pathway",
      "complete": 0,
      "one_step_missing": 0,
      "two_steps_missing": 0,
      "partial": 0,
      "no_edge": 3
    },
    ...
  ],
  "results": [
    {
      "organism_name": "Synechococcus WH8102",
      "module_id": "kegg.module:M00531",
      "module_name": "Assimilatory nitrate reduction, nitrate => ammonia",
      "module_type": "pathway",
      "module_class": "Energy metabolism",
      "status": "complete",
      "steps_total": 2,
      "steps_present": 2,
      "steps_present_via_ec": 0,
      "missing_step_indices": [],
      "missing_kos": []
    },
    {
      "organism_name": "Prochlorococcus MIT9313",
      "module_id": "kegg.module:M00531",
      "module_name": "Assimilatory nitrate reduction, nitrate => ammonia",
      "module_type": "pathway",
      "module_class": "Energy metabolism",
      "status": "one_step_missing",
      "steps_total": 2,
      "steps_present": 1,
      "steps_present_via_ec": 0,
      "missing_step_indices": [1],
      "missing_kos": ["K00367", "K00372", "K10534"]
    }
  ]
}
```

### Example 5: Near-miss to candidate genes

```
Step 1: kegg_module_completeness(organism="Prochlorococcus MIT9313", module_ids=["M00531"])
        → status 'one_step_missing', missing_kos ['K00367', 'K00372', 'K10534']

Step 2: genes_by_function(search_text="nitrate reductase", organism="Prochlorococcus MIT9313")
        → is there an unannotated candidate, or is the step really absent?

Step 3: genes_by_ontology(ontology="kegg_module", term_ids=["kegg.module:M00531"], organism="Prochlorococcus MIT9313", min_gene_set_size=1)
        → the genes behind the KO-covered step
```

## Chaining patterns

```
list_organisms (per-row `complete_pathway_module_count`) → kegg_module_completeness(organism=..., status=['complete']) for the modules behind the count
search_ontology(search_text=..., ontology='kegg_module') → kegg_module_completeness(module_ids=[...]) — module ids from a search
kegg_module_completeness → genes_by_ontology(ontology='kegg_module', term_ids=[module_id], organism=..., min_gene_set_size=1) for the genes behind the KO-covered steps
kegg_module_completeness (`missing_kos`) → genes_by_function / resolve_gene / gene_ontology_terms to look for an unannotated candidate; `kegg.orthology:{ko}` → ontology_term_details for what the KO is
ontology_term_details(term_ids=[module_id], organism=...) gives one organism's status on one module (`organism_module_status`) without a call here
pathway_enrichment(ontology='kegg_module', level=3) → kegg_module_completeness(organism=..., module_ids=[enriched term_ids]) — is the enriched module's route complete in the genome?
```

## Common mistakes

- No edge does not mean no genes. A strain has an edge to a module only when at least one step is covered, and a one-step complex module needs every subunit: Synechococcus elongatus PCC 7942 carries 5 of the 6 Photosystem II (M00161) subunit KOs, but psbD (K02706) has no KO, so the single step is uncovered and there is no row. Check `genes_by_ontology(ontology='kegg_module', term_ids=[...], organism=..., min_gene_set_size=1)` before calling a module absent (the default size floor of 5 drops most single-genome module gene sets).

- `complete` means every step has an annotated gene (KO, or the EC fallback), not that the route runs — expression, regulation and enzyme activity are not tested.

- One KO from `missing_kos` may not complete a step: the list flattens every KO named in the missing steps, and a `+` complex needs all its subunits while `,` alternatives need only one. Read `missing_step_definitions` (verbose) for the step's formula. A missing step that refers to another module contributes no KO.

- `missing_kos` are bare `K#####`; prefix `kegg.orthology:` to chain into `ontology_term_details` or `genes_by_ontology(ontology='kegg', ...)`.

- `top_organisms` and `top_modules` are capped at 20 — compare their length with `organisms_in_scope` / `modules_in_scope`, and page rows (`limit` / `offset`) for the whole table. `by_status` and `by_class` are complete.

```mistake
kegg_module_completeness(module_ids=['M00627'])  # a signature module under the default module_type='pathway' lands in not_matched_modules
```

```correction
kegg_module_completeness(module_ids=['M00627'], module_type='signature')  # or module_type=None for both kinds
```

- `status` filters rows, `by_status`, `by_class` and the `top_*` band counts, never the no-edge counts (`no_edge_count`, `no_edge`, `organisms_without_edge`).

- `organism` follows `genes_by_ontology`: a string names exactly one strain (an ambiguous name raises), a list is word-matched and can expand to many strains (unmatched entries → `not_found_organisms`), `None` covers every organism with genes.

## Package import equivalent

```python
from multiomics_explorer import kegg_module_completeness

result = kegg_module_completeness()
# returns dict with keys: total_entries, total_matching, returned, truncated, offset, organism_name, organisms_in_scope, modules_in_scope, by_status, no_edge_count, by_class, top_organisms, top_modules, not_found_modules, not_matched_modules, not_found_organisms, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
