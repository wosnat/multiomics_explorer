# KG change spec for list_organisms

## Summary

Fix garbage taxonomy nodes, populate missing `species`, add precomputed
data-availability stats on OrganismTaxon nodes, and align
Publication.organisms with OrganismTaxon.preferred_name.

## Current state

18 OrganismTaxon nodes. 13 have genes (strains with sequenced genomes),
5 have 0 genes (parent/umbrella nodes or garbage).

### Problem 1: Garbage taxonomy nodes (wrong NCBI taxon mapping)

Three nodes have `preferred_name` values that don't match their NCBI
taxonomy. These appear to be name collisions in the taxonomy lookup
during KG build — the organism name matched the wrong NCBI taxon ID.

| preferred_name | ncbi_taxon_id | Actual organism (NCBI) | genus (wrong) |
|---|---|---|---|
| Pseudohoeflea | 398581 | Influenza A virus H5N1 | Alphainfluenzavirus |
| Marinobacter | 413470 | *Masdevallia* (orchid) | Masdevallia |
| Thalassospira | 191411 | Chlorobiia (class) | null |

All three have 0 genes and 0 publications — no downstream data depends
on them.

```cypher
-- Verify: all three have 0 genes and 0 publications
MATCH (o:OrganismTaxon)
WHERE o.preferred_name IN ['Pseudohoeflea', 'Marinobacter', 'Thalassospira']
OPTIONAL MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o)
OPTIONAL MATCH (p:Publication)
  WHERE ANY(org IN p.organisms WHERE org = o.preferred_name)
RETURN o.preferred_name, count(DISTINCT g) AS genes, count(DISTINCT p) AS pubs
```

### Problem 2: Missing `species` on some strain nodes

`species` is populated for 8 of 13 strain-level organisms. Missing for:

| preferred_name | genus | Expected species |
|---|---|---|
| Prochlorococcus RSP50 | Prochlorococcus | (unclassified — no formal species) |
| Synechococcus CC9311 | Synechococcus | (unclassified — no formal species) |
| Alteromonas macleodii MIT1002 | Alteromonas | Alteromonas macleodii |
| Alteromonas macleodii EZ55 | Alteromonas | Alteromonas macleodii |
| Alteromonas macleodii HOT1A3 | Alteromonas | Alteromonas macleodii |

```cypher
-- Verify: which strain nodes are missing species
MATCH (o:OrganismTaxon)
WHERE o.strain_name IS NOT NULL AND o.species IS NULL
RETURN o.preferred_name, o.genus, o.strain_name, o.ncbi_taxon_id
```

Note: RSP50 and CC9311 are genuinely unclassified at species level in
NCBI taxonomy. The Alteromonas strains should have species
"Alteromonas macleodii" — likely missing because the NCBI taxon ID
(28108) is genus-level, not strain-level.

## Required changes

### New nodes

None.

### New edges

None.

### Property changes

| Node/Edge | Property | Change | Notes |
|---|---|---|---|
| OrganismTaxon (Pseudohoeflea) | — | delete node | Garbage: maps to Influenza virus. 0 genes, 0 pubs. |
| OrganismTaxon (Marinobacter) | — | delete node | Garbage: maps to orchid genus. 0 genes, 0 pubs. |
| OrganismTaxon (Thalassospira) | — | delete node | Garbage: maps to Chlorobiia class. 0 genes, 0 pubs. |
| OrganismTaxon (Alt. MIT1002) | `species` | add: "Alteromonas macleodii" | Extract from lineage or set during build |
| OrganismTaxon (Alt. EZ55) | `species` | add: "Alteromonas macleodii" | Extract from lineage or set during build |
| OrganismTaxon (Alt. HOT1A3) | `species` | add: "Alteromonas macleodii" | Extract from lineage or set during build |
| OrganismTaxon (all) | `gene_count` | add (int) | Count of `Gene_belongs_to_organism` edges. 0 for parent/umbrella nodes. |
| OrganismTaxon (all) | `publication_count` | add (int) | Count of publications with exact match in `Publication.organisms`. |
| OrganismTaxon (all) | `experiment_count` | add (int) | Sum of `p.experiment_count` across matched publications. 0 if no publications. |
| OrganismTaxon (all) | `treatment_types` | add (list[str]) | Distinct treatment types across matched publications. Empty list if none. |
| OrganismTaxon (all) | `omics_types` | add (list[str]) | Distinct omics types across matched publications. Empty list if none. |

### Data alignment: Publication.organisms ↔ OrganismTaxon.preferred_name

`Publication.organisms` values must exactly match `OrganismTaxon.preferred_name`.
Currently 1 mismatch:

| Publication.organisms value | OrganismTaxon.preferred_name | Fix |
|---|---|---|
| `"Alteromonas MIT1002"` | `"Alteromonas macleodii MIT1002"` | Align — either update Publication or OrganismTaxon |

This alignment is required because `list_organisms` joins on exact match
to compute `publication_count`, and `list_publications` organism filter
should also use exact match for consistency.

**Root cause:** The publication organism names are set during publication
ingestion, likely from manual/curated metadata that uses a shorter form.
The OrganismTaxon preferred_name includes the species epithet. The KG
build pipeline should normalize Publication.organisms values against
OrganismTaxon.preferred_name after both are loaded.

