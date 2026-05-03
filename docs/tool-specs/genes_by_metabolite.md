# genes_by_metabolite — Tool spec (Phase 1)

## Executive Summary

Step 2 of the chemistry slice 1 symmetric three-tool set:

| Step | Tool | Anchor |
|---|---|---|
| 1 | `list_metabolites` (shipped 2026-05-03, commit 121097a) | metabolite discovery (cross-organism) |
| **2** | **`genes_by_metabolite` (THIS SPEC)** | **metabolite → genes (single-organism)** |
| 3 | `metabolites_by_gene` | gene → metabolites (single-organism) |

Drill-down anchored on metabolite IDs. Returns rows showing which genes in the
requested organism are connected to each metabolite, via either:

- **Metabolism path:** `Gene → Reaction → Metabolite` (`evidence_source = "metabolism"`)
- **Transport path:** `Gene → TcdbFamily → Metabolite` (`evidence_source = "transport"`) — single-hop via the **TCDB substrate-edge rollup** (landed 2026-05-03; the underlying TCDB-CAZy ontology landed 2026-05-02)

UNION semantics: a gene/metabolite pair reachable through both paths produces
two rows (one per evidence source). Direction-agnostic on both arms — neither
path distinguishes substrate from product.

The marquee design constraint of this spec is the **`transport_confidence` model**.
The TCDB substrate-edge rollup propagates leaf-curated substrates up the
hierarchy, so a gene annotated only at a broad family level
(e.g. `tcdb:3.A.1` ABC Superfamily) appears to "transport" every substrate
of every member system. Each transport row carries a required
`transport_confidence` field (`substrate_confirmed` / `family_inferred`)
discriminating these cases, with five reinforcement surfaces (filter,
envelope rollup, auto-warning, sort, docstring) so the LLM cannot quietly
conflate them. Metabolism rows leave `transport_confidence = None` (sparse) —
the field is scoped strictly to transport-row provenance.

The `evidence_source` Literal is **`{"metabolism", "transport"}` only** —
metabolomics evidence is metabolite-anchored (no gene anchor) and surfaces in
`list_metabolites`, not here. Same for `metabolites_by_gene`.

## Out of Scope

- **`tcdb_class_ids` filter.** TCDB is now a first-class ontology — TCDB-anchored
  gene queries belong in `genes_by_ontology(ontology="tcdb", term_ids=[...])`.
  Cross-cutting TCDB-class filtering here would duplicate that surface and
  conflict with the dual-role architecture (TCDB serves as both a connecting
  layer used here AND an ontology used elsewhere).
- **Rhea / `Gene.catalytic_activities` direction-aware substrate vs product
  splitting.** Future spec opportunity. Both arms remain direction-agnostic
  in slice 1.
- **Metabolomics evidence rows.** No gene anchor — surfaces only in
  `list_metabolites`.
- **Explicit `min_reaction_count` / `min_gene_count` row filters.** Caller
  ranks client-side from envelope rollups.
- **Cross-organism mode.** Single-organism enforced (mirrors
  `differential_expression_by_gene`). Cross-feeding workflows call once per
  organism and intersect locus_tags client-side.
- **Pathway-anchored TCDB rollup tweaks.** The `metabolite_pathway_ids`
  filter applies via `m.pathway_ids` (KG-A5 denorm) — uniform across both
  arms. **No gene-anchored pathway filter** — gene-side pathway scoping
  goes through `genes_by_ontology(ontology="kegg")`.

## Status / Prerequisites

- [x] Slice-1 design approved
  (`docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md` § 2.2)
- [x] Chemistry-slice-1 KG asks A1–A4 landed (verified 2026-05-02)
- [x] Chemistry-slice-1 follow-up KG asks A5–A8 landed (verified 2026-05-02)
- [x] TCDB-CAZy ontology spec landed
  (`multiomics_biocypher_kg/docs/kg-changes/tcdb-cazy-ontologies.md`,
  2026-05-02)
- [x] TCDB substrate-edge rollup landed (2026-05-03; substrate edges propagate
  to all ancestors — single-hop transport queries at any level)
- [x] Cypher verified against live KG (see "KG verification" below)
- [x] Result-size controls decided: `summary` / `verbose` / `limit=10` /
  `offset` (default `limit=10` covers p75 of UNION row distribution; offset
  for coenzyme-tail pages)
- [ ] Ready for Phase 2 (build) — pending user approval of this spec

## Use cases

- **Discovery → drill-down.** From `list_metabolites`, when a row has
  `gene_count > 0`, pivot to find catalysts and transporters in a specific
  organism:
  `genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4")`
  → urea catalysts (urease) + transporters (urtA-urtE substrate-confirmed,
  plus broader ABC family-inferred).

- **Cross-feeding hypothesis primitive (Workflow B).** Run the same call once
  per organism with the same metabolite_ids; intersect / diff locus_tag
  result sets client-side to find metabolites where one organism's catalysts
  go up in coculture and the other's transporters do too.

- **N-source drill-down (Workflow A step 4).** After identifying N-bearing
  metabolites in MED4 via `list_metabolites(elements=["N"])`, drill into the
  high-coverage ones:
  `genes_by_metabolite(metabolite_ids=[ammonia, glutamine, urea], organism=MED4)`
  → all enzymes and transporters in MED4 connected to N-input metabolites.

- **High-precision transporter hunt.** Find substrate-curated transporters
  (no rollup false positives):
  `genes_by_metabolite(metabolite_ids=[id], organism=..., transport_confidence="substrate_confirmed", evidence_sources=["transport"])`.

- **Routing to drill-downs.** Any `top_genes` row pivots to
  `differential_expression_by_gene(locus_tags=[...], organism=...)` for
  transcriptional response or `gene_overview` for richer per-gene context.
  Any `top_tcdb_families` row pivots to
  `genes_by_ontology(ontology="tcdb", term_ids=[id], organism=...)` for
  sibling genes in the same family.

## KG dependencies

### Nodes & properties read

`Gene`:
- `locus_tag` (str)
- `gene_name` (str | null) — sparse result field
- `product` (str | null) — sparse result field
- `gene_category` (str) — both filter target and result/envelope field
- `organism_name` (str) — single-organism filter

`Reaction`:
- `id` (str, full prefixed `kegg.reaction:R*`) — result field, `top_reactions` envelope key
- `name` (str | empty) — result field; **32/2,349 reactions have empty name** in the KG. Surfaces as `reaction_name = ''` on the row; no envelope-level diagnostic (this tool is gene → metabolite focused; reaction-name nullness is a niche reaction-side detail).
- `ec_numbers` (list[str]) — `ec_numbers` filter target + result field
- `mass_balance` (Literal["balanced","unbalanced"]) — filter target (no nulls in KG; 1,922 balanced + 427 unbalanced) + result field
- `mnxr_id` (str | null) — verbose field
- `rhea_ids` (list[str] | null) — verbose field

`TcdbFamily`:
- `id` (str, e.g. `tcdb:3.A.1.4.5`) — result field on transport rows
- `name` (str) — result field; **for `tc_subfamily` / `tc_specificity` levels falls back to `tcdb_id`**; only `tc_family`-level (10 distinct in MED4) carry full human-readable names
- `level_kind` (Literal["tc_class","tc_subclass","tc_family","tc_subfamily","tc_specificity"]) — drives `transport_confidence` derivation; sparse result field on transport rows
- `tc_class_id` (str, post-import; 100% coverage) — pointer to the `tc_class` ancestor; powers TCDB-class envelope/diagnostics

`Metabolite`:
- `id` (str, full prefixed) — primary join key
- `name`, `formula`, `mass`, `chebi_id` (sparse) — result fields
- `pathway_ids` (list[str], KG-A5 denorm; 100% coverage, 920/3,025 with empty list) — backs the `metabolite_pathway_ids` filter
- `inchikey`, `smiles`, `mnxm_id`, `hmdb_id` — verbose fields

### Edges traversed

| Edge | Direction | Arm | Hops |
|---|---|---|---|
| `Gene_catalyzes_reaction` | Gene → Reaction | metabolism | 1 |
| `Reaction_has_metabolite` | Reaction → Metabolite | metabolism | 1 |
| `Gene_has_tcdb_family` | Gene → TcdbFamily | transport | 1 |
| `Tcdb_family_transports_metabolite` | TcdbFamily → Metabolite | transport | 1 (rollup-extended; no variable-length walk) |

Total **2 hops per arm**. Pre-rollup the transport arm needed
`Tcdb_family_is_a_tcdb_family*0..` to descend to leaves; post-rollup the
substrate edge exists on every TcdbFamily ancestor at any level eggNOG
might annotate.

### Indexes
- `MATCH (g:Gene {organism_name: $org})` benefits from the `organism_name`
  index on Gene (existing).
- `m.id IN $metabolite_ids` benefits from the `Metabolite(id)` unique
  constraint / index (existing).
- No fulltext entry point on this tool — `metabolite_ids` is required.

---

## Live-KG state snapshot (verified 2026-05-03)

### Filter-column population

| Column | Coverage | Notes |
|---|---|---|
| `r.mass_balance` | 100% (no nulls) | balanced=1,922; unbalanced=427 |
| `r.ec_numbers` | 95% (2,242/2,349 reactions) | 107 reactions w/o EC |
| `r.name` | 100% non-null | **32 reactions have empty `''`**; surfaces as-is on metabolism rows; not tracked at envelope level |
| `tf.tc_class_id` | 100% (4,844/4,844) | post-import pointer |
| `m.pathway_ids` | 100% (3,025/3,025) | 920 metabolites have empty list |
| `g.gene_category` | 100% on Gene | ~25 distinct values per organism |

### Row-count distribution per (metabolite × MED4) — UNION metabolism + transport

