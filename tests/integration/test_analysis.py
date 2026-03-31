"""Integration tests for analysis utilities — requires Neo4j."""

import pytest

from multiomics_explorer.analysis import gene_set_compare, response_matrix

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
