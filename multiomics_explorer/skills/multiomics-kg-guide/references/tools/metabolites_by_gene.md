# metabolites_by_gene

## What it does

Find metabolites the input gene set's chemistry reaches in one
organism.

What: symmetric counterpart to `genes_by_metabolite` — same two
arms (metabolism and transport over each gene's deepest TCDB
attachments only, so distinct transport metabolites equal
`gene_overview.transported_metabolite_count`), same per-row union
shape with `substrate_depth` + `tcdb_evidence_score`, same
direction-agnostic semantics. The `metabolite_elements` filter is
the N-source workflow primitive (presence-only AND-of, e.g.
`['N']`). The `by_element` envelope is presence-only — not
stoichiometric, not mass-balanced.

Transport semantics: genes with only lumping attachments (notably
ABC-only) emit many `inherited` rows; the global sort (metabolism →
most_specific → inherited, score desc within a tier) prevents one
gene from consuming `limit`, and the auto-warning names input genes
whose `transport_substrate_resolution` is 'family_inferred'
(breadth is reachability, not capability; 'resolved' means at
least one non-lumping attachment, not all).

Batch advice: use `summary=True` on batch DE inputs (50+
locus_tags). Bare / xref metabolite IDs are coerced to canonical
(`resolved_aliases`; collisions expand + warn).

Routing: narrow with `substrate_depth=['most_specific']` to mute
inherited long tails; from `top_metabolites` drill into
`list_metabolites(metabolite_ids=[...])` for cross-refs OR
`genes_by_metabolite(metabolite_ids=[...], organism=PARTNER)`
for the cross-feeding bridge; from `top_metabolite_pathways` to
`list_metabolites(pathway_ids=[...])` (chemistry-pathway rollup,
distinct from gene-KO pathway annotations on
`genes_by_ontology(ontology="kegg")`); from `top_reactions` to
`genes_by_ontology(ontology="ec", term_ids=[ec], organism=...)`
or `pathway_enrichment`; from `top_tcdb_families` to
`genes_by_ontology(ontology="tcdb", term_ids=[id],
organism=...)`; from `not_matched` to `gene_overview`. See
`docs://guide/conventions` for substrate-depth and
direction-agnostic semantics, and `docs://analysis/metabolites`
for the chemistry-layer decision tree.

