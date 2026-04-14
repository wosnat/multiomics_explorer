"""Scoping: PROFILE per-(ontology x level) aggregation queries against live KG.

Run: uv run python docs/superpowers/specs/scoping/profile_landscape.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from multiomics_explorer.kg.connection import GraphConnection


ORG = "Prochlorococcus MED4"

# (ontology_key, node_label, gene_edge_type, is_a_rel(s))
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


def level_query(label: str, gene_edge: str, is_a_rels: list[str]) -> str:
    """Aggregate per-term gene counts for all levels in one scan."""
    if is_a_rels:
        rel_union = "|".join(is_a_rels)
        anc = f"-[:{rel_union}*0..]->(t:{label})"
    else:
        # No hierarchy: gene-attached term IS the term at its level.
        anc = ""
    # When no hierarchy edges, bind t directly:
    if is_a_rels:
        match = (
            f"MATCH (g:Gene {{organism_name:$org}})-[:{gene_edge}]->(leaf:{label})\n"
            f"MATCH (leaf){anc}\n"
        )
    else:
        match = (
            f"MATCH (g:Gene {{organism_name:$org}})-[:{gene_edge}]->(t:{label})\n"
        )
    return (
        match
        + "WITH t.level AS level, t, collect(DISTINCT g) AS genes\n"
        + "WITH level, t, size(genes) AS n_genes\n"
        + "WITH level,\n"
        + "     count(t) AS n_terms_with_genes,\n"
        + "     sum(n_genes) AS gene_term_pairs,\n"
        + "     min(n_genes) AS min_g,\n"
        + "     max(n_genes) AS max_g,\n"
        + "     percentileCont(toFloat(n_genes), 0.25) AS q1,\n"
        + "     percentileCont(toFloat(n_genes), 0.5) AS median,\n"
        + "     percentileCont(toFloat(n_genes), 0.75) AS q3\n"
        + "RETURN level, n_terms_with_genes, gene_term_pairs, min_g, median, max_g, q1, q3\n"
        + "ORDER BY level\n"
    )


def distinct_genes_at_level_query(label: str, gene_edge: str, is_a_rels: list[str]) -> str:
    """Distinct genes reachable at each level (for genome_coverage)."""
    if is_a_rels:
        rel_union = "|".join(is_a_rels)
        return (
            f"MATCH (g:Gene {{organism_name:$org}})-[:{gene_edge}]->(leaf:{label})\n"
            f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
            "WITH t.level AS level, collect(DISTINCT g) AS genes\n"
            "RETURN level, size(genes) AS n_genes_at_level\n"
            "ORDER BY level\n"
        )
    return (
        f"MATCH (g:Gene {{organism_name:$org}})-[:{gene_edge}]->(t:{label})\n"
        "WITH t.level AS level, collect(DISTINCT g) AS genes\n"
        "RETURN level, size(genes) AS n_genes_at_level\n"
        "ORDER BY level\n"
    )


def time_query(conn: GraphConnection, cypher: str, **params) -> tuple[float, list[dict]]:
    t0 = time.perf_counter()
    rows = conn.execute_query(cypher, timeout=120, **params)
    dt = time.perf_counter() - t0
    return dt, rows


def main():
    out: dict = {"organism": ORG, "per_ontology": {}}
    with GraphConnection() as conn:
        for key, label, edge, is_a in ONTOLOGIES:
            print(f"\n=== {key} ===")
            term_q = level_query(label, edge, is_a)
            gene_q = distinct_genes_at_level_query(label, edge, is_a)

            dt_term, term_rows = time_query(conn, term_q, org=ORG)
            print(f"  term-aggregation: {dt_term*1000:.0f} ms, {len(term_rows)} levels")
            for r in term_rows:
                print(f"    L{r['level']}: "
                      f"n_terms={r['n_terms_with_genes']} "
                      f"median={r['median']:.1f} max={r['max_g']}")

            dt_gene, gene_rows = time_query(conn, gene_q, org=ORG)
            print(f"  distinct-genes:   {dt_gene*1000:.0f} ms")
            for r in gene_rows:
                print(f"    L{r['level']}: n_genes_at_level={r['n_genes_at_level']}")

            out["per_ontology"][key] = {
                "label": label,
                "term_aggregation_ms": round(dt_term * 1000, 1),
                "distinct_genes_ms": round(dt_gene * 1000, 1),
                "term_rows": term_rows,
                "gene_rows": gene_rows,
            }

    out_path = Path(__file__).parent / "profile_landscape_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
