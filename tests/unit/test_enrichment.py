"""Unit tests for multiomics_explorer.analysis.enrichment."""
from __future__ import annotations

import pytest


class TestEnrichmentInputs:
    def test_importable_from_top_level(self):
        from multiomics_explorer import EnrichmentInputs
        assert EnrichmentInputs is not None

    def test_construct_with_required_fields(self):
        from multiomics_explorer import EnrichmentInputs
        obj = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"exp1|T0|up": ["PMM0001"]},
            background={"exp1|T0|up": ["PMM0001", "PMM0002"]},
            cluster_metadata={"exp1|T0|up": {"experiment_id": "exp1"}},
        )
        assert obj.organism_name == "MED4"
        assert obj.not_found == []
        assert obj.not_matched == []
        assert obj.no_expression == []

    def test_buckets_accept_explicit_values(self):
        from multiomics_explorer import EnrichmentInputs
        obj = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={},
            background={},
            cluster_metadata={},
            not_found=["missing_exp"],
            not_matched=["wrong_org_exp"],
            no_expression=["empty_de_exp"],
        )
        assert obj.not_found == ["missing_exp"]
        assert obj.not_matched == ["wrong_org_exp"]
        assert obj.no_expression == ["empty_de_exp"]

    def test_gene_stats_default_empty(self):
        from multiomics_explorer import EnrichmentInputs
        obj = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={}, background={}, cluster_metadata={},
        )
        assert obj.gene_stats == {}

    def test_gene_stats_populated(self):
        from multiomics_explorer import EnrichmentInputs, DEStats
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"c1": ["PMM0001"]},
            background={"c1": ["PMM0001"]},
            cluster_metadata={"c1": {}},
            gene_stats={
                "c1": {
                    "PMM0001": DEStats(
                        log2fc=1.5, padj=0.01, direction="up", significant=True,
                    ),
                },
            },
        )
        assert inputs.gene_stats["c1"]["PMM0001"].log2fc == 1.5


import math
import pandas as pd


