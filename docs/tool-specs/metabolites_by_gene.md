# metabolites_by_gene — Tool spec (Phase 1)

## Executive Summary

Step 3 of the chemistry slice 1 symmetric three-tool set:

| Step | Tool | Anchor |
|---|---|---|
| 1 | `list_metabolites` (shipped 2026-05-03, commit 121097a) | metabolite discovery (cross-organism) |
| 2 | `genes_by_metabolite` (shipped 2026-05-03) | metabolite → genes (single-organism) |
| **3** | **`metabolites_by_gene` (THIS SPEC)** | **gene → metabolites (single-organism)** |

Drill-down anchored on locus_tags. Returns rows showing the metabolites the
input gene set's chemistry reaches in the requested organism, via either:

- **Metabolism path:** `Gene → Reaction → Metabolite` (`evidence_source = "metabolism"`)
- **Transport path:** `Gene → TcdbFamily → Metabolite` (`evidence_source = "transport"`) — single-hop via the **TCDB substrate-edge rollup** (landed 2026-05-03)

Unified two-arm UNION; identical `transport_confidence` model as `genes_by_metabolite`
(`substrate_confirmed` / `family_inferred`); identical `evidence_sources` Literal
(`"metabolism"`, `"transport"` only — metabolomics evidence is metabolite-anchored
and surfaces in `list_metabolites`).

**Shared row class.** Reuses `GeneReactionMetaboliteTriplet` from
`genes_by_metabolite` (module-level in `mcp_server/tools.py`). Identical
per-row schema, different anchor.

**The gene-anchored asymmetries vs. `genes_by_metabolite`** are the value-add
of this spec:

1. **One filter addition:** `metabolite_elements: list[str] | None` — the slice-1
   design doc's headline N-source workflow primitive
   (`metabolites_by_gene(locus_tags=DE_genes, organism=MED4, metabolite_elements=["N"])`)
2. **Two envelope additions** that have no peer in `genes_by_metabolite` because
   they only make sense gene-set-anchored (rolling up across multiple genes):
   - **`top_pathways`** — KEGG pathways the gene set's chemistry reaches.
     Mirror of `list_metabolites.top_pathways` naming for cross-tool consistency;
     docstring disambiguates from gene-KO-mediated pathway annotations
     (which live in `genes_by_ontology(ontology="kegg")`).
   - **`by_element`** — C/N/P/S/metal-presence signature of the metabolites
     the gene set touches. Free Cypher (uses `m.elements`).
3. **Sort design diverges:** global precision-first
   (`metabolism` → `transport_substrate_confirmed` → `transport_family_inferred`)
   rather than per-gene-then-per-precision. Forced by the long tail finding
   below — a single ABC-superfamily-only gene at the front of a batch DE input
   would otherwise eat the entire `limit=10` with family_inferred rows before
   the next gene gets to surface anything.

All other axes mirror `genes_by_metabolite`: filter set, per-arm scope semantics,
`Mbg*` Pydantic prefix (tool-anchored, mixed-entity envelope), `not_found` /
`not_matched` model, `*_count_total` envelope counters, `warnings`,
`summary` / `verbose` / `limit` / `offset` controls, single-organism enforcement.

## Out of Scope

- **`tcdb_class_ids` filter.** Same reasoning as
  `genes_by_metabolite` — TCDB class queries belong in
  `genes_by_ontology(ontology="tcdb")`.
- **Rhea / `Gene.catalytic_activities` direction-aware substrate vs product
  splitting.** Future spec opportunity. Both arms remain direction-agnostic.
- **Metabolomics evidence rows.** No gene anchor — surfaces only in `list_metabolites`.
- **Cross-organism mode.** Single-organism enforced (mirrors
  `differential_expression_by_gene` and `genes_by_metabolite`).
- **Annotation-quality enrichment of `not_matched`.** F1 KG fields
  (`Gene.annotation_state`, `informative_annotation_types`) are out of slice-1
  chemistry scope. The plain `list[str]` of locus_tags is sufficient; caller
  pivots to `gene_overview(locus_tags=not_matched)` for annotation context.
  Tracked as cross-cutting design opportunity (annotation-quality awareness
  across the MCP surface), separate spec.
- **Per-row pathway field on the triplet.** Skipped to keep the shared
  `GeneReactionMetaboliteTriplet` row class unchanged. Per-row pathway info
  is what `list_metabolites(metabolite_ids=[...])` is for; pathway-level
  context lives in the `top_pathways` envelope rollup.
- **Explicit `min_metabolite_count` / `min_reaction_count` row filters.**
  Caller ranks client-side from envelope rollups (mirror GBM).
- **`top_ec_classes` envelope rollup.** Derivable client-side from
  `top_reactions[].ec_numbers` first-digit. Marginal value-add.
- **`gene_count_with_chemistry` scalar counter.** Derivable from
  `len(input_locus_tags) - len(not_matched)`; covered by
  `metabolite_count_total` (the metabolite-side breadth answer).

## Status / Prerequisites

- [x] Slice-1 design approved
  (`docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md` § 2.3,
  formerly named `gene_metabolic_role` — renamed to `metabolites_by_gene`
  on 2026-05-03 per genes_by_metabolite freeze)
- [x] Sister tool `genes_by_metabolite` shipped and verified live (commit
  landed 2026-05-03; live MCP returns expected envelope shape and row counts)
- [x] Sister tool `list_metabolites` shipped (commit 121097a) — establishes
  the `top_pathways` rollup naming MBG mirrors
- [x] All slice-1 KG asks landed (chemistry-slice-1 KG-A1..A10, TCDB-CAZy
  ontology, TCDB substrate-edge rollup, KeggTerm.metabolite_count /
  reaction_count rollups, KeggTerm.id index)
- [x] Cypher verified against live KG (see "KG verification" below)
- [x] Result-size controls decided: `summary` / `verbose` / `limit=10` /
  `offset` (default `limit=10` covers ~p70 of single-gene UNION row distribution
  in MED4; cross-tool consistency with GBM)
- [ ] Ready for Phase 2 (build) — pending user approval of this spec

## Use cases

- **N-source workflow (marquee, slice-1 design § Workflow A).**
  `differential_expression_by_gene(organism=MED4, experiment_ids=[N-limitation], direction="up")`
  → `metabolites_by_gene(locus_tags=DE_genes, organism=MED4, metabolite_elements=["N"])`
  → triplet rows showing which N-bearing metabolites the upregulated genes touch.
  `top_pathways` answers "which pathways concentrate" (e.g. nitrogen
  metabolism, arginine biosynthesis); `top_metabolites` ranks specific
  N-compounds by gene reach in the input set.

- **Gene-set chemistry characterization (post-clustering or post-function-search).**
  `genes_in_cluster(cluster_id=...)` or `genes_by_function(query=...)`
  → `metabolites_by_gene(locus_tags=cluster_genes, organism=...)` →
  "what is this co-expressed cluster doing chemically." `top_pathways`
  is the highest-density answer per byte; `by_element` adds a C/N/P/S
  signature for free.

