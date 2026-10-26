# gene_ontology_terms

## What it does

Reverse lookup: locus_tags to their ontology annotations in ONE organism, most-specific leaves (default) or rolled up to a level.

Use for what a gene carries; for which genes carry a term use `genes_by_ontology`, to find term IDs `search_ontology`.
Filters: locus_tags, organism, ontology, mode, level, tree, informative_only, include_weak_tcdb_hits, trust filters (+tcdb_call).
Returns: by_ontology, by_term, terms-per-gene stats, trust rollups, skipped_ontologies, not_found, no_terms; one row = (locus_tag, term_id, evidence).
docs://tools/gene_ontology_terms; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Must resolve to ONE organism — an ambiguous match (e.g. a genus word) raises; see list_organisms. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') \| list[string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops')] \| None | None | Filter to one ontology, or a list of ontologies (trust filters/facets shape all-or-skip-or-raise per docs://guide/conventions). None returns all. |
| mode | string ('leaf', 'rollup') | leaf | 'leaf' returns most-specific annotations (default). 'rollup' walks up to ancestors at the given level. |
| level | int \| None | None | Hierarchy level (0 = broadest). In leaf mode: filter to leaves at this level. In rollup mode: required — target ancestor level. See docs://guide/conventions. |
| tree | string \| None | None | BRITE tree name filter. Narrows brite and leaves any other ontology in the list untouched; raises when brite is not among them. See docs://guide/conventions for the BRITE-tree scoping rule. |
| informative_only | bool | False | True drops terms the KG flags uninformative (roots, catch-alls). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| sources | list[string] \| None | None | Keep rows whose edge sources[] contains any of these values. Valid on the 15 functional-edge ontologies (all but PSORTb/SignalP; brite shares kegg's edge). See list_filter_values('sources'). |
| evidence | list[string] \| None | None | Keep rows whose compact evidence-ladder value is in this list. Valid on the 15 functional-edge ontologies (all but PSORTb/SignalP; brite shares kegg's edge). See docs://analysis/annotation_evidence. |
| max_tier | int \| None | None | Keep rows with edge tier <= this value OR tier IS NULL (1-3; null always kept, e.g. TCDB eggnog). tcdb, merops only. TCDB tier is consensus tier on diamond_tier, identity band on diamond_best_hit; never compare across kinds or ontologies. |
| min_evidence_score | float \| None | None | Keep rows with edge evidence_score >= this cutoff (0-1; the only native-scalar cutoff allowed). Valid on go_bp/mf/cc, ec, pfam, cazy, merops; TCDB carries no evidence_score (raises). |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; unfiltered mixes in catalytically-dead nonpeptidase_homolog rows. |
| tcdb_call | list[string] \| None | None | TCDB only: keep edges whose tcdb_call is in this list, applied before the representative edge is picked. Leaf mode still drops ancestors via all edges, so a call kind only on an ancestor term yields no row. Values: list_filter_values('tcdb_call'). |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |
| include_weak_tcdb_hits | bool | False | TCDB only: also return one row per weak hit (tcdb_gate='below_gate', diamond only), tagged in tcdb_gate. Adds rows; default rows are unchanged. No-op for other ontologies. |
| limit | int | 50 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_genes, total_terms, by_ontology, by_term, terms_per_gene_min, terms_per_gene_max, terms_per_gene_median, returned, offset, truncated, not_found, no_terms, trust_axes, by_evidence, by_tier, by_sources, by_call_class, by_tcdb_call, evidence_score_stats, filters_applied, skipped_ontologies, warnings, results
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
- **by_tcdb_call** (list[object]): Rollup of the representative tcdb_call over every matching row (tcdb only); twin of by_call_class. Empty with summary=true.
- **evidence_score_stats** (object | None): {min, median, max, n_null} over evidence_score across every matching row. None for TCDB (no evidence_score). All-null with summary=true.
- **evidence_score_signals** (object | None): Fired ControlledVocabulary signals per edge_type; present only when min_evidence_score was set.
- **filters_applied** (object): Echo of the trust filters that were actually set on this call.
- **skipped_ontologies** (list[object]): Multi-ontology: [{ontology, reason}] for ontologies dropped because a filter/facet only some of the queried ontologies own.
- **warnings** (list[string]): Auto-warnings, incl. skipped-ontology, trust-cutoff, and locus_tag case-mismatch notices.

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
| tcdb_call | string \| None (optional) | TCDB call kind of the row's representative edge (precedence diamond_best_hit > diamond_tier > eggnog, then identity). Sparse: tcdb only. |
| tcdb_gate | string \| None (optional) | KG gate of the representative TCDB edge: 'direct' / 'annotated' (default rows) or 'below_gate' (only with include_weak_tcdb_hits=True). Sparse: tcdb only. |
| tcdb_calls | list[string] \| None (optional) | TCDB call kinds on the gene's gated edges along the term's lineage, in precedence order. The two diamond kinds are one run; eggnog + diamond = independent agreement. Sparse: tcdb only. |
| interpro_type | string \| None (optional) | InterPro entry type (sparse: interpro only). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| sources | list[string] \| None (optional) | Provenance tags on this edge (verbose only; sparse). |
| evidence_score | float \| None (optional) | Composite trust score in [0,1] (verbose only; sparse). |
| tier | int \| None (optional) | Diamond tier 1-3 (verbose only; sparse: tcdb, merops). TCDB: consensus tier on diamond_tier, identity band on diamond_best_hit, null on eggnog; never compare across kinds or ontologies. |
| confidence_score | float \| None (optional) | Native rank score (verbose only; sparse: merops only). |
| pfam_support | string \| None (optional) | Pfam-domain corroboration detail (verbose only; sparse: merops only). |
| identity | float \| None (optional) | Alignment percent identity (verbose only; sparse: tcdb, merops). |
| qcov | float \| None (optional) | Query coverage, percent (verbose only; sparse: tcdb, merops). |
| evalue | float \| None (optional) | Alignment e-value (verbose only; sparse). Never a filter cutoff. |
| consensus_n | int \| None (optional) | Corroborating-calls count (verbose only; sparse: merops only). |
| tcdb_scov | float \| None (optional) | TCDB diamond subject coverage, percent (verbose only; sparse: tcdb diamond edges). |
| tcdb_best_hit_rank | int \| None (optional) | Rank of this TCDB best hit among the gene's hits (edge `rank`; 1 = top). Not a row rank (verbose only; sparse: tcdb diamond_best_hit edges). |
| tcdb_bitscore | float \| None (optional) | TCDB diamond best-hit bit score (verbose only; sparse: tcdb diamond_best_hit edges). |
| tcdb_bitscore_ratio | float \| None (optional) | TCDB best-hit bit score relative to the top hit (verbose only; sparse: tcdb diamond_best_hit edges). |
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
  "by_tcdb_call": [],
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
  "by_evidence": [{"evidence": "family_inferred", "count": 4}],
  "by_tier": [],
  "by_sources": [{"source": "eggnog", "count": 4}, {"source": "interproscan", "count": 2}],
  "by_call_class": [],
  "by_tcdb_call": [],
  "evidence_score_stats": {"min": 0.333, "median": 0.5, "max": 0.667, "n_null": 0},
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
      "evidence": "family_inferred"
    },
    {
      "locus_tag": "PMM0584",
      "term_id": "cazy:GH",
      "term_name": "Glycoside Hydrolases",
      "level": 0,
      "is_informative": true,
      "evidence": "family_inferred"
    },
    {
      "locus_tag": "PMM1322",
      "term_id": "cazy:CBM",
      "term_name": "Carbohydrate-Binding Modules",
      "level": 0,
      "is_informative": true,
      "evidence": "family_inferred"
    },
    ...
  ]
}
```

### Example 6: TCDB annotations for a gene

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
      "term_name": "The Cobalamin Precursor (B12-P) Family",
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
  "returned": 7,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"tcdb": ["sources", "evidence", "tier"], "merops": ["sources", "evidence", "evidence_score", "tier"]},
  "by_evidence": [{"evidence": "family_inferred", "count": 7}],
  "by_tier": [{"tier": "null", "count": 7}],
  "by_sources": [{"source": "eggnog", "count": 7}],
  "by_call_class": [],
  "by_tcdb_call": [{"tcdb_call": "eggnog", "count": 7}],
  "evidence_score_stats": {"min": null, "median": null, "max": null, "n_null": 0},
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
      "tcdb_call": "eggnog",
      "tcdb_gate": "annotated",
      "tcdb_calls": ["eggnog"]
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.28",
      "term_name": "The Queuosine (Queuosine) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "tcdb_call": "eggnog",
      "tcdb_gate": "annotated",
      "tcdb_calls": ["eggnog"]
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.29",
      "term_name": "The Methionine Precursor (Met-P) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "tcdb_call": "eggnog",
      "tcdb_gate": "annotated",
      "tcdb_calls": ["eggnog"]
    },
    ...
  ]
}
```

