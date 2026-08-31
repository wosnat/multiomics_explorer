"""Runnable companion to docs://analysis/enrichment.

Five scenarios, each exercising one gene-set source end-to-end against the
live KG (Neo4j at localhost:7687 unless .env says otherwise):

  landscape  ontology_landscape -> pick an (ontology, level) for MED4
  de         pathway_enrichment on real MED4 RNA-seq nitrogen experiments
             (EnrichmentResult accessors, compareCluster frame, envelope,
             informative_only side-by-side on KEGG pathways)
  cluster    cluster_enrichment on a published MED4 clustering analysis, then
             the same thing from the Python primitives
             (cluster_enrichment_inputs -> fisher_ora)
  ortholog   ortholog-group gene set (search_homolog_groups ->
             genes_by_homolog_group) against the MED4 gene universe
  custom     any locus_tag list (--locus-tags) against the MED4 gene universe,
             plus a hand-built term2gene run that needs no KG at all

Run with:
  uv run python examples/pathway_enrichment.py --scenario de
  uv run python examples/pathway_enrichment.py --scenario custom \
      --locus-tags PMM0001,PMM0002,PMM0003
"""
# CONTENTS
#   1. scenario_landscape  — ontology_landscape ranking (line ~114)
#   2. scenario_de         — pathway_enrichment + EnrichmentResult accessors (line ~135)
#   3. scenario_cluster    — cluster_enrichment + primitives (line ~189)
#   4. scenario_ortholog   — ortholog-group gene set vs organism universe (line ~223)
#   5. scenario_custom     — locus-tag list + hand-built term2gene (line ~252)
from __future__ import annotations

import argparse

import pandas as pd

from multiomics_explorer import (
    EnrichmentInputs,
    EnrichmentResult,
    cluster_enrichment,
    cluster_enrichment_inputs,
    fisher_ora,
    genes_by_homolog_group,
    genes_by_ontology,
    list_clustering_analyses,
    list_experiments,
    ontology_landscape,
    pathway_enrichment,
    run_cypher,
    search_homolog_groups,
    to_dataframe,
)

ORGANISM = "MED4"
ORGANISM_FULL = "Prochlorococcus MED4"

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 12)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def med4_rnaseq_nitrogen_experiments(min_genes: int = 500) -> list[str]:
    """Real MED4 RNA-seq experiment IDs for the DE scenario.

    `list_experiments` is the discovery surface; `distinct_gene_count` is the
    quantified universe size (the table_scope background), so tiny
    significant-only tables are skipped here.
    """
    found = list_experiments(
        organism=ORGANISM, omics_type=["RNASEQ"], treatment_type=["nitrogen"],
        limit=None,
    )
    ids = [
        r["experiment_id"] for r in found["results"]
        if (r.get("distinct_gene_count") or 0) >= min_genes
    ]
    if not ids:
        raise SystemExit("no MED4 RNA-seq nitrogen experiments with >= 500 genes")
    return ids


def organism_gene_universe(organism_full: str) -> list[str]:
    """Every locus_tag of one organism — the `organism` background.

    This is the one-liner the analysis doc recommends; `list_organisms` does
    not carry locus_tags.
    """
    rows = run_cypher(
        f"MATCH (g:Gene {{organism_name: '{organism_full}'}}) "
        "RETURN g.locus_tag AS locus_tag",
    )["results"]
    return sorted(r["locus_tag"] for r in rows)


def show_result(result: EnrichmentResult, label: str) -> None:
    df = result.results
    print(f"[{label}] kind={result.kind} rows={len(df)} "
          f"clusters={df['cluster'].nunique() if not df.empty else 0}")
    if df.empty:
        print("  (no (cluster x term) pairs passed the size filter)")
        return
    cols = ["cluster", "term_id", "term_name", "count", "bg_count",
            "fold_enrichment", "p_adjust"]
    print(df[cols].head(8).to_string(index=False))


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_landscape() -> None:
    """Rank (ontology x level) combinations before committing to one."""
    experiment_ids = med4_rnaseq_nitrogen_experiments()
    landscape = ontology_landscape(
        organism=ORGANISM,
        experiment_ids=experiment_ids,   # optional: adds experiment-weighted coverage
        min_gene_set_size=5, max_gene_set_size=500,
        limit=None,
    )
    df = to_dataframe(landscape)
    cols = ["ontology_type", "level", "relevance_rank", "genome_coverage",
            "median_genes_per_term", "n_terms_with_genes"]
    print(f"{len(df)} (ontology x level) rows for {ORGANISM}; "
          f"top 10 by relevance_rank:")
    print(df.sort_values("relevance_rank")[cols].head(10).to_string(index=False))
    print("\nGO rows carry best_effort_share (DAG depth is approximate):")
    go = df[df["ontology_type"].str.startswith("go_")]
    print(go[["ontology_type", "level", "best_effort_share",
              "genome_coverage"]].head(6).to_string(index=False))


