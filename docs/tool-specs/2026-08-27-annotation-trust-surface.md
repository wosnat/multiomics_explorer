# Tool spec: annotation-trust surface (slice 3 — interpro / ncbifam / merops + trust normalization + `ontology_term_details`)

**Status:** DRAFT v1 for freeze · **Design:** `docs/superpowers/specs/2026-08-27-annotation-trust-surface-design.md` (sections 1–10 approved) · **KG:** KG-SYNC-005 landed 2026-08-27 (`multiomics_biocypher_kg/docs/kg-changes/annotation-trust-surface.md`); explorer schema baseline refreshed 2026-08-27 · **Asks:** `docs/kg-specs/2026-08-27-annotation-trust-kg-asks.md` (ONT-001…015 all landed)
**Mode:** B (8 existing tools, config-driven) + one Mode-A tool (`ontology_term_details`).

Every Cypher block below is **verified against the live KG-SYNC-005 build (2026-08-27)** unless marked otherwise.

## 0. One open decision for freeze

**Single compact trust column** on gene×term rows (design §1). Options: (a) `evidence_score` — numeric rank key, present on 8 of 17 ontologies (GO×3, EC, Pfam, CAZy, TCDB, MEROPS; null on KO, COG, roles, InterPro, NCBIfam, PSORTb, SignalP); (b) `evidence` — categorical ladder, present on all 14 functional-edge ontologies (null only on PSORTb/SignalP). Owner's lean: (a). **Spec is written for (a); switching to (b) changes only the compact/verbose placement of the two columns — no Cypher change.**

## 1. Purpose

Give every gene→term annotation a readable, filterable trust profile with one vocabulary across 17 ontologies; register InterPro, NCBIfam, MEROPS; add a term-side drill-down (`ontology_term_details`) and a browse mode to `search_ontology`; publish a per-ontology reference. Design doc holds the rationale; this spec holds the contract.

## 2. Out of scope

`controlled_vocabularies_hash` in `kg_release_info`; per-row `transport_substrate_resolution`; `list_organisms` protease/domain rollups; NCBIfam `family_type` filter; ORA over bridges; any cutoff on native scalars.

## 3. Status / prerequisites

- [x] KG-SYNC-005 landed and live-verified (all 14 functional edge types carry `sources`+`evidence`; TCDB `attachment_depth` 46,593/7,170; MEROPS `evidence_score` 151/3,768/338; `gene_count`+`organism_count` on all 18 labels; `direct_gene_count` on BP/MF/CC/EC/KEGG/CyanorakRole/InterPro/TCDB/CAZy/MEROPS; `bit_score`; `family_class`; 10 `retired`; 110 vocab nodes)
- [x] Schema baseline refreshed (`config/schema_baseline.yaml`)
- [x] Design approved section-by-section
- [ ] §0 decided
- [ ] Spec frozen

## 4. `ONTOLOGY_CONFIG` registry (design §2) — authoritative table

