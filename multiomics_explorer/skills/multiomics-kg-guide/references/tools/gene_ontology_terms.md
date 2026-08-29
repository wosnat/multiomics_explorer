# gene_ontology_terms

## What it does

Reverse-lookup: gene locus_tags → ontology annotations (one row per gene × term).

`mode='leaf'` (default) returns the most specific annotations only —
redundant ancestors are excluded. `mode='rollup'` walks UP to ancestors
at the given level. Single-organism enforced. `ontology` accepts a
list; when a trust filter/facet is carried by only some of the
requested ontologies, the rest drop into `skipped_ontologies` with
a warning.

[TRUST] `sources` / `evidence` / `max_tier` / `min_evidence_score` /
`call_class` / `interpro_type` filter on the per-edge trust profile;
`include_superseded` (tcdb leaf mode) also surfaces less-specific
attachments. Defaults never filter. See docs://analysis/annotation_evidence.

Routing: for the forward direction (term → genes, with hierarchy
expansion) use `genes_by_ontology`; for term discovery by text use
`search_ontology`.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| organism | string | — | Organism: word-based, case-insensitive match on preferred_name + name_synonyms ('MED4' works; ambiguous match raises). Required — single-valued. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') \| list[string ('go_bp', 'go_mf', 'go_cc', 'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops')] \| None | None | Filter to one ontology, or a list of ontologies (trust filters/facets shape all-or-skip-or-raise per docs://guide/conventions). None returns all. |
| mode | string ('leaf', 'rollup') | leaf | 'leaf' returns most-specific annotations (default). 'rollup' walks up to ancestors at the given level. |
| level | int \| None | None | Hierarchy level (0 = broadest). In leaf mode: filter to leaves at this level. In rollup mode: required — target ancestor level. See docs://guide/conventions. |
| tree | string \| None | None | BRITE tree name filter. Narrows brite and leaves any other ontology in the list untouched; raises when brite is not among them. See docs://guide/conventions for the BRITE-tree scoping rule. |
| informative_only | bool | False | When True, exclude terms flagged uninformative in KG (e.g. KEGG KO 'uncharacterized protein' terms, GO root go:0008150; global KEGG maps like ko01100 are not flagged yet). Term-side filter only — never restricts the gene set. Default False (opt-in). |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include organism_name per row. |
| sources | list[string] \| None | None | Keep rows whose edge sources[] contains any of these values (e.g. ['eggnog']). Valid on the 14 functional-edge ontologies (not PSORTb / SignalP). Default None never filters. See list_filter_values(filter_type='sources'). |
| evidence | list[string] \| None | None | Keep rows whose compact evidence ladder value is in this list (read the value; rung assignment is per ontology — see docs://analysis/annotation_evidence). Valid on the 14 functional-edge ontologies. Default None never filters. |
| max_tier | int \| None | None | Keep rows with edge tier <= this value OR tier IS NULL (diamond truncation depth, 1-3; tier-null edges are always kept - see by_tier's null bucket). Valid on tcdb, merops only. |
| min_evidence_score | float \| None | None | Keep rows with edge evidence_score >= this cutoff (composite trust score, 0-1; the only native-scalar cutoff allowed). Valid on go_bp/mf/cc, ec, pfam, cazy, tcdb, merops. Envelope adds evidence_score_signals when set. |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; leaving unfiltered mixes in catalytically-dead homologs (nonpeptidase_homolog) - the envelope warns when it does. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |
| include_superseded | bool | False | TCDB leaf mode only: when True, also include rows whose gene->term attachment is less specific ('superseded') rather than the deepest ('most_specific'). Default False. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_genes, total_terms, by_ontology, by_term, terms_per_gene_min, terms_per_gene_max, terms_per_gene_median, returned, offset, truncated, not_found, no_terms, trust_axes, by_evidence, by_tier, by_sources, by_call_class, evidence_score_stats, filters_applied, skipped_ontologies, warnings, results
```

- **total_matching** (int): Total gene × term annotation rows
- **total_genes** (int): Distinct genes with at least one term
- **total_terms** (int): Distinct terms across all input genes
- **by_ontology** (list[OntologyTypeBreakdown]): Per ontology type: term + gene counts, sorted by term_count desc
- **by_term** (list[TermBreakdown]): Gene counts per term, sorted desc — shows shared terms across input genes
- **terms_per_gene_min** (int): Fewest leaf terms on any gene with terms (e.g. 1)
- **terms_per_gene_max** (int): Most leaf terms on any gene with terms (e.g. 15)
- **terms_per_gene_median** (float): Median leaf terms per gene with terms (e.g. 6.0)
- **returned** (int): Results in this response (0 when summary=true)
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > returned
- **not_found** (list[string]): Input locus_tags not in KG
- **no_terms** (list[string]): Input locus_tags in KG but with no terms for queried ontology
- **trust_axes** (object): Trust axes carried per queried ontology.
- **by_evidence** (list[object]): Rollup of the compact evidence column over every matching row, not just the page you are reading. Empty with summary=true, which fetches no rows.
- **by_tier** (list[object]): Rollup of tier over every matching row; carries an explicit 'null' bucket. Present in compact mode too, where tier itself is not on the row. Empty with summary=true.
- **by_sources** (list[object]): Membership counts per source value over every matching row. Empty with summary=true.
- **by_call_class** (list[object]): Rollup of MEROPS call_class over every matching row (merops only). Empty with summary=true.
- **evidence_score_stats** (object | None): {min, median, max, n_null} over evidence_score across every matching row. All-null with summary=true.
- **evidence_score_signals** (object | None): Fired ControlledVocabulary signals per edge_type; present only when min_evidence_score was set.
- **filters_applied** (object): Echo of the trust filters that were actually set on this call.
- **skipped_ontologies** (list[object]): Multi-ontology: [{ontology, reason}] for ontologies dropped because a filter/facet only some of the queried ontologies own.
- **warnings** (list[string]): Auto-warnings, incl. skipped-ontology and trust-cutoff notices.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| term_id | string | Ontology term ID (e.g. 'go:0006260') |
| term_name | string | Term name (e.g. 'DNA replication') |
| level | int | Hierarchy level of this term (0 = broadest) |
| is_informative | bool | True iff term is not flagged is_uninformative (positive framing; coerced from sparse '<term>.is_uninformative' KG flag) |
| ontology_type | string \| None (optional) | Ontology type when querying all (e.g. 'go_bp') |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |
| localization_score | float \| None (optional) | PSORTb confidence score (sparse: only set when ontology='subcellular_localization'). Range 7.5–10.0. |
| signal_peptide_probability | float \| None (optional) | SignalP winning-class probability (sparse: only set when ontology='signal_peptide_type'). Range 0–1. |
| signal_peptide_cleavage_site | int \| None (optional) | SignalP-predicted cleavage residue position (sparse: only set when ontology='signal_peptide_type'; absent when SignalP reports no cleavage site). |
| signal_peptide_cleavage_probability | float \| None (optional) | SignalP cleavage-site probability (sparse: only set when ontology='signal_peptide_type' and cleavage_site present). |
| evidence | string \| None (optional) | Compact trust ladder value (read it as-is; rung assignment is per ontology — see docs://analysis/annotation_evidence). Present on the 14 functional-edge ontologies; null on PSORTb/SignalP. |
| call_class | string \| None (optional) | MEROPS peptidase call (sparse: merops only). |
| interpro_type | string \| None (optional) | InterPro entry type (sparse: interpro only). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| sources | list[string] \| None (optional) | Provenance tags on this edge (verbose only; sparse). |
| evidence_score | float \| None (optional) | Composite trust score in [0,1] (verbose only; sparse). |
| tier | int \| None (optional) | Diamond truncation depth 1-3 (verbose only; sparse: tcdb, merops). |
| attachment_depth | string \| None (optional) | TCDB attachment depth: 'most_specific' or 'superseded' (verbose only; sparse: tcdb only). |
| confidence_score | float \| None (optional) | Native rank score (verbose only; sparse: tcdb, merops). |
| source_agreement | string \| None (optional) | TCDB two-source agreement detail (verbose only; sparse: tcdb only). |
| pfam_support | string \| None (optional) | Pfam-domain corroboration detail (verbose only; sparse: tcdb, merops). |
| go_support | string \| None (optional) | GO corroboration detail (verbose only; sparse: tcdb only). |
| identity | float \| None (optional) | Alignment percent identity (verbose only; sparse: tcdb, merops). |
| qcov | float \| None (optional) | Query coverage fraction (verbose only; sparse: tcdb, merops). |
| evalue | float \| None (optional) | Alignment e-value (verbose only; sparse). Never a filter cutoff. |
| consensus_n | int \| None (optional) | Corroborating-calls count (verbose only; sparse: tcdb, merops). |
| best_hit_kind | string \| None (optional) | MEROPS best-hit classification (verbose only; sparse: merops only). |
| best_hit_id | string \| None (optional) | MEROPS best-hit identifier (verbose only; sparse: merops only). |
| libraries | list[string] \| None (optional) | InterPro member-database libraries (verbose only; sparse: interpro only). |
| evalue_library | string \| None (optional) | InterPro per-library e-value detail (verbose only; sparse: interpro only). |
| match_count | int \| None (optional) | InterPro match-segment count (verbose only; sparse: interpro only). |
| start | int \| None (optional) | Match start coordinate (verbose only; sparse: interpro, ncbifam). |
| end | int \| None (optional) | Match end coordinate (verbose only; sparse: interpro, ncbifam). |
| bit_score | float \| None (optional) | NCBIfam alignment bit score (verbose only; sparse: ncbifam only). |
| organism_name | string \| None (optional) | Organism (e.g. 'Prochlorococcus MED4') |

## Few-shot examples

### Example 1: GO biological process terms for a gene

```example-call
gene_ontology_terms(locus_tags=["PMM0001"], organism="MED4", ontology="go_bp")
```

```example-response
{
  "total_matching": 1,
  "total_genes": 1,
  "total_terms": 1,
  "by_ontology": [{"ontology_type": "go_bp", "term_count": 1, "gene_count": 1, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "go:0006271",
      "term_name": "DNA strand elongation involved in DNA replication",
      "level": 7,
      "ontology_type": "go_bp",
      "count": 1
    }
  ],
  "terms_per_gene_min": 1,
  "terms_per_gene_max": 1,
  "terms_per_gene_median": 1.0,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"go_bp": ["sources", "evidence", "evidence_score"]},
  "by_evidence": [{"evidence": "curated", "count": 1}],
  "by_tier": [],
  "by_sources": [{"source": "uniprot", "count": 1}],
  "by_call_class": [],
  "evidence_score_stats": {"min": 0.667, "median": 0.667, "max": 0.667, "n_null": 0},
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0001",
      "term_id": "go:0006271",
      "term_name": "DNA strand elongation involved in DNA replication",
      "level": 7,
      "is_informative": true,
      "evidence": "curated"
    }
  ]
}
```

### Example 2: All ontology annotations for a gene

```example-call
gene_ontology_terms(locus_tags=["PMM0001"], organism="MED4")
```

### Example 3: Batch annotations with summary only

```example-call
gene_ontology_terms(locus_tags=["PMM0001", "PMM0845"], organism="MED4", summary=True)
```

### Example 4: Rollup to BRITE category level

```example-call
gene_ontology_terms(locus_tags=["PMM0001", "PMM0845"], organism="MED4", ontology="brite", mode="rollup", level=1, tree="transporters")
```

### Example 5: CAZy class membership rollup (which CAZy class does each gene belong to?)

```example-call
gene_ontology_terms(locus_tags=["PMM0584", "PMM1322"], organism="MED4", ontology="cazy", mode="rollup", level=0)
```

```example-response
{
  "total_matching": 4,
  "total_genes": 2,
  "total_terms": 2,
  "by_ontology": [{"ontology_type": "cazy", "term_count": 4, "gene_count": 2, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "cazy:GH",
      "term_name": "Glycoside Hydrolases",
      "level": 0,
      "ontology_type": "cazy",
      "count": 2
    },
    {
      "term_id": "cazy:CBM",
      "term_name": "Carbohydrate-Binding Modules",
      "level": 0,
      "ontology_type": "cazy",
      "count": 2
    }
  ],
  "terms_per_gene_min": 2,
  "terms_per_gene_max": 2,
  "terms_per_gene_median": 2.0,
  "returned": 4,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"cazy": ["sources", "evidence", "evidence_score"]},
  "by_evidence": [{"evidence": "curated", "count": 4}],
  "by_tier": [],
  "by_sources": [{"source": "eggnog", "count": 4}, {"source": "interproscan", "count": 2}],
  "by_call_class": [],
  "evidence_score_stats": {"min": 0.667, "median": 0.8335, "max": 1.0, "n_null": 0},
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0584",
      "term_id": "cazy:CBM",
      "term_name": "Carbohydrate-Binding Modules",
      "level": 0,
      "is_informative": true,
      "evidence": "curated"
    },
    {
      "locus_tag": "PMM0584",
      "term_id": "cazy:GH",
      "term_name": "Glycoside Hydrolases",
      "level": 0,
      "is_informative": true,
      "evidence": "curated"
    },
    {
      "locus_tag": "PMM1322",
      "term_id": "cazy:CBM",
      "term_name": "Carbohydrate-Binding Modules",
      "level": 0,
      "is_informative": true,
      "evidence": "curated"
    },
    ...
  ]
}
```

### Example 6: TCDB family annotations for a gene

```example-call
gene_ontology_terms(locus_tags=["PMM0402"], organism="MED4", ontology="tcdb")
```

### Example 7: Multiple ontologies in one call (ontology now accepts a list)

```example-call
gene_ontology_terms(locus_tags=["PMM0392"], organism="MED4", ontology=["tcdb", "merops"])
```

```example-response
{
  "total_matching": 7,
  "total_genes": 1,
  "total_terms": 7,
  "by_ontology": [{"ontology_type": "tcdb", "term_count": 7, "gene_count": 1, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "tcdb:3.A.1.33",
      "term_name": "The Methylthioadenosine (MTA) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.32",
      "term_name": "The Cobalamin Precursor (B 12 -P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.31",
      "term_name": "The Unknown-ABC1 (U-ABC1) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.30",
      "term_name": "The Thiamin Precursor (Thi-P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.29",
      "term_name": "The Methionine Precursor (Met-P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    ...
  ],
  "terms_per_gene_min": 7,
  "terms_per_gene_max": 7,
  "terms_per_gene_median": 7.0,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {
    "tcdb": ["sources", "evidence", "evidence_score", "tier"],
    "merops": ["sources", "evidence", "evidence_score", "tier"]
  },
  "by_evidence": [{"evidence": "family_inferred", "count": 7}],
  "by_tier": [{"tier": "null", "count": 7}],
  "by_sources": [{"source": "eggnog", "count": 7}],
  "by_call_class": [],
  "evidence_score_stats": {"min": 0.6, "median": 0.8, "max": 0.8, "n_null": 0},
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.25",
      "term_name": "The Biotin Uptake Transporter (BioMNY) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred"
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.28",
      "term_name": "The Queuosine (Queuosine) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred"
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.29",
      "term_name": "The Methionine Precursor (Met-P) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred"
    },
    ...
  ]
}
```

### Example 8: TCDB leaf mode — most-specific attachments only (default)

```example-call
gene_ontology_terms(locus_tags=["PMM0392"], organism="MED4", ontology=["tcdb"], mode="leaf", verbose=True)
```

*Default mode='leaf' on tcdb applies `attachment_depth='most_specific'` under the hood. PMM0392 carries 8 TCDB edges — the ABC superfamily (tcdb:3.A.1) plus seven of its subfamilies — and the superfamily edge is superseded by the deeper ones, so 7 rows come back. `most_specific` is not unique per gene: every deepest attachment survives. `attachment_depth` is verbose-only (compact rows omit it).*

```example-response
{
  "total_matching": 7,
  "total_genes": 1,
  "total_terms": 7,
  "by_ontology": [{"ontology_type": "tcdb", "term_count": 7, "gene_count": 1, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "tcdb:3.A.1.33",
      "term_name": "The Methylthioadenosine (MTA) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.32",
      "term_name": "The Cobalamin Precursor (B 12 -P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.31",
      "term_name": "The Unknown-ABC1 (U-ABC1) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.30",
      "term_name": "The Thiamin Precursor (Thi-P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.29",
      "term_name": "The Methionine Precursor (Met-P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    ...
  ],
  "terms_per_gene_min": 7,
  "terms_per_gene_max": 7,
  "terms_per_gene_median": 7.0,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"tcdb": ["sources", "evidence", "evidence_score", "tier"]},
  "by_evidence": [{"evidence": "family_inferred", "count": 7}],
  "by_tier": [{"tier": "null", "count": 7}],
  "by_sources": [{"source": "eggnog", "count": 7}],
  "by_call_class": [],
  "evidence_score_stats": {"min": 0.6, "median": 0.8, "max": 0.8, "n_null": 0},
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.25",
      "term_name": "The Biotin Uptake Transporter (BioMNY) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "sources": ["eggnog"],
      "evidence_score": 0.8,
      "tier": null,
      "attachment_depth": "most_specific",
      "confidence_score": null,
      "source_agreement": "both_sources",
      "pfam_support": "corroborated",
      "go_support": "corroborated",
      "identity": null,
      "qcov": null,
      "evalue": null,
      "consensus_n": null,
      "organism_name": "Prochlorococcus MED4"
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.28",
      "term_name": "The Queuosine (Queuosine) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "sources": ["eggnog"],
      "evidence_score": 0.6,
      "tier": null,
      "attachment_depth": "most_specific",
      "confidence_score": null,
      "source_agreement": "both_sources",
      "pfam_support": "corroborated",
      "go_support": "uncorroborated",
      "identity": null,
      "qcov": null,
      "evalue": null,
      "consensus_n": null,
      "organism_name": "Prochlorococcus MED4"
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.29",
      "term_name": "The Methionine Precursor (Met-P) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "sources": ["eggnog"],
      "evidence_score": 0.8,
      "tier": null,
      "attachment_depth": "most_specific",
      "confidence_score": null,
      "source_agreement": "both_sources",
      "pfam_support": "corroborated",
      "go_support": "corroborated",
      "identity": null,
      "qcov": null,
      "evalue": null,
      "consensus_n": null,
      "organism_name": "Prochlorococcus MED4"
    },
    ...
  ]
}
```

### Example 9: TCDB leaf mode with include_superseded — see the collapsed rows too

```example-call
gene_ontology_terms(locus_tags=["PMM0392"], organism="MED4", ontology=["tcdb"], mode="leaf", include_superseded=True, verbose=True)
```

*include_superseded=True adds back the rows most_specific mode drops — each labelled attachment_depth='superseded' (PMM0392: 7 → 8 rows). 'Superseded' means less specific, not wrong: it is a real annotation, just not the gene's deepest call for that lineage.*

```example-response
{
  "total_matching": 8,
  "total_genes": 1,
  "total_terms": 8,
  "by_ontology": [{"ontology_type": "tcdb", "term_count": 8, "gene_count": 1, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "tcdb:3.A.1",
      "term_name": "The ATP-binding Cassette (ABC) Superfamily",
      "level": 2,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.33",
      "term_name": "The Methylthioadenosine (MTA) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.32",
      "term_name": "The Cobalamin Precursor (B 12 -P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.31",
      "term_name": "The Unknown-ABC1 (U-ABC1) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.30",
      "term_name": "The Thiamin Precursor (Thi-P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    ...
  ],
  "terms_per_gene_min": 8,
  "terms_per_gene_max": 8,
  "terms_per_gene_median": 8.0,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"tcdb": ["sources", "evidence", "evidence_score", "tier"]},
  "by_evidence": [{"evidence": "family_inferred", "count": 7}, {"evidence": "homology", "count": 1}],
  "by_tier": [{"tier": "null", "count": 7}, {"tier": 3, "count": 1}],
  "by_sources": [{"source": "eggnog", "count": 8}, {"source": "tcdb_diamond", "count": 1}],
  "by_call_class": [],
  "evidence_score_stats": {"min": 0.6, "median": 0.8, "max": 0.8, "n_null": 0},
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1",
      "term_name": "The ATP-binding Cassette (ABC) Superfamily",
      "level": 2,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "homology",
      "sources": ["eggnog", "tcdb_diamond"],
      "evidence_score": 0.8,
      "tier": 3,
      "attachment_depth": "superseded",
      "confidence_score": 0.1545,
      "source_agreement": "both_sources",
      "pfam_support": "corroborated",
      "go_support": "corroborated",
      "identity": 26.4,
      "qcov": 83.6,
      "evalue": 1.78e-22,
      "consensus_n": 2,
      "organism_name": "Prochlorococcus MED4"
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.25",
      "term_name": "The Biotin Uptake Transporter (BioMNY) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "sources": ["eggnog"],
      "evidence_score": 0.8,
      "tier": null,
      "attachment_depth": "most_specific",
      "confidence_score": null,
      "source_agreement": "both_sources",
      "pfam_support": "corroborated",
      "go_support": "corroborated",
      "identity": null,
      "qcov": null,
      "evalue": null,
      "consensus_n": null,
      "organism_name": "Prochlorococcus MED4"
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.28",
      "term_name": "The Queuosine (Queuosine) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "sources": ["eggnog"],
      "evidence_score": 0.6,
      "tier": null,
      "attachment_depth": "most_specific",
      "confidence_score": null,
      "source_agreement": "both_sources",
      "pfam_support": "corroborated",
      "go_support": "uncorroborated",
      "identity": null,
      "qcov": null,
      "evalue": null,
      "consensus_n": null,
      "organism_name": "Prochlorococcus MED4"
    },
    ...
  ]
}
```

### Example 10: MEROPS leaf annotations with call_class and confidence

```example-call
gene_ontology_terms(locus_tags=["MIT1002_03660"], organism="MIT1002", ontology=["merops"], verbose=True)
```

```example-response
{
  "total_matching": 1,
  "total_genes": 1,
  "total_terms": 1,
  "by_ontology": [{"ontology_type": "merops", "term_count": 1, "gene_count": 1, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "merops.family:T01B",
      "term_name": "HslV component of HslUV peptidase",
      "level": 2,
      "ontology_type": "merops",
      "count": 1
    }
  ],
  "terms_per_gene_min": 1,
  "terms_per_gene_max": 1,
  "terms_per_gene_median": 1.0,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"merops": ["sources", "evidence", "evidence_score", "tier"]},
  "by_evidence": [{"evidence": "homology", "count": 1}],
  "by_tier": [{"tier": 2, "count": 1}],
  "by_sources": [{"source": "merops_diamond", "count": 1}],
  "by_call_class": [{"call_class": "peptidase", "count": 1}],
  "evidence_score_stats": {"min": 1.0, "median": 1.0, "max": 1.0, "n_null": 0},
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "MIT1002_03660",
      "term_id": "merops.family:T01B",
      "term_name": "HslV component of HslUV peptidase",
      "level": 2,
      "is_informative": true,
      "ontology_type": "merops",
      "evidence": "homology",
      "call_class": "peptidase",
      "sources": ["merops_diamond"],
      "evidence_score": 1.0,
      "tier": 2,
      "confidence_score": 0.6987,
      "pfam_support": "corroborated",
      "identity": 82.7,
      "qcov": 99.4,
      "evalue": 1.13e-98,
      "consensus_n": 4,
      "best_hit_kind": "holotype",
      "best_hit_id": "T01.006",
      "organism_name": "Alteromonas macleodii MIT1002"
    }
  ]
}
```

### Example 11: Filter by evidence + max_tier (skip/raise matrix — multi-ontology)

```example-call
gene_ontology_terms(locus_tags=["PMM0392"], organism="MED4", ontology=["tcdb", "kegg"], max_tier=2)
```

```example-response
{
  "total_matching": 7,
  "total_genes": 1,
  "total_terms": 7,
  "by_ontology": [{"ontology_type": "tcdb", "term_count": 7, "gene_count": 1, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "tcdb:3.A.1.33",
      "term_name": "The Methylthioadenosine (MTA) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.32",
      "term_name": "The Cobalamin Precursor (B 12 -P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.31",
      "term_name": "The Unknown-ABC1 (U-ABC1) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.30",
      "term_name": "The Thiamin Precursor (Thi-P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.29",
      "term_name": "The Methionine Precursor (Met-P) Family",
      "level": 3,
      "ontology_type": "tcdb",
      "count": 1
    },
    ...
  ],
  "terms_per_gene_min": 7,
  "terms_per_gene_max": 7,
  "terms_per_gene_median": 7.0,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"tcdb": ["sources", "evidence", "evidence_score", "tier"]},
  "by_evidence": [{"evidence": "family_inferred", "count": 7}],
  "by_tier": [{"tier": "null", "count": 7}],
  "by_sources": [{"source": "eggnog", "count": 7}],
  "by_call_class": [],
  "evidence_score_stats": {"min": 0.6, "median": 0.8, "max": 0.8, "n_null": 0},
  "evidence_score_signals": null,
  "filters_applied": {"max_tier": 2},
  "skipped_ontologies": [{"ontology": "kegg", "reason": "does not carry the max_tier filter"}],
  "warnings": [
    "Dropped 1 ontologies that do not carry max_tier: kegg. Re-run without max_tier to see them.",
    "max_tier=2 kept 7 rows that carry no tier — single-source edges are never truncated, so a null tier is not a tier-1 c..."
  ],
  "results": [
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.25",
      "term_name": "The Biotin Uptake Transporter (BioMNY) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred"
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.28",
      "term_name": "The Queuosine (Queuosine) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred"
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.29",
      "term_name": "The Methionine Precursor (Met-P) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred"
    },
    ...
  ]
}
```

### Example 12: Filter out uninformative terms (KOs named "uncharacterized protein")

```example-call
gene_ontology_terms(locus_tags=["PMM0001"], organism="Prochlorococcus MED4", ontology="kegg", informative_only=True)
```

*Each result row carries `is_informative: bool` (always populated; coalesce of the sparse term-side `is_uninformative='true'` flag). Genome-wide effect on MED4 KEGG leaf rows: 1124 → 1094 with informative_only=True (30 rows, all KO-level — KEGG pathway maps are never flagged). PMM0001's single KO is informative, so its row count is unchanged.*

```example-response
{
  "total_matching": 1,
  "total_genes": 1,
  "total_terms": 1,
  "by_ontology": [{"ontology_type": "kegg", "term_count": 1, "gene_count": 1, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "kegg.orthology:K02338",
      "term_name": "dnaN; DNA polymerase III subunit beta [EC:2.7.7.7]",
      "level": 3,
      "ontology_type": "kegg",
      "count": 1
    }
  ],
  "terms_per_gene_min": 1,
  "terms_per_gene_max": 1,
  "terms_per_gene_median": 1.0,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"kegg": ["sources", "evidence"]},
  "by_evidence": [{"evidence": "family_inferred", "count": 1}],
  "by_tier": [],
  "by_sources": [{"source": "eggnog", "count": 1}],
  "by_call_class": [],
  "evidence_score_stats": {"min": null, "median": null, "max": null, "n_null": 0},
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0001",
      "term_id": "kegg.orthology:K02338",
      "term_name": "dnaN; DNA polymerase III subunit beta [EC:2.7.7.7]",
      "level": 3,
      "is_informative": true,
      "evidence": "family_inferred"
    }
  ]
}
```

### Example 13: Per-gene SignalP call with cleavage info

```example-call
gene_ontology_terms(locus_tags=["PMM0006", "PMM0296"], ontology="signal_peptide_type", organism="MED4", mode="leaf", verbose=True)
```

*SignalP is 1:1 — at most one row per gene; genes with no confident call land in `no_terms`. `signal_peptide_probability` / `signal_peptide_cleavage_*` are verbose-only.*

```example-response
{
  "total_matching": 2,
  "total_genes": 2,
  "total_terms": 2,
  "by_ontology": [
    {
      "ontology_type": "signal_peptide_type",
      "term_count": 2,
      "gene_count": 2,
      "tree": null,
      "tree_code": null
    }
  ],
  "by_term": [
    {
      "term_id": "signalp_SP",
      "term_name": "Signal peptide (Sec/SPI)",
      "level": 0,
      "ontology_type": "signal_peptide_type",
      "count": 1
    },
    {
      "term_id": "signalp_LIPO",
      "term_name": "Lipoprotein signal peptide (Sec/SPII)",
      "level": 0,
      "ontology_type": "signal_peptide_type",
      "count": 1
    }
  ],
  "terms_per_gene_min": 1,
  "terms_per_gene_max": 1,
  "terms_per_gene_median": 1.0,
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"signal_peptide_type": []},
  "by_evidence": [],
  "by_tier": [],
  "by_sources": [],
  "by_call_class": [],
  "evidence_score_stats": {"min": null, "median": null, "max": null, "n_null": 0},
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0006",
      "term_id": "signalp_SP",
      "term_name": "Signal peptide (Sec/SPI)",
      "level": 0,
      "is_informative": true,
      "signal_peptide_probability": 0.542014,
      "signal_peptide_cleavage_site": 21,
      "signal_peptide_cleavage_probability": 0.3982,
      "organism_name": "Prochlorococcus MED4"
    },
    {
      "locus_tag": "PMM0296",
      "term_id": "signalp_LIPO",
      "term_name": "Lipoprotein signal peptide (Sec/SPII)",
      "level": 0,
      "is_informative": true,
      "signal_peptide_probability": 1.0,
      "signal_peptide_cleavage_site": 23,
      "signal_peptide_cleavage_probability": 0.9964,
      "organism_name": "Prochlorococcus MED4"
    }
  ]
}
```

### Example 14: From overview to ontology details

```
Step 1: gene_overview(locus_tags=["PMM0001"])
        → check annotation_types: ["go_bp", "go_mf", "kegg", "ec", ...]

