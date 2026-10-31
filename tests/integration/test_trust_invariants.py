"""Graph-level invariants the annotation-trust surface depends on.

These are the assertions a mocked unit test cannot make: they pin what the
KG's precomputed counts *mean*, what "leaf" selects, and that the two ways of
asking for the gated TCDB leaf set agree. A rebuild that quietly changes
`tcdb_gate` semantics or re-scopes `gene_count` would otherwise pass
every other gate.

All tests are `-m kg`: they read the live build.
"""

import pytest

from multiomics_explorer.api import functions as api

MED4 = "Prochlorococcus MED4"
MIT1002 = "Alteromonas macleodii MIT1002"


# ---------------------------------------------------------------------------
# MEROPS: peptidase_gene_count / peptidase_organism_count are subtree counts
# over `call_class = 'peptidase'` edges only.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestMeropsPeptidaseCounts:
    TERM = "merops.family:S14"

    @staticmethod
    def _subtree(conn, term_id):
        return conn.execute_query(
            "MATCH (t:MeropsFamily {id: $id})\n"
            "OPTIONAL MATCH (t)<-[:Merops_family_is_a_merops_family*0..]-"
            "(d:MeropsFamily)<-[r:Gene_has_merops_family]-(g:Gene)\n"
            "WHERE r.call_class = 'peptidase'\n"
            "RETURN t.peptidase_gene_count AS declared_genes,\n"
            "       t.peptidase_organism_count AS declared_organisms,\n"
            "       count(DISTINCT g) AS walked_genes,\n"
            "       count(DISTINCT g.organism_name) AS walked_organisms",
            id=term_id,
        )[0]

    def test_peptidase_gene_count_is_the_walked_subtree(self, conn):
        row = self._subtree(conn, self.TERM)
        assert row["declared_genes"] == row["walked_genes"], (
            f"{self.TERM}.peptidase_gene_count={row['declared_genes']} but "
            f"walking the subtree over call_class='peptidase' edges gives "
            f"{row['walked_genes']}."
        )

    def test_peptidase_organism_count_is_the_walked_subtree(self, conn):
        row = self._subtree(conn, self.TERM)
        assert row["declared_organisms"] == row["walked_organisms"], (
            f"{self.TERM}.peptidase_organism_count="
            f"{row['declared_organisms']} but walking gives "
            f"{row['walked_organisms']}."
        )

    def test_the_peptidase_count_excludes_other_call_classes(self, conn):
        """The count is peptidase-only, not "every gene in the clan"."""
        row = conn.execute_query(
            "MATCH (t:MeropsFamily {id: $id})"
            "<-[:Merops_family_is_a_merops_family*0..]-(d:MeropsFamily)"
            "<-[r:Gene_has_merops_family]-(g:Gene)\n"
            "RETURN t.peptidase_gene_count AS declared,\n"
            "       count(DISTINCT g) AS all_calls",
            id=self.TERM,
        )[0]
        assert row["all_calls"] >= row["declared"]


