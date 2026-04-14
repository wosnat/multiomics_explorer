"""Verify simpler per-responsibility Cypher vs the complex aggregation.

Strategy: emit per-term rows, let Python aggregate percentiles/shares/examples.
Principle: "counts and set-intersections in Cypher, stats in Python" (parent spec).

Three builder queries per (ontology):
  Q_terms:    per-(level, term_id) n_genes_per_term + best_effort flag
  Q_coverage: per-level distinct n_genes_at_level
  Q_expcov:   per-(level, experiment_id) n_quantified_at_level + n_total_quantified

Plus edge-case probes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import median

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

# --- Simple query builders ---

def q_terms(edge: str, label: str, is_a_rels: list[str]) -> str:
    """Per-(level, term) rows: n_genes_per_term + best_effort flag.
    One row per distinct (level, term_id) reached by org genes."""
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
        "WITH t, count(DISTINCT g) AS n_genes_per_term\n"
        "RETURN t.level AS level,\n"
        "       t.id    AS term_id,\n"
        "       t.name  AS term_name,\n"
        "       t.level_is_best_effort AS best_effort,\n"
        "       n_genes_per_term\n"
        "ORDER BY level, term_id"
    )


def q_coverage(edge: str, label: str, is_a_rels: list[str]) -> str:
    """Per-level distinct genes reachable."""
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
        "RETURN t.level AS level, count(DISTINCT g) AS n_genes_at_level\n"
        "ORDER BY level"
    )


def q_expcov(edge: str, label: str, is_a_rels: list[str]) -> str:
    """Per-(experiment, level) coverage: n_quantified_at_level and n_total_quantified."""
    if is_a_rels:
        rel = "|".join(is_a_rels)
        walk = f"MATCH (leaf)-[:{rel}*0..]->(t:{label})\n"
        bind = f"-[:{edge}]->(leaf:{label})"
    else:
        walk = ""
        bind = f"-[:{edge}]->(t:{label})"
    return (
        "UNWIND $experiment_ids AS eid\n"
        "MATCH (e:Experiment {id:eid})-[:Changes_expression_of]->"
        "(g:Gene {organism_name:$org})\n"
        "WITH eid, collect(DISTINCT g) AS quantified\n"
        "WITH eid, quantified, size(quantified) AS n_total\n"
        "UNWIND quantified AS g\n"
        f"MATCH (g){bind}\n"
        + walk +
        "RETURN eid, n_total, t.level AS level,\n"
        "       count(DISTINCT g) AS n_at_level\n"
        "ORDER BY eid, level"
    )


# --- Python aggregation (what L2 would do) ---

def percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return s[f] + (s[c] - s[f]) * (k - f)


def aggregate_per_level(term_rows: list[dict], cov_rows: list[dict],
                        is_go: bool) -> list[dict]:
    by_level: dict[int, list[dict]] = {}
    for r in term_rows:
        by_level.setdefault(r["level"], []).append(r)
    cov_by_level = {r["level"]: r["n_genes_at_level"] for r in cov_rows}

    out = []
    for level in sorted(by_level):
        rows = by_level[level]
        n_gs = [r["n_genes_per_term"] for r in rows]
        n_terms = len(rows)
        row = {
            "level": level,
            "n_terms_with_genes": n_terms,
            "n_genes_at_level": cov_by_level.get(level, 0),
            "min_genes_per_term": min(n_gs),
            "q1_genes_per_term": round(percentile(n_gs, 0.25), 2),
            "median_genes_per_term": round(percentile(n_gs, 0.5), 2),
            "q3_genes_per_term": round(percentile(n_gs, 0.75), 2),
            "max_genes_per_term": max(n_gs),
        }
        if is_go:
            n_be = sum(1 for r in rows if r["best_effort"] is not None)
            row["best_effort_share"] = round(n_be / n_terms, 3) if n_terms else 0.0
        out.append(row)
    return out


def aggregate_exp_coverage(exp_rows: list[dict]) -> dict[int, dict]:
    """Group per-experiment rows by level; compute min/median/max coverage."""
    by_level: dict[int, list[float]] = {}
    for r in exp_rows:
        cov = r["n_at_level"] / r["n_total"] if r["n_total"] else 0.0
        by_level.setdefault(r["level"], []).append(cov)
    return {
        level: {
            "min_exp_coverage": round(min(covs), 4),
            "median_exp_coverage": round(percentile(covs, 0.5), 4),
            "max_exp_coverage": round(max(covs), 4),
            "n_experiments_with_coverage": len(covs),
        }
        for level, covs in by_level.items()
    }


# --- Runner ---

def time_q(conn, q, **p):
    t0 = time.perf_counter()
    rows = conn.execute_query(q, timeout=60, **p)
    return time.perf_counter() - t0, rows


def main():
    result: dict = {}
    with GraphConnection() as conn:
        # === Compare: per-ontology genome branch timing ===
        print("=== Timing: simpler 2-query split per ontology ===")
        grand = 0.0
        for key, label, edge, is_a in ONTOLOGIES:
            dt1, r1 = time_q(conn, q_terms(edge, label, is_a), org=ORG)
            dt2, r2 = time_q(conn, q_coverage(edge, label, is_a), org=ORG)
            grand += dt1 + dt2
            aggs = aggregate_per_level(r1, r2, key.startswith("go"))
            print(f"  {key:<16} terms_q={dt1*1000:>5.0f}ms ({len(r1):>4} rows)  "
                  f"cov_q={dt2*1000:>4.0f}ms ({len(r2):>2} levels)  "
                  f"levels_out={len(aggs)}")
            result.setdefault("genome_timings", {})[key] = {
                "terms_ms": round(dt1*1000, 1),
                "coverage_ms": round(dt2*1000, 1),
                "term_rows": len(r1),
                "levels": len(aggs),
            }
        print(f"  TOTAL genome (2 queries × 9 ontologies serial): {grand*1000:.0f} ms")
        result["genome_total_ms"] = round(grand * 1000, 1)

        # === Sanity: aggregation matches the complex query's output ===
        # Spot-check go_bp
        key, label, edge, is_a = ONTOLOGIES[0]
        _, r1 = time_q(conn, q_terms(edge, label, is_a), org=ORG)
        _, r2 = time_q(conn, q_coverage(edge, label, is_a), org=ORG)
        aggs = aggregate_per_level(r1, r2, is_go=True)
        print("\n=== go_bp aggregation sanity (should match earlier scoping) ===")
        for a in aggs[:6]:
            print(f"  L{a['level']}: n_terms={a['n_terms_with_genes']}, "
                  f"median={a['median_genes_per_term']}, max={a['max_genes_per_term']}, "
                  f"cov={a['n_genes_at_level']}, be_share={a.get('best_effort_share', '—')}")
        result["go_bp_sanity"] = aggs

        # === Experiment branch: simpler per-exp rows + Python aggregate ===
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
        print(f"\n=== Experiment branch: {len(EXP_IDS)} experiments × all ontologies ===")
        exp_total = 0.0
        for key, label, edge, is_a in ONTOLOGIES:
            dt, rows = time_q(conn, q_expcov(edge, label, is_a),
                              org=ORG, experiment_ids=EXP_IDS)
            aggs = aggregate_exp_coverage(rows)
            exp_total += dt
            print(f"  {key:<16} {dt*1000:>5.0f}ms ({len(rows):>3} rows) levels={list(aggs.keys())}")
        print(f"  TOTAL experiment branch: {exp_total*1000:.0f} ms")
        result["experiment_total_ms"] = round(exp_total * 1000, 1)

        # === Edge cases ===
        print("\n=== Edge cases ===")

        # E1: unknown organism
        dt, rows = time_q(conn, q_coverage("Gene_has_cyanorak_role",
                                            "CyanorakRole",
                                            ["Cyanorak_role_is_a_cyanorak_role"]),
                          org="Nonexistent Organism X")
        print(f"  E1 unknown organism: {dt*1000:.0f}ms, rows={len(rows)} (expect 0)")
        result["edge_unknown_org"] = rows

        # E2: flat ontology (no hierarchy_rels) — verify empty walk works
        dt, rows = time_q(conn, q_terms("Gene_has_tigr_role", "TigrRole", []), org=ORG)
        print(f"  E2 tigr flat: {dt*1000:.0f}ms, rows={len(rows)} "
              f"(all level==0? {all(r['level']==0 for r in rows)})")

        # E3: unknown experiment_id
        dt, rows = time_q(
            conn,
            q_expcov("Gene_has_cyanorak_role", "CyanorakRole",
                     ["Cyanorak_role_is_a_cyanorak_role"]),
            org=ORG,
            experiment_ids=["nonexistent_experiment_X"],
        )
        print(f"  E3 unknown experiment_id: {dt*1000:.0f}ms, rows={len(rows)} "
              f"(expect 0 — OPTIONAL MATCH needed?)")

        # E4: mix of found + not-found experiment ids
        dt, rows = time_q(
            conn,
            q_expcov("Gene_has_cyanorak_role", "CyanorakRole",
                     ["Cyanorak_role_is_a_cyanorak_role"]),
            org=ORG,
            experiment_ids=[EXP_IDS[0], "nonexistent_X", EXP_IDS[1]],
        )
        eids = {r["eid"] for r in rows}
        print(f"  E4 mixed found/not-found: rows={len(rows)}, distinct eids={eids}")

        # E5: experiment from wrong organism (hot1a3 experiment but filtering MED4 genes)
        dt, rows = time_q(
            conn,
            q_expcov("Gene_has_cyanorak_role", "CyanorakRole",
                     ["Cyanorak_role_is_a_cyanorak_role"]),
            org=ORG,
            experiment_ids=["10.1101/2025.11.24.690089_coculture_prochlorococcus_med4_hot1a3_rnaseq"],
        )
        print(f"  E5 wrong-organism experiment: rows={len(rows)} "
              f"(should be 0 — exp is on HOT1A3 not MED4)")

        # E6: integer type check — level should come back as Python int
        dt, rows = time_q(conn, q_terms("Gene_has_cyanorak_role", "CyanorakRole",
                                         ["Cyanorak_role_is_a_cyanorak_role"]), org=ORG)
        print(f"  E6 level type: {type(rows[0]['level']).__name__}")
        print(f"  E6 n_genes type: {type(rows[0]['n_genes_per_term']).__name__}")
        print(f"  E6 best_effort sample: "
              f"{[r.get('best_effort') for r in rows[:3]]}")

        # E7: total gene count lookup (for genome_coverage denominator)
        dt, rows = time_q(
            conn,
            "MATCH (o:OrganismTaxon {organism_name:$short_name}) "
            "RETURN o.gene_count AS n",
            short_name="MED4",
        )
        print(f"  E7 gene_count via OrganismTaxon: {dt*1000:.0f}ms, "
              f"rows={rows}")

        # E8: alt lookup — direct MATCH count (used by landscape via organism_name='Prochlorococcus MED4')
        dt, rows = time_q(
            conn,
            "MATCH (g:Gene {organism_name:$org}) RETURN count(g) AS n",
            org=ORG,
        )
        print(f"  E8 gene_count via direct count: {dt*1000:.0f}ms, "
              f"rows={rows}")

    Path(__file__).parent.joinpath("verify_simple_queries_results.json").write_text(
        json.dumps(result, indent=2, default=str)
    )


if __name__ == "__main__":
    main()