Step 2: gene_ontology_terms(locus_tags=["PMM0001"], organism="MED4", ontology="go_bp")
        → get actual GO BP terms

Step 3: genes_by_ontology(ontology="go_bp", organism="MED4", term_ids=["go:0006260"])
        → find other (gene × term) pairs with same term in MED4
        (ontology + organism are required)
```

## Chaining patterns

```
gene_overview → gene_ontology_terms (check annotation_types first)
gene_ontology_terms → genes_by_ontology (reverse: term → other genes)
resolve_gene → gene_ontology_terms
gene_ontology_terms(ontology=['merops'], call_class=['peptidase']) → gene_overview to cross-check merops_classes / merops_evidence_score_max
See docs://analysis/annotation_evidence for the full trust-axis reference and rank-vs-filter guidance.
```

## Common mistakes

- Gene-anchored: locus_tags → the terms they carry. The term-anchored reverse (term → genes, hierarchy expanded DOWN, TERM2GENE for enrichment) is `genes_by_ontology`; for enrichment workflows that forward direction is canonical — see `docs://analysis/enrichment`.

- organism is required — single-valued. Locus tags must belong to the specified organism.

- ontology=None returns ALL ontology types — use ontology filter when you only need one type

- Default mode='leaf' returns only leaf (most specific) terms — ancestor terms like 'metabolic process' are excluded because they are implied by the more specific child terms

