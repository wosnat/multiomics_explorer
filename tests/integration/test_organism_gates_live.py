"""Live-KG contract for 2d.7a: relaxed single-organism gates on the
locus-tag tools (gene_ontology_terms, gene_clusters_by_gene,
gene_derived_metrics, metabolites_by_gene).

Spec: docs/tool-specs/2d7-single-organism-gates.md ("Degenerate inputs",
"Verified Cypher"). Target: release KG alpha.9 (2026-11-18).

What these pin (and a mocked unit test cannot):
  * `$org` null does not change single-organism output: for MED4-only tags,
    every GO-terms ontology branch (hierarchical, bridge-free KEGG, pfam,
    cyanorak_role, flat cog_category) gives IDENTICAL rows and envelope with
    `organism` given and omitted, leaf and rollup.
  * A mixed MED4 + MIT9313 batch without organism is the union of the
    per-organism calls, and `by_organism` adds up.
  * organism + a foreign tag raises; all-unknown tags without organism give
    an empty envelope (no raise).

Exemplars (discovery Cypher, release KG):
  MATCH (g:Gene {locus_tag:$lt}) RETURN g.organism_name
    PMM0001 / PMM1404 / PMM0370 -> Prochlorococcus MED4
    PMT0419 / PMT0856           -> Prochlorococcus MIT9313
  MATCH (:GeneCluster)-[r:Gene_in_gene_cluster]->(g:Gene {locus_tag:$lt})
  RETURN count(r)  -> PMM0370: 5, PMT0856: 3 (PMT0419: 0)
  MATCH (:DerivedMetric)-[r]->(g:Gene {locus_tag:$lt}) RETURN count(r)
    -> PMM0001: 17, PMT0419: 5

All tests are `-m kg`. RED until 2d.7a lands (organism required / raises).
"""

import pytest

from multiomics_explorer.api import functions as api

MED4 = "Prochlorococcus MED4"
MIT9313 = "Prochlorococcus MIT9313"
MED4_TAGS = ["PMM0001", "PMM1404", "PMM0370"]
MIXED_GO = ["PMM0001", "PMT0419"]
MIXED_CLUSTERS = ["PMM0370", "PMT0856"]
MIXED_METRICS = ["PMM0001", "PMT0419"]
UNKNOWN = ["PMM_DOES_NOT_EXIST", "NOPE_2D7"]

# (ontology, mode, level) — hierarchical / KEGG / pfam (cross-label) /
# cyanorak_role / flat, each leaf and rollup.
GO_BRANCHES = [
    ("go_bp", "leaf", None), ("go_bp", "rollup", 2),
    ("kegg", "leaf", None), ("kegg", "rollup", 1),
    ("pfam", "leaf", None), ("pfam", "rollup", 0),
    ("cyanorak_role", "leaf", None), ("cyanorak_role", "rollup", 1),
    ("cog_category", "leaf", None), ("cog_category", "rollup", 0),
    ("brite", "leaf", None), ("brite", "rollup", 1),
]

# Envelope keys that must be byte-identical between the scoped and unscoped
# call (warnings / filters echo are call-shape, not data).
_GO_PARITY_KEYS = (
    "total_matching", "total_genes", "total_terms", "by_ontology", "by_term",
    "terms_per_gene_min", "terms_per_gene_max", "terms_per_gene_median",
    "not_found", "no_terms", "by_evidence", "by_tier", "by_sources",
    "evidence_score_stats", "results", "by_organism",
)


def _ids(branches):
    return [f"{o}-{m}" for o, m, _ in branches]


