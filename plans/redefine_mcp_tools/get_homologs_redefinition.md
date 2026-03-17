# Plan: `get_homologs` — group-centric redesign

Rewrite `get_homologs` to return results grouped by OrthologGroup instead of
a flat gene list. Add filtering by source/level/rank. Exclude same-organism
paralogs by default. Return group summaries by default (opt in to full
member lists with `include_members`). Remove `include_expression`
(expression for orthologs will be handled by `query_expression` in a
separate plan).

**Depends on KG change:**
[ortholog_group_enrichment.md](/home/osnat/github/multiomics_biocypher_kg/docs/ortholog_group_enrichment.md)
adds `consensus_product`, `consensus_gene_name`, `member_count`,
`organism_count`, `genera`, `has_cross_genus_members` to OrthologGroup nodes.
These properties are now live in the KG (verified 2026-03-16).

**`has_cross_genus_members`** is a string: `"cross_genus"` (3,596 groups) or
`"single_genus"` (17,526 groups).

---

## Current State

**Query builder** (`queries_lib.py:260-270`):
```cypher
MATCH (g:Gene {locus_tag: $lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)
      <-[:Gene_in_ortholog_group]-(other:Gene)
WHERE other <> g
RETURN DISTINCT other.locus_tag AS locus_tag, other.product AS product,
       other.organism_strain AS organism_strain,
       og.source AS source, og.taxonomic_level AS taxonomic_level
ORDER BY og.taxonomic_level, other.locus_tag
```

**Tool wrapper** (`tools.py:375-411`):
- Parameters: `gene_id`, `include_expression` (bool)
- Returns flat list of homologs, or `{homologs, expression}` dict

### Problems

