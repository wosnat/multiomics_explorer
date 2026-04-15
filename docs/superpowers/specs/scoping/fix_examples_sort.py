"""Test apoc sort syntax variants to get top-5 terms correctly."""

from multiomics_explorer.kg.connection import GraphConnection

ORG = "Prochlorococcus MED4"
EDGE = "Gene_involved_in_biological_process"
LABEL = "BiologicalProcess"
REL = "Biological_process_is_a_biological_process|Biological_process_part_of_biological_process"


VARIANTS = {
    "sortMaps('^n_genes') [0..5]": (
        "WITH t.level AS level, "
        "apoc.coll.sortMaps(collect({term_id:t.id, name:t.name, n_genes:n_g_per_term}), "
        "'^n_genes')[0..5] AS ex\n"
    ),
    "sortMaps('n_genes') REVERSE [0..5]": (
        "WITH t.level AS level, "
        "apoc.coll.reverse(apoc.coll.sortMaps(collect({term_id:t.id, name:t.name, n_genes:n_g_per_term}), "
        "'n_genes'))[0..5] AS ex\n"
    ),
    "sortMaps('n_genes') TAIL [-5..]": (
        "WITH t.level AS level, "
        "collect({term_id:t.id, name:t.name, n_genes:n_g_per_term}) AS all_t\n"
        "WITH level, apoc.coll.sortMaps(all_t, 'n_genes') AS sorted_t\n"
        "WITH level, sorted_t[size(sorted_t)-5..] AS ex\n"
    ),
    "apoc.agg.maxItems(map, n_g, 5)": (
        # NB: apoc.agg.maxItems is an aggregation function — applies inline
        "WITH t.level AS level, "
        "apoc.agg.maxItems({term_id:t.id, name:t.name, n_genes:n_g_per_term}, "
        "toFloat(n_g_per_term), 5) AS ex_raw\n"
        "WITH level, ex_raw.items AS ex\n"
    ),
    "ORDER BY ... DESC + collect [0..5]": (
        # The trick: ORDER BY before collect preserves order within the collected list.
        "WITH t.level AS level, t, n_g_per_term\n"
        "ORDER BY level, n_g_per_term DESC\n"
        "WITH level, collect({term_id:t.id, name:t.name, "
        "n_genes:n_g_per_term})[0..5] AS ex\n"
    ),
}


def run_variant(conn, label, with_clause):
    q = (
        f"MATCH (g:Gene {{organism_name:$org}})-[:{EDGE}]->(leaf:{LABEL})\n"
        f"MATCH (leaf)-[:{REL}*0..]->(t:{LABEL})\n"
        "WITH t, count(DISTINCT g) AS n_g_per_term\n"
        + with_clause +
        "RETURN level, ex\n"
        "ORDER BY level"
    )
    try:
        rows = conn.execute_query(q, timeout=60, org=ORG)
    except Exception as exc:
        print(f"\n[{label}] ERROR: {exc}")
        return
    # Look at L3 (should show large n_genes)
    l3 = next((r for r in rows if r["level"] == 3), None)
    if l3 is None:
        print(f"\n[{label}] no L3 row")
        return
    print(f"\n[{label}] L3 top entries:")
    for e in l3["ex"]:
        print(f"  n={e['n_genes']:>3}  {e['term_id']}  {e.get('name','')[:60]}")


def main():
    with GraphConnection() as conn:
        for label, with_clause in VARIANTS.items():
            run_variant(conn, label, with_clause)


if __name__ == "__main__":
    main()
