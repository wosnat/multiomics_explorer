# ontology_landscape

## What it does

Rank (ontology × level) strata by enrichment suitability — term-size distribution, genome coverage, relevance_rank.

Use as the pre-flight that picks (ontology, level) for `pathway_enrichment` / `cluster_enrichment`; the terms are `search_ontology`, gene sets `genes_by_ontology`.
Filters: organism, ontology, tree, experiment_ids, min/max_gene_set_size, informative_only, call_class, interpro_type.
Returns: organism_gene_count, n_ontologies, by_ontology, not_found, not_matched; one row = one stratum (BRITE per tree, InterPro per type).
docs://tools/ontology_landscape; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') \| list[string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops')] \| None | None | If None, surveys all 17 ontologies. Accepts a list; a facet carried by only some of them drops the rest into skipped_ontologies. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Narrows brite and leaves any other ontology in the list untouched; raises when brite is not among them. See docs://guide/conventions for the BRITE-tree scoping rule. |
| experiment_ids | list[string] \| None | None | Restrict coverage computation to genes quantified in these experiments. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields in docs://tools/{name}. |
| limit | int \| None | 15 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |
| min_gene_set_size | int | 5 | Exclude terms with fewer genes than this (default 5). |
| max_gene_set_size | int | 500 | Exclude terms with more genes than this (default 500). |
| informative_only | bool | True | True drops terms the KG flags uninformative (roots, catch-alls). |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; unfiltered mixes in catalytically-dead nonpeptidase_homolog rows. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
organism_name, organism_gene_count, n_ontologies, by_ontology, not_found, not_matched, total_matching, returned, truncated, offset, results
```

- **organism_name** (string)
- **organism_gene_count** (int)
- **n_ontologies** (int)
- **by_ontology** (object)
- **not_found** (list[string])
- **not_matched** (list[string])
- **total_matching** (int)
- **returned** (int)
- **truncated** (bool)
- **offset** (int)

### Per-result fields

| Field | Type | Description |
|---|---|---|
| ontology_type | string | Ontology key (e.g. 'cyanorak_role') |
| level | int | Hierarchy level; 0 = broadest |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |
| interpro_type | string \| None (optional) | InterPro entry type this stratum covers (sparse: interpro only). |
| relevance_rank | int | 1-indexed rank by spec_score; stable under pagination |
| n_terms_with_genes | int |  |
| n_genes_at_level | int |  |
| genome_coverage | float | n_genes_at_level / organism_gene_count |
| min_genes_per_term | int |  |
| q1_genes_per_term | float |  |
| median_genes_per_term | float |  |
| q3_genes_per_term | float |  |
| max_genes_per_term | int |  |
| n_levels_in_ontology | int | Levels this ontology spans (1 = flat) |
| best_effort_share | float \| None (optional) | Fraction of reached terms flagged level_is_best_effort (GO only; None for others) |
| min_exp_coverage | float \| None (optional) |  |
| median_exp_coverage | float \| None (optional) |  |
| max_exp_coverage | float \| None (optional) |  |
| n_experiments_with_coverage | int \| None (optional) |  |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| example_terms | list[ExampleTerm] \| None (optional) | Top 3 terms by gene count (verbose only) |

## Few-shot examples

### Example 1: Default survey — which ontology/level should I use for MED4?

```example-call
ontology_landscape(organism="MED4")
```

*One row per (ontology × level) — BRITE per tree, InterPro per `interpro_type` — ranked by `relevance_rank`. `by_ontology` is an object keyed by ontology name (`brite:<tree>` for BRITE) with each ontology's best level. Ranks and coverages shift with each KG build; read the live response, not this one. All 17 ontologies are surveyed by default (`n_ontologies`).*

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "organism_gene_count": 1973,
  "n_ontologies": 17,
  "by_ontology": {
    "tigr_role": {
      "best_level": 1,
      "best_genome_coverage": 0.6203750633552965,
      "best_relevance_rank": 1,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "go_mf": {
      "best_level": 2,
      "best_genome_coverage": 0.5823618854536239,
      "best_relevance_rank": 2,
      "n_levels": 7,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "cyanorak_role": {
      "best_level": 1,
      "best_genome_coverage": 0.5615813482007096,
      "best_relevance_rank": 3,
      "n_levels": 3,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "go_bp": {
      "best_level": 3,
      "best_genome_coverage": 0.5458692346680183,
      "best_relevance_rank": 5,
      "n_levels": 9,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "pfam": {
      "best_level": 0,
      "best_genome_coverage": 0.43740496705524584,
      "best_relevance_rank": 9,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "cog_category": {
      "best_level": 0,
      "best_genome_coverage": 0.5641155600608211,
      "best_relevance_rank": 10,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "go_cc": {
      "best_level": 2,
      "best_genome_coverage": 0.4034465281297516,
      "best_relevance_rank": 11,
      "n_levels": 6,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "ec": {
      "best_level": 1,
      "best_genome_coverage": 0.40293968575772937,
      "best_relevance_rank": 12,
      "n_levels": 4,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "kegg": {
      "best_level": 1,
      "best_genome_coverage": 0.3867207298530157,
      "best_relevance_rank": 14,
      "n_levels": 3,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "interpro": {
      "best_level": 0,
      "best_genome_coverage": 0.33046122655854027,
      "best_relevance_rank": 18,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": "HOMOLOGOUS_SUPERFAMILY"
    },
    "brite:enzymes": {
      "best_level": 1,
      "best_genome_coverage": 0.31779016725798276,
      "best_relevance_rank": 20,
      "n_levels": 4,
      "tree": "enzymes",
      "tree_code": "ko01000",
      "best_interpro_type": null
    },
    "subcellular_localization": {
      "best_level": 0,
      "best_genome_coverage": 0.1875316776482514,
      "best_relevance_rank": 26,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "tcdb": {
      "best_level": 0,
      "best_genome_coverage": 0.1804358844399392,
      "best_relevance_rank": 27,
      "n_levels": 5,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "signal_peptide_type": {
      "best_level": 0,
      "best_genome_coverage": 0.05423213380638622,
      "best_relevance_rank": 42,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "brite:transporters": {
      "best_level": 0,
      "best_genome_coverage": 0.04308160162189559,
      "best_relevance_rank": 44,
      "n_levels": 3,
      "tree": "transporters",
      "tree_code": "ko02000",
      "best_interpro_type": null
    },
    "brite:trna_biogenesis": {
      "best_level": 0,
      "best_genome_coverage": 0.03294475418144957,
      "best_relevance_rank": 47,
      "n_levels": 3,
      "tree": "trna_biogenesis",
      "tree_code": "ko03016",
      "best_interpro_type": null
    },
    "brite:ribosome": {
      "best_level": 2,
      "best_genome_coverage": 0.027369488089204256,
      "best_relevance_rank": 50,
      "n_levels": 3,
      "tree": "ribosome",
      "tree_code": "ko03011",
      "best_interpro_type": null
    },
    "brite:peptidases": {
      "best_level": 0,
      "best_genome_coverage": 0.01926001013684744,
      "best_relevance_rank": 57,
      "n_levels": 1,
      "tree": "peptidases",
      "tree_code": "ko01002",
      "best_interpro_type": null
    },
    "merops": {
      "best_level": 0,
      "best_genome_coverage": 0.017232640648758235,
      "best_relevance_rank": 59,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "cazy": {
      "best_level": 0,
      "best_genome_coverage": 0.016218955904713634,
      "best_relevance_rank": 61,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "brite:chaperones": {
      "best_level": 0,
      "best_genome_coverage": 0.012164216928535226,
      "best_relevance_rank": 63,
      "n_levels": 1,
      "tree": "chaperones",
      "tree_code": "ko03110",
      "best_interpro_type": null
    },
    "brite:dna_replication": {
      "best_level": 0,
      "best_genome_coverage": 0.011150532184490624,
      "best_relevance_rank": 64,
      "n_levels": 4,
      "tree": "dna_replication",
      "tree_code": "ko03032",
      "best_interpro_type": null
    },
    "brite:translation_factors": {
      "best_level": 0,
      "best_genome_coverage": 0.008109477952356817,
      "best_relevance_rank": 66,
      "n_levels": 2,
      "tree": "translation_factors",
      "tree_code": "ko03012",
      "best_interpro_type": null
    },
    "ncbifam": {
      "best_level": 0,
      "best_genome_coverage": 0.008109477952356817,
      "best_relevance_rank": 67,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "brite:transcription_factors": {
      "best_level": 0,
      "best_genome_coverage": 0.00506842372022301,
      "best_relevance_rank": 72,
      "n_levels": 2,
      "tree": "transcription_factors",
      "tree_code": "ko03000",
      "best_interpro_type": null
    },
    "brite:secretion": {
      "best_level": 0,
      "best_genome_coverage": 0.00456158134820071,
      "best_relevance_rank": 73,
      "n_levels": 2,
      "tree": "secretion",
      "tree_code": "ko02044",
      "best_interpro_type": null
    },
    "brite:two_component": {
      "best_level": 0,
      "best_genome_coverage": 0.0030410542321338066,
      "best_relevance_rank": 78,
      "n_levels": 1,
      "tree": "two_component",
      "tree_code": "ko02022",
      "best_interpro_type": null
    }
  },
  "not_found": [],
  "not_matched": [],
  "total_matching": 81,
  "returned": 15,
  "truncated": true,
  "offset": 0,
  "results": [
    {
      "ontology_type": "tigr_role",
      "level": 1,
      "relevance_rank": 1,
      "n_terms_with_genes": 76,
      "n_genes_at_level": 1224,
      "genome_coverage": 0.6203750633552965,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 7.0,
      "median_genes_per_term": 12.5,
      "q3_genes_per_term": 20.25,
      "max_genes_per_term": 118,
      "n_levels_in_ontology": 2,
      "best_effort_share": null
    },
    {
      "ontology_type": "go_mf",
      "level": 2,
      "relevance_rank": 2,
      "n_terms_with_genes": 35,
      "n_genes_at_level": 1149,
      "genome_coverage": 0.5823618854536239,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 9.5,
      "median_genes_per_term": 26.0,
      "q3_genes_per_term": 98.5,
      "max_genes_per_term": 318,
      "n_levels_in_ontology": 7,
      "best_effort_share": 0.2
    },
    {
      "ontology_type": "cyanorak_role",
      "level": 1,
      "relevance_rank": 3,
      "n_terms_with_genes": 67,
      "n_genes_at_level": 1108,
      "genome_coverage": 0.5615813482007096,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 9.0,
      "median_genes_per_term": 14.0,
      "q3_genes_per_term": 23.0,
      "max_genes_per_term": 213,
      "n_levels_in_ontology": 3,
      "best_effort_share": null
    },
    ...
  ]
}
```