- **Cross-feeding gene set (Workflow B').**
  `differential_expression_by_gene(MED4 coculture-up genes)`
  → `metabolites_by_gene(MED4 DE genes)` → top_metabolites
  → `genes_by_metabolite(metabolite_ids=top_metabolites, organism=Alteromonas)`
  → catalysts and transporters in the partner organism for the same metabolites.

- **Single-gene drill-down.**
  `genes_by_function(query="urease")` → PMM0913
  → `metabolites_by_gene(locus_tags=["PMM0913"], organism=MED4)`
  → "what metabolites does this gene touch via either arm." Envelope
  rollups mostly noise at n=1; detail rows + total_matching do the work.

- **Routing to drill-downs.** `top_metabolites` rows pivot to:
  - `list_metabolites(metabolite_ids=[...])` for richer per-metabolite context
    (cross-refs, mass, formula, pathway names)
  - `list_metabolites(metabolite_ids=[...], organism_names=[partner])` for
    cross-organism presence check (and metabolomics presence once that lands)

  `top_pathways` rows pivot to:
  - `list_metabolites(pathway_ids=[from top_pathways])` for the full
    metabolite roster of the pathway, not just gene-set hits
  - `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)`
    for genes annotated to the pathway via KO (different surface)

  `top_reactions` and `top_tcdb_families` mirror GBM's drill-down clauses
  (route to `genes_by_ontology(ontology="ec"/"tcdb")` for sibling annotations).

## KG dependencies

### Nodes & properties read

`Gene`:
- `locus_tag` (str) — input filter target, primary identifier
- `gene_name` (str | null) — sparse result field
- `product` (str | null) — sparse result field
- `gene_category` (str) — both filter target and verbose-result / envelope field
- `organism_name` (str) — single-organism filter

`Reaction`:
- `id` (str, full prefixed `kegg.reaction:R*`) — result field on metabolism rows;
  `top_reactions` envelope key
- `name` (str | empty) — result field; **32/2,349 reactions have empty name**
  (surfaces as `reaction_name = ''`; no envelope-level diagnostic)
- `ec_numbers` (list[str]) — `ec_numbers` filter target + result field
- `mass_balance` (Literal["balanced","unbalanced"]) — filter target + result field
- `mnxr_id` (str | null) — verbose field
- `rhea_ids` (list[str] | null) — verbose field

`TcdbFamily`:
- `id` (str, e.g. `tcdb:3.A.1.4.5`) — result field on transport rows;
  `top_tcdb_families` envelope key
- `name` (str) — result field; falls back to `tcdb_id` for non-`tc_family` levels
- `level_kind` (Literal[…]) — drives `transport_confidence` derivation; verbose
  result field on transport rows

`Metabolite`:
- `id` (str, full prefixed) — primary join key + `top_metabolites` envelope key
- `name`, `formula`, `mass`, `chebi_id` (sparse) — result fields
- **`elements` (list[str])** — backs the new `metabolite_elements` filter +
  the new `by_element` envelope rollup. Hill-parsed presence list (e.g.
  Urea CH4N2O → `["C","H","N","O"]`); empty list for the 31/2,188
  metabolites without `formula`.
- `pathway_ids` (list[str], KG-A5 denorm; 100% coverage) — backs the
  `metabolite_pathway_ids` filter
- `inchikey`, `smiles`, `mnxm_id`, `hmdb_id` — verbose fields

`KeggTerm` (for `top_pathways` rollup):
- `id` (str, full prefixed `kegg.pathway:ko*`) — pathway identifier
- `name` (str) — pathway display name
- `level_kind` (Literal["pathway", …]) — filter to pathway-level entries
- **`reaction_count` (int, KG-4 post-import rollup, 100% on pathway-level)** —
  backs the `>= 3` chemistry-pathway filter that drops signaling/disease
  pathways (otherwise water/CO2 promiscuity surfaces "Vasopressin water
  reabsorption" above "Nitrogen metabolism")
- **`metabolite_count` (int, KG-4 post-import rollup)** — verbose envelope
  field for at-a-glance pathway sizing

### Edges traversed

| Edge | Direction | Arm | Hops |
|---|---|---|---|
| `Gene_catalyzes_reaction` | Gene → Reaction | metabolism | 1 |
| `Reaction_has_metabolite` | Reaction → Metabolite | metabolism | 1 |
| `Reaction_in_kegg_pathway` | Reaction → KeggTerm | metabolism (pathway rollup) | 1 |
| `Metabolite_in_pathway` | Metabolite → KeggTerm | both arms (pathway rollup) | 1 |
| `Gene_has_tcdb_family` | Gene → TcdbFamily | transport | 1 |
| `Tcdb_family_transports_metabolite` | TcdbFamily → Metabolite | transport | 1 (rollup-extended; no variable-length walk) |

Total **2 hops per arm** for the detail / by-gene / by-metabolite rollups;
3 hops via metabolite for the `top_pathways` rollup.

### Indexes
- `MATCH (g:Gene {organism_name: $org}) WHERE g.locus_tag IN $locus_tags`
  benefits from `organism_name` index + `locus_tag` index on Gene (both existing)
- `MATCH (p:KeggTerm {id: pid})` benefits from the `kegg_term_id_idx`
  RANGE index (KG-A9, landed 2026-05-02 — directly added to support this rollup)
- No fulltext entry point on this tool — `locus_tags` is required.

---

## Live-KG state snapshot (verified 2026-05-03)

### Per-gene UNION row distribution (MED4)

| Slice | value |
|---|---|
| Total MED4 genes | 1,976 |
| Genes with ≥1 chemistry edge | 610 (31%) |
| Genes with zero chemistry edges (→ `not_matched` if requested) | 1,366 (69%) |
| Median rows per gene (across both arms) | 6 |
| p75 | 12 |
| p90 | 20 |
| p95 | 32 |
| p99 | **551** |
| Max | 551 |

The p99 = max = 551 represents 9 ABC-superfamily-only genes (`tcdb:3.A.1`
family-inferred annotation) that emit the same 551 substrate-curated rolled-up
metabolites. Same hot pattern as GBM's transport noise, now per-gene-side.

| Long-tail genes (all 551 rows, all transport-arm family_inferred) |
|---|
| PMM0434 (ftsE), PMM0449 (ccmA), PMM0450 (ycf38), PMM0749 (devC), PMM0750 (devA), PMM0913 (salY), PMM0976/0977/0978 (evrA/B/C) |

Next-largest: **PMM0331 (ALDH, 229 rows)** — a broad-specificity aldehyde
dehydrogenase, pure metabolism arm. KEGG promiscuity.

### Filter-column population (all chemistry-relevant)

| Column | Coverage | Notes |
|---|---|---|
| `r.mass_balance` | 100% (no nulls) | 1,922 balanced + 427 unbalanced |
| `r.ec_numbers` | 95% (2,242/2,349) | 107 reactions w/o EC |
| `m.pathway_ids` | 100% (3,025/3,025) | 920 metabolites have empty list |
| `m.elements` | 99% (2,157/2,188) | 31 metabolites without `formula` → empty list |
| `g.gene_category` | 100% on Gene | ~25 distinct values per organism |
| `tf.tc_class_id` | 100% (4,844/4,844) | post-import pointer |
| `p.reaction_count` (KeggTerm pathway-level, KG-4) | 100% on pathway-level entries | backs `>= 3` filter on `top_pathways` |

### `top_pathways` rollup behavior (verified)

For input `[PMM0963, PMM0964, PMM0965]` (urease alpha/beta/gamma subunits)
× MED4, with `WHERE p.reaction_count >= 3` chemistry filter applied, the
top-15 pathways are:

| Rank | pathway_id | pathway_name | gene_count | pathway_reactions |
|---|---|---|---|---|
| 1 | `kegg.pathway:ko01310` | Nitrogen cycle | 3 | 10 |
| 2 | `kegg.pathway:ko00625` | Chloroalkane and chloroalkene degradation | 3 | 11 |
| 3 | `kegg.pathway:ko00460` | Cyanoamino acid metabolism | 3 | 13 |
| 4 | `kegg.pathway:ko00361` | Chlorocyclohexane and chlorobenzene degradation | 3 | 18 |
| 5 | `kegg.pathway:ko00780` | Biotin metabolism | 3 | 18 |
| 6 | `kegg.pathway:ko00785` | Lipoic acid metabolism | 3 | 21 |
| 7 | `kegg.pathway:ko00710` | Carbon fixation by Calvin cycle | 3 | 22 |
| 8 | `kegg.pathway:ko00910` | Nitrogen metabolism | 3 | 23 |
| 9 | `kegg.pathway:ko00220` | Arginine biosynthesis | 3 | 26 |
| 10 | `kegg.pathway:ko00250` | Alanine, aspartate and glutamate metabolism | 3 | 33 |

Without the `reaction_count >= 3` filter, "Vasopressin-regulated water
reabsorption" (2 metabolites, 0 chemistry breadth) would rank above
"Nitrogen metabolism" because both contain water. Filter pre-empts.

**Pathway scope asymmetry confirmed:** R00131 (urease) has **zero**
`Reaction_in_kegg_pathway` edges — the metabolite-side join is **load-bearing**.
Reaction-side-only `top_pathways` would emit zero results for this input,
even though biologically it sits squarely in nitrogen/arginine metabolism.

### `by_element` rollup behavior (verified)

For input `[PMM0963, PMM0964, PMM0965]` × MED4 (urease subunits touching
{Urea, H2O, CO2, NH3}):

```
[
  {element: "H", metabolite_count: 3},  // Urea, H2O, NH3
  {element: "O", metabolite_count: 3},  // Urea, H2O, CO2
  {element: "C", metabolite_count: 2},  // Urea, CO2
  {element: "N", metabolite_count: 2},  // Urea, NH3
]
```

Bounded cardinality (~30 elements max in KG); full rollup, no top-N truncation.

### `not_matched` candidates (verified)

| locus_tag | gene_name | product | annotation_state |
|---|---|---|---|
| PMM0002 | — | conserved hypothetical protein | informative_single |
| PMM0005 | — | DNA gyrase/topoisomerase IV, subunit A family protein | informative_multi |
| PMM0006 | — | tetratricopeptide repeat family protein | informative_multi |
| PMM0007 | queG | epoxyqueuosine reductase | informative_multi |
| PMM0008 | — | uncharacterized conserved membrane protein (DUF502) | informative_multi |

Most `not_matched` genes are richly-annotated — they're genuine non-chemistry
genes (DNA gyrase, queG enzyme without explicit reaction mapping, signaling
modules), not annotation gaps. Plain locus_tag list is sufficient for slice 1.

---

## Tool Signature

```python
@mcp.tool(
    tags={"genes", "metabolites", "chemistry", "drill-down"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def metabolites_by_gene(
    ctx: Context,
    locus_tags: Annotated[list[str], Field(
        description="Gene locus tags to drill into (case-sensitive). "
        "E.g. ['PMM0963', 'PMM0964', 'PMM0965'] for urease α/β/γ subunits. "
        "`not_found.locus_tags` lists tags that don't resolve to any Gene "
        "in the requested organism; `not_matched` lists tags that DO "
        "resolve but have no chemistry edges (no Gene_catalyzes_reaction "
        "AND no Gene_has_tcdb_family).",
        min_length=1,
    )],
    organism: Annotated[str, Field(
        description="Organism name (case-insensitive, fuzzy word-based match — "
        "mirrors `differential_expression_by_gene` and `genes_by_metabolite`). "
        "Single-organism enforced. E.g. 'Prochlorococcus MED4'. "
        "`not_found.organism` is set when the name resolves to zero matching "
        "genes for the input locus_tags.",
        min_length=1,
    )],
    metabolite_elements: Annotated[list[str] | None, Field(
        description="Filter to rows where the metabolite contains ALL of the "
        "given element symbols (AND-of-presence). E.g. `['N']` keeps only "
        "N-bearing metabolites — the headline N-source workflow primitive. "
        "`['N', 'P']` requires both. Anchored on `Metabolite.elements` "
        "(KG-A3 Hill-parsed presence list); applies uniformly to both arms. "
        "Never substring-match on `formula` (Hill notation has element-clash "
        "footguns: 'Cl' contains 'C', 'Na' contains 'N'). "
        "`not_found.metabolite_elements` lists symbols that don't exist on "
        "any KG metabolite.",
    )] = None,
    metabolite_ids: Annotated[list[str] | None, Field(
        description="Restrict rows to specific metabolite IDs (full prefixed, "
        "e.g. ['kegg.compound:C00086', 'kegg.compound:C00064']). Useful for "
        "the cross-feeding workflow: after MBG returns top_metabolites, "
        "re-query a partner organism via `genes_by_metabolite` with these IDs. "
        "Applies uniformly to both arms.",
    )] = None,
    ec_numbers: Annotated[list[str] | None, Field(
        description="Narrow metabolism rows to those whose Reaction carries "
        "any of these EC numbers. **Metabolism arm only — does not affect "
        "transport rows**, which are returned unchanged. To restrict to "
        "metabolism rows alone, combine with `evidence_sources=['metabolism']`. "
        "E.g. ['3.5.1.5'] for urease.",
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
        "transport rows**.",
    )] = None,
    gene_categories: Annotated[list[str] | None, Field(
        description="Filter on `Gene.gene_category` (exact match, applies to "
        "both arms uniformly). Use `list_filter_values(filter_type=\"gene_category\")` "
        "for valid values. Note: somewhat redundant with `locus_tags` input; "
        "useful when locus_tags is a broad batch and you want chemistry from "
        "specific functional categories only.",
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
            "**Recommended for high-precision transporter-hunting in batch "
            "DE inputs:** `transport_confidence='substrate_confirmed', "
            "evidence_sources=['transport']` (mutes the ABC-superfamily "
            "551-row blowup).",
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
        description="When true, return only summary fields (results=[]). "
        "**Strongly recommended for batch DE inputs** (50+ locus_tags) — "
        "envelope rollups (top_metabolites, top_pathways, top_reactions, "
        "top_tcdb_families, by_element, by_gene, top_gene_categories) "
        "are the actually-useful artifact at that scale; detail rows can "
        "exceed 1,000 quickly.",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include extended fields per row: gene_category, "
        "metabolite_inchikey/smiles/mnxm_id/hmdb_id, reaction_mnxr_id/"
        "rhea_ids (metabolism rows), tcdb_level_kind/tc_class_id "
        "(transport rows). Same field set as `genes_by_metabolite`.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results in `results`. Default 10 covers ~p70 of "
        "single-gene UNION row distributions (median 6, p75 12 in MED4). "
        "Long-tail genes (ABC-superfamily-only) emit up to 551 rows — "
        "use `transport_confidence='substrate_confirmed'` to mute, or "
        "`offset` to page.",
        ge=1,
    )] = 10,
    offset: Annotated[int, Field(
        description="Number of results to skip for pagination.", ge=0,
    )] = 0,
) -> MetabolitesByGeneResponse:
    """Find metabolites the input gene set's chemistry reaches in one organism.

    **Direction-agnostic.** Joins through `Reaction_has_metabolite` (metabolism)
    and `Tcdb_family_transports_metabolite` (transport) are direction-agnostic —
    a gene that *produces* a metabolite and a gene that *consumes* it surface
    identically. KEGG equation order is arbitrary. To distinguish, layer
    transcriptional evidence (`differential_expression_by_gene`) and gene
    functional annotation (`gene_overview` Pfam / KEGG KO names like
    `*-synthase` vs `*-permease`).

    **Transport-confidence semantics (transport arm only).** Identical model
    to `genes_by_metabolite`: `family_inferred` rows ride a TCDB substrate-edge
    rollup that propagates leaf-curated substrates up the hierarchy. The
    ABC Superfamily long tail (9 MED4 genes annotated only at `tcdb:3.A.1`
    emit 551 family_inferred rows each via the rollup) means batch DE inputs
    can explode in row count. Filter
    `transport_confidence='substrate_confirmed'` (paired with
    `evidence_sources=['transport']` for the transport arm in isolation) for
    the precise set; the default fires both arms and flags `family_inferred`
    in `warnings` when it dominates.

    **Evidence sources accepted here:** `metabolism`, `transport`. The
    metabolomics path (DerivedMetric → Metabolite) has no gene anchor and is
    not surfaced by gene-anchored chemistry tools — see `list_metabolites`.

    **Sort order:** detail rows are globally sorted by precision tier
    (metabolism → transport_substrate_confirmed → transport_family_inferred),
    then by input gene order, then by locus_tag, then by metabolite_id. This
    surfaces high-precision rows from the entire batch first regardless of
    input position — a single ABC-superfamily-only gene at the front of input
    does NOT eat the entire `limit=10` with family_inferred rows.

    Drill-downs from result rows / envelope rollups:
    - Any `top_metabolites` entry → `list_metabolites(metabolite_ids=[...])`
      for richer per-metabolite cross-refs, or
      `list_metabolites(metabolite_ids=[...], organism_names=[partner])` for
      cross-organism presence (cross-feeding primitive).
    - Any `top_pathways` entry → `list_metabolites(pathway_ids=[...])` for
      the full metabolite roster of the pathway (not just gene-set hits), or
      `genes_by_ontology(ontology="kegg", term_ids=[id], organism=...)` for
      gene-KO-mediated pathway annotations (different surface — see naming
      disambiguation below).
    - Any `top_reactions` entry → `genes_by_ontology(ontology="ec", term_ids=[ec], organism=...)`
      for genes in adjacent reactions, or `pathway_enrichment` for context.
    - Any `top_tcdb_families` entry → `genes_by_ontology(ontology="tcdb", term_ids=[id], organism=...)`
      for sibling genes in the same family.

    **`top_pathways` naming disambiguation.** Despite this being a
    gene-anchored tool, `top_pathways` here means *KEGG pathways the gene set's
    chemistry reaches* — via `Reaction_in_kegg_pathway` and
    `Metabolite_in_pathway`. Distinct from the **gene-KO-mediated** pathway
    annotations available via `genes_by_ontology(ontology="kegg")` (where
    pathway membership is asserted by the gene's KO assignment). For metabolic
    pathway analysis with a hypothesis test, use `pathway_enrichment`.
    """
