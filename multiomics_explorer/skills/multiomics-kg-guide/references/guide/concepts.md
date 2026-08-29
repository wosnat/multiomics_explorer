# KG concepts — what each node and edge means

The knowledge graph integrates Prochlorococcus and Alteromonas multi-omics
data: genomes, transcriptomes, proteomes, metabolomes, ortholog groups,
ontologies, and curated reaction / transport chemistry. This page is a
short orientation to the entities you will see in tool outputs and a map
of how they connect. For a tool-by-tool index see `docs://guide/start_here`.

For the live, full schema with property lists, call `kg_schema` —
that's the source of truth. This doc explains *meaning*; the schema
explains *structure*. Node counts are deliberately not quoted here —
see "Cardinalities" at the end for where to read them live.

---

## Four evidence layers

Gene- and metabolite-level evidence in the KG sits in one of four
layers, each with a distinct shape:

| Layer | Node | Edges to Gene | What it represents | Discovery tool |
|---|---|---|---|---|
| **Differential expression** | `Experiment` | `Changes_expression_of` (carries `log2_fold_change`, `p_value`, `expression_direction`, timepoint) | Per-experiment-and-timepoint DE results from RNAseq / microarray / proteomics | `list_experiments` |
| **DerivedMetric** | `DerivedMetric` | `Derived_metric_quantifies_gene` (numeric), `Derived_metric_flags_gene` (boolean), `Derived_metric_classifies_gene` (categorical) | Column-level evidence: rhythmicity flags, diel amplitudes, darkness-survival classes — anything that's not a per-experiment DE column | `list_derived_metrics` |
| **MetaboliteAssay** | `MetaboliteAssay` | (none — anchored on Metabolite, not Gene) | Mass-spec metabolite measurements: `Assay_quantifies_metabolite` (numeric) and `Assay_flags_metabolite` (boolean) | `list_metabolite_assays` |
| **Co-expression clustering** | `ClusteringAnalysis` / `GeneCluster` | `Gene_in_gene_cluster` (membership) | Published co-regulation modules — gene groupings inferred from expression data, with cluster-level metadata (treatment, omics_type, growth phase) | `list_clustering_analyses` |

The first three are direct measurements; clustering is derived
evidence (inferred from expression measurements upstream). The four do
not interchange:
- DE measures per-condition response.
- DM captures column-level traits beyond DE (rhythmicity, amplitude, class labels).
- MetaboliteAssay measures compounds, not genes — anchored on `Metabolite`.
- Clustering captures co-regulation patterns — anchored on `Gene` via membership.

A "tested-absent" row in metabolomics (`Assay_flags_metabolite` with
`flag_value=False`, or `Assay_quantifies_metabolite` with
`detection_status='not_detected'`) encodes real biology — the
metabolite was looked for and not detected. `docs://guide/conventions`
explains tested-absent semantics across the whole surface.

### Cross-cutting axes

Two orthogonal dimensions cut across the layers above. Both are
properties of the parent node (Experiment / DerivedMetric /
MetaboliteAssay), not the gene — so the same gene can carry evidence
from multiple modalities and compartments simultaneously.

**Omics modality.** `Experiment.omics_type` names the measurement
technology — `RNASEQ`, `MICROARRAY`, `PROTEOMICS`, `METABOLOMICS`, plus
compartment-specific and paired variants (`VESICLE_PROTEOMICS`,
`EXOPROTEOMICS`, `PAIRED_RNASEQ_PROTEOME`, ...). Read the live set with
`list_filter_values(filter_type='omics_type')`.

- A gene with RNAseq DE in one experiment and proteomics DE in another
  surfaces as two distinct rows in `differential_expression_by_gene`,
  discriminated by the parent experiment's `omics_type`.
- DerivedMetrics also carry `omics_type` — e.g. a vesicle-proteomics
  boolean DM (`omics_type='PROTEOMICS'`) is gene-anchored proteomics
  evidence.
- Metabolomics (`omics_type='METABOLOMICS'`) is the MetaboliteAssay
  layer — anchored on Metabolite, not Gene.

