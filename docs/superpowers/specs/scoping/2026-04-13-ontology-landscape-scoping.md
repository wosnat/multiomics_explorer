# `ontology_landscape` Cypher Scoping

**Date:** 2026-04-13
**Spec:** [../2026-04-12-ontology-landscape-design.md](../2026-04-12-ontology-landscape-design.md)
**Scripts:** [profile_landscape.py](profile_landscape.py), [profile_experiment_branch.py](profile_experiment_branch.py)
**Raw results:** `profile_landscape_results.json`, `profile_experiment_branch_results.json`

Profiled against the 2026-04-13 KG rebuild (unified `level: int` on all
ten ontology labels). Test organism: `Prochlorococcus MED4` (1976 genes,
48 experiments) — the largest MED4 scenario in the spec's test matrix.

## Query shape

**Design principle** (parent spec + cloud-readiness): aggregate in
Cypher, ship minimal rows. Per-term rows to Python would cost ~860 KB
on a genome call — 98× more bytes over the wire than Cypher-side
aggregation. Prefer simple per-responsibility queries but not at the
cost of shipping the raw relation.

Three query templates per call. Verified against MED4 on the 2026-04-13
KG. Flat ontologies (no `is_a_rels`) drop the hierarchy MATCH.

### Q_validate_experiments *(optional, only when `experiment_ids` set)*

Classifies each experiment_id into `found` / `not_found` / `not_matched`.
L2 raises only on the full-list failure mode (all eids missing/mismatched).

```cypher
UNWIND $experiment_ids AS eid
OPTIONAL MATCH (e:Experiment {id: eid})
RETURN eid,
       e IS NOT NULL AS exists,
       coalesce(e.organism_name, '') AS exp_organism
```

L2 classification:
- `not_found`   = eids where `exists=false`
- `not_matched` = eids where `exists=true` AND `exp_organism != canonical_org`
- `valid_eids`  = eids where both match

**Timing:** 1-18 ms for up to 10 experiments.

### Q_landscape — per-level aggregated stats *(always run)*

One query per ontology. Cypher computes percentiles, term-size
distribution, distinct-gene coverage, and `best_effort` counts. The
`min_gene_set_size` / `max_gene_set_size` filter (default 5 / 500)
is applied after per-term aggregation but before per-level aggregation.
When `verbose=True`, the builder adds a pre-aggregation `ORDER BY
n_genes_per_term DESC` and a `collect(...)[0..3]` clause for
`example_terms` — all in the same scan, no second query needed.

```cypher
MATCH (g:Gene {organism_name:$org})-[:<gene_edge>]->(leaf:<Label>)
MATCH (leaf)-[:<is_a|part_of>*0..]->(t:<Label>)
WITH t, count(DISTINCT g)   AS n_g_per_term,
     collect(DISTINCT g)    AS term_genes
-- gene-set size filter (applied before per-level aggregation)
WHERE n_g_per_term >= $min_gene_set_size
  AND n_g_per_term <= $max_gene_set_size
-- verbose only: pre-sort so order-preserving collect() gives top-3
ORDER BY n_g_per_term DESC
WITH t.level AS level,
     count(t)                                     AS n_terms_with_genes,
     min(n_g_per_term)                            AS min_genes_per_term,
     percentileCont(toFloat(n_g_per_term), 0.25)  AS q1_genes_per_term,
     percentileCont(toFloat(n_g_per_term), 0.5)   AS median_genes_per_term,
     percentileCont(toFloat(n_g_per_term), 0.75)  AS q3_genes_per_term,
     max(n_g_per_term)                            AS max_genes_per_term,
     apoc.coll.toSet(apoc.coll.flatten(collect(term_genes))) AS all_genes,
     sum(CASE WHEN t.level_is_best_effort IS NOT NULL
              THEN 1 ELSE 0 END)                  AS n_best_effort,
     -- verbose only:
     collect({term_id:t.id, name:t.name,
              n_genes:n_g_per_term})[0..3]        AS example_terms
RETURN level, n_terms_with_genes,
       size(all_genes) AS n_genes_at_level,
       min_genes_per_term, q1_genes_per_term, median_genes_per_term,
       q3_genes_per_term, max_genes_per_term,
       n_best_effort,
       example_terms  -- verbose only
ORDER BY level
```

