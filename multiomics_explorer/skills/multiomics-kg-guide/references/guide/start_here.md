# Start here — picking the right tool

This MCP server exposes 42 tools over a Prochlorococcus/Alteromonas
multi-omics knowledge graph, clustered into ten families below. Match
your question to a family, then read the entry-point tool's full doc at
`docs://tools/{name}`.

**First call: `kg_release_info`.** `ok` — proceed. `warn` / `unknown` —
every call still works, but value lists quoted in docs may be stale;
trust `list_filter_values` over any quoted list.

New to the entities (Gene, Experiment, DerivedMetric, Metabolite,
MetaboliteAssay, Reaction, ontology terms)? Read `docs://guide/concepts`
first. For cross-cutting semantics (`not_found` vs `not_matched`,
tested-absent rows, summary/verbose modes, rankable-gated filters,
`informative_only` defaults, organism naming), read
`docs://guide/conventions`. For scripting the Python package, read
`docs://guide/python_api`.

---

## The ten tool families

| Family | Anchor concept | Entry-point tool(s) | Drill-down |
|---|---|---|---|
| **Identity** | "I have a gene name / locus tag / partial label" | `resolve_gene`, `gene_overview` | `gene_details` (every Gene property) when the overview isn't enough; family-specific tools below |
| **Function / annotation** | "I have a function description, pathway, or ontology term" | `genes_by_function` (text), `search_ontology` (browse or search terms) | `ontology_term_details` (term → parents / children / bridges), `genes_by_ontology`, `gene_ontology_terms`. Per-ontology reference: `docs://ontologies/index` |
| **Expression** | "I have an experimental condition or want DE results" | `list_experiments`, `list_publications` | `differential_expression_by_gene`, `differential_expression_by_ortholog`, `gene_response_profile` |
| **Literature index** | "What does paper Y name in prose? / Which papers name gene X?" | `list_publications` | `discussed_by_publication`; reverse signals on `gene_overview` (`discussed_in_publication_count`) and `search_ontology(ontology='kegg')` (`discussed_by_n_publications`) |
| **Orthology** | "I want to compare across organisms" | `search_homolog_groups`, `gene_homologs` | `genes_by_homolog_group`, `differential_expression_by_ortholog` |
| **Co-expression / clustering** | "I want gene modules from a published clustering" | `list_clustering_analyses` | `genes_in_cluster`, `gene_clusters_by_gene` |
| **Enrichment** | "I have a gene set or DE result; what pathways / functional categories are enriched?" | `pathway_enrichment` (DE-driven), `cluster_enrichment` (clustering-driven) | Pre-flight: `ontology_landscape` (pick a defensible ontology + level). Methodology: `docs://analysis/enrichment` |
| **Derived metrics** | "I want non-DE column-level evidence (rhythmicity, amplitudes, traits)" | `list_derived_metrics` | `gene_derived_metrics`, `genes_by_{numeric,boolean,categorical}_metric` |
| **Chemistry / metabolomics** | "I have a metabolite, element, transport substrate, or measurement data" | `list_metabolites`, `list_metabolite_assays` | `genes_by_metabolite`, `metabolites_by_gene`, `metabolites_by_{quantifies,flags}_assay`, `assays_by_metabolite`. Methodology: `docs://analysis/metabolites` |
| **Sequence & genomic context** | "I have a gene; I want its protein sequence, or what sits next to it on the genome" | `gene_aa_sequence`, `gene_neighbors` | — terminal export / positional lookup; chain neighbor locus_tags into the families above |

Plus five orthogonal helpers:

- **`kg_release_info`** — release identity + compatibility verdict. Call it first (see above).
- **`kg_schema`** — node labels, relationship types, properties. Read this before reaching for `run_cypher`.
- **`list_filter_values`** — canonical values for every closed vocabulary (gene categories, growth phases, `cluster_type`, `table_scope`, and the annotation-trust vocabularies), each with a `count` and, where the KG stores one, a `description`. Full enum: `docs://tools/list_filter_values`.
- **`list_organisms`** — organism taxonomy plus per-organism capability rollups (expression/DM/chemistry/metabolomics/annotation counts).
- **`run_cypher`** — read-only Cypher escape hatch for the rare question no tool covers; validate against `kg_schema` first.