# ---------------------------------------------------------------------------
# TCDB leaf mode (KG 3a, spec tcdb-cleanup-surface G1/G2): gate-passing edges
# (`tcdb_gate IN ['direct','annotated']`) minus any target that is an
# ancestor of another gate-passing target — exactly what the KG counts in
# `Gene.tcdb_assignment_count`.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestTcdbLeafEquivalence:
    @staticmethod
    def _pairs(conn, cypher):
        rows = conn.execute_query(cypher, org=MED4)
        return {(r["locus_tag"], r["term_id"]) for r in rows}

    GATED_LEAF = (
        "MATCH (g:Gene {organism_name: $org})-[r:Gene_has_tcdb_family]->"
        "(t:TcdbFamily)\n"
        "WHERE r.tcdb_gate IN ['direct','annotated']\n"
        "  AND NOT EXISTS {\n"
        "    MATCH (g)-[r2:Gene_has_tcdb_family]->(d:TcdbFamily)\n"
        "    WHERE r2.tcdb_gate IN ['direct','annotated']\n"
        "      AND (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(t)\n"
        "  }\n"
        "RETURN DISTINCT g.locus_tag AS locus_tag, t.id AS term_id"
    )

    def test_gated_leaf_set_reproduces_tcdb_assignment_count(self, conn):
        """KG-side invariant the explorer leaf mode relies on (0 mismatches
        on the target build)."""
        leaf = self._pairs(conn, self.GATED_LEAF)
        per_gene: dict[str, int] = {}
        for lt, _ in leaf:
            per_gene[lt] = per_gene.get(lt, 0) + 1
        declared = {r["l"]: r["n"] for r in conn.execute_query(
            "MATCH (g:Gene {organism_name: $org}) "
            "WHERE g.tcdb_assignment_count > 0 "
            "RETURN g.locus_tag AS l, g.tcdb_assignment_count AS n", org=MED4)}
        assert per_gene == declared

    def test_leaf_is_a_strict_subset_of_every_attachment(self, conn):
        total = conn.execute_query(
            "MATCH (:Gene {organism_name: $org})-[r:Gene_has_tcdb_family]->()"
            " RETURN count(r) AS n",
            org=MED4,
        )[0]["n"]
        assert 0 < len(self._pairs(conn, self.GATED_LEAF)) < total

    def test_gene_ontology_terms_leaf_rows_equal_the_gated_leaf_set(self, conn):
        lts = sorted({lt for lt, _ in self._pairs(conn, self.GATED_LEAF)})
        result = api.gene_ontology_terms(
            locus_tags=lts, organism="MED4", ontology="tcdb",
            mode="leaf", verbose=True, limit=None, conn=conn,
        )
        rows = result["results"]
        assert {(r["locus_tag"], r["term_id"]) for r in rows} == self._pairs(
            conn, self.GATED_LEAF)
        assert {r["tcdb_gate"] for r in rows} <= {"direct", "annotated"}
        for retired in ("attachment_depth", "evidence_score",
                        "confidence_score", "consensus_n"):
            assert not any(retired in r for r in rows), retired

    @pytest.mark.parametrize("locus,narrow_n,wide_n", [
        # ecfA1: 7 eggNOG subfamily rows + 3 below_gate best-hit systems
        # (33-35% identity) — spec G4 example.
        ("PMM0125", 7, 10),
    ])
    def test_include_weak_tcdb_hits_widens_rows_and_counts_together(
        self, conn, locus, narrow_n, wide_n,
    ):
        """The envelope counts must move with the rows — a summary query
        that ignores the flag under-reports the batch size."""
        narrow = api.gene_ontology_terms(
            locus_tags=[locus], organism="MED4", ontology="tcdb",
            mode="leaf", limit=None, conn=conn,
        )
        wide = api.gene_ontology_terms(
            locus_tags=[locus], organism="MED4", ontology="tcdb",
            mode="leaf", include_weak_tcdb_hits=True, limit=None, conn=conn,
        )
        assert narrow["returned"] == narrow_n
        assert wide["returned"] == wide_n
        assert wide["total_matching"] == wide["returned"]
        assert wide["total_terms"] == wide["returned"]
        added = [r for r in wide["results"] if r not in narrow["results"]]
        assert len(added) == wide_n - narrow_n
        assert {r["tcdb_gate"] for r in added} == {"below_gate"}


# ---------------------------------------------------------------------------
# Term-side counts: `gene_count` is the subtree, `direct_gene_count` is not.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestTermGeneCountSemantics:
    TERM = "go:0006979"

    def test_gene_count_is_the_subtree_count(self, conn):
        row = conn.execute_query(
            "MATCH (t:BiologicalProcess {id: $id})\n"
            "OPTIONAL MATCH (t)<-[:Biological_process_is_a_biological_process"
            "|Biological_process_part_of_biological_process*0..]-(d)"
            "<-[:Gene_involved_in_biological_process]-(g:Gene)\n"
            "RETURN t.gene_count AS declared, count(DISTINCT g) AS walked",
            id=self.TERM,
        )[0]
        assert row["declared"] == row["walked"], (
            f"{self.TERM}.gene_count={row['declared']} but the subtree walk "
            f"gives {row['walked']}."
        )

    def test_direct_gene_count_is_the_direct_count(self, conn):
        row = conn.execute_query(
            "MATCH (t:BiologicalProcess {id: $id})\n"
            "OPTIONAL MATCH (t)<-[:Gene_involved_in_biological_process]-"
            "(g:Gene)\n"
            "RETURN t.direct_gene_count AS declared, "
            "count(DISTINCT g) AS walked",
            id=self.TERM,
        )[0]
        assert row["declared"] == row["walked"]

    def test_the_two_counts_are_not_the_same_number(self, conn):
        """If they collapse, one of them stopped meaning what it says."""
        row = conn.execute_query(
            "MATCH (t:BiologicalProcess {id: $id}) "
            "RETURN t.gene_count AS gc, t.direct_gene_count AS dgc",
            id=self.TERM,
        )[0]
        assert row["gc"] > row["dgc"]