**Notes**

- The `ORDER BY n_g_per_term DESC` + `collect()[0..3]` trick gives
  top-3 by count inside the same per-level aggregation. Tested on
  MED4 × GO BP L3: returns 657, 586, 400 — correctly descending. `apoc.coll.sortMaps` with the `^` descending syntax
  does NOT work on this KG's apoc install (verified empirically);
  `apoc.coll.reverse` is not installed. The ORDER BY trick is both
  simpler and portable.
- `apoc.coll.toSet(apoc.coll.flatten(collect(term_genes)))` computes
  distinct genes at a level by union of per-term gene sets. Peak
  memory for MED4 × GO BP: a few hundred KB — well within budget.
- `best_effort_share` is computed at L2 as `n_best_effort /
  n_terms_with_genes`. Cypher could do the division via
  `toFloat(n_be)/n_terms`, but keeping integer counts in the wire
  shape lets L2 format the fraction once with consistent rounding.
- `level_is_best_effort` stays `null` for non-GO ontologies. L2 emits
  `best_effort_share = None` (not `0.0`) for rows where the column
  is irrelevant.

### Q_expcov — per-(experiment, level) coverage *(optional)*

One row per `(eid, level)`. L2 aggregates `min / median / max`
`exp_coverage` across experiments per level. Only runs on `valid_eids`
from Q_validate. Same `min_gene_set_size` / `max_gene_set_size` filter
applied after per-term aggregation so the coverage denominator uses
only terms that pass the landscape filter.

```cypher
UNWIND $experiment_ids AS eid
MATCH (e:Experiment {id:eid})-[:Changes_expression_of]->
      (g:Gene {organism_name:$org})
WITH eid, collect(DISTINCT g) AS quantified
WITH eid, quantified, size(quantified) AS n_total
UNWIND quantified AS g
MATCH (g)-[:<gene_edge>]->(leaf:<Label>)
MATCH (leaf)-[:<is_a|part_of>*0..]->(t:<Label>)
WITH eid, n_total, t, count(DISTINCT g) AS n_g_per_term_exp,
     collect(DISTINCT g) AS term_genes_exp
WHERE n_g_per_term_exp >= $min_gene_set_size
  AND n_g_per_term_exp <= $max_gene_set_size
WITH eid, n_total, t.level AS level,
     apoc.coll.toSet(apoc.coll.flatten(collect(term_genes_exp))) AS level_genes
RETURN eid, n_total, level, size(level_genes) AS n_at_level
ORDER BY eid, level
```

### L2 orchestration

```python
def ontology_landscape(organism, ontology=None, experiment_ids=None,
                       verbose=False, summary=False, limit=None, offset=0,
                       *, conn=None):
    canonical_org = _validate_organism_inputs(organism=organism, ...)  # hard-raise

    # Total gene count for genome_coverage denominator.
    # Small query — or reuse from OrganismTaxon lookup at L1.
    total_genes = execute(*build_organism_gene_count(canonical_org))

    valid_eids, not_found, not_matched = [], [], []
    if experiment_ids:
        rows = execute(*build_check_experiments(experiment_ids, canonical_org))
        valid_eids, not_found, not_matched = classify(rows, canonical_org)

    targets = ALL_ONTOLOGIES if ontology is None else [ontology]
    rows_out = []
    for ont in targets:
        stats = execute(*build_ontology_landscape(ont, canonical_org, verbose))
        exp   = (execute(*build_ontology_expcov(ont, canonical_org, valid_eids))
                 if valid_eids else [])
        rows_out.extend(assemble_rows(ont, stats, exp, total_genes, verbose))

    # Rank in Python: coverage × size_factor(median); paginate; build envelope.
    ...
```

