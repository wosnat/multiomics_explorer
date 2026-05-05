# metabolites_by_gene

## What it does

Find metabolites the input gene set's chemistry reaches in one organism.

**Direction-agnostic.** Joins through `Reaction_has_metabolite`
(metabolism) and `Tcdb_family_transports_metabolite` (transport)
are direction-agnostic — a gene that *produces* a metabolite and
a gene that *consumes* it surface identically. KEGG equation
order is arbitrary. To distinguish, layer transcriptional
evidence (`differential_expression_by_gene`) and gene functional
annotation (`gene_overview` Pfam / KEGG KO names like
`*-synthase` vs `*-permease`).

**Transport-confidence semantics (transport arm only).** Identical
model to `genes_by_metabolite`: `family_inferred` rows ride a
TCDB substrate-edge rollup that propagates leaf-curated
substrates up the hierarchy. The ABC Superfamily long tail
(9 MED4 genes annotated only at `tcdb:3.A.1` emit 551
family_inferred rows each via the rollup) means batch DE inputs
can explode in row count. Filter
`transport_confidence='substrate_confirmed'` (paired with
`evidence_sources=['transport']` for the transport arm in
isolation) for the precise set; the default fires both arms and
flags `family_inferred` in `warnings` when it dominates.
Metabolism rows are not subject to this concern — direct
catalysis edges are always substrate-confirmed — and their
`transport_confidence` is None.

**Evidence sources accepted here:** `metabolism`, `transport`.
The metabolomics path (DerivedMetric → Metabolite) has no gene
anchor and is not surfaced by gene-anchored chemistry tools —
see `list_metabolites`.

**Sort order:** detail rows are globally sorted by precision
tier (metabolism → transport_substrate_confirmed →
transport_family_inferred), then by input gene order, then by
locus_tag, then by metabolite_id. This surfaces high-precision
rows from the entire batch first regardless of input position —
a single ABC-superfamily-only gene at the front of input does
NOT eat the entire `limit=10` with family_inferred rows.

Drill-downs from result rows / envelope rollups:
- Any `top_metabolites` entry →
  `list_metabolites(metabolite_ids=[...])` for richer per-
  metabolite cross-refs, or
  `list_metabolites(metabolite_ids=[...], organism_names=[partner])`
  for cross-organism presence (cross-feeding primitive).
- Any `top_metabolite_pathways` entry →
  `list_metabolites(pathway_ids=[...])` for the full metabolite
  roster of the pathway (not just gene-set hits), or
  `genes_by_ontology(ontology="kegg", term_ids=[id], organism=...)`
  for gene-KO-mediated pathway annotations (different surface —
  see naming disambiguation below).
- Any `top_reactions` entry →
  `genes_by_ontology(ontology="ec", term_ids=[ec], organism=...)`
  for genes in adjacent reactions, or `pathway_enrichment` for
  context.
- Any `top_tcdb_families` entry →
  `genes_by_ontology(ontology="tcdb", term_ids=[id], organism=...)`
  for sibling genes in the same family.

