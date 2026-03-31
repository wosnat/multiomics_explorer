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
    """Process a single object-typed column — stub (no-op) for Task 1."""
    return df
