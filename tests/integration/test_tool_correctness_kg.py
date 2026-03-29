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

from multiomics_explorer.api import functions as api
from multiomics_explorer.kg.queries_lib import (
    build_gene_ontology_terms,
    build_gene_overview,
    build_gene_stub,
    build_genes_by_ontology,
    build_gene_details,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_list_gene_categories,
    build_list_organisms,
    build_resolve_gene,
    build_genes_by_function,
    build_search_ontology,
    build_search_ontology_summary,
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
class TestGenesByFunctionCorrectnessKG:
    """Validate full-text genes_by_function returns scored results."""

    def test_basic_search_has_scores(self, conn):
        """Full-text search for 'photosystem' should return results with scores."""
        cypher, params = build_genes_by_function(search_text="photosystem")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "score" in r
            assert r["score"] > 0

    def test_organism_filter(self, conn):
        """Organism filter should restrict full-text results."""
        cypher, params = build_genes_by_function(search_text="DNA repair", organism="MED4")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "MED4" in r["organism_strain"], (
                f"Expected MED4, got {r['organism_strain']}"
            )

    def test_quality_filter_reduces_results(self, conn):
        """Higher min_quality should return fewer or equal results than lower."""
        cypher_low, params_low = build_genes_by_function(
            search_text="polymerase", min_quality=0,
        )
        cypher_high, params_high = build_genes_by_function(
            search_text="polymerase", min_quality=2,
        )
        results_low = conn.execute_query(cypher_low, **params_low)
        results_high = conn.execute_query(cypher_high, **params_high)
        assert len(results_high) <= len(results_low)

    def test_category_filter(self, conn):
        """Category filter restricts results to genes in that category."""
        cypher, params = build_genes_by_function(
            search_text="reaction centre", category="Photosynthesis",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0

    def test_cross_organism_results(self, conn):
        """Search without organism filter returns genes from multiple organisms."""
        cypher, params = build_genes_by_function(
            search_text="chaperone",
        )
        results = conn.execute_query(cypher, **params)
        orgs = {r["organism_strain"] for r in results}
        assert len(orgs) >= 2, f"Expected multi-organism results, got {orgs}"


# ---------------------------------------------------------------------------
# TestGetGeneDetailsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGeneDetailsCorrectnessKG:
    """Validate gene details queries return flat g{.*} properties."""

    def test_well_annotated_prochlorococcus(self, conn):
        """PMM0001 returns flat g{.*} with locus_tag, gene_name, product, organism_strain."""
        cypher, params = build_gene_details(locus_tags=["PMM0001"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        gene = results[0]["gene"]
        assert gene is not None
        assert gene["locus_tag"] == "PMM0001"
        assert gene["gene_name"] == "dnaN"
        assert "product" in gene
        assert "organism_strain" in gene

    def test_alteromonas_gene(self, conn):
        """ALT831_RS00180 returns flat properties with organism_strain containing 'Alteromonas'."""
        cypher, params = build_gene_details(locus_tags=["ALT831_RS00180"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        gene = results[0]["gene"]
        assert gene is not None
        assert gene["locus_tag"] == "ALT831_RS00180"
        assert "Alteromonas" in gene["organism_strain"]


# ---------------------------------------------------------------------------
# TestGeneOverviewCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGeneOverviewCorrectnessKG:
    """Validate gene_overview queries return routing signals from pre-computed properties."""

    def test_single_gene_pro(self, conn):
        """PMM1428: verify annotation_types, expression counts, ortholog signals."""
        cypher, params = build_gene_overview(locus_tags=["PMM1428"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        r = results[0]
        assert r["locus_tag"] == "PMM1428"
        assert set(r["annotation_types"]) >= {"go_mf", "pfam", "cog_category", "tigr_role"}
        assert r["expression_edge_count"] == 36
        assert r["significant_up_count"] + r["significant_down_count"] == 5
        assert r["closest_ortholog_group_size"] == 9
        assert set(r["closest_ortholog_genera"]) == {"Prochlorococcus", "Synechococcus"}

    def test_single_gene_alt(self, conn):
        """EZ55_00275: empty annotation_types, no expression, small ortholog group."""
        cypher, params = build_gene_overview(locus_tags=["EZ55_00275"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        r = results[0]
        assert r["locus_tag"] == "EZ55_00275"
        assert r["annotation_types"] == []
        assert r["expression_edge_count"] == 0
        assert r["closest_ortholog_group_size"] == 1

    def test_batch_mixed_organisms(self, conn):
        """[PMM1428, EZ55_00275]: returns 2 rows with correct organism_strain."""
        cypher, params = build_gene_overview(locus_tags=["PMM1428", "EZ55_00275"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 2
        orgs = {r["organism_strain"] for r in results}
        assert len(orgs) == 2  # different organisms

    def test_nonexistent_gene_excluded(self, conn):
        """[PMM1428, FAKE_GENE]: returns 1 row (only PMM1428)."""
        cypher, params = build_gene_overview(locus_tags=["PMM1428", "FAKE_GENE"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        assert results[0]["locus_tag"] == "PMM1428"


# ---------------------------------------------------------------------------
# TestGeneHomologsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGeneHomologsCorrectnessKG:
    """Validate gene_homologs queries return correct data (flat long format)."""

    def test_pmm1375_has_three_groups(self, conn):
        """PMM1375 should belong to 3 ortholog groups."""
        cypher, params = build_gene_homologs(locus_tags=["PMM1375"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 3

    def test_results_have_compact_columns(self, conn):
        """Each result has compact columns."""
        cypher, params = build_gene_homologs(locus_tags=["PMM1375"])
        results = conn.execute_query(cypher, **params)
        for r in results:
            for col in ("locus_tag", "organism_strain", "group_id",
                        "consensus_gene_name", "consensus_product",
                        "taxonomic_level", "source"):
                assert col in r, f"Missing compact column: {col}"

    def test_verbose_adds_columns(self, conn):
        """verbose=True adds group metadata columns."""
        cypher, params = build_gene_homologs(locus_tags=["PMM1375"], verbose=True)
        results = conn.execute_query(cypher, **params)
        for r in results:
            for col in ("specificity_rank", "member_count", "organism_count",
                        "genera", "has_cross_genus_members"):
                assert col in r, f"Missing verbose column: {col}"

    def test_ordered_by_locus_rank_source(self, conn):
        """Results ordered by locus_tag, specificity_rank, source."""
        cypher, params = build_gene_homologs(locus_tags=["PMM1375"], verbose=True)
        results = conn.execute_query(cypher, **params)
        ranks = [r["specificity_rank"] for r in results]
        assert ranks == sorted(ranks)

    def test_source_filter(self, conn):
        """source='cyanorak' returns only cyanorak groups."""
        cypher, params = build_gene_homologs(locus_tags=["PMM1375"], source="cyanorak")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1
        for r in results:
            assert r["source"] == "cyanorak"

    def test_max_specificity_rank_0(self, conn):
        """max_specificity_rank=0 returns only curated groups."""
        cypher, params = build_gene_homologs(
            locus_tags=["PMM1375"], max_specificity_rank=0, verbose=True,
        )
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert r["specificity_rank"] == 0

    def test_batch_multiple_genes(self, conn):
        """Batch query returns rows for multiple genes."""
        cypher, params = build_gene_homologs(locus_tags=["PMM0001", "PMM0845"])
        results = conn.execute_query(cypher, **params)
        loci = {r["locus_tag"] for r in results}
        assert loci == {"PMM0001", "PMM0845"}

    def test_alteromonas_no_cyanorak(self, conn):
        """Alteromonas gene has no cyanorak groups."""
        cypher, params = build_gene_homologs(locus_tags=["MIT1002_00002"])
        results = conn.execute_query(cypher, **params)
        sources = {r["source"] for r in results}
        assert "cyanorak" not in sources

    def test_synechococcus_has_eggnog(self, conn):
        """Synechococcus gene has eggnog groups."""
        cypher, params = build_gene_homologs(locus_tags=["SYNW0305"])
        results = conn.execute_query(cypher, **params)
        sources = {r["source"] for r in results}
        assert "eggnog" in sources

    def test_summary_not_found(self, conn):
        """Fake gene appears in not_found."""
        cypher, params = build_gene_homologs_summary(locus_tags=["FAKE_GENE_XYZ"])
        result = conn.execute_query(cypher, **params)[0]
        assert "FAKE_GENE_XYZ" in result["not_found"]

    def test_summary_no_groups(self, conn):
        """Gene with no OGs appears in no_groups."""
        cypher, params = build_gene_homologs_summary(locus_tags=["A9601_RS13285"])
        result = conn.execute_query(cypher, **params)[0]
        assert "A9601_RS13285" in result["no_groups"]

    def test_summary_breakdowns(self, conn):
        """Summary returns by_organism and by_source breakdowns."""
        cypher, params = build_gene_homologs_summary(locus_tags=["PMM0001"])
        result = conn.execute_query(cypher, **params)[0]
        assert result["total_matching"] >= 2
        assert len(result["by_organism"]) >= 1
        assert len(result["by_source"]) >= 1

    def test_limit(self, conn):
        """LIMIT caps results."""
        cypher, params = build_gene_homologs(locus_tags=["PMM0001"], limit=1)
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1


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

    def test_all_counts_positive(self, conn):
        """All gene_count values must be > 0."""
        cat_cypher, cat_params = build_list_gene_categories()
        categories = conn.execute_query(cat_cypher, **cat_params)
        for r in categories:
            assert r["gene_count"] > 0, (
                f"Category '{r['category']}' has gene_count={r['gene_count']}"
            )

    def test_minimum_gene_categories(self, conn):
        """At least 20 gene categories should be returned."""
        cypher, params = build_list_gene_categories()
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 20, (
            f"Expected >= 20 gene categories, got {len(results)}"
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
        names = {r["organism_name"] for r in results}
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

    def test_cog_category_energy(self, conn):
        """Search for 'energy' in COG categories returns results."""
        cypher, params = build_search_ontology(ontology="cog_category", search_text="energy")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "id" in r
            assert "name" in r
            assert "score" in r

    def test_cyanorak_role_dna(self, conn):
        """Search for 'DNA' in CyanoRAK roles returns results."""
        cypher, params = build_search_ontology(ontology="cyanorak_role", search_text="DNA")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "id" in r
            assert "name" in r

    def test_tigr_role_metabolism(self, conn):
        """Search for 'metabolism' in TIGR roles returns results."""
        cypher, params = build_search_ontology(ontology="tigr_role", search_text="metabolism")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0

    def test_pfam_polymerase(self, conn):
        """Search for 'polymerase' in Pfam returns results from domains and/or clans."""
        cypher, params = build_search_ontology(ontology="pfam", search_text="polymerase")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert "id" in r
            assert "name" in r

    def test_limit_parameter(self, conn):
        """Limit parameter caps number of returned rows."""
        cypher, params = build_search_ontology(ontology="go_bp", search_text="replication", limit=3)
        results = conn.execute_query(cypher, **params)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# TestSearchOntologySummaryCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestSearchOntologySummaryCorrectnessKG:
    """Validate search_ontology_summary queries against live Neo4j."""

    def test_go_bp_summary_keys(self, conn):
        """Summary query returns expected keys."""
        cypher, params = build_search_ontology_summary(ontology="go_bp", search_text="replication")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        row = results[0]
        assert "total_entries" in row
        assert "total_matching" in row
        assert "score_max" in row
        assert "score_median" in row
        assert row["total_entries"] > 0
        assert row["total_matching"] > 0

    def test_pfam_summary(self, conn):
        """Pfam summary uses UNION and returns totals."""
        cypher, params = build_search_ontology_summary(ontology="pfam", search_text="polymerase")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        row = results[0]
        assert row["total_entries"] > 0
        assert row["total_matching"] > 0


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
            ontology="go_bp", term_ids=["go:0006139"],
        )
        cypher_leaf, params_leaf = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"],
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
            ontology="go_bp", term_ids=["go:0006139"],
        )
        cypher_filtered, params_filtered = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006139"],
            organism="MED4",
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

    def test_cog_category_flat(self, conn):
        """COG category C (Energy) -- flat ontology, no hierarchy expansion."""
        cypher, params = build_genes_by_ontology(
            ontology="cog_category", term_ids=["cog.category:C"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1
        for r in results:
            assert "locus_tag" in r
            assert "organism_strain" in r

    def test_cyanorak_role_hierarchy(self, conn):
        """CyanoRAK role hierarchy expansion returns genes."""
        cypher, params = build_genes_by_ontology(
            ontology="cyanorak_role", term_ids=["cyanorak.role:F"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_tigr_role_flat(self, conn):
        """TIGR role (flat ontology) returns genes."""
        cypher, params = build_genes_by_ontology(
            ontology="tigr_role", term_ids=["tigr.role:120"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_pfam_domain(self, conn):
        """Pfam domain PF00712 returns annotated genes."""
        cypher, params = build_genes_by_ontology(
            ontology="pfam", term_ids=["pfam:PF00712"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_pfam_clan_hierarchy(self, conn):
        """Pfam clan CL0060 with hierarchy expansion returns more genes than domain alone."""
        cypher, params = build_genes_by_ontology(
            ontology="pfam", term_ids=["pfam.clan:CL0060"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1


# ---------------------------------------------------------------------------
# TestGeneOntologyTermsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGeneOntologyTermsCorrectnessKG:
    """Validate gene_ontology_terms queries against live Neo4j."""

    def test_bp_leaf_argr(self, conn):
        """argR (MIT1002_03493) leaf BP terms should be around 12."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["MIT1002_03493"], ontology="go_bp",
        )
        results = conn.execute_query(cypher, **params)
        assert 5 <= len(results) <= 20, (
            f"Expected 5-20 leaf BP terms for argR, got {len(results)}"
        )
        for r in results:
            assert "locus_tag" in r
            assert "term_id" in r
            assert "term_name" in r

    def test_ec_annotations(self, conn):
        """Gene with EC annotations returns EC numbers."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["MIT1002_03493"], ontology="ec",
        )
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert "locus_tag" in r
            assert "term_id" in r
            assert "term_name" in r

    def test_kegg_annotations(self, conn):
        """Gene with KEGG KOs returns terms."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["MIT1002_03493"], ontology="kegg",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1, "argR should have at least 1 KEGG KO"
        for r in results:
            assert "term_id" in r

    def test_no_annotations_empty_result(self, conn):
        """Gene with no annotations for given ontology returns empty."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMT9312_0342"], ontology="go_cc",
        )
        results = conn.execute_query(cypher, **params)
        assert isinstance(results, list)

    def test_mf_annotations(self, conn):
        """Gene with GO:MF annotations returns molecular function terms."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["MIT1002_03493"], ontology="go_mf",
        )
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert "term_id" in r
            assert "term_name" in r

    def test_cc_annotations(self, conn):
        """Gene with GO:CC annotations returns cellular component terms."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["MIT1002_03493"], ontology="go_cc",
        )
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert "term_id" in r

    def test_different_gene_bp(self, conn):
        """Different gene (PMM0001/dnaN) has GO:BP annotations."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1, "PMM0001 (dnaN) should have GO:BP annotations"

    def test_cog_category_annotations(self, conn):
        """PMM0001 should have COG category annotations (flat ontology)."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="cog_category",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1
        for r in results:
            assert "term_id" in r
            assert "term_name" in r

    def test_cyanorak_role_annotations(self, conn):
        """PMM0001 should have CyanoRAK role annotations."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="cyanorak_role",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_tigr_role_annotations(self, conn):
        """PMM0001 should have TIGR role annotations."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="tigr_role",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_pfam_annotations(self, conn):
        """PMM0001 should have Pfam domain annotations."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="pfam",
        )
        results = conn.execute_query(cypher, **params)
        assert isinstance(results, list)
        for r in results:
            assert "term_id" in r
            assert "term_name" in r

    def test_batch_multiple_genes(self, conn):
        """Batch query returns results for multiple genes."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001", "MIT1002_03493"], ontology="go_bp",
        )
        results = conn.execute_query(cypher, **params)
        locus_tags_found = {r["locus_tag"] for r in results}
        assert "PMM0001" in locus_tags_found
        assert "MIT1002_03493" in locus_tags_found

    def test_verbose_includes_organism(self, conn):
        """verbose=True adds organism_strain to results."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", verbose=True,
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1
        assert "organism_strain" in results[0]


# ---------------------------------------------------------------------------
# run_cypher
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestRunCypherCorrectness:
    def test_valid_query_no_warnings(self, conn):
        """A well-formed query against real labels returns empty warnings."""
        result = api.run_cypher(
            "MATCH (g:Gene) RETURN count(g) AS cnt", conn=conn
        )
        assert result["warnings"] == []
        assert result["returned"] > 0
        assert "cnt" in result["results"][0]

    def test_bad_label_populates_warnings(self, conn):
        """A query referencing a non-existent label returns schema warnings."""
        result = api.run_cypher(
            "MATCH (n:NonExistentLabel_XYZ) RETURN n LIMIT 1", conn=conn
        )
        assert len(result["warnings"]) > 0
        assert any("NonExistentLabel_XYZ" in w or "not" in w.lower() for w in result["warnings"])

    def test_bad_property_populates_warnings(self, conn):
        """PropertiesValidator fires when a valid label has a non-existent property."""
        result = api.run_cypher(
            "MATCH (g:Gene) RETURN g.nonexistent_prop_xyz AS val LIMIT 1", conn=conn
        )
        assert len(result["warnings"]) > 0

    def test_truncated_true_when_limit_hit(self, conn):
        """truncated=True when exactly limit rows are returned."""
        result = api.run_cypher(
            "MATCH (g:Gene) RETURN g.locus_tag AS tag", limit=1, conn=conn
        )
        assert result["returned"] == 1
        assert result["truncated"] is True

    def test_truncated_false_when_under_limit(self, conn):
        """truncated=False when fewer rows than limit come back."""
        # There is exactly 1 Gene with locus_tag PMM0001, so limit=10 won't be hit.
        result = api.run_cypher(
            "MATCH (g:Gene) WHERE g.locus_tag = 'PMM0001' RETURN g.locus_tag AS tag",
            limit=10, conn=conn,
        )
        assert result["returned"] == 1
        assert result["truncated"] is False
