"""Unit tests for EnrichmentResult and associated Pydantic models."""
from __future__ import annotations

import pytest


class TestDEStats:
    def test_importable(self):
        from multiomics_explorer import DEStats
        assert DEStats is not None

    def test_construct_with_required_fields(self):
        from multiomics_explorer import DEStats
        stats = DEStats(
            log2fc=1.5,
            padj=0.01,
            direction="up",
            significant=True,
        )
        assert stats.log2fc == 1.5
        assert stats.padj == 0.01
        assert stats.direction == "up"
        assert stats.significant is True
        assert stats.rank is None

    def test_rank_optional(self):
        from multiomics_explorer import DEStats
        stats = DEStats(
            log2fc=1.5, padj=0.01, direction="up", significant=True, rank=3,
        )
        assert stats.rank == 3

    def test_direction_literal_validates(self):
        from multiomics_explorer import DEStats
        with pytest.raises(Exception):  # pydantic ValidationError
            DEStats(log2fc=1.5, padj=0.01, direction="invalid", significant=True)

    def test_field_descriptions_present(self):
        from multiomics_explorer import DEStats
        for name, field in DEStats.model_fields.items():
            assert field.description, f"DEStats.{name} missing description"


class TestGeneRef:
    def test_importable(self):
        from multiomics_explorer import GeneRef
        assert GeneRef is not None

    def test_minimal_construction(self):
        from multiomics_explorer import GeneRef
        ref = GeneRef(locus_tag="PMM0712")
        assert ref.locus_tag == "PMM0712"
        assert ref.gene_name is None
        assert ref.product is None
        assert ref.log2fc is None

    def test_full_construction(self):
        from multiomics_explorer import GeneRef
        ref = GeneRef(
            locus_tag="PMM0712",
            gene_name="pstS",
            product="phosphate ABC transporter",
            log2fc=2.0,
            padj=0.001,
            rank=1,
            direction="up",
            significant=True,
        )
        assert ref.gene_name == "pstS"
        assert ref.rank == 1

    def test_field_descriptions_present(self):
        from multiomics_explorer import GeneRef
        for name, field in GeneRef.model_fields.items():
            assert field.description, f"GeneRef.{name} missing description"


class TestEnrichmentExplanation:
    def test_importable(self):
        from multiomics_explorer import EnrichmentExplanation
        assert EnrichmentExplanation is not None

    def test_minimal_construction(self):
        from multiomics_explorer import EnrichmentExplanation
        exp = EnrichmentExplanation(
            cluster="c1",
            term_id="GO:0006810",
            term_name="transport",
            cluster_kind="pathway",
            cluster_metadata={"experiment_id": "EXP042"},
            count=2,
            n_foreground=10,
            bg_count=20,
            n_background=100,
            gene_ratio="2/10",
            bg_ratio="20/100",
            fold_enrichment=1.0,
            rich_factor=0.1,
            pvalue=0.05,
            p_adjust=0.10,
            rank_in_cluster=3,
            n_terms_in_cluster=50,
            overlap_genes=[],
            background_genes=[],
        )
        assert exp.cluster == "c1"
        assert exp.overlap_preview_n == 10  # default

    def test_cluster_kind_literal_validates(self):
        from multiomics_explorer import EnrichmentExplanation
        with pytest.raises(Exception):
            EnrichmentExplanation(
                cluster="c1", term_id="t", term_name="tn",
                cluster_kind="invalid",  # not in Literal
                cluster_metadata={}, count=0, n_foreground=0,
                bg_count=0, n_background=0,
                gene_ratio="0/0", bg_ratio="0/0",
                fold_enrichment=0.0, rich_factor=0.0,
                pvalue=1.0, p_adjust=1.0,
                rank_in_cluster=1, n_terms_in_cluster=1,
                overlap_genes=[], background_genes=[],
            )

    def test_field_descriptions_present(self):
        from multiomics_explorer import EnrichmentExplanation
        for name, field in EnrichmentExplanation.model_fields.items():
            assert field.description, f"EnrichmentExplanation.{name} missing description"


import pandas as pd


