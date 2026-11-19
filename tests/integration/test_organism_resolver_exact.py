"""Live-KG contract for backlog 2.8: organism resolver exact-first.

Spec: docs/tool-specs/organism-resolver-exact-first.md (FROZEN 2026-11-19).

Two gene-bearing strain names are substrings of others:
  'Alteromonas mediterranea AltDE'  ⊂  'Alteromonas mediterranea AltDE1'
  'Prochlorococcus PAC1'            ⊂  'Prochlorococcus EQPAC1'
Before 2.8 single-organism tools raised "matches multiple organisms" on the
exact name, and discovery tools pooled both strains. These tests pin that an
exact canonical name now selects exactly one strain everywhere, while a genus
('Alteromonas') still pools and '9312' still resolves (tier 3).

Exemplars (discovery Cypher, dev KG 2026-11-19):
  MATCH (o:OrganismTaxon) WHERE o.preferred_name IN [...] RETURN
    o.preferred_name, o.gene_count
    -> AltDE 3817, AltDE1 4238, PAC1 2317, EQPAC1 1990
  MATCH (g:Gene) WHERE g.organism_name IN ['Prochlorococcus PAC1',
    'Prochlorococcus EQPAC1'] AND toLower(g.product) CONTAINS 'photosystem'
    RETURN g.organism_name, count(*)              -> PAC1 53, EQPAC1 45
  MATCH (e:Experiment) WHERE e.organism_name IN [PAC1, EQPAC1]
    RETURN e.id                                   -> one each (BIOINFORMATIC)
  MATCH (d:DerivedMetric) ... same two          -> 2 each
  MATCH (g:Gene) WHERE g.gene_name = 'psbA'     -> EV03_2285 (PAC1),
                                                   PROCH_1994 (EQPAC1)
  urea (kegg.compound:C00086) metabolism genes  -> AltDE 5, AltDE1 2,
                                                   PAC1 4, EQPAC1 4
  eggnog:46530@72275 has members in AltDE and AltDE1
  MADE_1000015 (dnaN) is an AltDE gene
  MATCH (p:Publication) WHERE 'Phage' IN p.organisms RETURN count(p) -> 5
  'Escherichia coli' is an OrganismTaxon with gene_count 0.
  No Changes_expression_of edges for PAC1 / AltDE (DE by gene → 0 rows).

All tests are `-m kg`. RED until 2.8 lands for the leak / raise cases;
the genus-pooling and '9312' cases may already be green.
"""

import pytest

from multiomics_explorer.api import functions as api
from multiomics_explorer.kg.queries_lib import (
    build_resolve_organism_for_organism,
)

PAC1 = "Prochlorococcus PAC1"
EQPAC1 = "Prochlorococcus EQPAC1"
ALTDE = "Alteromonas mediterranea AltDE"
ALTDE1 = "Alteromonas mediterranea AltDE1"
UREA = "kegg.compound:C00086"
ALT_GROUP = "eggnog:46530@72275"
ALTDE_TAG = "MADE_1000015"

pytestmark = pytest.mark.kg


def _resolve(conn, organism):
    cypher, params = build_resolve_organism_for_organism(organism=organism)
    rows = conn.execute_query(cypher, **params)
    assert len(rows) == 1, "resolver must always return exactly one row"
    return rows[0]


def _row_orgs(result, key="organism_name"):
    return {r[key] for r in result["results"]}


# ---------------------------------------------------------------------------
# §1 resolver tiers
# ---------------------------------------------------------------------------


