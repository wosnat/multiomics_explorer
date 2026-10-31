"""P1: Integration tests for MCP tool logic against live Neo4j.

These tests exercise the tool-level logic (query building + result handling)
without the MCP transport layer. They use the shared `conn` fixture from conftest.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP

from multiomics_explorer.mcp_server.tools import register_tools
from multiomics_explorer.kg.queries_lib import (
    build_gene_details,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_list_organisms,
    build_list_publications,
    build_list_publications_summary,
    build_resolve_gene,
    build_genes_by_function,
    TCDB_DIRECT_GATE_PREDICATE,
)
from multiomics_explorer.api import functions as api


@pytest.mark.kg
class TestKgSchema:
    def test_returns_nodes_and_relationships(self, conn):
        result = api.kg_schema(conn=conn)
        assert "Gene" in result["nodes"]
        assert len(result["relationships"]) > 0

    def test_gene_node_has_properties(self, conn):
        result = api.kg_schema(conn=conn)
        assert "properties" in result["nodes"]["Gene"]

    def test_default_call_reports_no_not_found(self, conn):
        result = api.kg_schema(conn=conn)
        assert result["not_found_labels"] == []
        assert result["not_found_relationship_types"] == []

    def test_labels_scopes_nodes_and_leaves_relationships_empty(self, conn):
        result = api.kg_schema(labels=["Gene"], section="nodes", conn=conn)
        assert set(result["nodes"]) == {"Gene"}
        assert result["relationships"] == {}
        assert "properties" in result["nodes"]["Gene"]
        assert result["not_found_labels"] == []

    def test_unknown_label_reported_not_found_and_excluded(self, conn):
        result = api.kg_schema(labels=["Gene", "NotARealLabelXYZ"], conn=conn)
        assert result["not_found_labels"] == ["NotARealLabelXYZ"]
        assert "Gene" in result["nodes"]
        assert "NotARealLabelXYZ" not in result["nodes"]

    def test_relationship_types_scopes_relationships_and_leaves_nodes_empty(self, conn):
        result = api.kg_schema(
            relationship_types=["Changes_expression_of"], section="relationships", conn=conn,
        )
        assert set(result["relationships"]) == {"Changes_expression_of"}
        assert result["nodes"] == {}
        assert result["not_found_relationship_types"] == []

    def test_unknown_relationship_type_reported_not_found_and_excluded(self, conn):
        result = api.kg_schema(relationship_types=["Changes_expression_of", "NotARealRelXYZ"], conn=conn)
        assert result["not_found_relationship_types"] == ["NotARealRelXYZ"]
        assert "Changes_expression_of" in result["relationships"]
        assert "NotARealRelXYZ" not in result["relationships"]

    def test_property_sampling_is_deterministic_across_calls(self, conn):
        """The controller-mandated ORDER BY fix: repeated calls against the
        same live KG must capture the same property set/types for a label,
        even one with polymorphic/optional properties."""
        first = api.kg_schema(labels=["Gene"], section="nodes", conn=conn)
        second = api.kg_schema(labels=["Gene"], section="nodes", conn=conn)
        assert first["nodes"]["Gene"] == second["nodes"]["Gene"]


@pytest.mark.kg
class TestGenesByFunction:
    def test_invalid_lucene_syntax_does_not_crash(self, conn):
        """Unbalanced brackets should trigger the Lucene escape fallback."""
        import re

        search_text = "DNA [repair"
        cypher, params = build_genes_by_function(search_text=search_text)
        try:
            results = conn.execute_query(cypher, **params)
        except Exception:
            # Retry with escaped Lucene chars (mirrors tools.py fallback logic)
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_genes_by_function(search_text=escaped)
            results = conn.execute_query(cypher, **params)
        # Should not raise — may return 0 or more results
        assert isinstance(results, list)

    def test_basic_search_returns_results(self, conn):
        cypher, params = build_genes_by_function(search_text="photosystem")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        assert "locus_tag" in results[0]


@pytest.mark.kg
class TestGeneHomologs:
    def test_detail_returns_flat_rows(self, conn):
        """build_gene_homologs returns flat gene×group rows."""
        cypher, params = build_gene_homologs(locus_tags=["PMM0845"])
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert r["locus_tag"] == "PMM0845"
            assert "group_id" in r
            assert "source" in r
            assert "consensus_product" in r
            assert "organism_name" in r

    def test_summary_returns_counts(self, conn):
        """build_gene_homologs_summary returns counts + breakdowns."""
        cypher, params = build_gene_homologs_summary(locus_tags=["PMM0845"])
        result = conn.execute_query(cypher, **params)[0]
        assert result["total_matching"] > 0
        assert len(result["by_organism"]) > 0
        assert len(result["by_source"]) > 0
        assert result["not_found"] == []
        assert result["no_groups"] == []

    def test_summary_not_found(self, conn):
        """Fake gene appears in not_found."""
        cypher, params = build_gene_homologs_summary(locus_tags=["FAKE_GENE_XYZ"])
        result = conn.execute_query(cypher, **params)[0]
        assert "FAKE_GENE_XYZ" in result["not_found"]


@pytest.mark.kg
class TestRunCypher:
    def test_valid_query_returns_results(self, conn):
        """Valid query returns envelope with rows and empty warnings."""
        result = api.run_cypher("MATCH (g:Gene) RETURN count(g) AS cnt", conn=conn)
        assert result["returned"] > 0
        assert result["warnings"] == []
        assert set(result.keys()) >= {"returned", "truncated", "warnings", "results"}

    def test_bad_label_produces_warnings(self, conn):
        """Query referencing a non-existent label returns non-empty warnings."""
        result = api.run_cypher(
            "MATCH (n:NonExistentLabel_XYZ) RETURN n LIMIT 1", conn=conn
        )
        assert len(result["warnings"]) > 0

    def test_write_query_raises_value_error(self, conn):
        """Write keywords raise ValueError before execution."""
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("CREATE (n:Gene {name: 'test'})", conn=conn)

    def test_syntax_error_raises_value_error(self, conn):
        """Syntax-invalid Cypher raises ValueError with a message."""
        with pytest.raises(ValueError, match="Syntax error"):
            api.run_cypher("MATC (n) RETURNN n LIMIT 1", conn=conn)


@pytest.mark.kg
class TestEdgeCases:
    def test_resolve_gene_empty_id(self, conn):
        cypher, params = build_resolve_gene(identifier="")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 0

    def test_gene_details_nonexistent(self, conn):
        cypher, params = build_gene_details(locus_tags=["FAKE_GENE_XYZ"])
        results = conn.execute_query(cypher, **params)
        assert results == []


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
        cypher, params = build_list_publications(treatment_type=["coculture"])
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

    def test_publication_dois_filter(self, conn):
        """publication_dois filter returns only the requested DOIs (case-
        insensitive). `not_found` surfaces unmatched DOIs."""
        result = api.list_publications(
            publication_dois=["10.1038/ISMEJ.2016.70", "10.9999/does-not-exist"],
            conn=conn,
        )
        assert result["total_matching"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["doi"].lower() == "10.1038/ismej.2016.70"
        assert result["not_found"] == ["10.9999/does-not-exist"]

    def test_empty_intersection_returns_zero_matching(self, conn):
        """Filter combinations that match zero publications return
        total_matching=0 cleanly (not IndexError). The summary builder uses
        OPTIONAL MATCH so the total_entries row survives an empty filter."""
        # Pair a real DOI with a non-matching organism to force empty intersection.
        result = api.list_publications(
            publication_dois=["10.1038/ismej.2016.70"],
            organism="DefinitelyNotARealOrganism",
            conn=conn,
        )
        assert result["total_matching"] == 0
        assert result["total_entries"] >= 15  # unfiltered count survives
        assert result["results"] == []
        assert result["not_found"] == []  # the DOI exists; it's filtered out

    def test_dm_rollups_present(self, conn):
        """Envelope keys by_value_kind, by_metric_type, by_compartment are returned."""
        result = api.list_publications(conn=conn)
        assert "by_value_kind" in result, "Missing by_value_kind envelope key"
        assert "by_metric_type" in result, "Missing by_metric_type envelope key"
        assert "by_compartment" in result, "Missing by_compartment envelope key"
        # At least some DMs exist in the KG (verified live 2026-04-27)
        assert isinstance(result["by_value_kind"], list)
        assert isinstance(result["by_metric_type"], list)
        assert isinstance(result["by_compartment"], list)
        assert len(result["by_value_kind"]) > 0, "by_value_kind is empty (expected DMs in KG)"

    def test_compartment_filter_narrows(self, conn):
        """vesicle filter returns fewer publications than unfiltered."""
        result_all = api.list_publications(conn=conn)
        result_vesicle = api.list_publications(compartment="vesicle", conn=conn)
        assert result_vesicle["total_matching"] <= result_all["total_matching"]
        # vesicle compartment has at least 1 publication (verified live 2026-04-27)
        assert result_vesicle["total_matching"] >= 1

    def test_per_row_dm_fields_present(self, conn):
        """Each result row includes derived_metric_count, derived_metric_value_kinds,
        compartments."""
        cypher, params = build_list_publications()
        results = conn.execute_query(cypher, **params)
        for r in results:
            assert "derived_metric_count" in r, f"Missing derived_metric_count in row: {r['doi']}"
            assert "derived_metric_value_kinds" in r, f"Missing derived_metric_value_kinds in row: {r['doi']}"
            assert "compartments" in r, f"Missing compartments in row: {r['doi']}"

    def test_summary_mode_preserves_cluster_type_rollup(self, conn):
        """Regression guard: summary Cypher populates by_cluster_type (migrated from
        in-memory). Previously this was computed from detail rows; now it must come
        from the summary Cypher via apoc.coll.frequencies."""
        cypher, params = build_list_publications_summary()
        rows = conn.execute_query(cypher, **params)
        assert rows, "Summary query returned no rows"
        row = rows[0]
        assert "by_cluster_type" in row, "by_cluster_type missing from summary row"
        ct = row["by_cluster_type"]
        # The KG has publications with cluster analyses — by_cluster_type must be non-empty
        assert len(ct) > 0, (
            "by_cluster_type is empty in summary mode — regression from in-memory removal"
        )
        # Each entry is a {item, count} dict (apoc.coll.frequencies shape)
        entry = ct[0]
        assert "item" in entry, (
            f"Unexpected by_cluster_type entry shape: {entry}"
        )


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

    def test_organism_names_filter_known_and_unknown(self, conn):
        """organism_names filter returns matched rows + reports unknowns in not_found."""
        result = api.list_organisms(
            organism_names=[
                "Prochlorococcus MED4",
                "Prochlorococcus MIT9301",
                "Bogus organism",
            ],
            conn=conn,
        )
        assert result["total_matching"] == 2
        assert result["total_entries"] >= 13
        assert result["not_found"] == ["Bogus organism"]
        names = {r["organism_name"] for r in result["results"]}
        assert "Prochlorococcus MED4" in names
        assert "Prochlorococcus MIT9301" in names

    def test_organism_names_case_insensitive(self, conn):
        """Lowercase / mixed-case input still matches preferred_name."""
        result = api.list_organisms(
            organism_names=["prochlorococcus med4"], conn=conn,
        )
        assert result["total_matching"] == 1
        assert result["not_found"] == []
        assert result["results"][0]["organism_name"] == "Prochlorococcus MED4"

    def test_summary_flag_returns_only_envelope(self, conn):
        """summary=True yields results=[] + envelope counts."""
        result = api.list_organisms(summary=True, conn=conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] == result["total_entries"]
        assert result["truncated"] is True

    def test_envelope_dm_rollups_present(self, conn):
        """Summary mode returns by_value_kind, by_metric_type, by_compartment."""
        result = api.list_organisms(summary=True, conn=conn)
        for key in ("by_value_kind", "by_metric_type", "by_compartment"):
            assert key in result, f"Missing envelope key: {key}"
            assert isinstance(result[key], list), f"{key} should be a list"

    def test_compartment_filter_narrows(self, conn):
        """Filtering by 'vesicle' returns fewer or equal organisms than unfiltered."""
        result_all = api.list_organisms(summary=True, conn=conn)
        result_vesicle = api.list_organisms(compartment="vesicle", summary=True, conn=conn)
        assert result_vesicle["total_matching"] <= result_all["total_matching"]

    def test_per_row_dm_count_present(self, conn):
        """Each result row has the 3 new compact DM fields."""
        result = api.list_organisms(limit=5, conn=conn)
        for row in result["results"]:
            assert "derived_metric_count" in row, "Missing derived_metric_count"
            assert "derived_metric_value_kinds" in row, "Missing derived_metric_value_kinds"
            assert "compartments" in row, "Missing compartments"

    def test_summary_mode_preserves_cluster_and_organism_type_rollups(self, conn):
        """Regression guard: by_cluster_type and by_organism_type must be populated
        in summary mode (where detail query is skipped). Pre-Task-2 behavior."""
        s = api.list_organisms(summary=True, conn=conn)
        assert len(s["by_cluster_type"]) > 0, (
            "by_cluster_type empty in summary mode (regression)"
        )
        assert len(s["by_organism_type"]) > 0, (
            "by_organism_type empty in summary mode (regression)"
        )

    def test_per_row_chemistry_rollups_present(self, conn):
        """Each result row carries the chemistry rollups (slice 1)."""
        result = api.list_organisms(
            organism_names=[
                "Prochlorococcus MED4",
                "Alteromonas macleodii EZ55",
            ],
            conn=conn,
        )
        names = {r["organism_name"]: r for r in result["results"]}
        for org_name in ("Prochlorococcus MED4", "Alteromonas macleodii EZ55"):
            row = names[org_name]
            assert "reaction_count" in row
            assert "catalyzed_metabolite_count" in row
            assert row["reaction_count"] > 0
            assert row["catalyzed_metabolite_count"] > 0

    def test_top_metabolic_capability_top_organisms(self, conn):
        """top_metabolic_capability (summary=True) is the FULL ranking
        (llm-review 2b.2: summary keeps the full list), sorted desc by
        catalyzed_metabolite_count, excluding zero-chemistry organisms
        (catalysis-arm rename, KG-SYNC-001)."""
        result = api.list_organisms(summary=True, conn=conn)
        cap = result["top_metabolic_capability"]
        assert len(cap) > 0
        assert "top_metabolic_capability_truncated" not in result
        # Sorted descending by catalyzed_metabolite_count
        catalyzed_counts = [r["catalyzed_metabolite_count"] for r in cap]
        assert catalyzed_counts == sorted(catalyzed_counts, reverse=True)
        # All entries have non-zero chemistry
        for entry in cap:
            assert (entry["catalyzed_metabolite_count"] > 0
                    or entry["reaction_count"] > 0)

    def test_top_metabolic_capability_capped_on_detail_call(self, conn):
        """Detail calls (summary=False) cap the same ranking to the first 10
        (llm-review 2b.2 `_cap_breakdowns`)."""
        result = api.list_organisms(limit=500, conn=conn)
        cap = result["top_metabolic_capability"]
        assert len(cap) == 10
        assert result["top_metabolic_capability_truncated"] is True


@pytest.mark.kg
class TestListExperiments:
    """Integration tests for list_experiments against live KG."""

    # --- Summary mode ---

    def test_summary_no_filters(self, conn):
        """Summary returns all experiments with breakdowns."""
        result = api.list_experiments(summary=True, conn=conn)
        assert result["total_matching"] == result["total_entries"]
        assert result["total_matching"] >= 70
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert result["results"] == []
        assert len(result["by_organism"]) >= 8
        assert len(result["by_treatment_type"]) >= 8
        assert len(result["by_omics_type"]) >= 2

    def test_summary_organism_filter(self, conn):
        """Organism filter narrows summary."""
        result = api.list_experiments(organism="MED4", summary=True, conn=conn)
        assert result["total_matching"] < result["total_entries"]
        assert result["total_matching"] >= 20

    def test_summary_breakdown_counts_sum(self, conn):
        """by_organism experiment_counts sum to total_matching."""
        result = api.list_experiments(summary=True, conn=conn)
        org_total = sum(b["count"] for b in result["by_organism"])
        assert org_total == result["total_matching"]

    def test_summary_treatment_type_counts_sum(self, conn):
        """by_treatment_type counts >= total_matching (experiments can have multiple treatment_types)."""
        result = api.list_experiments(summary=True, conn=conn)
        tt_total = sum(b["count"] for b in result["by_treatment_type"])
        assert tt_total >= result["total_matching"]

    def test_summary_omics_type_counts_sum(self, conn):
        """by_omics_type counts sum to total_matching."""
        result = api.list_experiments(summary=True, conn=conn)
        omics_total = sum(b["count"] for b in result["by_omics_type"])
        assert omics_total == result["total_matching"]

    # --- Detail mode ---

    def test_detail_no_filters(self, conn):
        """Detail returns experiments up to limit."""
        result = api.list_experiments(limit=50, conn=conn)
        assert result["returned"] == min(50, result["total_matching"])
        assert len(result["results"]) == result["returned"]
        # Breakdowns also present
        assert len(result["by_organism"]) >= 8

    def test_detail_organism_filter(self, conn):
        """Organism filter returns MED4 experiments."""
        result = api.list_experiments(organism="MED4", conn=conn)
        assert result["total_matching"] >= 20
        for r in result["results"]:
            assert "MED4" in r["organism_name"] or (
                any("MED4" in p for p in r["coculture_partner"])
            )

    def test_detail_coculture_partner_filter_matches_list(self, conn):
        """coculture_partner= matches any list entry, background partners included.

        The 2026-10-06 N-import analysis missed Weissberg 2025 proteomics
        because the partner was recorded only when coculture was the treatment.
        """
        result = api.list_experiments(coculture_partner="Alteromonas", conn=conn)
        rows = result["results"]
        assert rows
        for r in rows:
            assert isinstance(r["coculture_partner"], list)
            assert any("alteromonas" in p.lower() for p in r["coculture_partner"])
        assert any(
            r["omics_type"] == "PROTEOMICS"
            and "coculture" not in r["treatment_type"]
            and "coculture" in r["background_factors"]
            for r in rows
        )

    def test_detail_treatment_type_filter(self, conn):
        """Treatment type list filter works."""
        result = api.list_experiments(
            treatment_type=["coculture"], conn=conn,
        )
        assert result["total_matching"] >= 10
        for r in result["results"]:
            assert "coculture" in r["treatment_type"]

    def test_detail_omics_type_filter(self, conn):
        """Omics type list filter works."""
        result = api.list_experiments(
            omics_type=["PROTEOMICS"], conn=conn,
        )
        assert result["total_matching"] >= 1
        for r in result["results"]:
            assert r["omics_type"] == "PROTEOMICS"

    def test_detail_time_course_only(self, conn):
        """time_course_only returns only time-course experiments."""
        result = api.list_experiments(
            time_course_only=True, conn=conn,
        )
        assert result["total_matching"] >= 20
        for r in result["results"]:
            assert r["is_time_course"] is True

    def test_detail_expected_columns(self, conn):
        """Each result has compact columns."""
        result = api.list_experiments(limit=5, conn=conn)
        for r in result["results"]:
            for col in ["experiment_id", "experiment_name",
                        "publication_doi", "organism_name",
                        "treatment_type", "omics_type", "is_time_course",
                        "table_scope", "gene_count", "genes_by_status"]:
                assert col in r, f"Missing column: {col}"

    def test_detail_is_time_course_is_bool(self, conn):
        """is_time_course is bool, not string."""
        result = api.list_experiments(limit=5, conn=conn)
        for r in result["results"]:
            assert isinstance(r["is_time_course"], bool)

    def test_detail_gene_count_nonnegative(self, conn):
        """gene_count and genes_by_status counts are >= 0."""
        result = api.list_experiments(conn=conn)
        for r in result["results"]:
            assert r["gene_count"] >= 0
            gbs = r["genes_by_status"]
            assert gbs["significant_up"] >= 0
            assert gbs["significant_down"] >= 0
            assert gbs["not_significant"] >= 0

    def test_detail_time_course_has_timepoints(self, conn):
        """Time-course experiments have timepoints with >1 entry."""
        result = api.list_experiments(
            time_course_only=True, limit=5, conn=conn,
        )
        for r in result["results"]:
            assert "timepoints" in r
            assert len(r["timepoints"]) > 1
            tp = r["timepoints"][0]
            assert "timepoint" in tp
            assert "timepoint_order" in tp
            assert "gene_count" in tp
            assert "genes_by_status" in tp

    def test_detail_non_time_course_no_timepoints(self, conn):
        """Non-time-course experiments have no timepoints key."""
        result = api.list_experiments(conn=conn)
        non_tc = [r for r in result["results"] if not r["is_time_course"]]
        assert len(non_tc) > 0
        for r in non_tc:
            assert "timepoints" not in r

    # --- Consistency ---

    def test_summary_consistency(self, conn):
        """Summary total_matching == detail total row count (same filters)."""
        kwargs = dict(organism="MED4", treatment_type=["coculture"])
        summary = api.list_experiments(**kwargs, summary=True, conn=conn)
        detail = api.list_experiments(**kwargs, limit=500, conn=conn)
        assert summary["total_matching"] == detail["total_matching"]
        assert summary["total_matching"] == len(detail["results"])

    # --- Task 4: DM rollups + compartment filter ---

    def test_dm_rollups_in_experiment_envelope(self, conn):
        """by_value_kind, by_metric_type, by_compartment present in summary envelope."""
        result = api.list_experiments(summary=True, conn=conn)
        assert "by_value_kind" in result
        assert "by_metric_type" in result
        assert "by_compartment" in result
        # Envelope lists should be non-empty (KG has DMs + compartments)
        assert len(result["by_value_kind"]) >= 1
        assert len(result["by_compartment"]) >= 1

    def test_compartment_vesicle_returns_11(self, conn):
        """compartment='vesicle' filter returns experiments (pinned baseline)."""
        result = api.list_experiments(compartment="vesicle", summary=True, conn=conn)
        assert result["total_matching"] == 13

    def test_compartment_exoproteome_returns_8(self, conn):
        """compartment='exoproteome' filter returns experiments (pinned baseline)."""
        result = api.list_experiments(compartment="exoproteome", summary=True, conn=conn)
        # 10 -> 7 at the 2026-10-18 rebuild: Oleza 2017 re-curated as whole_cell proteomics.
        # 7 -> 19 at the 2026-10-31 rebuild: Oleza 2015b adds 12 exoproteome experiments.
        assert result["total_matching"] == 19

    def test_per_row_compartment_field(self, conn):
        """Each result row has 'compartment' field in {whole_cell, vesicle, exoproteome}."""
        result = api.list_experiments(limit=20, conn=conn)
        valid_compartments = {"whole_cell", "vesicle", "exoproteome"}
        for row in result["results"]:
            assert "compartment" in row, "Missing compartment field"
            # compartment may be None for experiments without it, or a valid value
            if row["compartment"] is not None:
                assert row["compartment"] in valid_compartments, (
                    f"Unexpected compartment value: {row['compartment']}"
                )

    def test_per_row_dm_compact_fields(self, conn):
        """Each result row has derived_metric_count and derived_metric_value_kinds."""
        result = api.list_experiments(limit=10, conn=conn)
        for row in result["results"]:
            assert "derived_metric_count" in row
            assert "derived_metric_value_kinds" in row
            assert isinstance(row["derived_metric_count"], int)
            assert isinstance(row["derived_metric_value_kinds"], list)

    def test_verbose_reports_derived_metric_types(self, conn):
        """Verbose mode includes reports_derived_metric_types per row."""
        result = api.list_experiments(verbose=True, limit=5, conn=conn)
        for row in result["results"]:
            assert "reports_derived_metric_types" in row
            assert isinstance(row["reports_derived_metric_types"], list)

    def test_compartment_filter_rows_match_value(self, conn):
        """All rows returned by compartment filter have the matching compartment value."""
        result = api.list_experiments(compartment="vesicle", limit=10, conn=conn)
        for row in result["results"]:
            assert row["compartment"] == "vesicle"

    def test_per_tp_growth_phase(self, conn):
        """Per-TP growth_phase populated on time-course experiments with phase data."""
        result = api.list_experiments(
            experiment_ids=[
                # Martiny 2006 MED4 P starvation: exponential -> acute_stress -> nutrient_limited.
                # (Was the Weissberg MED4 axenic proteome; all `death` since the 2026-10-18 rebuild.)
                "10.1073/pnas.0601301103_phosphorus_phosphate_starvation_med4_microarray"
            ],
            conn=conn,
        )
        assert result["results"], "Expected at least one experiment"
        exp = result["results"][0]
        assert exp["is_time_course"] is True
        timepoints = exp.get("timepoints") or []
        assert timepoints, "Expected at least one timepoint"
        phases = [tp.get("growth_phase") for tp in timepoints]
        # At least one TP has a non-null phase
        assert any(p is not None for p in phases), \
            f"No growth_phase populated on TPs: {phases}"
        # Stronger: this specific experiment should have phase-varying TPs
        nonnull = [p for p in phases if p]
        assert len(set(nonnull)) >= 2, \
            f"Expected phase-varying TPs on MED4 P starvation, got: {phases}"
        # Experiment-level field is gone (post-F3)
        assert "time_point_growth_phases" not in exp


@pytest.mark.kg
class TestListFilterValues:
    def test_returns_envelope_keys(self, conn):
        result = api.list_filter_values(conn=conn)
        for key in ("filter_type", "total_entries", "returned", "truncated", "results"):
            assert key in result

    def test_filter_type_is_gene_category(self, conn):
        result = api.list_filter_values(conn=conn)
        assert result["filter_type"] == "gene_category"

    def test_results_have_value_and_count(self, conn):
        result = api.list_filter_values(conn=conn)
        assert len(result["results"]) >= 1
        assert "value" in result["results"][0]
        assert "count" in result["results"][0]


    @pytest.mark.kg
    def test_metric_type_returns_baseline(self, conn):
        result = api.list_filter_values(filter_type="metric_type", conn=conn)
        # Slice-2 baseline 2026-04-27: 13 distinct metric_types
        assert result["total_entries"] >= 13
        values = {row["value"] for row in result["results"]}
        assert "damping_ratio" in values
        assert "diel_amplitude_protein_log2" in values

    @pytest.mark.kg
    def test_value_kind_returns_three_kinds(self, conn):
        result = api.list_filter_values(filter_type="value_kind", conn=conn)
        values = {row["value"] for row in result["results"]}
        assert values == {"numeric", "boolean", "categorical"}

    @pytest.mark.kg
    def test_compartment_returns_baseline(self, conn):
        result = api.list_filter_values(filter_type="compartment", conn=conn)
        values = {row["value"] for row in result["results"]}
        assert "whole_cell" in values
        assert "vesicle" in values


@pytest.mark.kg
class TestDifferentialExpressionByGene:
    def test_organism_summary(self, conn):
        """Organism-only summary returns counts without rows."""
        result = api.differential_expression_by_gene(
            organism="MED4", summary=True, conn=conn,
        )
        assert "MED4" in result["organism_name"]
        assert result["total_matching"] > 0
        assert result["results"] == []
        assert result["truncated"] is True

    def test_locus_tags_with_limit(self, conn):
        """Locus tags return detail rows sorted by |log2fc|."""
        result = api.differential_expression_by_gene(
            locus_tags=["PMM0001"], limit=5, conn=conn,
        )
        assert result["returned"] <= 5
        assert result["matching_genes"] >= 1
        for row in result["results"]:
            assert row["locus_tag"] == "PMM0001"
            assert "log2fc" in row
            assert "expression_status" in row

    def test_significant_only(self, conn):
        """significant_only filters to significant rows."""
        result = api.differential_expression_by_gene(
            organism="MED4", significant_only=True, limit=5, conn=conn,
        )
        for row in result["results"]:
            assert row["expression_status"] in ("significant_up", "significant_down")

    def test_no_filters_raises(self, conn):
        """All three None raises ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            api.differential_expression_by_gene(conn=conn)

    def test_summary_consistency(self, conn):
        """Summary total_matching matches detail row count (small dataset)."""
        kwargs = dict(locus_tags=["PMM0001"], conn=conn)
        summary = api.differential_expression_by_gene(**kwargs, summary=True)
        detail = api.differential_expression_by_gene(**kwargs, limit=500)
        assert summary["total_matching"] == detail["total_matching"]
        assert summary["total_matching"] == len(detail["results"])

    def test_experiment_with_no_expression_edges(self, conn):
        """Experiment without any Changes_expression_of edges returns empty
        envelope, not IndexError. Vesicle-proteomics experiments live in the
        KG but never wire up DE edges — they surface in
        not_matched_experiments, not not_found_experiments."""
        eid = "10.1126/science.1243457_vesicle_proteomics_med4"
        result = api.differential_expression_by_gene(
            experiment_ids=[eid],
            significant_only=True,
            conn=conn,
        )
        assert result["total_matching"] == 0
        assert result["matching_genes"] == 0
        assert result["results"] == []
        assert result["top_categories"] == []
        assert result["not_found"] == []
        assert result["no_expression"] == []
        assert result["not_found_experiments"] == []
        assert result["not_matched_experiments"] == [eid]

    def test_experiment_not_found_in_mixed_input(self, conn):
        """A bogus experiment_id mixed with a valid one surfaces in
        not_found_experiments. (All-bogus input is rejected upfront by
        single-organism validation before diagnostics run — that's
        pre-existing behavior, not what this diagnostic targets.)"""
        bogus = "does-not-exist-experiment-id"
        valid = "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_hot1a3_rnaseq_axenic"
        result = api.differential_expression_by_gene(
            experiment_ids=[bogus, valid],
            summary=True,
            conn=conn,
        )
        assert result["not_found_experiments"] == [bogus]
        assert result["not_matched_experiments"] == []

    def test_experiment_diagnostics_empty_without_experiment_ids(self, conn):
        """Without experiment_ids the two diagnostic buckets stay empty."""
        result = api.differential_expression_by_gene(
            locus_tags=["PMM0001"], summary=True, conn=conn,
        )
        assert result["not_found_experiments"] == []
        assert result["not_matched_experiments"] == []