def scenario_de() -> None:
    """DE path: pathway_enrichment + every EnrichmentResult accessor."""
    experiment_ids = med4_rnaseq_nitrogen_experiments()
    print(f"experiments: {experiment_ids}")

    result: EnrichmentResult = pathway_enrichment(
        organism=ORGANISM, experiment_ids=experiment_ids,
        ontology="go_bp", level=3, direction="both",
    )
    show_result(result, "go_bp level 3")
    print(f"clusters_skipped: {result.clusters_skipped}")

    if not result.results.empty:
        first = result.results.iloc[0]
        explanation = result.explain(first["cluster"], first["term_id"])
        print("\n--- explain() for the top row ---")
        print(explanation._repr_markdown_())
        overlap = result.overlap_genes(first["cluster"], first["term_id"])
        print(f"overlap_genes: {[g.locus_tag for g in overlap][:10]}")
        print(f"cluster_context: {result.cluster_context(first['cluster'])}")

    cc = result.to_compare_cluster_frame()
    print("\n--- to_compare_cluster_frame() head ---")
    print(cc.head(5).to_string(index=False))

    summary = result.generate_summary()
    print(f"\nn_significant={summary['n_significant']} "
          f"by_direction={summary['by_direction']}")
    env = result.to_envelope(limit=5)
    print(f"to_envelope: returned={env['returned']} truncated={env['truncated']} "
          f"filters_applied={env['filters_applied']} "
          f"background_filtered={env['background_filtered']}")

    # informative_only side-by-side on KEGG pathways (level 2 = pathway maps).
    print("\n--- informative_only on KEGG pathways ---")
    common = dict(organism=ORGANISM, experiment_ids=experiment_ids,
                  ontology="kegg", level=2, direction="both")
    default_run = pathway_enrichment(**common)                      # True
    full_run = pathway_enrichment(**common, informative_only=False)
    print(f"informative_only=True  rows={len(default_run.results)} "
          f"term2gene_rows={default_run.params['term2gene_row_count']}")
    print(f"informative_only=False rows={len(full_run.results)} "
          f"term2gene_rows={full_run.params['term2gene_row_count']}")
    global_maps = full_run.results[
        full_run.results["term_id"].str.contains("ko011", regex=False)
    ]
    kept = default_run.results["term_id"].str.contains("ko011", regex=False).sum()
    print("KEGG global/overview maps (ko011xx) are flagged uninformative in "
          f"the live KG — {len(global_maps)} rows with informative_only=False, "
          f"{kept} with the default:")
    print(global_maps[["cluster", "term_id", "term_name", "bg_count",
                       "p_adjust"]].head(4).to_string(index=False))


def scenario_cluster() -> None:
    """Cluster-membership enrichment: MCP-style call, then the primitives."""
    analyses = list_clustering_analyses(organism=ORGANISM, limit=None)
    chosen = next(
        r for r in analyses["results"]
        if "nstarvation" in r["analysis_id"]
    )
    analysis_id = chosen["analysis_id"]
    print(f"analysis: {analysis_id} ({chosen['name']})")

    result = cluster_enrichment(
        analysis_id=analysis_id, organism=ORGANISM,
        ontology="cyanorak_role", level=1,
    )
    show_result(result, "cluster_enrichment cyanorak_role level 1")
    summary = result.generate_summary()
    print(f"by_cluster: {summary['by_cluster'][:3]}")
    print(f"clusters_tested={summary['clusters_tested']} "
          f"clusters_skipped={summary['clusters_skipped']}")

    # Same thing from the primitives — this is what cluster_enrichment does.
    inputs = cluster_enrichment_inputs(analysis_id=analysis_id, organism=ORGANISM)
    print(f"\nprimitives: {len(inputs.gene_sets)} gene sets, "
          f"background(cluster_union)={len(next(iter(inputs.background.values())))} genes")
    term2gene = to_dataframe(genes_by_ontology(
        ontology="cyanorak_role", organism=ORGANISM, level=1,
        min_gene_set_size=0, max_gene_set_size=None, limit=None,
        informative_only=True,   # what cluster_enrichment passes by default
    ))
    manual = fisher_ora(inputs, term2gene)
    print(f"fisher_ora rows={len(manual.results)} "
          f"(cluster_enrichment rows={len(result.results)})")


