"""Graph-level invariants the annotation-trust surface depends on.

These are the assertions a mocked unit test cannot make: they pin what the
KG's precomputed counts *mean*, what "leaf" selects, and that the two ways of
asking for the deepest attachment agree. A rebuild that quietly changes
`attachment_depth` semantics or re-scopes `gene_count` would otherwise pass
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
# TCDB leaf mode: `attachment_depth = 'most_specific'` and the generic
# transitive NOT EXISTS predicate select the same rows.
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestTcdbLeafEquivalence:
    @staticmethod
    def _pairs(conn, cypher):
        rows = conn.execute_query(cypher, org=MED4)
        return {(r["locus_tag"], r["term_id"]) for r in rows}

    ATTACHMENT = (
        "MATCH (g:Gene {organism_name: $org})-[r:Gene_has_tcdb_family]->"
        "(t:TcdbFamily)\n"
        "WHERE r.attachment_depth = 'most_specific'\n"
        "RETURN g.locus_tag AS locus_tag, t.id AS term_id"
    )
    NOT_EXISTS = (
        "MATCH (g:Gene {organism_name: $org})-[r:Gene_has_tcdb_family]->"
        "(t:TcdbFamily)\n"
        "WHERE NOT EXISTS {\n"
        "  MATCH (g)-[:Gene_has_tcdb_family]->(c:TcdbFamily)"
        "-[:Tcdb_family_is_a_tcdb_family*1..]->(t)\n"
        "}\n"
        "RETURN g.locus_tag AS locus_tag, t.id AS term_id"
    )

    def test_the_two_leaf_predicates_select_the_same_rows(self, conn):
        by_attachment = self._pairs(conn, self.ATTACHMENT)
        by_not_exists = self._pairs(conn, self.NOT_EXISTS)
        assert by_attachment == by_not_exists, (
            f"MED4 TCDB leaf sets diverge: "
            f"{len(by_attachment)} by attachment_depth vs "
            f"{len(by_not_exists)} by the transitive predicate. "
            f"`include_superseded` semantics depend on them being equal."
        )

    def test_leaf_is_a_strict_subset_of_every_attachment(self, conn):
        total = conn.execute_query(
            "MATCH (:Gene {organism_name: $org})-[r:Gene_has_tcdb_family]->()"
            " RETURN count(r) AS n",
            org=MED4,
        )[0]["n"]
        assert 0 < len(self._pairs(conn, self.ATTACHMENT)) < total

    def test_gene_ontology_terms_leaf_mode_returns_only_most_specific(
        self, conn,
    ):
        result = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism="MED4", ontology="tcdb",
            mode="leaf", verbose=True, limit=None, conn=conn,
        )
        depths = {r.get("attachment_depth") for r in result["results"]}
        assert depths == {"most_specific"}, depths

    def test_include_superseded_widens_rows_and_counts_together(self, conn):
        """The envelope counts must move with the rows — a summary query
        that ignores the flag under-reports the batch size."""
        narrow = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism="MED4", ontology="tcdb",
            mode="leaf", limit=None, conn=conn,
        )
        wide = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism="MED4", ontology="tcdb",
            mode="leaf", include_superseded=True, limit=None, conn=conn,
        )
        assert wide["returned"] > narrow["returned"]
        assert wide["total_matching"] == wide["returned"]
        assert wide["total_terms"] == wide["returned"]


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
    def test_signal_names_match_the_vocabulary(self, conn):
        result = api.genes_by_ontology(
            ontology="tcdb", organism="MED4", level=2,
            min_evidence_score=0.6, limit=1, conn=conn,
        )
        signals = result["evidence_score_signals"]
        assert "Gene_has_tcdb_family" in signals
        declared = conn.execute_query(
            "MATCH (v:ControlledVocabulary {applies_to: $rel, "
            "property: 'evidence_score'}) RETURN v.signals AS signals",
            rel="Gene_has_tcdb_family",
        )[0]["signals"]
        assert signals["Gene_has_tcdb_family"] == list(declared)

    def test_signals_absent_without_the_numeric_cutoff(self, conn):
        result = api.genes_by_ontology(
            ontology="tcdb", organism="MED4", level=2, limit=1, conn=conn,
        )
        assert "evidence_score_signals" not in result


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

    def test_by_sources_and_score_stats_populated_in_compact_mode(self, conn):
        result = api.genes_by_ontology(
            ontology="tcdb", organism="MED4", level=2, limit=5, conn=conn,
        )
        assert result["by_sources"]
        assert result["evidence_score_stats"]["max"] is not None

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
        """Spec §7.1: dense on 48/48 (a missing prop coalesces to 0 in the
        builder, but the KG stamps every node)."""
        row = conn.execute_query(
            "MATCH (o:OrganismTaxon)\n"
            "RETURN count(o) AS n,\n"
            "       count(o.peptidase_gene_count) AS pep,\n"
            "       count(o.nonpeptidase_homolog_gene_count) AS nonpep,\n"
            "       count(o.interpro_gene_count) AS ipr,\n"
            "       count(o.ncbifam_gene_count) AS ncbi,\n"
            "       sum(o.peptidase_gene_count) AS pep_sum,\n"
            "       max(o.peptidase_gene_count) AS pep_max")[0]
        assert row["n"] == 48
        assert row["pep"] == row["nonpep"] == row["ipr"] == row["ncbi"] == 48
        assert row["pep_sum"] == 3439
        assert row["pep_max"] == 148

    def test_meiothermus_ruber_name_collision_is_real(self, conn):
        """Guards the 'join by edge' rule: the strain and the treatment
        taxon share a preferred_name but only one has genes."""
        rows = conn.execute_query(
            "MATCH (o:OrganismTaxon {preferred_name: 'Meiothermus ruber'})\n"
            "RETURN o.organism_type AS t, coalesce(o.gene_count, 0) AS g,\n"
            "       coalesce(o.peptidase_gene_count, 0) AS p ORDER BY g")
        assert len(rows) == 2
        assert rows[0]["g"] == 0 and rows[0]["p"] == 0
        assert rows[1]["g"] > 0 and rows[1]["p"] > 0

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
# gene_overview family counts (backlog 3.4): tcdb_family_count counts
# attachment_depth='most_specific' edges only (the KG precompute
# Gene.tcdb_family_count counts superseded ancestors too — PMM0392 8 vs 7);
# cazy_family_count is the precompute verbatim.
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

    def test_tcdb_family_count_is_the_most_specific_edge_count(self, conn, result):
        live = {
            r["lt"]: r["n"] for r in conn.execute_query(
                "UNWIND $lts AS lt\n"
                "MATCH (g:Gene {locus_tag: lt})\n"
                "OPTIONAL MATCH (g)-[r:Gene_has_tcdb_family]->(:TcdbFamily)\n"
                "WHERE r.attachment_depth = 'most_specific'\n"
                "RETURN lt, count(r) AS n",
                lts=self.BATCH)
        }
        rows = self._rows(result)
        assert set(rows) == set(self.BATCH)
        for lt, row in rows.items():
            assert row["tcdb_family_count"] == live[lt], (
                f"{lt}: api tcdb_family_count={row['tcdb_family_count']} "
                f"but live most_specific edge count={live[lt]}")

    def test_pmm0392_reads_seven_not_eight(self, result):
        row = self._rows(result)["PMM0392"]
        assert row["tcdb_family_count"] == 7
        assert row["cazy_family_count"] == 0

    def test_hp15_1897_reads_four_cazy_families(self, result):
        row = self._rows(result)["HP15_1897"]
        assert row["cazy_family_count"] == 4
        assert row["tcdb_family_count"] == 0

    def test_tcdb_family_count_iff_transport_substrate_resolution(self, result):
        for lt, row in self._rows(result).items():
            assert (row["tcdb_family_count"] > 0) == (
                row["transport_substrate_resolution"] is not None), lt

    def test_envelope_has_tcdb_has_cazy(self, result):
        assert result["has_tcdb"] == 2
        assert result["has_cazy"] == 2