**`top_metabolite_pathways` naming disambiguation.** Despite this being a
gene-anchored tool, `top_metabolite_pathways` here means *KEGG pathways the
gene set's chemistry reaches* — via `Reaction_in_kegg_pathway`
and `Metabolite_in_pathway`. Distinct from the **gene-KO-
mediated** pathway annotations available via
`genes_by_ontology(ontology="kegg")` (where pathway membership
is asserted by the gene's KO assignment). For metabolic pathway
analysis with a hypothesis test, use `pathway_enrichment`.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to drill into (case-sensitive). E.g. ['PMM0963', 'PMM0964', 'PMM0965'] for urease α/β/γ subunits. `not_found.locus_tags` lists tags that don't resolve to any Gene in the requested organism; `not_matched` lists tags that DO resolve but have no chemistry edges (no Gene_catalyzes_reaction AND no Gene_has_tcdb_family). |
| organism | string | — | Organism name (case-insensitive, fuzzy word-based match — mirrors `differential_expression_by_gene` and `genes_by_metabolite`). Single-organism enforced. E.g. 'Prochlorococcus MED4'. `not_found.organism` is set when the name resolves to zero matching genes for the input locus_tags. |
| metabolite_elements | list[string] \| None | None | Filter to rows where the metabolite contains ALL of the given element symbols (AND-of-presence). E.g. `['N']` keeps only N-bearing metabolites — the headline N-source workflow primitive. `['N', 'P']` requires both. Anchored on `Metabolite.elements` (KG-A3 Hill-parsed presence list); applies uniformly to both arms. Never substring-match on `formula` (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). `not_found.metabolite_elements` lists symbols that don't exist on any KG metabolite. |
| metabolite_ids | list[string] \| None | None | Restrict rows to specific metabolite IDs (full prefixed, e.g. ['kegg.compound:C00086', 'kegg.compound:C00064']). Useful for the cross-feeding workflow: after MBG returns top_metabolites, re-query a partner organism via `genes_by_metabolite` with these IDs. Applies uniformly to both arms. |
| exclude_metabolite_ids | list[string] \| None | None | Exclude metabolites with these IDs. Set-difference semantics with `metabolite_ids` — exclude wins on overlap. Empty list is no-op. |
| ec_numbers | list[string] \| None | None | Narrow metabolism rows to those whose Reaction carries any of these EC numbers. **Metabolism arm only — does not affect transport rows**, which are returned unchanged. To restrict to metabolism rows alone, combine with `evidence_sources=['metabolism']`. E.g. ['3.5.1.5'] for urease. |
| metabolite_pathway_ids | list[string] \| None | None | Filter to rows where the **metabolite** is in any of these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` (KG-A5 denorm, transport-extended), so applies uniformly to both arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway annotations, route through `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)` first to obtain locus_tags. `not_found.metabolite_pathway_ids` lists IDs that don't exist as a KeggTerm. |
| mass_balance | string ('balanced', 'unbalanced') \| None | None | Narrow metabolism rows to those whose Reaction has this mass balance status. **Metabolism arm only — does not affect transport rows**. Combine with `evidence_sources=['metabolism']` to restrict to metabolism rows alone. |
| gene_categories | list[string] \| None | None | Filter on `Gene.gene_category` (exact match, applies to both arms uniformly). Use `list_filter_values(filter_type="gene_category")` for valid values. Note: somewhat redundant with `locus_tags` input; useful when locus_tags is a broad batch and you want chemistry from specific functional categories only. |
| transport_confidence | string ('substrate_confirmed', 'family_inferred') \| None | None | Narrow transport rows by TCDB-annotation specificity. `substrate_confirmed` restricts transport rows to those annotated at TCDB `tc_specificity` (substrate-curated). `family_inferred` restricts to transport rows annotated at coarser TCDB levels (rolled up via the substrate edge). **Transport arm only — does not affect metabolism rows**, which are always substrate-confirmed by definition (direct catalysis edge) and carry `transport_confidence = None`. To restrict to transport rows alone, combine with `evidence_sources=['transport']`. **Recommended for high-precision transporter-hunting in batch DE inputs:** `transport_confidence='substrate_confirmed', evidence_sources=['transport']` (mutes the ABC-superfamily 551-row blowup). |
| evidence_sources | list[string ('metabolism', 'transport')] \| None | None | Path selector — restricts which arms execute. Set to `['metabolism']` to skip transport entirely (no rollup noise); `['transport']` to skip metabolism. Default fires both arms. Note: `'metabolomics'` is NOT a valid value here — metabolomics evidence has no gene anchor and surfaces only in `list_metabolites`. |
| summary | bool | False | When true, return only summary fields (results=[]). **Strongly recommended for batch DE inputs** (50+ locus_tags) — envelope rollups (top_metabolites, top_metabolite_pathways, top_reactions, top_tcdb_families, by_element, by_gene, top_gene_categories) are the actually-useful artifact at that scale; detail rows can exceed 1,000 quickly. |
| verbose | bool | False | Include extended fields per row: gene_category, metabolite_inchikey/smiles/mnxm_id/hmdb_id, reaction_mnxr_id/rhea_ids (metabolism rows), tcdb_level_kind/tc_class_id (transport rows). Same field set as `genes_by_metabolite`. |
| limit | int | 10 | Max results in `results`. Default 10 covers ~p70 of single-gene UNION row distributions (median 6, p75 12 in MED4). Long-tail genes (ABC-superfamily-only) emit up to 551 rows — use `transport_confidence='substrate_confirmed'` to mute, or `offset` to page. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, warnings, not_found, not_matched, by_gene, by_evidence_source, by_transport_confidence, by_element, top_metabolites, top_reactions, top_tcdb_families, top_gene_categories, top_metabolite_pathways, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

- **total_matching** (int): Total row count after all filters, across both arms.
- **returned** (int): Number of rows in `results` (≤ `limit`).
- **offset** (int): Echo of the requested offset.
- **truncated** (bool): True when `offset + limit < total_matching`.
- **warnings** (list[string]): Diagnostic strings. Currently emitted: family-inferred-dominance auto-warning when transport rows are family-inferred majority and `transport_confidence` was not set explicitly (mirror of GBM behavior).
- **not_found** (MbgNotFound): Inputs that did not resolve to a KG node — see model.
- **not_matched** (list[string]): Input locus_tags that resolve to a Gene in the requested organism but produced zero chemistry rows (no Gene_catalyzes_reaction AND no Gene_has_tcdb_family). Distinct from `not_found.locus_tags` (those don't resolve at all).
- **by_gene** (list[MbgByGene]): Per-gene rollup. One entry per input locus_tag that produced ≥1 row.
- **by_evidence_source** (list[MbgByEvidenceSource]): Frequency over `evidence_source` values present in the slice (≤2 entries).
- **by_transport_confidence** (list[MbgByTransportConfidence]): Frequency over `transport_confidence` values across transport rows only (≤2 entries; metabolism rows are excluded).
- **by_element** (list[MbgByElement]): NEW (vs GBM): element-presence rollup across the metabolites the gene set touches. Periodic-table-bounded (~30 elements max in KG); full rollup, not top-N.
- **top_metabolites** (list[MbgTopMetabolite]): Top 10 metabolites by gene reach in the filtered slice. The headline answer to 'what metabolites do my gene set hit most.' Drill into any entry via `list_metabolites(metabolite_ids=[id])`.
- **top_reactions** (list[MbgTopReaction]): Top 10 reactions by gene_count in the metabolism arm. Drill into any entry via `genes_by_ontology(ontology="ec", term_ids=[ec], organism=...)`.
- **top_tcdb_families** (list[MbgTopTcdbFamily]): Top 10 TCDB families by gene_count in the transport arm. Drill into any entry via `genes_by_ontology(ontology="tcdb", term_ids=[id], organism=...)`.
- **top_gene_categories** (list[MbgTopGeneCategory]): Top 10 gene categories by gene_count across both arms.
- **top_metabolite_pathways** (list[MbgTopPathway]): NEW (vs GBM): top 10 KEGG pathways the gene set's chemistry reaches. Metabolite-pathway rollup (distinct from KO-pathway annotations on `genes_by_ontology(ontology="kegg")`) — see model docstring for naming disambiguation. Drill into any entry via `list_metabolites(pathway_ids=[id])`.
- **gene_count_total** (int): Distinct input genes in the filtered slice (across both arms).
- **reaction_count_total** (int): Distinct reactions in the filtered metabolism arm.
- **transporter_count_total** (int): Distinct TcdbFamily nodes in the filtered transport arm.
- **metabolite_count_total** (int): Distinct metabolites that produced ≥1 row across both arms.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0974' for MED4 urtE). |
| gene_name | string \| None (optional) | Curated gene name (e.g. 'urtE'); often null. |
| product | string \| None (optional) | Annotated gene product description (high-signal short label, e.g. 'ABC-type urea transporter, ATPase component UrtE'). |
| evidence_source | string ('metabolism', 'transport') | Path through which this row reaches the metabolite. 'metabolism' = `Gene → Reaction → Metabolite`. 'transport' = `Gene → TcdbFamily → Metabolite` (rollup-extended). Metabolomics evidence has no gene anchor and never produces rows here. |
| transport_confidence | string ('substrate_confirmed', 'family_inferred') \| None (optional) | Set on transport rows only. 'substrate_confirmed' = the TCDB family annotation is at `tc_specificity` level (substrate-curated). 'family_inferred' = annotation is at a coarser TCDB level (rolled up via the substrate edge — gene may or may not move this metabolite). None on metabolism rows (direct catalysis edge is always substrate-confirmed by definition). |
| reaction_id | string \| None (optional) | Full prefixed Reaction ID (e.g. 'kegg.reaction:R00253'). Metabolism rows only. |
| reaction_name | string \| None (optional) | Reaction systematic name + KEGG equation (raw KEGG value, can be lengthy; ~32 reactions in the KG have empty `''`). Metabolism rows only. |
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

### Example 1: Single-gene drill-down — urease subunit (Workflow D)

```example-call
metabolites_by_gene(locus_tags=["PMM0913"], organism="Prochlorococcus MED4", limit=5)
```

### Example 2: Urease subunits (canonical detail-row example)

```example-call
metabolites_by_gene(locus_tags=["PMM0963", "PMM0964", "PMM0965"], organism="Prochlorococcus MED4", limit=5)
```

### Example 3: Workflow A (N-source marquee) — DE batch with element filter

```
Step 1: differential_expression_by_gene(
          organism="Prochlorococcus MED4",
          experiment_ids=[<N-limitation experiment IDs>],
          direction="up", significant_only=True,
        )
        → DE gene set (~50-200 locus_tags)

