"""P1: Integration tests for MCP tool logic against live Neo4j.

These tests exercise the tool-level logic (query building + result handling)
without the MCP transport layer. They use the shared `conn` fixture from conftest.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP

from multiomics_explorer.mcp_server.tools import register_tools
from multiomics_explorer.kg.queries_lib import (
    build_gene_stub,
    build_gene_details,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_genes_by_homolog_group,
    build_genes_by_homolog_group_summary,
    build_list_experiments,
    build_list_experiments_summary,
    build_list_organisms,
    build_list_publications,
    build_list_publications_summary,
    build_resolve_gene,
    build_genes_by_function,
    build_search_homolog_groups,
    build_search_homolog_groups_summary,
)
from multiomics_explorer.api import functions as api
from multiomics_explorer.api.functions import _WRITE_KEYWORDS


@pytest.mark.kg
class TestKgSchema:
    def test_returns_nodes_and_relationships(self, conn):
        result = api.kg_schema(conn=conn)
        assert "Gene" in result["nodes"]
        assert len(result["relationships"]) > 0

    def test_gene_node_has_properties(self, conn):
        result = api.kg_schema(conn=conn)
        assert "properties" in result["nodes"]["Gene"]


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
            assert "metabolite_count" in row
            assert row["reaction_count"] > 0
            assert row["metabolite_count"] > 0

    def test_by_metabolic_capability_top_organisms(self, conn):
        """by_metabolic_capability is populated with top organisms in summary mode,
        sorted desc by metabolite_count, excluding zero-chemistry organisms."""
        result = api.list_organisms(summary=True, conn=conn)
        cap = result["by_metabolic_capability"]
        assert len(cap) > 0 and len(cap) <= 10
        # Sorted descending by metabolite_count
        metabolite_counts = [r["metabolite_count"] for r in cap]
        assert metabolite_counts == sorted(metabolite_counts, reverse=True)
        # All entries have non-zero chemistry
        for entry in cap:
            assert entry["metabolite_count"] > 0 or entry["reaction_count"] > 0


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
                r.get("coculture_partner") and "MED4" in r.get("coculture_partner", "")
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
        """compartment='vesicle' filter returns exactly 11 experiments (pinned baseline)."""
        result = api.list_experiments(compartment="vesicle", summary=True, conn=conn)
        assert result["total_matching"] == 11

    def test_compartment_exoproteome_returns_8(self, conn):
        """compartment='exoproteome' filter returns exactly 8 experiments (pinned baseline)."""
        result = api.list_experiments(compartment="exoproteome", summary=True, conn=conn)
        assert result["total_matching"] == 8

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
                "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_proteomics_axenic"
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
            f"Expected phase-varying TPs on axenic proteomics, got: {phases}"
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
    def test_med4_all_ontologies_cyanorak_l1_rank1_among_hierarchical(self, conn):
        from multiomics_explorer.api.functions import ontology_landscape
        # informative_only=False preserves the pre-F1-surface rank ordering
        # (cyanorak_role L1 has 5 uninformative-flagged terms / ~16.5% of
        # gene-pairs that the default-on filter would drop).
        result = ontology_landscape(
            organism="MED4", limit=None, informative_only=False, conn=conn,
        )
        hierarchical = [
            r for r in result["results"]
            if r["n_levels_in_ontology"] > 1
        ]
        assert hierarchical, "expected at least one hierarchical row"
        top_hier = min(hierarchical, key=lambda r: r["relevance_rank"])
        assert top_hier["ontology_type"] == "cyanorak_role"
        assert top_hier["level"] == 1, (
            f"expected cyanorak_role L1, got L{top_hier['level']}"
        )

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


@pytest.mark.kg
class TestListDerivedMetrics:
    """Live-KG integration tests for list_derived_metrics."""

    def test_no_filters_13_dms(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(conn=conn, limit=None)
        assert out["total_entries"] == 61
        assert out["total_matching"] == 61
        assert len(out["results"]) == 61

    def test_value_kind_numeric_6(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="numeric", conn=conn, limit=None)
        assert out["total_matching"] == 35
        assert all(r["value_kind"] == "numeric" for r in out["results"])
        compartments = {r["compartment"] for r in out["results"]}
        assert compartments == {"whole_cell", "vesicle", "exoproteome"}

    def test_value_kind_boolean_6(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="boolean", conn=conn, limit=None)
        assert out["total_matching"] == 18
        organisms = {r["organism_name"] for r in out["results"]}
        assert "Prochlorococcus NATL2A" in organisms
        assert "Alteromonas macleodii MIT1002" in organisms

    def test_value_kind_categorical_1(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="categorical", conn=conn, limit=None)
        assert out["total_matching"] == 8
        metric_types = {r["metric_type"] for r in out["results"]}
        assert "darkness_survival_class" in metric_types
        assert all(r["allowed_categories"] is not None for r in out["results"])

    def test_rankable_true_4(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(rankable=True, conn=conn, limit=None)
        assert out["total_matching"] == 29
        assert all(r["rankable"] is True for r in out["results"])

    def test_rankable_false_9(self, conn):
        """Sanity-checks bool→'false' string coercion path."""
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(rankable=False, conn=conn, limit=None)
        assert out["total_matching"] == 32
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

    def test_organism_short_code(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(organism="MED4", conn=conn, limit=None)
        assert out["total_matching"] == 17
        assert all(r["organism_name"] == "Prochlorococcus MED4" for r in out["results"])

    def test_organism_full_name(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            organism="Prochlorococcus NATL2A", conn=conn, limit=None)
        assert out["total_matching"] == 5

    def test_organism_alteromonas(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(organism="MIT1002", conn=conn, limit=None)
        assert out["total_matching"] == 5

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
            publication_doi=["10.1128/mSystems.00040-18"], conn=conn, limit=None)
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
        assert len(out["by_organism"]) == 11

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


def _ctx_with_conn(conn):
    """Build an AsyncMock Context with the real GraphConnection injected."""
    ctx = AsyncMock()
    ctx.request_context.lifespan_context.conn = conn
    return ctx


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
    async def test_pmm1714_all_three_kinds(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], limit=20)
        assert response.total_matching == 11
        assert response.total_derived_metrics == 11
        assert response.genes_with_metrics == 1
        assert response.returned == 11
        kinds = {r.value_kind for r in response.results}
        assert kinds == {"numeric", "boolean", "categorical"}
        # Polymorphic value typing
        for r in response.results:
            if r.value_kind == "numeric":
                assert isinstance(r.value, float)
            elif r.value_kind == "boolean":
                assert r.value in ("true", "false")
            elif r.value_kind == "categorical":
                assert isinstance(r.value, str)

    @pytest.mark.asyncio
    async def test_pmm0001_diel_only(self, tool_fns, conn):
        # value_kind='numeric' filters out the gene-level categorical DMs
        # (expression_level_class, pangenome_membership) that aren't diel-related.
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM0001"], value_kind="numeric", limit=20)
        assert response.total_matching == 6
        assert all(r.value_kind == "numeric" for r in response.results)
        # 4 rankable (damping_ratio, diel_amp_*, protein_transcript_lag),
        # 2 non-rankable (peak_time_*)
        rankable_count = sum(1 for r in response.results if r.rankable)
        assert rankable_count == 4
        # Sparse extras null on non-rankable rows
        for r in response.results:
            if not r.rankable:
                assert r.rank_by_metric is None
                assert r.metric_percentile is None
                assert r.metric_bucket is None

    @pytest.mark.asyncio
    async def test_value_kind_filter_routes(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], value_kind="boolean")
        assert response.total_matching == 1
        # metric_type is verbose-only; assert against compact fields instead
        assert response.results[0].derived_metric_id.endswith(
            "vesicle_proteome_member")
        assert response.results[0].value == "true"
        assert response.results[0].value_kind == "boolean"

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
    async def test_mixed_input_with_filter(self, tool_fns, conn):
        """All 3 diagnostic buckets within single-organism scope."""
        ctx = _ctx_with_conn(conn)
        # NOTE: PMN2A_2128 (NATL2A) cannot be combined with MED4 locus_tags —
        # single-organism enforcement is by design. Use PMM0002 (MED4 gene
        # with no DM signal) for the not_matched bucket instead.
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714", "PMM_FAKE", "PMM0002"],
            value_kind="numeric", limit=20)
        assert response.total_matching == 7  # PMM1714 numeric only
        assert response.genes_with_metrics == 1
        assert response.genes_without_metrics == 1  # PMM0002
        assert response.not_found == ["PMM_FAKE"]
        assert response.not_matched == ["PMM0002"]

    @pytest.mark.asyncio
    async def test_compartment_filter(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], compartment="vesicle", limit=20)
        assert response.total_matching == 3  # boolean + categorical + numeric Biller 2014

    @pytest.mark.asyncio
    async def test_publication_doi_filter(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"],
            publication_doi=["10.1371/journal.pone.0043432"], limit=20)
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
    async def test_by_metric_disambiguates(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], summary=True)
        assert len(response.by_metric) == 11  # one per DM touching the gene
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
    async def test_truncation(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], limit=2)
        assert response.returned == 2
        assert response.truncated is True
        assert response.total_matching == 11


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
            ctx, metric_types=["damping_ratio"], bucket=["top_decile"],
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
            ctx, metric_types=["damping_ratio"], bucket=["top_decile"],
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
            bucket=["top_decile"], limit=50)
        # damping_ratio survives, peak_time_protein_h soft-excluded
        assert response.total_matching == 32
        assert len(response.excluded_derived_metrics) == 1
        excluded = response.excluded_derived_metrics[0]
        assert excluded.derived_metric_id.endswith("peak_time_protein_h")
        assert excluded.rankable is False
        assert "bucket" in excluded.reason
        assert len(response.warnings) == 1

    def test_all_non_rankable_hard_fail(self, conn):
        """All-non-rankable + bucket → api raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            api.genes_by_numeric_metric(
                metric_types=["peak_time_transcript_h"],
                bucket=["top_decile"], conn=conn)
        msg = str(exc_info.value)
        assert "rankable=False" in msg or "non-rankable" in msg
        assert "bucket" in msg

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
    async def test_cross_organism_no_scope(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["cell_abundance_biovolume_normalized"],
            bucket=["top_quartile"], limit=10)
        assert response.total_matching == 308
        assert len(response.by_organism) == 2
        # 152 MIT9312 + 156 MIT9313 = 308
        org_counts = {o.organism_name: o.count for o in response.by_organism}
        # match by substring (organism_name is full e.g. "Prochlorococcus MIT9312")
        mit9312_hits = [c for n, c in org_counts.items() if "MIT9312" in n]
        mit9313_hits = [c for n, c in org_counts.items() if "MIT9313" in n]
        assert mit9312_hits == [152]
        assert mit9313_hits == [156]
        assert len(response.by_metric) == 2
        assert response.not_matched_organism is None

    @pytest.mark.asyncio
    async def test_cross_organism_with_scope(self, tool_fns, conn):
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_numeric_metric"](
            ctx, metric_types=["cell_abundance_biovolume_normalized"],
            bucket=["top_quartile"], organism="MIT9313", limit=10)
        assert response.total_matching == 156
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
            ctx, metric_types=["damping_ratio"], bucket=["top_decile"],
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
            ctx, metric_types=["damping_ratio"], bucket=["top_decile"],
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
    async def test_vesicle_proteome_cross_organism(self, tool_fns, conn):
        """Happy path: 32 MED4 + 26 MIT9313 = 58 vesicle-proteome members."""
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_boolean_metric"](
            ctx, metric_types=["vesicle_proteome_member"], limit=200)
        assert response.total_matching == 58
        assert response.total_genes == 58
        # Cross-organism: by_organism shows both strains
        org_counts = {o.organism_name: o.count for o in response.by_organism}
        med4_hits = [c for n, c in org_counts.items() if "MED4" in n]
        mit9313_hits = [c for n, c in org_counts.items() if "MIT9313" in n]
        assert med4_hits == [32]
        assert mit9313_hits == [26]
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
            type(response.by_value[0])(value="true", count=58)
        ] or all(bv.value == "true" for bv in response.by_value)

    @pytest.mark.asyncio
    async def test_flag_false_zero_rows(self, tool_fns, conn):
        """flag=False → 0 rows (positive-only KG storage today).

        With the edge-level filter active, by_metric is necessarily empty
        (no surviving 'false' edges). The "dm_false_count echoes 0" signal
        is verified separately in the no-flag-filter test above (same DMs).
        """
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_boolean_metric"](
            ctx, metric_types=["vesicle_proteome_member"], flag=False, limit=10)
        assert response.total_matching == 0
        assert response.returned == 0
        # All `r.value='false'` filtered out → no DMs contribute rows
        assert response.by_metric == []
        # excluded_derived_metrics / warnings always [] for boolean
        assert response.excluded_derived_metrics == []
        assert response.warnings == []

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
    async def test_kind_mismatch_surfaces_as_not_found_ids(self, tool_fns, conn):
        """Numeric DM ID passed to boolean tool → not_found_ids, no raise."""
        numeric_dm_id = (
            "derived_metric:journal.pone.0043432:"
            "table_s2_waldbauer_diel_metrics:damping_ratio"
        )
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_boolean_metric"](
            ctx, derived_metric_ids=[numeric_dm_id], limit=5)
        assert response.total_matching == 0
        assert response.results == []
        assert response.not_found_ids == [numeric_dm_id]


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
    async def test_kind_mismatch_surfaces_as_not_found_ids(self, tool_fns, conn):
        """Numeric DM ID passed to categorical tool → not_found_ids, no raise."""
        numeric_dm_id = (
            "derived_metric:journal.pone.0043432:"
            "table_s2_waldbauer_diel_metrics:damping_ratio"
        )
        ctx = _ctx_with_conn(conn)
        response = await tool_fns["genes_by_categorical_metric"](
            ctx, derived_metric_ids=[numeric_dm_id], limit=5)
        assert response.total_matching == 0
        assert response.results == []
        assert response.not_found_ids == [numeric_dm_id]

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

    def test_no_filters_returns_all(self, conn):
        """Unfiltered query reports 3,035 total Metabolite nodes."""
        result = api.list_metabolites(conn=conn)
        assert result["total_matching"] == 3035

    def test_elements_n_filter(self, conn):
        """N-bearing metabolites: 1,566 total."""
        result = api.list_metabolites(elements=["N"], conn=conn)
        assert result["total_matching"] == 1566

    def test_elements_n_and_p_filter(self, conn):
        """Multi-element AND filter (must contain both N and P): 557."""
        result = api.list_metabolites(elements=["N", "P"], conn=conn)
        assert result["total_matching"] == 557

    def test_organism_plus_elements_filter(self, conn):
        """MED4 + N elements (the canonical N-source primitive): 804."""
        result = api.list_metabolites(
            organism_names=["Prochlorococcus MED4"],
            elements=["N"],
            conn=conn,
        )
        assert result["total_matching"] == 804

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
        """Lucene search by name returns ranked rows with `score` field."""
        result = api.list_metabolites(search="glucose", conn=conn)
        assert len(result["results"]) >= 1
        assert "score" in result["results"][0]

    def test_evidence_sources_transport_filter(self, conn):
        """transport-only evidence filter: 1,097 metabolites."""
        result = api.list_metabolites(
            evidence_sources=["transport"], conn=conn,
        )
        assert result["total_matching"] == 1097

    def test_summary_mode_empty_results_envelope_populated(self, conn):
        """summary=True returns no result rows but envelope is populated."""
        result = api.list_metabolites(summary=True, conn=conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] == 3035
        # Envelope rollups present (lists, possibly empty but typed)
        assert isinstance(result["top_organisms"], list)
        assert isinstance(result["top_pathways"], list)
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
        """Urea × MED4: both arms exercised, sc > fi, warning DOES NOT fire.

        Pins the spec § Live-KG state snapshot probes (verified 2026-05-03):
        total_matching=23, gene_count_total=18, metabolism_rows=4,
        transport_substrate_confirmed_rows=10, transport_family_inferred_rows=9.
        """
        from multiomics_explorer.mcp_server.tools import (
            GenesByMetaboliteResponse,
        )

        result = api.genes_by_metabolite(
            metabolite_ids=["kegg.compound:C00086"],
            organism="Prochlorococcus MED4",
            conn=conn,
        )
        model = GenesByMetaboliteResponse(**result)
        assert model.total_matching == 23
        assert model.gene_count_total == 18
        urea_row = next(
            r for r in model.by_metabolite
            if r.metabolite_id == "kegg.compound:C00086"
        )
        assert urea_row.metabolism_rows == 4
        assert urea_row.transport_substrate_confirmed_rows == 10
        assert urea_row.transport_family_inferred_rows == 9
        assert model.warnings == []

    def test_nitrite_med4_transport_only_warning_fires(self, conn):
        """Nitrite × MED4: transport-only, fi > sc, auto-warning fires.

        Pins spec smoke 2: total_matching=14, no metabolism rows,
        substrate_confirmed=5, family_inferred=9, family-inferred-dominance
        warning present.
        """
        from multiomics_explorer.mcp_server.tools import (
            GenesByMetaboliteResponse,
        )

        result = api.genes_by_metabolite(
            metabolite_ids=["kegg.compound:C00088"],
            organism="Prochlorococcus MED4",
            conn=conn,
        )
        model = GenesByMetaboliteResponse(**result)
        assert model.total_matching == 14
        es_counts = {r.evidence_source: r.count for r in model.by_evidence_source}
        assert "metabolism" not in es_counts
        assert es_counts.get("transport") == 14
        tc_counts = {
            r.transport_confidence: r.count
            for r in model.by_transport_confidence
        }
        assert tc_counts == {"substrate_confirmed": 5, "family_inferred": 9}
        assert any("family_inferred" in w for w in model.warnings)
