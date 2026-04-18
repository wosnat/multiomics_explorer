# EnrichmentResult Class Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dict return type of `pathway_enrichment` / `cluster_enrichment` / `fisher_ora` with an `EnrichmentResult` dataclass that owns intermediates (inputs, term2gene) and surfaces them through typed accessors (`.explain`, `.overlap_genes`, `.background_genes`, `.generate_summary`, `.to_envelope`).

**Architecture:** New Pydantic models (`DEStats`, `GeneRef`, `EnrichmentExplanation`) in `analysis/enrichment.py`. `EnrichmentResult` is a `@dataclass` (holds a `pd.DataFrame` which Pydantic handles awkwardly). `fisher_ora` takes `EnrichmentInputs` + `term2gene` and returns `EnrichmentResult`. API layer adds the `signed_score` post-process (pathway path) and the `params` dict. MCP wrappers call `.to_envelope()`; the MCP tool schemas drop the phantom `verbose` parameter.

**Tech Stack:** Python, Pydantic v2 (`Field(description=...)` pattern), pandas, pytest. No Neo4j dependency for new unit tests.

**Spec:** [docs/superpowers/specs/2026-04-18-enrichment-result-class-design.md](../specs/2026-04-18-enrichment-result-class-design.md)

---

## File Structure

**Modified:**
- `multiomics_explorer/analysis/enrichment.py` — add `DEStats`, `GeneRef`, `EnrichmentExplanation`, `EnrichmentResult`; extend `EnrichmentInputs` with `gene_stats`; change `fisher_ora` signature; update `de_enrichment_inputs` to populate `gene_stats`.
- `multiomics_explorer/api/functions.py` — refactor `pathway_enrichment` and `cluster_enrichment` to return `EnrichmentResult`; add `params` dict; delete `_build_pathway_enrichment_envelope` / `_build_cluster_enrichment_envelope` helpers (logic moved to `EnrichmentResult.generate_summary()` / `.to_envelope()`).
- `multiomics_explorer/mcp_server/tools.py` — wrappers call `.to_envelope()`; drop `verbose` parameter.
- `multiomics_explorer/__init__.py` — re-export new symbols (`EnrichmentResult`, `EnrichmentExplanation`, `GeneRef`, `DEStats`).
- `multiomics_explorer/inputs/tools/pathway_enrichment.yaml` — drop `verbose` parameter.
- `multiomics_explorer/inputs/tools/cluster_enrichment.yaml` — drop `verbose` parameter.
- `multiomics_explorer/skills/multiomics-kg-guide/references/tools/pathway_enrichment.md` — regenerated.
- `multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md` — regenerated.
- `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md` — hand-edit canonical doc.
- `examples/pathway_enrichment.py` — rewrite to demonstrate new surface.
- `tests/unit/test_enrichment.py` — migrate `fisher_ora` tests to new signature.
- `tests/unit/test_api_functions.py` — migrate envelope-dict assertions to `.to_envelope()`.
- `tests/integration/test_api_contract.py` — same migration.
- `tests/integration/test_mcp_tools.py` — same migration.
- `tests/regression/test_regression.py` — same migration.
- `tests/evals/test_eval.py` — audit + migrate.

**Created:**
- `tests/unit/test_enrichment_result.py` — new unit tests for `EnrichmentResult` accessors.

**Deleted:**
- `multiomics_explorer/analysis/enrichment.md` — orphaned duplicate (not served by MCP; see spec).

---

## Phase 1 — Foundation types

### Task 1: Add `DEStats`, `GeneRef`, `EnrichmentExplanation` Pydantic models

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py:13` (imports) + end of file
- Test: `tests/unit/test_enrichment_result.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_enrichment_result.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_enrichment_result.py -v`
Expected: FAIL with `ImportError: cannot import name 'DEStats' from 'multiomics_explorer'`

- [ ] **Step 3: Add the models to `analysis/enrichment.py`**

Update imports at `multiomics_explorer/analysis/enrichment.py:13`:

```python
from typing import Literal
from pydantic import BaseModel, Field
```

Add these classes after the existing `EnrichmentInputs` class (after line 76), before `_REQUIRED_TERM2GENE_COLS = ...`:

```python
class DEStats(BaseModel):
    """Differential-expression statistics for one gene in one experiment × timepoint."""

    log2fc: float = Field(
        description="log2 fold change from DE analysis."
    )
    padj: float = Field(
        description="BH-adjusted p-value from the source DE table."
    )
    rank: int | None = Field(
        default=None,
        description=(
            "Rank by |log2FC| within the experiment × timepoint. 1 = strongest. "
            "None when the source DE tool didn't emit a rank."
        ),
    )
    direction: Literal["up", "down", "none"] = Field(
        description="'up', 'down', or 'none' (not significant)."
    )
    significant: bool = Field(
        description="Whether the gene meets the experiment's significance threshold."
    )


class GeneRef(BaseModel):
    """A gene referenced in an enrichment result — locus_tag plus optional name/product/DE stats."""

    locus_tag: str = Field(
        description="Primary gene identifier, e.g. 'PMM0712'."
    )
    gene_name: str | None = Field(
        default=None,
        description=(
            "Short gene name (e.g. 'pstS') from term2gene's gene_name column. "
            "None when term2gene lacks the column or the cell is null."
        ),
    )
    product: str | None = Field(
        default=None,
        description=(
            "Gene product description (e.g. 'phosphate ABC transporter'). "
            "None when term2gene lacks the column or the cell is null."
        ),
    )
    log2fc: float | None = Field(
        default=None, description="log2 fold change; None outside the DE path."
    )
    padj: float | None = Field(
        default=None, description="BH-adjusted p-value; None outside the DE path."
    )
    rank: int | None = Field(
        default=None,
        description="Rank by |log2FC| within experiment × timepoint; None outside the DE path.",
    )
    direction: Literal["up", "down", "none"] | None = Field(
        default=None, description="DE direction; None outside the DE path."
    )
    significant: bool | None = Field(
        default=None, description="DE significance flag; None outside the DE path."
    )


class EnrichmentExplanation(BaseModel):
    """Single (cluster, term_id) pair explained: Fisher numbers, ranking, gene lists, narrative."""

    cluster: str = Field(description="Cluster identifier from EnrichmentInputs.gene_sets.")
    term_id: str = Field(description="Ontology term identifier (e.g. 'GO:0006810').")
    term_name: str = Field(description="Human-readable term name (e.g. 'transport').")
    cluster_kind: Literal["pathway", "cluster"] = Field(
        description=(
            "Which enrichment path produced this result — dispatches the narrative "
            "wording. 'pathway' = DE-driven; 'cluster' = clustering-analysis-driven."
        ),
    )
    cluster_metadata: dict = Field(
        description=(
            "Cluster-specific context. For pathway kind: experiment_id, timepoint, "
            "direction, omics_type, table_scope, treatment_type, background_factors. "
            "For cluster kind: analysis_id, analysis_name, cluster_type, treatment, "
            "experimental_context."
        ),
    )

    count: int = Field(description="k — genes in foreground ∩ background ∩ term.")
    n_foreground: int = Field(description="n — genes in foreground ∩ background.")
    bg_count: int = Field(description="M — genes in background ∩ term.")
    n_background: int = Field(description="N — total genes in background.")
    gene_ratio: str = Field(description="Pretty 'k/n' string (e.g. '12/87').")
    bg_ratio: str = Field(description="Pretty 'M/N' string (e.g. '210/2340').")
    fold_enrichment: float = Field(description="(k/n) / (M/N) — observed over expected.")
    rich_factor: float = Field(
        description="k / M — fraction of the term's background that landed in foreground."
    )
    pvalue: float = Field(description="Fisher's exact test one-sided p-value (greater).")
    p_adjust: float = Field(description="BH-adjusted p-value within this cluster's tests.")

    rank_in_cluster: int = Field(
        description=(
            "Rank of this term among all terms tested in this cluster, by p_adjust "
            "ascending. 1 = most significant."
        ),
    )
    n_terms_in_cluster: int = Field(
        description="Total terms tested in this cluster (denominator for rank_in_cluster)."
    )

    overlap_genes: list[GeneRef] = Field(
        description=(
            "The k locus_tags (foreground ∩ background ∩ term) as GeneRef objects, "
            "sorted: named genes first (by rank if present, else gene_name), then "
            "unnamed (by rank if present, else locus_tag)."
        ),
    )
    background_genes: list[GeneRef] = Field(
        description=(
            "The M locus_tags (background ∩ term) as GeneRef objects, same sort. "
            "DE fields populated for any locus_tag present in inputs.gene_stats."
        ),
    )
    overlap_preview_n: int = Field(
        default=10,
        description="Max number of overlap genes to inline in the _repr_markdown_ narrative.",
    )

    def _repr_markdown_(self) -> str:
        """Rendered in Jupyter; implementation added in Task 5."""
        raise NotImplementedError("Implemented in Task 5")
```

- [ ] **Step 4: Re-export from `__init__.py`**

In `multiomics_explorer/__init__.py`, find the existing `from .analysis.enrichment import ...` line (or equivalent) and add the new symbols. Example edit:

```python
from multiomics_explorer.analysis.enrichment import (
    EnrichmentInputs,
    de_enrichment_inputs,
    cluster_enrichment_inputs,
    fisher_ora,
    signed_enrichment_score,
    # New:
    DEStats,
    GeneRef,
    EnrichmentExplanation,
)
```

And add to `__all__` if present.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_enrichment_result.py -v`
Expected: all `TestDEStats`, `TestGeneRef`, `TestEnrichmentExplanation` tests PASS.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py multiomics_explorer/__init__.py tests/unit/test_enrichment_result.py
git commit -m "feat: add DEStats, GeneRef, EnrichmentExplanation Pydantic models"
```

---

### Task 2: Extend `EnrichmentInputs` with `gene_stats`

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py:20-76` (EnrichmentInputs class)
- Test: `tests/unit/test_enrichment.py` (extend existing TestEnrichmentInputs)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_enrichment.py` inside `class TestEnrichmentInputs`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_enrichment.py::TestEnrichmentInputs -v`
Expected: FAIL with `AttributeError: 'EnrichmentInputs' object has no attribute 'gene_stats'`

