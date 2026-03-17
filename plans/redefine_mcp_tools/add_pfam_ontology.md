# Plan: Add Pfam domain/clan ontology to MCP tools

Add `pfam` as a single ontology type to `search_ontology`, `genes_by_ontology`,
and `gene_ontology_terms`. The KG uses two node labels (`Pfam` for domains,
`PfamClan` for clans) with a cross-label hierarchy edge — this requires small
builder extensions but presents as one unified `ontology="pfam"` to the LLM.

## Status / Prerequisites

- [ ] KG change: Pfam/PfamClan nodes, edges, indexes, Gene property cleanup —
  see [kg_changes_for_pfam.md](/home/osnat/github/multiomics_biocypher_kg/plans/kg_changes_for_pfam.md)

## Out of Scope

- `geneFullText` index update (handled in KG rebuild, transparent to explorer)

---

## Key Differences from Previous Ontology Additions

| Aspect | GO/EC/KEGG/COG/etc. | Pfam |
|--------|----------------------|------|
| Node labels | 1 per ontology | 2: `Pfam` (domain), `PfamClan` (clan) |
| Hierarchy edge | Same-type (`X_is_a_X`) | Cross-type: `Pfam_in_pfam_clan` (Pfam → PfamClan) |
| Fulltext indexes | 1 | 2: `pfamFullText`, `pfamClanFullText` |
| Gene connection | Genes → single label | Genes → `Pfam` only (not PfamClan) |
| ID format | Single prefix | `pfam:PF00712` (domain), `pfam.clan:CL0060` (clan) |

## Design Decision: Single `pfam` Entry

Two entries (`pfam` + `pfam_clan`) would force the LLM to pick the right
key and know that `gene_ontology_terms` doesn't work with `pfam_clan`.
Instead, use one `pfam` entry with two new optional config fields
(`parent_label`, `parent_fulltext_index`) and small builder extensions.

From the LLM's perspective: `ontology="pfam"` works everywhere — search
returns both domains and clans, `genes_by_ontology` accepts both domain
and clan IDs, `gene_ontology_terms` returns domains.

---

## Tool Signature

No new tools. One new `ontology` value: `"pfam"`.

```python
# In search_ontology, genes_by_ontology, gene_ontology_terms:
ontology: str
    # Add: "pfam" (Pfam protein domains and clans)
```

---

## KG-side Changes

- [ ] K1: `Pfam` nodes: `id` (`pfam:PF*`), `name`, `short_name`
- [ ] K2: `PfamClan` nodes: `id` (`pfam.clan:CL*`), `name`
- [ ] K3: `Gene_has_pfam` edges (Gene → Pfam, ~25k)
- [ ] K4: `Pfam_in_pfam_clan` edges (Pfam → PfamClan, ~1.5k)
- [ ] K5: `pfamFullText` index on Pfam `[name, short_name]`
- [ ] K6: `pfamClanFullText` index on PfamClan `[name]`
- [ ] K7: Drop `pfam_ids`, `pfam_names`, `pfam_descriptions` from Gene nodes
- [ ] K8: Update `geneFullText` to remove `pfam_names`

## Implementation Order

| Order | Change | Where | Status |
|-------|--------|-------|--------|
| 0 | KG rebuild | KG repo | pending |
| 1 | Add `pfam` to `ONTOLOGY_CONFIG` with new fields | queries_lib.py | this file |
| 2 | Extend `build_search_ontology` for parent index | queries_lib.py | this file |
| 3 | Extend `build_genes_by_ontology` for parent label | queries_lib.py | this file |
| 4 | Update ontology tool docstrings | tools.py | this file |
| 5a | Update tests | tests/ | this file |
| 5b | Update docs | CLAUDE.md etc. | this file |
| 6 | Code review | — | this file |

## Agent Assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 1-3 | **query-builder** | ONTOLOGY_CONFIG entry + builder extensions | KG deploy |
| 4 | **tool-wrapper** | Update docstrings in 3 ontology tools | steps 1-3 |
| 5a | **test-updater** | Unit, integration, eval, regression tests | step 4 |
| 5b | **doc-updater** | CLAUDE.md, README.md, AGENT.md | step 4 |
| 6 | **code-reviewer** | Review all changes, run unit tests | 5a, 5b |

---

## Query Builders

**File:** `queries_lib.py`

### ONTOLOGY_CONFIG entry

