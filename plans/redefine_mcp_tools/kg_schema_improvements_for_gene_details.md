# KG Schema Improvements for `get_gene_details`

Proposed changes to the `multiomics_biocypher_kg` build pipeline that would
simplify the Gene node and eliminate workarounds in the explorer's query layer.

None of these are blockers for the current `get_gene_details` redefinition
(which works around them with curated RETURN clauses and DISTINCT). These
are upstream improvements to pursue separately.

Based on KG property distribution analysis (2026-03-16, 35,226 genes across
13 strains).

---

## 1. Fix bidirectional homolog edges

**Problem:** Every `Gene_is_homolog_of_gene` relationship stores both A→B
and B→A, doubling edge count and forcing every consumer to deduplicate
with `DISTINCT`.

**Fix:** Store one edge per pair at build time (e.g. alphabetically lower
`locus_tag` → higher). Cypher undirected match
`(g)-[:Gene_is_homolog_of_gene]-(other)` still works — it just won't
return duplicate rows.

**Impact:** Eliminates `DISTINCT` workaround in `get_gene_details`,
`get_homologs`, and any future homolog queries. Halves homolog edge storage.

## 2. Unify `cluster_id` at build time

**Problem:** Two mutually exclusive properties for the same concept:
- `cluster_number` (20,657 genes) — Pro/Syn with Cyanorak data
- `alteromonadaceae_og` (10,403 genes) — Alteromonas eggNOG OG

Every query uses `coalesce(g.cluster_number, g.alteromonadaceae_og)`.

**Fix:** Compute a single `cluster_id` property during the build.
Optionally add `cluster_source: "cyanorak" | "eggnog"` for provenance.
Combined coverage: 31,060 genes (88%).

**Impact:** Drop `coalesce()` from all queries. Drop the
`Gene_in_cyanorak_cluster` relationship + `Cyanorak_cluster` node
(cluster ID is sufficient as a gene property).

## 3. Drop pipeline metadata from Gene nodes

**Properties to remove (8):**

| Property | Count | Why remove |
|---|---|---|
| `seed_ortholog` | 32,295 | EggNOG internal — never queried |
| `seed_ortholog_evalue` | 32,295 | EggNOG internal — never queried |
| `max_annot_lvl` | 32,295 | EggNOG internal — never queried |
| `product_source` | 35,226 | Build provenance — not useful to consumers |
| `function_description_source` | 29,236 | Build provenance — not useful to consumers |
| `gene_name_source` | 18,868 | Build provenance — not useful to consumers |
| `preferred_id` | 35,226 | Build internal identifier |
| `id` | 35,226 | Build internal identifier |

**If provenance tracking is needed later:** Store in a separate
`AnnotationProvenance` node or keep in the build repo's output JSON
(not in the KG).

## 4. Drop redundant identifier fields

**Problem:** 5 overlapping fields that all feed into `all_identifiers`:

| Property | Count | Overlap with `all_identifiers` |
|---|---|---|
| `old_locus_tags` | 32,644 | Subset |
| `alternative_locus_tags` | 33,904 | Subset |
| `gene_synonyms` | 33,904 | Superset (includes old_locus_tags) |
| `gene_name_synonyms` | 1,511 | Subset of gene_synonyms |
| `locus_tag_ncbi` | 33,376 | Already in all_identifiers |
| `locus_tag_cyanorak` | 20,658 | Already in all_identifiers |

**Fix:** Keep `all_identifiers` as the single comprehensive list.
For full-text search indexing, index `all_identifiers` + `gene_name`.
Drop the other 6 fields.

**Note:** `gene_name_synonyms` (1,511 genes) contains gene-name-like
tokens filtered from `gene_synonyms`. If this distinction matters for
search, it can be a computed index rather than a stored property.

## 5. Drop Cyanorak duplicate coordinates

**Properties to remove (5):**

| Property | Count | Redundant with |
|---|---|---|
| `start_cyanorak` | 20,658 | `start` |
| `end_cyanorak` | 20,658 | `end` |
| `strand_cyanorak` | 10,316 | `strand` |
| `product_cyanorak` | 20,658 | `product` |
| `locus_tag_cyanorak` | 20,658 | Already in `all_identifiers` |

The merge pipeline already resolves Cyanorak vs NCBI values into the
canonical fields. Keeping both sets is confusing and the Cyanorak
originals are never queried independently.

## 6. Remove ontology ID lists from Gene nodes

