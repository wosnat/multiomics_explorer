"""Live-KG contract for 2d.4: genes_by_ontology across organisms + bucket
paging.

Spec: docs/tool-specs/2d4-genes-by-ontology-cross-organism.md ("Verified
Cypher", "Degenerate inputs", "Tests"). Target: release KG alpha.9
(2026-11-18, 118 organisms with genes).

What these pin (and a mocked unit test cannot):
  * Per-organism oracle: each organism's slice of a LIST call equals that
    organism's single-organism call (rows, order, per-organism totals) —
    KEGG level 1 with explicit 5 / 500 bounds, and the hli InterPro FAMILY
    terms with the bounds off.
  * Bucket paging: concatenated pages == the unpaged rows, pages sorted
    (organism_name, term_id, locus_tag) and disjoint across bucket
    boundaries.
  * Single organism, a matrix of ontology modes: paged == unpaged, the
    order is (term_id, locus_tag), and the aggregate trust rollups of a paged
    call (Query C, the C5 carried-edge rewrite) equal the row-derived
    rollups of the unpaged call.
  * The quadratic-memory fix: a detail page on a ~6k-gene term across all
    organisms returns instead of MemoryPoolOutOfMemoryError.
  * Latency: ALL go_bp level 3 summary under 45 s.

Exemplars (discovery Cypher, release KG):
  MATCH (t:InterproEntry) WHERE t.id IN ['interpro:IPR063966','interpro:IPR054650']
  RETURN t.id, t.interpro_type, t.gene_count, t.organism_count
    -> IPR063966 FAMILY 500 / 102 strains; IPR054650 FAMILY 100 / 100
  kegg.pathway:ko00195 (Photosynthesis) ~6,058 genes across organisms
  (OOM'd the pre-2d.4 detail query at limit=100).

All tests are `-m kg`. RED until 2d.4 lands (organism must be a str today).
No frozen expectations from today's code: single-organism equivalence is
asserted structurally (paged vs unpaged, aggregate vs row-derived); the
byte-level "unchanged" guard is the regression goldens (Stage 3 regen).
"""

import time

import pytest

from multiomics_explorer.api import functions as api

pytestmark = pytest.mark.kg

MED4 = "Prochlorococcus MED4"
MIT9313 = "Prochlorococcus MIT9313"
WH8102 = "Synechococcus WH8102"
EZ55 = "Alteromonas macleodii EZ55"
LIST4 = [MED4, MIT9313, WH8102, EZ55]
HLI_TERMS = ["interpro:IPR063966", "interpro:IPR054650"]
BIG_KEGG_TERM = "kegg.pathway:ko00195"

_ROLLUP_KEYS = ("by_evidence", "by_tier", "by_sources", "by_call_class",
                "by_tcdb_call")


def _key(r):
    return (r["organism_name"], r["term_id"], r["locus_tag"])


def _rows_for(rows, org):
    return [r for r in rows if r["organism_name"] == org]


def _freq(entries):
    """Rollup list -> {value: count}, whatever the value key is called."""
    out = {}
    for e in entries or []:
        (val_key,) = [k for k in e if k != "count"]
        out[e[val_key]] = e["count"]
    return out


def _paged(conn, page, **kw):
    rows, offset = [], 0
    while True:
        out = api.genes_by_ontology(conn=conn, limit=page, offset=offset, **kw)
        if not out["results"]:
            break
        rows.append(out["results"])
        offset += len(out["results"])
        if not out["truncated"]:
            break
    return rows


@pytest.fixture(scope="module")
def organisms_with_genes(conn):
    rows = conn.execute_query(
        "MATCH (o:OrganismTaxon) WHERE coalesce(o.gene_count, 0) > 0 "
        "RETURN o.preferred_name AS name")
    return sorted(r["name"] for r in rows)


# --------------------------------------------------------------------------
# Per-organism oracle
# --------------------------------------------------------------------------

