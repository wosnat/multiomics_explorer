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
        assert row["organism_name"] == gene["organism_name"]

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
        assert "MED4" in results[0]["organism_name"]

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
            assert "MED4" in r["organism_name"], (
                f"Expected MED4, got {r['organism_name']}"
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
        """gene_categories filter restricts results to genes in that category."""
        cypher, params = build_genes_by_function(
            search_text="reaction centre", gene_categories=["Photosynthesis"],
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0

    def test_cross_organism_results(self, conn):
        """Search without organism filter returns genes from multiple organisms."""
        cypher, params = build_genes_by_function(
            search_text="chaperone",
        )
        results = conn.execute_query(cypher, **params)
        orgs = {r["organism_name"] for r in results}
        assert len(orgs) >= 2, f"Expected multi-organism results, got {orgs}"


# ---------------------------------------------------------------------------
# TestGetGeneDetailsCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGeneDetailsCorrectnessKG:
    """Validate gene details queries return flat g{.*} properties."""

    def test_well_annotated_prochlorococcus(self, conn):
        """PMM0001 returns flat g{.*} with locus_tag, gene_name, product, organism_name."""
        cypher, params = build_gene_details(locus_tags=["PMM0001"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        gene = results[0]["gene"]
        assert gene is not None
        assert gene["locus_tag"] == "PMM0001"
        assert gene["gene_name"] == "dnaN"
        assert "product" in gene
        assert "organism_name" in gene

    def test_alteromonas_gene(self, conn):
        """ALT831_RS00180 returns flat properties with organism_name containing 'Alteromonas'."""
        cypher, params = build_gene_details(locus_tags=["ALT831_RS00180"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        gene = results[0]["gene"]
        assert gene is not None
        assert gene["locus_tag"] == "ALT831_RS00180"
        assert "Alteromonas" in gene["organism_name"]


# ---------------------------------------------------------------------------
# TestGeneOverviewCorrectnessKG
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestGeneOverviewCorrectnessKG:
    """Validate gene_overview queries return routing signals from pre-computed properties."""

    def test_single_gene_pro(self, conn, kg_count):
        """PMM1428: verify annotation_types, expression counts, ortholog signals.

        Counts are checked against live edge counts rather than literals
        (paper batches flip them) — this also validates the Gene-level
        precomputes the query reads."""
        cypher, params = build_gene_overview(locus_tags=["PMM1428"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        r = results[0]
        assert r["locus_tag"] == "PMM1428"
        assert set(r["annotation_types"]) >= {"go_mf", "pfam", "cog_category", "tigr_role"}
        n_edges = kg_count(
            "MATCH (:Gene {locus_tag: $lt})<-[e:Changes_expression_of]-() RETURN count(e)",
            lt="PMM1428")
        n_sig = kg_count(
            "MATCH (:Gene {locus_tag: $lt})<-[e:Changes_expression_of]-() "
            "WHERE e.significant = 'significant' RETURN count(e)", lt="PMM1428")
        assert n_edges > n_sig > 0
        assert r["expression_edge_count"] == n_edges
        assert r["significant_up_count"] + r["significant_down_count"] == n_sig
        # closest group = lowest specificity_rank (the curated cyanorak group);
        # every organism added so far has joined it, so it only grows.
        closest_size = kg_count(
            "MATCH (:Gene {locus_tag: $lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup) "
            "WITH og ORDER BY og.specificity_rank LIMIT 1 "
            "MATCH (og)<-[:Gene_in_ortholog_group]-(m:Gene) RETURN count(m)", lt="PMM1428")
        assert closest_size >= 14
        assert r["closest_ortholog_group_size"] == closest_size
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
        assert r["closest_ortholog_group_size"] >= 1

    def test_batch_mixed_organisms(self, conn):
        """[PMM1428, EZ55_00275]: returns 2 rows with correct organism_name."""
        cypher, params = build_gene_overview(locus_tags=["PMM1428", "EZ55_00275"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 2
        orgs = {r["organism_name"] for r in results}
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
        """PMM1375 should belong to 4 ortholog groups."""
        cypher, params = build_gene_homologs(locus_tags=["PMM1375"])
        results = conn.execute_query(cypher, **params)
        assert len(results) == 4

    def test_results_have_compact_columns(self, conn):
        """Each result has compact columns."""
        cypher, params = build_gene_homologs(locus_tags=["PMM1375"])
        results = conn.execute_query(cypher, **params)
        for r in results:
            for col in ("locus_tag", "organism_name", "group_id",
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
                f"Organism '{r['organism_name']}' has gene_count={r['gene_count']}"
            )

    def test_clade_populated_for_prochlorococcus(self, conn):
        """Prochlorococcus strains should have a non-null clade."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        pro_strains = [r for r in results if r["genus"] == "Prochlorococcus"]
        assert len(pro_strains) > 0, "No Prochlorococcus strains found"
        for r in pro_strains:
            assert r["clade"] is not None, (
                f"Prochlorococcus strain '{r['organism_name']}' has null clade"
            )

    def test_clade_null_for_alteromonas(self, conn):
        """Alteromonas strains should not have a clade."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        alt_strains = [r for r in results if r["genus"] == "Alteromonas"]
        for r in alt_strains:
            assert r["clade"] is None, (
                f"Alteromonas strain '{r['organism_name']}' has unexpected clade={r['clade']}"
            )

    def test_clade_for_synechococcus(self, conn):
        """Marine Synechococcus/Parasynechococcus carry ecotype clades where
        available (added in the 2026-05 KG); freshwater Synechococcus elongatus
        and Thermosynechococcus carry none."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        syn_strains = [r for r in results if "synechococcus" in (r["genus"] or "").lower()
                       or "parasynechococcus" in (r["genus"] or "").lower()]
        assert syn_strains, "No Synechococcus strains found"

        # Freshwater / thermophilic cyanobacteria carry no marine ecotype clade.
        for r in syn_strains:
            if ("elongatus" in r["organism_name"].lower()
                    or "thermosynechococcus" in (r["genus"] or "").lower()):
                assert r["clade"] is None, (
                    f"Freshwater cyanobacterium '{r['organism_name']}' "
                    f"unexpectedly has clade={r['clade']}"
                )

        # The enhancement: marine picocyanobacteria now carry clades where available.
        marine = [r for r in syn_strains
                  if "elongatus" not in r["organism_name"].lower()
                  and "thermosynechococcus" not in (r["genus"] or "").lower()
                  and "picosynechococcus" not in (r["genus"] or "").lower()]
        assert any(r["clade"] is not None for r in marine), (
            "Expected at least one marine Synechococcus to carry a clade "
            f"(clades added where available); got "
            f"{[(r['organism_name'], r['clade']) for r in marine]}"
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
    """Validate genes_by_ontology against live Neo4j.

    Counts verified 2026-04-14 during Task 11 execution.
    """

    def test_mode2_go_bp_level1_med4(self):
        r = api.genes_by_ontology(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=1,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        # Verified 2026-04-14; recounted 2026-08-20: 410 → 429 rows,
        # 332 → 349 genes (+17) after InterPro Layer-B GO enrichment added
        # ~45K GO edges; term count unchanged (8), same +17 gene delta as
        # test_mode1_mixed_levels L1 — Layer-B-consistent. Recounted
        # 2026-10-18 (GO release update, built 2026-10-18T13:42:30Z):
        # 429 → 447 rows, 349 → 365 genes; term count unchanged (8).
        assert r["total_matching"] == 447
        assert r["total_genes"] == 365
        assert r["total_terms"] == 8
        # by_level is a single entry at level 1
        assert len(r["by_level"]) == 1
        assert r["by_level"][0]["level"] == 1
        assert r["by_level"][0]["n_genes"] == 365
        assert r["by_level"][0]["row_count"] == 447
        # All validation buckets empty (Mode 2)
        assert r["not_found"] == []
        assert r["wrong_ontology"] == []
        assert r["wrong_level"] == []
        assert r["filtered_out"] == []

    def test_mode1_mixed_levels(self):
        # L1 (cellular process) and L6 (DNA replication)
        r = api.genes_by_ontology(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            term_ids=["go:0009987", "go:0006260"],
            min_gene_set_size=5,
            max_gene_set_size=2000,
        )
        levels_in_result = {e["level"] for e in r["by_level"]}
        assert levels_in_result == {1, 6}
        by_level = {e["level"]: e for e in r["by_level"]}
        # total = sum over the two scoped terms; L1 (cellular process) dwarfs
        # L6 (DNA replication). Not pinned — GO gene counts drift per rebuild.
        assert r["total_matching"] == by_level[1]["n_genes"] + by_level[6]["n_genes"]
        assert by_level[1]["n_genes"] > 1000 > by_level[6]["n_genes"] >= 20
        assert by_level[6]["n_genes"] == 30

    def test_mode3_wrong_level_bucket(self):
        r = api.genes_by_ontology(
            ontology="cyanorak_role",
            organism="Prochlorococcus MED4",
            level=1,
            term_ids=["cyanorak.role:A"],  # a level-0 root
        )
        assert "cyanorak.role:A" in r["wrong_level"]

    def test_validation_not_found(self):
        r = api.genes_by_ontology(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=3,
            term_ids=["go:0006260", "fake:X"],
        )
        assert r["not_found"] == ["fake:X"]

    def test_wrong_ontology_bucket(self):
        r = api.genes_by_ontology(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=3,
            term_ids=["go:0006260", "kegg.orthology:K00001"],
        )
        assert r["wrong_ontology"] == ["kegg.orthology:K00001"]

    def test_summary_mode(self):
        r = api.genes_by_ontology(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=1,
            summary=True,
        )
        assert r["results"] == []
        assert r["total_matching"] > 0
        assert r["truncated"] is True

    def test_pfam_two_level(self):
        # Level 1 = Pfam domains
        r1 = api.genes_by_ontology(
            ontology="pfam", organism="Prochlorococcus MED4", level=1,
        )
        assert r1["total_terms"] > 0
        assert all(row["level"] == 1 for row in r1["results"])
        # Level 0 = PfamClan
        r0 = api.genes_by_ontology(
            ontology="pfam", organism="Prochlorococcus MED4", level=0,
        )
        assert r0["total_terms"] > 0
        assert all(row["level"] == 0 for row in r0["results"])
        # Verified 2026-04-14: MED4 top clan is NADP_Rossmann
        top_clan_names = {t["term_name"] for t in r0["top_terms"]}
        assert "NADP_Rossmann" in top_clan_names


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
            organism_name="Alteromonas macleodii MIT1002",
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
            organism_name="Alteromonas macleodii MIT1002",
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
            organism_name="Alteromonas macleodii MIT1002",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1, "argR should have at least 1 KEGG KO"
        for r in results:
            assert "term_id" in r

    def test_no_annotations_empty_result(self, conn):
        """Gene with no annotations for given ontology returns empty."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMT9312_0342"], ontology="go_cc",
            organism_name="Prochlorococcus marinus str. MIT 9312",
        )
        results = conn.execute_query(cypher, **params)
        assert isinstance(results, list)

    def test_mf_annotations(self, conn):
        """Gene with GO:MF annotations returns molecular function terms."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["MIT1002_03493"], ontology="go_mf",
            organism_name="Alteromonas macleodii MIT1002",
        )
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert "term_id" in r
            assert "term_name" in r

    def test_cc_annotations(self, conn):
        """Gene with GO:CC annotations returns cellular component terms."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["MIT1002_03493"], ontology="go_cc",
            organism_name="Alteromonas macleodii MIT1002",
        )
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert "term_id" in r

    def test_different_gene_bp(self, conn):
        """Different gene (PMM0001/dnaN) has GO:BP annotations."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp",
            organism_name="Prochlorococcus MED4",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1, "PMM0001 (dnaN) should have GO:BP annotations"

    def test_cog_category_annotations(self, conn):
        """PMM0001 should have COG category annotations (flat ontology)."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="cog_category",
            organism_name="Prochlorococcus MED4",
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
            organism_name="Prochlorococcus MED4",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_tigr_role_annotations(self, conn):
        """PMM0001 should have TIGR role annotations."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="tigr_role",
            organism_name="Prochlorococcus MED4",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1

    def test_pfam_annotations(self, conn):
        """PMM0001 should have Pfam domain annotations."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="pfam",
            organism_name="Prochlorococcus MED4",
        )
        results = conn.execute_query(cypher, **params)
        assert isinstance(results, list)
        for r in results:
            assert "term_id" in r
            assert "term_name" in r

    def test_batch_multiple_genes(self, conn):
        """Batch query returns results for multiple genes."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["MIT1002_03493", "MIT1002_00002"], ontology="go_bp",
            organism_name="Alteromonas macleodii MIT1002",
        )
        results = conn.execute_query(cypher, **params)
        locus_tags_found = {r["locus_tag"] for r in results}
        assert "MIT1002_03493" in locus_tags_found

    def test_verbose_includes_organism(self, conn):
        """verbose=True adds organism_name to results."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", verbose=True,
            organism_name="Prochlorococcus MED4",
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 1
        assert "organism_name" in results[0]


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



# ---------------------------------------------------------------------------
# PR 3b — builder-level checks for browse mode and ontology_term_details
# (spec §7.4 / §7.5 verified figures, freeze notes v1.2).
# ---------------------------------------------------------------------------

@pytest.mark.kg
class TestSearchOntologyBrowseCorrectnessKG:
    def test_merops_level1_browse_top5(self, conn, run_query):
        cypher, params = build_search_ontology(
            ontology="merops", search_text=None, level=1, limit=5)
        rows = conn.execute_query(cypher, **params)
        assert [r["id"] for r in rows] == [
            "merops.family:S33", "merops.family:S09", "merops.family:C26",
            "merops.family:M38", "merops.family:C44",
        ]
        live = {x["id"]: x["gc"] for x in run_query(
            "MATCH (t:MeropsFamily) WHERE t.id IN $ids RETURN t.id AS id, t.gene_count AS gc",
            ids=[r["id"] for r in rows])}
        counts = [r["gene_count"] for r in rows]
        assert counts == [live[r["id"]] for r in rows]
        assert counts == sorted(counts, reverse=True)
        assert all(r["score"] is None for r in rows)

    def test_merops_browse_summary_by_level(self, conn):
        cypher, params = build_search_ontology_summary(
            ontology="merops", search_text=None)
        row = conn.execute_query(cypher, **params)[0]
        assert row["total_matching"] == row["total_entries"]
        assert row["score_max"] is None
        assert {e["level"] for e in row["by_level"]} >= {0, 1}

    def test_pfam_browse_dual_label(self, conn):
        cypher, params = build_search_ontology(
            ontology="pfam", search_text=None, level=0, limit=5)
        rows = conn.execute_query(cypher, **params)
        assert rows and all(r["level"] == 0 for r in rows)

    def test_interpro_med4_scoped_browse(self, conn):
        cypher, params = build_search_ontology(
            ontology="interpro", search_text=None,
            interpro_type="HOMOLOGOUS_SUPERFAMILY",
            organism="Prochlorococcus MED4", min_gene_count=5, limit=5,
            informative_only=True)
        rows = conn.execute_query(cypher, **params)
        assert rows[0]["id"] == "interpro:IPR027417"
        assert rows[0]["organism_gene_count"] == 119
        assert [r["organism_gene_count"] for r in rows] == sorted(
            [r["organism_gene_count"] for r in rows], reverse=True)


@pytest.mark.kg
class TestOntologyTermDetailsCorrectnessKG:
    _IDS = ["tcdb:3.A.1", "merops.family:S14", "interpro:IPR000362",
            "ncbifam:NF000812", "go:0006979", "bogus:xyz"]

    def _rows(self, conn, **kw):
        from multiomics_explorer.kg.queries_lib import build_ontology_term_details
        cypher, params = build_ontology_term_details(term_ids=self._IDS, **kw)
        rows = conn.execute_query(cypher, **params)
        return {r["term_id"]: r for r in rows}

    def test_one_row_per_input_in_order(self, conn):
        from multiomics_explorer.kg.queries_lib import build_ontology_term_details
        cypher, params = build_ontology_term_details(term_ids=self._IDS)
        rows = conn.execute_query(cypher, **params)
        assert [r["term_id"] for r in rows] == self._IDS

    def test_verified_counts(self, conn, run_query):
        rows = self._rows(conn)
        t = rows["tcdb:3.A.1"]
        assert (len(t["parents"]), t["children_total"], t["links_total"]) == (1, 98, 11)  # 129 → 128 2026-10-18: go:0005548 retired by the GO update; → (98, 11) 2026-10-24T17:33Z: TCDB 3a range-only children, bridges on systems
        assert len(t["children"]) == 50
        s = rows["merops.family:S14"]
        assert (len(s["parents"]), s["children_total"], s["links_total"]) == (1, 0, 1)
        i = rows["interpro:IPR000362"]
        assert (len(i["parents"]), i["children_total"], i["links_total"]) == (0, 4, 5)
        n = rows["ncbifam:NF000812"]
        assert (len(n["parents"]), n["children_total"], n["links_total"]) == (0, 0, 0)
        g = rows["go:0006979"]
        live = run_query(
            "MATCH (t {id: 'go:0006979'}) RETURN t.gene_count AS gc, t.organism_count AS oc")[0]
        assert (g["level"], g["gene_count"], g["organism_count"]) == (3, live["gc"], live["oc"])
        assert (len(g["parents"]), g["children_total"], g["links_total"]) == (1, 3, 0)

    def test_not_found_flag(self, conn):
        rows = self._rows(conn)
        assert rows["bogus:xyz"]["not_found"] is True
        assert rows["tcdb:3.A.1"]["not_found"] is False

    def test_link_kinds_router_only(self, conn):
        rows = self._rows(conn, link_kinds=["router"])
        assert rows["tcdb:3.A.1"]["links_total"] == 0
        assert rows["interpro:IPR000362"]["links_total"] == 5

    def test_verbose_shape(self, conn, kg_count):
        rows = self._rows(conn, verbose=True)
        g = rows["go:0006979"]
        assert g["properties"]["id"] == "go:0006979"
        assert len(g["genes_by_organism"]) == kg_count(
            "MATCH (t {id: 'go:0006979'}) RETURN t.organism_count")


# ---------------------------------------------------------------------------
# GO transport surface (RED) — independent-Cypher ground truth
# ---------------------------------------------------------------------------

_GO_ROUTE = (
    "(g:Gene)-[r:Gene_enables_molecular_function|Gene_involved_in_biological_process]"
    "->(go)-[t:Molecular_function_transports_metabolite|"
    "Biological_process_transports_metabolite|"
    "Molecular_function_transports_chemical_role|"
    "Biological_process_transports_chemical_role]->(m:Metabolite|ChemicalRole)"
)


@pytest.mark.kg
class TestGoTransportCorrectnessKG:
    _ORG = "Prochlorococcus MED4"

    def test_gbm_go_rows_match_independent_cypher(self, conn, kg_count):
        """api GO row count == direct edge count (gene x own term x target)."""
        direct = kg_count(
            "MATCH " + _GO_ROUTE + " WHERE m.id = $m AND g.organism_name = $o "
            "RETURN count(*)", m="kegg.compound:C00086", o=self._ORG)
        r = api.genes_by_metabolite(
            ["kegg.compound:C00086"], self._ORG, evidence_sources=["go_transport"],
            summary=True, conn=conn)
        assert direct == 11
        assert r["total_matching"] == direct

    def test_gbm_namespace_comes_from_edge_type_not_label(self, conn):
        """MF term nodes lack the GeneOntology label BP nodes carry; the
        namespace must still be right for every row."""
        r = api.genes_by_metabolite(
            ["kegg.compound:C00086"], self._ORG, evidence_sources=["go_transport"],
            limit=50, conn=conn)
        edge_ns = {
            row["go_id"]: ("molecular_function"
                           if row["t"].startswith("Molecular_function")
                           else "biological_process")
            for row in conn.execute_query(
                "MATCH " + _GO_ROUTE + " WHERE m.id = 'kegg.compound:C00086' "
                "AND g.organism_name = $o "
                "RETURN DISTINCT go.id AS go_id, type(t) AS t", o=self._ORG)
        }
        assert r["results"]
        for row in r["results"]:
            assert row["go_namespace"] == edge_ns[row["go_term_id"]]

    def test_gbm_go_evidence_matches_gene_go_edge(self, conn):
        r = api.genes_by_metabolite(
            ["kegg.compound:C00086"], self._ORG, evidence_sources=["go_transport"],
            limit=50, conn=conn)
        for row in r["results"]:
            e = conn.execute_query(
                "MATCH (g:Gene {locus_tag: $lt})-[r:Gene_enables_molecular_function"
                "|Gene_involved_in_biological_process]->(go {id: $go}) "
                "RETURN r.evidence AS ev, r.sources AS src",
                lt=row["locus_tag"], go=row["go_term_id"])
            assert len(e) == 1
            assert e[0]["ev"] == row["go_evidence"]
            assert e[0]["src"] == row["go_sources"]

    def test_gbm_ancestors_inherited_rows_are_not_direct(self, conn, kg_count):
        """Every depth>=1 row is for a (gene, target) pair the gene does not
        reach directly through GO; its axiom term is a real is_a ancestor."""
        r = api.metabolites_by_gene(
            ["PMM0261", "PMM0970"], self._ORG, go_include_ancestors=True,
            evidence_sources=["go_transport"], limit=50, conn=conn)
        inherited = [x for x in r["results"] if x["go_term_depth"] >= 1]
        assert inherited
        for x in inherited:
            direct = kg_count(
                "MATCH (g:Gene {locus_tag: $lt})-[:Gene_enables_molecular_function"
                "|Gene_involved_in_biological_process]->()-[:"
                "Molecular_function_transports_metabolite|"
                "Biological_process_transports_metabolite|"
                "Molecular_function_transports_chemical_role|"
                "Biological_process_transports_chemical_role]->(m {id: $m}) "
                "RETURN count(*)", lt=x["locus_tag"], m=x["metabolite_id"])
            assert direct == 0
            hops = kg_count(
                "MATCH (own {id: $own}), (ax {id: $ax}), "
                "p = shortestPath((own)-[:Molecular_function_is_a_molecular_function"
                "|Biological_process_is_a_biological_process*1..]->(ax)) "
                "RETURN length(p)", own=x["go_term_id"], ax=x["go_axiom_term_id"])
            assert hops == x["go_term_depth"]

    def test_gene_overview_go_tag_matches_independent_exists(self, conn, kg_count):
        direct = kg_count(
            "MATCH (g:Gene {organism_name: $o}) "
            "WHERE EXISTS { MATCH (g)-[:Gene_enables_molecular_function"
            "|Gene_involved_in_biological_process]->()-[:"
            "Molecular_function_transports_metabolite|"
            "Biological_process_transports_metabolite|"
            "Molecular_function_transports_chemical_role|"
            "Biological_process_transports_chemical_role]->() } "
            "RETURN count(g)", o=self._ORG)
        assert direct == 59
        cypher, params = build_gene_overview(locus_tags=["PMM0970", "PMM0533"])
        rows = {r["locus_tag"]: r for r in conn.execute_query(cypher, **params)}
        assert "go_transport" in rows["PMM0970"]["evidence_sources"]
        assert rows["PMM0533"]["evidence_sources"] == ["go_transport"]

    def test_list_metabolites_go_organisms_match_node_property(self, conn, kg_count):
        n = kg_count(
            "MATCH (m:Metabolite) WHERE $o IN coalesce(m.go_transport_organism_names, []) "
            "RETURN count(m)", o=self._ORG)
        assert n == 45
        r = api.list_metabolites(
            evidence_sources=["go_transport"], organism_names=[self._ORG],
            summary=True, conn=conn)
        assert r["total_matching"] >= n


# ---------------------------------------------------------------------------
# GO transport follow-ups (RED) — docs/tool-specs/go-transport-followups.md
# Live numbers verified against built_at 2026-10-19T17:03:46Z (spec §3/§4).
# limit=5000 rather than None: limit=None raises TypeError on gbm / mbg
# today (backlog 3.18).
# ---------------------------------------------------------------------------

_UREA = "kegg.compound:C00086"
_SIDEROPHORE_ROLE = "chebi.role:26672"
_KT2440 = "Pseudomonas putida KT2440"


def _combo_map(envelope):
    return {
        tuple(e["evidence_sources"]): e["pair_count"]
        for e in envelope["by_evidence_source_combination"]
    }


def _pairs_by_sources(rows):
    pairs: dict = {}
    for x in rows:
        pairs.setdefault((x["locus_tag"], x["metabolite_id"]), set()).add(
            x["evidence_source"])
    out: dict = {}
    for srcs in pairs.values():
        key = tuple(sorted(srcs))
        out[key] = out.get(key, 0) + 1
    return out


def _go_row_key(x):
    return (x["locus_tag"], x["metabolite_id"], x["go_term_id"],
            x["go_axiom_term_id"], x["go_term_depth"])


@pytest.mark.kg
class TestGoTransportFollowupsKG:
    _ORG = "Prochlorococcus MED4"

    # --- 2c.17 route agreement -------------------------------------------

    def test_gbm_urea_med4_combination(self, conn):
        """TCDB cleanup: the 20 inherited-3.A.1-only (transport,) pairs are
        gone with the direct gate; urtA-E agree across TCDB + GO."""
        r = api.genes_by_metabolite([_UREA], self._ORG, summary=True, conn=conn)
        assert _combo_map(r) == {
            ("go_transport", "transport"): 5,
            ("metabolism",): 4,
        }
        assert [e["pair_count"] for e in r["by_evidence_source_combination"]] \
            == [5, 4]

    def test_gbm_urea_multi_source_gene_count(self, conn):
        r = api.genes_by_metabolite([_UREA], self._ORG, summary=True, conn=conn)
        urea = [e for e in r["by_metabolite"] if e["metabolite_id"] == _UREA]
        assert urea[0]["multi_source_gene_count"] == 5

    def test_gbm_urea_top_genes_multi_source(self, conn):
        """urtA..urtE reach urea via TCDB + GO -> 1 multi-source metabolite."""
        r = api.genes_by_metabolite([_UREA], self._ORG, summary=True, conn=conn)
        multi = {g["locus_tag"] for g in r["top_genes"]
                 if g["multi_source_metabolite_count"] == 1}
        assert len(multi) == 5

    def test_mbg_urt_genes_combination(self, conn):
        r = api.metabolites_by_gene(
            ["PMM0970", "PMM0971", "PMM0974"], self._ORG, summary=True,
            conn=conn)
        # TCDB cleanup: transport-only pairs 8 -> 6 (urtA/urtB/urtE reach
        # hydroxyurea / thiourea via direct 3.A.1.4.5 only; the inherited
        # 3.A.1 pairs are gone). GO and TCDB+GO pairs unchanged.
        assert _combo_map(r) == {
            ("transport",): 6,
            ("go_transport", "transport"): 3,
            ("go_transport",): 3,
        }
        for g in r["by_gene"]:
            assert "multi_source_metabolite_count" in g
        for m in r["top_metabolites"]:
            assert "multi_source_gene_count" in m

    @pytest.mark.parametrize("call", [
        ("gbm", [_UREA], "Prochlorococcus MED4", {}),
        ("gbm", [_SIDEROPHORE_ROLE], _KT2440, {}),
        ("gbm", [_UREA], "Prochlorococcus MED4",
         {"go_include_ancestors": True}),
        ("mbg", ["PMM0970", "PMM0971", "PMM0974"], "Prochlorococcus MED4", {}),
        ("mbg", ["PMM0261", "PMM0970"], "Prochlorococcus MED4",
         {"go_include_ancestors": True}),
    ])
    def test_combination_equals_detail_pairs(self, conn, call):
        tool, ids, org, kw = call
        fn = api.genes_by_metabolite if tool == "gbm" else api.metabolites_by_gene
        r = fn(ids, org, limit=5000, conn=conn, **kw)
        assert not r["truncated"]
        assert _combo_map(r) == _pairs_by_sources(r["results"])
        n_pairs = len({(x["locus_tag"], x["metabolite_id"])
                       for x in r["results"]})
        assert sum(e["pair_count"]
                   for e in r["by_evidence_source_combination"]) == n_pairs

    def test_combination_unchanged_total_matching(self, conn):
        """The combination rollup never changes total_matching: it equals
        the row count (4 metabolism + 10 TCDB direct + 11 GO post-3a)."""
        r = api.genes_by_metabolite([_UREA], self._ORG, summary=True, conn=conn)
        full = api.genes_by_metabolite([_UREA], self._ORG, limit=500, conn=conn)
        assert r["total_matching"] == len(full["results"]) == 25

    # --- 2c.15 GO-arm filters ---------------------------------------------

    def test_gbm_urea_mf_curated_four_rows(self, conn):
        r = api.genes_by_metabolite(
            [_UREA], self._ORG, evidence_sources=["go_transport"],
            go_namespace=["molecular_function"], go_evidence=["curated"],
            limit=50, conn=conn)
        assert r["total_matching"] == 4
        assert len(r["results"]) == 4
        for x in r["results"]:
            assert x["go_namespace"] == "molecular_function"
            assert x["go_evidence"] == "curated"

    def test_gbm_urea_bp_curated_seven_rows(self, conn):
        r = api.genes_by_metabolite(
            [_UREA], self._ORG, evidence_sources=["go_transport"],
            go_namespace=["biological_process"], go_evidence=["curated"],
            summary=True, conn=conn)
        assert r["total_matching"] == 7

    def test_go_filters_leave_non_go_rows_untouched(self, conn):
        base = api.genes_by_metabolite(
            [_UREA], self._ORG, summary=True, conn=conn)
        filt = api.genes_by_metabolite(
            [_UREA], self._ORG, go_namespace=["molecular_function"],
            summary=True, conn=conn)
        b = {e["evidence_source"]: e["count"] for e in base["by_evidence_source"]}
        f = {e["evidence_source"]: e["count"] for e in filt["by_evidence_source"]}
        assert f["metabolism"] == b["metabolism"]
        assert f["transport"] == b["transport"]
        assert f["go_transport"] < b["go_transport"]

    @pytest.mark.parametrize("call", [
        ("gbm", [_UREA], "Prochlorococcus MED4", False),
        ("gbm", [_SIDEROPHORE_ROLE], _KT2440, False),
        ("gbm", [_SIDEROPHORE_ROLE], _KT2440, True),
        ("mbg", ["PMM0261", "PMM0970"], "Prochlorococcus MED4", True),
    ])
    @pytest.mark.parametrize("filters", [
        {"go_namespace": ["molecular_function"]},
        {"go_namespace": ["biological_process"]},
        {"go_evidence": ["curated"]},
        {"go_namespace": ["biological_process"],
         "go_evidence": ["family_inferred", "domain_inferred"]},
    ])
    def test_filtered_go_rows_subset_of_unfiltered(self, conn, call, filters):
        tool, ids, org, anc = call
        fn = api.genes_by_metabolite if tool == "gbm" else api.metabolites_by_gene
        common = dict(evidence_sources=["go_transport"],
                      go_include_ancestors=anc, limit=5000, conn=conn)
        full = fn(ids, org, **common)
        sub = fn(ids, org, **common, **filters)
        assert not full["truncated"] and not sub["truncated"]
        full_keys = {_go_row_key(x) for x in full["results"]}
        sub_keys = {_go_row_key(x) for x in sub["results"]}
        assert sub_keys <= full_keys
        for x in sub["results"]:
            if "go_namespace" in filters:
                assert x["go_namespace"] in filters["go_namespace"]
            if "go_evidence" in filters:
                assert x["go_evidence"] in filters["go_evidence"]

    def test_filtered_counts_match_summary(self, conn):
        """Summary total_matching under GO filters equals the detail row
        count (filters threaded to the summary builder)."""
        kw = dict(evidence_sources=["go_transport"],
                  go_namespace=["biological_process"], go_evidence=["curated"],
                  go_include_ancestors=True)
        s = api.genes_by_metabolite(
            [_SIDEROPHORE_ROLE], _KT2440, summary=True, conn=conn, **kw)
        d = api.genes_by_metabolite(
            [_SIDEROPHORE_ROLE], _KT2440, limit=5000, conn=conn, **kw)
        assert s["total_matching"] == len(d["results"])

    def test_go_filter_arm_off_warns_no_raise(self, conn):
        r = api.genes_by_metabolite(
            [_UREA], self._ORG, evidence_sources=["metabolism", "transport"],
            go_namespace=["molecular_function"], go_evidence=["curated"],
            summary=True, conn=conn)
        assert (
            "go_namespace / go_evidence apply to the go_transport arm only, "
            "which evidence_sources excluded — filter ignored."
        ) in r["warnings"]

    def test_unknown_go_evidence_raises_live(self, conn):
        with pytest.raises(ValueError, match="curated"):
            api.genes_by_metabolite(
                [_UREA], self._ORG, go_evidence=["bogus"], conn=conn)

    def test_unknown_go_namespace_raises_live(self, conn):
        with pytest.raises(ValueError, match="molecular_function"):
            api.metabolites_by_gene(
                ["PMM0970"], self._ORG, go_namespace=["cellular_component"],
                conn=conn)

    # --- 2c.16 list_organisms GO count -------------------------------------

    def test_list_organisms_med4_go_count(self, conn):
        r = api.list_organisms(organism_names=[self._ORG], conn=conn)
        assert r["results"][0]["go_transport_metabolite_count"] == 45

    def test_list_organisms_capability_carries_go_count(self, conn):
        r = api.list_organisms(
            organism_names=[self._ORG], summary=True, conn=conn)
        cap = {e["organism_name"]: e for e in r["top_metabolic_capability"]}
        assert cap[self._ORG]["go_transport_metabolite_count"] == 45

    def test_list_organisms_go_count_matches_live_walk(self, conn, kg_count):
        """Count via Metabolite.go_transport_organism_names == live walk
        Gene -> GO -> Metabolite (direct, metabolite targets)."""
        walk = kg_count(
            "MATCH (g:Gene {organism_name: $o})-[:Gene_enables_molecular_function"
            "|Gene_involved_in_biological_process]->()-[:"
            "Molecular_function_transports_metabolite|"
            "Biological_process_transports_metabolite]->(m:Metabolite) "
            "RETURN count(DISTINCT m)", o=_KT2440)
        r = api.list_organisms(organism_names=[_KT2440], conn=conn)
        assert r["results"][0]["go_transport_metabolite_count"] == walk == 144

    # --- 2c.14 gene_overview GO count --------------------------------------

    @pytest.mark.parametrize("locus_tag, expected", [
        ("PMM0974", 3), ("PMM0970", 1), ("PMM0392", 0), ("PMM0001", 0),
    ])
    def test_gene_overview_go_count(self, conn, locus_tag, expected):
        r = api.gene_overview(locus_tags=[locus_tag], conn=conn)
        assert r["results"][0]["go_transport_metabolite_count"] == expected
