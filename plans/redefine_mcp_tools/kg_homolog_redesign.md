# Plan: Homolog Edge Redesign — Cluster Nodes Instead of Pairwise Edges

Replace materialized pairwise `Gene_is_homolog_of_gene` edges and propagated
`*_expression_of_ortholog` edges with `OrthologGroup` cluster nodes. Homology
becomes implicit through shared group membership. Expression propagation moves
from build-time materialization to query-time joins.

Motivated by: adding Ruegeria (2-3 strains) and future heterotrophs would
explode pairwise edge counts. Current design already stores 13x more derived
edges than real experimental data.

---

## Current State (2026-03-16)

### Edge budget

| Layer | Edges | Notes |
|---|---|---|
| Condition_changes_expression_of | 170,904 | Experimental data |
| Coculture_changes_expression_of | 17,597 | Experimental data |
| **Subtotal: real data** | **188,501** | |
| Gene_is_homolog_of_gene | 365,840 | Derived, bidirectional |
| Condition_changes_expression_of_ortholog | 2,005,209 | Propagated |
| Coculture_changes_expression_of_ortholog | 82,782 | Propagated |
| **Subtotal: derived** | **2,453,831** | **13x the real data** |

### Homolog edge sources

| Source | Directed edges | Connects | Cluster size (median / p95 / max) |
|---|---|---|---|
| `cyanorak_cluster` | 120,272 | Pro↔Pro, Pro↔Syn, Syn↔Syn | 2 / 9 / 41 |
| `eggnog_alteromonadaceae_og` | 23,048 | Alt↔Alt | 3 / 3 / 24 |
| `eggnog_bacteria_cog_og` | 222,520 | Alt↔Pro/Syn only | 9 / 30 / 217 |

All edges stored bidirectionally (A→B and B→A). Actual unique pairs = half.

### EggNOG OG taxonomic levels per gene

EggNOG-mapper assigns OGs at multiple taxonomic levels simultaneously.
Example:

```
MIT1002_03493 (Alteromonas):
  root → Bacteria → Proteobacteria → Gammaproteobacteria → Alteromonadaceae

PMM1428 (Prochlorococcus):
  root → Bacteria → Cyanobacteria → Prochloraceae
```

The lowest (most specific) level is the most informative for within-clade
orthology. Higher levels provide cross-phylum functional grouping.

### Coverage of eggnog levels (current KG)

**Alteromonas genes:**

| Level | Count |
|---|---|
| Bacteria | 12,435 |
| Proteobacteria | 11,601 |
| Gammaproteobacteria | 11,411 |
| Alteromonadaceae | 10,403 |

**Prochlorococcus genes:**

| Level | Count |
|---|---|
| Bacteria | 15,760 |
| Cyanobacteria | 15,166 |
| Prochloraceae | 14,844 |

---

## Problems with Current Design

### 1. Pairwise edges scale quadratically

A cluster of N genes produces N×(N-1) directed edges. The largest bacteria
COG cluster (COG0457, 217 members) alone generates 46,872 directed pairwise
edges. Adding 3 Ruegeria strains (~10K genes) would roughly double the
total KG edge count.

### 2. Expression propagation multiplies the problem

170K direct expression edges get propagated through 365K homolog edges to
create 2M ortholog expression edges. This is the single largest edge set
in the KG, yet it contains no new information — it's a precomputed join.

### 3. `bacteria_cog_og` edges are hardcoded to Alteromonas

Lines 81-90 of `post-import.cypher` filter for `o1.genus = "Alteromonas"`
on one side of the cross-phylum edges. Adding Ruegeria requires a new
code block. Each future organism family needs another block.

### 4. No within-family edges for new heterotrophs

The `alteromonadaceae_og` block (lines 63-75) is Alteromonas-specific.
Ruegeria would need an equivalent `rhodobacteraceae_og` property and
parallel code.

### 5. `homology_source` hardcoded in expression propagation

Lines 115 and 143 of `post-import.cypher` set
`homology_source: 'cyanorak_cluster'` for ALL ortholog expression edges,
even when the homolog edge came from `eggnog_bacteria_cog_og` or
`eggnog_alteromonadaceae_og`. This is a bug.

### 6. Coculture distance filter is too coarse

Line 126 filters `h.distance <> 'cross phylum'`. This made sense when
the only cross-phylum pair was Alteromonas↔Cyanobacteria. With Ruegeria,
Alt↔Ruegeria is cross-class (both Proteobacteria, different classes) —
the distance labels don't capture this.

---

## Proposed Design: OrthologGroup Cluster Nodes

### Core idea

Replace pairwise `Gene_is_homolog_of_gene` edges with membership edges to
shared `OrthologGroup` nodes. Two genes are homologs if they share an
OrthologGroup. Expression propagation is computed at query time, not
materialized.