def scenario_ortholog() -> None:
    """Ortholog-group gene set against the organism gene universe."""
    groups = search_homolog_groups(search_text="transporter", limit=100)
    group_ids = [r["group_id"] for r in groups["results"]]
    print(f"{len(group_ids)} ortholog groups match 'transporter'")

    members = genes_by_homolog_group(
        group_ids=group_ids, organisms=[ORGANISM], limit=None,
    )
    # Rows are per gene: group by group_id to get one set per group. Most
    # groups have one MED4 member, so pool them into one gene set.
    gene_set = sorted({r["locus_tag"] for r in members["results"]})
    print(f"{len(gene_set)} MED4 genes across those groups")

    universe = organism_gene_universe(ORGANISM_FULL)
    inputs = EnrichmentInputs(
        organism_name=ORGANISM,
        gene_sets={"transporter_orthologs": gene_set},
        background={"transporter_orthologs": universe},
        cluster_metadata={"transporter_orthologs": {}},
    )
    term2gene = to_dataframe(genes_by_ontology(
        ontology="cyanorak_role", organism=ORGANISM, level=1,
        min_gene_set_size=0, max_gene_set_size=None, limit=None,
    ))
    result = fisher_ora(inputs, term2gene)
    show_result(result, "ortholog gene set vs organism universe")


def scenario_custom(locus_tags: list[str]) -> None:
    """Any locus_tag list; caller supplies the background."""
    universe = organism_gene_universe(ORGANISM_FULL)
    missing = sorted(set(locus_tags) - set(universe))
    if missing:
        print(f"not in {ORGANISM_FULL}: {missing}")
    inputs = EnrichmentInputs(
        organism_name=ORGANISM,
        gene_sets={"my_genes": locus_tags},
        background={"my_genes": universe},
        cluster_metadata={"my_genes": {}},
    )
    term2gene = to_dataframe(genes_by_ontology(
        ontology="cyanorak_role", organism=ORGANISM, level=1,
        min_gene_set_size=0, max_gene_set_size=None, limit=None,
    ))
    result = fisher_ora(inputs, term2gene, min_gene_set_size=2)
    show_result(result, f"{len(locus_tags)} custom genes vs organism universe")

    # No KG at all: hand-built term2gene.
    print("\n--- hand-built term2gene (no KG) ---")
    t2g = pd.DataFrame([
        {"term_id": "MY_PATHWAY", "term_name": "My pathway", "locus_tag": f"g{i}"}
        for i in range(1, 11)
    ])
    toy = EnrichmentInputs(
        organism_name="custom",
        gene_sets={"my_cluster": ["g1", "g2", "g3"]},
        background={"my_cluster": [f"g{i}" for i in range(1, 21)]},
        cluster_metadata={"my_cluster": {}},
    )
    toy_result = fisher_ora(toy, t2g, min_gene_set_size=0)
    print(toy_result.results[["cluster", "term_id", "count", "bg_count",
                              "pvalue", "p_adjust"]].to_string(index=False))
    print(f"overlap: {[g.locus_tag for g in toy_result.overlap_genes('my_cluster', 'MY_PATHWAY')]}")


SCENARIOS = {
    "landscape": scenario_landscape,
    "de": scenario_de,
    "cluster": scenario_cluster,
    "ortholog": scenario_ortholog,
    "custom": scenario_custom,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument(
        "--locus-tags", default="PMM0001,PMM0002,PMM0003",
        help="comma-separated locus tags for --scenario custom",
    )
    args = parser.parse_args()
    print(f"=== {args.scenario} ===")
    if args.scenario == "custom":
        tags = [t.strip() for t in args.locus_tags.split(",") if t.strip()]
        scenario_custom(tags)
    else:
        SCENARIOS[args.scenario]()


if __name__ == "__main__":
    main()
