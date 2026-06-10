# Tool spec: Publication "discusses" literature-index surface

Mode B (cross-tool): **1 new tool** + **3 existing-tool extensions**, over the two new
`discusses` relationship types now live in the KG.

> **Scope revision (this draft):** the originally-proposed standalone *reverse* router
> (gene/pathway → publications) was **dropped**. Distribution check: 89% of discussed
> genes are named by exactly 1 publication (avg 1.18, max 6), so the gene-side reverse
> lookup is answered inline by enriching `gene_overview` with the actual DOI(s) rather
> than a separate tool. The pathway-side reverse lookup is answered by enriching
> `search_ontology`. Only the **forward** tool remains standalone.

## Purpose

Surface the **Publication "discusses" edges** — a recall-biased narrative literature
index linking each publication to the genes and KEGG pathways it names in prose
(regulators, model genes, pathways discussed in text), distinct from the
supplementary DE-table expression data.

- `Publication_discusses_gene` (Publication → Gene), ~1,099 edges
- `Publication_discusses_kegg_pathway` (Publication → KeggTerm, pathway-level), ~140 edges

Both carry `prominence` (`central` | `peripheral`) and an extraction `evidence` quote.
Spread across **40 of 43** publications.

This is a **router**, not exhaustive coverage: 935 distinct genes named out of 120k.
Tool docs must set that expectation.

## Out of Scope

- Not a DE / expression surface — use `differential_expression_by_gene` for the
  supplementary-table expression data. The `discusses` edges are prose mentions only.
- No standalone reverse (gene/pathway → publications) tool — folded into `gene_overview`
  (gene arm, incl. `top_discussing_publications` batch set-coverage rollup) and
  `search_ontology` (pathway arm).
- Forward tool does NOT expand KEGG-pathway membership to genes; it returns the pathway
  terms the paper discusses, verbatim.
- No write path (repo is read-only).
- No new node/edge types needed — all edges + node rollups already live (KG built
  2026-06-09). **No KG-side spec required.**

## Status / Prerequisites

- [x] KG spec complete — N/A, edges + rollups already live
- [x] KG changes landed — verified live (`kg_release_info` ok, built 2026-06-09)
- [x] Scope reviewed with user (forward tool + 3 extensions; reverse tool dropped)
- [x] Result-size controls decided
- [x] **Frozen spec APPROVED 2026-06-09 — ready for Phase 2 (build)**

## Use cases

- "What does paper 10.1038/ismej.2016.70 discuss?" → `discussed_by_publication`
  (forward). Chains from `list_publications` (find DOIs) → `discussed_by_publication` →
  `gene_overview` / `genes_by_ontology(ontology='kegg')` (drill into entities).
- "Which paper discusses gene PMT1030?" → `gene_overview` (DOI carried inline,
  verbose). No separate tool needed at ~1 pub/gene.
- "Which papers discuss KEGG pathway ko00710?" → `search_ontology` (KEGG), reads the
  per-term DOI list (verbose).
- "Does this paper have a narrative literature index at all?" → `list_publications`
  per-pub `discussed_gene_count` / `discussed_pathway_count` + `by_discusses_coverage`.

## KG dependencies

| Element | Detail |
|---|---|
| `(:Publication)-[:Publication_discusses_gene {prominence, evidence}]->(:Gene)` | 1,099 edges, 100% populated |
| `(:Publication)-[:Publication_discusses_kegg_pathway {prominence, evidence}]->(:KeggTerm)` | 140 edges, all `level=2` (pathway), IDs `kegg.pathway:koXXXXX` |
| `Publication.discussed_gene_count`, `.discussed_pathway_count` | precomputed, match live edge counts exactly |
| `Gene.discussed_in_publication_count` | precomputed |
| `Gene.locus_tag`, `.organism_name` | anchor + grouping |
| `Publication.doi`, `.title`, `.publication_year`, `.authors` | identity (prop is `doi`, not `publication_doi`) |
| `KeggTerm.id`, `.name`, `.level` | pathway identity (no precomputed discusses count → pattern-count) |

---