Measured for MED4:

| Branch | Queries total | Cold wall-clock | Bytes |
|---|---:|---:|---:|
| Genome, non-verbose, `ontology=None` | 9 | 291-568 ms | 8.8 KB |
| Genome, verbose, `ontology=None` | 9 | 542 ms | 25.5 KB |
| + 10 experiments | +9 expcov + 1 validate | +1291 ms | +~10 KB |

Full worst case (verbose + 10 experiments + all ontologies): **~1.9 s,
~35 KB**. Cloud-transferable; no streaming or chunking needed.

## Timing (wall-clock, client-side, MED4)

### Genome branch — per-ontology (final combined-query shape)

| Ontology      | stats only | verbose (+examples) |
|---------------|-----------:|--------------------:|
| go_bp         |  69-113 ms |     96 ms (6.8 KB)  |
| go_mf         |  44- 92 ms |     78 ms (5.4 KB)  |
| go_cc         |  26- 58 ms |     58 ms (3.7 KB)  |
| cyanorak_role |  23- 53 ms |     54 ms (2.6 KB)  |
| kegg          |  27- 57 ms |     59 ms (2.9 KB)  |
| ec            |  25- 55 ms |     59 ms (2.5 KB)  |
| tigr_role     |  18- 50 ms |     47 ms (0.8 KB)  |
| cog_category  |  24- 61 ms |     44 ms (0.7 KB)  |
| pfam          |  19- 79 ms |     47 ms (0.7 KB)  |
| **TOTAL**     | **291 ms / 8.8 KB** | **542 ms / 25.5 KB** |

### Experiment branch (Q_expcov, cold)

Unchanged from prior scoping — already aggregated per-row:

**Total, 9 ontologies × 10 experiments:** 1291 ms.

### Data-volume reduction (the cloud-readiness win)

| Approach                                      | Bytes   | Ratio |
|-----------------------------------------------|--------:|------:|
| Per-term rows (Python aggregation on client)  | 858 KB  | 1×    |
| Cypher-aggregated, combined (final)           | 8.8 KB  | **98×** |
| Cypher-aggregated, combined, verbose          | 25.5 KB | 34×   |

The per-term approach would ship 6753 rows across 9 ontologies. The
combined aggregate ships 41 rows. When the KG moves to the cloud,
this is the difference between a tool call that's interactive and one
that isn't.

## Decisions

### D1. L2 orchestration + Cypher-side aggregation (cloud-aware)

**L2 orchestration** over L1 UNION. Measured mega-UNION cold at 404 ms
vs L2-serial at 436 ms — within noise. L2 wins on:

- Per-ontology dispatch already clean (edge, label, hierarchy rels).
- Error isolation: one bad ontology doesn't break the whole response.
- Easier unit tests; parallelisable later (9 independent reads).

**Three builders per call:**

| Builder | Purpose | Rows | Runs when |
|---|---|---:|---|
| `build_experiment_check` | Classify eids into found/not_found/not_matched | ≤N_eids | `experiment_ids` set |
| `build_ontology_landscape(ontology, organism, verbose)` | Per-level aggregated stats (+ top-3 examples if verbose) | 1-11 per ontology | always |
| `build_ontology_expcov(ontology, organism, experiment_ids)` | Per-(eid, level) coverage rows | ≤N_eids × N_levels | `valid_eids` non-empty |

Aggregation happens in Cypher via `percentileCont`, `apoc.coll.toSet`,
and `ORDER BY n_g DESC + collect()[0..3]` for top-N examples. Python
handles rank formula (coverage × size_factor(median)), pagination,
and per-experiment min/median/max across levels from the small
`expcov` output.

**Rationale over per-term-rows + Python aggregation:**

- 98× less data over the wire (8.8 KB vs 858 KB genome branch).
- 2× faster in wall-clock (291 ms vs 855 ms non-verbose).
- Cloud-ready: stays interactive when the KG is remote.
- Parent-spec principle ("counts in Cypher, stats in Python") still
  holds — "stats" here means the ranking formula and cross-experiment
  min/median/max, not percentiles over thousands of raw term rows.