# ---------------------------------------------------------------------------
# evidence_score_signals come from the vocabulary, verbatim.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestEvidenceScoreSignals:
    """TCDB lost evidence_score in KG 3a (spec G3); MEROPS keeps it, so the
    signal passthrough is pinned there."""

    def test_signal_names_match_the_vocabulary(self, conn):
        result = api.genes_by_ontology(
            ontology="merops", organism="MIT1002", level=0,
            min_evidence_score=0.6, limit=1, conn=conn,
        )
        signals = result["evidence_score_signals"]
        assert "Gene_has_merops_family" in signals
        declared = conn.execute_query(
            "MATCH (v:ControlledVocabulary {applies_to: $rel, "
            "property: 'evidence_score'}) RETURN v.signals AS signals",
            rel="Gene_has_merops_family",
        )[0]["signals"]
        assert signals["Gene_has_merops_family"] == list(declared)

    def test_signals_absent_without_the_numeric_cutoff(self, conn):
        result = api.genes_by_ontology(
            ontology="merops", organism="MIT1002", level=0, limit=1, conn=conn,
        )
        assert "evidence_score_signals" not in result

    def test_min_evidence_score_on_tcdb_is_an_unsupported_axis(self, conn):
        with pytest.raises(ValueError, match="min_evidence_score"):
            api.genes_by_ontology(
                ontology="tcdb", organism="MED4", level=2,
                min_evidence_score=0.6, limit=1, conn=conn,
            )


# ---------------------------------------------------------------------------
# C1: the trust rollups and the tier-null warning are there in compact mode
# and describe the whole match, not the page.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestCompactModeTrustEnvelope:
    def test_by_tier_is_populated_in_compact_mode(self, conn):
        result = api.genes_by_ontology(
            ontology="tcdb", organism="MED4", level=2, max_tier=3,
            limit=5, conn=conn,
        )
        assert "tier" not in result["results"][0], (
            "compact rows must not carry tier"
        )
        buckets = {e["tier"] for e in result["by_tier"]}
        assert buckets, "by_tier is empty in compact mode"
        assert "null" in buckets, buckets

    def test_tier_null_warning_fires_in_compact_mode(self, conn):
        result = api.genes_by_ontology(
            ontology="tcdb", organism="MED4", level=2, max_tier=3,
            limit=5, conn=conn,
        )
        assert any("carry no tier" in w for w in result["warnings"]), (
            result["warnings"]
        )

    def test_by_sources_and_by_tcdb_call_populated_in_compact_mode(self, conn):
        """TCDB carries no evidence_score (KG 3a), so its score stats are
        null; by_tcdb_call (twin of by_call_class) covers the full match."""
        result = api.genes_by_ontology(
            ontology="tcdb", organism="MED4", level=2, limit=5, conn=conn,
        )
        assert result["by_sources"]
        assert result["evidence_score_stats"] is None
        assert sum(e["count"] for e in result["by_tcdb_call"]) == (
            result["total_matching"])

    def test_rollups_describe_the_full_match_not_the_page(self, conn):
        page = api.genes_by_ontology(
            ontology="tcdb", organism="MED4", level=2, limit=3, conn=conn,
        )
        rolled = sum(e["count"] for e in page["by_evidence"])
        assert page["returned"] == 3
        assert rolled == page["total_matching"], (
            f"by_evidence sums to {rolled}, not total_matching "
            f"{page['total_matching']} — the rollup is following the page."
        )

    def test_summary_mode_still_reports_by_call_class(self, conn):
        result = api.genes_by_ontology(
            ontology="merops", organism="MIT1002", level=0, summary=True,
            conn=conn,
        )
        assert result["results"] == []
        assert result["by_call_class"], "by_call_class empty with summary=True"
        classes = {e["call_class"] for e in result["by_call_class"]}
        assert "peptidase" in classes, classes


