# Start here — picking the right tool

This MCP server exposes 39 tools over a Prochlorococcus/Alteromonas multi-omics
knowledge graph. Tools cluster into nine families. Before calling anything,
match your question to a family below, then read the entry-point tool's full
doc at `docs://tools/{name}`.

If you are new to the KG entities (Gene, Experiment, DerivedMetric,
Metabolite, MetaboliteAssay, Reaction, Ontology terms), read
`docs://guide/concepts` first — it is short and answers "what is each node
type and how do they connect?".

For cross-cutting semantics that apply to most tools (not_found vs
not_matched, tested-absent rows, AND-vs-UNION filters, summary/verbose
modes, rankable-gated filters, `informative_only` defaults), read
`docs://guide/conventions`.

For scripting against the Python package (bulk extraction, DataFrame
workflows, `EnrichmentResult` accessors, connection management,
worked recipes), read `docs://guide/python_api`.

---

## The nine tool families

| Family | Anchor concept | Entry-point tool(s) | Drill-down |
|---|---|---|---|
| **Identity** | "I have a gene name / locus tag / partial label" | `resolve_gene`, `gene_overview` | family-specific tools below |
| **Function / annotation** | "I have a function description, pathway, or ontology term" | `genes_by_function` (text), `search_ontology`, `ontology_landscape` | `genes_by_ontology`, `gene_ontology_terms` |
| **Expression** | "I have an experimental condition or want DE results" | `list_experiments`, `list_publications` | `differential_expression_by_gene`, `differential_expression_by_ortholog`, `gene_response_profile` |
| **Orthology** | "I want to compare across organisms" | `search_homolog_groups`, `gene_homologs` | `genes_by_homolog_group`, `differential_expression_by_ortholog` |
| **Co-expression / clustering** | "I want gene modules from a published clustering" | `list_clustering_analyses` | `genes_in_cluster`, `gene_clusters_by_gene` |
| **Enrichment** | "I have a gene set or DE result; what pathways / functional categories are enriched?" | `pathway_enrichment` (DE-driven), `cluster_enrichment` (clustering-driven) | Pre-flight: `ontology_landscape` (pick a defensible ontology + level). Methodology: `docs://analysis/enrichment` |
| **Derived metrics** | "I want non-DE column-level evidence (rhythmicity, amplitudes, traits)" | `list_derived_metrics` | `gene_derived_metrics`, `genes_by_{numeric,boolean,categorical}_metric` |
| **Chemistry / metabolomics** | "I have a metabolite, an element, a transport substrate, or measurement data" | `list_metabolites`, `list_metabolite_assays` | `genes_by_metabolite`, `metabolites_by_gene`, `metabolites_by_{quantifies,flags}_assay`, `assays_by_metabolite`. Methodology: `docs://analysis/metabolites` |
| **Sequence & genomic context** | "I have a gene; I want its protein sequence, or what sits next to it on the genome" | `gene_aa_sequence`, `gene_neighbors` | — (terminal export / positional lookup; chain neighbor locus_tags into the gene families above) |

Plus three orthogonal helpers:

- **`kg_schema`** — node labels, relationship types, properties. Read this
  before reaching for `run_cypher`.
- **`list_filter_values`** — the canonical source for valid values of
  categorical filters (gene categories, BRITE trees, metric types,
  compartments, value kinds, omics types, evidence sources).
- **`list_organisms`** — full organism taxonomy plus per-organism
  capability rollups (gene/expression/DM/chemistry/metabolomics counts).
- **`run_cypher`** — read-only Cypher escape hatch when no tool fits. The
  surface above covers the vast majority of questions; reach for raw
  Cypher only as a last resort.

---

## Decision tree: 15 common question shapes

### "What does gene X do? / Show me everything about gene X."
1. `resolve_gene(query="X")` if the input is a name or partial label.
2. `gene_overview(locus_tags=[...])` for a one-shot identity + data-availability rollup. The result tells you which drill-downs have evidence (`expression_edge_count`, `cluster_membership_count`, `derived_metric_count`, `evidence_sources`).
3. Drill into whichever signals are non-zero: `differential_expression_by_gene`, `gene_clusters_by_gene`, `gene_derived_metrics`, `gene_ontology_terms`, `metabolites_by_gene`, `gene_homologs`.

### "Find genes related to {keyword / function}."
1. `genes_by_function(query="...")` — Lucene over functional annotations. Best when you have a free-text description.
2. Or `search_ontology(query="...", ontology=...)` then `genes_by_ontology(term_ids=[...], organism=...)` when the keyword maps to a known ontology term (more precise than text search).

### "What pathways / functional categories are enriched in my DE set?"
- `pathway_enrichment(experiment_ids=[...], organism=..., ontology=..., level=...)`. See `docs://analysis/enrichment` for methodology, background semantics, and the `informative_only` default.
- Pre-flight: `ontology_landscape(organism=..., experiment_ids=[...])` to pick a defensible (ontology, level) before running enrichment.

