"""Live two-state invariants (KG hand-off 2026-08-28, HO-001).

For every boolean filter that maps onto a two-state KG string, the tool's
True-slice + False-slice must equal its unfiltered slice, and both slices
must be non-empty where the KG carries both states. A stale Cypher literal
makes one side read 0 and the sum fail — the failure mode this guards
against is silent, so these run through the api layer, not raw Cypher.
"""
from __future__ import annotations

import pytest

from multiomics_explorer.api import functions as api

pytestmark = pytest.mark.kg

_MSYSTEMS_FLAGS = (
    "metabolite_assay:msystems.01261-22:presence_flags_table_s2:"
    "presence_flag_intracellular"
)


def _split(fn, key, **kw):
    both = fn(**kw)[key]
    yes = fn(**{**kw, "_flag": True})
    return both, yes


def test_experiments_time_course_partition(conn):
    allx = api.list_experiments(limit=1000, conn=conn)
    tc = api.list_experiments(time_course_only=True, limit=1000, conn=conn)
    # api coerces the KG literal to bool for this tool.
    vals = {r["is_time_course"] for r in allx["results"]}
    assert vals == {True, False}
    n_tc = sum(r["is_time_course"] is True for r in allx["results"])
    assert tc["total_matching"] == n_tc > 0
    assert all(r["is_time_course"] is True for r in tc["results"])


def test_derived_metrics_rankable_and_p_value_partition(conn):
    allx = api.list_derived_metrics(limit=1000, conn=conn)
    yes = api.list_derived_metrics(rankable=True, limit=1000, conn=conn)
    no = api.list_derived_metrics(rankable=False, limit=1000, conn=conn)
    assert yes["total_matching"] > 0 and no["total_matching"] > 0
    assert yes["total_matching"] + no["total_matching"] == allx["total_matching"]
    assert all(r["rankable"] is True for r in yes["results"])
    assert all(r["rankable"] is False for r in no["results"])
    # has_p_value moved behind verbose on list_derived_metrics compact rows
    # (llm-review 2b.2 Task 5).
    p_yes = api.list_derived_metrics(has_p_value=True, limit=1000, conn=conn)
    p_no = api.list_derived_metrics(
        has_p_value=False, verbose=True, limit=1000, conn=conn)
    assert p_yes["total_matching"] + p_no["total_matching"] == allx["total_matching"]
    assert all(r["has_p_value"] is False for r in p_no["results"])


def test_metabolite_assays_rankable_partition(conn):
    allx = api.list_metabolite_assays(limit=1000, conn=conn)
    yes = api.list_metabolite_assays(rankable=True, limit=1000, conn=conn)
    no = api.list_metabolite_assays(rankable=False, limit=1000, conn=conn)
    assert yes["total_matching"] > 0 and no["total_matching"] > 0
    assert yes["total_matching"] + no["total_matching"] == allx["total_matching"]
    assert all(r["rankable"] is True for r in yes["results"])
    assert all(r["rankable"] is False for r in no["results"])


def test_boolean_dm_flag_partition(conn):
    dms = api.list_derived_metrics(value_kind="boolean", limit=1000, conn=conn)
    ids = [r["derived_metric_id"] for r in dms["results"]]
    assert ids
    allx = api.genes_by_boolean_metric(derived_metric_ids=ids, summary=True, conn=conn)
    yes = api.genes_by_boolean_metric(derived_metric_ids=ids, flag_value=True, summary=True, conn=conn)
    no = api.genes_by_boolean_metric(derived_metric_ids=ids, flag_value=False, summary=True, conn=conn)
    assert yes["total_matching"] > 0 and no["total_matching"] > 0  # 11/27 DMs store not_flagged
    assert yes["total_matching"] + no["total_matching"] == allx["total_matching"]
    assert {bv["value"] for bv in allx["by_value"]} == {"flagged", "not_flagged"}
    assert {bv["value"] for bv in yes["by_value"]} == {"flagged"}
    assert {bv["value"] for bv in no["by_value"]} == {"not_flagged"}
    assert sum(bm["false_count"] for bm in no["by_metric"]) == no["total_matching"]