```

### Return envelope

```python
class MetabolitesByGeneResponse(BaseModel):
    total_matching: int               # rows after all filters, across both arms
    returned: int                     # rows in `results` (≤ limit)
    offset: int
    truncated: bool
    warnings: list[str]               # family-inferred-dominance auto-warning
    not_found: MbgNotFound            # {locus_tags, organism, metabolite_ids, metabolite_pathway_ids, metabolite_elements}
    not_matched: list[str]            # locus_tags that resolve in organism but have zero chemistry edges
    by_gene: list[MbgByGene]                          # full freq, bounded by input list (≤ len(locus_tags))
    by_evidence_source: list[MbgByEvidenceSource]     # full freq, ≤2 entries
    by_transport_confidence: list[MbgByTransportConfidence]  # full freq, transport rows only, ≤2 entries
    by_element: list[MbgByElement]                    # NEW — full freq, periodic-table-bounded ~30 max
    top_metabolites: list[MbgTopMetabolite]           # top 10 by gene reach in input set
    top_reactions: list[MbgTopReaction]               # top 10 (mirror GBM)
    top_tcdb_families: list[MbgTopTcdbFamily]         # top 10 (mirror GBM)
    top_gene_categories: list[MbgTopGeneCategory]     # top 10 (mirror GBM)
    top_pathways: list[MbgTopPathway]                 # NEW — top 10, chemistry-filtered (reaction_count >= 3)
    gene_count_total: int             # distinct genes in filtered slice
    reaction_count_total: int         # distinct reactions in filtered metabolism arm
    transporter_count_total: int      # distinct TcdbFamily nodes in filtered transport arm
    metabolite_count_total: int       # distinct metabolites in filtered slice (across both arms)
    results: list[GeneReactionMetaboliteTriplet]      # SHARED row class with genes_by_metabolite
