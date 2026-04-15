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


import math
import pandas as pd


class TestFisherOra:
    @staticmethod
    def _term2gene_simple():
        """One pathway P with 3 members, one pathway Q with 6 members."""
        rows = [
            {"term_id": "P", "term_name": "Pathway P", "locus_tag": "g1"},
            {"term_id": "P", "term_name": "Pathway P", "locus_tag": "g2"},
            {"term_id": "P", "term_name": "Pathway P", "locus_tag": "g3"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g4"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g5"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g6"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g7"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g8"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g9"},
        ]
        return pd.DataFrame(rows)

    def test_missing_required_columns_raises(self):
        from multiomics_explorer import fisher_ora
        bad = pd.DataFrame([{"term_id": "P", "locus_tag": "g1"}])  # no term_name
        with pytest.raises(ValueError, match="term_name"):
            fisher_ora(
                gene_sets={"c1": ["g1"]},
                background={"c1": ["g1", "g2"]},
                term2gene=bad,
            )

    def test_extra_columns_pass_through(self):
        from multiomics_explorer import fisher_ora
        t2g = self._term2gene_simple().assign(level=1, extra="x")
        df = fisher_ora(
            gene_sets={"c1": ["g1", "g2"]},
            background={"c1": ["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "g9", "g10"]},
            term2gene=t2g,
        )
        assert "level" in df.columns
        assert "extra" in df.columns