_ORACLE_CASES = [
    ("kegg_level1_bounds",
     dict(ontology="kegg", level=1, min_gene_set_size=5,
          max_gene_set_size=500)),
    ("hli_interpro_bounds_off",
     dict(ontology="interpro", term_ids=HLI_TERMS, interpro_type="FAMILY",
          min_gene_set_size=1, max_gene_set_size=None)),
]


@pytest.mark.parametrize("label,kw", _ORACLE_CASES,
                         ids=[c[0] for c in _ORACLE_CASES])
def test_list_slice_equals_single_organism_call(conn, label, kw):
    cross = api.genes_by_ontology(organism=LIST4, limit=None, conn=conn, **kw)
    assert cross["organism_name"] is None
    assert cross["not_found_organisms"] == []
    keys = [_key(r) for r in cross["results"]]
    assert keys == sorted(keys), "cross-organism rows not totally ordered"
    assert len(set(keys)) == len(keys), "duplicate rows"
    assert cross["returned"] == cross["total_matching"]
    by_org = {b["organism_name"]: b for b in cross["by_organism"]}
    assert sum(b["row_count"] for b in cross["by_organism"]) == \
        cross["total_matching"]
    for org in LIST4:
        single = api.genes_by_ontology(organism=org, limit=None, conn=conn,
                                       **kw)
        assert single["organism_name"] == org
        assert _rows_for(cross["results"], org) == single["results"], org
        if single["total_matching"]:
            assert by_org[org]["row_count"] == single["total_matching"]
            assert by_org[org]["gene_count"] == single["total_genes"]
            assert by_org[org]["term_count"] == single["total_terms"]
        else:
            assert org in cross["organisms_without_genes"]
    assert sorted(set(by_org) | set(cross["organisms_without_genes"])) == \
        sorted(LIST4)


def test_kegg_level1_oracle_is_not_trivial(conn):
    """The oracle above must compare real data in every organism."""
    out = api.genes_by_ontology(
        ontology="kegg", organism=LIST4, level=1, min_gene_set_size=5,
        max_gene_set_size=500, summary=True, conn=conn)
    assert {b["organism_name"] for b in out["by_organism"]} == set(LIST4)
    assert all(b["row_count"] > 500 for b in out["by_organism"])


def test_list_markers_mean_no_size_bounds(conn):
    """MED4 carries 5 HliA-D (IPR063966) genes and 1 IPR054650 gene
    (release KG, 2026-11-18). With the default markers a list call keeps
    both (bounds off); the single-string call keeps today's 5 / 500 and
    drops the 1-gene set."""
    cross = api.genes_by_ontology(
        ontology="interpro", organism=[MED4], term_ids=HLI_TERMS,
        interpro_type="FAMILY", summary=True, conn=conn)
    assert cross["total_matching"] == 6
    assert cross["size_filtered_terms"] == 0
    assert cross["filtered_out"] == []
    single = api.genes_by_ontology(
        ontology="interpro", organism=MED4, term_ids=HLI_TERMS,
        interpro_type="FAMILY", summary=True, conn=conn)
    assert single["total_matching"] == 5
    assert single["filtered_out"] == ["interpro:IPR054650"]


# --------------------------------------------------------------------------
# Bucket paging
# --------------------------------------------------------------------------

def test_pages_ordered_and_disjoint_across_bucket_boundaries(conn):
    kw = dict(ontology="kegg", organism=LIST4, level=1, min_gene_set_size=5,
              max_gene_set_size=500)
    full = api.genes_by_ontology(limit=None, conn=conn, **kw)["results"]
    # page size chosen so pages straddle (term) and (organism) boundaries
    pages = _paged(conn, 997, **kw)
    assert len(pages) > 3
    flat = [r for p in pages for r in p]
    assert [_key(r) for r in flat] == [_key(r) for r in full]
    for a, b in zip(pages, pages[1:]):
        assert [_key(r) for r in a] == sorted(_key(r) for r in a)
        assert _key(a[-1]) < _key(b[0])
    orgs_seen = {r["organism_name"] for r in flat}
    assert orgs_seen == set(LIST4)