```

**Envelope naming convention** (mirrors `list_metabolites` and `genes_by_metabolite`):
- `by_*` — full frequency rollup (every distinct value present, sorted desc by count). Used when cardinality is bounded ≤ ~15 or when bounded by input.
- `top_*` — hardcoded top-N (truncated to 10). Used when cardinality often exceeds 15.

`by_gene` is bounded by the input `locus_tags` list (one entry per locus_tag with ≥1 row). `by_element` is bounded by periodic-table cardinality. `by_evidence_source` and `by_transport_confidence` are bounded ≤2.

### Per-row `GeneReactionMetaboliteTriplet`

**Reused verbatim from `genes_by_metabolite`** — module-level Pydantic class
in `mcp_server/tools.py`. No fields added or removed for MBG. See GBM spec §
"Per-row `GeneReactionMetaboliteTriplet`" for the full field list.

Compact mode: 15 fields including `evidence_source` + `transport_confidence`
+ both arm-specific subsets. Verbose mode adds 9 more.

### Envelope row classes (`Mbg*` prefix)

```python
class MbgByGene(BaseModel):
    """Per-gene rollup. One entry per input locus_tag that produced ≥1 row.

    Cardinality bounded by the input list — kept as `by_*` (full rollup),
    not `top_*`. The gene-anchored mirror of GBM's `by_metabolite`.
    """
    locus_tag: str = Field(
        description="Gene locus tag (e.g. 'PMM0963').")
    gene_name: str | None = Field(
        default=None,
        description="Curated gene name (e.g. 'ureC'); often null.")
    product: str | None = Field(
        default=None,
        description="Annotated product description (e.g. 'urease alpha subunit').")
    rows: int = Field(
        description="Total rows for this gene across both arms in the "
        "filtered slice.")
    metabolite_count: int = Field(
        description="Distinct metabolites this gene reaches via either arm "
        "(deduplicated across metabolism and transport).")
    reaction_count: int = Field(
        description="Distinct Reactions this gene catalyzes (metabolism arm). "
        "0 when the gene is reachable only via the transport arm.")
    transporter_count: int = Field(
        description="Distinct TcdbFamily nodes this gene is annotated to "
        "(transport arm). 0 when the gene is reachable only via the "
        "metabolism arm.")
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


class MbgByEvidenceSource(BaseModel):
    """Frequency rollup over `evidence_source` values present in the slice.

    ≤2 entries — `metabolism` and/or `transport`. Identical shape to GBM's
    `GbmByEvidenceSource`.
    """
    evidence_source: Literal["metabolism", "transport"] = Field(
        description="Path through which the gene reaches the metabolite.")
    count: int = Field(
        description="Row count for this evidence_source in the filtered slice.")


class MbgByTransportConfidence(BaseModel):
    """Frequency rollup over `transport_confidence` for transport rows only.

    ≤2 entries. Identical shape to GBM's `GbmByTransportConfidence`.
    """
    transport_confidence: Literal["substrate_confirmed", "family_inferred"] = Field(
        description="TCDB-annotation specificity behind the transport edge.")
    count: int = Field(
        description="Transport-row count for this confidence level in the "
        "filtered slice.")


class MbgByElement(BaseModel):
    """NEW — Element presence rollup across the metabolites the gene set
    touches. Periodic-table-bounded (~30 elements max in KG); full rollup.

    Answers the C/N/P/S/metal-presence signature question. Free Cypher
    (uses `Metabolite.elements`, KG-A3 Hill-parsed presence list).
    """
    element: str = Field(
        description="Element symbol (Hill notation, e.g. 'C', 'N', 'P', 'S', 'Fe').")
    metabolite_count: int = Field(
        description="Distinct metabolites in the filtered slice that contain "
        "this element. Empty `m.elements` (31/2,188 metabolites without "
        "formula) does not contribute.")


class MbgTopMetabolite(BaseModel):
    """Top-N (truncated to 10) metabolites by gene reach in the filtered
    slice. The headline answer to 'what metabolites do my gene set hit
    most.' The gene-anchored mirror of GBM's `top_genes`.
    """
    metabolite_id: str = Field(
        description="Full prefixed Metabolite ID (e.g. 'kegg.compound:C00086').")
    name: str = Field(
        description="Metabolite display name (e.g. 'Urea').")
    formula: str | None = Field(
        default=None,
        description="Hill-notation formula (e.g. 'CH4N2O'); null on ~9% of "
        "metabolites (transport-only ChEBI generics).")
    gene_count: int = Field(
        description="Distinct input genes touching this metabolite via either "
        "arm.")
    reaction_count: int = Field(
        description="Distinct Reactions in the filtered metabolism arm "
        "connecting this metabolite to input genes. 0 when the metabolite "
        "is reachable only via the transport arm.")
    transporter_count: int = Field(
        description="Distinct TcdbFamily nodes (transport arm). 0 when "
        "reachable only via the metabolism arm.")
    metabolism_rows: int = Field(
        description="Metabolism-arm row count for this metabolite.")
    transport_substrate_confirmed_rows: int = Field(
        description="Transport-arm row count at `tc_specificity` (substrate-"
        "curated). High-precision.")
    transport_family_inferred_rows: int = Field(
        description="Transport-arm row count at coarser TCDB levels (rolled "
        "up; lower-precision).")


class MbgTopReaction(BaseModel):
    """Top-N (truncated to 10) reactions by gene_count in the metabolism arm.
    Identical shape to GBM's `GbmTopReaction`.
    """
    reaction_id: str = Field(
        description="Full prefixed Reaction ID (e.g. 'kegg.reaction:R00131').")
    name: str = Field(
        description="Reaction systematic name + KEGG equation (raw KEGG; "
        "may be empty `''` for 32 reactions).")
    ec_numbers: list[str] = Field(
        description="EC classification(s); empty list for 107/2,349 reactions "
        "without EC.")
    gene_count: int = Field(
        description="Distinct input genes catalyzing this reaction in the "
        "filtered slice.")
    metabolite_count: int = Field(
        description="Distinct metabolites this reaction connects to in the "
        "filtered slice.")


class MbgTopTcdbFamily(BaseModel):
    """Top-N (truncated to 10) TCDB families by gene_count in transport rows.
    Identical shape to GBM's `GbmTopTcdbFamily`.
    """
    tcdb_family_id: str = Field(
        description="Full prefixed TcdbFamily ID (e.g. 'tcdb:3.A.1.4.5').")
    tcdb_family_name: str = Field(
        description="Display name. tc_family-level entries are human-readable; "
        "tc_subfamily / tc_specificity fall back to the tcdb_id.")
    level_kind: str = Field(
        description="One of tc_class / tc_subclass / tc_family / tc_subfamily "
        "/ tc_specificity. Determines `transport_confidence`.")
    transport_confidence: Literal["substrate_confirmed", "family_inferred"] = Field(
        description="Derived from level_kind: 'substrate_confirmed' iff "
        "level_kind == 'tc_specificity'.")
    gene_count: int = Field(
        description="Distinct input genes annotated to this family in the "
        "filtered transport-row slice.")
    metabolite_count: int = Field(
        description="Distinct metabolites this family transports in the "
        "filtered slice.")


