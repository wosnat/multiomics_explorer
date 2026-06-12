# KG concepts — what each node and edge means

The knowledge graph integrates Prochlorococcus and Alteromonas multi-omics
data: genomes, transcriptomes, proteomes, metabolomes, ortholog groups,
ontologies, and curated reaction / transport chemistry. This page is a
short orientation to the entities you will see in tool outputs and a map
of how they connect. For a tool-by-tool index see `docs://guide/start_here`.

For the live, full schema with property lists, call `kg_schema` —
that's the source of truth. This doc explains *meaning*; the schema
explains *structure*.

> **Node/edge counts in this doc are an illustrative snapshot and lag the
> live KG** — the graph is rebuilt periodically and every count grows. Use
> them for rough orientation only; for current figures call
> `kg_release_info` (headline gene / experiment / paper / organism counts),
> `list_organisms`, or `kg_schema`. Never quote a count from this page as
> ground truth.

---

## Four evidence layers

Gene- and metabolite-level evidence in the KG sits in one of four
layers, each with a distinct shape:

| Layer | Node | Edges to Gene | What it represents | Discovery tool |
|---|---|---|---|---|
| **Differential expression** | `Experiment` | `Changes_expression_of` (carries `log2_fold_change`, `p_value`, `expression_direction`, timepoint) | Per-experiment-and-timepoint DE results from RNAseq / proteomics | `list_experiments` |
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

**Omics modality.** Gene-anchored evidence comes from transcriptomics
or proteomics:

- `Experiment.omics_type` ∈ {`RNASEQ`, `PROTEOMICS`, `METABOLOMICS`, ...}
- A gene with RNAseq DE in one experiment and proteomics DE in another
  surfaces as two distinct rows in `differential_expression_by_gene`,
  discriminated by the parent experiment's `omics_type`.
- DerivedMetrics also carry `omics_type` — e.g. a vesicle-proteomics
  boolean DM (`omics_type='PROTEOMICS'`) is gene-anchored proteomics
  evidence.
- Metabolomics (`omics_type='METABOLOMICS'`) is the MetaboliteAssay
  layer — anchored on Metabolite, not Gene.

**Compartment.** Where in the cell the measurement was sampled:
`whole_cell`, `extracellular`, `vesicle`, `exoproteome`, `spent_medium`,
`lysate`. Carried on `Experiment.compartment` (proteomics +
metabolomics), `DerivedMetric.compartment`, and `MetaboliteAssay.compartment`.
RNAseq experiments are uniformly `whole_cell` (no fractionation).
The same gene may have proteomics DE in `whole_cell` and `vesicle`
simultaneously — distinct rows. Filter via `compartment=...` on
`list_experiments`, `list_derived_metrics`, `list_metabolite_assays`,
and `list_organisms`. Discover valid values with
`list_filter_values('compartment')`.

---

## Backbone node types

### Organisms and genes

- **`OrganismTaxon`** (37 nodes) — strain-level organism with full
  taxonomy hierarchy. `preferred_name` is the canonical identifier (e.g.
  `"Prochlorococcus MED4"`); use exact case-insensitive matching.
- **`Gene`** (~100k nodes across all organisms) — anchored by
  `locus_tag` and `organism_name`. Carries pre-computed routing
  rollups: `expression_edge_count`, `numeric_metric_count` /
  `boolean_metric_count` / `categorical_metric_count`,
  `cluster_membership_count`, `closest_ortholog_group_size`,
  `reaction_count`, `metabolite_count`, `tcdb_family_count`,
  `cazy_family_count`, `compartments_observed`, `annotation_quality`
  (0..3 — see `docs://guide/conventions`). Each Gene also carries an
  amino-acid `sequence` and genomic coordinates (`contig`, `start`,
  `end`, `strand`) — all co-populated; null only on the ~3% of
  expression-only genes with no genome match. Exposed by
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
  coverage** — 935 distinct genes named across the whole corpus (out of
  ~100k), spread over 40 of the 43 publications. Precomputed counts live
  on the nodes (`Publication.discussed_gene_count` /
  `.discussed_pathway_count`, `Gene.discussed_in_publication_count`).
  Forward lookup: `discussed_by_publication` (paper → named genes +
  pathways). Reverse signals are folded inline — `gene_overview` carries
  per-gene `discussed_in_publication_count` + the discussing DOIs, and
  `search_ontology` carries per-KEGG-term `discussed_by_n_publications`.