def test_page_two_of_list4(conn):
    kw = dict(ontology="kegg", organism=LIST4, level=1, min_gene_set_size=5,
              max_gene_set_size=500)
    p1 = api.genes_by_ontology(limit=50, offset=0, conn=conn, **kw)
    p2 = api.genes_by_ontology(limit=50, offset=50, conn=conn, **kw)
    assert p1["total_matching"] == p2["total_matching"]
    assert p2["returned"] == 50 and p2["truncated"] is True
    assert _key(p1["results"][-1]) < _key(p2["results"][0])
    assert p1["by_organism"] == p2["by_organism"]


def test_offset_past_end_is_empty(conn):
    out = api.genes_by_ontology(
        ontology="interpro", organism=LIST4, term_ids=HLI_TERMS,
        interpro_type="FAMILY", offset=10_000_000, limit=10, conn=conn)
    assert out["results"] == []
    assert out["truncated"] is False
    assert out["total_matching"] > 0


def test_large_term_detail_page_does_not_run_out_of_memory(conn):
    """Pre-2d.4 the detail query held the term's whole gene list per row
    and failed at ~6k genes per term even with limit=100."""
    out = api.genes_by_ontology(
        ontology="kegg", organism=None, term_ids=[BIG_KEGG_TERM],
        limit=100, conn=conn)
    assert out["total_matching"] >= 5_000
    assert out["returned"] == 100
    keys = [_key(r) for r in out["results"]]
    assert keys == sorted(keys)


# --------------------------------------------------------------------------
# Single organism: paged == unpaged, order, aggregate rollups == row rollups
# --------------------------------------------------------------------------

_SINGLE_MODES = [
    ("go_bp_level3", dict(ontology="go_bp", level=3)),
    ("go_bp_term", dict(ontology="go_bp", term_ids=["go:0006260"])),
    ("kegg_level1", dict(ontology="kegg", level=1)),
    ("kegg_level2_terms", dict(ontology="kegg", level=2,
                               term_ids=["kegg.pathway:ko00010",
                                         "kegg.pathway:ko00195"])),
    ("cyanorak_role_level1", dict(ontology="cyanorak_role", level=1)),
    ("pfam_level0_clan", dict(ontology="pfam", level=0)),
    ("ec_level1", dict(ontology="ec", level=1)),
    ("cog_category_flat", dict(ontology="cog_category", level=0)),
    ("tcdb_level1", dict(ontology="tcdb", level=1)),
    ("tcdb_weak", dict(ontology="tcdb", level=1, include_weak_tcdb_hits=True)),
    ("interpro_family", dict(ontology="interpro", level=0,
                             interpro_type="FAMILY")),
    ("brite_transporters", dict(ontology="brite", level=1,
                                tree="transporters")),
    ("go_bp_evidence", dict(ontology="go_bp", level=1,
                            evidence=["curated", "family_inferred"])),
    ("kegg_level2_informative", dict(ontology="kegg", level=2,
                                     informative_only=True)),
]


@pytest.mark.parametrize("org", [MED4, EZ55], ids=["MED4", "EZ55"])
@pytest.mark.parametrize("label,kw", _SINGLE_MODES,
                         ids=[c[0] for c in _SINGLE_MODES])
def test_single_organism_paged_equals_unpaged(conn, org, label, kw):
    full = api.genes_by_ontology(organism=org, limit=None, conn=conn, **kw)
    assert full["organism_name"] == org
    rows = full["results"]
    assert full["returned"] == full["total_matching"] == len(rows)
    assert all(r["organism_name"] == org for r in rows)
    order = [(r["term_id"], r["locus_tag"]) for r in rows]
    assert order == sorted(order)
    assert len(set(order)) == len(order)
    pages = _paged(conn, 500, organism=org, **kw)
    assert [_key(r) for p in pages for r in p] == [_key(r) for r in rows]
    if full["total_matching"]:
        assert full["by_organism"] == [{
            "organism_name": org, "gene_count": full["total_genes"],
            "term_count": full["total_terms"],
            "row_count": full["total_matching"]}]
        assert full["organisms_without_genes"] == []
    else:
        assert full["organisms_without_genes"] == [org]


