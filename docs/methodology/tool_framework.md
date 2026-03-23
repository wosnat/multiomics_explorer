# MCP Tool Framework

## The 3-phase research workflow

The tool set is organized around the natural flow of a multi-omics analysis:

```
Phase 1: Orientation        → select experiments + organisms
Phase 2: Gene work          → identify genes of interest
Phase 3: Expression         → explore gene expression in selected experiments
```

**Experiments and organisms are the frame.** Phase 1 establishes the scope; everything in phases 2 and 3 is filtered through that selection.

---

## Phase 1 — Orientation

**Goal:** understand what is in the KG; select publications, experiments, and organisms to work with.

**Output:** a set of experiment IDs and a target organism scope.

| Tool | Role |
|---|---|
| `list_organisms` | What species/strains are available, with gene/experiment counts |
| `list_publications` | What studies exist; filter by organism, treatment, keyword |
| `list_experiments` | Drill into individual experiments; filter by organism/treatment/omics; returns experiment IDs |


---

## Phase 2 — Gene work

**Goal:** identify and characterize genes of interest in the selected organisms.

**Output:** a set of gene IDs (locus_tags) per organism, with enough characterization to decide which to carry into Phase 3.

Discovery and details interleave — find some genes, check details, refine, find more. Annotation tools let you explore ontology terms and ortholog groups as first-class entities before using them in discovery. Homology bridges between organisms within this loop.

| Annotation | Discovery | Details |
|---|---|---|
| — | `resolve_gene`, `genes_by_function` | `gene_overview` |
| `search_ontology` | `genes_by_ontology` | `gene_ontology_terms` |
| `search_homolog_groups` ★ | `genes_by_homolog_group` ★ | `gene_homologs` ↻ |

- **Annotation** — explore ontology terms and ortholog groups as first-class entities; entry points to the annotation-mediated discovery paths
- **Discovery** — text/terms/identifiers → gene IDs
- **Details** — gene IDs → information about those genes

**Details tools are batch-first** — all accept a list of gene IDs and return long format (one row per gene × item). Rich entity details live in the Annotation tools; Details tools return only enough to read and navigate.

`gene_ontology_terms` — one row per gene × term:
```
locus_tag | term_id | term_name | term_type
```

`gene_homologs` — one row per gene × ortholog group:
```
locus_tag | group_id | consensus_gene_name | consensus_product | taxonomic_level | source
```
(`consensus_gene_name` is often null; `consensus_product` is the reliable fallback.)

---

## Phase 3 — Expression

**Goal:** explore expression of selected genes in selected experiments, including cross-organism comparison via homology.

**Output:** a single long table — one row per gene/cluster × experiment × timepoint. All context is inlined; no separate metadata tables.

| Tool | Role | Status |
|---|---|---|
| `differential_expression_by_gene` | Gene-centric expression; one organism at a time | to build |
| `differential_expression_by_ortholog` | Cluster-centric expression; cross-organism comparison | to build |

### Output schema

**`differential_expression_by_gene`** — one row per gene × experiment × timepoint:
```
locus_tag | gene_name | product | organism_strain |
experiment_id | experiment_name | condition_type | treatment | timepoint | timepoint_hours |
log2fc | padj | direction | rank | significant
```

**`differential_expression_by_ortholog`** — one row per cluster × experiment × timepoint:
```
cluster_id | consensus_product | consensus_gene_name |
experiment_id | experiment_name | condition_type | treatment | organism | timepoint | timepoint_hours |
log2fc | padj | direction | rank | significant
```

Missing cells (no homolog in organism, or homolog has no expression data) are absent rows, not nulls. This is biologically meaningful — absence is explicit by omission.

Cluster membership (which genes belong to a cluster per organism) is not included in the expression response — use `genes_by_homolog_group` for that.

### Summary mode

Both tools return a summary header (counts, breakdowns) alongside the long table. Summary stats draw from precomputed KG properties where possible — cheap at query time.

**Precomputed properties needed on `OrthologGroup` nodes** (to be added to KG build pipeline):
- `expression_experiment_count` — number of experiments with data for any member gene
- `expression_organism_count` — number of organisms with expression data for members
- `conservation_pattern` — precomputed summary of cross-organism response consistency **(TBD: exact definition)**