`not_found.organism` is set when the `organism` name resolves to
zero organisms. Long-tail genes (ABC-only annotations) can emit
large numbers of `limit` rows — use
`substrate_depth=['most_specific']` to mute, or `offset` to page.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to drill into (case-sensitive). E.g. ['PMM0963', 'PMM0964', 'PMM0965'] for urease α/β/γ subunits. `not_found.locus_tags` lists tags that don't resolve to any Gene in the requested organism; `not_matched` lists tags that DO resolve but have no chemistry edges (no Gene_catalyzes_reaction AND no Gene_has_tcdb_family). |
| organism | string \| None | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| metabolite_elements | list[string] \| None | None | Filter to rows where the metabolite contains ALL of the given element symbols (AND-of-presence). E.g. `['N']` keeps only N-bearing metabolites — the headline N-source workflow primitive. `['N', 'P']` requires both. Anchored on `Metabolite.elements` (KG-A3 Hill-parsed presence list); applies uniformly to both arms. Never substring-match on `formula` (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). `not_found.metabolite_elements` lists symbols that don't exist on any KG metabolite. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| ec_numbers | list[string] \| None | None | Narrow metabolism rows to those whose Reaction carries any of these EC numbers. **Metabolism arm only — does not affect transport rows**, which are returned unchanged. To restrict to metabolism rows alone, combine with `evidence_sources=['metabolism']`. E.g. ['3.5.1.5'] for urease. |
| metabolite_pathway_ids | list[string] \| None | None | Filter to rows where the **metabolite** is in any of these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` (transport-extended), so applies uniformly to both arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway annotations, route through `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)` first to obtain locus_tags. `not_found.metabolite_pathway_ids` lists IDs that don't exist as a KeggTerm. |
| mass_balance | string ('balanced', 'unbalanced') \| None | None | Narrow metabolism rows to those whose Reaction has this mass balance status. **Metabolism arm only — does not affect transport rows**. Combine with `evidence_sources=['metabolism']` to restrict to metabolism rows alone. |
| gene_categories | list[string] \| None | None | Filter on `Gene.gene_category` (exact match, applies to both arms uniformly). Use `list_filter_values(filter_type="gene_category")` for valid values. Note: somewhat redundant with `locus_tags` input; useful when locus_tags is a broad batch and you want chemistry from specific functional categories only. |
| substrate_depth | list[string ('most_specific', 'inherited')] \| None | None | Keep transport rows whose edge `substrate_depth` is in this list. 'most_specific' = most specific surviving transporter node for the substrate (gene-pruned hierarchy, not a curation level). Transport arm only; mutes ABC tails. |
| evidence_sources | list[string ('metabolism', 'transport')] \| None | None | Path selector — restricts which arms execute. Set to `['metabolism']` to skip transport entirely (no rollup noise); `['transport']` to skip metabolism. Default fires both arms. Note: `'metabolomics'` is NOT a valid value here — metabolomics evidence has no gene anchor and surfaces only in `list_metabolites`. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields in docs://tools/{name}. |
| limit | int \| None | 10 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, warnings, resolved_aliases, not_found, not_matched, by_gene, by_evidence_source, by_substrate_depth, by_element, top_metabolites, top_reactions, top_tcdb_families, top_gene_categories, top_metabolite_pathways, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

- **total_matching** (int): Total row count after all filters, across both arms.
- **returned** (int): Number of rows in `results` (≤ `limit`).
- **offset** (int): Echo of the requested offset.
- **truncated** (bool): True when `offset + limit < total_matching`.
- **warnings** (list[string]): Diagnostic strings. Currently emitted: gene-anchored auto-warning naming input genes whose `transport_substrate_resolution='family_inferred'` — their substrate breadth is reachability, not capability; bare-ID collision notes (one input → several metabolites, expanded to all); a `gene_categories` value not found in the live vocabulary; a `not_found.locus_tags` entry differing only by case from a real one (locus_tags are never case-normalised).
- **resolved_aliases** (object): Bare / xref metabolite inputs coerced to canonical IDs, `{input: [canonical, ...]}` — only coerced entries, across both `metabolite_ids` and `exclude_metabolite_ids`. A list longer than 1 is a collision (expanded to all; see `warnings`).
- **not_found** (MbgNotFound): Inputs that did not resolve to a KG node — see model.
- **not_matched** (list[string]): Input locus_tags that resolve to a Gene in the requested organism but produced zero chemistry rows (no Gene_catalyzes_reaction AND no Gene_has_tcdb_family). Distinct from `not_found.locus_tags` (those don't resolve at all).
- **by_gene** (list[MbgByGene]): Per-gene rollup. One entry per input locus_tag that produced ≥1 row.
- **by_evidence_source** (list[MbgByEvidenceSource]): Frequency over `evidence_source` values present in the slice (≤2 entries).
- **by_substrate_depth** (list[MbgBySubstrateDepth]): Frequency over `substrate_depth` values across transport rows only (≤2 entries; metabolism rows are excluded).
- **by_element** (list[MbgByElement]): Element-presence rollup across the metabolites the gene set touches. Singleton elements (metabolite_count < 2) are dropped, then capped to the top 10 by metabolite_count desc on detail calls; summary=True returns the full rollup. Presence-only — count of distinct compounds containing each element at all. NOT stoichiometric (no atom counts per compound; stoichiometry lives in `metabolite.formula`). NOT mass-balanced (KG carries no substrate-vs-product role on `Reaction_has_metabolite`).
- **by_element_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **top_metabolites** (list[MbgTopMetabolite]): Top 10 metabolites by gene reach in the filtered slice. The headline answer to 'what metabolites do my gene set hit most.' Drill into any entry via `list_metabolites(metabolite_ids=[id])`.
- **top_reactions** (list[MbgTopReaction]): Top 10 reactions by gene_count in the metabolism arm. Drill into any entry via `genes_by_ontology(ontology="ec", term_ids=[ec], organism=...)`.
- **top_tcdb_families** (list[MbgTopTcdbFamily]): Top 10 TCDB families by gene_count in the transport arm. Drill into any entry via `genes_by_ontology(ontology="tcdb", term_ids=[id], organism=...)`.
- **top_gene_categories** (list[MbgTopGeneCategory]): Top 10 gene categories by gene_count across both arms.
- **top_metabolite_pathways** (list[MbgTopPathway]): NEW (vs GBM): top 10 KEGG pathways the gene set's chemistry reaches, sorted by gene_count desc then pathway_metabolite_count asc. Metabolite-pathway rollup (distinct from KO-pathway annotations on `genes_by_ontology(ontology="kegg")`) — see model docstring for naming disambiguation. Drill into any entry via `list_metabolites(pathway_ids=[id])`. summary=True returns the full ranked list.
- **top_metabolite_pathways_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
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
| evidence_source | string ('metabolism', 'transport') | Path through which this row reaches the metabolite. 'metabolism' = `Gene → Reaction → Metabolite`. 'transport' = `Gene → TcdbFamily → Metabolite` via the gene's deepest TCDB attachments only. Metabolomics evidence has no gene anchor here. |
| substrate_depth | string ('most_specific', 'inherited') \| None (optional) | Transport rows only (None on metabolism rows). 'most_specific' = this family is the most specific surviving transporter node for this substrate, relative to the gene-pruned hierarchy — not a curation level. 'inherited' = rolled up from a descendant. |
| tcdb_evidence_score | float \| None (optional) | Transport rows only (None on metabolism rows). KG 5-signal composite for the gene×family call, in [0,1]. Rank with it, don't filter: 0 = uncorroborated DIAMOND hit, not absent. Rows within a depth tier sort by it desc. |
| transport_substrate_resolution | string ('resolved', 'family_inferred') \| None (optional) | Transport rows only (None on metabolism rows). The gene's KG-authoritative TCDB substrate resolution, repeated on each of its transport rows — not a per-substrate fact ('family_inferred' = reachability, not capability). Row fact: substrate_depth. |
| reaction_id | string \| None (optional) | Full prefixed Reaction ID (e.g. 'kegg.reaction:R00253'). Metabolism rows only — see class-level note on undirected, non-reversible interpretation. |
| reaction_name | string \| None (optional) | Reaction systematic name + KEGG equation (raw KEGG value, can be lengthy; a small fraction of reactions have empty `''`). Metabolism rows only — see class-level note on undirected, non-reversible interpretation. |
| ec_numbers | list[string] \| None (optional) | EC classification(s) for this reaction. Empty list on reactions without an EC annotation. None on transport rows. |
| mass_balance | string ('balanced', 'unbalanced') \| None (optional) | Reaction mass-balance status. None on transport rows. |
| tcdb_family_id | string \| None (optional) | Full prefixed TcdbFamily ID (e.g. 'tcdb:3.A.1.4.5'). Transport rows only. |
| tcdb_family_name | string \| None (optional) | TCDB family name. For tc_family-level entries this is human-readable (e.g. 'The ATP-binding Cassette (ABC) Superfamily'); for tc_subfamily / tc_specificity it falls back to the tcdb_id. Transport rows only. |
| metabolite_id | string | Full prefixed Metabolite ID (e.g. 'kegg.compound:C00086'). |
| metabolite_name | string | Metabolite display name (e.g. 'Urea'). |
| metabolite_formula | string \| None (optional) | Hill-notation formula; null on a minority of metabolites (transport-only ChEBI generics). |
| metabolite_mass | float \| None (optional) | Monoisotopic mass (Da); null on a minority of metabolites. |
| metabolite_chebi_id | string \| None (optional) | ChEBI numeric ID; populated on most metabolites. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| gene_category | string \| None (optional) | Curated `Gene.gene_category` value (e.g. 'Transport', 'Amino acid metabolism'). Verbose only. |
| metabolite_inchikey | string \| None (optional) | Structural fingerprint. Verbose only. |
| metabolite_smiles | string \| None (optional) | Canonical SMILES. Verbose only. |
| metabolite_mnxm_id | string \| None (optional) | MetaNetX ID (e.g. 'MNXM731'). Verbose only. |
| metabolite_hmdb_id | string \| None (optional) | HMDB ID (e.g. 'HMDB0000122'). Verbose only. |
| reaction_mnxr_id | string \| None (optional) | Reaction MetaNetX ID. Verbose, metabolism rows only. |
| reaction_rhea_ids | list[string] \| None (optional) | Rhea reaction cross-refs. Verbose, metabolism rows only. |
| tcdb_level_kind | string ('tc_class', 'tc_subclass', 'tc_family', 'tc_subfamily', 'tc_specificity') \| None (optional) | TCDB hierarchy level of the annotated family (ontology convention). Verbose, transport rows only. Does NOT drive `substrate_depth` — a family-level node can be 'most_specific' for a substrate. |
| tc_class_id | string \| None (optional) | TCDB class ancestor (e.g. 'tcdb:3' for Primary Active Transporters). Pre-computed pointer. Verbose, transport rows only. |

## Few-shot examples

### Example 1: Single-gene drill-down — resolved transporter (Workflow D)

```example-call
metabolites_by_gene(locus_tags=["PMM0392"], organism="Prochlorococcus MED4", evidence_sources=["transport"])
```

### Example 2: Single-gene drill-down — superfamily-only gene (reachability, not capability)

```example-call
metabolites_by_gene(locus_tags=["PMM0913"], organism="Prochlorococcus MED4", limit=5)
```

### Example 3: Urease subunits (canonical detail-row example)

```example-call
metabolites_by_gene(locus_tags=["PMM0963", "PMM0964", "PMM0965"], organism="Prochlorococcus MED4", limit=5)
```

### Example 4: Workflow A (N-source marquee) — DE batch with element filter

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
          by_element confirms N-presence dominance;
          by_gene[].transport_substrate_resolution separates genes whose
          N-substrate breadth is a real call from superfamily reachability.

Step 3 (optional): list_metabolites(metabolite_ids=[top_N_metabolite_ids])
        → cross-refs, mass, formula, full pathway names.
```