---

## Decision tree: 19 common question shapes

### "What does gene X do? / Show me everything about gene X."
1. `resolve_gene(identifier="X")` if the input is a name or partial label.
2. `gene_overview(locus_tags=[...])` — one-shot identity + data-availability rollup; per-row routing fields (`expression_edge_count`, `derived_metric_count`, `evidence_sources`, `tcdb_family_count`, `discussed_in_publication_count`, ...) tell you which drill-downs have evidence — full field list: `docs://tools/gene_overview`.
3. Drill into whichever signals are non-zero: `differential_expression_by_gene`, `gene_clusters_by_gene`, `gene_derived_metrics`, `gene_ontology_terms`, `metabolites_by_gene`, `gene_homologs`. `gene_details` for the raw property dump.

### "Find genes related to {keyword / function}."
1. `genes_by_function(search_text="...")` — Lucene over functional annotations; best with a free-text description.
2. Or, when the keyword maps to a known ontology term: `search_ontology(search_text="...", ontology=[...])` then `genes_by_ontology(term_ids=[...], organism=...)`. Omit `search_text` to *browse* terms ranked by `gene_count` (`level=`, `min_gene_count=`, `organism=`).
3. Holding term IDs already? `ontology_term_details(term_ids=[...])` gives parents, children, bridges and counts across ontologies. Per-ontology semantics: `docs://ontologies/{key}` (index: `docs://ontologies/index`).

### "What pathways / functional categories are enriched in my DE set?"
0. **Step 0, always:** `ontology_landscape(organism=..., experiment_ids=[...])` — pick a defensible (ontology, level) before running enrichment, or risk an oversized or uninformative term set.
1. `pathway_enrichment(experiment_ids=[...], organism=..., ontology=..., level=...)`. Methodology, background semantics, `informative_only` default: `docs://analysis/enrichment`.
2. Trust filters (`sources=`, `evidence=`, `max_tier=`, `min_evidence_score=`, `call_class=`) shape TERM2GENE and background identically; `interpro_type=` is **required** for `ontology='interpro'`.

### "What do experiments in this KG measure?"
1. `list_experiments(summary=True)` — orientation breakdowns by organism / treatment / omics / table_scope.
2. Filter to a slice (`organism=`, `treatment_type=`, `compartment=`, `publication_dois=`, `experiment_ids=`; values are closed vocabularies — `list_filter_values`), then drop `summary=True` for individual experiments.
3. Drill into expression: `differential_expression_by_gene(experiment_ids=[...], organism=...)`.

### "Compare gene X across Prochlorococcus and Alteromonas."
1. `gene_homologs(locus_tags=["X"])` to find ortholog group memberships.
2. `genes_by_homolog_group(group_ids=[...], organisms=[...])` to enumerate members per organism.
3. `differential_expression_by_ortholog(group_ids=[...])` for cross-organism DE framed by ortholog group.

### "What are the modules in the published co-expression clustering?"
1. `list_clustering_analyses(organism=..., search_text=...)` to discover analyses (`cluster_type` values: `list_filter_values('cluster_type')`).
2. `genes_in_cluster(analysis_id=...)` for a full module roster.
3. `cluster_enrichment(analysis_id=..., ontology=..., level=...)` for ORA over each cluster.

### "Find genes with diel rhythmicity / large fold-amplitude / a specific categorical trait."
1. `list_derived_metrics(organism=..., value_kind=..., metric_types=[...])` to discover DerivedMetric nodes; inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories` here.
2. Drill by `value_kind`: `genes_by_numeric_metric` (thresholds, `metric_bucket` / percentile / rank on `rankable` DMs), `genes_by_boolean_metric` (`flag_value=`), or `genes_by_categorical_metric` (`categories=` a subset of `allowed_categories`).
3. One gene's full DM profile: `gene_derived_metrics(locus_tags=[...], organism=...)`.

### "What metabolites does this gene catalyse / transport?"
1. `gene_overview(locus_tags=[...])` first — `evidence_sources` tells you whether `metabolism` and/or `transport` apply.
2. `metabolites_by_gene(locus_tags=[...], organism=...)`. Inspect per-row `evidence_source`, `substrate_depth` (`most_specific` / `inherited`) and `tcdb_evidence_score`.
3. Direction is **never** decidable from the KG alone (KEGG reactions are undirected) — layer DE direction to discriminate produced vs consumed. Full tree: `docs://analysis/metabolites`.

