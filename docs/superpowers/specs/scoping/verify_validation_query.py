"""Verify the experiment-validation helper query for not_found / not_matched."""

from __future__ import annotations

import time
from multiomics_explorer.kg.connection import GraphConnection

ORG = "Prochlorococcus MED4"


def build_check_experiments(experiment_ids, organism_name):
    cypher = (
        "UNWIND $experiment_ids AS eid\n"
        "OPTIONAL MATCH (e:Experiment {id: eid})\n"
        "RETURN eid,\n"
        "       e IS NOT NULL AS exists,\n"
        "       coalesce(e.organism_name, '') AS exp_organism\n"
    )
    return cypher, {
        "experiment_ids": experiment_ids,
        "organism": organism_name,
    }


def classify(rows, organism_name):
    """Split into found/not_found/not_matched."""
    found, not_found, not_matched = [], [], []
    for r in rows:
        if not r["exists"]:
            not_found.append(r["eid"])
        elif r["exp_organism"] != organism_name:
            not_matched.append(r["eid"])
        else:
            found.append(r["eid"])
    return found, not_found, not_matched


def main():
    cases = [
        (
            "all-good",
            [
                "10.1101/2025.11.24.690089_coculture_alteromonas_hot1a3_med4_rnaseq",
                "10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq",
            ],
        ),
        (
            "mixed found + not_found",
            [
                "10.1101/2025.11.24.690089_coculture_alteromonas_hot1a3_med4_rnaseq",
                "nonexistent_X",
                "another_missing",
            ],
        ),
        (
            "mixed found + not_matched (wrong org)",
            [
                "10.1101/2025.11.24.690089_coculture_alteromonas_hot1a3_med4_rnaseq",
                # This one profiles HOT1A3, not MED4:
                "10.1101/2025.11.24.690089_coculture_prochlorococcus_med4_hot1a3_rnaseq",
            ],
        ),
        (
            "all three mixed",
            [
                "10.1101/2025.11.24.690089_coculture_alteromonas_hot1a3_med4_rnaseq",  # ok
                "nonexistent_X",                                                        # not_found
                "10.1101/2025.11.24.690089_coculture_prochlorococcus_med4_hot1a3_rnaseq",  # not_matched
            ],
        ),
        (
            "empty list",
            [],
        ),
    ]

    with GraphConnection() as conn:
        for label, eids in cases:
            cypher, params = build_check_experiments(eids, ORG)
            t0 = time.perf_counter()
            if eids:
                rows = conn.execute_query(cypher, timeout=30, **params)
            else:
                rows = []
            dt = time.perf_counter() - t0
            found, nf, nm = classify(rows, ORG)
            print(f"\n[{label}] ({dt*1000:.0f}ms)")
            print(f"  input   : {eids}")
            print(f"  found      : {found}")
            print(f"  not_found  : {nf}")
            print(f"  not_matched: {nm}")


if __name__ == "__main__":
    main()