### Example 8: TCDB leaf mode — gated targets, one row per gene × TC node (default)

```example-call
gene_ontology_terms(locus_tags=["PMM0372", "PMM0710"], organism="MED4", ontology=["tcdb"], mode="leaf", verbose=True)
```

*Leaf mode on tcdb keeps the gene's gate-passing edges (`tcdb_gate` direct or annotated) and drops any node that is an ancestor of another gated target, so the row count per gene equals `gene_overview.tcdb_assignment_count`. cynD (PMM0372) gives 2 rows, its two sibling systems (an eggNOG call on tcdb:3.A.1.16.1, a rank-1 DIAMOND best hit on tcdb:3.A.1.16.2); its weak tier-3 call on 3.A.1 is not shown. pstS (PMM0710) gives 1 row on tcdb:3.A.1.7.6: its eggNOG and tier-2 calls sit on the ancestor 3.A.1.7, so the row's `tcdb_calls` lists all three call kinds. When several edges point at the same node, the row reports one by precedence (`tcdb_call` best hit, then tier, then eggNOG; then identity). DIAMOND detail (`identity`, `qcov` in percent, `evalue`, `tcdb_scov`, `tcdb_best_hit_rank`, `tcdb_bitscore`, `tcdb_bitscore_ratio`) is verbose-only.*