| Slice | rows |
|---|---|
| Total metabolites reachable from any MED4 gene | **1,550** |
| Median rows per (metabolite × MED4) | 3 |
| p75 | 9 |
| p90 | 13 |
| p95 | 15 |
| p99 | 55 |
| Max (water/H+) | 355 |
| Examples: ATP × MED4 | 199 (metabolism-only) |
| Urea × MED4 | 23 (4 metabolism + 19 transport: 10 substrate-confirmed rows + 9 family-inferred rows; 14 distinct transport genes — 5 substrate-confirmed × 2 specificity-leaves + 9 family-inferred) |
| Nitrite × MED4 | 14 (transport-only: 5 substrate-confirmed + 9 family-inferred) |
| Glutamine × MED4 | 42 (32 metabolism + 10 transport, all family-inferred — no urea-style tc_specificity leaf) |

### Transport-arm row mix by `tf.level_kind` (MED4 transport rows)

| level_kind | rows | distinct families | transport_confidence |
|---|---|---|---|
| `tc_family` | 5,045 (89%) | 10 (broad: ABC, MFS, etc.) | `family_inferred` |
| `tc_subfamily` | 576 | 48 | `family_inferred` |
| `tc_specificity` | 54 (1%) | 18 (substrate-curated) | `substrate_confirmed` |

The 89% / 1% split is **why the auto-warning matters**: family-inferred
dominates the transport arm. Substrate-confirmed transporters in MED4 are a
minority by count but the biologically precise set.

### Empty-result reachability

- **1,475 / 3,025 Metabolites** are unreachable from any MED4 gene via either
  arm — these become `not_matched` if requested (e.g. transport-only Metabolites
  curated for non-MED4 strains).

---

## Tool Signature

```python
@mcp.tool(
    tags={"genes", "metabolites", "chemistry", "drill-down"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def genes_by_metabolite(
    ctx: Context,
    metabolite_ids: Annotated[list[str], Field(
        description="Metabolite IDs to drill into (full prefixed, "
        "case-sensitive). E.g. ['kegg.compound:C00086', 'kegg.compound:C00064']. "
        "`not_found.metabolite_ids` lists IDs that don't exist as a Metabolite "
        "node; `not_matched` lists IDs that exist but have no gene reach in "
        "the requested organism via either arm.",
        min_length=1,
    )],
    organism: Annotated[str, Field(
        description="Organism name (case-insensitive, fuzzy word-based match — "
        "mirrors `differential_expression_by_gene`). Single-organism enforced. "
        "E.g. 'Prochlorococcus MED4'. `not_found.organism` is set when the "
        "name resolves to zero matching genes.",
        min_length=1,
    )],
    ec_numbers: Annotated[list[str] | None, Field(
        description="Narrow metabolism rows to those whose Reaction carries "
        "any of these EC numbers. **Metabolism arm only — does not affect "
        "transport rows**, which are returned unchanged. To restrict to "
        "metabolism rows alone, combine with `evidence_sources=['metabolism']`. "
        "E.g. ['6.3.1.2'] for glutamine synthetase.",
    )] = None,
    metabolite_pathway_ids: Annotated[list[str] | None, Field(
        description="Filter to rows where the **metabolite** is in any of "
        "these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] "
        "for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` "
        "(KG-A5 denorm, transport-extended), so applies uniformly to both "
        "arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway "
        "annotations, route through `genes_by_ontology(ontology=\"kegg\", "
        "term_ids=[pathway_id], organism=...)` first to obtain locus_tags. "
        "`not_found.metabolite_pathway_ids` lists IDs that don't exist as "
        "a KeggTerm.",
    )] = None,
    mass_balance: Annotated[Literal["balanced", "unbalanced"] | None, Field(
        description="Narrow metabolism rows to those whose Reaction has this "
        "mass balance status. **Metabolism arm only — does not affect "
        "transport rows**. Combine with `evidence_sources=['metabolism']` to "
        "restrict to metabolism rows alone.",
    )] = None,
    gene_categories: Annotated[list[str] | None, Field(
        description="Filter on `Gene.gene_category` (exact match, applies to "
        "both arms uniformly). Use `list_filter_values(filter_type=\"gene_category\")` "
        "to discover valid values.",
    )] = None,
    transport_confidence: Annotated[
        Literal["substrate_confirmed", "family_inferred"] | None,
        Field(
            description="Narrow transport rows by TCDB-annotation specificity. "
            "`substrate_confirmed` restricts transport rows to those annotated "
            "at TCDB `tc_specificity` (substrate-curated). `family_inferred` "
            "restricts to transport rows annotated at coarser TCDB levels "
            "(rolled up via the substrate edge). **Transport arm only — does "
            "not affect metabolism rows**, which are always substrate-"
            "confirmed by definition (direct catalysis edge) and carry "
            "`transport_confidence = None`. To restrict to transport rows "
            "alone, combine with `evidence_sources=['transport']`. "
            "**Recommended for high-precision transporter-hunting:** "
            "`transport_confidence='substrate_confirmed', "
            "evidence_sources=['transport']`.",
        ),
    ] = None,
    evidence_sources: Annotated[
        list[Literal["metabolism", "transport"]] | None,
        Field(
            description="Path selector — restricts which arms execute. "
            "Set to `['metabolism']` to skip transport entirely (no rollup "
            "noise); `['transport']` to skip metabolism. Default fires both "
            "arms. Note: `'metabolomics'` is NOT a valid value here — "
            "metabolomics evidence has no gene anchor and surfaces only in "
            "`list_metabolites`.",
        ),
    ] = None,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include extended fields per row: gene_category, "
        "metabolite_inchikey/smiles/mnxm_id/hmdb_id, reaction_mnxr_id/"
        "rhea_ids (metabolism rows), tcdb_level_kind/tc_class_id "
        "(transport rows).",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results. Default covers p75 of typical "
        "(metabolite × organism) UNION row distributions; coenzyme-tail "
        "queries (ATP, water) use `offset` to page.",
        ge=1,
    )] = 10,
    offset: Annotated[int, Field(
        description="Number of results to skip for pagination.", ge=0,
    )] = 0,
) -> GenesByMetaboliteResponse:
    """Find genes connected to specified metabolites in one organism.

    **Direction-agnostic.** Joins through `Reaction_has_metabolite` (metabolism)
    and `Tcdb_family_transports_metabolite` (transport) are direction-agnostic —
    a gene that *produces* a metabolite and a gene that *consumes* it surface
    identically. KEGG equation order is arbitrary. To distinguish, layer
    transcriptional evidence (`differential_expression_by_gene`) and gene
    functional annotation (`gene_overview` Pfam / KEGG KO names like
    `*-synthase` vs `*-permease`).

    **Transport-confidence semantics (transport arm only).** Transport rows
    ride a TCDB substrate-edge rollup that propagates leaf-curated substrates
    up the hierarchy. A `family_inferred` transport row means *the gene is
    annotated to a TCDB family that contains members curated as moving this
    metabolite* — not that this gene is curated as such. ABC Superfamily–level
    annotations make every ABC gene appear to "transport urea" through the
    rollup. Filter `transport_confidence='substrate_confirmed'` (paired with
    `evidence_sources=['transport']` if you want the transport arm in
    isolation) for the precise set; the default fires both arms and flags
    `family_inferred` in `warnings` when it dominates the result. Metabolism
    rows are not subject to this concern — direct catalysis edges are
    always substrate-confirmed — and their `transport_confidence` is None.

    **Evidence sources accepted here:** `metabolism`, `transport`. The
    metabolomics path (DerivedMetric → Metabolite) has no gene anchor and is
    not surfaced by gene-anchored chemistry tools — see `list_metabolites`.

    Drill-downs from result rows / envelope rollups:
    - Any `top_genes` entry → `differential_expression_by_gene(locus_tags=[...], organism=...)`
      for transcriptional response, or `gene_overview` for richer context.
    - Any `top_tcdb_families` entry → `genes_by_ontology(ontology="tcdb", term_ids=[id], organism=...)`
      for sibling genes in the same family.
    - Any `top_reactions` entry → `genes_by_ontology(ontology="ec", term_ids=[ec], organism=...)`
      for genes in adjacent reactions, or `pathway_enrichment` for context.
    """
```

### Return envelope

```python
class GenesByMetaboliteResponse(BaseModel):
    total_matching: int               # rows after all filters
    returned: int                     # rows in `results` (≤ limit)
    offset: int
    truncated: bool
    warnings: list[str]               # family_inferred-dominance auto-warning
    not_found: GbmNotFound            # {metabolite_ids, organism, metabolite_pathway_ids}
    not_matched: list[str]            # metabolite_ids in KG with no gene reach in this organism
    by_metabolite: list[GbmByMetabolite]              # full freq, bounded by input list
    by_evidence_source: list[GbmByEvidenceSource]     # full freq, ≤2 entries forever
    by_transport_confidence: list[GbmByTransportConfidence]   # full freq, transport rows only, ≤2 entries forever
    top_reactions: list[GbmTopReaction]               # top 10 (data-driven, often >15)
    top_tcdb_families: list[GbmTopTcdbFamily]         # top 10 (data-driven)
    top_gene_categories: list[GbmTopGeneCategory]     # top 10 (coenzymes can hit ~20)
    top_genes: list[GbmTopGene]                       # top 10 by reaction breadth
    gene_count_total: int
    reaction_count_total: int
    transporter_count_total: int
    metabolite_count_total: int
    results: list[GeneReactionMetaboliteTriplet]