- [ ] **Step 3: Add `gene_stats` field**

Edit `multiomics_explorer/analysis/enrichment.py` inside the `EnrichmentInputs` class, after `analysis_metadata` (around line 76):

```python
    gene_stats: dict[str, dict[str, DEStats]] = Field(
        default_factory=dict,
        description=(
            "cluster -> locus_tag -> DEStats. Populated by de_enrichment_inputs "
            "for every measured gene (not just foreground/significant). Empty for "
            "cluster_enrichment_inputs. Consumed by GeneRef construction in "
            "EnrichmentResult accessors."
        ),
    )
```

Note: `EnrichmentInputs` is defined before `DEStats` in the current file. Since we added `DEStats` in Task 1 AFTER `EnrichmentInputs`, you must move `DEStats` ABOVE `EnrichmentInputs` — or use `from __future__ import annotations` with a string-forward-reference `dict[str, dict[str, "DEStats"]]`. Use the forward-reference approach because `from __future__ import annotations` is already at the top of the file.

The field should work as-is because `from __future__ import annotations` at line 11 defers annotation evaluation. Verify with the test.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_enrichment.py::TestEnrichmentInputs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py tests/unit/test_enrichment.py
git commit -m "feat: add gene_stats field to EnrichmentInputs"
```

---

## Phase 2 — EnrichmentResult class

### Task 3: `EnrichmentResult` dataclass skeleton + `fisher_ora` signature change

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py` (add `EnrichmentResult` class; change `fisher_ora` signature to return it)
- Modify: `multiomics_explorer/__init__.py` (re-export `EnrichmentResult`)
- Modify: `tests/unit/test_enrichment.py` (migrate existing `TestFisherOra` to new signature)

**Rationale:** The class and the `fisher_ora` signature change are co-dependent
— `fisher_ora` must return `EnrichmentResult`, which must exist. Doing them
together avoids a broken-state interim commit.

- [ ] **Step 1: Write failing test — fisher_ora returns EnrichmentResult**

Append to `tests/unit/test_enrichment_result.py`:

```python
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
        assert result.kind == "pathway"  # default
        assert result.organism_name == "MED4"
        assert not result.results.empty
        assert result.inputs is inputs
        assert result.term2gene is t2g
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestFisherOraReturnsResult -v`
Expected: FAIL with `ImportError: cannot import name 'EnrichmentResult'`.

- [ ] **Step 3: Add `EnrichmentResult` dataclass (skeleton — no accessors yet)**

At the end of `multiomics_explorer/analysis/enrichment.py`, add:

```python
from dataclasses import dataclass, field


@dataclass
class EnrichmentResult:
    """Rich wrapper around Fisher ORA output. See docs://analysis/enrichment."""

    kind: Literal["pathway", "cluster"]
    organism_name: str
    ontology: str | None
    level: int | None

    results: pd.DataFrame
    inputs: EnrichmentInputs
    term2gene: pd.DataFrame

    term_validation: dict = field(default_factory=dict)
    clusters_skipped: list[dict] = field(default_factory=list)
    params: dict = field(default_factory=dict)
```

- [ ] **Step 4: Change `fisher_ora` signature**

Replace the existing `fisher_ora` body at `analysis/enrichment.py:82` with:

```python
def fisher_ora(
    inputs: EnrichmentInputs,
    term2gene: pd.DataFrame,
    *,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
) -> "EnrichmentResult":
    """Run Fisher-exact ORA and return an EnrichmentResult.

    See docs://analysis/enrichment for methodology. Users can construct an
    EnrichmentInputs directly (passing gene_sets, background, organism_name,
    optional gene_stats) — no KG required. Gene name/product for accessors
    comes from term2gene rows.

    Parameters
    ----------
    inputs : EnrichmentInputs
        Gene sets + per-cluster backgrounds + cluster metadata + optional
        gene_stats (DE-specific).
    term2gene : pandas.DataFrame
        Required columns: term_id, term_name, locus_tag.
        Optional: gene_name, product (used by GeneRef accessors).
        Extra columns pass through to result rows.
    min_gene_set_size, max_gene_set_size : int, int | None
        Per-cluster M filter (same as before).

    Returns
    -------
    EnrichmentResult
        Holds the Fisher DataFrame plus inputs and term2gene for accessor use.
    """
    missing = [c for c in _REQUIRED_TERM2GENE_COLS if c not in term2gene.columns]
    if missing:
        raise ValueError(
            f"term2gene is missing required column(s): {missing}. "
            f"Required: {list(_REQUIRED_TERM2GENE_COLS)}."
        )
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError(
            f"max_gene_set_size ({max_gene_set_size}) must be >= "
            f"min_gene_set_size ({min_gene_set_size})."
        )
    df = _fisher_ora_impl(
        gene_sets=inputs.gene_sets,
        background=inputs.background,
        term2gene=term2gene,
        min_gene_set_size=min_gene_set_size,
        max_gene_set_size=max_gene_set_size,
    )
    return EnrichmentResult(
        kind="pathway",  # default; api layer overrides for cluster_enrichment
        organism_name=inputs.organism_name,
        ontology=None,
        level=None,
        results=df,
        inputs=inputs,
        term2gene=term2gene,
    )
```

- [ ] **Step 5: Migrate existing `TestFisherOra` tests to new signature**

In `tests/unit/test_enrichment.py`, for each test in `class TestFisherOra`,
wrap the old dict-form kwargs in an `EnrichmentInputs` and read the
DataFrame from `result.results`. Apply this transformation everywhere:

```python
# Before:
df = fisher_ora(
    gene_sets={"c1": ["g1", "g2"]},
    background={"c1": [...]},
    term2gene=t2g,
)

# After:
from multiomics_explorer import EnrichmentInputs
inputs = EnrichmentInputs(
    organism_name="test",
    gene_sets={"c1": ["g1", "g2"]},
    background={"c1": [...]},
    cluster_metadata={"c1": {}},
)
result = fisher_ora(inputs, t2g)
df = result.results
```

The `test_missing_required_columns_raises` test needs the inputs wrapper
too — the ValueError is still raised (column validation comes first).

- [ ] **Step 6: Re-export `EnrichmentResult`**

Add `EnrichmentResult` to imports and `__all__` in `multiomics_explorer/__init__.py`.

- [ ] **Step 7: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestFisherOraReturnsResult tests/unit/test_enrichment.py::TestFisherOra -v`
Expected: PASS. Note: `tests/unit/test_api_functions.py` will fail at this
point because `api.pathway_enrichment`/`api.cluster_enrichment` still call
the old `fisher_ora` signature — that's fixed in Tasks 10 and 11.

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py multiomics_explorer/__init__.py \
        tests/unit/test_enrichment.py tests/unit/test_enrichment_result.py
git commit -m "refactor: fisher_ora returns EnrichmentResult; add dataclass skeleton"
```

---

### Task 4: `overlap_genes` / `background_genes` accessors

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py` (add accessors to `EnrichmentResult`)
- Test: `tests/unit/test_enrichment_result.py` (add shared fixture + tests)

- [ ] **Step 1: Add a shared fixture for a hand-rolled EnrichmentResult**

Append to `tests/unit/test_enrichment_result.py`:

```python
import pandas as pd


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

    result = fisher_ora(
        inputs,
        term2gene,
        min_gene_set_size=0,
    )
    return inputs, term2gene, result


class TestOverlapAndBackgroundGenes:
    def test_overlap_genes_intersection_and_content(self):
        inputs, t2g, result = _build_simple_result()
        overlap = result.overlap_genes("c1", "P")
        # foreground(c1)={g1,g2} ∩ background(c1)={g1..g6} ∩ P={g1,g2,g3} = {g1,g2}
        lts = [g.locus_tag for g in overlap]
        assert set(lts) == {"g1", "g2"}

    def test_overlap_genes_sort_named_first(self):
        inputs, t2g, result = _build_simple_result()
        overlap = result.overlap_genes("c1", "P")
        # g1 is named 'geneA', g2 is unnamed -> g1 first
        assert overlap[0].locus_tag == "g1"
        assert overlap[0].gene_name == "geneA"
        assert overlap[1].locus_tag == "g2"
        assert overlap[1].gene_name is None

    def test_background_genes_intersection(self):
        inputs, t2g, result = _build_simple_result()
        bg = result.background_genes("c1", "P")
        # background(c1)={g1..g6} ∩ P={g1,g2,g3} = {g1,g2,g3}
        lts = [g.locus_tag for g in bg]
        assert set(lts) == {"g1", "g2", "g3"}

    def test_background_genes_sort_named_by_rank(self):
        inputs, t2g, result = _build_simple_result()
        bg = result.background_genes("c1", "P")
        # Named genes: g1 (rank 1), g3 (no rank in gene_stats -> falls back to name)
        # g1 should come first (has rank), then g3 (has name but no rank)
        named = [g for g in bg if g.gene_name is not None]
        assert named[0].locus_tag == "g1"  # rank 1
        assert named[1].locus_tag == "g3"  # name 'geneC'

    def test_gene_stats_populated_for_measured_gene(self):
        inputs, t2g, result = _build_simple_result()
        overlap = result.overlap_genes("c1", "P")
        g1 = next(g for g in overlap if g.locus_tag == "g1")
        assert g1.log2fc == 2.0
        assert g1.rank == 1
        assert g1.direction == "up"

    def test_gene_stats_none_for_unmeasured_gene(self):
        inputs, t2g, result = _build_simple_result()
        # c2 has empty gene_stats; overlap gene should have None DE fields
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
        """term2gene without gene_name/product — GeneRef returns None."""
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestOverlapAndBackgroundGenes -v`
Expected: FAIL with `AttributeError: 'EnrichmentResult' object has no attribute 'overlap_genes'`.

- [ ] **Step 3: Add helper functions + accessor methods**

At module level in `analysis/enrichment.py`, above the `EnrichmentResult`
class (defined in Task 3), add these private helpers:

```python
def _gene_ref_from_row(
    locus_tag: str,
    t2g_row: dict | None,
    de_stats: "DEStats | None",
) -> "GeneRef":
    """Build a GeneRef from a term2gene row + optional DE stats."""
    gene_name = None
    product = None
    if t2g_row is not None:
        gn = t2g_row.get("gene_name")
        if gn is not None and not (isinstance(gn, float) and pd.isna(gn)):
            gene_name = gn
        pr = t2g_row.get("product")
        if pr is not None and not (isinstance(pr, float) and pd.isna(pr)):
            product = pr
    kwargs = {"locus_tag": locus_tag, "gene_name": gene_name, "product": product}
    if de_stats is not None:
        kwargs.update({
            "log2fc": de_stats.log2fc,
            "padj": de_stats.padj,
            "rank": de_stats.rank,
            "direction": de_stats.direction,
            "significant": de_stats.significant,
        })
    return GeneRef(**kwargs)