```example-response
{
  "total_matching": 3,
  "total_genes": 2,
  "total_terms": 3,
  "by_ontology": [{"ontology_type": "tcdb", "term_count": 3, "gene_count": 2, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "tcdb:3.A.1.16.2",
      "term_name": "Bispecific cyanate/nitrite transporter.",
      "level": 4,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.16.1",
      "term_name": "Four component nitrate/nitrite porter.",
      "level": 4,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.7.6",
      "term_name": "High affinity phosphate-specific transporter, PstABCS, where PstA = 304 aas with 6 TMSs, PstB = 267 aas with 0 TMSs, ...",
      "level": 4,
      "ontology_type": "tcdb",
      "count": 1
    }
  ],
  "terms_per_gene_min": 1,
  "terms_per_gene_max": 2,
  "terms_per_gene_median": 1.5,
  "returned": 3,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"tcdb": ["sources", "evidence", "tier"]},
  "by_evidence": [{"evidence": "homology", "count": 2}, {"evidence": "family_inferred", "count": 1}],
  "by_tier": [{"tier": "null", "count": 1}, {"tier": 2, "count": 1}, {"tier": 1, "count": 1}],
  "by_sources": [{"source": "tcdb_diamond", "count": 2}, {"source": "eggnog", "count": 1}],
  "by_call_class": [],
  "by_tcdb_call": [{"tcdb_call": "diamond_best_hit", "count": 2}, {"tcdb_call": "eggnog", "count": 1}],
  "evidence_score_stats": null,
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0372",
      "term_id": "tcdb:3.A.1.16.1",
      "term_name": "Four component nitrate/nitrite porter.",
      "level": 4,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "tcdb_call": "eggnog",
      "tcdb_gate": "direct",
      "tcdb_calls": ["eggnog"],
      "sources": ["eggnog"],
      "tier": null,
      "identity": null,
      "qcov": null,
      "evalue": null,
      "tcdb_scov": null,
      "tcdb_best_hit_rank": null,
      "tcdb_bitscore": null,
      "tcdb_bitscore_ratio": null,
      "organism_name": "Prochlorococcus MED4"
    },
    {
      "locus_tag": "PMM0372",
      "term_id": "tcdb:3.A.1.16.2",
      "term_name": "Bispecific cyanate/nitrite transporter.",
      "level": 4,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "homology",
      "tcdb_call": "diamond_best_hit",
      "tcdb_gate": "direct",
      "tcdb_calls": ["diamond_best_hit"],
      "sources": ["tcdb_diamond"],
      "tier": 2,
      "identity": 59.2,
      "qcov": 95.4,
      "evalue": 1.16e-108,
      "tcdb_scov": 94.1,
      "tcdb_best_hit_rank": 1,
      "tcdb_bitscore": 316.0,
      "tcdb_bitscore_ratio": 1.0,
      "organism_name": "Prochlorococcus MED4"
    },
    {
      "locus_tag": "PMM0710",
      "term_id": "tcdb:3.A.1.7.6",
      "term_name": "High affinity phosphate-specific transporter, PstABCS, where PstA = 304 aas with 6 TMSs, PstB = 267 aas with 0 TMSs, ...",
      "level": 4,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "homology",
      "tcdb_call": "diamond_best_hit",
      "tcdb_gate": "direct",
      "tcdb_calls": ["diamond_best_hit", "diamond_tier", "eggnog"],
      "sources": ["tcdb_diamond"],
      "tier": 1,
      "identity": 85.9,
      "qcov": 94.1,
      "evalue": 2.83e-188,
      "tcdb_scov": 95.3,
      "tcdb_best_hit_rank": 1,
      "tcdb_bitscore": 520.0,
      "tcdb_bitscore_ratio": 1.0,
      "organism_name": "Prochlorococcus MED4"
    }
  ]
}
```

