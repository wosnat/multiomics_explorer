"""Live-KG contract for the TCDB cleanup surface (KG project 3a).

Spec: docs/tool-specs/tcdb-cleanup-surface.md ("Tests" + "Verified Cypher").
Target build: KG feat/post-3a-fixes, built_at 2026-10-24T17:33:40.709Z.

What these pin (and a mocked unit test cannot):
  * Agreement: the explorer's gated rows reproduce the KG's gated precomputes
    (`Gene.tcdb_assignment_count`, `TcdbFamily.gene_count`,
    `Metabolite.transporter_gene_count`, `Gene.transported_metabolite_count`)
    — counts are read live, never pinned.
  * Envelope totals equal the rows actually returned (overcount regression).
  * "The switch only adds rows": `include_weak_tcdb_hits` and
    `include_tcdb_family_substrates` never change the default rows.
  * Exemplar biology (cynD, phnD, urtA, pstS, thiL, orthophosphate), each with
    its discovery Cypher in a comment.
  * Nesting and no-duplicate-row invariants.

All tests are `-m kg`.
"""

from collections import Counter

import pytest

from multiomics_explorer.api import functions as api
from multiomics_explorer.kg.queries_lib import TCDB_DIRECT_GATE_PREDICATE

MED4 = "Prochlorococcus MED4"
PUTIDA = "Pseudomonas putida KT2440"

CYND = "PMM0372"
PHND = "PMM0673"
URTA = "PMM0970"
PSTS = "PMM0710"
THIL = "PMM0024"
ORTHOPHOSPHATE = "kegg.compound:C00009"
TRIPHOSPHATE = "kegg.compound:C00536"

_BIG = 100_000  # limit for gbm / mbg (they take no limit=None)


def _tcdb_rows(results):
    return [r for r in results if r["evidence_source"] == "transport"]


def _route(results, route):
    return [r for r in _tcdb_rows(results) if r["tcdb_route"] == route]


def _transport_key(r):
    return (r["locus_tag"], r["tcdb_family_id"], r["metabolite_id"])


def _row_key(r):
    """Stable identity of a gene x term row for set comparisons."""
    return tuple(sorted((k, repr(v)) for k, v in r.items()))


# ---------------------------------------------------------------------------
# Shared live fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def med4_genes(conn):
    return [r["l"] for r in conn.execute_query(
        "MATCH (g:Gene {organism_name: $o}) RETURN g.locus_tag AS l ORDER BY l",
        o=MED4)]


@pytest.fixture(scope="module")
def med4_tcdb_genes(conn):
    """MED4 genes with >= 1 gated TCDB assignment (KG precompute)."""
    return [r["l"] for r in conn.execute_query(
        "MATCH (g:Gene {organism_name: $o}) WHERE g.tcdb_assignment_count > 0 "
        "RETURN g.locus_tag AS l ORDER BY l", o=MED4)]


@pytest.fixture(scope="module")
def med4_leaf_default(conn, med4_genes):
    return api.gene_ontology_terms(
        med4_genes, MED4, ontology="tcdb", mode="leaf", limit=None, conn=conn)


@pytest.fixture(scope="module")
def med4_leaf_weak(conn, med4_genes):
    return api.gene_ontology_terms(
        med4_genes, MED4, ontology="tcdb", mode="leaf",
        include_weak_tcdb_hits=True, limit=None, conn=conn)


@pytest.fixture(scope="module")
def med4_mbg_transport(conn, med4_tcdb_genes):
    return {
        walk: api.metabolites_by_gene(
            med4_tcdb_genes, MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=walk, limit=_BIG, conn=conn)
        for walk in (False, True)
    }


