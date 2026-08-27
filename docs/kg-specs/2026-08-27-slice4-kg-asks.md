# KG-side asks: slice 4 light surface + paper batch (KG-SYNC-006)

**Date:** 2026-08-27 · **From:** explorer (`multiomics_explorer`) · **To:** KG (`multiomics_biocypher_kg`)
**Context:** synced release program (KG 0.1.0-alpha.7 + explorer 0.1.0-alpha.5), slice 4 — the last slice
before the release cut. Rides on the same rebuild as the new-paper ingestion so the explorer pays one
regen cycle, not two. Previous asks docs: `2026-08-19-presync-kg-asks.md`,
`2026-08-27-annotation-trust-kg-asks.md` (KG-SYNC-005, §9 landed).

## 1. Why this doc

Slice 4 is three small explorer surfaces. Two of them are explorer-only reads of facts the KG already
carries; one needs four precomputed organism props so `list_organisms` stays a single node scan, the way
every existing organism rollup is built (`coalesce(o.<prop>, 0)` — `reaction_count`,
`transported_metabolite_count`, `measured_metabolite_count`, `derived_metric_count`). The rest of the doc
states what the explorer expects from the paper batch so the post-rebuild regen is a diff review, not an
investigation.

Current state is taken from `config/schema_baseline.yaml` (refreshed 2026-08-27 against KG-SYNC-005) — the
graph was down for the rebuild while this was written; §5 verification queries run once it is back.

## 2. Ask summary

