"""Live-KG contract for release prep: organism-scoped transport reach (2c.5)
and TCDB role-only genes in gene_overview (2c.19).

Spec: docs/tool-specs/release-prep-transport-reach-and-alpha6-cleanup.md §3
(KG facts verified on dev build 2026-10-31T14:01:03Z).

All tests are `-m kg`.
"""

import pytest

from multiomics_explorer.api import functions as api

MED4 = "Prochlorococcus MED4"
PUTIDA = "Pseudomonas putida KT2440"

# A gene whose only TCDB route is a direct system with chemical-role
# substrates (SMR / BmrA-type efflux pump -> "drug"); spec §3 counts 108 such
# genes. Discovery:
#   MATCH (g:Gene)-[gt:Gene_has_tcdb_family]->(:TcdbFamily)
#         -[:Tcdb_family_transports_chemical_role]->(:ChemicalRole)
#   WHERE gt.tcdb_gate = 'direct'
#     AND NOT EXISTS { MATCH (g)-[gt2:Gene_has_tcdb_family]->(:TcdbFamily)
#                      -[:Tcdb_family_transports_metabolite]->(:Metabolite)
#                      WHERE gt2.tcdb_gate = 'direct' }
#   RETURN g.locus_tag
ROLE_ONLY_TCDB_GENE = "SynWH7803_0604"


@pytest.mark.kg
class TestListMetabolitesRouteScopedOrganismKG:
    """2c.5 — with organism_names AND evidence_sources, the organism must
    reach the metabolite by that route (Organism_has_metabolite edge)."""

    def test_med4_transport_nitrogen_is_edge_scoped(self, conn):
        r = api.list_metabolites(
            organism_names=[MED4], evidence_sources=["transport"],
            elements=["N"], summary=True, conn=conn)
        # was 147 (any-route organism x catalogue-level transport)
        assert r["total_matching"] == 20

    def test_top_organisms_counts_matching_route_only(self, conn):
        r = api.list_metabolites(
            evidence_sources=["transport"], elements=["N"], summary=True,
            conn=conn)
        top = r["top_organisms"]
        assert top, r
        # any-route count was KT2440 275; edge-scoped transport is 147.
        assert top[0]["organism_name"] == PUTIDA
        assert top[0]["count"] == 147
        med4 = [t for t in top if t["organism_name"] == MED4]
        assert not med4 or med4[0]["count"] <= 20

    def test_med4_top_organisms_with_both_filters(self, conn):
        r = api.list_metabolites(
            organism_names=[MED4], evidence_sources=["transport"],
            elements=["N"], summary=True, conn=conn)
        counts = {t["organism_name"]: t["count"] for t in r["top_organisms"]}
        assert counts.get(MED4) == 20
        assert all(c <= r["total_matching"] for c in counts.values())

    def test_organism_only_still_any_route(self, conn):
        """organism_names alone is unchanged (any route): a superset of the
        route-scoped answer."""
        any_route = api.list_metabolites(
            organism_names=[MED4], elements=["N"], summary=True, conn=conn)
        scoped = api.list_metabolites(
            organism_names=[MED4], evidence_sources=["transport"],
            elements=["N"], summary=True, conn=conn)
        assert any_route["total_matching"] > scoped["total_matching"]


@pytest.mark.kg
class TestGeneOverviewTcdbRoleOnlyKG:
    """2c.19 — a role-only direct TCDB system counts as transport chemistry."""

    def test_role_only_gene_tagged_transport(self, conn):
        r = api.gene_overview(locus_tags=[ROLE_ONLY_TCDB_GENE], conn=conn)
        assert r["results"], r
        row = r["results"][0]
        assert row["locus_tag"] == ROLE_ONLY_TCDB_GENE
        assert "transport" in row["evidence_sources"]

    def test_role_only_gene_counts_toward_has_chemistry(self, conn):
        r = api.gene_overview(locus_tags=[ROLE_ONLY_TCDB_GENE], conn=conn)
        assert r["has_chemistry"] == 1

    def test_role_only_gene_metabolomics_not_tagged_by_role(self, conn):
        """metabolomics stays metabolite-only (roles have no assays)."""
        r = api.gene_overview(locus_tags=[ROLE_ONLY_TCDB_GENE], conn=conn)
        row = r["results"][0]
        assert "metabolomics" not in row["evidence_sources"]