def _sort_gene_refs(refs: list["GeneRef"]) -> list["GeneRef"]:
    """Named genes first; within each group, rank ascending if present, else
    gene_name (named) / locus_tag (unnamed) alphabetical.
    """
    def named_key(r):
        rank = r.rank if r.rank is not None else 10**9
        return (rank, (r.gene_name or "").lower())

    def unnamed_key(r):
        rank = r.rank if r.rank is not None else 10**9
        return (rank, r.locus_tag)

    named = sorted([r for r in refs if r.gene_name], key=named_key)
    unnamed = sorted([r for r in refs if not r.gene_name], key=unnamed_key)
    return named + unnamed
```

Now add these methods to the existing `EnrichmentResult` class (from Task 3):

```python
    def _term_row(self, term_id: str) -> dict | None:
        rows = self.term2gene[self.term2gene["term_id"] == term_id]
        if rows.empty:
            return None
        return rows.iloc[0].to_dict()

    def _term_members(self, term_id: str) -> set[str]:
        return set(
            self.term2gene[self.term2gene["term_id"] == term_id]["locus_tag"]
        )

    def _assert_cluster(self, cluster: str) -> None:
        if cluster not in self.inputs.gene_sets and cluster not in self.inputs.background:
            raise KeyError(
                f"Cluster {cluster!r} not found. Known: {sorted(self.inputs.gene_sets)}"
            )

    def _assert_term(self, term_id: str) -> None:
        if term_id not in set(self.term2gene["term_id"]):
            raise KeyError(f"Term {term_id!r} not found in term2gene.")

    def overlap_genes(self, cluster: str, term_id: str) -> list[GeneRef]:
        """Return k genes: foreground ∩ background ∩ term, as GeneRefs, sorted."""
        self._assert_cluster(cluster)
        self._assert_term(term_id)
        fg = set(self.inputs.gene_sets.get(cluster, []))
        bg = set(self.inputs.background.get(cluster, []))
        term_set = self._term_members(term_id)
        locus_tags = fg & bg & term_set
        return self._build_gene_refs(cluster, locus_tags, term_id)

    def background_genes(self, cluster: str, term_id: str) -> list[GeneRef]:
        """Return M genes: background ∩ term, as GeneRefs, sorted."""
        self._assert_cluster(cluster)
        self._assert_term(term_id)
        bg = set(self.inputs.background.get(cluster, []))
        term_set = self._term_members(term_id)
        locus_tags = bg & term_set
        return self._build_gene_refs(cluster, locus_tags, term_id)

    def _build_gene_refs(
        self, cluster: str, locus_tags: set[str], term_id: str,
    ) -> list[GeneRef]:
        # Lookup per-locus_tag info from term2gene (may have multiple rows per term_id).
        t2g_sub = self.term2gene[
            (self.term2gene["term_id"] == term_id)
            & (self.term2gene["locus_tag"].isin(locus_tags))
        ]
        row_by_lt = {
            r["locus_tag"]: r.to_dict() for _, r in t2g_sub.iterrows()
        }
        cluster_stats = self.inputs.gene_stats.get(cluster, {})
        refs = [
            _gene_ref_from_row(
                lt,
                row_by_lt.get(lt),
                cluster_stats.get(lt),
            )
            for lt in locus_tags
        ]
        return _sort_gene_refs(refs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestOverlapAndBackgroundGenes -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py tests/unit/test_enrichment_result.py
git commit -m "feat: EnrichmentResult overlap_genes / background_genes accessors"
```

---

### Task 5: `explain()` accessor with narrative

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py` (`EnrichmentResult.explain`, `EnrichmentExplanation._repr_markdown_`)
- Test: `tests/unit/test_enrichment_result.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_enrichment_result.py`:

```python
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
        # c1 foreground = {g1,g2}; bg = {g1..g6}; P = {g1,g2,g3}
        # overlap = {g1,g2} -> k=2
        # n = |fg ∩ bg| = 2
        # M = |P ∩ bg| = 3
        # N = |bg| = 6
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
        # c1 has both P and Q tested; P should be rank 1 (significant), Q rank 2
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
        assert "P" in md  # term_id
        assert "Pathway P" in md  # term_name
        assert "geneA" in md  # named gene display
        assert "2 of 2" in md or "2/2" in md  # gene ratio
        assert "experiment EXP042" in md or "EXP042" in md

    def test_explain_narrative_falls_back_to_locus_tag_when_unnamed(self):
        """When no gene_name, narrative should show locus_tag."""
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
        assert "g1" in md  # raw locus_tag, no "(g1)" wrapping
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestExplain -v`
Expected: FAIL with `AttributeError: ... has no attribute 'explain'` or `NotImplementedError`.

- [ ] **Step 3: Implement `explain` and `_repr_markdown_`**

Add to the `EnrichmentResult` class in `analysis/enrichment.py`:

```python
    def explain(self, cluster: str, term_id: str) -> EnrichmentExplanation:
        """Build a full EnrichmentExplanation for (cluster, term_id)."""
        self._assert_cluster(cluster)
        self._assert_term(term_id)
        rows = self.results[
            (self.results["cluster"] == cluster)
            & (self.results["term_id"] == term_id)
        ]
        if rows.empty:
            raise KeyError(
                f"No enrichment row for cluster={cluster!r}, term_id={term_id!r}."
            )
        row = rows.iloc[0].to_dict()

        # Rank-in-cluster: position by p_adjust ascending among this cluster's rows
        cluster_rows = self.results[self.results["cluster"] == cluster]
        sorted_cluster = cluster_rows.sort_values("p_adjust").reset_index(drop=True)
        rank = int(
            sorted_cluster.index[sorted_cluster["term_id"] == term_id][0] + 1
        )
        n_terms = int(len(cluster_rows))

        overlap = self.overlap_genes(cluster, term_id)
        background = self.background_genes(cluster, term_id)

        # n_foreground = |foreground ∩ background|; N = |background|
        fg = set(self.inputs.gene_sets.get(cluster, []))
        bg = set(self.inputs.background.get(cluster, []))
        n_fg = len(fg & bg)
        N = len(bg)

        return EnrichmentExplanation(
            cluster=cluster,
            term_id=term_id,
            term_name=row["term_name"],
            cluster_kind=self.kind,
            cluster_metadata=self.inputs.cluster_metadata.get(cluster, {}),
            count=int(row["count"]),
            n_foreground=n_fg,
            bg_count=int(row["bg_count"]),
            n_background=N,
            gene_ratio=row["gene_ratio"],
            bg_ratio=row["bg_ratio"],
            fold_enrichment=float(row["fold_enrichment"]),
            rich_factor=float(row["rich_factor"]),
            pvalue=float(row["pvalue"]),
            p_adjust=float(row["p_adjust"]),
            rank_in_cluster=rank,
            n_terms_in_cluster=n_terms,
            overlap_genes=overlap,
            background_genes=background,
        )
```

Replace the stub `_repr_markdown_` in `EnrichmentExplanation` with a real implementation:

```python
    def _repr_markdown_(self) -> str:
        def _fmt_gene(g: "GeneRef") -> str:
            if g.gene_name:
                return f"{g.gene_name} ({g.locus_tag})"
            return g.locus_tag

        md = self.cluster_metadata or {}
        # Cluster context sentence
        if self.cluster_kind == "pathway":
            parts = []
            if md.get("experiment_id"):
                parts.append(f"experiment {md['experiment_id']}")
            if md.get("direction"):
                parts.append(f"{md['direction']}-regulated")
            if md.get("timepoint"):
                parts.append(f"at {md['timepoint']}")
            context = f" ({', '.join(parts)})" if parts else ""
        else:  # cluster kind
            parts = []
            if md.get("analysis_id") or md.get("analysis_name"):
                parts.append(
                    f"analysis {md.get('analysis_name') or md.get('analysis_id')}"
                )
            if md.get("cluster_type"):
                parts.append(f"cluster_type={md['cluster_type']}")
            context = f" ({', '.join(parts)})" if parts else ""

        preview = self.overlap_genes[: self.overlap_preview_n]
        remainder = max(0, len(self.overlap_genes) - self.overlap_preview_n)
        overlap_str = ", ".join(_fmt_gene(g) for g in preview)
        if remainder:
            overlap_str += f", ... (+{remainder} more)"

        return (
            f"**{self.term_id}** ({self.term_name}) is enriched in `{self.cluster}`{context}. "
            f"{self.count} of {self.n_foreground} foreground genes hit this term; "
            f"{self.bg_count} of {self.n_background} background genes carry it "
            f"(fold {self.fold_enrichment:.2f}, p.adjust {self.p_adjust:.2e}, "
            f"rank {self.rank_in_cluster} of {self.n_terms_in_cluster}). "
            f"Overlap: {overlap_str}."
        )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestExplain -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py tests/unit/test_enrichment_result.py
git commit -m "feat: EnrichmentResult.explain() with narrative repr"
```

---

### Task 6: Nice-to-have accessors (`cluster_context`, `why_skipped`, `missing_terms`, `to_compare_cluster_frame`)

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py`
- Test: `tests/unit/test_enrichment_result.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
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
        # Build a result with an explicitly skipped cluster
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
        # fisher_ora itself doesn't populate clusters_skipped; the api layer does.
        # For this test we assert that accessor reads from inputs.clusters_skipped.
        result.clusters_skipped = inputs.clusters_skipped  # simulate api population
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestNiceAccessors -v`
Expected: FAIL with `AttributeError: ... has no attribute 'cluster_context'`.

- [ ] **Step 3: Implement accessors**

Add to `EnrichmentResult` in `analysis/enrichment.py`:

```python
    def cluster_context(self, cluster: str) -> dict:
        """inputs.cluster_metadata[cluster] + n_tests/n_significant from results."""
        self._assert_cluster(cluster)
        md = dict(self.inputs.cluster_metadata.get(cluster, {}))
        sub = self.results[self.results["cluster"] == cluster]
        md["n_tests"] = int(len(sub))
        pvc = self.params.get("pvalue_cutoff", 0.05)
        md["n_significant"] = int((sub["p_adjust"] < pvc).sum()) if not sub.empty else 0
        return md

    def why_skipped(self, cluster: str) -> str | None:
        """Reason from clusters_skipped, or None if cluster produced results."""
        for entry in self.clusters_skipped:
            if (
                entry.get("cluster_name") == cluster
                or entry.get("cluster") == cluster
                or entry.get("cluster_id") == cluster
            ):
                return entry.get("reason")
        return None

    def missing_terms(self) -> dict[str, list[str]]:
        """Return term_validation buckets."""
        return {
            "not_found": list(self.term_validation.get("not_found", [])),
            "wrong_ontology": list(self.term_validation.get("wrong_ontology", [])),
            "wrong_level": list(self.term_validation.get("wrong_level", [])),
            "filtered_out": list(self.term_validation.get("filtered_out", [])),
        }

    def to_compare_cluster_frame(self) -> pd.DataFrame:
        """Rename columns to clusterProfiler compareCluster convention.

        Columns: Cluster, ID, Description, GeneRatio, BgRatio, pvalue,
        p.adjust, geneID. geneID is '/'-joined locus_tags of the overlap.
        """
        if self.results.empty:
            return pd.DataFrame(columns=[
                "Cluster", "ID", "Description", "GeneRatio", "BgRatio",
                "pvalue", "p.adjust", "geneID",
            ])

        rows = []
        for _, row in self.results.iterrows():
            overlap_lts = [
                g.locus_tag for g in self.overlap_genes(row["cluster"], row["term_id"])
            ]
            rows.append({
                "Cluster": row["cluster"],
                "ID": row["term_id"],
                "Description": row["term_name"],
                "GeneRatio": row["gene_ratio"],
                "BgRatio": row["bg_ratio"],
                "pvalue": row["pvalue"],
                "p.adjust": row["p_adjust"],
                "geneID": "/".join(overlap_lts),
            })
        return pd.DataFrame(rows)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestNiceAccessors -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py tests/unit/test_enrichment_result.py
git commit -m "feat: EnrichmentResult nice-to-have accessors"
```

---

### Task 7: `generate_summary()` method

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py`
- Test: `tests/unit/test_enrichment_result.py`

This task lifts the envelope-summary-building logic from
`_build_pathway_enrichment_envelope` and `_build_cluster_enrichment_envelope`
into `EnrichmentResult.generate_summary()`, dispatching on `self.kind`.

- [ ] **Step 1: Write failing test**

Append:

```python
class TestGenerateSummary:
    def test_summary_pathway_kind_shape(self):
        inputs, t2g, result = _build_simple_result()
        result.kind = "pathway"
        result.ontology = "go"
        result.level = 1
        result.params = {"pvalue_cutoff": 0.05}
        summary = result.generate_summary()
        # Pathway-kind keys
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
        # Must NOT have pagination or results
        assert "results" not in summary
        assert "returned" not in summary
        assert "truncated" not in summary

    def test_summary_cluster_kind_dispatches(self):
        inputs, t2g, result = _build_simple_result()
        result.kind = "cluster"
        result.params = {"pvalue_cutoff": 0.05}
        summary = result.generate_summary()
        # Cluster-kind keys (by_cluster, by_term instead of by_experiment/direction)
        assert "by_cluster" in summary
        assert "by_term" in summary
        # by_experiment should be absent for cluster kind
        assert "by_experiment" not in summary
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestGenerateSummary -v`
Expected: FAIL with `AttributeError: ... has no attribute 'generate_summary'`.

- [ ] **Step 3: Implement `generate_summary`**

Add to `EnrichmentResult` in `analysis/enrichment.py`:

```python
    def generate_summary(self) -> dict:
        """Aggregate view — no per-row results, no pagination.

        Pathway kind emits by_experiment/by_direction/by_omics_type;
        cluster kind emits by_cluster/by_term.
        """
        df = self.results
        pvc = self.params.get("pvalue_cutoff", 0.05)
        total_matching = int(len(df))
        n_significant = int((df["p_adjust"] < pvc).sum()) if total_matching else 0

        base = {
            "organism_name": self.organism_name,
            "ontology": self.ontology,
            "level": self.level,
            "total_matching": total_matching,
            "n_significant": n_significant,
            "not_found": list(self.inputs.not_found),
            "not_matched": list(self.inputs.not_matched),
            "term_validation": self.missing_terms(),
            "clusters_skipped": list(self.clusters_skipped),
            "enrichment_params": dict(self.params),
        }

        if self.kind == "pathway":
            base.update({
                "no_expression": list(self.inputs.no_expression),
                "by_experiment": _envelope_by_experiment(df, self.inputs, pvc),
                "by_direction": _envelope_by_direction(df, pvc),
                "by_omics_type": _envelope_by_omics_type(df, pvc),
                "cluster_summary": _envelope_cluster_summary(df, self.inputs),
                "top_clusters_by_min_padj": _envelope_top_clusters(df, self.inputs),
                "top_pathways_by_padj": _envelope_top_pathways(df),
            })
        else:  # cluster kind
            base.update({
                "analysis_id": self.inputs.analysis_metadata.get("analysis_id"),
                "analysis_name": self.inputs.analysis_metadata.get("analysis_name"),
                "cluster_method": self.inputs.analysis_metadata.get("cluster_method"),
                "cluster_type": self.inputs.analysis_metadata.get("cluster_type"),
                "omics_type": self.inputs.analysis_metadata.get("omics_type"),
                "treatment_type": self.inputs.analysis_metadata.get("treatment_type"),
                "background_factors": self.inputs.analysis_metadata.get("background_factors"),
                "by_cluster": _envelope_by_cluster(df, self.inputs, pvc),
                "by_term": _envelope_by_term(df, pvc),
                "clusters_tested": int(df["cluster"].nunique()) if total_matching else 0,
            })
        return base
```

- [ ] **Step 4: Move envelope helpers into `analysis/enrichment.py`**

The existing `_envelope_*` helpers live in `api/functions.py`. Move them into
`analysis/enrichment.py` as module-level private functions. Find them in
`api/functions.py` by searching for `def _envelope_by_experiment`,
`_envelope_by_direction`, `_envelope_by_omics_type`, `_envelope_cluster_summary`,
`_envelope_top_clusters`, `_envelope_top_pathways`, `_envelope_by_cluster`,
`_envelope_by_term`. Copy them verbatim (they're pure DataFrame → dict functions)
into `analysis/enrichment.py` above the `EnrichmentResult` class.

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestGenerateSummary -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py tests/unit/test_enrichment_result.py
git commit -m "feat: EnrichmentResult.generate_summary with pathway/cluster dispatch"
```

---

### Task 8: `to_envelope()` method

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py`
- Test: `tests/unit/test_enrichment_result.py`

- [ ] **Step 1: Write failing test**

```python
class TestToEnvelope:
    def test_envelope_default_has_results(self):
        inputs, t2g, result = _build_simple_result()
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
        # Scalar rows only — no list-typed columns
        if env["results"]:
            row = env["results"][0]
            for v in row.values():
                assert not isinstance(v, list), f"unexpected list in row: {row}"

    def test_envelope_summary_true(self):
        inputs, t2g, result = _build_simple_result()
        result.kind = "pathway"
        result.params = {"pvalue_cutoff": 0.05}
        env = result.to_envelope(summary=True)
        assert env["results"] == []
        assert env["returned"] == 0
        # summary fields are still there
        assert "by_experiment" in env
        assert "total_matching" in env

    def test_envelope_pagination(self):
        inputs, t2g, result = _build_simple_result()
        result.kind = "pathway"
        result.params = {"pvalue_cutoff": 0.05}
        total = len(result.results)
        env = result.to_envelope(limit=1, offset=0)
        assert env["returned"] == 1
        assert env["truncated"] is (total > 1)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestToEnvelope -v`
Expected: FAIL with `AttributeError: ... has no attribute 'to_envelope'`.

- [ ] **Step 3: Implement `to_envelope`**

Add to `EnrichmentResult`:

```python
    def to_envelope(
        self,
        *,
        summary: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict:
        """MCP-compatible envelope: summary fields + paginated scalar results rows."""
        env = self.generate_summary()
        total = int(len(self.results))

        if summary:
            env["results"] = []
            env["returned"] = 0
            env["truncated"] = total > 0
            env["offset"] = offset
            return env

        eff_limit = limit if limit is not None else total
        sliced = self.results.iloc[offset:offset + eff_limit] if total else self.results
        returned_rows = sliced.to_dict(orient="records")
        # Strip sparse tree/tree_code columns for non-BRITE rows
        import pandas as _pd
        for r in returned_rows:
            tv = r.get("tree")
            if tv is None or (isinstance(tv, float) and _pd.isna(tv)):
                r.pop("tree", None)
                r.pop("tree_code", None)

        env["results"] = returned_rows
        env["returned"] = len(returned_rows)
        env["truncated"] = (offset + len(returned_rows)) < total
        env["offset"] = offset
        return env
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_enrichment_result.py::TestToEnvelope -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py tests/unit/test_enrichment_result.py
git commit -m "feat: EnrichmentResult.to_envelope with pagination"
```

---

## Phase 3 — Input builders

### Task 9: `de_enrichment_inputs` populates `gene_stats`

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py:362-514` (de_enrichment_inputs)
- Test: `tests/unit/test_enrichment.py` (extend TestDeEnrichmentInputs)

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_enrichment.py` inside the existing
`TestDeEnrichmentInputs` class (or create it if missing):

```python
    def test_gene_stats_populated_for_all_measured_genes(self, monkeypatch):
        """gene_stats includes measured genes regardless of significance."""
        from multiomics_explorer import de_enrichment_inputs
        from multiomics_explorer.analysis import enrichment as _mod

        fake_rows = [
            # Significant gene
            {"locus_tag": "g1", "experiment_id": "E1", "timepoint": "T0",
             "direction": "up", "significant": True,
             "log2fc": 2.0, "padj": 0.001, "rank": 1,
             "organism_name": "MED4"},
            # Non-significant gene — should still be in gene_stats
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
        assert "g2" in out.gene_stats[cluster]  # non-significant still included
        assert out.gene_stats[cluster]["g1"].log2fc == 2.0
        assert out.gene_stats[cluster]["g1"].significant is True
        assert out.gene_stats[cluster]["g2"].significant is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_enrichment.py::TestDeEnrichmentInputs::test_gene_stats_populated_for_all_measured_genes -v`
Expected: FAIL with `assert cluster in out.gene_stats` / KeyError.

- [ ] **Step 3: Update `de_enrichment_inputs`**

Find the row-processing loop in `de_enrichment_inputs`
(around `analysis/enrichment.py:464-504`). Add `gene_stats` construction.

Before the return statement, add:

```python
    # Build gene_stats: cluster -> locus_tag -> DEStats (every measured gene).
    gene_stats: dict[str, dict[str, DEStats]] = {}
    for row in de_full.get("results", []):
        tp = _normalize_timepoint(row.get("timepoint"))
        if timepoint_filter is not None and tp not in set(timepoint_filter):
            continue
        if _gp_filter is not None:
            gp = (row.get("growth_phase") or "").lower()
            if gp not in _gp_filter:
                continue
        row_direction = row.get("direction") or _STATUS_TO_DIR.get(
            row.get("expression_status", ""), None
        )
        if row_direction not in ("up", "down"):
            continue
        exp_id = row.get("experiment_id")
        cluster = f"{exp_id}|{tp}|{row_direction}"
        locus_tag = row.get("locus_tag")
        if not locus_tag:
            continue
        log2fc = row.get("log2fc") if row.get("log2fc") is not None else row.get("log2_fc")
        padj = row.get("padj") if row.get("padj") is not None else row.get("p_adjust")
        if log2fc is None or padj is None:
            continue
        is_significant = bool(
            row.get("significant")
            or (row.get("expression_status", "") not in ("not_significant", ""))
        )
        de_direction = row_direction if is_significant else "none"
        gene_stats.setdefault(cluster, {})[locus_tag] = DEStats(
            log2fc=float(log2fc),
            padj=float(padj),
            rank=row.get("rank"),
            direction=de_direction,
            significant=is_significant,
        )
```

And update the return to include `gene_stats=gene_stats`:

```python
    return EnrichmentInputs(
        organism_name=de_full.get("organism_name", organism),
        gene_sets=gene_sets,
        background=background,
        cluster_metadata=cluster_metadata,
        not_found=list(de_full.get("not_found", []) or []),
        not_matched=list(de_full.get("not_matched", []) or []),
        no_expression=list(de_full.get("no_expression", []) or []),
        gene_stats=gene_stats,
    )
```

- [ ] **Step 4: Run test to verify pass**

Run: `uv run pytest tests/unit/test_enrichment.py::TestDeEnrichmentInputs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py tests/unit/test_enrichment.py
git commit -m "feat: de_enrichment_inputs populates gene_stats for all measured genes"
```

---

## Phase 4 — API layer

### Task 10: Refactor `api.pathway_enrichment` to return `EnrichmentResult`

**Files:**
- Modify: `multiomics_explorer/api/functions.py:3214-3372` (pathway_enrichment)
- Modify: delete `_build_pathway_enrichment_envelope` (lines 3003-3070 ish) and its `_envelope_*` helpers that were copied to `analysis/enrichment.py` in Task 6
- Test: existing tests in `test_api_functions.py` need `.to_envelope()` calls

- [ ] **Step 1: Rewrite `pathway_enrichment`**

Replace the body of `pathway_enrichment` at `api/functions.py:3214`:

```python
def pathway_enrichment(
    organism: str,
    experiment_ids: list[str],
    ontology: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    direction: str = "both",
    significant_only: bool = True,
    background: str | list[str] = "table_scope",
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    pvalue_cutoff: float = 0.05,
    timepoint_filter: list[str] | None = None,
    growth_phases: list[str] | None = None,
    tree: str | None = None,
    *,
    conn: GraphConnection | None = None,
):
    """Pathway over-representation analysis from DE results.

    Returns an EnrichmentResult. Callers who need the MCP-dict envelope
    should call result.to_envelope(...).
    """
    # --- validation ---
    if ontology not in ALL_ONTOLOGIES:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {ALL_ONTOLOGIES}")
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    if level is None and not term_ids:
        raise ValueError("At least one of `level` or `term_ids` must be provided.")
    if direction not in {"up", "down", "both"}:
        raise ValueError(f"direction must be 'up'|'down'|'both'; got {direction!r}")
    if isinstance(background, str):
        if background not in {"table_scope", "organism"}:
            raise ValueError(
                f"background must be 'table_scope', 'organism', or a list; got {background!r}"
            )
    elif isinstance(background, list):
        if not background:
            raise ValueError("background list must be non-empty")
    else:
        raise ValueError(
            f"background must be 'table_scope', 'organism', or a list; "
            f"got {type(background).__name__}"
        )
    if min_gene_set_size < 0:
        raise ValueError("min_gene_set_size must be >= 0.")
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError("max_gene_set_size must be >= min_gene_set_size.")
    if not (0 < pvalue_cutoff < 1):
        raise ValueError(f"pvalue_cutoff must be in (0, 1); got {pvalue_cutoff}")
    if not experiment_ids:
        raise ValueError("at least one experiment_id required")

    from multiomics_explorer.analysis.enrichment import (
        de_enrichment_inputs, fisher_ora, EnrichmentResult,
    )
    import pandas as pd
    import numpy as np

    conn = _default_conn(conn)

    inputs = de_enrichment_inputs(
        experiment_ids=experiment_ids,
        organism=organism,
        direction=direction,
        significant_only=significant_only,
        timepoint_filter=timepoint_filter,
        growth_phases=growth_phases,
        conn=conn,
    )

    # Resolve background
    if background == "table_scope":
        resolved_bg = inputs.background
        background_mode = "table_scope"
    elif background == "organism":
        org_rows = conn.execute_query(
            "MATCH (g:Gene {organism_name: $org}) "
            "RETURN collect(g.locus_tag) AS locus_tags",
            org=inputs.organism_name,
        )
        org_locus_tags = org_rows[0]["locus_tags"] if org_rows else []
        resolved_bg = {c: list(org_locus_tags) for c in inputs.gene_sets}
        background_mode = "organism"
    else:
        resolved_bg = {c: list(background) for c in inputs.gene_sets}
        background_mode = {
            "explicit": list(background)[:5] + (
                [f"+{len(background) - 5} more"] if len(background) > 5 else []
            ),
        }

    # Apply resolved background to inputs (so accessors see the right background)
    inputs.background = resolved_bg

    # TERM2GENE
    gbo_result = genes_by_ontology(
        ontology=ontology, organism=inputs.organism_name,
        level=level, term_ids=term_ids,
        min_gene_set_size=0, max_gene_set_size=None,
        summary=False, verbose=False,
        limit=None, offset=0, tree=tree,
        conn=conn,
    )
    from multiomics_explorer.analysis.frames import to_dataframe
    term2gene = to_dataframe(gbo_result)

    if term2gene.empty or not inputs.gene_sets:
        result_df = pd.DataFrame()
        result = EnrichmentResult(
            kind="pathway", organism_name=inputs.organism_name,
            ontology=ontology, level=level,
            results=result_df, inputs=inputs, term2gene=term2gene,
        )
    else:
        result = fisher_ora(
            inputs, term2gene,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
        )
        result.kind = "pathway"
        result.ontology = ontology
        result.level = level

        # Attach cluster metadata to rows + signed_score
        md_df = pd.DataFrame.from_dict(
            inputs.cluster_metadata, orient="index"
        ).reset_index().rename(columns={"index": "cluster"})
        result.results = result.results.merge(md_df, on="cluster", how="left")
        sign = np.where(result.results["direction"] == "up", 1,
                        np.where(result.results["direction"] == "down", -1, 0))
        result.results["signed_score"] = (
            sign * -np.log10(result.results["p_adjust"].clip(lower=1e-300))
        )

    # term_validation + clusters_skipped
    result.term_validation = {
        "not_found": list(gbo_result.get("not_found", [])),
        "wrong_ontology": list(gbo_result.get("wrong_ontology", [])),
        "wrong_level": list(gbo_result.get("wrong_level", [])),
        "filtered_out": list(gbo_result.get("filtered_out", [])),
    }
    # clusters_skipped populated from inputs + missing-from-results
    produced = set(result.results["cluster"]) if not result.results.empty else set()
    skipped = []
    for cluster in inputs.cluster_metadata:
        if cluster in produced:
            continue
        if cluster not in inputs.background or not inputs.background.get(cluster):
            reason = "empty_background"
        elif not inputs.gene_sets.get(cluster):
            reason = "empty_gene_set"
        else:
            reason = "no_pathways_in_size_range"
        skipped.append({"cluster": cluster, "reason": reason})
    result.clusters_skipped = skipped

    # enrichment_params
    result.params = {
        "organism": organism, "ontology": ontology,
        "level": level, "term_ids": term_ids, "tree": tree,
        "min_gene_set_size": min_gene_set_size,
        "max_gene_set_size": max_gene_set_size,
        "pvalue_cutoff": pvalue_cutoff,
        "background_mode": background_mode,
        "experiment_ids": experiment_ids,
        "direction": direction,
        "significant_only": significant_only,
        "timepoint_filter": timepoint_filter,
        "growth_phases": growth_phases,
        "n_clusters_input": len(inputs.cluster_metadata),
        "n_clusters_tested": len(produced),
        "n_clusters_skipped": len(skipped),
        "term2gene_row_count": int(len(term2gene)),
        "n_unique_terms": int(term2gene["term_id"].nunique()) if not term2gene.empty else 0,
        "multitest_method": "fdr_bh",
    }

    return result
```

- [ ] **Step 2: Delete `_build_pathway_enrichment_envelope`**

Find it in `api/functions.py` around line 3003 and delete the entire function.
Its logic lives in `EnrichmentResult.generate_summary()` + `.to_envelope()` now.

- [ ] **Step 3: Update `tests/unit/test_api_functions.py`**

Every test that calls `api.pathway_enrichment(...)` and does `result["key"]`
must do `result.to_envelope()["key"]` instead.

```bash
grep -n "pathway_enrichment" tests/unit/test_api_functions.py
```

Update each callsite. Similar for `cluster_enrichment` (done in Task 11).

- [ ] **Step 4: Run test suite**

Run: `uv run pytest tests/unit/test_api_functions.py -k pathway_enrichment -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "refactor: pathway_enrichment returns EnrichmentResult with params"
```

---

### Task 11: Refactor `api.cluster_enrichment` to return `EnrichmentResult`

**Files:**
- Modify: `multiomics_explorer/api/functions.py:3523-3694` (cluster_enrichment)
- Delete: `_build_cluster_enrichment_envelope`
- Test: `tests/unit/test_api_functions.py` + integration

- [ ] **Step 1: Rewrite `cluster_enrichment`**

Same shape as Task 10 but for cluster_enrichment. Key differences:
- `kind="cluster"`
- Uses `cluster_enrichment_inputs` instead of `de_enrichment_inputs`
- No `signed_score` step
- `background_mode` can be `"cluster_union"` / `"organism"` / explicit
- No `direction` / `timepoint_filter` / `growth_phases` / `significant_only` in params

Replace the body of `cluster_enrichment` (starting around `api/functions.py:3523`)
with:

```python
def cluster_enrichment(
    analysis_id: str,
    organism: str,
    ontology: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    background: str | list[str] = "cluster_union",
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    min_cluster_size: int = 3,
    max_cluster_size: int | None = None,
    pvalue_cutoff: float = 0.05,
    tree: str | None = None,
    *,
    conn: GraphConnection | None = None,
):
    """Cluster-based over-representation analysis — returns EnrichmentResult."""
    # --- validation (copy from existing body) ---
    if ontology not in ALL_ONTOLOGIES:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {ALL_ONTOLOGIES}")
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    if level is None and not term_ids:
        raise ValueError("At least one of `level` or `term_ids` must be provided.")
    if isinstance(background, str):
        if background not in {"cluster_union", "organism"}:
            raise ValueError(
                f"background must be 'cluster_union', 'organism', or a list; got {background!r}"
            )
    elif isinstance(background, list):
        if not background:
            raise ValueError("background list must be non-empty")
    else:
        raise ValueError(
            f"background must be 'cluster_union', 'organism', or a list; "
            f"got {type(background).__name__}"
        )
    if min_gene_set_size < 0:
        raise ValueError("min_gene_set_size must be >= 0.")
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError("max_gene_set_size must be >= min_gene_set_size.")
    if min_cluster_size < 0:
        raise ValueError("min_cluster_size must be >= 0.")
    if max_cluster_size is not None and max_cluster_size < min_cluster_size:
        raise ValueError("max_cluster_size must be >= min_cluster_size.")
    if not (0 < pvalue_cutoff < 1):
        raise ValueError(f"pvalue_cutoff must be in (0, 1]; got {pvalue_cutoff}")

    from multiomics_explorer.analysis.enrichment import (
        cluster_enrichment_inputs, fisher_ora, EnrichmentResult,
    )
    import pandas as pd

    conn = _default_conn(conn)

    inputs = cluster_enrichment_inputs(
        analysis_id=analysis_id,
        organism=organism,
        min_cluster_size=min_cluster_size,
        max_cluster_size=max_cluster_size,
        conn=conn,
    )

    # Resolve background
    if background == "cluster_union":
        resolved_bg = inputs.background
        background_mode = "cluster_union"
    elif background == "organism":
        org_rows = conn.execute_query(
            "MATCH (g:Gene {organism_name: $org}) "
            "RETURN collect(g.locus_tag) AS locus_tags",
            org=inputs.organism_name,
        )
        org_locus_tags = org_rows[0]["locus_tags"] if org_rows else []
        resolved_bg = {c: list(org_locus_tags) for c in inputs.gene_sets}
        background_mode = "organism"
    else:
        resolved_bg = {c: list(background) for c in inputs.gene_sets}
        background_mode = {
            "explicit": list(background)[:5] + (
                [f"+{len(background) - 5} more"] if len(background) > 5 else []
            ),
        }
    inputs.background = resolved_bg

    # If no gene sets (analysis not found / empty) → empty result
    if not inputs.gene_sets:
        result = EnrichmentResult(
            kind="cluster", organism_name=inputs.organism_name,
            ontology=ontology, level=level,
            results=pd.DataFrame(), inputs=inputs, term2gene=pd.DataFrame(),
        )
        result.term_validation = {
            "not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": [],
        }
        result.clusters_skipped = list(inputs.clusters_skipped)
        result.params = _cluster_enrichment_params_dict(
            analysis_id=analysis_id, organism=organism,
            ontology=ontology, level=level, term_ids=term_ids, tree=tree,
            background_mode=background_mode,
            min_gene_set_size=min_gene_set_size, max_gene_set_size=max_gene_set_size,
            min_cluster_size=min_cluster_size, max_cluster_size=max_cluster_size,
            pvalue_cutoff=pvalue_cutoff,
            inputs=inputs, produced=set(), term2gene=pd.DataFrame(),
        )
        return result

    # TERM2GENE
    gbo_result = genes_by_ontology(
        ontology=ontology, organism=inputs.organism_name,
        level=level, term_ids=term_ids,
        min_gene_set_size=0, max_gene_set_size=None,
        summary=False, verbose=False,
        limit=None, offset=0, tree=tree,
        conn=conn,
    )
    from multiomics_explorer.analysis.frames import to_dataframe
    term2gene = to_dataframe(gbo_result)

    if term2gene.empty:
        result = EnrichmentResult(
            kind="cluster", organism_name=inputs.organism_name,
            ontology=ontology, level=level,
            results=pd.DataFrame(), inputs=inputs, term2gene=term2gene,
        )
    else:
        result = fisher_ora(
            inputs, term2gene,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
        )
        result.kind = "cluster"
        result.ontology = ontology
        result.level = level
        # Attach cluster metadata
        if not result.results.empty:
            md_df = pd.DataFrame.from_dict(
                inputs.cluster_metadata, orient="index"
            ).reset_index().rename(columns={"index": "cluster"})
            result.results = result.results.merge(md_df, on="cluster", how="left")

    result.term_validation = {
        "not_found": list(gbo_result.get("not_found", [])),
        "wrong_ontology": list(gbo_result.get("wrong_ontology", [])),
        "wrong_level": list(gbo_result.get("wrong_level", [])),
        "filtered_out": list(gbo_result.get("filtered_out", [])),
    }

    produced = set(result.results["cluster"]) if not result.results.empty else set()
    skipped = list(inputs.clusters_skipped)
    skipped_names = {s.get("cluster_name") for s in skipped}
    for cluster in inputs.cluster_metadata:
        if cluster in produced or cluster in skipped_names:
            continue
        if cluster not in inputs.background or not inputs.background.get(cluster):
            reason = "empty_background"
        elif not inputs.gene_sets.get(cluster):
            reason = "empty_gene_set"
        else:
            reason = "no_pathways_in_size_range"
        skipped.append({"cluster_name": cluster, "reason": reason})
    result.clusters_skipped = skipped

    result.params = _cluster_enrichment_params_dict(
        analysis_id=analysis_id, organism=organism,
        ontology=ontology, level=level, term_ids=term_ids, tree=tree,
        background_mode=background_mode,
        min_gene_set_size=min_gene_set_size, max_gene_set_size=max_gene_set_size,
        min_cluster_size=min_cluster_size, max_cluster_size=max_cluster_size,
        pvalue_cutoff=pvalue_cutoff,
        inputs=inputs, produced=produced, term2gene=term2gene,
    )
    return result


def _cluster_enrichment_params_dict(
    *, analysis_id, organism, ontology, level, term_ids, tree, background_mode,
    min_gene_set_size, max_gene_set_size,
    min_cluster_size, max_cluster_size, pvalue_cutoff,
    inputs, produced, term2gene,
):
    return {
        "analysis_id": analysis_id, "organism": organism,
        "ontology": ontology, "level": level, "term_ids": term_ids, "tree": tree,
        "background_mode": background_mode,
        "min_gene_set_size": min_gene_set_size,
        "max_gene_set_size": max_gene_set_size,
        "min_cluster_size": min_cluster_size,
        "max_cluster_size": max_cluster_size,
        "pvalue_cutoff": pvalue_cutoff,
        "n_clusters_input": len(inputs.cluster_metadata),
        "n_clusters_tested": len(produced),
        "n_clusters_skipped": len(inputs.clusters_skipped),
        "term2gene_row_count": int(len(term2gene)),
        "n_unique_terms": int(term2gene["term_id"].nunique()) if not term2gene.empty else 0,
        "multitest_method": "fdr_bh",
    }
```

- [ ] **Step 2: Delete `_build_cluster_enrichment_envelope`**

Find around `api/functions.py:3380` and delete.

- [ ] **Step 3: Update `tests/unit/test_api_functions.py`**

Migrate `cluster_enrichment` test assertions to `.to_envelope()`.

- [ ] **Step 4: Run test suite**

Run: `uv run pytest tests/unit/test_api_functions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "refactor: cluster_enrichment returns EnrichmentResult"
```

---

## Phase 5 — MCP + docs + tests

### Task 12: Update MCP wrappers

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` (lines around 3746-3864, 3871-3930)
- Test: `tests/integration/test_mcp_tools.py`

- [ ] **Step 1: Update pathway_enrichment wrapper**

In `mcp_server/tools.py` around line 3746, find the `pathway_enrichment` tool
function. Remove the `verbose` parameter from its signature and from the API
call. Change the final return from `PathwayEnrichmentResponse(**result)` to:

```python
        envelope = result.to_envelope(summary=summary, limit=limit, offset=offset)
        # Emit warnings on non-empty validation buckets
        warnings = []
        if envelope["not_found"]:
            warnings.append(f"{len(envelope['not_found'])} experiment_ids not_found")
        if envelope["not_matched"]:
            warnings.append(f"{len(envelope['not_matched'])} not_matched (wrong organism)")
        if envelope.get("no_expression"):
            warnings.append(f"{len(envelope['no_expression'])} no_expression (no DE rows)")
        tv = envelope.get("term_validation", {})
        for key in ("not_found", "wrong_ontology", "wrong_level"):
            if tv.get(key):
                warnings.append(f"{len(tv[key])} term_ids {key}")
        if envelope.get("clusters_skipped"):
            warnings.append(f"{len(envelope['clusters_skipped'])} clusters skipped")
        if warnings:
            await ctx.warning("; ".join(warnings))

        return PathwayEnrichmentResponse(**envelope)
```

Also remove `verbose=verbose` from the `api.pathway_enrichment(...)` call
arguments (the API function no longer takes it).

- [ ] **Step 2: Update cluster_enrichment wrapper**

Similar change in the `cluster_enrichment` MCP tool around line 3871. Remove
`verbose` parameter and call, replace return with:

```python
        envelope = result.to_envelope(summary=summary, limit=limit, offset=offset)
        # warnings logic as above (reuse buckets that are relevant to cluster_enrichment)
        warnings = []
        if envelope["not_found"]:
            warnings.append(f"{len(envelope['not_found'])} not_found")
        if envelope["not_matched"]:
            warnings.append(f"{len(envelope['not_matched'])} not_matched")
        tv = envelope.get("term_validation", {})
        for key in ("not_found", "wrong_ontology", "wrong_level"):
            if tv.get(key):
                warnings.append(f"{len(tv[key])} term_ids {key}")
        if envelope.get("clusters_skipped"):
            warnings.append(f"{len(envelope['clusters_skipped'])} clusters skipped")
        if warnings:
            await ctx.warning("; ".join(warnings))

        return ClusterEnrichmentResponse(**envelope)
```

- [ ] **Step 3: Update PathwayEnrichmentResponse / ClusterEnrichmentResponse Pydantic models**

In `mcp_server/tools.py` around line 25 (for pathway) and 260 (for cluster),
the response models use Pydantic. Ensure their shapes match the
`to_envelope()` output (they should, since the spec says envelope shape is
preserved). Spot-check by running contract tests.

- [ ] **Step 4: Update integration tests**

In `tests/integration/test_mcp_tools.py`, ensure no tests call
`pathway_enrichment(..., verbose=True)` or read stripped-column behavior.

- [ ] **Step 5: Run integration tests**

Run: `uv run pytest -m kg tests/integration/ -v -k enrichment`
Expected: PASS (requires Neo4j at localhost:7687).
If Neo4j unavailable, run the unit-level MCP tests: `uv run pytest tests/unit -k mcp -v`.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/integration/test_mcp_tools.py
git commit -m "refactor: MCP wrappers call to_envelope; drop verbose param"
```

---

### Task 13: Update YAMLs and regenerate tool reference MDs

**Files:**
- Modify: `multiomics_explorer/inputs/tools/pathway_enrichment.yaml`
- Modify: `multiomics_explorer/inputs/tools/cluster_enrichment.yaml`
- Regenerate: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/pathway_enrichment.md`
- Regenerate: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md`

- [ ] **Step 1: Edit `pathway_enrichment.yaml`**

Open `multiomics_explorer/inputs/tools/pathway_enrichment.yaml`. Search for a
`verbose:` entry under parameters; delete the entry (keep the rest unchanged).

- [ ] **Step 2: Edit `cluster_enrichment.yaml`**

Same for `cluster_enrichment.yaml` — delete `verbose:` entry.

- [ ] **Step 3: Regenerate tool reference MDs**

Delete the stale MDs first, then regenerate:

```bash
rm multiomics_explorer/skills/multiomics-kg-guide/references/tools/pathway_enrichment.md
rm multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md
uv run python scripts/build_about_content.py
```

Verify the outputs were created:

```bash
ls -la multiomics_explorer/skills/multiomics-kg-guide/references/tools/pathway_enrichment.md
ls -la multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md
```

- [ ] **Step 4: Verify `verbose` is absent from generated MDs**

```bash
grep -n "verbose" multiomics_explorer/skills/multiomics-kg-guide/references/tools/pathway_enrichment.md multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md
```

Expected: no matches (or no parameter-row matches).

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/inputs/tools/pathway_enrichment.yaml \
        multiomics_explorer/inputs/tools/cluster_enrichment.yaml \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/pathway_enrichment.md \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md
git commit -m "docs: drop verbose from enrichment tool YAMLs; regenerate MDs"
```

---

### Task 14: Rewrite `examples/pathway_enrichment.py`

**Files:**
- Modify: `examples/pathway_enrichment.py`

- [ ] **Step 1: Replace with a demonstration script**

Overwrite `examples/pathway_enrichment.py` with (adapt imports / organism /
experiment_ids to match a realistic KG in this project):

```python
"""Example: pathway enrichment with the EnrichmentResult API.

Demonstrates:
  - pathway_enrichment returns an EnrichmentResult object
  - result.results DataFrame for pandas slicing/plotting
  - result.explain(cluster, term_id) for per-term drill-down
  - result.overlap_genes / background_genes accessors
  - result.to_compare_cluster_frame() for clusterProfiler-style output
  - result.generate_summary() for the aggregate view
  - result.to_envelope() for the MCP-compatible dict
  - Custom term2gene path (hand-built, no KG)

Run with: uv run python examples/pathway_enrichment.py
"""
from __future__ import annotations

import pandas as pd
from multiomics_explorer import (
    EnrichmentInputs,
    EnrichmentResult,
    fisher_ora,
    pathway_enrichment,
)


def demo_mcp_path():
    """High-level API demo (requires KG)."""
    result: EnrichmentResult = pathway_enrichment(
        organism="MED4",
        experiment_ids=["EXP042"],
        ontology="go",
        level=2,
    )
    print(f"kind={result.kind}  rows={len(result.results)}")
    print(result.results.head())

    if not result.results.empty:
        first = result.results.iloc[0]
        exp = result.explain(first["cluster"], first["term_id"])
        print(exp._repr_markdown_())
        overlap = result.overlap_genes(first["cluster"], first["term_id"])
        print(f"Overlap genes: {[g.locus_tag for g in overlap]}")

    # Aggregate view vs full envelope
    summary = result.generate_summary()
    print(f"n_significant={summary['n_significant']}")
    envelope = result.to_envelope(limit=5)
    print(f"returned={envelope['returned']}, truncated={envelope['truncated']}")


def demo_custom_term2gene():
    """Low-level fisher_ora demo with hand-built term2gene (no KG)."""
    # Minimal term2gene WITHOUT gene_name / product columns.
    term2gene = pd.DataFrame([
        {"term_id": "MY_PATHWAY", "term_name": "My pathway", "locus_tag": f"g{i}"}
        for i in range(1, 11)
    ])
    inputs = EnrichmentInputs(
        organism_name="custom",
        gene_sets={"my_cluster": ["g1", "g2", "g3"]},
        background={"my_cluster": [f"g{i}" for i in range(1, 21)]},
        cluster_metadata={"my_cluster": {}},
    )
    result = fisher_ora(inputs, term2gene, min_gene_set_size=0)
    print(result.results)
    # Name falls back to locus_tag — no error
    overlap = result.overlap_genes("my_cluster", "MY_PATHWAY")
    for g in overlap:
        assert g.gene_name is None
        print(g.locus_tag)


def demo_compare_cluster():
    """Export to clusterProfiler compareCluster format for plotting."""
    result = pathway_enrichment(
        organism="MED4", experiment_ids=["EXP042"], ontology="go", level=2,
    )
    cc_frame = result.to_compare_cluster_frame()
    print(cc_frame.head())
    # cc_frame is ready for dotplot / emapplot in R via feather/CSV export.


if __name__ == "__main__":
    print("=== Custom term2gene (no KG) ===")
    demo_custom_term2gene()
    print("\n=== KG-backed pathway_enrichment ===")
    try:
        demo_mcp_path()
        demo_compare_cluster()
    except Exception as e:
        print(f"(skipped KG demos: {e})")
```

- [ ] **Step 2: Smoke-run the non-KG demo**

```bash
uv run python -c "from examples.pathway_enrichment import demo_custom_term2gene; demo_custom_term2gene()"
```

Expected: prints a small DataFrame + locus tags.

- [ ] **Step 3: Commit**

```bash
git add examples/pathway_enrichment.py
git commit -m "docs: rewrite pathway_enrichment example for EnrichmentResult API"
```

---

### Task 15: Update canonical `enrichment.md` and delete orphan

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md`
- Delete: `multiomics_explorer/analysis/enrichment.md`

- [ ] **Step 1: Add a new section to the canonical enrichment.md**

Open `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md`
and find a good anchor (after the existing §5 on cluster enrichment or at the end).
Add a new section covering the EnrichmentResult API:

````markdown
## §N. `EnrichmentResult` — rich return type

Both `pathway_enrichment` and `cluster_enrichment` return an `EnrichmentResult`
object (not a dict). `fisher_ora` also returns one when called directly.

**Attributes:**
- `result.results` — pandas DataFrame, one row per (cluster × term).
- `result.inputs` — `EnrichmentInputs` (gene_sets, background, cluster_metadata,
  optional `gene_stats`).
- `result.term2gene` — DataFrame used for overlap computation and GeneRef data.
- `result.params` — dict of ORA parameters for reproducibility.
- `result.kind` — `"pathway"` or `"cluster"`.

**Accessors** (only methods that join results + inputs or compute something
non-trivial; pure slicing uses `result.results` directly):
- `explain(cluster, term_id) -> EnrichmentExplanation` — full narrative +
  Fisher numbers + sorted gene refs. `_repr_markdown_` renders in Jupyter.
- `overlap_genes(cluster, term_id) -> list[GeneRef]` — the k genes.
- `background_genes(cluster, term_id) -> list[GeneRef]` — the M genes.
- `cluster_context(cluster) -> dict` — metadata + n_tests + n_significant.
- `why_skipped(cluster) -> str | None` — reason from clusters_skipped.
- `to_compare_cluster_frame() -> pd.DataFrame` — clusterProfiler convention
  (`Cluster`, `ID`, `Description`, `GeneRatio`, `BgRatio`, `pvalue`, `p.adjust`, `geneID`).
- `missing_terms() -> dict[str, list[str]]` — term_validation buckets.
- `generate_summary() -> dict` — aggregate view (no rows, no pagination).
- `to_envelope(*, summary=False, limit=None, offset=0) -> dict` —
  MCP-compatible dict. Called internally by MCP tool wrappers; Python
  callers rarely need it.

**Pydantic models:** `DEStats`, `GeneRef`, `EnrichmentExplanation` — see
module docstrings for field semantics.

**`term2gene` required vs optional columns:**

| Column | Status | Used by |
|---|---|---|
| `term_id` | required | Fisher math |
| `term_name` | required | Narrative |
| `locus_tag` | required | Fisher math |
| `gene_name` | *optional* | `GeneRef.gene_name` (None if absent) |
| `product` | *optional* | `GeneRef.product` (None if absent) |

Custom-built term2gene works — missing optional columns just yield `None`
GeneRef fields.

**`fisher_ora` signature change:** takes `EnrichmentInputs` + `term2gene` and
returns `EnrichmentResult`. Callers without a KG construct `EnrichmentInputs`
with just `gene_sets`, `background`, `organism_name`; `gene_stats` defaults
to empty.

**MCP schema change:** the `verbose` parameter was removed from
`pathway_enrichment` and `cluster_enrichment` tool schemas (it was phantom
— stripping columns that were never populated). Rich per-row overlap lives
in the Python API (`.explain()` / accessors).
````

- [ ] **Step 2: Bring cluster_enrichment mentions forward**

Compare with `multiomics_explorer/analysis/enrichment.md` (the deprecated copy).
Copy any cluster_enrichment-related paragraphs that only exist in the old copy
into the canonical location. Key known drift (see spec): lines 202-205 and
494-496 in the old copy.

- [ ] **Step 3: Delete orphaned duplicate**

```bash
git rm multiomics_explorer/analysis/enrichment.md
```

- [ ] **Step 4: Verify nothing references the deleted file at runtime**

```bash
grep -rn "multiomics_explorer/analysis/enrichment\.md" multiomics_explorer/ tests/ scripts/ examples/ 2>/dev/null
```

Expected: no matches.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md
git commit -m "docs: update canonical enrichment.md; delete orphaned duplicate"
```

---

### Task 16: Migrate remaining integration, regression, and eval tests

**Files:**
- Modify: `tests/integration/test_api_contract.py`
- Modify: `tests/integration/test_mcp_tools.py`
- Modify: `tests/regression/test_regression.py`
- Modify: `tests/evals/test_eval.py`

- [ ] **Step 1: Audit each test file for envelope-dict access**

For each file above, run:

```bash
grep -n "pathway_enrichment\|cluster_enrichment" tests/integration/test_api_contract.py tests/integration/test_mcp_tools.py tests/regression/test_regression.py tests/evals/test_eval.py
```

Note every callsite.

- [ ] **Step 2: Migrate each callsite**

For calls like:
```python
result = api.pathway_enrichment(...)
assert result["total_matching"] > 0
```

Change to:
```python
result = api.pathway_enrichment(...)
envelope = result.to_envelope()
assert envelope["total_matching"] > 0
```

For MCP-tool tests that go through the MCP wrapper, **no change is needed** —
the wrapper returns the Pydantic response model constructed from
`to_envelope()`, so the shape is preserved.

For regression fixtures that snapshot the return of `pathway_enrichment`,
change the fixture load point to `result.to_envelope()` and regenerate
fixtures if shape has drifted.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v -x
```

Expected: all tests PASS (or skip if Neo4j unavailable for `-m kg`).

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: migrate envelope-dict assertions to result.to_envelope()"
```

---

## Final verification

### Task 17: End-to-end validation

- [ ] **Step 1: Run full unit test suite**

```bash
uv run pytest tests/unit/ -v
```

Expected: all PASS.

- [ ] **Step 2: Run integration tests (requires Neo4j)**

```bash
uv run pytest -m kg tests/integration/ -v
```

Expected: all PASS. Skip if no Neo4j running.

- [ ] **Step 3: Smoke-test the MCP server**

```bash
uv run multiomics-kg-mcp &
MCP_PID=$!
sleep 2
# If you have an MCP client script or just verify no startup error:
kill $MCP_PID
```

Expected: server starts without errors (check stderr).

- [ ] **Step 4: Smoke-test the example**

```bash
uv run python examples/pathway_enrichment.py
```

Expected: the custom-term2gene demo runs cleanly; KG demos may skip if no KG.

- [ ] **Step 5: Run the example + doctest**

```bash
uv run python -c "from multiomics_explorer import EnrichmentResult, EnrichmentExplanation, GeneRef, DEStats, fisher_ora; print('imports OK')"
```

Expected: `imports OK` printed, no traceback.

- [ ] **Step 6: Final commit if anything needs fixing up**

If Steps 1-5 revealed issues, fix them and commit. Otherwise this task is
a no-op verification.

---

## Summary of commits (for reference when executing)

1. `feat: add DEStats, GeneRef, EnrichmentExplanation Pydantic models` (Task 1)
2. `feat: add gene_stats field to EnrichmentInputs` (Task 2)
3. `refactor: fisher_ora returns EnrichmentResult; add dataclass skeleton` (Task 3)
4. `feat: EnrichmentResult overlap_genes / background_genes accessors` (Task 4)
5. `feat: EnrichmentResult.explain() with narrative repr` (Task 5)
6. `feat: EnrichmentResult nice-to-have accessors` (Task 6)
7. `feat: EnrichmentResult.generate_summary with pathway/cluster dispatch` (Task 7)
8. `feat: EnrichmentResult.to_envelope with pagination` (Task 8)
9. `feat: de_enrichment_inputs populates gene_stats for all measured genes` (Task 9)
10. `refactor: pathway_enrichment returns EnrichmentResult with params` (Task 10)
11. `refactor: cluster_enrichment returns EnrichmentResult` (Task 11)
12. `refactor: MCP wrappers call to_envelope; drop verbose param` (Task 12)
13. `docs: drop verbose from enrichment tool YAMLs; regenerate MDs` (Task 13)
14. `docs: rewrite pathway_enrichment example for EnrichmentResult API` (Task 14)
15. `docs: update canonical enrichment.md; delete orphaned duplicate` (Task 15)
16. `test: migrate envelope-dict assertions to result.to_envelope()` (Task 16)
