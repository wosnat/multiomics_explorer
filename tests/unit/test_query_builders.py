"""Unit tests for query builder functions — no Neo4j needed.

Verifies Cypher structure and parameter correctness.
"""

from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
    build_find_gene,
    build_resolve_gene,
    build_get_gene_details_homologs,
    build_get_gene_details_main,
    build_get_homologs,
    build_homolog_expression,
    build_query_expression,
)


class TestBuildResolveGene:
    def test_basic(self):
        cypher, params = build_resolve_gene(identifier="PMM0001")
        assert "MATCH (g:Gene)" in cypher
        assert params["identifier"] == "PMM0001"
        assert params["organism"] is None

    def test_with_organism(self):
        cypher, params = build_resolve_gene(identifier="dnaN", organism="MED4")
        assert params["organism"] == "MED4"
        assert "toLower($organism)" in cypher
        assert "toLower(g.organism_strain)" in cypher

    def test_organism_case_insensitive(self):
        """Organism filter uses toLower for case-insensitive matching."""
        cypher, params = build_resolve_gene(identifier="recF", organism="prochlorococcus")
        assert params["organism"] == "prochlorococcus"
        assert "toLower($organism)" in cypher

    def test_organism_multi_word_partial(self):
        """Multi-word organism like 'Alteromonas EZ55' uses ALL/split for word matching."""
        cypher, params = build_resolve_gene(identifier="recF", organism="Alteromonas EZ55")
        assert params["organism"] == "Alteromonas EZ55"
        assert "ALL(word IN split(" in cypher

    def test_returns_expected_columns(self):
        cypher, _ = build_resolve_gene(identifier="x")
        for col in ["locus_tag", "gene_name", "product", "organism_strain"]:
            assert col in cypher

    def test_matches_all_identifiers(self):
        """Query checks all_identifiers list for alternate IDs (old locus tags, RefSeq IDs)."""
        cypher, _ = build_resolve_gene(identifier="x")
        assert "$identifier IN g.all_identifiers" in cypher

    def test_order_by_locus_tag(self):
        cypher, _ = build_resolve_gene(identifier="x")
        assert "ORDER BY g.locus_tag" in cypher


class TestBuildFindGene:
    def test_basic(self):
        cypher, params = build_find_gene(search_text="DNA repair")
        assert "fulltext" in cypher.lower() or "geneFullText" in cypher
        assert params["search_text"] == "DNA repair"

    def test_min_quality(self):
        _, params = build_find_gene(search_text="x", min_quality=2)
        assert params["min_quality"] == 2

    def test_organism_case_insensitive(self):
        """Organism filter uses toLower for case-insensitive matching."""
        cypher, params = build_find_gene(search_text="x", organism="prochlorococcus")
        assert params["organism"] == "prochlorococcus"
        assert "toLower($organism)" in cypher

    def test_organism_multi_word(self):
        """Multi-word organism uses ALL/split for word matching."""
        cypher, _ = build_find_gene(search_text="x", organism="Alteromonas EZ55")
        assert "ALL(word IN split(" in cypher


class TestBuildGetGeneDetails:
    def test_main_query(self):
        cypher, params = build_get_gene_details_main(gene_id="PMM0001")
        assert params["lt"] == "PMM0001"
        assert "Gene_encodes_protein" in cypher
        assert "Gene_belongs_to_organism" in cypher

    def test_homologs_query(self):
        cypher, params = build_get_gene_details_homologs(gene_id="PMM0001")
        assert params["lt"] == "PMM0001"
        assert "Gene_is_homolog_of_gene" in cypher


class TestBuildQueryExpression:
    def test_by_gene(self):
        cypher, params = build_query_expression(gene_id="PMM0845")
        assert params["gene_id"] == "PMM0845"
        assert "g.locus_tag = $gene_id" in cypher

    def test_direction_lowercased(self):
        _, params = build_query_expression(gene_id="x", direction="UP")
        assert params["dir"] == "up"

    def test_includes_orthologs(self):
        cypher, _ = build_query_expression(gene_id="x", include_orthologs=True)
        assert "ortholog" in cypher.lower()

    def test_excludes_orthologs_by_default(self):
        cypher, _ = build_query_expression(gene_id="x")
        assert "ortholog" not in cypher.lower()

    def test_min_log2fc(self):
        cypher, params = build_query_expression(gene_id="x", min_log2fc=1.5)
        assert params["min_fc"] == 1.5
        assert "abs(r.log2_fold_change) >= $min_fc" in cypher

    def test_max_pvalue(self):
        cypher, params = build_query_expression(gene_id="x", max_pvalue=0.05)
        assert params["max_pv"] == 0.05


class TestBuildCompareConditions:
    def test_by_gene_ids(self):
        cypher, params = build_compare_conditions(gene_ids=["PMM0001", "PMM0002"])
        assert params["gene_ids"] == ["PMM0001", "PMM0002"]
        assert "g.locus_tag IN $gene_ids" in cypher

    def test_by_organisms(self):
        cypher, params = build_compare_conditions(organisms=["MED4"])
        assert params["organisms"] == ["MED4"]


class TestBuildGetHomologs:
    def test_basic(self):
        cypher, params = build_get_homologs(gene_id="PMM0845")
        assert params["lt"] == "PMM0845"
        assert "Gene_is_homolog_of_gene" in cypher

    def test_returns_expected_columns(self):
        cypher, _ = build_get_homologs(gene_id="x")
        for col in ["locus_tag", "organism_strain", "distance"]:
            assert col in cypher


class TestBuildHomologExpression:
    def test_basic(self):
        cypher, params = build_homolog_expression(gene_ids=["PMM0001", "PMM0002"])
        assert params["ids"] == ["PMM0001", "PMM0002"]
        assert "g.locus_tag IN $ids" in cypher
