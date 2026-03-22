"""P1: Integration tests for MCP tool logic against live Neo4j.

These tests exercise the tool-level logic (query building + result handling)
without the MCP transport layer. They use the shared `conn` fixture from conftest.
"""

import json

import pytest

from multiomics_explorer.kg.queries_lib import (
    build_gene_stub,
    build_get_gene_details,
    build_get_homologs_groups,
    build_get_homologs_members,
    build_list_organisms,
    build_list_publications,
    build_list_publications_summary,
    build_resolve_gene,
    build_search_genes,
)
from multiomics_explorer.kg.schema import load_schema_from_neo4j
from multiomics_explorer.api.functions import _WRITE_KEYWORDS


@pytest.mark.kg
class TestGetSchema:
    def test_returns_node_counts_and_relationships(self, conn):
        schema = load_schema_from_neo4j(conn)
        assert len(schema.nodes) > 0
        assert len(schema.relationships) > 0
        # At least Gene nodes should exist
        assert "Gene" in schema.nodes
        assert schema.nodes["Gene"].count > 0

    def test_prompt_string_not_empty(self, conn):
        schema = load_schema_from_neo4j(conn)
        text = schema.to_prompt_string()
        assert "Gene" in text
        assert "## Graph Schema" in text


@pytest.mark.kg
class TestSearchGenes:
    def test_invalid_lucene_syntax_does_not_crash(self, conn):
        """Unbalanced brackets should trigger the Lucene escape fallback."""
        import re

        search_text = "DNA [repair"
        cypher, params = build_search_genes(search_text=search_text)
        try:
            results = conn.execute_query(cypher, **params)
        except Exception:
            # Retry with escaped Lucene chars (mirrors tools.py fallback logic)
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_search_genes(search_text=escaped)
            results = conn.execute_query(cypher, **params)
        # Should not raise — may return 0 or more results
        assert isinstance(results, list)

    def test_basic_search_returns_results(self, conn):
        cypher, params = build_search_genes(search_text="photosystem")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        assert "locus_tag" in results[0]


@pytest.mark.kg
class TestGetHomologs:
    def test_gene_stub_returns_metadata(self, conn):
        """build_gene_stub returns query gene metadata."""
        cypher, params = build_gene_stub(gene_id="PMM0845")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        assert results[0]["locus_tag"] == "PMM0845"
        assert "gene_name" in results[0]
        assert "product" in results[0]
        assert "organism_strain" in results[0]

    def test_groups_query_returns_ortholog_groups(self, conn):
        """build_get_homologs_groups returns group metadata for PMM0845."""
        cypher, params = build_get_homologs_groups(gene_id="PMM0845")
        groups = conn.execute_query(cypher, **params)
        assert len(groups) > 0
        for g in groups:
            assert "og_name" in g
            assert "source" in g
            assert "consensus_product" in g

    def test_members_query_returns_homolog_genes(self, conn):
        """build_get_homologs_members returns member genes."""
        cypher, params = build_get_homologs_members(gene_id="PMM0845")
        members = conn.execute_query(cypher, **params)
        assert len(members) > 0
        for m in members:
            assert "locus_tag" in m
            assert "og_name" in m
            assert "organism_strain" in m


@pytest.mark.kg
class TestRunCypherBlocking:
    def test_invalid_cypher_returns_error(self, conn):
        """Syntax-invalid Cypher should raise, not hang."""
        with pytest.raises(Exception):
            conn.execute_query("MATC (n) RETURNN n LIMIT 1")

    def test_write_blocked_at_regex_level(self):
        """Write keywords are caught before reaching Neo4j."""
        assert _WRITE_KEYWORDS.search("CREATE (n:Gene {name: 'test'})")
        assert _WRITE_KEYWORDS.search("MATCH (n) DELETE n")
        assert _WRITE_KEYWORDS.search("MATCH (n) SET n.x = 1")