Step 2: metabolites_by_gene(
          locus_tags=DE_gene_set,
          organism="Prochlorococcus MED4",
          metabolite_elements=["N"],
          summary=True,                 # batch DE → envelope is the artifact
        )
        → top_metabolites ranks N-bearing compounds by gene reach;
          top_metabolite_pathways concentrates Nitrogen metabolism,
          Arginine biosynthesis, Alanine/aspartate/glutamate metabolism;
          by_element confirms N-presence dominance.

Step 3 (optional): list_metabolites(metabolite_ids=[top_N_metabolite_ids])
        → cross-refs, mass, formula, full pathway names.
```

### Example 4: Workflow C (cluster characterization) — chemistry of a co-expressed cluster

```
Step 1: genes_in_cluster(cluster_ids=[<cluster_id>])
        → gene set (~10-100 locus_tags)

Step 2: metabolites_by_gene(
          locus_tags=cluster_genes,
          organism="Prochlorococcus MED4",
          summary=True,
        )
        → top_metabolite_pathways = "what pathways does this set sit in"
          by_element = C/N/P/S signature
          top_metabolites = specific compounds the set's chemistry hits

Step 3 (optional): list_metabolites(pathway_ids=[<top_metabolite_pathway_id>])
        → full metabolite roster of the pathway (not just gene-set hits).