- mode='rollup' requires `level` (and optionally `ontology`). It walks UP the hierarchy from leaf annotations to the requested level, returning rolled-up (gene x ancestor-term) pairs.

- to check if a gene is connected to a broad term (e.g. 'DNA repair'), use genes_by_ontology(term_ids=[...], ontology=..., organism=...) which expands down the hierarchy — gene_ontology_terms only returns the leaf annotations

- For brite: leaf annotations are KO-level terms (same leaf as kegg). Use ontology='brite' to filter; the returned term_ids are KO IDs shared with the kegg ontology.

- Use `tree` to scope BRITE rollup to a single tree (e.g. 'transporters'). Without it, rollup mixes all BRITE trees.

- Supported ontologies: `go_bp`, `go_mf`, `go_cc`, `kegg`, `ec`, `cog_category`, `cyanorak_role`, `tigr_role`, `pfam`, `brite`, `tcdb`, `cazy`, `subcellular_localization`, `signal_peptide_type`, `interpro`, `ncbifam`, `merops`.

- `ontology` is now `str | list[str] | None` (was single-value only). With a list: a filter carried by all requested ontologies applies normally; carried by some but not all applies to those and drops the rest into `skipped_ontologies` with a warning; carried by none raises `ValueError`. An unknown ontology name always raises.

