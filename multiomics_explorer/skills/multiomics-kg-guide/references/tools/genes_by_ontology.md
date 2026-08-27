# genes_by_ontology

## What it does

Find (gene × term) pairs for an ontology, scoped by terms and/or level.

Three modes:
- `term_ids` only — gene discovery by pathway (walk DOWN from each term).
- `level` only — pathway definitions at level N (walk UP from leaves).
- `level` + `term_ids` — scoped rollup (walk UP, restrict to given terms).

Single-organism enforced. Default `limit=500` because this tool feeds
enrichment via TERM2GENE. `min/max_gene_set_size` is organism-scoped
(matches `ontology_landscape`).

[TRUST] `sources` / `evidence` / `max_tier` / `min_evidence_score` /
`call_class` / `interpro_type` filter on the per-edge trust profile;
defaults never filter. See docs://analysis/annotation_evidence.

Routing: pipe `results` into `pathway_enrichment` / `cluster_enrichment`
as TERM2GENE; chain from `search_ontology` for term discovery;
`gene_ontology_terms` for per-gene reverse lookup. For
substrate-anchored TCDB / EC questions ("which genes transport / act
on compound X?"), use `genes_by_metabolite` instead. See
docs://guide/conventions for the hierarchy `level` and BRITE-tree
conventions; docs://analysis/enrichment for the enrichment workflow.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') | — | Ontology for these term_ids / this level. |
| organism | string | — | Organism (case-insensitive substring match, e.g. 'MED4'). Required — single-valued. Use list_organisms for valid values. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'. See docs://guide/conventions for the BRITE-tree scoping rule. |
| level | int \| None | None | Hierarchy level to roll UP to (0 = broadest). At least one of `level` or `term_ids` must be provided. See docs://guide/conventions. |
| term_ids | list[string] \| None | None | Ontology term IDs (from search_ontology). Without `level`: expand DOWN from each input term. With `level`: scope rollup to these level-N terms. |
| min_gene_set_size | int | 5 | Exclude terms with fewer organism-scoped genes than this. Matches `ontology_landscape`'s organism-scoped convention. |
| max_gene_set_size | int | 500 | Exclude terms with more organism-scoped genes than this. Matches `ontology_landscape`'s organism-scoped convention. |
| informative_only | bool | False | When True, exclude terms flagged uninformative in KG (e.g. KEGG 'metabolic pathways' map00001, GO root 'biological_process' go:0008150). Term-side filter only — never restricts the gene set. Default False (opt-in). |
| summary | bool | False | If true, omit `results` (envelope only). |
| verbose | bool | False | Include function_description and sparse level_is_best_effort. |
| sources | list[string] \| None | None | Keep rows whose edge sources[] contains any of these values (e.g. ['eggnog']). Valid on the 14 functional-edge ontologies (not PSORTb / SignalP). Default None never filters. See list_filter_values(filter_type='sources'). |
| evidence | list[string] \| None | None | Keep rows whose compact evidence ladder value is in this list (curated > signature > homology > family_inferred > domain_inferred). Valid on the 14 functional-edge ontologies. Default None never filters. |
| max_tier | int \| None | None | Keep rows with edge tier <= this value OR tier IS NULL (diamond truncation depth, 1-3; tier-null edges are always kept - see by_tier's null bucket). Valid on tcdb, merops only. |
| min_evidence_score | float \| None | None | Keep rows with edge evidence_score >= this cutoff (composite trust score, 0-1; the only native-scalar cutoff allowed). Valid on go_bp/mf/cc, ec, pfam, cazy, tcdb, merops. Envelope adds evidence_score_signals when set. |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; leaving unfiltered mixes in catalytically-dead homologs (nonpeptidase_homolog) - the envelope warns when it does. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |
| limit | int | 500 | Max rows returned. Default 500 — this tool feeds enrichment. |
| offset | int | 0 | Skip N rows before limit |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
ontology, organism_name, total_matching, total_genes, total_terms, total_categories, genes_per_term_min, genes_per_term_median, genes_per_term_max, terms_per_gene_min, terms_per_gene_median, terms_per_gene_max, by_category, by_level, top_terms, n_best_effort_terms, not_found, wrong_ontology, wrong_level, filtered_out, returned, offset, truncated, trust_axes, warnings, filters_applied, skipped_ontologies, by_evidence, by_tier, by_sources, by_call_class, evidence_score_stats, results
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
- **returned** (int): Rows in this response
- **offset** (int): Offset into full result set
- **truncated** (bool): True when total_matching > offset + returned
- **trust_axes** (object): Trust axes this ontology carries, e.g. {'tcdb': ['sources','evidence','evidence_score','tier']}.
- **warnings** (list[string]): Auto-warnings (e.g. nonpeptidase_homolog rows without a call_class filter).
- **filters_applied** (object): Echo of the trust filters that were actually set on this call.
- **skipped_ontologies** (list[object]): Empty for single-ontology tools; reserved for multi-ontology callers.
- **by_evidence** (list[object]): Rollup of the compact evidence column over every matching row, not just the page you are reading.
- **by_tier** (list[object]): Rollup of tier over every matching row; carries an explicit 'null' bucket. Present in compact mode too, where tier itself is not on the row.
- **by_sources** (list[object]): Membership counts per source value over every matching row.
- **by_call_class** (list[object]): Rollup of MEROPS call_class over every matching row (merops only).
- **evidence_score_stats** (object | None): {min, median, max, n_null} over evidence_score across every matching row.
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
| localization_score | float \| None (optional) | PSORTb confidence score (sparse: only set when ontology='subcellular_localization'). Range 7.5–10.0. |
| signal_peptide_probability | float \| None (optional) | SignalP winning-class probability (sparse: only set when ontology='signal_peptide_type'). Range 0–1. |
| signal_peptide_cleavage_site | int \| None (optional) | SignalP-predicted cleavage residue position (sparse: only set when ontology='signal_peptide_type'; absent when SignalP reports no cleavage site). |
| signal_peptide_cleavage_probability | float \| None (optional) | SignalP cleavage-site probability (sparse: only set when ontology='signal_peptide_type' and cleavage_site present). |
| evidence | string \| None (optional) | Compact trust ladder: curated > signature > homology > family_inferred > domain_inferred. Present on the 14 functional-edge ontologies; null on PSORTb/SignalP. |
| call_class | string \| None (optional) | MEROPS peptidase call (sparse: merops only). 'nonpeptidase_homolog' rows are catalytically dead. |
| interpro_type | string \| None (optional) | InterPro entry type (sparse: interpro only), e.g. 'DOMAIN', 'FAMILY', 'HOMOLOGOUS_SUPERFAMILY'. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| sources | list[string] \| None (optional) | Provenance tags on this edge (verbose only; sparse outside the 14 functional-edge ontologies), e.g. ['eggnog']. |
| evidence_score | float \| None (optional) | Composite trust score in [0,1] (verbose only; sparse: go_bp/mf/cc, ec, pfam, cazy, tcdb, merops). |
| tier | int \| None (optional) | Diamond truncation depth 1-3 (verbose only; sparse: tcdb, merops; owned-but-null when the edge carries no tier). |
| attachment_depth | string \| None (optional) | TCDB rollup attachment depth: 'most_specific' or 'superseded' (verbose only; sparse: tcdb only). |
| confidence_score | float \| None (optional) | Native rank score (verbose only; sparse: tcdb, merops). |
| source_agreement | string \| None (optional) | TCDB two-source agreement detail (verbose only; sparse: tcdb only). |
| pfam_support | string \| None (optional) | Pfam-domain corroboration detail (verbose only; sparse: tcdb, merops). |
| go_support | string \| None (optional) | GO corroboration detail (verbose only; sparse: tcdb only). |
| identity | float \| None (optional) | Alignment percent identity (verbose only; sparse: tcdb, merops). |
| qcov | float \| None (optional) | Query coverage fraction (verbose only; sparse: tcdb, merops). |
| evalue | float \| None (optional) | Alignment e-value (verbose only; sparse: tcdb, merops, interpro, ncbifam). Never a filter cutoff. |
| consensus_n | int \| None (optional) | Number of corroborating calls in consensus (verbose only; sparse: tcdb, merops). |
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
{"ontology": "go_bp", "organism_name": "Prochlorococcus MED4", "total_matching": 30, "total_genes": 30, "total_terms": 1, "total_categories": 1, "by_level": [{"level": 6, "n_terms": 1, "n_genes": 30, "row_count": 30}], "top_terms": [{"term_id": "go:0006260", "term_name": "DNA replication", "count": 30}], "n_best_effort_terms": 0, "not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": [], "returned": 5, "truncated": true, "offset": 0, "results": [{"locus_tag": "PMM0001", "gene_name": "dnaN", "product": "DNA polymerase III", "gene_category": "Replication", "term_id": "go:0006260", "term_name": "DNA replication", "level": 6}]}
```

### Example 2: Mode 2 — pathway definitions at level N (level only)

```example-call
genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
```

```example-response
{"ontology": "cyanorak_role", "organism_name": "Prochlorococcus MED4", "total_matching": 1740, "total_genes": 1100, "total_terms": 69, "by_level": [{"level": 1, "n_terms": 69, "n_genes": 1100, "row_count": 1740}], "top_terms": [{"term_id": "cyanorak.role:A.1", "term_name": "...", "count": 120}], "returned": 500, "truncated": true, "results": [...]}
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

### Example 7: TCDB family → gene drill-down (with descendant expansion)

```example-call
genes_by_ontology(ontology="tcdb", organism="MED4", term_ids=["tcdb:1.A.1"])
```

```example-response
{"ontology": "tcdb", "organism_name": "Prochlorococcus MED4",
 "total_matching": 1, "total_genes": 1, "total_terms": 1,
 "by_level": [{"level": 0, "n_terms": 1, "n_genes": 1, "row_count": 1}],
 "top_terms": [{"term_id": "tcdb:1.A.1", "term_name": "Voltage-gated Ion Channel (VIC) Superfamily", "count": 1}],
 "results": [{"locus_tag": "PMM1129", "term_id": "tcdb:1.A.1", "term_name": "Voltage-gated Ion Channel (VIC) Superfamily", "level": 0}]}
```

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
  "organism_name": "MED4",
  "total_matching": 45,
  "...": "...",
  "results": [
    {"locus_tag": "PMM0001", "gene_name": "...",
     "term_id": "psortb_OuterMembrane",
     "term_name": "Outer membrane", "level": 0,
     "is_informative": true,
     "localization_score": 9.93}
  ]
}
```

### Example 10: SignalP lipoproteins with cleavage info

```example-call
genes_by_ontology(ontology="signal_peptide_type", term_ids=["signalp_LIPO"], organism="MED4")
```

```example-response
{
  "...": "...",
  "results": [
    {"locus_tag": "PMM0123",
     "term_id": "signalp_LIPO", "term_name": "Lipoprotein signal peptide (Sec/SPII)",
     "level": 0, "is_informative": true,
     "signal_peptide_probability": 0.97,
     "signal_peptide_cleavage_site": 22,
     "signal_peptide_cleavage_probability": 0.91}
  ]
}
```

### Example 11: InterPro homologous-superfamily census (interpro_type facet)

```example-call
genes_by_ontology(ontology="interpro", organism="MED4", term_ids=["interpro:IPR027417"])
```

```example-response
{"ontology": "interpro", "organism_name": "Prochlorococcus MED4",
 "total_genes": 119, "total_terms": 1,
 "top_terms": [{"term_id": "interpro:IPR027417", "term_name": "P-loop containing nucleoside triphosphate hydrolase", "count": 119}],
 "results": [{"locus_tag": "PMM0001", "term_id": "interpro:IPR027417", "term_name": "P-loop containing nucleoside triphosphate hydrolase", "level": 2, "interpro_type": "HOMOLOGOUS_SUPERFAMILY", "evidence": "signature"}]}
```

### Example 12: MEROPS peptidase-only clan census (call_class filter)

```example-call
genes_by_ontology(ontology="merops", organism="MIT1002", level=0, call_class=["peptidase"])
```

```example-response
# call_class=['peptidase'] restricts the clan census to genes whose best
# MEROPS edge calls them an actual peptidase, dropping nonpeptidase_homolog
# rows (catalytically-dead homologs that still resemble a peptidase family
# by sequence). MIT1002 level=0: 7 clans pass the default gene-set-size
# filter — SC 22, MA 18, MH 8, PB 8, SB 6, MG 5, SK 5. No warning fires
# because the filter already excludes the ambiguous rows.
{"ontology": "merops", "organism_name": "Alteromonas macleodii MIT1002",
 "by_call_class": [{"call_class": "peptidase", "count": 67}],
 "top_terms": [
   {"term_id": "merops.clan:SC", "term_name": "...", "count": 22},
   {"term_id": "merops.clan:MA", "term_name": "...", "count": 18},
   {"term_id": "merops.clan:MH", "term_name": "...", "count": 8}
 ],
 "warnings": [],
 "results": [{"locus_tag": "MIT1002_03660", "term_id": "merops.clan:SC", "term_name": "...", "level": 0, "evidence": "curated", "call_class": "peptidase"}]}
```

### Example 13: MEROPS clan census without call_class (warns)

```example-call
genes_by_ontology(ontology="merops", organism="MIT1002", level=0)
```

```example-response
# Omitting call_class folds nonpeptidase_homolog rows into the census —
# MIT1002 level=0 returns 10 clans (vs 7 with call_class=['peptidase'])
# and fires a warning naming the catalytically-dead-homolog rows.
{"ontology": "merops", "organism_name": "Alteromonas macleodii MIT1002",
 "warnings": ["12 rows call_class='nonpeptidase_homolog' (catalytically-dead homologs) are included in this clan census"],
 "results": [{"locus_tag": "MIT1002_04012", "term_id": "merops.clan:C26", "term_name": "...", "level": 0, "evidence": "homology", "call_class": "nonpeptidase_homolog"}]}
```

### Example 14: TCDB trust detail — sources / evidence_score / tier (verbose)

```example-call
genes_by_ontology(ontology="tcdb", organism="MED4", term_ids=["tcdb:3.A.1"], verbose=True)
```

```example-response
# Compact rows carry only `evidence` (the ladder). verbose=True adds
# `sources`, `evidence_score`, `tier` plus TCDB's native detail
# (confidence_score, source_agreement, pfam_support, go_support,
# identity, qcov, evalue, consensus_n, attachment_depth). On a
# hierarchical rollup like tcdb:3.A.1, trust columns come from the
# gene's single best edge under the term (ranked by evidence_score) —
# never a duplicated per-edge row.
{"ontology": "tcdb", "organism_name": "Prochlorococcus MED4",
 "results": [{"locus_tag": "PMM0392", "term_id": "tcdb:3.A.1", "term_name": "ATP-binding Cassette (ABC) Superfamily",
              "level": 2, "evidence": "homology", "sources": ["eggnog"], "evidence_score": 0.6, "tier": 2,
              "confidence_score": 0.6, "attachment_depth": "most_specific"}]}
```

### Example 15: Cutoff on evidence_score (the only numeric trust filter)

```example-call
genes_by_ontology(ontology="tcdb", organism="MED4", term_ids=["tcdb:3.A.1"], min_evidence_score=0.6, evidence=["homology"])
```

```example-response
# min_evidence_score is the only numeric cutoff anywhere in the trust
# surface — no filter exists on native scalars (evalue, bit_score,
# confidence_score, ...). Setting it adds `evidence_score_signals` to
# the envelope, naming which ControlledVocabulary signals fired
# (composite inputs behind the score). MED4 tcdb: evidence=['homology']
# AND evidence_score>=0.6 narrows 670 rows to 98.
{"ontology": "tcdb", "organism_name": "Prochlorococcus MED4",
 "filters_applied": {"evidence": ["homology"], "min_evidence_score": 0.6},
 "evidence_score_signals": {"Gene_has_tcdb_family": ["source_agreement", "pfam_support", "go_support", "identity", "qcov"]},
 "results": [{"locus_tag": "PMM0392", "term_id": "tcdb:3.A.1", "evidence": "homology", "evidence_score": 0.6}]}
```

### Example 16: Filter out uninformative terms (term-side filter, opt-in)

```example-call
genes_by_ontology(ontology="kegg", organism="MED4", level=3, informative_only=True)
```

```example-response
# `informative_only=True` excludes terms flagged `is_uninformative='true'`
# (~224 terms genome-wide, concentrated in KEGG / Cyanorak / TIGR /
# CogFunctionalCategory / GO-CC / GO-MF / GO-BP). The filter is term-side
# only — never narrows the gene set.
#
# Detail rows (and `per_term` mode) carry `is_informative: bool`. The
# `per_gene` aggregate mode does NOT include `is_informative` because the
# row is per-gene, not per-term.
{
  "ontology": "kegg", "organism_name": "Prochlorococcus MED4",
  "results": [
    {"locus_tag": "PMM0001", "term_id": "kegg:K02338", "term_name": "DNA polymerase III subunit beta", "level": 3, "is_informative": true}
  ]
}
```

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

- At least one of `level` or `term_ids` must be set — calling without either is an error.

- Results are `(gene × term)` pairs, not distinct genes — use `total_genes` for the gene count. `total_matching` is the row count.

- Gene-set-size filter is organism-scoped via descendants — count of distinct genes annotated to the term or any descendant for `$organism`. Matches `ontology_landscape`'s convention.

- For GO (a DAG), level slicing is a best-effort approximation — `level_is_best_effort` flags rows where the min-path to root was ambiguous. Check `ontology_landscape`'s `best_effort_share` per level.

- `level_is_best_effort` is a sparse column — absent when not GO / not best-effort. In pandas, call `df['level_is_best_effort'].fillna(False)` before boolean filtering.

- `organism` is required and single-valued. For cross-organism browsing, loop the tool or use `gene_ontology_terms`.

- Pfam is a 2-level ontology: `level=1` → Pfam domains (leaf), `level=0` → PfamClan (parent). Both kinds of IDs are accepted under `ontology='pfam'`.

- KEGG: gene edges only hit the KO leaf (`level=3`). Passing `level=0/1/2` rolls up to category/subcategory/pathway via `is_a`.

- BRITE: gene edges hit the KO leaf (`level=3`, same as KEGG). Passing `level=0/1/2` rolls up through BRITE tree hierarchy. Each BRITE tree is a separate functional classification — use `tree` to scope to a specific tree (e.g. `tree='transporters'`). Without `tree`, results mix all BRITE trees. Use `list_filter_values('brite_tree')` to discover available trees.

- Flat ontologies (`cog_category`, `tigr_role`) have only `level=0`. Passing `level >= 1` in Mode 2 returns empty results; in Mode 3 the ids route to `wrong_level`.

- Supported ontologies: `go_bp`, `go_mf`, `go_cc`, `ec`, `kegg`, `cog_category`, `cyanorak_role`, `tigr_role`, `pfam`, `brite`, `tcdb`, `cazy`, `subcellular_localization`, `signal_peptide_type`, `interpro`, `ncbifam`, `merops`.

- Trust surface: compact rows on the 14 functional-edge ontologies (everything except PSORTb/SignalP) carry `evidence` — a categorical ladder `curated > signature > homology > family_inferred > domain_inferred`. `sources`, `evidence_score`, and `tier` (TCDB + MEROPS only) move to verbose. Filters `sources`, `evidence`, `max_tier`, `min_evidence_score` default to `None` and never narrow the result unless set; `min_evidence_score` is the only numeric cutoff anywhere in the surface. `call_class` (`peptidase` / `inhibitor` / `nonpeptidase_homolog`) is MEROPS-only and compact always (not verbose-gated) because it changes the biological reading. `interpro_type` is InterPro-only and compact always. Passing an axis an ontology doesn't carry raises `ValueError` naming that ontology's axes. See `docs://analysis/annotation_evidence` for the full per-ontology profile.

- `max_tier` keeps tier-null rows (`r.tier <= max_tier OR r.tier IS NULL`) — an eggNOG-only TCDB edge with no `tier` passes any `max_tier` filter. Check the envelope's `by_tier` `"null"` bucket to see how many rows that affects.

- `sources` is set-membership ANY (`any(s IN $sources WHERE s IN r.sources)`), not exact match — an edge with `sources=['eggnog', 'blast']` matches `sources=['eggnog']`.

- Row strip rule: a row only carries the columns its ontology owns. `tier` never appears on a `kegg` row (KEGG carries no `tier` axis); `interpro_type` never appears on a `tcdb` row. Owned-but-null stays — e.g. `tier` is present and `null` on a TCDB edge with only eggNOG support (no tier assigned).

```mistake
genes_by_ontology(ontology='go_bp', organism='MED4', level=3, call_class=['peptidase'])  # call_class is MEROPS-only
```

```correction
list_filter_values(filter_type='trust_axes', ontology='go_bp')  # check axes first — go_bp supports sources/evidence/evidence_score only, raises ValueError otherwise
```

- TCDB is hierarchical (5 levels: `tc_class` → `tc_subclass` → `tc_family` → `tc_subfamily` → `tc_specificity`). `term_ids=['tcdb:1.A.1']` expands DOWN through ~31 descendant subfamilies before binding to genes via `Gene_has_tcdb_family`.

- CAZy is a small ontology (~64 terms, 6 classes / 58 families). `level=0` gives ~6 class-level rows (GH, GT, PL, CE, AA, CBM); `level=1` gives families. With default `min_gene_set_size=5`, many CAZy terms are filtered out — pass `min_gene_set_size=1` to see all.

- Substrate-anchored TCDB questions ('which genes transport sucrose?') chain via `genes_by_metabolite`, NOT `genes_by_ontology`. Use `genes_by_ontology(ontology='tcdb', term_ids=[...])` for *family*-level questions ('which genes are in voltage-gated ion channels?'). The metabolite-anchored route includes all TCDB families curating the substrate; the family-anchored route here is anchored on a single family ID and misses cross-family substrate hits.

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

## Package import equivalent

```python
from multiomics_explorer import genes_by_ontology

result = genes_by_ontology(ontology=..., organism=...)
# returns dict with keys: ontology, organism_name, total_matching, total_genes, total_terms, total_categories, genes_per_term_min, genes_per_term_median, genes_per_term_max, terms_per_gene_min, terms_per_gene_median, terms_per_gene_max, by_category, by_level, top_terms, n_best_effort_terms, not_found, wrong_ontology, wrong_level, filtered_out, offset, trust_axes, warnings, filters_applied, skipped_ontologies, by_evidence, by_tier, by_sources, by_call_class, evidence_score_stats, evidence_score_signals, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