### "What do experiments in this KG measure?"
1. `list_experiments(summary=True)` — orientation breakdowns by organism / treatment / omics / table_scope.
2. Filter to a slice (`organism=`, `treatment_type=`, `compartment=`, `publication_doi=`, `experiment_ids=`), then drop `summary=True` to see individual experiments.
3. Drill into expression: `differential_expression_by_gene(experiment_ids=[...], organism=...)`.

### "Compare gene X across Prochlorococcus and Alteromonas."
1. `gene_homologs(locus_tags=["X"])` to find ortholog group memberships.
2. `genes_by_homolog_group(group_ids=[...], organisms=[...])` to enumerate members per organism.
3. `differential_expression_by_ortholog(group_ids=[...])` for cross-organism DE framed by ortholog group.

### "What are the modules in the published co-expression clustering?"
1. `list_clustering_analyses(organism=..., search_text=...)` to discover analyses.
2. `genes_in_cluster(analysis_id=...)` for a full module roster.
3. `cluster_enrichment(analysis_id=..., ontology=..., level=...)` for ORA over each cluster.

### "Find genes with diel rhythmicity / large fold-amplitude / a specific categorical trait."
1. `list_derived_metrics(organism=..., value_kind=..., metric_types=[...])` to discover applicable DerivedMetric nodes. Inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories` here.
2. Drill: `genes_by_numeric_metric(...)`, `genes_by_boolean_metric(...)`, or `genes_by_categorical_metric(...)` depending on `value_kind`.
3. For a specific gene's full DM profile, `gene_derived_metrics(locus_tags=[...], organism=...)`.

### "What metabolites does this gene catalyse / transport?"
1. `gene_overview(locus_tags=[...])` first — the `evidence_sources` rollup tells you whether `metabolism` and/or `transport` apply.
2. `metabolites_by_gene(locus_tags=[...], organism=...)`. Inspect per-row `evidence_source` (`metabolism` / `transport`) and `transport_confidence` (`substrate_confirmed` / `family_inferred`).
3. See `docs://analysis/metabolites` — direction is **never** decidable from the KG alone (KEGG reactions are stored undirected; family-inferred transport substrates dominate). Layer DE direction to discriminate produced vs consumed.

### "What genes catalyse / transport / measure metabolite Y?"
1. `list_metabolites(search_text="Y")` or `list_metabolites(metabolite_ids=["kegg.compound:C..."])` to confirm the metabolite exists and inspect organism reach.
2. `genes_by_metabolite(metabolite_ids=[...], organism=...)` for catalysts/transporters in one organism.

### "Which metabolites were measured under condition Z?"
1. `list_metabolite_assays(experiment_ids=[...], compartment=..., value_kind=...)` — discovers the MetaboliteAssay nodes for that slice. Tested-absent metabolites are real biology — see `docs://guide/conventions`.
2. Numeric arm: `metabolites_by_quantifies_assay(assay_ids=[...])` for per-metabolite values + detection_status.
3. Boolean arm: `metabolites_by_flags_assay(assay_ids=[...])` for presence/absence flags.
4. Reverse: `assays_by_metabolite(metabolite_ids=[...])` collects all measurement evidence (numeric + boolean) for given metabolites.

### "Which genes belong to BRITE category / TCDB family / CAZy family X?"
- `genes_by_ontology(ontology=..., term_ids=[...], organism=...)` works for all 14 ontologies (GO, KEGG, EC, COG, Cyanorak, TIGR, Pfam, BRITE, TCDB, CAZy, plus the two structural ontologies below). For BRITE, scope with `tree=` (use `list_filter_values(filter_type='brite_tree')` to discover trees).

### "Where in the cell does gene X live? / Is gene X secreted (signal peptide)?"
- `genes_by_ontology(ontology="subcellular_localization", term_ids=["psortb_OuterMembrane"|"psortb_CytoplasmicMembrane"|...], organism=...)` for PSORTb-predicted localization; row carries `localization_score` (∈[7.5, 10.0]).
- `genes_by_ontology(ontology="signal_peptide_type", term_ids=["signalp_SP"|"signalp_LIPO"|"signalp_TAT"|"signalp_PILIN"|"signalp_TATLIPO"], organism=...)` for SignalP-predicted signal-peptide type; row carries `signal_peptide_probability`, `signal_peptide_cleavage_site`, `signal_peptide_cleavage_probability`.
- Both are **flat** (5 nodes each, `level=0` only) and **structural** — they describe where the protein lives / how it's handled, not what it does. Don't fold into `annotation_quality` reasoning.
- Per-gene lookup: `gene_ontology_terms(locus_tags=[...], ontology="subcellular_localization"|"signal_peptide_type", organism=..., mode="leaf")` returns the call (and confidence) for each input gene.