### Example 5: Workflow C (cluster characterization) — chemistry of a co-expressed cluster

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

### Example 6: Cross-feeding workflow — MBG → GBM bridge

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

### Example 7: Currency-cofactor strip — exclude ATP/ADP/NADH/NADPH/H2O on a chemistry rollup

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

### Example 8: Conservative-cast transporter slice (mute the rollup blowup)

```example-call
metabolites_by_gene(locus_tags=["PMM0434", "PMM0913"], organism="Prochlorococcus MED4", substrate_depth=["most_specific"], evidence_sources=["transport"], limit=5)
```

## Chaining patterns

```
differential_expression_by_gene(organism=..., direction='up') → metabolites_by_gene(locus_tags=DE_genes, organism=..., metabolite_elements=['N']) (Workflow A — N-source marquee)
genes_in_cluster(cluster_ids=...) → metabolites_by_gene(locus_tags=cluster_genes, organism=...) (Workflow C — cluster chemistry characterization)
genes_by_function(search_text=..., organism=...) → metabolites_by_gene(locus_tags=function_hit_genes, organism=...) (Workflow C variant — function-search chemistry)
gene_overview(locus_tags=[...]) → per-row reaction_count/catalyzed_metabolite_count > 0 → metabolites_by_gene(locus_tags=chemistry_genes, organism=...)
gene_overview(locus_tags=[...]) → per-row transport_substrate_resolution='resolved' (read tcdb_evidence_score_max first) → metabolites_by_gene(locus_tags=[...], organism=..., evidence_sources=['transport']) — distinct metabolites in the rows equal transported_metabolite_count
metabolites_by_gene → top_metabolites → list_metabolites(metabolite_ids=[top_metabolite_ids]) for richer per-metabolite cross-refs (mass, formula, full pathway names)
metabolites_by_gene → top_metabolites → list_metabolites(metabolite_ids=[top_metabolite_ids], organism_names=[partner_organism]) for cross-organism presence (cross-feeding seed)
metabolites_by_gene → top_metabolites → genes_by_metabolite(metabolite_ids=[top_metabolite_ids], organism=PARTNER_ORGANISM) (cross-feeding bridge — catalysts + transporters in partner)
metabolites_by_gene → top_metabolite_pathways → list_metabolites(pathway_ids=[metabolite_pathway_id]) for the full metabolite roster of the pathway (not just gene-set hits)
metabolites_by_gene → top_metabolite_pathways → genes_by_ontology(ontology='kegg', term_ids=[metabolite_pathway_id], organism=...) for gene-KO-mediated pathway annotations (different surface — see top_metabolite_pathways naming disambiguation)
metabolites_by_gene → top_metabolite_pathways → pathway_enrichment(...) when gene-set hypothesis test is the goal
metabolites_by_gene → top_reactions → genes_by_ontology(ontology='ec', term_ids=[ec_number], organism=...) for genes in adjacent reactions
metabolites_by_gene → top_tcdb_families → genes_by_ontology(ontology='tcdb', term_ids=[tcdb_family_id], organism=...) for sibling genes in the same family
metabolites_by_gene → by_gene (transport_substrate_resolution='family_inferred') → gene_ontology_terms(locus_tags=[...], ontology='tcdb', organism=...) to see every TCDB family the gene is attached to, including ancestors superseded in the rows here
metabolites_by_gene → not_matched (locus_tags with no chemistry edges) → gene_overview(locus_tags=not_matched) for annotation context (most are richly-annotated non-chemistry genes — DNA gyrase, signaling, etc. — not annotation gaps)
```