### D2. Level-filtered aggregation is memory-safe; no HAS_ANCESTOR needed

The 1.4 GiB Neo4j cap hit in the old `gene_ontology_terms` query came
from materialising per-(gene, ancestor-term) pairs at every level in a
single projection — a near-cartesian output shape on ~2000 genes × GO
MF depth. The landscape query groups by `(t, level)` and then by
`level` alone, so intermediates stay small. **Confirmed empirically**:
GO BP all levels at MED4 finishes in 181 ms with no memory warnings.

Pre-emptive `HAS_ANCESTOR` closure edges are therefore not needed for
Phase 1. Revisit only if (a) future organisms 3-4× larger than MED4
push this pattern past a few seconds, or (b) Child 3's
`pathway_contingency_counts_query` shows a different shape that does
benefit from closure.

### D3. ~1.9 s / 35 KB budget for the worst documented case

Under the final combined-query shape — all 9 ontologies × 10
experiments, verbose — takes **~1.9 s cold, ~35 KB over the wire**
(542 ms genome + 1291 ms experiment + 18 ms validation). Within the
30 s driver timeout; cloud-transferable with no streaming or chunking.

### D4. Deliberate deviation: Python string composition over `apoc.map.merge`

`layer-rules/references/layer-boundaries.md` §Layer 1 recommends
`apoc.map.fromPairs` / `apoc.map.merge` for "verbose vs compact RETURN
without duplicating the query." `build_ontology_landscape` instead
composes two Cypher variants via Python string conditionals on
`verbose`.

**Why we deviate:**

- `apoc.map.merge` solves output-duplication; it does not short-circuit
  compute. The verbose path needs a pre-aggregation `ORDER BY
  n_g_per_term DESC` and a `collect({term_id, name, n_genes})[0..3]`
  inside the per-level aggregation. Both still run when `verbose=False`
  if guarded only by a CASE at RETURN time.
- Measured cost of running the verbose clauses needlessly: ~250 ms
  across 9 ontologies (542 ms verbose → 291 ms non-verbose). That's
  2× the default path.
- Python string composition in the builder gives a true short-circuit:
  the ORDER BY and the collect are absent from the query text when
  `verbose=False`.

**Tradeoff:** two Cypher strings emerging from one builder vs one
Cypher string that pays compute for discarded output. We pick the
former for the common-path speed.

CyVer validation still works: SyntaxValidator runs substitution on
whatever string the builder returns. Two code paths in one builder
are fine per layer conventions — existing builders like
`build_differential_expression_by_gene` already conditionally add
WHERE clauses via Python.

### D5. Organism resolution via existing `_validate_organism_inputs`

Existing helper in `api/functions.py:1463` fuzzy-matches `organism`
against `Experiment.organism_name` (via word-based CONTAINS) and
returns the canonical string (e.g. `'Prochlorococcus MED4'`). Raises
on unknown or ambiguous input. **Reuse as-is** for organism
resolution — don't invent a new resolver.

Note: the existing helper *raises* on `experiment_ids` spanning
multiple organisms, which is too aggressive for `ontology_landscape`'s
soft `not_matched` semantics. Handle experiment validation
separately via Q_validate_experiments — don't pass `experiment_ids`
to `_validate_organism_inputs`. Pass only `organism=organism` to the
existing helper.

### D6. `min_gene_set_size` / `max_gene_set_size` filter (borrowed from pathway_enrichment)

The `pathway_enrichment` design spec (Child 3) exposes `min_gene_set_size=5` /
`max_gene_set_size=500` as the enrichment test filter. `ontology_landscape`
adds the same defaults so its term-size stats are pre-filtered to the same
population the enrichment test will actually see.

**What the filter changes:**

- Applied after per-term aggregation (`WITH t, count(DISTINCT g) AS n_g_per_term`),
  before per-level aggregation. So percentiles, coverage, and `n_terms_with_genes`
  reflect only terms in [min, max].
