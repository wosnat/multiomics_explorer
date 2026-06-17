"""DataFrame conversion utilities for multiomics_explorer API results.

The single entry point is :func:`to_dataframe`. It returns the right
shape automatically for any tool result:

- ``gene_response_profile()`` → one row per gene × treatment group.
- ``list_experiments()`` → one row per experiment × timepoint.
- ``list_clustering_analyses()`` → one row per analysis × cluster.
- Anything else → flat one-row-per-result conversion (list columns
  joined by ``" | "``, dict columns expanded into ``{col}_{key}``,
  remaining nested columns dropped with a :class:`UserWarning`).

The dedicated functions :func:`profile_summary_to_dataframe`,
:func:`experiments_to_dataframe`, and :func:`analyses_to_dataframe`
are public for direct use, but most callers should just reach for
:func:`to_dataframe`.
"""

from __future__ import annotations

import math
import warnings
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

_LIST_DELIMITER = " | "


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def profile_summary_to_dataframe(result: dict) -> pd.DataFrame:
    """Convert a ``gene_response_profile`` result to a gene × group DataFrame.

    Parameters
    ----------
    result:
        Raw dict returned by ``gene_response_profile()``.

    Returns
    -------
    pd.DataFrame
        One row per gene × treatment group, with response stats as columns.

    Raises
    ------
    ValueError
        If ``result`` does not contain a ``"results"`` key, or if the results
        do not contain ``"response_summary"``.
    """
    if "results" not in result:
        raise ValueError(
            "Expected a dict with a 'results' key. "
            "Got keys: " + ", ".join(sorted(result.keys()))
        )
    rows_list = result["results"]
    if not rows_list:
        return pd.DataFrame()
    if "response_summary" not in rows_list[0]:
        raise ValueError(
            "Results do not contain 'response_summary'. "
            "This function is for gene_response_profile results. "
            "Got keys: " + ", ".join(sorted(rows_list[0].keys()))
        )
    records = []
    for gene in rows_list:
        lt = gene["locus_tag"]
        gn = gene.get("gene_name")
        for group_key, stats in gene["response_summary"].items():
            record = {"locus_tag": lt, "gene_name": gn, "group": group_key, **stats}
            records.append(record)
    return pd.DataFrame(records)


def experiments_to_dataframe(result: dict) -> pd.DataFrame:
    """Convert a ``list_experiments`` result to an experiment × timepoint DataFrame.

    Parameters
    ----------
    result:
        Raw dict returned by ``list_experiments()``.

    Returns
    -------
    pd.DataFrame
        One row per experiment × timepoint. Non-time-course experiments produce
        a single row with NaN timepoint fields.

    Raises
    ------
    ValueError
        If ``result`` does not contain a ``"results"`` key.
    """
    if "results" not in result:
        raise ValueError(
            "Expected a dict with a 'results' key. "
            "Got keys: " + ", ".join(sorted(result.keys()))
        )
    rows_list = result["results"]
    if not rows_list:
        return pd.DataFrame()
    records = []
    for exp in rows_list:
        base = {k: v for k, v in exp.items() if k not in ("timepoints", "genes_by_status")}
        gbs = exp.get("genes_by_status")
        if isinstance(gbs, dict):
            for status_key, count in gbs.items():
                base[f"genes_by_status_{status_key}"] = count
        timepoints = exp.get("timepoints")
        if timepoints:
            for tp in timepoints:
                record = {**base}
                record["timepoint"] = tp.get("timepoint")
                record["timepoint_order"] = tp.get("timepoint_order")
                record["timepoint_hours"] = tp.get("timepoint_hours")
                record["tp_gene_count"] = tp.get("gene_count")
                record["tp_growth_phase"] = tp.get("growth_phase")
                tp_gbs = tp.get("genes_by_status", {})
                record["tp_significant_up"] = tp_gbs.get("significant_up")
                record["tp_significant_down"] = tp_gbs.get("significant_down")
                record["tp_not_significant"] = tp_gbs.get("not_significant")
                records.append(record)
        else:
            record = {**base}
            record["timepoint"] = None
            record["timepoint_order"] = None
            record["timepoint_hours"] = None
            record["tp_gene_count"] = None
            record["tp_growth_phase"] = None
            record["tp_significant_up"] = None
            record["tp_significant_down"] = None
            record["tp_not_significant"] = None
            records.append(record)
    df = pd.DataFrame(records)
    if df.empty:
        return df
    return _flatten_columns(df)