```

### Example 5: Workflow B' (cross-feeding) — MBG → GBM bridge

```
Step 1: differential_expression_by_gene(
          organism="Prochlorococcus MED4",
          experiment_ids=[<coculture experiment IDs>],
          direction="up", significant_only=True,
        )
        → MED4 coculture-up DE gene set

Step 2: metabolites_by_gene(
          locus_tags=MED4_DE_genes,
          organism="Prochlorococcus MED4",
          summary=True,
        )
        → top_metabolites = "metabolites my upregulated MED4 genes deal in"

Step 3: genes_by_metabolite(
          metabolite_ids=[id for id in top_metabolites],
          organism="Alteromonas macleodii MIT1002",
        )
        → catalysts and transporters for those metabolites in the
          partner organism. Intersect / diff client-side to seed
          cross-feeding hypotheses.
```

### Example 6: Currency-cofactor strip — exclude ATP/ADP/NADH/NADPH/H2O on a chemistry rollup

```example-call
metabolites_by_gene(
  locus_tags=["PMM0963", "PMM0964", "PMM0965"],
  organism="Prochlorococcus MED4",
  exclude_metabolite_ids=[
    "kegg.compound:C00002",
    "kegg.compound:C00008",
    "kegg.compound:C00004",
    "kegg.compound:C00005",
    "kegg.compound:C00001",
  ],
  summary=True,
)