```python
"pfam": {
    "label": "Pfam",
    "gene_rel": "Gene_has_pfam",
    "hierarchy_rels": ["Pfam_in_pfam_clan"],
    "fulltext_index": "pfamFullText",
    "parent_label": "PfamClan",                  # NEW
    "parent_fulltext_index": "pfamClanFullText",  # NEW
},
```

New optional fields (unused by all other ontologies):
- `parent_label`: A second node label to accept in `genes_by_ontology`
  root matching. When present, the root MATCH uses
  `(root:Pfam OR root:PfamClan)` instead of just `(root:Pfam)`.
- `parent_fulltext_index`: A second fulltext index to UNION into
  `search_ontology` results.

### Builder change 1: `build_search_ontology`

When `parent_fulltext_index` is present, UNION both index searches:

```python
def build_search_ontology(
    *, ontology: str, search_text: str, limit: int = 25,
) -> tuple[str, dict]:
    cfg = ONTOLOGY_CONFIG[ontology]
    index_name = cfg["fulltext_index"]
    parent_index = cfg.get("parent_fulltext_index")

    if parent_index:
        # UNION search across both indexes (domain + clan)
        cypher = (
            "CALL {\n"
            f"  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "  YIELD node AS t, score\n"
            "  RETURN t.id AS id, t.name AS name, score\n"
            "  UNION ALL\n"
            f"  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)\n"
            "  YIELD node AS t, score\n"
            "  RETURN t.id AS id, t.name AS name, score\n"
            "}\n"
            "RETURN id, name, score\n"
            "ORDER BY score DESC\n"
            "LIMIT $limit"
        )
    else:
        # Existing single-index path (unchanged)
        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            "RETURN t.id AS id, t.name AS name, score\n"
            "ORDER BY score DESC\n"
            "LIMIT $limit"
        )
    return cypher, {"search_text": search_text, "limit": limit}
```

The `CALL {}` subquery with UNION ALL is Neo4j 5+ syntax. Results are
merged, sorted by score, and limited — so domains and clans compete
fairly in the ranking.

### Builder change 2: `build_genes_by_ontology`

When `parent_label` is present, the root MATCH accepts both labels:

```python
def build_genes_by_ontology(...):
    cfg = ONTOLOGY_CONFIG[ontology]
    label = cfg["label"]
    parent_label = cfg.get("parent_label")
    # ...

    if parent_label:
        root_match = (
            f"MATCH (root) WHERE (root:{label} OR root:{parent_label})\n"
            f"  AND root.id IN $term_ids"
        )
    else:
        root_match = f"MATCH (root:{label}) WHERE root.id IN $term_ids"

    # ... rest unchanged (expansion, gene_rel traversal)
```

This allows `genes_by_ontology(ontology="pfam", term_ids=["pfam.clan:CL0060"])`
to match PfamClan roots, expand via `Pfam_in_pfam_clan` to domains, then
find genes via `Gene_has_pfam`.

**How the expansion works for clan IDs:**
1. `root` = PfamClan node
2. `(root)<-[:Pfam_in_pfam_clan*0..15]-(descendant)`:
   - depth 0: descendant = PfamClan (harmless — no genes connect here)
   - depth 1: descendant = Pfam domains
3. `(g:Gene)-[:Gene_has_pfam]->(descendant)`: matches at depth 1 only ✓

### No change needed: `build_gene_ontology_terms`

Returns `Pfam` domains linked via `Gene_has_pfam`. This is correct —
genes are annotated to domains, not clans.

The `leaf_only` filter with `hierarchy_rels=["Pfam_in_pfam_clan"]` checks
whether another domain the gene is linked to has a `Pfam_in_pfam_clan`
edge to `t`. Since `Pfam_in_pfam_clan` goes Pfam→PfamClan (not Pfam→Pfam),
and `t` is matched as `:Pfam`, the NOT EXISTS pattern never matches —
all domains pass through. Effectively leaf_only has no impact, which is
correct (all gene-linked terms are already leaves).

---

## Tool Wrapper Logic

No wrapper changes. Only docstring updates to add `"pfam"` to the
ontology parameter docs in `search_ontology`, `genes_by_ontology`, and
`gene_ontology_terms`.

Suggested docstring addition:
```
"pfam" (Pfam protein domains and clans — search returns both,
    gene lookup accepts both domain and clan IDs,
    gene annotations return domains)
```

---

## Impact of Gene Property Removal

The KG rebuild drops `pfam_ids`, `pfam_names`, `pfam_descriptions` from
Gene nodes:

