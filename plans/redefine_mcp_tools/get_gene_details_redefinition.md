# Plan: `get_gene_details` redefinition

## Context

The `get_gene_details` MCP tool currently dumps all ~50 Gene node properties
via `g {.*}`, wasting tokens on pipeline metadata, redundant identifiers,
and raw ontology ID lists. The tool needs to return a curated set of
properties that help Claude reason about Pro/Alt interactions — the primary
research focus (ROS detoxification, nutrient exchange, exoenzymatic activity).

Neither the KG nor the MCP server are deployed yet, so we can make breaking
changes to both without backward-compatibility concerns.

## Scope

### In scope
1. Curate `get_gene_details` return — explicit properties instead of `g {.*}`
2. Replace homolog list with one-line `homolog_summary` (reuse `build_get_homologs_groups`)
3. Add expression edge count (tells Claude whether to follow up with `query_expression`)
4. Suggest KG-level property cleanup (separate effort in `multiomics_biocypher_kg`)

### Out of scope
- Changes to `resolve_gene`, `search_genes`, or ontology tools
- CyanorakRole ontology addition (separate plan — Pro/Syn only, doesn't help Alteromonas)
- KG schema implementation (tracked separately in `multiomics_biocypher_kg`)

---

## Part 1: KG changes (multiomics_biocypher_kg — separate effort)

Properties to **drop from Gene nodes** during KG build. These stay in the
source data but are not loaded into Neo4j.

| Category | Properties to drop | Rationale |
|---|---|---|
| Pipeline metadata | `seed_ortholog`, `seed_ortholog_evalue`, `max_annot_lvl`, `product_source`, `function_description_source`, `gene_name_source` | Build-time only, not useful to end users |
| Redundant Cyanorak coords | `start_cyanorak`, `end_cyanorak`, `strand_cyanorak`, `locus_tag_cyanorak`, `product_cyanorak` | Identical to merged `start/end/strand/product` |
| Ontology ID lists | `go_terms`, `go_term_descriptions`, `kegg_ko`, `kegg_ko_descriptions`, `kegg_pathway`, `kegg_module`, `kegg_reaction`, `kegg_brite`, `ec_numbers`, `ontology_terms` | Represented as graph edges; dedicated MCP tools provide these with names |
| Pipeline-internal OG data | `eggnog_ogs`, `eggnog_og_descriptions`, `bacteria_cog_og` | Represented by OrthologGroup edges. `alteromonadaceae_og` already dropped in OrthologGroup migration. |
| Redundant with graph edges | `cog_category`, `cyanorak_Role`, `cyanorak_Role_description`, `tIGR_Role`, `tIGR_Role_description` | `cog_category` → `Gene_in_cog_category` → `CogFunctionalCategory` nodes; roles → `Gene_has_cyanorak_role`, `Gene_has_tigr_role` edges |
| Empty properties | `subcellular_location`, `uniprot_accession` | 0% coverage — never loaded |

**Reformat existing properties:**

| Property | Current | Proposed | Rationale |
|---|---|---|---|
| `pfam_ids` + `pfam_names` | Separate lists, often misaligned (different sources contribute to each) | Single `pfam_domains` list of `{id, name}` dicts, built by joining on Pfam accession during merge | Enables reliable pairing; currently PMT1707 has 3 IDs but 2 names. **Open question:** if merged into `pfam_domains`, Part 2 query needs updating to match. |
| `pfam_descriptions` | Duplicated entries from multiple sources, inconsistent casing | Deduplicate and align with `pfam_domains` as an optional `description` field | Currently 5 descriptions for 2 domains |

**Resulting Gene node (~24 properties):**
`locus_tag`, `gene_name`, `product`, `function_description`, `gene_summary`,
`gene_category`, `annotation_quality`, `organism_strain`,
`protein_id`,
`old_locus_tags`, `gene_synonyms`, `all_identifiers`,
`alternative_locus_tags`, `gene_name_synonyms`,
`pfam_ids`, `pfam_names`, `pfam_descriptions`,
`protein_family`,
`catalytic_activities`, `signal_peptide`, `transmembrane_regions`,
`alternate_functional_descriptions`,
`cazy_ids`, `transporter_classification`, `bigg_reaction`

---

## Part 2: MCP tool changes (this repo)

### Return structure

**Properties returned by `get_gene_details`:**

| Property | Source | Coverage | Notes |
|---|---|---|---|
| `locus_tag` | Gene node | 100% | Primary key |
| `gene_name` | Gene node | 54% | e.g. "pebB", "prxQ" |
| `product` | Gene node | 100% | Merged best product name |
| `function_description` | Gene node | 83% | Functional description (UniProt > EggNOG) |
| `gene_summary` | Gene node | 100% | One-line: `name :: product :: function` |
| `gene_category` | Gene node | ~100% | Functional category (e.g. "Signal transduction", "Replication and repair"). 22 genes (~0.4%) have null. |
| `annotation_quality` | Gene node | 100% | 0-3 score |
| `organism_strain` | Gene node | 100% | e.g. "Prochlorococcus MED4" |
| `protein_id` | Gene node | 95% | RefSeq accession |
| `alternative_locus_tags` | Gene node | 96% | Locus tag variants (e.g. ["PMT_1708", "RG24_RS09180"]) |
| `gene_name_synonyms` | Gene node | 4% | Gene name aliases (e.g. ["cobJ", "cbiG"]) |
| `pfam_names` | Gene node | 76% | Short domain names, e.g. ["Fe_bilin_red"] |
| `pfam_ids` | Gene node | 51% | Pfam accessions, e.g. ["PF05996"] |
| `protein_family` | Gene node | 17% | Single string. Key for enzyme subfamily identification. |
| `signal_peptide` | Gene node | 2% | Relevant for secreted/exoenzyme identification |
| `transmembrane_regions` | Gene node | 10% | Relevant for transport proteins |
| `homolog_summary` | Computed (reuse `build_get_homologs_groups`) | 98% | One-line summary of ortholog groups: count, consensus product, member range, genera |
| `expression_edge_count` | Computed (OPTIONAL MATCH + count) | 51% | Tells Claude whether to call `query_expression` |

**Properties excluded from return (stay on node for `run_cypher`):**

| Property | Why exclude |
|---|---|
| `alternate_functional_descriptions` | Avg 9 entries, multi-sentence. `gene_summary` covers essentials. |
| `pfam_descriptions` | Messy duplicates across sources. `pfam_names` sufficient. |
| `start`, `end`, `strand` | Genomic coordinates — stay on Gene node, not returned by this tool. Only needed for neighborhood/operon questions. Available via `run_cypher`. |
| `catalytic_activities` | Verbose Rhea reaction strings. Available via `run_cypher`. |
| `cazy_ids`, `transporter_classification`, `bigg_reaction` | Very sparse (1-8%), niche. |
| `old_locus_tags`, `gene_synonyms`, `all_identifiers` | Used for search indexing and `resolve_gene`. Not needed in gene details response. |

### Query changes

**File:** `multiomics_explorer/kg/queries_lib.py`

#### `build_get_gene_details_main` — curated RETURN

Replace `g {.*}` with explicit properties. Add expression edge count.
Drop `Gene_in_ortholog_group` OPTIONAL MATCH (replaced by `homolog_summary`).

```cypher
MATCH (g:Gene {locus_tag: $lt})
OPTIONAL MATCH (factor)-[expr:Condition_changes_expression_of|Coculture_changes_expression_of]->(g)
WITH g, count(expr) AS expression_edge_count
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.function_description AS function_description,
       g.gene_summary AS gene_summary,
       g.gene_category AS gene_category, g.annotation_quality AS annotation_quality,
       g.organism_strain AS organism_strain,
       g.protein_id AS protein_id,
       g.alternative_locus_tags AS alternative_locus_tags,
       g.gene_name_synonyms AS gene_name_synonyms,
       g.pfam_names AS pfam_names, g.pfam_ids AS pfam_ids,
       g.protein_family AS protein_family,
       g.signal_peptide AS signal_peptide,
       g.transmembrane_regions AS transmembrane_regions,
       expression_edge_count
```

#### Homolog summary — reuse `build_get_homologs_groups`

Instead of a separate homolog count query, call `build_get_homologs_groups(gene_id=...)`
(no filters) and condense the OG rows into a one-line summary in the wrapper.

Example output for PMM1428:
> "3 ortholog groups (consensus: EVE domain protein); 8–13 members across Prochlorococcus, Synechococcus, Alteromonas. Use get_homologs for details."

Delete `build_get_gene_details_homologs` from `queries_lib.py` — no longer needed.

### Tool wrapper changes

**File:** `multiomics_explorer/mcp_server/tools.py`

The main query no longer returns `g {.*}` as a nested map. The wrapper
assembles flat columns into the response dict:

```python
def get_gene_details(ctx: Context, gene_id: str) -> str:
    conn = _conn(ctx)

    cypher_main, params_main = build_get_gene_details_main(gene_id=gene_id)
    main = conn.execute_query(cypher_main, **params_main)
    if not main:
        return f"Gene '{gene_id}' not found."

    row = main[0]
    if row.get("locus_tag") is None:
        return f"Gene '{gene_id}' not found."

    # Homolog summary — reuse get_homologs group query
    cypher_hom, params_hom = build_get_homologs_groups(gene_id=gene_id)
    hom_rows = conn.execute_query(cypher_hom, **params_hom)

    # Assemble result
    result = dict(row)
    result["homolog_summary"] = _summarize_homologs(hom_rows)

    response = _fmt([result])
    return _with_query(response, cypher_main, params_main)  # debug handling unchanged


def _summarize_homologs(rows: list[dict]) -> str:
    """Condense ortholog group rows into a one-line summary."""
    if not rows:
        return "No ortholog groups."
    n = len(rows)
    members = [r.get("member_count") for r in rows if r.get("member_count") is not None]
    if not members:
        return f"{len(rows)} ortholog group(s) (member counts unavailable). Use get_homologs for details."
    # Collect unique genera across all groups
    all_genera = sorted({g for r in rows for g in (r.get("genera") or [])})
    # Use consensus_product from most specific group (lowest rank, first row due to ORDER BY)
    product = rows[0].get("consensus_product") or "unknown function"
    lo, hi = min(members), max(members)
    member_str = str(lo) if lo == hi else f"{lo}–{hi}"
    genera_str = ", ".join(all_genera) if all_genera else "unknown"
    return (
        f"{n} ortholog group(s) (consensus: {product}); "
        f"{member_str} members across {genera_str}. "
        f"Use get_homologs for details."
    )
```

### Docstring update

```python
"""Get full details for a gene: functional annotations, ortholog group
summary, and expression data availability.

Args:
    gene_id: Gene locus_tag (e.g. "PMM0001", "sync_0001").
            Use resolve_gene to find the locus_tag from any gene identifier.

Notes:
    - gene_category is available for all organisms (e.g. "Signal transduction",
      "Replication and repair").
    - For ontology annotations (GO, KEGG, EC), use gene_ontology_terms
      — works for all organisms including Alteromonas.
    - For coculture expression, use query_expression with the
      coculture partner name (e.g. condition="Alteromonas").
    - For full homolog list with cross-genus orthologs, use get_homologs.
"""
```

---

## Implementation order

| Step | What | Files | Depends on |
|---|---|---|---|
| 1 | Curate RETURN in `build_get_gene_details_main` | `queries_lib.py` | — |
| 2 | Delete `build_get_gene_details_homologs`; reuse `build_get_homologs_groups` in wrapper | `queries_lib.py` | — |
| 3 | Update tool wrapper + docstring | `tools.py` | 1, 2 |
| 4 | Update tests | `tests/` | 3 |
| 5 | Update CLAUDE.md tool table | `CLAUDE.md` | 3 |

Steps 1 and 2 are independent. Step 3 depends on both.
Steps 4 and 5 can run in parallel after step 3.

## Verification

1. **Unit tests** — `pytest tests/unit/ -v`
   - Query builder returns explicit columns (not `g {.*}`)
   - Dropped properties not in RETURN clause
   - `build_get_gene_details_homologs` removed; homolog summary built from `build_get_homologs_groups`
2. **KG integration** — `pytest -m kg -v`
   - Pro gene (PMM1428): has `gene_category`, `pfam_names`, `expression_edge_count` > 0
   - Alt gene (EZ55_00275): has `gene_category`, `organism_strain` contains "Alteromonas"
   - `homolog_summary` is a string sentence (not a raw list)
3. **Manual MCP test** — restart server, call `get_gene_details` for PMM1428
   - Verify curated return (~18 fields, not ~50)
   - Verify `homolog_summary` is a readable sentence
   - Verify `expression_edge_count` present
4. **Regression snapshots** — regenerate after changes:
   ```bash
   pytest tests/regression/ --force-regen -m kg
   pytest tests/regression/ -m kg
   ```

---

## Future considerations

- **`catalytic_activities` on Gene nodes:** Currently excluded (verbose Rhea reaction strings,
  ~8% coverage). Relevant for ROS detoxification and exoenzymatic activity research.
  Consider adding a condensed form in the KG (e.g. EC number + short name) and including
  it in the return.
- **`cazy_ids` on Gene nodes:** Currently excluded (~1% coverage). Relevant for
  exoenzymatic activity on polysaccharides — sparse but highly informative when present.
  Consider including conditionally (only when non-null) once coverage improves or if
  the KG adds CAZy family names alongside IDs.
- **Pfam format:** Open question whether KG should merge `pfam_ids` + `pfam_names` into
  a single `pfam_domains` list of `{id, name}` dicts. If so, Part 2 query and return
  structure need updating to match.
