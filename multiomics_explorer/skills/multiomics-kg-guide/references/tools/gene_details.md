# gene_details

## What it does

All Gene node properties (deep-dive). Use `gene_overview` for the common routing case; this tool adds what overview omits — `sequence`, `gene_summary`, `function_description`, `alternate_functional_descriptions`, `catalytic_activities` (sparse: ~8k genes), `contributing_sources`, `seed_ortholog` / `seed_ortholog_evalue`, `protein_family`, coordinates (`contig`, `start`, `end`, `strand`). The Gene node carries NO `ec_numbers` / `ko_terms` / `kegg_ids` / `cog_categories` properties — chemistry and ontology annotations are graph edges: use `gene_ontology_terms(ontology=['ec','kegg'])` or `metabolites_by_gene`. TCDB/CAZy memberships are edges too.

Routing: prefer `gene_overview` for triage; chain into `metabolites_by_gene` for chemistry, `gene_homologs` for orthologs, `gene_ontology_terms` for annotations, `list_organisms` for taxonomy.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'sync_0001']. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| limit | int \| None | None | Default: every input gene (min 25). Pass a number to page. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, not_found, results
```

- **total_matching** (int): Genes found from input locus_tags.
- **returned** (int): Results in this response (0 when summary=true).
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if total_matching > returned.
- **not_found** (list[string]): Input locus_tags not in KG.

## Few-shot examples

### Example 1: Full properties for a single gene

```example-call
gene_details(locus_tags=["PMM0001"])
```

```example-response
{
  "total_matching": 1,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "results": [
    {
      "merops_family_count": 0,
      "categorical_metric_count": 2,
      "strand": "+",
      "significant_down_count": 1,
      "compartments_observed": ["whole_cell"],
      "closest_ortholog_group_size": 22,
      "gene_summary": "dnaN :: DNA polymerase III, beta subunit :: Confers DNA tethering and processivity to DNA polymerases and other prote...",
      "categorical_metric_types_observed": ["expression_level_class", "pangenome_membership"],
      "informative_annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "annotation_quality": 3,
      "gene_name": "dnaN",
      "ncbifam_family_count": 1,
      "numeric_metric_count": 13,
      "catalyzed_metabolite_count": 6,
      "contig": "NC_005072.1",
      "significant_up_count": 5,
      "merops_classes": [],
      "numeric_metric_types_observed": [
        "antisense_tss_count",
        "damping_ratio",
        "diel_amplitude_protein_log2",
        "diel_amplitude_transcript_log2",
        "expression_at_t0_log2",
        ...
      ],
      "gene_category": "Replication and repair",
      "start": 174,
      "cluster_membership_count": 2,
      "all_identifiers": ["CK_Pro_MED4_00001", "Q7V3R7", "TX50_RS00020", "WP_011131639.1"],
      "boolean_metric_count": 2,
      "transported_metabolite_count": 0,
      "organism_name": "Prochlorococcus MED4",
      "tcdb_family_count": 0,
      "reaction_count": 4,
      "function_description": "Confers DNA tethering and processivity to DNA polymerases and other proteins. Acts as a clamp, forming a ring around ...",
      "subcellular_localization": "Cytoplasmic",
      "annotation_state": "informative_multi",
      "protein_id": "WP_011131639.1",
      "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
      "id": "ncbigene:PMM0001",
      "annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "expression_edge_count": 38,
      "seed_ortholog_evalue": 1.12e-267,
      "cluster_types": ["decay_pattern", "diel"],
      "end": 1331,
      "locus_tag": "PMM0001",
      "alternate_functional_descriptions": [
        "[cyanorak] DNA polymerase III, beta subunit",
        "[ncbi] DNA polymerase III subunit beta",
        "[eggnog] Confers DNA tethering and processivity to DNA polymerases and other proteins. Acts as a clamp, forming a rin...",
        "[uniprot] Confers DNA tethering and processivity to DNA polymerases and other proteins. Acts as a clamp, forming a ri...",
        "[protein_family] Beta sliding clamp family",
        ...
      ],
      "contributing_sources": ["cyanorak", "eggnog", "interproscan", "ncbi", "psortb", ...],
      "interpro_entry_count": 5,
      "preferred_id": "ncbigene",
      "product": "DNA polymerase III, beta subunit",
      "cazy_family_count": 0,
      "boolean_metric_types_observed": ["expressed_above_background", "has_primary_tss"],
      "protein_family": "Beta sliding clamp family",
      "sequence": "MEIVCNQNEFNYAIQLVSKAVASRPTHPILANLLLTADQGTNKISLTGFDLNLGIQTSFDATVNKSGAITIPSKLLSEIVNKLPSETPVSLDVDESSDNILIKSDRGSFNIKGIPSD...",
      "seed_ortholog": "59919.PMM0001",
      "discussed_in_publication_count": 1
    }
  ]
}
```

### Example 2: Batch deep-dive

```example-call
gene_details(locus_tags=["PMM0001", "ALT831_RS00180"])
```

### Example 3: Just check existence (summary only)

```example-call
gene_details(locus_tags=["PMM0001", "FAKE_GENE"], summary=True)
```

```example-response
{
  "total_matching": 1,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "not_found": ["FAKE_GENE"],
  "results": []
}
```

### Example 4: From gene_overview to deep-dive

```
Step 1: gene_overview(locus_tags=["PMM0001", "PMM0845"])
        → see annotation_types, expression counts, ortholog summary

