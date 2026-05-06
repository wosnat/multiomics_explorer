# genes_by_metabolite

## What it does

Find genes connected to specified metabolites in one organism.

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

Per-row schema (union shape):
    Every row carries the full cross-arm key set. Metabolism-arm rows
    have `transport_confidence` / `tcdb_family_id` / `tcdb_family_name`
    = None; transport-arm rows have `reaction_id` / `reaction_name` /
    `ec_numbers` / `mass_balance` = None. Use `row['key']` (KeyError-free)
    rather than `row.get('key')` if the difference matters to you.

Reaction-arm framing:
    Reaction edges are undirected AND carry no reversibility flag —
    interpret all reaction-arm rows as 'involved in', never 'produces'
    / 'consumes' / 'reversible'. (KG limitation: KEGG-anchored reactions
    lack both direction and `is_reversible`; see audit §4.1.1 + §4.1.2.)

Drill-downs from result rows / envelope rollups:
- Any `top_genes` entry → `differential_expression_by_gene(locus_tags=[...], organism=...)`
  for transcriptional response, or `gene_overview` for richer context.
- Any `top_tcdb_families` entry → `genes_by_ontology(ontology="tcdb", term_ids=[id], organism=...)`
  for sibling genes in the same family.
- Any `top_reactions` entry → `genes_by_ontology(ontology="ec", term_ids=[ec], organism=...)`
  for genes in adjacent reactions, or `pathway_enrichment` for context.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| metabolite_ids | list[string] | — | Metabolite IDs to drill into (full prefixed, case-sensitive). E.g. ['kegg.compound:C00086', 'kegg.compound:C00064']. `not_found.metabolite_ids` lists IDs that don't exist as a Metabolite node; `not_matched` lists IDs that exist but have no gene reach in the requested organism via either arm. |