class MbgTopGeneCategory(BaseModel):
    """Top-N (truncated to 10) `Gene.gene_category` values by gene_count
    over the input gene set. Identical shape to GBM's `GbmTopGeneCategory`.
    """
    category: str = Field(
        description="Curated Gene.gene_category value (use "
        "`list_filter_values(filter_type=\"gene_category\")` for valid set).")
    gene_count: int = Field(
        description="Distinct input genes in this category contributing rows "
        "in the filtered slice.")


class MbgTopPathway(BaseModel):
    """NEW — Top-N (truncated to 10) KEGG pathways the gene set's chemistry
    reaches. Pathway namespace explicitly distinct from gene-KO pathway
    annotations available via `genes_by_ontology(ontology="kegg")`.

    Source: UNION of `Reaction_in_kegg_pathway` (reaction-side) +
    `Metabolite_in_pathway` (metabolite-side, via reaction-arm metabolites
    OR transport-arm metabolites). Filter `WHERE p.reaction_count >= 3`
    drops signaling/disease pathways with no chemistry breadth.
    Rank: `gene_count DESC, p.reaction_count ASC` (more genes hitting +
    more focused pathway).
    """
    pathway_id: str = Field(
        description="Full prefixed KEGG pathway ID (e.g. 'kegg.pathway:ko00910').")
    pathway_name: str = Field(
        description="Pathway display name (e.g. 'Nitrogen metabolism').")
    gene_count: int = Field(
        description="Distinct input genes with ≥1 chemistry edge into this "
        "pathway (via reaction-side or metabolite-side).")
    pathway_reaction_count: int = Field(
        description="Total reactions in this pathway in the KG (KG-4 rollup, "
        "100% on pathway-level entries). At-a-glance pathway sizing.")
    pathway_metabolite_count: int = Field(
        description="Total metabolites in this pathway in the KG (KG-4 rollup).")


class MbgNotFound(BaseModel):
    """Diagnostics for inputs that did not resolve to any KG node.

    See also `not_matched` (top-level field on the response): locus_tags
    that DO resolve to a Gene in the requested organism but produce zero
    rows — different concept.
    """
    locus_tags: list[str] = Field(
        default_factory=list,
        description="Input locus_tags that don't resolve to any Gene in the "
        "requested organism (typo, wrong organism, gene removed in KG rebuild).")
    organism: str | None = Field(
        default=None,
        description="Set to the input string when fuzzy-match resolves to "
        "zero genes for the input locus_tags. None on success.")
    metabolite_ids: list[str] = Field(
        default_factory=list,
        description="Input metabolite_ids that don't exist as a Metabolite "
        "node (typo, wrong prefix, ChEBI ID not in our KG).")
    metabolite_pathway_ids: list[str] = Field(
        default_factory=list,
        description="Input metabolite_pathway_ids that don't exist as a "
        "KeggTerm node.")
    metabolite_elements: list[str] = Field(
        default_factory=list,
        description="Input element symbols that don't appear on any KG "
        "Metabolite (typo, lowercase).")
```

---

## Per-arm filter scope semantics

Mirrors `genes_by_metabolite` exactly:

| Filter | Metabolism arm | Transport arm |
|---|---|---|
| `locus_tags` (anchor) | yes | yes |
| `organism` (anchor) | yes | yes |
| `metabolite_elements` | yes (uniform via `m.elements`) | yes (uniform via `m.elements`) |
| `metabolite_ids` | yes (uniform) | yes (uniform) |
| `ec_numbers` | yes | **no — pass-through** |
| `mass_balance` | yes | **no — pass-through** |
| `metabolite_pathway_ids` | yes (uniform via `m.pathway_ids`) | yes (uniform via `m.pathway_ids`) |
| `gene_categories` | yes (uniform via `g.gene_category`) | yes (uniform) |
| `transport_confidence` | **no — pass-through** | yes (`tf.level_kind` discriminator) |
| `evidence_sources` | arm selector (skips arm) | arm selector (skips arm) |

**Single-arm restriction is explicit**: pass `evidence_sources=['metabolism']`
or `evidence_sources=['transport']`. Path-scoped filters (ec_numbers,
mass_balance, transport_confidence) **do not implicitly suppress the other arm**;
they narrow within their arm only. Predictable + composable.

---

## Sort order

Detail rows sorted by:

1. **Precision tier** (primary): `metabolism` → `transport_substrate_confirmed`
   → `transport_family_inferred`. Surfaces high-precision rows from the entire
   batch first, regardless of input position. Critical for batch DE inputs
   where a single ABC-superfamily-only gene at position 0 would otherwise
   eat the entire `limit=10` with 551 family_inferred rows.
2. **Input gene order** (secondary): preserves caller intent within precision tier.
3. **`locus_tag`** (tertiary): stable secondary order within input-tied rows.
4. **`metabolite_id`** (quaternary): stable final order.

Implementation: in the detail Cypher, RETURN with `ORDER BY <precision_tier>, <input_index>, locus_tag, metabolite_id`.
The input index is computed via `apoc.coll.indexOf($locus_tags, g.locus_tag)`
or equivalently a `WITH $locus_tags AS input_tags ... ORDER BY ... apoc.coll.indexOf(input_tags, g.locus_tag)`.

---

## Verified Cypher

All probes verified against live KG 2026-05-03. Prochlorococcus MED4 used as
canonical organism.

### 1. Detail query (single-gene metabolism + transport, baseline shape)

```cypher
// Inputs: $locus_tags = ['PMM0963', 'PMM0970'], $org = "Prochlorococcus MED4"
// Expected: 4 metabolism rows (PMM0963 × R00131 × {Urea, H2O, CO2, NH3})
//           + 3 transport rows (PMM0970 × {3.A.1.4.4, 3.A.1.4.5, 3.A.1}) × 1 metabolite (urea)

CALL {
  // Metabolism arm
  MATCH (g:Gene {organism_name: $org})-[:Gene_catalyzes_reaction]->(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)
  WHERE g.locus_tag IN $locus_tags
  RETURN g, r, NULL AS tf, m, 'metabolism' AS evidence_source, NULL AS transport_confidence
  UNION
  // Transport arm
  MATCH (g:Gene {organism_name: $org})-[:Gene_has_tcdb_family]->(tf:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)
  WHERE g.locus_tag IN $locus_tags
  RETURN g, NULL AS r, tf, m,
         'transport' AS evidence_source,
         CASE WHEN tf.level_kind = 'tc_specificity'
              THEN 'substrate_confirmed' ELSE 'family_inferred' END AS transport_confidence
}
WITH g, r, tf, m, evidence_source, transport_confidence,
     CASE evidence_source
       WHEN 'metabolism' THEN 0
       ELSE CASE transport_confidence
              WHEN 'substrate_confirmed' THEN 1
              ELSE 2 END
     END AS precision_tier
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name, g.product AS product,
       evidence_source, transport_confidence,
       r.id AS reaction_id, r.name AS reaction_name, r.ec_numbers AS ec_numbers, r.mass_balance AS mass_balance,
       tf.id AS tcdb_family_id, tf.name AS tcdb_family_name,
       m.id AS metabolite_id, m.name AS metabolite_name,
       m.formula AS metabolite_formula, m.mass AS metabolite_mass, m.chebi_id AS metabolite_chebi_id
ORDER BY precision_tier,
         apoc.coll.indexOf($locus_tags, locus_tag),
         locus_tag,
         metabolite_id
