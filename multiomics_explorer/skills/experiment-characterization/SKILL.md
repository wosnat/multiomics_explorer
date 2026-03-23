---
name: experiment-characterization
description: "Pipeline skill: characterize a differential expression experiment — orient, scope, extract complete gene lists, run enrichment, produce artifacts."
skill-type: research
skill-layer: 2
trigger: "Questions like 'What happens when you starve MED4 of nitrogen?', 'Characterize this experiment', 'What genes respond to coculture?', or any question about the transcriptional/proteomic response in a specific condition."
---

# Experiment characterization

Characterize the transcriptional or proteomic response in a
differential expression experiment. Produces a complete analysis
with enrichment, visualization, and a publication-ready methods
document.

**When to use this skill:** The researcher asks about what happens
in a condition, what genes respond, or what pathways are affected
in a specific experiment or treatment. The question implies a
structured analysis, not just a lookup.

**What this skill produces:**

```
analyses/{analysis_name}/
├── data/          # complete gene lists from KG
├── scripts/       # extraction + analysis scripts
├── results/       # enrichment tables, volcano plot, summary stats
├── README.md      # findings summary, file index
└── methods.md     # publication-ready methods
```

---

## Pipeline

### Step 1: Orient — identify the experiment

**Goal:** Find the specific experiment(s) that match the
researcher's question. Establish scope.

**Tools:** `list_experiments`, `list_organisms`, `list_publications`

```
list_experiments(summary=True, organism="<organism>", treatment_type=["<treatment>"])
→ see how many experiments match, check by_organism and by_treatment_type breakdowns

list_experiments(organism="<organism>", treatment_type=["<treatment>"], verbose=True)
→ browse individual experiments, read treatment/control descriptions
```

**Decision point:** If multiple experiments match, present them to
the researcher with key differences (omics type, publication,
coculture partner, time-course vs endpoint) and ask which to use.
Do not pick silently.

**Gate 1 — Scope confirmed:**
- [ ] Experiment ID(s) selected
- [ ] Organism and condition confirmed with researcher
- [ ] Time-course vs endpoint understood
- [ ] Omics type noted (affects downstream interpretation)

---

### Step 2: Survey — what does the response look like?

**Goal:** Get summary statistics for the experiment's differential
expression profile without pulling full data into context.

**Tools:** `list_experiments` (already have gene_count and
significant_count from step 1)

From step 1 results, note:
- `gene_count` — total genes with expression data
- `significant_count` — genes with significant DE
- Ratio tells you how broad or targeted the response is

If time-course: note `time_points` array — how many time points,
gene counts per point.

**Gate 2 — Response characterized:**
- [ ] Total gene count and significant count recorded
- [ ] If time-course: time points enumerated
- [ ] Proportion significant noted (broad vs targeted response)

---

### Step 3: Extract — get complete gene lists

**Goal:** Extract the full set of differentially expressed genes
to disk via package import. Never rely on MCP truncated results
for downstream analysis.

**Why package import:** MCP returns at most `limit` rows through
context. Enrichment requires the complete gene list. Using
truncated data produces wrong biological conclusions.

**Action:** Write and run an extraction script.

```python
# scripts/extract_de_genes.py
"""Extract DE genes for experiment characterization."""
from multiomics_explorer import differential_expression_by_gene
import pandas as pd

result = differential_expression_by_gene(
    experiment_ids=["<experiment_id>"],
    significant_only=True,
)

df = pd.DataFrame(result["results"])
df.to_csv("data/de_genes_significant.csv", index=False)
print(f"Extracted {len(df)} significant DE genes")
print(f"Direction breakdown: {df['direction'].value_counts().to_dict()}")
```

**Gate 3 — Data complete:**
- [ ] Script ran successfully
- [ ] Output CSV exists and is non-empty
- [ ] Row count matches `significant_count` from step 2 (± small
      tolerance for filtering differences)
- [ ] Direction breakdown (up/down) is plausible

If row count is far from `significant_count`, investigate before
proceeding. Do not silently accept a mismatch.

---

### Step 4: Characterize — functional enrichment

**Goal:** Identify enriched pathways, functions, and ontology
categories among the DE genes.

**Action:** Write and run an enrichment script. Use the gene
universe from the KG as the background set.

```python
# scripts/enrichment.py
"""GO/KEGG enrichment analysis for DE genes."""
import pandas as pd
from scipy import stats

de_genes = pd.read_csv("data/de_genes_significant.csv")

# Extract background gene universe for this organism
from multiomics_explorer import genes_by_function
bg = genes_by_function(search_text="*", organism="<organism>")
# bg["total_matching"] is the gene universe size

# For each ontology (go_bp, kegg, etc.):
# 1. Get annotations for DE genes via gene_ontology_terms
# 2. Count genes per term
# 3. Fisher's exact test against background frequency
# 4. BH correction for multiple testing
# ... (implementation details depend on available annotation data)
```

