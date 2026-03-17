# Convention: Shared KG Constants

Enumerated value sets used for parameter validation and query building
live in `multiomics_explorer/kg/constants.py`. Single source of truth —
tools and query builders import from here.

## File: `multiomics_explorer/kg/constants.py`

```python
"""Shared constants for the knowledge graph layer."""

# -- Ortholog group enums --

VALID_OG_SOURCES: set[str] = {"cyanorak", "eggnog"}

VALID_TAXONOMIC_LEVELS: set[str] = {
    "curated", "Prochloraceae", "Synechococcus",
    "Alteromonadaceae", "Cyanobacteria",
    "Gammaproteobacteria", "Bacteria",
}

MAX_SPECIFICITY_RANK: int = 3  # 0=curated, 1=family, 2=order, 3=domain
```

## Initial scope (this plan)

Only the OG enums above. Created by `get_homologs` redefinition step 0.

## Future migration (separate effort)

`ONTOLOGY_CONFIG`, `DIRECT_EXPR_RELS` / `ALL_EXPR_RELS` currently in
`queries_lib.py` should move here eventually, but that touches all
ontology/expression tools and their tests — not part of the `get_homologs` plan.

## Usage

- **Query builders** (`queries_lib.py`): import constants for building
  Cypher (e.g. `DIRECT_EXPR_RELS` in f-strings, `ONTOLOGY_CONFIG` for
  index/label lookup).
- **Tool wrappers** (`tools.py`): import value sets for parameter
  validation (e.g. `VALID_OG_SOURCES` to check `source` param).
- When the KG adds a new taxonomic level or OG source, update one file.