class TestFisherOraReturnsResult:
    def test_returns_enrichment_result(self):
        from multiomics_explorer import (
            EnrichmentInputs, EnrichmentResult, fisher_ora,
        )
        t2g = pd.DataFrame([
            {"term_id": "P", "term_name": "P", "locus_tag": "g1"},
            {"term_id": "P", "term_name": "P", "locus_tag": "g2"},
            {"term_id": "P", "term_name": "P", "locus_tag": "g3"},
        ])
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"c1": ["g1", "g2"]},
            background={"c1": ["g1", "g2", "g3", "g4", "g5"]},
            cluster_metadata={"c1": {}},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        assert isinstance(result, EnrichmentResult)
        assert result.kind == "pathway"
        assert result.organism_name == "MED4"
        assert not result.results.empty
        assert result.inputs is inputs
        assert result.term2gene is t2g


def _build_simple_result():
    """Tiny hand-rolled EnrichmentResult with 2 clusters, 2 terms.

    Clusters:
      c1: foreground = [g1, g2]; background = [g1, g2, g3, g4, g5, g6] (6 genes)
      c2: foreground = [g1];     background = [g1, g2, g3, g4, g5, g6]

    Terms:
      P: members = [g1, g2, g3]  -- enriched in c1 (overlap: g1, g2)
      Q: members = [g4, g5]      -- no overlap with c1 foreground

    gene_name / product populated for g1 (named 'geneA') and g3 (named 'geneC');
    g2, g4, g5, g6 are unnamed.

    gene_stats populated for c1 only (pathway-kind demo).
    """
    from multiomics_explorer import (
        EnrichmentInputs, EnrichmentResult, fisher_ora, DEStats,
    )

    term2gene = pd.DataFrame([
        {"term_id": "P", "term_name": "Pathway P", "locus_tag": "g1",
         "gene_name": "geneA", "product": "productA"},
        {"term_id": "P", "term_name": "Pathway P", "locus_tag": "g2",
         "gene_name": None, "product": None},
        {"term_id": "P", "term_name": "Pathway P", "locus_tag": "g3",
         "gene_name": "geneC", "product": "productC"},
        {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g4",
         "gene_name": None, "product": None},
        {"term_id": "Q", "term_name": "Pathway Q", "locus_tag": "g5",
         "gene_name": None, "product": None},
    ])

    inputs = EnrichmentInputs(
        organism_name="MED4",
        gene_sets={"c1": ["g1", "g2"], "c2": ["g1"]},
        background={
            "c1": ["g1", "g2", "g3", "g4", "g5", "g6"],
            "c2": ["g1", "g2", "g3", "g4", "g5", "g6"],
        },
        cluster_metadata={
            "c1": {"experiment_id": "EXP042", "timepoint": "24h", "direction": "up"},
            "c2": {"experiment_id": "EXP042", "timepoint": "48h", "direction": "up"},
        },
        gene_stats={
            "c1": {
                "g1": DEStats(log2fc=2.0, padj=0.001, direction="up",
                              significant=True, rank=1),
                "g2": DEStats(log2fc=1.5, padj=0.01, direction="up",
                              significant=True, rank=2),
                "g3": DEStats(log2fc=0.2, padj=0.8, direction="none",
                              significant=False),
            },
        },
    )

    result = fisher_ora(inputs, term2gene, min_gene_set_size=0)
    return inputs, term2gene, result