@pytest.mark.kg
class TestGeneOntologyTermsSingleOrganismParity:
    """(a) `$org` null must not change single-organism output."""

    @pytest.mark.parametrize("verbose", [False, True], ids=["compact", "verbose"])
    @pytest.mark.parametrize("ontology,mode,level", GO_BRANCHES, ids=_ids(GO_BRANCHES))
    def test_scoped_equals_unscoped(self, conn, ontology, mode, level, verbose):
        kw = dict(ontology=ontology, mode=mode, level=level, verbose=verbose,
                  limit=None, conn=conn)
        scoped = api.gene_ontology_terms(MED4_TAGS, organism="MED4", **kw)
        unscoped = api.gene_ontology_terms(MED4_TAGS, **kw)
        for key in _GO_PARITY_KEYS:
            assert scoped[key] == unscoped[key], (ontology, mode, key)

    def test_all_ontologies_scoped_equals_unscoped(self, conn):
        scoped = api.gene_ontology_terms(MED4_TAGS, organism="MED4",
                                         limit=None, conn=conn)
        unscoped = api.gene_ontology_terms(MED4_TAGS, limit=None, conn=conn)
        for key in _GO_PARITY_KEYS:
            assert scoped[key] == unscoped[key], key

    def test_single_organism_by_organism(self, conn):
        out = api.gene_ontology_terms(MED4_TAGS, ontology="go_bp",
                                      limit=None, conn=conn)
        assert out["by_organism"] == [
            {"organism_name": MED4, "gene_count": out["total_genes"]}]


@pytest.mark.kg
class TestGeneOntologyTermsMixedBatch:
    """(b) mixed MED4 + MIT9313 batch without organism."""

    @pytest.mark.parametrize("ontology,mode,level", [
        ("go_bp", "leaf", None), ("go_bp", "rollup", 2),
        ("cyanorak_role", "rollup", 1),
    ], ids=["go_bp-leaf", "go_bp-rollup", "cyanorak_role-rollup"])
    def test_mixed_batch_rows_for_both_tags(self, conn, ontology, mode, level):
        out = api.gene_ontology_terms(MIXED_GO, ontology=ontology, mode=mode,
                                      level=level, limit=None, conn=conn)
        assert {r["locus_tag"] for r in out["results"]} == set(MIXED_GO)
        assert out["not_found"] == []
        assert out["no_terms"] == []
        assert len(out["by_organism"]) == 2
        assert {b["organism_name"] for b in out["by_organism"]} == {MED4, MIT9313}
        assert sum(b["gene_count"] for b in out["by_organism"]) == out["total_genes"]
        assert out["total_genes"] == 2

    def test_mixed_batch_is_union_of_single_calls(self, conn):
        kw = dict(ontology="go_bp", limit=None, conn=conn)
        mixed = api.gene_ontology_terms(MIXED_GO, **kw)
        med4 = api.gene_ontology_terms(["PMM0001"], organism="MED4", **kw)
        mit = api.gene_ontology_terms(["PMT0419"], organism="MIT9313", **kw)
        assert mixed["total_matching"] == med4["total_matching"] + mit["total_matching"]
        assert mixed["results"] == sorted(
            med4["results"] + mit["results"],
            key=lambda r: (r["locus_tag"], r["term_id"]))

    def test_mixed_batch_verbose_rows_carry_own_organism(self, conn):
        out = api.gene_ontology_terms(MIXED_GO, ontology="go_bp", verbose=True,
                                      limit=None, conn=conn)
        org_of = {"PMM0001": MED4, "PMT0419": MIT9313}
        assert out["results"]
        for r in out["results"]:
            assert r["organism_name"] == org_of[r["locus_tag"]]


_TOOLS = ["gene_ontology_terms", "gene_clusters_by_gene",
          "gene_derived_metrics", "metabolites_by_gene"]


@pytest.mark.kg
class TestForeignTagRaises:
    """(c) organism='MED4' + a MIT9313 tag raises (rule 2)."""

    @pytest.mark.parametrize("tool", _TOOLS)
    @pytest.mark.parametrize("tags", [["PMT0419"], ["PMM0001", "PMT0419"]],
                             ids=["only_foreign", "mixed"])
    def test_raises(self, conn, tool, tags):
        with pytest.raises(ValueError, match="MIT9313"):
            getattr(api, tool)(locus_tags=tags, organism="MED4", conn=conn)