Step 2: gene_details(locus_tags=["PMM0001"])
        → inspect the raw node: sequence + coordinates (contig / start /
        end / strand / protein_id), gene_summary, function_description,
        sparse catalytic_activities, contributing_sources, seed_ortholog
        (+ evalue), all_identifiers, and every precomputed count.
        Ontology memberships (GO / KEGG / EC / TCDB / CAZy / ...) are
        graph edges, not Gene properties — use gene_ontology_terms.
```

## Chaining patterns

```
gene_overview → gene_details
resolve_gene → gene_details
genes_by_function → gene_details
gene_details → gene_ontology_terms(locus_tags=[...], ontology=['ec', 'kegg']) — the EC numbers / KO terms behind a gene live on edges, not on the node.
gene_details → metabolites_by_gene — when reaction_count / transported_metabolite_count are non-zero, list the metabolites this gene's reactions involve / its TCDB families transport. Single-gene chemistry deep-dive. See docs://analysis/metabolites.
```

## Common mistakes

- annotation_quality / min_quality semantics shifted in 2026-05 KG release. Existing notebooks using min_quality may select a different gene set than before. See docs://guide/conventions.

- This returns ALL Gene node properties via g{.*} — for the common case, use gene_overview which returns curated fields with routing signals.

- What this adds over gene_overview: the amino-acid `sequence`, genome coordinates (`contig`, `start`, `end`, `strand`, `protein_id`), the free-text `gene_summary` / `function_description` / `alternate_functional_descriptions`, sparse `catalytic_activities` (present on a minority of genes), `contributing_sources`, `seed_ortholog` + `seed_ortholog_evalue`, `all_identifiers`, `subcellular_localization`, and the full set of precomputed per-kind DM counts.

- The Gene node carries NO `ec_numbers`, `ko_terms`, `kegg_ids` or `cog_categories` properties — those are null on every gene. Ontology memberships (GO, KEGG KO / pathway, EC, COG, TCDB, CAZy, Pfam, ...) are graph edges: use gene_ontology_terms(locus_tags=[...], ontology=['ec', 'kegg']) (or any ontology list) to read them, gene_overview's `annotation_types` to see which exist.

- Chemistry context lives in three places: (1) edge-side EC / KO terms via `gene_ontology_terms(ontology=['ec', 'kegg'])` plus the sparse `catalytic_activities` text returned here; (2) `gene_overview` per-row `reaction_count` / `catalyzed_metabolite_count` / `tcdb_family_count` / `transported_metabolite_count` + `evidence_sources` rollup (routing surface — when non-zero, drill; the same counts are on the raw node here); (3) `metabolites_by_gene` for the actual metabolite list (per-arm: reaction-anchored via Gene → Reaction → Metabolite, transport-anchored via Gene → TcdbFamily → Metabolite). For 'what compounds does this gene's chemistry touch?', chain `gene_details → metabolites_by_gene` (or pre-filter with `gene_overview` first to skip genes with no chemistry).

```mistake
gene_details(locus_tags='PMM0001')
```

```correction
gene_details(locus_tags=['PMM0001']) — always a list
```

## Package import equivalent

```python
from multiomics_explorer import gene_details

result = gene_details(locus_tags=...)
# returns dict with keys: total_matching, returned, offset, truncated, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