class TestOverlapAndBackgroundGenes:
    def test_overlap_genes_intersection_and_content(self):
        inputs, t2g, result = _build_simple_result()
        overlap = result.overlap_genes("c1", "P")
        lts = [g.locus_tag for g in overlap]
        assert set(lts) == {"g1", "g2"}

    def test_overlap_genes_sort_named_first(self):
        inputs, t2g, result = _build_simple_result()
        overlap = result.overlap_genes("c1", "P")
        assert overlap[0].locus_tag == "g1"
        assert overlap[0].gene_name == "geneA"
        assert overlap[1].locus_tag == "g2"
        assert overlap[1].gene_name is None

    def test_background_genes_intersection(self):
        inputs, t2g, result = _build_simple_result()
        bg = result.background_genes("c1", "P")
        lts = [g.locus_tag for g in bg]
        assert set(lts) == {"g1", "g2", "g3"}

    def test_background_genes_sort_named_by_rank(self):
        inputs, t2g, result = _build_simple_result()
        bg = result.background_genes("c1", "P")
        # Named genes: g1 (rank 1), g3 (no rank in gene_stats -> falls back to name)
        named = [g for g in bg if g.gene_name is not None]
        assert named[0].locus_tag == "g1"
        assert named[1].locus_tag == "g3"

    def test_gene_stats_populated_for_measured_gene(self):
        inputs, t2g, result = _build_simple_result()
        overlap = result.overlap_genes("c1", "P")
        g1 = next(g for g in overlap if g.locus_tag == "g1")
        assert g1.log2fc == 2.0
        assert g1.rank == 1
        assert g1.direction == "up"

    def test_gene_stats_none_for_unmeasured_gene(self):
        inputs, t2g, result = _build_simple_result()
        overlap = result.overlap_genes("c2", "P")
        g1 = next(g for g in overlap if g.locus_tag == "g1")
        assert g1.log2fc is None
        assert g1.rank is None

    def test_nonexistent_cluster_raises(self):
        inputs, t2g, result = _build_simple_result()
        with pytest.raises(KeyError, match="nonexistent"):
            result.overlap_genes("nonexistent", "P")

    def test_nonexistent_term_raises(self):
        inputs, t2g, result = _build_simple_result()
        with pytest.raises(KeyError, match="NOTERM"):
            result.overlap_genes("c1", "NOTERM")

    def test_missing_optional_columns(self):
        from multiomics_explorer import EnrichmentInputs, fisher_ora
        minimal = pd.DataFrame([
            {"term_id": "P", "term_name": "P", "locus_tag": "g1"},
            {"term_id": "P", "term_name": "P", "locus_tag": "g2"},
            {"term_id": "P", "term_name": "P", "locus_tag": "g3"},
        ])
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"c1": ["g1", "g2"]},
            background={"c1": ["g1", "g2", "g3", "g4", "g5"]},
            cluster_metadata={"c1": {}},
        )
        result = fisher_ora(inputs, minimal, min_gene_set_size=0)
        overlap = result.overlap_genes("c1", "P")
        assert all(g.gene_name is None for g in overlap)
        assert all(g.product is None for g in overlap)


class TestExplain:
    def test_explain_returns_explanation(self):
        from multiomics_explorer import EnrichmentExplanation
        inputs, t2g, result = _build_simple_result()
        exp = result.explain("c1", "P")
        assert isinstance(exp, EnrichmentExplanation)
        assert exp.cluster == "c1"
        assert exp.term_id == "P"
        assert exp.cluster_kind == "pathway"

    def test_explain_fisher_numbers(self):
        inputs, t2g, result = _build_simple_result()
        exp = result.explain("c1", "P")
        assert exp.count == 2
        assert exp.n_foreground == 2
        assert exp.bg_count == 3
        assert exp.n_background == 6
        assert exp.gene_ratio == "2/2"
        assert exp.bg_ratio == "3/6"

    def test_explain_overlap_gene_lists_populated(self):
        inputs, t2g, result = _build_simple_result()
        exp = result.explain("c1", "P")
        overlap_lts = [g.locus_tag for g in exp.overlap_genes]
        assert set(overlap_lts) == {"g1", "g2"}
        bg_lts = [g.locus_tag for g in exp.background_genes]
        assert set(bg_lts) == {"g1", "g2", "g3"}

    def test_explain_rank_in_cluster(self):
        inputs, t2g, result = _build_simple_result()
        exp_p = result.explain("c1", "P")
        assert exp_p.rank_in_cluster >= 1
        assert exp_p.n_terms_in_cluster >= 1

    def test_explain_missing_pair_raises(self):
        inputs, t2g, result = _build_simple_result()
        with pytest.raises(KeyError):
            result.explain("c1", "NOTERM")

    def test_explain_narrative_pathway_substrings(self):
        inputs, t2g, result = _build_simple_result()
        exp = result.explain("c1", "P")
        md = exp._repr_markdown_()
        assert "P" in md
        assert "Pathway P" in md
        assert "geneA" in md
        assert "2 of 2" in md or "2/2" in md
        assert "experiment EXP042" in md or "EXP042" in md

    def test_explain_narrative_falls_back_to_locus_tag_when_unnamed(self):
        from multiomics_explorer import EnrichmentInputs, fisher_ora
        minimal = pd.DataFrame([
            {"term_id": "P", "term_name": "P", "locus_tag": "g1"},
            {"term_id": "P", "term_name": "P", "locus_tag": "g2"},
            {"term_id": "P", "term_name": "P", "locus_tag": "g3"},
        ])
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"c1": ["g1", "g2"]},
            background={"c1": ["g1", "g2", "g3", "g4", "g5"]},
            cluster_metadata={"c1": {"experiment_id": "EXP01"}},
        )
        result = fisher_ora(inputs, minimal, min_gene_set_size=0)
        exp = result.explain("c1", "P")
        md = exp._repr_markdown_()
        assert "g1" in md


