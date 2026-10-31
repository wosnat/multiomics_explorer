# Transport: three routes, read side by side

What transports compound X in organism Y, or what does gene Z move? The KG answers from three routes. They are kept apart on every row (`evidence_source`), never blended into one count. This page says what each route is, where it is biased, how to read agreement, and what an empty answer means.

## The routes

| `evidence_source` | Path | What a row says | Bias to know |
|---|---|---|---|
| `metabolism` | `Gene → Reaction → Metabolite` (KEGG) | The gene's enzyme takes part in a reaction involving the compound. Not transport. | Undirected reactions; KO inference may be putative. |
| `transport` | `Gene → TcdbFamily (tc_system) → Metabolite / ChemicalRole` (TCDB) | A TCDB system the gene points at directly (`tcdb_gate='direct'`) is curated with the compound (or a role class). `tcdb_identity` and `tcdb_calls` qualify it. | Genes TCDB placed only at family or subfamily level return no rows by default; see `include_tcdb_family_substrates` below. |
| `go_transport` | `Gene → GO term → Metabolite / ChemicalRole` (GO) | GO defines the gene's term as moving the compound. A term definition, not a gene fact; the gene→GO edge says how the gene came to carry it (`go_evidence`: `curated`, `family_inferred`, `domain_inferred`; `go_sources`). | Molecular-function and biological-process terms mean different things; curated target filter; coarse class targets. |

Use `genes_by_metabolite` (compound → genes) and `metabolites_by_gene` (genes → compounds). With `evidence_sources=None` all three routes run; scope with `evidence_sources=['go_transport']`.

## Reading a GO row

- **MF vs BP.** `go_namespace='molecular_function'` terms are transporter activities ("urea transmembrane transporter activity"). `'biological_process'` terms are broader: they also cover storage, regulation and accessory subunits. A gene carrying "iron ion transport" is not necessarily a transporter (MED4 `ftn`, ferritin, reaches iron this way). Prefer MF rows for "is this gene a transporter"; BP rows add genes linked to the process. Most GO-route genes reach a substrate through both. `go_namespace=['molecular_function']` keeps only the MF rows.
- **Row grain.** One row per gene × own GO term × target. A gene with an MF and a BP term for the same compound gives two rows; count genes with `gene_count_total`, not rows.
- **Evidence.** `go_evidence` is a class label (`curated`, `family_inferred`, `domain_inferred`), not a numeric score, and this route has no score to threshold. Rank rows by it (`curated` first). `go_evidence=['curated']` keeps only curated rows when you want the strict set; the allowed values come from `list_filter_values`.
- **Direct vs inherited.** Default rows are direct: the gene's own term names the target (`go_term_depth=0`). `go_include_ancestors=True` adds rows where an is_a ancestor of the gene's term names the target: `go_term_depth` counts hops, `go_axiom_term_id` / `go_axiom_term_name` name the ancestor, and a (gene, target) already reached directly is not repeated. Inherited rows widen to broader targets and are a recall expansion. `rows_by_go_term_depth` in the envelope shows the split, and appears only when the GO arm is active.
- **Targets that are classes.** A `target_kind='chemical_role'` row names a role (siderophore, xenobiotic, drug, toxin, vitamin, neurotransmitter), not a compound; roles are not propagated to the compounds they cover. The role id is a valid input to both tools and also reaches TCDB role edges. The neurotransmitter role is eukaryote-centred: in bacteria the matching terms are mostly amino-acid transporters (a warning says so). Class-valued metabolite targets (Lipid, carbohydrate, peptide) are real `Metabolite` nodes with no formula.

## Reading a TCDB row