@pytest.mark.parametrize("org", [MED4, EZ55], ids=["MED4", "EZ55"])
@pytest.mark.parametrize("label,kw", _SINGLE_MODES,
                         ids=[c[0] for c in _SINGLE_MODES])
def test_aggregate_rollups_equal_row_rollups(conn, org, label, kw):
    """C5: a paged call's rollups come from Query C (carried edges); the
    unpaged call's come from the detail rows. They must agree."""
    paged = api.genes_by_ontology(organism=org, limit=5, conn=conn, **kw)
    full = api.genes_by_ontology(organism=org, limit=None, conn=conn, **kw)
    for key in _ROLLUP_KEYS:
        assert _freq(paged[key]) == _freq(full[key]), key
    ps, fs = paged["evidence_score_stats"], full["evidence_score_stats"]
    if fs is None or ps is None:
        assert ps == fs or not full["total_matching"]
    else:
        for k in ("min", "max", "median"):
            if fs[k] is None:
                assert ps[k] is None, k
            else:
                assert ps[k] == pytest.approx(fs[k]), k
        assert ps["n_null"] == fs["n_null"]


def test_cross_organism_rollups_equal_row_rollups(conn):
    kw = dict(ontology="go_bp", organism=LIST4[:2], level=2,
              min_gene_set_size=5, max_gene_set_size=500)
    paged = api.genes_by_ontology(limit=5, conn=conn, **kw)
    full = api.genes_by_ontology(limit=None, conn=conn, **kw)
    for key in _ROLLUP_KEYS:
        assert _freq(paged[key]) == _freq(full[key]), key


# --------------------------------------------------------------------------
# ALL organisms
# --------------------------------------------------------------------------

def test_all_organisms_hli_presence(conn, organisms_with_genes):
    out = api.genes_by_ontology(
        ontology="interpro", term_ids=HLI_TERMS, interpro_type="FAMILY",
        summary=True, conn=conn)
    assert out["organism_name"] is None
    assert out["not_found_organisms"] == []
    present = {b["organism_name"] for b in out["by_organism"]}
    absent = set(out["organisms_without_genes"])
    assert not present & absent
    assert sorted(present | absent) == organisms_with_genes
    assert len(present) >= 100
    assert out["organisms_without_genes"] == sorted(absent)
    assert sum(b["row_count"] for b in out["by_organism"]) == \
        out["total_matching"]
    top = {t["term_id"]: t for t in out["top_terms"]}
    assert top["interpro:IPR054650"]["organism_count"] >= 100


def test_all_organisms_term_with_no_genes(conn, organisms_with_genes):
    out = api.genes_by_ontology(
        ontology="kegg", term_ids=["kegg.pathway:ko00140"], summary=True,
        conn=conn)
    assert out["total_matching"] == 0
    assert out["by_organism"] == []
    assert out["organisms_without_genes"] == organisms_with_genes


def test_all_organisms_go_bp_level3_summary_under_45s(conn):
    t0 = time.monotonic()
    out = api.genes_by_ontology(
        ontology="go_bp", level=3, summary=True, conn=conn)
    elapsed = time.monotonic() - t0
    assert elapsed < 45, f"{elapsed:.1f}s"
    assert out["total_matching"] > 100_000
    assert len(out["by_organism"]) > 100
    assert sum(b["row_count"] for b in out["by_organism"]) == \
        out["total_matching"]


def test_list_entry_expands_to_strains(conn):
    out = api.genes_by_ontology(
        ontology="interpro", organism=["Prochlorococcus", "nope_2d4"],
        term_ids=HLI_TERMS, interpro_type="FAMILY", summary=True, conn=conn)
    assert out["not_found_organisms"] == ["nope_2d4"]
    names = ({b["organism_name"] for b in out["by_organism"]}
             | set(out["organisms_without_genes"]))
    assert len(names) >= 40
    assert all(n.startswith("Prochlorococcus") for n in names)


def test_str_matching_several_raises(conn):
    with pytest.raises(ValueError, match=r"\blist\b"):
        api.genes_by_ontology(ontology="kegg", organism="Alteromonas",
                              level=1, summary=True, conn=conn)