# Tool (new): `discussed_by_publication` — forward lookup

## Tool Signature

```python
@mcp.tool(tags={"publications", "literature"}, annotations={"readOnlyHint": True})
async def discussed_by_publication(
    ctx: Context,
    publication_dois: Annotated[list[str], Field(
        description="Publication DOIs (e.g. ['10.1038/ismej.2016.70']).")],
    entity_kind: Annotated[Literal["gene", "kegg_pathway"] | None, Field(
        description="Restrict to one arm: 'gene' or 'kegg_pathway'. None = both.")] = None,
    prominence: Annotated[Literal["central", "peripheral"] | None, Field(
        description="Filter edges by prominence: 'central' or 'peripheral'.")] = None,
    summary: Annotated[bool, Field(description="Return only summary fields.")] = False,
    verbose: Annotated[bool, Field(description="Include the full evidence quote.")] = False,
    limit: Annotated[int, Field(description="Max detail rows.", ge=0)] = 50,
    offset: Annotated[int, Field(description="Skip this many detail rows (pagination).", ge=0)] = 0,
) -> DiscussedByPublicationResponse:
    """List the genes and KEGG pathways a publication discusses in prose.

    Recall-biased literature router (narrative mentions, NOT exhaustive, NOT DE-table
    expression data). Routing: feed DOIs from list_publications; drill returned genes
    into gene_overview and pathways into genes_by_ontology(ontology='kegg').
    """
```

**Per-result columns (compact):** `doi`, `entity_kind` (`gene`|`kegg_pathway`),
`entity_id` (locus_tag or `kegg.pathway:koXXXXX`), `entity_name`
(gene **`gene_name`**, falling back to `product` when the gene has no symbol —
`coalesce(g.gene_name, g.product)`; pathway `name` — consistently the entity's
readable name), `organism` (gene `organism_name`; explicit `None` on pathway rows
— union padding), `prominence`.
**Verbose adds:** `evidence` (the extraction quote).

## Result-size controls — Option B (batch input)

#### Summary fields (always returned)

| Field | Type | Description |
|---|---|---|
| total_entries | int | All discusses edges from matched DOIs, **before** `entity_kind`/`prominence` filters |
| total_matching | int | Rows after `entity_kind` / `prominence` filters |
| returned, truncated | int/bool | Standard envelope |
| by_entity_kind | dict | `{gene, kegg_pathway}` row counts of the **filtered** (`total_matching`) set |
| by_prominence | dict | `{central, peripheral}` row counts of the **filtered** (`total_matching`) set |
| top_kegg_pathways | list | discussed KEGG pathways across the input DOIs, by mention count (id, name, n) |
| top_publications | list | input DOIs ranked by their discussed-edge count (gene + pathway), surfacing the densest narrative index in a batch (doi, title, n) |
| not_found | list[str] | DOIs absent from the KG |
| not_matched | list[str] | DOIs present but with no discusses edge (3 such pubs exist) |

**Sort key:** `doi`, then `entity_kind`, then `prominence` (central first), then `entity_id`
(deterministic — required for stable `offset` pagination).
**Default limit:** 50. `summary=True` ⇒ `limit=0`. **`offset`:** default 0; `SKIP $offset`
applied after the global ORDER BY, before `LIMIT`. `returned`/`truncated` reflect the
offset slice; `total_matching` stays the full filtered count.

**`total_entries` is unfiltered** — compute it in `build_discussed_by_publication_summary`
by summing the precomputed `Publication.discussed_gene_count + discussed_pathway_count`
over the matched DOIs, NOT by re-running the detail query without filters. The summary
builder therefore does **not** apply `entity_kind`/`prominence` when deriving
`total_entries`; every other summary rollup (`total_matching`, `by_entity_kind`,
`by_prominence`, `top_kegg_pathways`, `top_publications`) reflects the **filtered** set.

## Verified Cypher (UNION ALL, distinct edge vars)