# ---------------------------------------------------------------------------
# Agreement: rows vs KG precompute
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestTcdbRowsAgreeWithKgPrecomputes:
    def test_leaf_rows_per_gene_equal_tcdb_assignment_count(
        self, conn, med4_genes, med4_leaf_default,
    ):
        expected = {r["l"]: r["n"] for r in conn.execute_query(
            "MATCH (g:Gene {organism_name: $o}) "
            "RETURN g.locus_tag AS l, coalesce(g.tcdb_assignment_count, 0) AS n",
            o=MED4)}
        assert not med4_leaf_default["truncated"]
        got = Counter(r["locus_tag"] for r in med4_leaf_default["results"])
        mismatches = {lt: (got.get(lt, 0), n) for lt, n in expected.items()
                      if got.get(lt, 0) != n}
        assert mismatches == {}, list(mismatches.items())[:10]
        assert sum(expected.values()) == med4_leaf_default["total_matching"]

    @pytest.mark.parametrize("level", [1, 2, 3, 4])
    def test_term2gene_distinct_genes_equal_term_gene_count(self, conn, level):
        """Organism-scoped: TcdbFamily.gene_count is global, so the MED4
        reference is the gated subtree walk restricted to MED4 — and the
        global precompute is checked separately below."""
        res = api.genes_by_ontology(
            "tcdb", MED4, level=level, min_gene_set_size=1,
            max_gene_set_size=None, limit=None, conn=conn)
        assert not res["truncated"]
        got: dict[str, set] = {}
        for r in res["results"]:
            got.setdefault(r["term_id"], set()).add(r["locus_tag"])
        live = {r["t"]: r["n"] for r in conn.execute_query(
            "MATCH (g:Gene {organism_name: $o})-[r:Gene_has_tcdb_family]->"
            "(:TcdbFamily)-[:Tcdb_family_is_a_tcdb_family*0..]->"
            "(t:TcdbFamily {level: $lv}) "
            "WHERE r.tcdb_gate IN ['direct','annotated'] "
            "RETURN t.id AS t, count(DISTINCT g) AS n", o=MED4, lv=level)}
        assert {t: len(g) for t, g in got.items()} == live

    def test_gated_subtree_walk_reproduces_term_gene_count(self, conn):
        """The reference walk above is the KG's gene_count definition
        (global, all organisms) — 0 mismatches on the target build."""
        bad = conn.execute_query(
            "MATCH (t:TcdbFamily) WHERE t.gene_count > 0 "
            "OPTIONAL MATCH (g:Gene)-[r:Gene_has_tcdb_family]->(:TcdbFamily)"
            "-[:Tcdb_family_is_a_tcdb_family*0..]->(t) "
            "WHERE r.tcdb_gate IN ['direct','annotated'] "
            "WITH t, count(DISTINCT g) AS walked "
            "WHERE walked <> t.gene_count "
            "RETURN t.id AS t, t.gene_count AS declared, walked LIMIT 10")
        assert bad == []

    @pytest.mark.parametrize("metabolite_id", [
        "kegg.compound:C00088",   # nitrite
        "kegg.compound:C00086",   # urea
        "kegg.compound:C01417",   # cyanate
        ORTHOPHOSPHATE,
    ])
    def test_gbm_direct_genes_unioned_over_organisms_equal_transporter_gene_count(
        self, conn, kg_count, metabolite_id,
    ):
        live = kg_count(
            "MATCH (m:Metabolite {id: $id}) RETURN m.transporter_gene_count",
            id=metabolite_id)
        orgs = api.list_organisms(limit=500, conn=conn)["results"]
        genes: set[str] = set()
        for org in orgs:
            try:
                gbm = api.genes_by_metabolite(
                    [metabolite_id], org["organism_name"],
                    evidence_sources=["transport"], limit=_BIG, conn=conn)
            except ValueError:
                # Ambiguous preferred_name under word-CONTAINS (Alteromonas,
                # AltDE vs AltDE1): recover the exact set with the same
                # direct-gate predicate the transport arm uses.
                rows = conn.execute_query(
                    "MATCH (g:Gene {organism_name: $organism})"
                    "-[gt:Gene_has_tcdb_family]->(tf:TcdbFamily)"
                    "-[:Tcdb_family_transports_metabolite]->"
                    "(m:Metabolite {id: $metabolite_id})\n"
                    f"WHERE {TCDB_DIRECT_GATE_PREDICATE}\n"
                    "RETURN collect(DISTINCT g.locus_tag) AS locus_tags",
                    organism=org["organism_name"], metabolite_id=metabolite_id)
                genes |= set(rows[0]["locus_tags"])
                continue
            assert not gbm["truncated"], org["organism_name"]
            assert all(r["tcdb_route"] == "direct" for r in gbm["results"])
            genes |= {r["locus_tag"] for r in gbm["results"]}
        assert len(genes) == live

    def test_mbg_direct_metabolite_targets_equal_transported_metabolite_count(
        self, conn, med4_mbg_transport,
    ):
        res = med4_mbg_transport[False]
        assert not res["truncated"]
        got: dict[str, set] = {}
        for r in _route(res["results"], "direct"):
            if r["target_kind"] == "metabolite":
                got.setdefault(r["locus_tag"], set()).add(r["metabolite_id"])
        expected = {r["l"]: r["n"] for r in conn.execute_query(
            "MATCH (g:Gene {organism_name: $o}) "
            "WHERE g.transported_metabolite_count > 0 "
            "RETURN g.locus_tag AS l, g.transported_metabolite_count AS n",
            o=MED4)}
        assert {lt: len(m) for lt, m in got.items()} == expected