class TestResolverTiersLive:
    @pytest.mark.parametrize("text,expected", [
        (PAC1, [PAC1]),
        (ALTDE, [ALTDE]),
        ("PAC1", [PAC1]),
        ("AltDE", [ALTDE]),
        ("pac1", [PAC1]),
        ("  Prochlorococcus PAC1  ", [PAC1]),
        ("9312", ["Prochlorococcus MIT9312"]),
        ("MED4", ["Prochlorococcus MED4"]),
    ])
    def test_single_strain(self, conn, text, expected):
        row = _resolve(conn, text)
        assert row["organisms"] == expected

    @pytest.mark.parametrize("text,tier", [
        (PAC1, 1), (ALTDE, 1), ("PAC1", 2), ("AltDE", 2), ("9312", 3),
    ])
    def test_match_tier(self, conn, text, tier):
        assert _resolve(conn, text)["match_tier"] == tier

    def test_genus_pools_all_alteromonas(self, conn):
        row = _resolve(conn, "alteromonas")
        assert len(row["organisms"]) >= 11
        assert ALTDE in row["organisms"] and ALTDE1 in row["organisms"]
        assert all("Alteromonas" in o for o in row["organisms"])
        assert "Alteromonas" in row["geneless_matches"]

    def test_geneless_taxon(self, conn):
        row = _resolve(conn, "Escherichia coli")
        assert row["organisms"] == []
        assert "Escherichia coli" in row["geneless_matches"]

    def test_no_match_one_row(self, conn):
        row = _resolve(conn, "Bogus")
        assert row["organisms"] == []
        assert row["geneless_matches"] == []
        assert row["match_tier"] is None


# ---------------------------------------------------------------------------
# §4 discovery / filter tools: exact name → only that strain
# ---------------------------------------------------------------------------


class TestDiscoveryToolsSelectOneStrain:
    def test_genes_by_function(self, conn):
        r = api.genes_by_function("photosystem", organism=PAC1, limit=500,
                                  conn=conn)
        assert r["total_matching"] > 0
        assert _row_orgs(r) == {PAC1}
        assert {b["organism_name"] for b in r["by_organism"]} == {PAC1}

    def test_list_experiments(self, conn):
        r = api.list_experiments(organism=PAC1, conn=conn)
        assert r["total_matching"] >= 1
        assert _row_orgs(r) == {PAC1}

    def test_list_derived_metrics(self, conn):
        r = api.list_derived_metrics(organism=PAC1, conn=conn)
        assert r["total_matching"] >= 1
        assert _row_orgs(r) == {PAC1}

    def test_genes_by_categorical_metric(self, conn):
        # Review finding: the DM drill-downs filtered diagnostics with a
        # Python word match, so PAC1 also pulled EQPAC1's sbp DM.
        r = api.genes_by_categorical_metric(
            metric_types=["sbp_nutrient_class"], organism=PAC1,
            summary=True, conn=conn)
        assert r["total_matching"] >= 1
        assert {b["organism_name"] for b in r["by_organism"]} == {PAC1}

    def test_list_organisms(self, conn):
        r = api.list_organisms(organism_names=[PAC1], conn=conn)
        assert _row_orgs(r) == {PAC1}

    def test_list_organisms_short_name(self, conn):
        r = api.list_organisms(organism_names=["AltDE"], conn=conn)
        assert _row_orgs(r) == {ALTDE}

    def test_resolve_gene(self, conn):
        r = api.resolve_gene("psbA", organism=PAC1, conn=conn)
        assert [x["locus_tag"] for x in r["results"]] == ["EV03_2285"]
        assert _row_orgs(r) == {PAC1}

    def test_genes_by_homolog_group(self, conn):
        r = api.genes_by_homolog_group([ALT_GROUP], organisms=[ALTDE],
                                       conn=conn)
        assert r["total_matching"] > 0
        assert _row_orgs(r) == {ALTDE}
        assert r["not_found_organisms"] == []
        assert r["not_matched_organisms"] == []

    def test_genes_by_homolog_group_unresolved_entry_not_found(self, conn):
        r = api.genes_by_homolog_group([ALT_GROUP], organisms=[ALTDE, "Bogus"],
                                       conn=conn)
        assert _row_orgs(r) == {ALTDE}
        assert r["not_found_organisms"] == ["Bogus"]


