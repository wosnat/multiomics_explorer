"""Unit tests for multiomics_explorer.analysis.enrichment."""
from __future__ import annotations

import pytest


class TestEnrichmentInputs:
    def test_importable_from_top_level(self):
        from multiomics_explorer import EnrichmentInputs
        assert EnrichmentInputs is not None

    def test_construct_with_required_fields(self):
        from multiomics_explorer import EnrichmentInputs
        obj = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"exp1|T0|up": ["PMM0001"]},
            background={"exp1|T0|up": ["PMM0001", "PMM0002"]},
            cluster_metadata={"exp1|T0|up": {"experiment_id": "exp1"}},
        )
        assert obj.organism_name == "MED4"
        assert obj.not_found == []
        assert obj.not_matched == []
        assert obj.no_expression == []

    def test_buckets_accept_explicit_values(self):
        from multiomics_explorer import EnrichmentInputs
        obj = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={},
            background={},
            cluster_metadata={},
            not_found=["missing_exp"],
            not_matched=["wrong_org_exp"],
            no_expression=["empty_de_exp"],
        )
        assert obj.not_found == ["missing_exp"]
        assert obj.not_matched == ["wrong_org_exp"]
        assert obj.no_expression == ["empty_de_exp"]