- `geneFullText`: `pfam_names` removed — `search_genes` no longer matches
  Pfam names. Users should use `search_ontology(ontology="pfam")` instead.
- `get_gene_details`: Properties disappear from `g {.*}` projection.
  No code change needed.
- No explorer code references these properties explicitly.

---

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**
- [ ] Update `test_all_*_keys_present` to expect 9 keys (8 + pfam)
- [ ] Add `"pfam"` to parametrized `search_ontology` test cases
- [ ] Add `"pfam"` to parametrized `genes_by_ontology` test cases
- [ ] Add `"pfam"` to parametrized `gene_ontology_terms` test cases
- [ ] Verify Pfam config has all 6 fields (including `parent_label`,
  `parent_fulltext_index`)
- [ ] Test `build_search_ontology(ontology="pfam")` generates UNION query
  with both fulltext indexes
- [ ] Test `build_genes_by_ontology(ontology="pfam")` generates multi-label
  root match `(root:Pfam OR root:PfamClan)`
- [ ] Test non-Pfam ontologies are unaffected (no UNION, single label)

**`tests/unit/test_tool_wrappers.py`:**
- [ ] No changes needed

**`tests/unit/test_tool_correctness.py`:**
- [ ] No changes needed (tool count unchanged)

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

After KG rebuild:
- [ ] `search_ontology(ontology="pfam", search_text="polymerase")` —
  returns domain hits (`pfam:PF*` IDs)
- [ ] `search_ontology(ontology="pfam", search_text="DNA_clamp")` —
  returns clan hits (`pfam.clan:CL*` IDs)
- [ ] `genes_by_ontology(ontology="pfam", term_ids=["pfam:PF00712"])` —
  direct domain → gene lookup
- [ ] `genes_by_ontology(ontology="pfam", term_ids=["pfam.clan:CL0060"])` —
  clan → domain expansion → genes
- [ ] `gene_ontology_terms(ontology="pfam", gene_id="PMM0001")` —
  returns `pfam:PF*` domain IDs
- [ ] Verify `pfam_ids`, `pfam_names` absent from `get_gene_details`

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: search_ontology_pfam
  tool: search_ontology
  desc: Search Pfam domains and clans by name
  params:
    ontology: pfam
    search_text: "polymerase"
  expect:
    min_rows: 1
    columns: [id, name, score]

- id: genes_by_ontology_pfam_domain
  tool: genes_by_ontology
  desc: Find genes by Pfam domain ID
  params:
    ontology: pfam
    term_ids: ["pfam:PF00712"]
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain]

- id: genes_by_ontology_pfam_clan
  tool: genes_by_ontology
  desc: Find genes by Pfam clan (hierarchy expansion)
  params:
    ontology: pfam
    term_ids: ["pfam.clan:CL0060"]
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain]

- id: gene_ontology_terms_pfam
  tool: gene_ontology_terms
  desc: Get Pfam domain annotations for a gene
  params:
    ontology: pfam
    gene_id: PMM0001
  expect:
    min_rows: 0
    columns: [id, name]
```

### Regression tests (`tests/regression/`)

New `TOOL_BUILDERS` entry:
```python
"search_ontology_pfam": partial(build_search_ontology, ontology="pfam"),
"gene_ontology_terms_pfam": partial(build_gene_ontology_terms, ontology="pfam"),
```

New cases:
```yaml
- id: search_ontology_pfam
  tool: search_ontology_pfam
  desc: Pfam domain and clan search
  params:
    search_text: "polymerase"

- id: gene_ontology_terms_pfam
  tool: gene_ontology_terms_pfam
  desc: Pfam annotations for a gene
  params:
    gene_id: PMM0001
```

After implementation + KG rebuild:
```bash
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add `"pfam"` to ontology tool descriptions |
| `README.md` | Add Pfam to ontology list if mentioned |
| `AGENT.md` | Add Pfam to ontology list if mentioned |

---

## Summary of Code Changes

1. **ONTOLOGY_CONFIG**: One `pfam` entry with 6 fields (4 standard +
   `parent_label` + `parent_fulltext_index`)
2. **`build_search_ontology`**: Add `parent_fulltext_index` branch —
   UNION both indexes when present (~10 lines)
3. **`build_genes_by_ontology`**: Add `parent_label` branch — multi-label
   root match when present (~5 lines)
4. **`build_gene_ontology_terms`**: No changes (works correctly as-is)
5. **Tool docstrings**: Add `"pfam"` to ontology parameter docs
6. **Tests + docs**: Config count, parametrized cases, builder-specific tests