## Common mistakes

- Gene-anchored (locus_tags → metabolites). The metabolite-anchored mirror is `genes_by_metabolite` (metabolite → genes); both share the same row class, discriminators and per-arm filter scope.

- Single-organism enforced (mirrors `differential_expression_by_gene` and `genes_by_metabolite`). There is no `organisms` list. For cross-organism / cross-feeding work: call MBG once on the focal organism, take `top_metabolites`, then route to `genes_by_metabolite(metabolite_ids=[...], organism=partner)` (or `list_metabolites(metabolite_ids=[...], organism_names=[partner])` for presence-only).

- `'metabolomics'` is NOT accepted in `evidence_sources` here — the Pydantic Literal allows only `('metabolism', 'transport')`. The metabolomics path (`MetaboliteAssay → Metabolite`) has no Gene anchor, so a metabolomics-only metabolite contributes no rows from this tool. For measurement evidence, use `list_metabolite_assays` / `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay`. Same divergence as `genes_by_metabolite`.

- Transport trust reads top down, exactly as on `genes_by_metabolite`: (1) `tcdb_evidence_score` (row) / `tcdb_evidence_score_max` (in `by_gene`) — rank by it, never filter; (2) gene-level `transport_substrate_resolution` in `by_gene` and repeated on every transport row of that gene (`family_inferred` = reachability through a lumping family, not capability; `resolved` = at least one non-lumping deepest attachment; metabolism rows read `None`); (3) per-row `substrate_depth` (`most_specific` = most specific SURVIVING node in the gene-pruned hierarchy, which can be a family node; `inherited` = came down from an ancestor's substrate set). When the auto-warning fires, `substrate_depth=['most_specific']` does NOT remove `family_inferred` genes (PMM0913 keeps 242 such rows) — only the gene-level resolution guards against reading their substrates. Full ladder and the depth-filter decision (conservative cast vs broad screen): `docs://analysis/metabolites`.

- Transport rows are deepest-attachment projections. A gene attached to a TCDB family AND to one of that family's descendants contributes rows only through the descendant; the ancestor's substrate rollup is intentionally absent. Consequently distinct metabolites across a gene's transport rows equal `gene_overview.transported_metabolite_count` (PMM0392: 13, not the ABC-superfamily plateau), and metabolite-side distinct genes equal `list_metabolites.transporter_gene_count`. To see a gene's full family membership including superseded ancestors, use `gene_ontology_terms(ontology='tcdb')`.

- Every result row has the same key set — cross-arm fields are explicitly `None` on rows from the other arm (metabolism rows have `substrate_depth`/`tcdb_evidence_score`/`transport_substrate_resolution`/`tcdb_family_id`/`tcdb_family_name` = None; transport rows have `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` = None). Use `row['substrate_depth']` (KeyError-free) rather than `row.get('substrate_depth')` if the difference matters.

- Reaction-arm rows are NOT directional — KG reactions carry neither a substrate-vs-product role on `Reaction_has_metabolite` nor an `is_reversible` flag. Read `evidence_source='metabolism'` rows as 'gene catalyses a reaction *involving* this metabolite,' never as 'produces X' / 'consumes Y' / 'reversibly interconverts'. The KG limitation is permanent (KEGG lacks both upstream).

- `by_element` envelope is presence-only — count of distinct metabolites containing each element at all. NOT stoichiometric (atom counts live in `metabolite.formula`); NOT mass-balanced (KG `Reaction_has_metabolite` is undirected and carries no substrate/product role).

- There is no `top_genes` envelope field. The per-gene rollup IS `by_gene` (one entry per input locus_tag, populated identically in summary and detail modes — `rows` / `metabolite_count` / `reaction_count` / `transporter_count` / `metabolism_rows` / `transport_most_specific_rows` / `transport_inherited_rows` / `transport_substrate_resolution` / `tcdb_evidence_score_max`). The compound-anchored counterpart `top_metabolites` exists (sorted by gene_count); there's no symmetric `top_genes` because gene-anchored aggregation already lives in `by_gene`. Inspect the actual response shape before assuming a field — don't extrapolate from `genes_by_metabolite.top_genes` (different tool, different shape) or `top_*` patterns on other tools.

- `gene_categories` filter is partially redundant with `locus_tags` input (since the input already constrains the gene set). It's useful only as further narrowing within a broad batch — e.g. `locus_tags=DE_genes, gene_categories=['Transport and binding']` to slice DE chemistry to transport-classified genes only. Don't use it as the primary anchor.

- `ec_numbers` and `mass_balance` are metabolism-arm-only filters — they DO NOT suppress transport rows. Transport rows pass through unchanged. To restrict to metabolism alone, combine with `evidence_sources=['metabolism']`. Symmetrically, `substrate_depth` narrows transport rows only and metabolism rows are unaffected. Per-arm filter scope is predictable + composable; it is NOT soft-exclude. `metabolite_elements`, `metabolite_ids`, `metabolite_pathway_ids`, and `gene_categories` are the only filters that narrow both arms uniformly.

- `top_metabolite_pathways` here means *KEGG pathways the gene set's chemistry reaches* (via `Reaction_in_kegg_pathway` + `Metabolite_in_pathway`). These are NOT the same as gene-KO-mediated pathway annotations (where pathway membership is asserted by the gene's KO assignment) — those live in `genes_by_ontology(ontology='kegg', term_ids=[...], organism=...)`. The two are distinct surfaces: chemistry-reach (this tool) vs KO-annotation (`genes_by_ontology`). For metabolic pathway analysis with a hypothesis test, use `pathway_enrichment` instead.