@pytest.mark.kg
class TestAllUnknownWithoutOrganism:
    """(d) all-unknown tags, no organism -> empty envelope, no raise."""

    @pytest.mark.parametrize("tool", _TOOLS)
    def test_empty_envelope(self, conn, tool):
        out = getattr(api, tool)(locus_tags=UNKNOWN, conn=conn)
        nf = out["not_found"]
        if tool == "metabolites_by_gene":
            nf = nf["locus_tags"]
        assert nf == UNKNOWN
        assert out["total_matching"] == 0
        assert out["results"] == []
        if tool != "metabolites_by_gene":
            assert out["by_organism"] == []

    @pytest.mark.parametrize("tool", _TOOLS)
    def test_some_unknown_infers_from_known(self, conn, tool):
        tags = ["PMM0001", "PMM_DOES_NOT_EXIST"]
        out = getattr(api, tool)(locus_tags=tags, conn=conn)
        nf = out["not_found"]
        if tool == "metabolites_by_gene":
            nf = nf["locus_tags"]
        assert nf == ["PMM_DOES_NOT_EXIST"]


@pytest.mark.kg
class TestRowToolsMixedBatch:
    """(e) clusters / metrics: mixed batch = sum of per-organism calls."""

    @pytest.mark.parametrize("tool,tags", [
        ("gene_clusters_by_gene", MIXED_CLUSTERS),
        ("gene_derived_metrics", MIXED_METRICS),
    ])
    def test_counts_equal_sum_of_single_calls(self, conn, tool, tags):
        fn = getattr(api, tool)
        mixed = fn(locus_tags=tags, limit=None, conn=conn)
        singles = {
            MED4: fn(locus_tags=[tags[0]], organism="MED4", limit=None, conn=conn),
            MIT9313: fn(locus_tags=[tags[1]], organism="MIT9313", limit=None,
                        conn=conn),
        }
        assert all(s["total_matching"] > 0 for s in singles.values())
        assert mixed["total_matching"] == sum(
            s["total_matching"] for s in singles.values())
        assert len(mixed["results"]) == sum(
            len(s["results"]) for s in singles.values())
        assert {r["locus_tag"] for r in mixed["results"]} == set(tags)
        assert mixed["by_organism"] == sorted(
            [{"organism_name": o, "count": s["total_matching"]}
             for o, s in singles.items()],
            key=lambda b: (-b["count"], b["organism_name"]))

    @pytest.mark.parametrize("tool,tags", [
        ("gene_clusters_by_gene", MIXED_CLUSTERS),
        ("gene_derived_metrics", MIXED_METRICS),
    ])
    def test_verbose_rows_carry_organism_name(self, conn, tool, tags):
        out = getattr(api, tool)(locus_tags=tags, verbose=True, limit=None,
                                 conn=conn)
        org_of = {tags[0]: MED4, tags[1]: MIT9313}
        assert out["results"]
        for r in out["results"]:
            assert r["organism_name"] == org_of[r["locus_tag"]]

    @pytest.mark.parametrize("tool,tags", [
        ("gene_clusters_by_gene", MIXED_CLUSTERS),
        ("gene_derived_metrics", MIXED_METRICS),
    ])
    def test_compact_rows_have_no_organism_name(self, conn, tool, tags):
        out = getattr(api, tool)(locus_tags=tags, limit=None, conn=conn)
        assert out["results"]
        assert all("organism_name" not in r for r in out["results"])


@pytest.mark.kg
class TestMetabolitesByGeneMixedRaises:

    def test_mixed_batch_without_organism_raises(self, conn):
        with pytest.raises(ValueError, match="span multiple organisms"):
            api.metabolites_by_gene(locus_tags=["PMM0963", "PMT0419"],
                                    conn=conn)

    def test_organism_inferred_equals_given(self, conn):
        inferred = api.metabolites_by_gene(locus_tags=["PMM0963"], limit=None,
                                           conn=conn)
        given = api.metabolites_by_gene(locus_tags=["PMM0963"], organism="MED4",
                                        limit=None, conn=conn)
        assert inferred["total_matching"] == given["total_matching"] > 0
        assert inferred["results"] == given["results"]
        assert inferred["by_gene"] == given["by_gene"]