def analyses_to_dataframe(result: dict) -> pd.DataFrame:
    """Convert a ``list_clustering_analyses`` result to an analysis × cluster DataFrame.

    Parameters
    ----------
    result:
        Raw dict returned by ``list_clustering_analyses()``.

    Returns
    -------
    pd.DataFrame
        One row per analysis × cluster. Analysis-level scalar fields repeat
        for each cluster row. Compact cluster columns: ``cluster_id``,
        ``cluster_name``, ``cluster_member_count``. Verbose cluster columns
        (when present): ``cluster_functional_description``,
        ``cluster_expression_dynamics``, ``cluster_temporal_pattern``.

    Raises
    ------
    ValueError
        If ``result`` does not contain a ``"results"`` key.
    """
    if "results" not in result:
        raise ValueError(
            "Expected a dict with a 'results' key. "
            "Got keys: " + ", ".join(sorted(result.keys()))
        )
    rows_list = result["results"]
    if not rows_list:
        return pd.DataFrame()

    # Verbose cluster field names (only present when verbose=True was used)
    _VERBOSE_CLUSTER_FIELDS = (
        "functional_description",
        "expression_dynamics",
        "temporal_pattern",
    )

    records = []
    for analysis in rows_list:
        base = {k: v for k, v in analysis.items() if k != "clusters"}
        clusters = analysis.get("clusters") or []
        for cl in clusters:
            record = {**base}
            record["cluster_id"] = cl.get("cluster_id")
            record["cluster_name"] = cl.get("name")
            record["cluster_member_count"] = cl.get("member_count")
            for field in _VERBOSE_CLUSTER_FIELDS:
                if field in cl:
                    record[f"cluster_{field}"] = cl.get(field)
            records.append(record)

    df = pd.DataFrame(records)
    if df.empty:
        return df
    return _flatten_columns(df)


# Dispatch table — maps a key present in ``result["results"][0]`` to the
# dedicated converter. Order matters only when keys could collide
# (currently none do).
_DISPATCH_BY_KEY: dict[str, Any] = {
    "response_summary": profile_summary_to_dataframe,
    "timepoints": experiments_to_dataframe,
    "clusters": analyses_to_dataframe,
}


