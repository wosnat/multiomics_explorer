# Research checklist

Step-by-step protocol for answering a biological research question
using the multiomics KG.

---

## Before starting

- [ ] Restate the research question precisely
- [ ] Identify what kind of question it is:
  - **Lookup** — gene identity, function, annotations → MCP only
  - **Survey** — one gene across conditions, or one condition across
    genes → MCP + maybe extraction
  - **Comparative** — two conditions, two organisms, pathway
    comparison → extraction + statistics required
  - **Discovery** — enrichment, clustering, unbiased screen →
    full extraction + computational pipeline required
- [ ] For comparative/discovery: create the analysis directory
  structure (see artifacts guide)

---

## Phase 1: Orientation

- [ ] `list_organisms` — confirm target organisms are in the KG
- [ ] `list_publications` — find relevant studies
- [ ] `list_experiments(summary=true)` — understand available
  conditions, time points, omics types
- [ ] `list_experiments` with filters — get specific experiment IDs
- [ ] **Gate: scope check**
  - Are the needed organisms present?
  - Are there experiments for the conditions of interest?
  - What data types are available (transcriptomics, proteomics)?
  - Document any gaps: "The KG does not contain [X] data for [Y]"

---

## Phase 2: Gene identification

- [ ] Identify genes of interest using appropriate discovery tools:
  - By name/keyword: `resolve_gene`, `genes_by_function`
  - By pathway/ontology: `search_ontology` → `genes_by_ontology`
  - By homology: `search_homolog_groups` → `genes_by_homolog_group`
  - By prior knowledge: start with `resolve_gene` for known names
- [ ] Resolve all gene names to locus tags
- [ ] Check for paralogs — multiple locus tags per gene name?
  - If yes: `gene_overview` on all locus tags, treat separately
- [ ] `gene_overview` — confirm annotation types, expression data
  availability, ortholog coverage
- [ ] **Gate: gene set complete?**
  - Check `total_matching` — is the full set captured?
  - Are there genes with no expression data? Flag them.
  - Are paralogs identified and catalogued?
  - Record the gene set with locus tags in methods.md

---

## Phase 3: Expression analysis

### For MCP-scale results (few genes, few experiments)
- [ ] `differential_expression_by_gene` — gene-centric, per organism
- [ ] Check summary fields: total results, direction breakdown
- [ ] If `truncated: false` — results are complete, can interpret
  directly

### For analyses requiring full data
- [ ] Check `truncated` flag — if true, must extract via package
- [ ] Write extraction script using Python package:
  ```python
  from multiomics_explorer import differential_expression_by_gene
  data = differential_expression_by_gene(
      organism="...", locus_tags=[...], experiment_ids=[...])
  pd.DataFrame(data["results"]).to_csv("data/de_genes.csv")
  ```
- [ ] Verify extraction: row count matches `total_matching` from
  MCP summary
- [ ] **Gate: data completeness**
  - All expected genes present?
  - All expected experiments present?
  - Missing data documented?

### For cross-organism comparison
- [ ] `differential_expression_by_ortholog` for cluster-level view
- [ ] `genes_by_homolog_group` for cluster membership
- [ ] Verify ortholog assignments — are the right groups selected?
- [ ] Missing organisms in a group = no homolog, not missing data

---

## Phase 4: Analysis and computation

All computation happens in scripts, not chat.

- [ ] Write analysis scripts in `scripts/`
- [ ] Scripts read from `data/`, write to `results/`
- [ ] Include in scripts:
  - Library imports with version logging
  - Clear input/output file paths
  - Statistical methods with parameters
  - Seed setting for reproducibility where applicable
- [ ] **Gate: outputs valid?**
  - Do output files exist and are non-empty?
  - Do row/gene counts match expectations?
  - Are statistical assumptions met?

---

## Phase 5: Interpretation and documentation

- [ ] Interpret results using biological context
- [ ] Flag where intrinsic knowledge is used vs KG data
- [ ] Write `methods.md` with all required sections:
  - Research question
  - Data scope (organisms, experiments, conditions — with IDs)
  - Gene selection method and filtering steps
  - Statistical methods and parameters
  - Results summary with effect sizes and p-values
  - Limitations and KG gaps
- [ ] Write `README.md` — summary, key findings, file index
- [ ] Populate `references.md` or `references.bib`
- [ ] **Gate: reproducibility check**
  - Can the analysis be rerun from scripts alone?
  - Are all data sources documented?
  - Are all decisions explained in methods.md?

---

## Review (self or peer)

- [ ] Every number traces to a named KG query or script output
- [ ] No gene name used without its locus tag
- [ ] Paralogs and orthologs handled correctly
- [ ] Truncation metadata respected (not counting from limited rows)
- [ ] Statistical methods appropriate and documented
- [ ] KG gaps and limitations explicitly stated
- [ ] All artifact files exist and are consistent with the narrative
- [ ] Claims match the data — no over-interpretation
