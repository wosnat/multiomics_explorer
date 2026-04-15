"""Verify ranking under min_gene_set_size=5, max_gene_set_size=500.

Confirms cyanorak_role L1 remains rank-1 among hierarchical ontologies
after filtering terms with < 5 or > 500 genes per term.
"""

from __future__ import annotations

from multiomics_explorer.kg.connection import GraphConnection

ORG = "Prochlorococcus MED4"
MIN_GSS = 5
MAX_GSS = 500

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
    ("tigr_role", "TigrRole", "Gene_has_tigr_role", []),
    ("cog_category", "CogFunctionalCategory", "Gene_in_cog_category", []),
    ("pfam", "Pfam", "Gene_has_pfam", []),
]


def build_landscape(edge: str, label: str, is_a: list[str]) -> str:
    """Q_landscape with WHERE n_g_per_term filter applied after per-term aggregation."""
    if is_a:
        rel = "|".join(is_a)
        bind = f"-[:{edge}]->(leaf:{label})"
        walk = f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
    else:
        bind = f"-[:{edge}]->(t:{label})"
        walk = ""
    return (
        f"MATCH (g:Gene {{organism_name:$org}}){bind}\n"
        + walk
        + "WITH t, count(DISTINCT g) AS n_g_per_term, "
        "collect(DISTINCT g) AS term_genes\n"
        "WHERE n_g_per_term >= $min_gss AND n_g_per_term <= $max_gss\n"
        "WITH t.level AS level,\n"
        "     count(t) AS n_terms_with_genes,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.25) AS q1_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.5)  AS median_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.75) AS q3_genes_per_term,\n"
        "     apoc.coll.toSet(apoc.coll.flatten(collect(term_genes))) AS all_genes\n"
        "RETURN level, n_terms_with_genes, q1_genes_per_term,\n"
        "       size(all_genes) AS n_genes_at_level,\n"
        "       median_genes_per_term, q3_genes_per_term\n"
        "ORDER BY level"
    )


def size_factor(m: float) -> float:
    if m <= 0:
        return 0.0
    return min(1.0, m / 5.0) * min(1.0, 50.0 / m)


def main() -> None:
    with GraphConnection() as conn:
        gc_rows = conn.execute_query(
            "MATCH (g:Gene {organism_name:$org}) RETURN count(g) AS total_genes",
            org=ORG,
        )
        total_genes = gc_rows[0]["total_genes"]
        print(f"Organism: {ORG}  total_genes={total_genes}")
        print(f"Filter: min_gene_set_size={MIN_GSS}  max_gene_set_size={MAX_GSS}\n")

        # Collect all rows across ontologies
        all_rows: list[dict] = []
        ont_level_counts: dict[str, int] = {}

        for key, label, edge, is_a in ONTOLOGIES:
            q = build_landscape(edge, label, is_a)
            rows = conn.execute_query(
                q, org=ORG, min_gss=MIN_GSS, max_gss=MAX_GSS
            )
            ont_level_counts[key] = len(rows)
            for r in rows:
                cov = r["n_genes_at_level"] / total_genes if total_genes else 0.0
                med = r["median_genes_per_term"]
                sf = size_factor(med)
                all_rows.append({
                    "ont": key,
                    "level": r["level"],
                    "n_terms": r["n_terms_with_genes"],
                    "n_genes": r["n_genes_at_level"],
                    "cov": cov,
                    "q1": r["q1_genes_per_term"],
                    "med": med,
                    "q3": r["q3_genes_per_term"],
                    "sf": sf,
                    "score": cov * sf,
                    "hierarchical": bool(is_a),
                })

        # Attach n_levels_in_ontology after collecting all rows
        for r in all_rows:
            r["n_levels"] = ont_level_counts[r["ont"]]

        # Sort by score desc, then coverage desc, then level asc
        all_rows.sort(key=lambda r: (-r["score"], -r["cov"], r["level"]))
        for i, r in enumerate(all_rows):
            r["rank"] = i + 1

        # Print top-15 overall
        print(f"{'Rank':>4}  {'Ontology':>16} L{'ev':2}  {'cov':>6}  "
              f"{'q1':>5}  {'med':>6}  {'q3':>6}  {'sf':>6}  "
              f"{'score':>6}  {'n_terms':>7}  H?")
        print("-" * 100)
        for r in all_rows[:15]:
            h = "H" if r["hierarchical"] else "F"
            print(f"  {r['rank']:>2}.  {r['ont']:>16} L{r['level']:<2}  "
                  f"{r['cov']:.3f}  {r['q1']:>5.1f}  {r['med']:>6.1f}  "
                  f"{r['q3']:>6.1f}  {r['sf']:.3f}  {r['score']:.3f}  "
                  f"{r['n_terms']:>7}  {h}")

        # Hierarchical subset
        hier_rows = [r for r in all_rows if r["hierarchical"]]
        print(f"\n--- Hierarchical ontologies (n_levels > 1) ---")
        for r in hier_rows[:10]:
            print(f"  hier_rank {hier_rows.index(r)+1:>2}.  "
                  f"{r['ont']} L{r['level']}  "
                  f"cov={r['cov']:.3f}  med={r['med']:.1f}  "
                  f"score={r['score']:.3f}")

        # Spot-check: cyanorak_role L1
        cyano_l1 = next(
            (r for r in all_rows if r["ont"] == "cyanorak_role" and r["level"] == 1),
            None,
        )
        if cyano_l1 is None:
            print("\nWARNING: cyanorak_role L1 not found — "
                  "all terms filtered out by min_gene_set_size?")
        else:
            hier_rank = hier_rows.index(cyano_l1) + 1
            print(f"\ncyanorak_role L1:  "
                  f"rank={cyano_l1['rank']} overall  "
                  f"hier_rank={hier_rank}  "
                  f"cov={cyano_l1['cov']:.3f}  "
                  f"med={cyano_l1['med']:.1f}  "
                  f"n_terms={cyano_l1['n_terms']}")
            if hier_rank == 1:
                print("  ✓ cyanorak_role L1 is rank-1 among hierarchical — test assertion holds.")
            else:
                print(f"  ! NOT rank-1 among hierarchical (rank {hier_rank}). "
                      "Update integration test assertion.")


if __name__ == "__main__":
    main()