- Same filter applies in Q_expcov (experiment-coverage query).
- Default values: `min_gene_set_size=5`, `max_gene_set_size=500` — same as
  pathway_enrichment.

**Ranking under the filter (MED4, min=5, max=500):**

Verified via `verify_min_gene_set_size.py`. Key changes vs. unfiltered:

| Rank | Ontology × level | cov   | median | score |
|-----:|------------------|------:|-------:|------:|
|    1 | tigr_role L0     | 0.874 |   13.0 | 0.874 |
|    2 | cyanorak_role L1 | 0.728 |   14.0 | 0.728 |
|    3 | go_mf L2         | 0.578 |   25.0 | 0.578 |
|    4 | go_mf L3         | 0.559 |   19.5 | 0.559 |
|    5 | go_bp L3         | 0.538 |   13.0 | 0.538 |

**Integration test assertion still holds:** cyanorak_role L1 is rank-1 among
hierarchical rows (verified: hier_rank=1, score=0.728 vs next hierarchical
go_mf L2 at 0.578).

**What the filter solves:** terms with 1–4 genes are noise for enrichment
purposes; including them in median can mask bimodality (the concern raised
in the Q1/Q3 revisit section). Filtering is simpler and more transparent
than switching the ranking formula to `size_factor(q1, q3)`. The Q1/Q3
revisit is therefore retired — see updated section below.

## Observations (investigated; conclusions baked in)

### O1. `ontology=None` ranking — spec formula differs from B1, intentionally

**B1's criterion** (located at
`multiomics_research/analyses/2026-04-09-1713-pathway_enrichment_b1/enrich_utils/survey.py`):
a hard gate — `median ∈ [5, 50]` AND `coverage ≥ 0.3` AND ontology is
hierarchical (`n_levels > 1`). Non-qualifying rows score 0. Score is
then raw `coverage`. Under this rule, TIGR/COG/Pfam score 0 (flat) and
cyanorak_role L1 wins.

**Spec formula** (`coverage × size_factor`) is softer and admits flat
ontologies. Full MED4 ranking under both:

| Rank | Ontology × level | coverage | median | size_factor | spec_score | B1_rank |
|-----:|------------------|---------:|-------:|------------:|-----------:|--------:|
|    1 | tigr_role L0     |    0.893 |    9   |      1.000  |     0.893  |   (0)   |
|    2 | cyanorak_role L1 |    0.755 |    9   |      1.000  |     0.755  |   **1** |
|    3 | cog_category L0  |    0.886 |   65   |      0.769  |     0.682  |   (0)   |
|    4 | go_mf L1         |    0.605 |   17   |      1.000  |     0.605  |     2   |
|    5 | go_mf L2         |    0.600 |    5   |      1.000  |     0.600  |     3   |
|    6 | go_bp L1         |    0.566 |    7   |      1.000  |     0.566  |     4   |
|    7 | go_bp L2         |    0.566 |    9   |      1.000  |     0.566  |     5   |
|    8 | go_bp L3         |    0.555 |    5   |      1.000  |     0.555  |     6   |
|    9 | cyanorak_role L0 |    0.761 |   70   |      0.714  |     0.544  |   (0)   |
|   10 | go_bp L4         |    0.508 |    5   |      1.000  |     0.508  |     7   |

The formula difference is not a bug in the spec; it's a design choice.
The landscape tool's job is "given this organism and maybe experiments,
what ontology/level combinations are candidates for enrichment?" — a
superset of B1's "pick the one best hierarchical level for pathway
enrichment" question. TIGR L0 is a legitimate enrichment surface for
MED4 (89% coverage, 106 terms, median 9 genes/term). Hiding it because
it's flat would be misleading.

**Decision for plan:** keep the spec formula. Three concrete test
changes:

- Integration test assertion becomes "cyanorak_role L1 is rank 1
  **among hierarchical ontologies** (n_levels > 1)" — precisely
  encodes B1's decision logic without pinning the flat-ontology
  relative position.