- `include_superseded=False` (default) applies TCDB's `attachment_depth='most_specific'` predicate in leaf mode — ancestor rows made redundant by a deeper attachment on the same gene are dropped. `include_superseded=True` adds them back labelled `attachment_depth='superseded'`; superseded means less specific, not incorrect. `most_specific` is not unique per gene — a gene attached to several sibling subfamilies keeps one row per subfamily (PMM0392: 7). `attachment_depth` itself is verbose-only.

- Trust filters (`sources`, `evidence`, `max_tier`, `min_evidence_score`, `call_class`) mirror `genes_by_ontology` exactly — same defaults (`None`, never filter), same per-ontology axis gating, same `ValueError` on an unsupported axis. See `docs://analysis/annotation_evidence` for the per-ontology axis table.

- Compact rows carry `evidence` on the 14 functional-edge ontologies (null on PSORTb/SignalP); `interpro_type` (interpro rows) and `call_class` (merops rows) are compact always. `sources`, `evidence_score`, `tier`, `attachment_depth` (tcdb) and native detail (`confidence_score`, `libraries`, `evalue`, `signal_peptide_*`, `localization_score`, ...) are verbose-only.

- CAZy rollup at `level=0` returns the 6 top-level classes (GH, GT, PL, CE, AA, CBM). Genes commonly belong to multiple top-level classes (e.g. a CBM-domain-containing GH); duplicates per `(gene × class)` are de-duped automatically.

- TCDB substrate-level questions ('which genes does this metabolite bind to?') chain via `genes_by_metabolite`, NOT this tool. Use `gene_ontology_terms(ontology='tcdb')` for *family*-level annotations (e.g. 'what TCDB family does PMM1129 belong to?').

## Package import equivalent

```python
from multiomics_explorer import gene_ontology_terms

result = gene_ontology_terms(locus_tags=..., organism=...)
# returns dict with keys: total_matching, total_genes, total_terms, by_ontology, by_term, terms_per_gene_min, terms_per_gene_max, terms_per_gene_median, returned, offset, truncated, not_found, no_terms, trust_axes, by_evidence, by_tier, by_sources, by_call_class, evidence_score_stats, evidence_score_signals, filters_applied, skipped_ontologies, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
