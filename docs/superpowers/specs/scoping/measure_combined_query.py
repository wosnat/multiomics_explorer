"""Compare: stats-only vs stats+examples in one query (verbose path)."""

from __future__ import annotations

import json
import time
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


def build(edge, label, is_a, with_examples: bool):
    """Single query: stats + optional top-5 examples per level."""
    if is_a:
        rel = "|".join(is_a)
        walk = f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
        bind = f"-[:{edge}]->(leaf:{label})"
    else:
        walk = ""
        bind = f"-[:{edge}]->(t:{label})"

    # Per-term aggregation
    q = (
        f"MATCH (g:Gene {{organism_name:$org}}){bind}\n"
        + walk +
        "WITH t, count(DISTINCT g) AS n_g_per_term, "
        "collect(DISTINCT g) AS term_genes\n"
    )
    # If examples: pre-sort by n_g DESC so collect() preserves order
    if with_examples:
        q += (
            "ORDER BY n_g_per_term DESC\n"
        )
    # Per-level aggregation
    q += (
        "WITH t.level AS level,\n"
        "     count(t) AS n_terms_with_genes,\n"
        "     min(n_g_per_term) AS min_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.25) AS q1_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.5)  AS median_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.75) AS q3_genes_per_term,\n"
        "     max(n_g_per_term) AS max_genes_per_term,\n"
        "     apoc.coll.toSet(apoc.coll.flatten(collect(term_genes))) AS all_genes,\n"
        "     sum(CASE WHEN t.level_is_best_effort IS NOT NULL "
        "THEN 1 ELSE 0 END) AS n_best_effort"
    )
    if with_examples:
        q += (
            ",\n     collect({term_id:t.id, name:t.name, "
            "n_genes:n_g_per_term})[0..5] AS example_terms"
        )
    q += "\n"
    # RETURN
    cols = [
        "level", "n_terms_with_genes", "size(all_genes) AS n_genes_at_level",
        "min_genes_per_term", "q1_genes_per_term", "median_genes_per_term",
        "q3_genes_per_term", "max_genes_per_term", "n_best_effort",
    ]
    if with_examples:
        cols.append("example_terms")
    q += "RETURN " + ", ".join(cols) + "\nORDER BY level"
    return q


def approx_bytes(rows):
    return sum(len(json.dumps(r, default=str).encode("utf-8")) for r in rows)


def main():
    with GraphConnection() as conn:
        for with_ex in (False, True):
            label = "WITH examples" if with_ex else "stats only"
            total_ms = 0.0
            total_b = 0
            total_rows = 0
            print(f"\n=== {label} ===")
            for key, lbl, edge, is_a in ONTOLOGIES:
                q = build(edge, lbl, is_a, with_ex)
                t0 = time.perf_counter()
                rows = conn.execute_query(q, timeout=60, org=ORG)
                dt = time.perf_counter() - t0
                b = approx_bytes(rows)
                total_ms += dt * 1000
                total_b += b
                total_rows += len(rows)
                print(f"  {key:<16} {dt*1000:>5.0f}ms  {b:>5}B")
            print(f"  TOTAL: {total_ms:.0f}ms  {total_rows} rows  "
                  f"{total_b/1024:.1f} KB")

        # Spot-check: go_bp L3 top 5 under combined query
        q = build("Gene_involved_in_biological_process", "BiologicalProcess",
                  ["Biological_process_is_a_biological_process",
                   "Biological_process_part_of_biological_process"], True)
        rows = conn.execute_query(q, timeout=60, org=ORG)
        l3 = next(r for r in rows if r["level"] == 3)
        print("\ngo_bp L3 top-5 from combined query:")
        for e in l3["example_terms"]:
            print(f"  n={e['n_genes']:>3}  {e['term_id']}  {e['name'][:55]}")


if __name__ == "__main__":
    main()
