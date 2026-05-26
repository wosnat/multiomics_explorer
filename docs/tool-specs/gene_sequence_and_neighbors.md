# Tool spec: gene_aa_sequence + gene_neighbors

**Mode:** B (spec names 2 tools → each file-owned agent handles both tools in its file).
**Brainstorming design:** [`docs/superpowers/specs/2026-05-26-gene-sequence-neighbors-design.md`](../superpowers/specs/2026-05-26-gene-sequence-neighbors-design.md).
**KG changes:** no schema changes — both tools read existing `Gene` node properties. One **performance** index requested for `gene_neighbors`: `Gene(organism_name, contig, start)` — see [`docs/kg-specs/kg-spec-gene-neighbors.md`](../kg-specs/kg-spec-gene-neighbors.md). Not a correctness dependency.

## Purpose

- **`gene_aa_sequence`** — return amino-acid sequences for a batch of genes, export-optimized (BLAST / HMMER / alignment). Optional FASTA blob.
- **`gene_neighbors`** — return each gene's genomic neighborhood (genes adjacent on the same contig) for operon / synteny reasoning, with strand orientation and intergenic distance.

## Out of Scope

- Nucleotide sequences — the KG stores only amino-acid `sequence`.
- Cross-contig / cross-organism synteny, gene-cluster/operon prediction, alignment, BLAST execution — `gene_neighbors` reports raw positional adjacency only.
- Co-expression "neighbors" — positional only. (Co-expression lives in the expression/DM tools.)
- Sequence-based search (find genes by sequence motif) — out of scope.

## Status / Prerequisites

- [x] All data fields exist (`sequence`, `contig`, `start`, `end`, `strand`) — no schema changes
- [x] KG spec written for the one **performance** index: `docs/kg-specs/kg-spec-gene-neighbors.md`
- [ ] Index landed (`Gene(organism_name, contig, start)`) — performance only; **not** a correctness blocker for Phase 2 build/test (user confirmed willing to add)
- [x] Scope reviewed with user (brainstorming, 2026-05-26)
- [x] Result-size controls decided
- [ ] Frozen-spec approved by user → **gate before Phase 2**

## Use cases

- **`gene_aa_sequence`**: after `resolve_gene` / `gene_overview` / `genes_by_function` produce locus_tags, pull AA sequences (often `fasta=True`) to export for external alignment/search. Terminal export step.
- **`gene_neighbors`**: given a gene of interest (e.g. a DE hit from `differential_expression_by_gene` or a transporter from `genes_by_metabolite`), inspect what sits beside it on the genome to reason about operon context. Chains **out** to `gene_overview` / `gene_aa_sequence` / `differential_expression_by_gene` / `gene_ontology_terms` on the returned neighbor locus_tags.

## KG dependencies

Both tools read only `Gene` node properties — no relationship traversal.

| Property | Type | Used by | Notes |
|---|---|---|---|
| `locus_tag` | str | both | Globally unique (verified: 0 ambiguous across all organisms). |
| `organism_name` | str | both | Scopes neighbor windows; `by_organism` rollup. |
| `sequence` | str | `gene_aa_sequence` | Amino-acid. Null on ~10–15% of genes (expression-only, no genome match). |
| `contig`, `start`, `end` | str, int, int | `gene_neighbors` | Always co-populated. `(contig, start)` unique within a contig (verified) → deterministic ordering. |
| `strand` | str | `gene_neighbors` | `'+'`/`'-'`, **null on ~50% of genes**. Nullable throughout. |
| `gene_name`, `product`, `gene_category` | str | both | Functional context. `gene_name` frequently null. |
| `protein_id` | str | `gene_aa_sequence` | FASTA header. |

Genomes are often fragmented (e.g. *Alteromonas (MarRef v6)*: 573 contigs) → neighbor windows scope to the same `contig` **and** `organism_name`.

**Index:** existing `Gene` indexes are on `locus_tag` / `gene_name` / `organism_name` (RANGE) — anchor lookups are index-backed. `gene_neighbors` additionally wants a composite RANGE index `Gene(organism_name, contig, start)` so the windowed scan is a seek + ordered-limit rather than an organism-wide scan + in-memory sort. See [`docs/kg-specs/kg-spec-gene-neighbors.md`](../kg-specs/kg-spec-gene-neighbors.md). Performance only.

