# Ontology reference index

One page per supported ontology — what it is, how genes get annotated, identifier form, hierarchy, the registry row (labels, edges, trust axes, bridges), node properties, controlled vocabularies, interpretation and pitfalls. Open `docs://ontologies/{key}` for the detail; `key` is the value you pass as `ontology=` to `search_ontology`, `genes_by_ontology`, `gene_ontology_terms`, `ontology_landscape` and the enrichment tools. `ontology_term_details` is cross-ontology and takes self-prefixed term IDs instead.

| key | Ontology | Node label | Shape | Trust axes | Bridges out | Summary |
|---|---|---|---|---|---|---|
| `go_bp` | GO biological process | `BiologicalProcess` | hierarchical | sources, evidence, evidence_score | — | Gene Ontology *biological process* — the "what larger program is this gene part of" branch of GO… |
| `go_mf` | GO molecular function | `MolecularFunction` | hierarchical | sources, evidence, evidence_score | — | Gene Ontology *molecular function* — the biochemical activity a gene product performs… |
| `go_cc` | GO cellular component | `CellularComponent` | hierarchical | sources, evidence, evidence_score | — | Gene Ontology *cellular component* — where a gene product is found… |
| `ec` | EC numbers | `EcNumber` | hierarchical | sources, evidence, evidence_score | — | Enzyme Commission numbers — the four-field nomenclature of enzyme *reactions*… |
| `kegg` | KEGG (categories, pathways, KOs) | `KeggTerm` | hierarchical | sources, evidence | brite (membership) | KEGG orthology and pathway maps — the most common "which pathway is this gene in" vocabulary. |
| `cog_category` | COG functional categories | `CogFunctionalCategory` | flat | sources, evidence | — | COG functional categories — the 26 single-letter classes of the Clusters of Orthologous Groups system… |
| `cyanorak_role` | Cyanorak roles | `CyanorakRole` | hierarchical | sources, evidence | — | Cyanorak functional roles — the curated, cyanobacteria-specific role hierarchy of the Cyanorak information… |
| `tigr_role` | TIGR roles | `TigrRole` | hierarchical | sources, evidence | — | TIGR (JCVI) functional roles — the classic "main role / sub role" scheme from TIGR genome annotation… |
| `pfam` | Pfam domains and clans | `Pfam` | hierarchical | sources, evidence, evidence_score | interpro (membership) | Pfam protein domain families and clans. |
| `brite` | KEGG BRITE hierarchies | `BriteCategory` | hierarchical, facet `tree` | sources, evidence | — | KEGG BRITE functional hierarchies — twelve curated trees that classify KEGG Orthology groups by protein… |
| `tcdb` | TCDB transporter families | `TcdbFamily` | hierarchical | sources, evidence, evidence_score, tier | pfam (composition), go_bp (composition), go_mf (composition), go_cc (composition) | The Transporter Classification Database — a five-level classification of membrane transport systems… |
| `cazy` | CAZy families | `CazyFamily` | hierarchical | sources, evidence, evidence_score | — | CAZy — Carbohydrate-Active enZymes: sequence-based families of the enzymes that build, break and modify… |
| `subcellular_localization` | PSORTb subcellular localization | `SubcellularLocalization` | flat | — | — | PSORTb predicted subcellular localization — a *structural* ontology of five compartments for Gram-negative… |
| `signal_peptide_type` | SignalP signal-peptide type | `SignalPeptideType` | flat | — | — | SignalP predicted signal-peptide type — a *structural* ontology of five N-terminal signal classes… |
| `interpro` | InterPro entries | `InterproEntry` | hierarchical, facet `interpro_type` | sources, evidence | ec (router), cazy (router) | InterPro — the integrated protein-signature database that unifies Pfam, TIGRFAMs/NCBIfam, PANTHER, SMART… |
| `ncbifam` | NCBIfam families | `NcbifamFamily` | flat | sources, evidence | interpro (membership), tigr_role (router) | NCBIfam — NCBI's curated protein-family HMM collection, which absorbed and continues TIGRFAMs. |
| `merops` | MEROPS peptidase families | `MeropsFamily` | hierarchical | sources, evidence, evidence_score, tier | pfam (composition) | MEROPS — the peptidase (protease) and peptidase-inhibitor database. |

Cross-cutting semantics live in `docs://analysis/annotation_evidence` (trust ladder, rank-vs-filter, bridges) and `docs://guide/conventions` (`level` convention, browse vs search, lockstep paging, strip rule).
