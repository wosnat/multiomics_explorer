# Transport: three routes, read side by side

What transports compound X in organism Y, or what does gene Z move? The KG answers from three routes. They are kept apart on every row (`evidence_source`), never blended into one count. This page says what each route is, where it is biased, how to read agreement, and what an empty answer means.

## The routes

| `evidence_source` | Path | What a row says | Bias to know |
|---|---|---|---|
| `metabolism` | `Gene → Reaction → Metabolite` (KEGG) | The gene's enzyme takes part in a reaction involving the compound. Not transport. | Undirected reactions; KO inference may be putative. |
| `transport` | `Gene → TcdbFamily → Metabolite / ChemicalRole` (TCDB) | The gene's TCDB family lists the compound (or a role class) as a substrate. `substrate_depth` and `tcdb_evidence_score` qualify it. | Superfamily-only genes (`transport_substrate_resolution='family_inferred'`) show reachability, not capability. |
| `go_transport` | `Gene → GO term → Metabolite / ChemicalRole` (GO) | GO defines the gene's term as moving the compound. A term definition, not a gene fact; the gene→GO edge says how the gene came to carry it (`go_evidence`: `curated`, `family_inferred`, `domain_inferred`; `go_sources`). | Molecular-function and biological-process terms mean different things; curated target filter; coarse class targets. |

Use `genes_by_metabolite` (compound → genes) and `metabolites_by_gene` (genes → compounds). With `evidence_sources=None` all three routes run; scope with `evidence_sources=['go_transport']`.

## Reading a GO row

- **MF vs BP.** `go_namespace='molecular_function'` terms are transporter activities ("urea transmembrane transporter activity"). `'biological_process'` terms are broader: they also cover storage, regulation and accessory subunits. A gene carrying "iron ion transport" is not necessarily a transporter (MED4 `ftn`, ferritin, reaches iron this way). Prefer MF rows for "is this gene a transporter"; BP rows add genes linked to the process. Most GO-route genes reach a substrate through both. `go_namespace=['molecular_function']` keeps only the MF rows.
- **Row grain.** One row per gene × own GO term × target. A gene with an MF and a BP term for the same compound gives two rows; count genes with `gene_count_total`, not rows.
- **Evidence.** `go_evidence` is a class label (`curated`, `family_inferred`, `domain_inferred`), not a numeric score, and this route has no score to threshold. Rank rows by it (`curated` first). `go_evidence=['curated']` keeps only curated rows when you want the strict set; the allowed values come from `list_filter_values`.
- **Direct vs inherited.** Default rows are direct: the gene's own term names the target (`go_term_depth=0`). `go_include_ancestors=True` adds rows where an is_a ancestor of the gene's term names the target: `go_term_depth` counts hops, `go_axiom_term_id` / `go_axiom_term_name` name the ancestor, and a (gene, target) already reached directly is not repeated. Inherited rows widen to broader targets and are a recall expansion. `rows_by_go_term_depth` in the envelope shows the split, and appears only when the GO arm is active.
- **Targets that are classes.** A `target_kind='chemical_role'` row names a role (siderophore, xenobiotic, drug, toxin, vitamin, neurotransmitter), not a compound; roles are not propagated to the compounds they cover. The role id is a valid input to both tools and also reaches TCDB role edges. The neurotransmitter role is eukaryote-centred: in bacteria the matching terms are mostly amino-acid transporters (a warning says so). Class-valued metabolite targets (Lipid, carbohydrate, peptide) are real `Metabolite` nodes with no formula.

## What an empty answer means

1. The compound is not on the route for this organism: genuinely nothing in GO for these genes. Fall back to TCDB or KEGG rows.
2. The target was filtered by curation. H+ (`kegg.compound:C00080`), Na+ (`kegg.compound:C01330`) and upper-level classes (ion, monoatomic cation / anion, metal cation, chemical entity, protein, ...) were removed from the GO route because they are coupling ions or transporter-ness, not substrates. The list is `Schema_info.go_transport_excluded_targets` (read it from `kg_release_info`); a warning fires when you ask for one. An empty GO answer for these is curation, not biology; TCDB answers them.
3. A role id with no edges in the KG returns no rows and lands in `not_matched`.
4. Metabolite-level organism properties (`go_transport_organism_names` on `list_metabolites`) count direct gene annotations only; absence there is not absence of a GO edge.

`go_namespace` and `go_evidence` narrow the GO arm only (direct and inherited rows alike): KEGG and TCDB rows are untouched, and the filtered result is always a subset of the unfiltered one. Set while `evidence_sources` excludes `go_transport`, they are ignored with a warning.

Scale, so you can judge a result: in MED4 59 genes reach at least one GO transport target (a small set next to the TCDB route).

## Reading agreement

The routes are not independent. GO terms often arrive through InterPro2GO or eggNOG, which share homology with the TCDB calls. Agreement between a `go_transport` and a `transport` row is therefore weaker evidence than it reads. Disagreement is mostly naming granularity (a GO class target vs a specific TCDB compound). Where only one route speaks, say which; where two agree, treat it as one line of homology evidence, not two confirmations. None of the routes gives transport direction.

Read agreement from the envelope rather than by regrouping rows. `by_evidence_source_combination` (both tools) counts (gene, metabolite) pairs by the set of routes that name them, for example `{evidence_sources: ['go_transport', 'transport'], pair_count: 5}` for urea in MED4 (urtA–E). Per entity, `multi_source_gene_count` (on `genes_by_metabolite` `by_metabolite[]` and `metabolites_by_gene` `top_metabolites[]`) and `multi_source_metabolite_count` (on `genes_by_metabolite` `top_genes[]` and `metabolites_by_gene` `by_gene[]`) count what two or more routes reach. `transport` is one route whatever its `substrate_depth`, so a superfamily-only TCDB row still counts; add `substrate_depth=['most_specific']` for the strict core. A multi-source pair is corroborated, not proven, and a single-source pair is not wrong.

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

- **What moves X in organism Y?** `genes_by_metabolite(metabolite_ids=[X], organism=Y)`: read `by_evidence_source` and `by_evidence_source_combination`, then rank within each route by its own signal (TCDB `tcdb_evidence_score`; GO MF before BP, `curated` first).
- **What does gene Z move?** `gene_overview(locus_tags=[Z])` for which routes exist (`evidence_sources`, `transported_metabolite_count`, `go_transport_metabolite_count`), then `metabolites_by_gene(locus_tags=[Z], organism=...)`.
- **A role question (siderophore, xenobiotic).** `genes_by_metabolite(metabolite_ids=['chebi.role:26672'], organism=...)`: GO and TCDB role rows come back together, labelled.
- **Which compounds does the GO route cover?** `list_metabolites(evidence_sources=['go_transport'], organism_names=[...])`.

See also: `docs://analysis/metabolites` (the three source pipelines and stereo forms), `docs://tools/genes_by_metabolite`, `docs://tools/metabolites_by_gene`.
