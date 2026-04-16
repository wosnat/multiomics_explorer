"""Runnable examples matching docs://analysis/enrichment's code blocks.

Usage:
    uv run python examples/pathway_enrichment.py --scenario de
    uv run python examples/pathway_enrichment.py --scenario cluster

Scenarios:
    landscape    — pick (ontology, level) via ontology_landscape
    de           — DE path, reproduces the MCP tool output
    cluster      — cluster-membership enrichment (non-DE)
    ortholog     — ortholog-group enrichment (non-DE)
    custom       — manual gene list
    brite        — BRITE tree-scoped enrichment (transporters)

Each scenario prints a short summary (top 5 pathways by p_adjust).
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from multiomics_explorer import (
    EnrichmentInputs,
    de_enrichment_inputs,
    fisher_ora,
    signed_enrichment_score,
)
from multiomics_explorer.api import (
    genes_by_ontology,
    list_experiments,
    list_filter_values,
    list_organisms,
    ontology_landscape,
    gene_clusters_by_gene,
    genes_in_cluster,
    list_clustering_analyses,
)
from multiomics_explorer.analysis.frames import to_dataframe


def _print_top(df: pd.DataFrame, n: int = 5, title: str = "top pathways") -> None:
    print(f"\n{title} (top {n} by p_adjust):")
    if df is None or df.empty:
        print("  (no rows)")
        return
    cols = [c for c in ["cluster", "term_id", "term_name", "p_adjust", "count", "bg_count"] if c in df.columns]
    print(df.sort_values("p_adjust").head(n)[cols].to_string(index=False))


def scenario_1_landscape(args: argparse.Namespace) -> None:
    """Rank (ontology × level) combinations for MED4."""
    result = ontology_landscape(
        organism=args.organism,
        min_gene_set_size=5,
        max_gene_set_size=500,
    )
    df = to_dataframe(result)
    if df.empty:
        print("Landscape returned zero rows.")
        return
    print("Top 10 (ontology × level) combinations by relevance_rank:")
    cols = [c for c in ["ontology", "level", "genome_coverage", "median_genes_per_term", "relevance_rank"] if c in df.columns]
    print(df.sort_values("relevance_rank").head(10)[cols].to_string(index=False))


def scenario_2_de(args: argparse.Namespace) -> None:
    """DE → enrichment. Reproduces the MCP tool's output."""
    experiments = list_experiments(organism=args.organism, limit=50)
    # Filter: list_experiments returns all experiments touching the organism (including cocultures),
    # so we need to filter to experiments where organism_name matches and there's no conflicting
    # organism_id in the experiment_ids that would cause the DE call to fail.
    # The safest approach: only use experiments for the target organism.
    exp_ids = []
    for e in experiments["results"]:
        # Skip cocultures to avoid multi-organism constraint violations
        if "coculture" not in (e.get("treatment_type") or []):
            exp_ids.append(e["experiment_id"])
        if len(exp_ids) >= 5:
            break
    if not exp_ids:
        print(f"No non-coculture experiments for organism={args.organism}")
        return
    inputs = de_enrichment_inputs(
        experiment_ids=exp_ids,
        organism=args.organism,
        direction="both",
        significant_only=True,
    )
    if not inputs.gene_sets:
        print("No clusters produced (no significant DE rows).")
        return
    term2gene = to_dataframe(
        genes_by_ontology(
            ontology=args.ontology,
            organism=args.organism,
            level=args.level,
        )
    )
    df = fisher_ora(
        inputs.gene_sets, inputs.background, term2gene,
        min_gene_set_size=5, max_gene_set_size=500,
    )
    if df.empty:
        print("fisher_ora produced zero rows.")
        return
    df["direction"] = df["cluster"].map(
        lambda c: inputs.cluster_metadata[c]["direction"]
    )
    sign = np.where(df["direction"] == "up", 1, -1)
    df["signed_score"] = sign * -np.log10(df["p_adjust"].clip(lower=1e-300))
    _print_top(df, title="DE enrichment")


