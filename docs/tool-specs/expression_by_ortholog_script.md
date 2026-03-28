# Spec: expression_by_ortholog script + skill

## Purpose

Python script + Claude Code skill that orchestrates existing API
functions to produce full expression detail rows with ortholog group
framing. Cross-organism by design.

**Not an MCP tool** — Claude Code only. Other MCP clients use the
individual tools (`genes_by_homolog_group`,
`differential_expression_by_ortholog`, `differential_expression_by_gene`)
directly.

## Relationship to existing tools

| Tool | Role in this workflow |
|---|---|
| `genes_by_homolog_group` | Step 1: get member genes per organism per group |
| `differential_expression_by_ortholog` | Step 2: per-group expression overview (triage) |
| `differential_expression_by_gene` | Step 3: per-organism detail rows |
| **this script** | Orchestrates steps 1-3, merges results with group_id |

## Why a script, not an MCP tool?

`differential_expression_by_gene` enforces single organism (by
design — expression experiments are organism-specific). Cross-organism
comparison requires per-organism iteration + result merging. That
orchestration logic belongs in a script, not a single Cypher query or
MCP tool.

The summary stats (step 2) are handled by `differential_expression_by_ortholog`
as a proper MCP tool because those can be computed in a single Cypher.

---

## What the script does

1. **Membership:** Calls `api.genes_by_homolog_group(group_ids, organisms)`
   to get member genes per organism per group.
2. **Summary:** Calls `api.differential_expression_by_ortholog(group_ids, ...)`
   for per-group expression overview stats.
3. **Detail rows:** For each organism with members, calls
   `api.differential_expression_by_gene(organism=org, locus_tags=[...], ...)`
   to get per-gene expression detail rows.
4. **Merge:** Combines detail rows across organisms, adds `group_id`
   column from membership data, outputs structured result.

---

## Script interface

**File:** `scripts/expression_by_ortholog.py`

```python
"""Full expression-by-ortholog workflow.

Orchestrates:
  1. genes_by_homolog_group() for membership
  2. differential_expression_by_ortholog() for overview
  3. differential_expression_by_gene() per organism for detail
  4. Merge results with group_id framing

Usage:
    uv run python scripts/expression_by_ortholog.py \
        --group-ids cyanorak:CK_00000570 \
        --organisms MED4 MIT9313 \
        --significant-only \
        --output json
"""
import argparse
from multiomics_explorer.api import (
    genes_by_homolog_group,
    differential_expression_by_ortholog,
    differential_expression_by_gene,
)


def expression_by_ortholog(
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    verbose: bool = False,
    limit: int | None = None,
) -> dict:
    """Full expression-by-ortholog workflow.

    Returns dict with keys:
        summary: differential_expression_by_ortholog result
        membership: genes_by_homolog_group result
        results: merged detail rows with group_id framing
        returned, truncated
    """
    ...
```

### CLI arguments

| Argument | Type | Description |
|---|---|---|
| `--group-ids` | list[str] (required) | Ortholog group IDs |
| `--organisms` | list[str] | Filter to specific organisms |
| `--experiment-ids` | list[str] | Filter to specific experiments |
| `--direction` | up/down | Filter by expression direction |
| `--significant-only` | flag | Only significant rows |
| `--verbose` | flag | Include gene product, experiment details |
| `--limit` | int | Max detail rows per organism |
| `--output` | json/table | Output format |

### Output structure

```python
{
    "summary": { ... },       # differential_expression_by_ortholog result (full)
    "membership": { ... },    # genes_by_homolog_group result (summary only)
    "results": [
        {
            "group_id": "cyanorak:CK_00000570",
            "locus_tag": "PMM0845",
            "gene_name": "psbB",
            "organism_strain": "Prochlorococcus MED4",
            "experiment_id": "EXP001",
            "treatment_type": "nitrogen_limitation",
            "timepoint": "24h",
            "timepoint_hours": 24.0,
            "timepoint_order": 3,
            "log2fc": 2.5,
            "padj": 0.001,
            "rank": 5,
            "expression_status": "significant_up",
        },
        ...
    ],
    "returned": 50,
    "truncated": false,
}
```

**Sort key:** `group_id ASC, organism_strain ASC, ABS(log2fc) DESC,
locus_tag ASC, experiment_id ASC, timepoint_order ASC`

---

## Skill file

**File:** `multiomics_explorer/skills/expression-by-ortholog/`

The skill prompt instructs Claude Code to use the script for full
expression-by-ortholog workflows. It covers:
- When to use the summary tool vs the script
- How to interpret `by_group` stats for triage
- Example workflow: `search_homolog_groups` → summary tool for triage →
  script for detail on interesting groups

---

## Chaining flow

```
search_homolog_groups(text)  →  group_ids
                                    |
                    +---------------+---------------+
                    |                               |
    differential_expression_by_ortholog       genes_by_homolog_group
    (triage: which groups respond?)      (membership: who is in the group?)
                    |                               |
                    +-------→ script combines ←-----+
                               per-organism calls to
                               differential_expression_by_gene
                               → full detail with group_id

gene_homologs(locus_tags)  →  group_ids  →  differential_expression_by_ortholog
```

---

## Tests

### Integration (live KG)

- Script with single group → returns summary + membership + merged results
- Results have group_id column
- Per-organism detail rows match `differential_expression_by_gene` output
- Organisms filter restricts to specified organisms
- significant_only filters to significant rows
- Output structure has expected keys

---

## Implementation Order

| Step | What |
|------|------|
| 1 | Create `scripts/expression_by_ortholog.py` — orchestration function + CLI |
| 2 | Create skill file at `skills/expression-by-ortholog/` |
| 3 | Integration test against live KG |
| 4 | Code review |

**Depends on:** `differential_expression_by_ortholog` MCP tool (task 2) must
be implemented first.
