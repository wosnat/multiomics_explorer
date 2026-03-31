"""Expression analysis utilities.

Composes API results into DataFrames for downstream analysis.
"""

from __future__ import annotations

import pandas as pd

from multiomics_explorer.api import functions as api
from multiomics_explorer.kg.connection import GraphConnection


# ---------------------------------------------------------------------------
# Direction classification
# ---------------------------------------------------------------------------

def _classify_direction(entry: dict) -> str:
    """Classify a response_summary entry as up/down/mixed/not_responded.

    Args:
        entry: A single group's stats dict from response_summary, containing
               at minimum experiments_up and experiments_down counts.

    Returns:
        "mixed"         if both up and down experiments present
        "up"            if only up experiments present
        "down"          if only down experiments present
        "not_responded" if tested but neither up nor down
    """
    up = entry.get("experiments_up", 0) or 0
    down = entry.get("experiments_down", 0) or 0

    if up > 0 and down > 0:
        return "mixed"
    if up > 0:
        return "up"
    if down > 0:
        return "down"
    return "not_responded"


# ---------------------------------------------------------------------------
# response_matrix
# ---------------------------------------------------------------------------

_METADATA_COLS = ["gene_name", "product", "gene_category"]


def response_matrix(
    genes: list[str],
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    group_map: dict[str, str] | None = None,
    conn: GraphConnection | None = None,
) -> pd.DataFrame:
    """Build a pivot DataFrame of gene response directions across treatment groups.

    Without group_map:
        Calls gene_response_profile with group_by="treatment_type".
        Each column is a treatment type (e.g. "nitrogen_stress").
        Uses groups_not_responded and groups_not_known lists from the API result
        to fill in non-response cells.

    With group_map:
        Calls gene_response_profile with group_by="experiment" and
        experiment_ids=list(group_map.keys()).
        Re-aggregates per-experiment stats by summing experiments_up/experiments_down
        for experiments that share the same label in group_map.
        Experiment IDs not in group_map are ignored.
        Groups (labels) with no matching experiments in the result get "not_known".

    Args:
        genes:          Locus tags to query.
        organism:       Optional organism filter.
        experiment_ids: Optional experiment ID filter (ignored when group_map is set).
        group_map:      Optional mapping of experiment_id → group label for
                        re-aggregation. When provided, overrides experiment_ids.
        conn:           Optional Neo4j connection.

    Returns:
        DataFrame with index=locus_tag, group columns, and metadata columns
        (gene_name, product, gene_category). Empty DataFrame (index.name="locus_tag")
        if no results.
    """
    if group_map is not None:
        # Call with group_by="experiment" using the group_map keys as experiment_ids
        result = api.gene_response_profile(
            locus_tags=genes,
            organism=organism,
            experiment_ids=list(group_map.keys()),
            group_by="experiment",
            conn=conn,
        )
    else:
        result = api.gene_response_profile(
            locus_tags=genes,
            organism=organism,
            experiment_ids=experiment_ids,
            group_by="treatment_type",
            conn=conn,
        )

    rows = result.get("results", [])
    if not rows:
        df = pd.DataFrame()
        df.index.name = "locus_tag"
        return df

    records = []
    for gene in rows:
        locus_tag = gene["locus_tag"]
        record: dict = {"locus_tag": locus_tag}

        # Metadata
        for col in _METADATA_COLS:
            record[col] = gene.get(col)

        summary = gene.get("response_summary", {})

        if group_map is not None:
            # Re-aggregate: sum experiments_up/down for each label
            label_up: dict[str, int] = {}
            label_down: dict[str, int] = {}
            for exp_id, label in group_map.items():
                if exp_id not in summary:
                    continue
                entry = summary[exp_id]
                label_up[label] = label_up.get(label, 0) + (entry.get("experiments_up", 0) or 0)
                label_down[label] = label_down.get(label, 0) + (entry.get("experiments_down", 0) or 0)

            # All unique labels from group_map
            all_labels = set(group_map.values())
            for label in all_labels:
                if label not in label_up and label not in label_down:
                    record[label] = "not_known"
                else:
                    record[label] = _classify_direction({
                        "experiments_up": label_up.get(label, 0),
                        "experiments_down": label_down.get(label, 0),
                    })
        else:
            # Use groups_not_responded and groups_not_known for non-response cells
            not_responded = set(gene.get("groups_not_responded", []))
            not_known = set(gene.get("groups_not_known", []))

            # Groups present in response_summary (responded or not_responded)
            for group_key, entry in summary.items():
                if group_key in not_known:
                    record[group_key] = "not_known"
                elif group_key in not_responded:
                    record[group_key] = "not_responded"
                else:
                    record[group_key] = _classify_direction(entry)

            # Groups only in not_known (no summary entry)
            for group_key in not_known:
                if group_key not in record:
                    record[group_key] = "not_known"

            # Groups only in not_responded (no summary entry)
            for group_key in not_responded:
                if group_key not in record:
                    record[group_key] = "not_responded"

        records.append(record)

    df = pd.DataFrame(records).set_index("locus_tag")
    df.index.name = "locus_tag"
    return df


