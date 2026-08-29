# KG-side asks: findings from the explorer MCP-docs review (2026-08-29)

**Date:** 2026-08-29 · **From:** explorer (`multiomics_explorer`) · **To:** KG (`multiomics_biocypher_kg`)
**Context:** a six-reviewer audit of every explorer doc surface (68 `docs://` pages, 4 example scripts, tool
docstrings, CLAUDE.md table) checked every claim against code and the live dev build
(`0.0.0-dev`, `built_at 2026-08-29T10:11Z`, 127,035 genes, 48 `OrganismTaxon`). Most findings are
explorer-side and are being fixed there. The items below are the ones where the **docs describe what the
KG was designed to do, and the KG does something else** — or where the KG's own stated rule is not what the
graph holds. Each needs a KG-side answer before the explorer prose can be rewritten with confidence.
Previous asks docs: `2026-08-27-annotation-trust-kg-asks.md`, `2026-08-29-gene-overview-family-counts-asks.md`.

## 1. Ask summary

| ID | Ask | Pri | Kind |
|---|---|---|---|
| **DOC-001** | **`evidence` rung on eggNOG-sourced GO / EC / Pfam / CAZy edges is `curated`**, contradicting the KG's own ladder definition (`family_inferred` = orthology transfer). Also `['eggnog','interproscan']` reads `signature` on Pfam but `curated` on CAZy. Decide the intended mapping and re-emit, or amend the ladder doc. | **P1** | graph + doc |
| **DOC-002** | **KEGG `is_uninformative` is KO-only by config** (`^K\d+;\s+uncharacterized protein`); no pathway / category term is flagged. `ko01100` "Metabolic pathways" (27,192 genes), `ko01110`, `ko01120`, `ko01240`, `ko01230`, `ko01200` are unflagged. Explorer docs (and `informative_only=True`'s stated purpose) assumed global maps were flagged. Flag the `ko011xx` global-map family (and `category`/`subcategory` levels?) or confirm the explorer should gate on `max_gene_set_size` instead. | **P1** | graph + vocab |
| DOC-003 | `ControlledVocabulary` **descriptions leak build provenance** into researcher-facing text — e.g. `Experiment.compartment`: "Harvested from COMPARTMENTS in multiomics_kg/vocab/non_de_evidence.py. Matches CLAUDE.md exactly once its Phase-2 addendum…". `list_filter_values` now surfaces `description` verbatim. Move provenance to a comment (the `table_scope` entry already did this on 2026-08-29). Audit all entries. | P2 | vocab |
| DOC-004 | `Experiment.compartment` declares 6 values; `spent_medium` and `lysate` occur on **0** nodes of any label. Either drop from the closed list or mark declared-unused so consumers don't document phantom values. Same check for `MeropsFamily.catalytic_type = 'glutamic'` (0 nodes). | P3 | vocab |
| DOC-005 | Confirm there are **no Gene-level chemistry scalars** (`Gene.ec_numbers` / `ko_terms` / `kegg_ids` / `cog_categories` are null on all 127,035 genes; only `catalytic_activities` exists, 8,084 genes). If these were dropped deliberately, list them in `breaking_changes` once; the explorer will stop documenting them. | P3 | doc |
| DOC-006 | `KeggTerm` pathway nodes carry `direct_gene_count = 0` on all 447 (genes attach to KOs only). Either omit the prop on `level_kind='pathway'` (as done for BriteCategory/PfamClan) or document "always 0 by construction" in the vocab entry. | P4 | graph or doc |
| DOC-007 | R5 grandfathered exceptions: `is_uninformative='true'` and `level_is_best_effort='true'` are one-state string flags (absent = false). Not asking for a change — asking that `docs/kg-changes/vocabulary-contract.md` list them explicitly as R5 exceptions so consumers stop expecting `'false'`. | P4 | doc |
| DOC-008 | `TigrRole` informativeness: explorer measured 9 flagged roles; `tigr.role:270` ("Disrupted reading frame /") and `856` ("Not Found") are level-0 roots with no parent. Confirm both are in the F1.1 list (the 2026-08-29 note says 270 was added; 856 not mentioned). | P4 | doc |

## 2. Detail

### DOC-001 — `evidence` on eggNOG-sourced functional edges (P1)

KG CLAUDE.md (KG-SYNC-005 bullet) defines the ladder as
`curated > signature > homology > family_inferred > domain_inferred` with
"`family_inferred` = orthology transfer (eggNOG KO/COG/TCDB-only)" and "`curated` = Cyanorak/TIGR roles".
Live cross-tab of `sources × evidence` (top rows per edge type):

```
Gene_catalyzes_ec_number
  ['uniprot']                              curated          12689
  ['eggnog']                               curated          11676   <-- orthology transfer reads curated
  ['interproscan']                         family_inferred   9726
Gene_has_pfam
  ['eggnog','interproscan']                signature        59338
  ['eggnog']                               curated          24700   <--
  ['interproscan']                         signature        14307
  ['cyanorak']                             curated           2970
Gene_has_cazy_family
  ['eggnog','interproscan']                curated            801   <-- same source pair is `signature` on Pfam
  ['eggnog']                               curated            744   <--
  ['interproscan']                         domain_inferred    449
  ['interproscan']                         family_inferred    203
Gene_involved_in_biological_process (single-source edges)
  ['eggnog']                               curated         434094   <--
  ['cyanorak'] / ['ncbi'] / ['uniprot']    curated         15405 / 12006 / 10400
  ['interproscan']                         family_inferred   8709 ; domain_inferred 7177
Gene_enables_molecular_function   ['eggnog'] curated 180473 <-- ; interproscan domain_inferred 13023 / family_inferred 11006
Gene_located_in_cellular_component ['eggnog'] curated 100481 <-- ; interproscan family_inferred 3864 / domain_inferred 2042
Gene_has_kegg_ko      ['eggnog']  family_inferred  73912   (consistent with the ladder)
Gene_in_cog_category  ['eggnog']  family_inferred 115246   (consistent)
Gene_has_tcdb_family  ['eggnog']  family_inferred  13385   (consistent)
Gene_has_tigr_role    ['interproscan'] family_inferred 16300; ['cyanorak'] curated 39544 (consistent)
```

So on the four eggNOG-era edge types (GO×3, EC, Pfam, CAZy — the ones that predate KG-SYNC-005 and take
their rung from the per-token `<field>_evidence` map in `gene_annotations_merged.json`), eggNOG-only
transfer is labelled `curated`, while on the four post-SYNC-005 edge types it is `family_inferred`. The
explorer's `evidence=['curated']` filter therefore means "curated or eggNOG-transferred" on GO/EC/Pfam/CAZy
and "curated" on roles — the exact non-uniformity ONT-008 was meant to remove.

Two consistent readings; please pick one:

- **(a) Re-map the merged-annotation rung.** In `annotation_provenance.annotation_edge_props`, eggNOG-only
  tokens → `family_inferred`; `uniprot`/`ncbi`/`cyanorak`-backed tokens → `curated`; `interproscan`-only →
  `signature` (Pfam) / `family_inferred` / `domain_inferred` (EC/CAZy/GO via router). Multi-source edges
  take the strongest rung, as today. Expected effect: GO-BP `curated` drops by ~434k edges, EC by ~11.7k,
  Pfam by ~24.7k, CAZy by ~744. This is a value change on released edges → `breaking_changes`.
- **(b) Keep the data, amend the ladder doc**: "`curated` on GO/EC/Pfam/CAZy means *asserted by a
  reference annotation (UniProt/NCBI/Cyanorak) or transferred by eggNOG from a curated ortholog*". Then
  `evidence` is not comparable across ontologies and the explorer will say so on every page.

Explorer preference: (a). The `Pfam` vs `CAZy` disagreement on `['eggnog','interproscan']` suggests the
current rung is an artefact of which source wrote the token first, not a decision.

Verification after (a):
```cypher
MATCH ()-[r]->() WHERE type(r) IN ['Gene_involved_in_biological_process','Gene_enables_molecular_function','Gene_located_in_cellular_component','Gene_catalyzes_ec_number','Gene_has_pfam','Gene_has_cazy_family']
  AND r.sources = ['eggnog'] AND r.evidence = 'curated'
RETURN type(r), count(*)   -- 0 rows expected
```

### DOC-002 — KEGG informativeness stops at KO (P1)

`config/uninformative_terms.yaml`:
```yaml
kegg_term:
  name_patterns:
    - '^K\d+;\s+uncharacterized protein\b'
```
Live: `ko` 212 / 4,644 flagged; `pathway` 0 / 447; `subcategory` 0 / 46; `category` 0 / 6.

`kegg.pathway:ko01100` "Metabolic pathways" carries 27,192 genes (subtree; 519 / 1,973 on MED4 = 26%);
`ko01110` 12,711; `ko01120` 6,559. These are KEGG's *global/overview maps* (the `011xx` block) and are
the standard exclusion in every KEGG-ORA implementation because they are unions of other pathways. The
explorer's `informative_only=True` default (F1 / A3, 2026-05) was documented as removing exactly these — the
explorer docs and CLAUDE.md `[ENR]` note cite "KEGG map00001 'metabolic pathways'" (an ID that has never
existed in the KG; the prose was written from the design, not the graph).

Ask: add the global maps to the KEGG rule. Note the 13 `ko011xx`/`ko012xx` global/overview maps are
**parentless level-2 nodes** in the KG — there is no "Global and overview maps" subcategory node to key a
structural rule on — so the rule has to be an ID list (or a `name_patterns` entry for the parentless
pathway set): `ko01100, ko01110, ko01120, ko01200, ko01210, ko01212, ko01220, ko01230, ko01232, ko01240,
ko01250, …` (please enumerate the parentless pathway nodes live: `MATCH (p:KeggTerm {level_kind:'pathway'})
WHERE NOT (p)-[:Kegg_term_is_a_kegg_term]->() RETURN p.id, p.name`). Also decide `category` /
`subcategory` levels (6 + 46 nodes): they are never ORA targets at `level=2` but `genes_by_ontology(level=0|1)`
rolls up to them; flagging them is harmless and honest.

Until this lands the explorer will document: "KEGG `informative_only` drops uncharacterized KOs only; drop
global maps with `max_gene_set_size` or by id".

Verification:
```cypher
MATCH (p:KeggTerm {level_kind:'pathway'}) WHERE NOT (p)-[:Kegg_term_is_a_kegg_term]->()
RETURN p.id, p.is_uninformative   -- all 'true' expected
```

### DOC-003 — vocabulary descriptions are researcher-facing now (P2)

`list_filter_values(filter_type=…)` (explorer backlog 2.3, shipped 2026-08-29) emits
`ControlledVocabulary.description` once on the envelope and each value's description per row. Live sample:

```
Experiment.compartment:
  "Subcellular fraction this experiment measured; default "whole_cell". Harvested from COMPARTMENTS in
   multiomics_kg/vocab/non_de_evidence.py. Matches CLAUDE.md exactly once its Phase-2 addendum
   ("extracellular") is folded into the base 5-value list documented under SubcellularLocalization — the
   two CLAUDE.md mentions are consistent, just split across two bullets."
```

The `Experiment.table_scope` entry already moved provenance into a YAML comment on 2026-08-29 — ask for the
same pass over every entry (a `kg_validity` test: description must not match `CLAUDE.md|\.py|Phase-|addendum|
harvested`). Related: the explorer's envelope description for a *cross-edge* property (`evidence`,
`sources`) takes the first owner's text, which is GO-edge-specific ("InterPro contributes GO from FAMILY
and DOMAIN entries"). If the vocabulary could carry one property-level description alongside the
per-`applies_to` ones, the explorer would use it; otherwise the explorer will label the owner.