---
---

# Tool 1 — `gene_aa_sequence`

## Tool Signature

```python
@mcp.tool(tags={"gene", "sequence"}, annotations={"readOnlyHint": True})
async def gene_aa_sequence(
    ctx: Context,
    locus_tags: Annotated[list[str], Field(
        description="Gene locus tags. Cross-organism OK (globally unique). E.g. ['ACZ81_08860', 'PMM0001'].")],
    fasta: Annotated[bool, Field(
        description="If true, omit per-row `sequence` and return one multi-FASTA blob in the envelope instead (no duplication).")] = False,
    summary: Annotated[bool, Field(
        description="If true, return envelope only (results=[]); sugar for limit=0.")] = False,
    limit: Annotated[int, Field(description="Max results.", ge=1)] = 25,
    offset: Annotated[int, Field(description="Rows to skip for pagination.", ge=0)] = 0,
) -> GeneAaSequenceResponse:
    ...
```

No `verbose` (decision: the only heavy field is `sequence`, governed by `fasta`).

**Return envelope:** `{total_matching, returned, truncated, by_organism, sequence_length_stats, not_found, not_matched, fasta, results}`

**Per-result columns:** `locus_tag`, `organism_name`, `gene_name`, `product`, `protein_id`, `sequence_length`, `sequence`.

- `fasta=False`: `sequence` carries the AA string.
- `fasta=True`: `sequence` is `null`; the envelope `fasta` field carries one multi-FASTA blob covering the returned page. Header: `>{locus_tag} {organism_name}|{protein_id}|{product}`. (`fasta` is `""` when `fasta=False`.)

## Result-size controls (Option B — batch)

| Field | Type | Description |
|---|---|---|
| total_matching | int | Input locus_tags resolving to a gene **with** a sequence. |
| returned | int | Rows in this response. |
| truncated | bool | `offset + returned < total_matching` (more rows beyond this page). |
| by_organism | list[{organism_name, count}] | Rollup over matched genes. |
| sequence_length_stats | {count, min, q1, median, q3, max, mean} | Over **all** matched genes (full match, not just the page — stable across `limit`/`offset`). |
| not_found | list[str] | Input locus_tags absent from the KG. |
| not_matched | list[str] | Locus_tags whose gene exists but `sequence` is null. |
| fasta | str | Multi-FASTA blob (non-empty only when `fasta=True`). |

**Sort key:** `organism_name, locus_tag` (deterministic).
**Default limit:** 25. **Pagination:** `offset` (default 0). Summary fields (`total_matching`, `by_organism`, `sequence_length_stats`) cover the full match and are page-independent.

## Query Builders (`kg/queries_lib.py`)

### `build_gene_aa_sequence` (detail) — verified against live KG 2026-05-26

```cypher
MATCH (g:Gene)
WHERE g.locus_tag IN $locus_tags AND g.sequence IS NOT NULL
RETURN g.locus_tag AS locus_tag,
       g.organism_name AS organism_name,
       g.gene_name AS gene_name,
       g.product AS product,
       g.protein_id AS protein_id,
       size(g.sequence) AS sequence_length,
       g.sequence AS sequence
ORDER BY g.organism_name, g.locus_tag
```
`SKIP $offset LIMIT $limit` appended for pagination — pushes the cut into Cypher so sequences for off-page rows are never transferred.

### `not_found` — REUSE existing `build_gene_existence_check`

Do **not** re-implement existence. `build_gene_existence_check(locus_tags=...)` already exists (`kg/queries_lib.py`) and is the canonical primitive — same Step-1 pattern as `gene_ontology_terms` (`api/functions.py:1811`):

```python
exist_cypher, exist_params = build_gene_existence_check(locus_tags=locus_tags)
exist_rows = conn.execute_query(exist_cypher, **exist_params)   # rows: {lt, found}
not_found   = [r["lt"] for r in exist_rows if not r["found"]]
found_tags  = [r["lt"] for r in exist_rows if r["found"]]
```

