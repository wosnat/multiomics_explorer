# Plan: Gene tools redesign

## Context

The current `get_gene_details` tool serves two roles poorly: it dumps all
Gene node properties (identity) AND nested sub-objects (homologs, protein,
organism), without helping Claude decide what to do next. After the KG
cleanup (Gene node: ~50 → ~27 properties) and the ontology edge framework
(9 types with dedicated MCP tools), we can redesign around how Claude
actually uses gene information.

**Typical Claude workflow:**
1. `search_genes` / `resolve_gene` → find gene(s), get locus_tags
2. Understand what the gene is + what data exists → decide next steps
3. Optionally deep-dive into specific aspects

Step 2 currently requires calling `get_gene_details` (expensive, noisy)
or guessing which follow-up tools to try. For a batch of genes from step 1,
there's no way to get routing signals without N individual calls.

## Design: two tools

| Tool | When | Input | Returns |
|---|---|---|---|
| `gene_overview` | After resolve/search, for one or more genes | list of locus_tags | Compact routing table: identity + data availability signals |
| `get_gene_details` | Rare deep dive, before resorting to `run_cypher` | one locus_tag | Full gene node properties + protein + organism |

`gene_overview` handles both single-gene and batch cases with the same
return structure. No need for a separate single-gene variant.

---

## Part 0: KG changes (multiomics_biocypher_kg — separate effort)

Pre-compute routing signals as Gene node properties during KG build. Since
the KG is rebuilt from scratch (never incrementally updated), these
are recomputed every build and cannot go stale.

| Property | Type | Value | Eliminates |
|---|---|---|---|
| `annotation_types` | list | `["go_bp", "go_mf", "pfam", "cog_category"]` — ontology types with >0 edges | 9 OPTIONAL MATCHes per gene |
| `expression_edge_count` | int | total count of expression edges | 1 OPTIONAL MATCH per gene |
| `significant_expression_count` | int | count of expression edges where `significant = 'significant'` | (same OPTIONAL MATCH, filtered) |
| `closest_ortholog_group_size` | int | member_count from the most specific OG (lowest specificity_rank) | 1 OPTIONAL MATCH + ORDER/LIMIT per gene |
| `closest_ortholog_genera` | list | genera list from the most specific OG | (same OPTIONAL MATCH) |

With these three properties, the `gene_overview` query becomes a single
UNWIND + MATCH with no OPTIONAL MATCHes:

```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.gene_summary AS gene_summary,
       g.gene_category AS gene_category, g.annotation_quality AS annotation_quality,
       g.organism_strain AS organism_strain,
       g.annotation_types AS annotation_types,
       g.expression_edge_count AS expression_edge_count,
       g.significant_expression_count AS significant_expression_count,
       g.closest_ortholog_group_size AS closest_ortholog_group_size,
       g.closest_ortholog_genera AS closest_ortholog_genera
ORDER BY g.locus_tag
```

Fast even for 50 genes. No graph traversal beyond the initial index lookup.

**Expression count context:** ~77% of expression edges are "not significant".
A gene with 15 expression edges but 0 significant ones is very different
from one with 5 significant hits. Both counts help Claude decide whether
and how to follow up with `query_expression`.

---

## Tool 1: `gene_overview`

**Purpose:** Routing table for one or more genes. Returns core identity
plus signals for what follow-up data exists. The tool Claude calls right
after `resolve_gene` or `search_genes`.

### Return structure

One row per gene:

| Field | Source | Notes |
|---|---|---|
| `locus_tag` | Gene node | Primary key |
| `gene_name` | Gene node | e.g. "prxQ" (54% coverage) |
| `product` | Gene node | Merged best product name |
| `gene_summary` | Gene node | One-line: `name :: product :: function` |
| `gene_category` | Gene node | e.g. "Signal transduction", "Photosynthesis" |
| `annotation_quality` | Gene node | 0-3 score |
| `organism_strain` | Gene node | e.g. "Prochlorococcus MED4" |
| `annotation_types` | Gene node (pre-computed) | `["go_bp", "kegg", "pfam"]` — ontology types with data. → which `gene_ontology_terms` calls are productive? |
| `expression_edge_count` | Gene node (pre-computed) | Total expression edges. |
| `significant_expression_count` | Gene node (pre-computed) | Expression edges passing significance threshold. → `> 0` means `query_expression` has meaningful hits. |
| `closest_ortholog_group_size` | Gene node (pre-computed) | Member count of the most specific (tightest) OG. → `> 0` means `get_homologs` has data. |
| `closest_ortholog_genera` | Gene node (pre-computed) | Genera in the tightest OG, e.g. `["Prochlorococcus", "Synechococcus"]`. → which organisms have orthologs? |

### Query: `build_gene_overview`