# ---------------------------------------------------------------------------
# Envelope totals == rows returned (overcount regression)
# ---------------------------------------------------------------------------


_GBM_SAMPLES = [
    (MED4, [ORTHOPHOSPHATE, "kegg.compound:C00086", "kegg.compound:C00064"]),
    (PUTIDA, [ORTHOPHOSPHATE, "kegg.compound:C00064"]),
]


@pytest.mark.kg
class TestTransportEnvelopeTotalsMatchRows:
    @pytest.mark.parametrize("walk", [False, True])
    @pytest.mark.parametrize("org,mids", _GBM_SAMPLES)
    def test_gbm_summary_total_equals_rows(self, conn, org, mids, walk):
        kw = dict(evidence_sources=["transport"],
                  include_tcdb_family_substrates=walk, conn=conn)
        summ = api.genes_by_metabolite(mids, org, summary=True, **kw)
        full = api.genes_by_metabolite(mids, org, limit=_BIG, **kw)
        assert not full["truncated"]
        rows = full["results"]
        assert summ["total_matching"] == full["total_matching"] == len(rows)
        assert summ["gene_count_total"] == len({r["locus_tag"] for r in rows})
        routes = Counter(r["tcdb_route"] for r in rows)
        assert {e["tcdb_route"]: e["count"] for e in summ["by_tcdb_route"]} == dict(routes)

    @pytest.mark.parametrize("walk", [False, True])
    def test_mbg_summary_total_equals_rows(
        self, conn, med4_tcdb_genes, med4_mbg_transport, walk,
    ):
        summ = api.metabolites_by_gene(
            med4_tcdb_genes, MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=walk, summary=True, conn=conn)
        full = med4_mbg_transport[walk]
        assert not full["truncated"]
        rows = full["results"]
        assert summ["total_matching"] == full["total_matching"] == len(rows)
        routes = Counter(r["tcdb_route"] for r in rows)
        assert {e["tcdb_route"]: e["count"] for e in summ["by_tcdb_route"]} == dict(routes)
        assert "family" in routes if walk else set(routes) == {"direct"}