### `build_gene_aa_sequence_summary` (aggregates in Cypher) — verified against live KG 2026-05-26

```cypher
MATCH (g:Gene)
WHERE g.locus_tag IN $locus_tags AND g.sequence IS NOT NULL
WITH g ORDER BY g.organism_name, g.locus_tag
WITH g.organism_name AS org, size(g.sequence) AS len, g.locus_tag AS lt
WITH collect(lt) AS matched_tags, collect(org) AS orgs, count(*) AS total_matching,
     min(len) AS len_min, max(len) AS len_max, avg(len) AS len_mean,
     apoc.agg.percentiles(len, [0.25, 0.5, 0.75]) AS len_pcts
RETURN total_matching,
       matched_tags,
       apoc.coll.frequencies(orgs) AS by_organism,
       len_min, len_max, len_mean, len_pcts
```
Returns a **single summary row** — stats computed in Cypher (no sequences transferred), matching the `apoc.coll.frequencies` summary pattern used elsewhere. `RETURN keys: total_matching, matched_tags, by_organism, len_min, len_max, len_mean, len_pcts.` The API:
- assembles `sequence_length_stats = {count: total_matching, min: len_min, q1: len_pcts[0], median: len_pcts[1], q3: len_pcts[2], max: len_max, mean: len_mean}`;
- renames `by_organism` `{item,count}` → `{organism_name,count}` (sorted desc, via the existing `_rename_freq` helper);
- derives `not_matched = [t for t in found_tags if t not in matched_tags]` (gene exists but `sequence` null). `matched_tags` is internal — not emitted in the envelope.

`ORDER BY` before `collect` keeps `matched_tags` deterministic for regression snapshots.

**KG verification (done during spec):** batch `['ACZ81_08860','ACZ81_08855','SYNW1755','NOTAREAL']` → existence check: `NOTAREAL` not found, other 3 found; summary → `total_matching=2`, `matched_tags=['ACZ81_08855','ACZ81_08860']`, `by_organism=[{Alteromonas macleodii HOT1A3:2}]`, `len_min=178`, `len_max=487`, `len_mean=332.5`, `len_pcts=[178,178,487]` → `not_matched=['SYNW1755']`, `not_found=['NOTAREAL']`. `total_matching` (2) == detail row count.

## API Function (`api/functions.py`)

`gene_aa_sequence(locus_tags, fasta=False, summary=False, limit=25, offset=0, *, conn=None) -> dict`.
- Step 1: `build_gene_existence_check` → `not_found`, `found_tags`.
- Step 2: summary builder always (cheap, no sequences) → one row with `total_matching`, `matched_tags`, `by_organism`, and the length aggregates. API assembles `sequence_length_stats` from those aggregates (no Python recompute) and `not_matched = found_tags − matched_tags`. All page-independent.
- Step 3: detail builder unless `summary or limit == 0`; passes `offset` (`SKIP $offset LIMIT $limit`). `truncated = offset + returned < total_matching`.
- When `fasta=True`: build the multi-FASTA blob from detail rows, then set each row's `sequence` to `None`. (Do not also keep it in rows.)
- Returns the complete envelope dict.

## Special handling

- Length stats computed in Cypher (`min`/`max`/`avg` + `apoc.agg.percentiles`) — summary query transfers one row, never sequences. Follows the standard summary-builder pattern.
- `fasta` mutual exclusion of carriers is the whole point — never emit `sequence` in both rows and blob.

---
---

# Tool 2 — `gene_neighbors`

## Tool Signature

```python
@mcp.tool(tags={"gene", "genome"}, annotations={"readOnlyHint": True})
async def gene_neighbors(
    ctx: Context,
    locus_tags: Annotated[list[str], Field(
        description="Anchor gene locus tags. Cross-organism OK. E.g. ['ACZ81_08860'].")],
    window: Annotated[int, Field(
        description="Number of genes upstream AND downstream on the same contig (±N by start order).", ge=1)] = 5,
    max_bp_distance: Annotated[int | None, Field(
        description="Optional cap: drop neighbors whose intergenic gap to the anchor exceeds this many bp.")] = None,
    same_strand: Annotated[bool | None, Field(
        description="None=all neighbors; True=co-oriented only; False=opposite-strand only. Null-strand neighbors dropped when set.")] = None,
    summary: Annotated[bool, Field(
        description="If true, return envelope only (results=[]); sugar for limit=0.")] = False,
    limit: Annotated[int, Field(description="Max neighbor rows.", ge=1)] = 25,
) -> GeneNeighborsResponse:
    ...
```

