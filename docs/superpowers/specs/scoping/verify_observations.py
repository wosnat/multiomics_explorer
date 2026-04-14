"""Verify O1-O4 with data.

O1: Full ranking of (ontology x level) under spec formula + B1 gate.
O2: GO L0 scores empirically — confirm roots crushed by size_factor.
O3: KEGG coverage gap — structural or data bug?
O4: level_is_best_effort share among terms attached to MED4 genes vs all terms.
"""

from __future__ import annotations

import json
from pathlib import Path

from multiomics_explorer.kg.connection import GraphConnection

ORG = "Prochlorococcus MED4"
ORG_GENE_COUNT = 1976  # MED4

ONTOLOGIES: list[tuple[str, str, str, list[str]]] = [
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
    ("kegg", "KeggTerm", "Gene_has_kegg_ko",
     ["Kegg_term_is_a_kegg_term"]),
    ("ec", "EcNumber", "Gene_catalyzes_ec_number",
     ["Ec_number_is_a_ec_number"]),
    ("tigr", "TigrRole", "Gene_has_tigr_role", []),
    ("cog", "CogFunctionalCategory", "Gene_in_cog_category", []),
    ("pfam", "Pfam", "Gene_has_pfam", []),
]

# --- Ranking helpers ---

def size_factor(median: float) -> float:
    if median <= 0:
        return 0.0
    return min(1.0, median / 5.0) * min(1.0, 50.0 / median)


def spec_score(coverage: float, median: float) -> float:
    return coverage * size_factor(median)


def b1_score(coverage: float, median: float, n_levels_in_ont: int) -> float:
    """B1: qualifies iff median in [5,50] AND cov>=0.3 AND hierarchical."""
    if n_levels_in_ont <= 1:
        return 0.0
    if not (5 <= median <= 50):
        return 0.0
    if coverage < 0.3:
        return 0.0
    return coverage


def o1_o2_full_ranking(conn: GraphConnection) -> dict:
    """Compute every (ontology x level) row for MED4 and rank."""
    rows = []
    per_ont_n_levels = {}
    for key, label, edge, is_a in ONTOLOGIES:
        if is_a:
            rel = "|".join(is_a)
            term_q = (
                f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(leaf:{label})\n"
                f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
                "WITH t.level AS level, t, collect(DISTINCT g) AS genes\n"
                "WITH level, t, size(genes) AS n_g\n"
                "RETURN level, count(t) AS n_terms, "
                "percentileCont(toFloat(n_g),0.5) AS median\n"
                "ORDER BY level"
            )
            gene_q = (
                f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(leaf:{label})\n"
                f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
                "WITH t.level AS level, collect(DISTINCT g) AS genes\n"
                "RETURN level, size(genes) AS n_g\n"
                "ORDER BY level"
            )
        else:
            term_q = (
                f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(t:{label})\n"
                "WITH t.level AS level, t, collect(DISTINCT g) AS genes\n"
                "WITH level, t, size(genes) AS n_g\n"
                "RETURN level, count(t) AS n_terms, "
                "percentileCont(toFloat(n_g),0.5) AS median\n"
                "ORDER BY level"
            )
            gene_q = (
                f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(t:{label})\n"
                "WITH t.level AS level, collect(DISTINCT g) AS genes\n"
                "RETURN level, size(genes) AS n_g\n"
                "ORDER BY level"
            )
        t_rows = conn.execute_query(term_q, timeout=60, org=ORG)
        g_rows = conn.execute_query(gene_q, timeout=60, org=ORG)
        g_by_level = {r["level"]: r["n_g"] for r in g_rows}
        per_ont_n_levels[key] = len(t_rows)
        for r in t_rows:
            coverage = g_by_level.get(r["level"], 0) / ORG_GENE_COUNT
            rows.append({
                "ontology": key,
                "level": r["level"],
                "n_terms_with_genes": r["n_terms"],
                "median": round(r["median"], 2),
                "n_genes_at_level": g_by_level.get(r["level"], 0),
                "coverage": round(coverage, 4),
                "size_factor": round(size_factor(r["median"]), 4),
                "spec_score": round(spec_score(coverage, r["median"]), 4),
            })
    # B1 score needs n_levels
    for r in rows:
        r["b1_score"] = round(b1_score(r["coverage"], r["median"],
                                        per_ont_n_levels[r["ontology"]]), 4)
    # Rank by spec_score
    rows.sort(key=lambda r: (-r["spec_score"], -r["coverage"], r["level"]))
    for i, r in enumerate(rows):
        r["spec_rank"] = i + 1
    # Re-rank by b1_score
    b1_sorted = sorted(rows, key=lambda r: (-r["b1_score"], -r["coverage"], r["level"]))
    for i, r in enumerate(b1_sorted):
        r["b1_rank"] = i + 1
    return {"rows": rows, "per_ont_n_levels": per_ont_n_levels}