### Example 2: Drill into a specific ontology

```example-call
ontology_landscape(organism="MED4", ontology="go_bp", verbose=True)
```

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "organism_gene_count": 1973,
  "n_ontologies": 1,
  "by_ontology": {
    "go_bp": {
      "best_level": 3,
      "best_genome_coverage": 0.5458692346680183,
      "best_relevance_rank": 1,
      "n_levels": 9,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    }
  },
  "not_found": [],
  "not_matched": [],
  "total_matching": 9,
  "returned": 9,
  "truncated": false,
  "offset": 0,
  "results": [
    {
      "ontology_type": "go_bp",
      "level": 3,
      "relevance_rank": 1,
      "n_terms_with_genes": 69,
      "n_genes_at_level": 1077,
      "genome_coverage": 0.5458692346680183,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 8.0,
      "median_genes_per_term": 13.0,
      "q3_genes_per_term": 38.0,
      "max_genes_per_term": 403,
      "n_levels_in_ontology": 9,
      "best_effort_share": 0.2028985507246377,
      "example_terms": [
        {"term_id": "go:0043170", "name": "macromolecule metabolic process", "n_genes": 403},
        {"term_id": "go:0044281", "name": "small molecule metabolic process", "n_genes": 333},
        {"term_id": "go:0006793", "name": "phosphorus metabolic process", "n_genes": 160}
      ]
    },
    {
      "ontology_type": "go_bp",
      "level": 4,
      "relevance_rank": 2,
      "n_terms_with_genes": 133,
      "n_genes_at_level": 992,
      "genome_coverage": 0.5027876330461226,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 8.0,
      "median_genes_per_term": 13.0,
      "q3_genes_per_term": 38.0,
      "max_genes_per_term": 292,
      "n_levels_in_ontology": 9,
      "best_effort_share": 0.40601503759398494,
      "example_terms": [
        {"term_id": "go:0006139", "name": "nucleobase-containing compound metabolic process", "n_genes": 292},
        {"term_id": "go:0009059", "name": "macromolecule biosynthetic process", "n_genes": 277},
        {"term_id": "go:0019538", "name": "protein metabolic process", "n_genes": 211}
      ]
    },
    {
      "ontology_type": "go_bp",
      "level": 5,
      "relevance_rank": 3,
      "n_terms_with_genes": 143,
      "n_genes_at_level": 882,
      "genome_coverage": 0.44703497212366955,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 8.0,
      "median_genes_per_term": 11.0,
      "q3_genes_per_term": 24.5,
      "max_genes_per_term": 219,
      "n_levels_in_ontology": 9,
      "best_effort_share": 0.6293706293706294,
      "example_terms": [
        {"term_id": "go:0010467", "name": "gene expression", "n_genes": 219},
        {"term_id": "go:0043436", "name": "oxoacid metabolic process", "n_genes": 171},
        {"term_id": "go:0016070", "name": "RNA metabolic process", "n_genes": 120}
      ]
    },
    ...
  ]
}
```

### Example 3: BRITE landscape scoped to a specific tree

```example-call
ontology_landscape(organism="MED4", ontology="brite", tree="transporters")
```

### Example 4: Small hierarchical ontologies — TCDB and CAZy only

```example-call
ontology_landscape(organism="MED4", ontology=["tcdb", "cazy"])
```

*TCDB has 5 levels (`tc_class` … `tc_specificity`), CAZy 2 (class, family); rows carry only `level`, not a level-kind label — see docs://ontologies/tcdb and docs://ontologies/cazy for what each level means. Both are small and thinly annotated in Prochlorococcus, so few levels pass the default size filter.*

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "organism_gene_count": 1973,
  "n_ontologies": 2,
  "by_ontology": {
    "tcdb": {
      "best_level": 0,
      "best_genome_coverage": 0.1804358844399392,
      "best_relevance_rank": 1,
      "n_levels": 5,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "cazy": {
      "best_level": 0,
      "best_genome_coverage": 0.016218955904713634,
      "best_relevance_rank": 5,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    }
  },
  "not_found": [],
  "not_matched": [],
  "total_matching": 7,
  "returned": 7,
  "truncated": false,
  "offset": 0,
  "results": [
    {
      "ontology_type": "tcdb",
      "level": 0,
      "relevance_rank": 1,
      "n_terms_with_genes": 7,
      "n_genes_at_level": 356,
      "genome_coverage": 0.1804358844399392,
      "min_genes_per_term": 14,
      "q1_genes_per_term": 21.5,
      "median_genes_per_term": 43.0,
      "q3_genes_per_term": 71.0,
      "max_genes_per_term": 188,
      "n_levels_in_ontology": 5,
      "best_effort_share": null
    },
    {
      "ontology_type": "tcdb",
      "level": 1,
      "relevance_rank": 2,
      "n_terms_with_genes": 11,
      "n_genes_at_level": 342,
      "genome_coverage": 0.17334009123162697,
      "min_genes_per_term": 8,
      "q1_genes_per_term": 15.0,
      "median_genes_per_term": 26.0,
      "q3_genes_per_term": 49.0,
      "max_genes_per_term": 133,
      "n_levels_in_ontology": 5,
      "best_effort_share": null
    },
    {
      "ontology_type": "tcdb",
      "level": 2,
      "relevance_rank": 3,
      "n_terms_with_genes": 22,
      "n_genes_at_level": 197,
      "genome_coverage": 0.09984794728839332,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 6.0,
      "median_genes_per_term": 8.0,
      "q3_genes_per_term": 10.75,
      "max_genes_per_term": 65,
      "n_levels_in_ontology": 5,
      "best_effort_share": null
    },
    ...
  ]
}
```