# ---------------------------------------------------------------------------
# gene_set_compare
# ---------------------------------------------------------------------------

_RESPONDING_VALUES = {"up", "down", "mixed"}


def gene_set_compare(
    set_a: list[str],
    set_b: list[str],
    organism: str | None = None,
    set_a_name: str = "set_a",
    set_b_name: str = "set_b",
    experiment_ids: list[str] | None = None,
    group_map: dict[str, str] | None = None,
    conn: GraphConnection | None = None,
) -> dict[str, pd.DataFrame | list[str]]:
    """Compare expression response profiles for two gene sets.

    Computes a union of set_a and set_b, fetches the response matrix for all
    genes in a single API call, then partitions rows into overlap/only_a/only_b
    and produces a per-group summary with responding-gene counts for each set.

    Args:
        set_a:          First gene locus tag list.
        set_b:          Second gene locus tag list.
        organism:       Optional organism filter forwarded to response_matrix.
        set_a_name:     Label for set_a in summary_per_group columns.
        set_b_name:     Label for set_b in summary_per_group columns.
        experiment_ids: Optional experiment ID filter (ignored when group_map is set).
        group_map:      Optional experiment_id → group label mapping.
        conn:           Optional Neo4j connection.

    Returns:
        Dict with keys:
            overlap         — DataFrame of genes in both sets
            only_a          — DataFrame of genes only in set_a
            only_b          — DataFrame of genes only in set_b
            shared_groups   — list[str] of group names where both sets respond
            divergent_groups — list[str] of group names where exactly one set responds
            summary_per_group — DataFrame indexed by group with columns:
                                {set_a_name}, {set_b_name}, overlap, shared
    """
    set_a_set = set(set_a)
    set_b_set = set(set_b)
    union = list(dict.fromkeys(list(set_a) + [g for g in set_b if g not in set_a_set]))

    matrix = response_matrix(
        genes=union,
        organism=organism,
        experiment_ids=experiment_ids,
        group_map=group_map,
        conn=conn,
    )

    # Partition rows into overlap / only_a / only_b
    overlap_mask = matrix.index.isin(set_a_set) & matrix.index.isin(set_b_set)
    only_a_mask = matrix.index.isin(set_a_set) & ~matrix.index.isin(set_b_set)
    only_b_mask = ~matrix.index.isin(set_a_set) & matrix.index.isin(set_b_set)

    overlap_df = matrix[overlap_mask]
    only_a_df = matrix[only_a_mask]
    only_b_df = matrix[only_b_mask]

    # Identify group columns (all except metadata)
    group_cols = [c for c in matrix.columns if c not in _METADATA_COLS]

    # Build per-group summary
    summary_records = []
    for group in group_cols:
        col = matrix[group]

        a_count = int(col[matrix.index.isin(set_a_set)].isin(_RESPONDING_VALUES).sum())
        b_count = int(col[matrix.index.isin(set_b_set)].isin(_RESPONDING_VALUES).sum())
        overlap_count = int(col[overlap_mask].isin(_RESPONDING_VALUES).sum())
        is_shared = a_count >= 1 and b_count >= 1

        summary_records.append({
            "group": group,
            set_a_name: a_count,
            set_b_name: b_count,
            "overlap": overlap_count,
            "shared": is_shared,
        })

    summary_df = pd.DataFrame(summary_records).set_index("group")

    # Derive shared and divergent group lists
    shared_groups = list(summary_df.index[summary_df["shared"]])
    divergent_groups = list(
        summary_df.index[
            (summary_df[set_a_name] >= 1) != (summary_df[set_b_name] >= 1)
        ]
    )

    return {
        "overlap": overlap_df,
        "only_a": only_a_df,
        "only_b": only_b_df,
        "shared_groups": shared_groups,
        "divergent_groups": divergent_groups,
        "summary_per_group": summary_df,
    }
