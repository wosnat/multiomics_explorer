---
name: research
description: Academic research methodology for multi-omics analysis. Activate when answering biological questions, analyzing expression data, or producing research artifacts.
argument-hint: "[research question or 'review' to audit an existing analysis]"
---

# Research methodology

See [research checklist](references/research-checklist.md) for the
step-by-step protocol, [artifacts guide](references/artifacts-guide.md)
for output structure, and [anti-hallucination](references/anti-hallucination.md)
for concrete failure modes to avoid.

## Core principles

### 1. KG is the sole data source

Every claim must trace to a KG query. Never rely on intrinsic
knowledge for data — gene names, expression values, experiment
details, organism properties, ortholog assignments. Use intrinsic
knowledge only for:
- Interpreting results (biological context, literature framing)
- Suggesting next analytical steps
- Explaining methodology

**When the KG is insufficient**, say so explicitly. Common gaps:
- Missing organisms or strains not yet in the KG
- Annotations not loaded (e.g., some GO terms, regulatory elements)
- Expression data not available for a condition/study
- No adjusted p-values in the original dataset
- Missing metadata (timepoints, replicates, normalization method)

Do not fill gaps with assumptions or intrinsic knowledge. Document
what is missing and flag it as a limitation.

### 2. Reproducibility over convenience

Every analysis must be reproducible without access to the Claude
conversation. This means:
- **Scripts over chat reasoning** — computations go in `.py` files,
  not in chat responses
- **Data staged to files** — KG extracts saved as CSV/TSV before
  analysis, using the Python package (not MCP tool output)
- **Methods documented** — every decision recorded in `methods.md`
  as it happens, not retroactively
- **No manual steps** — if it can't be scripted, document it as a
  limitation

### 3. Locus tags, not gene names

Gene names are ambiguous. The catalase analysis showed that "katA"
maps to two paralogs per strain with opposite expression behavior,
and "katB" was conflated with "katE" in a different strain. Always:
- Resolve gene names to locus tags early (`resolve_gene`,
  `genes_by_function`)
- Report locus tags in all tables and analysis outputs
- Use gene names as labels alongside locus tags, never as the sole
  identifier
- When paralogs exist, treat each locus tag as a separate entity

### 4. Artifacts, not answers

Research questions produce files, not chat messages. Chat is for
reasoning, planning, and interpretation. Data, statistics, and
figures go to disk. See the [artifacts guide](references/artifacts-guide.md).

---

## The 3-phase workflow

Follow the tool framework phases. Each phase produces outputs that
feed the next.

### Phase 1: Orientation

Establish scope before touching data.

- `list_organisms` — what species/strains are available
- `list_publications` — what studies cover the question
- `list_experiments` — which experiments, conditions, time points

**Gate:** Can the KG answer this question? If key organisms,
conditions, or data types are missing, report the gap before
proceeding.

### Phase 2: Gene work

Identify and characterize genes of interest.

- Discovery: `resolve_gene`, `genes_by_function`, `genes_by_ontology`,
  `genes_by_homolog_group`
- Details: `gene_overview`, `gene_ontology_terms`, `gene_homologs`
- Annotation: `search_ontology`, `search_homolog_groups`

**Gate:** Are all genes resolved to locus tags? Are paralogs
identified and separated? Is the gene set complete (check
`total_matching` vs `returned`)?

### Phase 3: Expression

Explore expression of selected genes in selected experiments.

- `differential_expression_by_gene` — single organism, gene-centric
- `differential_expression_by_ortholog` — cross-organism, cluster-centric

**Gate:** Is data truncated? If `truncated: true`, extract full
data via Python package before computing statistics.

---

## MCP vs Python package

| Use MCP when | Use Python package when |
|---|---|
| Browsing and orienting | Extracting full datasets |
| Checking gene counts and summaries | Running enrichment or statistics |
| Navigating between tools | Producing tables and figures |
| Quick lookups (< 50 results) | Any computation on gene lists |
| Working in chat mode | Result set > MCP limit |

The decision point: if `truncated: true` in MCP output and you
need the full data, switch to package import in a script.

```python
from multiomics_explorer import differential_expression_by_gene
data = differential_expression_by_gene(
    experiment_ids=["..."], significant_only=True)
# limit=None by default in api/ -> all rows
pd.DataFrame(data["results"]).to_csv("data/de_genes.csv", index=False)
```

---

## Statistical rigor

### What the KG provides
- log2FC and padj from the original DESeq2 analysis
- Per-study statistics — do not combine p-values across studies
- Precomputed summary counts (gene counts, significant counts)

### What you must do in scripts
- Enrichment analysis (Fisher's exact, hypergeometric) with proper
  background set from the KG
- Multiple testing correction when comparing across conditions
- Effect size reporting (not just significance)
- Volcano plots, heatmaps with proper clustering

### What to flag
- Studies without adjusted p-values (report as fold-change only)
- Borderline significance (padj near 0.05)
- Duplicate KG entries for the same gene/condition (different
  contrasts — investigate, don't cherry-pick)
- Small sample sizes or missing replicates
- Conflation of paralogs or orthologs in aggregated results

---

## References and citations

### Publication tracking
- Record publication DOIs from `list_publications` output
- Every experiment traces to a publication — maintain this link
  throughout the analysis
- Cite the original study when presenting its expression data

### Methods referencing
- KG version/build date (from `kg_schema` or connection metadata)
- Tool versions and parameters used
- Statistical software versions (scipy, statsmodels, etc.)
- Python and package versions

### Reference library
For analyses that produce a manuscript or report:
- Maintain a `references.bib` or `references.md` in the analysis
  directory
- Include: original data publications, methods references (DESeq2,
  enrichment tools), KG/tool citations
- Link each claim in the analysis to its data source (KG query)
  and original publication

---

## Review protocol

Every analysis should be reviewed. Use `/research review` or
apply this checklist:

1. **Data provenance** — Can every number be traced to a KG query?
2. **Gene identity** — Are locus tags used throughout? Are paralogs
   separated?
3. **Completeness** — Were full datasets extracted for statistical
   analyses, or were truncated MCP results used?
4. **Statistics** — Were p-values taken from the KG (original study)
   or computed? If computed, is the method documented?
5. **Gaps declared** — Are KG limitations and missing data explicitly
   stated?
6. **Reproducibility** — Can someone run `python scripts/*.py` and
   reproduce the results?
7. **Artifacts** — Do all claimed files exist and contain what
   they should?
