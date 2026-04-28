# DerivedMetric Analysis Guide

**Served as:** `docs://analysis/derived_metrics`

This document covers the DerivedMetric (DM) node family: what DMs are, how to discover
them, and how to drill into gene-level annotations across the three value kinds
(numeric, boolean, categorical).

---

## Overview

`DerivedMetric` nodes represent non-differential-expression, column-level quantitative
or qualitative evidence — for example rhythmicity flags, diel amplitudes, vesicle
enrichment scores, and darkness-survival classes. They sit alongside expression data
and are surfaced by a dedicated tool family.

Key properties on a `DerivedMetric` node:
- `metric_type` — free-text tag (e.g. `damping_ratio`, `vesicle_proteome_member`)
- `value_kind` — enum: `numeric`, `boolean`, `categorical`
- `compartment` — wet-lab fraction: `whole_cell`, `vesicle`, `exoproteome`, `spent_medium`, `lysate`
- `rankable` — whether edge-level `rank`/`bucket`/`percentile` fields are populated
- `has_p_value` — whether edge-level `p_value` is populated
- `allowed_categories` — (categorical only) declared full set of category labels

---

## Tool family

| Tool | Role |
|---|---|
| `list_derived_metrics` | Entry-point — discover DM nodes, inspect `rankable`/`has_p_value`/`value_kind`/`allowed_categories` before drill-down |
| `gene_derived_metrics` | Gene-centric batch lookup — one row per gene × DM, polymorphic `value` column |
| `genes_by_numeric_metric` | Drill-down on numeric DMs — threshold/bucket/percentile/rank filters |
| `genes_by_boolean_metric` | Drill-down on boolean DMs — `flag` filter (True / False / None) |
| `genes_by_categorical_metric` | Drill-down on categorical DMs — `categories` filter |

---

## Discovery patterns

The slice-2 discovery tools (`gene_overview`, `list_experiments`, `list_publications`,
`list_organisms`, `list_filter_values`) surface DerivedMetric rollups so you can browse
DM evidence without a separate `list_derived_metrics` call:

- `list_experiments` / `list_publications` / `list_organisms` carry per-row
  `derived_metric_count` (richness) and `derived_metric_value_kinds` (which kinds
  — use to route to the right drill-down). Verbose adds `derived_metric_types`
  (full list of metric_type tags) and `derived_metric_gene_count` (gene-level
  annotation total).
- Envelope rollups: `by_value_kind`, `by_metric_type`, `by_compartment`.
- `compartment` filter on the 3 list tools — values: `whole_cell`, `vesicle`,
  `exoproteome`, `spent_medium`, `lysate`. Scopes to a wet-lab fraction.
- **`compartment` field shape varies by tool:** `list_experiments` per-row carries
  `compartment` (scalar string — an experiment lives in one fraction).
  `list_publications` and `list_organisms` carry `compartments` (list[str] — they
  aggregate over multiple experiments / strains). `gene_overview` (verbose) carries
  `compartments_observed` (list[str]). The `compartment` *filter param* is scalar on
  all 3 list tools — it filters to rows where the compartment is present (scalar
  equality on Experiment, list-membership on Publication/Organism).
- `gene_overview` carries per-gene `derived_metric_count` and
  `derived_metric_value_kinds`; verbose adds per-kind counts and
  `compartments_observed`. Envelope: `has_derived_metrics` (count of requested
  locus_tags with DM evidence).
- `list_filter_values` enumerates `metric_type`, `value_kind`, and `compartment`
  for guided discovery.

**Routing from discovery to drill-down:**

```
if "boolean" in row["derived_metric_value_kinds"]:
    → genes_by_boolean_metric(metric_types=[...])
if "numeric" in row["derived_metric_value_kinds"]:
    → genes_by_numeric_metric(metric_types=[...])
if "categorical" in row["derived_metric_value_kinds"]:
    → genes_by_categorical_metric(metric_types=[...])
```

**Search-text reach:** `list_experiments(search_text="diel amplitude")` and
`list_publications(search_text="vesicle proteome")` route through DM tokens
(name, metric_type, field_description, compartment) because the fulltext index
was enriched in the 2026-04-27 KG build. `genes_by_function` is NOT enriched
with DM tokens — measuring `damping_ratio` on a gene does not make it part of the
gene's function.

---

## Typical workflows

### 1. Browse what DM evidence exists for an organism

```python
from multiomics_explorer import api

# Which compartments and value kinds does MED4 have?
orgs = api.list_organisms(organism_names=["Prochlorococcus MED4"])
med4 = orgs["results"][0]
print(med4["derived_metric_value_kinds"])   # e.g. ['boolean', 'numeric', 'categorical']
print(med4["compartments"])                 # e.g. ['whole_cell', 'vesicle']

# Discover the specific metric_type tags
dms = api.list_derived_metrics(organism="MED4")
for dm in dms["results"]:
    print(dm["metric_type"], dm["value_kind"], dm["rankable"])
```

### 2. Get boolean-flagged genes (e.g. periodicity)

```python
result = api.genes_by_boolean_metric(
    metric_types=["periodic_in_axenic_LD"],
    flag=True,
)
locus_tags = [r["locus_tag"] for r in result["results"]]
```

### 3. Filter by numeric threshold

```python
result = api.genes_by_numeric_metric(
    metric_types=["diel_amplitude"],
    min_value=2.0,
)
```

### 4. Filter by categorical class

```python
result = api.genes_by_categorical_metric(
    metric_types=["darkness_survival_class"],
    categories=["high"],
)
```

### 5. Vesicle-enriched genes

```python
# Step 1: find the right metric
fv = api.list_filter_values(filter_type="metric_type")
# → includes "log2_vesicle_cell_enrichment"

# Step 2: get top-enriched genes
result = api.genes_by_numeric_metric(
    metric_types=["log2_vesicle_cell_enrichment"],
    min_value=1.0,   # ≥2-fold enriched in vesicles
)
```

---

## Notes on current KG constraints

- `genes_by_boolean_metric(flag=False)` returns 0 rows today — the KG stores only
  positive (True) flag edges. `dm_false_count=0` on every current DM.
- `genes_by_numeric_metric` with `has_p_value=True` gate raises today — no numeric
  DM currently has p-values. Check `has_p_value` on `list_derived_metrics` output
  before using the p-value filter.
- `compartment` on `DerivedMetric` is a property of the DM node (the wet-lab
  fraction the measurement came from), not a per-gene property.
