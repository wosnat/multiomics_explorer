"""Pull Q1/median/Q3 per (ontology x level) for MED4, re-rank, compare formulas."""

from __future__ import annotations

import json
from pathlib import Path

from multiomics_explorer.kg.connection import GraphConnection

ORG = "Prochlorococcus MED4"
ORG_GENES = 1976

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


def sf_median(m):
    if m <= 0: return 0.0
    return min(1.0, m/5) * min(1.0, 50/m)

def sf_q1q3(q1, q3):
    """Penalise if Q1 < 5 (too many small) OR Q3 > 50 (too many huge)."""
    if q1 <= 0 or q3 <= 0: return 0.0
    low = min(1.0, q1/5)
    high = min(1.0, 50/q3)
    return low * high


def main():
    rows = []
    with GraphConnection() as conn:
        for key, label, edge, is_a in ONTOLOGIES:
            if is_a:
                rel = "|".join(is_a)
                term_q = (
                    f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(leaf:{label})\n"
                    f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
                    "WITH t.level AS level, t, collect(DISTINCT g) AS genes\n"
                    "WITH level, t, size(genes) AS n_g\n"
                    "RETURN level, count(t) AS n_terms, "
                    "percentileCont(toFloat(n_g),0.25) AS q1, "
                    "percentileCont(toFloat(n_g),0.5) AS median, "
                    "percentileCont(toFloat(n_g),0.75) AS q3, "
                    "max(n_g) AS max_g "
                    "ORDER BY level"
                )
                gene_q = (
                    f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(leaf:{label})\n"
                    f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
                    "WITH t.level AS level, collect(DISTINCT g) AS genes\n"
                    "RETURN level, size(genes) AS n_g ORDER BY level"
                )
            else:
                term_q = (
                    f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(t:{label})\n"
                    "WITH t.level AS level, t, collect(DISTINCT g) AS genes\n"
                    "WITH level, t, size(genes) AS n_g\n"
                    "RETURN level, count(t) AS n_terms, "
                    "percentileCont(toFloat(n_g),0.25) AS q1, "
                    "percentileCont(toFloat(n_g),0.5) AS median, "
                    "percentileCont(toFloat(n_g),0.75) AS q3, "
                    "max(n_g) AS max_g "
                    "ORDER BY level"
                )
                gene_q = (
                    f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(t:{label})\n"
                    "WITH t.level AS level, collect(DISTINCT g) AS genes\n"
                    "RETURN level, size(genes) AS n_g ORDER BY level"
                )
            t_rows = conn.execute_query(term_q, timeout=60, org=ORG)
            g_rows = conn.execute_query(gene_q, timeout=60, org=ORG)
            g_by = {r["level"]: r["n_g"] for r in g_rows}
            for r in t_rows:
                cov = g_by.get(r["level"], 0) / ORG_GENES
                rows.append({
                    "ont": key, "lvl": r["level"],
                    "n_terms": r["n_terms"],
                    "q1": round(r["q1"], 1),
                    "med": round(r["median"], 1),
                    "q3": round(r["q3"], 1),
                    "max": r["max_g"],
                    "cov": round(cov, 3),
                    "sf_med": round(sf_median(r["median"]), 3),
                    "sf_q1q3": round(sf_q1q3(r["q1"], r["q3"]), 3),
                    "score_med": round(cov * sf_median(r["median"]), 3),
                    "score_q1q3": round(cov * sf_q1q3(r["q1"], r["q3"]), 3),
                })

    # Rank under each formula
    by_med = sorted(rows, key=lambda r: -r["score_med"])
    by_q13 = sorted(rows, key=lambda r: -r["score_q1q3"])
    for i, r in enumerate(by_med): r["rank_med"] = i+1
    for i, r in enumerate(by_q13): r["rank_q13"] = i+1

    print("Top 15 by MEDIAN formula (current spec):")
    print(f"{'rank':<4} {'ont':<16} {'lvl':<3} {'cov':>5} {'q1':>5} {'med':>5} {'q3':>5} "
          f"{'max':>5} {'sf_med':>6} {'sf_q13':>6} {'score_med':>9} {'score_q13':>9}")
    for r in by_med[:15]:
        print(f"{r['rank_med']:<4} {r['ont']:<16} {r['lvl']:<3} "
              f"{r['cov']:>5.2f} {r['q1']:>5} {r['med']:>5} {r['q3']:>5} "
              f"{r['max']:>5} {r['sf_med']:>6.2f} {r['sf_q1q3']:>6.2f} "
              f"{r['score_med']:>9.3f} {r['score_q1q3']:>9.3f}")

    print("\nRank DIFFERENCES (|rank_med - rank_q13| > 0):")
    print(f"{'ont':<16} {'lvl':<3} {'cov':>5} {'q1':>5} {'med':>5} {'q3':>5} "
          f"{'rnk_med':>7} {'rnk_q13':>7} {'shift':>6}")
    shifted = [r for r in rows if r["rank_med"] != r["rank_q13"]]
    shifted.sort(key=lambda r: -abs(r["rank_med"] - r["rank_q13"]))
    for r in shifted[:20]:
        print(f"{r['ont']:<16} {r['lvl']:<3} "
              f"{r['cov']:>5.2f} {r['q1']:>5} {r['med']:>5} {r['q3']:>5} "
              f"{r['rank_med']:>7} {r['rank_q13']:>7} "
              f"{r['rank_med']-r['rank_q13']:>+6}")

    print("\nTop 15 by Q1/Q3 formula:")
    print(f"{'rank':<4} {'ont':<16} {'lvl':<3} {'cov':>5} {'q1':>5} {'med':>5} {'q3':>5} "
          f"{'sf_q13':>6} {'score_q13':>9}")
    for r in by_q13[:15]:
        print(f"{r['rank_q13']:<4} {r['ont']:<16} {r['lvl']:<3} "
              f"{r['cov']:>5.2f} {r['q1']:>5} {r['med']:>5} {r['q3']:>5} "
              f"{r['sf_q1q3']:>6.2f} {r['score_q1q3']:>9.3f}")

    Path(__file__).parent.joinpath("quartile_results.json").write_text(
        json.dumps(rows, indent=2, default=str))


if __name__ == "__main__":
    main()