| organism | string | — | Organism name (case-insensitive, fuzzy word-based match — mirrors `differential_expression_by_gene`). Single-organism enforced. E.g. 'Prochlorococcus MED4'. `not_found.organism` is set when the name resolves to zero matching genes. |
| exclude_metabolite_ids | list[string] \| None | None | Exclude metabolites with these IDs. Set-difference semantics with `metabolite_ids` — exclude wins on overlap. Empty list is no-op. |
| ec_numbers | list[string] \| None | None | Narrow metabolism rows to those whose Reaction carries any of these EC numbers. **Metabolism arm only — does not affect transport rows**, which are returned unchanged. To restrict to metabolism rows alone, combine with `evidence_sources=['metabolism']`. E.g. ['6.3.1.2'] for glutamine synthetase. |
| metabolite_pathway_ids | list[string] \| None | None | Filter to rows where the **metabolite** is in any of these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` (KG-A5 denorm, transport-extended), so applies uniformly to both arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway annotations, route through `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)` first to obtain locus_tags. `not_found.metabolite_pathway_ids` lists IDs that don't exist as a KeggTerm. |
| mass_balance | string ('balanced', 'unbalanced') \| None | None | Narrow metabolism rows to those whose Reaction has this mass balance status. **Metabolism arm only — does not affect transport rows**. Combine with `evidence_sources=['metabolism']` to restrict to metabolism rows alone. |
| gene_categories | list[string] \| None | None | Filter on `Gene.gene_category` (exact match, applies to both arms uniformly). Use `list_filter_values(filter_type="gene_category")` to discover valid values. |
| transport_confidence | string ('substrate_confirmed', 'family_inferred') \| None | None | Narrow transport rows by TCDB-annotation specificity. `substrate_confirmed` restricts transport rows to those annotated at TCDB `tc_specificity` (substrate-curated). `family_inferred` restricts to transport rows annotated at coarser TCDB levels (rolled up via the substrate edge). **Transport arm only — does not affect metabolism rows**, which are always substrate-confirmed by definition (direct catalysis edge) and carry `transport_confidence = None`. To restrict to transport rows alone, combine with `evidence_sources=['transport']`. **Workflow-dependent (see analysis-doc §g — both tiers are annotations, neither is ground truth):** use `substrate_confirmed` for conservative-cast questions (e.g. cross-organism inference); keep `family_inferred` for broad-screen candidate enumeration (e.g. N-source DE — the real MED4 N-uptake genes are family_inferred-only). |
| evidence_sources | list[string ('metabolism', 'transport')] \| None | None | Path selector — restricts which arms execute. Set to `['metabolism']` to skip transport entirely (no rollup noise); `['transport']` to skip metabolism. Default fires both arms. Note: `'metabolomics'` is NOT a valid value here — metabolomics evidence has no gene anchor and surfaces only in `list_metabolites`. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include extended fields per row: gene_category, metabolite_inchikey/smiles/mnxm_id/hmdb_id, reaction_mnxr_id/rhea_ids (metabolism rows), tcdb_level_kind/tc_class_id (transport rows). |
| limit | int | 10 | Max results. Default covers p75 of typical (metabolite × organism) UNION row distributions; coenzyme-tail queries (ATP, water) use `offset` to page. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, warnings, not_found, not_matched, by_metabolite, by_evidence_source, by_transport_confidence, top_reactions, top_tcdb_families, top_gene_categories, top_genes, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

- **total_matching** (int): Total row count after all filters, across both arms.
- **returned** (int): Number of rows in `results` (≤ `limit`).
- **offset** (int): Echo of the requested offset.
- **truncated** (bool): True when `offset + limit < total_matching`.
- **warnings** (list[string]): Diagnostic strings. Currently emitted: family-inferred-dominance auto-warning when transport rows are family-inferred majority and `transport_confidence` was not set explicitly.
- **not_found** (GbmNotFound): Inputs that did not resolve to a KG node — see model.
- **not_matched** (list[string]): Input metabolite_ids that exist as Metabolite nodes but produced zero rows in this organism slice (under the active filters). Distinct from `not_found.metabolite_ids` (those don't exist at all).
- **by_metabolite** (list[GbmByMetabolite]): Per-metabolite rollup. One entry per input metabolite_id that produced ≥1 row.
- **by_evidence_source** (list[GbmByEvidenceSource]): Frequency over `evidence_source` values present in the slice (≤2 entries).
- **by_transport_confidence** (list[GbmByTransportConfidence]): Frequency over `transport_confidence` values across transport rows only (≤2 entries; metabolism rows are excluded).
- **top_reactions** (list[GbmTopReaction]): Top 10 reactions by gene_count in the metabolism arm.
- **top_tcdb_families** (list[GbmTopTcdbFamily]): Top 10 TCDB families by gene_count in the transport arm.
- **top_gene_categories** (list[GbmTopGeneCategory]): Top 10 gene categories by gene_count across both arms.
- **top_genes** (list[GbmTopGene]): Top 10 genes by combined reaction + transporter breadth across both arms.
- **gene_count_total** (int): Distinct genes in the filtered slice (across both arms).
- **reaction_count_total** (int): Distinct reactions in the filtered metabolism arm.
- **transporter_count_total** (int): Distinct TcdbFamily nodes in the filtered transport arm.
- **metabolite_count_total** (int): Distinct metabolite_ids that produced ≥1 row.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0974' for MED4 urtE). |
| gene_name | string \| None (optional) | Curated gene name (e.g. 'urtE'); often null. |
| product | string \| None (optional) | Annotated gene product description (high-signal short label, e.g. 'ABC-type urea transporter, ATPase component UrtE'). |
| evidence_source | string ('metabolism', 'transport') | Path through which this row reaches the metabolite. 'metabolism' = `Gene → Reaction → Metabolite`. 'transport' = `Gene → TcdbFamily → Metabolite` (rollup-extended). Metabolomics evidence has no gene anchor and never produces rows here. |
| transport_confidence | string ('substrate_confirmed', 'family_inferred') \| None (optional) | Set on transport rows only. 'substrate_confirmed' = the TCDB family annotation is at `tc_specificity` level (substrate-curated). 'family_inferred' = annotation is at a coarser TCDB level (rolled up via the substrate edge — gene may or may not move this metabolite). None on metabolism rows (direct catalysis edge is always substrate-confirmed by definition). |
| reaction_id | string \| None (optional) | Full prefixed Reaction ID (e.g. 'kegg.reaction:R00253'). Metabolism rows only — see class-level note on undirected, non-reversible interpretation. |
| reaction_name | string \| None (optional) | Reaction systematic name + KEGG equation (raw KEGG value, can be lengthy; ~32 reactions in the KG have empty `''`). Metabolism rows only — see class-level note on undirected, non-reversible interpretation. |
| ec_numbers | list[string] \| None (optional) | EC classification(s) for this reaction. Empty list for ~107/2,349 reactions without EC. None on transport rows. |
| mass_balance | string ('balanced', 'unbalanced') \| None (optional) | Reaction mass-balance status (no nulls in KG: 1,922 balanced + 427 unbalanced). None on transport rows. |
| tcdb_family_id | string \| None (optional) | Full prefixed TcdbFamily ID (e.g. 'tcdb:3.A.1.4.5'). Transport rows only. |
| tcdb_family_name | string \| None (optional) | TCDB family name. For tc_family-level entries this is human-readable (e.g. 'The ATP-binding Cassette (ABC) Superfamily'); for tc_subfamily / tc_specificity falls back to the tcdb_id. Transport rows only. |
| metabolite_id | string | Full prefixed Metabolite ID (e.g. 'kegg.compound:C00086'). |
| metabolite_name | string | Metabolite display name (e.g. 'Urea'). |
| metabolite_formula | string \| None (optional) | Hill-notation formula; null on ~9% of metabolites (transport-only ChEBI generics). |
| metabolite_mass | float \| None (optional) | Monoisotopic mass (Da); null on ~22% of metabolites. |
| metabolite_chebi_id | string \| None (optional) | ChEBI numeric ID; populated on ~90% of metabolites. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| gene_category | string \| None (optional) | Curated `Gene.gene_category` value (e.g. 'Transport', 'Amino acid metabolism'). Verbose only. |
| metabolite_inchikey | string \| None (optional) | Structural fingerprint; populated on ~78% of metabolites. Verbose only. |
| metabolite_smiles | string \| None (optional) | Canonical SMILES; populated on ~84% of metabolites. Verbose only. |
| metabolite_mnxm_id | string \| None (optional) | MetaNetX ID (e.g. 'MNXM731'); 100% coverage. Verbose only. |
| metabolite_hmdb_id | string \| None (optional) | HMDB ID (e.g. 'HMDB0000122'); ~47% coverage. Verbose only. |
| reaction_mnxr_id | string \| None (optional) | Reaction MetaNetX ID. Verbose, metabolism rows only. |
| reaction_rhea_ids | list[string] \| None (optional) | Rhea reaction cross-refs. Verbose, metabolism rows only. |
| tcdb_level_kind | string ('tc_class', 'tc_subclass', 'tc_family', 'tc_subfamily', 'tc_specificity') \| None (optional) | TCDB hierarchy level of the annotation. Verbose, transport rows only. `tc_specificity` ⇔ transport_confidence='substrate_confirmed'. |
| tc_class_id | string \| None (optional) | TCDB class ancestor (e.g. 'tcdb:3' for Primary Active Transporters). Pre-computed pointer. Verbose, transport rows only. |

## Few-shot examples

### Example 1: Discovery → drill-down — urea catalysts and transporters in MED4

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4")
```

