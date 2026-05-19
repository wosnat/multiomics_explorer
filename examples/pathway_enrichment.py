"""Example: pathway enrichment with the EnrichmentResult API.

Demonstrates:
  - pathway_enrichment returns an EnrichmentResult object
  - result.results DataFrame for pandas slicing/plotting
  - result.explain(cluster, term_id) for per-term drill-down
  - result.overlap_genes / background_genes accessors
  - result.to_compare_cluster_frame() for clusterProfiler-style output
  - result.generate_summary() for the aggregate view
  - result.to_envelope() for the MCP-compatible dict
  - Custom term2gene path (hand-built, no KG)
  - Side-by-side `informative_only=True` (default) vs `False` row counts

Run with: uv run python examples/pathway_enrichment.py
"""
from __future__ import annotations

import pandas as pd

from multiomics_explorer import (
    EnrichmentInputs,
    EnrichmentResult,
    fisher_ora,
    pathway_enrichment,
)


def demo_mcp_path():
    """High-level API demo (requires KG)."""
    result: EnrichmentResult = pathway_enrichment(
        organism="MED4",
        experiment_ids=["EXP042"],
        ontology="go",
        level=2,
    )
    print(f"kind={result.kind}  rows={len(result.results)}")
    print(result.results.head())

    if not result.results.empty:
        first = result.results.iloc[0]
        exp = result.explain(first["cluster"], first["term_id"])
        print(exp._repr_markdown_())
        overlap = result.overlap_genes(first["cluster"], first["term_id"])
        print(f"Overlap genes: {[g.locus_tag for g in overlap]}")

    summary = result.generate_summary()
    print(f"n_significant={summary['n_significant']}")
    envelope = result.to_envelope(limit=5)
    print(f"returned={envelope['returned']}, truncated={envelope['truncated']}")


def demo_custom_term2gene():
    """Low-level fisher_ora demo with hand-built term2gene (no KG)."""
    term2gene = pd.DataFrame([
        {"term_id": "MY_PATHWAY", "term_name": "My pathway", "locus_tag": f"g{i}"}
        for i in range(1, 11)
    ])
    inputs = EnrichmentInputs(
        organism_name="custom",
        gene_sets={"my_cluster": ["g1", "g2", "g3"]},
        background={"my_cluster": [f"g{i}" for i in range(1, 21)]},
        cluster_metadata={"my_cluster": {}},
    )
    result = fisher_ora(inputs, term2gene, min_gene_set_size=0)
    print(result.results)
    overlap = result.overlap_genes("my_cluster", "MY_PATHWAY")
    for g in overlap:
        assert g.gene_name is None
        print(g.locus_tag)


def demo_compare_cluster():
    """Export to clusterProfiler compareCluster format for plotting."""
    result = pathway_enrichment(
        organism="MED4", experiment_ids=["EXP042"], ontology="go", level=2,
    )
    cc_frame = result.to_compare_cluster_frame()
    print(cc_frame.head())


def demo_informative_only():
    """Side-by-side: `informative_only=True` (default) vs `False`.

    As of the 2026-05 KG release, both `pathway_enrichment` and
    `cluster_enrichment` default to `informative_only=True`. Uninformative
    ontology terms (e.g. KEGG `map00001` "metabolic pathways", GO root
    `go:0008150`) are excluded from the Fisher tests by default — they are
    large catch-all buckets that "enrich" trivially in any DE set.

    The filter is term-side only — the DE foreground, the background, and
    the DE inputs are all unaffected. Only the term2gene mapping fed into
    Fisher loses rows when `informative_only=True`.

    Running the same call once with the default and once with
    `informative_only=False` lets you see both rankings side by side. The
    per-row `is_informative` column is present in either mode, so the
    opt-out call alone gives you both views (filter the DataFrame on
    `is_informative` post-hoc to recover the default-True ranking).
    """
    common_kwargs = dict(
        organism="MED4",
        experiment_ids=["EXP042"],
        ontology="kegg",
        level=2,
    )
    default_run: EnrichmentResult = pathway_enrichment(
        **common_kwargs,  # informative_only=True (default)
    )
    full_run: EnrichmentResult = pathway_enrichment(
        **common_kwargs,
        informative_only=False,
    )
    print(f"informative_only=True   rows={len(default_run.results)}")
    print(f"informative_only=False  rows={len(full_run.results)}")
    print("\nFull-run head (uninformative terms surfaced via is_informative):")
    print(
        full_run.results[
            ["term_id", "term_name", "is_informative", "p_adjust"]
        ].head(10)
    )


if __name__ == "__main__":
    print("=== Custom term2gene (no KG) ===")
    demo_custom_term2gene()
    print("\n=== KG-backed pathway_enrichment ===")
    try:
        demo_mcp_path()
        demo_compare_cluster()
        print("\n=== informative_only side-by-side ===")
        demo_informative_only()
    except Exception as e:
        print(f"(skipped KG demos: {e})")
