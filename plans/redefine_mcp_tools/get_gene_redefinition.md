# Plan: Redefine `get_gene` → `resolve_gene` as a pure ID-resolution tool

## Motivation

`get_gene` currently returns a mix of identification fields and detailed annotations
(gene_summary, function_description, go_terms, kegg_ko, annotation_quality). This
conflates two concerns: **resolving an identifier to graph nodes** and **retrieving
gene details**.

The name `get_gene` reinforces this confusion — it sounds like "give me the gene info",
which is really what `get_gene_details` does. Renaming to `resolve_gene` makes the
tool's purpose self-evident: map an identifier to node(s), then use other tools for
details.

In practice, `resolve_gene` is the first step in a multi-tool workflow:

```
resolve_gene("dnaN")  ->  which locus_tags in which organisms?
    |
    v
get_gene_details("PMM1428")  ->  full annotations, protein, cluster, homologs
query_expression(gene="PMM1428", ...)  ->  expression data
```

Returning heavy annotation fields at the resolution step wastes tokens, clutters
Claude's context, and duplicates data that `get_gene_details` already provides.
Since there is no existing production usage (only tests), now is the right time to
make this change.

## Changes

### 1. Rename `get_gene` to `resolve_gene`

**Files:** `multiomics_explorer/mcp_server/tools.py`, `multiomics_explorer/kg/queries_lib.py`,
all tests and fixtures referencing `get_gene` / `build_get_gene`.

- Tool name: `get_gene` → `resolve_gene`
- Query builder: `build_get_gene` → `build_resolve_gene`
- The name signals this is a lookup/mapping step, not a data-retrieval step.

### 2. Slim down the RETURN clause

**File:** `multiomics_explorer/kg/queries_lib.py`

Current RETURN:
```
locus_tag, gene_name, gene_summary, product, function_description,
organism_strain, go_terms, kegg_ko, annotation_quality
```

New RETURN — only fields needed to identify and disambiguate:
```
locus_tag, gene_name, product, organism_strain
```

- `product` stays as a short one-liner so Claude can distinguish hits without
  a second round-trip (e.g. "hypothetical protein" vs "DNA polymerase III beta subunit").
- Everything else moves to `get_gene_details`.

### 3. Remove the hard limit of 5

**File:** `multiomics_explorer/kg/queries_lib.py`

A gene name like `dnaN` exists in every strain. A cap of 5 silently drops matches.
Since each row is now ~4 small fields, returning all matches is cheap.

- Remove `LIMIT 5` from the Cypher query.
- Remove the limit from the tool wrapper as well (no `LIMIT` parameter needed).

### 4. Rename the `id` parameter to `identifier`

**Files:** `multiomics_explorer/kg/queries_lib.py`, `multiomics_explorer/mcp_server/tools.py`

- `id` shadows a Python builtin and is vague in the tool schema.
- Rename to `identifier` in the query builder signature, Cypher params, and the
  MCP tool signature.
- Update the tool docstring accordingly.

### 5. Group results by organism in the response

**File:** `multiomics_explorer/mcp_server/tools.py`

Instead of returning a flat list, group by `organism_strain`:

```json
{
  "results": {
    "Prochlorococcus MED4": [
      {"locus_tag": "PMM1428", "gene_name": "dnaN", "product": "DNA polymerase III beta subunit"}
    ],
    "Prochlorococcus MIT9313": [
      {"locus_tag": "PMT1246", "gene_name": "dnaN", "product": "DNA polymerase III beta subunit"}
    ]
  },
  "total": 2
}
```

- When a single match is found, the structure stays the same (one organism, one entry) —
  no special-casing needed.
- The "Ambiguous" message is no longer needed; multiple organisms in the response is
  self-explanatory.

### 6. Update the tool docstring

**File:** `multiomics_explorer/mcp_server/tools.py`

Rewrite to reflect the new role:

> Resolve a gene identifier to matching graph nodes. Returns locus_tags grouped by
> organism. Use the returned locus_tag with get_gene_details, query_expression, or
> other tools.

### 7. Update tests

**Files:** `tests/unit/test_tool_correctness.py`, `tests/unit/test_query_builders.py`,
`tests/regression/test_regression/get_gene_*.yml`, and related fixtures.

- Rename all references from `get_gene` / `build_get_gene` to `resolve_gene` / `build_resolve_gene`.
- Update expected return fields (drop annotation fields).
- Update expected response structure (grouped by organism).
- Update parameter name from `id` to `identifier`.
- Remove or adjust any assertions on the 5-result limit.

## Out of scope

- Changes to `get_gene_details`, `find_gene`, or other tools (separate plans).
- Adding new fields to the response.
- Changing the Cypher matching logic (WHERE clause stays the same).