### Precomputed stats on OrganismTaxon

Computed post-import, after Publication.organisms alignment is done.
Follows the same pattern as precomputed stats on Publication nodes
(see `kg-spec-list-publications.md`).

```cypher
-- Step 1: gene_count
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o)
WITH o, count(g) AS gc
SET o.gene_count = gc

-- Step 2: publication/experiment stats
-- (requires Publication.organisms ↔ preferred_name alignment first)
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (p:Publication)
  WHERE ANY(org IN p.organisms WHERE org = o.preferred_name)
WITH o,
     count(DISTINCT p) AS pc,
     CASE WHEN count(p) > 0 THEN sum(p.experiment_count) ELSE 0 END AS ec,
     apoc.coll.toSet(reduce(s = [], t IN collect(p.treatment_types) | s + t)) AS tts,
     apoc.coll.toSet(reduce(s = [], t IN collect(p.omics_types) | s + t)) AS ots
SET o.publication_count = pc,
    o.experiment_count = ec,
    o.treatment_types = tts,
    o.omics_types = ots
```

**Note:** `treatment_types` and `omics_types` list ordering may differ
between precomputed and live aggregation (Neo4j `collect` ordering is
non-deterministic). This is expected — values match, order may not.
Verification queries should compare sets, not ordered lists.

### New indexes

None.

## Root cause (KG build pipeline)

The garbage nodes likely come from the organism name resolution step in
`multiomics_biocypher_kg`. Possible causes:

- **Name collision in NCBI taxonomy lookup:** "Pseudohoeflea",
  "Marinobacter", "Thalassospira" are valid marine bacterial genera,
  but the taxon ID lookup returned the wrong organism. May be a
  case-sensitivity issue, a homonym resolution bug, or stale cache.
- **Missing species on Alteromonas strains:** The NCBI taxon ID 28108
  is genus-level (*Alteromonas*), not strain-level. The build pipeline
  may not be extracting species from the lineage string for
  genus-level taxon IDs.

**Recommended fix in KG repo:** investigate the organism name → taxon ID
mapping step. Likely need to either:
1. Fix the lookup to resolve correct taxon IDs for these organisms
2. Add a validation step that flags when taxonomy lineage doesn't
   match the organism's expected domain (e.g. marine bacterium
   resolving to a virus or plant)
3. For species: extract from lineage string when taxon ID is genus-level

## Verification queries

```cypher
-- 1. Garbage nodes are gone
MATCH (o:OrganismTaxon)
WHERE o.preferred_name IN ['Pseudohoeflea', 'Marinobacter', 'Thalassospira']
RETURN count(o)
-- Expected: 0

-- 2. All strain-level Alteromonas nodes have species
MATCH (o:OrganismTaxon)
WHERE o.genus = 'Alteromonas' AND o.strain_name IS NOT NULL
RETURN o.preferred_name, o.species
-- Expected: all 3 have species = "Alteromonas macleodii"

-- 3. No OrganismTaxon has a non-bacterial lineage
--    (sanity check — all organisms in this KG should be bacteria or phage)
MATCH (o:OrganismTaxon)
WHERE o.superkingdom IS NOT NULL
  AND o.superkingdom <> 'Bacteria'
  AND o.preferred_name <> 'Phage'
RETURN o.preferred_name, o.superkingdom, o.ncbi_taxon_id
-- Expected: 0 rows

-- 4. Total organism count is reasonable
MATCH (o:OrganismTaxon) RETURN count(o)
-- Expected: 15 (was 18, minus 3 garbage)

-- 5. Precomputed gene_count matches live count
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o)
WITH o, count(g) AS live_count
WHERE o.gene_count <> live_count
RETURN o.preferred_name, o.gene_count, live_count
-- Expected: 0 rows

-- 6. Precomputed publication_count matches live count
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (p:Publication)
  WHERE ANY(org IN p.organisms WHERE org = o.preferred_name)
WITH o, count(DISTINCT p) AS live_count
WHERE o.publication_count <> live_count
RETURN o.preferred_name, o.publication_count, live_count
-- Expected: 0 rows

-- 7. Precomputed experiment_count matches live sum
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (p:Publication)
  WHERE ANY(org IN p.organisms WHERE org = o.preferred_name)
WITH o, CASE WHEN count(p) > 0 THEN sum(p.experiment_count) ELSE 0 END AS live_count
WHERE o.experiment_count <> live_count
RETURN o.preferred_name, o.experiment_count, live_count
-- Expected: 0 rows

-- 8. No nulls in precomputed lists
MATCH (o:OrganismTaxon)
WHERE o.treatment_types IS NULL OR o.omics_types IS NULL
RETURN o.preferred_name
-- Expected: 0 rows

-- 9. All Publication.organisms values match an OrganismTaxon.preferred_name
MATCH (p:Publication)
UNWIND p.organisms AS pub_org
WITH DISTINCT pub_org
WHERE NOT EXISTS { MATCH (o:OrganismTaxon) WHERE o.preferred_name = pub_org }
RETURN pub_org
-- Expected: 0 rows
```

## Status

- [x] Spec reviewed with user
- [x] Changes implemented in KG repo
- [x] KG rebuilt
- [x] Verification queries pass (2026-03-22)