### Example 5: Restrict the fan-out to specific ontologies

```example-call
ontology_landscape(organism="MED4", ontology=["interpro", "merops"])
```

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "organism_gene_count": 1973,
  "n_ontologies": 2,
  "by_ontology": {
    "interpro": {
      "best_level": 0,
      "best_genome_coverage": 0.33046122655854027,
      "best_relevance_rank": 1,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": "HOMOLOGOUS_SUPERFAMILY"
    },
    "merops": {
      "best_level": 0,
      "best_genome_coverage": 0.017232640648758235,
      "best_relevance_rank": 5,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    }
  },
  "not_found": [],
  "not_matched": [],
  "total_matching": 8,
  "returned": 8,
  "truncated": false,
  "offset": 0,
  "results": [
    {
      "ontology_type": "interpro",
      "level": 0,
      "interpro_type": "HOMOLOGOUS_SUPERFAMILY",
      "relevance_rank": 1,
      "n_terms_with_genes": 74,
      "n_genes_at_level": 652,
      "genome_coverage": 0.33046122655854027,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 6.0,
      "median_genes_per_term": 7.0,
      "q3_genes_per_term": 11.75,
      "max_genes_per_term": 119,
      "n_levels_in_ontology": 2,
      "best_effort_share": null
    },
    {
      "ontology_type": "interpro",
      "level": 0,
      "interpro_type": "DOMAIN",
      "relevance_rank": 2,
      "n_terms_with_genes": 47,
      "n_genes_at_level": 283,
      "genome_coverage": 0.1434363912823112,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 5.0,
      "median_genes_per_term": 6.0,
      "q3_genes_per_term": 7.0,
      "max_genes_per_term": 49,
      "n_levels_in_ontology": 2,
      "best_effort_share": null
    },
    {
      "ontology_type": "interpro",
      "level": 1,
      "interpro_type": "DOMAIN",
      "relevance_rank": 3,
      "n_terms_with_genes": 4,
      "n_genes_at_level": 46,
      "genome_coverage": 0.02331474911302585,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 5.75,
      "median_genes_per_term": 7.0,
      "q3_genes_per_term": 12.75,
      "max_genes_per_term": 27,
      "n_levels_in_ontology": 2,
      "best_effort_share": null
    },
    ...
  ]
}
```

### Example 6: InterPro rows are broken down per interpro_type

```example-call
ontology_landscape(organism="MED4", ontology="interpro", verbose=True)
```

*Like BRITE's per-tree rows, InterPro rows are broken down per `interpro_type` instead of one pooled row — HOMOLOGOUS_SUPERFAMILY, DOMAIN, FAMILY, REPEAT, CONSERVED_SITE, ACTIVE_SITE, BINDING_SITE, PTM size very differently (MED4 level 0: HOMOLOGOUS_SUPERFAMILY 74 testable terms, DOMAIN 47, FAMILY 5, the rest ≤ 4). Pass `interpro_type=` to keep one type only.*

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "organism_gene_count": 1973,
  "n_ontologies": 1,
  "by_ontology": {
    "interpro": {
      "best_level": 0,
      "best_genome_coverage": 0.33046122655854027,
      "best_relevance_rank": 1,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": "HOMOLOGOUS_SUPERFAMILY"
    }
  },
  "not_found": [],
  "not_matched": [],
  "total_matching": 6,
  "returned": 6,
  "truncated": false,
  "offset": 0,
  "results": [
    {
      "ontology_type": "interpro",
      "level": 0,
      "interpro_type": "HOMOLOGOUS_SUPERFAMILY",
      "relevance_rank": 1,
      "n_terms_with_genes": 74,
      "n_genes_at_level": 652,
      "genome_coverage": 0.33046122655854027,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 6.0,
      "median_genes_per_term": 7.0,
      "q3_genes_per_term": 11.75,
      "max_genes_per_term": 119,
      "n_levels_in_ontology": 2,
      "best_effort_share": null,
      "example_terms": [
        {
          "term_id": "interpro:IPR027417",
          "name": "P-loop containing nucleoside triphosphate hydrolase",
          "n_genes": 119
        },
        {"term_id": "interpro:IPR036291", "name": "NAD(P)-binding domain superfamily", "n_genes": 54},
        {"term_id": "interpro:IPR013785", "name": "Aldolase-type TIM barrel", "n_genes": 32}
      ]
    },
    {
      "ontology_type": "interpro",
      "level": 0,
      "interpro_type": "DOMAIN",
      "relevance_rank": 2,
      "n_terms_with_genes": 47,
      "n_genes_at_level": 283,
      "genome_coverage": 0.1434363912823112,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 5.0,
      "median_genes_per_term": 6.0,
      "q3_genes_per_term": 7.0,
      "max_genes_per_term": 49,
      "n_levels_in_ontology": 2,
      "best_effort_share": null,
      "example_terms": [
        {"term_id": "interpro:IPR003593", "name": "AAA+ ATPase domain", "n_genes": 49},
        {"term_id": "interpro:IPR001509", "name": "NAD-dependent epimerase/dehydratase", "n_genes": 12},
        {"term_id": "interpro:IPR001173", "name": "Glycosyltransferase 2-like", "n_genes": 12}
      ]
    },
    {
      "ontology_type": "interpro",
      "level": 1,
      "interpro_type": "DOMAIN",
      "relevance_rank": 3,
      "n_terms_with_genes": 4,
      "n_genes_at_level": 46,
      "genome_coverage": 0.02331474911302585,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 5.75,
      "median_genes_per_term": 7.0,
      "q3_genes_per_term": 12.75,
      "max_genes_per_term": 27,
      "n_levels_in_ontology": 2,
      "best_effort_share": null,
      "example_terms": [
        {"term_id": "interpro:IPR003439", "name": "ABC transporter-like, ATP-binding domain", "n_genes": 27},
        {
          "term_id": "interpro:IPR006638",
          "name": "Elp3/MiaA/NifB-like, radical SAM core domain",
          "n_genes": 8
        },
        {"term_id": "interpro:IPR011545", "name": "DEAD/DEAH-box helicase domain", "n_genes": 6}
      ]
    },
    ...
  ]
}
```

