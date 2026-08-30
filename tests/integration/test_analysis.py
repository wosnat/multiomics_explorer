"""Integration tests for analysis utilities — requires Neo4j."""

import pytest

from multiomics_explorer.analysis import (
    gene_set_compare,
    response_matrix,
    to_dataframe,
)

# De-exposed from the public package API in commit 8d85962 (Python API
# simplification); still callable at the .frames submodule for tests/internal use.
from multiomics_explorer.analysis.frames import (
    experiments_to_dataframe,
    profile_summary_to_dataframe,
)
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
        assert "nitrogen" in gene["groups_responded"]

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


@pytest.mark.kg
class TestToDataFrameIntegration:
    """Round-trip: API call → to_dataframe → verify CSV-safe."""

    def _assert_csv_safe(self, df):
        """Verify no column contains list or dict values."""
        for col in df.columns:
            for val in df[col].dropna():
                assert not isinstance(val, (list, dict)), (
                    f"Column '{col}' has non-scalar value: {type(val).__name__}"
                )

    def test_resolve_gene(self, conn):
        result = api.resolve_gene("PMM0370", conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_genes_by_function(self, conn):
        result = api.genes_by_function("nitrogen", conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_gene_overview(self, conn):
        result = api.gene_overview(locus_tags=["PMM0370", "PMM0920"], conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_list_organisms(self, conn):
        result = api.list_organisms(conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_list_publications(self, conn):
        result = api.list_publications(conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_list_experiments(self, conn):
        result = api.list_experiments(conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_gene_response_profile(self, conn):
        result = api.gene_response_profile(
            locus_tags=["PMM0370", "PMM0920"], conn=conn,
        )
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)
        assert "response_summary" not in df.columns

    def test_differential_expression_by_gene(self, conn):
        result = api.differential_expression_by_gene(
            organism="MED4", conn=conn,
        )
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_search_ontology(self, conn):
        result = api.search_ontology("nitrogen", ontology="go_bp", conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)


@pytest.mark.kg
class TestProfileSummaryIntegration:
    def test_round_trip(self, conn):
        result = api.gene_response_profile(
            locus_tags=["PMM0370", "PMM0920"], conn=conn,
        )
        df = profile_summary_to_dataframe(result)
        assert len(df) >= 1
        assert "group" in df.columns
        assert "experiments_up" in df.columns
        for col in df.columns:
            for val in df[col].dropna():
                assert not isinstance(val, (list, dict))


@pytest.mark.kg
class TestExperimentsToDataFrameIntegration:
    def test_round_trip(self, conn):
        result = api.list_experiments(conn=conn)
        df = experiments_to_dataframe(result)
        assert len(df) >= 1
        assert "experiment_id" in df.columns
        for col in df.columns:
            for val in df[col].dropna():
                assert not isinstance(val, (list, dict))


@pytest.mark.kg
class TestEnrichmentIncludeNonsignificantIntegration:
    """llm-review 2b.2 Task 2 (+ follow-up fix), against a real KG:
    `include_nonsignificant` threads from `api.pathway_enrichment` through
    `result.to_envelope()`, filtering rows and narrowing `total_matching`
    to the pageable (significant) subset — while `n_significant` and the
    aggregate breakdowns stay unaffected — same contract the unit tests
    pin with mocks, exercised here over real DE + ontology data.
    """

    @staticmethod
    def _med4_nitrogen_experiment_id(conn):
        experiments = api.list_experiments(
            organism="MED4", search_text="nitrogen", limit=5, conn=conn,
        )
        if not experiments["results"]:
            pytest.skip("No MED4 nitrogen experiment in KG")
        return experiments["results"][0]["experiment_id"]

    def test_false_returns_fewer_or_equal_rows_narrower_total(self, conn):
        exp_id = self._med4_nitrogen_experiment_id(conn)
        common = dict(
            organism="MED4", experiment_ids=[exp_id],
            ontology="kegg", level=1, conn=conn,
        )
        full = api.pathway_enrichment(**common, include_nonsignificant=True)
        sig_only = api.pathway_enrichment(**common, include_nonsignificant=False)

        env_full = full.to_envelope(limit=None)
        env_sig = sig_only.to_envelope(limit=None)

        assert env_full["n_significant"] == env_sig["n_significant"]
        # total_matching narrows to the pageable (significant) subset —
        # controller ruling, llm-review 2b.2 follow-up.
        assert env_full["total_matching"] >= env_sig["total_matching"]
        assert env_sig["total_matching"] == env_sig["n_significant"]
        assert env_sig["returned"] <= env_full["returned"]
        assert env_sig["returned"] == env_sig["n_significant"]
        # An empty results page must never pair with a nonzero total_matching
        # (the repo-wide empty-layer invariant).
        assert (len(env_sig["results"]) == 0) == (env_sig["total_matching"] == 0)
        # Rows returned under significant-only are exactly the significant subset.
        assert all(
            row["p_adjust"] < sig_only.params["pvalue_cutoff"]
            for row in env_sig["results"]
        )
        # by_experiment / by_omics_type aggregates are unaffected by the filter.
        assert env_full["by_experiment"] == env_sig["by_experiment"]
        assert env_full["by_omics_type"] == env_sig["by_omics_type"]
        assert env_full["clusters_skipped"] == env_sig["clusters_skipped"]