def test_metabolite_flags_partition(conn):
    kw = dict(assay_ids=[_MSYSTEMS_FLAGS], limit=1000, conn=conn)
    allx = api.metabolites_by_flags_assay(**kw)
    yes = api.metabolites_by_flags_assay(flag_value=True, **kw)
    no = api.metabolites_by_flags_assay(flag_value=False, **kw)
    assert yes["total_matching"] > 0 and no["total_matching"] > 0
    assert yes["total_matching"] + no["total_matching"] == allx["total_matching"]
    assert all(r["flag_value"] is True for r in yes["results"])
    assert all(r["flag_value"] is False for r in no["results"])
    by_value = {bv["flag_value"]: bv["count"] for bv in allx["by_value"]}
    assert by_value == {True: yes["total_matching"], False: no["total_matching"]}
    # Sort key: detected rows first (coerced bool DESC, not the raw literal).
    flags = [r["flag_value"] for r in allx["results"]]
    assert flags == sorted(flags, reverse=True)


def test_assays_by_metabolite_flag_rollup_is_boolean(conn):
    # PEP: has boolean-arm evidence on the msystems flags assay.
    res = api.assays_by_metabolite(
        metabolite_ids=["kegg.compound:C00074"], evidence_kind="flags",
        limit=100, conn=conn)
    assert res["total_matching"] > 0
    assert set(res["by_flag_value"][0].keys()) >= {"flag_value", "count"}
    assert {bv["flag_value"] for bv in res["by_flag_value"]} <= {True, False}
    assert all(isinstance(r["flag_value"], bool) for r in res["results"])


def test_no_tested_absent_row_carries_a_rank(conn):
    # llm-review 2b.1: a tested-absent row (`detection_status='not_detected'`)
    # can tie into a high metric_bucket / metric_percentile purely from the
    # raw-zero coincidence (many numeric edges are zero) — those columns
    # must be nulled for display on both the numeric drill-down and the
    # cross-arm reverse lookup, on every rankable numeric assay in the KG.
    assays = api.list_metabolite_assays(
        rankable=True, value_kind="numeric", limit=1000, conn=conn)
    assay_ids = [r["assay_id"] for r in assays["results"]]
    assert assay_ids

    mqa = api.metabolites_by_quantifies_assay(
        assay_ids=assay_ids, detection_status=["not_detected"],
        limit=1000, conn=conn)
    assert mqa["total_matching"] > 0
    for row in mqa["results"]:
        assert row["detection_status"] == "not_detected"
        assert row["metric_bucket"] is None
        assert row["metric_percentile"] is None
        assert row["rank_by_metric"] is None

    # Mirror on the metabolite-anchored reverse lookup: PEP (C00074) has
    # not_detected numeric-arm rows on rankable assays (see
    # test_assays_by_metabolite_flag_rollup_is_boolean for the boolean twin).
    abm = api.assays_by_metabolite(
        metabolite_ids=["kegg.compound:C00074"], evidence_kind="quantifies",
        limit=100, conn=conn)
    not_detected_rows = [
        r for r in abm["results"] if r["detection_status"] == "not_detected"
    ]
    assert not_detected_rows
    for row in not_detected_rows:
        assert row["metric_bucket"] is None
        assert row["metric_percentile"] is None


def test_assays_by_metabolite_summary_not_matched_from_full_match_set(conn):
    # llm-review 2b.1: summary=True skips the detail query, so
    # not_matched / metabolites_without_evidence must come from the summary's
    # unpaged matched_metabolite_ids, never from the (empty) results page.
    res = api.assays_by_metabolite(
        metabolite_ids=["kegg.compound:C00025"], summary=True, conn=conn)
    assert res["results"] == []
    assert res["metabolites_matched"] > 0
    assert res["not_matched"] == []
    assert res["metabolites_without_evidence"] == []
    assert res["metabolites_with_evidence"] == ["kegg.compound:C00025"]