### Example 7: MEROPS landscape scoped to peptidase calls (call_class filter)

```example-call
ontology_landscape(organism="MED4", ontology="merops", call_class=["peptidase"])
```

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "organism_gene_count": 1973,
  "n_ontologies": 1,
  "by_ontology": {
    "merops": {
      "best_level": 0,
      "best_genome_coverage": 0.013684744044602128,
      "best_relevance_rank": 1,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    }
  },
  "not_found": [],
  "not_matched": [],
  "total_matching": 2,
  "returned": 2,
  "truncated": false,
  "offset": 0,
  "results": [
    {
      "ontology_type": "merops",
      "level": 0,
      "relevance_rank": 1,
      "n_terms_with_genes": 4,
      "n_genes_at_level": 27,
      "genome_coverage": 0.013684744044602128,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 6.5,
      "median_genes_per_term": 7.0,
      "q3_genes_per_term": 7.25,
      "max_genes_per_term": 8,
      "n_levels_in_ontology": 2,
      "best_effort_share": null
    },
    {
      "ontology_type": "merops",
      "level": 1,
      "relevance_rank": 2,
      "n_terms_with_genes": 1,
      "n_genes_at_level": 6,
      "genome_coverage": 0.0030410542321338066,
      "min_genes_per_term": 6,
      "q1_genes_per_term": 6.0,
      "median_genes_per_term": 6.0,
      "q3_genes_per_term": 6.0,
      "max_genes_per_term": 6,
      "n_levels_in_ontology": 2,
      "best_effort_share": null
    }
  ]
}
```

### Example 8: Opt out of informative-only filtering (browse all terms, including catch-alls)

```example-call
ontology_landscape(organism="MED4", informative_only=False)
```

*`ontology_landscape` defaults to `informative_only=True` (the only ontology tool that does) — the ranking surface for enrichment should reflect informative terms only. Pass `informative_only=False` for an unfiltered census, e.g. when triaging coverage gaps or comparing unfiltered vs filtered genome_coverage. Term counts and genome_coverage rise slightly (MED4 KEGG level 3: 30 KO terms; at KEGG level 2 the global / overview maps such as ko01100 are flagged and drop out under the default).*

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "organism_gene_count": 1973,
  "n_ontologies": 17,
  "by_ontology": {
    "tigr_role": {
      "best_level": 1,
      "best_genome_coverage": 0.8773441459706032,
      "best_relevance_rank": 1,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "cyanorak_role": {
      "best_level": 1,
      "best_genome_coverage": 0.728839330968069,
      "best_relevance_rank": 2,
      "n_levels": 3,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "go_mf": {
      "best_level": 2,
      "best_genome_coverage": 0.5823618854536239,
      "best_relevance_rank": 4,
      "n_levels": 7,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "go_bp": {
      "best_level": 3,
      "best_genome_coverage": 0.5458692346680183,
      "best_relevance_rank": 6,
      "n_levels": 9,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "pfam": {
      "best_level": 0,
      "best_genome_coverage": 0.43740496705524584,
      "best_relevance_rank": 11,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "cog_category": {
      "best_level": 0,
      "best_genome_coverage": 0.5641155600608211,
      "best_relevance_rank": 12,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "go_cc": {
      "best_level": 2,
      "best_genome_coverage": 0.4034465281297516,
      "best_relevance_rank": 13,
      "n_levels": 6,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "ec": {
      "best_level": 1,
      "best_genome_coverage": 0.40293968575772937,
      "best_relevance_rank": 14,
      "n_levels": 4,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "kegg": {
      "best_level": 1,
      "best_genome_coverage": 0.3867207298530157,
      "best_relevance_rank": 15,
      "n_levels": 3,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "interpro": {
      "best_level": 0,
      "best_genome_coverage": 0.33046122655854027,
      "best_relevance_rank": 18,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": "HOMOLOGOUS_SUPERFAMILY"
    },
    "brite:enzymes": {
      "best_level": 1,
      "best_genome_coverage": 0.31779016725798276,
      "best_relevance_rank": 20,
      "n_levels": 4,
      "tree": "enzymes",
      "tree_code": "ko01000",
      "best_interpro_type": null
    },
    "subcellular_localization": {
      "best_level": 0,
      "best_genome_coverage": 0.1875316776482514,
      "best_relevance_rank": 26,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "tcdb": {
      "best_level": 0,
      "best_genome_coverage": 0.1804358844399392,
      "best_relevance_rank": 27,
      "n_levels": 5,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "signal_peptide_type": {
      "best_level": 0,
      "best_genome_coverage": 0.05423213380638622,
      "best_relevance_rank": 42,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "brite:transporters": {
      "best_level": 0,
      "best_genome_coverage": 0.04308160162189559,
      "best_relevance_rank": 44,
      "n_levels": 3,
      "tree": "transporters",
      "tree_code": "ko02000",
      "best_interpro_type": null
    },
    "brite:trna_biogenesis": {
      "best_level": 0,
      "best_genome_coverage": 0.03294475418144957,
      "best_relevance_rank": 47,
      "n_levels": 3,
      "tree": "trna_biogenesis",
      "tree_code": "ko03016",
      "best_interpro_type": null
    },
    "brite:ribosome": {
      "best_level": 2,
      "best_genome_coverage": 0.027369488089204256,
      "best_relevance_rank": 50,
      "n_levels": 3,
      "tree": "ribosome",
      "tree_code": "ko03011",
      "best_interpro_type": null
    },
    "brite:peptidases": {
      "best_level": 0,
      "best_genome_coverage": 0.01926001013684744,
      "best_relevance_rank": 58,
      "n_levels": 1,
      "tree": "peptidases",
      "tree_code": "ko01002",
      "best_interpro_type": null
    },
    "merops": {
      "best_level": 0,
      "best_genome_coverage": 0.017232640648758235,
      "best_relevance_rank": 60,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "cazy": {
      "best_level": 0,
      "best_genome_coverage": 0.016218955904713634,
      "best_relevance_rank": 62,
      "n_levels": 2,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "brite:chaperones": {
      "best_level": 0,
      "best_genome_coverage": 0.012164216928535226,
      "best_relevance_rank": 63,
      "n_levels": 1,
      "tree": "chaperones",
      "tree_code": "ko03110",
      "best_interpro_type": null
    },
    "brite:dna_replication": {
      "best_level": 0,
      "best_genome_coverage": 0.011150532184490624,
      "best_relevance_rank": 64,
      "n_levels": 4,
      "tree": "dna_replication",
      "tree_code": "ko03032",
      "best_interpro_type": null
    },
    "brite:translation_factors": {
      "best_level": 0,
      "best_genome_coverage": 0.008109477952356817,
      "best_relevance_rank": 66,
      "n_levels": 2,
      "tree": "translation_factors",
      "tree_code": "ko03012",
      "best_interpro_type": null
    },
    "ncbifam": {
      "best_level": 0,
      "best_genome_coverage": 0.008109477952356817,
      "best_relevance_rank": 67,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "brite:transcription_factors": {
      "best_level": 0,
      "best_genome_coverage": 0.00506842372022301,
      "best_relevance_rank": 72,
      "n_levels": 2,
      "tree": "transcription_factors",
      "tree_code": "ko03000",
      "best_interpro_type": null
    },
    "brite:secretion": {
      "best_level": 0,
      "best_genome_coverage": 0.00456158134820071,
      "best_relevance_rank": 73,
      "n_levels": 2,
      "tree": "secretion",
      "tree_code": "ko02044",
      "best_interpro_type": null
    },
    "brite:two_component": {
      "best_level": 0,
      "best_genome_coverage": 0.0030410542321338066,
      "best_relevance_rank": 78,
      "n_levels": 1,
      "tree": "two_component",
      "tree_code": "ko02022",
      "best_interpro_type": null
    }
  },
  "not_found": [],
  "not_matched": [],
  "total_matching": 81,
  "returned": 15,
  "truncated": true,
  "offset": 0,
  "results": [
    {
      "ontology_type": "tigr_role",
      "level": 1,
      "relevance_rank": 1,
      "n_terms_with_genes": 79,
      "n_genes_at_level": 1731,
      "genome_coverage": 0.8773441459706032,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 7.0,
      "median_genes_per_term": 13.0,
      "q3_genes_per_term": 24.0,
      "max_genes_per_term": 456,
      "n_levels_in_ontology": 2,
      "best_effort_share": null
    },
    {
      "ontology_type": "cyanorak_role",
      "level": 1,
      "relevance_rank": 2,
      "n_terms_with_genes": 69,
      "n_genes_at_level": 1438,
      "genome_coverage": 0.728839330968069,
      "min_genes_per_term": 5,
      "q1_genes_per_term": 9.0,
      "median_genes_per_term": 14.0,
      "q3_genes_per_term": 23.0,
      "max_genes_per_term": 340,
      "n_levels_in_ontology": 3,
      "best_effort_share": null
    },
    {
      "ontology_type": "tigr_role",
      "level": 0,
      "relevance_rank": 3,
      "n_terms_with_genes": 19,
      "n_genes_at_level": 1763,
      "genome_coverage": 0.8935631018753167,
      "min_genes_per_term": 7,
      "q1_genes_per_term": 39.5,
      "median_genes_per_term": 76.0,
      "q3_genes_per_term": 125.5,
      "max_genes_per_term": 456,
      "n_levels_in_ontology": 2,
      "best_effort_share": null
    },
    ...
  ]
}
```

