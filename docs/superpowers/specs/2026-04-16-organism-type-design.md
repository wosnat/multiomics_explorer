# Organism Type Property — Design Spec

**Date**: 2026-04-16
**Scope**: `list_organisms` tool only
**KG change doc**: `multiomics_biocypher_kg/docs/kg-changes/reference-proteome-match-organisms.md`

## Context

The KG now carries `organism_type` on all OrganismTaxon nodes, classifying each as `genome_strain`, `treatment`, or `reference_proteome_match`. Two organisms also have `reference_database` and `reference_proteome` properties. Two organisms were renamed. This spec surfaces those properties in the explorer's `list_organisms` tool.

## Changes

### Query builder (`queries_lib.py`)

Add three columns to `build_list_organisms` RETURN:

```
o.organism_type AS organism_type
o.reference_database AS reference_database
o.reference_proteome AS reference_proteome
```

No new params. No WHERE changes.

### API layer (`functions.py`)

- Sparse-strip `reference_database` and `reference_proteome` when null.
- Build `by_organism_type` summary from results: `[{organism_type, count}]` sorted by count descending. Add to the returned envelope alongside existing `by_cluster_type`.

### MCP model (`tools.py`)

`OrganismResult` — add fields:

| Field | Type | Description |
|---|---|---|
| `organism_type` | `str` | Classification: `genome_strain`, `treatment`, or `reference_proteome_match` |
| `reference_database` | `str \| None` | Sparse. Database used for matching (e.g. "MarRef v6"). Only on `reference_proteome_match` organisms. |
| `reference_proteome` | `str \| None` | Sparse. Accession of matched reference proteome. Only on `reference_proteome_match` organisms. |

`ListOrganismsResponse` — add field:

| Field | Type | Description |
|---|---|---|
| `by_organism_type` | `list[OrgTypeBreakdown]` | Organism counts per type, sorted by count descending |

New model `OrgTypeBreakdown`:

| Field | Type | Description |
|---|---|---|
| `organism_type` | `str` | e.g. `genome_strain` |
| `count` | `int` | Number of organisms of this type |

### Tests

- **Unit (query builder)**: verify new columns appear in generated Cypher.
- **Unit (tool correctness)**: verify `organism_type` in result rows, sparse fields absent for non-reference organisms, `by_organism_type` in envelope.
- **Regression fixtures**: regenerate `list_organisms.yml` and `list_organisms_raw.yml` (picks up organism renames too).

### Not changed

- No new tool params or filters.
- No changes to any other tool (organism resolution is substring-based, unaffected by renames).
- No changes to CLAUDE.md tool table (organism_type is self-describing in output).