- Add `n_levels_in_ontology` as an output column so users can see at a
  glance which rows come from flat ontologies and which admit
  drill-down.
- About-content "mistakes" note: "top-ranked flat ontologies (TIGR,
  COG, Pfam) are valid enrichment surfaces but offer no level choice;
  for hierarchical drill-down, filter to rows where n_levels > 1".

### O2. GO L0 roots — crushed by size_factor, verified

Measured at MED4:

| Ontology | L0 coverage | L0 median | size_factor | spec_score |
|----------|------------:|----------:|------------:|-----------:|
| go_bp L0 |       0.568 |    1122   |      0.045  |     0.025  |
| go_mf L0 |       0.607 |    1200   |      0.042  |     0.025  |
| go_cc L0 |       0.407 |     805   |      0.062  |     0.025  |

All three GO roots score ~0.025 (ranks ~40+ out of 51 rows). They will
never contaminate top rankings. ✓

### O3. KEGG coverage gap — structural, not a data bug

KEGG graph state (confirmed by query):

- **Total KO terms (L3):** 4367
- **KOs with a parent pathway:** 2543 (58%)
- **KOs without a parent:** 1824 (42%)
- **MED4-attached KOs with parent:** 722; **without parent:** 295
- **MED4 genes attached *only* to parent-less KOs:** 319 (16% of MED4)

This is not a query bug or KG build bug — it reflects KEGG's actual
structure: KOs without pathway membership exist by design (many are
enzymatic annotations not organised into a pathway). The landscape
output correctly shows:

- KEGG L3 (KO): 1065 MED4 genes, coverage 0.539
- KEGG L0-L2 (category/subcategory/pathway): 765 MED4 genes, coverage
  0.387

**Decision for plan:** surface both rows honestly; no data-cleaning
logic. Add an about-content note: "KEGG has ~40% orphan KOs lacking
pathway membership. If you see L3 coverage substantially higher than
L0-L2 coverage, the gap is structural — those genes have KO-level
annotations only."

### O4. `level_is_best_effort` — measured on terms reached by MED4 genes

Global (whole-ontology) best-effort shares differ from the share
observed in **terms actually attached to MED4 genes**. The latter is
what the landscape row would report. Measured at MED4:

| Ontology | L1 | L2 | L3 | L4 | L5 | L6 | L7 |
|----------|---:|---:|---:|---:|---:|---:|---:|
| go_bp    | 9%  | 23% | 36% | 46% | 64% | 78% | 80% |
| go_mf    | 0%  | 23% | 32% | 25% | 17% | 26% | 24% |
| go_cc    | 0%  | 50% | 77% | 77% | 44% | 33% |  —  |

(Shares at L0 are 0% by construction — roots have min_path == max_path.)

Takeaways:

- For **BP**, best-effort share climbs monotonically with level. At
  mid-depths where spec_score is highest (L3-L5), 36-64% of reached
  terms are best-effort. The spec's "common path for GO" framing holds
  for BP specifically.
- For **MF**, best-effort stays ~20-30% and doesn't climb — the MF DAG
  is flatter and more consistent.
- For **CC**, the share spikes at mid-levels (77% at L3-L4) but drops
  again deeper.

**Decision for plan:**

- Per-row output column: `best_effort_share: float | None` — fraction
  of terms reached at (ontology, level) whose `level_is_best_effort`
  is set. `None` for non-GO ontologies. Single query extension; same
  scan.
- Not a "mistakes" note; more an interpretation hint in about-content:
  "for GO BP, `best_effort_share` will typically be 30-80% at useful
  levels — this is normal DAG geometry, not a data quality issue."

### O5. `Gene` edge type dispatch

One gene edge per ontology; no ambiguity. Dispatch table as a
module-level constant in `queries_lib.py`:

```python
ONTOLOGY_CONFIG = {
    "go_bp": dict(label="BiologicalProcess",
                  gene_edge="Gene_involved_in_biological_process",
                  hierarchy_rels=["Biological_process_is_a_biological_process",
                                  "Biological_process_part_of_biological_process"]),
    # ... 9 entries total
}
```

