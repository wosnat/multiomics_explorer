"""Scoping: experiment_ids branch performance.

Two questions:
1. Does per-experiment coverage computation blow up for MED4 x cyanorak_role x 10 exps?
2. L1 multi-ontology UNION vs L2 per-ontology orchestration — measure both.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from multiomics_explorer.kg.connection import GraphConnection

ORG = "Prochlorococcus MED4"

EXP_IDS = [
    "10.1101/2025.11.24.690089_coculture_alteromonas_hot1a3_med4_rnaseq",
    "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_proteomics_coculture",
    "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_proteomics_axenic",
    "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
    "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_coculture",
    "10.3389/fmicb.2022.1038136_salt_low_salinity_acclimation_28_med4_rnaseq",
    "10.1038/ismej.2017.88_nitrogen_stress_ndepleted_pro99_medium_med4_rnaseq",
    "10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq",
    "10.1371/journal.pone.0165375_light_stress_constant_dark_med4_rnaseq_dark",
    "10.1038/ismej.2015.36_carbon_air_0036_co2_21_med4_microarray",
]

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


def exp_branch_query(label: str, gene_edge: str, is_a_rels: list[str]) -> str:
    """Per-(level, experiment) coverage + per-level term-size stats."""
    if is_a_rels:
        rel_union = "|".join(is_a_rels)
        walk = f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
        bind = f"-[:{gene_edge}]->(leaf:{label})"
    else:
        walk = ""
        bind = f"-[:{gene_edge}]->(t:{label})"

    # Step 1: per-experiment, collect the set of quantified genes.
    # Step 2: cross with gene-term annotations and rollup levels.
    return (
        "UNWIND $experiment_ids AS eid\n"
        "MATCH (e:Experiment {id:eid})-[:Changes_expression_of]->(gq:Gene {organism_name:$org})\n"
        "WITH eid, collect(DISTINCT gq) AS quantified_genes\n"
        f"UNWIND quantified_genes AS g\n"
        f"MATCH (g){bind}\n"
        + walk +
        "WITH eid, quantified_genes, t.level AS level, t, collect(DISTINCT g) AS genes\n"
        "WITH eid, size(quantified_genes) AS n_quant, level, t, size(genes) AS n_g_t\n"
        "WITH eid, n_quant, level,\n"
        "     count(t) AS n_terms_with_genes,\n"
        "     sum(n_g_t) AS gene_term_pairs,\n"
        "     min(n_g_t) AS min_g, max(n_g_t) AS max_g,\n"
        "     percentileCont(toFloat(n_g_t), 0.5) AS median_g,\n"
        "     collect(DISTINCT t) AS terms\n"
        "RETURN eid, n_quant, level, n_terms_with_genes, gene_term_pairs,\n"
        "       min_g, median_g, max_g\n"
        "ORDER BY level, eid\n"
    )


def multi_ontology_union_query(ontologies: list[tuple]) -> str:
    """Single L1 query: UNION per-ontology aggregations (no experiment filter)."""
    parts = []
    for key, label, edge, is_a in ontologies:
        if is_a:
            rel = "|".join(is_a)
            m = (
                f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(leaf:{label})\n"
                f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
            )
        else:
            m = f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(t:{label})\n"
        parts.append(
            m
            + f"WITH '{key}' AS ontology, t.level AS level, t, collect(DISTINCT g) AS genes\n"
            + "WITH ontology, level, t, size(genes) AS n_g\n"
            + "RETURN ontology, level,\n"
            + "       count(t) AS n_terms_with_genes,\n"
            + "       sum(n_g) AS gene_term_pairs,\n"
            + "       min(n_g) AS min_g, max(n_g) AS max_g,\n"
            + "       percentileCont(toFloat(n_g), 0.5) AS median_g"
        )
    return "\nUNION ALL\n".join(parts)


def time_query(conn, cypher, **p):
    t0 = time.perf_counter()
    rows = conn.execute_query(cypher, timeout=240, **p)
    return time.perf_counter() - t0, rows


def main():
    out: dict = {"organism": ORG, "n_experiments": len(EXP_IDS)}
    with GraphConnection() as conn:

        # === Q1: cyanorak_role x 10 experiments ===
        key, label, edge, is_a = next(o for o in ONTOLOGIES if o[0] == "cyanorak_role")
        q = exp_branch_query(label, edge, is_a)
        dt, rows = time_query(conn, q, org=ORG, experiment_ids=EXP_IDS)
        print(f"\n=== cyanorak_role x 10 experiments: {dt*1000:.0f} ms, {len(rows)} rows ===")
        by_level: dict[int, list] = {}
        for r in rows:
            by_level.setdefault(r["level"], []).append(r)
        for lvl, lrows in sorted(by_level.items()):
            covers = [r["gene_term_pairs"] for r in lrows]
            print(f"  L{lvl}: {len(lrows)} (exp,lvl) rows, "
                  f"n_terms_with_genes={lrows[0]['n_terms_with_genes']}, "
                  f"median_g sample={[round(r['median_g'],1) for r in lrows[:3]]}")
        out["cyanorak_x_10_exp_ms"] = round(dt * 1000, 1)
        out["cyanorak_x_10_exp_rows"] = rows

        # === Q2: go_bp x 10 experiments (biggest expected case) ===
        key, label, edge, is_a = next(o for o in ONTOLOGIES if o[0] == "go_bp")
        q = exp_branch_query(label, edge, is_a)
        dt, rows = time_query(conn, q, org=ORG, experiment_ids=EXP_IDS)
        print(f"\n=== go_bp x 10 experiments: {dt*1000:.0f} ms, {len(rows)} rows ===")
        out["go_bp_x_10_exp_ms"] = round(dt * 1000, 1)

        # === Q3: go_mf x 10 experiments ===
        key, label, edge, is_a = next(o for o in ONTOLOGIES if o[0] == "go_mf")
        q = exp_branch_query(label, edge, is_a)
        dt, rows = time_query(conn, q, org=ORG, experiment_ids=EXP_IDS)
        print(f"=== go_mf x 10 experiments: {dt*1000:.0f} ms, {len(rows)} rows ===")
        out["go_mf_x_10_exp_ms"] = round(dt * 1000, 1)

        # === Q4: L2 orchestration: 9 separate queries, all ontologies, no experiments ===
        t0 = time.perf_counter()
        per_ont_results = {}
        for key, label, edge, is_a in ONTOLOGIES:
            if is_a:
                rel = "|".join(is_a)
                m = (
                    f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(leaf:{label})\n"
                    f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
                )
            else:
                m = f"MATCH (g:Gene {{organism_name:$org}})-[:{edge}]->(t:{label})\n"
            q_single = (
                m
                + "WITH t.level AS level, t, collect(DISTINCT g) AS genes\n"
                + "WITH level, t, size(genes) AS n_g\n"
                + "RETURN level, count(t) AS n_terms, sum(n_g) AS pairs, "
                + "min(n_g) AS min_g, max(n_g) AS max_g, "
                + "percentileCont(toFloat(n_g),0.5) AS median_g"
            )
            rr = conn.execute_query(q_single, timeout=60, org=ORG)
            per_ont_results[key] = rr
        dt_l2 = time.perf_counter() - t0
        print(f"\n=== L2 orchestration (9 serial queries): {dt_l2*1000:.0f} ms ===")
        out["l2_orch_all_ontologies_ms"] = round(dt_l2 * 1000, 1)

        # === Q5: L1 UNION all ontologies ===
        q_union = multi_ontology_union_query(ONTOLOGIES)
        t0 = time.perf_counter()
        rows_union = conn.execute_query(q_union, timeout=120, org=ORG)
        dt_l1 = time.perf_counter() - t0
        print(f"=== L1 UNION (1 query, all ontologies): {dt_l1*1000:.0f} ms, {len(rows_union)} rows ===")
        out["l1_union_all_ontologies_ms"] = round(dt_l1 * 1000, 1)
        out["l1_union_rows"] = len(rows_union)

        # === Q6: sanity re-run (cache warm) ===
        t0 = time.perf_counter()
        rows_union2 = conn.execute_query(q_union, timeout=120, org=ORG)
        dt_l1_warm = time.perf_counter() - t0
        print(f"=== L1 UNION warm re-run: {dt_l1_warm*1000:.0f} ms ===")
        out["l1_union_warm_ms"] = round(dt_l1_warm * 1000, 1)

        # === Q7: worst case — all ontologies x 10 experiments ===
        # Serialised L2 orchestration with experiment filter
        t0 = time.perf_counter()
        l2_exp_results = {}
        for key, label, edge, is_a in ONTOLOGIES:
            q = exp_branch_query(label, edge, is_a)
            rr = conn.execute_query(q, timeout=120, org=ORG, experiment_ids=EXP_IDS)
            l2_exp_results[key] = len(rr)
        dt_l2_exp = time.perf_counter() - t0
        print(f"\n=== L2 orchestration x 10 experiments (all ontologies): {dt_l2_exp*1000:.0f} ms ===")
        for key, n in l2_exp_results.items():
            print(f"    {key}: {n} rows")
        out["l2_orch_x_10_exp_all_ms"] = round(dt_l2_exp * 1000, 1)

    out_path = Path(__file__).parent / "profile_experiment_branch_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