# ---------------------------------------------------------------------------
# The switches only add rows
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestSwitchesOnlyAddRows:
    def test_weak_hits_leaf_default_rows_unchanged(
        self, med4_leaf_default, med4_leaf_weak,
    ):
        default = {_row_key(r) for r in med4_leaf_default["results"]}
        weak_rows = med4_leaf_weak["results"]
        weak = {_row_key(r) for r in weak_rows}
        assert default <= weak
        added = [r for r in weak_rows if _row_key(r) not in default]
        assert added
        assert {r["tcdb_gate"] for r in added} == {"below_gate"}
        assert {r["tcdb_gate"] for r in med4_leaf_default["results"]} <= {
            "direct", "annotated"}

    def test_weak_hits_reach_every_below_gate_only_gene(
        self, conn, med4_leaf_weak,
    ):
        only_weak = {r["l"] for r in conn.execute_query(
            "MATCH (g:Gene {organism_name: $o})-[:Gene_has_tcdb_family]->() "
            "WHERE NOT EXISTS { MATCH (g)-[r:Gene_has_tcdb_family]->() "
            "WHERE r.tcdb_gate IN ['direct','annotated'] } "
            "RETURN DISTINCT g.locus_tag AS l", o=MED4)}
        assert only_weak
        assert only_weak <= {r["locus_tag"] for r in med4_leaf_weak["results"]}

    @pytest.mark.parametrize("level", [0, 1, 2, 3, 4])
    def test_weak_hits_genes_by_ontology_default_rows_unchanged(
        self, conn, level,
    ):
        kw = dict(level=level, min_gene_set_size=1, max_gene_set_size=None,
                  limit=None, conn=conn)
        d = api.genes_by_ontology("tcdb", MED4, **kw)
        w = api.genes_by_ontology("tcdb", MED4, include_weak_tcdb_hits=True, **kw)
        assert {_row_key(r) for r in d["results"]} <= {
            _row_key(r) for r in w["results"]}

    def test_weak_hits_do_not_push_a_gated_term_past_the_size_bound(self, conn):
        """P. putida tcdb:3.A: 424 gated genes (< default max 500) but 563
        with weak hits. Size bounds are judged on the gated set, so the
        switch must not drop the term (it only adds rows). Discovery:
          MATCH (g:Gene {organism_name:'Pseudomonas putida KT2440'})
            -[r:Gene_has_tcdb_family]->()-[:Tcdb_family_is_a_tcdb_family*0..]
            ->(t:TcdbFamily {id:'tcdb:3.A'})
          RETURN count(DISTINCT CASE WHEN r.tcdb_gate IN ['direct','annotated']
            THEN g END), count(DISTINCT g)   -> 424, 563"""
        counts = self._putida_3a_counts(conn)
        assert counts["gated"] < 500 < counts["all"], counts
        d = api.genes_by_ontology(
            "tcdb", PUTIDA, term_ids=["tcdb:3.A"], limit=None, conn=conn)
        w = api.genes_by_ontology(
            "tcdb", PUTIDA, term_ids=["tcdb:3.A"], include_weak_tcdb_hits=True,
            limit=None, conn=conn)
        assert d["total_matching"] == counts["gated"]
        assert {_row_key(r) for r in d["results"]} <= {
            _row_key(r) for r in w["results"]}
        assert len({r["locus_tag"] for r in w["results"]}) == counts["all"]

    @staticmethod
    def _putida_3a_counts(conn):
        return conn.execute_query(
            "MATCH (g:Gene {organism_name: $o})-[r:Gene_has_tcdb_family]->()"
            "-[:Tcdb_family_is_a_tcdb_family*0..]->(:TcdbFamily {id: 'tcdb:3.A'}) "
            "RETURN count(DISTINCT CASE WHEN r.tcdb_gate IN ['direct','annotated'] "
            "THEN g END) AS gated, count(DISTINCT g) AS all", o=PUTIDA)[0]

    def test_family_walk_mbg_direct_rows_identical(self, med4_mbg_transport):
        off = _tcdb_rows(med4_mbg_transport[False]["results"])
        on = med4_mbg_transport[True]["results"]
        assert [r for r in _route(on, "direct")] == off
        family = _route(on, "family")
        assert family
        direct_pairs = {(r["locus_tag"], r["metabolite_id"]) for r in off}
        # dedupe: no family row for a (gene, metabolite) that has a direct row
        assert not any((r["locus_tag"], r["metabolite_id"]) in direct_pairs
                       for r in family)
        for r in family:
            assert r["attached_tcdb_id"] == r["tcdb_family_id"]
            assert r["tcdb_substrate_system_count"] >= 1

    @pytest.mark.parametrize("org,mids", _GBM_SAMPLES)
    def test_family_walk_gbm_direct_rows_identical(self, conn, org, mids):
        kw = dict(evidence_sources=["transport"], limit=_BIG, conn=conn)
        off = api.genes_by_metabolite(mids, org, **kw)
        on = api.genes_by_metabolite(
            mids, org, include_tcdb_family_substrates=True, **kw)
        assert _route(on["results"], "direct") == off["results"]
        hint = off["tcdb_family_substrates_not_shown"]
        family = _route(on["results"], "family")
        assert hint["rows"] == len(family)
        assert hint["genes"] == len({r["locus_tag"] for r in family})
        assert hint["metabolites"] == len({r["metabolite_id"] for r in family})
        assert on["tcdb_family_substrates_not_shown"] is None