```

### Example 7: High-precision transporter slice (mute the 551-row blowup)

```example-call
metabolites_by_gene(locus_tags=["PMM0434", "PMM0913"], organism="Prochlorococcus MED4", transport_confidence="substrate_confirmed", evidence_sources=["transport"], limit=5)
```

## Chaining patterns

```
differential_expression_by_gene(organism=..., direction='up') → metabolites_by_gene(locus_tags=DE_genes, organism=..., metabolite_elements=['N']) (Workflow A — N-source marquee)
genes_in_cluster(cluster_ids=...) → metabolites_by_gene(locus_tags=cluster_genes, organism=...) (Workflow C — cluster chemistry characterization)
genes_by_function(query=..., organism=...) → metabolites_by_gene(locus_tags=function_hit_genes, organism=...) (Workflow C variant — function-search chemistry)
gene_overview(locus_tags=[...]) → per-row reaction_count/metabolite_count > 0 → metabolites_by_gene(locus_tags=chemistry_genes, organism=...)
metabolites_by_gene → top_metabolites → list_metabolites(metabolite_ids=[top_metabolite_ids]) for richer per-metabolite cross-refs (mass, formula, full pathway names)
metabolites_by_gene → top_metabolites → list_metabolites(metabolite_ids=[top_metabolite_ids], organism_names=[partner_organism]) for cross-organism presence (Workflow B' cross-feeding seed)
metabolites_by_gene → top_metabolites → genes_by_metabolite(metabolite_ids=[top_metabolite_ids], organism=PARTNER_ORGANISM) (Workflow B' cross-feeding bridge — catalysts + transporters in partner)
metabolites_by_gene → top_metabolite_pathways → list_metabolites(pathway_ids=[metabolite_pathway_id]) for the full metabolite roster of the pathway (not just gene-set hits)
metabolites_by_gene → top_metabolite_pathways → genes_by_ontology(ontology='kegg', term_ids=[metabolite_pathway_id], organism=...) for gene-KO-mediated pathway annotations (different surface — see top_metabolite_pathways naming disambiguation)
metabolites_by_gene → top_metabolite_pathways → pathway_enrichment(...) when gene-set hypothesis test is the goal
metabolites_by_gene → top_reactions → genes_by_ontology(ontology='ec', term_ids=[ec_number], organism=...) for genes in adjacent reactions
metabolites_by_gene → top_tcdb_families → genes_by_ontology(ontology='tcdb', term_ids=[tcdb_family_id], organism=...) for sibling genes in the same family
metabolites_by_gene → not_matched (locus_tags with no chemistry edges) → gene_overview(locus_tags=not_matched) for annotation context (most are richly-annotated non-chemistry genes — DNA gyrase, signaling, etc. — not annotation gaps)
```

## Good to know

- Single-organism enforced (mirrors `differential_expression_by_gene` and `genes_by_metabolite`). There is no `organisms` list. For cross-organism / cross-feeding work, use Workflow B': call MBG once on the focal organism, take `top_metabolites`, then route to `genes_by_metabolite(metabolite_ids=[...], organism=partner)` (or `list_metabolites(metabolite_ids=[...], organism_names=[partner])` for presence-only).

- `'metabolomics'` is NOT accepted in `evidence_sources` here — the Pydantic Literal allows only `('metabolism', 'transport')`. The metabolomics path (DerivedMetric → Metabolite) has no Gene anchor and surfaces only in `list_metabolites` (where `'metabolomics'` is a valid forward-compat filter value). Same divergence as `genes_by_metabolite`.

- family_inferred-dominance blowup is per-gene-side here. The 9 ABC-superfamily-only MED4 genes (PMM0434, PMM0449, PMM0450, PMM0749, PMM0750, PMM0913, PMM0976/0977/0978) each emit 551 family_inferred transport rows via the TCDB substrate-edge rollup — a single one of them in a batch DE input is enough to dominate the result. The precision-tier sort (metabolism → substrate_confirmed → family_inferred) keeps high-precision rows at the top regardless of input position, but `total_matching` and the auto-warning still reflect the blowup. For high-precision transporter-hunting set BOTH `transport_confidence='substrate_confirmed'` AND `evidence_sources=['transport']`.

- `gene_categories` filter is partially redundant with `locus_tags` input (since the input already constrains the gene set). It's useful only as further narrowing within a broad batch — e.g. `locus_tags=DE_genes, gene_categories=['Transport and binding']` to slice DE chemistry to transport-classified genes only. Don't use it as the primary anchor.

- `ec_numbers` and `mass_balance` are metabolism-arm-only filters — they DO NOT suppress transport rows. Transport rows pass through unchanged. To restrict to metabolism alone, combine with `evidence_sources=['metabolism']`. Symmetrically, `transport_confidence` narrows transport rows only and metabolism rows are unaffected. Per-arm filter scope is predictable + composable; it is NOT soft-exclude. `metabolite_elements`, `metabolite_ids`, `metabolite_pathway_ids`, and `gene_categories` are the only filters that narrow both arms uniformly.

- `top_metabolite_pathways` here means *KEGG pathways the gene set's chemistry reaches* (via `Reaction_in_kegg_pathway` + `Metabolite_in_pathway`). These are NOT the same as gene-KO-mediated pathway annotations (where pathway membership is asserted by the gene's KO assignment) — those live in `genes_by_ontology(ontology='kegg', term_ids=[...], organism=...)`. The two are distinct surfaces: chemistry-reach (this tool) vs KO-annotation (`genes_by_ontology`). For metabolic pathway analysis with a hypothesis test, use `pathway_enrichment` instead.

- `metabolite_elements` is presence-only AND-of (not formula substring). `['N']` keeps metabolites whose `Metabolite.elements` Hill-parsed list contains 'N'. `['N', 'P']` requires BOTH N and P. Never substring-match on `formula` — Hill notation has element-clash footguns: `'Cl'` contains `'C'`, `'Na'` contains `'N'`. Use the `metabolite_elements` filter, never grep `formula`.

- Use `summary=True` for batch DE inputs (50+ locus_tags). Detail rows can exceed 1,000 quickly even after the precision-tier sort; the envelope rollups (top_metabolites, top_metabolite_pathways, top_reactions, top_tcdb_families, by_element, by_gene, top_gene_categories) are the actually-useful artifact at that scale.

- `not_found.locus_tags` vs `not_matched`. `not_found.locus_tags` = locus_tags that don't resolve to any Gene in the requested organism (typo, wrong organism, gene removed in KG rebuild). `not_matched` = locus_tags that DO resolve to a Gene but have zero chemistry edges (no `Gene_catalyzes_reaction` AND no `Gene_has_tcdb_family`). In MED4 1,366/1,976 genes (69%) fall into the `not_matched` bucket — most are richly-annotated non-chemistry genes (DNA gyrase, queG, signaling modules), not annotation gaps. Pivot via `gene_overview(locus_tags=not_matched)` for annotation context.

- When `top_metabolites` is dominated by ATP / ADP / NADH / NADPH / H2O, pass `exclude_metabolite_ids=[<kegg.compound:Cxxxxx>]` to strip the currency-cofactor noise. Set-difference semantics with `metabolite_ids` — exclude wins on overlap (silent). Per-arm scope: exclude applies on BOTH metabolism + transport arms (mirrors `metabolite_ids`). KG namespace is `kegg.compound:` (not `chebi:`).

- Detail rows are direction-agnostic. The transport edge (`Tcdb_family_transports_metabolite`) does not distinguish substrate from product, and the metabolism arm's `Reaction_has_metabolite` edge doesn't either (KEGG equation order is arbitrary). To distinguish, layer transcriptional evidence (`differential_expression_by_gene`) and functional annotation (`gene_overview` Pfam / KEGG KO names like `*-synthase` vs `*-permease`).

## Package import equivalent

```python
from multiomics_explorer import metabolites_by_gene

result = metabolites_by_gene(locus_tags=..., organism=...)
# returns dict with keys: total_matching, offset, warnings, not_found, not_matched, by_gene, by_evidence_source, by_transport_confidence, by_element, top_metabolites, top_reactions, top_tcdb_families, top_gene_categories, top_metabolite_pathways, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