SKIP $offset
LIMIT $limit
```

**Verified output for `$locus_tags = ['PMM0963','PMM0964','PMM0965','PMM0970']`:**
- 12 metabolism rows (3 ureA/B/C × R00131 × 4 metabolites) followed by
- 3 transport rows (PMM0970 × {3.A.1.4.4 substrate_confirmed, 3.A.1.4.5
  substrate_confirmed, 3.A.1 family_inferred} × Urea)
- Metabolism rows precede transport rows; substrate_confirmed precedes
  family_inferred.

### 2. Summary aggregation query

```cypher
// Same UNION as detail query, but aggregate immediately
CALL {
  MATCH (g:Gene {organism_name: $org})-[:Gene_catalyzes_reaction]->(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)
  WHERE g.locus_tag IN $locus_tags
  RETURN g, r, NULL AS tf, m, 'metabolism' AS evidence_source, NULL AS transport_confidence
  UNION
  MATCH (g:Gene {organism_name: $org})-[:Gene_has_tcdb_family]->(tf:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)
  WHERE g.locus_tag IN $locus_tags
  RETURN g, NULL AS r, tf, m,
         'transport' AS evidence_source,
         CASE WHEN tf.level_kind = 'tc_specificity'
              THEN 'substrate_confirmed' ELSE 'family_inferred' END AS transport_confidence
}
RETURN
  count(*) AS total_matching,
  count(DISTINCT g) AS gene_count_total,
  count(DISTINCT r) AS reaction_count_total,
  count(DISTINCT tf) AS transporter_count_total,
  count(DISTINCT m) AS metabolite_count_total
```

`total_matching` from this query MUST equal the row count of the detail
query without `LIMIT`. Verified for urease + urtA test case.

### 3. by_gene rollup

```cypher
// Per-input-gene aggregation. One entry per locus_tag with ≥1 row.
// Driven by the same UNION; aggregated to gene level.
CALL { ... same UNION as detail ... }
WITH g, evidence_source, transport_confidence, r, tf, m
WITH g.locus_tag AS locus_tag, g.gene_name AS gene_name, g.product AS product,
     count(*) AS rows,
     count(DISTINCT m) AS metabolite_count,
     count(DISTINCT CASE WHEN evidence_source = 'metabolism' THEN r END) AS reaction_count,
     count(DISTINCT CASE WHEN evidence_source = 'transport' THEN tf END) AS transporter_count,
     sum(CASE WHEN evidence_source = 'metabolism' THEN 1 ELSE 0 END) AS metabolism_rows,
     sum(CASE WHEN transport_confidence = 'substrate_confirmed' THEN 1 ELSE 0 END) AS transport_substrate_confirmed_rows,
     sum(CASE WHEN transport_confidence = 'family_inferred' THEN 1 ELSE 0 END) AS transport_family_inferred_rows
RETURN locus_tag, gene_name, product, rows, metabolite_count, reaction_count, transporter_count,
       metabolism_rows, transport_substrate_confirmed_rows, transport_family_inferred_rows
ORDER BY apoc.coll.indexOf($locus_tags, locus_tag)
```

### 4. top_metabolites rollup

```cypher
// Same UNION; aggregate to metabolite level; rank by gene reach.
CALL { ... same UNION as detail ... }
WITH m.id AS metabolite_id, m.name AS name, m.formula AS formula,
     count(*) AS total_rows,
     count(DISTINCT g) AS gene_count,
     count(DISTINCT CASE WHEN evidence_source = 'metabolism' THEN r END) AS reaction_count,
     count(DISTINCT CASE WHEN evidence_source = 'transport' THEN tf END) AS transporter_count,
     sum(CASE WHEN evidence_source = 'metabolism' THEN 1 ELSE 0 END) AS metabolism_rows,
     sum(CASE WHEN transport_confidence = 'substrate_confirmed' THEN 1 ELSE 0 END) AS transport_substrate_confirmed_rows,
     sum(CASE WHEN transport_confidence = 'family_inferred' THEN 1 ELSE 0 END) AS transport_family_inferred_rows
RETURN metabolite_id, name, formula, gene_count, reaction_count, transporter_count,
       metabolism_rows, transport_substrate_confirmed_rows, transport_family_inferred_rows