class TestNiceAccessors:
    def test_cluster_context_returns_metadata_plus_counts(self):
        inputs, t2g, result = _build_simple_result()
        ctx = result.cluster_context("c1")
        assert ctx["experiment_id"] == "EXP042"
        assert "n_tests" in ctx
        assert "n_significant" in ctx
        assert ctx["n_tests"] >= 1

    def test_why_skipped_none_for_active_cluster(self):
        inputs, t2g, result = _build_simple_result()
        assert result.why_skipped("c1") is None

    def test_why_skipped_returns_reason_for_skipped(self):
        from multiomics_explorer import (
            EnrichmentInputs, EnrichmentResult, fisher_ora,
        )
        t2g = pd.DataFrame([
            {"term_id": "P", "term_name": "P", "locus_tag": "g1"},
            {"term_id": "P", "term_name": "P", "locus_tag": "g2"},
            {"term_id": "P", "term_name": "P", "locus_tag": "g3"},
        ])
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"c1": ["g1"]},
            background={"c1": ["g1", "g2", "g3"]},
            cluster_metadata={"c1": {}, "c_skipped": {}},
            clusters_skipped=[
                {"cluster_name": "c_skipped", "reason": "below min_cluster_size"},
            ],
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        result.clusters_skipped = inputs.clusters_skipped
        assert result.why_skipped("c_skipped") == "below min_cluster_size"

    def test_missing_terms(self):
        inputs, t2g, result = _build_simple_result()
        result.term_validation = {
            "not_found": ["GO:FAKE"],
            "wrong_ontology": [],
            "wrong_level": [],
            "filtered_out": [],
        }
        missing = result.missing_terms()
        assert missing["not_found"] == ["GO:FAKE"]

    def test_to_compare_cluster_frame_columns(self):
        inputs, t2g, result = _build_simple_result()
        df = result.to_compare_cluster_frame()
        expected = {
            "Cluster", "ID", "Description", "GeneRatio", "BgRatio",
            "pvalue", "p.adjust", "geneID",
        }
        assert expected.issubset(set(df.columns))


class TestGenerateSummary:
    def test_summary_pathway_kind_shape(self):
        from multiomics_explorer.analysis.enrichment import EnrichmentInputs, fisher_ora
        import pandas as pd

        t2g = pd.DataFrame([
            {"term_id": "GO:0001", "term_name": "transport", "locus_tag": "g1"},
            {"term_id": "GO:0001", "term_name": "transport", "locus_tag": "g2"},
        ])
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"exp1__up": ["g1"]},
            background={"exp1__up": ["g1", "g2", "g3"]},
            cluster_metadata={"exp1__up": {
                "experiment_id": "exp1",
                "omics_type": "transcriptomics",
                "direction": "up",
                "table_scope": "DE",
                "treatment_type": ["light"],
                "background_factors": None,
                "is_time_course": False,
            }},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        # Merge cluster metadata into results df to simulate what pathway_enrichment does
        if not result.results.empty:
            md_df = pd.DataFrame.from_dict(
                inputs.cluster_metadata, orient="index"
            ).reset_index().rename(columns={"index": "cluster"})
            result.results = result.results.merge(md_df, on="cluster", how="left")
        result.kind = "pathway"
        result.ontology = "go"
        result.level = 1
        result.params = {"pvalue_cutoff": 0.05}
        summary = result.generate_summary()
        assert "organism_name" in summary
        assert "ontology" in summary
        assert "total_matching" in summary
        assert "n_significant" in summary
        assert "by_experiment" in summary
        assert "by_direction" in summary
        assert "cluster_summary" in summary
        assert "top_clusters_by_min_padj" in summary
        assert "top_pathways_by_padj" in summary
        assert "term_validation" in summary
        assert "clusters_skipped" in summary
        assert "enrichment_params" in summary
        assert "results" not in summary
        assert "returned" not in summary
        assert "truncated" not in summary

    def test_summary_cluster_kind_dispatches(self):
        from multiomics_explorer.analysis.enrichment import EnrichmentInputs, fisher_ora
        import pandas as pd

        t2g = pd.DataFrame([
            {"term_id": "GO:0001", "term_name": "transport", "locus_tag": "g1"},
        ])
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"cluster1": ["g1"]},
            background={"cluster1": ["g1", "g2"]},
            cluster_metadata={"cluster1": {}},
            analysis_metadata={"analysis_id": "a1", "analysis_name": "MyAnalysis"},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        result.kind = "cluster"
        result.params = {"pvalue_cutoff": 0.05}
        summary = result.generate_summary()
        assert "by_cluster" in summary
        assert "by_term" in summary
        assert "by_experiment" not in summary


