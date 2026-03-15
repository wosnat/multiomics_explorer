"""Integration tests validating MCP tool correctness against live Neo4j.

Each test compares query results to ground-truth fixture data extracted from
the original annotation JSONs. Tests are marked with @pytest.mark.kg and
auto-skip if Neo4j is unavailable.

Note: The KG build pipeline replaces reserved characters before loading:
  ' (apostrophe) → ^ (caret)
  | (pipe) → , (comma)
So product/description strings in the KG may differ from raw annotation JSONs.
"""

import pytest

from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
    build_search_genes,
    build_resolve_gene,
    build_get_gene_details_homologs,
    build_get_gene_details_main,
    build_get_homologs,
    build_query_expression,
)
from tests.fixtures.gene_data import (
    GENES,
    GENES_BY_LOCUS,
    GENES_WITH_GENE_NAME,
    GENES_WITHOUT_GENE_NAME,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _locus_tags(results):
    """Extract locus_tag values from a result set."""
    return [r["locus_tag"] for r in results]


def _kg_escape(text):
    """Apply the same character escaping the KG build pipeline uses.

    The pipeline replaces ' → ^ and | → , before loading into Neo4j.
    """
    if text is None:
        return None
    return text.replace("'", "^").replace("|", ",")


# ---------------------------------------------------------------------------
# TestGetGeneCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestResolveGeneCorrectnessKG:
    """Validate resolve_gene queries return correct data for every fixture gene."""

    @pytest.mark.parametrize(
        "gene", GENES, ids=[g["locus_tag"] for g in GENES],
    )
    def test_lookup_by_locus_tag(self, conn, gene):
        """Every fixture gene should be found by locus_tag with matching product and organism."""
        cypher, params = build_resolve_gene(identifier=gene["locus_tag"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1, (
            f"Expected 1 result for {gene['locus_tag']}, got {len(results)}"
        )
        row = results[0]
        # Product may differ due to KG char escaping (' → ^, | → ,)
        assert row["product"] == _kg_escape(gene["product"])
        assert row["organism_strain"] == gene["organism_strain"]

    @pytest.mark.parametrize(
        "gene",
        GENES_WITH_GENE_NAME,
        ids=[g["locus_tag"] for g in GENES_WITH_GENE_NAME],
    )
    def test_lookup_by_gene_name(self, conn, gene):
        """Genes with a real gene_name should return results.
        Note: resolve_gene also matches on all_identifiers, so results may
        include genes with different gene_names that share an identifier."""
        cypher, params = build_resolve_gene(identifier=gene["gene_name"])
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1, (
            f"No results for gene_name={gene['gene_name']}"
        )

    def test_dnan_ambiguous_without_organism(self, conn):
        """dnaN exists in multiple organisms, so unfiltered lookup returns >1 result."""
        cypher, params = build_resolve_gene(identifier="dnaN")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 1, "dnaN should match multiple organisms"

    def test_dnan_filtered_by_organism(self, conn):
        """dnaN + organism=MED4 should return exactly 1 result from MED4."""
        cypher, params = build_resolve_gene(identifier="dnaN", organism="MED4")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        assert "MED4" in results[0]["organism_strain"]

    def test_lookup_by_all_identifiers_entry(self, conn):
        """PMM0446 should be found via its WP_ protein accession."""
        cypher, params = build_resolve_gene(identifier="WP_011132082.1")
        results = conn.execute_query(cypher, **params)
        found_loci = _locus_tags(results)
        assert "PMM0446" in found_loci

    def test_lookup_by_old_locus_tag(self, conn):
        """PMT0106 should be found via old locus tag PMT_0106 (in all_identifiers)."""
        cypher, params = build_resolve_gene(identifier="PMT_0106")
        results = conn.execute_query(cypher, **params)
        found_loci = _locus_tags(results)
        assert "PMT0106" in found_loci

    def test_gene_name_equals_locus_tag(self, conn):
        """ALT831_RS00180 has gene_name = locus_tag; verify it returns correctly."""
        gene = GENES_BY_LOCUS["ALT831_RS00180"]
        cypher, params = build_resolve_gene(identifier=gene["locus_tag"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        assert results[0]["gene_name"] == gene["gene_name"]
        assert results[0]["gene_name"] == gene["locus_tag"]


# ---------------------------------------------------------------------------
# TestSearchGenesCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestSearchGenesCorrectnessKG:
    """Validate full-text search_genes returns scored results."""

    def test_basic_search_has_scores(self, conn):
        """Full-text search for 'photosystem' should return results with scores."""
        cypher, params = build_search_genes(search_text="photosystem")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "score" in r
            assert r["score"] > 0

    def test_organism_filter(self, conn):
        """Organism filter should restrict full-text results."""
        cypher, params = build_search_genes(search_text="DNA repair", organism="MED4")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "MED4" in r["organism_strain"], (
                f"Expected MED4, got {r['organism_strain']}"
            )

    def test_quality_filter_reduces_results(self, conn):
        """Higher min_quality should return fewer or equal results than lower."""
        cypher_low, params_low = build_search_genes(
            search_text="polymerase", min_quality=0, limit=50,
        )
        cypher_high, params_high = build_search_genes(
            search_text="polymerase", min_quality=2, limit=50,
        )
        results_low = conn.execute_query(cypher_low, **params_low)
        results_high = conn.execute_query(cypher_high, **params_high)
        assert len(results_high) <= len(results_low)


# ---------------------------------------------------------------------------
# TestGetGeneDetailsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGetGeneDetailsCorrectnessKG:
    """Validate gene details queries return expected nested structures."""

    def test_well_annotated_prochlorococcus(self, conn):
        """PMM0001 should have protein, organism, and cluster info."""
        cypher, params = build_get_gene_details_main(gene_id="PMM0001")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        gene = results[0]["gene"]
        assert gene is not None
        assert gene["locus_tag"] == "PMM0001"
        assert gene["_protein"] is not None, "PMM0001 should have a linked Protein"
        assert gene["_organism"] is not None, "PMM0001 should have a linked Organism"
        assert gene["_cluster"] is not None, "PMM0001 should have a CyanORAK cluster"

    def test_alteromonas_no_cluster(self, conn):
        """ALT831_RS00180 (Alteromonas) should have no CyanORAK cluster."""
        cypher, params = build_get_gene_details_main(gene_id="ALT831_RS00180")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        gene = results[0]["gene"]
        assert gene is not None
        assert gene["_cluster"] is None, "Alteromonas genes should not have CyanORAK clusters"

    def test_homologs_exist_for_pmm0001(self, conn):
        """PMM0001 (dnaN) should have homologs from other organisms."""
        cypher, params = build_get_gene_details_homologs(gene_id="PMM0001")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        strains = {r["organism_strain"] for r in results}
        # dnaN homologs should span multiple strains
        assert len(strains) >= 2, (
            f"Expected homologs from >=2 strains, got {strains}"
        )


# ---------------------------------------------------------------------------
# TestGetHomologsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGetHomologsCorrectnessKG:
    """Validate homolog queries return correct data."""

    def test_known_gene_has_homologs(self, conn):
        """PMM0001 (dnaN) should have homologs from multiple organisms."""
        cypher, params = build_get_homologs(gene_id="PMM0001")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0

    def test_homolog_distances_present(self, conn):
        """All homologs should have a non-null distance value."""
        cypher, params = build_get_homologs(gene_id="PMM0001")
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert r["distance"] is not None, (
                f"Null distance for {r['locus_tag']}"
            )

    def test_homologs_cross_organism(self, conn):
        """PMM0001 homologs should include genes from at least 2 different strains."""
        cypher, params = build_get_homologs(gene_id="PMM0001")
        results = conn.execute_query(cypher, **params)
        strains = {r["organism_strain"] for r in results}
        assert len(strains) >= 2, (
            f"Expected cross-organism homologs, got strains: {strains}"
        )


# ---------------------------------------------------------------------------
# TestQueryExpressionCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestQueryExpressionCorrectnessKG:
    """Validate expression queries return correct filtered data."""

    def test_med4_has_expression_data(self, conn):
        """MED4 should have expression data in the KG."""
        cypher, params = build_query_expression(organism="MED4", limit=5)
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0

    def test_direction_filter_up(self, conn):
        """Direction filter 'up' should only return upregulated genes."""
        cypher, params = build_query_expression(
            organism="MED4", direction="up", limit=10,
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert r["direction"] == "up", (
                f"Expected direction='up', got {r['direction']}"
            )

    def test_direction_filter_down(self, conn):
        """Direction filter 'down' should only return downregulated genes."""
        cypher, params = build_query_expression(
            organism="MED4", direction="down", limit=10,
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert r["direction"] == "down", (
                f"Expected direction='down', got {r['direction']}"
            )

    def test_min_log2fc_filter(self, conn):
        """All results with min_log2fc=2.0 should have abs(log2fc) >= 2.0."""
        cypher, params = build_query_expression(
            organism="MED4", min_log2fc=2.0, limit=20,
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert abs(r["log2fc"]) >= 2.0, (
                f"Expected abs(log2fc) >= 2.0, got {r['log2fc']}"
            )


# ---------------------------------------------------------------------------
# TestCompareConditionsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestCompareConditionsCorrectnessKG:
    """Validate compare_conditions queries."""

    def test_by_organism(self, conn):
        """Filtering by organism MED4 should return expression comparison data."""
        cypher, params = build_compare_conditions(organisms=["MED4"], limit=10)
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        assert "gene" in results[0]

    def test_by_gene_ids(self, conn):
        """Filtering by gene_ids should only return matching genes."""
        cypher, params = build_compare_conditions(
            gene_ids=["PMM0001"], limit=10,
        )
        results = conn.execute_query(cypher, **params)
        # PMM0001 may or may not have expression data; if it does, gene should match
        for r in results:
            assert r["gene"] == "PMM0001", (
                f"Expected gene='PMM0001', got {r['gene']}"
            )
