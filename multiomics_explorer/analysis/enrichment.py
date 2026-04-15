"""Pathway-enrichment primitives for multiomics_explorer.

Public API:
- EnrichmentInputs: Pydantic model holding gene_sets + backgrounds + metadata + validation buckets.
- de_enrichment_inputs: build EnrichmentInputs from DE results.
- fisher_ora: run Fisher-exact ORA over TERM2GENE for one or more gene sets.
- signed_enrichment_score: collapse up/down cluster pairs into a single signed row per pathway.

See docs://analysis/enrichment for methodology.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EnrichmentInputs(BaseModel):
    """Inputs bundle for fisher_ora. Produced by de_enrichment_inputs.

    Gene-list-agnostic callers construct this directly; the DE helper is
    convenience. See docs://analysis/enrichment for end-to-end examples.
    """

    organism_name: str = Field(
        description="Single organism for all clusters (single-organism enforced).",
    )
    gene_sets: dict[str, list[str]] = Field(
        description=(
            "Cluster name -> foreground locus_tags (e.g. significant DE genes "
            "for that experiment/timepoint/direction)."
        ),
    )
    background: dict[str, list[str]] = Field(
        description=(
            "Cluster name -> universe locus_tags. Per-cluster because "
            "table_scope backgrounds vary between experiments."
        ),
    )
    cluster_metadata: dict[str, dict] = Field(
        description=(
            "Cluster name -> metadata dict (experiment_id, timepoint, "
            "direction, omics_type, table_scope, treatment_type, "
            "background_factors, is_time_course, etc.)."
        ),
    )
    not_found: list[str] = Field(
        default_factory=list,
        description="experiment_ids absent from the KG.",
    )
    not_matched: list[str] = Field(
        default_factory=list,
        description=(
            "experiment_ids that exist but belong to a different organism."
        ),
    )
    no_expression: list[str] = Field(
        default_factory=list,
        description=(
            "experiment_ids matching the organism but with no DE rows "
            "(reuses differential_expression_by_gene's bucket name)."
        ),
    )
