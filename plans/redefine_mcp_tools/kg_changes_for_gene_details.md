# KG Changes for `get_gene_details` Redefinition

Spec for `multiomics_biocypher_kg` changes needed to support the leaner
Gene node described in `get_gene_details_redefinition.md`.

---

## 1. Drop pipeline metadata (6 properties)

| Property | Why |
|---|---|
| `seed_ortholog` | EggNOG internal |
| `seed_ortholog_evalue` | EggNOG internal |
| `max_annot_lvl` | EggNOG internal |
| `product_source` | Build provenance |
| `function_description_source` | Build provenance |
| `gene_name_source` | Build provenance |

These are build-time artifacts not useful to consumers.

## 2. Drop redundant Cyanorak coordinates (5 properties)

| Property | Redundant with |
|---|---|
| `start_cyanorak` | `start` |
| `end_cyanorak` | `end` |
| `strand_cyanorak` | `strand` |
| `locus_tag_cyanorak` | `all_identifiers` |
| `product_cyanorak` | `product` |

The merge pipeline already resolves these into the canonical fields.

## 3. Drop ontology ID lists (10 properties)

| Property |
|---|
| `go_terms` |
| `go_term_descriptions` |
| `kegg_ko` |
| `kegg_ko_descriptions` |
| `kegg_pathway` |
| `kegg_module` |
| `kegg_reaction` |
| `kegg_brite` |
| `ec_numbers` |
| `ontology_terms` |

All represented as graph edges. Dedicated MCP tools (`gene_ontology_terms`,
`search_ontology`, `genes_by_ontology`) use edges, not these lists.

## 4. Drop pipeline-internal OG data (3 properties)

| Property |
|---|
| `eggnog_ogs` |
| `eggnog_og_descriptions` |
| `bacteria_cog_og` |

Represented by `OrthologGroup` nodes and `Gene_in_ortholog_group` edges.

Note: `alteromonadaceae_og` was already dropped in the OrthologGroup migration.

## 5. Drop properties redundant with graph edges (5 properties)

| Property | Redundant with |
|---|---|
| `cog_category` | `Gene_in_cog_category` → `CogFunctionalCategory` nodes |
| `cyanorak_Role` | `Gene_has_cyanorak_role` edges |
| `cyanorak_Role_description` | `Gene_has_cyanorak_role` edges |
| `tIGR_Role` | `Gene_has_tigr_role` edges |
| `tIGR_Role_description` | `Gene_has_tigr_role` edges |

## 6. Drop empty properties (2 properties)

| Property | Issue |
|---|---|
| `subcellular_location` | 0% coverage — pipeline doesn't load it |
| `uniprot_accession` | 0% coverage — not propagated to Gene nodes |

Either fix the pipeline to populate them or remove from config.

## 7. Reformat Pfam properties

**Current:** `pfam_ids`, `pfam_names`, `pfam_descriptions` as separate lists,
often misaligned across sources (e.g. PMT1707 has 3 IDs but 2 names).

**Proposed:** Single `pfam_domains` list of `{id, name}` dicts, built by
joining on Pfam accession during the merge step. Drop `pfam_descriptions`
(messy duplicates, `pfam_names` is sufficient).

If this merge is too complex, keep `pfam_ids` and `pfam_names` as-is and
drop only `pfam_descriptions`.

---

## Summary

| Action | Count |
|---|---|
| Properties dropped | 31 |
| Properties reformatted | 2–3 (Pfam) |
| Resulting Gene node | ~24 properties |

## Verification

After rebuild:
```cypher
-- Property count per gene should be ~21 (not ~50)
MATCH (g:Gene {locus_tag: 'PMM1428'})
RETURN size(keys(g)) AS prop_count

-- Dropped properties should not exist
MATCH (g:Gene)
WHERE g.seed_ortholog IS NOT NULL
   OR g.go_terms IS NOT NULL
   OR g.eggnog_ogs IS NOT NULL
   OR g.cog_category IS NOT NULL
RETURN count(g)
-- Expected: 0

-- Kept properties still present
MATCH (g:Gene {locus_tag: 'PMM1428'})
RETURN g.locus_tag, g.gene_name, g.product, g.function_description,
       g.gene_summary, g.gene_category, g.annotation_quality,
       g.organism_strain, g.protein_id,
       g.alternative_locus_tags, g.gene_name_synonyms,
       g.pfam_ids, g.pfam_names, g.protein_family,
       g.signal_peptide, g.transmembrane_regions
```

---

## Review notes (2026-03-16)

- `ontology_terms`, `bacteria_cog_og`, `subcellular_location`, `uniprot_accession` don't
  exist on any Gene node in the current KG — sections 3, 4, 6 overcount by 4.
  Actual drop count is ~27, not 31. Keep the entries as guardrails for future builds.
- `locus_tag_ncbi` exists on all genes but is not addressed. Should be added to a drop
  category (redundant with `locus_tag` / `alternative_locus_tags`).
- `id`, `preferred_id`, `gene_synonyms`, `old_locus_tags`, `all_identifiers` are listed
  in the parent plan's "Redundant identifiers" drop list but omitted here. Not blocking
  — will address in a later pass if needed.