```cypher
MATCH (p:Publication)-[rg:Publication_discusses_gene]->(g:Gene)
WHERE toLower(p.doi) IN $publication_dois
  AND ($prominence IS NULL OR rg.prominence = $prominence)
RETURN p.doi AS doi, 'gene' AS entity_kind, g.locus_tag AS entity_id,
       coalesce(g.gene_name, g.product) AS entity_name, g.organism_name AS organism,
       rg.prominence AS prominence, rg.evidence AS evidence
UNION ALL
MATCH (p:Publication)-[rk:Publication_discusses_kegg_pathway]->(k:KeggTerm)
WHERE toLower(p.doi) IN $publication_dois
  AND ($prominence IS NULL OR rk.prominence = $prominence)
RETURN p.doi AS doi, 'kegg_pathway' AS entity_kind, k.id AS entity_id,
       k.name AS entity_name, NULL AS organism,
       rk.prominence AS prominence, rk.evidence AS evidence
```
*Verified against live KG.* Distinct edge variables (`rg`/`rk`) — reusing `r` across
rel types raises a CyVer conflicting-labels error. `entity_kind` filter drops the
unwanted arm in the API by skipping that UNION branch.

**ID conventions (verbatim node ids — no prefix stripping, matching existing tools):**
- `entity_id` is the raw node id: **gene → bare `locus_tag`** (e.g. `PMT1030`),
  **KEGG → prefixed `kegg.pathway:ko00010`** (as `search_ontology` / `genes_by_ontology`
  return `t.id` verbatim). Same prefixed form in the `top_kegg_pathways` envelope `id`.
- Publication keyed by **bare DOI** in field `doi` (= `p.doi`, like `list_publications`).
- **DOI match is case-insensitive** (`toLower(p.doi) IN $publication_dois`, param
  lowercased in API), matching `list_publications`. `not_found` diff compares lowercased.

**not_found / not_matched:** computed in API — diff (lowercased) input DOIs against
(a) DOIs that resolve to a `Publication`, (b) DOIs with ≥1 edge after filters.

---

# Extension 1: `gene_overview` — per-gene discussed publications

Gene arm of the (dropped) reverse lookup, folded in here since it is ~1 pub/gene.

- **Compact** per-row: `discussed_in_publication_count` (precomputed
  `Gene.discussed_in_publication_count`) — the signal.
- **Verbose** per-row: `discussed_in_publications` — list of `{doi, prominence, evidence}`
  (small; avg 1.18, max 6 per gene) — the `evidence` quote answers "why does this paper
  discuss the gene" inline. Field description signposts `discussed_by_publication` for the
  paper's full discussed set.