class TestFisherOra:
    @staticmethod
    def _term2gene_simple():
        """One pathway P with 3 members, one pathway Q with 6 members."""
        rows = [
            {"term_id": "P", "term_name": "Pathway P", "locus_tag": "g1"},
            {"term_id": "P", "term_name": "Pathway P", "locus_tag": "g2"},
            {"term_id": "P", "term_name": "Pathway P", "locus_tag": "g3"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g4"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g5"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g6"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g7"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g8"},
            {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g9"},
        ]
        return pd.DataFrame(rows)

    def test_missing_required_columns_raises(self):
        from multiomics_explorer import fisher_ora, EnrichmentInputs
        bad = pd.DataFrame([{"term_id": "P", "locus_tag": "g1"}])  # no term_name
        inputs = EnrichmentInputs(
            organism_name="test",
            gene_sets={"c1": ["g1"]},
            background={"c1": ["g1", "g2"]},
            cluster_metadata={"c1": {}},
        )
        with pytest.raises(ValueError, match="term_name"):
            fisher_ora(inputs, bad)

    def test_extra_columns_pass_through(self):
        from multiomics_explorer import fisher_ora, EnrichmentInputs
        t2g = self._term2gene_simple().assign(level=1, extra="x")
        inputs = EnrichmentInputs(
            organism_name="test",
            gene_sets={"c1": ["g1", "g2"]},
            background={"c1": ["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "g9", "g10"]},
            cluster_metadata={"c1": {}},
        )
        result = fisher_ora(inputs, t2g)
        df = result.results
        assert "level" in df.columns
        assert "extra" in df.columns

    def test_basic_enrichment_math(self):
        """A pathway enriched with 2/2 DE hits out of 3 members in a 10-gene background."""
        from multiomics_explorer import fisher_ora, EnrichmentInputs
        t2g = self._term2gene_simple()
        # Background has all 9 pathway members + 11 others = 20 genes.
        bg = ["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "g9"] + [f"x{i}" for i in range(11)]
        inputs = EnrichmentInputs(
            organism_name="test",
            gene_sets={"c1": ["g1", "g2"]},
            background={"c1": bg},
            cluster_metadata={"c1": {}},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        df = result.results
        # Two pathways: P (size 3, 2 hits); Q (size 6, 0 hits).
        assert set(df["term_id"]) == {"P", "Q"}
        p_row = df[df["term_id"] == "P"].iloc[0]
        assert p_row["count"] == 2
        assert p_row["bg_count"] == 3
        assert p_row["gene_ratio"] == "2/2"
        assert p_row["bg_ratio"] == "3/20"
        assert p_row["cluster"] == "c1"
        # Fisher's exact one-sided reference for [[2, 0], [1, 17]]:
        # scipy.stats.fisher_exact(..., alternative='greater')
        import scipy.stats as stats
        expected_p = stats.fisher_exact([[2, 0], [1, 17]], alternative="greater").pvalue
        assert math.isclose(p_row["pvalue"], expected_p, rel_tol=1e-9)

    def test_per_cluster_M_filter(self):
        """A pathway is tested in cluster A (M=3 >= min=3) but filtered in cluster B (M=1)."""
        from multiomics_explorer import fisher_ora, EnrichmentInputs
        t2g = self._term2gene_simple()
        bg_a = ["g1", "g2", "g3"] + [f"x{i}" for i in range(10)]
        bg_b = ["g1"] + [f"y{i}" for i in range(10)]  # only g1 is a P member in bg_b
        inputs = EnrichmentInputs(
            organism_name="test",
            gene_sets={"A": ["g1"], "B": ["g1"]},
            background={"A": bg_a, "B": bg_b},
            cluster_metadata={"A": {}, "B": {}},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=3, max_gene_set_size=None)
        df = result.results
        p_clusters = set(df[df["term_id"] == "P"]["cluster"])
        assert "A" in p_clusters
        assert "B" not in p_clusters  # M=1 < min=3 for cluster B

    def test_bh_per_cluster(self):
        """BH correction is within cluster, not across clusters."""
        from multiomics_explorer import fisher_ora, EnrichmentInputs
        import statsmodels.stats.multitest as mt
        t2g = self._term2gene_simple()
        bg = ["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "g9"] + [f"x{i}" for i in range(11)]
        inputs = EnrichmentInputs(
            organism_name="test",
            gene_sets={"c1": ["g1", "g2"], "c2": ["g5", "g6"]},
            background={"c1": bg, "c2": bg},
            cluster_metadata={"c1": {}, "c2": {}},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        df = result.results
        for cluster in ("c1", "c2"):
            sub = df[df["cluster"] == cluster].sort_values("term_id")
            pvals = sub["pvalue"].tolist()
            expected = mt.multipletests(pvals, method="fdr_bh")[1]
            assert list(sub["p_adjust"]) == pytest.approx(list(expected))

    def test_global_sort_by_padj(self):
        """Output rows globally sorted by p_adjust asc, tie-break cluster then term_id."""
        from multiomics_explorer import fisher_ora, EnrichmentInputs
        t2g = self._term2gene_simple()
        bg = ["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "g9"] + [f"x{i}" for i in range(11)]
        inputs = EnrichmentInputs(
            organism_name="test",
            gene_sets={"c2": ["g1"], "c1": ["g4", "g5", "g6", "g7"]},
            background={"c2": bg, "c1": bg},
            cluster_metadata={"c2": {}, "c1": {}},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        df = result.results
        padjs = df["p_adjust"].tolist()
        assert padjs == sorted(padjs)

    def test_max_gene_set_size_none_disables_upper_bound(self):
        from multiomics_explorer import fisher_ora, EnrichmentInputs
        t2g = self._term2gene_simple()
        bg = ["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "g9"]
        inputs = EnrichmentInputs(
            organism_name="test",
            gene_sets={"c1": ["g4"]},
            background={"c1": bg},
            cluster_metadata={"c1": {}},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0, max_gene_set_size=None)
        df = result.results
        assert "Q" in set(df["term_id"])

    def test_fold_enrichment_rich_factor_computed(self):
        from multiomics_explorer import fisher_ora, EnrichmentInputs
        t2g = self._term2gene_simple()
        bg = ["g1", "g2", "g3"] + [f"x{i}" for i in range(17)]
        inputs = EnrichmentInputs(
            organism_name="test",
            gene_sets={"c1": ["g1", "g2"]},
            background={"c1": bg},
            cluster_metadata={"c1": {}},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        df = result.results
        p_row = df[df["term_id"] == "P"].iloc[0]
        assert math.isclose(p_row["rich_factor"], 2 / 3, rel_tol=1e-9)
        assert math.isclose(p_row["fold_enrichment"], (2 / 2) / (3 / 20), rel_tol=1e-9)


import numpy as np


class TestSignedEnrichmentScore:
    def test_importable_from_top_level(self):
        from multiomics_explorer import signed_enrichment_score
        assert signed_enrichment_score is not None

    def test_both_directions_dominant_wins(self):
        """Up and down both significant — sign from smaller p_adjust wins."""
        from multiomics_explorer import signed_enrichment_score
        df = pd.DataFrame([
            {"cluster": "exp1|T0|up",   "direction": "up",   "term_id": "P", "p_adjust": 1e-8},
            {"cluster": "exp1|T0|down", "direction": "down", "term_id": "P", "p_adjust": 1e-3},
        ])
        out = signed_enrichment_score(df)
        assert len(out) == 1
        row = out.iloc[0]
        assert row["signed_score"] == pytest.approx(-math.log10(1e-8))
        assert row["term_id"] == "P"

    def test_down_only(self):
        from multiomics_explorer import signed_enrichment_score
        df = pd.DataFrame([
            {"cluster": "exp1|T0|down", "direction": "down", "term_id": "Q", "p_adjust": 1e-4},
        ])
        out = signed_enrichment_score(df)
        assert len(out) == 1
        assert out.iloc[0]["signed_score"] == pytest.approx(math.log10(1e-4))

    def test_up_only(self):
        from multiomics_explorer import signed_enrichment_score
        df = pd.DataFrame([
            {"cluster": "exp1|T0|up", "direction": "up", "term_id": "R", "p_adjust": 1e-5},
        ])
        out = signed_enrichment_score(df)
        assert out.iloc[0]["signed_score"] == pytest.approx(-math.log10(1e-5))

    def test_multiple_clusters_preserved(self):
        """Different (exp, tp) pairs stay as separate rows per pathway."""
        from multiomics_explorer import signed_enrichment_score
        df = pd.DataFrame([
            {"cluster": "exp1|T0|up", "direction": "up", "term_id": "P", "p_adjust": 1e-2},
            {"cluster": "exp2|T0|up", "direction": "up", "term_id": "P", "p_adjust": 1e-3},
        ])
        out = signed_enrichment_score(df)
        assert len(out) == 2
        assert set(out["cluster_stem"]) == {"exp1|T0", "exp2|T0"}


from unittest.mock import MagicMock


class TestDeEnrichmentInputs:
    def test_importable_from_top_level(self):
        from multiomics_explorer import de_enrichment_inputs
        assert de_enrichment_inputs is not None

    def test_partition_into_clusters(self, monkeypatch):
        from multiomics_explorer import de_enrichment_inputs
        de_result = {
            "organism_name": "MED4",
            "results": [
                {"locus_tag": "PMM0001", "experiment_id": "exp1",
                 "timepoint": "T0", "timepoint_hours": 24.0, "timepoint_order": 1,
                 "direction": "up", "significant": True,
                 "omics_type": "transcriptomics",
                 "table_scope": "rna_all",
                 "treatment_type": ["N_stress"],
                 "background_factors": None,
                 "is_time_course": True,
                 "experiment_name": "exp1_name"},
                {"locus_tag": "PMM0002", "experiment_id": "exp1",
                 "timepoint": "T0", "timepoint_hours": 24.0, "timepoint_order": 1,
                 "direction": "down", "significant": True,
                 "omics_type": "transcriptomics",
                 "table_scope": "rna_all",
                 "treatment_type": ["N_stress"],
                 "background_factors": None,
                 "is_time_course": True,
                 "experiment_name": "exp1_name"},
            ],
            "not_found": [],
            "no_expression": [],
        }
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(enr, "_call_de", lambda **_: de_result)

        out = de_enrichment_inputs(
            experiment_ids=["exp1"],
            organism="MED4",
            direction="both",
            significant_only=True,
        )
        assert out.organism_name == "MED4"
        assert set(out.gene_sets.keys()) == {"exp1|T0|up", "exp1|T0|down"}
        assert out.gene_sets["exp1|T0|up"] == ["PMM0001"]
        assert out.gene_sets["exp1|T0|down"] == ["PMM0002"]
        md = out.cluster_metadata["exp1|T0|up"]
        assert md["experiment_id"] == "exp1"
        assert md["timepoint_hours"] == 24.0
        assert md["omics_type"] == "transcriptomics"
        assert md["treatment_type"] == ["N_stress"]

    def test_nan_timepoint_bucketed_as_NA(self, monkeypatch):
        from multiomics_explorer import de_enrichment_inputs
        de_result = {
            "organism_name": "MED4",
            "results": [
                {"locus_tag": "PMM0001", "experiment_id": "exp1",
                 "timepoint": None, "timepoint_hours": math.nan, "timepoint_order": None,
                 "direction": "up", "significant": True,
                 "omics_type": "transcriptomics", "table_scope": "rna_all",
                 "treatment_type": ["cyanate"], "background_factors": None,
                 "is_time_course": False, "experiment_name": "steglich"},
            ],
            "not_found": [], "no_expression": [],
        }
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(enr, "_call_de", lambda **_: de_result)
        out = de_enrichment_inputs(
            experiment_ids=["exp1"], organism="MED4",
        )
        assert "exp1|NA|up" in out.gene_sets

    def test_buckets_populated_from_de(self, monkeypatch):
        from multiomics_explorer import de_enrichment_inputs
        de_result = {
            "organism_name": "MED4",
            "results": [],
            "not_found": ["missing_exp"],
            "no_expression": ["empty_de_exp"],
        }
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(enr, "_call_de", lambda **_: de_result)
        out = de_enrichment_inputs(
            experiment_ids=["missing_exp", "empty_de_exp"], organism="MED4",
        )
        assert out.not_found == ["missing_exp"]
        assert out.no_expression == ["empty_de_exp"]

    def test_timepoint_filter_applied(self, monkeypatch):
        from multiomics_explorer import de_enrichment_inputs
        de_result = {
            "organism_name": "MED4",
            "results": [
                {"locus_tag": "PMM0001", "experiment_id": "exp1",
                 "timepoint": "T0", "timepoint_hours": 0.0, "timepoint_order": 0,
                 "direction": "up", "significant": True,
                 "omics_type": "transcriptomics", "table_scope": "rna_all",
                 "treatment_type": None, "background_factors": None,
                 "is_time_course": True, "experiment_name": "exp1_name"},
                {"locus_tag": "PMM0002", "experiment_id": "exp1",
                 "timepoint": "T4", "timepoint_hours": 24.0, "timepoint_order": 4,
                 "direction": "up", "significant": True,
                 "omics_type": "transcriptomics", "table_scope": "rna_all",
                 "treatment_type": None, "background_factors": None,
                 "is_time_course": True, "experiment_name": "exp1_name"},
            ],
            "not_found": [], "no_expression": [],
        }
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(enr, "_call_de", lambda **_: de_result)
        out = de_enrichment_inputs(
            experiment_ids=["exp1"], organism="MED4",
            timepoint_filter=["T4"],
        )
        assert set(out.gene_sets.keys()) == {"exp1|T4|up"}

    def test_gene_stats_populated_for_all_measured_genes(self, monkeypatch):
        """gene_stats includes measured genes regardless of significance."""
        from multiomics_explorer import de_enrichment_inputs
        from multiomics_explorer.analysis import enrichment as _mod

        fake_rows = [
            {"locus_tag": "g1", "experiment_id": "E1", "timepoint": "T0",
             "direction": "up", "significant": True,
             "log2fc": 2.0, "padj": 0.001, "rank": 1,
             "organism_name": "MED4"},
            {"locus_tag": "g2", "experiment_id": "E1", "timepoint": "T0",
             "direction": "up", "significant": False,
             "log2fc": 0.5, "padj": 0.8, "rank": 50,
             "organism_name": "MED4"},
        ]
        monkeypatch.setattr(_mod, "_call_de", lambda **_: {
            "organism_name": "MED4", "results": fake_rows,
            "not_found": [], "not_matched": [], "no_expression": [],
        })
        out = de_enrichment_inputs(
            experiment_ids=["E1"],
            organism="MED4",
            direction="both",
            significant_only=True,
        )
        cluster = "E1|T0|up"
        assert cluster in out.gene_stats
        assert "g1" in out.gene_stats[cluster]
        assert "g2" in out.gene_stats[cluster]
        assert out.gene_stats[cluster]["g1"].log2fc == 2.0
        assert out.gene_stats[cluster]["g1"].significant is True
        assert out.gene_stats[cluster]["g2"].significant is False


import inspect
import re


class TestDocstringCoverage:
    """Public enrichment API must carry NumPy-style docstrings."""

    PUBLIC_NAMES = [
        "EnrichmentInputs",
        "de_enrichment_inputs",
        "fisher_ora",
        "signed_enrichment_score",
    ]

    REQUIRED_SECTIONS = {
        "EnrichmentInputs": [],  # Pydantic model - per-field descriptions checked elsewhere
        "de_enrichment_inputs": ["Parameters", "Returns", "Raises", "Examples", "See Also"],
        "fisher_ora": ["Parameters", "Returns", "Raises", "Examples", "See Also"],
        "signed_enrichment_score": ["Parameters", "Returns", "Examples", "See Also"],
    }

    def test_every_public_name_has_docstring(self):
        import multiomics_explorer as me
        for name in self.PUBLIC_NAMES:
            obj = getattr(me, name)
            assert obj.__doc__ is not None, f"{name} missing docstring"
            assert len(obj.__doc__.strip()) > 20, (
                f"{name} docstring too short: {obj.__doc__!r}"
            )

    def test_required_sections_present(self):
        import multiomics_explorer as me
        for name, sections in self.REQUIRED_SECTIONS.items():
            obj = getattr(me, name)
            doc = obj.__doc__ or ""
            for section in sections:
                pattern = rf"^{re.escape(section)}\s*$\s*^-+\s*$"
                assert re.search(pattern, doc, re.MULTILINE), (
                    f"{name} docstring missing section '{section}'"
                )

    def test_every_parameter_documented_for_functions(self):
        import multiomics_explorer as me
        for name in ["de_enrichment_inputs", "fisher_ora", "signed_enrichment_score"]:
            fn = getattr(me, name)
            sig = inspect.signature(fn)
            doc = fn.__doc__ or ""
            for param in sig.parameters:
                if param in {"self", "cls"} or param.startswith("_"):
                    continue
                assert re.search(rf"\b{re.escape(param)}\b", doc), (
                    f"{name} signature parameter '{param}' not documented in docstring"
                )