1. **Duplicate rows** — a gene in 3 OGs appears 3× in results (DISTINCT
   doesn't help because source/level differ per row).
2. **No paralog filtering** — Bacteria-level COGs have avg ~12, max 151
   same-organism paralogs.
3. **No level/source filtering** — curated Cyanorak and broad Bacteria COGs
   mixed together with no way to scope.
4. **`include_expression` couples two concerns** — homolog discovery and
   expression analysis should be separate tools. The flat expression dump
   is disconnected from OG context.
5. **No group metadata** — OG names like `CK_00003570` are opaque. No
   functional description, no member count, no genera info.
6. **Always returns full member lists** — no way to get a quick conservation
   overview without dumping every member gene.

---

## Tool Signature

```python
@mcp.tool()
def get_homologs(
    ctx: Context,
    gene_id: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    exclude_paralogs: bool = True,
    include_members: bool = False,
    member_limit: int = 50,
) -> str:
    """Find orthologs of a gene, grouped by ortholog group.

    Returns ortholog groups the gene belongs to, ordered from most specific
    (curated) to broadest (Bacteria-level COG). Each group includes its
    consensus function, member/organism counts, and genera.

    By default returns group summaries only. Set include_members=True to
    get the full list of member genes per group.

    Args:
        gene_id: Gene locus_tag (e.g. "PMM0001").
        source: Filter by OG source: "cyanorak" or "eggnog".
        taxonomic_level: Filter by level: "curated", "Prochloraceae",
            "Synechococcus", "Alteromonadaceae", "Cyanobacteria",
            "Gammaproteobacteria", "Bacteria".
        max_specificity_rank: Cap breadth — 0=curated only, 1=+family,
            2=+order, 3=+domain (all). Overrides source/taxonomic_level.
        exclude_paralogs: If True (default), exclude members from the same
            organism strain as the query gene. Set False to include paralogs.
            Only applies when include_members=True.
        include_members: If True, include full member gene lists per group.
            Default False returns group summaries (counts, consensus function,
            genera) without individual member genes.
        member_limit: Max members returned per group (default 50, max 200).
            Only applies when include_members=True. Groups exceeding the
            limit include a "truncated" flag.

    Raises:
        ValueError if source is not in {"cyanorak", "eggnog"} or
        taxonomic_level is not in {"curated", "Prochloraceae",
        "Synechococcus", "Alteromonadaceae", "Cyanobacteria",
        "Gammaproteobacteria", "Bacteria"} or max_specificity_rank
        is not in 0-3 or member_limit is not in 1-200.

    Notes:
        - member_count and organism_count are total group counts from the
          KG (include paralogs). When exclude_paralogs is True, the
          returned members list may be smaller than member_count.
        - For expression data of orthologs, use query_expression with
          include_orthologs (separate tool, not part of this response).
        - A gene typically belongs to 1-3 groups: one Cyanorak curated
          cluster (Pro/Syn only), one eggNOG family-level OG, and one
          eggNOG Bacteria-level COG.
    """
```

**Return structure (default — group summaries):**
```json
{
  "query_gene": {
    "locus_tag": "PMM1375",
    "gene_name": null,
    "product": "possible M protein repeat",
    "organism_strain": "Prochlorococcus MED4"
  },
  "ortholog_groups": [
    {
      "og_name": "CK_00003570",
      "source": "cyanorak",
      "taxonomic_level": "curated",
      "specificity_rank": 0,
      "consensus_product": "possible M protein repeat",
      "consensus_gene_name": null,
      "member_count": 7,
      "organism_count": 5,
      "genera": ["Prochlorococcus"],
      "has_cross_genus_members": "single_genus"
    }
  ]
}
```

**Return structure (include_members=True):**
```json
{
  "query_gene": {
    "locus_tag": "PMM1375",
    "gene_name": null,
    "product": "possible M protein repeat",
    "organism_strain": "Prochlorococcus MED4"
  },
  "ortholog_groups": [
    {
      "og_name": "CK_00003570",
      "source": "cyanorak",
      "taxonomic_level": "curated",
      "specificity_rank": 0,
      "consensus_product": "possible M protein repeat",
      "consensus_gene_name": null,
      "member_count": 7,
      "organism_count": 5,
      "genera": ["Prochlorococcus"],
      "has_cross_genus_members": "single_genus",
      "members": [
        {"locus_tag": "PMN2A_0562", "gene_name": null, "product": "possible M protein repeat", "organism_strain": "Prochlorococcus NATL2A"},
        {"locus_tag": "PMT9312_0685", "gene_name": null, "product": "possible M protein repeat", "organism_strain": "Prochlorococcus MIT9312"},
      ]  // each member uses the standard gene stub (see convention_gene_stub.md)
    },
    {
      "og_name": "1MNY6@1212",
      "source": "eggnog",
      "taxonomic_level": "Prochloraceae",
      "specificity_rank": 1,
      "consensus_product": "possible M protein repeat",
      "consensus_gene_name": null,
      "member_count": 3,
      "organism_count": 3,
      "genera": ["Prochlorococcus"],
      "has_cross_genus_members": "single_genus",
      "members": [...]
    }
  ]
}
```


---

## Query Builders

**File:** `queries_lib.py`

### `build_get_homologs` — full rewrite

Two queries: one for group metadata (always), one for members (only when
`include_members=True`).

#### `build_get_homologs_groups`

```cypher
MATCH (g:Gene {locus_tag: $lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)
[WHERE og.source = $source]                  -- optional filters,
  [AND og.taxonomic_level = $level]          -- added dynamically
  [AND og.specificity_rank <= $max_rank]     -- by the builder
RETURN og.name AS og_name, og.source AS source,
       og.taxonomic_level AS taxonomic_level,
       og.specificity_rank AS specificity_rank,
       og.consensus_product AS consensus_product,
       og.consensus_gene_name AS consensus_gene_name,
       og.member_count AS member_count,
       og.organism_count AS organism_count,
       og.genera AS genera,
       og.has_cross_genus_members AS has_cross_genus_members
ORDER BY og.specificity_rank, og.source
```

Built dynamically — WHERE clauses added only when the corresponding
parameter is not None.

#### `build_get_homologs_members`

Only executed when `include_members=True`. One query per OG could be N+1;
instead, fetch all members in a single query filtered to the same OGs:

```cypher
MATCH (g:Gene {locus_tag: $lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)
      <-[:Gene_in_ortholog_group]-(other:Gene)
WHERE other <> g
  [AND other.organism_strain <> g.organism_strain]   -- exclude_paralogs
  [AND og.source = $source]
  [AND og.taxonomic_level = $level]
  [AND og.specificity_rank <= $max_rank]
RETURN og.name AS og_name,
       other.locus_tag AS locus_tag, other.gene_name AS gene_name,
       other.product AS product, other.organism_strain AS organism_strain
ORDER BY og.specificity_rank, og.source, other.organism_strain, other.locus_tag
```

The tool wrapper groups the flat member rows by `og_name` and nests them
under the corresponding group from the groups query.

#### `build_gene_stub`

Fetched with a simple lookup (reuses the `g` matched in the groups query,
but cleaner as a standalone):

```cypher
MATCH (g:Gene {locus_tag: $lt})
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.organism_strain AS organism_strain
```

This can be a prefix on the groups query (WITH passthrough) or a separate
call. Separate is simpler and the gene lookup is trivially fast.

### `build_homolog_expression` — remove

No longer needed. Expression for orthologs will be handled by
`query_expression` with an `include_orthologs` parameter in a future plan.

---

## Tool Wrapper Logic

**File:** `tools.py`

```python
def get_homologs(ctx, gene_id, source=None, taxonomic_level=None,
                 max_specificity_rank=None, exclude_paralogs=True,
                 include_members=False, member_limit=50):
    conn = _conn(ctx)

    # Validate enum params (constants from kg/constants.py, see convention_kg_constants.md)
    if source is not None and source not in VALID_OG_SOURCES:
        return f"Invalid source '{source}'. Valid: {sorted(VALID_OG_SOURCES)}"
    if taxonomic_level is not None and taxonomic_level not in VALID_TAXONOMIC_LEVELS:
        return f"Invalid taxonomic_level '{taxonomic_level}'. Valid: {sorted(VALID_TAXONOMIC_LEVELS)}"
    if max_specificity_rank is not None and not (0 <= max_specificity_rank <= MAX_SPECIFICITY_RANK):
        return f"Invalid max_specificity_rank {max_specificity_rank}. Valid: 0-{MAX_SPECIFICITY_RANK}."
    if not (1 <= member_limit <= 200):
        return f"Invalid member_limit {member_limit}. Valid: 1-200."

    # 1. Query gene metadata
    cypher_gene, params_gene = build_gene_stub(gene_id=gene_id)
    gene_rows = conn.execute_query(cypher_gene, **params_gene)
    if not gene_rows:
        return f"Gene '{gene_id}' not found."
    query_gene = gene_rows[0]

    # 2. Query ortholog groups
    cypher_groups, params_groups = build_get_homologs_groups(
        gene_id=gene_id, source=source,
        taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
    )
    groups = conn.execute_query(cypher_groups, **params_groups)
    if not groups:
        return _with_query(
            _no_groups_msg(gene_id, source, taxonomic_level, max_specificity_rank),
            cypher_groups, params_groups, ctx,
        )

    # 3. Optionally fetch members
    if include_members:
        cypher_members, params_members = build_get_homologs_members(
            gene_id=gene_id, source=source,
            taxonomic_level=taxonomic_level,
            max_specificity_rank=max_specificity_rank,
            exclude_paralogs=exclude_paralogs,
        )
        members = conn.execute_query(cypher_members, **params_members)

        # Group members by og_name, apply per-group limit
        from collections import defaultdict
        members_by_og = defaultdict(list)
        for m in members:
            members_by_og[m.pop("og_name")].append(m)

        for g in groups:
            og_members = members_by_og.get(g["og_name"], [])
            if len(og_members) > member_limit:
                g["members"] = og_members[:member_limit]
                g["truncated"] = True
            else:
                g["members"] = og_members

    response = json.dumps(
        {"query_gene": query_gene, "ortholog_groups": groups},
        indent=2, default=str,
    )

    # Debug: attach all queries
    if _debug(ctx):
        queries = [{"cypher": cypher_groups, "params": params_groups}]
        if include_members:
            queries.append({"cypher": cypher_members, "params": params_members})
        debug_block = json.dumps({"_debug": {"queries": queries}}, indent=2, default=str)
        return f"{debug_block}\n---\n{response}"

    return response
```

Helper for the no-results message:

```python
def _no_groups_msg(gene_id, source, taxonomic_level, max_specificity_rank):
    msg = f"No ortholog groups found for '{gene_id}'"
    filters = []
    if source:
        filters.append(f"source={source}")
    if taxonomic_level:
        filters.append(f"taxonomic_level={taxonomic_level}")
    if max_specificity_rank is not None:
        filters.append(f"max_specificity_rank={max_specificity_rank}")
    if filters:
        msg += f" with constraints: {', '.join(filters)}"
    return msg + "."
```

**Key changes from current:**
- `include_expression` removed entirely — not replaced here.
- `build_homolog_expression` import removed.
- Return is always JSON (structured), not `_fmt()` (tabular) — the nested
  group structure doesn't work as a flat table.
- Gene lookup is a separate query (avoids returning gene info on every
  member row).

---

## Implementation Order

| Order | Change | Where | Status |
|-------|--------|-------|--------|
| 0 | Create `constants.py` with OG enums only (`VALID_OG_SOURCES`, `VALID_TAXONOMIC_LEVELS`, `MAX_SPECIFICITY_RANK`) | `kg/constants.py` | todo |
| 1 | New query builders: `build_gene_stub`, `build_get_homologs_groups`, `build_get_homologs_members` | `queries_lib.py` | todo |
| 2 | Remove `build_get_homologs` (old), remove `build_homolog_expression` | `queries_lib.py` | todo |
| 3 | Rewrite `get_homologs` wrapper with param validation, remove `include_expression`, remove `build_homolog_expression` import | `tools.py` | todo |
| 4 | Update unit tests | `tests/unit/` | todo |
| 5 | Update integration tests | `tests/integration/` | todo |
| 6 | Update eval cases and regression baselines | `tests/evals/`, `tests/regression/` | todo |
| 7 | Update docs | `CLAUDE.md`, `AGENT.md` | todo |

Steps 0–2 are one commit (query-builder agent does all three sequentially).
Step 3 depends on 0–2.
Steps 4 and 7 can run in parallel after step 3.
Steps 5–6 depend on step 3.

**Deferred:** Moving `ONTOLOGY_CONFIG` and `DIRECT_EXPR_RELS` from `queries_lib.py`
into `constants.py` — separate effort, not part of this plan.

## Agent Assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 0+1+2 | **query-builder** | Create `kg/constants.py` (OG enums only), new builders (`build_gene_stub`, `build_get_homologs_groups`, `build_get_homologs_members`), remove old `build_get_homologs` and `build_homolog_expression` | — |
| 3 | **tool-wrapper** | Rewrite `get_homologs` wrapper with new signature, remove `include_expression`, remove `build_homolog_expression` import | 0+1+2 |
| 4 | **test-updater** | Update unit tests (query builders + tool wrappers). Integration/eval/regression are blocked on KG. | 3 |
| 5 | **doc-updater** | Update `CLAUDE.md` tool table, `AGENT.md` if applicable | 3 |
| 6 | **code-reviewer** | Review all changes against this plan, run unit tests | 4, 5 |

---

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**

`TestBuildGetHomologs` (rewrite):
- [ ] `build_get_homologs_groups` returns query with OG enrichment properties (`consensus_product`, `consensus_gene_name`, `member_count`, `organism_count`, `genera`, `has_cross_genus_members`)
- [ ] Groups query orders by `specificity_rank, source`
- [ ] `source` filter adds `og.source = $source` when provided
- [ ] `taxonomic_level` filter adds `og.taxonomic_level = $level` when provided
- [ ] `max_specificity_rank` filter adds `og.specificity_rank <= $max_rank` when provided
- [ ] No filter when all None
- [ ] `build_get_homologs_members` includes `other <> g`
- [ ] `exclude_paralogs=True` adds `other.organism_strain <> g.organism_strain`
- [ ] `exclude_paralogs=False` does NOT add organism filter
- [ ] Members query returns `og_name`, `locus_tag`, `gene_name`, `product`, `organism_strain`
- [ ] Members query orders by `specificity_rank, source, organism_strain, locus_tag`
- [ ] `build_gene_stub` returns `locus_tag`, `gene_name`, `product`, `organism_strain`
- [ ] Old `build_get_homologs` no longer exists
- [ ] Old `build_homolog_expression` no longer exists

**`tests/unit/test_tool_wrappers.py`:**

`TestGetHomologsWrapper` (rewrite):
- [ ] Gene not found returns message
- [ ] No ortholog groups returns message
- [ ] Default mode: response has `query_gene` and `ortholog_groups` without `members` key
- [ ] `include_members=True`: response has `ortholog_groups` with `members` lists
- [ ] `source` filter is passed through to builder
- [ ] `exclude_paralogs=True` is passed through to members builder
- [ ] `include_expression` parameter no longer exists
- [ ] Response is JSON (not tabular `_fmt`)
- [ ] Invalid `source` returns error message listing valid values
- [ ] Invalid `taxonomic_level` returns error message listing valid values
- [ ] Invalid `max_specificity_rank` (e.g. 5) returns error message
- [ ] Invalid `member_limit` (e.g. 0 or 300) returns error message
- [ ] `member_limit` truncates per-group members and sets `truncated: true`
- [ ] Groups with fewer members than limit have no `truncated` key

**`tests/unit/test_tool_correctness.py`:**
- [ ] Update mock data if `get_homologs` is tested here

### Integration tests

**`tests/integration/test_tool_correctness_kg.py`:**
- [ ] PMM1375: returns 3 ortholog groups (cyanorak, Prochloraceae eggnog, Bacteria eggnog)
- [ ] Groups ordered by specificity_rank ascending
- [ ] Each group has enrichment properties (`consensus_product`, `member_count`, etc.)
- [ ] `source="cyanorak"` filter returns only cyanorak group
- [ ] `exclude_paralogs=True` (default): no members with same organism_strain as query gene
- [ ] `exclude_paralogs=False`: paralogs included (if any exist for the test gene)
- [ ] Default (no `include_members`): groups present, no `members` key
- [ ] `include_members=True`: groups present with `members` lists
- [ ] Alteromonas gene (e.g. MIT1002_00002): no cyanorak group, has Alteromonadaceae + Bacteria
- [ ] Gene with no OG membership returns "no ortholog groups" message

### Eval cases

```yaml
- id: homologs_exist
  tool: get_homologs
  desc: Find orthologs of a well-conserved gene
  params:
    gene_id: PMM0001
  expect:
    contains:
      ortholog_groups: [...]

- id: homologs_with_members
  tool: get_homologs
  desc: Full member lists per ortholog group
  params:
    gene_id: PMM0001
    include_members: true
  expect:
    contains:
      ortholog_groups: [...]

- id: homologs_source_filter
  tool: get_homologs
  desc: Only cyanorak orthologs
  params:
    gene_id: PMM0001
    source: cyanorak
  expect:
    contains:
      ortholog_groups: [...]
```

### Regression baselines (blocked on KG rebuild)

All `homologs_*` baselines must be regenerated after KG rebuild.

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Update `get_homologs` in tool table: "Orthologs grouped by ortholog group, with filtering by source/level/rank. Excludes paralogs by default." |
| `AGENT.md` | Update homology section to reference new group-centric return shape |

---

## Out of Scope

- `query_expression` ortholog mode — separate plan, uses OG traversal to
  fetch expression for orthologs. Replaces the removed `include_expression`.
- `search_genes` dedup logic — separate plan, needs OG-based grouping.
- `get_gene_details` homolog section — already handled by
  [get_gene_details_redefinition.md](get_gene_details_redefinition.md),
  returns `homolog_count` integer pointing users to this tool.
- KG enrichment — tracked in
  [ortholog_group_enrichment.md](/home/osnat/github/multiomics_biocypher_kg/docs/ortholog_group_enrichment.md).