# ---------------------------------------------------------------------------
# Exemplars
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestTcdbExemplars:
    def test_cynd_two_direct_systems_three_metabolites(self, conn):
        """cynD PMM0372. Discovery:
          MATCH (:Gene {locus_tag:'PMM0372'})-[r:Gene_has_tcdb_family
            {tcdb_gate:'direct'}]->(s)-[:Tcdb_family_transports_metabolite]->(m)
          RETURN s.id, r.tcdb_call, collect(m.id)
          -> 3.A.1.16.1 eggnog [nitrite, nitrate];
             3.A.1.16.2 diamond_best_hit (59.2%) [nitrite, cyanate]"""
        ov = api.gene_overview([CYND], conn=conn)["results"][0]
        assert ov["tcdb_assignment_count"] == 2
        assert ov["transported_metabolite_count"] == 3
        assert ov["tcdb_best_hit_identity"] == pytest.approx(59.2)
        mbg = api.metabolites_by_gene(
            [CYND], MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=100, conn=conn)
        rows = mbg["results"]
        assert {r["tcdb_route"] for r in rows} == {"direct"}
        assert {r["tcdb_family_id"] for r in rows} == {
            "tcdb:3.A.1.16.1", "tcdb:3.A.1.16.2"}
        assert {r["metabolite_id"] for r in rows} == {
            "kegg.compound:C00088", "kegg.compound:C00244",
            "kegg.compound:C01417"}
        calls = {r["tcdb_family_id"]: r["tcdb_calls"] for r in rows}
        # siblings are not lineage: one call kind each
        assert calls == {"tcdb:3.A.1.16.1": ["eggnog"],
                         "tcdb:3.A.1.16.2": ["diamond_best_hit"]}
        leaf = api.gene_ontology_terms(
            [CYND], MED4, ontology="tcdb", limit=None, conn=conn)
        assert {r["term_id"] for r in leaf["results"]} == {
            "tcdb:3.A.1.16.1", "tcdb:3.A.1.16.2"}
        assert {r["tcdb_gate"] for r in leaf["results"]} == {"direct"}

    def test_phnd_family_rows_via_3_a_1_9(self, conn):
        """phnD PMM0673: no system call; eggNOG on subfamily 3.A.1.9 (PhnT)
        is the walk start. Discovery: see the spec's family-walk Cypher."""
        off = api.metabolites_by_gene(
            [PHND], MED4, evidence_sources=["transport"], limit=100, conn=conn)
        assert off["results"] == []
        assert any("include_tcdb_family_substrates=True" in w
                   for w in off["warnings"]), off["warnings"]
        on = api.metabolites_by_gene(
            [PHND], MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=100, conn=conn)
        rows = on["results"]
        assert rows
        assert {r["tcdb_route"] for r in rows} == {"family"}
        assert {r["attached_tcdb_id"] for r in rows} == {"tcdb:3.A.1.9"}
        mets = {r["metabolite_id"] for r in rows}
        assert {ORTHOPHOSPHATE, "kegg.compound:C06701",
                "kegg.compound:C05339"} <= mets

    @pytest.mark.parametrize("locus", [URTA, PSTS])
    def test_no_family_rows_when_a_direct_system_sits_below(self, conn, locus):
        """Start rule 3: urtA (direct 3.A.1.4.4 / .5 under 3.A.1.4) and pstS
        (direct 3.A.1.7.6 under 3.A.1.7) never walk."""
        on = api.metabolites_by_gene(
            [locus], MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=500, conn=conn)
        assert on["results"]
        assert {r["tcdb_route"] for r in on["results"]} == {"direct"}

    def test_psts_direct_triphosphate_only(self, conn):
        """TCDB curation quirk: pstS's direct system 3.A.1.7.6 is curated
        with triphosphate only, so pstS does not reach orthophosphate.
          MATCH (:TcdbFamily {id:'tcdb:3.A.1.7.6'})
            -[:Tcdb_family_transports_metabolite]->(m) RETURN m.id
          -> kegg.compound:C00536"""
        rows = api.metabolites_by_gene(
            [PSTS], MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=100, conn=conn)["results"]
        assert {(r["tcdb_family_id"], r["metabolite_id"]) for r in rows} == {
            ("tcdb:3.A.1.7.6", TRIPHOSPHATE)}
        assert rows[0]["tcdb_calls"] == [
            "diamond_best_hit", "diamond_tier", "eggnog"]

    def test_orthophosphate_med4_family_hint(self, conn):
        """0 direct MED4 genes; hint {genes: 4, metabolites: 1, rows: 4}
        (phnC/D/E, PMM0717 — pstA/B/C/S are excluded by start rule 3)."""
        r = api.genes_by_metabolite(
            [ORTHOPHOSPHATE], MED4, evidence_sources=["transport"],
            limit=100, conn=conn)
        assert r["results"] == []
        assert r["tcdb_family_substrates_not_shown"] == {
            "genes": 4, "metabolites": 1, "rows": 4}
        hint_warning = next(
            (w for w in r["warnings"] if "include_tcdb_family_substrates=True" in w),
            None)
        assert hint_warning is not None, r["warnings"]
        assert "phnD" in hint_warning
        on = api.genes_by_metabolite(
            [ORTHOPHOSPHATE], MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=100, conn=conn)
        assert PHND in {x["locus_tag"] for x in on["results"]}
        assert PSTS not in {x["locus_tag"] for x in on["results"]}

    def test_thil_weak_only_row(self, conn):
        """thiL PMM0024: only TCDB edge is a 28.5% tier-3 hit on 8.A.159.
          MATCH (:Gene {locus_tag:'PMM0024'})-[r:Gene_has_tcdb_family]->(t)
          RETURN t.id, r.tcdb_call, r.tcdb_gate
          -> tcdb:8.A.159 diamond_tier below_gate"""
        ov = api.gene_overview([THIL], conn=conn)["results"][0]
        assert ov["tcdb_assignment_count"] == 0
        assert "tcdb" not in (ov.get("annotation_types") or [])
        d = api.gene_ontology_terms([THIL], MED4, ontology="tcdb", conn=conn)
        assert d["results"] == []
        w = api.gene_ontology_terms(
            [THIL], MED4, ontology="tcdb", include_weak_tcdb_hits=True,
            conn=conn)
        assert [(r["term_id"], r["tcdb_gate"], r["tcdb_call"])
                for r in w["results"]] == [
            ("tcdb:8.A.159", "below_gate", "diamond_tier")]
        mbg = api.metabolites_by_gene(
            [THIL], MED4, evidence_sources=["transport"],
            include_tcdb_family_substrates=True, limit=10, conn=conn)
        assert mbg["results"] == []

    def test_mbg_walkable_genes_all_yield_family_rows(
        self, conn, med4_tcdb_genes, med4_mbg_transport,
    ):
        """A gene is walkable iff it has no direct edge and an annotated
        start passing rules 1-4 with tcdb_substrate_count > 0 (88 in MED4 on
        the target build). Each must yield >= 1 family row, and the
        'transport arm is empty ... pass include_tcdb_family_substrates'
        warning must count exactly those genes."""
        walkable = {r["l"] for r in conn.execute_query(
            "MATCH (g:Gene {organism_name: $o})"
            "-[:Gene_has_tcdb_family {tcdb_gate: 'annotated'}]->(a:TcdbFamily) "
            "WHERE a.level_kind IN ['tc_family','tc_subfamily'] "
            "  AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family "
            "{tcdb_gate: 'annotated'}]->(d:TcdbFamily) "
            "WHERE (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(a) } "
            "  AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family "
            "{tcdb_gate: 'direct'}]->() } "
            "  AND 0 < a.tcdb_substrate_count <= 200 "
            "RETURN DISTINCT g.locus_tag AS l", o=MED4)}
        assert walkable
        fam = {r["locus_tag"]
               for r in _route(med4_mbg_transport[True]["results"], "family")}
        assert walkable <= fam, sorted(walkable - fam)[:10]
        warning = next(
            w for w in med4_mbg_transport[False]["warnings"]
            if "transport arm is empty" in w)
        named = warning.split(":")[0]
        n_named = named.count("PMM")
        n_more = int(named.split(" and ")[-1].split()[0]) if " more" in named else 0
        assert n_named + n_more == len(walkable), warning