**Alternatively, use MCP for a qualitative characterization:**

If the researcher needs a quick characterization (not
publication-grade statistics), use MCP tools to survey the
functional landscape:

```
gene_overview(locus_tags=<top_de_genes>, summary=True)
→ by_category breakdown shows which functional categories dominate

genes_by_ontology(term_ids=<relevant_terms>, ontology="go_bp", summary=True)
→ check overlap between DE genes and known pathways
```

This is the chat-mode ceiling — informative but not statistically
rigorous. Flag this to the researcher if they need publication
quality.

**Gate 4 — Enrichment valid:**
- [ ] Background set defined and documented (organism gene universe)
- [ ] Multiple testing correction applied (BH or equivalent)
- [ ] Results saved to `results/enrichment_<ontology>.csv`
- [ ] Top enriched terms are biologically plausible (sanity check)

---

### Step 5: Visualize — volcano plot and summary figures

**Goal:** Produce standard visualizations of the DE response.

**Action:** Write and run a plotting script.

```python
# scripts/volcano_plot.py
"""Volcano plot for DE genes."""
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv("data/de_genes_significant.csv")

plt.figure(figsize=(10, 8))
colors = ['#2166ac' if d == 'down' else '#b2182b'
          for d in df['direction']]
plt.scatter(df['log2fc'], -np.log10(df['padj']),
            c=colors, alpha=0.6, s=20)
plt.xlabel('log2 fold change')
plt.ylabel('-log10(adjusted p-value)')
plt.title('<Experiment description>')
plt.savefig('results/volcano.png', dpi=150, bbox_inches='tight')
```

**Gate 5 — Outputs exist:**
- [ ] `results/volcano.png` exists and is non-empty
- [ ] Enrichment result files exist
- [ ] All outputs are referenced in README.md

---

### Step 6: Interpret and document

**Goal:** Produce README.md and methods.md from the analysis.

**README.md** — summary of findings:
- Research question (from step 1)
- Key numbers: total DE genes, up/down split, top enriched terms
- File index with descriptions
- Key biological interpretation

**methods.md** — publication-ready methods (see template below):
- Fill in from decisions recorded at each gate
- Every parameter, threshold, and tool version documented
- Limitations section: what the analysis can and cannot conclude

**Gate 6 — Documentation complete:**
- [ ] README.md summarizes findings and indexes all files
- [ ] methods.md covers all required sections (see template)
- [ ] All scripts are re-runnable without Claude

---

## Methods template

Fill this in progressively as you complete each step. Do not write
it retroactively.

```markdown
# Methods

## Research question

[Precise statement of what was asked]

## Data scope

- **Organism:** [strain name]
- **Experiment:** [experiment_id] from [publication DOI]
- **Condition:** [treatment] vs [control]
- **Omics type:** [RNASEQ/MICROARRAY/PROTEOMICS]
- **Time points:** [if time-course, list them; otherwise "endpoint"]

## Gene selection

- Total genes with expression data: [gene_count]
- Significant DE genes: [significant_count]
- Significance criteria: [padj threshold, fold-change cutoff if any]
- Direction breakdown: [N up, N down]

## Enrichment analysis

- **Background set:** [N] genes ([organism] gene universe from KG)
- **Ontologies tested:** [GO BP, KEGG, etc.]
- **Statistical test:** Fisher's exact test
- **Multiple testing correction:** Benjamini-Hochberg (FDR < 0.05)
- **Software:** Python [version], scipy [version]

## Results summary

[Key findings with effect sizes, p-values, reference to output files]

## Limitations

[What this analysis can and cannot conclude. Known caveats.]
```

---

## Quality gates — summary

| Gate | Check | Fail action |
|---|---|---|
| 1. Scope | Experiment confirmed with researcher | Ask, don't guess |
| 2. Response | Gene counts recorded | Re-query if missing |
| 3. Data | CSV row count ≈ significant_count | Investigate mismatch |
| 4. Enrichment | BH correction applied, results saved | Fix stats before interpreting |
| 5. Outputs | All files exist and non-empty | Re-run failed scripts |
| 6. Docs | methods.md complete | Fill missing sections |

---

## Chaining context

**Upstream (how you get here):**
- Researcher asks about a condition → this skill
- Layer 3 (inversion) clarifies an ambiguous question → this skill

**Downstream (where results go):**
- Comparative analysis skill: compare this experiment to another
- Time-course skill: if experiment is time-course, hand off for
  temporal clustering
- Publication export skill: format for supplementary materials

**Layer 1 tools used:**
`list_experiments` → `list_organisms` → `gene_overview` →
`genes_by_ontology` → `gene_ontology_terms`

**Package imports used:**
`differential_expression_by_gene` (extraction),
`genes_by_function` (background set)