### "What genes catalyse / transport / measure metabolite Y?"
1. `list_metabolites(search_text="Y")` or `list_metabolites(metabolite_ids=[...])` to confirm the metabolite exists and check organism reach. Bare and xref IDs (`C00064`, `CHEBI:17234`, `HMDB…`, `MNXM…`) are accepted on every `metabolite_ids` parameter (reported back in `resolved_aliases`).
2. `genes_by_metabolite(metabolite_ids=[...], organism=...)` for catalysts/transporters in one organism; `exclude_metabolite_ids=[...]` strips currency cofactors.

### "Which metabolites were measured under condition Z?"
1. `list_metabolite_assays(experiment_ids=[...], compartment=..., value_kind=...)` — discovers MetaboliteAssay nodes for that slice; tested-absent metabolites are real biology (`docs://guide/conventions`).
2. Numeric arm: `metabolites_by_quantifies_assay` (`assay_ids=[...]`). Boolean arm: `metabolites_by_flags_assay` (`assay_ids=[...]`).
3. Reverse (both arms merged): `assays_by_metabolite(metabolite_ids=[...])`.

### "Which metabolites can organism A make that organism B can take up?"
This is **cross-feeding**: pair one organism's production with another's uptake capability.
1. `list_metabolites(organism_names=["A"])` — per-row `catalyst_gene_count` (production) and `transporter_gene_count` (A's own uptake/export).
2. `genes_by_metabolite(metabolite_ids=[...], organism="B")` — same IDs, filtered to B, for its transporter genes (`evidence_source='transport'`).
3. Compare the two gene sets per metabolite. Full tree + the undirected-reaction caveat: `docs://analysis/metabolites`.

### "Which genes belong to BRITE category / TCDB family / CAZy family / InterPro entry / MEROPS clan X?"
- `genes_by_ontology(ontology=..., term_ids=[...], organism=...)` builds the TERM2GENE for any of the 17 ontologies. BRITE: scope with `tree=` (`list_filter_values(filter_type='brite_tree')`).
- **Substrate-anchored TCDB** ("which genes transport metabolite Y", not "which genes are in family X")? Use `genes_by_metabolite` instead.
- Trust filters (`sources=`, `evidence=`, `max_tier=`, `min_evidence_score=`, `call_class=`, `interpro_type=`) on 15 of the 17; rank-vs-filter rule + per-ontology axes: `docs://analysis/annotation_evidence`.
- No term ID yet? `search_ontology(ontology=['tcdb'], level=2)` browses by size. Have the ID? `ontology_term_details(term_ids=[...])`. Per-ontology semantics: `docs://ontologies/{key}`.

### "Are transporters as a class responding to this condition?"
This is **DE by functional class**: roll a DE result up to an ontology family instead of reading gene-by-gene.
1. `genes_by_ontology(ontology='tcdb', level=0, organism=...)` — TERM2GENE: every gene under a top-level TCDB family.
2. Pull those `locus_tags` into `differential_expression_by_gene(locus_tags=[...], experiment_ids=[...])` for row-level fold changes, or `pathway_enrichment(experiment_ids=[...], ontology='tcdb', level=0)` for a class-level test.
3. Swap `ontology='tcdb'` for any other of the 17 to ask the same question of a different functional grouping.

### "This gene has a Pfam domain / InterPro entry — which transporter, peptidase or TIGR role does that point to?"
This is **bridge walking**: `ontology_term_details(term_ids=[...]).links_out[]` (`link_kind` = `composition` / `membership` / `router`; definitions: `docs://tools/ontology_term_details`).
- `router` links are recall-biased, **never** a gene-function call. Bridges are forward-only — to go the other way, browse the target ontology or intersect two `genes_by_ontology` calls.
- TIGR roles: directly (`ontology='tigr_role'`, the gene-level call) or via the NCBIfam router (explains *why*, not a call on its own). Filter with `link_kinds=[...]`.

### "Where in the cell does gene X live? / Is gene X secreted (signal peptide)?"
- `genes_by_ontology(ontology="subcellular_localization"|"signal_peptide_type", term_ids=[...], organism=...)` for PSORTb / SignalP calls. Term IDs and verbose fields: `docs://ontologies/subcellular_localization`, `docs://ontologies/signal_peptide_type`.
- Both are **flat** (5 terms, `level=0`) and **structural** — where the protein lives / how it's handled, not what it does. Don't fold into `annotation_quality` reasoning.
- Per-gene lookup: `gene_ontology_terms(locus_tags=[...], ontology=..., mode="leaf")`; `gene_details` carries the same calls as plain `Gene` properties.

### "Get the protein/AA sequence of gene X (for BLAST/alignment)."
- `gene_aa_sequence(locus_tags=[...], fasta=True)` — returns amino-acid sequences (no nucleotide). `fasta=True` gives one multi-FASTA blob ready to paste into an external aligner / search tool.

### "What genes sit next to X on the genome / is X in an operon?"
- `gene_neighbors(locus_tags=["X"], window=5)` — genes flanking the anchor on the same contig, with `rank_offset`, `bp_gap`, and `same_strand`. Positional only — co-regulation must be confirmed via the expression tools, not inferred from adjacency.

### "What does paper Y discuss? / Which papers discuss gene or pathway X?"
The **literature index** — a recall-biased index of genes and KEGG pathways each paper names in prose (`prominence` + an `evidence` quote); not exhaustive, not expression data (`differential_expression_by_gene` for DE).
- Paper → named entities: `discussed_by_publication(publication_dois=[...])`. Chains from `list_publications` (DOIs) into `gene_overview` (genes) / `genes_by_ontology(ontology='kegg', term_ids=[...])` (pathways).
- Gene → discussing papers: `gene_overview(locus_tags=[...])` carries `discussed_in_publication_count` (verbose: the DOIs).
- KEGG pathway → discussing papers: `search_ontology(ontology='kegg')` carries `discussed_by_n_publications` per term (verbose: the DOI list).

### "I want raw Cypher."
- `run_cypher(query="...")`. Read-only; writes blocked. Validate against `kg_schema` first; reach for Cypher only when you are sure no typed tool fits. Apostrophes in stored names are carets (`^`) — `docs://guide/conventions`.

---

## When to call `summary=True` first

36 of 42 tools accept `summary=True`: returns only the envelope rollups
(`by_organism`, `top_*`, counts) over the **full matched set**, with
`results=[]`. Pattern: `summary=True` → read rollups → narrow with
filters → drop `summary=True` for detail rows. The 6 tools without it,
and `truncated` semantics in summary mode: `docs://guide/conventions`.

---

## Two-step pattern: discover, then drill

Most families above pair a **discovery** tool (envelope + per-row
routing fields) with **drill-down** tools that take IDs from the
discovery result — see each row's Drill-down column for the pairs. A
zero-valued routing field (`expression_edge_count`,
`catalyzed_metabolite_count`, `evidence_sources`, ...) means that
drill-down has no data for the row. Full rule: `docs://guide/conventions`.

---

## Where to go next

Every served page — guides, per-tool briefs and `/full` pages,
per-ontology references, analysis methodology, runnable examples — is
listed with its size and a one-line "read when" at `docs://index`.
Worth knowing by name: `docs://guide/concepts` (entity model),
`docs://guide/conventions` (cross-tool semantics), and the methodology
pages behind the multi-tool workflows above (`docs://analysis/enrichment`,
`docs://analysis/metabolites`, `docs://analysis/derived_metrics`,
`docs://analysis/annotation_evidence`).