# ---------------------------------------------------------------------------
# Nesting + no duplicate rows
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestTcdbNestingAndUniqueness:
    def test_transport_genes_nest_inside_tcdb_annotated_genes(
        self, conn, med4_genes,
    ):
        ov = api.gene_overview(med4_genes, limit=len(med4_genes), conn=conn)
        rows = ov["results"]
        transport = {r["locus_tag"] for r in rows
                     if (r.get("transported_metabolite_count") or 0) > 0}
        tcdb = {r["locus_tag"] for r in rows
                if "tcdb" in (r.get("annotation_types") or [])}
        assert transport
        assert transport <= tcdb, sorted(transport - tcdb)[:10]
        assert {r["locus_tag"] for r in rows
                if "transport" in (r.get("evidence_sources") or [])} == transport

    @pytest.mark.parametrize("weak", [False, True])
    def test_no_duplicate_gene_term_rows_leaf(
        self, med4_leaf_default, med4_leaf_weak, weak,
    ):
        res = med4_leaf_weak if weak else med4_leaf_default
        c = Counter((r["locus_tag"], r["term_id"]) for r in res["results"])
        assert [k for k, v in c.items() if v > 1] == []
        assert res["total_matching"] == res["returned"]

    @pytest.mark.parametrize("level", [0, 1, 2, 3, 4])
    def test_no_duplicate_gene_term_rows_rollup(self, conn, med4_tcdb_genes, level):
        res = api.gene_ontology_terms(
            med4_tcdb_genes, MED4, ontology="tcdb", mode="rollup",
            level=level, limit=None, conn=conn)
        c = Counter((r["locus_tag"], r["term_id"]) for r in res["results"])
        assert [k for k, v in c.items() if v > 1] == []
        assert res["total_matching"] == res["returned"]

    @pytest.mark.parametrize("weak", [False, True])
    @pytest.mark.parametrize("level", [0, 1, 2, 3, 4])
    def test_no_duplicate_gene_term_rows_genes_by_ontology(self, conn, level, weak):
        res = api.genes_by_ontology(
            "tcdb", MED4, level=level, min_gene_set_size=1,
            max_gene_set_size=None, include_weak_tcdb_hits=weak, limit=None,
            conn=conn)
        c = Counter((r["locus_tag"], r["term_id"]) for r in res["results"])
        assert [k for k, v in c.items() if v > 1] == []
        assert res["total_matching"] == res["returned"]

    def test_no_duplicate_gene_term_rows_genes_by_ontology_term_ids(self, conn):
        """term_ids mode expands DOWN — PMM0970 3.A.1.4.4 (eggNOG + best hit)
        and PMM0710 3.A.1.7 (tier + eggNOG) were the pre-cleanup dups."""
        res = api.genes_by_ontology(
            "tcdb", MED4, term_ids=["tcdb:3.A.1.4.4", "tcdb:3.A.1.7"],
            min_gene_set_size=1, max_gene_set_size=None, limit=None, conn=conn)
        c = Counter((r["locus_tag"], r["term_id"]) for r in res["results"])
        assert [k for k, v in c.items() if v > 1] == []
        assert (URTA, "tcdb:3.A.1.4.4") in c

    @pytest.mark.parametrize("walk", [False, True])
    def test_no_duplicate_transport_rows(self, med4_mbg_transport, walk):
        rows = _tcdb_rows(med4_mbg_transport[walk]["results"])
        c = Counter(_transport_key(r) for r in rows)
        assert [k for k, v in c.items() if v > 1] == []
