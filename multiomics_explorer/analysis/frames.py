"""DataFrame conversion utilities for multiomics_explorer API results.

The primary entry point is :func:`to_dataframe`, which converts the
``{"results": [...]}`` dict returned by API functions into a tidy
:class:`pandas.DataFrame`.

Object-typed columns are processed automatically:
- List values are joined with ``" | "`` (space-pipe-space).
- Dict values are expanded into ``{col}_{key}`` columns.
- Mixed or nested complex values are dropped with a :class:`UserWarning`.
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

# Columns with dedicated conversion functions get a helpful suggestion in the
# drop warning rather than the generic "file an issue" message.
_DEDICATED_FUNCTIONS: dict[str, str] = {
    "response_summary": "profile_summary_to_dataframe()",
    "timepoints": "experiments_to_dataframe()",
}


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
            record["tp_significant_up"] = None
            record["tp_significant_down"] = None
            record["tp_not_significant"] = None
            records.append(record)
    return pd.DataFrame(records)


def to_dataframe(result: dict[str, Any]) -> pd.DataFrame:
    """Convert an API result dict to a :class:`pandas.DataFrame`.

    Parameters
    ----------
    result:
        Dict with a ``"results"`` key containing a list of row dicts.

    Returns
    -------
    pd.DataFrame
        One row per result item, object columns processed.

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

    df = pd.DataFrame(result["results"])
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

    # Mixed types — drop with warning.
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
    """Warn and drop *col* from *df* in-place."""
    dedicated = _DEDICATED_FUNCTIONS.get(col)
    if dedicated:
        suggestion = (
            f"Column '{col}' contains nested data. "
            f"Use {dedicated} to convert this column instead."
        )
    else:
        suggestion = (
            f"Column '{col}' contains nested data that cannot be flattened "
            "automatically. The column has been dropped. "
            "If you need this data, please file an issue."
        )
    warnings.warn(suggestion, UserWarning, stacklevel=4)
    df.drop(columns=[col], inplace=True)