### New node type: `OrthologGroup`

| Property | Type | Description |
|---|---|---|
| `id` | string | The OG identifier (e.g. `CK_00001099`, `465MN@72275`, `COG2947`) |
| `source` | string | `"cyanorak"` or `"eggnog"` |
| `taxonomic_level` | string | `"curated"` for Cyanorak; eggnog level name (`"Alteromonadaceae"`, `"Prochloraceae"`, `"Bacteria"`, etc.) |
| `taxon_id` | int | NCBI taxon ID of the taxonomic level (for sortable hierarchy) |

### New edge type: `Gene_in_ortholog_group`

```
(Gene)-[:Gene_in_ortholog_group]->(OrthologGroup)
```

One edge per gene per group. A gene may belong to multiple groups at
different taxonomic levels (its lowest-level eggnog OG + bacteria-level COG,
or Cyanorak cluster + bacteria-level COG).

### What gets removed

| Remove | Current count | Replaced by |
|---|---|---|
| `Gene_is_homolog_of_gene` edges | 365,840 | Implicit via shared OrthologGroup |
| `Condition_changes_expression_of_ortholog` edges | 2,005,209 | Query-time join |
| `Coculture_changes_expression_of_ortholog` edges | 82,782 | Query-time join |
| `alteromonadaceae_og` gene property | 10,403 | OrthologGroup node membership |
| `bacteria_cog_og` gene property | 26,298 | OrthologGroup node membership |
| Homolog + expression propagation in `post-import.cypher` | lines 36-146 | Replaced by OrthologGroup creation |
| **Total edges removed** | **2,453,831** | |

### What gets kept

| Keep | Why |
|---|---|
| `Cyanorak_cluster` nodes + `Gene_in_cyanorak_cluster` edges | Already cluster-node pattern, curated, 20,657 membership edges |
| `cluster_number` gene property | Useful for display, already exists |

**Decision point:** Should Cyanorak clusters become OrthologGroup nodes
(unifying the pattern), or stay separate? Arguments for unifying:
consistency, single traversal pattern. Arguments for keeping separate:
Cyanorak clusters are curated and semantically different from eggnog OGs,
already have their own node type and edges.

**Recommendation:** Unify. Create OrthologGroup nodes from Cyanorak clusters
with `source: "cyanorak"`, `taxonomic_level: "curated"`. Keep
`Cyanorak_cluster` nodes and `Gene_in_cyanorak_cluster` edges as aliases
during migration, remove in a later pass. This gives a single query pattern
for all homology while preserving backward compatibility.

### Edge count comparison

| | Current (13 strains) | Cluster nodes (13 strains) | Cluster nodes (+3 Ruegeria) |
|---|---|---|---|
| Homolog-related edges | 365,840 pairwise | ~56K membership | ~66K membership |
| Expression propagation edges | 2,087,991 | 0 | 0 |
| **Total derived edges** | **2,453,831** | **~56K** | **~66K** |

Adding 3 Ruegeria strains adds ~10K membership edges instead of ~3.5-5.5M
pairwise + propagated edges.

---

## OrthologGroup Construction

### Which OGs to create as nodes

For each gene, extract OrthologGroup memberships from the `eggnog_ogs`
list property. Create nodes at **two levels**:

1. **Lowest-level OG** — the most specific taxonomic level in the gene's
   eggnog_ogs list (e.g. Alteromonadaceae for Alt genes, Prochloraceae for
   Pro genes, Rhodobacteraceae for future Ruegeria genes). This is the
   primary orthology signal for within-clade comparisons.

2. **Bacteria-level COG** — the `Bacteria` level OG. This is the
   cross-phylum bridge, equivalent to the current `bacteria_cog_og`.