def scenario_3_cluster(args: argparse.Namespace) -> None:
    """Cluster-membership enrichment (non-DE)."""
    analyses = list_clustering_analyses(organism=args.organism, limit=1)
    if not analyses["results"]:
        print("No clustering analyses available.")
        return
    analysis_id = analyses["results"][0]["analysis_id"]
    members = genes_in_cluster(analysis_id=analysis_id)
    gene_sets: dict[str, list[str]] = {}
    universe: set[str] = set()
    for row in members["results"]:
        cluster_key = f"cluster_{row['cluster_id']}"
        gene_sets.setdefault(cluster_key, []).append(row["locus_tag"])
        universe.add(row["locus_tag"])
    if not gene_sets:
        print("No clusters produced.")
        return
    background = {c: list(universe) for c in gene_sets}
    term2gene = to_dataframe(
        genes_by_ontology(
            ontology=args.ontology,
            organism=args.organism,
            level=args.level,
        )
    )
    df = fisher_ora(gene_sets, background, term2gene)
    _print_top(df, title="Cluster-membership enrichment")


def scenario_4_homolog(args: argparse.Namespace) -> None:
    """Ortholog-group enrichment (non-DE) — skeleton."""
    print("scenario_4_homolog: placeholder — supply --group-ids to populate.")


def scenario_5_custom(args: argparse.Namespace) -> None:
    """Custom gene list. Any list of locus_tags works."""
    if not args.locus_tags:
        print("scenario_5_custom: pass --locus-tags with a comma-separated list.")
        return
    gene_sets = {"custom": args.locus_tags.split(",")}
    term2gene = to_dataframe(
        genes_by_ontology(
            ontology=args.ontology,
            organism=args.organism,
            level=args.level,
        )
    )
    if term2gene.empty:
        print(f"No ontology annotations found for organism={args.organism}")
        return
    # Use the genes in the ontology as the background universe
    background = list(term2gene["locus_tag"].unique())
    df = fisher_ora(gene_sets, background, term2gene)
    _print_top(df, title="Custom gene-list enrichment")


def scenario_6_brite(args: argparse.Namespace) -> None:
    """BRITE tree-scoped enrichment (transporters)."""
    # Step 1: discover BRITE trees.
    trees = list_filter_values("brite_tree")
    print("Available BRITE trees:")
    for t in trees["results"][:5]:
        print(f"  {t['value']} ({t.get('tree_code', '?')}): {t['count']} terms")

    # Step 2: check landscape for transporters.
    landscape = ontology_landscape(
        organism=args.organism,
        ontology="brite",
        tree="transporters",
    )
    df_landscape = to_dataframe(landscape)
    if df_landscape.empty:
        print("No BRITE transporter landscape rows.")
        return
    print("\nTransporter landscape:")
    cols = [c for c in ["ontology", "level", "genome_coverage", "median_genes_per_term", "relevance_rank", "tree"] if c in df_landscape.columns]
    print(df_landscape.sort_values("relevance_rank").head(5)[cols].to_string(index=False))

    # Step 3: pick experiments and run enrichment.
    experiments = list_experiments(organism=args.organism, limit=50)
    exp_ids = []
    for e in experiments["results"]:
        if "coculture" not in (e.get("treatment_type") or []):
            exp_ids.append(e["experiment_id"])
        if len(exp_ids) >= 3:
            break
    if not exp_ids:
        print(f"No non-coculture experiments for organism={args.organism}")
        return

    inputs = de_enrichment_inputs(
        experiment_ids=exp_ids,
        organism=args.organism,
        direction="both",
        significant_only=True,
    )
    if not inputs.gene_sets:
        print("No clusters produced (no significant DE rows).")
        return

    term2gene = to_dataframe(
        genes_by_ontology(
            ontology="brite", organism=args.organism, level=1, tree="transporters",
        )
    )
    if term2gene.empty:
        print("No transporter TERM2GENE rows.")
        return

    df = fisher_ora(
        inputs.gene_sets, inputs.background, term2gene,
        min_gene_set_size=3, max_gene_set_size=500,
    )
    _print_top(df, title="BRITE transporter enrichment")


_SCENARIOS = {
    "landscape": scenario_1_landscape,
    "de": scenario_2_de,
    "cluster": scenario_3_cluster,
    "ortholog": scenario_4_homolog,
    "custom": scenario_5_custom,
    "brite": scenario_6_brite,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", choices=list(_SCENARIOS), required=True,
        help="Which scenario to run",
    )
    parser.add_argument("--organism", default="Prochlorococcus MED4")
    parser.add_argument("--ontology", default="go_bp")
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--locus-tags", default=None, help="Comma-separated locus_tags (custom scenario)")
    args = parser.parse_args(argv)
    _SCENARIOS[args.scenario](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