@pytest.mark.kg
class TestDifferentialExpressionByOrtholog:
    KNOWN_GROUP = "cyanorak:CK_00000570"

    def test_single_group(self, conn):
        """Single group returns results with expected fields."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], limit=10, conn=conn,
        )
        assert result["total_matching"] > 0
        assert result["matching_genes"] >= 1
        assert result["matching_groups"] == 1
        assert result["returned"] >= 1
        row = result["results"][0]
        assert row["group_id"] == self.KNOWN_GROUP
        for key in ("experiment_id", "treatment_type", "organism_name",
                     "timepoint_order", "genes_with_expression", "total_genes",
                     "significant_up", "significant_down", "not_significant"):
            assert key in row

    def test_multiple_groups(self, conn):
        """Multiple groups return results from all groups."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP, "cyanorak:CK_00000364"],
            limit=200, conn=conn,
        )
        group_ids = {r["group_id"] for r in result["results"]}
        assert len(group_ids) >= 2
        assert result["matching_groups"] >= 2

    def test_organisms_filter(self, conn):
        """Organisms filter restricts by_organism and results."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], organisms=["MED4"],
            limit=50, conn=conn,
        )
        for row in result["results"]:
            assert "MED4" in row["organism_name"]
        organisms = [b["organism_name"] for b in result["by_organism"]]
        assert all("MED4" in o for o in organisms)

    def test_significant_only(self, conn):
        """significant_only filters to significant rows only."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], significant_only=True,
            limit=50, conn=conn,
        )
        for row in result["results"]:
            # Each row should have at least one significant gene
            assert row["significant_up"] + row["significant_down"] > 0
        rbs = result["rows_by_status"]
        assert rbs.get("not_significant", 0) == 0

    def test_direction_up(self, conn):
        """direction='up' only counts significant_up in rows_by_status."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], direction="up",
            limit=50, conn=conn,
        )
        rbs = result["rows_by_status"]
        assert rbs.get("significant_down", 0) == 0
        assert rbs.get("not_significant", 0) == 0

    def test_verbose_adds_fields(self, conn):
        """verbose=True adds experiment_name, treatment, omics_type."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], verbose=True, limit=1, conn=conn,
        )
        if result["results"]:
            row = result["results"][0]
            for key in ("experiment_name", "treatment", "omics_type",
                        "table_scope"):
                assert key in row

    def test_not_found_groups(self, conn):
        """Fake group ID appears in not_found_groups."""
        result = api.differential_expression_by_ortholog(
            group_ids=["FAKE_GROUP_ID"], conn=conn,
        )
        assert "FAKE_GROUP_ID" in result["not_found_groups"]
        assert result["total_matching"] == 0
        assert result["results"] == []

    def test_genes_with_expression_le_total_genes(self, conn):
        """genes_with_expression <= total_genes in every result row."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], limit=50, conn=conn,
        )
        for row in result["results"]:
            assert row["genes_with_expression"] <= row["total_genes"]

    def test_empty_group_ids_raises(self, conn):
        """Empty group_ids raises ValueError."""
        with pytest.raises(ValueError, match="group_ids must not be empty"):
            api.differential_expression_by_ortholog(group_ids=[], conn=conn)

    def test_top_groups_and_experiments(self, conn):
        """top_groups and top_experiments are populated."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP, "cyanorak:CK_00000364"],
            limit=10, conn=conn,
        )
        assert len(result["top_groups"]) >= 1
        assert len(result["top_experiments"]) >= 1
        tg = result["top_groups"][0]
        assert "group_id" in tg
        assert "significant_genes" in tg
        te = result["top_experiments"][0]
        assert "experiment_id" in te
        assert "significant_genes" in te

    def test_diagnostics_with_combined_filters(self, conn):
        """Diagnostics work with organisms + experiment_ids + direction."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP],
            organisms=["FAKE_ORG", "MED4"],
            experiment_ids=["FAKE_EXP"],
            direction="up",
            conn=conn,
        )
        assert "FAKE_ORG" in result["not_found_organisms"]
        assert "FAKE_EXP" in result["not_found_experiments"]


# ---------------------------------------------------------------------------
# search_homolog_groups
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestSearchHomologGroups:
    def test_basic_search(self, conn):
        """Text search returns matching groups with expected columns."""
        result = api.search_homolog_groups("photosynthesis", conn=conn)
        assert result["total_matching"] >= 5
        assert result["returned"] >= 1
        row = result["results"][0]
        for key in ("group_id", "group_name", "consensus_gene_name",
                     "consensus_product", "source", "taxonomic_level",
                     "specificity_rank", "member_count", "organism_count", "score"):
            assert key in row

    def test_source_filter_cyanorak(self, conn):
        """Source filter restricts to cyanorak groups only."""
        result = api.search_homolog_groups(
            "photosynthesis", source="cyanorak", conn=conn,
        )
        assert result["total_matching"] >= 1
        for row in result["results"]:
            assert row["source"] == "cyanorak"
        sources = [b["source"] for b in result["by_source"]]
        assert sources == ["cyanorak"]

    def test_source_filter_eggnog(self, conn):
        """Source filter restricts to eggnog groups only."""
        result = api.search_homolog_groups(
            "polymerase", source="eggnog", conn=conn,
        )
        assert result["total_matching"] >= 1
        for row in result["results"]:
            assert row["source"] == "eggnog"

    def test_max_specificity_rank(self, conn):
        """max_specificity_rank caps group breadth."""
        result = api.search_homolog_groups(
            "photosynthesis", max_specificity_rank=0, conn=conn,
        )
        for row in result["results"]:
            assert row["specificity_rank"] <= 0

    def test_verbose_adds_fields(self, conn):
        """Verbose mode includes description and genera."""
        result = api.search_homolog_groups(
            "nitrogen", verbose=True, limit=1, conn=conn,
        )
        if result["results"]:
            row = result["results"][0]
            for key in ("description", "functional_description",
                        "genera", "has_cross_genus_members"):
                assert key in row

    def test_summary_mode(self, conn):
        """Summary mode returns counts without detail rows."""
        result = api.search_homolog_groups(
            "photosynthesis", summary=True, conn=conn,
        )
        assert result["total_matching"] >= 5
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert len(result["by_source"]) >= 1
        assert len(result["by_level"]) >= 1

    def test_summary_consistency(self, conn):
        """Summary total_matching matches detail row count."""
        summary = api.search_homolog_groups(
            "kinase", summary=True, conn=conn,
        )
        detail = api.search_homolog_groups(
            "kinase", limit=1000, conn=conn,
        )
        assert summary["total_matching"] == detail["total_matching"]
        assert detail["total_matching"] == len(detail["results"])

    def test_empty_search_raises(self, conn):
        """Empty search_text raises ValueError."""
        with pytest.raises(ValueError, match="search_text"):
            api.search_homolog_groups("", conn=conn)

    def test_invalid_source_raises(self, conn):
        """Invalid source enum raises ValueError."""
        with pytest.raises(ValueError, match="Invalid source"):
            api.search_homolog_groups("kinase", source="invalid", conn=conn)

    def test_score_fields_populated(self, conn):
        """score_max and score_median are populated when results exist."""
        result = api.search_homolog_groups("photosynthesis", conn=conn)
        assert result["score_max"] is not None
        assert result["score_median"] is not None
        assert result["score_max"] >= result["score_median"]


# ---------------------------------------------------------------------------
# genes_by_homolog_group
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGenesByHomologGroup:
    KNOWN_GROUP = "cyanorak:CK_00000570"

    def test_basic_lookup(self, conn):
        """Single group returns member genes."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], conn=conn,
        )
        assert result["total_matching"] >= 1
        assert result["returned"] >= 1
        row = result["results"][0]
        for key in ("locus_tag", "gene_name", "product",
                     "organism_name", "gene_category", "group_id"):
            assert key in row
        assert row["group_id"] == self.KNOWN_GROUP

    def test_organisms_filter(self, conn):
        """Organisms filter restricts results."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], organisms=["MED4"], conn=conn,
        )
        for row in result["results"]:
            assert "MED4" in row["organism_name"]

    def test_verbose_adds_fields(self, conn):
        """Verbose mode adds gene_summary and group context."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], verbose=True, limit=1, conn=conn,
        )
        if result["results"]:
            row = result["results"][0]
            for key in ("gene_summary", "function_description",
                        "consensus_product", "source"):
                assert key in row

    def test_summary_mode(self, conn):
        """Summary mode returns counts without detail rows."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], summary=True, conn=conn,
        )
        assert result["total_matching"] >= 1
        assert result["results"] == []
        assert result["returned"] == 0

    def test_not_found_groups(self, conn):
        """Fake group ID appears in not_found_groups."""
        result = api.genes_by_homolog_group(
            group_ids=["FAKE_GROUP_XYZ"], conn=conn,
        )
        assert "FAKE_GROUP_XYZ" in result["not_found_groups"]
        assert result["total_matching"] == 0

    def test_not_matched_organisms(self, conn):
        """Organism that exists but has no members appears in not_matched."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP],
            organisms=["FAKE_ORG", "MED4"], conn=conn,
        )
        assert "FAKE_ORG" in result["not_found_organisms"]

    def test_empty_group_ids_raises(self, conn):
        """Empty group_ids raises ValueError."""
        with pytest.raises(ValueError, match="group_ids must not be empty"):
            api.genes_by_homolog_group(group_ids=[], conn=conn)

    def test_multiple_groups(self, conn):
        """Multiple groups return genes from all groups."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP, "cyanorak:CK_00000364"],
            limit=200, conn=conn,
        )
        group_ids = {r["group_id"] for r in result["results"]}
        assert len(group_ids) >= 2

    def test_summary_consistency(self, conn):
        """Summary total_matching matches detail row count."""
        summary = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], summary=True, conn=conn,
        )
        detail = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], limit=500, conn=conn,
        )
        assert summary["total_matching"] == detail["total_matching"]
        assert detail["total_matching"] == len(detail["results"])

    def test_top_groups_and_categories(self, conn):
        """top_groups and top_categories are populated."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP, "cyanorak:CK_00000364"],
            conn=conn,
        )
        assert len(result["top_groups"]) >= 1
        assert result["top_groups"][0]["group_id"] in (
            self.KNOWN_GROUP, "cyanorak:CK_00000364"
        )
        assert result["total_categories"] >= 1


# ---------------------------------------------------------------------------
# gene_overview
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneOverview:
    def test_single_gene(self, conn):
        """Single gene returns overview with routing signals."""
        result = api.gene_overview(["PMM0001"], conn=conn)
        assert result["total_matching"] == 1
        assert result["returned"] == 1
        row = result["results"][0]
        assert row["locus_tag"] == "PMM0001"
        for key in ("gene_name", "product", "gene_category",
                     "annotation_quality", "organism_name",
                     "annotation_types", "expression_edge_count",
                     "significant_up_count", "significant_down_count",
                     "closest_ortholog_group_size", "closest_ortholog_genera"):
            assert key in row

    def test_batch_pro_and_alt(self, conn):
        """Batch with Pro + Alt genes returns both."""
        result = api.gene_overview(
            ["PMM1428", "EZ55_00275"], conn=conn,
        )
        assert result["total_matching"] == 2
        tags = {r["locus_tag"] for r in result["results"]}
        assert tags == {"PMM1428", "EZ55_00275"}

    def test_not_found(self, conn):
        """Non-existent gene appears in not_found."""
        result = api.gene_overview(
            ["PMM0001", "FAKE_GENE_XYZ"], conn=conn,
        )
        assert "FAKE_GENE_XYZ" in result["not_found"]
        assert result["total_matching"] == 1

    def test_summary_mode(self, conn):
        """Summary mode returns counts without detail rows."""
        result = api.gene_overview(
            ["PMM0001"], summary=True, conn=conn,
        )
        assert result["total_matching"] == 1
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["has_expression"] >= 0
        assert result["has_orthologs"] >= 0

    def test_verbose_adds_fields(self, conn):
        """Verbose mode adds gene_summary and function_description."""
        result = api.gene_overview(
            ["PMM0001"], verbose=True, conn=conn,
        )
        row = result["results"][0]
        for key in ("gene_summary", "function_description", "all_identifiers"):
            assert key in row

    def test_by_organism_breakdown(self, conn):
        """by_organism is populated for cross-organism batch."""
        result = api.gene_overview(
            ["PMM1428", "EZ55_00275"], conn=conn,
        )
        assert len(result["by_organism"]) == 2
        org_total = sum(b["count"] for b in result["by_organism"])
        assert org_total == result["total_matching"]

    def test_expression_signals(self, conn):
        """MED4 gene has expression data available."""
        result = api.gene_overview(["PMM0001"], conn=conn)
        row = result["results"][0]
        assert row["expression_edge_count"] > 0

    def test_summary_consistency(self, conn):
        """Summary total_matching matches detail row count."""
        tags = ["PMM0001", "PMM0845", "EZ55_00275"]
        summary = api.gene_overview(tags, summary=True, conn=conn)
        detail = api.gene_overview(tags, limit=500, conn=conn)
        assert summary["total_matching"] == detail["total_matching"]
        assert detail["total_matching"] == len(detail["results"])

    def test_gene_overview_dm_rollup_for_dm_bearing_gene(self, conn):
        """DM-bearing gene surfaces has_derived_metrics=1 and a non-empty value_kinds list."""
        # locus_tag captured from live KG: g.boolean_metric_count > 0
        KNOWN_DM_GENE = "MIT1002_01809"
        result = api.gene_overview(locus_tags=[KNOWN_DM_GENE], conn=conn)
        assert result["has_derived_metrics"] == 1
        row = result["results"][0]
        assert row["derived_metric_count"] > 0
        assert "boolean" in row["derived_metric_value_kinds"]

    def test_gene_overview_verbose_surfaces_per_kind(self, conn):
        """Verbose mode preserves per-kind counts and compartments_observed."""
        KNOWN_DM_GENE = "MIT1002_01809"
        result = api.gene_overview(locus_tags=[KNOWN_DM_GENE], verbose=True, conn=conn)
        row = result["results"][0]
        assert row["boolean_metric_count"] > 0
        assert isinstance(row["compartments_observed"], list)


@pytest.mark.kg
class TestOntologyLandscapeIntegration:
    def test_med4_all_ontologies_tigr_l1_rank1_among_hierarchical(self, conn):
        from multiomics_explorer.api.functions import ontology_landscape
        # informative_only=False preserves the pre-F1-surface rank ordering
        # (cyanorak_role L1 has 5 uninformative-flagged terms / ~16.5% of
        # gene-pairs that the default-on filter would drop).
        # Since the 2026-08-29 KG TigrRole is two-level, so tigr_role L1
        # (MED4 coverage ~0.62) is the top hierarchical row, ahead of
        # cyanorak_role L1 (~0.56); both must appear as hierarchical rows.
        result = ontology_landscape(
            organism="MED4", limit=None, informative_only=False, conn=conn,
        )
        hierarchical = [
            r for r in result["results"]
            if r["n_levels_in_ontology"] > 1
        ]
        assert hierarchical, "expected at least one hierarchical row"
        top_hier = min(hierarchical, key=lambda r: r["relevance_rank"])
        assert top_hier["ontology_type"] == "tigr_role"
        assert top_hier["level"] == 1, (
            f"expected tigr_role L1, got L{top_hier['level']}"
        )
        cyanorak_l1 = [
            r for r in hierarchical
            if r["ontology_type"] == "cyanorak_role" and r["level"] == 1
        ]
        assert cyanorak_l1, "cyanorak_role L1 must still be a hierarchical row"

    def test_med4_experiment_branch_coverage_fields(self, conn):
        from multiomics_explorer.api.functions import ontology_landscape
        result = ontology_landscape(
            organism="MED4",
            ontology="cyanorak_role",
            experiment_ids=[
                "10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq",
                "THIS_DOES_NOT_EXIST",
            ],
            limit=None,
            conn=conn,
        )
        assert "THIS_DOES_NOT_EXIST" in result["not_found"]
        # Coverage fields present on every row
        for r in result["results"]:
            assert "min_exp_coverage" in r
            assert "median_exp_coverage" in r
            assert "max_exp_coverage" in r


@pytest.mark.kg
class TestPathwayEnrichmentIntegration:
    """Live-KG integration for pathway_enrichment."""

    def test_b1_reproduction_cyanorak_level1(self, conn):
        """MED4 × CyanoRak level 1 produces recognizable enriched pathways.

        Baseline: B1 analysis found enrichments in N-metabolism (E.4),
        photosynthesis (J.1–J.8), and ribosomal (K.2) categories.

        Uses background='organism' to give a meaningful universe size;
        table_scope background would be too small per-cluster to yield significance.
        """
        from multiomics_explorer.api.functions import pathway_enrichment, list_experiments
        all_experiments = list_experiments(organism="MED4", limit=100, conn=conn)
        # Filter to MED4-only experiments (exclude co-culture rows where Alteromonas is primary)
        exp_ids = [
            e["experiment_id"]
            for e in all_experiments["results"]
            if "MED4" in e.get("organism_name", "")
        ]
        result = pathway_enrichment(
            organism="MED4",
            experiment_ids=exp_ids,
            ontology="cyanorak_role",
            level=1,
            direction="both",
            significant_only=True,
            background="organism",
            conn=conn,
        )
        envelope = result.to_envelope()
        assert envelope["total_matching"] > 0
        assert envelope["n_significant"] > 0
        top_terms = {p["term_id"] for p in envelope["top_pathways_by_padj"]}
        expected_family_prefixes = ("cyanorak.role:E.", "cyanorak.role:J.", "cyanorak.role:K.")
        assert any(any(t.startswith(p) for p in expected_family_prefixes) for t in top_terms), (
            f"Expected at least one E./J./K. pathway; got {top_terms}"
        )

    def test_organism_background(self, conn):
        """`background='organism'` fetches the full MED4 gene set."""
        from multiomics_explorer.api.functions import pathway_enrichment, list_experiments
        all_experiments = list_experiments(organism="MED4", limit=20, conn=conn)
        exp_ids = [
            e["experiment_id"]
            for e in all_experiments["results"]
            if "MED4" in e.get("organism_name", "")
        ][:1]
        result = pathway_enrichment(
            organism="MED4",
            experiment_ids=exp_ids,
            ontology="cyanorak_role",
            level=1,
            background="organism",
            conn=conn,
        )
        assert result.to_envelope()["total_matching"] >= 0

    def test_explicit_background_list(self, conn):
        """`background=<list>` uses caller's universe."""
        from multiomics_explorer.api.functions import pathway_enrichment, list_experiments
        all_experiments = list_experiments(organism="MED4", limit=20, conn=conn)
        med4_exps = [
            e["experiment_id"]
            for e in all_experiments["results"]
            if "MED4" in e.get("organism_name", "")
        ]
        exp_ids = med4_exps[:1]
        custom_bg = [f"PMM{i:04d}" for i in range(1, 501)]
        result = pathway_enrichment(
            organism="MED4",
            experiment_ids=exp_ids,
            ontology="cyanorak_role",
            level=1,
            background=custom_bg,
            conn=conn,
        )
        assert result.to_envelope()["cluster_summary"]["universe_size_max"] <= len(custom_bg)

    def test_clusters_skipped_for_undersized(self, conn):
        """Very high min_gene_set_size forces all clusters to be skipped."""
        from multiomics_explorer.api.functions import pathway_enrichment, list_experiments
        all_experiments = list_experiments(organism="MED4", limit=20, conn=conn)
        med4_exps = [
            e["experiment_id"]
            for e in all_experiments["results"]
            if "MED4" in e.get("organism_name", "")
        ]
        exp_ids = med4_exps[:1]
        result = pathway_enrichment(
            organism="MED4",
            experiment_ids=exp_ids,
            ontology="cyanorak_role",
            level=1,
            min_gene_set_size=100000,
            max_gene_set_size=None,
            conn=conn,
        )
        assert result.to_envelope()["clusters_skipped"], "expected clusters skipped under impossible min filter"


@pytest.mark.kg
class TestClusterEnrichmentIntegration:
    """Live-KG integration for cluster_enrichment."""

    def test_basic_call(self, conn):
        from multiomics_explorer.api import list_clustering_analyses, cluster_enrichment
        analyses = list_clustering_analyses(organism="MED4", limit=1, conn=conn)
        if not analyses["results"]:
            pytest.skip("No clustering analyses in KG")
        analysis = analyses["results"][0]
        result = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role",
            level=1,
            pvalue_cutoff=0.99,
            conn=conn,
        )
        envelope = result.to_envelope()
        assert isinstance(envelope["results"], list)
        assert result.params["background_mode"] == "cluster_union"

    def test_organism_background_differs(self, conn):
        from multiomics_explorer.api import list_clustering_analyses, cluster_enrichment
        analyses = list_clustering_analyses(organism="MED4", limit=1, conn=conn)
        if not analyses["results"]:
            pytest.skip("No clustering analyses in KG")
        analysis = analyses["results"][0]
        r_union = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role", level=1,
            background="cluster_union", conn=conn,
        )
        r_org = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role", level=1,
            background="organism", conn=conn,
        )
        # organism background must be >= cluster_union background per cluster
        union_max = max((len(v) for v in r_union.inputs.background.values()), default=0)
        org_max = max((len(v) for v in r_org.inputs.background.values()), default=0)
        assert org_max >= union_max



# --- Live-count Cypher used instead of literal pins (backlog 2.9) ---
_DM_EDGES_TO_GENE = (
    "MATCH (d:DerivedMetric)-[:Derived_metric_quantifies_gene|"
    "Derived_metric_flags_gene|Derived_metric_classifies_gene]->"
    "(g:Gene {locus_tag: $lt}) RETURN count(DISTINCT d)"
)
_TOP_QUARTILE_CELL_ABUNDANCE = (
    "MATCH (d:DerivedMetric {metric_type: 'cell_abundance_biovolume_normalized'})"
    "-[r:Derived_metric_quantifies_gene {metric_bucket: 'top_quartile'}]->(g:Gene)"
    "-[:Gene_belongs_to_organism]->(o:OrganismTaxon {preferred_name: $org}) RETURN count(r)"
)
_TERM_PROP = "MATCH (t {id: $id}) RETURN t[$prop]"