class TestToEnvelope:
    def test_envelope_default_has_results(self):
        from multiomics_explorer.analysis.enrichment import EnrichmentInputs, fisher_ora
        import pandas as pd

        t2g = pd.DataFrame([
            {"term_id": "GO:0001", "term_name": "transport", "locus_tag": "g1"},
            {"term_id": "GO:0001", "term_name": "transport", "locus_tag": "g2"},
        ])
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"exp1__up": ["g1"]},
            background={"exp1__up": ["g1", "g2", "g3"]},
            cluster_metadata={"exp1__up": {
                "experiment_id": "exp1",
                "omics_type": "transcriptomics",
                "direction": "up",
                "table_scope": "DE",
                "treatment_type": ["light"],
                "background_factors": None,
                "is_time_course": False,
            }},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        # Merge cluster metadata into results df to simulate what pathway_enrichment does
        if not result.results.empty:
            md_df = pd.DataFrame.from_dict(
                inputs.cluster_metadata, orient="index"
            ).reset_index().rename(columns={"index": "cluster"})
            result.results = result.results.merge(md_df, on="cluster", how="left")
        result.kind = "pathway"
        result.ontology = "go"
        result.level = 1
        result.params = {"pvalue_cutoff": 0.05}
        env = result.to_envelope()
        assert "results" in env
        assert "returned" in env
        assert "truncated" in env
        assert "offset" in env
        assert env["returned"] == len(env["results"])
        if env["results"]:
            row = env["results"][0]
            for v in row.values():
                assert not isinstance(v, list), f"unexpected list in row: {row}"

    def test_envelope_summary_true(self):
        from multiomics_explorer.analysis.enrichment import EnrichmentInputs, fisher_ora
        import pandas as pd

        t2g = pd.DataFrame([
            {"term_id": "GO:0001", "term_name": "transport", "locus_tag": "g1"},
            {"term_id": "GO:0001", "term_name": "transport", "locus_tag": "g2"},
        ])
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"exp1__up": ["g1"]},
            background={"exp1__up": ["g1", "g2", "g3"]},
            cluster_metadata={"exp1__up": {
                "experiment_id": "exp1",
                "omics_type": "transcriptomics",
                "direction": "up",
                "table_scope": "DE",
                "treatment_type": ["light"],
                "background_factors": None,
                "is_time_course": False,
            }},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        # Merge cluster metadata into results df to simulate what pathway_enrichment does
        if not result.results.empty:
            md_df = pd.DataFrame.from_dict(
                inputs.cluster_metadata, orient="index"
            ).reset_index().rename(columns={"index": "cluster"})
            result.results = result.results.merge(md_df, on="cluster", how="left")
        result.kind = "pathway"
        result.params = {"pvalue_cutoff": 0.05}
        env = result.to_envelope(summary=True)
        assert env["results"] == []
        assert env["returned"] == 0
        assert "by_experiment" in env
        assert "total_matching" in env

    def test_envelope_pagination(self):
        from multiomics_explorer.analysis.enrichment import EnrichmentInputs, fisher_ora
        import pandas as pd

        t2g = pd.DataFrame([
            {"term_id": "GO:0001", "term_name": "transport", "locus_tag": "g1"},
            {"term_id": "GO:0001", "term_name": "transport", "locus_tag": "g2"},
        ])
        inputs = EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"exp1__up": ["g1"]},
            background={"exp1__up": ["g1", "g2", "g3"]},
            cluster_metadata={"exp1__up": {
                "experiment_id": "exp1",
                "omics_type": "transcriptomics",
                "direction": "up",
                "table_scope": "DE",
                "treatment_type": ["light"],
                "background_factors": None,
                "is_time_course": False,
            }},
        )
        result = fisher_ora(inputs, t2g, min_gene_set_size=0)
        # Merge cluster metadata into results df to simulate what pathway_enrichment does
        if not result.results.empty:
            md_df = pd.DataFrame.from_dict(
                inputs.cluster_metadata, orient="index"
            ).reset_index().rename(columns={"index": "cluster"})
            result.results = result.results.merge(md_df, on="cluster", how="left")
        result.kind = "pathway"
        result.params = {"pvalue_cutoff": 0.05}
        total = len(result.results)
        env = result.to_envelope(limit=1, offset=0)
        assert env["returned"] == 1
        assert env["truncated"] is (total > 1)