Plan-time detail: this constant is the natural place for the hierarchy
helper `hierarchy_expansion_cypher(ontology, level)` to consume. It
also hosts the `n_levels_in_ontology` count for the flat/hierarchical
distinction called out in O1.

## Phase 2 revisit — Cypher-aggregate experiment-branch stats

Considered during scoping: push `min / median / max exp_coverage` from
Python into Q_expcov by grouping per-level across experiments in
Cypher.

**Why we kept Python for Phase 1: zero-fill semantics.**

If an experiment's quantified genes don't reach a given level, Cypher
emits no row for `(eid, level)`. Computing `min/median/max` over just
the emitted rows gives "minimum *among experiments that had any
coverage*" — not "minimum across all experiments." For the researcher,
a row showing `min_exp_coverage=0.4` when 7 of 10 experiments actually
had 0 coverage is misleading.

Python handles zero-fill trivially: compare emitted rows against the
known `valid_eids` set, fill zeros, compute stats. Cypher can do it
too, but only with `OPTIONAL MATCH` over the level set plus a level ×
eid cartesian join — noticeably more complex for modest gain.

**Data volume actually saved:**

| Scenario                         | Python (current) | Cypher pre-aggregated |
|----------------------------------|-----------------:|----------------------:|
| 10 exps × 9 onto × avg 5 lvl     |    ~27 KB        |    ~9 KB              |
| 50 exps × 9 onto × avg 5 lvl     |   ~135 KB        |    ~9 KB              |

At the documented 10-experiment test case, delta is ~18 KB —
meaningful for cloud but not game-changing. Cypher pre-aggregation
becomes compelling at 30+ experiments.

**Phase 2 trigger:** if researchers routinely pass >30 experiments,
add a Cypher variant with explicit zero-fill via `OPTIONAL MATCH` over
the level set. Note the tradeoff: aggregated-output in Cypher also
loses the option to emit per-experiment coverage in a future
`verbose` mode — Python-side aggregation preserves that path.

## Phase 2 revisit — Q1/Q3 vs median in `size_factor` *(retired)*

**Retired by D6.** The original concern was that `size_factor(median)` hides
bimodal distributions (e.g. `go_mf L2` with Q1=1 gene and median=5 — half
the terms are 1-gene). The `min_gene_set_size=5` filter (D6) addresses this
more directly: 1-gene terms simply don't participate in the per-level stats.
After filtering, Q1/Q3 for the same rows are well above 5, so the bimodality
that motivated this revisit is gone.

See `verify_min_gene_set_size.py` for the updated ranking table under the filter.

## Caching — deferred

**Question considered:** should the genome branch
(`experiment_ids=None`) cache its results? It's a pure function of
`(organism, ontology)` and the KG build — same numbers until rebuild.

**Budget from our numbers (final combined-query shape):**

| Scenario                                | Cold    | Warm (Neo4j plan cache) |
|-----------------------------------------|--------:|------------------------:|
| Genome, all 9 ontologies, non-verbose   | 568 ms  | ~291 ms                 |
| Genome, all 9 ontologies, verbose       | 542 ms* | —                       |
| 10 experiments × all 9 ontologies       | 1291 ms | —                       |

(\* verbose timing measured after warm-up; cold closer to ~700 ms.)

Neo4j's built-in query-plan cache already provides a ~2× warm speedup
for free. Sub-600 ms cold for the full-organism survey is acceptable
for an interactive MCP tool that researchers hit *once at the start of
an analysis*, not on every turn.

**Options considered and rejected for Phase 1:**

- **Module-level LRU in L2** — ~100 μs warm hit, but requires an
  invalidation key (`Schema_info` has one). Small win, nonzero
  complexity, and we already restart MCP after KG rebuilds (user
  workflow memory `feedback_mcp_restart.md`) — reconnect resets the
  plan cache naturally.