### Example 9: Weak TCDB hits are opt-in — include_weak_tcdb_hits=True adds the below-gate DIAMOND rows

```example-call
gene_ontology_terms(locus_tags=["PMM0125", "PMM0024"], organism="MED4", ontology=["tcdb"], include_weak_tcdb_hits=True)
```

*The switch only adds rows, each tagged `tcdb_gate='below_gate'`; the default rows come back unchanged. ecfA1 (PMM0125) keeps its 7 eggNOG subfamily rows (3.A.1.25 … 3.A.1.33) and gains 3 best-hit system rows at 33–35% identity. thiL (PMM0024), a thiamine-monophosphate kinase, has no default TCDB row (`tcdb_assignment_count = 0`); its only edge is a 28.5% tier-3 hit on tcdb:8.A.159, a ubiquitin-ligase family. That is what weak hits mostly are on non-transporters. A below-gate edge on an ancestor of a row already returned is skipped. Passing the switch with a non-TCDB ontology is a no-op.*

```example-response
{
  "total_matching": 11,
  "total_genes": 2,
  "total_terms": 11,
  "by_ontology": [{"ontology_type": "tcdb", "term_count": 11, "gene_count": 2, "tree": null, "tree_code": null}],
  "by_term": [
    {
      "term_id": "tcdb:8.A.159",
      "term_name": "The MARCH Ubiquitin Ligase (MARCH) Family",
      "level": 2,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.26.10",
      "term_name": "ATP-dependent folic acid uptake porter, FolT/EcfT/EcfA1/EcfA2.",
      "level": 4,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.25.8",
      "term_name": "An ECF ABC transporter with 4 subunits, EcfS/EcfT/EcfA/EcfA^.",
      "level": 4,
      "ontology_type": "tcdb",
      "count": 1
    },
    {
      "term_id": "tcdb:3.A.1.25.5",
      "term_name": "Biotin/Riboflavin ECF transport system, EcfAA^T/RibU/BioY.",
      "level": 4,
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
    ...
  ],
  "terms_per_gene_min": 1,
  "terms_per_gene_max": 10,
  "terms_per_gene_median": 5.5,
  "returned": 11,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"tcdb": ["sources", "evidence", "tier"]},
  "by_evidence": [{"evidence": "family_inferred", "count": 7}, {"evidence": "homology", "count": 4}],
  "by_tier": [{"tier": "null", "count": 7}, {"tier": 3, "count": 4}],
  "by_sources": [{"source": "eggnog", "count": 7}, {"source": "tcdb_diamond", "count": 4}],
  "by_call_class": [],
  "by_tcdb_call": [
    {"tcdb_call": "eggnog", "count": 7},
    {"tcdb_call": "diamond_best_hit", "count": 3},
    {"tcdb_call": "diamond_tier", "count": 1}
  ],
  "evidence_score_stats": null,
  "evidence_score_signals": null,
  "filters_applied": {},
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0024",
      "term_id": "tcdb:8.A.159",
      "term_name": "The MARCH Ubiquitin Ligase (MARCH) Family",
      "level": 2,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "homology",
      "tcdb_call": "diamond_tier",
      "tcdb_gate": "below_gate",
      "tcdb_calls": ["diamond_tier"]
    },
    {
      "locus_tag": "PMM0125",
      "term_id": "tcdb:3.A.1.25",
      "term_name": "The Biotin Uptake Transporter (BioMNY) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "tcdb_call": "eggnog",
      "tcdb_gate": "annotated",
      "tcdb_calls": ["eggnog"]
    },
    {
      "locus_tag": "PMM0125",
      "term_id": "tcdb:3.A.1.25.5",
      "term_name": "Biotin/Riboflavin ECF transport system, EcfAA^T/RibU/BioY.",
      "level": 4,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "homology",
      "tcdb_call": "diamond_best_hit",
      "tcdb_gate": "below_gate",
      "tcdb_calls": ["diamond_best_hit", "diamond_tier", "eggnog"]
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
  "by_tcdb_call": [],
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
      "term_name": "The Cobalamin Precursor (B12-P) Family",
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
  "returned": 7,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "no_terms": [],
  "trust_axes": {"tcdb": ["sources", "evidence", "tier"]},
  "by_evidence": [{"evidence": "family_inferred", "count": 7}],
  "by_tier": [{"tier": "null", "count": 7}],
  "by_sources": [{"source": "eggnog", "count": 7}],
  "by_call_class": [],
  "by_tcdb_call": [{"tcdb_call": "eggnog", "count": 7}],
  "evidence_score_stats": null,
  "evidence_score_signals": null,
  "filters_applied": {"max_tier": 2},
  "skipped_ontologies": [{"ontology": "kegg", "reason": "does not carry the max_tier filter"}],
  "warnings": [
    "Dropped 1 ontologies that do not carry max_tier: kegg. Re-run without max_tier to see them.",
    "max_tier=2 kept 7 rows that carry no tier — not a tier-1 call: tier is set only on truncated diamond edges (for TCDB,..."
  ],
  "results": [
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.25",
      "term_name": "The Biotin Uptake Transporter (BioMNY) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "tcdb_call": "eggnog",
      "tcdb_gate": "annotated",
      "tcdb_calls": ["eggnog"]
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.28",
      "term_name": "The Queuosine (Queuosine) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "tcdb_call": "eggnog",
      "tcdb_gate": "annotated",
      "tcdb_calls": ["eggnog"]
    },
    {
      "locus_tag": "PMM0392",
      "term_id": "tcdb:3.A.1.29",
      "term_name": "The Methionine Precursor (Met-P) Family",
      "level": 3,
      "is_informative": true,
      "ontology_type": "tcdb",
      "evidence": "family_inferred",
      "tcdb_call": "eggnog",
      "tcdb_gate": "annotated",
      "tcdb_calls": ["eggnog"]
    },
    ...
  ]
}
```