| ID | Ask | Pri | Kind |
|---|---|---|---|
| **ORG-001** | Four precomputed `OrganismTaxon` props — `peptidase_gene_count`, `nonpeptidase_homolog_gene_count`, `interpro_gene_count`, `ncbifam_gene_count` — distinct genes per organism, same post-import aggregation family as `Gene.merops_classes` / `Gene.ncbifam_family_count` (already computed per gene). | **P2** | graph |
| ORG-002 | Document the `Schema_info.controlled_vocabularies_hash` recipe (what is hashed, in what order, which fields, algorithm) in the KG contract doc, and state the stability guarantee: unchanged vocab set ⇒ unchanged hash across rebuilds. Explorer pins the string and compares. | P3 | doc |
| ORG-003 | Paper batch: every new `Experiment.treatment_type` / `background_factors` / `omics_type` / `growth_phase` value is in the corresponding `ControlledVocabulary` node (no values outside the closed vocab); `Publication_discusses_*` edges + `Gene.discussed_in_publication_count` / `Publication.discussed_*_count` regenerated; `Schema_info.release_highlights` / `breaking_changes` stamped on the alpha.7 cut. | P2 | graph + vocab |
| ORG-004 | Paper batch: if any paper adds an organism, it lands as an `OrganismTaxon` with `organism_type` and the taxonomy fields populated (the explorer's `list_organisms` goldens key on `preferred_name`; a genome-only organism is fine — 2 exist). Tell the explorer the count delta (47 → N). | P2 | note |

Not asks (already in the KG, explorer-side only): `Schema_info.controlled_vocabularies_hash` (present since
KG-SYNC-005 — slice-4 item 1 is a read + verdict fold-in); per-row `transport_substrate_resolution` on
transport-arm rows (reads the existing `Gene.transport_substrate_resolution`).

## 3. Per-ask detail

### ORG-001 — organism-level protease / domain-coverage rollups

**Surface it unblocks.** `list_organisms` rows gain `peptidase_gene_count`, `nonpeptidase_homolog_gene_count`,
`interpro_gene_count`, `ncbifam_gene_count`; envelope gains `by_annotation_capability` (top-10 organisms by
`peptidase_gene_count`, carries the other three as columns, excludes zero rows) — the routing question is
"which organisms are protease-rich / which have thin domain coverage" before drilling into
`genes_by_ontology(ontology='merops', organism=…, call_class=['peptidase'])`.

**Definitions (distinct genes, organism-scoped, `OrganismTaxon` ← `Gene.organism_name`):**

| prop | definition | derived from |
|---|---|---|
| `peptidase_gene_count` | genes with `'peptidase' IN g.merops_classes` | `Gene.merops_classes` |
| `nonpeptidase_homolog_gene_count` | genes with `'nonpeptidase_homolog' IN g.merops_classes` (a gene can be in both — do not subtract) | `Gene.merops_classes` |
| `interpro_gene_count` | genes with ≥1 `Gene_has_interpro_entry` edge | edge existence |
| `ncbifam_gene_count` | genes with `g.ncbifam_family_count > 0` (retired families count — they are still calls) | `Gene.ncbifam_family_count` |

Emit `0`, not absent, on organisms with no such genes (genome-only organisms included) — the explorer
reads `coalesce(o.<prop>, 0)` either way, but a dense `0` keeps `capture_annotation_state` distributions
comparable. Invariant the explorer will assert in `tests/integration/test_trust_invariants.py`:
`peptidase_gene_count` == `count(DISTINCT g)` over `(g:Gene {organism_name})` with the MEROPS predicate,
per organism; and Σ over organisms of `peptidase_gene_count` ≥ any single `MeropsFamily.peptidase_gene_count`.

**Why KG-side.** Explorer pattern-counts would add four subqueries over gene edges to a tool that is a flat
47-node scan today, and would be the only organism rollup computed differently from its siblings. The KG
already runs the per-gene aggregation (`merops_classes`, `ncbifam_family_count`); this is one more
`collect`/`count` per organism in the same post-import pass.

**If declined:** explorer falls back to pattern counts on `list_organisms` (documented as such), or defers
the rollup past the release — it is the least important of the three slice-4 items.

### ORG-002 — `controlled_vocabularies_hash` recipe

`Schema_info.controlled_vocabularies_hash` already exists. The explorer will (a) pin the hash string it was
built against in `EXPECTED_KG_SHAPE`, (b) fold a mismatch into the `kg_release_info` verdict as `warn`
("vocabulary set changed since this explorer was built — `list_filter_values` reads live, filters still
validate, but docs://ontologies pages may list stale values"). For that to be honest the explorer needs to
know:

- what is hashed — presumably the sorted set of `(applies_to, property, values, closed, sparse, …)` tuples;
  say which fields are in and which (e.g. `description`) are out;
- the algorithm and encoding (sha256 over canonical JSON? first N hex chars?);
- the guarantee: a rebuild with an unchanged vocab set yields an identical hash (no build timestamp, no
  node-id, no ordering dependence).

Doc-only ask; no graph change. If the hash covers descriptions too, say so — then doc-only vocab edits
will also trip the warn, which is acceptable but should be stated.

### ORG-003 / ORG-004 — paper batch expectations

Not new schema — the explorer's regen rule for a content-only rebuild. The explorer expects, after the
rebuild:

- `Experiment` / `Publication` / `Changes_expression_of` counts grow; `Schema_info.paper_count` /
  `experiment_count` / `expression_edge_count` move accordingly (these feed `kg_release_info`).
- Every categorical on the new experiments is inside its `ControlledVocabulary` (`treatment_type`,
  `background_factors`, `omics_type`, `growth_phase`, `table_scope`, `direction`). A new value is fine —
  it just has to be in the vocab node so `list_filter_values` and the explorer's vocab-coverage test see it.
- The `discusses` literature index is regenerated for the new papers (the explorer's `discussed_*` rollups
  are precomputed node props — stale props would silently under-count).
- If a paper brings a data type the KG does not model today (new `DerivedMetric` kind, new
  `MetaboliteAssay` shape, a new omics layer), flag it in §6 — that is a schema change and would need its
  own explorer slice after the release rather than riding on slice 4.

## 4. Audited and accepted as-is (explicit non-asks)

- `Gene.transport_substrate_resolution` — the per-row transport-arm column is a read of the existing gene
  prop; no KG change.
- `Schema_info.controlled_vocabularies_hash` — exists; only the recipe doc (ORG-002).
- `MeropsFamily.peptidase_gene_count` / `peptidase_organism_count` — term-side twins already surfaced by
  `ontology_term_details`; ORG-001 is the organism-side complement, not a replacement.

## 5. Verification queries (run after the rebuild lands on `:7687`)

```cypher
-- ORG-001: props present and dense
MATCH (o:OrganismTaxon)
RETURN count(o) AS organisms,
       count(o.peptidase_gene_count) AS has_pep, count(o.nonpeptidase_homolog_gene_count) AS has_nonpep,
       count(o.interpro_gene_count) AS has_ipr, count(o.ncbifam_gene_count) AS has_nf,
       sum(o.peptidase_gene_count) AS pep_total

-- ORG-001: invariant, per organism (should return 0 rows)
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (g:Gene {organism_name: o.organism_name}) WHERE 'peptidase' IN coalesce(g.merops_classes, [])
WITH o, count(DISTINCT g) AS live WHERE live <> coalesce(o.peptidase_gene_count, 0)
RETURN o.preferred_name, live, o.peptidase_gene_count

-- ORG-002: hash present and stable across two rebuilds of the same vocab set
MATCH (s:Schema_info {id: 'schema_info'})
RETURN s.version, s.built_at, s.controlled_vocabularies_hash, s.paper_count, s.experiment_count, s.organism_count

-- ORG-003: no categorical outside its vocab (example: treatment_type)
MATCH (v:ControlledVocabulary {applies_to: 'Experiment', property: 'treatment_type'})
MATCH (e:Experiment) UNWIND e.treatment_type AS t
WITH v, collect(DISTINCT t) AS seen
RETURN [x IN seen WHERE NOT x IN v.values] AS outside_vocab

-- ORG-003: discusses index covers the new papers
MATCH (p:Publication) WHERE NOT (p)-[:Publication_discusses_gene|Publication_discusses_kegg_pathway]->()
RETURN count(p) AS pubs_without_discusses, collect(p.doi)[0..10] AS sample

-- ORG-004: organism delta
MATCH (o:OrganismTaxon) RETURN count(o) AS organisms, collect(o.preferred_name) AS names
```

## 6. KG review

_(KG owner fills in: accept / revise / decline per ask, plus any schema change the paper batch introduced.)_

## Status

- [ ] Asks reviewed (KG side)
- [ ] KG-SYNC-006 rebuilt (papers + ORG-001) on `:7687`
- [ ] §5 verification queries pass
- [ ] Explorer `schema_baseline.yaml` refreshed; slice-4 tool spec written against the live build