`Gene` and `Experiment` nodes already carry the necessary precomputed stats (`expression_edge_count`, `significant_expression_count`, `gene_count`, `significant_count`).

Conservation pattern is the key summary signal for `differential_expression_by_ortholog` — it tells the LLM immediately whether a cluster's response is conserved, divergent, or organism-specific, without scanning all rows. Exact shape TBD.

**Note:** Expression tools are currently `run_cypher` escape hatches. The redesign is tracked in `plans/redefine_mcp_tools/expression_tools_redesign.md`. This framework supersedes the output shape defined there.

---

## Homology framework

Homology serves two distinct purposes in the workflow, requiring different tool designs.

### Homology as discovery (Phase 2)

The homology tool triplet mirrors the ontology triplet:

| Ontology | Homology | Direction |
|---|---|---|
| `search_ontology` | `search_homolog_groups` | text → group IDs |
| `genes_by_ontology` | `genes_by_homolog_group` | group ID → genes |
| `gene_ontology_terms` | `gene_homologs` | gene → its groups |

- **`search_homolog_groups`** (new): text search on `consensus_gene_name` / `consensus_product` → returns matching OrthologGroup IDs. Entry point for cluster-centric discovery.
- **`genes_by_homolog_group`** (new): given a group ID, returns member genes per organism.
- **`gene_homologs`** (rename from `get_homologs`): given a gene, returns its ortholog groups. Redesign in progress — see `plans/redefine_mcp_tools/get_homologs_redefinition.md`.

`OrthologGroup` nodes support this because they carry `consensus_gene_name`, `consensus_product`, `genera`, `member_count`, `specificity_rank`, and `source` — rich enough to be first-class discoverable entities.

### Homology as cross-organism bridge (Phase 3)

For cross-organism expression comparison, the unit of analysis is the **ortholog cluster**, not the individual gene. `differential_expression_by_ortholog` returns long format (one row per cluster × experiment × timepoint) with cluster identity inlined — see Phase 3 output schema. Missing cells (no homolog, or no expression data) are absent rows.

### OrthologGroup selection algorithm

When selecting the ortholog group to represent a gene for a given set of target organisms:

```
candidates = ortholog groups where all target_genera are in og.genera
sort by: specificity_rank ASC
pick: first candidate
```

**Rules:**
1. **Tightest covering group** — lowest `specificity_rank` that still spans all target organisms. Cyanorak groups have rank=0 by design, so they naturally win when the target organisms fall within Prochlorococcus/Synechococcus.
2. **No spanning group** — gene has no homolog in the other organism(s). Absent row in the expression output. Not an error.

This logic is shared between the homology discovery tool and the cluster expression tool — implement as a reusable query builder function, not duplicated.

---

## Tool surface summary

### Phase 1 — Orientation
- `list_organisms`
- `list_publications`
- `list_experiments`

### Phase 2 — Gene work

| Annotation | Discovery | Details |
|---|---|---|
| — | `resolve_gene`, `genes_by_function` | `gene_overview` |
| `search_ontology` | `genes_by_ontology` | `gene_ontology_terms` |
| `search_homolog_groups` ★ | `genes_by_homolog_group` ★ | `gene_homologs` ↻ |

★ new — ↻ renamed from `get_homologs`

### Phase 3 — Expression
- `differential_expression_by_gene` — to build; gene × experiment, same-organism
- `differential_expression_by_ortholog` — to build; cluster × experiment, cross-organism

### Utils
- `run_cypher` — escape hatch for queries not covered by other tools
- `kg_schema` — schema introspection, developer/debug use
- `list_filter_values` — parameter helper; lists valid values for categorical filters

---

## Decisions

- **`differential_expression_by_ortholog`** is a separate tool (not a mode of `differential_expression_by_gene`) — output shape is fundamentally different.
- **`get_gene_details`** retired — `gene_overview` covers the Details column; edge cases go to `run_cypher`.
- **`gene_overview` name retained** — accurately describes its role: broad view of a gene's data landscape to guide next steps.