- `metabolite_elements` is presence-only AND-of (not formula substring). `['N']` keeps metabolites whose `Metabolite.elements` Hill-parsed list contains 'N'. `['N', 'P']` requires BOTH N and P. Never substring-match on `formula` — Hill notation has element-clash footguns: `'Cl'` contains `'C'`, `'Na'` contains `'N'`. Use the `metabolite_elements` filter, never grep `formula`.

- Use `summary=True` for batch DE inputs (50+ locus_tags). Detail rows can exceed 1,000 quickly even after the depth-tier sort; the envelope rollups (top_metabolites, top_metabolite_pathways, top_reactions, top_tcdb_families, by_element, by_gene, top_gene_categories) are the actually-useful artifact at that scale.

- `not_found.locus_tags` vs `not_matched`. `not_found.locus_tags` = locus_tags that don't resolve to any Gene in the requested organism (typo, wrong organism, gene removed in KG rebuild). `not_matched` = locus_tags that DO resolve to a Gene but have zero chemistry edges (no `Gene_catalyzes_reaction` AND no `Gene_has_tcdb_family`). Most MED4 genes fall into the `not_matched` bucket (roughly 1,170 of MED4's ~1,970 genes carry no chemistry edge) — most are richly-annotated non-chemistry genes (DNA gyrase, queG, signaling modules), not annotation gaps. Pivot via `gene_overview(locus_tags=not_matched)` for annotation context.

