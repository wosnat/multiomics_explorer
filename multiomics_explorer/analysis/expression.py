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
                    # No matching experiments found in summary for this label
                    record[label] = "not_known"
                else:
                    up = label_up.get(label, 0)
                    down = label_down.get(label, 0)
                    if up > 0 and down > 0:
                        record[label] = "mixed"
                    elif up > 0:
                        record[label] = "up"
                    elif down > 0:
                        record[label] = "down"
                    else:
                        record[label] = "not_responded"
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
# gene_set_compare (stub)
# ---------------------------------------------------------------------------

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

    Not yet implemented — will be added in Task 4.
    """
    raise NotImplementedError("gene_set_compare will be implemented in Task 4")
