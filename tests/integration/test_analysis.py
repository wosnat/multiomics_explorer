"""Integration tests for analysis utilities — requires Neo4j."""

import pytest

from multiomics_explorer.analysis import gene_set_compare, response_matrix
from multiomics_explorer.api import functions as api

KNOWN_GENE = "PMM0001"
# Two genes known to have expression data in the KG
KNOWN_EXPRESSED_GENES = ["PMM0370", "PMM0920"]


@pytest.mark.kg
class TestResponseMatrixIntegration:
    def test_returns_dataframe_with_correct_shape(self, conn):
        df = response_matrix(genes=KNOWN_EXPRESSED_GENES, conn=conn)

        assert len(df) == len(KNOWN_EXPRESSED_GENES)
        assert df.index.name == "locus_tag"
        for col in ("gene_name", "product", "gene_category"):
            assert col in df.columns

    def test_group_columns_are_treatment_types(self, conn):
        df = response_matrix(genes=KNOWN_EXPRESSED_GENES, conn=conn)

        metadata_cols = {"gene_name", "product", "gene_category"}
        group_cols = [c for c in df.columns if c not in metadata_cols]
        assert len(group_cols) > 0

    def test_cell_values_are_valid(self, conn):
        df = response_matrix(genes=KNOWN_EXPRESSED_GENES, conn=conn)

        valid_values = {"up", "down", "mixed", "not_responded", "not_known"}
        metadata_cols = {"gene_name", "product", "gene_category"}
        group_cols = [c for c in df.columns if c not in metadata_cols]
        for col in group_cols:
            for val in df[col]:
                assert val in valid_values, f"Unexpected value '{val}' in column '{col}'"


@pytest.mark.kg
class TestGeneSetCompareIntegration:
    def test_overlapping_sets(self, conn):
        set_a = [KNOWN_EXPRESSED_GENES[0], KNOWN_GENE]
        set_b = [KNOWN_EXPRESSED_GENES[1], KNOWN_GENE]

        result = gene_set_compare(set_a=set_a, set_b=set_b, conn=conn)

        assert KNOWN_GENE in result["overlap"].index
        assert KNOWN_EXPRESSED_GENES[0] in result["only_a"].index
        assert KNOWN_EXPRESSED_GENES[1] in result["only_b"].index
        assert isinstance(result["shared_groups"], list)
        assert isinstance(result["divergent_groups"], list)
        assert len(result["summary_per_group"]) > 0


@pytest.mark.kg
class TestGeneResponseProfileTestedNotResponded:
    """Validate groups_tested_not_responded with N-stress marker genes."""

    # N-stress markers known to respond only to nitrogen
    N_STRESS_GENES = ["PMM0965"]  # ureA

    def test_urea_tested_not_responded_for_non_nitrogen(self, conn):
        """ureA should be in groups_tested_not_responded for non-nitrogen
        treatment groups with full-coverage scope, not in groups_not_known."""
        result = api.gene_response_profile(
            locus_tags=self.N_STRESS_GENES, conn=conn,
        )
        assert len(result["results"]) >= 1
        gene = result["results"][0]

        # ureA should respond to nitrogen
        assert "nitrogen_stress" in gene["groups_responded"]

        # Non-nitrogen groups with full-coverage scope should be tested_not_responded
        tested_nr = gene.get("groups_tested_not_responded", [])
        not_known = gene.get("groups_not_known", [])

        # At least some non-nitrogen groups should move to tested_not_responded
        assert len(tested_nr) > 0, (
            f"Expected some groups in groups_tested_not_responded, "
            f"got groups_not_known={not_known}"
        )

        # groups_tested_not_responded should not overlap with groups_not_known
        overlap = set(tested_nr) & set(not_known)
        assert not overlap, f"Overlap between tested_not_responded and not_known: {overlap}"

    def test_groups_not_responded_unchanged(self, conn):
        """Genes with all_detected_genes experiments that have not_significant
        edges should remain in groups_not_responded (unchanged)."""
        result = api.gene_response_profile(
            locus_tags=["PMM0370"], conn=conn,  # cynA — responds broadly
        )
        gene = result["results"][0]

        # groups_not_responded should only contain groups where edges exist
        # (not inferred — those go to tested_not_responded)
        for gk in gene["groups_not_responded"]:
            assert gk in gene["response_summary"], (
                f"Group {gk} in groups_not_responded but not in response_summary"
            )
