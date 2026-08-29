# Tool spec: bare metabolite-ID coercion (cross-tool, Mode B) — backlog 3.2

## Purpose

Accept un-prefixed / xref metabolite identifiers (`C00064`, `CHEBI:17234`,
`17234`, `HMDB0000122`, `MNXM1095050`) in every `metabolite_ids` /
`exclude_metabolite_ids` parameter and resolve them to the KG-canonical
`Metabolite.id` (`kegg.compound:C00064`, `chebi:10004`, `mnx:MNXM…`) before
the query runs. Today every builder filters with `m.id IN $metabolite_ids`
(exact match), so a bare ID silently lands in `not_found` with 0 rows.

Origin: KG-MET-014 (closed KG-side 2026-05-05 — the node carries both forms;
fix is explorer-side).

## Tools touched (7)

`list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`,
`list_metabolite_assays`, `metabolites_by_quantifies_assay`,
`metabolites_by_flags_assay`, `assays_by_metabolite` — both `metabolite_ids`
and `exclude_metabolite_ids` on each (14 params).

## Out of scope

- `list_metabolites`' dedicated exact-xref filters `kegg_compound_ids` /
  `chebi_ids` / `hmdb_ids` / `mnxm_ids` — unchanged; docstring gains a
  one-line cross-reference.
- `metabolite_pathway_ids` / `pathway_ids` prefix tolerance.
- Non-numeric `mnxm_id` values (e.g. `WATER`) — not coerced.
- No Cypher builder changes. Builders keep `m.id IN $…` exactly as-is.

## KG facts (live, rebuild 2026-08-29)

| `m.id` prefix | nodes | `kegg_compound_id` | `chebi_id` | `hmdb_id` | `mnxm_id` |
|---|---|---|---|---|---|
| `kegg.compound:` | 2717 | 2717, bare `C00001` | 2407, bare `10743` | 1502, `HMDB0002111` | 2717 |
| `chebi:` | 635 | 0 | 635 (== id suffix) | 0 | 626 |
| `mnx:` | 4 | 0 | 0 | 0 | 4 |

Uniqueness: KEGG 1:1 (2717/2717). CHEBI 17 collisions (two `kegg.compound:`
nodes share one `chebi_id`, e.g. C00354/C05378). HMDB 15 dups, MNXM 18 dups.

## Design

### New api-layer helper (`api/functions.py`, private)

```python
def _canonicalize_metabolite_ids(
    conn, ids: list[str] | None,
) -> tuple[list[str] | None, dict[str, list[str]], list[str]]:
    """Return (canonical_ids, resolved_aliases, warnings)."""
```

Rules, applied per input string, in order:

1. Contains `:` and prefix ∈ {`kegg.compound`, `chebi`, `mnx`} → pass through
   verbatim (already canonical). Any other prefixed form except `CHEBI:` is
   also passed through verbatim (so it lands in `not_found` as today).
2. `^C\d{5}$` → `m.kegg_compound_id`.
3. `^CHEBI:\d+$` (case-insensitive prefix) or `^\d+$` → strip prefix, match
   `m.chebi_id`.
4. `^HMDB\d+$` → `m.hmdb_id`. `^MNXM\d+$` → `m.mnxm_id`.
5. Unresolved (no node matched) → kept verbatim in the output list so the
   existing existence probes report it in `not_found` in the **user's input
   form**.

Multiple matches (CHEBI/HMDB/MNXM collisions) → **expand to all matches**
and append a warning:
`"'<raw>' resolved to N metabolites: [<ids>] — pass the canonical id to narrow."`
Never silently pick one.

Input order preserved; duplicates after expansion removed (first-seen order).
`None`/`[]` → returned unchanged, no query. Exactly one round-trip per parameter
when at least one bare ID is present (single `UNWIND $raw` query, verified
below); zero when every ID is already canonical.