```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.gene_summary AS gene_summary,
       g.gene_category AS gene_category, g.annotation_quality AS annotation_quality,
       g.organism_strain AS organism_strain,
       g.annotation_types AS annotation_types,
       g.expression_edge_count AS expression_edge_count,
       g.significant_expression_count AS significant_expression_count,
       g.closest_ortholog_group_size AS closest_ortholog_group_size,
       g.closest_ortholog_genera AS closest_ortholog_genera
ORDER BY g.locus_tag
LIMIT $limit
```

### Wrapper logic

```python
def gene_overview(
    ctx: Context, gene_ids: list[str], limit: int = 50,
) -> str:
    conn = _conn(ctx)
    cypher, params = build_gene_overview(locus_tags=gene_ids, limit=limit)
    rows = conn.execute_query(cypher, **params)
    if not rows:
        return "No genes found for the given locus_tags."

    response = _fmt(rows)
    return _with_query(response, cypher, params, ctx)
```

### Docstring

```python
"""Get an overview of one or more genes: identity and data availability.

Use this after resolve_gene, search_genes, genes_by_ontology, or
get_homologs to understand what each gene is and what follow-up data
exists.

Returns one row per gene with routing signals:
- annotation_types: which ontology types have annotations
  → use gene_ontology_terms with the relevant type
- expression_edge_count + significant_expression_count: whether
  expression data exists and how much is significant
  → use query_expression
- closest_ortholog_group_size + closest_ortholog_genera: whether
  orthologs exist and in which genera
  → use get_homologs for full membership

Args:
    gene_ids: List of gene locus_tags.
              Use resolve_gene to find locus_tags from other identifiers.
    limit: Max genes to return (default 50).
"""
```

---

## Tool 2: `get_gene_details`

**Purpose:** Full gene dump for rare deep dives. Since the KG cleanup
already trimmed Gene from ~50 to ~27 properties, `g {.*}` is now
reasonable here. This is the step before `run_cypher`.

### Return structure

All Gene node properties (via `g {.*}`).

**Not included:**
- Protein details — use `run_cypher` for protein-level fields
  (sequence_length, annotation_score, is_reviewed, refseq_ids)
- Organism details — `organism_strain` is on the Gene node; full taxonomy
  available via `list_organisms` or `run_cypher`
- Homolog list — use `get_homologs` (dedicated tool, better filtering)
- Ortholog group list — use `get_homologs` (includes OG metadata)

### Query: `build_get_gene_details`

Simplified from current — drop `_organism`, `_ortholog_groups`, `_homologs`:

```cypher
MATCH (g:Gene {locus_tag: $lt})
RETURN g {.*} AS gene
```

### Wrapper logic

Essentially the current `get_gene_details` minus the homolog query:

```python
def get_gene_details(ctx: Context, gene_id: str) -> str:
    conn = _conn(ctx)
    cypher, params = build_get_gene_details(gene_id=gene_id)
    results = conn.execute_query(cypher, **params)
    if not results or results[0]["gene"] is None:
        return f"Gene '{gene_id}' not found."
    return _with_query(_fmt([results[0]["gene"]]), cypher, params, ctx)
```

### Docstring

```python
"""Get all properties for a gene.

This is a deep-dive tool — use gene_overview for the common case.
Returns all Gene node properties including sparse fields
(catalytic_activities, transporter_classification, cazy_ids, etc.).

For organism taxonomy, use list_organisms. For homologs, use
get_homologs. For ontology annotations, use gene_ontology_terms.
For expression data, use query_expression.

Args:
    gene_id: Gene locus_tag (e.g. "PMM0001", "sync_0001").
"""
```

---

## Current Gene node properties reference

All ~24 properties with coverage (35,226 total genes).
Pending removal: `gene_synonyms`, `alternative_locus_tags`, `old_locus_tags`.

| Property | Count | Coverage |
|---|---|---|
| `locus_tag` | 35,226 | 100% |
| `product` | 35,226 | 100% |
| `alternate_functional_descriptions` | 35,226 | 100% |
| `organism_strain` | 35,226 | 100% |
| `gene_summary` | 35,226 | 100% |
| `all_identifiers` | 35,226 | 100% |
| `annotation_quality` | 35,226 | 100% |
| `gene_category` | 35,226 | 100% |
| `id` | 35,226 | 100% |
| `preferred_id` | 35,226 | 100% |
| `start` | 33,376 | 95% |
| `end` | 33,376 | 95% |
| `protein_id` | 33,376 | 95% |
| `function_description` | 29,236 | 83% |
| `gene_name` | 18,868 | 54% |
| `strand` | 16,899 | 48% |
| `protein_family` | 6,113 | 17% |
| `transmembrane_regions` | 3,419 | 10% |
| `catalytic_activities` | 2,740 | 8% |
| `transporter_classification` | 2,688 | 8% |
| `bigg_reaction` | 2,009 | 6% |
| `gene_name_synonyms` | 1,511 | 4% |
| `signal_peptide` | 720 | 2% |
| `cazy_ids` | 371 | 1% |