# ---------------------------------------------------------------------------
# Single-organism tools: exact name accepted (no ambiguity raise)
# ---------------------------------------------------------------------------


class TestSingleOrganismToolsAcceptExactName:
    def test_genes_by_metabolite(self, conn):
        r = api.genes_by_metabolite(metabolite_ids=[UREA], organism=ALTDE,
                                    conn=conn)
        assert r["total_matching"] > 0
        assert r["results"]
        # rows carry no organism field: AltDE tags are MADE_*, AltDE1 amad1_*
        assert all(x["locus_tag"].startswith("MADE_") for x in r["results"])

    def test_metabolites_by_gene(self, conn):
        r = api.metabolites_by_gene(locus_tags=[ALTDE_TAG], organism=ALTDE,
                                    conn=conn)
        assert "results" in r

    def test_differential_expression_by_gene(self, conn):
        r = api.differential_expression_by_gene(organism=PAC1, conn=conn)
        assert r["organism_name"] == PAC1
        assert r["total_matching"] == 0  # no expression edges for PAC1

    def test_genes_by_ontology(self, conn):
        r = api.genes_by_ontology(ontology="kegg", level=1, organism=PAC1,
                                  summary=True, conn=conn)
        assert r["total_matching"] > 0

    def test_kegg_module_completeness(self, conn):
        r = api.kegg_module_completeness(organism=ALTDE, conn=conn,
                                         limit=500)
        assert r["results"]
        assert {x["organism_name"] for x in r["results"]} == {ALTDE}

    def test_ontology_landscape(self, conn):
        r = api.ontology_landscape(organism=PAC1, ontology="go_bp",
                                   conn=conn)
        assert r["results"]

    @pytest.mark.parametrize("call", [
        lambda c: api.differential_expression_by_gene(
            organism="Escherichia coli", conn=c),
        lambda c: api.genes_by_ontology(
            ontology="kegg", level=1, organism="Escherichia coli",
            summary=True, conn=c),
    ], ids=["de_by_gene", "genes_by_ontology"])
    def test_geneless_taxon_raises_specific_message(self, conn, call):
        with pytest.raises(ValueError) as exc:
            call(conn)
        msg = str(exc.value)
        assert "taxon without genes" in msg
        assert "list_organisms" in msg

    def test_genus_still_ambiguous_on_single_organism_tool(self, conn):
        """Decision 3: single-organism tools keep raising on ambiguity."""
        with pytest.raises(ValueError, match="matches multiple organisms"):
            api.differential_expression_by_gene(organism="Alteromonas",
                                                conn=conn)


# ---------------------------------------------------------------------------
# Back-compat: pooling + gene-less publication taxa
# ---------------------------------------------------------------------------


class TestBackCompat:
    def test_genus_pools_on_discovery_tool(self, conn):
        r = api.list_experiments(organism="Alteromonas", summary=True,
                                 conn=conn)
        orgs = {b["organism_name"] for b in r["by_organism"]}
        assert len(orgs) >= 2
        assert all(o.startswith("Alteromonas") for o in orgs)

    def test_genus_pools_genes_by_function(self, conn):
        r = api.genes_by_function("DNA polymerase", organism="Alteromonas",
                                  summary=True, conn=conn)
        orgs = {b["organism_name"] for b in r["by_organism"]}
        assert len(orgs) >= 2

    def test_9312_still_resolves_on_discovery_tool(self, conn):
        r = api.genes_by_function("photosystem", organism="9312",
                                  limit=50, conn=conn)
        assert r["total_matching"] > 0
        assert _row_orgs(r) == {"Prochlorococcus MIT9312"}

    def test_list_publications_phage(self, conn):
        r = api.list_publications(organism="Phage", conn=conn)
        assert r["total_matching"] == 5

    def test_list_publications_exact_strain(self, conn):
        r = api.list_publications(organism=PAC1, conn=conn)
        assert r["total_matching"] >= 1
        for row in r["results"]:
            assert PAC1 in row["organisms"]