- **`Experiment`** (~200 nodes) — one experimental contrast. Carries
  `treatment_type` (list[str], e.g. `['nutrient_stress']`),
  `background_factors` (list[str]|None), `omics_type` (e.g. `RNASEQ`,
  `PROTEOMICS`), `compartment` (`whole_cell` / `extracellular` /
  `vesicle` for proteomics+metabolomics), `is_time_course`,
  `table_scope` (which gene universe was quantified —
  `all_detected_genes` vs `significant_only`), and `coculture_partner`
  when applicable.
- **`ClusteringAnalysis`** (13 nodes) — a published co-expression
  clustering. Owns `GeneCluster` children
  (`ClusteringAnalysisHasGeneCluster`).
- **`GeneCluster`** (117 nodes) — a single co-expression module. Genes
  belong via `Gene_in_gene_cluster`.
- **`DerivedMetric`** (65 nodes) — one column of derived per-gene
  evidence from a publication (e.g. `is_rhythmic_with_p<0.01`,
  `light_dark_amplitude`). Polymorphic by `value_kind` ∈ {`numeric`,
  `boolean`, `categorical`}.
- **`MetaboliteAssay`** (14 nodes) — one column of mass-spec metabolite
  measurements. Polymorphic by `value_kind`. Connected to Metabolite via
  `Assay_quantifies_metabolite` (numeric, with `detection_status`) or
  `Assay_flags_metabolite` (boolean).

### Chemistry layer

- **`Metabolite`** (3230 nodes) — chemical compound, anchored by
  prefixed ID (`kegg.compound:Cxxxxx` for KEGG-derived; `chebi:NNN`
  for TCDB-only substrates). Carries cross-refs (`chebi_id`, `hmdb_id`,
  `mnxm_id`), `formula`, `elements` (presence list, never substring),
  `mass`, and a precomputed `evidence_sources` list — subset of
  {`metabolism`, `transport`, `metabolomics`} indicating which
  pipelines reach this compound. The first-class chemistry node:
  query directly with `list_metabolites`, drill in via
  `genes_by_metabolite` / `metabolites_by_gene`.

  KEGG `Reaction` nodes (2 349) sit *between* Gene and Metabolite
  on the metabolism arm — `Gene → Reaction → Metabolite` — but are
  **not directly queryable**: there's no `list_reactions` or
  `reaction_details` tool. Reactions surface as fields on chemistry
  rows (`reaction_id`, `reaction_name`, `ec_numbers`) and as the
  `top_reactions` envelope rollup on `genes_by_metabolite` /
  `metabolites_by_gene`. They are stored undirected — KEGG equation
  order is unreliable upstream, so the KG does not encode substrate
  vs product.
- **`TcdbFamily`** (~13k nodes) — TCDB transporter family hierarchy.
  Genes connect via `Gene_has_tcdb_family`; substrates via
  `Tcdb_family_transports_metabolite`. Substrates are curated at the
  **leaf** (`tc_specificity`) level and rolled **up** the hierarchy —
  every ancestor family carries the union of substrates from its
  descendant leaves. Why: transport-substrate specificity is
  biologically uncertain, so genes annotated to broad families still
  surface candidate substrates. Transport edges carry a
  `transport_confidence` discriminator: `substrate_confirmed` (gene
  annotated to the curated leaf itself) vs `family_inferred` (gene
  annotated to an ancestor; some descendant leaf carries the
  curation, but not necessarily the one matching this gene).
  Family-inferred dominates by volume — see
  `docs://analysis/metabolites`.

### Ontology nodes (14 ontologies)

All ontology nodes share a `level: int` property
(0 = root / broadest, higher = more specific) and most carry
`level_kind` and a sparse `level_is_best_effort` flag for DAG-shaped
ontologies. The two structural ontologies at the bottom (PSORTb,
SignalP) are flat — `level=0` only, no `level_kind`. The fourteen
supported ontologies:

| Ontology | Node label | Notes |
|---|---|---|
| Gene Ontology (GO) | `BiologicalProcess`, `MolecularFunction`, `CellularComponent` | DAG — `level` is min-path-from-root, `level_is_best_effort` flags ambiguous depth |
| KEGG | `KeggTerm` | Tree-ish; level kind in `{ko, pathway, module, ...}` |
| EC numbers | `EcNumber` | Tree (4-level enzyme nomenclature) |
| COG | `CogFunctionalCategory` | Tree, single-letter codes |
| Cyanorak | `CyanorakRole` | Tree (Prochlorococcus/Synechococcus-specific) |
| TIGR roles | `TigrRole` | Tree |
| Pfam | `Pfam`, `PfamClan` | Domains + clans |
| BRITE | `BriteCategory` | Multi-tree — **always scope with `tree=`** |
| TCDB | `TcdbFamily` | Transporter classification (also doubles as a chemistry node — see above) |
| CAZy | `CazyFamily` | Carbohydrate-active enzymes |
| PSORTb subcellular localization | `SubcellularLocalization` | Flat, 5 nodes (Cytoplasmic, CytoplasmicMembrane, OuterMembrane, Periplasmic, Extracellular). Scored edge: `localization_score: float` ∈[7.5, 10.0]. 1:1 (≤1 edge per gene). **Structural** — where the protein lives, not what it does. |
| SignalP signal-peptide type | `SignalPeptideType` | Flat, 5 nodes (SP, LIPO, TAT, TATLIPO, PILIN). Scored edge: `probability: float` ∈[0, 1], plus optional `cleavage_site: int` / `cleavage_probability: float`. 1:1. **Structural** — how the protein is handled at the membrane. |

Two reverse-mode ontology tools — `genes_by_ontology` (term → genes) and
`gene_ontology_terms` (genes → terms) — operate on all 14 uniformly
(with hierarchy expansion where applicable; PSORTb / SignalP are flat
so there's nothing to expand). For methodology see `docs://analysis/enrichment`.

PSORTb and SignalP are deliberately **NOT** folded into
`Gene.annotation_types` / `informative_annotation_types` /
`annotation_quality` — localization and signal-peptide presence describe
*how/where* a gene's product lives, not *what it does*, so folding would
skew `genes_by_function` `min_quality` reasoning. Routing strings
`Gene.subcellular_localization` and `Gene.signal_peptide_type` surface
the call directly via `gene_details` for 1:1 lookup without an ontology
tool call.

### Anchors that aren't measurement

- **`DataSource`** (4 nodes) — metadata about ingestion pipelines.
  Rarely surfaced through tools.
- **`Schema_info`** (1 node) — schema version metadata.

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
                                                                                             v
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
   Gene ──[Gene_has_subcellular_localization {score}]──► SubcellularLocalization (PSORTb)
   Gene ──[Gene_has_signal_peptide_type {probability, cleavage_site}]──► SignalPeptideType (SignalP)
```

The Gene node is the central hub. Almost every tool either finds genes
(by some criterion) or gets data about given genes. Metabolites form a
secondary hub for the chemistry layer; ontology terms form a third hub
for functional classification.

---

## Three metabolite source pipelines

The same Metabolite node may carry evidence from up to three
independent pipelines, indicated by `Metabolite.evidence_sources`:

1. **`metabolism`** — `Gene → Reaction → Metabolite` from KEGG. Catalysis
   evidence; direction-agnostic (KEGG equation order is unreliable, so
   we do not encode produced vs consumed).
2. **`transport`** — `Gene → TcdbFamily → Metabolite` from TCDB. Transport
   substrate evidence; `transport_confidence` discriminates curated leaf
   vs inherited-from-ancestor.
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

Exact counts are intentionally **not** listed here — they change with every
KG rebuild and a table reads as ground truth. To get current cardinalities,
call the tools that compute them live:

- **`kg_release_info`** — headline gene / experiment / paper / organism
  counts plus the release identity (version, built_at).
- **`list_organisms`** — per-organism gene / publication / experiment counts.
- **`kg_schema`** — node-label and relationship-type inventory.
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
  stored as MetaboliteAssay edges** — only the 14 curated assays.
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