- **Row grain.** One row per gene × TCDB system × metabolite (`tcdb_route='direct'`). The system is a 5-part TC number (`tcdb:3.A.1.4.4`, level kind `tc_system`), the only level TCDB curates substrates on. `tcdb_family_id` names it and `attached_tcdb_id` (the node the gene's edge points at) is the same id.
- **Direct vs family rows.** Direct rows need a `direct` call: a rank-1 DIAMOND best hit at ≥ 40% identity, a tier-1 DIAMOND call, or an eggNOG call onto a system. A gene TCDB could only place at family or subfamily level (`tcdb_gate='annotated'`) has no direct rows. `include_tcdb_family_substrates=True` is the fallback for those genes: it walks from the gene's deepest family or subfamily down to every system below it and adds `tcdb_route='family'` rows, one per (gene, attached node, metabolite). On a family row `tcdb_family_id` is the attached family, not a system, and `tcdb_substrate_system_count` says how many of its systems TCDB curates with that compound. The switch only adds rows; direct rows come back unchanged, and a (gene, metabolite) pair already reached directly is not repeated. Family rows are a recall expansion: they say the gene's family moves the compound somewhere, not that this gene does. Most of their noise is eggNOG family calls on genes that are not transporters at all; a per-gene transporter call is not in the KG yet.
  - **Example.** MED4 phnD (PMM0673), the phosphonate-binding protein, has no system call: eggNOG places it in subfamily `tcdb:3.A.1.9` (PhnT, phosphonate uptake), and its DIAMOND call is a weak tier-3 hit on the ABC superfamily. `genes_by_metabolite(['kegg.compound:C00009'], organism='MED4')` (orthophosphate) returns no transport rows. The envelope field `tcdb_family_substrates_not_shown` reports `{genes: 4, metabolites: 1, rows: 4}` (phnC, phnD, phnE, PMM0717), and a warning says to pass `include_tcdb_family_substrates=True`. With it, phnD reaches orthophosphate, phosphonic acid, phosphite, phosphinate and Fe³⁺ through `tcdb:3.A.1.9`.
  - **No walk above a direct system.** A gene with a direct system under a family never walks that family: it already has its system's substrates, and the walk would add only its sibling systems' substrates. urtA (PMM0970) has direct urea systems `tcdb:3.A.1.4.4` / `3.A.1.4.5`; walking `tcdb:3.A.1.4` would add about two dozen amino acids and keto acids from sibling systems, so it does not.
  - **Curation caveat: Pst.** MED4 pstA/B/C/S have direct calls onto `tcdb:3.A.1.7.6`, which TCDB curates with **triphosphate only**. So the phosphate-specific Pst system does not answer an orthophosphate question, and because it is direct, no family walk replaces it. The system name in `tcdb_family_name` ("High affinity phosphate-specific transporter, PstABCS") still says phosphate. Read system names when a substrate answer looks too narrow.
- **`tcdb_calls`.** The call kinds (`diamond_best_hit`, `diamond_tier`, `eggnog`) on the gene's edges anywhere on the row's lineage (the node, its ancestors, its descendants). pstS reads `['diamond_best_hit', 'diamond_tier', 'eggnog']`: the best hit on the system plus tier-2 and eggNOG calls on its family `tcdb:3.A.1.7`. `diamond_best_hit` and `diamond_tier` come from one DIAMOND run, so only eggNOG plus a DIAMOND kind is independent agreement.
- **`tcdb_identity`.** The percent identity of the row's representative DIAMOND edge; null when the call is eggNOG-only. It is the ranking signal within the route. Rank, don't filter.
- **`tcdb_direction`.** `uptake`, `export` or `unknown`, read from the TCDB node (the system on direct rows, the attached family on family rows). It comes from TCDB, not from the gene, and is conservative: ABC uptake numbering (subfamilies `3.A.1.1`–`99` and their systems), otherwise a system's own TCDB name (secretion counts as export). Family and subfamily names never set a direction, and hedged, organelle or two-way names read `unknown`. So family rows read `unknown` outside the ABC uptake subfamilies, and most nodes read `unknown`.
- **Catch-all substrates.** TCDB curates some generic substrates ("Peptide", "Protein"). They pass through as curated, and on family rows they can be the most frequent compound. Treat them as "some substrate", not a finding. The same holds for ChEBI structural classes such as amino acid, peptide, lipid, fatty acid or nucleoside: read them as "a class of compounds", not one molecule. The row's `metabolite_structure_kind` says which (`generic` = a class). This applies equally to the `[tcdb_substrates]` clause of a `[tcdb_best_hit]` line in a gene's description. Protein (`kegg.compound:C00017`) is also how Sec, Tat and the secretion systems answer "what moves protein". Placeholders ("molecule", "ion", "cation", ...) and the coupling ions H+ and Na+ are not TCDB substrate targets.
- **Breadth cap.** The walk never starts from a node curated with more than 200 substrates. That removes exactly two superfamilies: ABC `tcdb:3.A.1` (546) and MFS `tcdb:2.A.1` (468). A gene whose only family call is one of these is listed in `tcdb_family_substrates_skipped` (`metabolites_by_gene` also warns; `genes_by_metabolite` reports the list only): its call is superfamily-level and its substrate is unknown. To see such a node's range anyway, use `ontology_term_details`.
- **Weak hits never reach substrates.** Edges stamped `tcdb_gate='below_gate'` (tier-3 calls, near-tie best hits, best hits under 40% identity) feed no transport row and start no walk. `gene_ontology_terms(..., include_weak_tcdb_hits=True)` shows them.

## What an empty answer means

1. The compound is not on the route for this organism: genuinely nothing in GO for these genes. Fall back to TCDB or KEGG rows.
2. The target was filtered by curation. H+ (`kegg.compound:C00080`), Na+ (`chebi:29101`) and upper-level classes (ion, monoatomic cation / anion, metal cation, ...) are coupling ions or placeholders, not substrates, and both routes drop them. The GO list is `Schema_info.go_transport_excluded_targets`; the TCDB list, `Schema_info.tcdb_substrate_excluded_targets`, is a superset (it adds molecule, cation, anion, organic anion, ...). `genes_by_metabolite` warns when you ask for one, naming the route(s) that drop it. An empty answer for these ids is curation, not biology: no route answers them, so Na+/H+ antiporters carry no metabolite rows.
3. A role id with no edges in the KG returns no rows and lands in `not_matched`.
4. Metabolite-level organism properties (`go_transport_organism_names` on `list_metabolites`) count direct gene annotations only; absence there is not absence of a GO edge.
5. **TCDB, family-only call.** The gene's TCDB call stops at a family or subfamily, so it has no direct rows. Read `tcdb_family_substrates_not_shown` and the warning, then re-run with `include_tcdb_family_substrates=True`.
6. **TCDB, superfamily-only call.** The gene's only usable call is ABC or MFS. It appears in `tcdb_family_substrates_skipped`: the substrate is unknown, not absent.
7. **TCDB, weak hits only.** The gene's TCDB edges are all `below_gate`. It has no transport rows and no `tcdb_assignment_count`; `gene_ontology_terms(..., include_weak_tcdb_hits=True)` shows the hits.

`go_namespace` and `go_evidence` narrow the GO arm only (direct and inherited rows alike): KEGG and TCDB rows are untouched, and the filtered result is always a subset of the unfiltered one. Set while `evidence_sources` excludes `go_transport`, they are ignored with a warning.

Scale, so you can judge a result: in MED4, 59 genes reach at least one GO transport target, 56 genes reach a substrate through a direct TCDB system, and 203 carry a gate-passing TCDB call (`tcdb_assignment_count > 0`).

## Reading agreement

The routes are not independent. GO terms often arrive through InterPro2GO or eggNOG, which share homology with the TCDB calls. Agreement between a `go_transport` and a `transport` row is therefore weaker evidence than it reads. Disagreement is mostly naming granularity (a GO class target vs a specific TCDB compound). Where only one route speaks, say which; where two agree, treat it as one line of homology evidence, not two confirmations. Only TCDB rows carry a direction (`tcdb_direction`), and it is node-level and TCDB-stated, not a per-gene measurement.

Read agreement from the envelope rather than by regrouping rows. `by_evidence_source_combination` (both tools) counts (gene, metabolite) pairs by the set of routes that name them, for example `{evidence_sources: ['go_transport', 'transport'], pair_count: 5}` for urea in MED4 (urtA–E). Per entity, `multi_source_gene_count` (on `genes_by_metabolite` `by_metabolite[]` and `metabolites_by_gene` `top_metabolites[]`) and `multi_source_metabolite_count` (on `genes_by_metabolite` `top_genes[]` and `metabolites_by_gene` `by_gene[]`) count what two or more routes reach. `transport` is one route whether its rows are direct or family: family rows join `by_evidence_source_combination` and the `multi_source_*` counts only when `include_tcdb_family_substrates=True`. A multi-source pair is corroborated, not proven, and a single-source pair is not wrong.

## Class reach: two ways to widen "which compound"

- **Walk GO is_a (term side).** `go_include_ancestors=True` on the tools, or in Cypher, as below. A term inherits from its ancestors' target.
- **Expand the compound class (target side).** Two separate mechanisms over the curated KEGG BRITE classes, both with partial coverage. `list_metabolites(kegg_brite_classes=...)` filters on the top-level class stored on each compound row. A Cypher walk (`run_cypher`) of `Metabolite_in_metabolite_class` plus the `MetaboliteClass` hierarchy reaches deeper subclasses (example in `docs://analysis/metabolites`). Either way, call `genes_by_metabolite` on the resulting compounds.

The two answer different questions; do not expect them to match.

## Cypher examples (read-only, via `run_cypher`)

```cypher
// Which genes carry a GO term defined as moving urea, with the gene->GO evidence?
MATCH (m:Metabolite {id: 'kegg.compound:C00086'})<-[t:Molecular_function_transports_metabolite|Biological_process_transports_metabolite]-(go)
MATCH (g:Gene)-[r:Gene_enables_molecular_function|Gene_involved_in_biological_process]->(go)
RETURN g.locus_tag, go.id, go.name, type(t) AS route, r.evidence, r.sources;

// Class reach, term side: walk GO is_a down from a class-level transporter term
MATCH (go:MolecularFunction)-[:Molecular_function_is_a_molecular_function*0..]->(p:MolecularFunction)
WHERE p.name = 'amino acid transmembrane transporter activity'
MATCH (go)-[:Molecular_function_transports_metabolite]->(m:Metabolite)
RETURN DISTINCT m.id, m.name;

// Which organisms carry the GO route for a metabolite
MATCH (m:Metabolite {id: 'chebi:24875'}) RETURN m.go_transport_organism_names;
```

The GO namespace comes from `type(t)` (the edge type), not from node labels: molecular-function nodes lack the `GeneOntology` label that biological-process nodes carry.

## Recipes

- **What moves X in organism Y?** `genes_by_metabolite(metabolite_ids=[X], organism=Y)`: read `by_evidence_source` and `by_evidence_source_combination`, then rank within each route by its own signal (TCDB by `tcdb_identity`, then `tcdb_calls`; GO MF before BP, `curated` first).
- **What does gene Z move?** `gene_overview(locus_tags=[Z])` for which routes exist (`evidence_sources`, `transported_metabolite_count`, `go_transport_metabolite_count`), then `metabolites_by_gene(locus_tags=[Z], organism=...)`.
- **No direct transporter for X?** Read `tcdb_family_substrates_not_shown`; if it is non-zero, re-run with `include_tcdb_family_substrates=True` and report the family rows as candidates, not calls.
- **A role question (siderophore, xenobiotic).** `genes_by_metabolite(metabolite_ids=['chebi.role:26672'], organism=...)`: GO and TCDB role rows come back together, labelled.
- **Which compounds does the GO route cover?** `list_metabolites(evidence_sources=['go_transport'], organism_names=[...])`.

See also: `docs://analysis/metabolites` (the three source pipelines and stereo forms), `docs://tools/genes_by_metabolite`, `docs://tools/metabolites_by_gene`.
