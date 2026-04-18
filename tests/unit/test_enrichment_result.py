"""Unit tests for EnrichmentResult and associated Pydantic models."""
from __future__ import annotations

import pytest


class TestDEStats:
    def test_importable(self):
        from multiomics_explorer import DEStats
        assert DEStats is not None

    def test_construct_with_required_fields(self):
        from multiomics_explorer import DEStats
        stats = DEStats(
            log2fc=1.5,
            padj=0.01,
            direction="up",
            significant=True,
        )
        assert stats.log2fc == 1.5
        assert stats.padj == 0.01
        assert stats.direction == "up"
        assert stats.significant is True
        assert stats.rank is None

    def test_rank_optional(self):
        from multiomics_explorer import DEStats
        stats = DEStats(
            log2fc=1.5, padj=0.01, direction="up", significant=True, rank=3,
        )
        assert stats.rank == 3

    def test_direction_literal_validates(self):
        from multiomics_explorer import DEStats
        with pytest.raises(Exception):  # pydantic ValidationError
            DEStats(log2fc=1.5, padj=0.01, direction="invalid", significant=True)

    def test_field_descriptions_present(self):
        from multiomics_explorer import DEStats
        for name, field in DEStats.model_fields.items():
            assert field.description, f"DEStats.{name} missing description"


class TestGeneRef:
    def test_importable(self):
        from multiomics_explorer import GeneRef
        assert GeneRef is not None

    def test_minimal_construction(self):
        from multiomics_explorer import GeneRef
        ref = GeneRef(locus_tag="PMM0712")
        assert ref.locus_tag == "PMM0712"
        assert ref.gene_name is None
        assert ref.product is None
        assert ref.log2fc is None

    def test_full_construction(self):
        from multiomics_explorer import GeneRef
        ref = GeneRef(
            locus_tag="PMM0712",
            gene_name="pstS",
            product="phosphate ABC transporter",
            log2fc=2.0,
            padj=0.001,
            rank=1,
            direction="up",
            significant=True,
        )
        assert ref.gene_name == "pstS"
        assert ref.rank == 1

    def test_field_descriptions_present(self):
        from multiomics_explorer import GeneRef
        for name, field in GeneRef.model_fields.items():
            assert field.description, f"GeneRef.{name} missing description"


class TestEnrichmentExplanation:
    def test_importable(self):
        from multiomics_explorer import EnrichmentExplanation
        assert EnrichmentExplanation is not None

    def test_minimal_construction(self):
        from multiomics_explorer import EnrichmentExplanation
        exp = EnrichmentExplanation(
            cluster="c1",
            term_id="GO:0006810",
            term_name="transport",
            cluster_kind="pathway",
            cluster_metadata={"experiment_id": "EXP042"},
            count=2,
            n_foreground=10,
            bg_count=20,
            n_background=100,
            gene_ratio="2/10",
            bg_ratio="20/100",
            fold_enrichment=1.0,
            rich_factor=0.1,
            pvalue=0.05,
            p_adjust=0.10,
            rank_in_cluster=3,
            n_terms_in_cluster=50,
            overlap_genes=[],
            background_genes=[],
        )
        assert exp.cluster == "c1"
        assert exp.overlap_preview_n == 10  # default

    def test_cluster_kind_literal_validates(self):
        from multiomics_explorer import EnrichmentExplanation
        with pytest.raises(Exception):
            EnrichmentExplanation(
                cluster="c1", term_id="t", term_name="tn",
                cluster_kind="invalid",  # not in Literal
                cluster_metadata={}, count=0, n_foreground=0,
                bg_count=0, n_background=0,
                gene_ratio="0/0", bg_ratio="0/0",
                fold_enrichment=0.0, rich_factor=0.0,
                pvalue=1.0, p_adjust=1.0,
                rank_in_cluster=1, n_terms_in_cluster=1,
                overlap_genes=[], background_genes=[],
            )

    def test_field_descriptions_present(self):
        from multiomics_explorer import EnrichmentExplanation
        for name, field in EnrichmentExplanation.model_fields.items():
            assert field.description, f"EnrichmentExplanation.{name} missing description"