A gene gets 1-2 OrthologGroup memberships (lowest + bacteria, or just one
if they're the same). Cyanorak genes additionally get their Cyanorak cluster
membership.

### Why two levels, not all levels

The intermediate levels (Proteobacteria, Gammaproteobacteria, etc.) don't
add resolution that matters for our current organisms. The lowest level
gives within-clade precision, and bacteria-level gives cross-phylum reach.
If needed, intermediate-level groups can be added later without schema
changes — just create more OrthologGroup nodes and membership edges.

### Construction logic (pseudo-cypher)

```cypher
// Step 1: Create OrthologGroup nodes from eggnog_ogs
// (done in Python adapter or post-import script)
// For each gene, parse eggnog_ogs list, identify lowest-level and bacteria-level OGs
// Create OrthologGroup nodes and Gene_in_ortholog_group edges

// Step 2: Create OrthologGroup nodes from Cyanorak clusters
MATCH (c:Cyanorak_cluster)
MERGE (og:OrthologGroup {id: c.cluster_number, source: "cyanorak", taxonomic_level: "curated"})

MATCH (g:Gene)-[:Gene_in_cyanorak_cluster]->(c:Cyanorak_cluster)
MERGE (g)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: c.cluster_number})
```

### EggNOG OG parsing

The `eggnog_ogs` list contains entries like:
- `"COG1438@2,Bacteria"` — OG ID `COG1438`, taxon ID `2`, level `Bacteria`
- `"465MN@72275,Alteromonadaceae"` — OG ID `465MN`, taxon ID `72275`, level `Alteromonadaceae`
- `"COG2947"` — legacy format without `@`, ignore (redundant with `@2,Bacteria` entry)
- `"bactNOG23214"` — legacy format, ignore

Parsing: split on `@`, then split the second part on `,` to get taxon_id
and level name. Ignore entries without `@`.

To find the lowest level: the entry with the highest taxon_id (most
specific in the NCBI taxonomy tree). Alternatively, take the last `@`-format
entry in the list (eggnog-mapper outputs them root-to-leaf).

---

## Query Patterns

### Find homologs of a gene

**Current (1-hop pairwise):**
```cypher
MATCH (g:Gene {locus_tag: $lt})-[h:Gene_is_homolog_of_gene]-(other:Gene)
RETURN DISTINCT other.locus_tag, other.product, other.organism_strain,
       h.distance, h.source
```

**New (2-hop through cluster node):**
```cypher
MATCH (g:Gene {locus_tag: $lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)
      <-[:Gene_in_ortholog_group]-(other:Gene)
WHERE other <> g
OPTIONAL MATCH (other)-[:Gene_belongs_to_organism]->(o2:OrganismTaxon)
RETURN DISTINCT other.locus_tag AS locus_tag, other.product AS product,
       other.organism_strain AS organism_strain,
       og.source AS source, og.taxonomic_level AS taxonomic_level
```

Distance is no longer a pre-computed edge property. It can be computed
at query time from the two organisms' taxonomy, or approximated from the
OrthologGroup's taxonomic_level (if two genes share a Prochloraceae-level
OG, they're at most same-family).

### Ortholog expression lookup

**Current (1-hop materialized):**
```cypher
MATCH (cond)-[e:Condition_changes_expression_of_ortholog]->(g:Gene {locus_tag: $lt})
RETURN cond.name, e.expression_direction, e.log2_fold_change, e.original_gene
```

**New (3-hop query-time join):**
```cypher
MATCH (g:Gene {locus_tag: $lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)
      <-[:Gene_in_ortholog_group]-(homolog:Gene)
WHERE homolog <> g
MATCH (cond)-[e:Condition_changes_expression_of]->(homolog)
RETURN cond.name AS condition, e.expression_direction AS direction,
       e.log2_fold_change AS lfc, homolog.locus_tag AS original_gene,
       homolog.organism_strain AS organism,
       og.taxonomic_level AS homology_level
```

### Benchmark results (simulated on current KG)

| Query pattern | Gene | Cluster size | Results | Time |
|---|---|---|---|---|
| 1-hop materialized | PMM1428 | 11 homologs | 44 expr | <1ms |
| 3-hop property join | PMM1428 | 12 homologs | 44 expr | <1ms |
| 1-hop materialized (worst case) | BSR22_07790 | 75 homologs | 502 expr | <1ms |
| 3-hop property join (worst case) | BSR22_07790 | 216 homologs | 1196 expr | <1ms |
| Cluster node traversal (largest Cyanorak, 41 members) | SYNW2227 | 40 homologs | 267 expr | <1ms |

No measurable performance difference. The KG is small enough (~35K genes,
~170K expression edges) that Neo4j handles the join trivially.

---

## Distance Computation

The current design pre-computes `distance` as an edge property using a
CASE statement over the two organisms' taxonomy. With cluster nodes, this
moves to query time.

### Option A: Compute at query time (recommended)

Add the same CASE logic to queries that need distance:

```cypher
MATCH (g)-[:Gene_belongs_to_organism]->(o1:OrganismTaxon)
MATCH (other)-[:Gene_belongs_to_organism]->(o2:OrganismTaxon)
WITH *, CASE
  WHEN o1.id = o2.id THEN "same strain"
  WHEN o1.clade IS NOT NULL AND o1.clade = o2.clade THEN "same clade"
  WHEN o1.species = o2.species THEN "same species"
  WHEN o1.genus = o2.genus THEN "same genus"
  WHEN o1.family = o2.family THEN "same family"
  WHEN o1.order = o2.order THEN "same order"
  WHEN o1.tax_class = o2.tax_class THEN "same class"
  WHEN o1.phylum = o2.phylum THEN "same phylum"
  ELSE "cross phylum"
END AS distance
```

**Requires:** `family` and `tax_class` properties on `OrganismTaxon` nodes
(check if these exist — `order` and `phylum` already do).

### Option B: Use OrthologGroup taxonomic_level as proxy

If two genes share an Alteromonadaceae-level OG, they're at most
same-family apart. This is less precise but avoids the organism join:

```cypher
og.taxonomic_level AS homology_level
// "Alteromonadaceae" → within-family
// "Bacteria" → cross-phylum
// "curated" → Cyanorak (within-order at most)
```

### Recommendation

Use Option A for the `get_homologs` tool (where distance matters for
display). Use Option B for expression queries (where the homology level
is informative enough and the extra join is unnecessary).

---

## Impact on Explorer Queries

### Queries that change

| Tool | Current pattern | New pattern |
|---|---|---|
| `get_homologs` | 1-hop `Gene_is_homolog_of_gene` | 2-hop through OrthologGroup |
| `get_gene_details` (homolog count) | Count of `Gene_is_homolog_of_gene` | Count of shared OrthologGroup members |
| `query_expression` (include_orthologs) | 1-hop `*_expression_of_ortholog` | 3-hop: gene → OG → homolog ← expression |
| `compare_conditions` (ortholog mode) | 1-hop `*_expression_of_ortholog` | 3-hop join |
| `search_genes` (dedup by cluster) | Uses `Gene_is_homolog_of_gene` cluster_id | Uses OrthologGroup membership |

### Queries that don't change

| Tool | Why unchanged |
|---|---|
| `resolve_gene` | No homolog logic |
| `search_ontology` | No homolog logic |
| `genes_by_ontology` | No homolog logic |
| `gene_ontology_terms` | No homolog logic |
| `list_organisms` | No homolog logic |
| `list_filter_values` | No homolog logic |
| `get_schema` | Reflects whatever schema exists |

---

## Migration Path

### Phase 1: Add OrthologGroup nodes (additive, non-breaking)

1. Create `OrthologGroup` nodes from eggnog OGs (lowest-level + bacteria-level)
2. Create `Gene_in_ortholog_group` edges
3. Create OrthologGroup nodes from Cyanorak clusters
4. Keep all existing edges and properties

At this point both patterns work. Explorer can be updated incrementally.

### Phase 2: Update explorer queries

Update each tool to use OrthologGroup traversal instead of pairwise edges.
This can be done tool-by-tool with the existing test suite.

### Phase 3: Remove deprecated edges

1. Drop `Gene_is_homolog_of_gene` edges
2. Drop `Condition_changes_expression_of_ortholog` edges
3. Drop `Coculture_changes_expression_of_ortholog` edges
4. Drop homolog + expression propagation from `post-import.cypher`
5. Optionally drop `Cyanorak_cluster` nodes + `Gene_in_cyanorak_cluster`
   edges (if unified into OrthologGroup)
6. Optionally drop `bacteria_cog_og` and `alteromonadaceae_og` gene properties

---

## Adding New Organisms

With this design, adding Ruegeria (or any future organism) requires:

1. **Load gene nodes** with `eggnog_ogs` list property (already standard)
2. **Parse eggnog_ogs** to create OrthologGroup nodes at lowest level
   (e.g. Rhodobacteraceae) and bacteria level
3. **Create Gene_in_ortholog_group edges**

No new code blocks in post-import. No new gene properties. No pairwise
edge computation. The bacteria-level COG OGs automatically bridge to all
existing organisms that share them.

Estimated new edges for 3 Ruegeria strains (~10K genes): ~10-15K membership
edges to OrthologGroup nodes.

---

## Open Questions

1. **Unify Cyanorak clusters into OrthologGroup?** Recommendation is yes,
   but this adds migration complexity. Could defer to Phase 3.

2. **OrganismTaxon `family` and `tax_class` properties** — do they exist?
   Needed for fine-grained distance computation at query time. If not,
   add to organism adapter.

3. **Index strategy for OrthologGroup** — need index on `OrthologGroup.id`
   and possibly `(Gene_in_ortholog_group)` for fast traversal. Benchmark
   after creation.

4. **Should `search_genes` dedup use OrthologGroup?** Currently dedup
   uses `cluster_id` from homolog edges. With OrthologGroup, dedup could
   group by shared OG membership at any level. Needs design.

5. **Paralog handling** — large bacteria-level COGs (e.g. COG0457, 217
   members) contain paralogs within the same organism. The current pairwise
   edges include these. With cluster nodes, a query for "homologs of gene X"
   would return same-organism paralogs too. Should queries filter
   `WHERE other.organism_strain <> g.organism_strain` by default?