**Problem:** Ontology IDs stored as gene properties duplicate the
ontology node edges that already exist in the KG. The dedicated
ontology tools (`gene_ontology_terms`, `search_ontology`,
`genes_by_ontology`) use edges, not these lists.

**Properties to remove:**

| Property | Count | Avg size (Pro/Alt) | Max |
|---|---|---|---|
| `go_terms` | 23,013 | 12.7 / 22.4 | 188 |
| `kegg_ko` | 18,307 | 0.8 / 0.8 | — |
| `kegg_pathway` | 11,619 | — | — |
| `kegg_brite` | 18,307 | — | — |
| `kegg_reaction` | 7,788 | — | — |
| `kegg_module` | 7,469 | — | — |
| `ec_numbers` | 13,082 | 0.8 / 0.6 | — |
| `ontology_terms` | 0 | — | — |

Also drop related description fields (available through ontology nodes):

| Property | Count |
|---|---|
| `go_term_descriptions` | 12,258 |
| `kegg_ko_descriptions` | 5,612 |
| `eggnog_og_descriptions` | 14,939 |
| `pfam_descriptions` | 14,910 |

**Impact:** Biggest storage win — `go_terms` alone is ~370K list entries.
Removes ~12 properties from Gene nodes.

**Note:** `pfam_ids` (18,055) and `pfam_names` (26,607) should be kept —
these are compact domain annotations used directly in gene details, and
there are no Pfam ontology nodes in the KG.

## 7. Drop `alternate_functional_descriptions`

**Problem:** Built during merge by concatenating descriptions from all
sources with `[source]` prefixes. 100% coverage, avg 9.3 entries (Pro)
/ 3.7 (Alt), max 22. Individual entries can be multi-sentence paragraphs
(UniProt/EggNOG function descriptions).

**Why redundant:** `gene_summary` already combines the winning
`gene_name` + `product` + `function_description`. The remaining entries
in `alternate_functional_descriptions` are:
- Lower-priority source duplicates (e.g. `[ncbi]` when `[cyanorak]` won)
- COG/eggNOG OG category descriptions
- TIGR/Cyanorak role descriptions
- KEGG descriptions
- Pfam descriptions (available via `pfam_names`)

All of these are either available through dedicated tools or are
pipeline internals.

## 8. Fix empty properties

Two properties defined in `gene_annotations_config.yaml` produce no
data in the KG:

| Property | Issue |
|---|---|
| `subcellular_location` | 0 genes — pipeline doesn't load UniProt subcellular location |
| `uniprot_accession` | 0 genes — not propagated to Gene nodes |

**Fix:** Either fix the pipeline to load them (both are useful) or
remove from config to avoid confusion. `uniprot_accession` in
particular would be valuable for cross-referencing.

## 9. Keep `gene_summary` (search index artifact)

`gene_summary` is computed as `"{gene_name} :: {product} ::
{function_description}"`. It's computable from other fields, but it's
indexed for `search_genes` full-text search and is compact. Worth keeping
as a search optimization.

---

## Summary: Gene node before and after

| | Before | After |
|---|---|---|
| Total properties | ~40 | ~17 |
| Pipeline metadata | 8 | 0 |
| Redundant identifiers | 6 | 0 |
| Cyanorak duplicates | 5 | 0 |
| Ontology ID lists + descriptions | 12 | 0 (use edges) |
| Cluster fields | 2 | 1 (`cluster_id`) |
| `alternate_functional_descriptions` | 1 | 0 |
| Homolog edges per pair | 2 | 1 |

**Remaining ~17 core properties:**

| Category | Properties |
|---|---|
| Identity | `locus_tag`, `gene_name`, `all_identifiers` |
| Function | `product`, `function_description`, `gene_summary`, `gene_category`, `annotation_quality` |
| Genomic | `organism_strain`, `start`, `end`, `strand` |
| Cross-references | `protein_id`, `cluster_id` |
| Domains | `pfam_names`, `pfam_ids` |
| UniProt (sparse) | `protein_family`, `catalytic_activities`, `transmembrane_regions`, `signal_peptide` |
| Other (sparse) | `cazy_ids`, `transporter_classification`, `bigg_reaction`, `cog_category`, `cyanorak_Role`, `cyanorak_Role_description`, `tIGR_Role`, `tIGR_Role_description` |

With a lean Gene node, `get_gene_details` could use `g {.*}` again and
return only useful properties — no curation needed in the query layer.
