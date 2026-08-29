# Tool spec: `gene_overview` TCDB / CAZy family-count routing signals (backlog 3.4)

**Date:** 2026-08-29 · **Mode:** A (single tool, extension) · **Size:** S · **Origin:** backlog 3.4
(TCDB/CAZy follow-up). Verified against the live KG dev build 2026-08-29 (rebuild #3, 127,458 genes).

## Purpose

Add two per-row routing counts to `gene_overview` — `tcdb_family_count` and `cazy_family_count` —
parallel to the existing `ncbifam_family_count`, plus two envelope counts `has_tcdb` / `has_cazy`
parallel to `has_ncbifam`. They answer "does this gene carry a transporter-family / carbohydrate-active-
enzyme call, and how many?" before drilling into `gene_ontology_terms(ontology=['tcdb'|'cazy'])`.

`transporter_count` was removed in the substrate-depth migration because it counted TCDB ancestor
attachments superseded by a more specific call on the same gene. `tcdb_family_count` is its correct
replacement: it counts **`attachment_depth = 'most_specific'` edges only**, so it equals the number of
TCDB rows `gene_ontology_terms(ontology=['tcdb'], mode='leaf')` returns by default and the number of
families `metabolites_by_gene`'s transport arm walks.

## Out of scope

- No new parameters, no filters on the counts (routing signals — read, then drill).
- No organism-level `tcdb_gene_count` / `cazy_gene_count` on `list_organisms` (would need KG props;
  not asked — `ontology_landscape(ontology=['tcdb','cazy'])` already answers the organism question).
- No change to `tcdb_evidence_score_max` / `transport_substrate_resolution` / `transported_metabolite_count`.

## Status / Prerequisites

- [x] KG exploration done — both props exist on every Gene; `Gene.tcdb_family_count` has the wrong
      multiplicity (see §KG dependencies) → explorer computes live; KG ask filed
      (`docs/kg-specs/2026-08-29-gene-overview-family-counts-asks.md`, P3, non-blocking).
- [x] Cypher verified against live KG.
- [ ] Spec frozen (user approval).
- [ ] Ready for Phase 2.

## Use cases / chains

- `genes_by_function` / `resolve_gene` → `gene_overview` → per-row `tcdb_family_count > 0` →
  `gene_ontology_terms(locus_tags=[...], ontology=['tcdb'])` for the family IDs and evidence, or
  `metabolites_by_gene(..., evidence_sources=['transport'])` for substrates (when `transport_substrate_resolution='resolved'`).
- per-row `cazy_family_count > 0` → `gene_ontology_terms(locus_tags=[...], ontology=['cazy'])`;
  peers via `genes_by_ontology(ontology='cazy', organism=...)`.
- Envelope `has_tcdb` / `has_cazy` = batch triage ("how many of my DE genes are transporters / CAZymes")
  before deciding whether a TCDB / CAZy ORA (`pathway_enrichment(ontology='tcdb'|'cazy')`) is worth running.

## KG dependencies (verified 2026-08-29)

| Fact | Value |
|---|---|
| `Gene_has_tcdb_family` edges | 54,627 = 47,360 `attachment_depth='most_specific'` (30,547 genes, 1,377 families) + 7,267 `'superseded'` (7,045 genes, 160 families) |
| edge prop vs structural predicate | `attachment_depth='most_specific'` ⟺ `TCDB_DEEPEST_ATTACHMENT_PREDICATE` on **every** edge (0 disagreements) — the edge prop is the cheap, exact form |
| `Gene.tcdb_family_count` (KG precompute) | present on all 127,458 genes, **= all-edges count** (KG validity test `test_tcdb_family_count_is_not_tier_gated` pins that); differs from the most-specific count on 7,045 genes (e.g. PMM0392: 8 vs 7; M744_10340: 7 vs 4). **Not used** — same defect that removed `transporter_count`. |
| `Gene.cazy_family_count` (KG precompute) | present on all genes, = `Gene_has_cazy_family` edge count on every gene (CAZy is flat, 2,197 edges / 1,953 genes / 85 families; per-gene max 4). **Used as-is.** |
| invariant | genes with ≥1 most-specific TCDB edge (30,547) = genes with `transport_substrate_resolution IS NOT NULL` (28,854 resolved + 1,693 family_inferred) ⇒ `tcdb_family_count > 0 ⟺ tcdb_evidence_score_max IS NOT NULL ⟺ transport_substrate_resolution IS NOT NULL` |
| distribution | most-specific families per TCDB gene: 1 → 21,502 · 2 → 4,933 · 3 → 2,239 · … · 10 → 3 |

## Row / envelope contract

**Per-row compact (append after `ncbifam_family_count`, before `merops_evidence_score_max`):**

| field | type | semantics |
|---|---|---|
| `tcdb_family_count` | `int`, 0 default | Distinct TCDB families attached at `attachment_depth='most_specific'` (superseded ancestors excluded). 0 = no TCDB call; then `tcdb_evidence_score_max` is null and `transport_substrate_resolution` null. |
| `cazy_family_count` | `int`, 0 default | Distinct CAZy families (`Gene_has_cazy_family`; flat ontology, no depth rule). Precomputed `Gene.cazy_family_count`. |

**Envelope (next to `has_ncbifam`):**

| field | type | semantics |
|---|---|---|
| `has_tcdb` | `int` | Input genes with `tcdb_family_count > 0`. |
| `has_cazy` | `int` | Input genes with `cazy_family_count > 0`. |

Both are always present (0 when none) — `SparseRow` absent-vs-null rule does not apply to zero-filled counts,
same as `ncbifam_family_count`. No verbose additions. Result-size controls unchanged (batch tool:
`summary`, `verbose`, `limit`, `offset`, `not_found`).

## Verified Cypher

### Detail (`build_gene_overview`) — add to the RETURN block

```cypher
       -- TCDB family count at the deepest attachment only (backlog 3.4). The
       -- KG's Gene.tcdb_family_count counts every edge incl. superseded
       -- ancestors — the transporter_count defect — so count live on the
       -- edge prop (exactly equivalent to TCDB_DEEPEST_ATTACHMENT_PREDICATE).
       size([(g)-[r:Gene_has_tcdb_family]->(:TcdbFamily)
             WHERE r.attachment_depth = 'most_specific' | r]) AS tcdb_family_count,
       coalesce(g.cazy_family_count, 0) AS cazy_family_count,
```

Verified against live KG (`UNWIND [...] MATCH (g:Gene {locus_tag: lt})`):

| locus_tag | tcdb_family_count | cazy_family_count | KG `tcdb_family_count` (all edges) |
|---|---|---|---|
| PMM0392 | 7 | 0 | 8 (3.A.1 superseded) |
| PMM0001 | 0 | 0 | 0 |
| DEH24_11900 | 0 | 2 | 0 |
| HP15_1897 | 0 | 4 | 0 |
| Sputw3181_2456 | 1 | 2 | 1 |
| MIT1002_03660 | 0 | 0 | 0 |
| NOPE_1 | — (not_found) | | |

500-gene MED4 batch: 500 rows, 107 with TCDB, 6 with CAZy, max 8 — no measurable cost over the current query.

### Summary (`build_gene_overview_summary`) — add to the RETURN block

```cypher
       size([g IN found WHERE EXISTS {
         MATCH (g)-[r:Gene_has_tcdb_family]->(:TcdbFamily)
         WHERE r.attachment_depth = 'most_specific'
       }]) AS has_tcdb,
       size([g IN found WHERE coalesce(g.cazy_family_count, 0) > 0]) AS has_cazy,
```

Verified on the 7-tag batch above: `total_matching 6, has_tcdb 2, has_cazy 3` = detail rows with count > 0.

No filter no-ops to check (no new params). Edge cases: not-found tag drops out of both queries as today;
gene with no edges → 0 / 0 (PMM0001).

## Layer plan

| Layer | File | Change |
|---|---|---|
| query | `kg/queries_lib.py` | 2 RETURN columns in `build_gene_overview`, 2 in `build_gene_overview_summary`; docstring RETURN-key lists |
| api | `api/functions.py::gene_overview` | pass-through of `has_tcdb` / `has_cazy` into the envelope; docstring |
| mcp | `mcp_server/tools.py` | `GeneOverviewResult.tcdb_family_count` / `.cazy_family_count` (`int = 0`, ≤250-char descriptions with routing); `GeneOverviewResponse.has_tcdb` / `.has_cazy`; tool docstring `Routing:` sentence gains `gene_ontology_terms(ontology=['tcdb'|'cazy'])` |
| docs | `inputs/tools/gene_overview.yaml` (extend the PMM0392/PMM0001 example + a chaining line + a mistakes line: "`tcdb_family_count` counts deepest attachments only — ancestor membership is visible via `gene_ontology_terms(ontology=['tcdb'], include_superseded=True)`"), regen; `CLAUDE.md` tool-table row; `CHANGELOG.md [Unreleased]` Added entry |
| tests | unit ×3 layers (new tests only, ADD-only); `tests/integration/test_api_contract.py` expected-keys set += 2; `tests/integration/test_trust_invariants.py` — (i) `tcdb_family_count` == count of `attachment_depth='most_specific'` edges on a sample, (ii) `tcdb_family_count > 0 ⟺ transport_substrate_resolution IS NOT NULL` across the batch, (iii) PMM0392 reads 7 not 8; `tests/integration/test_mcp_tools.py` PMM0392 / PMM0001 cases; `tests/integration/edge_cases/scenarios.py` — extend `gene_overview_scenarios` with a CAZy-bearing gene (`HP15_1897`, `cazy_family_count=4`, `tcdb_family_count=0`) — coverage gate already satisfied; regression `--force-regen` (7 `gene_overview_*` goldens gain 2 row keys + 2 envelope keys, nothing else may move) |

## Acceptance

1. `gene_overview(locus_tags=['PMM0392','PMM0001'])` → PMM0392 `tcdb_family_count=7`, `cazy_family_count=0`; PMM0001 `0 / 0`; envelope `has_tcdb=1`, `has_cazy=0`.
2. `gene_overview(locus_tags=['HP15_1897'])` → `cazy_family_count=4`, `has_cazy=1`.
3. For every gene in the regression batches, `tcdb_family_count` equals the row count of `gene_ontology_terms(locus_tags=[lt], ontology=['tcdb'])` (leaf mode, default `include_superseded=False`).
4. `--lint` clean; unit / `-m kg` integration / regression green; regen diff limited to the 4 new keys.

## Follow-up (not blocking)

KG ask `2026-08-29-gene-overview-family-counts-asks.md` (P3): redefine `Gene.tcdb_family_count` to
most-specific-only. When it lands, swap the comprehension for `coalesce(g.tcdb_family_count, 0)`; the
`test_trust_invariants` check (i) guards the swap.
