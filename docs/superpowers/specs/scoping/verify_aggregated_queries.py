"""Cloud-aware design: aggregate in Cypher, ship minimal rows to Python.

Goal: verify that one aggregated query per ontology returns the same
numbers as the per-term Python aggregation, with ~100× less data.

Q_landscape_stats returns ~1-11 rows per ontology (one per level), each
containing:
  - level, n_terms_with_genes
  - min/q1/median/q3/max_genes_per_term   (Cypher percentileCont)
  - n_genes_at_level                       (Cypher count DISTINCT via apoc flatten)
  - n_best_effort, n_reached_terms         (for best_effort_share)

Q_landscape_examples is a SEPARATE verbose-only query — avoids shipping
example-term names when verbose=False.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from multiomics_explorer.kg.connection import GraphConnection

ORG = "Prochlorococcus MED4"

ONTOLOGIES = [
    ("go_bp", "BiologicalProcess", "Gene_involved_in_biological_process",
     ["Biological_process_is_a_biological_process",
      "Biological_process_part_of_biological_process"]),
    ("go_mf", "MolecularFunction", "Gene_enables_molecular_function",
     ["Molecular_function_is_a_molecular_function",
      "Molecular_function_part_of_molecular_function"]),
    ("go_cc", "CellularComponent", "Gene_located_in_cellular_component",
     ["Cellular_component_is_a_cellular_component",
      "Cellular_component_part_of_cellular_component"]),
    ("cyanorak_role", "CyanorakRole", "Gene_has_cyanorak_role",
     ["Cyanorak_role_is_a_cyanorak_role"]),
    ("kegg", "KeggTerm", "Gene_has_kegg_ko", ["Kegg_term_is_a_kegg_term"]),
    ("ec", "EcNumber", "Gene_catalyzes_ec_number", ["Ec_number_is_a_ec_number"]),
    ("tigr", "TigrRole", "Gene_has_tigr_role", []),
    ("cog", "CogFunctionalCategory", "Gene_in_cog_category", []),
    ("pfam", "Pfam", "Gene_has_pfam", []),
]


def q_landscape_stats(edge: str, label: str, is_a_rels: list[str]) -> str:
    """Per-level aggregated stats. Single query per ontology.

    The trick: keep per-term gene sets in collect() then flatten+toSet to
    compute distinct genes at each level. All other stats are ordinary
    per-level aggregations.
    """
    if is_a_rels:
        rel = "|".join(is_a_rels)
        walk = f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
        bind = f"-[:{edge}]->(leaf:{label})"
    else:
        walk = ""
        bind = f"-[:{edge}]->(t:{label})"
    return (
        f"MATCH (g:Gene {{organism_name:$org}}){bind}\n"
        + walk +
        "WITH t, count(DISTINCT g) AS n_g_per_term, "
        "collect(DISTINCT g) AS term_genes\n"
        "WITH t.level AS level,\n"
        "     count(t) AS n_terms_with_genes,\n"
        "     min(n_g_per_term) AS min_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.25) AS q1_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.5)  AS median_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.75) AS q3_genes_per_term,\n"
        "     max(n_g_per_term) AS max_genes_per_term,\n"
        "     apoc.coll.toSet(apoc.coll.flatten(collect(term_genes))) AS all_genes,\n"
        "     sum(CASE WHEN t.level_is_best_effort IS NOT NULL THEN 1 ELSE 0 END) "
        "AS n_best_effort\n"
        "RETURN level, n_terms_with_genes,\n"
        "       size(all_genes) AS n_genes_at_level,\n"
        "       min_genes_per_term, q1_genes_per_term, median_genes_per_term,\n"
        "       q3_genes_per_term, max_genes_per_term,\n"
        "       n_best_effort\n"
        "ORDER BY level"
    )


def q_landscape_examples(edge: str, label: str, is_a_rels: list[str],
                          top_n: int = 5) -> str:
    """Verbose-only: top-N terms per level by gene count."""
    if is_a_rels:
        rel = "|".join(is_a_rels)
        walk = f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
        bind = f"-[:{edge}]->(leaf:{label})"
    else:
        walk = ""
        bind = f"-[:{edge}]->(t:{label})"
    return (
        f"MATCH (g:Gene {{organism_name:$org}}){bind}\n"
        + walk +
        "WITH t, count(DISTINCT g) AS n_g_per_term\n"
        "WITH t.level AS level,\n"
        "     apoc.coll.sortMaps(\n"
        "       collect({term_id:t.id, name:t.name, n_genes:n_g_per_term}),\n"
        "       '^n_genes'\n"
        f"     )[0..{top_n}] AS example_terms\n"
        "RETURN level, example_terms\n"
        "ORDER BY level"
    )


def time_q(conn, q, **p):
    t0 = time.perf_counter()
    rows = conn.execute_query(q, timeout=60, **p)
    return time.perf_counter() - t0, rows


def approx_row_bytes(row: dict) -> int:
    """Crude estimate — what Neo4j actually ships is Bolt-packed, this is a proxy."""
    return len(json.dumps(row, default=str).encode("utf-8"))


def main():
    with GraphConnection() as conn:
        print("=== Q_landscape_stats (aggregated, cloud-friendly) ===")
        grand = 0.0
        total_rows = 0
        total_bytes = 0
        for key, label, edge, is_a in ONTOLOGIES:
            q = q_landscape_stats(edge, label, is_a)
            dt, rows = time_q(conn, q, org=ORG)
            grand += dt
            total_rows += len(rows)
            b = sum(approx_row_bytes(r) for r in rows)
            total_bytes += b
            print(f"  {key:<16} {dt*1000:>5.0f}ms  {len(rows):>2} levels  {b:>5} B")
        print(f"  TOTAL: {grand*1000:.0f}ms  {total_rows} rows  {total_bytes} B "
              f"({total_bytes/1024:.1f} KB)")

        print("\n=== Q_landscape_examples (verbose-only, top-5) ===")
        grand_v = 0.0
        total_rows_v = 0
        total_bytes_v = 0
        for key, label, edge, is_a in ONTOLOGIES:
            q = q_landscape_examples(edge, label, is_a, top_n=5)
            dt, rows = time_q(conn, q, org=ORG)
            grand_v += dt
            total_rows_v += len(rows)
            b = sum(approx_row_bytes(r) for r in rows)
            total_bytes_v += b
            print(f"  {key:<16} {dt*1000:>5.0f}ms  {len(rows):>2} levels  {b:>6} B")
        print(f"  TOTAL verbose: {grand_v*1000:.0f}ms  {total_rows_v} rows  "
              f"{total_bytes_v} B ({total_bytes_v/1024:.1f} KB)")

        print("\n=== Sanity: go_bp aggregated output (should match earlier) ===")
        q = q_landscape_stats("Gene_involved_in_biological_process",
                              "BiologicalProcess",
                              ["Biological_process_is_a_biological_process",
                               "Biological_process_part_of_biological_process"])
        _, rows = time_q(conn, q, org=ORG)
        print("Level  nTerms  nGenes  median  be_share")
        for r in rows:
            be = r["n_best_effort"] / r["n_terms_with_genes"] if r["n_terms_with_genes"] else 0
            print(f"  L{r['level']:<2} {r['n_terms_with_genes']:>5}  "
                  f"{r['n_genes_at_level']:>5}  {r['median_genes_per_term']:>6.1f}  "
                  f"{be*100:>5.1f}%")

        print("\n=== Sanity: verbose top-5 example_terms for go_bp L3 ===")
        q = q_landscape_examples("Gene_involved_in_biological_process",
                                  "BiologicalProcess",
                                  ["Biological_process_is_a_biological_process",
                                   "Biological_process_part_of_biological_process"])
        _, rows = time_q(conn, q, org=ORG)
        l3 = next(r for r in rows if r["level"] == 3)
        for e in l3["example_terms"]:
            print(f"  {e['term_id']}  n={e['n_genes']}  {e['name'][:60]}")

        print("\n=== Data-volume comparison ===")
        # Re-use the previous per-term query for comparison (what we'd ship if Python aggregated)
        def q_terms_bloat(edge, label, is_a):
            if is_a:
                rel = "|".join(is_a)
                walk = f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
                bind = f"-[:{edge}]->(leaf:{label})"
            else:
                walk = ""
                bind = f"-[:{edge}]->(t:{label})"
            return (
                f"MATCH (g:Gene {{organism_name:$org}}){bind}\n" + walk +
                "WITH t, count(DISTINCT g) AS n_g_per_term\n"
                "RETURN t.level AS level, t.id AS term_id, t.name AS term_name, "
                "t.level_is_best_effort AS best_effort, n_g_per_term AS n_genes "
                "ORDER BY level, term_id"
            )
        bloat_bytes = 0
        bloat_rows = 0
        for key, label, edge, is_a in ONTOLOGIES:
            _, rows = time_q(conn, q_terms_bloat(edge, label, is_a), org=ORG)
            b = sum(approx_row_bytes(r) for r in rows)
            bloat_bytes += b
            bloat_rows += len(rows)
        print(f"  Per-term rows (what Python-aggregation ships): "
              f"{bloat_rows} rows, {bloat_bytes} B ({bloat_bytes/1024:.1f} KB)")
        print(f"  Aggregated (Cypher-side): "
              f"{total_rows} rows, {total_bytes} B ({total_bytes/1024:.1f} KB)")
        print(f"  Reduction: {bloat_bytes/total_bytes:.0f}x smaller")


if __name__ == "__main__":
    main()