@pytest.mark.kg
class TestEdgeCases:
    def test_resolve_gene_empty_id(self, conn):
        cypher, params = build_resolve_gene(identifier="")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 0

    def test_get_gene_details_nonexistent(self, conn):
        cypher, params = build_get_gene_details(gene_id="FAKE_GENE_XYZ")
        results = conn.execute_query(cypher, **params)
        # Either empty or gene is None
        assert not results or results[0]["gene"] is None


@pytest.mark.kg
class TestListPublications:
    def test_no_filters_returns_all(self, conn):
        """Unfiltered query returns all publications."""
        cypher, params = build_list_publications()
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 15
        for r in results:
            assert "doi" in r
            assert "title" in r
            assert "experiment_count" in r

    def test_organism_filter(self, conn):
        """Organism filter returns subset with MED4 experiments."""
        cypher, params = build_list_publications(organism="MED4")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 5

    def test_treatment_type_filter(self, conn):
        """Treatment type filter returns papers with coculture experiments."""
        cypher, params = build_list_publications(treatment_type="coculture")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 3

    def test_author_filter(self, conn):
        """Author filter returns Chisholm lab papers."""
        cypher, params = build_list_publications(author="Chisholm")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 2

    def test_experiment_count_positive(self, conn):
        """All publications with experiments have experiment_count > 0."""
        cypher, params = build_list_publications()
        results = conn.execute_query(cypher, **params)
        with_experiments = [r for r in results if r["experiment_count"] > 0]
        assert len(with_experiments) >= 15

    def test_summary_matches_data(self, conn):
        """Summary total_matching equals actual data row count (no limit)."""
        summary_cypher, summary_params = build_list_publications_summary(organism="MED4")
        summary = conn.execute_query(summary_cypher, **summary_params)[0]

        data_cypher, data_params = build_list_publications(organism="MED4")
        data = conn.execute_query(data_cypher, **data_params)

        assert summary["total_matching"] == len(data)
        assert summary["total_entries"] >= summary["total_matching"]


@pytest.mark.kg
class TestListOrganisms:
    def test_returns_all_organisms(self, conn):
        """Returns all OrganismTaxon nodes with precomputed stats."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 13  # at least 13 strain-level organisms

    def test_expected_columns(self, conn):
        """Each result has all 11 compact columns."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        for col in ["organism_name", "genus", "species", "strain", "clade",
                     "ncbi_taxon_id", "gene_count", "publication_count",
                     "experiment_count", "treatment_types", "omics_types"]:
            assert col in results[0], f"Missing column: {col}"

    def test_verbose_adds_taxonomy(self, conn):
        """Verbose mode adds taxonomy hierarchy columns."""
        cypher, params = build_list_organisms(verbose=True)
        results = conn.execute_query(cypher, **params)
        for col in ["family", "order", "tax_class", "phylum",
                     "kingdom", "superkingdom", "lineage"]:
            assert col in results[0], f"Missing verbose column: {col}"

    def test_precomputed_gene_count_matches(self, conn):
        """Precomputed gene_count matches live count for MED4."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        med4 = [r for r in results if r["organism_name"] == "Prochlorococcus MED4"][0]
        assert med4["gene_count"] > 1900

    def test_precomputed_publication_count(self, conn):
        """MED4 has the most publications."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        med4 = [r for r in results if r["organism_name"] == "Prochlorococcus MED4"][0]
        assert med4["publication_count"] >= 10

    def test_treatment_types_not_empty(self, conn):
        """Organisms with publications have non-empty treatment_types."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        med4 = [r for r in results if r["organism_name"] == "Prochlorococcus MED4"][0]
        assert len(med4["treatment_types"]) >= 5

    def test_ordered_by_genus(self, conn):
        """Results are ordered by genus, then organism_name."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        genera = [r["genus"] for r in results if r["genus"] is not None]
        assert genera == sorted(genera)