def o3_kegg_gap(conn: GraphConnection) -> dict:
    """Why does KEGG L0-L2 cover 765 genes and L3 cover 1065?

    Hypotheses:
    (a) Some KOs lack a parent in Kegg_term_is_a_kegg_term (orphan KOs).
    (b) Hierarchy is incomplete.
    """
    out = {}
    # KO-level coverage
    q1 = """MATCH (k:KeggTerm) WHERE k.level = 3 RETURN count(k) AS n_ko"""
    q2 = """
    MATCH (k:KeggTerm) WHERE k.level = 3
    OPTIONAL MATCH (k)-[:Kegg_term_is_a_kegg_term]->(p:KeggTerm)
    WITH k, count(p) AS n_parents
    RETURN n_parents > 0 AS has_parent, count(k) AS n
    """
    q3 = """
    MATCH (g:Gene {organism_name:$org})-[:Gene_has_kegg_ko]->(k:KeggTerm)
    WITH k, count(DISTINCT g) AS n_genes
    OPTIONAL MATCH (k)-[:Kegg_term_is_a_kegg_term]->(p:KeggTerm)
    WITH k, n_genes, count(p) > 0 AS has_parent
    RETURN has_parent, count(k) AS n_kos, sum(n_genes) AS gene_term_pairs
    """
    # Genes attached to orphan KOs (those without parent)
    q4 = """
    MATCH (g:Gene {organism_name:$org})-[:Gene_has_kegg_ko]->(k:KeggTerm)
    WHERE NOT (k)-[:Kegg_term_is_a_kegg_term]->(:KeggTerm)
    RETURN count(DISTINCT g) AS n_orphan_kos_genes
    """
    out["n_ko_total"] = conn.execute_query(q1)[0]["n_ko"]
    out["ko_parent_breakdown"] = conn.execute_query(q2)
    out["med4_ko_parent_breakdown"] = conn.execute_query(q3, org=ORG)
    out["med4_orphan_ko_genes"] = conn.execute_query(q4, org=ORG)[0]["n_orphan_kos_genes"]
    return out


def o4_best_effort_share(conn: GraphConnection) -> dict:
    """Among terms REACHED by MED4 genes at each level, what share is best-effort?"""
    out = {}
    for key, label, edge, is_a in [
        o for o in ONTOLOGIES if o[0] in ("go_bp", "go_mf", "go_cc")
    ]:
        rel = "|".join(is_a)
        q = f"""
        MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(leaf:{label})
        MATCH (leaf)-[:{rel}*0..]->(t:{label})
        WITH DISTINCT t
        WITH t.level AS level,
             count(t) AS n_terms_reached,
             sum(CASE WHEN t.level_is_best_effort IS NOT NULL THEN 1 ELSE 0 END) AS n_best_effort
        RETURN level, n_terms_reached, n_best_effort,
               toFloat(n_best_effort)/n_terms_reached AS frac
        ORDER BY level
        """
        out[key] = conn.execute_query(q, timeout=60, org=ORG)
    return out


def main():
    with GraphConnection() as conn:
        print("=== O1/O2: Full (ontology x level) ranking for MED4 ===\n")
        r1 = o1_o2_full_ranking(conn)
        # Print by spec_rank
        print("Top 15 by spec_score (coverage x size_factor):")
        print(f"{'ont':<16} {'lvl':>3} {'cov':>6} {'med':>6} {'sf':>6} "
              f"{'spec':>6} {'b1':>6} {'n_lvl':>5}")
        for r in sorted(r1["rows"], key=lambda x: x["spec_rank"])[:15]:
            print(f"{r['ontology']:<16} {r['level']:>3} "
                  f"{r['coverage']:>6.3f} {r['median']:>6.1f} "
                  f"{r['size_factor']:>6.3f} {r['spec_score']:>6.3f} "
                  f"{r['b1_score']:>6.3f} "
                  f"{r1['per_ont_n_levels'][r['ontology']]:>5}")

        print("\nB1 qualifying rows (b1_score > 0):")
        print(f"{'ont':<16} {'lvl':>3} {'cov':>6} {'med':>6} "
              f"{'spec_rank':>9} {'b1_rank':>8}")
        for r in sorted(r1["rows"], key=lambda x: x["b1_rank"]):
            if r["b1_score"] > 0:
                print(f"{r['ontology']:<16} {r['level']:>3} "
                      f"{r['coverage']:>6.3f} {r['median']:>6.1f} "
                      f"{r['spec_rank']:>9} {r['b1_rank']:>8}")

        # GO L0 specifically
        print("\nGO L0 spec_scores (sanity):")
        for r in r1["rows"]:
            if r["level"] == 0 and r["ontology"].startswith("go"):
                print(f"  {r['ontology']} L0: cov={r['coverage']}, "
                      f"median={r['median']}, sf={r['size_factor']}, "
                      f"spec_score={r['spec_score']}")

        print("\n=== O3: KEGG coverage gap investigation ===")
        r3 = o3_kegg_gap(conn)
        print(f"Total KO (L3) terms: {r3['n_ko_total']}")
        print(f"KO has-parent breakdown (global): {r3['ko_parent_breakdown']}")
        print(f"MED4 KO has-parent breakdown: {r3['med4_ko_parent_breakdown']}")
        print(f"MED4 genes attached to KOs WITHOUT parent: {r3['med4_orphan_ko_genes']}")

        print("\n=== O4: best_effort share among MED4-reached GO terms ===")
        r4 = o4_best_effort_share(conn)
        for ont, rows in r4.items():
            print(f"\n  {ont}:")
            for r in rows:
                print(f"    L{r['level']}: {r['n_terms_reached']} terms reached, "
                      f"{r['n_best_effort']} best_effort ({r['frac']*100:.1f}%)")

    out_path = Path(__file__).parent / "verify_observations_results.json"
    out_path.write_text(json.dumps({
        "o1_o2": r1, "o3": r3, "o4": r4,
    }, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
