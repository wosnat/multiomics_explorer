import pytest
from tests.integration.edge_cases import fixtures as fx


@pytest.mark.kg
class TestFixtureGuards:
    """Assert each fixture still has its degenerate property. A failure here
    means a KG rebuild changed the fixture's nature — re-pin it."""

    def test_genome_only_has_no_experiments(self, conn):
        rows = conn.execute_query(
            "MATCH (o:OrganismTaxon {preferred_name:$n}) "
            "RETURN coalesce(o.experiment_count,0) AS e, "
            "coalesce(o.gene_count,0) AS g",
            n=fx.GENOME_ONLY_ORGANISM,
        )
        assert rows, f"{fx.GENOME_ONLY_ORGANISM} no longer in KG"
        assert rows[0]["e"] == 0
        assert rows[0]["g"] > 0

    def test_expression_layer_empty_has_experiments_no_de(self, conn):
        # Degenerate property: has Experiment nodes but ZERO
        # Changes_expression_of edges. Assert that directly (not via an
        # omics-label proxy) so the guard is tied to the actual invariant.
        rows = conn.execute_query(
            "MATCH (o:OrganismTaxon {preferred_name:$n}) "
            "RETURN coalesce(o.experiment_count,0) AS e, "
            "EXISTS { (e:Experiment {organism_name:$n})"
            "-[:Changes_expression_of]->() } AS has_de",
            n=fx.EXPRESSION_LAYER_EMPTY_ORGANISM,
        )
        assert rows, f"{fx.EXPRESSION_LAYER_EMPTY_ORGANISM} no longer in KG"
        assert rows[0]["e"] > 0
        assert rows[0]["has_de"] is False

    def test_gene_no_de_has_no_expression_edge(self, conn):
        rows = conn.execute_query(
            "MATCH (g:Gene {locus_tag:$lt}) "
            "RETURN EXISTS { (:Experiment)-[:Changes_expression_of]->(g) } AS de",
            lt=fx.GENE_NO_DE,
        )
        assert rows, f"{fx.GENE_NO_DE} no longer in KG"
        assert rows[0]["de"] is False

    def test_unknown_ids_truly_absent(self, conn):
        rows = conn.execute_query(
            "RETURN EXISTS { (g:Gene {locus_tag:$lt}) } AS gene_exists",
            lt=fx.UNKNOWN_LOCUS,
        )
        assert rows[0]["gene_exists"] is False

    def test_gene_no_coordinates_has_null_position(self, conn):
        # Degenerate property: gene exists but strand/start/contig are null.
        rows = conn.execute_query(
            "MATCH (g:Gene {locus_tag:$lt}) "
            "RETURN g.strand AS strand, g.start AS start, g.contig AS contig",
            lt=fx.GENE_NO_COORDINATES,
        )
        assert rows, f"{fx.GENE_NO_COORDINATES} no longer in KG"
        assert rows[0]["strand"] is None
        assert rows[0]["start"] is None
        assert rows[0]["contig"] is None