@pytest.mark.kg
class TestListDerivedMetrics:
    """Live-KG integration tests for list_derived_metrics."""

    def test_no_filters_all_dms(self, conn, kg_count):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(conn=conn, limit=None)
        n = kg_count("MATCH (d:DerivedMetric) RETURN count(d)")
        assert n > 0
        assert out["total_entries"] == n
        assert out["total_matching"] == n
        assert len(out["results"]) == n

    def test_value_kind_numeric(self, conn, kg_count):
        from multiomics_explorer.api import list_derived_metrics
        # `compartment` moved behind verbose (llm-review 2b.2 Task 5).
        out = list_derived_metrics(
            value_kind="numeric", verbose=True, conn=conn, limit=None)
        assert out["total_matching"] == kg_count(
            "MATCH (d:DerivedMetric {value_kind: 'numeric'}) RETURN count(d)")
        assert all(r["value_kind"] == "numeric" for r in out["results"])
        compartments = {r["compartment"] for r in out["results"]}
        assert compartments == {"whole_cell", "vesicle", "exoproteome"}

    def test_value_kind_boolean(self, conn, kg_count):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="boolean", conn=conn, limit=None)
        assert out["total_matching"] == kg_count(
            "MATCH (d:DerivedMetric {value_kind: 'boolean'}) RETURN count(d)")
        organisms = {r["organism_name"] for r in out["results"]}
        assert "Prochlorococcus NATL2A" in organisms
        assert "Alteromonas macleodii MIT1002" in organisms

    def test_value_kind_categorical(self, conn, kg_count):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="categorical", conn=conn, limit=None)
        assert out["total_matching"] == kg_count(
            "MATCH (d:DerivedMetric {value_kind: 'categorical'}) RETURN count(d)")
        metric_types = {r["metric_type"] for r in out["results"]}
        assert "darkness_survival_class" in metric_types
        assert all(r["allowed_categories"] is not None for r in out["results"])

    def test_rankable_true(self, conn, kg_count):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(rankable=True, conn=conn, limit=None)
        assert out["total_matching"] == kg_count(
            "MATCH (d:DerivedMetric {rankable: 'rankable'}) RETURN count(d)")
        assert all(r["rankable"] is True for r in out["results"])

    def test_rankable_false(self, conn, kg_count):
        """Sanity-checks bool→two-state string coercion path."""
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(rankable=False, conn=conn, limit=None)
        assert out["total_matching"] == kg_count(
            "MATCH (d:DerivedMetric {rankable: 'not_rankable'}) RETURN count(d)")
        metric_types = {r["metric_type"] for r in out["results"]}
        # The two non-rankable numeric DMs are always in this set
        assert "peak_time_protein_h" in metric_types
        assert "peak_time_transcript_h" in metric_types
        assert all(r["rankable"] is False for r in out["results"])

    def test_has_p_value_true_empty(self, conn):
        """Intentional: no DM in current KG has p-values."""
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(has_p_value=True, conn=conn, limit=None)
        assert out["total_matching"] == 0
        assert out["results"] == []

    def test_organism_short_code(self, conn, kg_count):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(organism="MED4", conn=conn, limit=None)
        assert out["total_matching"] == kg_count(
            "MATCH (d:DerivedMetric)-[:DerivedMetricBelongsToOrganism]->"
            "(o:OrganismTaxon {preferred_name: 'Prochlorococcus MED4'}) RETURN count(d)")
        assert all(r["organism_name"] == "Prochlorococcus MED4" for r in out["results"])

    def test_organism_full_name(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            organism="Prochlorococcus NATL2A", conn=conn, limit=None)
        assert out["total_matching"] == 7  # +2 Ford 2021 SBP DMs 2026-10-28

    def test_organism_alteromonas(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(organism="MIT1002", conn=conn, limit=None)
        assert out["total_matching"] == 6  # +1 Koch 2020 strain-unique DM 2026-10-31

    def test_search_text_diel_amplitude(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(search_text="diel amplitude", conn=conn, limit=5)
        # Top hits must include both diel_amplitude_* DMs
        top_metric_types = [r["metric_type"] for r in out["results"][:2]]
        assert "diel_amplitude_protein_log2" in top_metric_types
        assert "diel_amplitude_transcript_log2" in top_metric_types
        assert out["score_max"] is not None
        assert out["score_median"] is not None

    def test_publication_biller_7(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            publication_dois=["10.1128/mSystems.00040-18"], conn=conn, limit=None)
        assert out["total_matching"] == 7

    def test_derived_metric_ids_direct(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        target = (
            "derived_metric:journal.pone.0043432:"
            "table_s2_waldbauer_diel_metrics:damping_ratio"
        )
        out = list_derived_metrics(derived_metric_ids=[target], conn=conn)
        assert out["total_matching"] == 1
        assert out["results"][0]["derived_metric_id"] == target

    def test_summary_results_empty(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(summary=True, conn=conn)
        assert out["results"] == []
        assert out["returned"] == 0
        assert len(out["by_value_kind"]) == 3  # numeric, boolean, categorical
        assert len(out["by_organism"]) == 105  # 12 → 103 2026-10-28: Ford 2021 DMs on 95 genomes; +83-1, PCC 7942 2026-10-31

    def test_verbose_adds_fields(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(verbose=True, limit=1, conn=conn)
        row = out["results"][0]
        assert "treatment" in row
        assert "light_condition" in row
        assert "experimental_context" in row
        # p_value_threshold NOT in Cypher — still keyed in Pydantic default, absent here
        assert row.get("p_value_threshold") is None

    def test_envelope_keys_always_present(self, conn):
        """Zero-row filter case: breakdowns are [], not missing."""
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            derived_metric_ids=["nonexistent:id"], conn=conn, limit=None)
        assert out["total_matching"] == 0
        for key in (
            "by_organism", "by_value_kind", "by_metric_type", "by_compartment",
            "by_omics_type", "by_treatment_type", "by_background_factors",
            "by_growth_phase",
        ):
            assert key in out
            assert out[key] == []
        assert out["results"] == []
        assert out["score_max"] is None

    def test_pagination_offset(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        page1 = list_derived_metrics(conn=conn, limit=5, offset=0)
        page2 = list_derived_metrics(conn=conn, limit=5, offset=5)
        page1_ids = {r["derived_metric_id"] for r in page1["results"]}
        page2_ids = {r["derived_metric_id"] for r in page2["results"]}
        assert page1_ids.isdisjoint(page2_ids)
        assert page1["truncated"] is True
        assert page2["truncated"] is True  # 5 + 5 = 10 < 13


@pytest.fixture(scope="module")
def tool_fns():
    """Register MCP tools on a fresh FastMCP and return {name: fn} dict.

    Used by integration tests that exercise the wrapper layer (Pydantic
    response models, ToolError raising) against the live KG.
    """
    mcp = FastMCP("test")
    register_tools(mcp)
    tools = asyncio.run(mcp.list_tools())
    return {t.name: asyncio.run(mcp.get_tool(t.name)).fn for t in tools}


@pytest.fixture
def mcp_client(conn):
    """In-memory fastmcp.Client bound to a FastMCP app with the real
    GraphConnection injected via lifespan — exercises the actual MCP wire
    serialization (SparseRow model_serializer included), unlike `tool_fns`
    which returns the raw Pydantic object."""
    from contextlib import asynccontextmanager
    from dataclasses import dataclass

    from fastmcp import Client

    @dataclass
    class _LifespanContext:
        conn: object

    @asynccontextmanager
    async def lifespan(server):
        yield _LifespanContext(conn=conn)

    app = FastMCP("test-client", lifespan=lifespan)
    register_tools(app)
    return Client(app)


def _ctx_with_conn(conn):
    """Build an AsyncMock Context with the real GraphConnection injected."""
    ctx = AsyncMock()
    ctx.request_context.lifespan_context.conn = conn
    return ctx


@pytest.mark.kg
class TestExpressionByExperimentSparse:
    """I2 (llm-review 2b final review): ExpressionByExperiment is a
    SparseRow so a compact entry's verbose-only keys (timepoints,
    experiment_name, background_factors, coculture_partner,
    table_scope_detail) are absent on the wire, not null. Verified through
    the real fastmcp.Client wire path (structured_content), not just the
    Python object, since the sparse behavior lives in the model_serializer
    that only fires on serialization."""

    _VERBOSE_ONLY_KEYS = {
        "timepoints", "experiment_name", "background_factors",
        "coculture_partner", "table_scope_detail",
    }

    @pytest.mark.asyncio
    async def test_compact_entry_omits_verbose_only_keys(self, mcp_client):
        async with mcp_client as client:
            result = await client.call_tool(
                "differential_expression_by_gene",
                {"organism": "MED4", "limit": 5},
            )
        experiments = result.structured_content["experiments"]
        assert experiments, "expected ≥1 experiment entry for MED4"
        for entry in experiments:
            assert not (self._VERBOSE_ONLY_KEYS & entry.keys()), (
                f"compact entry carried verbose-only keys: "
                f"{self._VERBOSE_ONLY_KEYS & entry.keys()}"
            )

    @pytest.mark.asyncio
    async def test_verbose_entry_carries_the_keys(self, mcp_client):
        async with mcp_client as client:
            result = await client.call_tool(
                "differential_expression_by_gene",
                {"organism": "MED4", "limit": 5, "verbose": True},
            )
        experiments = result.structured_content["experiments"]
        assert experiments, "expected ≥1 experiment entry for MED4"
        for entry in experiments:
            assert self._VERBOSE_ONLY_KEYS <= entry.keys(), (
                f"verbose entry missing keys: "
                f"{self._VERBOSE_ONLY_KEYS - entry.keys()}"
            )


# ---------------------------------------------------------------------------
# Slice-2 MCP-wrapper integration tests.
#
# The TestListPublications / TestListOrganisms / TestListExperiments /
# TestGeneOverview classes earlier in this file call api.<func>(...) directly
# and so bypass the FastMCP wrapper layer (typed Pydantic response/breakdown
# submodels + ToolError raising). The classes below exercise the wrapper via
# the `tool_fns` fixture so that breakdown-model field drops or wrapper-only
# regressions surface as test failures.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestListPublicationsMcpWrapper:
    """Wrapper-level integration tests for list_publications."""

    @pytest.mark.asyncio
    async def test_typed_response_and_breakdowns(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_publications"](
            ctx, organism="MED4", limit=5)
        # Envelope counts.
        assert response.total_matching >= 5
        assert response.returned == len(response.results)
        # Typed result rows (Pydantic attribute access, not dict subscript).
        first = response.results[0]
        assert isinstance(first.doi, str) and first.doi
        assert isinstance(first.experiment_count, int)
        # Typed breakdown submodels — slice-2 added the 3 DM rollups.
        assert isinstance(response.by_organism, list)
        if response.by_organism:
            assert isinstance(response.by_organism[0].organism_name, str)
            assert isinstance(response.by_organism[0].count, int)
        assert isinstance(response.by_value_kind, list)
        assert isinstance(response.by_metric_type, list)
        assert isinstance(response.by_compartment, list)

    @pytest.mark.asyncio
    async def test_publication_dois_not_found_typed(self, tool_fns, conn):
        """Unknown DOI propagates through the typed response as `not_found`."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_publications"](
            ctx,
            publication_dois=[
                "10.1038/ISMEJ.2016.70", "10.9999/does-not-exist",
            ],
        )
        assert response.total_matching == 1
        assert response.not_found == ["10.9999/does-not-exist"]
        assert response.results[0].doi.lower() == "10.1038/ismej.2016.70"

    @pytest.mark.asyncio
    async def test_verbose_surfaces_abstract(self, tool_fns, conn):
        """verbose=True populates the verbose-only `abstract` field."""
        ctx = _ctx_with_conn(conn)
        compact = await tool_fns["list_publications"](ctx, limit=3)
        verbose = await tool_fns["list_publications"](ctx, limit=3, verbose=True)
        # Compact rows leave `abstract` at its default (None); verbose rows
        # surface a string for at least one publication.
        assert all(r.abstract is None for r in compact.results)
        assert any(isinstance(r.abstract, str) and r.abstract
                   for r in verbose.results)


@pytest.mark.kg
class TestListOrganismsMcpWrapper:
    """Wrapper-level integration tests for list_organisms."""

    @pytest.mark.asyncio
    async def test_typed_response_and_breakdowns(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_organisms"](ctx, limit=5)
        assert response.total_entries >= 13
        assert response.returned == len(response.results)
        # Typed result rows.
        first = response.results[0]
        assert isinstance(first.organism_name, str)
        assert isinstance(first.organism_type, str)
        assert isinstance(first.gene_count, int)
        # Slice-2 envelope keys are typed lists (may be empty in extreme
        # filter cases but type must be list).
        assert isinstance(response.by_value_kind, list)
        assert isinstance(response.by_metric_type, list)
        assert isinstance(response.by_compartment, list)
        assert isinstance(response.by_organism_type, list)

    @pytest.mark.asyncio
    async def test_organism_names_not_found_typed(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_organisms"](
            ctx,
            organism_names=[
                "Prochlorococcus MED4",
                "Prochlorococcus MIT9301",
                "Bogus organism",
            ],
        )
        assert response.total_matching == 2
        assert response.not_found == ["Bogus organism"]
        names = {r.organism_name for r in response.results}
        assert names == {"Prochlorococcus MED4", "Prochlorococcus MIT9301"}

    @pytest.mark.asyncio
    async def test_summary_typed(self, tool_fns, conn):
        """summary=True returns results=[] but keeps typed envelope rollups."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_organisms"](ctx, summary=True)
        assert response.results == []
        assert response.returned == 0
        assert response.truncated is True
        # Slice-2 DM rollups must round-trip through the typed envelope even
        # in summary mode (where the detail-row in-memory rollup path is skipped).
        assert isinstance(response.by_value_kind, list)
        assert isinstance(response.by_metric_type, list)
        assert isinstance(response.by_compartment, list)


@pytest.mark.kg
class TestListExperimentsMcpWrapper:
    """Wrapper-level integration tests for list_experiments."""

    @pytest.mark.asyncio
    async def test_typed_response_and_breakdowns(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_experiments"](
            ctx, organism="MED4", limit=5)
        assert response.total_matching >= 5
        assert response.returned == len(response.results)
        first = response.results[0]
        assert isinstance(first.experiment_id, str)
        assert isinstance(first.treatment_type, list)
        assert isinstance(first.is_time_course, bool)
        # Typed breakdown submodels — slice-2 added the 3 DM rollups +
        # by_compartment typed list.
        assert isinstance(response.by_organism, list)
        if response.by_treatment_type:
            assert isinstance(response.by_treatment_type[0].treatment_type, str)
            assert isinstance(response.by_treatment_type[0].count, int)
        assert isinstance(response.by_value_kind, list)
        assert isinstance(response.by_metric_type, list)
        assert isinstance(response.by_compartment, list)

    @pytest.mark.asyncio
    async def test_experiment_ids_not_found_typed(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        good_id = (
            "10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq"
        )
        response = await tool_fns["list_experiments"](
            ctx,
            experiment_ids=[good_id, "FAKE_EXPERIMENT_ID"],
        )
        assert response.total_matching == 1
        assert response.not_found == ["FAKE_EXPERIMENT_ID"]
        assert response.results[0].experiment_id == good_id

    @pytest.mark.asyncio
    async def test_summary_typed(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_experiments"](ctx, summary=True)
        assert response.results == []
        assert response.returned == 0
        assert response.truncated is True
        # Slice-2 DM rollups + compartment must be typed lists.
        assert isinstance(response.by_value_kind, list)
        assert isinstance(response.by_metric_type, list)
        assert isinstance(response.by_compartment, list)


@pytest.mark.kg
class TestGeneOverviewMcpWrapper:
    """Wrapper-level integration tests for gene_overview."""

    @pytest.mark.asyncio
    async def test_typed_response_and_breakdowns(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_overview"](
            ctx, locus_tags=["PMM1428", "EZ55_00275"])
        assert response.total_matching == 2
        # Typed result rows.
        tags = {r.locus_tag for r in response.results}
        assert tags == {"PMM1428", "EZ55_00275"}
        for r in response.results:
            assert isinstance(r.organism_name, str)
            assert isinstance(r.annotation_types, list)
            assert isinstance(r.expression_edge_count, int)
            assert isinstance(r.derived_metric_count, int)
            assert isinstance(r.derived_metric_value_kinds, list)
        # Typed breakdowns.
        assert isinstance(response.by_organism, list)
        assert {b.organism_name for b in response.by_organism} >= {
            r.organism_name for r in response.results}
        for b in response.by_organism:
            assert isinstance(b.count, int)

    @pytest.mark.asyncio
    async def test_not_found_typed(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_overview"](
            ctx, locus_tags=["PMM0001", "FAKE_GENE_XYZ"])
        assert response.total_matching == 1
        assert "FAKE_GENE_XYZ" in response.not_found
        assert response.results[0].locus_tag == "PMM0001"

    @pytest.mark.asyncio
    async def test_empty_locus_tags_raises_toolerror(self, tool_fns, conn):
        """Empty locus_tags raises ValueError in api → wrapper translates to ToolError."""
        from fastmcp.exceptions import ToolError
        ctx = _ctx_with_conn(conn)
        with pytest.raises(ToolError):
            await tool_fns["gene_overview"](ctx, locus_tags=[])

    @pytest.mark.asyncio
    async def test_verbose_surfaces_extras(self, tool_fns, conn):
        """verbose=True populates verbose-only fields (gene_summary, all_identifiers)."""
        ctx = _ctx_with_conn(conn)
        compact = await tool_fns["gene_overview"](ctx, locus_tags=["PMM0001"])
        verbose = await tool_fns["gene_overview"](
            ctx, locus_tags=["PMM0001"], verbose=True)
        assert compact.results[0].gene_summary is None
        assert compact.results[0].all_identifiers is None
        # Verbose row has at least one of the extras populated for an annotated gene.
        v_row = verbose.results[0]
        assert v_row.gene_summary is not None or v_row.all_identifiers is not None


@pytest.mark.kg
class TestGeneDerivedMetrics:
    """Integration tests against live KG. Baselines pinned 2026-04-26."""

    @pytest.mark.asyncio
    async def test_pmm1714_all_three_kinds(self, tool_fns, conn, kg_count):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], limit=100)
        n = kg_count(_DM_EDGES_TO_GENE, lt="PMM1714")
        assert n >= 3
        assert response.total_matching == n
        assert response.total_derived_metrics == n
        assert response.genes_with_metrics == 1
        assert response.returned == n
        kinds = {r.value_kind for r in response.results}
        assert kinds == {"numeric", "boolean", "categorical"}
        # Polymorphic value typing
        for r in response.results:
            if r.value_kind == "numeric":
                assert isinstance(r.value, float)
            elif r.value_kind == "boolean":
                assert r.value in ("flagged", "not_flagged")
            elif r.value_kind == "categorical":
                assert isinstance(r.value, str)

    @pytest.mark.asyncio
    async def test_pmm0001_diel_only(self, tool_fns, conn, kg_count):
        # value_kind='numeric' filters out the gene-level categorical DMs
        # (expression_level_class, pangenome_membership) that aren't diel-related.
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM0001"], value_kind="numeric", limit=100)
        n_numeric = kg_count(
            "MATCH (d:DerivedMetric)-[:Derived_metric_quantifies_gene]->"
            "(g:Gene {locus_tag: $lt}) RETURN count(d)", lt="PMM0001")
        assert n_numeric > 0
        assert response.total_matching == n_numeric
        assert all(r.value_kind == "numeric" for r in response.results)
        # The two non-rankable numeric DMs (peak_time_*) always sit in this set
        n_rankable = kg_count(
            "MATCH (d:DerivedMetric {rankable: 'rankable'})-[:Derived_metric_quantifies_gene]->"
            "(g:Gene {locus_tag: $lt}) RETURN count(d)", lt="PMM0001")
        assert 0 < n_rankable < n_numeric
        assert sum(1 for r in response.results if r.rankable) == n_rankable
        # Sparse extras null on non-rankable rows
        for r in response.results:
            if not r.rankable:
                assert r.rank_by_metric is None
                assert r.metric_percentile is None
                assert r.metric_bucket is None

    @pytest.mark.asyncio
    async def test_value_kind_filter_routes(self, tool_fns, conn, kg_count):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], value_kind="boolean")
        assert response.total_matching == kg_count(
            "MATCH (d:DerivedMetric)-[:Derived_metric_flags_gene]->"
            "(g:Gene {locus_tag: $lt}) RETURN count(d)", lt="PMM1714")
        # metric_type is verbose-only; assert against compact fields instead
        vesicle = next(r for r in response.results
                       if r.derived_metric_id.endswith("vesicle_proteome_member"))
        assert vesicle.value == "flagged"
        assert all(r.value_kind == "boolean" for r in response.results)

    @pytest.mark.asyncio
    async def test_kind_mismatch_not_matched(self, tool_fns, conn):
        """Gene with only boolean DM signal under value_kind='numeric' filter
        lands in not_matched, not silently dropped."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMN2A_2128"], value_kind="numeric")
        assert response.total_matching == 0
        assert response.not_matched == ["PMN2A_2128"]
        assert response.genes_without_metrics == 1
        assert response.not_found == []

    @pytest.mark.asyncio
    async def test_not_found_path(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        # When ALL locus_tags are unknown, organism cannot be inferred —
        # _validate_organism_inputs raises by design. Pass organism
        # explicitly to exercise the all-unknown-locus_tag path.
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM_DOES_NOT_EXIST"], organism="MED4")
        assert response.total_matching == 0
        assert response.not_found == ["PMM_DOES_NOT_EXIST"]
        assert response.not_matched == []
        assert response.genes_without_metrics == 0

    @pytest.mark.asyncio
    async def test_mixed_input_with_filter(self, tool_fns, conn, kg_count):
        """All 3 diagnostic buckets within single-organism scope."""
        ctx = _ctx_with_conn(conn)
        # NOTE: PMN2A_2128 (NATL2A) cannot be combined with MED4 locus_tags —
        # single-organism enforcement is by design. Use a MED4 gene with no
        # DM signal for the not_matched bucket. PMM0002 gained decay / TSS
        # DMs in the KG-SYNC-006 paper batch (verified live 2026-08-27), so the
        # DM-less probe is now PMM1720 (also the edge-case GENE_NO_DE fixture).
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714", "PMM_FAKE", "PMM1720"],
            value_kind="numeric", limit=20)
        assert response.total_matching == kg_count(  # PMM1714 numeric only
            "MATCH (d:DerivedMetric)-[:Derived_metric_quantifies_gene]->"
            "(g:Gene {locus_tag: $lt}) RETURN count(d)", lt="PMM1714")
        assert response.genes_with_metrics == 1
        assert response.genes_without_metrics == 1  # PMM1720
        assert response.not_found == ["PMM_FAKE"]
        assert response.not_matched == ["PMM1720"]

    @pytest.mark.asyncio
    async def test_compartment_filter(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], compartment="vesicle", limit=20)
        assert response.total_matching == 3  # boolean + categorical + numeric Biller 2014

    @pytest.mark.asyncio
    async def test_publication_dois_filter(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"],
            publication_dois=["10.1371/journal.pone.0043432"], limit=20)
        assert response.total_matching == 6  # 6 Waldbauer numeric DMs

    @pytest.mark.asyncio
    async def test_summary_only(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], summary=True)
        assert response.results == []
        assert response.truncated is True
        # All by_* keys present (even if empty)
        for breakdown_attr in [
            "by_value_kind", "by_metric_type", "by_metric",
            "by_compartment", "by_treatment_type",
            "by_background_factors", "by_publication",
        ]:
            assert hasattr(response, breakdown_attr)

    @pytest.mark.asyncio
    async def test_by_metric_disambiguates(self, tool_fns, conn, kg_count):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], summary=True)
        # one entry per DM touching the gene
        assert len(response.by_metric) == kg_count(_DM_EDGES_TO_GENE, lt="PMM1714")
        for entry in response.by_metric:
            assert entry.derived_metric_id  # non-empty
            assert entry.name
            assert entry.metric_type
            assert entry.value_kind in ("numeric", "boolean", "categorical")
            assert entry.count >= 1

    @pytest.mark.asyncio
    async def test_verbose_columns(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], verbose=True, limit=1)
        row = response.results[0]
        # Verbose-only fields populated (treatment, light_condition, etc.)
        assert row.treatment is not None
        assert row.light_condition is not None
        assert row.experimental_context is not None
        # p_value forward-compat — None today
        assert row.p_value is None

    @pytest.mark.asyncio
    async def test_organism_conflict_raises(self, tool_fns, conn):
        from fastmcp.exceptions import ToolError
        ctx = _ctx_with_conn(conn)
        with pytest.raises(ToolError):
            await tool_fns["gene_derived_metrics"](
                ctx, locus_tags=["PMM1714", "PMN2A_2128"])  # MED4 + NATL2A

    @pytest.mark.asyncio
    async def test_truncation(self, tool_fns, conn, kg_count):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], limit=2)
        assert response.returned == 2
        assert response.truncated is True
        assert response.total_matching == kg_count(_DM_EDGES_TO_GENE, lt="PMM1714")


@pytest.mark.kg
class TestGenesByNumericMetric:
    """Integration tests against live KG. Baselines pinned 2026-04-26.

    Calls the api function directly with a real GraphConnection. Most cases
    use the api/ surface (mirrors `gene_derived_metrics` precedent — also
    plays well with hard-fail tests that need ValueError, not ToolError).
    """

    @pytest.mark.asyncio
    async def test_damping_ratio_top_decile(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], metric_bucket=["top_decile"],
            limit=50)
        assert response.total_matching == 32
        assert response.total_genes == 32
        assert len(response.by_metric) == 1
        bm = response.by_metric[0]
        assert bm.metric_type == "damping_ratio"
        assert bm.count == 32
        assert bm.value_min == pytest.approx(12.2, abs=0.5)
        assert bm.value_median == pytest.approx(15.9, abs=0.5)
        assert bm.value_max == pytest.approx(25.3, abs=0.1)
        assert bm.rank_min == 1
        assert bm.rank_max == 32
        # Sort key validated: row 1 PMM1545 (rpsH, value=25.3, rank=1)
        first = response.results[0]
        assert first.locus_tag == "PMM1545"
        assert first.gene_name == "rpsH"
        assert first.value == pytest.approx(25.3, abs=0.1)
        assert first.rank_by_metric == 1

    @pytest.mark.asyncio
    async def test_top_decile_full_dm_context(self, tool_fns, conn):
        """Full-DM precomputed stats (dm.value_*) populated alongside slice."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], metric_bucket=["top_decile"],
            limit=1)
        bm = response.by_metric[0]
        assert bm.dm_value_min == pytest.approx(0.2, abs=0.1)
        assert bm.dm_value_q1 == pytest.approx(2.8, abs=0.5)
        assert bm.dm_value_median == pytest.approx(4.9, abs=0.5)
        assert bm.dm_value_q3 == pytest.approx(7.8, abs=0.5)
        assert bm.dm_value_max == pytest.approx(25.3, abs=0.1)

    @pytest.mark.asyncio
    async def test_mixed_rankable_soft_exclude(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio", "peak_time_protein_h"],
            metric_bucket=["top_decile"], limit=50)
        # damping_ratio survives, peak_time_protein_h soft-excluded
        assert response.total_matching == 32
        assert len(response.excluded_derived_metrics) == 1
        excluded = response.excluded_derived_metrics[0]
        assert excluded.derived_metric_id.endswith("peak_time_protein_h")
        assert excluded.rankable is False
        assert "metric_bucket" in excluded.reason
        assert len(response.warnings) == 1

    def test_all_non_rankable_hard_fail(self, conn):
        """All-non-rankable + metric_bucket → api raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            api.genes_by_numeric_metric(
                metric_types=["peak_time_transcript_h"],
                metric_bucket=["top_decile"], conn=conn)
        msg = str(exc_info.value)
        assert "rankable=False" in msg or "non-rankable" in msg
        assert "metric_bucket" in msg

    def test_p_value_filter_hard_fail_today(self, conn):
        """significant_only against has_p_value=False DM → ValueError."""
        with pytest.raises(ValueError) as exc_info:
            api.genes_by_numeric_metric(
                metric_types=["damping_ratio"],
                significant_only=True, conn=conn)
        msg = str(exc_info.value)
        assert "has_p_value" in msg

    @pytest.mark.asyncio
    async def test_max_rank_top_n(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], max_rank=5, limit=10)
        assert response.returned == 5
        assert response.total_matching == 5
        ranks = [r.rank_by_metric for r in response.results]
        assert ranks == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_min_value_threshold_non_rankable(self, tool_fns, conn):
        """min_value works on non-rankable DMs (raw threshold, not gated)."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["mascot_identification_probability"],
            organism="MED4", min_value=99, limit=50)
        assert response.total_matching >= 1
        for r in response.results:
            assert r.value >= 99
        # min_value is not gated → no soft-exclude
        assert response.excluded_derived_metrics == []

    @pytest.mark.asyncio
    async def test_cross_organism_no_scope(self, tool_fns, conn, kg_count):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["cell_abundance_biovolume_normalized"],
            metric_bucket=["top_quartile"], limit=10)
        live = {
            org: kg_count(_TOP_QUARTILE_CELL_ABUNDANCE, org=org)
            for org in ("Prochlorococcus MIT9312", "Prochlorococcus MIT9313")
        }
        assert all(v > 0 for v in live.values())
        assert response.total_matching == sum(live.values())
        assert len(response.by_organism) == 2
        org_counts = {o.organism_name: o.count for o in response.by_organism}
        assert org_counts == live
        assert len(response.by_metric) == 2
        assert response.not_matched_organism is None

    @pytest.mark.asyncio
    async def test_cross_organism_with_scope(self, tool_fns, conn, kg_count):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["cell_abundance_biovolume_normalized"],
            metric_bucket=["top_quartile"], organism="MIT9313", limit=10)
        assert response.total_matching == kg_count(
            _TOP_QUARTILE_CELL_ABUNDANCE, org="Prochlorococcus MIT9313")
        assert len(response.by_organism) == 1
        assert "MIT9313" in response.by_organism[0].organism_name
        assert response.not_matched_organism is None

    @pytest.mark.asyncio
    async def test_locus_tags_intersection(self, tool_fns, conn):
        """Top-5 ranked → intersect locus_tags → 5 rows."""
        ctx = _ctx_with_conn(conn)
        # Step 1: pull top-5 by max_rank
        top5 = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], max_rank=5, limit=10)
        top5_locs = [r.locus_tag for r in top5.results]
        assert len(top5_locs) == 5
        # Step 2: re-call with locus_tags filter
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], locus_tags=top5_locs,
            limit=10)
        assert response.total_matching == 5
        assert response.returned == 5
        assert {r.locus_tag for r in response.results} == set(top5_locs)

    @pytest.mark.asyncio
    async def test_summary_only(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], metric_bucket=["top_decile"],
            summary=True)
        assert response.results == []
        assert response.total_matching == 32
        assert response.returned == 0
        # truncated = total_matching (32) > offset (0) + returned (0)
        assert response.truncated is True
        # Envelope still populated
        assert len(response.by_metric) == 1
        assert response.total_genes == 32

    @pytest.mark.asyncio
    async def test_truncation_pagination(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        page1 = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], limit=10)
        assert page1.returned == 10
        assert page1.truncated is True
        assert page1.total_matching == 312
        page2 = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], limit=10, offset=10)
        assert page2.returned == 10
        # No locus_tag overlap between consecutive pages
        p1_locs = {r.locus_tag for r in page1.results}
        p2_locs = {r.locus_tag for r in page2.results}
        assert p1_locs & p2_locs == set()

    @pytest.mark.asyncio
    async def test_verbose_columns(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], limit=1, verbose=True)
        row = response.results[0]
        assert row.metric_type == "damping_ratio"
        assert row.unit is not None  # may be empty string but not None
        assert row.compartment == "whole_cell"
        assert row.experiment_id is not None
        assert row.treatment is not None
        assert row.light_condition is not None
        assert row.experimental_context is not None
        assert row.gene_function_description is not None
        assert row.gene_summary is not None
        # Forward-compat: p_value field accepts None today
        assert row.p_value is None

    @pytest.mark.asyncio
    async def test_by_metric_filtered_vs_full_dm(self, tool_fns, conn):
        """Filtered slice value range tighter than full-DM range; max
        coincides because top-decile slice contains the global max."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["damping_ratio"], metric_bucket=["top_decile"],
            limit=1)
        bm = response.by_metric[0]
        # Filtered slice min is well above full-DM min
        assert bm.value_min == pytest.approx(12.2, abs=0.5)
        assert bm.dm_value_min == pytest.approx(0.2, abs=0.1)
        assert bm.value_min > bm.dm_value_min
        # Slice max == full-DM max (top decile includes the global max)
        assert bm.value_max == pytest.approx(25.3, abs=0.1)
        assert bm.dm_value_max == pytest.approx(25.3, abs=0.1)
        assert bm.value_max == pytest.approx(bm.dm_value_max, abs=0.1)


@pytest.mark.kg
class TestGenesByBooleanMetric:
    """Integration tests against live KG. Baselines pinned 2026-04-26.

    Boolean DM drill-down — filtered slice + full-DM precomputed counts.
    Mirrors `TestGenesByNumericMetric` structure.
    """

    @pytest.mark.asyncio
    async def test_vesicle_proteome_cross_organism(self, tool_fns, conn, run_query):
        """Happy path: MED4 + MIT9313 vesicle-proteome members, one row per
        flag edge (positive-only DMs today, so rows == flagged edges)."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_boolean_metric"](
            ctx, metric_types=["vesicle_proteome_member"], limit=200)
        live = {x["org"]: x["n"] for x in run_query(
            "MATCH (d:DerivedMetric {metric_type: 'vesicle_proteome_member'})"
            "-[r:Derived_metric_flags_gene]->(g:Gene)-[:Gene_belongs_to_organism]->(o) "
            "RETURN o.preferred_name AS org, count(r) AS n")}
        assert set(live) == {"Prochlorococcus MED4", "Prochlorococcus MIT9313"}
        assert response.total_matching == sum(live.values())
        assert response.total_genes == sum(live.values())
        # Cross-organism: by_organism shows both strains
        org_counts = {o.organism_name: o.count for o in response.by_organism}
        assert org_counts == live
        # by_metric: filtered counts == full-DM precomputed counts (positive-only)
        assert len(response.by_metric) == 2
        for bm in response.by_metric:
            assert bm.value_kind == "boolean"
            assert bm.true_count == bm.count
            assert bm.false_count == 0
            assert bm.dm_true_count == bm.count
            assert bm.dm_false_count == 0
        # by_value: every surviving row is 'true'
        assert response.by_value == [
            type(response.by_value[0])(value="flagged", count=58)
        ] or all(bv.value == "flagged" for bv in response.by_value)

    @pytest.mark.asyncio
    async def test_flag_false_zero_rows(self, tool_fns, conn):
        """flag_value=False → 0 detail rows (positive-only KG storage today).

        by_metric keeps a zero-count entry per selected DM (llm-review
        2b.3) instead of the DM vanishing from the envelope — count and
        false_count both read 0, dm_false_count confirms positive-only.
        A warning names each positive-only DM.
        """
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_boolean_metric"](
            ctx, metric_types=["vesicle_proteome_member"], flag_value=False, limit=10)
        assert response.total_matching == 0
        assert response.returned == 0
        assert len(response.by_metric) == 2  # MED4 + MIT9313 DMs, both kept
        for bm in response.by_metric:
            assert bm.count == 0
            assert bm.false_count == 0
            assert bm.dm_false_count == 0
        # excluded_derived_metrics always [] for boolean (no gates)
        assert response.excluded_derived_metrics == []
        assert any(
            "stores positive flags only" in w and "false_count" in w
            for w in response.warnings
        )

    @pytest.mark.asyncio
    async def test_locus_tags_scoping(self, tool_fns, conn):
        """3 known vesicle MED4 genes + 1 non-vesicle → 3 rows matching."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_boolean_metric"](
            ctx, metric_types=["vesicle_proteome_member"],
            locus_tags=["PMM0090", "PMM0097", "PMM0107", "PMM0001"],
            limit=10)
        # PMM0001 exists in KG but isn't flagged → silent absence (no not_found)
        assert response.total_matching == 3
        assert response.returned == 3
        result_locs = {r.locus_tag for r in response.results}
        assert result_locs == {"PMM0090", "PMM0097", "PMM0107"}
        # locus_tags do NOT participate in not_found_ids/not_matched_ids;
        # those are reserved for DM-level inputs.
        assert response.not_found_ids == []
        assert response.not_matched_ids == []

    @pytest.mark.asyncio
    async def test_kind_mismatch_surfaces_as_not_matched_with_warning(
            self, tool_fns, conn):
        """Numeric DM ID passed to boolean tool → not_matched_ids (it
        genuinely exists, just as a different kind) + a sibling-tool
        warning, no raise (llm-review 2b.3)."""
        numeric_dm_id = (
            "derived_metric:journal.pone.0043432:"
            "table_s2_waldbauer_diel_metrics:damping_ratio"
        )
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_boolean_metric"](
            ctx, derived_metric_ids=[numeric_dm_id], limit=5)
        assert response.total_matching == 0
        assert response.results == []
        assert response.not_found_ids == []
        assert response.not_matched_ids == [numeric_dm_id]
        assert any(
            f"{numeric_dm_id} exists as value_kind=numeric" in w
            and "genes_by_numeric_metric" in w
            for w in response.warnings
        )


@pytest.mark.kg
class TestGenesByCategoricalMetric:
    """Integration tests against live KG. Baselines pinned 2026-04-26.

    Categorical DM drill-down — filtered slice + full-DM histogram per DM.
    Mirrors `TestGenesByNumericMetric` structure.
    """

    @pytest.mark.asyncio
    async def test_psortb_membrane_categories(self, tool_fns, conn):
        """Happy path: PSORTb Outer Membrane / Periplasmic across MED4 + MIT9313."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_categorical_metric"](
            ctx, metric_types=["predicted_subcellular_localization"],
            categories=["Outer Membrane", "Periplasmic"], limit=50)
        assert response.total_matching == 14
        # by_organism: MED4 (8) + MIT9313 (6)
        org_counts = {o.organism_name: o.count for o in response.by_organism}
        med4_hits = [c for n, c in org_counts.items() if "MED4" in n]
        mit9313_hits = [c for n, c in org_counts.items() if "MIT9313" in n]
        assert med4_hits == [8]
        assert mit9313_hits == [6]
        # by_metric: 2 DMs (one per organism); each carries filtered + full DM
        assert len(response.by_metric) == 2
        # Sort by_metric by count desc — MED4 (8) first, MIT9313 (6) second
        med4_bm = next(b for b in response.by_metric if "med4" in b.derived_metric_id)
        mit9313_bm = next(b for b in response.by_metric if "mit9313" in b.derived_metric_id)
        # MED4: 5 OM + 3 PP filtered slice; full DM histogram strict superset
        med4_filtered = {c.category: c.count for c in med4_bm.by_category}
        assert med4_filtered == {"Outer Membrane": 5, "Periplasmic": 3}
        med4_full = {c.category: c.count for c in med4_bm.dm_by_category}
        assert med4_full["Outer Membrane"] == 5
        assert med4_full["Periplasmic"] == 3
        # Full DM also includes Cytoplasmic / Unknown / etc.
        assert "Cytoplasmic" in med4_full or "Unknown" in med4_full
        # MIT9313: 3 OM + 3 PP filtered slice
        mit_filtered = {c.category: c.count for c in mit9313_bm.by_category}
        assert mit_filtered == {"Outer Membrane": 3, "Periplasmic": 3}

    @pytest.mark.asyncio
    async def test_unknown_category_raises(self, tool_fns, conn):
        """Unknown category → ToolError (FastMCP wraps the api ValueError).

        Error message must list every observed `allowed_category` so the
        caller can self-correct without an extra `list_derived_metrics` call.
        """
        from fastmcp.exceptions import ToolError
        ctx = _ctx_with_conn(conn)
        with pytest.raises(ToolError) as exc_info:
            await tool_fns["genes_by_categorical_metric"](
                ctx, metric_types=["predicted_subcellular_localization"],
                categories=["nonsense"], limit=10)
        msg = str(exc_info.value)
        # Spec: error message lists every observed allowed_category
        for cat in (
            "Cytoplasmic", "Cytoplasmic Membrane", "Extracellular",
            "Outer Membrane", "Periplasmic", "Unknown",
        ):
            assert cat in msg, f"missing '{cat}' from error message: {msg}"

    @pytest.mark.asyncio
    async def test_kind_mismatch_surfaces_as_not_matched_with_warning(
            self, tool_fns, conn):
        """Numeric DM ID passed to categorical tool → not_matched_ids +
        a sibling-tool warning, no raise (llm-review 2b.3)."""
        numeric_dm_id = (
            "derived_metric:journal.pone.0043432:"
            "table_s2_waldbauer_diel_metrics:damping_ratio"
        )
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_categorical_metric"](
            ctx, derived_metric_ids=[numeric_dm_id], limit=5)
        assert response.total_matching == 0
        assert response.results == []
        assert response.not_found_ids == []
        assert response.not_matched_ids == [numeric_dm_id]
        assert any(
            f"{numeric_dm_id} exists as value_kind=numeric" in w
            and "genes_by_numeric_metric" in w
            for w in response.warnings
        )

    @pytest.mark.asyncio
    async def test_by_category_rename_envelope_and_nested(self, tool_fns, conn):
        """`item` → `category` rename verified at envelope AND nested layers.

        The api/ orchestration step 9 walks `by_metric[*].by_category` and
        `by_metric[*].dm_by_category` to apply the rename — confirms that
        post-Cypher walk fired.
        """
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_categorical_metric"](
            ctx, metric_types=["predicted_subcellular_localization"],
            categories=["Outer Membrane", "Periplasmic"], limit=50)
        # Envelope-level by_category: keys {category, count}
        assert response.by_category, "envelope by_category should not be empty"
        env_freq = response.by_category[0]
        assert hasattr(env_freq, "category")
        assert hasattr(env_freq, "count")
        # Pydantic model dump confirms the renamed keys
        assert set(env_freq.model_dump().keys()) == {"category", "count"}
        # Nested by_metric[0].by_category — should also be renamed
        assert response.by_metric, "by_metric should not be empty"
        nested_freq = response.by_metric[0].by_category[0]
        assert hasattr(nested_freq, "category")
        assert hasattr(nested_freq, "count")
        assert set(nested_freq.model_dump().keys()) == {"category", "count"}
        # Nested by_metric[0].dm_by_category — same rename
        nested_full = response.by_metric[0].dm_by_category[0]
        assert hasattr(nested_full, "category")
        assert hasattr(nested_full, "count")
        assert set(nested_full.model_dump().keys()) == {"category", "count"}


