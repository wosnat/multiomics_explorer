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

    return df


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------


def _is_scalar_nan(value: Any) -> bool:
    """Return True if *value* is a float NaN (but not a list/dict)."""
    if isinstance(value, float):
        import math

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