```

**Naming convention (per `list_metabolites`):**

- `top_*` — hardcoded top-N (truncated; the list does NOT exhaust the matched set). Used when cardinality is often > 15.
- `by_*` — full frequency rollup (every distinct value present, sorted desc by count). Used when cardinality is bounded ≤ ~15.

### Per-row `GeneReactionMetaboliteTriplet` — compact

| Field | Type | Notes |
|---|---|---|
| `locus_tag` | str | gene identifier |
| `gene_name` | str \| None | sparse — null on most rows |
| `product` | str \| None | sparse — populated on most rows |
| `evidence_source` | Literal["metabolism","transport"] | per-row path discriminator |
| `transport_confidence` | Literal["substrate_confirmed","family_inferred"] \| None | sparse — None on metabolism rows; populated on transport rows only |
| `reaction_id` | str \| None | metabolism rows only |
| `reaction_name` | str \| None | metabolism rows only; may be empty `''` for 32 reactions |
| `ec_numbers` | list[str] \| None | metabolism rows only |
| `mass_balance` | Literal["balanced","unbalanced"] \| None | metabolism rows only |
| `tcdb_family_id` | str \| None | transport rows only — e.g. `tcdb:3.A.1.4.5` |
| `tcdb_family_name` | str \| None | transport rows only — falls back to `tcdb_id` for non-`tc_family` levels |
| `metabolite_id` | str | full prefixed |
| `metabolite_name` | str | |
| `metabolite_formula` | str \| None | sparse |
| `metabolite_mass` | float \| None | sparse |
| `metabolite_chebi_id` | str \| None | sparse |

### Verbose adds

| Field | Type | Notes |
|---|---|---|
| `gene_category` | str | per-gene category |
| `metabolite_inchikey` | str \| None | sparse |
| `metabolite_smiles` | str \| None | sparse |
| `metabolite_mnxm_id` | str \| None | always populated today |
| `metabolite_hmdb_id` | str \| None | sparse |
| `reaction_mnxr_id` | str \| None | metabolism rows; sparse |
| `reaction_rhea_ids` | list[str] \| None | metabolism rows; sparse |
| `tcdb_level_kind` | Literal[...] \| None | transport rows; one of tc_class/tc_subclass/tc_family/tc_subfamily/tc_specificity |
| `tc_class_id` | str \| None | transport rows; e.g. `tcdb:3` |

### Envelope row classes

All response models carry `Field(description=...)` so the JSON Schema
exposed to the LLM via MCP is self-documenting.

```python
class GbmByMetabolite(BaseModel):
    """Per-metabolite rollup. One entry per matched input metabolite_id.

    Cardinality bounded by the input list — kept as `by_*` (full rollup),
    not `top_*`.
    """
    metabolite_id: str = Field(
        description="Full prefixed Metabolite ID (e.g. 'kegg.compound:C00086').")
    name: str = Field(
        description="Metabolite display name (e.g. 'Urea').")
    formula: str | None = Field(
        description="Hill-notation formula (e.g. 'CH4N2O'); null on transport-"
        "only ChEBI generics (~9% of metabolites).")
    rows: int = Field(
        description="Total rows for this metabolite across both arms in the "
        "filtered slice.")
    gene_count: int = Field(
        description="Distinct genes touching this metabolite via either arm "
        "(deduplicated across metabolism and transport).")
    reaction_count: int = Field(
        description="Distinct Reactions (metabolism arm). 0 when the "
        "metabolite is reachable only via the transport arm.")
    transporter_count: int = Field(
        description="Distinct TcdbFamily nodes (transport arm). 0 when the "
        "metabolite is reachable only via the metabolism arm.")
    metabolism_rows: int = Field(
        description="Row count for the metabolism arm.")
    transport_substrate_confirmed_rows: int = Field(
        description="Row count for transport rows annotated at TCDB "
        "`tc_specificity` (substrate-curated). High-precision transport "
        "evidence.")
    transport_family_inferred_rows: int = Field(
        description="Row count for transport rows annotated at coarser TCDB "
        "levels (rolled up via the substrate edge). Lower-precision — the "
        "gene's actual substrate may differ.")


class GbmByEvidenceSource(BaseModel):
    """Frequency rollup over `evidence_source` values present in the slice.

    ≤2 entries — `metabolism` and/or `transport`. (Metabolomics has no gene
    anchor and never produces rows here.)
    """
    evidence_source: Literal["metabolism", "transport"] = Field(
        description="Path through which the gene reaches the metabolite.")
    count: int = Field(
        description="Row count for this evidence_source in the filtered slice.")


class GbmByTransportConfidence(BaseModel):
    """Frequency rollup over `transport_confidence` for transport rows only.

    ≤2 entries — `substrate_confirmed` and/or `family_inferred`. Metabolism
    rows are excluded from this rollup (their `transport_confidence` is None).
    """
    transport_confidence: Literal["substrate_confirmed", "family_inferred"] = Field(
        description="TCDB-annotation specificity behind the transport edge. "
        "`substrate_confirmed` = annotated at `tc_specificity` (leaf, "
        "substrate-curated). `family_inferred` = annotated at a coarser "
        "TCDB level (rolled up; gene may not move this metabolite).")
    count: int = Field(
        description="Transport-row count for this confidence level in the "
        "filtered slice.")


class GbmTopReaction(BaseModel):
    """Top-N (truncated to 10) reactions by gene count in the filtered slice."""
    reaction_id: str = Field(
        description="Full prefixed Reaction ID (e.g. 'kegg.reaction:R00253').")
    name: str = Field(
        description="Reaction systematic name + KEGG equation (raw KEGG; may "
        "be empty `''` for 32 reactions in the KG).")
    ec_numbers: list[str] = Field(
        description="EC classification(s) for this reaction; empty list for "
        "107/2,349 reactions without EC annotation.")
    gene_count: int = Field(
        description="Distinct genes catalyzing this reaction in the filtered "
        "slice.")
    metabolite_count: int = Field(
        description="Distinct input metabolites this reaction connects to "
        "(useful when batch-querying multiple metabolite_ids).")


class GbmTopTcdbFamily(BaseModel):
    """Top-N (truncated to 10) TCDB families by gene count in transport rows."""
    tcdb_family_id: str = Field(
        description="Full prefixed TcdbFamily ID (e.g. 'tcdb:3.A.1.4.5').")
    tcdb_family_name: str = Field(
        description="Display name. For tc_family-level entries (~10 in the "
        "KG) this is human-readable (e.g. 'The ATP-binding Cassette (ABC) "
        "Superfamily'); for tc_subfamily / tc_specificity levels it falls "
        "back to the `tcdb_id` value.")
    level_kind: str = Field(
        description="One of tc_class / tc_subclass / tc_family / "
        "tc_subfamily / tc_specificity. Determines `transport_confidence`.")
    transport_confidence: Literal["substrate_confirmed", "family_inferred"] = Field(
        description="Derived from level_kind: 'substrate_confirmed' iff "
        "level_kind == 'tc_specificity'. Pre-computed for at-a-glance "
        "filtering of the rollup.")
    gene_count: int = Field(
        description="Distinct genes annotated to this TCDB family in the "
        "filtered transport-row slice.")
    metabolite_count: int = Field(
        description="Distinct input metabolites this family transports.")


class GbmTopGeneCategory(BaseModel):
    """Top-N (truncated to 10) `Gene.gene_category` values by gene count."""
    category: str = Field(
        description="One of the curated Gene.gene_category values (use "
        "`list_filter_values(filter_type=\"gene_category\")` for valid set).")
    gene_count: int = Field(
        description="Distinct genes in this category contributing rows in "
        "the filtered slice.")


class GbmTopGene(BaseModel):
    """Top-N (truncated to 10) genes ranked by total reaction + transporter "
    breadth in the filtered slice. The gene-level rollup useful for picking
    candidate genes to drill into via `differential_expression_by_gene` /
    `gene_overview`.
    """
    locus_tag: str = Field(
        description="Gene locus tag (e.g. 'PMM0974').")
    gene_name: str | None = Field(
        description="Curated gene name (e.g. 'urtE'); often null.")
    reaction_count: int = Field(
        description="Distinct reactions this gene catalyzes in the filtered "
        "metabolism-arm slice.")
    transporter_count: int = Field(
        description="Distinct TCDB families this gene is annotated to in the "
        "filtered transport-arm slice.")
    metabolite_count: int = Field(
        description="Distinct input metabolites this gene reaches via either "
        "arm.")
    metabolism_rows: int = Field(
        description="Metabolism-arm row count for this gene.")
    transport_substrate_confirmed_rows: int = Field(
        description="Transport-arm row count for this gene at "
        "`tc_specificity` level (high-precision).")
    transport_family_inferred_rows: int = Field(
        description="Transport-arm row count for this gene at coarser TCDB "
        "levels (rolled up via the substrate edge; lower-precision).")


class GbmNotFound(BaseModel):
    """Diagnostics for inputs that did not resolve to any KG node.

    See also `not_matched` (top-level field on the response): metabolite_ids
    that DO resolve to a Metabolite node but produce zero rows in the
    requested organism slice — different concept.
    """
    metabolite_ids: list[str] = Field(
        description="Input metabolite_ids that don't exist as a Metabolite "
        "node (e.g. typo, wrong prefix, ChEBI ID not in our KG).")
    organism: str | None = Field(
        description="Set to the input string when the fuzzy-match resolves "
        "to zero genes (typo, unsupported strain). None on success.")
    metabolite_pathway_ids: list[str] = Field(
        description="Input metabolite_pathway_ids that don't exist as a "
        "KeggTerm node.")