No `verbose` (decision: richer per-gene context comes from chaining to `gene_overview`).

**Return envelope:** `{total_matching, returned, truncated, anchors, by_organism, not_found, not_matched, warnings, results}`

**Per-result columns (flat long — one row per anchor × neighbor):** `anchor_locus_tag`, `neighbor_locus_tag`, `rank_offset`, `bp_gap`, `strand`, `same_strand`, `product`, `gene_name`, `gene_category`.

- `rank_offset`: signed int (negative = upstream by `start`); anchor itself excluded.
- `bp_gap`: unsigned intergenic distance anchor↔neighbor (`0` if intervals overlap).
- `same_strand`: `True`/`False`/`None` (`None` when either strand is null).

## Result-size controls (Option B — batch)

| Field | Type | Description |
|---|---|---|
| total_matching | int | Neighbor rows after `max_bp_distance` + `same_strand` filters (pre-limit). |
| returned | int | Rows in this response. |
| truncated | bool | `total_matching > returned`. |
| anchors | list[AnchorBlock] | Per anchor with coordinates: `{locus_tag, organism_name, contig, start, end, strand, product, neighbors_returned, dropped_null_strand}`. |
| by_organism | list[{organism_name, count}] | Neighbor-row rollup. |
| not_found | list[str] | Anchor locus_tags absent from the KG. |
| not_matched | list[str] | Anchors that exist but lack coordinates (`start`/`contig` null) → no neighborhood. |
| warnings | list[str] | E.g. `same_strand` requested but an anchor's own strand is null → returned unfiltered for that anchor. |

**Sort key:** `anchor_locus_tag, rank_offset` (deterministic).
**Default limit:** 25. **Default window:** 5.

## Query Builders (`kg/queries_lib.py`)

### `build_gene_neighbors` (detail, bounded-window) — verified against live KG 2026-05-26

```cypher
UNWIND $locus_tags AS lt
MATCH (a:Gene {locus_tag: lt})
WHERE a.contig IS NOT NULL AND a.start IS NOT NULL
CALL {                                   // upstream: closest $window genes with smaller start
  WITH a
  MATCH (u:Gene)
  WHERE u.organism_name = a.organism_name AND u.contig = a.contig AND u.start < a.start
  WITH u ORDER BY u.start DESC LIMIT $window
  RETURN collect(u) AS ups
}
CALL {                                   // downstream: closest $window genes with larger start
  WITH a
  MATCH (d:Gene)
  WHERE d.organism_name = a.organism_name AND d.contig = a.contig AND d.start > a.start
  WITH d ORDER BY d.start ASC LIMIT $window
  RETURN collect(d) AS downs
}
WITH a, [i IN range(0, size(ups)-1)   | {nb: ups[i],   ro: -(i+1)}]
      + [i IN range(0, size(downs)-1) | {nb: downs[i], ro:  (i+1)}] AS pairs
UNWIND pairs AS p
WITH a, p.nb AS nb, p.ro AS rank_offset,
     CASE WHEN p.nb.end  < a.start THEN a.start  - p.nb.end  - 1
          WHEN p.nb.start > a.end  THEN p.nb.start - a.end   - 1
          ELSE 0 END AS bp_gap
// WHERE bp_gap <= $max_bp_distance    -- appended only when max_bp_distance is set
RETURN a.locus_tag AS anchor_locus_tag,
       nb.locus_tag AS neighbor_locus_tag,
       rank_offset, bp_gap,
       nb.strand AS strand,
       (nb.strand = a.strand) AS same_strand,
       nb.product AS product,
       nb.gene_name AS gene_name,
       nb.gene_category AS gene_category
ORDER BY anchor_locus_tag, rank_offset
```