### Example 9: Flat structural ontologies — PSORTb + SignalP have a single level 0

```example-call
ontology_landscape(organism="MED4", ontology=["subcellular_localization", "signal_peptide_type"])
```

*Flat ontologies contribute at most one row each (`level: 0`, `n_levels_in_ontology: 1`). Only categories with at least `min_gene_set_size` genes in the organism count towards `n_terms_with_genes`, so a small N here is expected.*

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "organism_gene_count": 1973,
  "n_ontologies": 2,
  "by_ontology": {
    "subcellular_localization": {
      "best_level": 0,
      "best_genome_coverage": 0.1875316776482514,
      "best_relevance_rank": 1,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    },
    "signal_peptide_type": {
      "best_level": 0,
      "best_genome_coverage": 0.05423213380638622,
      "best_relevance_rank": 2,
      "n_levels": 1,
      "tree": null,
      "tree_code": null,
      "best_interpro_type": null
    }
  },
  "not_found": [],
  "not_matched": [],
  "total_matching": 2,
  "returned": 2,
  "truncated": false,
  "offset": 0,
  "results": [
    {
      "ontology_type": "subcellular_localization",
      "level": 0,
      "relevance_rank": 1,
      "n_terms_with_genes": 4,
      "n_genes_at_level": 370,
      "genome_coverage": 0.1875316776482514,
      "min_genes_per_term": 6,
      "q1_genes_per_term": 9.0,
      "median_genes_per_term": 10.5,
      "q3_genes_per_term": 94.0,
      "max_genes_per_term": 343,
      "n_levels_in_ontology": 1,
      "best_effort_share": null
    },
    {
      "ontology_type": "signal_peptide_type",
      "level": 0,
      "relevance_rank": 2,
      "n_terms_with_genes": 2,
      "n_genes_at_level": 107,
      "genome_coverage": 0.05423213380638622,
      "min_genes_per_term": 15,
      "q1_genes_per_term": 34.25,
      "median_genes_per_term": 53.5,
      "q3_genes_per_term": 72.75,
      "max_genes_per_term": 92,
      "n_levels_in_ontology": 1,
      "best_effort_share": null
    }
  ]
}
```

### Example 10: Weight by experiments (coverage of quantified genes)

```
Step 1: list_experiments(organism="MED4", table_scope=["all_detected_genes"])
        -> collect experiment_ids