### Example 2: Cross-feeding pair (Workflow B) — call once per organism, intersect locus_tags client-side

```
Step 1: genes_by_metabolite(metabolite_ids=["kegg.compound:C00064"],
                            organism="Prochlorococcus MED4")
        → MED4 genes touching glutamine (catalysts + transporters)

Step 2: genes_by_metabolite(metabolite_ids=["kegg.compound:C00064"],
                            organism="Alteromonas macleodii MIT1002")
        → MIT1002 genes touching glutamine

Step 3: intersect / diff the two locus_tag sets client-side. Pair with
        differential_expression_by_gene(experiment filter='coculture',
        locus_tags=...) per organism to test whether one side's
        catalysts go up while the other's transporters do too.
```

### Example 3: High-precision transporter hunt — substrate_confirmed only

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4", transport_confidence="substrate_confirmed", evidence_sources=["transport"])
```

### Example 4: Pathway-anchored — N-metabolism only

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086", "kegg.compound:C00064", "kegg.compound:C00088"], organism="Prochlorococcus MED4", metabolite_pathway_ids=["kegg.pathway:ko00910"])
```

### Example 5: Currency-cofactor strip — exclude ATP/ADP/NADH/NADPH/H2O on a multi-metabolite drill

```example-call
genes_by_metabolite(
  metabolite_ids=["kegg.compound:C00064", "kegg.compound:C00086"],
  organism="Prochlorococcus MED4",
  exclude_metabolite_ids=[
    "kegg.compound:C00002",  # ATP
    "kegg.compound:C00008",  # ADP
    "kegg.compound:C00004",  # NADH
    "kegg.compound:C00005",  # NADPH
    "kegg.compound:C00001",  # H2O
  ],
)

```

