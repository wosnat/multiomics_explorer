# genes_by_ontology

## What it does

Gene × term pairs for ontology terms in ONE organism (term_ids expand down the hierarchy, level rolls up, both = scoped rollup).

Use to build TERM2GENE or list a term's genes; for a gene's own annotations use `gene_ontology_terms`, for substrate-anchored TCDB / EC `genes_by_metabolite`.
Filters: ontology, organism, term_ids, level, tree, min/max_gene_set_size, informative_only, trust filters.
Returns: by_category, by_level, top_terms, trust rollups, not_found, wrong_ontology, wrong_level; one row = (locus_tag, term_id, evidence).
docs://tools/genes_by_ontology; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') | — | Ontology for these term_ids / this level. |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Must resolve to ONE organism — an ambiguous match (e.g. a genus word) raises; see list_organisms. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'. See docs://guide/conventions for the BRITE-tree scoping rule. |
| level | int \| None | None | Hierarchy level to roll UP to (0 = broadest). At least one of `level` or `term_ids` must be provided. See docs://guide/conventions. |
| term_ids | list[string] \| None | None | Ontology term IDs (from search_ontology). Without `level`: expand DOWN from each input term. With `level`: scope rollup to these level-N terms. Bare ids are accepted (e.g. 'ko00910', 'GO:0006979') and coerced to canonical (see `resolved_aliases`). |
| min_gene_set_size | int | 5 | Exclude terms with fewer organism-scoped genes than this. Matches `ontology_landscape`'s organism-scoped convention. |
| max_gene_set_size | int | 500 | Exclude terms with more organism-scoped genes than this. Matches `ontology_landscape`'s organism-scoped convention. Pass a large value (e.g. 100000) to disable. |
| informative_only | bool | False | True drops terms the KG flags uninformative (roots, catch-alls). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's full page, docs://tools/{tool}/full. |
| sources | list[string] \| None | None | Keep rows whose edge sources[] contains any of these values. Valid on the 15 functional-edge ontologies (all but PSORTb/SignalP; brite shares kegg's edge). See list_filter_values('sources'). |
| evidence | list[string] \| None | None | Keep rows whose compact evidence-ladder value is in this list. Valid on the 15 functional-edge ontologies (all but PSORTb/SignalP; brite shares kegg's edge). See docs://analysis/annotation_evidence. |
| max_tier | int \| None | None | Keep rows with tier <= this OR tier null (1-3; e.g. TCDB eggnog). tcdb, merops only. TCDB: consensus tier on diamond_tier, identity band on diamond_best_hit; gated rows are never tier 3. Never compare tiers across kinds or ontologies. |
| min_evidence_score | float \| None | None | Keep rows with edge evidence_score >= this cutoff (0-1; the only native-scalar cutoff allowed). Valid on go_bp/mf/cc, ec, pfam, cazy, merops; TCDB carries no evidence_score (raises). |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; unfiltered mixes in catalytically-dead nonpeptidase_homolog rows. |
| tcdb_call | list[string] \| None | None | TCDB only: keep edges whose tcdb_call is in this list, applied before the representative edge is picked, so an ancestor-term row reports a surviving call kind. Values: list_filter_values('tcdb_call'). |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |
| include_weak_tcdb_hits | bool | False | TCDB only: also return one row per weak hit (tcdb_gate='below_gate', diamond only), tagged in tcdb_gate. Adds rows; default rows are unchanged. No-op for other ontologies. |
| limit | int | 50 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
ontology, organism_name, total_matching, total_genes, total_terms, total_categories, genes_per_term_min, genes_per_term_median, genes_per_term_max, terms_per_gene_min, terms_per_gene_median, terms_per_gene_max, by_category, by_level, top_terms, n_best_effort_terms, not_found, wrong_ontology, wrong_level, filtered_out, size_filtered_terms, size_filtered_genes, resolved_aliases, returned, offset, truncated, trust_axes, warnings, filters_applied, skipped_ontologies, by_evidence, by_tier, by_sources, by_call_class, by_tcdb_call, evidence_score_stats, results
```

- **ontology** (string): Echo of input ontology (e.g. 'go_bp')
- **organism_name** (string): Single organism for all results
- **total_matching** (int): (gene × term) row count matching all filters
- **total_genes** (int): Distinct genes across results
- **total_terms** (int): Distinct terms emitted
- **total_categories** (int): Distinct gene_category values
- **genes_per_term_min** (int): Fewest genes in any surviving term
- **genes_per_term_median** (float): Median genes per term
- **genes_per_term_max** (int): Most genes in any surviving term
- **terms_per_gene_min** (int): Fewest terms for any gene
- **terms_per_gene_median** (float): Median terms per gene
- **terms_per_gene_max** (int): Most terms for any gene
- **by_category** (list[OntologyCategoryBreakdown]): Distinct-gene counts per gene_category, sorted desc
- **by_level** (list[OntologyLevelBreakdown]): Per-level summary, sorted by level asc
- **top_terms** (list[OntologyTermBreakdown]): Top 5 terms by distinct-gene count, tie-break term_id asc
- **n_best_effort_terms** (int): Distinct best-effort terms (GO-only marker; 0 for other ontologies)
- **not_found** (list[string]): Input term_ids absent from the KG entirely
- **wrong_ontology** (list[string]): Input term_ids present but in a different ontology label
- **wrong_level** (list[string]): Input term_ids in the ontology but at wrong level (only when level + term_ids both set)
- **filtered_out** (list[string]): Input term_ids valid but outside [min, max]_gene_set_size
- **size_filtered_terms** (int): Terms passing every other filter but outside min/max_gene_set_size, dropped. >0 adds a warning when both bounds were left at their defaults; to enumerate all pass min_gene_set_size=1 and a large max_gene_set_size (e.g. 100000; Python also accepts None).
- **size_filtered_genes** (int): Genes found only in size-dropped terms (missing from total_genes).
- **resolved_aliases** (object): Bare term_ids (e.g. 'ko00910', 'GO:0006979') coerced to canonical CURIEs, {input: [canonical]}. Empty when none were coerced.
- **returned** (int): Rows in this response
- **offset** (int): Offset into full result set
- **truncated** (bool): True when total_matching > offset + returned
- **trust_axes** (object): Trust axes this ontology carries, e.g. {'tcdb': ['sources','evidence','tier']} (TCDB has no evidence_score).
- **warnings** (list[string]): Auto-warnings (e.g. nonpeptidase_homolog rows without a call_class filter).
- **filters_applied** (object): Echo of the trust filters that were actually set on this call.
- **skipped_ontologies** (list[object]): Always empty here (single ontology); same shape as gene_ontology_terms.skipped_ontologies.
- **by_evidence** (list[object]): Rollup of the compact evidence column over every matching row, not just the page you are reading.
- **by_tier** (list[object]): Rollup of tier over every matching row; carries an explicit 'null' bucket. Present in compact mode too, where tier itself is not on the row.
- **by_sources** (list[object]): Membership counts per source value over every matching row.
- **by_call_class** (list[object]): Rollup of MEROPS call_class over every matching row (merops only).
- **by_tcdb_call** (list[object]): Rollup of the representative tcdb_call over every matching row (tcdb only); twin of by_call_class.
- **evidence_score_stats** (object | None): {min, median, max, n_null} over evidence_score across every matching row. None for TCDB (no evidence_score).
- **evidence_score_signals** (object | None): Fired ControlledVocabulary signals per edge_type; present only when min_evidence_score was set.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN') |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III, beta subunit') |
| gene_category | string \| None (optional) | Functional category (e.g. 'Replication and repair') |
| term_id | string | Ontology term ID (e.g. 'go:0050896') |
| term_name | string | Term name (e.g. 'response to stimulus') |
| level | int | Hierarchy level of this term (0 = broadest) |
| is_informative | bool | True iff term is not flagged is_uninformative (positive framing; coerced from sparse '<term>.is_uninformative' KG flag) |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |
| evidence | string \| None (optional) | Compact trust ladder value (read it as-is; rung assignment is per ontology — see docs://analysis/annotation_evidence). Present on the 15 functional-edge ontologies; null on PSORTb/SignalP. |
| call_class | string \| None (optional) | MEROPS peptidase call (sparse: merops only). 'nonpeptidase_homolog' rows are catalytically dead. |
| tcdb_call | string \| None (optional) | TCDB call kind of the row's representative edge (precedence diamond_best_hit > diamond_tier > eggnog, then identity). Sparse: tcdb only. |
| tcdb_gate | string \| None (optional) | KG gate of the representative TCDB edge: 'direct' / 'annotated' (default rows) or 'below_gate' (only with include_weak_tcdb_hits=True). Sparse: tcdb only. |
| tcdb_calls | list[string] \| None (optional) | TCDB call kinds on the gene's gated edges along the term's lineage, in precedence order. The two diamond kinds are one run; eggnog + diamond = independent agreement. Sparse: tcdb only. |
| interpro_type | string \| None (optional) | InterPro entry type (sparse: interpro only), e.g. 'DOMAIN', 'FAMILY', 'HOMOLOGOUS_SUPERFAMILY'. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| localization_score | float \| None (optional) | PSORTb confidence score (sparse: only set when ontology='subcellular_localization'). Range 7.5–10.0. |
| signal_peptide_probability | float \| None (optional) | SignalP winning-class probability (sparse: only set when ontology='signal_peptide_type'). Range 0–1. |
| signal_peptide_cleavage_site | int \| None (optional) | SignalP-predicted cleavage residue position (sparse: only set when ontology='signal_peptide_type'; absent when SignalP reports no cleavage site). |
| signal_peptide_cleavage_probability | float \| None (optional) | SignalP cleavage-site probability (sparse: only set when ontology='signal_peptide_type' and cleavage_site present). |
| sources | list[string] \| None (optional) | Provenance tags on this edge (verbose only; sparse outside the 15 functional-edge ontologies), e.g. ['eggnog']. |
| evidence_score | float \| None (optional) | Composite trust score in [0,1] (verbose only; sparse: go_bp/mf/cc, ec, pfam, cazy, merops). |
| tier | int \| None (optional) | Diamond tier 1-3 (verbose only; sparse: tcdb, merops). TCDB: consensus tier on diamond_tier, identity band on diamond_best_hit, null on eggnog; never compare across kinds or ontologies. |
| confidence_score | float \| None (optional) | Native rank score (verbose only; sparse: merops only). |
| pfam_support | string \| None (optional) | Pfam-domain corroboration detail (verbose only; sparse: merops only). |
| identity | float \| None (optional) | Alignment percent identity (verbose only; sparse: tcdb, merops). |
| qcov | float \| None (optional) | Query coverage, percent (verbose only; sparse: tcdb, merops). |
| evalue | float \| None (optional) | Alignment e-value (verbose only; sparse: tcdb, merops, interpro, ncbifam). Never a filter cutoff. |
| consensus_n | int \| None (optional) | Number of corroborating calls in consensus (verbose only; sparse: merops only). |
| tcdb_scov | float \| None (optional) | TCDB diamond subject coverage, percent (verbose only; sparse: tcdb diamond edges). |
| tcdb_best_hit_rank | int \| None (optional) | Rank of this TCDB best hit among the gene's hits (edge `rank`; 1 = top). Not a row rank (verbose only; sparse: tcdb diamond_best_hit edges). |
| tcdb_bitscore | float \| None (optional) | TCDB diamond best-hit bit score (verbose only; sparse: tcdb diamond_best_hit edges). |
| tcdb_bitscore_ratio | float \| None (optional) | TCDB best-hit bit score relative to the top hit (verbose only; sparse: tcdb diamond_best_hit edges). |
| best_hit_kind | string \| None (optional) | MEROPS best-hit classification (verbose only; sparse: merops only). |
| best_hit_id | string \| None (optional) | MEROPS best-hit identifier (verbose only; sparse: merops only). |
| libraries | list[string] \| None (optional) | InterPro member-database libraries backing this match (verbose only; sparse: interpro only). |
| evalue_library | string \| None (optional) | InterPro per-library e-value detail (verbose only; sparse: interpro only). |
| match_count | int \| None (optional) | InterPro match-segment count (verbose only; sparse: interpro only). |
| start | int \| None (optional) | Match start coordinate (verbose only; sparse: interpro, ncbifam). |
| end | int \| None (optional) | Match end coordinate (verbose only; sparse: interpro, ncbifam). |
| bit_score | float \| None (optional) | NCBIfam alignment bit score (verbose only; sparse: ncbifam only). |
| function_description | string \| None (optional) | Curated functional description (verbose only) |
| level_is_best_effort | bool \| None (optional) | True when GO term's level is best-effort min-path (sparse: absent for non-GO or non-best-effort; verbose only) |

## Few-shot examples

### Example 1: Mode 1 — gene discovery by pathway (term_ids only)

```example-call
genes_by_ontology(ontology="go_bp", organism="MED4", term_ids=["go:0006260"])
```

```example-response
{
  "ontology": "go_bp",
  "organism_name": "Prochlorococcus MED4",
  "total_matching": 30,
  "total_genes": 30,
  "total_terms": 1,
  "total_categories": 6,
  "genes_per_term_min": 30,
  "genes_per_term_median": 30.0,
  "genes_per_term_max": 30,
  "terms_per_gene_min": 1,
  "terms_per_gene_median": 1.0,
  "terms_per_gene_max": 1,
  "by_category": [
    {"category": "Replication and repair", "count": 24},
    {"category": "Post-translational modification", "count": 2},
    {"category": "Transcription", "count": 1},
    ...
  ],
  "by_level": [{"level": 6, "n_terms": 1, "n_genes": 30, "row_count": 30}],
  "top_terms": [{"term_id": "go:0006260", "term_name": "DNA replication", "count": 30, "is_informative": true}],
  "n_best_effort_terms": 1,
  "not_found": [],
  "...": "11 empty fields omitted",
  "size_filtered_terms": 0,
  "size_filtered_genes": 0,
  "returned": 30,
  "offset": 0,
  "truncated": false,
  "trust_axes": {"go_bp": ["sources", "evidence", "evidence_score"]},
  "by_evidence": [{"count": 30, "evidence": "curated"}],
  "by_sources": [
    {"count": 18, "source": "cyanorak"},
    {"count": 13, "source": "uniprot"},
    {"count": 11, "source": "ncbi"},
    ...
  ],
  "evidence_score_stats": {"min": 0.667, "median": 0.667, "max": 1.0, "n_null": 0},
  "results": [
    {
      "locus_tag": "PMM0001",
      "gene_name": "dnaN",
      "product": "DNA polymerase III, beta subunit",
      "gene_category": "Replication and repair",
      "term_id": "go:0006260",
      "term_name": "DNA replication",
      "level": 6,
      "is_informative": true,
      "evidence": "curated"
    },
    {
      "locus_tag": "PMM0077",
      "gene_name": "rarA",
      "product": "recombination factor",
      "gene_category": "Replication and repair",
      "term_id": "go:0006260",
      "term_name": "DNA replication",
      "level": 6,
      "is_informative": true,
      "evidence": "curated"
    },
    {
      "locus_tag": "PMM0129",
      "gene_name": "holB",
      "product": "DNA polymerase III, delta^ subunit",
      "gene_category": "Replication and repair",
      "term_id": "go:0006260",
      "term_name": "DNA replication",
      "level": 6,
      "is_informative": true,
      "evidence": "curated"
    },
    ...
  ]
}
```

### Example 2: Mode 2 — pathway definitions at level N (level only)

```example-call
genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
```

```example-response
{
  "ontology": "cyanorak_role",
  "organism_name": "Prochlorococcus MED4",
  "total_matching": 1761,
  "total_genes": 1438,
  "total_terms": 69,
  "total_categories": 22,
  "genes_per_term_min": 5,
  "genes_per_term_median": 14.0,
  "genes_per_term_max": 340,
  "terms_per_gene_min": 1,
  "terms_per_gene_median": 1.0,
  "terms_per_gene_max": 3,
  "by_category": [
    {"category": "Unknown", "count": 333},
    {"category": "Stress response and adaptation", "count": 197},
    {"category": "Coenzyme metabolism", "count": 163},
    ...
  ],
  "by_level": [{"level": 1, "n_terms": 69, "n_genes": 1438, "row_count": 1761}],
  "top_terms": [
    {
      "term_id": "cyanorak.role:R.2",
      "term_name": "Other > Conserved hypothetical proteins",
      "count": 340,
      "is_informative": false
    },
    {
      "term_id": "cyanorak.role:D.1",
      "term_name": "Cellular processes > Adaptation/acclimation to atypical conditions and detoxification",
      "count": 213,
      "is_informative": true
    },
    {
      "term_id": "cyanorak.role:B.10",
      "term_name": "Biosynthesis of cofactors, prosthetic groups, and carriers > Vitamins",
      "count": 63,
      "is_informative": true
    },
    ...
  ],
  "n_best_effort_terms": 0,
  "not_found": [],
  "...": "10 empty fields omitted",
  "size_filtered_terms": 41,
  "size_filtered_genes": 53,
  "returned": 50,
  "offset": 0,
  "truncated": true,
  "trust_axes": {"cyanorak_role": ["sources", "evidence"]},
  "warnings": ["41 terms (53 genes not otherwise covered) fell outside min_gene_set_size=5 / max_gene_set_size=50..."],
  "by_evidence": [{"count": 1761, "evidence": "curated"}],
  "by_sources": [{"count": 1761, "source": "cyanorak"}],
  "evidence_score_stats": {"min": null, "median": null, "max": null, "n_null": 0},
  "results": [
    {
      "locus_tag": "PMM0107",
      "gene_name": "aroK",
      "product": "shikimate kinase",
      "gene_category": "Amino acid metabolism",
      "term_id": "cyanorak.role:A.1",
      "term_name": "Amino acid biosynthesis > Aromatic amino acids family (Phe, Trp, Tyr)",
      "level": 1,
      "is_informative": true,
      "evidence": "curated"
    },
    {
      "locus_tag": "PMM0164",
      "gene_name": "trpB",
      "product": "tryptophan synthase, beta subunit",
      "gene_category": "Amino acid metabolism",
      "term_id": "cyanorak.role:A.1",
      "term_name": "Amino acid biosynthesis > Aromatic amino acids family (Phe, Trp, Tyr)",
      "level": 1,
      "is_informative": true,
      "evidence": "curated"
    },
    {
      "locus_tag": "PMM0224",
      "gene_name": "aroC",
      "product": "chorismate synthase",
      "gene_category": "Amino acid metabolism",
      "term_id": "cyanorak.role:A.1",
      "term_name": "Amino acid biosynthesis > Aromatic amino acids family (Phe, Trp, Tyr)",
      "level": 1,
      "is_informative": true,
      "evidence": "curated"
    },
    ...
  ]
}
```

### Example 3: Mode 3 — scope rollup to specific pathways (level + term_ids)

```example-call
genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1, term_ids=["cyanorak.role:A.1", "cyanorak.role:A.2"])
```

### Example 4: Summary-only (envelope, no rows)

```example-call
genes_by_ontology(ontology="go_bp", organism="MED4", level=1, summary=True)
```

### Example 5: BRITE tree-scoped rollup (transporters at category level)

```example-call
genes_by_ontology(ontology="brite", organism="MED4", level=1, tree="transporters")
```

### Example 6: Inspect all terms (override size filter)

```example-call
genes_by_ontology(ontology="go_bp", organism="MED4", level=1, min_gene_set_size=0, max_gene_set_size=100000)
```

### Example 7: TCDB term → gene drill-down (with descendant expansion)

```example-call
genes_by_ontology(ontology="tcdb", organism="MED4", term_ids=["tcdb:2.A", "tcdb:2.A.1"])
```

*Each term expands DOWN through its families, subfamilies and systems before binding to genes, over gated edges only (`tcdb_gate` direct or annotated), so a term's gene set matches its `gene_count`. The default size filter applies to the expanded set: the subclass tcdb:2.A (Porters) keeps its MED4 genes, while MFS tcdb:2.A.1 has fewer than `min_gene_set_size=5` gated MED4 genes and lands in `filtered_out` with 0 rows — pass `min_gene_set_size=1` to see it. Rows carry `tcdb_call` / `tcdb_gate` / `tcdb_calls`; envelope `by_tcdb_call` counts them.*

### Example 8: CAZy class roll-up — genes by glycoside hydrolase / glycosyltransferase class

```example-call
genes_by_ontology(ontology="cazy", organism="MED4", level=0)
```

### Example 9: PSORTb outer-membrane proteins with confidence score

```example-call
genes_by_ontology(ontology="subcellular_localization", term_ids=["psortb_OuterMembrane"], organism="MED4")
```

```example-response
{
  "ontology": "subcellular_localization",
  "organism_name": "Prochlorococcus MED4",
  "total_matching": 11,
  "total_genes": 11,
  "total_terms": 1,
  "total_categories": 9,
  "genes_per_term_min": 11,
  "genes_per_term_median": 11.0,
  "genes_per_term_max": 11,
  "terms_per_gene_min": 1,
  "terms_per_gene_median": 1.0,
  "terms_per_gene_max": 1,
  "by_category": [
    {"category": "Stress response and adaptation", "count": 2},
    {"category": "Cell wall and membrane", "count": 2},
    {"category": "Transcription", "count": 1},
    ...
  ],
  "by_level": [{"level": 0, "n_terms": 1, "n_genes": 11, "row_count": 11}],
  "top_terms": [{"term_id": "psortb_OuterMembrane", "term_name": "Outer membrane", "count": 11, "is_informative": true}],
  "n_best_effort_terms": 0,
  "not_found": [],
  "...": "13 empty fields omitted",
  "size_filtered_terms": 0,
  "size_filtered_genes": 0,
  "returned": 11,
  "offset": 0,
  "truncated": false,
  "trust_axes": {"subcellular_localization": []},
  "evidence_score_stats": {"min": null, "median": null, "max": null, "n_null": 0},
  "results": [
    {
      "locus_tag": "PMM0063",
      "gene_name": "ycf66",
      "product": "uncharacterized conserved hypothetical protein Ycf66",
      "gene_category": "Transcription",
      "term_id": "psortb_OuterMembrane",
      "term_name": "Outer membrane",
      "level": 0,
      "is_informative": true
    },
    {
      "locus_tag": "PMM0097",
      "gene_name": "tolC",
      "product": "TolC-like outer membrane efflux protein, RND family",
      "gene_category": "Stress response and adaptation",
      "term_id": "psortb_OuterMembrane",
      "term_name": "Outer membrane",
      "level": 0,
      "is_informative": true
    },
    {
      "locus_tag": "PMM0151",
      "gene_name": "scpA",
      "product": "scpA/B family protein",
      "gene_category": "Cellular processes",
      "term_id": "psortb_OuterMembrane",
      "term_name": "Outer membrane",
      "level": 0,
      "is_informative": true
    },
    ...
  ]
}
```

### Example 10: SignalP lipoproteins with cleavage info

```example-call
genes_by_ontology(ontology="signal_peptide_type", term_ids=["signalp_LIPO"], organism="MED4")
```

```example-response
{
  "ontology": "signal_peptide_type",
  "organism_name": "Prochlorococcus MED4",
  "total_matching": 15,
  "total_genes": 15,
  "total_terms": 1,
  "total_categories": 6,
  "genes_per_term_min": 15,
  "genes_per_term_median": 15.0,
  "genes_per_term_max": 15,
  "terms_per_gene_min": 1,
  "terms_per_gene_median": 1.0,
  "terms_per_gene_max": 1,
  "by_category": [
    {"category": "Unknown", "count": 7},
    {"category": "Photosynthesis", "count": 2},
    {"category": "Stress response and adaptation", "count": 2},
    ...
  ],
  "by_level": [{"level": 0, "n_terms": 1, "n_genes": 15, "row_count": 15}],
  "top_terms": [
    {
      "term_id": "signalp_LIPO",
      "term_name": "Lipoprotein signal peptide (Sec/SPII)",
      "count": 15,
      "is_informative": true
    }
  ],
  "n_best_effort_terms": 0,
  "not_found": [],
  "...": "13 empty fields omitted",
  "size_filtered_terms": 0,
  "size_filtered_genes": 0,
  "returned": 15,
  "offset": 0,
  "truncated": false,
  "trust_axes": {"signal_peptide_type": []},
  "evidence_score_stats": {"min": null, "median": null, "max": null, "n_null": 0},
  "results": [
    {
      "locus_tag": "PMM0296",
      "gene_name": "ycf48",
      "product": "photosystem II stability/assembly factor",
      "gene_category": "Photosynthesis",
      "term_id": "signalp_LIPO",
      "term_name": "Lipoprotein signal peptide (Sec/SPII)",
      "level": 0,
      "is_informative": true
    },
    {
      "locus_tag": "PMM0437",
      "gene_name": null,
      "product": "conserved hypothetical protein",
      "gene_category": "Unknown",
      "term_id": "signalp_LIPO",
      "term_name": "Lipoprotein signal peptide (Sec/SPII)",
      "level": 0,
      "is_informative": true
    },
    {
      "locus_tag": "PMM0513",
      "gene_name": "lepB",
      "product": "signal peptidase I",
      "gene_category": "Post-translational modification",
      "term_id": "signalp_LIPO",
      "term_name": "Lipoprotein signal peptide (Sec/SPII)",
      "level": 0,
      "is_informative": true
    },
    ...
  ]
}
```

### Example 11: InterPro homologous-superfamily census (interpro_type facet)

```example-call
genes_by_ontology(ontology="interpro", organism="MED4", term_ids=["interpro:IPR027417"])
```

```example-response
{
  "ontology": "interpro",
  "organism_name": "Prochlorococcus MED4",
  "total_matching": 119,
  "total_genes": 119,
  "total_terms": 1,
  "total_categories": 17,
  "genes_per_term_min": 119,
  "genes_per_term_median": 119.0,
  "genes_per_term_max": 119,
  "terms_per_gene_min": 1,
  "terms_per_gene_median": 1.0,
  "terms_per_gene_max": 1,
  "by_category": [
    {"category": "Replication and repair", "count": 24},
    {"category": "Transport", "count": 17},
    {"category": "Coenzyme metabolism", "count": 16},
    ...
  ],
  "by_level": [{"level": 0, "n_terms": 1, "n_genes": 119, "row_count": 119}],
  "top_terms": [
    {
      "term_id": "interpro:IPR027417",
      "term_name": "P-loop containing nucleoside triphosphate hydrolase",
      "count": 119,
      "is_informative": true
    }
  ],
  "n_best_effort_terms": 0,
  "not_found": [],
  "...": "11 empty fields omitted",
  "size_filtered_terms": 0,
  "size_filtered_genes": 0,
  "returned": 50,
  "offset": 0,
  "truncated": true,
  "trust_axes": {"interpro": ["sources", "evidence"]},
  "by_evidence": [{"count": 119, "evidence": "signature"}],
  "by_sources": [{"count": 119, "source": "interproscan"}],
  "evidence_score_stats": {"min": null, "median": null, "max": null, "n_null": 0},
  "results": [
    {
      "locus_tag": "PMM0010",
      "gene_name": "ftsY",
      "product": "signal recognition particle-docking protein FtsY",
      "gene_category": "Post-translational modification",
      "term_id": "interpro:IPR027417",
      "term_name": "P-loop containing nucleoside triphosphate hydrolase",
      "level": 0,
      "is_informative": true,
      "evidence": "signature",
      "interpro_type": "HOMOLOGOUS_SUPERFAMILY"
    },
    {
      "locus_tag": "PMM0019",
      "gene_name": "rsgA",
      "product": "ribosome biogenesis GTPase / thiamine phosphate phosphatase",
      "gene_category": "Coenzyme metabolism",
      "term_id": "interpro:IPR027417",
      "term_name": "P-loop containing nucleoside triphosphate hydrolase",
      "level": 0,
      "is_informative": true,
      "evidence": "signature",
      "interpro_type": "HOMOLOGOUS_SUPERFAMILY"
    },
    {
      "locus_tag": "PMM0049",
      "gene_name": "coaE",
      "product": "dephospho-CoA kinase",
      "gene_category": "Coenzyme metabolism",
      "term_id": "interpro:IPR027417",
      "term_name": "P-loop containing nucleoside triphosphate hydrolase",
      "level": 0,
      "is_informative": true,
      "evidence": "signature",
      "interpro_type": "HOMOLOGOUS_SUPERFAMILY"
    },
    ...
  ]
}
```

### Example 12: MEROPS peptidase-only clan census (call_class filter)

```example-call
genes_by_ontology(ontology="merops", organism="MIT1002", level=0, call_class=["peptidase"])
```

```example-response
{
  "ontology": "merops",
  "organism_name": "Alteromonas macleodii MIT1002",
  "total_matching": 72,
  "total_genes": 72,
  "total_terms": 7,
  "total_categories": 10,
  "genes_per_term_min": 5,
  "genes_per_term_median": 8.0,
  "genes_per_term_max": 22,
  "terms_per_gene_min": 1,
  "terms_per_gene_median": 1.0,
  "terms_per_gene_max": 1,
  "by_category": [
    {"category": "Amino acid metabolism", "count": 28},
    {"category": "Unknown", "count": 17},
    {"category": "Post-translational modification", "count": 13},
    ...
  ],
  "by_level": [{"level": 0, "n_terms": 7, "n_genes": 72, "row_count": 72}],
  "top_terms": [
    {"term_id": "merops.clan:SC", "term_name": "SC", "count": 22, "is_informative": true},
    {"term_id": "merops.clan:MA", "term_name": "MA", "count": 18, "is_informative": true},
    {"term_id": "merops.clan:MH", "term_name": "MH", "count": 8, "is_informative": true},
    ...
  ],
  "n_best_effort_terms": 0,
  "not_found": [],
  "...": "7 empty fields omitted",
  "size_filtered_terms": 20,
  "size_filtered_genes": 46,
  "returned": 50,
  "offset": 0,
  "truncated": true,
  "trust_axes": {"merops": ["sources", "evidence", "evidence_score", ...]},
  "warnings": ["20 terms (46 genes not otherwise covered) fell outside min_gene_set_size=5 / max_gene_set_size=50..."],
  "filters_applied": {"call_class": ["peptidase"]},
  "by_evidence": [{"count": 72, "evidence": "homology"}],
  "by_tier": [{"count": 68, "tier": 3}, {"count": 4, "tier": 2}],
  "by_sources": [{"count": 72, "source": "merops_diamond"}],
  "by_call_class": [{"call_class": "peptidase", "count": 72}],
  "evidence_score_stats": {"min": 0.0, "median": 0.5, "max": 1.0, "n_null": 0},
  "results": [
    {
      "locus_tag": "MIT1002_00401",
      "gene_name": "dcp",
      "product": "M3 family metallopeptidase",
      "gene_category": "Amino acid metabolism",
      "term_id": "merops.clan:MA",
      "term_name": "MA",
      "level": 0,
      "is_informative": true,
      "evidence": "homology",
      "call_class": "peptidase"
    },
    {
      "locus_tag": "MIT1002_00745",
      "gene_name": null,
      "product": "dipeptidyl-peptidase 3 family protein",
      "gene_category": "Unknown",
      "term_id": "merops.clan:MA",
      "term_name": "MA",
      "level": 0,
      "is_informative": true,
      "evidence": "homology",
      "call_class": "peptidase"
    },
    {
      "locus_tag": "MIT1002_00890",
      "gene_name": "pepN",
      "product": "M1 family metallopeptidase",
      "gene_category": "Amino acid metabolism",
      "term_id": "merops.clan:MA",
      "term_name": "MA",
      "level": 0,
      "is_informative": true,
      "evidence": "homology",
      "call_class": "peptidase"
    },
    ...
  ]
}
```

### Example 13: MEROPS clan census without call_class (warns)

```example-call
genes_by_ontology(ontology="merops", organism="MIT1002", level=0)
```

```example-response
{
  "ontology": "merops",
  "organism_name": "Alteromonas macleodii MIT1002",
  "total_matching": 112,
  "total_genes": 112,
  "total_terms": 10,
  "total_categories": 12,
  "genes_per_term_min": 5,
  "genes_per_term_median": 8.0,
  "genes_per_term_max": 31,
  "terms_per_gene_min": 1,
  "terms_per_gene_median": 1.0,
  "terms_per_gene_max": 1,
  "by_category": [
    {"category": "Amino acid metabolism", "count": 38},
    {"category": "Unknown", "count": 22},
    {"category": "Post-translational modification", "count": 13},
    ...
  ],
  "by_level": [{"level": 0, "n_terms": 10, "n_genes": 112, "row_count": 112}],
  "top_terms": [
    {"term_id": "merops.clan:SC", "term_name": "SC", "count": 31, "is_informative": true},
    {"term_id": "merops.clan:MA", "term_name": "MA", "count": 18, "is_informative": true},
    {"term_id": "merops.clan:PC", "term_name": "PC", "count": 13, "is_informative": true},
    ...
  ],
  "n_best_effort_terms": 0,
  "not_found": [],
  "...": "8 empty fields omitted",
  "size_filtered_terms": 17,
  "size_filtered_genes": 38,
  "returned": 50,
  "offset": 0,
  "truncated": true,
  "trust_axes": {"merops": ["sources", "evidence", "evidence_score", ...]},
  "warnings": [
    "29 of 112 matching rows carry call_class=['nonpeptidase_homolog'] — catalytically-dead homologs t...",
    "17 terms (38 genes not otherwise covered) fell outside min_gene_set_size=5 / max_gene_set_size=50..."
  ],
  "by_evidence": [{"count": 112, "evidence": "homology"}],
  "by_tier": [{"count": 107, "tier": 3}, {"count": 5, "tier": 2}],
  "by_sources": [{"count": 112, "source": "merops_diamond"}],
  "by_call_class": [{"call_class": "peptidase", "count": 83}, {"call_class": "nonpeptidase_homolog", "count": 29}],
  "evidence_score_stats": {"min": 0.0, "median": 0.5, "max": 1.0, "n_null": 0},
  "results": [
    {
      "locus_tag": "MIT1002_00401",
      "gene_name": "dcp",
      "product": "M3 family metallopeptidase",
      "gene_category": "Amino acid metabolism",
      "term_id": "merops.clan:MA",
      "term_name": "MA",
      "level": 0,
      "is_informative": true,
      "evidence": "homology",
      "call_class": "peptidase"
    },
    {
      "locus_tag": "MIT1002_00745",
      "gene_name": null,
      "product": "dipeptidyl-peptidase 3 family protein",
      "gene_category": "Unknown",
      "term_id": "merops.clan:MA",
      "term_name": "MA",
      "level": 0,
      "is_informative": true,
      "evidence": "homology",
      "call_class": "peptidase"
    },
    {
      "locus_tag": "MIT1002_00890",
      "gene_name": "pepN",
      "product": "M1 family metallopeptidase",
      "gene_category": "Amino acid metabolism",
      "term_id": "merops.clan:MA",
      "term_name": "MA",
      "level": 0,
      "is_informative": true,
      "evidence": "homology",
      "call_class": "peptidase"
    },
    ...
  ]
}
```

### Example 14: TCDB trust detail — sources / tier / DIAMOND statistics (verbose)

```example-call
genes_by_ontology(ontology="tcdb", organism="MED4", term_ids=["tcdb:3.A.1.4"], min_gene_set_size=1, verbose=True)
```

*The urea / amino-acid subfamily tcdb:3.A.1.4 in MED4: the urtABCDE genes. Each row reports one edge by precedence (best hit, then tier, then eggNOG; then identity): `tcdb_call`, `tcdb_gate`, `sources`, `tier` and, on DIAMOND rows, `identity` / `qcov` (percent), `evalue`, `tcdb_scov`, `tcdb_best_hit_rank`, `tcdb_bitscore`, `tcdb_bitscore_ratio`. `tcdb_calls` lists every call kind on the gene's lineage through the term. TCDB carries no evidence score.*

### Example 15: Trust filters on TCDB — DIAMOND calls only (evidence + tcdb_call)

```example-call
genes_by_ontology(ontology="tcdb", organism="MED4", term_ids=["tcdb:3.A.1"], evidence=["homology"], tcdb_call=["diamond_best_hit", "diamond_tier"])
```

*TCDB's trust axes are `sources`, `evidence` and `tier`, plus the `tcdb_call` filter; `min_evidence_score` raises on tcdb. `evidence=['homology']` and `tcdb_call` both drop the eggNOG rows here. Default TCDB rows are gated, so their tier is 1, 2 or null (eggNOG): `max_tier=2` changes nothing unless `include_weak_tcdb_hits=True`. `max_tier=1` keeps tier-1 calls plus the tier-null eggNOG rows, so pair it with `evidence=['homology']`; on tcdb:3.A.1 in MED4 that leaves 4 genes, below the default `min_gene_set_size=5`, so also pass `min_gene_set_size=1`. `include_weak_tcdb_hits=True` adds the below-gate DIAMOND edges instead.*

### Example 16: Filter out uninformative terms (term-side filter, opt-in)

```example-call
genes_by_ontology(ontology="kegg", organism="MED4", level=3, informative_only=True, min_gene_set_size=1)
```

*`informative_only=True` excludes terms flagged `is_uninformative='true'` (GO roots, catch-all Cyanorak / TIGR / COG roles, KEGG KOs named 'uncharacterized protein' — for KEGG also the global / overview pathway maps such as `kegg.pathway:ko01100`). Term-side only — never narrows the gene set. Every detail row carries `is_informative: bool`. MED4 KEGG level 3: 1124 → 1094 rows. `min_gene_set_size=1` is needed here because most KOs carry a single MED4 gene and the default size filter (5) would drop them all.*

### Example 17: From level-survey to pathway defs

```
Step 1: ontology_landscape(organism="MED4")
        → identify best (ontology, level) pair, e.g. (cyanorak_role, level=1)

Step 2: genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
        → get TERM2GENE pathway definitions at that level

Step 3: pathway_enrichment(ontology="cyanorak_role", organism="MED4", level=1, experiment_ids=[...])
        → run ORA with those pathway definitions
```

## Chaining patterns

```
Term-anchored: term / level → (gene × term) pairs, hierarchy expanded DOWN. The gene-anchored reverse (locus_tags → their terms, leaf or rollup) is `gene_ontology_terms`.
ontology_landscape → genes_by_ontology(level=N)
search_ontology → genes_by_ontology(term_ids=[...])
genes_by_ontology → pathway_enrichment
genes_by_ontology → gene_overview
genes_by_ontology(ontology='tcdb' | 'ec', term_ids=[...]) → genes_by_metabolite (substrate-anchored pivot — see docs://analysis/metabolites)
From PSORTb-filtered genes → differential_expression_by_gene to ask: are outer-membrane proteins enriched in the up-regulated set?
list_filter_values(filter_type='trust_axes') → check which trust params an ontology supports before filtering — see docs://analysis/annotation_evidence
genes_by_ontology(ontology='merops', call_class=['peptidase']) → pathway_enrichment(ontology='merops', call_class=['peptidase']) to keep the TERM2GENE definitions and the enrichment test on the same trust-filtered gene set
```

## Common mistakes

- Term-anchored (term → genes). For 'which terms does this gene carry?' use `gene_ontology_terms(locus_tags=[...])` — same ontology surface, opposite anchor.

- Default `min_gene_set_size=5` / `max_gene_set_size=500` suit enrichment and drop small and huge terms, which can hide most of a gene set (e.g. BRITE `tree='transporters'`, `level=2` in MED4). To enumerate every gene pass `min_gene_set_size=1` and a large `max_gene_set_size` (e.g. 100000 over MCP; `None` from Python). The envelope reports what was dropped: `size_filtered_terms` (terms outside the size bounds), `size_filtered_genes` (genes found only in those terms), and a `warnings` entry when both bounds were left at their defaults (passing either bound explicitly keeps the counts but drops the warning). `filtered_out` lists only input `term_ids`, so in `level` mode these fields are the only signal.

- Substrate-anchored TCDB questions ('which genes transport sucrose?') chain via `genes_by_metabolite`, NOT `genes_by_ontology`. Use `genes_by_ontology(ontology='tcdb', term_ids=[...])` for *family*-level questions ('which genes are in voltage-gated ion channels?'). The metabolite-anchored route includes every TC system curated with the substrate (plus the opt-in family walk); the family-anchored route here is anchored on one TC id and misses cross-family substrate hits.

- At least one of `level` or `term_ids` must be set — calling without either is an error.

- Results are `(gene × term)` pairs, not distinct genes — use `total_genes` for the gene count. `total_matching` is the row count.

- Gene-set-size filter is organism-scoped via descendants — count of distinct genes annotated to the term or any descendant for `$organism`. Matches `ontology_landscape`'s convention.

- For GO (a DAG), level slicing is a best-effort approximation — `level_is_best_effort` flags rows where the min-path to root was ambiguous. Check `ontology_landscape`'s `best_effort_share` per level.

- `level_is_best_effort` is a sparse column — absent when not GO / not best-effort. In pandas, call `df['level_is_best_effort'].fillna(False)` before boolean filtering.

- `organism` is required and single-valued. For cross-organism browsing, loop the tool or use `gene_ontology_terms`.

- Pfam is a 2-level ontology: `level=1` → Pfam domains (leaf), `level=0` → PfamClan (parent). Both kinds of IDs are accepted under `ontology='pfam'`.

- KEGG: gene edges only hit the KO leaf (`level=3`). Passing `level=0/1/2` rolls up to category/subcategory/pathway via `is_a`.

- BRITE: gene edges hit the KO leaf (`level=3`, same as KEGG). Passing `level=0/1/2` rolls up through BRITE tree hierarchy. Each BRITE tree is a separate functional classification — use `tree` to scope to a specific tree (e.g. `tree='transporters'`). Without `tree`, results mix all BRITE trees. Use `list_filter_values('brite_tree')` to discover available trees.

- Flat ontologies (`cog_category`, `subcellular_localization`, `signal_peptide_type`, `ncbifam`) have only `level=0`: passing `level >= 1` in Mode 2 returns empty results; in Mode 3 the ids route to `wrong_level`. `tigr_role` is two-level, not flat: `level=0` = the 21 main roles, `level=1` = sub roles.

- Supported ontologies: `go_bp`, `go_mf`, `go_cc`, `ec`, `kegg`, `cog_category`, `cyanorak_role`, `tigr_role`, `pfam`, `brite`, `tcdb`, `cazy`, `subcellular_localization`, `signal_peptide_type`, `interpro`, `ncbifam`, `merops`.

- Compact rows carry `evidence` on the 15 functional-edge ontologies (null on PSORTb/SignalP), plus `call_class` on MEROPS, `interpro_type` on InterPro and `tcdb_call` / `tcdb_gate` / `tcdb_calls` on TCDB. `sources` / `evidence_score` / `tier` and native scalars are verbose. Trust filters (`sources`, `evidence`, `max_tier`, `min_evidence_score`, `call_class`, `tcdb_call`) default to `None`; an axis the ontology lacks raises `ValueError`. Per-ontology table: `docs://analysis/annotation_evidence`.

- `max_tier` keeps tier-null rows (`r.tier <= max_tier OR r.tier IS NULL`) — an eggNOG-only TCDB edge with no `tier` passes any `max_tier` filter. Check the envelope's `by_tier` `"null"` bucket to see how many rows that affects.

- `sources` is set-membership ANY (`any(s IN $sources WHERE s IN r.sources)`), not exact match — an edge with `sources=['eggnog', 'uniprot']` matches `sources=['eggnog']`.

- Row strip rule: a row only carries the columns its ontology owns. `tier` never appears on a `kegg` row (KEGG carries no `tier` axis); `interpro_type` never appears on a `tcdb` row. Owned-but-null stays — e.g. `tier` is present and `null` on a TCDB edge with only eggNOG support (no tier assigned).

```mistake
genes_by_ontology(ontology='go_bp', organism='MED4', level=3, call_class=['peptidase'])  # call_class is MEROPS-only
```

```correction
list_filter_values(filter_type='trust_axes', ontology='go_bp')  # check axes first — go_bp supports sources/evidence/evidence_score only, raises ValueError otherwise
```

- TCDB is hierarchical (5 levels: `tc_class` → `tc_subclass` → `tc_family` → `tc_subfamily` → `tc_system`). `term_ids=['tcdb:1.A.1']` expands DOWN through its subfamilies and systems before binding to genes via `Gene_has_tcdb_family`. Only gated edges count (`tcdb_gate` direct or annotated), so the distinct genes per term equal `TcdbFamily.gene_count` and `pathway_enrichment` sees the same gene sets. `include_weak_tcdb_hits=True` adds the `below_gate` DIAMOND edges as extra rows (default rows unchanged); it is not offered on the enrichment tools.

- Many TCDB nodes are range-only: a system or subfamily TCDB curates but no gene in the KG is called to (`gene_count = 0`). They exist so a family's substrate range is complete; they bind no genes here.

- CAZy is a small ontology (6 classes, ~90 families; `docs://ontologies/cazy`). `level=0` gives ~6 class-level rows (GH, GT, PL, CE, AA, CBM); `level=1` gives families. With default `min_gene_set_size=5`, many CAZy terms are filtered out — pass `min_gene_set_size=1` to see all.

- Substrate-anchored EC questions ('which genes catalyse a reaction involving glucose?') chain via `genes_by_metabolite(metabolite_ids=[...], evidence_sources=['metabolism'])`, NOT `genes_by_ontology(ontology='ec', ...)`. The metabolite-anchored route reaches every EC number whose Reaction touches the compound; the EC-anchored route here is anchored on a single EC family and misses promiscuous reactions. See docs://analysis/metabolites for the full anchor-disambiguation.

```mistake
genes_by_ontology(ontology='go_bp', organism='MED4')  # no level or term_ids
```

```correction
genes_by_ontology(ontology='go_bp', organism='MED4', level=3)
```

```mistake
len(response.results)  # wrong — that's the row count after limit
```

```correction
response.total_genes  # distinct genes across all matches
```

- TERM2GENE source for enrichment. Pass the result through `to_dataframe(...)` and feed it directly into `fisher_ora` / `pathway_enrichment` / `cluster_enrichment` — no manual column renaming. See `docs://analysis/enrichment` for the building blocks and the worked DE-path code example.

- `localization_score` / `signal_peptide_probability` are **edge** properties — they appear in rows only when querying their owner ontology. Other ontology queries omit those columns entirely (sparse-null stripping at the api layer).

- PSORTb and SignalP are 1:1 (≤1 edge per gene). Don't expect multiple rows per gene for the same ontology. Some genes will have **no** edge (no confident call); those genes are absent from the result set entirely.

- `informative_only` (default False here) drops terms the KG flags uninformative — ontology roots and catch-all KO terms, plus the KEGG global / overview maps. It is term-side only and never restricts the gene set. See docs://analysis/annotation_evidence.

- `limit` defaults to 50 over MCP; the Python package defaults to unbounded (all rows), which `pathway_enrichment` / `cluster_enrichment` rely on for a complete TERM2GENE.

- `tcdb_call` filters edges before the row's representative edge is chosen, so the same (gene, term) row can report a different `tcdb_call` under the filter: pstS (PMM0710) on tcdb:3.A.1.7 reads `diamond_best_hit` by default and `eggnog` with `tcdb_call=['eggnog']`. The filter selects genes with a call of that kind under the term; it does not rank them.

## Package import equivalent

```python
from multiomics_explorer import genes_by_ontology

result = genes_by_ontology(ontology=..., organism=...)
# returns dict with keys: ontology, organism_name, total_matching, total_genes, total_terms, total_categories, genes_per_term_min, genes_per_term_median, genes_per_term_max, terms_per_gene_min, terms_per_gene_median, terms_per_gene_max, by_category, by_level, top_terms, n_best_effort_terms, not_found, wrong_ontology, wrong_level, filtered_out, size_filtered_terms, size_filtered_genes, resolved_aliases, returned, offset, truncated, trust_axes, warnings, filters_applied, skipped_ontologies, by_evidence, by_tier, by_sources, by_call_class, by_tcdb_call, evidence_score_stats, evidence_score_signals, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