**Compartment.** Where in the cell the measurement was sampled.
Carried on `Experiment.compartment` (proteomics + metabolomics),
`DerivedMetric.compartment`, and `MetaboliteAssay.compartment`.
The vocabulary declares four values (`whole_cell`, `vesicle`,
`exoproteome`, `extracellular`) — `list_filter_values('compartment')`
returns the declared set with per-value counts, so read it before
filtering. RNAseq experiments are uniformly `whole_cell` (no
fractionation). The same gene may have proteomics DE in `whole_cell`
and `vesicle` simultaneously — distinct rows. Filter via
`compartment=...` on `list_experiments`, `list_derived_metrics`,
`list_metabolite_assays`, and `list_organisms`.

---

## Backbone node types

### Organisms and genes

- **`OrganismTaxon`** — strain-level organism with full taxonomy
  hierarchy. `preferred_name` is the canonical identifier (e.g.
  `"Prochlorococcus MED4"`) and equals `Gene.organism_name`; every
  organism parameter resolves by case-insensitive word match on it and
  on `name_synonyms` (rules in `docs://guide/conventions` "Organism
  naming"). Not every node has genes — genus-level, phage and
  treatment-only taxa exist for experiment metadata and never resolve
  as an `organism=` value.
- **`Gene`** (~127k nodes across all organisms) — anchored by
  `locus_tag` and `organism_name`. Carries pre-computed routing
  rollups: `expression_edge_count`, `numeric_metric_count` /
  `boolean_metric_count` / `categorical_metric_count`,
  `cluster_membership_count`, `closest_ortholog_group_size`,
  `reaction_count`, `catalyzed_metabolite_count`, `tcdb_family_count`,
  `cazy_family_count`, `ncbifam_family_count`,
  `discussed_in_publication_count`, `compartments_observed`,
  `annotation_quality` (0..3 — see `docs://guide/conventions`). Each
  Gene also carries an amino-acid `sequence` and genomic coordinates
  (`contig`, `start`, `end`, `strand`) — all co-populated; null only on
  the ~3% of expression-only genes with no genome match. Exposed by
  `gene_aa_sequence` (sequences) and `gene_neighbors` (coordinates →
  positional neighborhood).
- **`Protein`** / **`Polypeptide`** — each Gene has at most one
  Protein (`Gene_encodes_protein`). Few tools surface Protein directly;
  it is mostly a backbone node.
- **`OrthologGroup`** / **`GroupingClass`** — ortholog group memberships
  (`Gene_in_ortholog_group`). Multiple ortholog sources coexist, distinguished
  by `source` and `taxonomic_level`.

### Experiments and publications

- **`Publication`** — paper-level metadata (authors, DOI,
  abstract). Connected to experiments via `Has_experiment`. Two
  additional edge types index what each paper **names in prose** — a
  recall-biased narrative literature index, distinct from the
  supplementary DE-table expression data:
  - `Publication_discusses_gene` (→ Gene) — genes the paper names in
    text (regulators, model genes).
  - `Publication_discusses_kegg_pathway` (→ KeggTerm, pathway-level) —
    KEGG pathways the paper names.

  Both edges carry `prominence` (`central` | `peripheral`) and an
  extraction `evidence` quote. This is a **router, not exhaustive
  coverage** — on the order of a thousand distinct genes are named
  across the whole corpus (under 1% of all genes), and a handful of
  publications have no discusses edges at all. Precomputed counts live
  on the nodes (`Publication.discussed_gene_count` /
  `.discussed_pathway_count`, `Gene.discussed_in_publication_count`).
  Forward lookup: `discussed_by_publication` (paper → named genes +
  pathways). Reverse signals are folded inline — `gene_overview` carries
  per-gene `discussed_in_publication_count` + (verbose) the discussing
  DOIs, and `search_ontology` carries per-KEGG-term
  `discussed_by_n_publications`.
- **`Experiment`** — one experimental contrast. Carries
  `treatment_type` (list[str], never empty — read values from
  `list_filter_values`), `background_factors` (list[str]), `omics_type`,
  `compartment`, `is_time_course`, `table_scope` (which gene universe
  the DE table reports — `all_detected_genes`, `significant_only`,
  `significant_any_timepoint`, `filtered_subset`, `top_n`; absent on
  experiments with no DE table), and `coculture_partner` when
  applicable.
- **`ClusteringAnalysis`** — a published co-expression clustering.
  Owns `GeneCluster` children (`ClusteringAnalysisHasGeneCluster`);
  `cluster_type` is a closed vocabulary (`list_filter_values('cluster_type')`).
- **`GeneCluster`** — a single co-expression module. Genes belong via
  `Gene_in_gene_cluster`.
- **`DerivedMetric`** — one column of derived per-gene evidence from a
  publication (e.g. a rhythmicity flag, a light/dark amplitude).
  Polymorphic by `value_kind` ∈ {`numeric`, `boolean`, `categorical`}.
- **`MetaboliteAssay`** — one column of mass-spec metabolite
  measurements. Polymorphic by `value_kind`. Connected to Metabolite via
  `Assay_quantifies_metabolite` (numeric, with `detection_status`) or
  `Assay_flags_metabolite` (boolean).

### Chemistry layer

- **`Metabolite`** — chemical compound, anchored by prefixed ID
  (`kegg.compound:Cxxxxx` for KEGG-derived; `chebi:NNN` for TCDB-only
  substrates; a few `mnx:MNXM…` MetaNetX-only compounds). Carries
  cross-refs (`chebi_id`, `hmdb_id`, `mnxm_id`), `formula`, `elements`
  (presence list, never substring), `mass`, and a precomputed
  `evidence_sources` list — subset of {`metabolism`, `transport`,
  `metabolomics`} indicating which pipelines reach this compound. The
  first-class chemistry node: query directly with `list_metabolites`,
  drill in via `genes_by_metabolite` / `metabolites_by_gene`. Every
  `metabolite_ids` parameter also accepts bare / xref forms (`C00064`,
  `CHEBI:17234`, `HMDB…`, `MNXM…`) — see `docs://guide/conventions`
  "Metabolite ID forms".

  KEGG `Reaction` nodes sit *between* Gene and Metabolite on the
  metabolism arm — `Gene → Reaction → Metabolite` — but are
  **not directly queryable**: there's no `list_reactions` or
  `reaction_details` tool. Reactions surface as fields on chemistry
  rows (`reaction_id`, `reaction_name`, `ec_numbers`) and as the
  `top_reactions` envelope rollup on `genes_by_metabolite` /
  `metabolites_by_gene`. They are stored undirected — KEGG equation
  order is unreliable upstream, so the KG does not encode substrate
  vs product.
- **`TcdbFamily`** — TCDB transporter family hierarchy (class →
  subclass → family → subfamily). Genes connect via
  `Gene_has_tcdb_family`; substrates via
  `Tcdb_family_transports_metabolite`. Substrates attach to family
  nodes and are inherited **down** the hierarchy, so genes annotated to
  broad families still surface candidate substrates. Each substrate edge
  carries `substrate_depth`: `most_specific` (the most specific
  surviving node for that substrate in the gene-pruned hierarchy — not a
  curation level) or `inherited`. Each gene × family edge carries a
  composite `evidence_score` on `[0, 1]`; genes carry
  `tcdb_evidence_score_max`, `transported_metabolite_count` and
  `transport_substrate_resolution` (`resolved` / `family_inferred`),
  all computed over the gene's deepest attachments only. Inherited rows
  dominate by volume — see the trust ladder in
  `docs://analysis/metabolites`.

### Ontology nodes (17 ontologies)

All ontology nodes share a `level: int` property
(0 = root / broadest, higher = more specific) and most carry
`level_kind` and a sparse `level_is_best_effort` flag for DAG-shaped
ontologies. Flat ontologies are `level=0` only. The `key` column is the
`ontology=` value and the `docs://ontologies/{key}` page name.

| Ontology | `key` | Node label | Shape / notes |
|---|---|---|---|
| Gene Ontology — biological process | `go_bp` | `BiologicalProcess` | DAG — `level` is min-path-from-root, `level_is_best_effort` flags ambiguous depth |
| Gene Ontology — molecular function | `go_mf` | `MolecularFunction` | DAG, as above |
| Gene Ontology — cellular component | `go_cc` | `CellularComponent` | DAG, as above |
| KEGG | `kegg` | `KeggTerm` | Tree-ish; `level_kind` ∈ {`category`, `subcategory`, `pathway`, `ko`}. KO IDs are `kegg.orthology:K…`, pathways `kegg.pathway:ko…`. Bridges to BRITE (membership). |
| EC numbers | `ec` | `EcNumber` | Tree (4-level enzyme nomenclature) |
| COG functional categories | `cog_category` | `CogFunctionalCategory` | **Flat**, single-letter codes |
| Cyanorak roles | `cyanorak_role` | `CyanorakRole` | Tree (Prochlorococcus/Synechococcus-specific) |
| TIGR roles | `tigr_role` | `TigrRole` | Two levels: main role (`level=0`) → sub-role (`level=1`). Reached both by direct gene edges and through the NCBIfam router bridge. |
| Pfam | `pfam` | `Pfam`, `PfamClan` | Domains roll up into clans; bridges to InterPro (membership) |
| BRITE | `brite` | `BriteCategory` | Multi-tree — **always scope with `tree=`** |
| TCDB | `tcdb` | `TcdbFamily` | Transporter classification (also doubles as a chemistry node — see above). Bridges to Pfam and GO (composition). |
| CAZy | `cazy` | `CazyFamily` | Carbohydrate-active enzymes; class → family |
| PSORTb subcellular localization | `subcellular_localization` | `SubcellularLocalization` | Flat, 5 nodes (Cytoplasmic, CytoplasmicMembrane, OuterMembrane, Periplasmic, Extracellular). Scored edge: `localization_score: float` ∈[7.5, 10.0] (verbose). 1:1 (≤1 edge per gene). **Structural** — where the protein lives, not what it does. |
| SignalP signal-peptide type | `signal_peptide_type` | `SignalPeptideType` | Flat, 5 nodes (SP, LIPO, TAT, TATLIPO, PILIN). Scored edge: `probability: float` ∈[0, 1], plus optional `cleavage_site: int` / `cleavage_probability: float` (verbose). 1:1. **Structural** — how the protein is handled at the membrane. |
| InterPro | `interpro` | `InterproEntry` | Hierarchical (`Interpro_entry_is_a_interpro_entry`); each term carries `interpro_type` — one of `FAMILY`, `DOMAIN`, `HOMOLOGOUS_SUPERFAMILY`, `REPEAT`, `CONSERVED_SITE`, `ACTIVE_SITE`, `BINDING_SITE`, `PTM`. Forward-only router bridges to EC and CAZy (recall-biased, not a functional call). |
| NCBIfam | `ncbifam` | `NcbifamFamily` | Flat. Term-side `family_type` and `gene_symbol`. Bridges to InterPro (membership) and to TIGR roles (router — an NCBIfam family names the TIGR role it was curated under; never a gene-function call). |
| MEROPS | `merops` | `MeropsFamily` | Hierarchical (`Merops_family_is_a_merops_family`); families roll up into clans. Edge-level `call_class` (`peptidase` / `inhibitor` / `nonpeptidase_homolog`) distinguishes an active peptidase call, a peptidase-inhibitor family, and a catalytically-dead homolog. Bridges to Pfam (composition). |

Each ontology has its own reference page at `docs://ontologies/{key}` —
what it is, how genes get annotated, identifier form, hierarchy, the
registry row (labels, edges, trust axes, bridges), node properties,
interpretation and pitfalls. The index is `docs://ontologies/index`.
Term-side tools: `search_ontology` (browse or search terms, one or many
ontologies) and `ontology_term_details` (batch term IDs → parents,
children, bridges, counts). **Bridges** are forward-only term→term
links of three kinds: `composition` (a TCDB or MEROPS family is built
from these Pfam / GO terms), `membership` (a Pfam or NCBIfam entry
belongs to this InterPro entry; a KO sits in this BRITE category), and
`router` (InterPro → EC / CAZy, NCBIfam → TIGR role — recall-biased
pointers, never gene-function calls). Walk them with
`ontology_term_details(term_ids=[...])`, read `links_out[].link_kind`.

Fifteen of the seventeen carry a gene-edge **annotation-trust surface** —
`sources[]`, an `evidence` ladder (`curated > signature > homology >
family_inferred > domain_inferred`), and (on a subset) `evidence_score` /
`tier` — plus ontology-specific native detail (TCDB's `confidence_score` /
`attachment_depth`, MEROPS's `call_class`, InterPro's `libraries`, and so
on). PSORTb and SignalP carry no trust axes (their `localization_score` /
`signal_peptide_probability` are native detail only, verbose). See
`docs://analysis/annotation_evidence` for the per-ontology trust profile and
`docs://guide/conventions` for the compact/verbose placement rule.

Two reverse-mode ontology tools — `genes_by_ontology` (term → genes) and
`gene_ontology_terms` (genes → terms) — operate on all 17 uniformly
(with hierarchy expansion where applicable; COG / `subcellular_localization` (PSORTb) / `signal_peptide_type` (SignalP) /
NCBIfam are flat so there's nothing to expand). For methodology see
`docs://analysis/enrichment`.

PSORTb and SignalP are deliberately **NOT** folded into
`Gene.annotation_types` / `informative_annotation_types` /
`annotation_quality` — localization and signal-peptide presence describe
*how/where* a gene's product lives, not *what it does*, so folding would
skew `genes_by_function` `min_quality` reasoning. Routing strings
`Gene.subcellular_localization` and `Gene.signal_peptide_type` surface
the call directly via `gene_details` for 1:1 lookup without an ontology
tool call.

### Anchors that aren't measurement

- **`DataSource`** — metadata about ingestion pipelines. Rarely surfaced
  through tools.
- **`Schema_info`** (1 node) — release identity: version, `built_at`,
  counts, `controlled_vocabularies_hash`. Read via `kg_release_info`.
- **`ControlledVocabulary`** — one node per closed value set the tools
  filter on (treatment types, compartments, trust rungs, ...). Read via
  `list_filter_values`.

The base `BiologicalEntity` / `Entity` / `NamedThing` / `OrganismalEntity`
labels are Biolink-style supertype labels — they aggregate every gene
or every named entity and are not used by tools directly.

---

## How the layers connect — a mental map

```
                    OrganismTaxon
                          |
                          | Gene_belongs_to_organism
                          |
                          v
                        Gene  ────────────────────────────────────────────────
                          |  ^                                                  \
                          |  |                                                   \
        Gene_encodes_protein  Gene_in_ortholog_group → OrthologGroup              \
                          |                                                        \
                          v                                                         \
                        Protein                                                      \
                                                                                      \
   Experiment ───[Changes_expression_of]──────────────────► Gene                       \
                                                                                        \
   DerivedMetric ─[Derived_metric_{quantifies,flags,classifies}_gene]─► Gene             \
                                                                                          \
   ClusteringAnalysis ─owns─► GeneCluster ─[Gene_in_gene_cluster]──► Gene                  \
                                                                                            \
   Publication ─[Publication_discusses_gene]──► Gene                                         \
   Publication ─[Publication_discusses_kegg_pathway]──► KeggTerm (pathway)                    v
                                                                                             |
   Gene ──[Gene_catalyzes_reaction]──► Reaction ──[Reaction_has_metabolite]──► Metabolite ◄──┘
                                                                                  ^
                                                                                  |
   Gene ──[Gene_has_tcdb_family]──► TcdbFamily ──[Tcdb_family_transports_metabolite]
                                                                                  
   MetaboliteAssay ─[Assay_{quantifies,flags}_metabolite]─► Metabolite

   Gene ──[Gene_has_{pfam,cazy_family,kegg_ko,cyanorak_role,tigr_role}]──► <ontology term>
   Gene ──[Gene_in_cog_category]──► CogFunctionalCategory
   Gene ──[Gene_involved_in_biological_process]──► BiologicalProcess (GO BP)
   Gene ──[Gene_enables_molecular_function]──► MolecularFunction (GO MF)
   Gene ──[Gene_located_in_cellular_component]──► CellularComponent (GO CC)
   Gene ──[Gene_catalyzes_ec_number]──► EcNumber
   Gene ──[Gene_has_interpro_entry]──► InterproEntry ──[router]──► EcNumber / CazyFamily
   Gene ──[Gene_has_ncbifam_family]──► NcbifamFamily ──[membership]──► InterproEntry
                                                    ──[router]──► TigrRole
   Gene ──[Gene_has_merops_family]──► MeropsFamily ──[composition]──► Pfam
   Gene ──[Gene_has_subcellular_localization {score}]──► SubcellularLocalization (PSORTb)
   Gene ──[Gene_has_signal_peptide_type {probability, cleavage_site}]──► SignalPeptideType (SignalP)
```

The Gene node is the central hub. Almost every tool either finds genes
(by some criterion) or gets data about given genes. Metabolites form a
secondary hub for the chemistry layer; ontology terms form a third hub
for functional classification, cross-linked by the bridge edges.

---

## Three metabolite source pipelines

The same Metabolite node may carry evidence from up to three
independent pipelines, indicated by `Metabolite.evidence_sources`:

1. **`metabolism`** — `Gene → Reaction → Metabolite` from KEGG. Catalysis
   evidence; direction-agnostic (KEGG equation order is unreliable, so
   we do not encode produced vs consumed).
2. **`transport`** — `Gene → TcdbFamily → Metabolite` from TCDB. Transport
   substrate evidence; `substrate_depth` (`most_specific` / `inherited`)
   and `tcdb_evidence_score` qualify each transport row.
3. **`metabolomics`** — `MetaboliteAssay → Metabolite`. Mass-spec
   measurement evidence; *no gene anchor* — the measurement is on the
   compound, not the gene.

Because these pipelines are independent, `genes_by_metabolite`,
`metabolites_by_gene`, and `list_metabolites` carry an `evidence_source`
discriminator on each row (or in filters / rollups), and the
`metabolomics` arm has its own dedicated tool family. See
`docs://analysis/metabolites` for the full decision tree.

---

## Cardinalities

Exact counts are intentionally **not** listed on this page — they change
with every KG rebuild and a table reads as ground truth. The few orders
of magnitude above (~127k genes, ~3% coordinate-less) are there only to
set scale. To get current cardinalities, call the tools that compute
them live:

- **`kg_release_info`** — headline gene / experiment / paper / organism
  counts plus the release identity (version, built_at).
- **`list_organisms`** — per-organism gene / publication / experiment counts.
- **`kg_schema`** — node-label and relationship-type inventory.
- **`ontology_landscape`** / **`search_ontology`** (browse mode) —
  per-ontology term counts and level distributions.
- **Per-tool envelope rollups** (`by_organism`, `total_matching`, `top_*`)
  — counts scoped to whatever you just queried.

---

## What's NOT in the KG

To save you from asking:

- **Protein-protein interactions** — no PPI edges. Co-expression clusters
  approximate functional grouping but are not interaction data.
- **Genome variants / SNPs** — only the reference genome per strain.
- **Transcript isoforms** — bacterial transcriptomes are gene-level here.
- **Non-coding genes** — `Gene` nodes are protein-coding only. tRNAs,
  rRNAs, miRNAs, sRNAs, and other ncRNAs are not represented.
- **Three-dimensional structure** — neither protein structure nor
  membrane topology beyond `transmembrane_regions` count.
- **Reaction direction / reversibility** — KEGG-upstream limitation.
  Use DE direction to disambiguate produced vs consumed when needed.
- **Per-cell, per-condition metabolite concentrations beyond what is
  stored as MetaboliteAssay edges** — only the curated assays listed by
  `list_metabolite_assays`.
- **Full paper text.** `Publication` nodes carry metadata (title,
  authors, DOI, journal, year) and an abstract — but **not** the full
  body, figures, or supplementary materials. For the actual paper,
  follow the DOI link to the publisher. Note: prose *mentions* of genes
  and KEGG pathways ARE indexed best-effort via the
  `Publication_discusses_gene` / `Publication_discusses_kegg_pathway`
  edges (see "Experiments and publications" above) — so you can ask
  "what does this paper discuss?" even though the full text is not
  stored. That index is recall-biased, not a substitute for reading the
  paper.

For raw counts and property lists, call `kg_schema`.
