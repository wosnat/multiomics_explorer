# DerivedMetric Analysis Guide

**Served as:** `docs://analysis/derived_metrics`

The DerivedMetric (DM) node family: what DMs are, how to discover them, and how
to drill into gene-level annotations across the three value kinds (numeric,
boolean, categorical). Every Python block below runs as written against the
live KG.

> Counts here are a live snapshot (83 DMs: 46 numeric, 27 boolean, 10
> categorical) and drift with each KG rebuild. `list_derived_metrics` and
> `list_filter_values` are the current source.

---

## Overview

`DerivedMetric` nodes represent non-differential-expression, column-level
quantitative or qualitative evidence — rhythmicity flags, diel amplitudes,
vesicle enrichment scores, darkness-survival classes, TSS counts, RNA
half-lives. They sit alongside expression data and are surfaced by a dedicated
tool family.

Key properties on a `DerivedMetric` node:

- `metric_type` — free-text tag, e.g. `damping_ratio`,
  `diel_amplitude_transcript_log2`, `vesicle_proteome_member`,
  `darkness_survival_class`. Enumerate with
  `list_filter_values(filter_type="metric_type")` (53 values live) — the tag is
  the paper's column name, so guess nothing.
- `value_kind` — `numeric`, `boolean`, `categorical`.
- `compartment` — wet-lab fraction. DMs use `whole_cell` (45), `vesicle` (31)
  and `exoproteome` (7). The vocabulary
  (`list_filter_values(filter_type="compartment")`) also carries
  `extracellular`, which only metabolite assays use.
- `rankable` — whether edge-level `rank` / `bucket` / `percentile` are
  populated (numeric only).
- `has_p_value` — whether edge-level `p_value` is populated. **No DM in the
  live KG has p-values**; see "KG constraints".
- `allowed_categories` — (categorical only) the declared full set of labels;
  may be a strict superset of what is observed.

---

## Tool family

| Tool | Role |
|---|---|
| `list_derived_metrics` | Entry point — discover DM nodes; read `derived_metric_id`, `value_kind`, `rankable`, `has_p_value`, `allowed_categories` before any drill-down |
| `gene_derived_metrics` | Gene-centric batch lookup — one row per gene × DM, polymorphic `value` column; single organism |
| `genes_by_numeric_metric` | Drill-down on numeric DMs — value threshold (always), bucket / percentile / rank (rankable-gated), p-value (has_p_value-gated) |
| `genes_by_boolean_metric` | Drill-down on boolean DMs — `flag` filter (`True` / `False` / `None`) |
| `genes_by_categorical_metric` | Drill-down on categorical DMs — `categories` filter |

Both `derived_metric_ids` and `metric_types` select DMs on every drill-down;
`derived_metric_ids` is exact, `metric_types` can match the same tag across
organisms and papers.

---

## Discovery patterns

The DM-aware discovery tools (`gene_overview`, `list_experiments`,
`list_publications`, `list_organisms`, `list_filter_values`) surface DM rollups
so you can see where DM evidence exists without a separate
`list_derived_metrics` call:

- `list_experiments` / `list_publications` / `list_organisms` carry per-row
  `derived_metric_count` and `derived_metric_value_kinds` (route to the right
  drill-down). Verbose adds `derived_metric_types` and
  `derived_metric_gene_count`.
- Envelope rollups: `by_value_kind`, `by_metric_type`, `by_compartment`.
- `compartment` filter on the three list tools (scalar). The per-row field
  shape differs: `list_experiments` carries `compartment` (scalar — an
  experiment lives in one fraction); `list_publications` and `list_organisms`
  carry `compartments` (list — they aggregate); `gene_overview` (verbose)
  carries `compartments_observed` (list).
- `gene_overview` carries per-gene `derived_metric_count` and
  `derived_metric_value_kinds`; verbose adds per-kind counts and
  `compartments_observed`. Envelope `has_derived_metrics` counts requested
  genes with DM evidence.
- `list_filter_values` enumerates `metric_type`, `value_kind`, `compartment`.

**Routing from discovery to drill-down:**

```
if "boolean"     in row["derived_metric_value_kinds"]: genes_by_boolean_metric(...)
if "numeric"     in row["derived_metric_value_kinds"]: genes_by_numeric_metric(...)
if "categorical" in row["derived_metric_value_kinds"]: genes_by_categorical_metric(...)
```

**Search-text reach:** `list_experiments(search_text="diel amplitude")` and
`list_publications(search_text="vesicle proteome")` match DM tokens (name,
metric_type, field_description, compartment) because the fulltext index is
enriched with them. `genes_by_function` is not — measuring `damping_ratio` on
a gene does not make it part of the gene's function.

---

## Worked path: discover → gene lookup → tested-absent drill-down

The one path to know. Boolean DMs are the trap: 16 of the 27 store only
`flagged` edges, so `flag_value=False` returns 0 rows there and the absence of a
flag means nothing. The other 11 store `not_flagged` too, and there
`flag_value=False` is real tested-absent biology.