# ---------------------------------------------------------------------------
# I2: a facet that a tool demands must actually narrow term_ids mode.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestFacetAppliesInTermIdsMode:
    @staticmethod
    def _terms_of_type(conn, interpro_type, n=15):
        return [
            r["id"] for r in conn.execute_query(
                "MATCH (t:InterproEntry {interpro_type: $ty}) "
                "WHERE t.gene_count > 20 "
                "RETURN t.id AS id ORDER BY t.id LIMIT $n",
                ty=interpro_type, n=n,
            )
        ]

    def test_interpro_type_narrows_a_term_ids_call(self, conn):
        domain_ids = self._terms_of_type(conn, "DOMAIN")
        superfamily_ids = self._terms_of_type(conn, "HOMOLOGOUS_SUPERFAMILY")
        assert domain_ids and superfamily_ids
        term_ids = domain_ids + superfamily_ids
        pooled = api.genes_by_ontology(
            ontology="interpro", organism="MED4", term_ids=term_ids,
            min_gene_set_size=0, summary=True, conn=conn,
        )
        domains = api.genes_by_ontology(
            ontology="interpro", organism="MED4", term_ids=term_ids,
            interpro_type="DOMAIN", min_gene_set_size=0, summary=True,
            conn=conn,
        )
        assert domains["total_terms"] < pooled["total_terms"], (
            "interpro_type did not narrow a term_ids call — the stratum "
            "enrichment insists on would be a no-op."
        )
        assert domains["total_terms"] > 0



# ---------------------------------------------------------------------------
# Slice 4 (ORG-001): the organism-level annotation rollups are counts over
# `Gene_belongs_to_organism` — joined by EDGE, never by name (two
# `OrganismTaxon` nodes share preferred_name 'Meiothermus ruber').
# Spec docs/tool-specs/2026-08-27-slice4-light-surface.md §3.3 / §7.2.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestOrganismAnnotationRollups:
    """`OrganismTaxon.peptidase_gene_count` == distinct genes attached by
    `Gene_belongs_to_organism` carrying 'peptidase' in `merops_classes`
    (spec §7.2 — 0 offending rows expected)."""

    _DRIFT = (
        "MATCH (o:OrganismTaxon)\n"
        "OPTIONAL MATCH (o)<-[:Gene_belongs_to_organism]-(g:Gene)\n"
        "WHERE 'peptidase' IN coalesce(g.merops_classes, [])\n"
        "WITH o, count(DISTINCT g) AS live\n"
        "WHERE live <> coalesce(o.peptidase_gene_count, 0)\n"
        "RETURN o.preferred_name AS organism, live,\n"
        "       o.peptidase_gene_count AS declared"
    )

    def test_peptidase_gene_count_matches_edge_walk(self, conn):
        rows = conn.execute_query(self._DRIFT)
        assert rows == [], (
            "OrganismTaxon.peptidase_gene_count drifted from the "
            f"Gene_belongs_to_organism walk on: {rows}"
        )

    def test_nonpeptidase_homolog_gene_count_matches_edge_walk(self, conn):
        rows = conn.execute_query(
            self._DRIFT.replace("'peptidase' IN", "'nonpeptidase_homolog' IN")
            .replace("o.peptidase_gene_count",
                     "o.nonpeptidase_homolog_gene_count"))
        assert rows == [], rows

    def test_rollups_are_dense_on_every_organism(self, conn):
        """Spec §7.1: dense on every node (a missing prop coalesces to 0 in
        the builder, but the KG stamps every node)."""
        row = conn.execute_query(
            "MATCH (o:OrganismTaxon)\n"
            "RETURN count(o) AS n,\n"
            "       count(o.peptidase_gene_count) AS pep,\n"
            "       count(o.nonpeptidase_homolog_gene_count) AS nonpep,\n"
            "       count(o.interpro_gene_count) AS ipr,\n"
            "       count(o.ncbifam_gene_count) AS ncbi,\n"
            "       sum(o.peptidase_gene_count) AS pep_sum,\n"
            "       max(o.peptidase_gene_count) AS pep_max")[0]
        assert row["pep"] == row["nonpep"] == row["ipr"] == row["ncbi"] == row["n"]
        assert row["pep_sum"] == 8053  # 7926 before 83-1 (+127); 3439 over the 47 pre-Ford organisms
        assert row["pep_max"] == 148

    def test_organism_preferred_names_are_unique(self, conn):
        """The 2026-10-13 build retired the gene-less 'Meiothermus ruber'
        treatment taxon (ncbitaxon:277), the last duplicate name. The
        Experiment.coculture_partner list is built from partner
        preferred_names, so a name collision would make it ambiguous."""
        rows = conn.execute_query(
            "MATCH (o:OrganismTaxon)\n"
            "WITH o.preferred_name AS name, count(*) AS n WHERE n > 1\n"
            "RETURN name, n")
        assert rows == [], rows

    def test_list_organisms_row_equals_node_property(self, conn):
        """The api surfaces the node value verbatim (no re-count)."""
        res = api.list_organisms(organism_names=[MED4], conn=conn)
        row = res["results"][0]
        node = conn.execute_query(
            "MATCH (o:OrganismTaxon {preferred_name: $n})\n"
            "RETURN o.peptidase_gene_count AS p,\n"
            "       o.nonpeptidase_homolog_gene_count AS np,\n"
            "       o.interpro_gene_count AS i, o.ncbifam_gene_count AS nc",
            n=MED4)[0]
        assert row["peptidase_gene_count"] == node["p"]
        assert row["nonpeptidase_homolog_gene_count"] == node["np"]
        assert row["interpro_gene_count"] == node["i"]
        assert row["ncbifam_gene_count"] == node["nc"]