### Example 12: Filter TCDB rows by call kind — tcdb_call=['eggnog']

```example-call
gene_ontology_terms(locus_tags=["PMM0372", "PMM0710"], organism="MED4", ontology=["tcdb"], tcdb_call=["eggnog"])
```

*`tcdb_call` keeps only rows whose edges are of the listed kinds (`eggnog`, `diamond_tier`, `diamond_best_hit`; `list_filter_values('tcdb_call')`). The leaf rule still runs on every gated edge, so the filter never promotes an ancestor to a leaf. cynD keeps its eggNOG system tcdb:3.A.1.16.1. pstS drops out: its eggNOG call sits on tcdb:3.A.1.7, an ancestor of its best-hit system, so it is not a leaf. Envelope `by_tcdb_call` counts rows by representative call. With a single non-TCDB ontology the filter raises; with an ontology list it applies to tcdb and skips the rest.*

### Example 13: Filter out uninformative terms (KOs named "uncharacterized protein")

```example-call
gene_ontology_terms(locus_tags=["PMM0001"], organism="Prochlorococcus MED4", ontology="kegg", informative_only=True)
```

*Each result row carries `is_informative: bool` (always populated; coalesce of the sparse term-side `is_uninformative='true'` flag). Genome-wide effect on MED4 KEGG leaf rows: 1124 → 1094 with informative_only=True (30 rows, all KO-level — leaf mode never returns pathway-map rows; the flagged overview maps matter only in rollup / level queries). PMM0001's single KO is informative, so its row count is unchanged.*

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
  "by_tcdb_call": [],
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

### Example 14: Per-gene SignalP call with cleavage info

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
  "by_tcdb_call": [],
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

### Example 15: From overview to ontology details

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