### Example 6: EC-anchored metabolism narrowing (transport rows still returned)

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00064"], organism="Prochlorococcus MED4", ec_numbers=["6.3.1.2"])
```

## Chaining patterns

```
list_metabolites(...) → genes_by_metabolite(metabolite_ids=[chosen_ids], organism=...)
differential_expression_by_gene(...) → top hits → metabolites_by_gene(locus_tags=...) (Tool 3, planned) → genes_by_metabolite for the symmetric metabolite-anchored view
Workflow A (N-source): list_metabolites(elements=['N']) → genes_by_metabolite(metabolite_ids=[N-bearing IDs], organism=...) for catalysts + transporters
Workflow B (cross-feeding): genes_by_metabolite called once per organism on the same metabolite_ids; intersect/diff locus_tag result sets client-side
genes_by_metabolite → top_genes → differential_expression_by_gene(locus_tags=top_genes_locus_tags, organism=...) for transcriptional response
genes_by_metabolite → top_genes → gene_overview(locus_tags=...) for richer per-gene routing context
genes_by_metabolite → top_tcdb_families → genes_by_ontology(ontology='tcdb', term_ids=[top_tcdb_families[i].tcdb_family_id], organism=...) for sibling genes in the same family
genes_by_metabolite → top_reactions → genes_by_ontology(ontology='ec', term_ids=[ec_number], organism=...) for genes in adjacent reactions
genes_by_metabolite → top_reactions / top_genes → pathway_enrichment for KEGG-pathway context
```

## Good to know

- When the auto-warning fires (most transport rows are `family_inferred`), interpret workflow-dependent: use `transport_confidence='substrate_confirmed'` for conservative-cast questions (e.g. cross-organism inference); keep `family_inferred` for broad-screen candidate enumeration (e.g. N-source DE — the real MED4 N-uptake genes are family_inferred-only). Both tiers are annotations, neither is ground truth — see analysis-doc §g.

- Every result row has the same key set — cross-arm fields are explicitly `None` on rows from the other arm (metabolism rows have `transport_confidence`/`tcdb_family_id`/`tcdb_family_name` = None; transport rows have `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` = None). Use `row['transport_confidence']` (KeyError-free) rather than `row.get('transport_confidence')` if the difference matters.

- Reaction-arm rows are NOT directional — KG reactions carry neither a substrate-vs-product role on `Reaction_has_metabolite` nor an `is_reversible` flag. Read `evidence_source='metabolism'` rows as 'gene catalyses a reaction *involving* this metabolite,' never as 'produces X' / 'consumes Y' / 'reversibly interconverts'. The KG limitation is permanent (KEGG lacks both upstream).

- Filtering by `ec_numbers` does NOT restrict to metabolism only. Per-arm filter scope: `ec_numbers` and `mass_balance` narrow the metabolism arm WHERE; transport rows are returned UNCHANGED (no soft-exclude). Symmetrically, `transport_confidence` narrows transport only and metabolism rows are unaffected. To restrict to one arm, set `evidence_sources=['metabolism']` (or `['transport']`) explicitly. `metabolite_pathway_ids` and `gene_categories` are the only filters that narrow both arms uniformly.

- Single-organism enforced (mirrors `differential_expression_by_gene`). There is no `organisms` list. For cross-organism / cross-feeding work, call once per organism with the same metabolite_ids and combine locus_tag result sets client-side (Workflow B).

- `'metabolomics'` is NOT accepted in `evidence_sources` here — the Pydantic Literal allows only `('metabolism', 'transport')`. The metabolomics path (DerivedMetric → Metabolite) has no Gene anchor and surfaces only in `list_metabolites` (where `'metabolomics'` is a valid forward-compat filter value). Same `_VALID_EVIDENCE_SOURCES` validator pattern, intentionally divergent value set per the tool's biology.

- TCDB-class filtering does NOT belong here. There is no `tcdb_class_ids` parameter. TCDB is now a first-class ontology — for "all genes in TCDB class 3.A.1 (ABC superfamily) for organism X", route through `genes_by_ontology(ontology='tcdb', term_ids=['tcdb:3.A.1'], organism=...)`. From here the drill-out path is `top_tcdb_families[i].tcdb_family_id` → `genes_by_ontology(ontology='tcdb', term_ids=[that_id], organism=...)`.

- `not_found.metabolite_ids` vs `not_matched`. `not_found.metabolite_ids` = IDs that don't exist as a Metabolite node at all (typo, wrong prefix, ChEBI ID not in our KG). `not_matched` = IDs whose Metabolite exists but produced zero rows in this organism slice under the active filters (e.g. transport-only metabolite curated for non-MED4 strains). Don't conflate them — `not_matched` may go to zero by relaxing filters or swapping organism; `not_found` won't.

- When the result is dominated by ATP / ADP / NADH / NADPH / H2O (currency cofactors that catalysts and transporters touch ubiquitously), pass `exclude_metabolite_ids=[<kegg.compound:Cxxxxx>]` to strip them. Set-difference semantics with `metabolite_ids` — exclude wins on overlap (silent). Per-arm scope: exclude applies on BOTH metabolism + transport arms (mirrors `metabolite_ids`). KG namespace is `kegg.compound:` (not `chebi:`).

- Transport rows are direction-agnostic. The `Tcdb_family_transports_metabolite` edge does not distinguish substrate from product, and the metabolism arm's `Reaction_has_metabolite` edge doesn't either (KEGG equation order is arbitrary). To distinguish substrate vs product, layer transcriptional evidence (`differential_expression_by_gene`) and functional annotation (`gene_overview` Pfam / KEGG KO names like `*-synthase` vs `*-permease`).

## Package import equivalent

```python
from multiomics_explorer import genes_by_metabolite

result = genes_by_metabolite(metabolite_ids=..., organism=...)
# returns dict with keys: total_matching, offset, warnings, not_found, not_matched, by_metabolite, by_evidence_source, by_transport_confidence, top_reactions, top_tcdb_families, top_gene_categories, top_genes, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