```

## Result-size controls

`summary` / `verbose` / `limit=10` / `offset=0` mirror `list_metabolites`
exactly except for the default `limit`. Default `limit=10` chosen based on
the live UNION row distribution probe:

| Slice | rows |
|---|---|
| p50 | 3 |
| **p75 (covered by `limit=10`)** | **9** |
| p90 | 13 |
| p95 | 15 |
| p99 | 55 |

Most calls land at p50–p75 (1 metabolite × 1 organism); coenzyme tail
(ATP, phosphate, water — p99+) requires offset paging. Bumping default to
15 would cover p90 but inflate the typical-call payload by 50% with no
biological gain.

**Sort key:** `metabolite_id, evidence_source, transport_confidence_priority, secondary_id, locus_tag`

where `transport_confidence_priority`:
- `0` if `transport_confidence == 'substrate_confirmed'`
- `1` if `transport_confidence == 'family_inferred'`
- `0` if `transport_confidence IS NULL` (metabolism rows — sort doesn't differentiate within metabolism)

Effect: within each metabolite, metabolism rows come first (alphabetical
`'metabolism' < 'transport'`); within transport rows, substrate-confirmed
rows come before family-inferred. **Truncation by `limit` preferentially
drops `family_inferred` transport rows**, so the LLM sees high-precision
rows first even without filtering.

`secondary_id` is `r.id` for metabolism rows and `tf.id` for transport rows —
deterministic tiebreaker within a (metabolite, evidence_source, transport_confidence_priority) group.

## Special handling

- **Two-arm `MATCH` architecture.** Detail Cypher emits two separate `MATCH`
  blocks (one per arm), each with its own filter conditions, joined via
  the API layer (`api/functions.py`) which concatenates row lists and
  applies the global sort + limit + offset. **No `UNION` inside the detail
  Cypher** — different arms have different RETURN columns, and a unified
  RETURN of nullable columns adds Cypher complexity for no gain over
  api-side concat.

- **Per-arm filter scope.** Each filter narrows only the arm it applies
  to; the other arm runs unfiltered. To restrict the result set to a
  single arm, set `evidence_sources` explicitly. Concretely:

  | Filter | Scope | Effect on the OTHER arm |
  |---|---|---|
  | `ec_numbers` | metabolism arm WHERE | transport rows returned unchanged |
  | `mass_balance` | metabolism arm WHERE | transport rows returned unchanged |
  | `transport_confidence` | transport arm WHERE | metabolism rows returned unchanged |
  | `metabolite_pathway_ids` | both arms (via `m.pathway_ids`) | both narrowed uniformly |
  | `gene_categories` | both arms (`g.gene_category`) | both narrowed uniformly |
  | `evidence_sources` | path selector — suppresses arms not in the list | n/a |

  **No soft-exclude warnings.** The previous draft's auto-suppression of
  the transport arm when `ec_numbers` or `mass_balance` was set has been
  removed. Filters never silently drop the other arm's rows; if the
  caller wants a single arm, they say so via `evidence_sources`.

- **Auto-warning: family-inferred dominance (transport only).** After
  collecting rows, if **transport rows are present in the result set**
  AND `transport_family_inferred_rows > transport_substrate_confirmed_rows`
  AND the user did not explicitly set `transport_confidence`:

  ```
  warnings.append(
    "Majority of transport rows are family_inferred (rolled-up from broad "
    "TCDB families). Re-run with transport_confidence='substrate_confirmed' "
    "for substrate-curated transporter genes only."
  )
  ```

  Strict majority threshold avoids noise. Comparison is **within transport
  rows only** — metabolism row count does not factor in.

- **`not_found` vs `not_matched` discrimination:**
  - `not_found.metabolite_ids`: IDs that resolve to no `Metabolite` node
    (verified via UNWIND + OPTIONAL MATCH on m).
  - `not_matched`: IDs whose Metabolite exists but produces zero rows in
    this organism via either arm under the active filters. Computed in
    api/ from the difference (input - found - returned-IDs-in-results).
  - `not_found.organism`: set to the input string when no matching gene
    exists for `g.organism_name` under the fuzzy match.
  - `not_found.metabolite_pathway_ids`: IDs that resolve to no `KeggTerm` node.

- **Pathway filter via `m.pathway_ids` denorm.** `ANY(p IN $metabolite_pathway_ids
  WHERE p IN coalesce(m.pathway_ids, []))` — single property check,
  uniform across arms. No edge traversal at query time.

- **Organism match: fuzzy word-based** (mirrors DE):
  ```cypher
  ALL(word IN split(toLower($organism), ' ')
      WHERE toLower(g.organism_name) CONTAINS word)
  ```
  Tolerant of case and spacing variation (e.g. `'med4'`, `'Prochlorococcus med4'`,
  `'prochlorococcus MED4'` all match).

- **Empty `r.name` handling.** `reaction_name` surfaces the raw value
  (empty string `''` for 32 reactions in the KG). No envelope-level
  diagnostic — gene→metabolite is the tool's focus, reaction-name nullness
  is a niche reaction-side detail.

- **TCDB family name fallback** (KG-side): `tf.name == tf.tcdb_id` for
  `tc_subfamily` / `tc_specificity` levels. `tcdb_family_name` field
  carries whatever the KG holds — no tool-side normalization.

- **`coalesce(...)` defensive on rollup props:**
  - `coalesce(m.pathway_ids, [])` — defensive against pre-rebuild rows.
  - `coalesce(m.elements, [])` — analogous (verbose path).

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `_genes_by_metabolite_metabolism_where()` and `_genes_by_metabolite_transport_where()` shared helpers; `build_genes_by_metabolite_metabolism()`, `build_genes_by_metabolite_transport()` (detail per arm); `build_genes_by_metabolite_summary()` (single-pass envelope rollup). |
| 2 | API function | `api/functions.py` | `genes_by_metabolite()`. Decides which arms to fire from `evidence_sources` only (single-arm mode); applies path-scoped filters per arm independently; concatenates arm result lists; computes `not_found` / `not_matched`; computes `top_*` and `by_*` rollups from the summary builder; emits the family-inferred-dominance `warnings` entry when applicable. |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add `genes_by_metabolite` to imports + `__all__`. |
| 4 | MCP wrapper | `mcp_server/tools.py` | Pydantic models: `GeneReactionMetaboliteTriplet` (shared with `metabolites_by_gene`), `GenesByMetaboliteResponse`, `GbmByMetabolite`, `GbmByEvidenceSource`, `GbmByTransportConfidence`, `GbmTopReaction`, `GbmTopTcdbFamily`, `GbmTopGeneCategory`, `GbmTopGene`, `GbmNotFound`. `@mcp.tool` wrapper. Update `EXPECTED_TOOLS`. |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuildGenesByMetaboliteMetabolism`, `TestBuildGenesByMetaboliteTransport`, `TestBuildGenesByMetaboliteSummary`. |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | `TestGenesByMetabolite` — mocked-conn fixtures; covers single-arm vs both-arm modes (driven by `evidence_sources`), per-arm filter scoping (e.g. `ec_numbers` narrows metabolism while transport rows stay unfiltered), family-inferred-dominance warning trigger (transport-only check), `not_found`/`not_matched` discrimination, `transport_confidence` filter behavior. |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestGenesByMetaboliteWrapper`. Update `EXPECTED_TOOLS`. |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Live-KG smoke (urea × MED4 — covers both arms + both transport_confidence levels). |
| 8b | Integration | `tests/integration/test_api_contract.py` | `TestGenesByMetaboliteContract`. |
| 9 | Regression | `tests/regression/test_regression.py` + `tests/evals/test_eval.py` | Add `genes_by_metabolite: build_genes_by_metabolite_metabolism` (or composite key) to both `TOOL_BUILDERS` dicts. **Use small `limit` (≤5) on baseline snapshots** — list_metabolites's initial unbounded baselines hit ~59k lines and were re-capped post-merge (commit 7eed712). Snapshot fixtures stay under ~1k lines each. |
| 10 | Eval cases | `tests/evals/cases.yaml` | 5–7 cases (urea / glutamine / nitrite single-org; mixed metabolism+transport; transport_confidence='substrate_confirmed' + evidence_sources=['transport']; ec_numbers narrowing metabolism while transport unaffected; mixed found/not_found IDs; metabolite_pathway_ids filter). |
| 11 | About content | `multiomics_explorer/inputs/tools/genes_by_metabolite.yaml` | examples + chaining + mistakes; run `build_about_content.py`. |
| 12 | Docs | `CLAUDE.md` | Add `genes_by_metabolite` row to MCP tool table; update `gene_overview` row's drill-down clause to point here when chemistry counts are non-zero. |

---

## Query Builder

**File:** `kg/queries_lib.py`

### Shared `_genes_by_metabolite_metabolism_where()`

```python
def _genes_by_metabolite_metabolism_where(
    *,
    metabolite_ids: list[str],
    organism: str,
    ec_numbers: list[str] | None = None,
    mass_balance: str | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params for the metabolism arm.

    `transport_confidence` is not accepted here — it is a transport-arm
    filter and the metabolism arm is unaffected by it (per the per-arm
    filter scope rule in 'Special handling').
    """
```

WHERE fragments (metabolism arm):

| Filter | Fragment |
|---|---|
| organism (fuzzy) | `ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_name) CONTAINS word)` |
| `metabolite_ids` | `m.id IN $metabolite_ids` |
| `ec_numbers` | `ANY(ec IN $ec_numbers WHERE ec IN coalesce(r.ec_numbers, []))` |
| `mass_balance` | `r.mass_balance = $mass_balance` |
| `metabolite_pathway_ids` | `ANY(p IN $metabolite_pathway_ids WHERE p IN coalesce(m.pathway_ids, []))` |
| `gene_categories` | `g.gene_category IN $gene_categories` |

### Shared `_genes_by_metabolite_transport_where()`

```python
def _genes_by_metabolite_transport_where(
    *,
    metabolite_ids: list[str],
    organism: str,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    transport_confidence: str | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params for the transport arm.

    `ec_numbers` / `mass_balance` are not accepted here — they are
    metabolism-arm filters and the transport arm is unaffected by them.
    `transport_confidence='substrate_confirmed'` adds `tf.level_kind = 'tc_specificity'`.
    `transport_confidence='family_inferred'` adds `tf.level_kind <> 'tc_specificity'`.
    """
```

WHERE fragments (transport arm):

| Filter | Fragment |
|---|---|
| organism (fuzzy) | (same as metabolism) |
| `metabolite_ids` | `m.id IN $metabolite_ids` |
| `metabolite_pathway_ids` | `ANY(p IN $metabolite_pathway_ids WHERE p IN coalesce(m.pathway_ids, []))` |
| `gene_categories` | `g.gene_category IN $gene_categories` |
| `transport_confidence='substrate_confirmed'` | `tf.level_kind = 'tc_specificity'` |
| `transport_confidence='family_inferred'` | `tf.level_kind <> 'tc_specificity'` |

### `build_genes_by_metabolite_metabolism` (detail)

```python
def build_genes_by_metabolite_metabolism(
    *,
    metabolite_ids: list[str],
    organism: str,
    ec_numbers: list[str] | None = None,
    mass_balance: str | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,           # api/ may pass None and apply limit after concat
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for the metabolism arm of genes_by_metabolite.

    RETURN keys (compact, 13): locus_tag, gene_name, product,
    evidence_source ('metabolism'), transport_confidence (always null),
    reaction_id, reaction_name, ec_numbers, mass_balance,
    metabolite_id, metabolite_name, metabolite_formula, metabolite_mass,
    metabolite_chebi_id.
    Verbose adds: gene_category, metabolite_inchikey, metabolite_smiles,
    metabolite_mnxm_id, metabolite_hmdb_id, reaction_mnxr_id,
    reaction_rhea_ids.
    """
```

Cypher shape (metabolism arm):

```cypher
MATCH (g:Gene)-[:Gene_catalyzes_reaction]->(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)
WHERE <conditions>
RETURN g.locus_tag AS locus_tag,
       g.gene_name AS gene_name,
       g.product AS product,
       'metabolism' AS evidence_source,
       null AS transport_confidence,
       r.id AS reaction_id,
       r.name AS reaction_name,
       coalesce(r.ec_numbers, []) AS ec_numbers,
       r.mass_balance AS mass_balance,
       null AS tcdb_family_id,
       null AS tcdb_family_name,
       m.id AS metabolite_id,
       m.name AS metabolite_name,
       m.formula AS metabolite_formula,
       m.mass AS metabolite_mass,
       m.chebi_id AS metabolite_chebi_id
       <verbose_cols>
ORDER BY metabolite_id, reaction_id, locus_tag
SKIP $offset LIMIT $limit
```

Verbose tail (metabolism arm):
```cypher
,
g.gene_category AS gene_category,
m.inchikey AS metabolite_inchikey,
m.smiles AS metabolite_smiles,
m.mnxm_id AS metabolite_mnxm_id,
m.hmdb_id AS metabolite_hmdb_id,
r.mnxr_id AS reaction_mnxr_id,
r.rhea_ids AS reaction_rhea_ids,
null AS tcdb_level_kind,
null AS tc_class_id
```

### `build_genes_by_metabolite_transport` (detail)

```python
def build_genes_by_metabolite_transport(
    *,
    metabolite_ids: list[str],
    organism: str,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    transport_confidence: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for the transport arm of genes_by_metabolite.

    RETURN keys (compact, 13): locus_tag, gene_name, product,
    evidence_source ('transport'), transport_confidence (derived from level_kind),
    null reaction_*/ec_numbers/mass_balance,
    tcdb_family_id, tcdb_family_name,
    metabolite_id, metabolite_name, metabolite_formula, metabolite_mass,
    metabolite_chebi_id.
    Verbose adds: gene_category, metabolite_inchikey, metabolite_smiles,
    metabolite_mnxm_id, metabolite_hmdb_id, tcdb_level_kind, tc_class_id.
    """
```

Cypher shape (transport arm):

```cypher
MATCH (g:Gene)-[:Gene_has_tcdb_family]->(tf:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)
WHERE <conditions>
RETURN g.locus_tag AS locus_tag,
       g.gene_name AS gene_name,
       g.product AS product,
       'transport' AS evidence_source,
       CASE WHEN tf.level_kind = 'tc_specificity'
            THEN 'substrate_confirmed' ELSE 'family_inferred' END AS transport_confidence,
       null AS reaction_id,
       null AS reaction_name,
       null AS ec_numbers,
       null AS mass_balance,
       tf.id AS tcdb_family_id,
       tf.name AS tcdb_family_name,
       m.id AS metabolite_id,
       m.name AS metabolite_name,
       m.formula AS metabolite_formula,
       m.mass AS metabolite_mass,
       m.chebi_id AS metabolite_chebi_id
       <verbose_cols>
ORDER BY metabolite_id,
         CASE WHEN tf.level_kind = 'tc_specificity' THEN 0 ELSE 1 END,
         tcdb_family_id, locus_tag
SKIP $offset LIMIT $limit
```

Verbose tail (transport arm):
```cypher
,
g.gene_category AS gene_category,
m.inchikey AS metabolite_inchikey,
m.smiles AS metabolite_smiles,
m.mnxm_id AS metabolite_mnxm_id,
m.hmdb_id AS metabolite_hmdb_id,
null AS reaction_mnxr_id,
null AS reaction_rhea_ids,
tf.level_kind AS tcdb_level_kind,
tf.tc_class_id AS tc_class_id
```

### Limit / offset strategy across arms

Three operating modes the api/ layer chooses between:

**Mode 1 — single-arm fired.** Triggered **only** by `evidence_sources`
restricting to one arm. Path-scoped filters (`ec_numbers`, `mass_balance`,
`transport_confidence`) narrow their own arm but do not trigger Mode 1 —
the other arm still runs unfiltered. Action: pass `limit` + `offset`
directly into the single Cypher arm. Fully deterministic, no api-side
slicing.

**Mode 2 — `summary=True`.** Skip detail builders entirely. Only the
aggregation Cypher runs.

**Mode 3 — both arms fire, detail mode.** This is the subtle case.

Why per-arm Cypher offset would be wrong: each arm's Cypher only sees its
own rows. If `offset=10` and arm 1 has 8 rows total, applying offset=10
to arm 1's Cypher returns nothing while we should be drawing from arm 2
— but arm 2 with offset=10 would skip its first 10 rows that should have
been returned. The arms are unaware of each other's row counts at Cypher
time. **The api/ layer is the only place with the global view.**

Why over-fetching `limit + offset` per arm is correct: the per-arm
`ORDER BY` shares its leading column (`metabolite_id`) with the global
sort. Within a single (metabolite_id, evidence_source) group, only one
arm contributes — there is no interleaving between metabolism and transport
rows within a metabolite. Combined with `evidence_source` ordering
('metabolism' < 'transport' alphabetically), this means: **for any global
position p, the first p rows in global-sorted order are a prefix of
(arm1 ∪ arm2)** as long as each arm has surfaced its first p rows in
per-arm order. Fetching `limit + offset` from each arm guarantees that
prefix exists in the concatenation; api/ then re-sorts and slices.

Algorithm:

```python
per_arm_fetch = limit + offset
arm1_rows = run(metabolism_cypher, limit=per_arm_fetch, offset=0)
arm2_rows = run(transport_cypher,  limit=per_arm_fetch, offset=0)
combined = arm1_rows + arm2_rows
combined.sort(key=global_sort_key)
results = combined[offset : offset + limit]
truncated = (offset + limit) < total_matching   # total_matching from summary builder
```

**Deep-paging guardrail.** Before either Cypher fires, api/ checks
`offset >= total_matching` (cheap — `total_matching` comes from the
summary builder which always runs). If true, short-circuits to empty
`results` + `truncated=False` without touching the detail arms.

**Over-fetch worst case.** `2 × (limit + offset)`. Bounded by data: at
the live p99 = 55 rows per (metabolite × organism), batch of 30
metabolite_ids puts the absolute ceiling at ~30 × 55 = 1,650 rows per
arm. Cheap on the wire. Practical typical case (`limit=10`, `offset=0`):
≤ 20 rows fetched.

### `build_genes_by_metabolite_summary` (envelope)

```python
def build_genes_by_metabolite_summary(
    *,
    metabolite_ids: list[str],
    organism: str,
    ec_numbers: list[str] | None = None,
    mass_balance: str | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    transport_confidence: str | None = None,
    arms: tuple[str, ...] = ("metabolism", "transport"),
) -> tuple[str, dict]:
    """Build single-pass aggregation Cypher.

    Per-arm filter scope (matches detail builders): `ec_numbers` and
    `mass_balance` apply only to the metabolism arm of the UNION;
    `transport_confidence` applies only to the transport arm;
    `metabolite_pathway_ids` and `gene_categories` apply to both arms.

    RETURN keys: total_matching, gene_count_total, reaction_count_total,
    transporter_count_total, metabolite_count_total,
    rows_by_evidence_source (apoc-frequencies long format, ≤2 entries),
    rows_by_transport_confidence (long format, transport rows only, ≤2 entries),
    by_metabolite (apoc-collected list of {metabolite_id, name, formula,
       rows, gene_count, reaction_count, transporter_count,
       metabolism_rows, transport_substrate_confirmed_rows,
       transport_family_inferred_rows}),
    top_reactions (apoc-collected, top 10 by gene_count),
    top_tcdb_families (apoc-collected, top 10 by gene_count),
    top_gene_categories (apoc-collected, top 10 by gene_count),
    top_genes (apoc-collected, top 10 by combined reaction + transporter breadth).
    """
```

Cypher shape — aggregates across both arms with shared reduction:

```cypher
// Compose row stream as UNION inside a CALL (different RETURN columns
// — use null-padding to align). Aggregation runs once over the union.
CALL {
  // metabolism arm rows (filter scope: ec_numbers, mass_balance, metabolite_pathway_ids, gene_categories)
  MATCH (g:Gene)-[:Gene_catalyzes_reaction]->(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)
  WHERE <metabolism conditions>
  RETURN g, r, null AS tf, m, 'metabolism' AS es, null AS tconf
  UNION
  // transport arm rows (filter scope: transport_confidence, metabolite_pathway_ids, gene_categories)
  MATCH (g:Gene)-[:Gene_has_tcdb_family]->(tf:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)
  WHERE <transport conditions>
  RETURN g, null AS r, tf, m, 'transport' AS es,
         CASE WHEN tf.level_kind = 'tc_specificity'
              THEN 'substrate_confirmed' ELSE 'family_inferred' END AS tconf
}
WITH g, r, tf, m, es, tconf
// global aggregates
WITH count(*) AS total_matching,
     count(DISTINCT g) AS gene_count_total,
     count(DISTINCT r) AS reaction_count_total,
     count(DISTINCT tf) AS transporter_count_total,
     count(DISTINCT m) AS metabolite_count_total,
     collect({g: g, r: r, tf: tf, m: m, es: es, tconf: tconf}) AS rows
// per-evidence-source frequency
WITH total_matching, gene_count_total, reaction_count_total,
     transporter_count_total, metabolite_count_total, rows,
     [es IN apoc.coll.toSet([row IN rows | row.es]) |
        {evidence_source: es, count: size([row IN rows WHERE row.es=es])}] AS rows_by_evidence_source,
     // transport-only confidence rollup — metabolism rows excluded (their tconf is null)
     [tc IN apoc.coll.toSet([row IN rows WHERE row.tconf IS NOT NULL | row.tconf]) |
        {transport_confidence: tc,
         count: size([row IN rows WHERE row.tconf=tc])}] AS rows_by_transport_confidence
// by_metabolite (per-metabolite expansion with metabolism_rows /
// transport_substrate_confirmed_rows / transport_family_inferred_rows)
WITH ..., apoc.coll.toSet([row IN rows | row.m.id]) AS distinct_mids,
     [...] AS by_metabolite
// top_reactions
WITH ..., apoc.coll.frequenciesBy([row IN rows WHERE row.r IS NOT NULL | row.r.id])[..10] AS top_reactions
// ... similarly for top_tcdb_families, top_gene_categories, top_genes
RETURN total_matching, gene_count_total, reaction_count_total,
       transporter_count_total, metabolite_count_total,
       rows_by_evidence_source, rows_by_transport_confidence,
       by_metabolite, top_reactions, top_tcdb_families,
       top_gene_categories, top_genes
```

> The summary Cypher is sketched; the api/ layer may move some apoc.coll
> rollups into Python where it's cheaper / clearer. Phase 2 implementer
> decides; the contract is the RETURN keys and their semantics.

### KG verification

| Probe | Expected | Verified live (2026-05-03) |
|---|---|---|
| Metabolism arm rows: glutamine × MED4 | 32 | **32** ✓ |
| Metabolism arm rows: urea × MED4 | 4 | **4** ✓ |
| Transport arm rows (rollup): urea × MED4 | 19 (10 substrate_confirmed rows + 9 family_inferred rows) | **19 (10 + 9)** ✓ |
| Transport arm rows: nitrite × MED4 | 14 (5 substrate_confirmed + 9 family_inferred) | **14 (5 + 9)** ✓ |
| Combined rows: urea+glutamine+nitrite × MED4 | 79 (36 metabolism + 43 transport: 15 sc + 28 fi) | **79 (36 / 43 / 15 / 28)** ✓ |
| Per-metabolite gene_count (urea × MED4) | 18 distinct genes (4 metabolism arm distinct genes + 14 distinct transport genes, no overlap) | **18 (4 + 14)** ✓ |
| `not_found` discrimination: chebi:9314 (sucrose) | true (not in KG) | **true** ✓ |
| `not_matched`: kegg.compound:C00069 (alcohol) × Alteromonas ATCC27126 | true (Metabolite node exists; no gene reach via either arm) | **true** ✓ (water/C00001 was the original probe but turned out to have 770 reachable rows — Alteromonas ATCC27126 catalyzes 333 water-touching reactions; spec drift discovered during Phase 2 build, swapped to alcohol which is genuinely unreachable) |
| Filter narrow: metabolite_pathway_ids=['kegg.pathway:ko00910'] reduces 79 → 56 | yes | **56** ✓ |
| Filter narrow: gene_categories=['Transport'] reduces 79 → 15 | yes | **15** ✓ |
| Filter narrow: ec_numbers=['6.3.1.2'] (glutamine synthetase) → 1 row | yes (glnA × glutamine) | **1** ✓ |
| Filter narrow: mass_balance='unbalanced' → 0 (slice has no unbalanced reactions) | yes | **0** ✓ |
| `tf.level_kind` distribution on MED4 transport: tc_family 89% / tc_subfamily 10% / tc_specificity 1% | matches earlier verification | **5,045 / 576 / 54** ✓ |

---

## API Function

**File:** `api/functions.py`

```python
def genes_by_metabolite(
    metabolite_ids: list[str],
    organism: str,
    *,
    ec_numbers: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    mass_balance: str | None = None,
    gene_categories: list[str] | None = None,
    transport_confidence: str | None = None,
    evidence_sources: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int = 10,
    offset: int = 0,
) -> dict:
    """Find genes connected to specified metabolites in one organism.

    See spec at docs/tool-specs/genes_by_metabolite.md.
    """
```

API responsibilities (orchestration logic on top of the query builders):

1. **Defense-in-depth input validation** (matches `list_metabolites`
   precedent — protects direct-to-api callers from CLI / Python that
   bypass the MCP-boundary Pydantic Literal). Module-level constant:

   ```python
   _VALID_EVIDENCE_SOURCES = ("metabolism", "transport")
   ```

   At function entry, validate `evidence_sources` membership:

   ```python
   if evidence_sources is not None:
       invalid = [s for s in evidence_sources if s not in _VALID_EVIDENCE_SOURCES]
       if invalid:
           raise ValueError(
               f"evidence_sources contains invalid value(s) {invalid}; "
               f"allowed: {list(_VALID_EVIDENCE_SOURCES)}."
           )
   ```

   **Note:** the value tuple **diverges from `list_metabolites`'s**
   `("metabolism", "transport", "metabolomics")` — see Resolved section.
   Same validator pattern, different value set.

2. **Arm selection** is determined **only** by `evidence_sources`. Path-scoped
   filters (`ec_numbers` / `mass_balance` / `transport_confidence`) narrow
   their own arm; they do not suppress the other arm. Concretely:
   - `evidence_sources` unset → both arms fire.
   - `evidence_sources=['metabolism']` → only metabolism arm fires.
   - `evidence_sources=['transport']` → only transport arm fires.
3. **Per-arm filter dispatch:**
   - Metabolism arm builder receives `metabolite_ids`, `organism`,
     `ec_numbers`, `mass_balance`, `metabolite_pathway_ids`, `gene_categories`.
   - Transport arm builder receives `metabolite_ids`, `organism`,
     `metabolite_pathway_ids`, `gene_categories`, `transport_confidence`.
4. **Run summary builder** (always; even `summary=False` needs envelope rollups).
5. **If `summary=False`**: run detail builder per active arm, concat results,
   apply global sort, slice `[offset : offset + limit]` (see paging
   strategy section above).
6. **Compute `not_found`:**
   - `not_found.metabolite_ids` ← input metabolite_ids that don't resolve to
     a `Metabolite` node (separate UNWIND-existence query — distinct from
     "no rows returned" which is `not_matched`).
   - `not_found.organism` ← `organism` if `gene_count_total == 0`, else `None`.
   - `not_found.metabolite_pathway_ids` ← input pathway_ids that don't resolve to a
     `KeggTerm` node.
7. **Compute `not_matched`:** input metabolite_ids that exist as Metabolite
   nodes but produced zero rows in this organism slice. Equals
   `(input - not_found.metabolite_ids) - <metabolite_ids present in summary `by_metabolite`>`.
8. **Auto-warning: family-inferred dominance** (transport-only check). If
   transport rows exist in the result set AND
   `transport_family_inferred_rows > transport_substrate_confirmed_rows`
   AND the user did not set `transport_confidence`, append:
   `"Majority of transport rows are family_inferred (rolled-up from broad TCDB families). Re-run with transport_confidence='substrate_confirmed' for substrate-curated transporter genes only."`
   Strict majority threshold; metabolism rows do not factor in.
9. **Sparse-strip nullable result columns** when null (gene_name, product,
   chebi_id, mass, formula, plus all per-arm-specific fields on rows from
   the other arm — `reaction_*` / `ec_numbers` / `mass_balance` on
   transport rows; `tcdb_family_*` / `transport_confidence` on metabolism
   rows).

## MCP Wrapper

**File:** `mcp_server/tools.py`

### Pydantic naming convention: `Gbm*` (tool-anchored)

This tool's envelope sub-models use a **tool-anchored prefix** (`Gbm` =
"GenesByMetabolite") rather than the entity-anchored `Met*` prefix used
by sibling `list_metabolites`. Reason: this tool's envelope mixes entity
types (metabolite-anchored `by_metabolite`, reaction-anchored
`top_reactions`, TCDB-anchored `top_tcdb_families`, gene-anchored
`top_genes`, etc.). No single entity prefix covers all of them; mixing
prefixes would be inconsistent within a single tool's response. Tool-
anchored is the principled choice for mixed-entity envelopes.

`list_metabolites` keeps `Met*` because every sub-model there is
metabolite-anchored — the entity prefix fits naturally. Both tools follow
the same underlying rule (use the prefix that uniformly covers the tool's
envelope); they diverge only because their envelopes have different
shapes.

The shared row class `GeneReactionMetaboliteTriplet` keeps its
descriptive name (no `Gbm*` prefix) — it's reused by `metabolites_by_gene`
(Tool 3) and naming it after either tool would suggest false ownership.

### Pydantic models

```python
class GeneReactionMetaboliteTriplet(BaseModel):
    """Shared row class with metabolites_by_gene (Tool 3).

    Compact mode: 15 fields including evidence_source +
    transport_confidence. Verbose mode adds 9 more. All per-arm-specific
    fields are Optional and sparse-stripped at the api/ layer when null.
    """
    locus_tag: str = Field(
        description="Gene locus tag (e.g. 'PMM0974' for MED4 urtE).")
    gene_name: str | None = Field(
        description="Curated gene name (e.g. 'urtE'); often null.")
    product: str | None = Field(
        description="Annotated gene product description (high-signal short "
        "label, e.g. 'ABC-type urea transporter, ATPase component UrtE').")

    evidence_source: Literal["metabolism", "transport"] = Field(
        description="Path through which this row reaches the metabolite. "
        "'metabolism' = `Gene → Reaction → Metabolite`. 'transport' = "
        "`Gene → TcdbFamily → Metabolite` (rollup-extended). Metabolomics "
        "evidence has no gene anchor and never produces rows here.")
    transport_confidence: Literal["substrate_confirmed", "family_inferred"] | None = Field(
        description="Set on transport rows only. 'substrate_confirmed' = "
        "the TCDB family annotation is at `tc_specificity` level "
        "(substrate-curated). 'family_inferred' = annotation is at a "
        "coarser TCDB level (rolled up via the substrate edge — gene may "
        "or may not move this metabolite). None on metabolism rows "
        "(direct catalysis edge is always substrate-confirmed by definition).")

    # metabolism-arm fields (None on transport rows)
    reaction_id: str | None = Field(
        description="Full prefixed Reaction ID (e.g. 'kegg.reaction:R00253'). "
        "Metabolism rows only.")
    reaction_name: str | None = Field(
        description="Reaction systematic name + KEGG equation (raw KEGG "
        "value, can be lengthy; ~32 reactions in the KG have empty `''`). "
        "Metabolism rows only.")
    ec_numbers: list[str] | None = Field(
        description="EC classification(s) for this reaction. Empty list "
        "for ~107/2,349 reactions without EC. None on transport rows.")
    mass_balance: Literal["balanced", "unbalanced"] | None = Field(
        description="Reaction mass-balance status (no nulls in KG: 1,922 "
        "balanced + 427 unbalanced). None on transport rows.")

    # transport-arm fields (None on metabolism rows)
    tcdb_family_id: str | None = Field(
        description="Full prefixed TcdbFamily ID (e.g. 'tcdb:3.A.1.4.5'). "
        "Transport rows only.")
    tcdb_family_name: str | None = Field(
        description="TCDB family name. For tc_family-level entries this is "
        "human-readable (e.g. 'The ATP-binding Cassette (ABC) Superfamily'); "
        "for tc_subfamily / tc_specificity falls back to the tcdb_id. "
        "Transport rows only.")

    # always-populated metabolite fields
    metabolite_id: str = Field(
        description="Full prefixed Metabolite ID (e.g. 'kegg.compound:C00086').")
    metabolite_name: str = Field(
        description="Metabolite display name (e.g. 'Urea').")
    metabolite_formula: str | None = Field(
        description="Hill-notation formula; null on ~9% of metabolites "
        "(transport-only ChEBI generics).")
    metabolite_mass: float | None = Field(
        description="Monoisotopic mass (Da); null on ~22% of metabolites.")
    metabolite_chebi_id: str | None = Field(
        description="ChEBI numeric ID; populated on ~90% of metabolites.")

    # verbose-only fields:
    gene_category: str | None = Field(
        description="Curated `Gene.gene_category` value (e.g. 'Transport', "
        "'Amino acid metabolism'). Verbose only.")
    metabolite_inchikey: str | None = Field(
        description="Structural fingerprint; populated on ~78% of "
        "metabolites. Verbose only.")
    metabolite_smiles: str | None = Field(
        description="Canonical SMILES; populated on ~84% of metabolites. "
        "Verbose only.")
    metabolite_mnxm_id: str | None = Field(
        description="MetaNetX ID (e.g. 'MNXM731'); 100% coverage. Verbose only.")
    metabolite_hmdb_id: str | None = Field(
        description="HMDB ID (e.g. 'HMDB0000122'); ~47% coverage. Verbose only.")
    reaction_mnxr_id: str | None = Field(
        description="Reaction MetaNetX ID. Verbose, metabolism rows only.")
    reaction_rhea_ids: list[str] | None = Field(
        description="Rhea reaction cross-refs. Verbose, metabolism rows only.")
    tcdb_level_kind: Literal["tc_class","tc_subclass","tc_family",
                             "tc_subfamily","tc_specificity"] | None = Field(
        description="TCDB hierarchy level of the annotation. Verbose, "
        "transport rows only. `tc_specificity` ⇔ "
        "transport_confidence='substrate_confirmed'.")
    tc_class_id: str | None = Field(
        description="TCDB class ancestor (e.g. 'tcdb:3' for Primary Active "
        "Transporters). Pre-computed pointer. Verbose, transport rows only.")


class GenesByMetaboliteResponse(BaseModel):
    """Top-level response envelope for genes_by_metabolite."""
    total_matching: int = Field(
        description="Total row count after all filters, across both arms.")
    returned: int = Field(
        description="Number of rows in `results` (≤ `limit`).")
    offset: int = Field(
        description="Echo of the requested offset.")
    truncated: bool = Field(
        description="True when `offset + limit < total_matching`.")
    warnings: list[str] = Field(
        description="Diagnostic strings. Currently emitted: family-inferred-"
        "dominance auto-warning when transport rows are family-inferred "
        "majority and `transport_confidence` was not set explicitly.")
    not_found: GbmNotFound = Field(
        description="Inputs that did not resolve to a KG node — see model.")
    not_matched: list[str] = Field(
        description="Input metabolite_ids that exist as Metabolite nodes "
        "but produced zero rows in this organism slice (under the active "
        "filters). Distinct from `not_found.metabolite_ids` (those don't "
        "exist at all).")
    by_metabolite: list[GbmByMetabolite] = Field(
        description="Per-metabolite rollup. One entry per input metabolite_id "
        "that produced ≥1 row.")
    by_evidence_source: list[GbmByEvidenceSource] = Field(
        description="Frequency over `evidence_source` values present in "
        "the slice (≤2 entries).")
    by_transport_confidence: list[GbmByTransportConfidence] = Field(
        description="Frequency over `transport_confidence` values across "
        "transport rows only (≤2 entries; metabolism rows are excluded).")
    top_reactions: list[GbmTopReaction] = Field(
        description="Top 10 reactions by gene_count in the metabolism arm.")
    top_tcdb_families: list[GbmTopTcdbFamily] = Field(
        description="Top 10 TCDB families by gene_count in the transport arm.")
    top_gene_categories: list[GbmTopGeneCategory] = Field(
        description="Top 10 gene categories by gene_count across both arms.")
    top_genes: list[GbmTopGene] = Field(
        description="Top 10 genes by combined reaction + transporter "
        "breadth across both arms.")
    gene_count_total: int = Field(
        description="Distinct genes in the filtered slice (across both arms).")
    reaction_count_total: int = Field(
        description="Distinct reactions in the filtered metabolism arm.")
    transporter_count_total: int = Field(
        description="Distinct TcdbFamily nodes in the filtered transport arm.")
    metabolite_count_total: int = Field(
        description="Distinct metabolite_ids that produced ≥1 row.")
    results: list[GeneReactionMetaboliteTriplet] = Field(
        description="Detail rows after global sort + slice. Empty when "
        "`summary=True`.")
```

(Sub-models defined under "Envelope row classes" above with their own
field descriptions.)

### Wrapper

Standard `@mcp.tool` async def — calls the api function with kwargs,
constructs the Pydantic response. Update `EXPECTED_TOOLS` constant.

---

## Tests

### Unit: query builder (`test_query_builders.py`)

- `TestBuildGenesByMetaboliteMetabolism` — covers WHERE composition
  per filter, RETURN-column shape (compact + verbose), ORDER BY,
  SKIP/LIMIT clauses.
- `TestBuildGenesByMetaboliteTransport` — same coverage; includes
  `transport_confidence='substrate_confirmed'` adding `tf.level_kind = 'tc_specificity'`.
- `TestBuildGenesByMetaboliteSummary` — covers single-pass UNION + aggregation,
  RETURN keys, top-N truncation in apoc-collected envelopes.

### Unit: API function (`test_api_functions.py`)

- `TestGenesByMetabolite` — mocked-conn fixtures:
  - Default both arms fire; `not_found` empty when all IDs resolve.
  - `evidence_sources=['metabolism']` skips transport arm; no warning emitted.
  - `evidence_sources=['transport']` skips metabolism arm; no warning emitted.
  - `ec_numbers` set + both arms active → metabolism arm narrowed; transport
    arm rows returned UNCHANGED (no soft-exclude). No warning.
  - `mass_balance` set → same per-arm-scope behavior as `ec_numbers`.
  - `transport_confidence='substrate_confirmed'` narrows transport arm WHERE
    only; metabolism arm unaffected. No warning.
  - `transport_confidence='family_inferred'` narrows transport arm only;
    metabolism arm unaffected. No warning.
  - Family-inferred-dominance warning fires only when:
    transport rows present in result AND
    `transport_family_inferred_rows > transport_substrate_confirmed_rows`
    AND user did NOT set `transport_confidence`.
  - `not_found.metabolite_ids`, `not_matched`, `not_found.metabolite_pathway_ids` populated
    correctly under mixed input (e.g. `[urea, chebi:9314, C99999]`).
  - `summary=True` skips detail builder dispatch; returns envelope only.
  - Limit/offset slicing across concatenated arm results (paging strategy
    correctness — verifies `[offset:offset+limit]` returns globally-sorted
    rows even when both arms over-fetch).

### Unit: MCP wrapper (`test_tool_wrappers.py`)

- `TestGenesByMetaboliteWrapper` — Pydantic schema validation, sparse-strip
  behavior on optional fields, EXPECTED_TOOLS update.

### Integration (`test_mcp_tools.py`)

Two complementary live-KG smoke tests:

**Smoke 1 — `urea × MED4` (both arms exercised, both transport_confidence levels present, auto-warning does NOT fire):**
- `total_matching == 23`
- `by_metabolite[0]` (urea): `metabolism_rows = 4`,
  `transport_substrate_confirmed_rows = 10`, `transport_family_inferred_rows = 9`
- `by_evidence_source`: both `metabolism` (4) and `transport` (19) entries
- `by_transport_confidence`: both `substrate_confirmed` (10) and `family_inferred` (9)
- `gene_count_total == 18` (4 metabolism distinct genes + 14 distinct transport genes; no overlap)
- With `limit=10`, the first 4 rows are metabolism rows (alphabetical 'metabolism' < 'transport');
  rows 5–10 are transport substrate_confirmed (urtA-urtE × 2 specificity leaves).
- `warnings == []` (transport_substrate_confirmed=10 > transport_family_inferred=9, so auto-warning does NOT fire).

**Smoke 2 — `nitrite × MED4` (transport-only, family-inferred dominates → auto-warning fires):**
- `total_matching == 14` (no metabolism rows — MED4 has no nitrite-anchored metabolism reactions today)
- `by_evidence_source`: only `transport` entry
- `by_transport_confidence`: `substrate_confirmed` (5), `family_inferred` (9)
- `warnings` includes the family-inferred-dominance string (9 > 5).

### Integration: API contract (`test_api_contract.py`)

- `TestGenesByMetaboliteContract` — round-trips representative inputs,
  verifies envelope shape across arm-suppression modes.

### Regression (`test_regression.py` + `test_eval.py`)

- Add `genes_by_metabolite: build_genes_by_metabolite_metabolism` to
  `TOOL_BUILDERS`. Snapshot: urea × MED4 default call.
  Note: regression captures the metabolism-arm Cypher; the transport-arm
  Cypher is implicit via the api round-trip.

### Eval cases (`tests/evals/cases.yaml`)

5–7 cases covering:

1. **`urea × MED4` default** — both arms exercised, both transport_confidence
   levels present (10 sc + 9 fi); auto-warning does NOT fire (sc > fi for urea).
   23 rows total.
2. **`nitrite × MED4` default** — transport-only (no metabolism rows; 5 sc +
   9 fi); auto-warning DOES fire (fi > sc). 14 rows total.
3. **`urea × MED4` with `transport_confidence='substrate_confirmed', evidence_sources=['transport']`**
   — transporter precision check; returns 10 rows (5 distinct genes urtA-urtE
   × 2 specificity-leaf annotations); no auto-warning.
4. **`glutamine × MED4` with `ec_numbers=['6.3.1.2']`** — verifies metabolism
   arm narrows to 1 row (glnA × glutamine, R00253) while transport rows (10
   family_inferred, urtA-urtE-like generic ABC) are returned unchanged.
   Total 11 rows. Auto-warning fires (10 fi > 0 sc on transport).
5. **Mixed input `[urea, chebi:9314, kegg.compound:C99999]` × MED4** —
   `not_found.metabolite_ids = ['chebi:9314', 'kegg.compound:C99999']`;
   urea returns 23 rows; no auto-warning.
6. **C00069 (alcohol) × Alteromonas macleodii ATCC27126** — empty result
   with `not_matched=['kegg.compound:C00069']`, `not_found.metabolite_ids=[]`.
   (Originally drafted with water/C00001; swapped during Phase 2 build —
   ATCC27126 has 333 water-catalyzing genes. Alcohol's Metabolite node
   exists in KG but has no gene reach in this organism via either arm.)
7. **Pathway-anchored: `metabolite_pathway_ids=['kegg.pathway:ko00910']`**
   (nitrogen metabolism) + N-bearing metabolites × MED4 — both arms
   narrowed uniformly via `m.pathway_ids` denorm. 56 rows.

---

## About Content

**File:** `multiomics_explorer/inputs/tools/genes_by_metabolite.yaml`

Sections (matches existing schema):

- `examples`: 5 chained examples — list_metabolites → genes_by_metabolite for one organism; cross-feeding pairs of calls; substrate_confirmed transporter hunt; pathway-anchored; ec-anchored.
- `chaining`:
  - **upstream:** `list_metabolites`, `differential_expression_by_gene` (then map locus_tags to metabolites via Tool 3), workflow-A and B step references.
  - **downstream from rows:** `differential_expression_by_gene(locus_tags=top_genes, organism=...)`, `gene_overview`.
  - **downstream from envelope:** `genes_by_ontology(ontology="tcdb", term_ids=top_tcdb_families[i].tcdb_family_id, organism=...)`, `genes_by_ontology(ontology="ec", term_ids=...)`, `pathway_enrichment`.
- `mistakes`:
  - "I want all transporter genes for substrate X" → set
    `transport_confidence='substrate_confirmed', evidence_sources=['transport']`
    to drop family-inferred noise AND exclude metabolism rows.
  - "Filtering by `ec_numbers` should restrict to metabolism only" → no.
    Filters narrow only their own arm; the other arm runs unfiltered.
    Add `evidence_sources=['metabolism']` to restrict.
  - "Cross-organism filter" — single-organism enforced; call once per organism.
  - "metabolomics" not accepted in `evidence_sources` — see `list_metabolites`.
  - "TCDB-class filtering" — go through `genes_by_ontology(ontology="tcdb")`, not back here.
- `verbose_fields`: gene_category, metabolite cross-refs, reaction cross-refs, tcdb_level_kind, tc_class_id.

After edits, regenerate the skill md:
```bash
uv run python scripts/build_about_content.py
```

## Documentation Updates

- **`CLAUDE.md` MCP tool table:** add `genes_by_metabolite` row alongside
  the chemistry tools (`list_metabolites`, future `metabolites_by_gene`).
- **`gene_overview` row description:** when `chemistry_count > 0`,
  drill-down clause should now point to `genes_by_metabolite` (when the
  caller has the metabolite IDs) or `metabolites_by_gene` (when starting
  from gene IDs).

## Forward-compatibility notes

- **Metabolomics-DM landing.** No change here — metabolomics evidence
  has no gene anchor, so it never produces rows in this tool.
  `evidence_sources` Literal stays `{metabolism, transport}`. The forward-
  compat slot lives in `list_metabolites` (cross-organism, metabolite-anchored).
- **TCDB-CAZy schema extensions.** Already shipped. No further changes
  expected for slice 1.
- **`Gene.catalytic_activities` direction-aware reaction parsing.** A
  future spec could add `direction` per metabolism row (substrate / product).
  Such a field would be a sparse addition to the existing row class
  (transport rows keep null) — no breaking change.

## Open questions / risks

No open questions blocking Phase 2 build. Items deferred to backlog
(tracked in `project_backlog.md`):

- `list_filter_values(filter_type="tcdb_level_kind")` discoverability.
- `metabolites_by_pathway` (and other metabolite-anchored ontology tools)
  as a slice-2 sibling of `list_metabolites`.
- `gene_overview` extension drill-down clause update — coordinates with
  slice-1 design Tool 5 (`gene_overview` extension); sequence after this
  tool ships.

### Resolved

- **Tool 3 naming locked: `metabolites_by_gene`.** Design doc's
  `gene_metabolic_role` is superseded by the symmetric `metabolites_by_gene`
  name (mirrors `genes_by_metabolite`). Affects file/exports/EXPECTED_TOOLS
  registration when Tool 3 ships; no impact on this spec's build.
- **`reactions_without_name` envelope field dropped.** Reaction-name
  nullness is a niche reaction-side detail; this tool's focus is gene →
  metabolite. The 32 empty-name reactions surface as `reaction_name = ''`
  on individual rows (no envelope diagnostic).
- **`metabolite_pathway_ids` filter naming.** Renamed from `pathway_ids`
  to disambiguate from gene-side pathway annotations (which Gene reaches
  via KO ontology, accessed through `genes_by_ontology(ontology="kegg")`).
  KG property `m.pathway_ids` (the Neo4j property name) unchanged.
- **`evidence_sources` Literal divergence with `list_metabolites`.**
  `list_metabolites` accepts `("metabolism", "transport", "metabolomics")`
  — three values, with `"metabolomics"` reserved as forward-compat input
  (zero matches today; activates when the metabolomics-DM KG spec lands).
  This tool accepts only `("metabolism", "transport")` — two values. The
  divergence is intentional: metabolomics evidence is metabolite-anchored
  (DerivedMetric → Metabolite, no Gene anchor). A user passing
  `evidence_sources=["metabolomics"]` on a gene-anchored tool would never
  match a row, so we reject at the boundary instead of silently returning
  zero. Same `_VALID_EVIDENCE_SOURCES` validator pattern, different value
  set per tool's biology.
- **Splitting metabolism vs transport into two tools.** Considered;
  rejected. Unified tool with per-row `evidence_source` is the right
  shape — biological question is unified, evidence_source slot keeps
  forward-compat for metabolomics in metabolite-centric tools (though it
  doesn't appear in gene-anchored tools), asymmetry pressure on Tool 3
  avoided.
- **`confidence` field name.** Renamed to `transport_confidence` and
  scoped strictly to transport rows (sparse `None` on metabolism rows).
  `transport_confidence` is self-documenting; the previous "metabolism
  rows always = substrate_confirmed" was redundant signal.
- **Default `transport_confidence` behavior.** Default returns both
  levels; sort puts `substrate_confirmed` first within transport rows;
  auto-warning fires when family-inferred dominates the transport-row
  subset. Avoids losing recall while making the rollup-induced false-
  positive risk visible.
- **Per-arm filter scope semantics.** Path-scoped filters (`ec_numbers`,
  `mass_balance`, `transport_confidence`) narrow only their own arm; the
  other arm runs unfiltered. The earlier "soft-exclude with warning"
  pattern was abandoned in favor of explicit `evidence_sources` for
  single-arm restriction. Result: filter behavior is predictable and
  composable — no surprise warnings, no auto-suppressed arms.
- **`tcdb_class_ids` filter.** Dropped — TCDB-class queries belong in
  `genes_by_ontology(ontology="tcdb")`. TCDB's dual role (connecting
  layer here; ontology elsewhere) is an architectural feature, not a
  duplication.
- **`UNION` inside detail Cypher.** Rejected. Two-arm `MATCH` blocks
  with api-side concat is simpler and faster than a unified RETURN with
  null-padded columns; only the summary builder uses CALL{...UNION...}
  for a single-pass aggregation across arms.

## References

- Slice-1 design doc: `docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md`
  (§ 2.2 = Tool 2 = this spec)
- KG asks doc (slice 1): `docs/superpowers/specs/2026-05-01-kg-side-chemistry-slice1-asks.md`
- Follow-up KG asks: `docs/superpowers/specs/2026-05-02-kg-side-chemistry-slice1-followup-asks.md`
- TCDB-CAZy KG changes: `multiomics_biocypher_kg/docs/kg-changes/tcdb-cazy-ontologies.md`
- Sibling spec: `docs/tool-specs/list_metabolites.md` (Tool 1, frozen 2026-05-03)
- Add-or-update-tool skill: `.claude/skills/add-or-update-tool/SKILL.md`
