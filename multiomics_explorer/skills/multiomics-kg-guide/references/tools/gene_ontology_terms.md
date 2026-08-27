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
| organism | string | — | Organism (case-insensitive substring match, e.g. 'MED4'). Required — single-valued. |
| ontology | list[string ('go_bp', 'go_mf', 'go_cc', 'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops')] \| None | None | Filter to one ontology, or a list of ontologies (trust filters/facets shape all-or-skip-or-raise per docs://guide/conventions). None returns all. |
| mode | string ('leaf', 'rollup') | leaf | 'leaf' returns most-specific annotations (default). 'rollup' walks up to ancestors at the given level. |
| level | int \| None | None | Hierarchy level (0 = broadest). In leaf mode: filter to leaves at this level. In rollup mode: required — target ancestor level. See docs://guide/conventions. |
| tree | string \| None | None | BRITE tree name filter. Only valid when ontology='brite'. See docs://guide/conventions for the BRITE-tree scoping rule. |
| informative_only | bool | False | When True, exclude terms flagged uninformative in KG (e.g. KEGG 'metabolic pathways' map00001, GO root 'biological_process' go:0008150). Term-side filter only — never restricts the gene set. Default False (opt-in). |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include organism_name per row. |
| sources | list[string] \| None | None | Keep rows whose edge sources[] contains any of these values (e.g. ['eggnog']). Valid on the 14 functional-edge ontologies (not PSORTb / SignalP). Default None never filters. See list_filter_values(filter_type='sources'). |
| evidence | list[string] \| None | None | Keep rows whose compact evidence ladder value is in this list (curated > signature > homology > family_inferred > domain_inferred). Valid on the 14 functional-edge ontologies. Default None never filters. |
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
- **by_evidence** (list[object]): Rollup of the compact evidence column over result rows.
- **by_tier** (list[object]): Rollup of tier over result rows; carries an explicit 'null' bucket.
- **by_sources** (list[object]): Membership counts per source value over result rows.
- **by_call_class** (list[object]): Rollup of MEROPS call_class over result rows (merops only).
- **evidence_score_stats** (object | None): {min, median, max, n_null} over evidence_score in result rows.
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
| evidence | string \| None (optional) | Compact trust ladder: curated > signature > homology > family_inferred > domain_inferred. Present on the 14 functional-edge ontologies; null on PSORTb/SignalP. |
| call_class | string \| None (optional) | MEROPS peptidase call (sparse: merops only). |
| interpro_type | string \| None (optional) | InterPro entry type (sparse: interpro only). |
| attachment_depth | string \| None (optional) | TCDB attachment depth: 'most_specific' or 'superseded' (verbose only; sparse: tcdb only). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| sources | list[string] \| None (optional) | Provenance tags on this edge (verbose only; sparse). |
| evidence_score | float \| None (optional) | Composite trust score in [0,1] (verbose only; sparse). |
| tier | int \| None (optional) | Diamond truncation depth 1-3 (verbose only; sparse: tcdb, merops). |
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
  "total_matching": 2, "total_genes": 1, "total_terms": 2,
  "by_ontology": [{"ontology_type": "go_bp", "term_count": 2, "gene_count": 1}],
  "by_term": [
    {"term_id": "go:0006260", "term_name": "DNA replication", "ontology_type": "go_bp", "count": 1},
    {"term_id": "go:0006271", "term_name": "DNA strand elongation involved in DNA replication", "ontology_type": "go_bp", "count": 1}
  ],
  "terms_per_gene_min": 2, "terms_per_gene_max": 2, "terms_per_gene_median": 2.0,
  "returned": 2, "truncated": false, "offset": 0, "not_found": [], "no_terms": [],
  "results": [
    {"locus_tag": "PMM0001", "term_id": "go:0006260", "term_name": "DNA replication"},
    {"locus_tag": "PMM0001", "term_id": "go:0006271", "term_name": "DNA strand elongation involved in DNA replication"}
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
  "total_matching": 4, "total_genes": 2, "total_terms": 2,
  "by_ontology": [{"ontology_type": "cazy", "term_count": 2, "gene_count": 2}],
  "by_term": [
    {"term_id": "cazy:CBM", "term_name": "Carbohydrate-Binding Module", "ontology_type": "cazy", "count": 2},
    {"term_id": "cazy:GH",  "term_name": "Glycoside Hydrolases",        "ontology_type": "cazy", "count": 2}
  ],
  "results": [
    {"locus_tag": "PMM0584", "term_id": "cazy:CBM", "term_name": "Carbohydrate-Binding Module"},
    {"locus_tag": "PMM0584", "term_id": "cazy:GH",  "term_name": "Glycoside Hydrolases"},
    {"locus_tag": "PMM1322", "term_id": "cazy:CBM", "term_name": "Carbohydrate-Binding Module"},
    {"locus_tag": "PMM1322", "term_id": "cazy:GH",  "term_name": "Glycoside Hydrolases"}
  ]
}
```

### Example 6: TCDB family annotations for a gene

```example-call
gene_ontology_terms(locus_tags=["PMM1129"], organism="MED4", ontology="tcdb")
```

### Example 7: Multiple ontologies in one call (ontology now accepts a list)

```example-call
gene_ontology_terms(locus_tags=["PMM0392"], organism="MED4", ontology=["tcdb", "merops"])
```

```example-response
# `ontology` accepts a single str, a list, or None (all ontologies).
# PMM0392 has tcdb edges but no merops edges — merops contributes
# nothing to `results` and nothing to `by_ontology`; no error, no
# skipped_ontologies entry (skip/raise only applies to *filters*
# unsupported on one of the requested ontologies, not to empty hits).
{"total_matching": 8, "by_ontology": [{"ontology_type": "tcdb", "term_count": 8, "gene_count": 1}],
 "results": [{"locus_tag": "PMM0392", "term_id": "tcdb:3.A.1.28", "term_name": "...", "evidence": "homology"}]}
```

### Example 8: TCDB leaf mode — most-specific attachment only (default)

```example-call
gene_ontology_terms(locus_tags=["PMM0392"], organism="MED4", ontology=["tcdb"], mode="leaf")
```

```example-response
# Default mode='leaf' on tcdb applies `attachment_depth='most_specific'`
# under the hood — PMM0392's 8 raw edges collapse to the gene's deepest
# attachment(s) only. Genome-wide MED4: 670 raw tcdb edges → 597 rows
# under this predicate (73 rows are superseded — a less-specific
# ancestor attachment made redundant by a deeper one on the same gene).
{"total_matching": 1, "results": [{"locus_tag": "PMM0392", "term_id": "tcdb:3.A.1.28", "term_name": "...", "attachment_depth": "most_specific", "evidence": "homology"}]}
```

### Example 9: TCDB leaf mode with include_superseded — see the collapsed rows too

```example-call
gene_ontology_terms(locus_tags=["PMM0392"], organism="MED4", ontology=["tcdb"], mode="leaf", include_superseded=True)
```

```example-response
# include_superseded=True adds back the rows most_specific mode drops —
# each labelled attachment_depth='superseded'. 'Superseded' means less
# specific, not wrong: it is a real annotation, just not the gene's
# deepest call for that lineage.
{"total_matching": 2, "results": [
  {"locus_tag": "PMM0392", "term_id": "tcdb:3.A.1.28", "term_name": "...", "attachment_depth": "most_specific", "evidence": "homology"},
  {"locus_tag": "PMM0392", "term_id": "tcdb:3.A.1", "term_name": "ATP-binding Cassette (ABC) Superfamily", "attachment_depth": "superseded", "evidence": "homology"}
]}
```

### Example 10: MEROPS leaf annotations with call_class and confidence

```example-call
gene_ontology_terms(locus_tags=["MIT1002_03660"], organism="MIT1002", ontology=["merops"], verbose=True)
```

```example-response
{"total_matching": 1, "results": [
  {"locus_tag": "MIT1002_03660", "term_id": "merops.family:S14", "term_name": "...", "evidence": "curated", "call_class": "peptidase",
   "sources": ["merops"], "evidence_score": 1.0, "tier": 1, "confidence_score": 1.0}
]}
```

### Example 11: Filter by evidence + max_tier (skip/raise matrix — multi-ontology)

```example-call
gene_ontology_terms(locus_tags=["PMM0392"], organism="MED4", ontology=["tcdb", "kegg"], max_tier=2)
```

```example-response
# max_tier is a tcdb/merops-only axis. Carried by some of the
# requested ontologies (tcdb) but not all (kegg has no tier axis) →
# apply to tcdb, drop kegg into `skipped_ontologies` with a warning.
# Requesting max_tier with ontology=['kegg'] alone (no ontology in the
# set supports it) raises ValueError instead.
{"skipped_ontologies": [{"ontology": "kegg", "reason": "max_tier is not a trust axis of ontology='kegg'"}],
 "warnings": ["ontology 'kegg' dropped from this call: max_tier does not apply to it"],
 "results": [{"locus_tag": "PMM0392", "term_id": "tcdb:3.A.1.28", "term_name": "...", "tier": 2}]}
```

### Example 12: Filter out uninformative terms (e.g. catch-all KEGG modules)

```example-call
gene_ontology_terms(locus_tags=["PMM0001"], organism="Prochlorococcus MED4", ontology="kegg", informative_only=True)
```

```example-response
# Filter effect on Prochlorococcus MED4 KEGG: 1124 leaf-mode rows → 1094
# with informative_only=True (30 rows filtered, ~2.7%). Each result row
# carries an `is_informative: bool` column (always populated;
# coalesce of sparse term-side `is_uninformative='true'` flag).
{
  "total_matching": 1094,
  "results": [
    {"locus_tag": "PMM0001", "term_id": "kegg:K02338", "term_name": "DNA polymerase III subunit beta", "is_informative": true},
    ...
  ]
}
```

### Example 13: Per-gene SignalP call with cleavage info

```example-call
gene_ontology_terms(locus_tags=["PMM0001", "PMM0123"], ontology="signal_peptide_type", organism="MED4", mode="leaf")
```

```example-response
{
  "...": "...",
  "results": [
    {"locus_tag": "PMM0001", "term_id": "signalp_SP",
     "term_name": "Signal peptide (Sec/SPI)", "level": 0,
     "is_informative": true,
     "signal_peptide_probability": 0.93,
     "signal_peptide_cleavage_site": 25,
     "signal_peptide_cleavage_probability": 0.85},
    {"locus_tag": "PMM0123", "term_id": "signalp_PILIN",
     "term_name": "Pilin-like signal peptide (Sec/SPIII)", "level": 0,
     "is_informative": true,
     "signal_peptide_probability": 0.78}
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

## Good to know

- organism is required — single-valued. Locus tags must belong to the specified organism.

- ontology=None returns ALL ontology types — use ontology filter when you only need one type

- Default mode='leaf' returns only leaf (most specific) terms — ancestor terms like 'metabolic process' are excluded because they are implied by the more specific child terms

- mode='rollup' requires `level` (and optionally `ontology`). It walks UP the hierarchy from leaf annotations to the requested level, returning rolled-up (gene x ancestor-term) pairs.

- to check if a gene is connected to a broad term (e.g. 'DNA repair'), use genes_by_ontology(term_ids=[...], ontology=..., organism=...) which expands down the hierarchy — gene_ontology_terms only returns the leaf annotations

- For brite: leaf annotations are KO-level terms (same leaf as kegg). Use ontology='brite' to filter; the returned term_ids are KO IDs shared with the kegg ontology.

- Use `tree` to scope BRITE rollup to a single tree (e.g. 'transporters'). Without it, rollup mixes all BRITE trees.

- Supported ontologies: `go_bp`, `go_mf`, `go_cc`, `kegg`, `ec`, `cog_category`, `cyanorak_role`, `tigr_role`, `pfam`, `brite`, `tcdb`, `cazy`, `subcellular_localization`, `signal_peptide_type`, `interpro`, `ncbifam`, `merops`.

- `ontology` is now `str | list[str] | None` (was single-value only). With a list: a filter carried by all requested ontologies applies normally; carried by some but not all applies to those and drops the rest into `skipped_ontologies` with a warning; carried by none raises `ValueError`. An unknown ontology name always raises.

- `include_superseded=False` (default) applies TCDB's `attachment_depth='most_specific'` predicate in leaf mode — ancestor rows made redundant by a deeper attachment on the same gene are dropped. `include_superseded=True` adds them back labelled `attachment_depth='superseded'`; superseded means less specific, not incorrect.

- Trust filters (`sources`, `evidence`, `max_tier`, `min_evidence_score`, `call_class`) mirror `genes_by_ontology` exactly — same defaults (`None`, never filter), same per-ontology axis gating, same `ValueError` on an unsupported axis. See `docs://analysis/annotation_evidence` for the per-ontology axis table.

- Compact rows carry `evidence` on the 14 functional-edge ontologies (null on PSORTb/SignalP); `interpro_type` (interpro rows) and `call_class` (merops rows) are compact always. `sources`, `evidence_score`, `tier`, and native detail (`confidence_score`, `libraries`, `evalue`, ...) are verbose-only.

- CAZy rollup at `level=0` returns the 6 top-level classes (GH, GT, PL, CE, AA, CBM). Genes commonly belong to multiple top-level classes (e.g. a CBM-domain-containing GH); duplicates per `(gene × class)` are de-duped automatically.

- TCDB substrate-level questions ('which genes does this metabolite bind to?') chain via `genes_by_metabolite`, NOT this tool. Use `gene_ontology_terms(ontology='tcdb')` for *family*-level annotations (e.g. 'what TCDB family does PMM1129 belong to?').

- Reverse-lookup of `genes_by_ontology` — same ontology surface, gene-anchored. For enrichment workflows the forward direction (`genes_by_ontology` → TERM2GENE → `pathway_enrichment` / `cluster_enrichment`) is canonical; see `docs://analysis/enrichment`.

## Package import equivalent

```python
from multiomics_explorer import gene_ontology_terms

result = gene_ontology_terms(locus_tags=..., organism=...)
# returns dict with keys: total_matching, total_genes, total_terms, by_ontology, by_term, terms_per_gene_min, terms_per_gene_max, terms_per_gene_median, offset, not_found, no_terms, trust_axes, by_evidence, by_tier, by_sources, by_call_class, evidence_score_stats, evidence_score_signals, filters_applied, skipped_ontologies, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