- `ontology` accepts `str | list[str] | None`. With a list: a filter carried by all requested ontologies applies normally; carried by some but not all applies to those and drops the rest into `skipped_ontologies` with a warning; carried by none raises `ValueError`. An unknown ontology name always raises.

- TCDB rows are gated by default: only edges the KG stamps `tcdb_gate` `direct` (a system call) or `annotated` (a family or subfamily call) count, and leaf mode drops a node that is an ancestor of another gated target for the same gene. Leaf rows per gene therefore equal `gene_overview.tcdb_assignment_count`, and a gene can keep several sibling rows (ecfA1 PMM0125: 7 subfamilies). `include_weak_tcdb_hits=True` adds the `below_gate` DIAMOND edges (tier-3 calls, near-tie best hits, best hits under 40% identity) as extra rows; the default rows never change. Do not re-derive the gate from `tcdb_call` or `tier`.

- `tcdb_calls` lists the call kinds found anywhere on the row's lineage (the node, its ancestors and descendants) in precedence order, and `tcdb_call` / `tcdb_gate` describe the one edge the row reports. eggNOG plus a DIAMOND kind is independent agreement; `diamond_tier` and `diamond_best_hit` come from the same DIAMOND run, so the two together count as one source. `tier` is null on eggNOG rows and means different things on the two DIAMOND kinds (consensus tier vs identity band): never compare tiers across kinds.

- Trust filters (`sources`, `evidence`, `max_tier`, `min_evidence_score`, `call_class`, `tcdb_call`) mirror `genes_by_ontology` exactly — same defaults (`None`, never filter), same per-ontology axis gating, same `ValueError` on an unsupported axis (`min_evidence_score` with `ontology='tcdb'` raises: TCDB has no evidence score). See `docs://analysis/annotation_evidence` for the per-ontology axis table.

- Compact rows carry `evidence` on the 14 functional-edge ontologies (null on PSORTb/SignalP); `interpro_type` (interpro rows) and `call_class` (merops rows) are compact always. `tcdb_call`, `tcdb_gate` and `tcdb_calls` (tcdb rows) are compact too. `sources`, `evidence_score`, `tier` and native detail (`identity`, `qcov`, `evalue`, `tcdb_scov`, `tcdb_best_hit_rank`, `confidence_score`, `libraries`, `signal_peptide_*`, `localization_score`, ...) are verbose-only; `identity` and `qcov` are percent on both TCDB and MEROPS.

- CAZy rollup at `level=0` returns the 6 top-level classes (GH, GT, PL, CE, AA, CBM). Genes commonly belong to multiple top-level classes (e.g. a CBM-domain-containing GH); duplicates per `(gene × class)` are de-duped automatically.

- TCDB substrate-level questions ('which genes does this metabolite bind to?') chain via `genes_by_metabolite`, NOT this tool. Use `gene_ontology_terms(ontology='tcdb')` for the TC ids a gene is called to (e.g. 'which TCDB system or family is PMM1129 placed in?').

- `informative_only` (default False here) drops terms the KG flags uninformative — ontology roots and catch-all KO terms, plus the KEGG global / overview maps. It is term-side only and never restricts the gene set. See docs://analysis/annotation_evidence.

- `tcdb_call` filters edges before the row's representative edge is chosen, but in leaf mode the ancestor drop still runs over every gated edge. So a call kind that sits only on an ancestor of the gene's leaf returns nothing: `gene_ontology_terms(['PMM0710'], 'MED4', ontology=['tcdb'], tcdb_call=['eggnog'])` returns 0 rows, because pstS's eggNOG call is on tcdb:3.A.1.7, an ancestor of its best-hit leaf tcdb:3.A.1.7.6. Zero rows under `tcdb_call` means no leaf of that kind, not no call of that kind; drop the filter and read `tcdb_calls`, or use `mode='rollup'`.

## Package import equivalent

```python
from multiomics_explorer import gene_ontology_terms

result = gene_ontology_terms(locus_tags=..., organism=...)
# returns dict with keys: total_matching, total_genes, total_terms, by_ontology, by_term, terms_per_gene_min, terms_per_gene_max, terms_per_gene_median, returned, offset, truncated, not_found, no_terms, trust_axes, by_evidence, by_tier, by_sources, by_call_class, by_tcdb_call, evidence_score_stats, evidence_score_signals, filters_applied, skipped_ontologies, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
