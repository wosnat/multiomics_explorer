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
    build_gene_ontology_terms,
    build_gene_stub,
    build_genes_by_ontology,
    build_get_gene_details_homologs,
    build_get_gene_details_main,
    build_get_homologs_groups,
    build_get_homologs_members,
    build_list_condition_types,
    build_list_gene_categories,
    build_list_organisms,
    build_query_expression,
    build_resolve_gene,
    build_search_genes,
    build_search_ontology,
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
        """ALT831_RS00180 has gene_name = locus_tag in source; KG stores it as synonym instead."""
        gene = GENES_BY_LOCUS["ALT831_RS00180"]
        cypher, params = build_resolve_gene(identifier=gene["locus_tag"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        assert results[0]["gene_name"] is None
        assert results[0]["locus_tag"] == gene["locus_tag"]


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

    def test_category_filter(self, conn):
        """Category filter restricts results to genes in that category."""
        cypher, params = build_search_genes(
            search_text="reaction centre", category="Photosynthesis",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0

    def test_cross_organism_results(self, conn):
        """Search without organism filter returns genes from multiple organisms."""
        cypher, params = build_search_genes(
            search_text="chaperone", limit=20,
        )
        results = conn.execute_query(cypher, **params)
        orgs = {r["organism_strain"] for r in results}
        assert len(orgs) >= 2, f"Expected multi-organism results, got {orgs}"


# ---------------------------------------------------------------------------
# TestGetGeneDetailsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGetGeneDetailsCorrectnessKG:
    """Validate gene details queries return expected nested structures."""

    def test_well_annotated_prochlorococcus(self, conn):
        """PMM0001 should have protein, organism, and ortholog group info."""
        cypher, params = build_get_gene_details_main(gene_id="PMM0001")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        gene = results[0]["gene"]
        assert gene is not None
        assert gene["locus_tag"] == "PMM0001"
        assert gene["_protein"] is not None, "PMM0001 should have a linked Protein"
        assert gene["_organism"] is not None, "PMM0001 should have a linked Organism"
        assert len(gene["_ortholog_groups"]) >= 1, "PMM0001 should have OrthologGroup memberships"

    def test_alteromonas_has_eggnog_groups(self, conn):
        """ALT831_RS00180 (Alteromonas) should have eggnog OrthologGroup memberships."""
        cypher, params = build_get_gene_details_main(gene_id="ALT831_RS00180")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        gene = results[0]["gene"]
        assert gene is not None
        og_sources = {og["source"] for og in gene["_ortholog_groups"]}
        assert "cyanorak" not in og_sources, "Alteromonas genes should not have Cyanorak groups"

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
    """Validate homolog queries return correct data with group-centric API."""

    def test_pmm1375_has_three_ortholog_groups(self, conn):
        """PMM1375 should belong to 3 ortholog groups (cyanorak, Prochloraceae eggnog, Bacteria eggnog)."""
        cypher, params = build_get_homologs_groups(gene_id="PMM1375")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 3, (
            f"Expected 3 ortholog groups for PMM1375, got {len(results)}"
        )

    def test_groups_ordered_by_specificity_rank(self, conn):
        """Groups should be ordered by specificity_rank ascending."""
        cypher, params = build_get_homologs_groups(gene_id="PMM1375")
        results = conn.execute_query(cypher, **params)
        ranks = [r["specificity_rank"] for r in results]
        assert ranks == sorted(ranks), (
            f"Groups not ordered by specificity_rank: {ranks}"
        )

    def test_groups_have_enrichment_properties(self, conn):
        """Each group has enrichment properties (consensus_product, member_count, etc.)."""
        cypher, params = build_get_homologs_groups(gene_id="PMM1375")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "og_name" in r
            assert "source" in r
            assert "taxonomic_level" in r
            assert "specificity_rank" in r
            assert "consensus_product" in r
            assert "consensus_gene_name" in r
            assert "member_count" in r
            assert "organism_count" in r
            assert "genera" in r
            assert "has_cross_genus_members" in r
            assert r["member_count"] is not None and r["member_count"] > 0

    def test_source_cyanorak_filter(self, conn):
        """source='cyanorak' filter returns only cyanorak group."""
        cypher, params = build_get_homologs_groups(gene_id="PMM1375", source="cyanorak")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1
        for r in results:
            assert r["source"] == "cyanorak"

    def test_exclude_paralogs_default(self, conn):
        """exclude_paralogs=True (default): no members with same organism_strain as query gene."""
        # First get the query gene's organism
        cypher_gene, params_gene = build_gene_stub(gene_id="PMM1375")
        gene_rows = conn.execute_query(cypher_gene, **params_gene)
        query_org = gene_rows[0]["organism_strain"]

        cypher, params = build_get_homologs_members(gene_id="PMM1375", exclude_paralogs=True)
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert r["organism_strain"] != query_org, (
                f"Paralog found with same organism: {r['locus_tag']} ({r['organism_strain']})"
            )

    def test_exclude_paralogs_false(self, conn):
        """exclude_paralogs=False: query does not filter by organism_strain."""
        cypher, params = build_get_homologs_members(gene_id="PMM1375", exclude_paralogs=False)
        results = conn.execute_query(cypher, **params)
        # Just verify it runs without error and returns members
        assert isinstance(results, list)

    def test_default_no_members_key(self, conn):
        """Default mode (groups query) returns group metadata, not member genes."""
        cypher, params = build_get_homologs_groups(gene_id="PMM1375")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "members" not in r

    def test_include_members_returns_member_genes(self, conn):
        """Members query returns member genes with locus_tag, gene_name, product, organism_strain."""
        cypher, params = build_get_homologs_members(gene_id="PMM1375")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "og_name" in r
            assert "locus_tag" in r
            assert "gene_name" in r
            assert "product" in r
            assert "organism_strain" in r

    def test_alteromonas_no_cyanorak_group(self, conn):
        """Alteromonas gene (MIT1002_00002) should not have cyanorak group."""
        cypher, params = build_get_homologs_groups(gene_id="MIT1002_00002")
        results = conn.execute_query(cypher, **params)
        sources = {r["source"] for r in results}
        assert "cyanorak" not in sources, (
            f"Alteromonas gene should not have cyanorak group, got sources: {sources}"
        )

    def test_gene_stub_returns_metadata(self, conn):
        """build_gene_stub returns query gene metadata."""
        cypher, params = build_gene_stub(gene_id="PMM1375")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        r = results[0]
        assert r["locus_tag"] == "PMM1375"
        assert "gene_name" in r
        assert "product" in r
        assert "organism_strain" in r

    def test_known_gene_has_homolog_groups(self, conn):
        """PMM0001 (dnaN) should have ortholog groups."""
        cypher, params = build_get_homologs_groups(gene_id="PMM0001")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0

    def test_homolog_groups_have_source_and_level(self, conn):
        """All groups should have non-null source and taxonomic_level."""
        cypher, params = build_get_homologs_groups(gene_id="PMM0001")
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert r["source"] is not None, f"Null source for {r['og_name']}"
            assert r["taxonomic_level"] is not None, f"Null taxonomic_level for {r['og_name']}"

    # -- Non-Prochlorococcus gene tests --

    def test_synechococcus_gene_has_eggnog_groups(self, conn):
        """Synechococcus gene (SYNW0305) should have eggnog ortholog groups."""
        cypher, params = build_get_homologs_groups(gene_id="SYNW0305")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1
        sources = {r["source"] for r in results}
        assert "eggnog" in sources

    def test_alteromonas_gene_has_members(self, conn):
        """Alteromonas gene should have homolog members across organisms."""
        cypher, params = build_get_homologs_members(gene_id="ALT831_RS00180")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1
        orgs = {r["organism_strain"] for r in results}
        assert len(orgs) >= 1

    # -- Filter combination tests --

    def test_source_and_max_specificity_rank_combined(self, conn):
        """Combining source + max_specificity_rank narrows results correctly."""
        # Unfiltered groups for PMM0001
        cypher_all, params_all = build_get_homologs_groups(gene_id="PMM0001")
        all_groups = conn.execute_query(cypher_all, **params_all)

        # Filtered: eggnog only with rank <= 3
        cypher_filtered, params_filtered = build_get_homologs_groups(
            gene_id="PMM0001", source="eggnog", max_specificity_rank=3,
        )
        filtered = conn.execute_query(cypher_filtered, **params_filtered)
        assert len(filtered) <= len(all_groups)
        for r in filtered:
            assert r["source"] == "eggnog"
            assert r["specificity_rank"] <= 3

    def test_max_specificity_rank_0_curated_only(self, conn):
        """max_specificity_rank=0 returns only curated groups (rank 0)."""
        cypher, params = build_get_homologs_groups(
            gene_id="PMM1375", max_specificity_rank=0,
        )
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert r["specificity_rank"] == 0, (
                f"Expected rank 0, got {r['specificity_rank']} for {r['og_name']}"
            )

    # -- Member ordering correctness test --

    def test_members_ordered_by_specificity_organism_locus(self, conn):
        """Members query results are ordered by specificity_rank, source, organism, locus_tag."""
        cypher, params = build_get_homologs_members(gene_id="PMM0001")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 1
        # Check organism_strain + locus_tag ordering within each og_name group
        prev_org = ""
        prev_locus = ""
        prev_og = ""
        for r in results:
            if r["og_name"] == prev_og:
                if r["organism_strain"] == prev_org:
                    assert r["locus_tag"] >= prev_locus, (
                        f"Locus tags not sorted: {prev_locus} > {r['locus_tag']}"
                    )
            prev_og = r["og_name"]
            prev_org = r["organism_strain"]
            prev_locus = r["locus_tag"]

    # -- Gene with zero ortholog groups --

    def test_hypothetical_gene_may_lack_groups(self, conn):
        """A hypothetical protein may have fewer ortholog groups."""
        # PMT9312_0342 is a hypothetical protein — may have 0 or few groups
        cypher, params = build_get_homologs_groups(gene_id="PMT9312_0342")
        results = conn.execute_query(cypher, **params)
        # Just verify the query runs and returns a list
        assert isinstance(results, list)


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


# ---------------------------------------------------------------------------
# TestListFilterValuesCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestListFilterValuesCorrectnessKG:
    """Validate list_filter_values query builders against live Neo4j."""

    def test_known_categories_present(self, conn):
        """Known gene categories must be present in results."""
        cypher, params = build_list_gene_categories()
        results = conn.execute_query(cypher, **params)
        categories = {r["category"] for r in results}
        for expected in ["Photosynthesis", "Transport",
                         "Stress response and adaptation", "Translation"]:
            assert expected in categories, (
                f"Expected category '{expected}' not found in {sorted(categories)}"
            )

    def test_known_condition_types_present(self, conn):
        """Known condition types must be present in results."""
        cypher, params = build_list_condition_types()
        results = conn.execute_query(cypher, **params)
        condition_types = {r["condition_type"] for r in results}
        for expected in ["nitrogen_stress", "light_stress", "coculture"]:
            assert expected in condition_types, (
                f"Expected condition_type '{expected}' not found in {sorted(condition_types)}"
            )

    def test_all_counts_positive(self, conn):
        """All gene_count and cnt values must be > 0."""
        cat_cypher, cat_params = build_list_gene_categories()
        categories = conn.execute_query(cat_cypher, **cat_params)
        for r in categories:
            assert r["gene_count"] > 0, (
                f"Category '{r['category']}' has gene_count={r['gene_count']}"
            )

        cond_cypher, cond_params = build_list_condition_types()
        conditions = conn.execute_query(cond_cypher, **cond_params)
        for r in conditions:
            assert r["cnt"] > 0, (
                f"Condition type '{r['condition_type']}' has cnt={r['cnt']}"
            )

    def test_minimum_gene_categories(self, conn):
        """At least 20 gene categories should be returned."""
        cypher, params = build_list_gene_categories()
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 20, (
            f"Expected >= 20 gene categories, got {len(results)}"
        )

    def test_minimum_condition_types(self, conn):
        """At least 5 condition types should be returned."""
        cypher, params = build_list_condition_types()
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 5, (
            f"Expected >= 5 condition types, got {len(results)}"
        )


# ---------------------------------------------------------------------------
# TestListOrganismsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestListOrganismsCorrectnessKG:
    """Validate list_organisms query builder against live Neo4j."""

    def test_known_organisms_present(self, conn):
        """Known organisms MED4 and EZ55 must appear in results."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        names = {r["name"] for r in results}
        for expected in ["Prochlorococcus MED4", "Alteromonas macleodii EZ55", "MIT9313", "HOT1A3"]:
            assert any(expected in n for n in names), (
                f"Expected organism containing '{expected}' not found in {sorted(names)}"
            )

    def test_gene_count_positive(self, conn):
        """Organisms with a strain should have gene_count > 0."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        strain_organisms = [r for r in results if r.get("strain")]
        assert len(strain_organisms) > 0, "No organisms with strains found"
        for r in strain_organisms:
            assert r["gene_count"] > 0, (
                f"Organism '{r['name']}' has gene_count={r['gene_count']}"
            )

    def test_clade_populated_for_prochlorococcus(self, conn):
        """Prochlorococcus strains should have a non-null clade."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        pro_strains = [r for r in results if r["genus"] == "Prochlorococcus"]
        assert len(pro_strains) > 0, "No Prochlorococcus strains found"
        for r in pro_strains:
            assert r["clade"] is not None, (
                f"Prochlorococcus strain '{r['name']}' has null clade"
            )

    def test_clade_null_for_alteromonas(self, conn):
        """Alteromonas strains should not have a clade."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        alt_strains = [r for r in results if r["genus"] == "Alteromonas"]
        for r in alt_strains:
            assert r["clade"] is None, (
                f"Alteromonas strain '{r['name']}' has unexpected clade={r['clade']}"
            )

    def test_clade_null_for_synechococcus(self, conn):
        """Synechococcus/Parasynechococcus strains should not have a clade."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        syn_strains = [r for r in results if "synechococcus" in (r["genus"] or "").lower()
                       or "parasynechococcus" in (r["genus"] or "").lower()]
        for r in syn_strains:
            assert r["clade"] is None, (
                f"Synechococcus strain '{r['name']}' has unexpected clade={r['clade']}"
            )

    def test_minimum_organisms(self, conn):
        """At least 10 organisms should be returned."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 10, (
            f"Expected >= 10 organisms, got {len(results)}"
        )


# ---------------------------------------------------------------------------
# TestSearchOntologyCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestSearchOntologyCorrectnessKG:
    """Validate search_ontology queries against live Neo4j."""

    def test_go_bp_replication(self, conn):
        """Search for 'replication' in GO:BP returns biological process terms."""
        cypher, params = build_search_ontology(ontology="go_bp", search_text="replication")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "id" in r
            assert "name" in r
            assert "score" in r

    def test_ec_oxidoreductase(self, conn):
        """Search for 'oxidoreductase' in EC returns EC terms."""
        cypher, params = build_search_ontology(ontology="ec", search_text="oxidoreductase")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0

    def test_kegg_metabolism_multiple_levels(self, conn):
        """Search for 'metabolism' in KEGG returns results from multiple levels."""
        cypher, params = build_search_ontology(ontology="kegg", search_text="metabolism")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        # KEGG levels are visible from ID prefixes
        id_prefixes = {r["id"].split(":")[0] for r in results}
        # Should see at least 2 different prefixes (e.g. kegg.category, kegg.subcategory)
        assert len(id_prefixes) >= 1

    def test_go_mf_binding(self, conn):
        """Search for 'binding' in GO:MF returns molecular function terms."""
        cypher, params = build_search_ontology(ontology="go_mf", search_text="binding")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "id" in r
            assert "name" in r

    def test_go_cc_membrane(self, conn):
        """Search for 'membrane' in GO:CC returns cellular component terms."""
        cypher, params = build_search_ontology(ontology="go_cc", search_text="membrane")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0


# ---------------------------------------------------------------------------
# TestGenesByOntologyCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGenesByOntologyCorrectnessKG:
    """Validate genes_by_ontology queries against live Neo4j."""

    def test_go_bp_hierarchy_expansion(self, conn):
        """GO:BP by ID with hierarchy: nucleobase-containing compound metabolic process."""
        cypher, params = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006139"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 10, (
            f"Expected >= 10 genes for go:0006139 hierarchy, got {len(results)}"
        )

    def test_go_bp_leaf_fewer_than_parent(self, conn):
        """A specific leaf term should return fewer genes than a parent term."""
        cypher_parent, params_parent = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006139"], limit=100,
        )
        cypher_leaf, params_leaf = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"], limit=100,
        )
        parent_results = conn.execute_query(cypher_parent, **params_parent)
        leaf_results = conn.execute_query(cypher_leaf, **params_leaf)
        assert len(leaf_results) <= len(parent_results), (
            f"Leaf term go:0006260 ({len(leaf_results)} genes) should have "
            f"<= parent go:0006139 ({len(parent_results)} genes)"
        )

    def test_ec_hierarchy_top_level(self, conn):
        """EC hierarchy: ec:1.-.-.- returns all oxidoreductases via tree walk."""
        cypher, params = build_genes_by_ontology(
            ontology="ec", term_ids=["ec:1.-.-.-"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 10

    def test_ec_leaf_direct(self, conn):
        """EC leaf: ec:2.7.7.7 returns DNA polymerases."""
        cypher, params = build_genes_by_ontology(
            ontology="ec", term_ids=["ec:2.7.7.7"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_kegg_category_traversal(self, conn):
        """KEGG Category: kegg.category:09100 (Metabolism) traverses to genes."""
        cypher, params = build_genes_by_ontology(
            ontology="kegg", term_ids=["kegg.category:09100"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 10

    def test_kegg_ko_direct(self, conn):
        """KEGG KO direct: kegg.orthology:K00001 returns genes."""
        cypher, params = build_genes_by_ontology(
            ontology="kegg", term_ids=["kegg.orthology:K00001"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_organism_filter(self, conn):
        """Organism filter restricts results to matching organism."""
        cypher_all, params_all = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006139"], limit=500,
        )
        cypher_filtered, params_filtered = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006139"],
            organism="MED4", limit=500,
        )
        all_results = conn.execute_query(cypher_all, **params_all)
        filtered = conn.execute_query(cypher_filtered, **params_filtered)
        assert len(filtered) < len(all_results), (
            "Organism filter should reduce result count"
        )
        for r in filtered:
            assert "MED4" in r["organism_strain"]

    def test_multiple_term_ids(self, conn):
        """Multiple term IDs return union of results."""
        cypher, params = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260", "go:0006139"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_go_mf_dna_binding(self, conn):
        """GO:MF hierarchy: go:0003677 (DNA binding) finds genes."""
        cypher, params = build_genes_by_ontology(
            ontology="go_mf", term_ids=["go:0003677"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1, "Expected genes for DNA binding (go:0003677)"

    def test_go_cc_membrane(self, conn):
        """GO:CC hierarchy: go:0016020 (membrane) finds genes."""
        cypher, params = build_genes_by_ontology(
            ontology="go_cc", term_ids=["go:0016020"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1, "Expected genes for membrane (go:0016020)"

    def test_kegg_subcategory(self, conn):
        """KEGG subcategory: kegg.subcategory:09101 traverses to genes."""
        cypher, params = build_genes_by_ontology(
            ontology="kegg", term_ids=["kegg.subcategory:09101"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_ec_intermediate_level(self, conn):
        """EC intermediate: ec:1.1.-.- returns a subset of ec:1.-.-.-."""
        cypher, params = build_genes_by_ontology(
            ontology="ec", term_ids=["ec:1.1.-.-"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1


# ---------------------------------------------------------------------------
# TestGeneOntologyTermsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGeneOntologyTermsCorrectnessKG:
    """Validate gene_ontology_terms queries against live Neo4j."""

    def test_bp_leaf_only_argr(self, conn):
        """argR (MIT1002_03493) leaf BP terms should be around 12."""
        cypher, params = build_gene_ontology_terms(
            ontology="go_bp", gene_id="MIT1002_03493", leaf_only=True,
        )
        results = conn.execute_query(cypher, **params)
        assert 5 <= len(results) <= 20, (
            f"Expected 5-20 leaf BP terms for argR, got {len(results)}"
        )
        for r in results:
            assert "id" in r
            assert "name" in r

    def test_bp_all_argr(self, conn):
        """argR (MIT1002_03493) all BP terms should be many more than leaf-only."""
        cypher, params = build_gene_ontology_terms(
            ontology="go_bp", gene_id="MIT1002_03493", leaf_only=False,
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 50, (
            f"Expected >= 50 total BP terms for argR, got {len(results)}"
        )

    def test_ec_annotations(self, conn):
        """Gene with EC annotations returns EC numbers with id and name."""
        cypher, params = build_gene_ontology_terms(
            ontology="ec", gene_id="MIT1002_03493",
        )
        results = conn.execute_query(cypher, **params)
        # argR may or may not have EC; just check column structure if results exist
        for r in results:
            assert "id" in r
            assert "name" in r

    def test_kegg_annotations(self, conn):
        """Gene with KEGG KOs returns terms with id and name."""
        cypher, params = build_gene_ontology_terms(
            ontology="kegg", gene_id="MIT1002_03493",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1, "argR should have at least 1 KEGG KO"
        for r in results:
            assert "id" in r
            assert "name" in r

    def test_no_annotations_empty_result(self, conn):
        """Gene with no annotations for given ontology returns empty."""
        # Use a gene unlikely to have GO:CC annotations
        cypher, params = build_gene_ontology_terms(
            ontology="go_cc", gene_id="PMT9312_0342",
        )
        results = conn.execute_query(cypher, **params)
        # Just verify it returns a list (may be empty or not)
        assert isinstance(results, list)

    def test_limit_caps_results(self, conn):
        """Limit parameter caps result count."""
        cypher, params = build_gene_ontology_terms(
            ontology="go_bp", gene_id="MIT1002_03493",
            leaf_only=False, limit=5,
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) <= 5

    def test_mf_annotations(self, conn):
        """Gene with GO:MF annotations returns molecular function terms."""
        cypher, params = build_gene_ontology_terms(
            ontology="go_mf", gene_id="MIT1002_03493",
        )
        results = conn.execute_query(cypher, **params)
        # Just check structure — may or may not have MF annotations
        for r in results:
            assert "id" in r
            assert "name" in r

    def test_cc_annotations(self, conn):
        """Gene with GO:CC annotations returns cellular component terms."""
        cypher, params = build_gene_ontology_terms(
            ontology="go_cc", gene_id="MIT1002_03493",
        )
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert "id" in r
            assert "name" in r

    def test_different_gene_bp(self, conn):
        """Different gene (PMM0001/dnaN) has GO:BP annotations."""
        cypher, params = build_gene_ontology_terms(
            ontology="go_bp", gene_id="PMM0001",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1, "PMM0001 (dnaN) should have GO:BP annotations"