Step 2: ontology_landscape(
          organism="MED4",
          experiment_ids=[ids from Step 1],
        )
        -> rows ranked by median_exp_coverage x size_factor;
           min_exp_coverage and max_exp_coverage reveal per-experiment spread
```

## Chaining patterns

```
ontology_landscape -> genes_by_ontology(level=N) -> pathway_enrichment
list_experiments -> ontology_landscape(experiment_ids=...)
ontology_landscape(ontology='interpro', ...) -> pathway_enrichment(ontology='interpro', interpro_type=..., level=...) (interpro_type is required on interpro enrichment)
ontology_landscape(ontology='merops', call_class=['peptidase']) -> genes_by_ontology(ontology='merops', call_class=['peptidase'], level=...) -> pathway_enrichment(ontology='merops', call_class=['peptidase'], ...)
```

## Common mistakes

- Don't pick a level by term-size stats alone -- always check genome_coverage. An ontology may have appealing median term size at a level that covers only 18% of the genome.

- Top-ranked flat ontologies (cog_category, ncbifam) are valid enrichment surfaces but offer no level choice. For hierarchical drill-down, filter results to rows where n_levels_in_ontology > 1. Rows carry `level` only — the meaning of each level (`tc_class`, `tigr_mainrole`, ...) is documented per ontology at docs://ontologies/{key}; there is no `level_kind` column here.

- KEGG has ~40% orphan KOs lacking pathway membership. If L3 coverage is substantially higher than L0-L2 coverage, the gap is structural -- those genes have KO-level annotations only.

- For GO BP, best_effort_share is typically 30-80% at useful levels (L3-L5). This is normal GO-DAG geometry (min-path != max-path), not a data quality issue.

- Stats reflect only terms with min_gene_set_size <= genes <= max_gene_set_size (default 5-500). If you pass min_gene_set_size=1, coverage and term counts will be higher but include terms too small or large for meaningful enrichment.

```mistake
results[0]['rank']  # AttributeError
```

```correction
results[0]['relevance_rank']
```

- BRITE rows are always broken down per tree — each row carries `tree` / `tree_code`, and `by_ontology` keys them as `brite:<tree>` (never a pooled `brite` entry). `tree=` merely restricts the fan-out to one tree (e.g. `tree='transporters'`). Use `list_filter_values('brite_tree')` to discover available trees.

- Default surveys all 17 ontologies (`go_bp`, `go_mf`, `go_cc`, `ec`, `kegg`, `cog_category`, `cyanorak_role`, `tigr_role`, `pfam`, `brite`, `tcdb`, `cazy`, `subcellular_localization`, `signal_peptide_type`, `interpro`, `ncbifam`, `merops`). Pass `ontology=[...]` (str or list) to restrict the fan-out.

- `call_class` (merops-only) and `interpro_type` (interpro-only; scopes to one InterPro type instead of the per-type breakdown) narrow landscape term-size stats the same way they narrow `genes_by_ontology` / enrichment gene sets — pass them here first to check what a trust-filtered enrichment run will actually test.

- InterPro rows break down by `interpro_type` the same way BRITE rows break down by `tree` — without a specific `interpro_type`, `results` mixes all 8 InterPro types (HOMOLOGOUS_SUPERFAMILY, DOMAIN, FAMILY, REPEAT, CONSERVED_SITE, ACTIVE_SITE, BINDING_SITE, PTM), each carrying `interpro_type` per row (`by_ontology` still has a single `interpro` key).

- CAZy is a small ontology (64 nodes — 6 classes + 58 families). With default `min_gene_set_size=5`, only a handful of CAZy terms ever pass the filter — typically 1–2 rows per organism. This is expected, not a bug. Pass `min_gene_set_size=1` to see all CAZy classes/families.

- TCDB and CAZy use organism-scoped term-size stats just like the other ontologies. TCDB has 5 levels (`tc_class`...`tc_specificity`); CAZy has 2 (`cazy_class`, `cazy_family`).

```mistake
result['total_rows']  # KeyError
```

```correction
result['total_matching']
```

- Default `limit=15` returns the top-ranked rows; pass `limit=None` for every row, or an explicit integer to page — check the response envelope's `truncated` field to know whether more rows exist beyond what was returned.

- PSORTb / SignalP are flat (single `level=0`) — at most one `results` row and one `by_ontology` entry each. If only a few of their categories pass the default `min_gene_set_size=5` filter, the small `n_terms_with_genes` is expected (categories range from tens to tens of thousands of genes KG-wide; per organism it's much smaller).

- `relevance_rank` is the composite score (rank 1 = best): genome coverage times a size factor that peaks at a mid-sized median genes-per-term. Rank the rows against each other; the score is not a probability.

- `informative_only` defaults True here — pass False to survey the full term set, which rebaselines the coverage stats. `call_class` / `interpro_type` are part of the annotation-trust surface: see docs://analysis/annotation_evidence.

## Package import equivalent

```python
from multiomics_explorer import ontology_landscape

result = ontology_landscape(organism=...)
# returns dict with keys: organism_name, organism_gene_count, n_ontologies, by_ontology, not_found, not_matched, total_matching, returned, truncated, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