```python
from multiomics_explorer import (
    list_derived_metrics, gene_derived_metrics, genes_by_boolean_metric,
)

# 1. Discover: what boolean DMs does MED4 have?
# verbose=True — compartment is a verbose-only field.
dms = list_derived_metrics(
    organism="MED4", value_kind="boolean", verbose=True, limit=None,
)
for dm in dms["results"]:
    print(dm["derived_metric_id"], dm["metric_type"], dm["compartment"])
# derived_metric:gb-2010-11-5-r54:halflife_table:expressed_above_background  expressed_above_background  whole_cell
# derived_metric:ismej.2014.57:tss_metrics_med4:has_primary_tss              has_primary_tss             whole_cell
# derived_metric:science.1243457:s2_med4_vesicle_proteome:vesicle_proteome_member  vesicle_proteome_member  vesicle
# ...

dm_id = "derived_metric:gb-2010-11-5-r54:halflife_table:expressed_above_background"

# 2. Gene lookup: what does this DM say about specific genes?
rows = gene_derived_metrics(
    locus_tags=["PMM0001", "PMM0002", "PMM1697"], organism="MED4",
    derived_metric_ids=[dm_id],
)
[(r["locus_tag"], r["value"]) for r in rows["results"]]
# [('PMM0001', 'flagged'), ('PMM0002', 'not_flagged'), ('PMM1697', 'flagged')]
# rows["not_found"]   -> locus_tags absent from the KG
# rows["not_matched"] -> genes present but with no edge to the selected DMs

# 3. Tested-absent drill-down: every gene this DM says is NOT expressed above
#    background at t0 (Steglich 2010) — a real negative, because this DM stores
#    both states.
absent = genes_by_boolean_metric(derived_metric_ids=[dm_id], flag_value=False, limit=None)
absent["total_matching"]          # 920
absent["by_value"]                # [{'value': 'not_flagged', 'count': 920}]
absent["by_metric"][0]["dm_true_count"], absent["by_metric"][0]["dm_false_count"]
# (1010, 920)  <- full-DM counts; dm_false_count == 0 means "positive-only, don't
#                 read flag_value=False as absence" on the other 16 boolean DMs
```

Read `by_metric[*].dm_false_count` before interpreting a `flag_value=False` result:
`0` means the paper never reported negatives, not that every gene was present.

---

## Typical workflows

### 1. Browse what DM evidence exists for an organism

```python
from multiomics_explorer import list_organisms, list_derived_metrics

med4 = list_organisms(organism_names=["Prochlorococcus MED4"])["results"][0]
med4["derived_metric_value_kinds"]   # ['boolean', 'categorical', 'numeric']
med4["compartments"]                 # ['vesicle', 'whole_cell']

# verbose=True — has_p_value is a verbose-only field.
for dm in list_derived_metrics(
        organism="MED4", verbose=True, limit=None)["results"]:   # 26 DMs
    print(dm["metric_type"], dm["value_kind"], dm["rankable"], dm["has_p_value"])
```

### 2. Boolean-flagged genes (periodicity)

```python
from multiomics_explorer import genes_by_boolean_metric

periodic = genes_by_boolean_metric(metric_types=["periodic_in_axenic_LD"], flag_value=True, limit=None)
locus_tags = [r["locus_tag"] for r in periodic["results"]]   # 1,377 genes
```

### 3. Numeric threshold

```python
from multiomics_explorer import genes_by_numeric_metric

amp = genes_by_numeric_metric(
    metric_types=["diel_amplitude_transcript_log2"], min_value=2.0, limit=None,
)
amp["total_matching"]                 # 91
amp["by_metric"][0]["dm_value_median"], amp["by_metric"][0]["value_median"]
# (1.43, 2.62)  <- full-DM distribution vs the filtered slice
```

### 4. Categorical class

```python
from multiomics_explorer import genes_by_categorical_metric

dark = genes_by_categorical_metric(metric_types=["darkness_survival_class"], limit=None)
dark["by_category"][:2]
# [{'category': 'darkness_axenic+darkness_coculture', 'count': 95},
#  {'category': 'darkness_coculture+unique_coculture', 'count': 87}]
# Pass categories=[...] from allowed_categories on list_derived_metrics; unknown
# labels raise with the allowed union in the message.
```

### 5. Vesicle-enriched genes

```python
from multiomics_explorer import list_filter_values, genes_by_numeric_metric

tags = [v["value"] for v in list_filter_values(filter_type="metric_type")["results"]]
"log2_vesicle_cell_enrichment" in tags   # True

vesicle = genes_by_numeric_metric(
    metric_types=["log2_vesicle_cell_enrichment"], min_value=1.0, limit=None,
)   # >= 2-fold enriched in vesicles; 11 genes
```

---

## KG constraints

- **Boolean tested-absent storage is per DM.** `genes_by_boolean_metric(flag_value=False)`
  returns rows only on the 11 of 27 boolean DMs that store `not_flagged`
  edges — Steglich 2010 `expressed_above_background` (1), Voigt 2014
  `has_primary_tss` (MED4 + MIT9313, 2), Hennon 2015 `rapid_recovery_*` (2),
  and the Alteromonas EZ55 `whole_cell_detected_*` / `exoproteome_detected_*`
  set (6); the rest are positive-only. Read the
  filtered-slice `by_metric[*].false_count` or the full-DM `dm_false_count`.
- **Two-state strings in the KG, `bool` on the surface.** Node props are
  `rankable` / `not_rankable`, `p_value` / `no_p_value`; the edge value is
  `flagged` / `not_flagged`. The explorer exposes `rankable` / `has_p_value` as
  `bool`; `gene_derived_metrics.value` and `by_value` report the KG literal.
- **The p-value gate raises in the current KG.** On `genes_by_numeric_metric` the
  `has_p_value`-gated parameters are `significant_only` and
  `max_adjusted_p_value`. No numeric DM in the live KG has `has_p_value=True`,
  so setting either raises
  (`All N selected DMs have has_p_value=False; cannot apply has_p_value-gated
  filter(s) ['significant_only'] ...`). Check `has_p_value` on
  `list_derived_metrics` first.
- **Rankable-gated parameters soft-exclude.** `bucket`, `min_percentile` /
  `max_percentile`, `max_rank` need `rankable=True`; on a mixed selection the
  non-rankable DMs land in `excluded_derived_metrics` + `warnings`, and the
  call raises only when every selected DM is non-rankable.
- **`compartment` is a DM-node property** (the fraction the measurement came
  from), not a per-gene property.