@pytest.mark.kg
class TestSliceTwoSearchTextReach:
    """Slice-2 D5: list_experiments / list_publications search_text routes through
    DM-derived tokens (derived_metric_search_text on Experiment / Publication).
    Negative assertion confirms genes_by_function is NOT enriched (function-vs-
    measurement category-error guard)."""

    def test_list_experiments_search_diel_amplitude_hits_waldbauer(self, conn):
        result = api.list_experiments(search_text="diel amplitude", limit=5, conn=conn)
        ids = [row["experiment_id"] for row in result["results"]]
        assert any("waldbauer_2012" in i.lower() for i in ids), \
            f"Expected Waldbauer 2012 in {ids}"

    def test_list_publications_search_damping_ratio_hits(self, conn):
        result = api.list_publications(search_text="damping ratio", limit=5, conn=conn)
        dois = [row["doi"] for row in result["results"]]
        assert "10.1371/journal.pone.0043432" in dois, \
            f"Expected Waldbauer 2012 (10.1371/journal.pone.0043432) in {dois}"

    def test_list_publications_search_vesicle_proteome_hits(self, conn):
        result = api.list_publications(search_text="vesicle proteome", limit=5, conn=conn)
        # Biller 2014 / 2022 vesicle proteomics papers (and others)
        assert result["total_matching"] >= 1

    def test_genes_by_function_NOT_enriched_with_dm_tokens(self, conn):
        """D5 regression guard: geneFullText must NOT match every protein-quantified
        gene for 'damping ratio'. If geneFullText were DM-enriched, this would
        return ~312 Waldbauer 2012 genes."""
        result = api.genes_by_function(search_text="damping ratio", limit=5, conn=conn)
        assert result["total_matching"] < 50, (
            f"genes_by_function returned {result['total_matching']} hits for "
            "'damping ratio' — D5 regression: geneFullText looks DM-enriched."
        )


# ---------------------------------------------------------------------------
# list_metabolites — chemistry slice-1 Tool #1
# Smoke values frozen 2026-05-03 (Phase 1 spec lines 1015-1028).
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestListMetabolites:
    """Live-KG smoke tests for the list_metabolites api function."""

    def test_no_filters_returns_all(self, conn, kg_count):
        """Unfiltered query reports total Metabolite node count."""
        result = api.list_metabolites(conn=conn)
        assert result["total_matching"] == kg_count("MATCH (m:Metabolite) RETURN count(m)")

    def test_elements_n_filter(self, conn):
        """N-bearing metabolites total (1693 → 1688 at the 2026-10-15
        metabolite-identity rebuild: merges + role removal; → 1692 at the
        2026-10-15T19:17Z stereo-guard rebuild: 9 stereo splits + 2
        keep_separate; → 1694 at the 2026-10-18T18:40Z GO-transport rebuild:
        2 of the 29 new GO-substrate nodes carry N)."""
        result = api.list_metabolites(elements=["N"], conn=conn)
        assert result["total_matching"] == 1706  # → 1706 2026-10-28T05:04Z: Ford 2021 strains (KEGG metabolites only new strains reach) ← 1694 → 1663 2026-10-24T17:33Z: TCDB 3a removed 65 transport-only metabolites → 1673 2026-10-26T04:21Z: 10 N-bearing generic forms added (TCDB review)

    def test_elements_n_and_p_filter(self, conn):
        """Multi-element AND filter (must contain both N and P)."""
        result = api.list_metabolites(elements=["N", "P"], conn=conn)
        assert result["total_matching"] == 593  # → 593 2026-10-28T05:04Z: Ford 2021 strains ← 583 → 574 (2026-10-15 identity rebuild) → 576 (stereo-guard splits) → 574 (2026-10-24T17:33Z, TCDB 3a removed metabolites)

    def test_organism_plus_elements_filter(self, conn):
        """MED4 + N elements (the canonical N-source primitive): 992.

        813 → 992 (verified live 2026-08-20): InterPro Layer-B GO/EC
        enrichment (new Gene→Reaction links) + the 2026-08 TCDB rebuild
        expanded MED4's chemistry-reachable metabolite set
        (by_evidence_source now: metabolism 659, transport 510,
        metabolomics 90). 992 → 1002 at the 2026-10-15 metabolite-identity
        rebuild (re-keyed chebi: → KEGG nodes gain catalysis reach; 33
        class nodes gain ChEBI generic formulas + elements); → 1003 at the
        stereo-guard rebuild (split stereo forms)."""
        result = api.list_metabolites(
            organism_names=["Prochlorococcus MED4"],
            elements=["N"],
            conn=conn,
        )
        assert result["total_matching"] == 630  # 1003 → 630 2026-10-24T17:33Z: organism transport arm now direct systems only (Organism_has_metabolite 88,579 → 52,648)

    def test_pathway_id_filter(self, conn):
        """Nitrogen metabolism pathway (ko00910) has 18 metabolites."""
        result = api.list_metabolites(
            pathway_ids=["kegg.pathway:ko00910"], conn=conn,
        )
        assert result["total_matching"] == 18

    def test_metabolite_ids_with_unknown_populates_not_found(self, conn):
        """Batch ID lookup: known glucose ID resolves; unknown surfaces in
        not_found.metabolite_ids (typed dict per spec)."""
        result = api.list_metabolites(
            metabolite_ids=[
                "kegg.compound:C00031", "kegg.compound:C99999",
            ],
            conn=conn,
        )
        assert result["total_matching"] == 1
        assert len(result["results"]) == 1
        assert result["not_found"]["metabolite_ids"] == [
            "kegg.compound:C99999"
        ]
        # Other not_found buckets stay empty (typed dict shape)
        assert result["not_found"]["organism_names"] == []
        assert result["not_found"]["pathway_ids"] == []

    def test_search_glucose_returns_score(self, conn):
        """Lucene search by name returns ranked rows with `score` field.

        Phase 2 Item 1: `search` kwarg renamed to `search_text` (the
        Cypher `$search` param stays unchanged).
        """
        result = api.list_metabolites(search_text="glucose", conn=conn)
        assert len(result["results"]) >= 1
        assert "score" in result["results"][0]

    def test_evidence_sources_transport_filter(self, conn):
        """transport-only evidence filter: 1,382 metabolites (1,462 before the
        2026-10-15 identity rebuild: −57 roles, merges)."""
        result = api.list_metabolites(
            evidence_sources=["transport"], conn=conn,
        )
        assert result["total_matching"] == 1311  # → 1311 2026-10-28T05:04Z: Ford 2021 strains (TC systems only new-strain genes hit) ← 1382 → 1285 2026-10-24T17:33Z: 'transport' = substrate of a kept TCDB system (65 removed, 31 lost the tag) → 1282 2026-10-26T04:21Z: TCDB substrate filter

    def test_summary_mode_empty_results_envelope_populated(self, conn, kg_count):
        """summary=True returns no result rows but envelope is populated."""
        result = api.list_metabolites(summary=True, conn=conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] == kg_count("MATCH (m:Metabolite) RETURN count(m)")
        # Envelope rollups present (lists, possibly empty but typed)
        assert isinstance(result["top_organisms"], list)
        assert isinstance(result["top_metabolite_pathways"], list)
        assert isinstance(result["by_evidence_source"], list)
        assert isinstance(result["xref_coverage"], dict)
        assert isinstance(result["mass_stats"], dict)

    def test_organism_names_known_plus_unknown(self, conn):
        """Known organism passes through; unknown lands in not_found.organism_names.

        Guards against the OrganismTaxon-vs-Organism label regression — a wrong
        label silently buckets every input as not_found.
        """
        result = api.list_metabolites(
            organism_names=["Prochlorococcus MED4", "Bogus organism"],
            summary=True,
            conn=conn,
        )
        assert result["not_found"]["organism_names"] == ["Bogus organism"]
        assert result["total_matching"] > 0


@pytest.mark.kg
class TestGenesByMetabolite:
    """Live-KG round-trip smokes for genes_by_metabolite.

    Each test pipes the api result through `GenesByMetaboliteResponse(**r)`.
    This is the contract-drift guard: mocked unit tests can't catch a
    summary-Cypher RETURN-key rename, but Pydantic validation here will
    raise if any future change to the summary builder emits a field name
    or shape that diverges from the response model. (Caught the B1/B2/B3
    drift during the genes_by_metabolite Phase 2 build, 2026-05-03.)
    """

    def test_urea_med4_both_arms_round_trip(self, conn):
        """Urea x MED4 under the TCDB direct gate (spec tcdb-cleanup-surface,
        G1 / transport arm). Discovery (target build 2026-10-24):
          MATCH (g:Gene {organism_name:'Prochlorococcus MED4'})
            -[r:Gene_has_tcdb_family {tcdb_gate:'direct'}]->(s)
            -[:Tcdb_family_transports_metabolite]->(:Metabolite {id:'kegg.compound:C00086'})
          RETURN g.locus_tag, s.id, collect(r.tcdb_call)
          -> urtA-E (PMM0970-PMM0974) x {3.A.1.4.4 (best hit + eggNOG),
             3.A.1.4.5 (eggNOG)} = 10 rows, one per (gene, system).
        metabolism 4 + transport 10 + GO 11 = 25; 9 genes (ureABC/urtA-E
        union). The pre-3a 20 inherited 3.A.1 rows are gone (no substrate
        edges above tc_system), so no family-dominance warning fires."""
        from multiomics_explorer.mcp_server.tools import (
            GenesByMetaboliteResponse,
        )

        result = api.genes_by_metabolite(
            metabolite_ids=["kegg.compound:C00086"],
            organism="Prochlorococcus MED4",
            limit=50,
            conn=conn,
        )
        model = GenesByMetaboliteResponse(**result)
        assert {r.evidence_source: r.count for r in model.by_evidence_source} == {
            "metabolism": 4, "transport": 10, "go_transport": 11,
        }
        assert model.total_matching == 25
        assert model.gene_count_total == 9
        urea_row = next(
            r for r in model.by_metabolite
            if r.metabolite_id == "kegg.compound:C00086"
        )
        assert urea_row.metabolism_rows == 4
        assert urea_row.tcdb_direct_rows == 10
        assert urea_row.tcdb_family_rows == 0
        assert {r.tcdb_route: r.count for r in model.by_tcdb_route} == {"direct": 10}
        # urea has direct genes and no family-only MED4 gene reaches it
        assert model.tcdb_family_substrates_not_shown.genes == 0
        assert not any("include_tcdb_family_substrates" in w for w in model.warnings)

        # Sort: metabolism -> transport direct -> GO; within transport
        # tcdb_identity DESC NULLS LAST (eggNOG-only 3.A.1.4.5 rows last).
        rows = model.results
        tier_rank = {"metabolism": 0, "transport": 1, "go_transport": 2}
        ranks = [tier_rank[r.evidence_source] for r in rows]
        assert ranks == sorted(ranks)
        transport = [r for r in rows if r.evidence_source == "transport"]
        idents = [r.tcdb_identity for r in transport]
        non_null = [i for i in idents if i is not None]
        assert non_null == sorted(non_null, reverse=True)
        assert idents == non_null + [None] * (len(idents) - len(non_null))
        assert {r.tcdb_family_id for r in transport} == {
            "tcdb:3.A.1.4.4", "tcdb:3.A.1.4.5"}
        for r in rows:
            if r.evidence_source == "transport":
                assert r.tcdb_route == "direct"
                assert r.attached_tcdb_id == r.tcdb_family_id
                assert r.tcdb_direction == "uptake"
                assert r.tcdb_calls
                assert r.tcdb_substrate_system_count is None
            else:
                assert r.tcdb_route is None
                assert r.tcdb_calls is None
                assert r.tcdb_family_id is None
        # top_genes carry the KG gene-level precompute + per-route rows
        urt = next(g for g in model.top_genes if g.locus_tag == "PMM0974")
        assert urt.tcdb_assignment_count == 2
        assert urt.tcdb_direct_rows == 2
        assert urt.tcdb_family_rows == 0

    def test_retired_substrate_depth_kwarg_raises(self, conn):
        """TCDB cleanup G3: `substrate_depth` (and the older
        `transport_confidence`) are removed with no alias."""
        for kw in ({"substrate_depth": ["most_specific"]},
                   {"transport_confidence": "substrate_confirmed"}):
            with pytest.raises(TypeError):
                api.genes_by_metabolite(
                    metabolite_ids=["kegg.compound:C00086"],
                    organism="Prochlorococcus MED4",
                    conn=conn, **kw,
                )

    def test_nitrite_med4_transport_only_direct(self, conn):
        """Nitrite x MED4: transport-only, direct rows only. Discovery:
          MATCH (g:Gene {organism_name:'Prochlorococcus MED4'})
            -[:Gene_has_tcdb_family {tcdb_gate:'direct'}]->(s)
            -[:Tcdb_family_transports_metabolite]->(:Metabolite {id:'kegg.compound:C00088'})
          RETURN g.locus_tag, s.id
          -> cynA/B/D (PMM0370-PMM0372) x {3.A.1.16.1, 3.A.1.16.2} = 6 rows.
        The pre-3a 23 inherited 3.A.1 genes are gone."""
        from multiomics_explorer.mcp_server.tools import (
            GenesByMetaboliteResponse,
        )

        result = api.genes_by_metabolite(
            metabolite_ids=["kegg.compound:C00088"],
            organism="Prochlorococcus MED4",
            limit=50,
            conn=conn,
        )
        model = GenesByMetaboliteResponse(**result)
        assert model.total_matching == 6
        assert model.gene_count_total == 3
        es_counts = {r.evidence_source: r.count for r in model.by_evidence_source}
        assert es_counts == {"transport": 6}
        assert {r.tcdb_route: r.count for r in model.by_tcdb_route} == {"direct": 6}
        assert {r.locus_tag for r in model.results} == {
            "PMM0370", "PMM0371", "PMM0372"}
        assert {r.tcdb_family_id for r in model.results} == {
            "tcdb:3.A.1.16.1", "tcdb:3.A.1.16.2"}


@pytest.mark.kg
class TestTcdbDirectGateCrossToolAgreement:
    """TCDB cleanup G1: rows, envelope counts and the KG's gated transport
    precomputes are projections of ONE (gene, system, metabolite) set — the
    `tcdb_gate = 'direct'` edges. The full-organism agreement sweeps live in
    test_tcdb_cleanup_surface.py; these are the cross-tool spot checks.
    """

    _MED4 = "Prochlorococcus MED4"
    _NITRITE = "kegg.compound:C00088"

    def test_gene_overview_pmm0001_no_tcdb_call(self, conn):
        """PMM0001 has no TCDB edge -> nulls / zeros, never a sentinel; the
        removed fields are gone."""
        row = api.gene_overview(["PMM0001"], conn=conn)["results"][0]
        for gone in ("transporter_count", "tcdb_evidence_score_max",
                     "transport_substrate_resolution", "tcdb_family_count"):
            assert gone not in row
        assert row["tcdb_assignment_count"] == 0
        assert row["tcdb_best_hit_identity"] is None
        assert row["transported_metabolite_count"] == 0
        assert "transport" not in row["evidence_sources"]

    def test_gene_overview_cynd_direct(self, conn):
        """cynD PMM0372: 2 direct systems, 3 metabolites, best hit 59.2%."""
        row = api.gene_overview(["PMM0372"], conn=conn)["results"][0]
        assert row["tcdb_assignment_count"] == 2
        assert row["transported_metabolite_count"] == 3
        assert row["tcdb_best_hit_identity"] == pytest.approx(59.2)
        assert "transport" in row["evidence_sources"]

    def test_gene_overview_pmm0392_family_only(self, conn):
        """PMM0392 cbiQ: 7 gated eggNOG subfamily calls (3.A.1.25..33), no
        direct system -> transported_metabolite_count 0 and no 'transport'
        evidence source; its best hit is below the gate but still reported
        (25.5%, rank-don't-filter)."""
        row = api.gene_overview(["PMM0392"], conn=conn)["results"][0]
        assert row["tcdb_assignment_count"] == 7
        assert row["transported_metabolite_count"] == 0
        assert "transport" not in row["evidence_sources"]
        assert row["tcdb_best_hit_identity"] is not None
        assert row["tcdb_best_hit_identity"] < 40

    def test_gene_overview_counts_pmm0392_pmm0001(self, conn):
        res = api.gene_overview(["PMM0392", "PMM0001"], conn=conn)
        rows = {r["locus_tag"]: r for r in res["results"]}
        assert rows["PMM0392"]["tcdb_assignment_count"] == 7
        assert rows["PMM0392"]["cazy_family_count"] == 0
        assert rows["PMM0001"]["tcdb_assignment_count"] == 0
        assert res["has_tcdb"] == 1
        assert res["has_cazy"] == 0

    def test_mbg_pmm0392_family_walk_only(self, conn):
        """Family-only gene: default transport arm empty + walk warning;
        walk on adds family rows only, by_gene counts them."""
        off = api.metabolites_by_gene(
            ["PMM0392"], self._MED4, evidence_sources=["transport"],
            limit=1000, conn=conn)
        assert off["results"] == []
        assert any("include_tcdb_family_substrates=True" in w
                   for w in off["warnings"]), off["warnings"]
        on = api.metabolites_by_gene(
            ["PMM0392"], self._MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=1000, conn=conn)
        assert not on["truncated"]
        assert on["results"]
        assert {r["tcdb_route"] for r in on["results"]} == {"family"}
        by_gene = next(g for g in on["by_gene"] if g["locus_tag"] == "PMM0392")
        assert by_gene["tcdb_direct_rows"] == 0
        assert by_gene["tcdb_family_rows"] == len(on["results"])
        assert by_gene["tcdb_assignment_count"] == 7

    def test_mbg_cynd_transport_metabolites_equal_gene_overview_count(self, conn):
        mbg = api.metabolites_by_gene(
            ["PMM0372"], self._MED4, evidence_sources=["transport"],
            limit=1000, conn=conn)
        mets = {r["metabolite_id"] for r in mbg["results"]
                if r["target_kind"] == "metabolite"}
        ov = api.gene_overview(["PMM0372"], conn=conn)["results"][0]
        assert len(mets) == ov["transported_metabolite_count"] == 3

    def test_gbm_nitrite_med4_distinct_transport_genes(self, conn, kg_count):
        gbm = api.genes_by_metabolite(
            [self._NITRITE], self._MED4, evidence_sources=["transport"],
            limit=1000, conn=conn)
        assert not gbm["truncated"]
        live = kg_count(
            "MATCH (g:Gene {organism_name: $o})-[gt:Gene_has_tcdb_family]->"
            "(:TcdbFamily)-[:Tcdb_family_transports_metabolite]->"
            "(:Metabolite {id: $m}) "
            f"WHERE {TCDB_DIRECT_GATE_PREDICATE} "
            "RETURN count(DISTINCT g)", o=self._MED4, m=self._NITRITE)
        genes = {r["locus_tag"] for r in gbm["results"]}
        assert len(genes) == gbm["gene_count_total"] == live == 3

    def test_list_metabolites_transporter_gene_count_closes_trap_loop(self, conn, kg_count):
        """list_metabolites row `transporter_gene_count` == the KG's gated
        precompute; the transport-only trap loop (catalyst 0, transporter
        > 0) is pinned on tetracycline (kegg.compound:C06570; was sodium
        cation C01330, removed 2026-10-26T04:21Z by the TCDB substrate filter)."""
        rows = api.list_metabolites(
            metabolite_ids=["kegg.compound:C00031", "kegg.compound:C06570"],
            limit=10, conn=conn,
        )["results"]
        by_id = {r["metabolite_id"]: r for r in rows}
        glucose = by_id["kegg.compound:C00031"]
        assert glucose["transporter_gene_count"] == kg_count(
            "MATCH (m:Metabolite {id: 'kegg.compound:C00031'}) RETURN m.transporter_gene_count")
        tet = by_id["kegg.compound:C06570"]
        assert tet["catalyst_gene_count"] == 0
        assert tet["transporter_gene_count"] == kg_count(
            "MATCH (m:Metabolite {id: 'kegg.compound:C06570'}) RETURN m.transporter_gene_count")
        assert tet["transporter_gene_count"] > 0
        assert tet["evidence_sources"] == ["transport"]

    def test_list_organisms_med4_transported_metabolite_count(self, conn):
        """list_organisms: MED4 transported_metabolite_count > 0 on the row
        and on its top_metabolic_capability entry (ranking unchanged)."""
        res = api.list_organisms(organism_names=[self._MED4], conn=conn)
        row = res["results"][0]
        assert row["transported_metabolite_count"] > 0
        cap = next(c for c in res["top_metabolic_capability"]
                   if c["organism_name"] == self._MED4)
        assert cap["transported_metabolite_count"] == row["transported_metabolite_count"]
        assert cap["catalyzed_metabolite_count"] == row["catalyzed_metabolite_count"]


# ===========================================================================
# Phase 2 — KG-integration round-trip cases (frozen spec
# 2026-05-05-phase2-cross-cutting-renames.md). Stage 1 RED — failing tests.
# ===========================================================================


@pytest.mark.kg
class TestListMetabolitesPhase2:
    """Phase 2 Item 3 — exclude_metabolite_ids on list_metabolites."""

    # Currency cofactors per spec §6.3 worked example (kegg.compound IDs).
    _COFACTORS = [
        "kegg.compound:C00002",  # ATP
        "kegg.compound:C00008",  # ADP
        "kegg.compound:C00004",  # NADH
        "kegg.compound:C00005",  # NADPH
        "kegg.compound:C00001",  # H2O
    ]

    def test_exclude_cofactors_drops_rows(self, conn):
        """Pass exclude list of 5 currency cofactors; assert their IDs do
        not appear in any returned row, and total_matching decreases by
        exactly the count of cofactors known to the KG."""
        # Baseline (no exclusion) — get total_matching for the unfiltered set.
        baseline = api.list_metabolites(conn=conn)
        # With exclusion
        filtered = api.list_metabolites(
            exclude_metabolite_ids=self._COFACTORS, conn=conn,
        )
        assert filtered["total_matching"] <= baseline["total_matching"]
        # Reduction is at most len(cofactors) — possibly less if some
        # cofactor IDs aren't in the KG.
        reduction = (
            baseline["total_matching"] - filtered["total_matching"]
        )
        assert 0 <= reduction <= len(self._COFACTORS)
        # Spot-check: no excluded metabolite_id appears in the returned
        # rows. (Pull a generous sample to make this assertion robust.)
        rows = api.list_metabolites(
            exclude_metabolite_ids=self._COFACTORS, limit=200, conn=conn,
        )["results"]
        seen_ids = {r["metabolite_id"] for r in rows}
        for cofactor in self._COFACTORS:
            assert cofactor not in seen_ids


@pytest.mark.kg
class TestGenesByMetabolitePhase2:
    """Phase 2 Item 3 — exclude_metabolite_ids on genes_by_metabolite."""

    def test_exclude_metabolite_ids_drops_target(self, conn):
        """Excluding the only requested metabolite drops the result set
        to zero rows (set-difference semantics confirmed end-to-end)."""
        # Baseline: urea × MED4 — a known non-empty result.
        base = api.genes_by_metabolite(
            metabolite_ids=["kegg.compound:C00086"],
            organism="Prochlorococcus MED4",
            conn=conn,
        )
        assert base["total_matching"] > 0
        # Now exclude the SAME urea ID — set-difference reduces to zero
        # since the include set is fully removed.
        excluded = api.genes_by_metabolite(
            metabolite_ids=["kegg.compound:C00086"],
            exclude_metabolite_ids=["kegg.compound:C00086"],
            organism="Prochlorococcus MED4",
            conn=conn,
        )
        assert excluded["total_matching"] == 0


@pytest.mark.kg
class TestMetabolitesByGenePhase2:
    """Phase 2 Items 2 + 3 on metabolites_by_gene."""

    # Cofactor list per spec §6.3.
    _COFACTORS = [
        "kegg.compound:C00002",  # ATP
        "kegg.compound:C00008",  # ADP
        "kegg.compound:C00004",  # NADH
        "kegg.compound:C00005",  # NADPH
        "kegg.compound:C00001",  # H2O
    ]

    def test_exclude_metabolite_ids_drops_cofactor_rows(self, conn):
        """Cofactor exclusion drops rows whose metabolite_id matches."""
        result = api.metabolites_by_gene(
            ["PMM0963", "PMM0964", "PMM0965"],
            "Prochlorococcus MED4",
            exclude_metabolite_ids=self._COFACTORS,
            limit=200,
            conn=conn,
        )
        seen_ids = {r["metabolite_id"] for r in result["results"]}
        for cofactor in self._COFACTORS:
            assert cofactor not in seen_ids

    def test_top_metabolite_pathways_envelope_round_trip(self, conn):
        """Phase 2 Item 2: envelope key `top_metabolite_pathways` round-trips
        through Cypher → API → Pydantic envelope."""
        from multiomics_explorer.mcp_server.tools import (
            MetabolitesByGeneResponse,
        )
        result = api.metabolites_by_gene(
            ["PMM0963", "PMM0964", "PMM0965"],
            "Prochlorococcus MED4",
            summary=True, conn=conn,
        )
        # Envelope key present at the dict level
        assert "top_metabolite_pathways" in result
        # Pydantic round-trip succeeds (validates field rename end-to-end)
        model = MetabolitesByGeneResponse(**result)
        assert hasattr(model, "top_metabolite_pathways")


@pytest.mark.kg
class TestListMetabolitesPhase2Item2:
    """Phase 2 Item 2 — top_metabolite_pathways round-trip on list_metabolites."""

    def test_top_metabolite_pathways_envelope_round_trip(self, conn):
        from multiomics_explorer.mcp_server.tools import (
            ListMetabolitesResponse,
        )
        result = api.list_metabolites(summary=True, conn=conn)
        assert "top_metabolite_pathways" in result
        # Pydantic round-trip succeeds (validates field rename end-to-end)
        model = ListMetabolitesResponse(**result)
        assert hasattr(model, "top_metabolite_pathways")


@pytest.mark.kg
class TestDifferentialExpressionByGenePhase2:
    """Phase 2 Item 4 — direction='both' functional equivalence on DE."""

    def test_direction_both_equals_significant_only_none(self, conn):
        """Spec §6.4 verification: `direction='both'` is functionally
        equivalent to `direction=None, significant_only=True` on the
        current 3-status universe (verified live KG 2026-05-05).

        Both forms must return the same `total_matching` on a controlled
        organism + treatment slice.
        """
        kwargs = dict(
            organism="MED4", summary=True, conn=conn,
        )
        both = api.differential_expression_by_gene(
            **kwargs, direction="both",
        )
        none_significant = api.differential_expression_by_gene(
            **kwargs, direction=None, significant_only=True,
        )
        assert both["total_matching"] == none_significant["total_matching"]
        # Both should be > 0 on the live MED4 dataset.
        assert both["total_matching"] > 0

    def test_direction_both_returns_only_significant_rows(self, conn):
        """direction='both' rows are all in {significant_up, significant_down}."""
        result = api.differential_expression_by_gene(
            organism="MED4", direction="both", limit=20, conn=conn,
        )
        for row in result["results"]:
            assert row["expression_status"] in (
                "significant_up", "significant_down"
            )


@pytest.mark.kg
class TestDifferentialExpressionByGeneMcpWrapper:
    """Wrapper-level integration tests for differential_expression_by_gene."""

    @pytest.mark.asyncio
    async def test_de_by_gene_all_genes_no_de_no_crash(self, tool_fns, conn):
        # PMM1720: valid MED4 gene with zero Changes_expression_of edges.
        # Previously crashed: synthetic null-category row violated the
        # non-nullable ExpressionTopCategory.category model.
        ctx = _ctx_with_conn(conn)
        resp = await tool_fns["differential_expression_by_gene"](
            ctx, locus_tags=["PMM1720"], organism="Prochlorococcus MED4")
        assert resp.total_matching == 0
        assert all(c.category is not None for c in resp.top_categories)