| key | label / gene_rel / hierarchy / fulltext | trust | rank_prop | compact_edge | verbose_edge | facet | term_verbose | term_details_compact (⊇) | bridges_out |
|---|---|---|---|---|---|---|---|---|---|
| go_bp / go_mf / go_cc | (existing) | sources, evidence, evidence_score | — | — | — | — | — | go_id, direct_gene_count, member_count | — |
| ec | (existing) | sources, evidence, evidence_score | — | — | — | — | — | direct_gene_count | — |
| kegg | (existing, + discusses_rel) | sources, evidence | — | — | — | — | — | direct_gene_count, reaction_count, metabolite_count | Kegg_term_in_brite_category → brite (membership) |
| cog_category, tigr_role | (existing) | sources, evidence | — | — | — | — | — | — | — |
| cyanorak_role | (existing) | sources, evidence | — | — | — | — | — | direct_gene_count | — |
| pfam | (existing, parent_label PfamClan) | sources, evidence, evidence_score | — | — | — | — | — | pfam_id | Pfam_in_interpro_entry → interpro (membership) |
| brite | (existing, bridge via kegg) | (kegg's) | — | — | — | tree | — | tree, tree_code | — |
| tcdb | (existing) | sources, evidence, evidence_score, tier | evidence_score | — | confidence_score, source_agreement, pfam_support, go_support, identity, qcov, evalue, consensus_n, attachment_depth | — | superfamily, metabolite_count | tcdb_id, tc_class_id, direct_gene_count, member_count | Tcdb_family_has_pfam_domain → pfam; Tcdb_family_involved_in_biological_process → go_bp; Tcdb_family_enables_molecular_function → go_mf; Tcdb_family_located_in_cellular_component → go_cc (all composition, prop curated_tcids) |
| cazy | (existing) | sources, evidence, evidence_score | — | — | — | — | — | cazy_id, direct_gene_count | — |
| subcellular_localization | (existing) | — | — | — | localization_score (← `score`) | — | — | psortb_id | — |
| signal_peptide_type | (existing) | — | — | — | signal_peptide_probability (← `probability`), cleavage_site, cleavage_probability | — | — | signalp_id | — |
| **interpro** | InterproEntry / Gene_has_interpro_entry / [Interpro_entry_is_a_interpro_entry] / interproEntryFullText | sources, evidence | — | — | libraries, evalue_library, evalue, match_count, start, end | interpro_type | — | interpro_id, interpro_type, direct_gene_count, member_count | Interpro_entry_related_to_ec_number → ec; Interpro_entry_related_to_cazy_family → cazy (router; computed router_ambiguous) |
| **ncbifam** | NcbifamFamily / Gene_has_ncbifam_family / [] / ncbifamFamilyFullText | sources, evidence | — | — | evalue, bit_score, start, end | — | family_type, gene_symbol | ncbifam_id, family_type, gene_symbol | Ncbifam_family_in_interpro_entry → interpro (membership) |
| **merops** | MeropsFamily / Gene_has_merops_family / [Merops_family_is_a_merops_family] / meropsFamilyFullText | sources, evidence, evidence_score, tier | confidence_score | call_class (warn: nonpeptidase_homolog) | confidence_score, pfam_support, best_hit_kind, identity, qcov, evalue, consensus_n, best_hit_id | — | family_class, catalytic_type, peptidase_gene_count | merops_id, family_class, catalytic_type, peptidase_gene_count, peptidase_organism_count, direct_gene_count, member_count, cleavage_summary, cleavage_p1_residues, known_cleavage_count | Merops_family_has_pfam_domain → pfam (composition, prop member_id_count) |

`term_compact` = `[gene_count, organism_count]` everywhere. `term_details_verbose = "*"` everywhere. `ALL_ONTOLOGIES` = existing 14 + `interpro, ncbifam, merops`. `direct_gene_count` is absent on flat labels and on PfamClan/BriteCategory (KG: vacuous) — nulls there are "not applicable" and stripped.

## 5. Parameters (design §4)

| tool | new params |
|---|---|
| `genes_by_ontology` | `sources: list[str]`, `evidence: list[str]`, `max_tier: int`, `min_evidence_score: float`, `call_class: list[str]`, `interpro_type: Literal[8]` |
| `gene_ontology_terms` | same + `ontology: list[str] | None` (was single | None) + `include_superseded: bool = False` |
| `pathway_enrichment`, `cluster_enrichment` | `sources`, `evidence`, `max_tier`, `min_evidence_score`, `call_class`, `interpro_type` (required when `ontology='interpro'`) |
| `ontology_landscape` | `ontology: list[str] | None`, `call_class`, `interpro_type` |
| `search_ontology` | `search_text` optional (browse), `ontology: list[str] | None`, `min_gene_count: int`, `organism: str | None`, `interpro_type` |
| `list_filter_values` | `filter_type` += evidence, sources, call_class, interpro_type, ncbifam_family_type, merops_catalytic_type, merops_family_class, best_hit_kind, pfam_support, attachment_depth, trust_axes, link_kinds; `ontology: str | None` scope |
| `gene_overview` | none (new columns only) |
| `ontology_term_details` (new) | `term_ids: list[str]`, `organism: str | None`, `link_kinds: list[Literal] | None`, `verbose`, `limit=50`, `offset` |

Validation: unsupported axis → `ValueError` naming the ontology's axes; unknown value → allowed set from `ControlledVocabulary` (pivot-query fallback + warning if the node is missing); multi-ontology skip/raise matrix per design §4.5. All trust params default `None`.

## 6. Row / envelope contracts — see design §3 and §5 (verbatim contract). Column-placement summary:

- gene×term compact: existing + `evidence_score` (§0) + `interpro_type` + `call_class`; verbose: `sources`, `evidence`, `tier` + config `verbose_edge` (strip non-applicable).
- `search_ontology` compact: existing + `ontology_type`, `gene_count`, `organism_count`, `interpro_type`, `score` null in browse; verbose: + `description`, `level_kind`, `direct_gene_count`, config `term_verbose`.
- `ontology_term_details` compact: `term_id, ontology, label, name, description, level, level_kind, is_informative, gene_count, organism_count, direct_gene_count, <term_details_compact>, parents[], children[] (+children_total, children_truncated), links_out[]`; verbose: + `properties` (`t{.*}`), `links_out[].props`, `genes_by_organism[]`.
- `gene_overview` compact: + `merops_classes`, `ncbifam_family_count`, `merops_evidence_score_max` (sparse, uncoalesced).

## 7. Verified Cypher

### 7.1 Trust filters bind at the gene→leaf MATCH, before the walk and the size collapse (merops, level mode, `call_class=['peptidase']`)

```cypher
MATCH (g:Gene {organism_name: $org})-[r:Gene_has_merops_family]->(leaf:MeropsFamily)
WHERE r.call_class IN $call_class            -- generic slot: AND r.evidence IN $evidence, AND (r.tier <= $max_tier OR r.tier IS NULL), AND r.evidence_score >= $min_evidence_score, AND any(s IN $sources WHERE s IN r.sources)
MATCH (leaf)-[:Merops_family_is_a_merops_family*0..]->(t:MeropsFamily)
WHERE t.level = $level
WITH t, collect(DISTINCT g) AS term_genes
WHERE size(term_genes) >= $min_gene_set_size AND ($max_gene_set_size IS NULL OR size(term_genes) <= $max_gene_set_size)
...
```
Verified MIT1002, level 0: SC 22 · MA 18 · MH 8 · PB 8 · SB 6 · MG 5 · SK 5 (peptidase-only); unfiltered gives 10 clans ≥5. Invariant: for `merops.family:S14`, distinct peptidase genes over subtree (125) == `peptidase_gene_count` (125); organisms 41 == `peptidase_organism_count`.

### 7.2 One edge per (gene, term) on hierarchical rollups (tcdb, level 2)

```cypher
MATCH (g:Gene {organism_name: $org})-[r:Gene_has_tcdb_family]->(leaf:TcdbFamily)
MATCH (leaf)-[:Tcdb_family_is_a_tcdb_family*0..]->(t:TcdbFamily) WHERE t.level = $level
WITH DISTINCT t, g
WITH t, g, [(g)-[r2:Gene_has_tcdb_family]->(l2:TcdbFamily)-[:Tcdb_family_is_a_tcdb_family*0..]->(t)
            | {es: r2.evidence_score, ad: r2.attachment_depth, ev: r2.evidence, tier: r2.tier, sources: r2.sources, leaf: l2.id}] AS edges
WITH t, g, edges, head(reverse(apoc.coll.sortMaps(edges, 'es'))) AS best      -- rank_prop desc (confidence_score for merops)
RETURN t.id AS term_id, g.locus_tag AS locus_tag, best.es AS evidence_score, best.ev AS evidence, best.tier AS tier,
       best.sources AS sources, best.ad AS attachment_depth, size(edges) AS n_edges
```
Verified MED4: PMM0392 has 8 edges under `tcdb:3.A.1`, best = eggNOG `3.A.1.28` (0.6); no duplicate (g,t) rows. Same shape for merops with `'confidence_score'` as sort key. Flat ontologies keep the direct `OPTIONAL MATCH (g)-[r]->(t)`.

### 7.3 Leaf mode — `*1..` leaf filter ≡ `attachment_depth = 'most_specific'` (tcdb)

```cypher
MATCH (g:Gene {organism_name: $org})-[r:Gene_has_tcdb_family]->(t:TcdbFamily)
WHERE g.locus_tag IN $locus_tags
  AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family]->(c:TcdbFamily)-[:Tcdb_family_is_a_tcdb_family*1..]->(t) }   -- generic (all hierarchical ontologies)
  -- tcdb only: replaced by  AND ($include_superseded OR r.attachment_depth = 'most_specific')
```
Verified MED4 all genes: 670 rows → 597 by either predicate (identical sets). With `include_superseded=true`, rows carry `attachment_depth='superseded'` (73 in MED4).

### 7.4 `search_ontology` browse mode (merops, level 1) — sort `gene_count DESC, id`

```cypher
MATCH (t:MeropsFamily)
WHERE t.level = $level AND coalesce(t.is_uninformative, '') <> 'true'   -- + ($min_gene_count IS NULL OR t.gene_count >= $min_gene_count), facet
WITH t ORDER BY t.gene_count DESC, t.id SKIP $offset LIMIT $limit
RETURN t.id AS id, t.name AS name, t.level AS level, t.gene_count AS gene_count, t.organism_count AS organism_count,
       null AS score, t.direct_gene_count AS direct_gene_count, t.family_class AS family_class,
       t.catalytic_type AS catalytic_type, t.peptidase_gene_count AS peptidase_gene_count
```
Verified: S33 412 · S09 298 · C26 272 (peptidase_gene_count 41 — the C26 dead-homolog family) · M38 175 · C44 169. Pfam dual-label variant: `MATCH (t) WHERE (t:Pfam OR t:PfamClan) …` (verified). Per-organism scope (`organism` given):

```cypher
MATCH (t:InterproEntry {interpro_type: $interpro_type}) WHERE coalesce(t.is_uninformative,'') <> 'true'
OPTIONAL MATCH (t)<-[:Gene_has_interpro_entry]-(g:Gene {organism_name: $org})
WITH t, count(DISTINCT g) AS org_gene_count WHERE org_gene_count >= $min_gene_count
RETURN t.id AS id, t.name AS name, t.gene_count AS gene_count, org_gene_count ORDER BY org_gene_count DESC, id
```
Verified MED4 HOMOLOGOUS_SUPERFAMILY ≥5: IPR027417 P-loop NTPase 119 · IPR036291 54 · IPR013785 32 · IPR029063 32 · IPR015421 26.

### 7.5 `ontology_term_details` batch (null-safe collects; label guard over all 18 labels; is-a union + bridge union generated from config)

```cypher
UNWIND $term_ids AS tid
OPTIONAL MATCH (t {id: tid}) WHERE t:TcdbFamily OR t:MeropsFamily OR t:InterproEntry OR t:NcbifamFamily OR t:BiologicalProcess OR ... (18 labels)
WITH tid, t
OPTIONAL MATCH (t)-[:<is-a union>]->(p)
WITH tid, t, [x IN collect(DISTINCT CASE WHEN p IS NULL THEN null ELSE {id:p.id, name:p.name, level:p.level} END) WHERE x IS NOT NULL] AS parents
OPTIONAL MATCH (t)<-[:<is-a union>]-(c)
WITH tid, t, parents, count(DISTINCT c) AS children_total,
     [x IN collect(DISTINCT CASE WHEN c IS NULL THEN null ELSE {id:c.id, name:c.name, level:c.level} END) WHERE x IS NOT NULL][0..50] AS children
OPTIONAL MATCH (t)-[b:<bridges_out union>]->(x)
WITH tid, t, parents, children_total, children, count(b) AS links_total,
     [l IN collect(CASE WHEN b IS NULL THEN null ELSE {rel:type(b), target_id:x.id, target_name:x.name, props: properties(b)} END) WHERE l IS NOT NULL] AS links_out
RETURN tid AS term_id, t IS NULL AS not_found, t.name AS name, t.description AS description, t.level AS level, t.level_kind AS level_kind,
       t.gene_count AS gene_count, t.organism_count AS organism_count, t.direct_gene_count AS direct_gene_count,
       parents, children_total, children, links_total, links_out            -- verbose: + t{.*} AS properties, genes_by_organism
```
Verified batch `['tcdb:3.A.1','merops.family:S14','interpro:IPR000362','ncbifam:NF000812','go:0006979','bogus:xyz']`: 3.A.1 → 1 parent, 55 children, 129 links (Pfam + GO); S14 → 1 link (PF00574 Clp protease); IPR000362 → 4 children, 5 router links (5 ECs, `router_ambiguous = true`); NF000812 → 0/0/0; go:0006979 → level 3, 1050/860; `bogus:xyz` → `not_found`. `link_kind` derived from rel type via config. `router_ambiguous` (interpro only): `count(r) > 1 OR t.interpro_type <> 'FAMILY'` (verified IPR000362 → true).

### 7.6 `evidence_score_signals` (when `min_evidence_score` set) and vocab reads

```cypher
MATCH (v:ControlledVocabulary {applies_to: $edge_type, property: 'evidence_score'}) RETURN v.signals AS signals, v.signal_count AS signal_count
MATCH (v:ControlledVocabulary {applies_to: $edge_type, property: $prop}) RETURN v.values, v.description, v.min_value, v.max_value, v.sparse
-- pivot fallback (missing node): MATCH ()-[r:<edge_type>]->() RETURN DISTINCT r.<prop> AS value ORDER BY value
```
Verified: TCDB 5 signals, MEROPS `[tier_le_2, pfam_support]` (2), GO/EC/Pfam/CAZy 3; `evidence` per-edge subsets present on all 14; pivot on `call_class` → 3 values.

### 7.7 Landscape InterPro `(interpro_type, level)` — existing landscape Cypher with `t.interpro_type` in the grouping key (verified earlier this slice, MED4: HOMOLOGOUS_SUPERFAMILY-L0 74 testable terms, DOMAIN-L0 47, FAMILY-L0 7, rest ≤4).

### 7.8 `gene_overview` additions — `coalesce(g.merops_classes, []) AS merops_classes, coalesce(g.ncbifam_family_count, 0) AS ncbifam_family_count, g.merops_evidence_score_max AS merops_evidence_score_max` (props verified on Gene).

### 7.9 Filter semantics numbers (MED4 tcdb, 670 rows): `max_tier=2` keeps 276 (175 tier-null kept); `sources=['eggnog']` 212; `evidence=['homology'] AND evidence_score>=0.6` 98.

## 8. Not verified yet (verify in Stage 3 against the same build)

- Full lockstep multi-ontology paging is api-layer; no Cypher.
- `genes_by_organism` verbose block of `ontology_term_details`: `OPTIONAL MATCH (t)<-[:<is-a>*0..]-(d)<-[:<gene_rel>]-(g) WITH t, g.organism_name AS org, count(DISTINCT g) AS n` — shape only.

## 9. Tests, docs, build order — design §9–§10 apply verbatim. Regression regen rule: existing golden rows may only (i) lose `localization_score` / `signal_peptide_*` from compact, (ii) gain the three appended ontologies; anything else is a concern.

## 10. Acceptance

1. `genes_by_ontology(ontology='merops', organism='MIT1002', level=0, call_class=['peptidase'])` returns the 7 clans above with `by_call_class` and no warning; without `call_class` returns 10 and warns.
2. `gene_ontology_terms(locus_tags=['PMM0392'], ontology=['tcdb'], mode='leaf')` returns only `attachment_depth='most_specific'` rows; `include_superseded=True` adds the `3.A.1` row labelled `superseded`.
3. `search_ontology(ontology=['merops'], level=1)` (browse) returns S33 first with `gene_count=412`; `ontology=['go_bp','tcdb'], search_text='transport', limit=5` returns ≤10 rows ordered by ontology then score with `by_ontology` truncation flags.
4. `ontology_term_details(term_ids=[...6 above...])` matches §7.5 counts; `bogus:xyz` in `not_found`.
5. `pathway_enrichment(ontology='interpro', level=0)` without `interpro_type` raises; with `interpro_type='HOMOLOGOUS_SUPERFAMILY'` returns a well-formed envelope.
6. Trust-vocab coverage test green on this build; `list_filter_values(filter_type='evidence')` lists 5 values with per-edge `applies_to`.
7. `gene_overview(['MIT1002_03660'])` shows `merops_classes=['peptidase']`, `merops_evidence_score_max=1.0`.
