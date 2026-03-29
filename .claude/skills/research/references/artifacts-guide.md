# Artifacts guide

Every non-trivial analysis produces a directory under `analyses/`
with a standard structure. This ensures reproducibility and makes
it easy for collaborators (or future Claude sessions) to understand
what was done.

---

## Directory structure

```
analyses/{analysis_name}/
├── data/              # Staged data from KG (CSV/TSV)
├── scripts/           # Python analysis scripts
├── results/           # Outputs: tables, figures, statistics
├── README.md          # Summary, key findings, file index
├── methods.md         # Publication-ready methods document
└── references.md      # Data sources and citations
```

### Naming convention

`{analysis_name}` should be descriptive and lowercase with
underscores: `catalase_expression`, `nitrogen_stress_enrichment`,
`photosystem_conservation`.

---

## data/

KG extracts staged as files. These are the inputs to analysis
scripts.

- Format: CSV (preferred) or TSV
- One file per extraction query
- Include metadata columns (organism, experiment_id, locus_tag)
- Name files descriptively: `de_genes_med4_nitrogen.csv`,
  `catalase_orthologs.csv`

**How to extract:**

```python
#!/usr/bin/env python3
"""Extract differential expression data for analysis."""
import pandas as pd
from multiomics_explorer import differential_expression_by_gene

data = differential_expression_by_gene(
    organism="Prochlorococcus marinus MED4",
    experiment_ids=["exp_001", "exp_002"],
    significant_only=True,
)
df = pd.DataFrame(data["results"])
df.to_csv("data/de_genes_med4.csv", index=False)
print(f"Extracted {len(df)} rows (total_matching: {data['total_matching']})")
```

Scripts in `data/` or `scripts/` — either works, but extraction
scripts should be clearly labeled.

---

## scripts/

Analysis scripts that read from `data/` and write to `results/`.

Requirements:
- **Self-contained** — run with `python scripts/analysis.py` from
  the analysis directory
- **Documented** — docstring explaining what the script does
- **Versioned** — log library versions in output or methods.md
- **Deterministic** — set random seeds where applicable
- **Clear I/O** — explicit input/output file paths, no hardcoded
  absolute paths

Example patterns:
- `scripts/extract_data.py` — KG extraction
- `scripts/enrichment.py` — pathway enrichment analysis
- `scripts/volcano_plot.py` — visualization
- `scripts/clustering.py` — gene clustering

---

## results/

Outputs from analysis scripts.

### Tables
- CSV format for data tables
- Include headers with clear column names
- Include units where applicable (log2FC, padj, etc.)
- Name: `enrichment_results.csv`, `top_genes.csv`

### Figures
- PNG (for quick viewing) and PDF/SVG (for publication)
- Resolution: 300 DPI minimum for PNG
- Include axis labels, legends, titles
- Name: `volcano_nitrogen.png`, `heatmap_catalase.pdf`
- Consistent style across figures in the same analysis

### Statistics
- Summary statistics as CSV or in methods.md
- Full test results (test statistic, p-value, effect size,
  confidence interval)

---

## methods.md

Publication-ready methods document. **Required sections:**

### Research question
What was asked, in precise terms. Not the user's original phrasing
but the operationalized question.

### Data scope
- Organisms and strains (with KG identifiers)
- Publications (DOIs)
- Experiments (IDs, conditions, time points)
- What was included and what was excluded, with reasons
- KG build date / version

### Gene selection
- How genes of interest were identified (search terms, ontology
  terms, homolog groups)
- Filters applied (significance, fold-change, quality)
- Gene counts at each filtering step
- Paralog handling

### Statistical methods
- Tests used (with parameters)
- Multiple testing correction method
- Background set definition (for enrichment)
- Software versions
- Significance thresholds

### Results summary
- Key findings with effect sizes and p-values
- Reference to specific output files in `results/`
- What was significant, what wasn't

### Limitations
- KG gaps (missing organisms, conditions, annotations)
- Statistical caveats (missing padj, small samples, borderline
  significance)
- What the analysis can and cannot conclude
- Known issues (duplicate entries, paralog conflation risks)

---

## references.md

Track all data sources and citations.

```markdown
# References

## Data sources
- KG build: [date], multiomics_biocypher_kg [version/commit]
- Neo4j: [connection info]

## Publications (data)
- [DOI] — [short description of what data was used from this study]
- [DOI] — ...

## Methods references
- DESeq2: Love et al. (2014) Genome Biology 15:550
- [enrichment tool]: [citation]
- [clustering method]: [citation]

## Software
- Python [version]
- multiomics_explorer [version]
- pandas [version]
- scipy [version]
- matplotlib [version]
```

---

## README.md

Brief summary for someone encountering the analysis directory.

```markdown
# {Analysis title}

## Question
[One-sentence research question]

## Key findings
- [Finding 1]
- [Finding 2]

## Files
| File | Description |
|---|---|
| `data/de_genes.csv` | Differential expression data from KG |
| `scripts/enrichment.py` | Pathway enrichment analysis |
| `results/volcano.png` | Volcano plot of DE genes |
| `methods.md` | Full methods documentation |

## How to reproduce
```bash
cd analyses/{analysis_name}
python scripts/extract_data.py   # stage data from KG
python scripts/enrichment.py     # run analysis
python scripts/volcano_plot.py   # generate figures
```

## Date
[Analysis date]
```

---

## When NOT to create artifacts

Simple lookups and quick answers don't need the full artifact
structure:
- "What is gene PMM0120?" — MCP lookup, answer in chat
- "How many genes respond to nitrogen?" — MCP summary, answer in
  chat
- "List the catalase genes" — MCP query, table in chat

Create artifacts when:
- The question requires statistical computation
- Multiple data extractions feed into an analysis
- Results need to be shared or revisited
- The analysis takes more than 2-3 tool calls
- Figures or publication-ready tables are needed
