"""P2: Parameter edge-case tests against live Neo4j.

Tests boundary conditions, empty inputs, filter combinations,
summary/verbose interactions, and consistency checks that are
missing from the main integration and contract test suites.

Marked with @pytest.mark.kg — auto-skips if Neo4j is unavailable.
"""

import pytest

from multiomics_explorer.api import functions as api


KNOWN_GENE = "PMM0001"
KNOWN_GROUP = "cyanorak:CK_00000570"


# ---------------------------------------------------------------------------
# API-level input validation
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestAPIInputValidation:
    """Verify that the API layer raises ValueError for bad inputs
    rather than letting them reach Neo4j."""

    def test_genes_by_function_empty(self, conn):
        with pytest.raises(ValueError, match="search_text"):
            api.genes_by_function("", conn=conn)

    def test_genes_by_function_whitespace(self, conn):
        with pytest.raises(ValueError, match="search_text"):
            api.genes_by_function("   ", conn=conn)

    def test_gene_overview_empty_locus_tags(self, conn):
        with pytest.raises(ValueError, match="locus_tags"):
            api.gene_overview([], conn=conn)

    def test_gene_homologs_empty_locus_tags(self, conn):
        with pytest.raises(ValueError, match="locus_tags"):
            api.gene_homologs([], conn=conn)

    def test_search_ontology_invalid_ontology(self, conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.search_ontology("transport", "invalid_ont", conn=conn)

    def test_genes_by_ontology_invalid_ontology(self, conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.genes_by_ontology(["go:0006260"], "invalid_ont", conn=conn)

    def test_run_cypher_empty_query(self, conn):
        with pytest.raises(ValueError, match="query"):
            api.run_cypher("", conn=conn)

    def test_run_cypher_whitespace_query(self, conn):
        with pytest.raises(ValueError, match="query"):
            api.run_cypher("   ", conn=conn)

    def test_resolve_gene_empty(self, conn):
        with pytest.raises(ValueError, match="identifier"):
            api.resolve_gene("", conn=conn)

    def test_gene_details_empty_locus_tags(self, conn):
        with pytest.raises(ValueError, match="locus_tags"):
            api.gene_details([], conn=conn)

    def test_gene_ontology_terms_empty_locus_tags(self, conn):
        with pytest.raises(ValueError, match="locus_tags"):
            api.gene_ontology_terms([], conn=conn)

    def test_genes_by_ontology_empty_term_ids(self, conn):
        with pytest.raises(ValueError, match="term_ids"):
            api.genes_by_ontology([], "go_bp", conn=conn)

    def test_genes_by_homolog_group_empty(self, conn):
        with pytest.raises(ValueError, match="group_ids"):
            api.genes_by_homolog_group([], conn=conn)

    def test_diff_expr_by_ortholog_empty(self, conn):
        with pytest.raises(ValueError, match="group_ids"):
            api.differential_expression_by_ortholog([], conn=conn)

    def test_search_homolog_groups_empty(self, conn):
        with pytest.raises(ValueError, match="search_text"):
            api.search_homolog_groups("", conn=conn)

    def test_diff_expr_by_gene_no_filters(self, conn):
        with pytest.raises(ValueError, match="at least one"):
            api.differential_expression_by_gene(conn=conn)

    def test_diff_expr_by_gene_invalid_direction(self, conn):
        with pytest.raises(ValueError, match="Invalid direction"):
            api.differential_expression_by_gene(
                organism="MED4", direction="sideways", conn=conn,
            )

    def test_search_homolog_groups_invalid_source(self, conn):
        with pytest.raises(ValueError, match="Invalid source"):
            api.search_homolog_groups("kinase", source="invalid", conn=conn)

    def test_gene_ontology_terms_invalid_ontology(self, conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.gene_ontology_terms(["PMM0001"], ontology="invalid_ont", conn=conn)


# ---------------------------------------------------------------------------
# resolve_gene edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestResolveGeneEdgeCases:
    def test_empty_identifier_raises(self, conn):
        with pytest.raises(ValueError, match="identifier"):
            api.resolve_gene("", conn=conn)

    def test_whitespace_identifier_raises(self, conn):
        with pytest.raises(ValueError, match="identifier"):
            api.resolve_gene("   ", conn=conn)

    def test_nonexistent_organism_returns_empty(self, conn):
        result = api.resolve_gene("dnaN", organism="ZZZZZ_FAKE", conn=conn)
        assert result["total_matching"] == 0
        assert result["results"] == []

    def test_limit_1(self, conn):
        result = api.resolve_gene("dnaN", limit=1, conn=conn)
        assert result["returned"] == 1
        assert result["total_matching"] >= 2
        assert result["truncated"] is True

    def test_by_organism_populated(self, conn):
        result = api.resolve_gene("dnaN", conn=conn)
        assert len(result["by_organism"]) >= 2
        total = sum(b["count"] for b in result["by_organism"])
        assert total == result["total_matching"]


# ---------------------------------------------------------------------------
# genes_by_function edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGenesByFunctionEdgeCases:
    def test_empty_search_raises(self, conn):
        """Empty search_text raises ValueError at API level."""
        with pytest.raises(ValueError, match="search_text"):
            api.genes_by_function("", conn=conn)

    def test_summary_mode(self, conn):
        result = api.genes_by_function(
            "photosystem", summary=True, conn=conn,
        )
        assert result["total_matching"] >= 1
        assert result["results"] == []
        assert result["returned"] == 0
        assert len(result["by_organism"]) >= 1
        assert len(result["by_category"]) >= 1

    def test_verbose_adds_fields(self, conn):
        result = api.genes_by_function(
            "photosystem", verbose=True, limit=1, conn=conn,
        )
        row = result["results"][0]
        assert "function_description" in row
        assert "gene_summary" in row

    def test_organism_nonexistent_returns_empty(self, conn):
        result = api.genes_by_function(
            "photosystem", organism="ZZZZZ_FAKE", conn=conn,
        )
        assert result["total_matching"] == 0

    def test_min_quality_boundaries(self, conn):
        """min_quality=3 returns fewer or equal results than min_quality=0."""
        q0 = api.genes_by_function(
            "polymerase", min_quality=0, summary=True, conn=conn,
        )
        q3 = api.genes_by_function(
            "polymerase", min_quality=3, summary=True, conn=conn,
        )
        assert q0["total_matching"] >= q3["total_matching"]

    def test_category_filter(self, conn):
        """Category filter restricts results to that category."""
        result = api.genes_by_function(
            "reaction", category="Photosynthesis", conn=conn,
        )
        # All results should be Photosynthesis if category filter works
        for row in result["results"]:
            assert row["gene_category"] == "Photosynthesis"

    def test_score_fields_present(self, conn):
        result = api.genes_by_function("photosystem", conn=conn)
        assert result["score_max"] is not None
        assert result["score_median"] is not None
        assert result["score_max"] >= result["score_median"]

    def test_summary_consistency(self, conn):
        """Summary total_matching matches detail row count."""
        summary = api.genes_by_function(
            "chaperone", summary=True, conn=conn,
        )
        detail = api.genes_by_function(
            "chaperone", limit=500, conn=conn,
        )
        assert summary["total_matching"] == detail["total_matching"]


# ---------------------------------------------------------------------------
# gene_details edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneDetailsEdgeCases:
    def test_not_found(self, conn):
        result = api.gene_details(["FAKE_XYZ"], conn=conn)
        assert "FAKE_XYZ" in result["not_found"]
        assert result["total_matching"] == 0

    def test_mixed_found_not_found(self, conn):
        result = api.gene_details([KNOWN_GENE, "FAKE_XYZ"], conn=conn)
        assert result["total_matching"] == 1
        assert "FAKE_XYZ" in result["not_found"]
        assert result["results"][0]["locus_tag"] == KNOWN_GENE

    def test_limit_1(self, conn):
        result = api.gene_details([KNOWN_GENE], limit=1, conn=conn)
        assert result["returned"] == 1

    def test_summary_mode(self, conn):
        result = api.gene_details([KNOWN_GENE], summary=True, conn=conn)
        assert result["total_matching"] == 1
        assert result["results"] == []
        assert result["returned"] == 0


# ---------------------------------------------------------------------------
# gene_homologs edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneHomologsEdgeCases:
    def test_verbose_adds_fields(self, conn):
        result = api.gene_homologs(
            [KNOWN_GENE], verbose=True, limit=1, conn=conn,
        )
        if result["results"]:
            row = result["results"][0]
            for key in ("member_count", "organism_count", "genera",
                        "has_cross_genus_members", "description",
                        "functional_description"):
                assert key in row

    def test_taxonomic_level_filter(self, conn):
        """taxonomic_level filter restricts results."""
        result = api.gene_homologs(
            [KNOWN_GENE], taxonomic_level="curated", conn=conn,
        )
        for row in result["results"]:
            assert row["taxonomic_level"] == "curated"

    def test_max_specificity_rank_filter(self, conn):
        """max_specificity_rank caps group breadth."""
        all_groups = api.gene_homologs([KNOWN_GENE], limit=100, conn=conn)
        rank0 = api.gene_homologs(
            [KNOWN_GENE], max_specificity_rank=0, limit=100, conn=conn,
        )
        assert rank0["total_matching"] <= all_groups["total_matching"]
        for row in rank0["results"]:
            assert row["specificity_rank"] <= 0

    def test_summary_mode(self, conn):
        result = api.gene_homologs([KNOWN_GENE], summary=True, conn=conn)
        assert result["total_matching"] >= 1
        assert result["results"] == []
        assert result["returned"] == 0
        assert len(result["by_source"]) >= 1


# ---------------------------------------------------------------------------
# search_ontology edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestSearchOntologyEdgeCases:
    def test_summary_mode(self, conn):
        result = api.search_ontology(
            "transport", "go_bp", summary=True, conn=conn,
        )
        assert result["total_matching"] >= 1
        assert result["results"] == []
        assert result["returned"] == 0

    def test_limit_1(self, conn):
        result = api.search_ontology(
            "transport", "go_bp", limit=1, conn=conn,
        )
        assert result["returned"] == 1
        assert result["total_matching"] >= 2
        assert result["truncated"] is True


# ---------------------------------------------------------------------------
# genes_by_ontology edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGenesByOntologyEdgeCases:
    def test_nonexistent_term_returns_empty(self, conn):
        result = api.genes_by_ontology(
            ["go:9999999"], "go_bp", conn=conn,
        )
        assert result["total_matching"] == 0

    def test_organism_filter(self, conn):
        result = api.genes_by_ontology(
            ["go:0006260"], "go_bp", organism="MED4", conn=conn,
        )
        for row in result["results"]:
            assert "MED4" in row["organism_name"]

    def test_by_term_populated(self, conn):
        result = api.genes_by_ontology(
            ["go:0006260", "go:0006139"], "go_bp", summary=True, conn=conn,
        )
        assert len(result["by_term"]) >= 1


# ---------------------------------------------------------------------------
# gene_ontology_terms edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneOntologyTermsEdgeCases:
    def test_no_terms_field(self, conn):
        """Gene with no terms for a specific ontology appears in no_terms."""
        # Use a gene unlikely to have Pfam annotations
        result = api.gene_ontology_terms(
            locus_tags=["PMT9312_0342"], ontology="pfam", conn=conn,
        )
        if result["total_matching"] == 0:
            assert "PMT9312_0342" in result["no_terms"]

    def test_all_ontology_mode(self, conn):
        result = api.gene_ontology_terms(
            locus_tags=[KNOWN_GENE], ontology=None, conn=conn,
        )
        assert result["total_matching"] >= 1
        # Multiple ontology types in results
        ontology_types = {r.get("ontology_type") for r in result["results"]}
        assert len(ontology_types) >= 2

    def test_summary_mode(self, conn):
        result = api.gene_ontology_terms(
            locus_tags=[KNOWN_GENE], ontology="go_bp", summary=True, conn=conn,
        )
        assert result["total_matching"] >= 1
        assert result["results"] == []
        assert result["returned"] == 0
        assert len(result["by_ontology"]) >= 1


# ---------------------------------------------------------------------------
# list_publications edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestListPublicationsEdgeCases:
    def test_search_text(self, conn):
        """search_text filters publications by content."""
        result = api.list_publications(
            search_text="light", conn=conn,
        )
        assert result["total_matching"] >= 1
        for row in result["results"]:
            assert "score" in row

    def test_combined_filters(self, conn):
        """organism + treatment_type filters stack."""
        org_only = api.list_publications(organism="MED4", conn=conn)
        combined = api.list_publications(
            organism="MED4", treatment_type="coculture", conn=conn,
        )
        assert combined["total_matching"] <= org_only["total_matching"]

    def test_verbose_result_has_abstract(self, conn):
        result = api.list_publications(verbose=True, limit=1, conn=conn)
        row = result["results"][0]
        assert "abstract" in row


# ---------------------------------------------------------------------------
# list_experiments edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestListExperimentsEdgeCases:
    def test_table_scope_filter(self, conn):
        """table_scope filter restricts experiments."""
        result = api.list_experiments(
            table_scope=["significant_only"], conn=conn,
        )
        for row in result["results"]:
            assert row["table_scope"] == "significant_only"

    def test_combined_organism_treatment(self, conn):
        """organism + treatment_type filters stack."""
        result = api.list_experiments(
            organism="MED4", treatment_type=["coculture"],
            conn=conn,
        )
        assert result["total_matching"] >= 1
        for row in result["results"]:
            assert "MED4" in row["organism_name"] or (
                row.get("coculture_partner") and "MED4" in row.get("coculture_partner", "")
            )
            assert "coculture" in row["treatment_type"]

    def test_verbose_adds_treatment_details(self, conn):
        result = api.list_experiments(verbose=True, limit=1, conn=conn)
        row = result["results"][0]
        for key in ("publication_title", "treatment", "control"):
            assert key in row

    def test_by_table_scope_populated(self, conn):
        result = api.list_experiments(summary=True, conn=conn)
        assert len(result["by_table_scope"]) >= 1
        for b in result["by_table_scope"]:
            assert "table_scope" in b
            assert "count" in b


# ---------------------------------------------------------------------------
# differential_expression_by_gene edge cases
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestDiffExprByGeneEdgeCases:
    def test_direction_up(self, conn):
        """direction='up' returns only upregulated rows."""
        result = api.differential_expression_by_gene(
            organism="MED4", direction="up", limit=5, conn=conn,
        )
        for row in result["results"]:
            assert row["expression_status"] == "significant_up"
        rbs = result["rows_by_status"]
        assert rbs["significant_down"] == 0
        assert rbs["not_significant"] == 0

    def test_direction_down(self, conn):
        """direction='down' returns only downregulated rows."""
        result = api.differential_expression_by_gene(
            organism="MED4", direction="down", limit=5, conn=conn,
        )
        for row in result["results"]:
            assert row["expression_status"] == "significant_down"
        rbs = result["rows_by_status"]
        assert rbs["significant_up"] == 0
        assert rbs["not_significant"] == 0

    def test_experiment_ids_filter(self, conn):
        """experiment_ids restricts results to those experiments."""
        # First get a valid experiment_id
        full = api.differential_expression_by_gene(
            locus_tags=[KNOWN_GENE], limit=1, conn=conn,
        )
        if not full["results"]:
            pytest.skip("No expression data for known gene")
        exp_id = full["results"][0]["experiment_id"]

        filtered = api.differential_expression_by_gene(
            locus_tags=[KNOWN_GENE], experiment_ids=[exp_id], conn=conn,
        )
        for row in filtered["results"]:
            assert row["experiment_id"] == exp_id

    def test_verbose_adds_product_and_experiment_name(self, conn):
        result = api.differential_expression_by_gene(
            locus_tags=[KNOWN_GENE], verbose=True, limit=1, conn=conn,
        )
        if result["results"]:
            row = result["results"][0]
            for key in ("product", "experiment_name", "treatment",
                        "gene_category", "omics_type"):
                assert key in row

    def test_rows_by_status_sums(self, conn):
        """rows_by_status values sum to total_matching."""
        result = api.differential_expression_by_gene(
            locus_tags=[KNOWN_GENE], summary=True, conn=conn,
        )
        rbs = result["rows_by_status"]
        assert sum(rbs.values()) == result["total_matching"]

    def test_experiments_field_populated(self, conn):
        """experiments list has entries with nested data."""
        result = api.differential_expression_by_gene(
            locus_tags=[KNOWN_GENE], summary=True, conn=conn,
        )
        assert result["experiment_count"] >= 1
        assert result["experiment_count"] == len(result["experiments"])
        exp = result["experiments"][0]
        assert "experiment_id" in exp
        assert "rows_by_status" in exp
        assert "matching_genes" in exp

    def test_not_found_gene(self, conn):
        """Fake gene mixed with real gene: fake appears in not_found."""
        result = api.differential_expression_by_gene(
            locus_tags=[KNOWN_GENE, "FAKE_GENE_XYZ"], conn=conn,
        )
        assert "FAKE_GENE_XYZ" in result["not_found"]

    def test_by_table_scope_populated(self, conn):
        """by_table_scope field is populated."""
        result = api.differential_expression_by_gene(
            organism="MED4", summary=True, conn=conn,
        )
        assert len(result["by_table_scope"]) >= 1
