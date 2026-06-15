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
        rows = conn.execute_query(
            "MATCH (o:OrganismTaxon {preferred_name:$n}) "
            "RETURN coalesce(o.experiment_count,0) AS e, "
            "coalesce(o.omics_types,[]) AS omics",
            n=fx.EXPRESSION_LAYER_EMPTY_ORGANISM,
        )
        assert rows, f"{fx.EXPRESSION_LAYER_EMPTY_ORGANISM} no longer in KG"
        assert rows[0]["e"] > 0
        assert "TRANSCRIPTOMICS" not in [o.upper() for o in rows[0]["omics"]]

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