- When `top_metabolites` is dominated by ATP / ADP / NADH / NADPH / H2O, pass `exclude_metabolite_ids=[<kegg.compound:Cxxxxx>]` to strip the currency-cofactor noise. Set-difference semantics with `metabolite_ids` — exclude wins on overlap (silent). Per-arm scope: exclude applies on BOTH metabolism + transport arms (mirrors `metabolite_ids`). KG namespace is `kegg.compound:` (not `chebi:`).

- Detail rows are direction-agnostic. The transport edge (`Tcdb_family_transports_metabolite`) does not distinguish substrate from product, and the metabolism arm's `Reaction_has_metabolite` edge doesn't either (KEGG equation order is arbitrary). To distinguish, layer transcriptional evidence (`differential_expression_by_gene`) and functional annotation (`gene_overview` Pfam / KEGG KO names like `*-synthase` vs `*-permease`).

```mistake
metabolites_by_gene(locus_tags=[...], organism=..., substrate_depth=['family_inferred'])  # retired value — raises with a rename pointer
```

```correction
metabolites_by_gene(locus_tags=[...], organism=..., substrate_depth=['inherited'])  # valid values: most_specific, inherited
```

```mistake
metabolites_by_gene(metabolite_ids=['C00064'])  # then treating `C00064` in `not_found` as 'no such metabolite'
```