### DOC-004 — declared-unused vocabulary values (P3)

| property | declared | observed on any label |
|---|---|---|
| `compartment` | whole_cell, vesicle, exoproteome, extracellular, spent_medium, lysate | first 4 (Experiment 183/13/10/3; DM: first 3; MetaboliteAssay: whole_cell/vesicle/extracellular) |
| `MeropsFamily.catalytic_type` | incl. `glutamic` | 0 `glutamic`; 5 of 7 inhibitor families null |

Docs now quote `list_filter_values` instead of the YAML, so phantom values propagate into every "valid
values are…" sentence. Either prune or add a `declared_only: true` marker the explorer can render.

### DOC-005 — Gene-level chemistry scalars (P3)

```cypher
MATCH (g:Gene) RETURN count(g), count(g.ec_numbers), count(g.ko_terms), count(g.kegg_ids), count(g.cog_categories), count(g.catalytic_activities)
-- 127035, 0, 0, 0, 0, 8084
```
`schema_baseline.yaml` (explorer) lists `ec_numbers: list` under a node (line 743); explorer `gene_details`
docs describe them as sparse Gene props. If they were never Gene props, no KG action — the explorer will
delete the prose. If they were and were dropped, one `breaking_changes` line please.

### DOC-006 / DOC-007 / DOC-008 — doc-only confirmations