### "Get the protein/AA sequence of gene X (for BLAST/alignment)."
- `gene_aa_sequence(locus_tags=[...], fasta=True)` — returns amino-acid sequences (no nucleotide). `fasta=True` gives one multi-FASTA blob ready to paste into an external aligner / search tool.

### "What genes sit next to X on the genome / is X in an operon?"
- `gene_neighbors(locus_tags=["X"], window=5)` — genes flanking the anchor on the same contig, with `rank_offset`, `bp_gap`, and `same_strand`. Positional only — co-regulation must be confirmed via the expression tools, not inferred from adjacency.

### "What does paper Y discuss? / Which papers discuss gene or pathway X?"
This is the **literature axis** — a recall-biased index of the genes and
KEGG pathways each paper names in prose (with `prominence` + an
`evidence` quote), distinct from DE-table expression data.
- Paper → named entities: `discussed_by_publication(publication_dois=[...])`. Chains from `list_publications` (find DOIs) into `gene_overview` (drill genes) / `genes_by_ontology(ontology='kegg', term_ids=[...])` (expand pathways).
- Gene → discussing papers: `gene_overview(locus_tags=[...])` carries per-gene `discussed_in_publication_count` and (verbose) the discussing DOIs. No separate tool — genes are named by ~1 paper on average.
- KEGG pathway → discussing papers: `search_ontology(ontology='kegg', verbose=True)` carries per-term `discussed_by_n_publications` and the DOI list.
This index is a router, NOT exhaustive and NOT expression — use `differential_expression_by_gene` for DE.

### "I want raw Cypher."
- `run_cypher(query="...")`. Read-only; write operations blocked. Validate against `kg_schema` first. Almost always there is a typed tool that fits — reach for Cypher only when you are sure none does.

---

## When to call `summary=True` first

**Nearly universal: 33 of 39 tools accept `summary=True`** — discovery,
drill-down, gene-anchored, ontology, enrichment, all of it. With
`summary=True` the call returns only the envelope rollups
(`by_organism`, `by_treatment_type`, `top_*`, counts) and an empty
`results=[]`. Rollups are computed over the **full matched set** —
unaffected by `limit` / `offset` — so you see the shape before
committing to a slice.

Pattern: `summary=True` → look at rollups → narrow with filters → drop
`summary=True` to fetch detail rows.

The 6 tools without `summary=`: `kg_schema`, `list_filter_values`,
`resolve_gene`, `list_publications`, `gene_response_profile`,
`run_cypher`. These either return small fixed sets, are themselves
summaries (`gene_response_profile`), or have raw / shape-specific
output (`run_cypher`, `kg_schema`).

---

## Two-step pattern: discover, then drill

The KG has a consistent shape: most question families pair a **discovery
tool** (returns envelope + per-row routing fields) with one or more
**drill-down tools** (operates on IDs from the discovery results).

| Discovery | Drill-down(s) |
|---|---|
| `list_experiments` | `differential_expression_by_gene`, `pathway_enrichment`, `list_metabolite_assays(experiment_ids=...)` |
| `list_publications` | `list_experiments(publication_doi=...)`, `list_metabolite_assays(publication_doi=...)`, `discussed_by_publication(publication_dois=...)` |
| `list_metabolites` | `genes_by_metabolite`, `assays_by_metabolite`, `genes_by_ontology(ontology='kegg', term_ids=[pathway_id])` |
| `list_metabolite_assays` | `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite` |
| `list_derived_metrics` | `gene_derived_metrics`, `genes_by_{numeric,boolean,categorical}_metric` |
| `list_clustering_analyses` | `genes_in_cluster`, `cluster_enrichment` |
| `search_homolog_groups` | `genes_by_homolog_group`, `differential_expression_by_ortholog` |
| `search_ontology` / `ontology_landscape` | `genes_by_ontology`, `pathway_enrichment`, `cluster_enrichment` |
| `gene_overview` | family-specific drill-downs based on per-row availability signals |

Per-row routing fields on the discovery output (e.g.
`expression_edge_count`, `derived_metric_count`, `metabolite_count`,
`evidence_sources`, `compartments_observed`) tell you which drill-downs
have evidence for that row. **Use the routing fields** — calling a
drill-down on a row with `expression_edge_count=0` returns no
expression data, and the routing field is there to prevent that.

---

## Where to go next

- `docs://guide/concepts` — node types, edge types, what each measurement layer means.
- `docs://guide/conventions` — filter semantics, response shapes, gotchas that apply across tools.
- `docs://guide/python_api` — using the Python package: import topology, return shapes, DataFrames, worked recipes.
- `docs://analysis/enrichment` — pathway enrichment methodology + background semantics.
- `docs://analysis/metabolites` — metabolites decision-tree (3 source pipelines).
- `docs://analysis/derived_metrics` — DerivedMetric family overview.
- `docs://examples/pathway_enrichment.py` — runnable enrichment example.
- `docs://examples/metabolites.py` — runnable metabolites workflow examples (7 scenarios).