```correction
Bare / xref metabolite IDs on `metabolite_ids` / `exclude_metabolite_ids` are resolved via
the node's cross-references before the query runs: `C00064` →
`kegg.compound:C00064`, `CHEBI:17234` / `17234` → the `chebi_id` match,
`HMDB0000122` → `hmdb_id`, `MNXM1095050` → `mnxm_id`. Canonical forms
(`kegg.compound:` / `chebi:` / `mnx:`) pass through untouched. Coerced
inputs are listed in envelope `resolved_aliases` (`{input: [canonical, ...]}`).
CHEBI / HMDB / MNXM xrefs are not unique — an ambiguous input expands to
ALL matching metabolites and appends a `warnings` entry; pass the canonical
id to narrow. Unresolved inputs stay verbatim and surface in `not_found`
in the form you passed. Exclude-wins-on-overlap is computed on the canonical IDs, so currency-cofactor exclude lists in either form behave identically.

```

- See `docs://analysis/metabolites` for the 3 source pipelines decision tree (metabolism / transport / metabolomics) and the transport trust ladder, and `docs://guide/concepts` for the chemistry layer overview.

## Package import equivalent

```python
from multiomics_explorer import metabolites_by_gene

result = metabolites_by_gene(locus_tags=..., organism=...)
# returns dict with keys: total_matching, returned, offset, truncated, warnings, resolved_aliases, not_found, not_matched, by_gene, by_evidence_source, by_substrate_depth, by_element, by_element_truncated, top_metabolites, top_reactions, top_tcdb_families, top_gene_categories, top_metabolite_pathways, top_metabolite_pathways_truncated, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