See table. DOC-006: `max(direct_gene_count)` over 447 pathway nodes = 0. DOC-007: R5 text says "no native
bool; a two-state fact is a categorical string naming both states" — `is_uninformative` / `level_is_best_effort`
are one-state `'true'`-or-absent; fine, just list them. DOC-008: explorer counts 9 flagged `TigrRole` nodes
live; please confirm the intended set (3 junk mainroles + 5 junk subroles + `270`? and `856`?).

## 3. Not asks — recorded so the KG side knows the explorer is handling them

- `organism_gene_count` subtree scope, `attachment_depth`, `tcdb_family_count`, TIGR two-level hierarchy,
  NCBIfam→TigrRole router, metabolite-ID coercion, two-state DM strings: all verified live and correct;
  explorer prose is being brought in line.
- TCDB gene attachments occur only at levels 1–4 (2 + 1 at level 1; 34,782 at 2; 15,743 at 3; 4,099 at 4);
  class/subclass `gene_count` are rollups. Explorer docs wrongly said "attached at every level"; fixing.
- `most_specific` is non-unique per gene (PMM0392: 7 most-specific + 1 superseded; 9,045 / 30,547 TCDB genes
  have > 1). Explorer will document; no KG change.
- Numeric drift after the −423-gene rebuild (node counts, 70.7 % / 68.8 % tested-absent shares, avg
  discussed-pubs 1.23 / max 8) is explorer-doc staleness.
- Two `OrganismTaxon` share `preferred_name='Meiothermus ruber'` — already known; explorer documents the
  join-by-edge rule.