- **Bounded window, not whole-contig:** two correlated subqueries each fetch ≤ `$window` genes (`ORDER BY start … LIMIT $window`) — materializes 2N rows, never the full contig. `collect()` is **inside** each subquery so a contig-edge anchor (no upstream/downstream) yields an empty list instead of being dropped — a correlated `CALL {}` returning zero rows would otherwise filter the anchor out, and 5.15 has no `OPTIONAL CALL`. **(This boundary bug was caught during verification — the naive two-CALL form silently dropped first/last genes on a contig.)**
- `range(0, size(x)-1)` is empty when a side is empty → natural boundary handling; anchor alone on its contig → `pairs=[]` → no neighbor rows (anchor still reported in the `anchors` envelope block).
- Efficiency rides the composite index `Gene(organism_name, contig, start)` (KG dependency below): index seek + ordered limit, ~`window` reads per side. **Correct without the index** (falls back to `organism_name`-index scan + in-memory sort).
- `same_strand` filter + `limit` applied in the API; `max_bp_distance` appended as a Cypher `WHERE` on the computed `bp_gap`.

**KG verification (done during spec):** anchors `['ACZ81_08860','ACZ81_00010']`, window 2 → ACZ81_08860 → −2/−1/+1/+2 (gaps 556/10/335/1119; the +1 neighbor is null-strand → `same_strand=null`); ACZ81_00010 (first gene on its contig) → only +1/+2 — boundary handled, anchor **not** dropped. Also verified: null-strand anchor (ACZ81_08865) → every neighbor `same_strand=null` (unappliable-filter case → API warns + returns unfiltered); `max_bp_distance=400` on ACZ81_08860 ±2 → 4 rows trimmed to 2 (gaps 10/335 kept, 556/1119 dropped).

### `not_found` — REUSE existing `build_gene_existence_check` (as in `gene_aa_sequence` above)

`not_found` comes from `build_gene_existence_check`; `found_tags` feeds the not_matched derivation below.

### `build_gene_neighbors_summary` (anchor metadata over existing anchors) — verified against live KG 2026-05-26

```cypher
UNWIND $locus_tags AS lt
MATCH (a:Gene {locus_tag: lt})
RETURN lt AS anchor_locus_tag,
       a.organism_name AS organism_name,
       a.contig AS contig, a.start AS start, a.end AS end,
       a.strand AS strand, a.product AS product,
       (a.contig IS NOT NULL AND a.start IS NOT NULL) AS has_coords
ORDER BY anchor_locus_tag
```
`MATCH` (not `OPTIONAL MATCH`) → only existing anchors return; existence/`not_found` is handled by the reused check, so this builder carries no `gene_exists` column. API derives `not_matched = [r.anchor_locus_tag for r if not r.has_coords]` (exists but no coordinates) and builds the `anchors` blocks from `has_coords=true` rows (strand carried for the `same_strand` warning).