- **Precompute as KG nodes** (`OrganismLandscape` with row properties
  emitted at build time) — scope creep into biocypher-kg repo;
  rejected for Phase 1.
- **Persistent disk cache** (parquet/sqlite keyed by KG-build stamp) —
  overkill for <500 ms queries.

**Decision for Phase 1: no cache.** Query every call. Rely on:

- Neo4j query-plan cache (automatic).
- MCP restart on KG rebuild (already the user's convention).

**Phase 2 trigger to revisit:** if the research repo's eval framework
(which runs organism × experiment sweeps) shows a pattern of repeated
identical genome-branch calls, add `@functools.lru_cache` at L2 keyed
by `(organism, ontology_key)` with process-lifetime invalidation.
20-line change, done when evidence warrants.

**Experiment branch — not cached, even in Phase 2.** Keys vary with
`sorted(experiment_ids)`; naive caching explodes in cardinality, and
~1.3 s per 10-experiment call is fine.

## Edge case behaviour (verified)

| Scenario | Observed | L2 behaviour |
|---|---|---|
| Unknown organism | `_validate_organism_inputs` matches 0 → raise | `ValueError`, surface via FastMCP `ToolError` |
| Ambiguous organism | `_validate_organism_inputs` matches >1 → raise | `ValueError` with list |
| Unknown `experiment_id` | Q_validate returns `exists=false` | Added to `not_found`, no error |
| Experiment wrong-organism | Q_validate returns `exp_organism != $org` | Added to `not_matched`, no error |
| All experiment_ids invalid | Q_validate returns 0 valid | Run genome branch only; response flags both lists |
| Empty `experiment_ids=[]` (explicit) | Treat as `None` | Genome branch only |
| Flat ontology (TIGR/COG/Pfam) | Q_landscape omits hierarchy MATCH, returns one level | Aggregated correctly; `n_levels_in_ontology=1` |
| Gene with no ontology annotation | Q_landscape skips that gene silently | Genome coverage denominator unchanged |
| `percentileCont` on 1-term level | Returns the term's gene count | Q1 = median = Q3 = max; `size_factor` unaffected |

Integer types on return: `level` = Python `int`, `n_genes_per_term` =
`int`, `best_effort` = `None` or `"true"`. Verified.

## What's next

Ready to write the implementation plan (step 2 in the parent prompt).
Key decisions to bake in:

**Architecture**
- L2 orchestration; three builders per call (D1).
- Cypher-side aggregation — 98× less data over the wire than Python
  aggregation over per-term rows. Cloud-ready (D1).
- No HAS_ANCESTOR closure (D2).
- ~1.9 s / ~35 KB worst-case budget (D3).
- Reuse `_validate_organism_inputs` for organism; separate experiment
  check for soft `not_found` / `not_matched` (D5).
- Python string composition for verbose vs compact Cypher — explicit
  deviation from `apoc.map.merge` recommendation for short-circuit
  compute (D4).
- Single combined query for stats + optional examples — no second
  round-trip for verbose (D1).

**Ranking and output**
- Keep spec's soft `coverage × size_factor(median)` formula (O1, D6).
- `min_gene_set_size=5`, `max_gene_set_size=500` filter (D6) applied after
  per-term aggregation in both Q_landscape and Q_expcov. Matches pathway_enrichment
  defaults.
- Add `n_levels_in_ontology` column (O1) so flat ontologies are
  visible.
- Integration test: "cyanorak_role L1 is rank 1 among rows where
  `n_levels_in_ontology > 1`" (O1, verified under filter).
- Surface both KEGG L3 and L0-L2 rows honestly (O3); about-content note.
- Add `best_effort_share` column for GO rows (O4) — per-row, not global.
- No caching in Phase 1 (separate section); rely on Neo4j plan cache +
  MCP restart.

**Config**
- Per-ontology dispatch table (`ONTOLOGY_CONFIG`) in `queries_lib.py`
  (O5) — consumed by the 3 builders and the `hierarchy_expansion_cypher`
  helper.