Called at the top of each of the 7 functions on `metabolite_ids` then
`exclude_metabolite_ids`, **before** the existing exclude-wins-on-overlap
set-difference, so overlap is computed on canonical IDs. `not_found` is then
computed as today (probes on `m.id`) — since unresolved inputs stay verbatim
they surface unchanged. Already-resolved inputs never appear in `not_found`.

### Verified Cypher (live KG, 2026-08-29)

```cypher
UNWIND $raw AS raw
WITH raw,
     CASE WHEN toUpper(raw) STARTS WITH 'CHEBI:' THEN substring(raw,6) ELSE raw END AS key
OPTIONAL MATCH (m:Metabolite)
WHERE (raw =~ 'C[0-9]{5}'  AND m.kegg_compound_id = raw)
   OR (key =~ '[0-9]+'     AND m.chebi_id = key)
   OR (raw =~ 'HMDB[0-9]+' AND m.hmdb_id = raw)
   OR (raw =~ 'MNXM[0-9]+' AND m.mnxm_id = raw)
RETURN raw, collect(m.id) AS canonical
```

Verified output: `C00064 → [kegg.compound:C00064]`, `HMDB0000122 →
[kegg.compound:C00221]`, `MNXM1095050 → [chebi:10004]`, `bogus → []`.
Prefixed passthrough is filtered out in Python before the UNWIND (not sent).
Lives in `queries_lib.py` as `build_resolve_metabolite_aliases(raw_ids)`
(query-builder owns the Cypher string; api owns the regex classification +
merge logic).

### Envelope additions (all 7 response models)

- `resolved_aliases: dict[str, list[str]]` — `{input: [canonical, ...]}`, only
  entries that were actually coerced (empty dict when none). Covers both
  `metabolite_ids` and `exclude_metabolite_ids` inputs in one map.
- `warnings: list[str]` — **added** to `ListMetabolitesResponse`,
  `ListMetaboliteAssaysResponse`, `AssaysByMetaboliteResponse` (default `[]`);
  the other 4 already carry it — collision warnings are appended.

No per-row changes. No new tool params. No filter/sort changes.

### Tool-layer

Pass-through of the two envelope keys; parameter descriptions for
`metabolite_ids` / `exclude_metabolite_ids` gain one clause:
"Accepts canonical `kegg.compound:C00064` or bare `C00064` / `CHEBI:17234` /
`HMDB…` / `MNXM…` (resolved via xrefs; see `resolved_aliases`)." ≤ 250 chars.

### Docs

Each of the 7 YAMLs: one `mistakes` entry replaced/added ("bare `C00064`
returned 0 rows — now resolves; ambiguous CHEBI expands + warns") and
`examples` untouched. `docs://guide/conventions` gains a short
"metabolite ID forms" paragraph. Regen via `build_about_content.py`.
CLAUDE.md table: one clause on `list_metabolites` row ("bare / xref metabolite
IDs coerced to canonical on every `metabolite_ids` param; `resolved_aliases`").

## Tests

- Unit (`test_api_functions.py`): helper classification per rule; passthrough
  short-circuit (no query); collision expansion + warning text; unresolved
  stays verbatim and appears in `not_found`; exclude-wins-on-overlap still
  holds when the overlap is only visible after coercion
  (`metabolite_ids=['C00064'], exclude_metabolite_ids=['kegg.compound:C00064']`
  → excluded).
- Unit (`test_query_builders.py`): `build_resolve_metabolite_aliases`
  shape/params.
- Unit (`test_tool_wrappers.py`): the two envelope keys on all 7 models.
- Edge cases (`tests/integration/edge_cases/scenarios.py`): add one bare-ID
  scenario per tool to the existing `{tool}_scenarios()` builders
  (tools are already registered — extend, do not re-register).
- Regression: `--force-regen` required (new envelope keys).

## Result-size controls

Unchanged for all 7 tools.

## Status

- [x] KG spec: none needed
- [x] Scope reviewed with user (backlog 3.2 scoping, 2026-08-29)
- [x] Cypher verified against live KG
- [x] Frozen 2026-08-29 (user approved: expand-all on collisions + warn)