After Part 0 KG changes, five new properties will be added:
`annotation_types` (list, 100%), `expression_edge_count` (int, 100%),
`significant_expression_count` (int, 100%),
`closest_ortholog_group_size` (int, ~98%), `closest_ortholog_genera` (list, ~98%).

---

## Implementation order

| Step | Repo | What | Status |
|---|---|---|---|
| 0a | multiomics_biocypher_kg | Add `annotation_types` to KG build | DONE |
| 0b | multiomics_biocypher_kg | Add `expression_edge_count` + `significant_expression_count` to KG build | DONE |
| 0c | multiomics_biocypher_kg | Add `closest_ortholog_group_size` + `closest_ortholog_genera` to KG build | DONE |
| 0d | multiomics_biocypher_kg | Remove `gene_synonyms`, `alternative_locus_tags`, `old_locus_tags` from Gene nodes | DONE |
| 0e | multiomics_biocypher_kg | Rebuild KG | DONE |
| 1 | multiomics_explorer | Add `build_gene_overview` query builder | TODO |
| 2 | multiomics_explorer | Simplify `build_get_gene_details_main` (drop OG/homolog joins) | TODO |
| 3 | multiomics_explorer | Delete `build_get_gene_details_homologs` | TODO |
| 4 | multiomics_explorer | Add `gene_overview` tool wrapper + docstring | TODO |
| 5 | multiomics_explorer | Update `get_gene_details` tool (simplified) | TODO |
| 6 | multiomics_explorer | Update tests | TODO |
| 7 | multiomics_explorer | Update CLAUDE.md tool table | TODO |

Steps 1-3 are independent. Steps 4-5 depend on their respective query
builders. Steps 6-7 can run in parallel after 4-5.

## Verification

1. **KG verification** — DONE
   - PMM1428: `annotation_types` = [go_mf, pfam, cog_category, tigr_role],
     `expression_edge_count` = 36, `significant_expression_count` = 5,
     `closest_ortholog_group_size` = 9, `closest_ortholog_genera` = [Prochlorococcus, Synechococcus]
   - EZ55_00275: `annotation_types` = [], `expression_edge_count` = 0,
     `closest_ortholog_group_size` = 1, `closest_ortholog_genera` = [Alteromonas]
   - `old_locus_tags`, `gene_synonyms`, `alternative_locus_tags` confirmed removed (count = 0)

2. **Unit tests** — `pytest tests/unit/ -v`
   - `build_gene_overview` uses UNWIND, returns pre-computed columns
   - `build_get_gene_details` uses `g {.*}`, no OG/homolog joins
   - `build_get_gene_details_homologs` deleted

3. **KG integration** — `pytest -m kg -v`
   - `gene_overview` for [PMM1428]: annotation_types includes expected types, expression_edge_count > 0, significant_expression_count > 0, closest_ortholog_group_size > 0, closest_ortholog_genera is non-empty
   - `gene_overview` for [PMM1428, EZ55_00275]: returns 2 rows
   - `get_gene_details` for PMM1428: returns all Gene node properties, no _organism/_homologs

4. **Manual MCP test** — restart server
   - `gene_overview` for [PMM1428]: compact table row
   - `gene_overview` for a search_genes result set: table format
   - `get_gene_details` for PMM1428: full dump

5. **Regression snapshots** — regenerate:
   ```bash
   pytest tests/regression/ --force-regen -m kg
   pytest tests/regression/ -m kg
   ```

---

## Deployment model

Target: 3-4 researchers using Claude Code in VSCode.

- **Neo4j**: shared instance (local server or Neo4j Aura cloud)
- **MCP server**: runs locally on each researcher's machine via `uv run`,
  connecting to shared Neo4j via `NEO4J_URI` in `.env`

This is the simplest setup: the only shared component is Neo4j. Each
researcher installs the package and configures their connection string.

---

## Future considerations

- **Sparse properties on Gene nodes:** `catalytic_activities` (8%),
  `transporter_classification` (8%), `bigg_reaction` (6%),
  `gene_name_synonyms` (4%), `cazy_ids` (1%) are only visible in
  `get_gene_details`. If frequently needed, consider surfacing in
  `gene_overview` or creating dedicated ontology edges.
- **Protein details:** Open question whether `get_gene_details` should
  include `_protein` sub-object. If protein-level fields (sequence_length,
  annotation_score, is_reviewed) are frequently needed, include it.
  Otherwise drop and let `run_cypher` cover protein queries.
- **`gene_overview` column selection:** Currently fixed columns. If
  use patterns show Claude frequently needs specific fields not in
  the overview (e.g. `function_description`), consider adding them
  to the fixed set rather than making columns configurable.
- **File I/O for large batches:** Consider adding `output_file` and
  `input_file` parameters for pipeline workflows (search → filter → overview)
  where data shouldn't round-trip through the LLM context. Separate plan.