def to_dataframe(result: dict[str, Any]) -> pd.DataFrame:
    """Convert any API result dict to a :class:`pandas.DataFrame`.

    The output shape adapts to which tool produced the result:

    - ``gene_response_profile()`` → one row per gene × treatment group.
    - ``list_experiments()`` → one row per experiment × timepoint
      (non-time-course experiments get one row).
    - ``list_clustering_analyses()`` → one row per analysis × cluster.
    - Anything else → one row per ``result["results"]`` entry, with
      list columns joined by ``" | "``, dict columns expanded into
      ``{col}_{key}``, and any remaining nested columns dropped with
      a :class:`UserWarning`.

    For an ``EnrichmentResult`` (returned by ``pathway_enrichment`` /
    ``cluster_enrichment`` / ``fisher_ora``), use ``result.results``
    directly — it is already a DataFrame.

    Parameters
    ----------
    result:
        Dict with a ``"results"`` key containing a list of row dicts.

    Returns
    -------
    pd.DataFrame
        Shape depends on the tool that produced the result; see above.

    Raises
    ------
    ValueError
        If ``result`` does not contain a ``"results"`` key.
    """
    if "results" not in result:
        raise ValueError(
            "'results' key not found in result dict. "
            "Pass the raw API response dict (e.g. the return value of "
            "gene_response_profile())."
        )

    rows = result["results"]
    if rows and isinstance(rows[0], dict):
        first_keys = rows[0].keys()
        for key, dispatched_fn in _DISPATCH_BY_KEY.items():
            if key in first_keys:
                return dispatched_fn(result)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = _flatten_columns(df)
    return df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Walk object-typed columns and delegate to :func:`_process_object_column`."""
    # Iterate over a snapshot of current columns because processing may insert
    # new columns and drop the original.
    for col in list(df.columns):
        if df[col].dtype == object:
            df = _process_object_column(df, col)
    return df


def _process_object_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Process a single object-typed column.

    - All non-null values are lists → join with :data:`_LIST_DELIMITER`.
    - All non-null values are dicts → expand into ``{col}_{key}`` columns.
    - Mixed or nested complex values → drop with :class:`UserWarning`.
    """
    series = df[col]
    non_null = [v for v in series if v is not None and not _is_scalar_nan(v)]

    if not non_null:
        # All nulls — nothing to do.
        return df

    if all(isinstance(v, list) for v in non_null):
        # Check for nested items (list of dicts/lists)
        has_nested_items = any(
            isinstance(item, (dict, list))
            for v in non_null
            for item in v
            if item is not None
        )
        if has_nested_items:
            _drop_with_warning(df, col)
            return df
        # Join list values with delimiter; preserve None as NaN, [] as "".
        df[col] = series.apply(
            lambda v: _LIST_DELIMITER.join(str(x) for x in v)
            if isinstance(v, list)
            else v
        )
        return df

    if all(isinstance(v, dict) for v in non_null):
        # Check for nested dict/list values inside the dicts
        has_nested_values = any(
            isinstance(inner_val, (dict, list))
            for v in non_null
            for inner_val in v.values()
        )
        if has_nested_values:
            _drop_with_warning(df, col)
            return df
        # Expand flat dicts into {col}_{key} columns, inserted at original position.
        col_pos = df.columns.get_loc(col)
        expanded = series.apply(lambda v: v if isinstance(v, dict) else {})
        expanded_df = pd.DataFrame(expanded.tolist(), index=df.index)
        expanded_df.columns = [f"{col}_{k}" for k in expanded_df.columns]
        df = df.drop(columns=[col])
        for i, new_col in enumerate(expanded_df.columns):
            df.insert(col_pos + i, new_col, expanded_df[new_col])
        return df

    # All non-null values are scalars of mixed Python type (e.g. the
    # polymorphic DerivedMetric `value` column: float + 'true'/'false' +
    # category string). Pandas infers object dtype, but the column is
    # already flat — keep it as-is rather than dropping data.
    if all(not isinstance(v, (list, dict)) for v in non_null):
        return df

    # Genuinely unflattenable: a mix of scalars and containers, or
    # containers of differing kind — drop with warning.
    _drop_with_warning(df, col)
    return df


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------


def _is_scalar_nan(value: Any) -> bool:
    """Return True if *value* is a float NaN (but not a list/dict)."""
    if isinstance(value, float):
        return math.isnan(value)
    return False


def _drop_with_warning(df: pd.DataFrame, col: str) -> None:
    """Warn and drop *col* from *df* in-place.

    The three dispatch keys (``response_summary``, ``timepoints``,
    ``clusters``) never reach this path — :func:`to_dataframe`
    auto-dispatches before the flat conversion runs. This warning fires
    only for unrecognized nested columns.
    """
    suggestion = (
        f"Column '{col}' contains nested data that cannot be flattened "
        "automatically. The column has been dropped. "
        "If you need this data, please file an issue."
    )
    warnings.warn(suggestion, UserWarning, stacklevel=4)
    df.drop(columns=[col], inplace=True)