**KG verification (done during spec):** `['ACZ81_08860','SYNW1755','NOTAREAL']` → existence check: `NOTAREAL` not found; anchor query returns ACZ81_08860 (`has_coords=true`) + SYNW1755 (`has_coords=false` → not_matched). NOTAREAL is absent from the anchor query (it's `MATCH`, not `OPTIONAL MATCH`) and surfaces only via the existence check.

## API Function (`api/functions.py`)

`gene_neighbors(locus_tags, window=5, max_bp_distance=None, same_strand=None, summary=False, limit=25, *, conn=None) -> dict`.

- Step 1: `build_gene_existence_check` → `not_found`, `found_tags`.
- Step 2: anchor (summary) builder over existing anchors → `not_matched` (`has_coords=false`) + anchor metadata blocks (incl. each anchor's `strand`).
- Step 3: detail builder (with `max_bp_distance` pushed into Cypher) unless `summary or limit == 0`.
- **`same_strand` filter applied in the API**, per anchor:
  - If the anchor's `strand` is null and `same_strand` is set → keep all its neighbors and append a `warnings` entry (filter unappliable). `dropped_null_strand = 0`.
  - Else keep neighbors where `same_strand == requested`; count dropped null-strand neighbors into `dropped_null_strand`.
- `total_matching` = post-filter neighbor-row count (pre-limit); `returned`/`truncated` from the limited slice; `by_organism` and per-anchor `neighbors_returned` from the post-filter set.

## Special handling — **deviations from the standard summary/total_matching contract (flag for reviewer)**

1. **`same_strand` filtered in the API, not Cypher.** Justified by the null-strand-anchor special case (warn + return unfiltered) and the need to count `dropped_null_strand` per anchor. Feasible because the result set is intrinsically bounded by `window` × anchors. (`max_bp_distance` stays in Cypher — clean numeric predicate, no special case.)
2. **`total_matching` derived from the detail set, not the summary query.** The summary/anchor query computes per-anchor identity (`not_found`/`not_matched`/metadata), not neighbor counts. Bounded result set makes detail-derived counting safe. This differs from the usual "summary computes `total_matching`; must equal detail count" rule — called out here per the skill's *"when something doesn't fit, surface to the user."*

---
---

# Shared: Implementation Order (per tool; Mode B → each agent does both)

| Step | Layer | File | What |
|---|---|---|---|
| 1 | Query builder | `kg/queries_lib.py` | `build_gene_aa_sequence` + `_summary`; `build_gene_neighbors` + `_summary`. **Reuse** existing `build_gene_existence_check` for `not_found` (no new existence builder). |
| 2 | API | `api/functions.py` | `gene_aa_sequence()`, `gene_neighbors()` |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | imports + `__all__` |
| 4 | MCP wrapper | `mcp_server/tools.py` | 2 `@mcp.tool` wrappers + Pydantic models |
| 5–7 | Unit tests | `tests/unit/test_{query_builders,api_functions,tool_wrappers}.py` | + `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py`, `test_api_contract.py` | live-KG smoke + contract |
| 9 | Regression / eval | `tests/regression/test_regression.py`, `tests/evals/{cases.yaml,test_eval.py}` | `TOOL_BUILDERS` (both dicts) + cases |
| 10 | About content | `inputs/tools/{name}.yaml` → `build_about_content.py` | examples, chaining, mistakes |
| 11 | Docs | `CLAUDE.md` | 2 rows in MCP Tools table |
| 12 | Cross-cutting (hand-authored) | `mcp_server/server.py` | instructions blurb: `37`→`39` tools; add a category for sequence/genomic context |
| 13 | Cross-cutting (hand-authored) | `skills/.../references/guide/start_here.md` | new 9th family "Sequence & genomic context" + decision-tree entries |
| 14 | Cross-cutting (hand-authored) | `skills/.../references/guide/concepts.md` | note Gene carries AA `sequence` + genomic coords (`contig`/`start`/`end`/`strand`) |

**No example file** (decision). `conventions.md` / `python_api.md` unchanged.

## Cross-cutting MCP assets & Phase-2 ownership

Steps 12–14 are hand-authored docs **outside** the standard doc-updater ownership (`inputs/tools/*.yaml`, `references/analysis/*.md`, `examples/*.py`, `CLAUDE.md`). To prevent them slipping through Phase 2, **expand the `doc-updater` brief** to also own:

- `mcp_server/server.py` instructions string — bump the tool count and add the sequence/genomic-context category. (Note: `tool-wrapper` owns `tools.py`, not `server.py`, so this is explicitly assigned to `doc-updater` to avoid a two-owner collision on neighboring code.)
- `skills/multiomics-kg-guide/references/guide/start_here.md` — **9th family** row "Sequence & genomic context" (anchor: *"I have a gene; I want its protein sequence, or what sits next to it on the genome"*; entry points `gene_aa_sequence`, `gene_neighbors`). Add decision-tree entries: *"Get the protein/AA sequence of gene X (for BLAST/alignment)"* → `gene_aa_sequence(fasta=True)`; *"What genes sit next to X on the genome / is X in an operon?"* → `gene_neighbors`. Update "the eight tool families" → "nine".
- `skills/multiomics-kg-guide/references/guide/concepts.md` — one sentence in the Gene data-model note: genes carry an amino-acid `sequence` and genomic coordinates (`contig`, `start`, `end`, `strand`; `strand` ~50% null), exposed by `gene_aa_sequence` / `gene_neighbors`.

These are hand-authored (not regenerated by `build_about_content.py`); the `--lint` outfacing-doc gate still applies to them.

## Pydantic response models (`mcp_server/tools.py`)

Field descriptions use real KG values per the field-rubric (e.g. `locus_tag` example `'ACZ81_08860'`, organism `'Alteromonas macleodii HOT1A3'`). Rows are typed models, not `list[dict]`:
- `GeneAaSequenceResult`, `GeneAaSequenceResponse` (with `SequenceLengthStats`, `OrganismCount`).
- `GeneNeighborsResult`, `AnchorBlock`, `GeneNeighborsResponse`.

`not_found` ≠ `not_matched` documented in both envelope schemas (rubric: empty-result shapes unambiguous).

## Tests (key cases beyond template defaults)

- `gene_aa_sequence`: `fasta=True` ⇒ rows have `sequence=None` and envelope `fasta` non-empty (no duplication); `fasta=False` ⇒ reverse. `not_matched` (no-sequence gene) vs `not_found`. `sequence_length_stats` quantiles. `summary=True` ⇒ `results=[]`, stats present.
- `gene_neighbors`: contig-boundary anchor (asymmetric offsets); null-strand anchor + `same_strand=True` ⇒ unfiltered + `warnings` entry; `same_strand=True` drops null-strand neighbors and increments `dropped_null_strand`; `max_bp_distance` cap; anchor-with-no-coords ⇒ `not_matched`; anchor alone on contig ⇒ empty neighbors but present in `anchors`.
- Fixtures: a no-coordinate / no-sequence gene (e.g. `SYNW1755`) and a null-strand gene (e.g. `ACZ81_08865`).

## Documentation / chaining (for YAML)

- `gene_aa_sequence` chaining: `resolve_gene → gene_aa_sequence(fasta=True)`; `genes_by_function → gene_aa_sequence`.
- `gene_neighbors` chaining: `differential_expression_by_gene → gene_neighbors → gene_overview` (operon context for a DE hit); `genes_by_metabolite → gene_neighbors`.
- Mistake to document: `gene_neighbors` is **positional only** — not co-expression; neighbors are on the same contig, so a fragmented assembly yields fewer/no neighbors near contig ends.

## Decisions log

| Question | Decision |
|---|---|
| Sequence kind / name | AA only; `gene_aa_sequence` (not `get_aa_fasta` — `gene_` is the convention). |
| FASTA shape | `fasta` flag, default `False`; sequence carried by rows **or** blob, never both. |
| Neighbor window | Rank ±N (default 5) + optional `max_bp_distance` cap. |
| same_strand | `bool\|None`; null-strand neighbors dropped when set; null-anchor → warn + unfiltered. Filtered in API. |
| Anchor in results | Excluded; reported in `anchors` envelope block. |
| `bp_gap` sign | Unsigned; direction via `rank_offset`. |
| verbose | None on either tool. |
| Batch scope | Cross-organism for both (locus_tags globally unique). |
| Spec file | One combined (this file). |
| Pagination | `gene_aa_sequence` has `offset` (default 0, `SKIP $offset LIMIT $limit`). `gene_neighbors` has no `offset` — its result set is bounded by `window × anchors`. |
| not_found primitive | Both reuse existing `build_gene_existence_check` (DRY; matches `gene_ontology_terms` Step-1 pattern). `not_matched` derived in Python: `found_tags − matched_tags` (aa_sequence) / `has_coords=false` (neighbors). No new existence builder. |
| Cross-cutting docs | Update `server.py` instructions (37→39 + new category), `start_here.md` (9th family "Sequence & genomic context"), `concepts.md` (Gene sequence + coords note). Assigned to expanded `doc-updater` brief. No example file. |
| total_matching (neighbors) | Derived from detail set (bounded) — documented deviation. |
| Neighbor query shape | Bounded-window (two `LIMIT $window` subqueries, `collect()` inside to survive contig edges), not whole-contig collect. Efficient + boundary-correct. |
| Index | Composite RANGE `Gene(organism_name, contig, start)` requested (KG-spec written; user willing). Performance only — tools correct without it. |
