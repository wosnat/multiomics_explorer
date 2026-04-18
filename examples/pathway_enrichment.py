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


if __name__ == "__main__":
    print("=== Custom term2gene (no KG) ===")
    demo_custom_term2gene()
    print("\n=== KG-backed pathway_enrichment ===")
    try:
        demo_mcp_path()
        demo_compare_cluster()
    except Exception as e:
        print(f"(skipped KG demos: {e})")