# ---------------------------------------------------------------------------
# list_metabolite_assays — Phase 5 live-KG integration tests
# Baselines pinned to KG state 2026-05-06 (parent §3 + §12.1 fixtures).
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestListMetaboliteAssays:
    """Live-KG integration tests. Baselines from spec §3 + §12.1 fixtures (2026-05-06)."""

    def test_no_filters_returns_all_10_assays(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(conn=conn)
        assert result["total_entries"] == 14
        assert result["total_matching"] == 14
        assert result["metabolite_count_total"] == 1050  # cumulative-across-assays (1044 → 1050: 2026-10-15 GSH/GSSG split + repoints)
        assert len(result["results"]) == 14

    def test_value_kind_numeric(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(value_kind="numeric", conn=conn)
        assert result["total_matching"] == 12
        for r in result["results"]:
            assert r["value_kind"] == "numeric"
            assert r["rankable"] is True  # all numeric assays are rankable

    def test_value_kind_boolean(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(value_kind="boolean", conn=conn)
        assert result["total_matching"] == 2
        for r in result["results"]:
            assert r["value_kind"] == "boolean"
            assert r["rankable"] is False
            assert r["detection_status_counts"] == []

    def test_compartment_extracellular(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(compartment="extracellular", conn=conn)
        assert result["total_matching"] == 3
        for r in result["results"]:
            assert r["compartment"] == "extracellular"

    def test_organism_contains_match(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(organism="MIT9301", conn=conn)
        assert result["total_matching"] == 4
        for r in result["results"]:
            assert "MIT9301" in r["organism_name"]

    def test_metabolite_ids_filter_pep(self, conn):
        """Phosphoenolpyruvate (C00074) is measured in all 10 assays."""
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(
            metabolite_ids=["kegg.compound:C00074"], conn=conn)
        assert result["total_matching"] == 10

    def test_search_text_chitosan(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(search_text="chitosan", conn=conn)
        # Capovilla 2023 chitosan paper has 2 numeric assays
        assert result["total_matching"] >= 2
        assert result["score_max"] is not None
        for r in result["results"]:
            assert r["score"] is not None

    def test_rankable_true_returns_8_numeric(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(rankable=True, conn=conn)
        assert result["total_matching"] == 12

    def test_rankable_false_returns_2_boolean(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(rankable=False, conn=conn)
        assert result["total_matching"] == 2

    def test_summary_returns_envelope_only(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(summary=True, conn=conn)
        assert result["results"] == []
        assert result["truncated"] is True
        # Envelope rollups populated regardless of summary flag
        assert len(result["by_organism"]) > 0
        assert len(result["by_value_kind"]) == 2  # numeric, boolean
        # by_detection_status: tested-absent dominates (75%+)
        det_counts = {b["detection_status"]: b["count"] for b in result["by_detection_status"]}
        assert det_counts.get("not_detected", 0) >= 800

    def test_verbose_adds_text_columns(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(verbose=True, limit=1, conn=conn)
        r = result["results"][0]
        assert "treatment" in r
        assert "light_condition" in r
        assert "experimental_context" in r

    def test_assay_ids_not_found(self, conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(
            assay_ids=["nonexistent_assay_id"], conn=conn)
        assert result["total_matching"] == 0
        assert "nonexistent_assay_id" in result["not_found"]["assay_ids"]

    def test_capovilla_assay_has_2_timepoints(self, conn):
        """MIT9313 chitosan assay: timepoints sentinel-stripped to ['4 days', '6 days']."""
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(
            assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"],
            conn=conn)
        assert result["total_matching"] == 1
        r = result["results"][0]
        assert sorted(r["timepoints"]) == ["4 days", "6 days"]
        # detection_status_counts has 3 statuses on this assay (27 detected, 30 sporadic, 7 not_detected)
        statuses = {d["detection_status"]: d["count"] for d in r["detection_status_counts"]}
        assert statuses.get("detected", 0) == 27
        assert statuses.get("sporadic", 0) == 30
        assert statuses.get("not_detected", 0) == 7

    def test_kujawinski_assay_no_timepoints(self, conn):
        """Kujawinski non-temporal experiment: timepoints == []."""
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(
            assay_ids=["metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration"],
            conn=conn)
        assert result["total_matching"] == 1
        assert result["results"][0]["timepoints"] == []  # sentinel-stripped

    def test_growth_phases_empty_kg_met_017(self, conn):
        """KG-MET-017: growth_phases empty on every assay today."""
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(conn=conn)
        for r in result["results"]:
            assert r["growth_phases"] == []
        assert result["by_growth_phase"] == []


# ---------------------------------------------------------------------------
# Phase 5 metabolites-by-assay slice — 3 drill-down / reverse-lookup tools.
# Baselines pinned per slice spec §7 (verified live 2026-05-06).
#   - docs/tool-specs/metabolites_by_assay.md §7
#   - docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md §10 §3.5
# ---------------------------------------------------------------------------
_MIT9313_CHITOSAN_ASSAY = (
    "metabolite_assay:pnas.2213271120:"
    "metabolites_intracellular_mit9313:cellular_concentration"
)
_MSYSTEMS_PRESENCE_FLAGS_ASSAY = (
    "metabolite_assay:msystems.01261-22:"
    "presence_flags_table_s2:presence_flag_intracellular"
)
_PEP_ID = "kegg.compound:C00074"


@pytest.mark.kg
class TestMetabolitesByQuantifiesAssayKG:
    """Live-KG integration tests for `metabolites_by_quantifies_assay`.
    Baselines from slice spec §7 (MIT9313 cellular_concentration assay)."""

    def test_mit9313_chitosan_summary(self, conn):
        """§7 fixture: total_matching=64, by_detection_status=
        {detected:27, sporadic:30, not_detected:7}, by_metric_bucket=
        {mid:32, low:16, top_quartile:9, top_decile:7}."""
        from multiomics_explorer.api import metabolites_by_quantifies_assay
        result = metabolites_by_quantifies_assay(
            assay_ids=[_MIT9313_CHITOSAN_ASSAY], summary=True, conn=conn)
        assert result["total_matching"] == 64
        det = {b["detection_status"]: b["count"]
               for b in result["by_detection_status"]}
        assert det == {"detected": 27, "sporadic": 30, "not_detected": 7}
        buck = {b["bucket"]: b["count"] for b in result["by_metric_bucket"]}
        assert buck == {"mid": 32, "low": 16,
                        "top_quartile": 9, "top_decile": 7}
        # summary mode: results=[]
        assert result["results"] == []
        # No rankable-gating exclusion (assay is rankable)
        assert result["excluded_assays"] == []
        # Only the dominant-form stereo warning (metabolite-identity-surface spec D).
        assert len(result["warnings"]) == 1
        assert result["warnings"][0].startswith("4 of 64 rows assume the dominant stereo form")

    def test_mit9313_top5_rows(self, conn):
        """§7: top-5 ranks 1-5; F6P top_decile rank 1-3, Citrate rank 4-5."""
        from multiomics_explorer.api import metabolites_by_quantifies_assay
        result = metabolites_by_quantifies_assay(
            assay_ids=[_MIT9313_CHITOSAN_ASSAY], limit=5, conn=conn)
        assert result["returned"] == 5
        ranks = [r["rank_by_metric"] for r in result["results"]]
        assert ranks == [1, 2, 3, 4, 5]
        names = [r["name"] for r in result["results"]]
        # Ranks 1-3 are F6P (D-Fructose 6-phosphate)
        assert all("Fructose 6-phosphate" in n for n in names[:3])
        # Ranks 4-5 are Citrate
        assert all("Citrate" in n for n in names[3:5])
        # All top-5 are top_decile bucket
        assert all(r["metric_bucket"] == "top_decile"
                   for r in result["results"])

    def test_growth_phase_null_today(self, conn):
        """KG-MET-017 (parent §3.5): every numeric row has growth_phase=None
        until KG-side backfill lands."""
        from multiomics_explorer.api import metabolites_by_quantifies_assay
        result = metabolites_by_quantifies_assay(
            assay_ids=[_MIT9313_CHITOSAN_ASSAY], limit=10, conn=conn)
        for r in result["results"]:
            assert r["growth_phase"] is None, (
                f"Expected null growth_phase per KG-MET-017; "
                f"got {r['growth_phase']!r}")

    def test_invalid_metric_bucket_raises(self, conn):
        """API-layer validation: unknown bucket label raises ValueError."""
        from multiomics_explorer.api import metabolites_by_quantifies_assay
        with pytest.raises(ValueError) as exc:
            metabolites_by_quantifies_assay(
                assay_ids=[_MIT9313_CHITOSAN_ASSAY],
                metric_bucket=["nonexistent_bucket"], conn=conn)
        msg = str(exc.value)
        assert "metric_bucket" in msg
        assert "nonexistent_bucket" in msg

    def test_all_non_rankable_raises(self, conn):
        """All-non-rankable selected-assay set + rankable-gated filter
        → ValueError (rankable-gating contract). Today the live KG has
        no non-rankable numeric assays — boolean assays never reach the
        numeric-kind partition at all. We simulate the failure mode by
        passing a boolean assay (non-rankable) — this path returns an
        empty envelope without raising (api guard requires diag_rows to
        be non-empty before the rankable check fires).

        llm-review 2b.3 Task 5: the boolean assay_id is genuinely found
        (diagnostics is now kind-agnostic) — it's excluded from
        `not_found.assay_ids` and reported via a sibling-tool warning
        instead, rather than silently landing in not_found.

        Documented as a KG-state limitation: the rankable-gate raise is
        unreachable from the live KG today. The test still pins the
        not-yet-failing surface so when a non-rankable numeric assay
        lands in the KG, this stops being a no-op."""
        from multiomics_explorer.api import metabolites_by_quantifies_assay
        result = metabolites_by_quantifies_assay(
            assay_ids=[_MSYSTEMS_PRESENCE_FLAGS_ASSAY],
            metric_bucket=["top_decile"], conn=conn)
        assert result["total_matching"] == 0
        assert result["results"] == []
        # Boolean assay is genuinely found -> NOT in not_found.assay_ids.
        assert _MSYSTEMS_PRESENCE_FLAGS_ASSAY not in result["not_found"]["assay_ids"]
        assert any(
            _MSYSTEMS_PRESENCE_FLAGS_ASSAY in w
            and "value_kind=boolean" in w
            and "metabolites_by_flags_assay" in w
            for w in result["warnings"]
        ), result["warnings"]

    def test_min_value_strips_tested_absent(self, conn):
        """Parent §10 anti-pattern: `min_value=0.001` slashes the
        not_detected bucket — tested-absent rows have value=0. Confirms
        the silent-drop hazard and surfaces the caller-controlled choice."""
        from multiomics_explorer.api import metabolites_by_quantifies_assay
        # Baseline: 7 not_detected in the unfiltered slice.
        baseline = metabolites_by_quantifies_assay(
            assay_ids=[_MIT9313_CHITOSAN_ASSAY], summary=True, conn=conn)
        baseline_det = {b["detection_status"]: b["count"]
                        for b in baseline["by_detection_status"]}
        assert baseline_det["not_detected"] == 7
        # With min_value=0.001 the not_detected bucket evaporates.
        filtered = metabolites_by_quantifies_assay(
            assay_ids=[_MIT9313_CHITOSAN_ASSAY],
            min_value=0.001, summary=True, conn=conn)
        filt_det = {b["detection_status"]: b["count"]
                    for b in filtered["by_detection_status"]}
        assert filt_det.get("not_detected", 0) == 0
        # Total drops from 64 → fewer rows (tested-absent gone, sporadic thinned).
        assert filtered["total_matching"] < baseline["total_matching"]
        assert filtered["total_matching"] == 49


@pytest.mark.kg
class TestMetabolitesByFlagsAssayKG:
    """Live-KG integration tests for `metabolites_by_flags_assay`.
    Baselines from slice spec §7 (msystems presence_flags_intracellular)."""

    def test_msystems_summary(self, conn):
        """§7 fixture: total_matching=93, by_value={false:58, true:35}."""
        from multiomics_explorer.api import metabolites_by_flags_assay
        result = metabolites_by_flags_assay(
            assay_ids=[_MSYSTEMS_PRESENCE_FLAGS_ASSAY],
            summary=True, conn=conn)
        assert result["total_matching"] == 93
        # API surfaces flag_value as bool (coerced from KG 'detected'/'not_detected').
        # Pydantic coerces to bool downstream (verified in contract test).
        by_val = {b["flag_value"]: b["count"] for b in result["by_value"]}
        # Accept either string or bool key per Pydantic-coercion-tolerance.
        false_count = by_val.get("false", by_val.get(False, 0))
        true_count = by_val.get("true", by_val.get(True, 0))
        assert false_count == 58
        assert true_count == 35
        assert result["results"] == []
        # Always-empty envelope-shape (no rankable gates on boolean arm).
        assert result["excluded_assays"] == []
        # Only the dominant-form stereo warning (metabolite-identity-surface spec D).
        assert len(result["warnings"]) == 1
        # 21 → 23 2026-10-24T17:33Z: stereo_assignment now judged from the node's own ChEBI enantiomer links
        # 23 → 29 2026-10-31T12:27Z: KEGG-filed stereo rule + 6 msystems names
        assert result["warnings"][0].startswith("29 of 93 rows assume the dominant stereo form")

    def test_msystems_top5_alphabetical_true(self, conn):
        """§7: top-5 detail rows are flag_value=true; expected names
        NAD+, S-Adenosyl-L-methionine, AMP, S-Adenosyl-L-homocysteine,
        L-Glutamate (sort key: flag_value DESC, m.id ASC). At least 4 of these
        surface in the top-5. Re-pinned at the 2026-10-15 identity rebuild:
        tyrosine / SAM moved off measurement-only chebi: nodes onto C00082 /
        C00019, and names are now KEGG names."""
        from multiomics_explorer.api import metabolites_by_flags_assay
        result = metabolites_by_flags_assay(
            assay_ids=[_MSYSTEMS_PRESENCE_FLAGS_ASSAY], limit=5, conn=conn)
        assert result["returned"] == 5
        # All top-5 are flag_value=True (DESC sort: true > false).
        assert all(r["flag_value"] is True for r in result["results"])
        names = [r["name"] for r in result["results"]]
        expected = {
            "NAD+", "S-Adenosyl-L-methionine", "AMP",
            "S-Adenosyl-L-homocysteine", "L-Glutamate",
        }
        match_count = sum(1 for n in names if n in expected)
        assert match_count >= 4, (
            f"Expected >=4 of {expected} in top-5; got names={names}, "
            f"match_count={match_count}")

    def test_flag_value_false_returns_rows(self, conn):
        """Distinct from DM `genes_by_boolean_metric` (positive-only KG
        storage): `Assay_flags_metabolite` stores both true and false,
        so `flag_value=False` returns 58 rows on the msystems assay."""
        from multiomics_explorer.api import metabolites_by_flags_assay
        result = metabolites_by_flags_assay(
            assay_ids=[_MSYSTEMS_PRESENCE_FLAGS_ASSAY],
            flag_value=False, summary=True, conn=conn)
        assert result["total_matching"] == 58

    def test_no_by_detection_status_envelope(self, conn):
        """Boolean arm has no `detection_status` field — envelope MUST NOT
        carry `by_detection_status` (slice spec §5.3)."""
        from multiomics_explorer.api import metabolites_by_flags_assay
        result = metabolites_by_flags_assay(
            assay_ids=[_MSYSTEMS_PRESENCE_FLAGS_ASSAY],
            summary=True, conn=conn)
        assert "by_detection_status" not in result, (
            f"Boolean arm must not carry by_detection_status; "
            f"got envelope keys={sorted(result.keys())}")
        # Positive assertion: the qualitative-detection signal is by_value.
        assert "by_value" in result

    def test_assay_ids_not_found(self, conn):
        """llm-review 2b.3 Task 5: `metabolites_by_flags_assay` now probes
        assay_ids via a kind-agnostic existence + value_kind lookup — a
        non-existent assay_id genuinely surfaces in not_found.assay_ids
        (superseding the old Task 3 deviation, which left this bucket
        always empty)."""
        from multiomics_explorer.api import metabolites_by_flags_assay
        result = metabolites_by_flags_assay(
            assay_ids=["nonexistent_assay"], summary=True, conn=conn)
        assert result["total_matching"] == 0
        assert result["not_found"]["assay_ids"] == ["nonexistent_assay"]

    def test_numeric_assay_id_reported_as_wrong_kind(self, conn):
        """A numeric assay_id passed to this boolean-only tool is
        genuinely found (excluded from not_found.assay_ids) but reported
        via a sibling-tool warning naming metabolites_by_quantifies_assay."""
        from multiomics_explorer.api import metabolites_by_flags_assay
        result = metabolites_by_flags_assay(
            assay_ids=[_MIT9313_CHITOSAN_ASSAY], summary=True, conn=conn)
        assert _MIT9313_CHITOSAN_ASSAY not in result["not_found"]["assay_ids"]
        assert any(
            _MIT9313_CHITOSAN_ASSAY in w
            and "value_kind=numeric" in w
            and "metabolites_by_quantifies_assay" in w
            for w in result["warnings"]
        ), result["warnings"]


@pytest.mark.kg
class TestAssaysByMetaboliteKG:
    """Live-KG integration tests for `assays_by_metabolite` (polymorphic
    reverse-lookup). Baselines from slice spec §7 (PEP / kegg.compound:C00074)."""

    def test_pep_polymorphic_summary(self, conn):
        """§7 fixture: total_matching=20 (18 quantifies + 2 flags),
        metabolites_matched=1, by_evidence_kind={quantifies:18, flags:2},
        by_detection_status={not_detected:12, detected:3, sporadic:3},
        by_flag_value={false:2}."""
        from multiomics_explorer.api import assays_by_metabolite
        result = assays_by_metabolite(
            metabolite_ids=[_PEP_ID], summary=True, conn=conn)
        assert result["total_matching"] == 20
        assert result["metabolites_matched"] == 1
        ek = {b["evidence_kind"]: b["count"]
              for b in result["by_evidence_kind"]}
        assert ek == {"quantifies": 18, "flags": 2}
        det = {b["detection_status"]: b["count"]
               for b in result["by_detection_status"]}
        assert det == {"not_detected": 12, "detected": 3, "sporadic": 3}
        # by_flag_value stores api-layer string flag values (apoc passthrough).
        fv = {b["flag_value"]: b["count"] for b in result["by_flag_value"]}
        false_count = fv.get("false", fv.get(False, 0))
        assert false_count == 2

    def test_pep_top5_evidence_kind_desc(self, conn):
        """§6.4 sort: m.id ASC, evidence_kind DESC, a.id ASC.
        'quantifies' > 'flags' alphabetically; 18 numeric rows surface
        first before any boolean — top-5 are all quantifies."""
        from multiomics_explorer.api import assays_by_metabolite
        result = assays_by_metabolite(
            metabolite_ids=[_PEP_ID], limit=5, conn=conn)
        assert result["returned"] == 5
        kinds = [r["evidence_kind"] for r in result["results"]]
        assert kinds == ["quantifies"] * 5
        # All rows are PEP (single-metabolite query).
        assert all(r["metabolite_id"] == _PEP_ID for r in result["results"])

    def test_evidence_kind_filter_quantifies_only(self, conn):
        """`evidence_kind="quantifies"` summary returns 18 (numeric arm only)."""
        from multiomics_explorer.api import assays_by_metabolite
        result = assays_by_metabolite(
            metabolite_ids=[_PEP_ID], evidence_kind="quantifies",
            summary=True, conn=conn)
        assert result["total_matching"] == 18
        # by_flag_value rollup is empty when evidence_kind='quantifies'
        assert result["by_flag_value"] == []

    def test_not_found_flat_list(self, conn):
        """§6.3 / parent §13.6: not_found is flat list[str] (single-batch
        reverse-lookup)."""
        from multiomics_explorer.api import assays_by_metabolite
        result = assays_by_metabolite(
            metabolite_ids=[_PEP_ID, "fake.id:DOESNOTEXIST"],
            summary=True, conn=conn)
        # Flat list[str] shape — NOT a dict with sub-buckets.
        assert isinstance(result["not_found"], list)
        assert result["not_found"] == ["fake.id:DOESNOTEXIST"]
        # PEP is present in KG with edges; not flagged not_found.
        assert _PEP_ID not in result["not_found"]

    def test_metabolites_with_evidence_partition_detail_mode(self, conn):
        """Per Task 3 deviation note: `metabolites_with_evidence` partition
        is only computable from detail rows. Test in NON-summary mode.

        With `metabolite_ids=[PEP]` and detail rows returned: PEP has
        18+2=20 edges → metabolites_with_evidence=[PEP], not_matched=[]."""
        from multiomics_explorer.api import assays_by_metabolite
        result = assays_by_metabolite(
            metabolite_ids=[_PEP_ID], limit=20, conn=conn)
        # Detail mode partitions correctly.
        assert result["metabolites_with_evidence"] == [_PEP_ID]
        assert result["metabolites_without_evidence"] == []
        # not_matched: KG-present but no edges-after-filter (empty here).
        assert result["not_matched"] == []


# ---------------------------------------------------------------------------
# PSORTb / SignalP ontology smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestOntologyToolsPsortbSignalpLive:
    """Smoke tests for psortb/signalp surfacing against live KG.
    Asserts only:
      - non-empty results where applicable
      - edge-prop columns populated on owner ontology
      - edge-prop columns absent on non-owner ontology
    NOT biological correctness (the KG-side is the source of truth for that)."""

    ORGANISM = "MED4"

    def test_search_ontology_psortb(self, conn):
        result = api.search_ontology(
            "outer", "subcellular_localization", conn=conn,
        )
        assert result["total_matching"] >= 1
        assert any(r["id"] == "psortb_OuterMembrane" for r in result["results"])

    def test_search_ontology_signalp(self, conn):
        result = api.search_ontology(
            "lipo", "signal_peptide_type", conn=conn,
        )
        assert result["total_matching"] >= 1
        result_ids = {r["id"] for r in result["results"]}
        assert "signalp_LIPO" in result_ids or "signalp_TATLIPO" in result_ids

    def test_genes_by_ontology_psortb_surfaces_score(self, conn):
        # Annotation-trust surface (design section 1): PSORTb / SignalP native
        # scalars are verbose-only now — compact = comparable, verbose = native.
        result = api.genes_by_ontology(
            ontology="subcellular_localization",
            term_ids=["psortb_OuterMembrane"],
            organism=self.ORGANISM,
            verbose=True,
            conn=conn,
        )
        assert result["total_matching"] > 0
        rows = result["results"]
        assert rows, "Expected at least one PMM* gene with OuterMembrane call"
        for row in rows:
            # Owner column populated, range [7.5, 10.0]
            assert "localization_score" in row, row
            assert 7.5 <= row["localization_score"] <= 10.0
            # Non-owner columns absent (strip-non-applicable)
            assert "signal_peptide_probability" not in row
            assert "signal_peptide_cleavage_site" not in row
            assert "signal_peptide_cleavage_probability" not in row

    def test_genes_by_ontology_psortb_compact_omits_score(self, conn):
        """localization_score moved compact -> verbose."""
        result = api.genes_by_ontology(
            ontology="subcellular_localization",
            term_ids=["psortb_OuterMembrane"],
            organism=self.ORGANISM,
            conn=conn,
        )
        rows = result["results"]
        assert rows, "Expected at least one PMM* gene with OuterMembrane call"
        for row in rows:
            assert "localization_score" not in row, row

    def test_genes_by_ontology_signalp_surfaces_probability(self, conn):
        result = api.genes_by_ontology(
            ontology="signal_peptide_type",
            term_ids=["signalp_LIPO"],
            organism=self.ORGANISM,
            verbose=True,
            conn=conn,
        )
        rows = result["results"]
        if rows:
            for row in rows:
                assert "signal_peptide_probability" in row
                assert 0.0 <= row["signal_peptide_probability"] <= 1.0
                # cleavage_site may or may not be present (depends on the gene);
                # both states must not crash
                assert "localization_score" not in row

    def test_genes_by_ontology_signalp_compact_omits_probability(self, conn):
        """signal_peptide_* moved compact -> verbose."""
        result = api.genes_by_ontology(
            ontology="signal_peptide_type",
            term_ids=["signalp_LIPO"],
            organism=self.ORGANISM,
            conn=conn,
        )
        for row in result["results"]:
            assert "signal_peptide_probability" not in row, row
            assert "signal_peptide_cleavage_site" not in row
            assert "signal_peptide_cleavage_probability" not in row


    def test_genes_by_ontology_pfam_strips_edge_prop_columns(self, conn):
        """Pre-existing ontology should NOT have the 4 edge-prop columns
        in its rows."""
        result = api.genes_by_ontology(
            ontology="pfam",
            level=1,
            organism=self.ORGANISM,
            min_gene_set_size=5,
            limit=5,
            conn=conn,
        )
        for row in result["results"]:
            assert "localization_score" not in row
            assert "signal_peptide_probability" not in row
            assert "signal_peptide_cleavage_site" not in row
            assert "signal_peptide_cleavage_probability" not in row

    def test_ontology_landscape_includes_new_ontologies(self, conn):
        """All-ontologies fan-out includes the two new flat ontologies."""
        from multiomics_explorer.api.functions import ontology_landscape
        result = ontology_landscape(organism=self.ORGANISM, conn=conn)
        # by_ontology is a dict keyed by ontology type; results rows carry ontology_type
        ontologies_seen = set(result["by_ontology"].keys())
        assert "subcellular_localization" in ontologies_seen
        assert "signal_peptide_type" in ontologies_seen
        # Both new ontologies are flat (level=0 only) — verify in results rows
        for row in result["results"]:
            if row["ontology_type"] in ("subcellular_localization", "signal_peptide_type"):
                assert row["level"] == 0

    def test_gene_ontology_terms_signalp_handles_cleavage_absence(self, conn):
        """For a SignalP-PILIN gene (typically no cleavage site), the row
        emits null cleavage fields cleanly — both states must not crash."""
        # Find a PILIN gene first via genes_by_ontology
        sp_search = api.genes_by_ontology(
            ontology="signal_peptide_type",
            term_ids=["signalp_PILIN"],
            organism=self.ORGANISM,
            limit=3,
            conn=conn,
        )
        if not sp_search["results"]:
            pytest.skip("No PILIN genes in MED4 — skip cleavage-absence test")
        pilin_lts = [r["locus_tag"] for r in sp_search["results"]][:2]
        result = api.gene_ontology_terms(
            locus_tags=pilin_lts,
            ontology="signal_peptide_type",
            organism=self.ORGANISM,
            mode="leaf",
            conn=conn,
        )
        for row in result["results"]:
            assert row["term_id"] == "signalp_PILIN"
            assert "signal_peptide_probability" in row
            # cleavage_site / cleavage_probability may be absent (stripped null)
            # or present (rare); both fine


@pytest.mark.kg
class TestOrganismResolverGenomeOnlyLive:
    """Resolving an organism is a genomic-identity question — it gates on the
    presence of genes (gene_count > 0), never on expression experiments.
    Regression for the friction-log bug where genome-only strains
    (experiment_count=0) raised 'no organism matching ... found' from the
    shared _validate_organism_inputs resolver, blocking every single-organism
    genomic tool. Gene-less higher-rank taxonomy nodes still (correctly) do
    not resolve."""

    # Prochlorococcus MIT9515: 1949 genes, 0 expression experiments.
    GENOME_ONLY_ORGANISM = "MIT9515"

    def test_genes_by_ontology_resolves_genome_only_strain(self, conn):
        # Previously raised ValueError("no organism matching 'MIT9515' found").
        result = api.genes_by_ontology(
            ontology="cyanorak_role",
            term_ids=["cyanorak.role:D.1.5"],
            organism=self.GENOME_ONLY_ORGANISM,
            conn=conn,
        )
        # 29 D.1.5 genes confirmed via run_cypher for this strain.
        gene_ids = {r["locus_tag"] for r in result["results"]}
        assert len(gene_ids) == 29

    def test_resolver_returns_genome_only_organism_name(self, conn):
        from multiomics_explorer.api.functions import _validate_organism_inputs

        resolved = _validate_organism_inputs(
            organism=self.GENOME_ONLY_ORGANISM,
            locus_tags=None,
            experiment_ids=None,
            conn=conn,
        )
        assert resolved == "Prochlorococcus MIT9515"

    def test_gene_less_taxon_does_not_resolve(self, conn):
        # A higher-rank taxonomy node with no genes (genus / phage / non-target
        # species, gene_count=0) must NOT resolve — resolving it would only
        # yield confusing empty downstream results. The resolver gates on
        # genomic presence (gene_count > 0), not on expression experiments.
        from multiomics_explorer.api.functions import _validate_organism_inputs

        rows = conn.execute_query(
            "MATCH (o:OrganismTaxon) WHERE coalesce(o.gene_count, 0) = 0 "
            "RETURN o.preferred_name AS name LIMIT 1"
        )
        if not rows:
            pytest.skip("no gene-less OrganismTaxon in current KG")
        gene_less = rows[0]["name"]
        with pytest.raises(ValueError, match="no organism matching"):
            _validate_organism_inputs(
                organism=gene_less,
                locus_tags=None,
                experiment_ids=None,
                conn=conn,
            )


# ---------------------------------------------------------------------------
# kg_release_info — MCP wrapper smoke (exercises full lifespan path)
# ---------------------------------------------------------------------------


def _ctx_with_kg_report(conn):
    """Build an AsyncMock Context with the real GraphConnection and a live
    kg_compat_report injected — mirrors what lifespan sets on KGContext."""
    report = api.kg_release_info(conn)
    ctx = AsyncMock()
    ctx.request_context.lifespan_context.conn = conn
    ctx.request_context.lifespan_context.kg_compat_report = report
    return ctx


@pytest.mark.kg
class TestKGReleaseInfoMCPSmoke:
    """Live-KG smoke through the MCP tool wrapper layer.

    The tool reads kg_compat_report from KGContext (cached at lifespan startup
    in production). Here we mirror that by calling api.kg_release_info(conn)
    directly and injecting the result — this exercises the Pydantic response
    model and the wrapper's KGReleaseInfoResponse(**report) path end-to-end.
    """

    @pytest.mark.asyncio
    async def test_tool_returns_verdict_and_identity(self, tool_fns, conn):
        """Exercises the wrapper: KGReleaseInfoResponse Pydantic model validates,
        the tool returns a structured response with verdict + kg identity."""
        ctx = _ctx_with_kg_report(conn)
        response = await tool_fns["kg_release_info"](ctx)

        # Pydantic model attribute access — not dict subscript
        assert response.verdict in ("ok", "warn", "unknown"), (
            f"Unexpected verdict={response.verdict!r}"
        )
        assert response.explorer_version  # non-empty string
        assert response.kg.version  # KG declares a version string
        assert response.kg.gene_count is not None and response.kg.gene_count > 0, (
            f"gene_count should be a positive int, got {response.kg.gene_count!r}"
        )
        assert isinstance(response.asserts, list) and len(response.asserts) > 0
        assert response.summary  # non-empty one-liner

    @pytest.mark.asyncio
    async def test_deployment_role_surfaced_from_live_kg(self, tool_fns, conn):
        """The KG self-declares deployment_role; the tool echoes it verbatim
        (KG is source of truth — no host/port inference).

        deployment_role is str|None: None means the KG predates the property
        (unknown). Not pinned to a specific role: dev builds stamp
        'local-dev', the alpha.7 release cut stamps 'staging' — the contract
        is verbatim passthrough of the live Schema_info value.
        """
        ctx = _ctx_with_kg_report(conn)
        response = await tool_fns["kg_release_info"](ctx)

        assert response.kg.deployment_role in (
            "local-dev", "staging", "production", None
        ), f"Unexpected deployment_role={response.kg.deployment_role!r}"
        live = conn.execute_query(
            "MATCH (s:Schema_info) RETURN s.deployment_role AS role"
        )[0]["role"]
        assert response.kg.deployment_role == live, (
            "kg_release_info must echo Schema_info.deployment_role verbatim; "
            f"got {response.kg.deployment_role!r}, live {live!r}"
        )



# ---------------------------------------------------------------------------
# PR 3b — annotation-trust surface, term side: browse / multi-ontology
# search and the `ontology_term_details` batch, live (spec §7.4, §7.5, §10.3,
# §10.4; freeze notes v1.2).
# ---------------------------------------------------------------------------

_BATCH6_LIVE = [
    "tcdb:3.A.1", "merops.family:S14", "interpro:IPR000362",
    "ncbifam:NF000812", "go:0006979", "bogus:xyz",
]


@pytest.mark.kg
class TestSearchOntologyBrowseLive:
    """Spec §10.3: `search_ontology(ontology=['merops'], level=1)` returns
    S33 first, carrying the term's precomputed gene_count."""

    def test_merops_level1_browse(self, conn, kg_count):
        result = api.search_ontology(
            ontology=["merops"], level=1, limit=5, conn=conn)
        assert result["mode"] == "browse"
        first = result["results"][0]
        assert first["id"] == "merops.family:S33"
        assert first["gene_count"] == kg_count(_TERM_PROP, id="merops.family:S33", prop="gene_count")
        assert first["score"] is None
        assert first["ontology_type"] == "merops"
        assert result["score_max"] is None
        assert result["by_level"]

    def test_merops_level1_verified_top5(self, conn):
        result = api.search_ontology(
            ontology="merops", level=1, limit=5, conn=conn)
        ids = [r["id"] for r in result["results"]]
        assert ids == [
            "merops.family:S33", "merops.family:C26", "merops.family:S09",
            "merops.family:C44", "merops.family:M41",
        ]  # 2026-10-31: M41 +1 (83-1) ties S14 at 426; id breaks the tie
        assert [r["gene_count"] for r in result["results"]] == [
            868, 710, 515, 464, 426]

    def test_browse_sorts_gene_count_desc(self, conn):
        result = api.search_ontology(ontology="tcdb", limit=20, conn=conn)
        counts = [r["gene_count"] for r in result["results"]]
        assert counts == sorted(counts, reverse=True)

    def test_browse_verbose_merops_carries_term_verbose(self, conn):
        result = api.search_ontology(
            ontology="merops", level=1, limit=3, verbose=True, conn=conn)
        row = result["results"][0]
        for col in ("description", "level_kind", "family_class",
                    "catalytic_type", "peptidase_gene_count"):
            assert col in row, col

    def test_c26_dead_homolog_family(self, conn):
        """C26 has 704 genes but only 74 peptidase calls (spec §7.4; 272 / 41 before the 2026-10-28 Ford 2021 strains)."""
        result = api.search_ontology(
            ontology="merops", level=1, limit=5, verbose=True, conn=conn)
        c26 = [r for r in result["results"] if r["id"] == "merops.family:C26"][0]
        assert c26["peptidase_gene_count"] == 74

    def test_browse_interpro_med4_scoped(self, conn):
        """Spec §7.4 per-organism scope: MED4 HOMOLOGOUS_SUPERFAMILY >= 5
        genes -> IPR027417 P-loop NTPase first with 119."""
        result = api.search_ontology(
            ontology="interpro", interpro_type="HOMOLOGOUS_SUPERFAMILY",
            organism="Prochlorococcus MED4", min_gene_count=5, limit=5,
            conn=conn)
        first = result["results"][0]
        assert first["id"] == "interpro:IPR027417"
        assert first["organism_gene_count"] == 119
        assert all(r["organism_gene_count"] >= 5 for r in result["results"])

    def test_pfam_browse_reaches_both_labels(self, conn):
        result = api.search_ontology(ontology="pfam", level=0, limit=5, conn=conn)
        assert result["returned"] > 0
        assert all(r["level"] == 0 for r in result["results"])

    def test_browse_truncated_without_narrowing_warns(self, conn):
        result = api.search_ontology(ontology="tcdb", limit=2, conn=conn)
        assert result["truncated"] is True
        assert any("browse" in w.lower() for w in result["warnings"])

    def test_browse_with_level_does_not_warn(self, conn):
        result = api.search_ontology(ontology="tcdb", level=2, limit=2, conn=conn)
        assert not [w for w in result["warnings"] if "browse" in w.lower()]

    def test_min_gene_count_bounds_rows(self, conn):
        result = api.search_ontology(
            ontology="merops", min_gene_count=100, limit=50, conn=conn)
        assert result["returned"] > 0
        assert all(r["gene_count"] >= 100 for r in result["results"])

    @pytest.mark.asyncio
    async def test_wrapper_browse(self, tool_fns, conn, kg_count):
        ctx = _ctx_with_conn(conn)
        result = await tool_fns["search_ontology"](
            ctx, ontology=["merops"], level=1, limit=5)
        assert result.mode == "browse"
        assert result.results[0].id == "merops.family:S33"
        assert result.results[0].gene_count == kg_count(
            _TERM_PROP, id="merops.family:S33", prop="gene_count")


@pytest.mark.kg
class TestSearchOntologyMultiLive:
    """Spec §10.3: `ontology=['go_bp','tcdb'], search_text='transport',
    limit=5` returns <= 10 rows ordered by ontology then score with
    `by_ontology` truncation flags."""

    def test_go_bp_tcdb_transport(self, conn):
        result = api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=5, conn=conn)
        assert result["mode"] == "search"
        assert result["returned"] <= 10
        types = [r["ontology_type"] for r in result["results"]]
        assert types == sorted(types, key=["go_bp", "tcdb"].index)
        by = {e["ontology"]: e for e in result["by_ontology"]}
        assert set(by) == {"go_bp", "tcdb"}
        for entry in by.values():
            assert isinstance(entry["truncated"], bool)
            assert entry["returned"] <= 5
            assert entry["truncated"] == (entry["total_matching"] > 5)
        assert result["total_matching"] == sum(
            e["total_matching"] for e in result["by_ontology"])

    def test_scores_desc_within_each_ontology(self, conn):
        result = api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=5, conn=conn)
        for key in ("go_bp", "tcdb"):
            scores = [r["score"] for r in result["results"]
                      if r["ontology_type"] == key]
            assert scores == sorted(scores, reverse=True)

    def test_lockstep_paging_second_page(self, conn):
        page1 = api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=3, conn=conn)
        page2 = api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=3, offset=3, conn=conn)
        ids1 = {r["id"] for r in page1["results"]}
        ids2 = {r["id"] for r in page2["results"]}
        assert not (ids1 & ids2)
        assert page2["offset"] == 3

    def test_none_fans_out_to_all_17(self, conn):
        result = api.search_ontology("transport", None, limit=1, conn=conn)
        assert len(result["by_ontology"]) == 17
        assert result["returned"] <= 17

    def test_facet_applies_to_owner_only(self, conn):
        result = api.search_ontology(
            "kinase", ["interpro", "kegg"], interpro_type="DOMAIN",
            limit=5, conn=conn)
        for row in result["results"]:
            if row["ontology_type"] == "interpro":
                assert row["interpro_type"] == "DOMAIN"
        assert result["skipped_ontologies"] == []
        assert isinstance(result["by_interpro_type"], list)

    def test_facet_owner_absent_raises(self, conn):
        with pytest.raises(ValueError, match="interpro_type"):
            api.search_ontology(
                "kinase", ["kegg", "tcdb"], interpro_type="DOMAIN", conn=conn)


@pytest.mark.kg
class TestOntologyTermDetailsLive:
    """Spec §7.5 / §10.4 verified batch counts (freeze notes v1.2)."""

    def _rows(self, conn, **kw):
        result = api.ontology_term_details(
            term_ids=list(_BATCH6_LIVE), conn=conn, **kw)
        return result, {r["term_id"]: r for r in result["results"]}

    def test_not_found(self, conn):
        result, _ = self._rows(conn)
        assert result["not_found"] == ["bogus:xyz"]
        assert result["total_matching"] == 5
        assert [r["term_id"] for r in result["results"]] == _BATCH6_LIVE[:5]

    def test_tcdb_3_a_1(self, conn):
        result, rows = self._rows(conn)
        row = rows["tcdb:3.A.1"]
        assert row["ontology"] == "tcdb"
        assert len(row["parents"]) == 1
        assert row["children_total"] == 97  # 55 → 98 2026-10-24T17:33Z: TCDB 3a keeps range-only subfamilies → 97 2026-10-26T04:21Z: 3.A.1.129 re-anchored
        assert len(row["children"]) == 50
        assert row["children_truncated"] is True
        # 129 → 128 2026-10-18: GO update retired go:0005548 (its 3.A.1 bridge went with it).
        assert len(row["links_out"]) == 11  # 128 → 11 2026-10-24T17:33Z: TCDB 3a bridges sit on the nearest kept node
        assert {lk["target_ontology"] for lk in row["links_out"]} >= {"pfam"}
        assert all(lk["link_kind"] == "composition" for lk in row["links_out"])

    def test_merops_s14(self, conn):
        _, rows = self._rows(conn)
        row = rows["merops.family:S14"]
        assert row["ontology"] == "merops"
        assert len(row["parents"]) == 1
        assert row["children_total"] == 0
        assert len(row["links_out"]) == 1
        assert row["links_out"][0]["target_id"] == "pfam:PF00574"
        assert row["links_out"][0]["link_kind"] == "composition"

    def test_interpro_ipr000362(self, conn):
        _, rows = self._rows(conn, verbose=True)
        row = rows["interpro:IPR000362"]
        assert row["ontology"] == "interpro"
        assert row["parents"] == []
        assert row["children_total"] == 4
        assert len(row["links_out"]) == 5
        assert all(lk["link_kind"] == "router" for lk in row["links_out"])
        assert all(lk["target_ontology"] == "ec" for lk in row["links_out"])
        assert all(lk["props"]["router_ambiguous"] is True
                   for lk in row["links_out"])

    def test_ncbifam_nf000812(self, conn):
        _, rows = self._rows(conn)
        row = rows["ncbifam:NF000812"]
        assert row["ontology"] == "ncbifam"
        assert row["parents"] == [] and row["children_total"] == 0
        assert row["links_out"] == []
        assert "direct_gene_count" not in row

    def test_go_0006979(self, conn, kg_count):
        _, rows = self._rows(conn)
        row = rows["go:0006979"]
        assert row["ontology"] == "go_bp"
        assert row["level"] == 3
        for prop in ("gene_count", "organism_count", "direct_gene_count"):
            assert row[prop] == kg_count(_TERM_PROP, id="go:0006979", prop=prop)
        assert row["direct_gene_count"] < row["gene_count"]
        assert len(row["parents"]) == 1
        assert row["children_total"] == 3
        assert row["links_out"] == []
        assert "member_count" not in row
        assert "go_id" not in row

    def test_envelope_rollups(self, conn):
        result, _ = self._rows(conn)
        # 134 → 17 2026-10-24T17:33Z: TCDB 3a emits bridges on the nearest kept node, mostly tc_system children
        assert result["links_out_total"] == 17
        by_kind = {e["link_kind"]: e["count"] for e in result["by_link_kind"]}
        assert by_kind == {"composition": 12, "router": 5}  # 129 → 12 2026-10-24T17:33Z: TCDB 3a
        by_ont = {e["ontology"]: e["count"] for e in result["by_ontology"]}
        assert by_ont == {"tcdb": 1, "merops": 1, "interpro": 1,
                          "ncbifam": 1, "go_bp": 1}

    def test_link_kinds_filter(self, conn):
        result, rows = self._rows(conn, link_kinds=["router"])
        assert rows["tcdb:3.A.1"]["links_out"] == []
        assert len(rows["interpro:IPR000362"]["links_out"]) == 5
        assert result["links_out_total"] == 5

    def test_organism_scope(self, conn):
        _, rows = self._rows(conn, organism="Prochlorococcus MED4", verbose=True)
        row = rows["tcdb:3.A.1"]
        assert row["organism_gene_count"] > 0
        assert row["genes_by_organism"] == [
            {"organism": "Prochlorococcus MED4",
             "gene_count": row["organism_gene_count"]}]

    def test_verbose_genes_by_organism_covers_organism_count(self, conn):
        _, rows = self._rows(conn, verbose=True)
        row = rows["go:0006979"]
        assert len(row["genes_by_organism"]) == row["organism_count"]
        assert row["properties"]["id"] == "go:0006979"

    def test_pagination(self, conn):
        result = api.ontology_term_details(
            term_ids=list(_BATCH6_LIVE), limit=2, offset=1, conn=conn)
        assert [r["term_id"] for r in result["results"]] == [
            "merops.family:S14", "interpro:IPR000362"]
        assert result["truncated"] is True
        assert result["not_found"] == ["bogus:xyz"]

    def test_pfam_clan_is_pfam(self, conn):
        result = api.ontology_term_details(
            term_ids=["pfam:PF00005"], verbose=True, conn=conn)
        row = result["results"][0]
        assert row["ontology"] == "pfam"
        assert "short_name" in row
        parent = row["parents"][0]["id"] if row["parents"] else None
        if parent:
            clan = api.ontology_term_details(term_ids=[parent], conn=conn)
            assert clan["results"][0]["ontology"] == "pfam"
            assert clan["results"][0]["label"] == "PfamClan"

    @pytest.mark.asyncio
    async def test_wrapper_batch(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        result = await tool_fns["ontology_term_details"](
            ctx, term_ids=list(_BATCH6_LIVE))
        assert result.not_found == ["bogus:xyz"]
        assert result.returned == 5
        assert result.results[0].children_truncated is True
        dumped = result.results[4].model_dump()
        assert "tcdb_id" not in dumped

    @pytest.mark.asyncio
    async def test_wrapper_empty_term_ids_is_a_toolerror(self, tool_fns, conn):
        from fastmcp.exceptions import ToolError
        ctx = _ctx_with_conn(conn)
        with pytest.raises(ToolError):
            await tool_fns["ontology_term_details"](ctx, term_ids=[])


@pytest.mark.kg
class TestOntologyOrganismResolutionLive:
    """PR 3b review fix #1: `organism` on search_ontology /
    ontology_term_details resolves like every other tool ('MED4' ->
    'Prochlorococcus MED4'); unknown names raise."""

    def test_search_ontology_short_name_matches_full_name(self, conn):
        short = api.search_ontology(
            ontology=["interpro"], interpro_type="HOMOLOGOUS_SUPERFAMILY",
            organism="MED4", min_gene_count=5, limit=5, conn=conn)
        first = short["results"][0]
        assert first["id"] == "interpro:IPR027417"
        assert first["organism_gene_count"] == 119
        full = api.search_ontology(
            ontology=["interpro"], interpro_type="HOMOLOGOUS_SUPERFAMILY",
            organism="Prochlorococcus MED4", min_gene_count=5, limit=5,
            conn=conn)
        assert [r["id"] for r in full["results"]] == [
            r["id"] for r in short["results"]]
        assert full["total_matching"] == short["total_matching"]

    def test_search_ontology_unknown_organism_raises(self, conn):
        with pytest.raises(ValueError, match="no organism matching"):
            api.search_ontology(
                ontology=["merops"], level=1, organism="NotAnOrganism",
                conn=conn)

    def test_term_details_short_name(self, conn):
        result = api.ontology_term_details(
            ["tcdb:3.A.1"], organism="MED4", conn=conn)
        row = result["results"][0]
        assert row["organism_gene_count"] > 0
        full = api.ontology_term_details(
            ["tcdb:3.A.1"], organism="Prochlorococcus MED4", conn=conn)
        assert full["results"][0]["organism_gene_count"] == row["organism_gene_count"]

    def test_term_details_unknown_organism_raises(self, conn):
        with pytest.raises(ValueError, match="no organism matching"):
            api.ontology_term_details(
                ["tcdb:3.A.1"], organism="NotAnOrganism", conn=conn)


@pytest.mark.kg
class TestOntologyTermDetailsStripRuleLive:
    """PR 3b review fixes #4 / #5: KEGG chemistry counts on pathway terms
    only; `direct_gene_count` absent when the node carries none."""

    def test_kegg_pathway_carries_chemistry_counts(self, conn):
        result = api.ontology_term_details(
            ["kegg.pathway:ko00010", "kegg.orthology:K00001"], conn=conn)
        rows = {r["term_id"]: r for r in result["results"]}
        pathway = rows["kegg.pathway:ko00010"]
        assert pathway["reaction_count"] == 43  # 40 → 43 2026-10-28: reactions only Ford 2021 strains catalyse
        assert pathway["metabolite_count"] == 31
        ko = rows["kegg.orthology:K00001"]
        assert "reaction_count" not in ko
        assert "metabolite_count" not in ko

    def test_pfam_has_no_direct_gene_count_key(self, conn, kg_count):
        result = api.ontology_term_details(
            ["pfam:PF00005", "go:0006979"], conn=conn)
        rows = {r["term_id"]: r for r in result["results"]}
        assert "direct_gene_count" not in rows["pfam:PF00005"]
        assert rows["go:0006979"]["direct_gene_count"] == kg_count(
            _TERM_PROP, id="go:0006979", prop="direct_gene_count")



# ---------------------------------------------------------------------------
# Slice 4 — light surface + paper-batch absorption, live (spec
# docs/tool-specs/2026-08-27-slice4-light-surface.md §7, §9, §10).
# Numbers verified live 2026-08-27 against the post-fix KG-SYNC-006 build
# (built_at 2026-08-27T16:11Z; 48 organisms, 209 experiments, 49 papers).
# ---------------------------------------------------------------------------

_SLICE4_MED4 = "Prochlorococcus MED4"
_SLICE4_UREA = "kegg.compound:C00086"
_SLICE4_MARREF = "Alteromonas (MarRef v6)"
# MATCH (ca:ClusteringAnalysis) WHERE ca.cluster_type = 'decay_pattern' RETURN ca.id
_SLICE4_DECAY_ANALYSIS = "clustering_analysis:gb-2010-11-5-r54:decay_clusters"
# A MED4 gene inside that analysis' clusters (verified live 2026-08-27).
_SLICE4_DECAY_GENE = "PMM2072"
# OrganismTaxon with all four annotation rollups = 0 (treatment taxon, 0 genes).
_SLICE4_ALL_ZERO_ORGANISM = "Phage"
_SLICE4_ANNOT_COLS = (
    "peptidase_gene_count", "nonpeptidase_homolog_gene_count",
    "interpro_gene_count", "ncbifam_gene_count",
)


@pytest.mark.kg
class TestKGReleaseInfoVocabularyHashLive:
    """Spec §9.1: on KG-SYNC-006 the verdict is `ok` and bucket 6 passes;
    the KG's hash is surfaced in the identity block."""

    def test_verdict_ok_and_bucket_six_passed(self, conn):
        report = api.kg_release_info(conn)
        b6 = [a for a in report["asserts"]
              if a["kind"] == "controlled_vocabularies_hash"]
        assert len(b6) == 1
        assert b6[0]["passed"] is True, b6[0]
        assert b6[0]["expected"] == b6[0]["actual"]
        assert report["verdict"] == "ok", report["summary"]

    def test_identity_surfaces_the_live_hash(self, conn):
        report = api.kg_release_info(conn)
        live = conn.execute_query(
            "MATCH (s:Schema_info {id: 'schema_info'}) "
            "RETURN s.controlled_vocabularies_hash AS h")[0]["h"]
        assert report["kg"]["controlled_vocabularies_hash"] == live

    def test_altered_pin_warns_naming_the_vocabulary(self, conn, monkeypatch):
        """Spec §9.1 second half: with the pin altered → `warn` naming the
        hash / vocabulary set."""
        from multiomics_explorer.kg import constants
        monkeypatch.setitem(
            constants.EXPECTED_KG_SHAPE, "controlled_vocabularies_hash",
            "sha256:" + "0" * 64)
        report = api.kg_release_info(conn)
        assert report["verdict"] == "warn"
        b6 = next(a for a in report["asserts"]
                  if a["kind"] == "controlled_vocabularies_hash")
        assert b6["passed"] is False
        assert "vocabulary" in report["summary"].lower()

    @pytest.mark.asyncio
    async def test_wrapper_validates_bucket_six(self, tool_fns, conn):
        ctx = _ctx_with_kg_report(conn)
        response = await tool_fns["kg_release_info"](ctx)
        kinds = {a.kind for a in response.asserts}
        assert "controlled_vocabularies_hash" in kinds
        assert response.kg.controlled_vocabularies_hash
        assert response.kg.controlled_vocabularies_hash.startswith("sha256:")


@pytest.mark.kg
class TestListOrganismsAnnotationCapabilityLive:
    """Spec §9.3 / §10: one row per organism (Schema_info.organism_count);
    MarRef v6 tops `top_annotation_capability`
    with 148 peptidase genes; a single-organism subset ranks exactly that
    organism; an all-zero treatment taxon is excluded."""

    def test_every_organism_row_carries_the_four_counts(self, conn):
        n_org = conn.execute_query(
            "MATCH (s:Schema_info {id: 'schema_info'}) "
            "RETURN s.organism_count AS n")[0]["n"]
        assert n_org > 40, n_org  # sanity floor — an empty DB must fail
        res = api.list_organisms(limit=500, conn=conn)
        assert res["total_entries"] == n_org
        assert res["total_matching"] == n_org
        assert len(res["results"]) == n_org
        for row in res["results"]:
            for col in _SLICE4_ANNOT_COLS:
                assert isinstance(row[col], int) and row[col] >= 0, (
                    row["organism_name"], col)

    def test_marref_tops_with_148(self, conn):
        res = api.list_organisms(limit=500, conn=conn)
        cap = res["top_annotation_capability"]
        assert len(cap) == 10
        assert cap[0]["organism_name"] == _SLICE4_MARREF
        assert cap[0]["preferred_name"] == _SLICE4_MARREF
        assert cap[0]["peptidase_gene_count"] == 148
        assert cap[0]["nonpeptidase_homolog_gene_count"] == 31
        assert cap[0]["interpro_gene_count"] == 3746
        assert cap[0]["ncbifam_gene_count"] == 1379
        # then AD45 129, Shewanella W3-18-1 128, BGP6 127 (spec §10)
        assert [c["peptidase_gene_count"] for c in cap[:4]] == [148, 129, 128, 127]
        peps = [c["peptidase_gene_count"] for c in cap]
        assert peps == sorted(peps, reverse=True)

    def test_summary_mode_is_the_full_ranking_detail_mode_is_capped(self, conn):
        """llm-review 2b.2 `_cap_breakdowns`: detail calls (summary=False)
        cap the ranking to the first 10 with `_truncated=True`; summary=True
        carries the full ranking. Detail's capped list is exactly the
        summary ranking's first 10 entries."""
        detail_result = api.list_organisms(limit=500, conn=conn)
        detail = detail_result["top_annotation_capability"]
        summary_result = api.list_organisms(summary=True, conn=conn)
        summary = summary_result["top_annotation_capability"]
        assert len(detail) == 10
        assert detail_result["top_annotation_capability_truncated"] is True
        assert len(summary) > 10
        assert "top_annotation_capability_truncated" not in summary_result
        assert summary[:10] == detail

    def test_med4_subset_ranks_exactly_med4(self, conn):
        res = api.list_organisms(organism_names=[_SLICE4_MED4], conn=conn)
        cap = res["top_annotation_capability"]
        assert [c["organism_name"] for c in cap] == [_SLICE4_MED4]
        row = res["results"][0]
        for col in _SLICE4_ANNOT_COLS:
            assert cap[0][col] == row[col], col
        assert row["peptidase_gene_count"] == 50

    def test_all_zero_organism_excluded(self, conn):
        res = api.list_organisms(
            organism_names=[_SLICE4_ALL_ZERO_ORGANISM, _SLICE4_MED4], conn=conn)
        assert res["not_found"] == []
        names = [c["organism_name"] for c in res["top_annotation_capability"]]
        assert names == [_SLICE4_MED4]
        zero = api.list_organisms(
            organism_names=[_SLICE4_ALL_ZERO_ORGANISM], conn=conn)
        assert zero["total_matching"] >= 1
        assert zero["top_annotation_capability"] == []

    def test_sum_of_peptidase_counts(self, conn):
        """Spec §7.1: Σ peptidase 8,053 over the 123 organisms (7,926 before 83-1; 3,439 over the old 47)."""
        res = api.list_organisms(limit=500, conn=conn)
        assert sum(r["peptidase_gene_count"] for r in res["results"]) == 8053

    @pytest.mark.asyncio
    async def test_wrapper_round_trip(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_organisms"](ctx, summary=True)
        assert response.top_annotation_capability[0].organism_name == _SLICE4_MARREF
        assert response.top_annotation_capability[0].peptidase_gene_count == 148


@pytest.mark.kg
class TestListFilterValuesClusterTypeLive:
    """Spec §9.4: 6 values from the ControlledVocabulary node,
    `source='vocabulary'`, no pivot warning."""

    _SIX = {"time_course", "diel", "condition_comparison",
            "expression_bin", "decay_pattern", "genomic_island"}

    def test_six_values_from_vocabulary(self, conn):
        result = api.list_filter_values(filter_type="cluster_type", conn=conn)
        assert result["total_entries"] == 6
        assert {r["value"] for r in result["results"]} == self._SIX
        assert all(r["source"] == "vocabulary" for r in result["results"])
        assert all(r["applies_to"] == ["ClusteringAnalysis"]
                   for r in result["results"])
        assert result["warnings"] == []

    def test_matches_the_offline_constant(self, conn):
        from multiomics_explorer.kg.constants import VALID_CLUSTER_TYPES
        result = api.list_filter_values(filter_type="cluster_type", conn=conn)
        assert {r["value"] for r in result["results"]} == VALID_CLUSTER_TYPES

    @pytest.mark.asyncio
    async def test_wrapper_round_trip(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_filter_values"](
            ctx, filter_type="cluster_type")
        assert {r.value for r in response.results} == self._SIX


@pytest.mark.kg
class TestListFilterValuesMultiLabelVocabsLive:
    """llm-review 2b.1: list_filter_values serves the remaining closed
    vocabularies — treatment_type / background_factors (union across
    Experiment, DerivedMetric, MetaboliteAssay, ClusteringAnalysis),
    table_scope (Experiment only), detection_status
    (Assay_quantifies_metabolite edge), expression_status
    (Changes_expression_of edge)."""

    def test_treatment_type_unions_at_least_15_values(self, conn):
        result = api.list_filter_values(filter_type="treatment_type", conn=conn)
        assert result["total_entries"] >= 15
        for row in result["results"]:
            assert row["applies_to"], row
            assert set(row["applies_to"]) <= {
                "Experiment", "DerivedMetric", "MetaboliteAssay",
                "ClusteringAnalysis",
            }

    def test_background_factors_unions_labels(self, conn):
        result = api.list_filter_values(filter_type="background_factors", conn=conn)
        assert result["total_entries"] >= 5
        for row in result["results"]:
            assert row["applies_to"], row

    def test_table_scope_is_experiment_only(self, conn):
        result = api.list_filter_values(filter_type="table_scope", conn=conn)
        assert result["total_entries"] >= 1
        assert all(r["applies_to"] == ["Experiment"] for r in result["results"])

    def test_detection_status_is_edge_scoped(self, conn):
        result = api.list_filter_values(filter_type="detection_status", conn=conn)
        assert result["total_entries"] >= 1
        assert all(
            r["applies_to"] == ["Assay_quantifies_metabolite"]
            for r in result["results"]
        )

    def test_expression_status_is_edge_scoped(self, conn):
        result = api.list_filter_values(filter_type="expression_status", conn=conn)
        assert result["total_entries"] >= 1
        assert all(
            r["applies_to"] == ["Changes_expression_of"]
            for r in result["results"]
        )

    @pytest.mark.asyncio
    async def test_wrapper_round_trip_treatment_type(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_filter_values"](
            ctx, filter_type="treatment_type")
        assert len(response.results) >= 15
        assert all(r.applies_to for r in response.results)


@pytest.mark.kg
class TestTcdbRouteRowsLive:
    """TCDB cleanup: urea x MED4 rows carry the compact TCDB route fields
    (tcdb_route / tcdb_calls / tcdb_identity / tcdb_direction /
    attached_tcdb_id / tcdb_substrate_system_count); metabolism and GO rows
    carry them as None (polymorphic shape). The retired gene-level
    `transport_substrate_resolution` / `tcdb_evidence_score` are gone."""

    _RETIRED = ("transport_substrate_resolution", "tcdb_evidence_score",
                "substrate_depth")

    def test_urea_med4_rows(self, conn):
        res = api.genes_by_metabolite(
            [_SLICE4_UREA], _SLICE4_MED4, limit=1000, conn=conn)
        assert not res["truncated"]
        rows = res["results"]
        assert rows
        for row in rows:
            for gone in self._RETIRED:
                assert gone not in row, (gone, row["locus_tag"])
            if row["evidence_source"] in ("metabolism", "go_transport"):
                assert row["tcdb_route"] is None
                assert row["tcdb_calls"] is None
                assert row["attached_tcdb_id"] is None
            else:
                assert row["tcdb_route"] == "direct"
                assert row["attached_tcdb_id"] == row["tcdb_family_id"]
                assert row["tcdb_direction"] in ("uptake", "export", "unknown")
                assert set(row["tcdb_calls"]) <= {
                    "diamond_best_hit", "diamond_tier", "eggnog"}
                assert row["tcdb_substrate_system_count"] is None
        assert {r["evidence_source"] for r in rows} == {
            "metabolism", "transport", "go_transport"}

    def test_tcdb_calls_are_in_precedence_order(self, conn):
        order = ["diamond_best_hit", "diamond_tier", "eggnog"]
        res = api.genes_by_metabolite(
            [_SLICE4_UREA], _SLICE4_MED4, evidence_sources=["transport"],
            limit=1000, conn=conn)
        assert res["results"]
        for row in res["results"]:
            calls = row["tcdb_calls"]
            assert calls == sorted(calls, key=order.index), row
            # eggNOG representative edge <=> null identity
            if calls == ["eggnog"]:
                assert row["tcdb_identity"] is None

    def test_top_genes_assignment_count_matches_gene_overview(self, conn):
        res = api.genes_by_metabolite(
            [_SLICE4_UREA], _SLICE4_MED4, evidence_sources=["transport"],
            limit=1000, conn=conn)
        top = {g["locus_tag"]: g for g in res["top_genes"]}
        assert top
        ov = {r["locus_tag"]: r for r in api.gene_overview(
            sorted(top), conn=conn)["results"]}
        for lt, g in top.items():
            assert g["tcdb_assignment_count"] == ov[lt]["tcdb_assignment_count"], lt
            for gone in ("transport_substrate_resolution",
                         "tcdb_evidence_score_max"):
                assert gone not in g

    def test_family_rows_carry_system_count_and_attached_node(self, conn):
        """phnD PMM0673 walks from tcdb:3.A.1.9 (spec motivating case)."""
        mbg = api.metabolites_by_gene(
            ["PMM0673"], _SLICE4_MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=100, conn=conn)
        assert mbg["results"]
        for row in mbg["results"]:
            assert row["tcdb_route"] == "family"
            assert row["attached_tcdb_id"] == row["tcdb_family_id"] == "tcdb:3.A.1.9"
            assert row["tcdb_substrate_system_count"] >= 1
            assert row["tcdb_direction"] in ("uptake", "export", "unknown")

    def test_wrapper_round_trip(self, conn):
        from multiomics_explorer.mcp_server.tools import GenesByMetaboliteResponse
        res = api.genes_by_metabolite(
            [_SLICE4_UREA], _SLICE4_MED4, limit=50, conn=conn)
        model = GenesByMetaboliteResponse(**res)
        by_src = {}
        for r in model.results:
            by_src.setdefault(r.evidence_source, r)
        assert by_src["metabolism"].tcdb_route is None
        assert by_src["transport"].tcdb_route == "direct"
        assert by_src["transport"].tcdb_calls


@pytest.mark.kg
class TestCharacterizationExperimentsLive:
    """Spec §3.4 (KG contract v2): `treatment_type` is dense and non-empty;
    the Steglich 2010 decay analysis names what was measured
    (`['rna_decay']`) and both cluster tools return it as a well-formed row
    rather than a ToolError (it was `None` → ValidationError on the first
    KG-SYNC-006 build)."""

    def test_list_clustering_analyses_decay_analysis(self, conn):
        res = api.list_clustering_analyses(
            analysis_ids=[_SLICE4_DECAY_ANALYSIS], conn=conn)
        assert res["total_matching"] == 1
        row = res["results"][0]
        assert row["cluster_type"] == "decay_pattern"
        assert row["treatment_type"] == ["rna_decay"]

    def test_gene_clusters_by_gene_decay_analysis(self, conn):
        res = api.gene_clusters_by_gene(
            [_SLICE4_DECAY_GENE], organism=_SLICE4_MED4,
            analysis_ids=[_SLICE4_DECAY_ANALYSIS], conn=conn)
        assert res["not_found"] == []
        assert res["results"], res
        for row in res["results"]:
            assert row["analysis_id"] == _SLICE4_DECAY_ANALYSIS
            assert row["treatment_type"] == ["rna_decay"]

    @pytest.mark.asyncio
    async def test_wrappers_do_not_raise(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        lca = await tool_fns["list_clustering_analyses"](
            ctx, analysis_ids=[_SLICE4_DECAY_ANALYSIS])
        assert lca.results[0].treatment_type == ["rna_decay"]
        gcg = await tool_fns["gene_clusters_by_gene"](
            ctx, locus_tags=[_SLICE4_DECAY_GENE], organism=_SLICE4_MED4,
            analysis_ids=[_SLICE4_DECAY_ANALYSIS])
        assert gcg.results and gcg.results[0].treatment_type == ["rna_decay"]


@pytest.mark.kg
class TestListExperimentsCocultureRole:
    """Backlog 2c.6 live smoke — coculture_role filter, verbose
    coculture_partners, by_coculture_role, list_filter_values('partner_role').
    Relational assertions; live counts at spec freeze (2026-10-13T13:51Z build):
    Alteromonas 53 = 5 treatment + 48 background; role-only 44 treatment /
    78 background."""

    def test_alteromonas_treatment_rows_are_coculture_contrasts(self, conn):
        result = api.list_experiments(
            coculture_partner="Alteromonas", coculture_role="treatment",
            verbose=True, conn=conn,
        )
        rows = result["results"]
        assert rows
        assert result["total_matching"] == len(rows)
        for r in rows:
            assert "coculture" in r["treatment_type"], r["experiment_id"]
            alt = [p for p in r["coculture_partners"]
                   if "alteromonas" in p["name"].lower()]
            assert alt, r["experiment_id"]
            assert all(p["role"] == "treatment" for p in alt)

    def test_alteromonas_background_rows_have_background_partner(self, conn):
        result = api.list_experiments(
            coculture_partner="Alteromonas", coculture_role="background",
            verbose=True, conn=conn,
        )
        rows = result["results"]
        assert rows
        for r in rows:
            assert any(
                "alteromonas" in p["name"].lower() and p["role"] == "background"
                for p in r["coculture_partners"]
            ), r["experiment_id"]

    def test_role_split_sums_to_partner_only_count(self, conn):
        def n(**kw):
            return api.list_experiments(
                coculture_partner="Alteromonas", summary=True, conn=conn, **kw,
            )["total_matching"]
        total = n()
        treat = n(coculture_role="treatment")
        back = n(coculture_role="background")
        assert treat > 0 and back > 0
        # KG invariant: no experiment mixes roles -> split is a partition.
        assert treat + back == total

    def test_summary_by_coculture_role_matches_split(self, conn):
        summ = api.list_experiments(
            coculture_partner="Alteromonas", summary=True, conn=conn,
        )
        assert "by_coculture_role" in summ
        roles = {b["coculture_role"]: b["count"] for b in summ["by_coculture_role"]}
        assert set(roles) == {"treatment", "background"}
        assert roles["treatment"] == api.list_experiments(
            coculture_partner="Alteromonas", coculture_role="treatment",
            summary=True, conn=conn)["total_matching"]
        assert roles["background"] == api.list_experiments(
            coculture_partner="Alteromonas", coculture_role="background",
            summary=True, conn=conn)["total_matching"]
        assert sum(roles.values()) == summ["total_matching"]

    def test_by_coculture_role_present_on_detail(self, conn):
        result = api.list_experiments(limit=1, conn=conn)
        assert "by_coculture_role" in result
        assert {b["coculture_role"] for b in result["by_coculture_role"]} <= {
            "treatment", "background"}

    def test_role_only_treatment_includes_phage(self, conn):
        result = api.list_experiments(
            coculture_role="treatment", verbose=True, conn=conn,
        )
        rows = result["results"]
        assert any("viral" in r["treatment_type"] for r in rows)
        assert any("coculture" in r["treatment_type"] for r in rows)
        for r in rows:
            assert any(p["role"] == "treatment" for p in r["coculture_partners"])

    def test_role_only_partitions_partnered_experiments(self, conn):
        treat = api.list_experiments(coculture_role="treatment", summary=True,
                                     conn=conn)["total_matching"]
        back = api.list_experiments(coculture_role="background", summary=True,
                                    conn=conn)["total_matching"]
        all_rows = api.list_experiments(conn=conn)["results"]
        partnered = sum(1 for r in all_rows if r["coculture_partner"])
        assert treat + back == partnered

    def test_verbose_coculture_partners_names_equal_list(self, conn):
        result = api.list_experiments(verbose=True, conn=conn)
        rows = result["results"]
        assert len(rows) == result["total_matching"]
        for r in rows:
            cps = r["coculture_partners"]
            assert [p["name"] for p in cps] == r["coculture_partner"], \
                r["experiment_id"]
            for p in cps:
                assert p["role"] in {"treatment", "background"}
                assert p["organism_id"]
                assert p["organism_type"]

    def test_compact_rows_have_no_coculture_partners(self, conn):
        result = api.list_experiments(coculture_partner="Alteromonas", limit=5,
                                      conn=conn)
        for r in result["results"]:
            assert "coculture_partners" not in r

    def test_mcp_wrapper_verbose_coculture_partners(self, tool_fns, conn):
        result = asyncio.run(tool_fns["list_experiments"](
            _ctx_with_conn(conn), coculture_partner="Alteromonas",
            coculture_role="treatment", verbose=True, limit=10,
        ))
        assert result.results
        for r in result.results:
            assert all(cp.role == "treatment" for cp in r.coculture_partners
                       if "alteromonas" in cp.name.lower())
        assert {b.coculture_role for b in result.by_coculture_role} == {"treatment"}

    def test_list_filter_values_partner_role(self, conn):
        result = api.list_filter_values(filter_type="partner_role", conn=conn)
        values = {r["value"] for r in result["results"]}
        assert values == {"treatment", "background"}
        for r in result["results"]:
            assert r["applies_to"] == ["Tests_coculture_with"]
            assert r["source"] == "vocabulary"


# ---------------------------------------------------------------------------
# Metabolite identity surface (spec docs/tool-specs/metabolite-identity-surface.md)
# Live values verified on build 2026-10-15T19:17Z.
# ---------------------------------------------------------------------------

_MIS_MSYSTEMS_FLAG_ASSAYS = [
    "metabolite_assay:msystems.01261-22:presence_flags_table_s2:"
    "presence_flag_extracellular",
    "metabolite_assay:msystems.01261-22:presence_flags_table_s2:"
    "presence_flag_intracellular",
]
_MIS_PNAS_MIT9313_ASSAY = (
    "metabolite_assay:pnas.2213271120:"
    "metabolites_intracellular_mit9313:cellular_concentration")


@pytest.mark.kg
class TestMetaboliteIdentitySurface:
    """§A resolver, §B xref filters, §C/§C2 classes, §D stereo_assignment."""

    # -- §A resolver ---------------------------------------------------------
    def test_retired_chebi_resolves_to_nitrate(self, conn):
        out = api.list_metabolites(metabolite_ids=["chebi:14654"], conn=conn)
        assert [r["metabolite_id"] for r in out["results"]] == [
            "kegg.compound:C00244"]
        assert out["resolved_aliases"] == {
            "chebi:14654": ["kegg.compound:C00244"]}
        assert out["not_found"]["metabolite_ids"] == []

    def test_recurated_id_lands_in_not_found_with_warning(self, conn):
        out = api.list_metabolites(
            metabolite_ids=["kegg.compound:C00525"], conn=conn)
        assert out["not_found"]["metabolite_ids"] == ["kegg.compound:C00525"]
        assert out["resolved_aliases"] == {}
        assert any("kegg.compound:C00078" in w for w in out["warnings"]), \
            out["warnings"]

    def test_removed_stereo_xref_lands_in_not_found_with_warning(self, conn):
        rows = conn.execute_query(
            "MATCH (m:Metabolite) WHERE m.removed_stereo_xrefs IS NOT NULL "
            "RETURN m.id AS id, m.removed_stereo_xrefs[0] AS x LIMIT 1")
        if not rows:
            pytest.skip("KG predates Metabolite.removed_stereo_xrefs")
        gen, removed = rows[0]["id"], rows[0]["x"]
        out = api.list_metabolites(metabolite_ids=[removed], conn=conn)
        assert out["not_found"]["metabolite_ids"] == [removed]
        assert out["resolved_aliases"] == {}
        assert any(gen in w and "stereo" in w for w in out["warnings"]), \
            out["warnings"]

    def test_role_id_lands_in_not_found_with_warning(self, conn):
        out = api.list_metabolites(metabolite_ids=["chebi:10004"], conn=conn)
        assert out["not_found"]["metabolite_ids"] == ["chebi:10004"]
        assert any("chebi.role:33229" in w for w in out["warnings"]), \
            out["warnings"]

    def test_mixed_batch(self, conn):
        out = api.list_metabolites(
            metabolite_ids=["kegg.compound:C00244", "chebi:14654",
                            "kegg.compound:C99999"],
            conn=conn)
        assert [r["metabolite_id"] for r in out["results"]] == [
            "kegg.compound:C00244"]
        assert out["resolved_aliases"] == {
            "chebi:14654": ["kegg.compound:C00244"]}
        assert out["not_found"]["metabolite_ids"] == ["kegg.compound:C99999"]

    def test_genes_by_metabolite_retired_nitrate_returns_rows(self, conn):
        out = api.genes_by_metabolite(
            ["chebi:14654"], "Prochlorococcus MED4", conn=conn)
        assert out["total_matching"] > 0
        assert out["resolved_aliases"] == {
            "chebi:14654": ["kegg.compound:C00244"]}
        assert {r["metabolite_id"] for r in out["results"]} == {
            "kegg.compound:C00244"}

    # -- §B xref filters -----------------------------------------------------
    def test_kegg_xref_filter_finds_merged_member(self, conn):
        out = api.list_metabolites(kegg_compound_ids=["C01327"], conn=conn)
        assert [r["metabolite_id"] for r in out["results"]] == [
            "kegg.compound:C00698"]

    def test_kegg_xref_filter_own_id(self, conn):
        out = api.list_metabolites(kegg_compound_ids=["C00085"], conn=conn)
        assert [r["metabolite_id"] for r in out["results"]] == [
            "kegg.compound:C00085"]

    @pytest.mark.parametrize("kwargs", [
        {"chebi_ids": ["chebi:14654"]},
        {"chebi_ids": ["17632"]},
        {"mnxm_ids": ["mnx:MNXM732399"]},  # MNXM732398 left nitrate 2026-10-26T04:21Z
    ])
    def test_xref_filters_find_nitrate(self, conn, kwargs):
        out = api.list_metabolites(conn=conn, **kwargs)
        assert [r["metabolite_id"] for r in out["results"]] == [
            "kegg.compound:C00244"]

    def test_chebi_filter_d_glucose(self, conn):
        """Ask 5 (build 2026-10-15T19:58Z): chebi:17634 sits on D-Glucose."""
        out = api.list_metabolites(chebi_ids=["17634"], conn=conn)
        assert [r["metabolite_id"] for r in out["results"]] == [
            "kegg.compound:C00031"]

    def test_hmdb_filter(self, conn):
        """KG ask 5 (build 2026-10-15T19:58Z) moved HMDB0000122 off the
        beta-anomer C00221 onto D-Glucose C00031."""
        out = api.list_metabolites(hmdb_ids=["hmdb:HMDB0000122"], conn=conn)
        assert [r["metabolite_id"] for r in out["results"]] == [
            "kegg.compound:C00031"]

    # -- §C/§C2 classes --------------------------------------------------------
    def test_structure_kind_generic_polymer(self, conn):
        out = api.list_metabolites(
            structure_kind=["generic", "polymer"], summary=True, conn=conn)
        # 650 → 675 2026-10-18T18:40Z: 25 of the 29 new GO-substrate nodes are generic.
        # 675 → 655 2026-10-24T17:33Z: TCDB 3a removed transport-only metabolites.
        assert out["total_matching"] == 667  # → 667 2026-10-28T05:04Z: Ford 2021 strains ← 655 → 647 2026-10-26T04:21Z: TCDB review re-keys

    def test_kegg_functional_category_peptides(self, conn):
        out = api.list_metabolites(
            kegg_functional_categories=["Peptides"], summary=True, conn=conn)
        assert out["total_matching"] == 59  # 60 → 61: a new GO-substrate node → 59 (2026-10-24T17:33Z, TCDB 3a removals)

    def test_kegg_brite_class_fatty_acyls(self, conn):
        out = api.list_metabolites(
            kegg_brite_classes=["Lipids: Fatty acyls"], summary=True, conn=conn)
        assert out["total_matching"] == 257  # → 257 2026-10-28T05:04Z: Ford 2021 strains ← 254 → 249 2026-10-24T17:33Z: TCDB 3a removals (prostaglandins etc.)

    def test_ouabain_brite_classes(self, conn):
        out = api.list_metabolites(
            # Digoxin replaces ouabain (kegg.compound:C01443, removed by TCDB 3a): same
            # four BRITE classes and Steroids category.
            metabolite_ids=["kegg.compound:C06956"], conn=conn)
        row = out["results"][0]
        assert sorted(row["kegg_brite_classes"]) == [
            "Glycosides: O-glycosides", "Lipids: Sterol lipids",
            "Natural toxins: Phytotoxins", "Phytochemical compounds: Terpenoids",
        ]
        assert row["kegg_functional_categories"] == ["Steroids"]
        assert row["structure_kind"] == "defined"

    def test_fumarate_unclassified_is_absent(self, conn):
        out = api.list_metabolites(
            metabolite_ids=["kegg.compound:C00122"], conn=conn)
        row = out["results"][0]
        assert "kegg_functional_categories" not in row
        assert "kegg_brite_classes" not in row

    def test_summary_not_classified_tails(self, conn):
        out = api.list_metabolites(summary=True, conn=conn)
        # +29 GO-substrate nodes 2026-10-18T18:40Z (4 defined, 25 generic).
        assert out["by_kegg_functional_category"][-1] == {
            "kegg_functional_category": "not classified", "count": 2925}  # 2026-10-28T05:04Z: Ford 2021 strains; 2026-10-24T17:33Z: TCDB 3a removals; 2026-10-26T04:21Z: TCDB review re-keys
        assert out["by_kegg_brite_class"][-1] == {
            "kegg_brite_class": "not classified", "count": 2597}
        assert {b["structure_kind"]: b["count"]
                for b in out["by_structure_kind"]} == {
            "defined": 2584, "generic": 641, "polymer": 26}

    def test_transport_n_breakdown(self, conn):
        out = api.list_metabolites(
            evidence_sources=["transport"], elements=["N"], summary=True,
            conn=conn)
        assert out["total_matching"] == 646  # → 646 2026-10-28T05:04Z: Ford 2021 strains ← 672 → 620 2026-10-24T17:33Z: TCDB 3a → 628 2026-10-26T04:21Z: generic forms added
        assert {b["structure_kind"]: b["count"]
                for b in out["by_structure_kind"]} == {
            "defined": 584, "generic": 58, "polymer": 4}
        assert out["by_kegg_functional_category"][-1] == {
            "kegg_functional_category": "not classified", "count": 513}

    def test_unknown_brite_class_warns_and_matches_nothing(self, conn):
        out = api.list_metabolites(
            kegg_brite_classes=["Fatty acyls"], summary=True, conn=conn)
        assert out["total_matching"] == 0
        assert any("Fatty acyls" in w for w in out["warnings"])

    # -- §D stereo_assignment ------------------------------------------------
    def test_flags_dominant_form_per_msystems_assay(self, conn):
        out = api.metabolites_by_flags_assay(
            assay_ids=_MIS_MSYSTEMS_FLAG_ASSAYS,
            stereo_assignment=["dominant_form_assumed"], summary=True,
            conn=conn)
        assert {b["assay_id"]: b["count"] for b in out["by_assay"]} == {
            a: 29 for a in _MIS_MSYSTEMS_FLAG_ASSAYS}  # 21 → 23 2026-10-24T17:33Z: stereo rule change; 23 → 29 2026-10-31T12:27Z: KEGG-filed stereo rule + 6 msystems names

    def test_flags_by_stereo_assignment_sums_and_warns(self, conn):
        out = api.metabolites_by_flags_assay(
            assay_ids=_MIS_MSYSTEMS_FLAG_ASSAYS, summary=True, conn=conn)
        assert sum(b["count"] for b in out["by_stereo_assignment"]) \
            == out["total_matching"]
        assert {b["stereo_assignment"]: b["count"]
                for b in out["by_stereo_assignment"]} == {
            "as_reported": 128, "dominant_form_assumed": 58}  # 2026-10-24T17:33Z: stereo rule change; 140/46 → 128/58 2026-10-31T12:27Z: KEGG-filed stereo rule + 6 msystems names
        assert any("dominant stereo form" in w for w in out["warnings"])

    def test_quantifies_by_stereo_assignment_sums(self, conn):
        out = api.metabolites_by_quantifies_assay(
            assay_ids=[_MIS_PNAS_MIT9313_ASSAY], summary=True, conn=conn)
        assert sum(b["count"] for b in out["by_stereo_assignment"]) \
            == out["total_matching"]

    def test_assays_by_metabolite_l_ala_all_assumed(self, conn):
        out = api.assays_by_metabolite(
            metabolite_ids=["kegg.compound:C00041"], summary=True, conn=conn)
        assert {b["stereo_assignment"]: b["count"]
                for b in out["by_stereo_assignment"]} == {
            "dominant_form_assumed": 6}
        assert sum(b["count"] for b in out["by_stereo_assignment"]) \
            == out["total_matching"]
        filtered = api.assays_by_metabolite(
            metabolite_ids=["kegg.compound:C00041"],
            stereo_assignment=["as_reported"], summary=True, conn=conn)
        assert filtered["total_matching"] == 0
        assert filtered["not_matched"] == ["kegg.compound:C00041"]

    # -- §E list_filter_values ---------------------------------------------
    @pytest.mark.parametrize("filter_type, expected", [
        ("structure_kind", {"defined", "generic", "polymer"}),
        ("stereo_assignment", {"as_reported", "dominant_form_assumed"}),
    ])
    def test_filter_values_small_vocabs(self, conn, filter_type, expected):
        out = api.list_filter_values(filter_type=filter_type, conn=conn)
        assert {r["value"] for r in out["results"]} == expected
        assert out["warnings"] == []

    def test_filter_values_kegg_functional_category(self, conn):
        out = api.list_filter_values(
            filter_type="kegg_functional_category", conn=conn)
        assert len(out["results"]) == 9
        assert "Peptides" in {r["value"] for r in out["results"]}

    def test_filter_values_kegg_brite_class(self, conn):
        out = api.list_filter_values(filter_type="kegg_brite_class", conn=conn)
        assert len(out["results"]) == 28
        assert "Lipids: Fatty acyls" in {r["value"] for r in out["results"]}


# ---------------------------------------------------------------------------
# Metabolite stereo-form hint (backlog 2c.8 part 3) —
# docs/tool-specs/metabolite-stereo-hint.md. Live MED4 facts (2026-10-16):
# Cysteine C00736 = 0 reactions / 5 families / 33 genes (transport-only);
# L-Cysteine C00097 = 13 / 3 / 38; D-Cysteine C00793 has no MED4 rows.
# 3-Phospho-D-glycerate C00197 has MED4 rows; its only stereo relative
# (Glycerate 3-phosphate C00597) has none.
# ---------------------------------------------------------------------------

_MSH_ORG = "Prochlorococcus MED4"
_MSH_CYS = "kegg.compound:C00736"
_MSH_LCYS = "kegg.compound:C00097"
_MSH_DCYS = "kegg.compound:C00793"
_MSH_UREA = "kegg.compound:C00086"
_MSH_3PG = "kegg.compound:C00197"


def _msh_stereo_warnings(out):
    return [w for w in out["warnings"] if "Stereo forms hold more rows" in w]


@pytest.mark.kg
class TestMetaboliteStereoHintKG:

    def test_list_metabolites_cysteine_relatives(self, conn):
        out = api.list_metabolites(
            metabolite_ids=[_MSH_CYS, _MSH_UREA], conn=conn)
        by_id = {r["metabolite_id"]: r for r in out["results"]}
        rels = by_id[_MSH_CYS]["stereo_relatives"]
        assert [(r["metabolite_id"], r["relation"]) for r in rels] == [
            (_MSH_LCYS, "specific_form"), (_MSH_DCYS, "specific_form")]
        lcys = rels[0]
        assert lcys["name"] == "L-Cysteine"
        assert lcys["catalyst_gene_count"] > 0
        assert lcys["transporter_gene_count"] > 0
        assert "stereo_relatives" not in by_id[_MSH_UREA]

    def test_list_metabolites_l_cysteine_relations(self, conn):
        out = api.list_metabolites(metabolite_ids=[_MSH_LCYS], conn=conn)
        rels = out["results"][0]["stereo_relatives"]
        assert [(r["metabolite_id"], r["relation"]) for r in rels] == [
            (_MSH_DCYS, "enantiomer"), (_MSH_CYS, "unspecified_form")]

    def test_gbm_cysteine_hints_l_not_d(self, conn):
        from multiomics_explorer.mcp_server.tools import (
            GenesByMetaboliteResponse,
        )
        out = api.genes_by_metabolite([_MSH_CYS], _MSH_ORG, conn=conn)
        GenesByMetaboliteResponse(**out)
        assert set(out["stereo_relatives"]) == {_MSH_CYS}
        (rel,) = out["stereo_relatives"][_MSH_CYS]
        assert rel["metabolite_id"] == _MSH_LCYS
        assert rel["relation"] == "specific_form"
        # TCDB cleanup: relative counts follow the direct gate — read the
        # L-form's own envelope instead of pinning (13, 3, 38 pre-3a; the 3
        # transporter families were inherited 3.A.1-lineage rows).
        lcys = api.genes_by_metabolite(
            [_MSH_LCYS], _MSH_ORG, summary=True, conn=conn)
        assert rel["reaction_count"] == lcys["reaction_count_total"] == 13
        assert rel["transporter_count"] == lcys["transporter_count_total"]
        assert rel["gene_count"] == lcys["gene_count_total"]
        assert out["stereo_forms_added"] == {}
        assert out["warnings"][0].startswith("Stereo forms hold more rows")
        assert "include_stereo_forms=True" in out["warnings"][0]
        # Post-3a generic Cysteine has no own MED4 rows (by_metabolite is
        # empty), which is exactly when the hint matters most.
        if out["by_metabolite"]:
            (bm,) = out["by_metabolite"]
            assert bm["stereo_relative_ids"] == [_MSH_LCYS]
        else:
            assert out["total_matching"] == 0

    def test_gbm_both_forms_passed_no_hint(self, conn):
        out = api.genes_by_metabolite(
            [_MSH_CYS, _MSH_LCYS], _MSH_ORG, conn=conn)
        assert out["stereo_relatives"] == {}
        assert _msh_stereo_warnings(out) == []

    def test_gbm_include_stereo_forms_tags_metabolism_rows(self, conn):
        from multiomics_explorer.mcp_server.tools import (
            GenesByMetaboliteResponse,
        )
        out = api.genes_by_metabolite(
            [_MSH_CYS], _MSH_ORG, include_stereo_forms=True, limit=500,
            conn=conn)
        GenesByMetaboliteResponse(**out)
        assert _MSH_LCYS in out["stereo_forms_added"][_MSH_CYS]
        tagged_metab = [
            r for r in out["results"]
            if r["evidence_source"] == "metabolism"
            and r.get("via_stereo_form_of") == _MSH_CYS]
        assert tagged_metab
        assert all(r["metabolite_id"] == _MSH_LCYS for r in tagged_metab)
        for r in out["results"]:
            if r["metabolite_id"] == _MSH_CYS:
                assert "via_stereo_form_of" not in r
        # Generic Cysteine has no own rows in MED4 under the TCDB direct gate
        # (its pre-3a rows were inherited 3.A.1 transport), so it is
        # not_matched iff its own default call is empty.
        own = api.genes_by_metabolite(
            [_MSH_CYS], _MSH_ORG, summary=True, conn=conn)["total_matching"]
        assert out["not_matched"] == ([] if own else [_MSH_CYS])
        assert out["stereo_relatives"] == {}
        assert _msh_stereo_warnings(out) == []

    def test_gbm_urea_no_hint(self, conn):
        out = api.genes_by_metabolite([_MSH_UREA], _MSH_ORG, conn=conn)
        assert out["stereo_relatives"] == {}
        assert out["stereo_forms_added"] == {}
        assert _msh_stereo_warnings(out) == []

    def test_gbm_stereo_linked_input_relative_without_rows(self, conn):
        out = api.genes_by_metabolite([_MSH_3PG], _MSH_ORG, conn=conn)
        assert out["total_matching"] > 0
        assert out["stereo_relatives"] == {}
        assert _msh_stereo_warnings(out) == []

    def test_mbg_cysteine_transporter_hints_l_cysteine(self, conn):
        from multiomics_explorer.mcp_server.tools import (
            MetabolitesByGeneResponse,
        )
        # TCDB cleanup: no MED4 gene reaches generic Cysteine through a
        # direct system post-3a; the family walk does (e.g. PMM1323), so the
        # transporter-side hint is exercised with the walk on.
        gbm = api.genes_by_metabolite(
            [_MSH_CYS], _MSH_ORG, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=1, conn=conn)
        assert gbm["results"], "no MED4 Cysteine transporter found"
        locus = gbm["results"][0]["locus_tag"]
        out = api.metabolites_by_gene(
            [locus], _MSH_ORG, include_tcdb_family_substrates=True, limit=500,
            conn=conn)
        MetabolitesByGeneResponse(**out)
        assert _MSH_CYS in out["stereo_relatives"]
        assert _MSH_LCYS in {
            r["metabolite_id"] for r in out["stereo_relatives"][_MSH_CYS]}
        assert out["warnings"][0].startswith("Stereo forms hold more rows")
        cys_rows = [r for r in out["results"]
                    if r["metabolite_id"] == _MSH_CYS]
        assert cys_rows
        for r in cys_rows:
            assert _MSH_LCYS in r["stereo_relative_ids"]
        assert any("stereo_relative_ids" not in r for r in out["results"])


# ---------------------------------------------------------------------------
# Control-timing surface (docs/tool-specs/control-timing-surface.md).
# KG 2026-10-18T07:51Z: control_timing CV {matched 151, baseline 18,
# mixed 4}; design_notes sparse on 138 experiments.
# ---------------------------------------------------------------------------
_CT_E7 = "10.1101/2025.11.24.690089_coculture_alteromonas_hot1a3_med4_rnaseq"


@pytest.mark.kg
class TestControlTimingSurface:

    def test_list_experiments_baseline_mixed_count(self, conn):
        out = api.list_experiments(
            control_timing=["baseline", "mixed"], summary=True, conn=conn)
        assert out["total_matching"] == 26  # +4 baseline 2026-10-31: Tetu 2009, Koch 2019 x2, Oleza 2015b
        counts = {b["control_timing"]: b["count"]
                  for b in out["by_control_timing"]}
        assert counts == {"baseline": 22, "mixed": 4}
        assert out["warnings"] == []

    def test_list_experiments_rows_match_filter(self, conn):
        out = api.list_experiments(
            control_timing=["baseline", "mixed"], limit=50, conn=conn)
        assert out["returned"] == 26
        for r in out["results"]:
            assert r["control_timing"] in ("baseline", "mixed")
            # every non-matched experiment carries design_notes (18 + 4)
            assert r.get("design_notes")

    def test_e7_matched_with_design_notes(self, conn):
        out = api.list_experiments(experiment_ids=[_CT_E7], conn=conn)
        assert out["returned"] == 1
        row = out["results"][0]
        assert row["control_timing"] == "matched"
        assert isinstance(row.get("design_notes"), str)
        assert row["design_notes"].strip()

    def test_list_experiments_design_notes_sparse(self, conn):
        """No row carries a null/'' design_notes key; at least one row omits it."""
        out = api.list_experiments(limit=500, conn=conn)
        assert any("design_notes" not in r for r in out["results"])
        for r in out["results"]:
            if "design_notes" in r:
                assert r["design_notes"]

    def test_unknown_control_timing_warns(self, conn):
        out = api.list_experiments(
            control_timing=["bogus"], summary=True, conn=conn)
        assert out["total_matching"] == 0
        assert any("'bogus'" in w and "control_timing" in w
                   for w in out["warnings"]), out["warnings"]

    def test_list_filter_values_control_timing(self, conn):
        out = api.list_filter_values(filter_type="control_timing", conn=conn)
        assert {r["value"] for r in out["results"]} == {
            "matched", "baseline", "mixed"}
        for r in out["results"]:
            assert r["applies_to"] == ["Experiment"]

    def test_de_by_gene_rows_carry_control_timing(self, conn):
        out = api.differential_expression_by_gene(
            locus_tags=["PMM0001"], limit=None, conn=conn)
        assert out["results"]
        values = [r["control_timing"] for r in out["results"]]
        assert set(values) <= {"matched", "baseline", "mixed"}
        assert "baseline" in values
        assert "matched" in values

    def test_de_by_gene_experiments_envelope(self, conn):
        out = api.differential_expression_by_gene(
            locus_tags=["PMM0001"], summary=True, conn=conn)
        assert out["experiments"]
        for e in out["experiments"]:
            assert e["control_timing"] in ("matched", "baseline", "mixed")
            if "design_notes" in e:
                assert e["design_notes"]
        assert any("design_notes" in e for e in out["experiments"])

    def test_de_by_ortholog_rows_carry_control_timing(self, conn):
        homs = api.gene_homologs(locus_tags=["PMM0001"], conn=conn)
        gid = homs["results"][0]["group_id"]
        out = api.differential_expression_by_ortholog(
            group_ids=[gid], limit=50, conn=conn)
        assert out["results"]
        for r in out["results"]:
            assert r["control_timing"] in ("matched", "baseline", "mixed")
            assert "design_notes" not in r

    @pytest.mark.asyncio
    async def test_wrapper_wire_omits_null_design_notes(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["list_experiments"](ctx, limit=500)
        dumped = response.model_dump()
        assert any("design_notes" not in r for r in dumped["results"])
        assert all("control_timing" in r for r in dumped["results"])


# ---------------------------------------------------------------------------
# GO transport surface (RED) — docs/tool-specs/go-transport-surface.md §7
# Live numbers pinned at KG built_at 2026-10-19T17:03:46Z.
# ---------------------------------------------------------------------------

_GOT_MED4 = "Prochlorococcus MED4"
_GOT_ALT = "Alteromonas mediterranea AltDE1"  # D12: exact strain, never "AltDE"
_GOT_UREA = "kegg.compound:C00086"
_GOT_SIDEROPHORE = "chebi.role:26672"
_GOT_MED4_GBM_TARGETS = [
    "kegg.compound:C00086", "kegg.compound:C00009", "kegg.compound:C00238",
    "kegg.compound:C01356", "chebi:16646",
]
_GOT_GO_EDGES = (
    "Molecular_function_transports_metabolite|"
    "Biological_process_transports_metabolite|"
    "Molecular_function_transports_chemical_role|"
    "Biological_process_transports_chemical_role"
)


def _got_by_source(results, source):
    return [r for r in results if r["evidence_source"] == source]


def _got_tcdb_direct_rows(conn, org=None, target_ids=None, locus_tags=None,
                          exclude_ids=()):
    """Live TCDB transport-arm row count under the direct gate (spec
    tcdb-cleanup-surface G1): distinct (gene, system, target) over
    `tcdb_gate = 'direct'` edges. GO / metabolism arm pins stay literal (the
    TCDB cleanup did not move them); the TCDB arm is read live so these
    GO-transport tests do not re-pin TCDB counts."""
    rows = conn.execute_query(
        "MATCH (g:Gene)-[gt:Gene_has_tcdb_family]->(s:TcdbFamily)"
        "-[:Tcdb_family_transports_metabolite"
        "|Tcdb_family_transports_chemical_role]->(x)\n"
        f"WHERE {TCDB_DIRECT_GATE_PREDICATE}\n"
        "  AND ($org IS NULL OR g.organism_name = $org)\n"
        "  AND ($ids IS NULL OR x.id IN $ids)\n"
        "  AND ($lts IS NULL OR g.locus_tag IN $lts)\n"
        "  AND NOT x.id IN $excl\n"
        "RETURN count(DISTINCT [g.locus_tag, s.id, x.id]) AS rows, "
        "count(DISTINCT g) AS genes, count(DISTINCT s) AS systems",
        org=org, ids=target_ids, lts=locus_tags, excl=list(exclude_ids))
    return rows[0]


def _got_med4_go_genes(conn):
    rows = conn.execute_query(
        "MATCH (g:Gene {organism_name: $o})-[:Gene_enables_molecular_function"
        "|Gene_involved_in_biological_process]->()-[:" + _GOT_GO_EDGES + "]->() "
        "RETURN collect(DISTINCT g.locus_tag) AS lts", o=_GOT_MED4)
    return sorted(rows[0]["lts"])


@pytest.mark.kg
class TestGoTransportGenesByMetabolite:
    def test_urea_med4_go_rows(self, conn):
        """Spec §7.1: 11 GO rows over PMM0970-PMM0974 (urtA 2, urtB 2, urtC 2,
        urtD 2, urtE 3); all arms = 4 metabolism + TCDB direct (live) + 11."""
        r = api.genes_by_metabolite(
            [_GOT_UREA], _GOT_MED4, limit=100, verbose=True, conn=conn)
        go = _got_by_source(r["results"], "go_transport")
        assert len(go) == 11
        per_gene = {}
        for row in go:
            per_gene[row["locus_tag"]] = per_gene.get(row["locus_tag"], 0) + 1
        assert per_gene == {
            "PMM0970": 2, "PMM0971": 2, "PMM0972": 2, "PMM0973": 2,
            "PMM0974": 3}
        assert {tuple(x["go_chebi_ids"]) for x in go} == {("CHEBI:16199",)}
        assert all(x["go_term_depth"] == 0 for x in go)
        assert all(x["target_kind"] == "metabolite" for x in go)
        urta = {x["go_term_id"]: x for x in go if x["locus_tag"] == "PMM0970"}
        assert urta["go:0033221"]["go_namespace"] == "molecular_function"
        assert urta["go:0033221"]["go_evidence"] == "curated"
        assert urta["go:0033221"]["go_sources"] == ["ncbi"]
        assert urta["go:0015840"]["go_namespace"] == "biological_process"
        assert urta["go:0015840"]["go_sources"] == ["cyanorak", "ncbi"]
        assert any(x["go_term_id"] == "go:0071918" for x in go)
        tcdb = _got_tcdb_direct_rows(conn, _GOT_MED4, [_GOT_UREA])
        assert len(_got_by_source(r["results"], "metabolism")) == 4
        assert len(_got_by_source(r["results"], "transport")) == tcdb["rows"]
        assert r["total_matching"] == 4 + tcdb["rows"] + 11
        # urtA-E (TCDB + GO) + the urease metabolism genes
        assert r["gene_count_total"] == len({x["locus_tag"] for x in r["results"]})
        assert r["transporter_count_total"] == tcdb["systems"]
        assert r["rows_by_go_term_depth"] == [{"go_term_depth": 0, "count": 11}]
        assert {e["evidence_source"]: e["count"]
                for e in r["by_evidence_source"]}["go_transport"] == 11

    def test_urea_med4_ancestors_unchanged(self, conn):
        r = api.genes_by_metabolite(
            [_GOT_UREA], _GOT_MED4, go_include_ancestors=True, limit=100,
            conn=conn)
        base = api.genes_by_metabolite(
            [_GOT_UREA], _GOT_MED4, summary=True, conn=conn)
        assert r["total_matching"] == base["total_matching"]
        assert r["rows_by_go_term_depth"] == [{"go_term_depth": 0, "count": 11}]

    def test_gbm_three_arm_paging_continuity(self, conn):
        """Review Focus 1: pages of 10 concatenate to exactly the full sorted
        rows; the first GO row follows every metabolism + TCDB row."""
        def key(r):
            return (r["evidence_source"], r["locus_tag"],
                    r.get("tcdb_family_id"), r.get("reaction_id"),
                    r.get("go_term_id"), r["metabolite_id"])
        full = api.genes_by_metabolite(
            [_GOT_UREA], _GOT_MED4, limit=100, conn=conn)["results"]
        n_pre_go = 4 + _got_tcdb_direct_rows(conn, _GOT_MED4, [_GOT_UREA])["rows"]
        assert len(full) == n_pre_go + 11
        idx_first_go = next(
            i for i, r in enumerate(full) if r["evidence_source"] == "go_transport")
        assert idx_first_go == n_pre_go
        assert all(r["evidence_source"] != "go_transport" for r in full[:n_pre_go])
        paged = []
        for off in range(0, len(full) + 10, 10):
            page = api.genes_by_metabolite(
                [_GOT_UREA], _GOT_MED4, limit=10, offset=off, conn=conn)
            assert page["total_matching"] == len(full)
            paged.extend(page["results"])
        assert [key(r) for r in paged] == [key(r) for r in full]
        assert len({key(r) for r in paged}) == len(full)

    def test_gbm_role_siderophore_altde1(self, conn):
        """Spec §7.3 (D12): 32 GO + TCDB direct (live; 96 pre-3a) rows."""
        r = api.genes_by_metabolite(
            [_GOT_SIDEROPHORE], _GOT_ALT, limit=500, conn=conn)
        go = _got_by_source(r["results"], "go_transport")
        tcdb = _got_tcdb_direct_rows(conn, _GOT_ALT, [_GOT_SIDEROPHORE])
        assert len(go) == 32
        assert len(_got_by_source(r["results"], "transport")) == tcdb["rows"]
        assert r["total_matching"] == 32 + tcdb["rows"]
        assert r["gene_count_total"] == len({x["locus_tag"] for x in r["results"]})
        assert r["transporter_count_total"] == tcdb["systems"]
        assert all(x["target_kind"] == "chemical_role" for x in r["results"])
        assert all(x["metabolite_id"] == _GOT_SIDEROPHORE for x in r["results"])
        row = next(x for x in go if x["locus_tag"] == "amad1_16875")
        assert row["go_term_id"] == "go:0015891"
        assert row["go_term_name"] == "siderophore transport"
        assert row["go_namespace"] == "biological_process"
        assert row["go_evidence"] == "curated"
        assert row["go_sources"] == ["ncbi"]
        assert not any("not a metabolite" in w for w in r["warnings"])
        assert r["not_found"]["metabolite_ids"] == []

    def test_gbm_mixed_role_and_metabolite_batch(self, conn):
        """Review Focus 2: both target kinds; 2 metabolism + TCDB direct
        (live; 169 pre-3a) + 32 GO."""
        r = api.genes_by_metabolite(
            [_GOT_SIDEROPHORE, _GOT_UREA], _GOT_ALT, limit=500, conn=conn)
        tcdb = _got_tcdb_direct_rows(
            conn, _GOT_ALT, [_GOT_SIDEROPHORE, _GOT_UREA])["rows"]
        assert r["total_matching"] == 2 + tcdb + 32
        assert len(_got_by_source(r["results"], "metabolism")) == 2
        assert len(_got_by_source(r["results"], "transport")) == tcdb
        assert len(_got_by_source(r["results"], "go_transport")) == 32
        assert {x["target_kind"] for x in r["results"]} == {
            "metabolite", "chemical_role"}

    def test_gbm_exclude_role_id(self, conn):
        """Review Focus 2: a role id in exclude_metabolite_ids drops its rows
        (metabolism 2 + TCDB direct urea rows (live; 73 pre-3a), GO 0)."""
        r = api.genes_by_metabolite(
            [_GOT_SIDEROPHORE, _GOT_UREA], _GOT_ALT,
            exclude_metabolite_ids=[_GOT_SIDEROPHORE], limit=500, conn=conn,
            evidence_sources=["metabolism", "transport", "go_transport"])
        tcdb = _got_tcdb_direct_rows(conn, _GOT_ALT, [_GOT_UREA])["rows"]
        assert r["total_matching"] == 2 + tcdb
        assert len(_got_by_source(r["results"], "go_transport")) == 0
        assert len(_got_by_source(r["results"], "transport")) == tcdb
        assert len(_got_by_source(r["results"], "metabolism")) == 2
        assert all(x["metabolite_id"] != _GOT_SIDEROPHORE for x in r["results"])

    def test_gbm_go_arm_empty_med4_siderophore(self, conn):
        """D13 / Review Focus 3: GO 0; TCDB direct rows read live (the pre-3a
        25 were all inherited 3.A.1 rows, gone with the direct gate);
        envelope keys present, no crash."""
        r = api.genes_by_metabolite(
            [_GOT_SIDEROPHORE], _GOT_MED4, limit=100, conn=conn)
        assert len(_got_by_source(r["results"], "go_transport")) == 0
        tcdb = _got_by_source(r["results"], "transport")
        live = _got_tcdb_direct_rows(conn, _GOT_MED4, [_GOT_SIDEROPHORE])["rows"]
        assert len(tcdb) == live
        assert {x["tcdb_route"] for x in tcdb} <= {"direct"}
        assert r["total_matching"] == live
        assert r["rows_by_go_term_depth"] == []
        for key in ("by_metabolite", "by_evidence_source", "top_genes",
                    "not_found", "not_matched", "warnings"):
            assert key in r

    def test_gbm_role_neurotransmitter_putida(self, conn):
        r = api.genes_by_metabolite(
            ["chebi.role:25512"], "Pseudomonas putida KT2440", limit=200,
            conn=conn)
        tcdb = _got_tcdb_direct_rows(
            conn, "Pseudomonas putida KT2440", ["chebi.role:25512"])["rows"]
        assert len(_got_by_source(r["results"], "go_transport")) == 5
        assert len(_got_by_source(r["results"], "transport")) == tcdb
        assert r["total_matching"] == 5 + tcdb
        assert any(
            "chebi.role:25512 (neurotransmitter) on the GO route is mostly "
            "bacterial NSS amino-acid transporters" in w
            for w in r["warnings"])

    def test_gbm_ancestors_respect_exclude(self, conn):
        """Review Focus 4: GO-only, MED4, 5 targets: 45 with ancestors, 37
        when the inherited-only target C01356 is excluded."""
        kw = dict(evidence_sources=["go_transport"], summary=True, conn=conn)
        base = api.genes_by_metabolite(
            _GOT_MED4_GBM_TARGETS, _GOT_MED4, go_include_ancestors=True, **kw)
        assert base["total_matching"] == 45
        assert base["rows_by_go_term_depth"] == [
            {"go_term_depth": 0, "count": 33}, {"go_term_depth": 1, "count": 12}]
        excl = api.genes_by_metabolite(
            _GOT_MED4_GBM_TARGETS, _GOT_MED4, go_include_ancestors=True,
            exclude_metabolite_ids=["kegg.compound:C01356"], **kw)
        assert excl["total_matching"] == 37
        assert excl["rows_by_go_term_depth"] == [
            {"go_term_depth": 0, "count": 32}, {"go_term_depth": 1, "count": 5}]
        assert all(
            m["metabolite_id"] != "kegg.compound:C01356"
            for m in excl["by_metabolite"])

    @pytest.mark.parametrize("kwargs,expected", [
        ({}, 33),
        ({"gene_categories": ["Transport"]}, 6),
        ({"metabolite_pathway_ids": ["kegg.pathway:ko02010"]}, 25),
        ({"exclude_metabolite_ids": ["kegg.compound:C00086"]}, 22),
    ])
    def test_gbm_shared_filters_change_go_arm(self, conn, kwargs, expected):
        """Spec §7.7: no shared filter is a no-op on the GO arm."""
        r = api.genes_by_metabolite(
            _GOT_MED4_GBM_TARGETS, _GOT_MED4, evidence_sources=["go_transport"],
            summary=True, conn=conn, **kwargs)
        assert r["total_matching"] == expected

    def test_gbm_excluded_target_without_node_warns(self, conn):
        """Review Focus 5: chebi:23906 has no node -> not_found AND warning."""
        r = api.genes_by_metabolite(["chebi:23906"], _GOT_MED4, conn=conn)
        assert "chebi:23906" in r["not_found"]["metabolite_ids"]
        assert any(
            "'chebi:23906' is excluded from both transport routes (TCDB and "
            "GO) by curation" in w for w in r["warnings"])

    @pytest.mark.parametrize("mid,metabolism_rows", [
        ("kegg.compound:C00080", 250),   # GO 0 + TCDB 0 + metabolism 250
    ])
    def test_gbm_excluded_target_with_node(self, conn, mid, metabolism_rows):
        r = api.genes_by_metabolite([mid], _GOT_MED4, limit=1, conn=conn)
        tcdb = _got_tcdb_direct_rows(conn, _GOT_MED4, [mid])["rows"]
        assert r["total_matching"] == metabolism_rows + tcdb
        go_count = {e["evidence_source"]: e["count"]
                    for e in r["by_evidence_source"]}.get("go_transport", 0)
        assert go_count == 0
        assert tcdb == 0  # H+ is a filtered TCDB substrate target too
        assert any(f"'{mid}' is excluded from both transport routes (TCDB "
                   "and GO) by curation" in w for w in r["warnings"])

    def test_gbm_excluded_warning_names_tcdb_without_go_arm(self, conn):
        r = api.genes_by_metabolite(
            ["kegg.compound:C00080"], _GOT_MED4, limit=1,
            evidence_sources=["metabolism", "transport"], conn=conn)
        curation = [w for w in r["warnings"] if "by curation" in w]
        assert curation == [
            "'kegg.compound:C00080' is excluded from the TCDB substrate route "
            "by curation (coupling ion or placeholder) — an empty TCDB answer "
            "is not biology."]

    def test_gbm_excluded_warning_silent_without_transport_arms(self, conn):
        r = api.genes_by_metabolite(
            ["kegg.compound:C00080"], _GOT_MED4, limit=1,
            evidence_sources=["metabolism"], conn=conn)
        assert not any("by curation" in w for w in r["warnings"])

    def test_gbm_role_with_no_edges_is_not_matched(self, conn):
        """D8: chebi.role:23357 has no edges anywhere -> not_matched."""
        r = api.genes_by_metabolite(
            ["chebi.role:23357"], _GOT_MED4, conn=conn)
        assert r["total_matching"] == 0
        assert "chebi.role:23357" in r["not_matched"]
        assert "chebi.role:23357" not in r["not_found"]["metabolite_ids"]

    def test_gbm_stereo_relative_counts_match_recall(self, conn):
        """Spec §7.9: C00025 -> relative C00302 (Glutamate); relative counts
        equal a re-call (include_ancestors threaded through)."""
        for anc in (False, True):
            r = api.genes_by_metabolite(
                ["kegg.compound:C00025"], _GOT_MED4,
                go_include_ancestors=anc, summary=True, conn=conn)
            rel = {x["metabolite_id"]: x
                   for x in r["stereo_relatives"]["kegg.compound:C00025"]}
            assert "kegg.compound:C00302" in rel
            recall = api.genes_by_metabolite(
                ["kegg.compound:C00302"], _GOT_MED4,
                go_include_ancestors=anc, summary=True, conn=conn)
            entry = recall["by_metabolite"][0]
            assert rel["kegg.compound:C00302"]["gene_count"] == entry["gene_count"]
        base = api.genes_by_metabolite(
            ["kegg.compound:C00302"], _GOT_MED4, summary=True, conn=conn)
        e = base["by_metabolite"][0]
        # GO 1 row; TCDB direct rows live (30 inherited 3.A.1 rows pre-3a)
        tcdb = _got_tcdb_direct_rows(conn, _GOT_MED4, ["kegg.compound:C00302"])
        assert e["go_transport_rows"] == 1
        assert e["rows"] == e["metabolism_rows"] + tcdb["rows"] + 1

    def test_gbm_response_model_validates(self, conn):
        from multiomics_explorer.mcp_server.tools import (
            GenesByMetaboliteResponse,
        )
        r = api.genes_by_metabolite(
            [_GOT_UREA], _GOT_MED4, limit=100, verbose=True, conn=conn)
        model = GenesByMetaboliteResponse(**r)
        go = [x for x in model.results if x.evidence_source == "go_transport"]
        assert len(go) == 11
        assert go[0].go_term_id is not None
        assert [(e.go_term_depth, e.count) for e in model.rows_by_go_term_depth] == [(0, 11)]


@pytest.mark.kg
class TestGoTransportMetabolitesByGene:
    def test_mbg_pmm0970_go_rows_after_tcdb(self, conn):
        """Spec §7.4: 4 TCDB then 2 GO; metabolite_count_total 3."""
        r = api.metabolites_by_gene(
            ["PMM0970"], _GOT_MED4, limit=50, conn=conn)
        rows = r["results"]
        assert [x["evidence_source"] for x in rows] == (
            ["transport"] * 4 + ["go_transport"] * 2)
        go = rows[4:]
        assert [x["go_term_id"] for x in go] == ["go:0033221", "go:0015840"]
        assert [x["go_namespace"] for x in go] == [
            "molecular_function", "biological_process"]
        assert all(x["metabolite_id"] == _GOT_UREA for x in go)
        assert all(x["go_term_depth"] == 0 for x in go)
        assert r["total_matching"] == 6
        assert r["metabolite_count_total"] == 3
        assert {e["evidence_source"]: e["count"]
                for e in r["by_evidence_source"]} == {
            "transport": 4, "go_transport": 2}

    def test_mbg_ancestors_pmm0970(self, conn):
        r = api.metabolites_by_gene(
            ["PMM0970"], _GOT_MED4, go_include_ancestors=True,
            evidence_sources=["go_transport"], conn=conn)
        assert r["total_matching"] == 3
        inh = [x for x in r["results"] if x["go_term_depth"] == 1]
        assert len(inh) == 1
        assert inh[0]["metabolite_id"] == "chebi:64708"
        assert inh[0]["go_term_id"] == "go:0015840"
        assert inh[0]["go_axiom_term_id"] == "go:0019755"
        assert inh[0]["go_axiom_term_name"] == "one-carbon compound transport"

    def test_mbg_ancestors_murj_lipid(self, conn):
        """Spec §7.2: PMM0261 ancestors -> one GO row, Lipid, depth 1;
        default call: 0 GO rows (TCDB direct rows live; 3 pre-3a)."""
        on = api.metabolites_by_gene(
            ["PMM0261"], _GOT_MED4, go_include_ancestors=True, conn=conn)
        go = _got_by_source(on["results"], "go_transport")
        assert len(go) == 1
        assert go[0]["metabolite_id"] == "kegg.compound:C01356"
        assert go[0]["go_term_id"] == "go:0034204"
        assert go[0]["go_term_depth"] == 1
        assert go[0]["go_axiom_term_id"] == "go:0006869"
        assert go[0]["go_axiom_term_name"] == "lipid transport"
        tcdb = _got_tcdb_direct_rows(conn, locus_tags=["PMM0261"])["rows"]
        assert on["total_matching"] == tcdb + 1
        off = api.metabolites_by_gene(["PMM0261"], _GOT_MED4, conn=conn)
        assert _got_by_source(off["results"], "go_transport") == []
        assert off["total_matching"] == tcdb
        assert off["rows_by_go_term_depth"] == []

    def test_mbg_ancestors_with_elements(self, conn):
        """Review Focus 4: metabolite_elements=['N'] drops role rows and
        formula-less inherited classes (spec §7.7)."""
        tags = _got_med4_go_genes(conn) + ["PMM0261"]
        kw = dict(evidence_sources=["go_transport"], limit=500, conn=conn)
        full = api.metabolites_by_gene(
            tags, _GOT_MED4, go_include_ancestors=True, **kw)
        assert full["total_matching"] == 206  # 199 → 206 2026-10-26T04:21Z: GO:0071806 → Protein
        assert any(x["target_kind"] == "chemical_role" for x in full["results"])
        n = api.metabolites_by_gene(
            tags, _GOT_MED4, go_include_ancestors=True,
            metabolite_elements=["N"], **kw)
        assert n["total_matching"] == 53
        assert all(x["target_kind"] == "metabolite" for x in n["results"])
        assert n["rows_by_go_term_depth"] == [
            {"go_term_depth": 0, "count": 45}, {"go_term_depth": 1, "count": 8}]
        direct = api.metabolites_by_gene(
            tags, _GOT_MED4, metabolite_elements=["N"], **kw)
        assert direct["total_matching"] == 45

    @pytest.mark.parametrize("kwargs,expected", [
        ({}, 128),  # +2 each 2026-10-26T04:21Z: GO:0071806 → Protein
        ({"gene_categories": ["Transport"]}, 40),
        ({"metabolite_pathway_ids": ["kegg.pathway:ko02010"]}, 58),
        ({"exclude_metabolite_ids": ["kegg.compound:C00086"]}, 117),
        ({"metabolite_elements": ["N"]}, 45),
        ({"metabolite_ids": ["kegg.compound:C00086"]}, 11),
    ])
    def test_mbg_shared_filters_change_go_arm(self, conn, kwargs, expected):
        tags = _got_med4_go_genes(conn) + ["PMM0261"]
        r = api.metabolites_by_gene(
            tags, _GOT_MED4, evidence_sources=["go_transport"], summary=True,
            conn=conn, **kwargs)
        assert r["total_matching"] == expected

    def test_mbg_tcdb_role_rows_move_tolc_rollups(self, conn):
        """Spec §7.3 (re-anchored by the TCDB cleanup): TCDB role rows count
        in the transport arm. PMM0097 tolC has no direct system post-3a, so
        its default arm is empty; with the family walk on, role targets
        (target_kind='chemical_role') appear as family rows and the
        route / transporter rollups follow the rows."""
        off = api.metabolites_by_gene(
            ["PMM0097"], _GOT_MED4, evidence_sources=["transport"],
            summary=True, conn=conn)
        assert off["total_matching"] == _got_tcdb_direct_rows(
            conn, locus_tags=["PMM0097"])["rows"]
        on = api.metabolites_by_gene(
            ["PMM0097"], _GOT_MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=5000, conn=conn)
        assert not on["truncated"]
        routes = {e["tcdb_route"]: e["count"] for e in on["by_tcdb_route"]}
        assert sum(routes.values()) == on["total_matching"] == len(on["results"])
        assert any(x["target_kind"] == "chemical_role" for x in on["results"])
        assert on["transporter_count_total"] == len(
            {x["tcdb_family_id"] for x in on["results"]})

    def test_mbg_ancestors_gene_without_ancestors_identical(self, conn):
        """PMM0085 (ktrA): ancestors add nothing."""
        a = api.metabolites_by_gene(["PMM0085"], _GOT_MED4, limit=500, conn=conn)
        b = api.metabolites_by_gene(
            ["PMM0085"], _GOT_MED4, go_include_ancestors=True, limit=500,
            conn=conn)
        assert a["results"] == b["results"]

    def test_mbg_paging_continuity(self, conn):
        """Spec §7.8: PMM0970 + PMM0261 with ancestors, limit=3; the first GO
        row follows every TCDB direct row (live count; 7 pre-3a)."""
        kw = dict(go_include_ancestors=True, conn=conn)
        full = api.metabolites_by_gene(
            ["PMM0970", "PMM0261"], _GOT_MED4, limit=50, **kw)["results"]
        n_tcdb = _got_tcdb_direct_rows(
            conn, locus_tags=["PMM0970", "PMM0261"])["rows"]
        assert len(full) == n_tcdb + 4
        assert next(i for i, r in enumerate(full)
                    if r["evidence_source"] == "go_transport") == n_tcdb
        paged = []
        for off in range(0, len(full) + 3, 3):
            paged.extend(api.metabolites_by_gene(
                ["PMM0970", "PMM0261"], _GOT_MED4, limit=3, offset=off,
                **kw)["results"])
        assert paged == full

    def test_mbg_response_model_validates(self, conn):
        from multiomics_explorer.mcp_server.tools import (
            MetabolitesByGeneResponse,
        )
        r = api.metabolites_by_gene(
            ["PMM0970"], _GOT_MED4, limit=50, verbose=True, conn=conn)
        model = MetabolitesByGeneResponse(**r)
        assert [(e.go_term_depth, e.count) for e in model.rows_by_go_term_depth] == [(0, 2)]
        assert model.results[-1].go_chebi_ids == ["CHEBI:16199"]


@pytest.mark.kg
class TestGoTransportPassThroughs:
    def test_gene_overview_med4_go_transport_tag(self, conn):
        """Spec §7.6: 59 MED4 genes tagged go_transport. GO-only genes were
        PMM0533 / PMM0866 pre-3a; under the TCDB direct gate every
        go_transport gene without a direct TCDB system and no reaction is
        GO-only too (family-only TCDB genes lost the 'transport' tag)."""
        tags = [r["locus_tag"] for r in conn.execute_query(
            "MATCH (g:Gene {organism_name: $o}) RETURN g.locus_tag AS locus_tag",
            o=_GOT_MED4)]
        r = api.gene_overview(tags, verbose=False, limit=len(tags), conn=conn)
        tagged = [x for x in r["results"]
                  if "go_transport" in (x.get("evidence_sources") or [])]
        assert len(tagged) == 59
        only = {
            x["locus_tag"] for x in tagged if x["evidence_sources"] == ["go_transport"]}
        assert {"PMM0533", "PMM0866"} <= only
        expected_only = {
            x["locus_tag"] for x in tagged
            if (x.get("transported_metabolite_count") or 0) == 0
            and (x.get("reaction_count") or 0) == 0
            and "metabolomics" not in x["evidence_sources"]}
        assert only == expected_only
        pmm0970 = next(x for x in r["results"] if x["locus_tag"] == "PMM0970")
        assert "go_transport" in pmm0970["evidence_sources"]

    def test_gene_overview_has_chemistry_widened(self, conn):
        """Spec §7.6: has_chemistry counts go_transport genes too (786 -> 788
        pre-3a). The TCDB direct gate narrowed the 'transport' route, so the
        envelope is checked against the rows rather than re-pinned: every gene
        with any of metabolism / transport / go_transport, and the two GO-only
        genes are in it."""
        tags = [r["locus_tag"] for r in conn.execute_query(
            "MATCH (g:Gene {organism_name: $o}) RETURN g.locus_tag AS locus_tag",
            o=_GOT_MED4)]
        r = api.gene_overview(tags, summary=True, conn=conn)
        rows = api.gene_overview(tags, limit=len(tags), conn=conn)["results"]
        chem = {x["locus_tag"] for x in rows
                if {"metabolism", "transport", "go_transport"}
                & set(x.get("evidence_sources") or [])}
        assert r["has_chemistry"] == len(chem)
        no_go = {x["locus_tag"] for x in rows
                 if {"metabolism", "transport"}
                 & set(x.get("evidence_sources") or [])}
        assert r["has_chemistry"] > len(no_go)

    def test_list_metabolites_med4_union(self, conn):
        """Spec §7.6: organism filter unions go_transport_organism_names."""
        r = api.list_metabolites(
            organism_names=[_GOT_MED4], summary=True, conn=conn)
        assert r["total_matching"] == 1089  # 1891 → 1092 2026-10-24T17:33Z: MED4 transport arm now direct systems only → 1089 2026-10-26T04:21Z: TCDB substrate filter
        top = {o["organism_name"]: o["count"] for o in r["top_organisms"]}
        assert top[_GOT_MED4] == 1089

    def test_list_metabolites_go_transport_source(self, conn):
        r = api.list_metabolites(
            evidence_sources=["go_transport"], summary=True, conn=conn)
        assert r["total_matching"] == 218  # → 218 2026-10-28T05:04Z: Ford 2021 strains ← 208 → 212 2026-10-26T04:21Z: Protein + TCDB review re-keys
        both = api.list_metabolites(
            evidence_sources=["go_transport"], organism_names=[_GOT_MED4],
            summary=True, conn=conn)
        assert both["total_matching"] == 100  # 98 → 100 2026-10-28: two MED4-reached metabolites gained the go_transport tag from Ford 2021 strains ← 165 → 98 2026-10-24T17:33Z: MED4 transport arm now direct systems only

    def test_list_metabolites_rows_carry_go_organisms(self, conn):
        r = api.list_metabolites(
            metabolite_ids=[_GOT_UREA], organism_names=[_GOT_MED4], conn=conn)
        row = r["results"][0]
        assert "go_transport_organism_names" in row
        assert _GOT_MED4 in row["go_transport_organism_names"]
        assert row["go_transport_organism_count"] >= 1

    def test_kg_release_info_carries_excluded_targets(self, conn):
        r = api.kg_release_info(conn)
        excluded = r["kg"]["go_transport_excluded_targets"]
        assert len(excluded) == 12  # 13 → 12 2026-10-26T04:21Z: Na+ now chebi:29101
        assert "kegg.compound:C00080" in excluded
        assert "chebi:23906" in excluded
        tcdb = r["kg"]["tcdb_substrate_excluded_targets"]
        assert set(excluded) <= set(tcdb)
        assert "chebi:25367" in tcdb  # molecule: TCDB-only placeholder

    def test_kg_schema_go_edge_descriptions(self, conn):
        r = api.kg_schema(conn=conn)
        rels = r["relationships"]
        for name in (
            "Molecular_function_transports_metabolite",
            "Biological_process_transports_metabolite",
            "Molecular_function_transports_chemical_role",
            "Biological_process_transports_chemical_role",
        ):
            assert name in rels
            assert rels[name]["description"]
        assert rels["Molecular_function_transports_metabolite"][
            "description"].startswith("GO defines this molecular-function term")
        assert "Tcdb_family_transports_chemical_role" in rels


@pytest.mark.kg
class TestTcdbDisplayNameAndStructureKind:
    """TCDB names shown as display_name; gene↔metabolite rows carry
    metabolite_structure_kind (spec tcdb-display-name-and-structure-kind)."""

    _MED4 = "Prochlorococcus MED4"

    def test_gene_ontology_terms_unnamed_subfamily_reads_borrowed_name(self, conn):
        out = api.gene_ontology_terms(
            ["PMM0010"], organism=self._MED4, ontology="tcdb", conn=conn)
        names = {r["term_id"]: r["term_name"] for r in out["results"]}
        assert names["tcdb:3.A.5.7"] == (
            "The General Secretory Pathway (Sec) Family — subfamily 3.A.5.7")
        # No TCDB row shows a bare TCID as its name.
        assert all(n != tid.removeprefix("tcdb:") for tid, n in names.items())

    def test_genes_by_ontology_rows_use_display_name(self, conn):
        out = api.genes_by_ontology(
            ontology="tcdb", organism=self._MED4, term_ids=["tcdb:3.A.5.7"],
            min_gene_set_size=1, conn=conn)
        assert out["results"]
        assert {r["term_name"] for r in out["results"]
                if r["term_id"] == "tcdb:3.A.5.7"} == {
            "The General Secretory Pathway (Sec) Family — subfamily 3.A.5.7"}

    def test_ontology_term_details_children_use_display_name(self, conn):
        out = api.ontology_term_details(["tcdb:3.A.5"], conn=conn)
        row = out["results"][0]
        assert row["name"] == "The General Secretory Pathway (Sec) Family"
        assert row["children"]
        assert all(not c["name"].startswith(c["id"].removeprefix("tcdb:"))
                   for c in row["children"])

    def test_non_tcdb_names_unchanged(self, conn):
        out = api.ontology_term_details(["go:0006260"], conn=conn)
        assert out["results"][0]["name"] == "DNA replication"

    def test_genes_by_metabolite_rows_carry_structure_kind(self, conn):
        # Peptide (C00012) is a TCDB class substrate; Urea (C00086) a molecule.
        out = api.genes_by_metabolite(
            ["kegg.compound:C00012", "kegg.compound:C00086"],
            organism=self._MED4, conn=conn)
        kinds = {r["metabolite_id"]: r.get("metabolite_structure_kind")
                 for r in out["results"]}
        assert kinds.get("kegg.compound:C00086") == "defined"
        assert kinds.get("kegg.compound:C00012") == "generic"
        assert all(r.get("metabolite_structure_kind") in
                   {"defined", "generic", "polymer"}
                   for r in out["results"]
                   if r.get("target_kind") != "chemical_role")