# ---------------------------------------------------------------------------
# gene_overview family counts: tcdb_assignment_count is the KG's gated
# precompute (distinct gate-passing targets minus ancestors; renamed from
# tcdb_family_count in KG 3a, no alias); cazy_family_count is the precompute
# verbatim.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestGeneOverviewFamilyCounts:
    BATCH = ["PMM0392", "PMM0001", "HP15_1897", "Sputw3181_2456"]

    @pytest.fixture(scope="class")
    def result(self, conn):
        return api.gene_overview(locus_tags=self.BATCH, conn=conn)

    @staticmethod
    def _rows(result):
        return {r["locus_tag"]: r for r in result["results"]}

    def test_tcdb_assignment_count_is_the_kg_precompute(self, conn, result):
        live = {
            r["lt"]: r["n"] for r in conn.execute_query(
                "UNWIND $lts AS lt\n"
                "MATCH (g:Gene {locus_tag: lt})\n"
                "RETURN lt, coalesce(g.tcdb_assignment_count, 0) AS n",
                lts=self.BATCH)
        }
        rows = self._rows(result)
        assert set(rows) == set(self.BATCH)
        for lt, row in rows.items():
            assert "tcdb_family_count" not in row
            assert row["tcdb_assignment_count"] == live[lt], lt

    def test_pmm0392_reads_seven(self, result):
        """cbiQ: 7 gated eggNOG subfamily calls 3.A.1.{25,28..33}."""
        row = self._rows(result)["PMM0392"]
        assert row["tcdb_assignment_count"] == 7
        assert row["cazy_family_count"] == 0

    def test_hp15_1897_reads_four_cazy_families(self, result):
        row = self._rows(result)["HP15_1897"]
        assert row["cazy_family_count"] == 4
        assert row["tcdb_assignment_count"] == 0

    def test_tcdb_assignment_count_iff_tcdb_annotation_type(self, result):
        for lt, row in self._rows(result).items():
            assert "transport_substrate_resolution" not in row
            assert (row["tcdb_assignment_count"] > 0) == (
                "tcdb" in (row.get("annotation_types") or [])), lt

    def test_envelope_has_tcdb_has_cazy(self, result):
        rows = self._rows(result).values()
        assert result["has_tcdb"] == sum(
            1 for r in rows if r["tcdb_assignment_count"] > 0)
        assert result["has_cazy"] == sum(
            1 for r in rows if r["cazy_family_count"] > 0) == 2