ORDER BY gene_count DESC, total_rows DESC, metabolite_id ASC
LIMIT 10
```

### 5. top_pathways rollup (NEW, verified)

```cypher
// UNION of reaction-side + metabolite-side pathways (both arms),
// filtered to chemistry pathways (reaction_count >= 3),
// ranked by input-gene reach + pathway specificity.
CALL {
  // Reaction-side pathways via metabolism arm
  MATCH (g:Gene {organism_name: $org})-[:Gene_catalyzes_reaction]->(:Reaction)-[:Reaction_in_kegg_pathway]->(p:KeggTerm)
  WHERE g.locus_tag IN $locus_tags
  RETURN g.locus_tag AS locus_tag, p.id AS pathway_id
  UNION
  // Metabolite-side pathways via metabolism arm
  MATCH (g:Gene {organism_name: $org})-[:Gene_catalyzes_reaction]->(:Reaction)-[:Reaction_has_metabolite]->(:Metabolite)-[:Metabolite_in_pathway]->(p:KeggTerm)
  WHERE g.locus_tag IN $locus_tags
  RETURN g.locus_tag AS locus_tag, p.id AS pathway_id
  UNION
  // Metabolite-side pathways via transport arm
  MATCH (g:Gene {organism_name: $org})-[:Gene_has_tcdb_family]->(:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(:Metabolite)-[:Metabolite_in_pathway]->(p:KeggTerm)
  WHERE g.locus_tag IN $locus_tags
  RETURN g.locus_tag AS locus_tag, p.id AS pathway_id
}
WITH pathway_id, count(DISTINCT locus_tag) AS gene_count
MATCH (p:KeggTerm {id: pathway_id})
WHERE p.reaction_count >= 3   // Chemistry-pathway filter
RETURN p.id AS pathway_id, p.name AS pathway_name, gene_count,
       p.reaction_count AS pathway_reaction_count,
       p.metabolite_count AS pathway_metabolite_count
ORDER BY gene_count DESC, p.reaction_count ASC, p.id ASC
LIMIT 10
```

**Verified output for `[PMM0963, PMM0964, PMM0965]`:** Top 10 includes
Nitrogen cycle, Cyanoamino acid metabolism, Biotin metabolism, Calvin cycle,
**Nitrogen metabolism**, **Arginine biosynthesis**, Alanine/aspartate/glutamate
metabolism — all chemistry-meaningful. Without the `reaction_count >= 3`
filter, "Vasopressin water reabsorption" and "Helicobacter signaling" would
rank above "Nitrogen metabolism".

### 6. by_element rollup (NEW, verified)

```cypher
// Distinct elements across metabolites the gene set touches via either arm.
CALL {
  MATCH (g:Gene {organism_name: $org})-[:Gene_catalyzes_reaction]->(:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)
  WHERE g.locus_tag IN $locus_tags
  RETURN m
  UNION
  MATCH (g:Gene {organism_name: $org})-[:Gene_has_tcdb_family]->(:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)
  WHERE g.locus_tag IN $locus_tags
  RETURN m
}
WITH DISTINCT m
WHERE size(m.elements) > 0
UNWIND m.elements AS element
RETURN element, count(DISTINCT m) AS metabolite_count
ORDER BY metabolite_count DESC, element ASC
```

**Verified output for `[PMM0963, PMM0964, PMM0965]`:**
`[{H, 3}, {O, 3}, {C, 2}, {N, 2}]`.

### 7. Per-arm filter scope (verified)

```cypher
// Setup: ureA/B/C (metabolism) + urtA/B/C (transport) × MED4
// Apply ec_numbers=['3.5.1.5'] — should narrow metabolism only

// With EC filter, metabolism arm: 12 rows ✓
// Baseline metabolism arm: 12 rows ✓ (urtA/B/C contribute 0 to metabolism arm)
// Transport arm with EC filter applied (should be unchanged): 12 rows ✓
```

Confirms `ec_numbers` is metabolism-arm only; transport rows pass through
unchanged. Same mechanic as GBM. Verified analogously for `mass_balance`
(metabolism only) and `transport_confidence` (transport only).

### 8. Edge case: gene with zero chemistry edges

```cypher
// PMM0005 (DNA gyrase) — annotation_state='informative_multi' but zero chemistry
MATCH (g:Gene {organism_name: "Prochlorococcus MED4", locus_tag: "PMM0005"})
OPTIONAL MATCH (g)-[r:Gene_catalyzes_reaction]->()
OPTIONAL MATCH (g)-[t:Gene_has_tcdb_family]->()
RETURN count(r) AS metab_edges, count(t) AS transp_edges
// → metab_edges=0, transp_edges=0
```

→ Goes to `not_matched` (resolved in organism, no chemistry edges).

### 9. Edge case: nonexistent locus_tag

```cypher
MATCH (g:Gene {organism_name: "Prochlorococcus MED4"})
WHERE g.locus_tag = "PMM9999"
RETURN g
// → 0 rows
```

→ Goes to `not_found.locus_tags` (no Gene node matched in this organism).

### 10. Edge case: mixed batch (found + not_found + not_matched)

```cypher
// Input: ['PMM0963' (chemistry-rich), 'PMM0005' (no chemistry), 'PMM9999' (nonexistent)]
// Expected behavior:
//   PMM0963 → produces ~4 rows
//   PMM0005 → not_matched
//   PMM9999 → not_found.locus_tags
// total_matching = 4; not_matched = ['PMM0005']; not_found.locus_tags = ['PMM9999']
```

Standard batch tool semantics (mirror GBM, list_metabolites).

---

## Edge cases / empty-result distinctions (Pass A rubric)

| Scenario | Bucket |
|---|---|
| Input locus_tag malformed / not in KG / wrong organism | `not_found.locus_tags` |
| Input locus_tag resolves but has zero chemistry edges (e.g. PMM0005) | `not_matched` |
| Input organism unknown / fuzzy-match yields zero genes | `not_found.organism` |
| Input metabolite_pathway_id not a KeggTerm | `not_found.metabolite_pathway_ids` |
| Input element symbol not on any KG metabolite | `not_found.metabolite_elements` |
| Input metabolite_id not a Metabolite node | (added: `not_found.metabolite_ids`) |
| All input filters yield zero rows but inputs were valid | `total_matching=0`, all rollups empty, `results=[]`, no `not_*` populated |

### Data sparsity (mirror GBM)

- **Reactions with empty `name`** (32/2,349). Surfaces as `reaction_name=''`
  on metabolism rows. Both `top_reactions` envelope and detail rows display.
- **Metabolites without `formula`** (31/2,188). `formula=None`,
  `elements=[]`, `mass=None`. `metabolite_elements` filter excludes these
  rows; `by_element` rollup ignores them (graceful).
- **Genes without `gene_name`** — common, sparse-result design handles.
- **Genes without `gene_category`** — `top_gene_categories` and `by_gene`
  surface them under a `null`/missing key (consistent with GBM).
- **Pathway-scope asymmetry** (load-bearing): R00131 has zero
  `Reaction_in_kegg_pathway` edges. The metabolite-side join in
  `top_pathways` is the only way these reactions surface in pathway rollups.

### family_inferred-dominance auto-warning (mirror GBM)

When transport rows are family_inferred majority AND `transport_confidence`
was not set explicitly, emit:
> `"Transport rows in this slice are dominated by `family_inferred` rollup
> (X of Y transport rows). For high-precision substrate-curated annotations
> only, set `transport_confidence='substrate_confirmed'` and/or
> `evidence_sources=['transport']`."`

The 9 ABC-superfamily-only MED4 genes will reliably trigger this when
present in input.

---

## Workflows

### Workflow A — N sources MED4 uses (marquee)

```
1. differential_expression_by_gene(
     organism="Prochlorococcus MED4",
     experiment_ids=[N-limitation experiment IDs],
     direction="up", significant_only=True
   )
   → DE gene set (~50-200 locus_tags)

2. metabolites_by_gene(
     locus_tags=DE_genes,
     organism="Prochlorococcus MED4",
     metabolite_elements=["N"]
   )
   → triplet rows (gene × reaction × N-metabolite),
   summary `top_metabolites` ranks N-metabolites by gene breadth,
   `top_pathways` answers "which N-pathways concentrate" (Nitrogen
   metabolism, Arginine biosynthesis, AA biosynthesis, …).

3. (Optional) Drill-down on top_metabolites:
   list_metabolites(metabolite_ids=[top_N_metabolite_ids])
   → cross-refs, mass, formula, full pathway names

4. (Optional) Cross-organism check:
   list_metabolites(metabolite_ids=[top_ids], organism_names=["Alteromonas..."])
   → presence in partner organism (cross-feeding seed)
```

**With N-limitation DE input expected to be 50-200 genes, use `summary=True`**
or `transport_confidence='substrate_confirmed'` to bound row volume.

### Workflow C — Gene-set chemistry characterization (cluster / function-search)

```
1. genes_in_cluster(cluster_id=...) or genes_by_function(query=...)
   → gene set (~10-100 locus_tags)

2. metabolites_by_gene(locus_tags=set, organism=...)
   → top_pathways = "what pathways does this set sit in"
   → by_element = C/N/P/S signature
   → top_metabolites = specific compounds

3. top_pathways drill-down:
   list_metabolites(pathway_ids=[top_pathway_id]) → full pathway metabolites
```

### Workflow B' — Cross-feeding gene set (MBG → GBM bridge)

```
1. differential_expression_by_gene(MED4 coculture-up genes)
   → MED4 DE gene set

2. metabolites_by_gene(locus_tags=MED4_DE, organism="Prochlorococcus MED4")
   → top_metabolites = "metabolites my upregulated MED4 genes deal in"

3. genes_by_metabolite(
     metabolite_ids=[from top_metabolites],
     organism="Alteromonas macleodii ..."
   )
   → "do those metabolites have catalysts/transporters in Alteromonas"
```

### Workflow D — Single-gene drill-down

```
metabolites_by_gene(locus_tags=["PMM0913"], organism="Prochlorococcus MED4")
→ ~4-12 rows; envelope rollups mostly noise at n=1; detail rows answer
```

---

## File-by-file build skeleton

Per `add-or-update-tool` skill, 4 layers + tests:

### Layer 1 — Query builder
**File:** `multiomics_explorer/kg/queries_lib.py`
**Function:** `build_metabolites_by_gene(locus_tags, organism, metabolite_elements=None, metabolite_ids=None, ec_numbers=None, metabolite_pathway_ids=None, mass_balance=None, gene_categories=None, transport_confidence=None, evidence_sources=None, summary=False, limit=10, offset=0) -> tuple[str, dict]`

Returns `(cypher, params)`. Internally constructs the two-arm UNION + filters
+ ORDER BY based on summary/detail mode. May produce multiple Cypher strings
if api/ orchestrates separate detail / summary / by_gene / top_metabolites /
top_pathways / by_element queries (mirror GBM's pattern).

### Layer 2 — API function
**File:** `multiomics_explorer/api/functions.py`
**Function:** `metabolites_by_gene(connection, locus_tags, organism, ...) -> dict`

Multi-query orchestration (mirror GBM's `genes_by_metabolite`):
1. Resolve organism (fuzzy match)
2. Issue detail query OR summary query (per mode)
3. Issue rollup queries: by_gene, top_metabolites, top_reactions,
   top_tcdb_families, top_gene_categories, top_pathways, by_element,
   by_evidence_source, by_transport_confidence
4. Compute not_found buckets + not_matched
5. Compute family_inferred-dominance warning if applicable
6. Assemble envelope dict matching `MetabolitesByGeneResponse` shape

### Layer 3 — MCP wrapper
**File:** `multiomics_explorer/mcp_server/tools.py`

Pydantic models (new):
- `MbgByGene`, `MbgByEvidenceSource`, `MbgByTransportConfidence`,
  `MbgByElement` (new), `MbgTopMetabolite`, `MbgTopReaction`,
  `MbgTopTcdbFamily`, `MbgTopGeneCategory`, `MbgTopPathway` (new),
  `MbgNotFound`, `MetabolitesByGeneResponse`

Reuse module-level `GeneReactionMetaboliteTriplet` (already defined for GBM).

`@mcp.tool` wrapper at end of `register_tools()`. Update `EXPECTED_TOOLS`.

### Layer 4 — About content (YAML → generated md)
**File:** `multiomics_explorer/inputs/tools/metabolites_by_gene.yaml`

Sections: `examples` (urease, transporter set, DE batch with N-source filter,
single-gene drill-down), `mistakes` (single-organism only, evidence_sources
metabolomics rejection, family_inferred-dominance, gene_categories
redundancy with locus_tags, EC filter is metabolism-only, top_pathways
naming disambiguation from gene-KO), `chaining` (DE → MBG, cluster → MBG,
MBG → GBM cross-feeding, MBG top_pathways → list_metabolites, MBG → list_metabolites
cross-organism), `verbose_fields` (gene_category, metabolite cross-refs,
reaction cross-refs, tcdb_level_kind, tc_class_id).

After edits: `uv run python scripts/build_about_content.py`

### Tests

Per `testing` skill:

- `tests/unit/test_query_builders.py` — `TestBuildMetabolitesByGene`:
  empty input → query well-formed; each filter contributes correct WHERE
  fragment; UNION two-arm structure; sort order has precision_tier first;
  `evidence_sources=['metabolism']` skips transport arm in builder output;
  pagination params honored; summary mode returns no detail-shape query.
- `tests/unit/test_api_functions.py` — `TestMetabolitesByGene`: stub
  connection returns mocked rows; assert envelope shape matches
  `MetabolitesByGeneResponse`; `not_found` / `not_matched` populated
  correctly under mixed batch; family_inferred-dominance warning fires
  when expected.
- `tests/unit/test_tool_wrappers.py` — `TestMetabolitesByGeneWrapper`:
  Pydantic field-rubric compliance (real-value examples in Field
  descriptions, drill-down clauses, sparse fields documented,
  direction-agnostic caveat in docstring, top_pathways naming
  disambiguation in docstring, `verbose=False` toggles correct field set).
  Update `EXPECTED_TOOLS`, `TOOL_BUILDERS`.
- `tests/integration/test_kg_metabolites_by_gene.py` (`-m kg`):
  - `[PMM0963, PMM0964, PMM0965, PMM0970]` × MED4 → assert 12+3 row split,
    expected top_metabolites/top_pathways/by_element values
  - DE-batch fixture (50-100 locus_tags) with summary=True → assert
    envelope shape + reasonable rollup populations
  - `[PMM0005]` (no chemistry) → `not_matched=['PMM0005']`
  - `[PMM9999]` (nonexistent) → `not_found.locus_tags=['PMM9999']`
- `tests/regression/baselines/metabolites_by_gene/` — 6-10 representative
  queries, snapshot baselines via `--force-regen` workflow.

### Documentation
- `CLAUDE.md` MCP tool table — add `metabolites_by_gene` row
- `gene_overview` row description — drill-down clause should now mention
  both `genes_by_metabolite` (when caller has metabolite IDs) AND
  `metabolites_by_gene` (when starting from gene IDs). Same backlog item
  as the GBM spec.

---

## Forward-compatibility notes

- **Metabolomics-DM landing.** No change here — metabolomics evidence has
  no gene anchor, so it never produces rows in this tool. `evidence_sources`
  Literal stays `{metabolism, transport}`. The forward-compat slot lives in
  `list_metabolites`.
- **TCDB-CAZy schema extensions.** Already shipped. No further changes
  expected for slice 1.
- **`Gene.catalytic_activities` direction-aware reaction parsing.** Future
  spec opportunity — could add `direction` per metabolism row (substrate /
  product). Sparse addition to existing row class; transport rows keep null;
  no breaking change.
- **F1 annotation-quality enrichment of `not_matched`.** Out of slice-1
  scope (cross-cutting design across MCP surface). If/when added, would
  enrich `not_matched: list[str]` to `list[{locus_tag, annotation_state}]`
  + an envelope rollup. Sparse addition; no breaking change to existing
  consumers.
- **`top_pathways` ranking refinements.** If gene-KO pathway membership becomes
  available as a third source for `top_pathways` (currently disjoint via
  `genes_by_ontology(ontology="kegg")`), could UNION as a fourth subquery
  with provenance tracking. Out of slice 1.

## Open questions / risks

No open questions blocking Phase 2 build.

**Risks:**

- **`top_pathways` `reaction_count >= 3` threshold may be too aggressive
  for narrow pathway specs.** If a real workflow turns up evidence of
  legitimate 1-2-reaction pathways being suppressed, lower the threshold
  to `>= 1` and accept the noise — or add a per-call override. Tracked as
  a tunable; default chosen for the urease example's chemistry-noise
  reduction.
- **Default `limit=10` may be undersized for batch DE inputs even with the
  precision-tier sort.** A 200-gene DE input with 10 ABC-only genes gets
  ~5,510 family_inferred transport rows. Even sorted last, the user may want
  a higher metabolism-row default. Mitigation: `summary=True` is documented
  as the recommended pattern for batch DE; if this becomes a friction
  point, raise default to 25 or split the limit per evidence_source.
- **Long-tail ABC-superfamily noise** is the same risk as GBM's, manifesting
  per-gene-side instead of per-metabolite-side. Mitigations identical:
  precision-tier sort, family_inferred-dominance auto-warning,
  `transport_confidence='substrate_confirmed'` filter, `evidence_sources`
  arm selector.
- **Per-input-order sort within precision tier** uses `apoc.coll.indexOf` —
  if APOC is unavailable on a target deployment, fall back to alphabetical
  locus_tag sort. Currently APOC is available in the dev KG; spec assumes
  this remains true for production deployments.

## Resolved decisions

- **Tool 3 naming locked: `metabolites_by_gene`** (slice-1 design's
  `gene_metabolic_role` superseded for symmetry with `genes_by_metabolite`).
- **Shared row class `GeneReactionMetaboliteTriplet`** reused verbatim
  (already module-level in `mcp_server/tools.py`).
- **Pydantic prefix `Mbg*`** — tool-anchored convention (mixed-entity
  envelope: gene-anchored `by_gene`, metabolite-anchored `top_metabolites`,
  reaction-anchored `top_reactions`, TCDB-anchored `top_tcdb_families`,
  pathway-anchored `top_pathways`, element-anchored `by_element`).
  No single entity prefix covers all of them; mirror GBM's `Gbm*` pattern.
- **`evidence_sources` Literal** — `{"metabolism", "transport"}` only,
  matches GBM. Metabolomics evidence has no gene anchor.
- **`metabolite_elements` filter** — single gene-anchored filter addition.
  AND-of-presence semantics (matches `list_metabolites.elements`).
  Hill-parsed `m.elements` — never substring-match on `formula`.
- **`top_pathways` envelope addition** — name mirrors `list_metabolites.top_pathways`
  for cross-tool consistency. Disambiguation from gene-KO-mediated pathway
  annotations lives in the docstring + drill-down clauses, not in the field
  name. Source = UNION of reaction-side + metabolite-side; chemistry-pathway
  filter (`p.reaction_count >= 3`); rank `gene_count DESC, p.reaction_count ASC`.
  Pathway scope asymmetry (R00131 has zero reaction-side pathway edges)
  makes the metabolite-side join load-bearing.
- **`by_element` envelope addition** — free Cypher (uses `m.elements`);
  full rollup; periodic-table-bounded; no top-N truncation.
- **Sort order** — global precision-first (metabolism →
  transport_substrate_confirmed → transport_family_inferred), then input
  gene order, then locus_tag, then metabolite_id. Diverges from per-input-order-first
  to prevent ABC-superfamily-only genes at position 0 from eating `limit=10`
  with family_inferred rows.
- **Default `limit=10`** — cross-tool consistency with GBM, covers ~p70
  of single-gene UNION distribution in MED4.
- **`gene_count_with_chemistry` counter dropped** — derivable from
  `len(input) - len(not_matched)`; covered by `metabolite_count_total`.
- **`top_ec_classes` rollup dropped** — derivable client-side from
  `top_reactions[].ec_numbers` first-digit.
- **Per-row pathway field on triplet dropped** — keeps shared row class
  unchanged; per-row pathway info lives in `list_metabolites(metabolite_ids=...)`.
- **`UNION` inside detail Cypher** — accepted (mirror current GBM
  implementation; the api/ layer can split if profiling motivates).
- **`metabolite_pathway_ids` filter naming** — mirror GBM exactly. Disambiguation
  prefix for the gene-anchored tool; KG property `m.pathway_ids` unchanged.
- **`metabolite_ids` filter included** — useful for cross-feeding workflow
  (Workflow B') where caller wants to restrict MBG output to a specific
  metabolite set. Cheap addition; uniform across both arms.
- **`transport_confidence` filter wording** — mirror GBM exactly, with
  added sentence about MBG-specific 551-row blowup mitigation in batch DE.

## References

- Slice-1 design doc: `docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md`
  (§ 2.3 = Tool 3 = this spec)
- KG asks doc (slice 1): `docs/superpowers/specs/2026-05-01-kg-side-chemistry-slice1-asks.md`
- Follow-up KG asks: `docs/superpowers/specs/2026-05-02-kg-side-chemistry-slice1-followup-asks.md`
- KG release F1-F4 (annotation_state, etc.): `multiomics_biocypher_kg/docs/kg-changes/2026-05-01-explorer-frictions-f1-f4.md`
- Sister spec: `docs/tool-specs/genes_by_metabolite.md` (Tool 2, frozen + shipped 2026-05-03)
- Sister spec: `docs/tool-specs/list_metabolites.md` (Tool 1, frozen + shipped 2026-05-03)
- Add-or-update-tool skill: `.claude/skills/add-or-update-tool/SKILL.md`
- Layer rules: `.claude/skills/layer-rules/`
- Testing patterns: `.claude/skills/testing/`