- **Envelope:** `has_discussed` (int — # input genes with ≥1 discussing pub), named to
  match the existing `has_expression` / `has_derived_metrics` / `has_chemistry` int-count
  envelope vocabulary on gene_overview; and
  `top_discussing_publications` — publications ranked by how many of the **queried genes**
  they discuss (doi, title, n_genes), recovering the batch set-coverage use ("which one
  paper covers most of my gene set").

Verified per-gene Cypher (verbose arm):
```cypher
MATCH (g:Gene) WHERE g.locus_tag IN $locus_tags
OPTIONAL MATCH (g)<-[r:Publication_discusses_gene]-(p:Publication)
RETURN g.locus_tag AS locus_tag,
       collect(CASE WHEN p IS NULL THEN NULL ELSE {doi: p.doi, prominence: r.prominence, evidence: r.evidence} END) AS discussed_in_publications
```
*Verified against live KG* (PMT2118/PMT0246 → `{doi, prominence, evidence}` rows).

Verified envelope Cypher (`top_discussing_publications` — pubs by # queried genes discussed):
```cypher
MATCH (g:Gene)<-[:Publication_discusses_gene]-(p:Publication)
WHERE g.locus_tag IN $locus_tags
WITH p, count(DISTINCT g) AS n_genes
RETURN p.doi AS doi, p.title AS title, n_genes ORDER BY n_genes DESC, p.doi LIMIT 10
```
*Verified against live KG* (5-gene set → one paper discussing all 5).

# Extension 2: `search_ontology` — per-KEGG-term discussed publications

Pathway arm of the (dropped) reverse lookup. KEGG terms only; null/0 for other ontologies.

- **NEW PARAM** — `search_ontology` gains a `verbose: bool = False` param. It has **no
  `verbose` today** (current params: `search_text`/`ontology`/`summary`/`limit`/`offset`/
  `level`/`tree`/`informative_only`). This is a real interface addition, not just a field
  add — the implementer adds the param across api + MCP layers. Slot `verbose` alongside
  the existing flags; do not remove any current param. Without `verbose`, only the compact
  count below is returned.
- **Compact** per-row: `discussed_by_n_publications` via pattern-count
  `size([(k)<-[:Publication_discusses_kegg_pathway]-() | 1])` (no precomputed prop).
- **Gate the pattern-count off `ONTOLOGY_CONFIG`, not a hardcoded `ontology == 'kegg'`.**
  Add an optional `"discusses_rel": "Publication_discusses_kegg_pathway"` key to the
  `kegg` entry in `ONTOLOGY_CONFIG` (`kg/queries_lib.py:10`). The `search_ontology`
  builder emits the pattern-count column **only when the selected ontology's config
  declares `discusses_rel`** (and reads the rel-type name from it rather than inlining
  the literal). For every other ontology (GO/EC/COG/Pfam/…) the column is omitted —
  no per-row subquery is paid on those hot generic searches, and `discussed_by_n_publications`
  is simply absent / `None`. This mirrors how `gene_rel` / `hierarchy_rels` / `fulltext_index`
  are already config-driven per ontology.
- **Verbose** per-row: `discussed_in_publications` — list of `{doi, prominence, evidence}`
  (pathways fan out more — ko00710 → 19; evidence quotes verbose-gated). Field
  description signposts `discussed_by_publication`.

*Verified:* ko00010 → 4, ko00710 → 19.

# Extension 3: `list_publications` — per-pub discusses rollup

- **Per-row:** `discussed_gene_count`, `discussed_pathway_count` (precomputed node props).
- **Envelope:** `by_discusses_coverage` binary split `{has_discusses, no_discusses}` (40 vs 3).
- No new query architecture (node props only); no new filter param.

---

## Cross-layer interface notes

- **Shared Pydantic sub-model** — define **one** `DiscussedPublicationRef`
  (`doi: str`, `prominence: Literal["central","peripheral"]`, `evidence: str`) in
  `mcp_server/tools.py` and REUSE it for both the `gene_overview` and `search_ontology`
  verbose `discussed_in_publications` lists. Precedent: `GeneReactionMetaboliteTriplet`
  reused verbatim across tools. Do not define it twice.
- **gene_overview multi-query orchestration** — `top_discussing_publications` ranks
  publications by distinct-queried-gene count, which the per-gene rows cannot yield. The
  api function gains **one extra builder call** (a small summary/aggregation builder)
  merged into the envelope — same orchestration shape as `gene_ontology_terms`. The
  per-row `discussed_in_publication_count` (compact) reads the precomputed node prop in
  the main builder; only the envelope rollup needs the extra query.
- **Exports** — new api fn `discussed_by_publication` → `api/__init__.py` +
  `multiomics_explorer/__init__.py` `__all__`. New builder `build_discussed_by_publication`
  (+ `build_discussed_by_publication_summary`) → `TOOL_BUILDERS`. New tool → `EXPECTED_TOOLS`.
- **search_ontology gains a `verbose` param** — it has no `verbose` today (current params
  are `search_text`/`ontology`/`summary`/`limit`/`offset`/`level`/`tree`/`informative_only`).
  Adding it touches the api function signature + MCP wrapper + the builder's RETURN-column
  gating. gene_overview and list_publications already have `verbose`.
- **search_ontology discusses pattern-count is `ONTOLOGY_CONFIG`-gated** — add a
  `"discusses_rel"` key to the `kegg` config entry; the builder emits
  `discussed_by_n_publications` (and reads the rel-type from config) only for ontologies
  whose config declares it. No subquery on non-KEGG searches. See Extension 2.
- **`discussed_by_publication` polymorphic rows** — `entity_name` (gene `product` /
  pathway `name`) and `organism` (gene-only; explicit `None` on pathway rows) are union
  padding, mirroring the Phase-3 polymorphic-row precedent (`genes_by_metabolite`).
- **list_filter_values** — `prominence` / `entity_kind` deliberately NOT added as
  filter_types; they are closed `Literal` sets, self-documenting in the tool schema.
- **CLAUDE.md tool table** — add the new `discussed_by_publication` row AND update the three
  extended rows (`gene_overview`, `search_ontology`, `list_publications`).

## Guide updates (hand-authored — `doc-updater`, NOT auto-generated)

The 4 cross-tool guides under `skills/multiomics-kg-guide/references/guide/` are
hand-authored (served at `docs://guide/{stem}`). Edit directly:

- **`concepts.md`** — in `### Experiments and publications`, add the two `discusses`
  relationship types (`Publication_discusses_gene`, `Publication_discusses_kegg_pathway`)
  as a narrative literature index: recall-biased prose mentions with `prominence` +
  `evidence`, distinct from DE-table expression. In the "what's NOT in the KG → full
  paper text" caveat, note that prose *mentions* of genes/pathways ARE indexed (best-effort)
  via these edges, even though full text is not. (Leave the node-count table as-is unless
  separately refreshing counts.)
- **`start_here.md`** — add a routing entry for the literature axis ("which papers discuss
  gene/pathway X?" / "what does paper Y discuss?") → `discussed_by_publication`,
  `gene_overview` (per-gene `discussed_in_publication_count` + DOI list),
  `search_ontology` (KEGG `discussed_by_n_publications`). Add `discussed_by_publication`
  to the `list_publications` chaining row.
- **`conventions.md`** — add `discussed_by_publication` to the batch-tool / `not_found`
  + `publication_dois` example lists; it follows existing case-insensitive-DOI +
  not_found/not_matched conventions (no new convention introduced).
- **`python_api.md`** — add `discussed_by_publication` to the import-topology / batch-tool
  listing; standard return shape, no special handling.

Run `uv run python scripts/build_about_content.py --lint` after editing (the lint now
covers hand-authored guide md).

## DataFrame note (`analysis/frames.py`)

**No `frames.py` change.** `discussed_by_publication` returns flat scalar rows → the generic
`to_dataframe()` path handles it (no dispatch-key collision, no converter). Scalar count
fields on the 3 extensions flatten fine. The verbose `discussed_in_publications`
list-of-dict fields are **intentionally dropped-with-`UserWarning`** by the generic
flattener — consistent with all other nested verbose fields; the nested per-pub detail
lives in the raw dict. Do NOT add a converter or a scalar-DOI shim (decided 2026-06-09).

## Field-rubric notes

- `discussed_*_count` fields are true counts of distinct entities — name predicts shape.
- Signal/count fields signpost the drill-down (`discussed_by_publication`) by name.
- `not_found` ≠ `not_matched` surfaced structurally on the new tool.
- Rows are typed Pydantic models; heavy text (`evidence`) and DOI lists gated behind `verbose`.
- New-tool docstring states the recall-biased / NOT-DE limitation up front.

## Resolved decisions (frozen)

- **Tool name** — `discussed_by_publication` (`X_by_Y` shape; LLM-discoverable; no verb fragment).
- **Reverse direction** — no standalone tool; gene arm folded into `gene_overview`, pathway
  arm into `search_ontology` (per ~1 pub/gene distribution).
- **IDs** — verbatim node ids (KEGG prefixed `kegg.pathway:ko00010`, gene bare locus_tag);
  publication keyed by bare `doi`; case-insensitive DOI match.
- **Polymorphic columns** — `entity_name` + `organism` (not a single overloaded `entity_label`).
- **Evidence** — surfaced on `discussed_by_publication` (verbose) AND in the gene_overview /
  search_ontology verbose DOI lists (`{doi, prominence, evidence}`).
- **search_ontology** — gains a `verbose` param to carry the DOI list.
- **DataFrame** — no `frames.py` change; nested verbose lists drop-with-warning.
- **list_filter_values** — unchanged (filters are self-documenting `Literal`s).
