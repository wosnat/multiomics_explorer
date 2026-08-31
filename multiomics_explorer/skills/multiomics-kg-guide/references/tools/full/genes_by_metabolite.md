# genes_by_metabolite

## What it does

Metabolite IDs to gene catalysts (via Reaction) and transporters (via TcdbFamily, deepest attachment) in ONE organism.

Use for the compound-anchored direction; the gene-anchored mirror is `metabolites_by_gene`, family-level TCDB `genes_by_ontology`.
Filters: metabolite_ids (+exclude), organism, ec_numbers, metabolite_pathway_ids, gene_categories, substrate_depth, evidence_sources.
Returns: by_metabolite, by_evidence_source, by_substrate_depth, top_genes, top_reactions, top_tcdb_families, not_matched; one row = one gene × metabolite.
docs://tools/genes_by_metabolite; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| metabolite_ids | list[string] | — | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| ec_numbers | list[string] \| None | None | Narrow metabolism rows to those whose Reaction carries any of these EC numbers. **Metabolism arm only — does not affect transport rows**, which are returned unchanged. To restrict to metabolism rows alone, combine with `evidence_sources=['metabolism']`. E.g. ['6.3.1.2'] for glutamine synthetase. |
| metabolite_pathway_ids | list[string] \| None | None | Filter to rows where the **metabolite** is in any of these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` (transport-extended), so applies uniformly to both arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway annotations, route through `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)` first to obtain locus_tags. `not_found.metabolite_pathway_ids` lists IDs that don't exist as a KeggTerm. |
| mass_balance | string ('balanced', 'unbalanced') \| None | None | Narrow metabolism rows to those whose Reaction has this mass balance status. **Metabolism arm only — does not affect transport rows**. Combine with `evidence_sources=['metabolism']` to restrict to metabolism rows alone. |
| gene_categories | list[string] \| None | None | Filter on `Gene.gene_category` (exact match, applies to both arms uniformly). Use `list_filter_values(filter_type="gene_category")` to discover valid values. |
| substrate_depth | list[string ('most_specific', 'inherited')] \| None | None | Keep transport rows whose edge `substrate_depth` is in this list. 'most_specific' = most specific surviving transporter node for the substrate (gene-pruned hierarchy, not a curation level). Transport arm only. |
| evidence_sources | list[string ('metabolism', 'transport')] \| None | None | Path selector — restricts which arms execute. Set to `['metabolism']` to skip transport entirely (no rollup noise); `['transport']` to skip metabolism. Default fires both arms. Note: `'metabolomics'` is NOT a valid value here — metabolomics evidence has no gene anchor and surfaces only in `list_metabolites`. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 10 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, warnings, resolved_aliases, not_found, not_matched, by_metabolite, by_evidence_source, by_substrate_depth, top_reactions, top_tcdb_families, top_gene_categories, top_genes, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

- **total_matching** (int): Total row count after all filters, across both arms.
- **returned** (int): Number of rows in `results` (≤ `limit`).
- **offset** (int): Echo of the requested offset.
- **truncated** (bool): True when `offset + limit < total_matching`.
- **warnings** (list[string]): Diagnostic strings. Currently emitted: inherited-dominance auto-warning when `substrate_depth='inherited'` rows are the transport-arm majority and `substrate_depth` was not set explicitly; bare-ID collision notes (one input → several metabolites, expanded to all); a `gene_categories` value not found in the live vocabulary.
- **resolved_aliases** (object): Bare / xref metabolite inputs coerced to canonical IDs, `{input: [canonical, ...]}` — only coerced entries, across both `metabolite_ids` and `exclude_metabolite_ids`. A list longer than 1 is a collision (expanded to all; see `warnings`).
- **not_found** (GbmNotFound): Inputs that did not resolve to a KG node — see model.
- **not_matched** (list[string]): Input metabolite_ids that exist as Metabolite nodes but produced zero rows in this organism slice (under the active filters). Distinct from `not_found.metabolite_ids` (those don't exist at all).
- **by_metabolite** (list[GbmByMetabolite]): Per-metabolite rollup. One entry per input metabolite_id that produced ≥1 row.
- **by_evidence_source** (list[GbmByEvidenceSource]): Frequency over `evidence_source` values present in the slice (≤2 entries).
- **by_substrate_depth** (list[GbmBySubstrateDepth]): Frequency over `substrate_depth` values across transport rows only (≤2 entries; metabolism rows are excluded).
- **top_reactions** (list[GbmTopReaction]): Top 10 reactions by gene_count in the metabolism arm. summary=True returns the full ranked list.
- **top_reactions_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **top_tcdb_families** (list[GbmTopTcdbFamily]): Top 10 TCDB families by gene_count in the transport arm. summary=True returns the full ranked list.
- **top_tcdb_families_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **top_gene_categories** (list[GbmTopGeneCategory]): Top 10 gene categories by gene_count across both arms.
- **top_genes** (list[GbmTopGene]): Top 10 genes by combined reaction + transporter breadth across both arms. summary=True returns the full ranked list.
- **top_genes_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
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

### Example 3: Narrow to the most specific surviving transporter nodes (substrate_depth filter)

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4", substrate_depth=["most_specific"], evidence_sources=["transport"])
```

*The urtABCDE rows only: no metabolism rows (evidence_sources excludes them) and no inherited rows (substrate_depth drops the superfamily-level attachments), so `by_substrate_depth` has a single bucket and no auto-warning fires. Read tcdb_evidence_score per row to rank within the slice — never as a cut-off.*

```example-response
{
  "total_matching": 10,
  "returned": 10,
  "offset": 0,
  "truncated": false,
  "warnings": [],
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": [],
  "by_metabolite": [
    {
      "metabolite_id": "kegg.compound:C00086",
      "name": "Urea",
      "formula": "CH4N2O",
      "rows": 10,
      "gene_count": 5,
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 10,
      "transport_inherited_rows": 0
    }
  ],
  "by_evidence_source": [{"evidence_source": "transport", "count": 10}],
  "by_substrate_depth": [{"substrate_depth": "most_specific", "count": 10}],
  "top_reactions": [],
  "top_reactions_truncated": null,
  "top_tcdb_families": [
    {
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (",
      "level_kind": "tc_specificity",
      "substrate_depth": "most_specific",
      "gene_count": 5,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.4.5",
      "tcdb_family_name": "The high affinity urea/thiourea/hydroxyurea porter",
      "level_kind": "tc_specificity",
      "substrate_depth": "most_specific",
      "gene_count": 5,
      "metabolite_count": 1
    }
  ],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [{"category": "Stress response and adaptation", "gene_count": 5}],
  "top_genes": [
    {
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 2,
      "transport_inherited_rows": 0,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.6
    },
    {
      "locus_tag": "PMM0971",
      "gene_name": "urtB",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 2,
      "transport_inherited_rows": 0,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.8
    },
    {
      "locus_tag": "PMM0972",
      "gene_name": "urtC",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 2,
      "transport_inherited_rows": 0,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.8
    },
    {
      "locus_tag": "PMM0973",
      "gene_name": "urtD",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 2,
      "transport_inherited_rows": 0,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.8
    },
    {
      "locus_tag": "PMM0974",
      "gene_name": "urtE",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 2,
      "transport_inherited_rows": 0,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.8
    }
  ],
  "top_genes_truncated": null,
  "gene_count_total": 5,
  "reaction_count_total": 0,
  "transporter_count_total": 2,
  "metabolite_count_total": 1,
  "results": [
    {
      "locus_tag": "PMM0971",
      "gene_name": "urtB",
      "product": "ABC-type urea transporter, permease component",
      "evidence_source": "transport",
      "substrate_depth": "most_specific",
      "tcdb_evidence_score": 0.8,
      "transport_substrate_resolution": "resolved",
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (",
      "metabolite_id": "kegg.compound:C00086",
      "metabolite_name": "Urea",
      "metabolite_formula": "CH4N2O",
      "metabolite_mass": 60.056,
      "metabolite_chebi_id": "134711"
    },
    {
      "locus_tag": "PMM0972",
      "gene_name": "urtC",
      "product": "ABC-type urea transporter, membrane component",
      "evidence_source": "transport",
      "substrate_depth": "most_specific",
      "tcdb_evidence_score": 0.8,
      "transport_substrate_resolution": "resolved",
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (",
      "metabolite_id": "kegg.compound:C00086",
      "metabolite_name": "Urea",
      "metabolite_formula": "CH4N2O",
      "metabolite_mass": 60.056,
      "metabolite_chebi_id": "134711"
    },
    {
      "locus_tag": "PMM0973",
      "gene_name": "urtD",
      "product": "ABC-type urea transporter, ATP-binding component UrtD",
      "evidence_source": "transport",
      "substrate_depth": "most_specific",
      "tcdb_evidence_score": 0.8,
      "transport_substrate_resolution": "resolved",
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (",
      "metabolite_id": "kegg.compound:C00086",
      "metabolite_name": "Urea",
      "metabolite_formula": "CH4N2O",
      "metabolite_mass": 60.056,
      "metabolite_chebi_id": "134711"
    },
    ...
  ]
}
```

### Example 4: Family-level most_specific — nitrite in MED4 (auto-warning fires)

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00088"], organism="Prochlorococcus MED4", evidence_sources=["transport"])
```

*Nitrite surfaces as substrate_depth='most_specific' at a FAMILY node (tcdb:2.A.16, formate-nitrite transporter family): no gene in the KG is annotated below it for this substrate, so the family is the most specific surviving node — 'most_specific' is a position in the gene-pruned hierarchy, not a curation level. The remaining rows are inherited via the ABC superfamily, and the auto-warning fires because inherited rows dominate. Rows are deepest-attachment projections: genes also attached to a descendant of tcdb:3.A.1 contribute only their deepest attachment.*

```example-response
{
  "total_matching": 29,
  "returned": 10,
  "offset": 0,
  "truncated": true,
  "warnings": [
    "Most transport rows are `inherited` (23 of 29) — the substrate is reached through a broader family's substrate list, ..."
  ],
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": [],
  "by_metabolite": [
    {
      "metabolite_id": "kegg.compound:C00088",
      "name": "Nitrite",
      "formula": "NO2",
      "rows": 29,
      "gene_count": 27,
      "reaction_count": 0,
      "transporter_count": 5,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 6,
      "transport_inherited_rows": 23
    }
  ],
  "by_evidence_source": [{"evidence_source": "transport", "count": 29}],
  "by_substrate_depth": [{"substrate_depth": "inherited", "count": 23}, {"substrate_depth": "most_specific", "count": 6}],
  "top_reactions": [],
  "top_reactions_truncated": null,
  "top_tcdb_families": [
    {
      "tcdb_family_id": "tcdb:3.A.1",
      "tcdb_family_name": "The ATP-binding Cassette (ABC) Superfamily",
      "level_kind": "tc_family",
      "substrate_depth": "inherited",
      "gene_count": 20,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:2.A.1",
      "tcdb_family_name": "The Major Facilitator Superfamily (MFS)",
      "level_kind": "tc_family",
      "substrate_depth": "inherited",
      "gene_count": 3,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.16.1",
      "tcdb_family_name": "Four component nitrate/nitrite porter.",
      "level_kind": "tc_specificity",
      "substrate_depth": "most_specific",
      "gene_count": 3,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.16.2",
      "tcdb_family_name": "Bispecific cyanate/nitrite transporter.",
      "level_kind": "tc_specificity",
      "substrate_depth": "most_specific",
      "gene_count": 2,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:2.A.16",
      "tcdb_family_name": "The Telurite-resistance/Dicarboxylate Transporter (TDT) Family",
      "level_kind": "tc_family",
      "substrate_depth": "most_specific",
      "gene_count": 1,
      "metabolite_count": 1
    }
  ],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [
    {"category": "Transport", "gene_count": 10},
    {"category": "Stress response and adaptation", "gene_count": 5},
    {"category": "Central intermediary metabolism", "gene_count": 3},
    {"category": "Amino acid metabolism", "gene_count": 1},
    {"category": "Carbohydrate metabolism", "gene_count": 1},
    ...
  ],
  "top_genes": [
    {
      "locus_tag": "PMM0370",
      "gene_name": "cynA",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 2,
      "transport_inherited_rows": 0,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.6
    },
    {
      "locus_tag": "PMM0371",
      "gene_name": "cynB",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 2,
      "transport_inherited_rows": 0,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.8
    },
    {
      "locus_tag": "PMM0072",
      "gene_name": "sufC",
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 0,
      "transport_inherited_rows": 1,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.4
    },
    {
      "locus_tag": "PMM0089",
      "gene_name": null,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 0,
      "transport_inherited_rows": 1,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.4
    },
    {
      "locus_tag": "PMM0097",
      "gene_name": "tolC",
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "transport_most_specific_rows": 0,
      "transport_inherited_rows": 1,
      "transport_substrate_resolution": "resolved",
      "tcdb_evidence_score_max": 0.4
    },
    ...
  ],
  "top_genes_truncated": true,
  "gene_count_total": 27,
  "reaction_count_total": 0,
  "transporter_count_total": 5,
  "metabolite_count_total": 1,
  "results": [
    {
      "locus_tag": "PMM0371",
      "gene_name": "cynB",
      "product": "cyanate ABC transporter, permease protein",
      "evidence_source": "transport",
      "substrate_depth": "most_specific",
      "tcdb_evidence_score": 0.8,
      "transport_substrate_resolution": "resolved",
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.16.1",
      "tcdb_family_name": "Four component nitrate/nitrite porter.",
      "metabolite_id": "kegg.compound:C00088",
      "metabolite_name": "Nitrite",
      "metabolite_formula": "NO2",
      "metabolite_mass": 46.005,
      "metabolite_chebi_id": "14658"
    },
    {
      "locus_tag": "PMM0372",
      "gene_name": "cynD",
      "product": "cyanate ABC transporter ATP-binding protein",
      "evidence_source": "transport",
      "substrate_depth": "most_specific",
      "tcdb_evidence_score": 0.8,
      "transport_substrate_resolution": "resolved",
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.16.1",
      "tcdb_family_name": "Four component nitrate/nitrite porter.",
      "metabolite_id": "kegg.compound:C00088",
      "metabolite_name": "Nitrite",
      "metabolite_formula": "NO2",
      "metabolite_mass": 46.005,
      "metabolite_chebi_id": "14658"
    },
    {
      "locus_tag": "PMM0371",
      "gene_name": "cynB",
      "product": "cyanate ABC transporter, permease protein",
      "evidence_source": "transport",
      "substrate_depth": "most_specific",
      "tcdb_evidence_score": 0.8,
      "transport_substrate_resolution": "resolved",
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.16.2",
      "tcdb_family_name": "Bispecific cyanate/nitrite transporter.",
      "metabolite_id": "kegg.compound:C00088",
      "metabolite_name": "Nitrite",
      "metabolite_formula": "NO2",
      "metabolite_mass": 46.005,
      "metabolite_chebi_id": "14658"
    },
    ...
  ]
}
```

### Example 5: Pathway-anchored — N-metabolism only

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086", "kegg.compound:C00064", "kegg.compound:C00088"], organism="Prochlorococcus MED4", metabolite_pathway_ids=["kegg.pathway:ko00910"])
```

### Example 6: Currency-cofactor strip — exclude ATP/ADP/NADH/NADPH/H2O on a multi-metabolite drill

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

### Example 7: EC-anchored metabolism narrowing (transport rows still returned)

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00064"], organism="Prochlorococcus MED4", ec_numbers=["6.3.1.2"])
```

## Chaining patterns

```
list_metabolites(...) → genes_by_metabolite(metabolite_ids=[chosen_ids], organism=...)
list_metabolites (per-row `transporter_gene_count > 0`) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['transport']) — distinct genes in the transport rows, summed over organisms, equal that count
differential_expression_by_gene(...) → top hits → metabolites_by_gene(locus_tags=...) → genes_by_metabolite for the symmetric metabolite-anchored view
Workflow A (N-source): list_metabolites(elements=['N']) → genes_by_metabolite(metabolite_ids=[N-bearing IDs], organism=...) for catalysts + transporters
Workflow B (cross-feeding): genes_by_metabolite called once per organism on the same metabolite_ids; intersect/diff locus_tag result sets client-side
genes_by_metabolite → top_genes → differential_expression_by_gene(locus_tags=top_genes_locus_tags, organism=...) for transcriptional response
genes_by_metabolite → top_genes (transport_substrate_resolution='resolved', high tcdb_evidence_score_max) → gene_overview(locus_tags=...) then metabolites_by_gene for the gene's full substrate set
genes_by_metabolite → top_genes → gene_overview(locus_tags=...) for richer per-gene routing context
genes_by_metabolite → top_tcdb_families → genes_by_ontology(ontology='tcdb', term_ids=[top_tcdb_families[i].tcdb_family_id], organism=...) for sibling genes in the same family
genes_by_metabolite → transport rows → gene_ontology_terms(locus_tags=[...], ontology='tcdb', organism=...) to see every TCDB family a gene is attached to, including ancestors superseded in the rows here
genes_by_metabolite → top_reactions → genes_by_ontology(ontology='ec', term_ids=[ec_number], organism=...) for genes in adjacent reactions
genes_by_metabolite → top_reactions / top_genes → pathway_enrichment for KEGG-pathway context
```

## Common mistakes

- Metabolite-anchored (metabolite → genes). The gene-anchored mirror is `metabolites_by_gene` (locus_tags → metabolites); both share the same row class, discriminators and per-arm filter scope, so read whichever matches your anchor rather than post-filtering the other.

- Read transport evidence as a three-level trust ladder, top down. (1) `tcdb_evidence_score` (row) / `tcdb_evidence_score_max` (gene, in `top_genes`) — how corroborated the gene × family call is. Rank by it, never filter by it; 0 means an uncorroborated hit, not an absent call (absent is `tcdb_evidence_score_max = None`). (2) Gene-level `transport_substrate_resolution` in `top_genes` — `family_inferred` means the gene's substrate breadth is reachability through a lumping family, not capability; `resolved` means AT LEAST ONE of the gene's deepest attachments is non-lumping, not all of them — a gene attached at both a specific family and the ABC superfamily is `resolved` and still carries the superfamily rollup. (3) Per-row `substrate_depth` — `most_specific` is the most specific SURVIVING transporter node for this substrate relative to the gene-pruned hierarchy; it can be a family node (nitrite via tcdb:2.A.16) and it is not a curation level. `inherited` rows came down from an ancestor's substrate set.

- Row-level `transport_substrate_resolution` is the GENE's resolution (the same KG value `gene_overview` and `top_genes[]` carry), repeated on every transport row of that gene — it is not a per-substrate fact and it does not vary across a gene's rows. Do not read `family_inferred` on a row as "this substrate is inferred": it says the gene's whole substrate breadth is reachability through a lumping family. The per-row fact is `substrate_depth`. Metabolism rows read `None` (union padding), never `resolved`. Group rows by locus_tag when you want one resolution per gene, or read `top_genes[]` directly.

- When the auto-warning fires (most transport rows are `inherited`), choose by question shape: `substrate_depth=['most_specific']` for conservative casts (cross-organism inference); no filter for broad-screen candidate enumeration (N-source DE), where inherited rows on real uptake genes are the biology you want. Both depths are annotations, neither is ground truth — see `docs://analysis/metabolites`.

- Transport rows are deepest-attachment projections. A gene attached to a TCDB family AND to one of that family's descendants contributes rows only through the descendant; the ancestor's substrate rollup is intentionally absent. Consequently distinct genes across the transport rows (summed over organisms) equal `list_metabolites.transporter_gene_count` and, gene-side, distinct metabolites equal `gene_overview.transported_metabolite_count`. To see a gene's full family membership including superseded ancestors, use `gene_ontology_terms(ontology='tcdb')`.

- Every result row has the same key set — cross-arm fields are explicitly `None` on rows from the other arm (metabolism rows have `substrate_depth`/`tcdb_evidence_score`/`transport_substrate_resolution`/`tcdb_family_id`/`tcdb_family_name` = None; transport rows have `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` = None). Use `row['substrate_depth']` (KeyError-free) rather than `row.get('substrate_depth')` if the difference matters.

- Reaction-arm rows are NOT directional — KG reactions carry neither a substrate-vs-product role on `Reaction_has_metabolite` nor an `is_reversible` flag. Read `evidence_source='metabolism'` rows as 'gene catalyses a reaction *involving* this metabolite,' never as 'produces X' / 'consumes Y' / 'reversibly interconverts'. The KG limitation is permanent (KEGG lacks both upstream).

- Filtering by `ec_numbers` does NOT restrict to metabolism only. Per-arm filter scope: `ec_numbers` and `mass_balance` narrow the metabolism arm WHERE; transport rows are returned UNCHANGED (no soft-exclude). Symmetrically, `substrate_depth` narrows transport only and metabolism rows are unaffected. To restrict to one arm, set `evidence_sources=['metabolism']` (or `['transport']`) explicitly. `metabolite_pathway_ids` and `gene_categories` are the only filters that narrow both arms uniformly.

- Single-organism enforced (mirrors `differential_expression_by_gene`). There is no `organisms` list. For cross-organism / cross-feeding work, call once per organism with the same metabolite_ids and combine locus_tag result sets client-side (Workflow B).

- `'metabolomics'` is NOT accepted in `evidence_sources` here — the Pydantic Literal allows only `('metabolism', 'transport')`. The metabolomics path (`MetaboliteAssay → Metabolite`) has no Gene anchor, so a metabolomics-only metabolite returns no rows from this tool. To inspect measurement evidence, use `list_metabolite_assays` / `assays_by_metabolite` instead. Same `_VALID_EVIDENCE_SOURCES` validator pattern as `list_metabolites`, intentionally divergent value set per the tool's biology.

- TCDB-class filtering does NOT belong here. There is no `tcdb_class_ids` parameter. TCDB is a first-class ontology — for "all genes in TCDB class 3.A.1 (ABC superfamily) for organism X", route through `genes_by_ontology(ontology='tcdb', term_ids=['tcdb:3.A.1'], organism=...)`. From here the drill-out path is `top_tcdb_families[i].tcdb_family_id` → `genes_by_ontology(ontology='tcdb', term_ids=[that_id], organism=...)`.

- `not_found.metabolite_ids` vs `not_matched`. `not_found.metabolite_ids` = IDs that don't exist as a Metabolite node at all (typo, wrong prefix, ChEBI ID not in our KG). `not_matched` = IDs whose Metabolite exists but produced zero rows in this organism slice under the active filters (e.g. transport-only metabolite curated for non-MED4 strains). Don't conflate them — `not_matched` may go to zero by relaxing filters or swapping organism; `not_found` won't.

- When the result is dominated by ATP / ADP / NADH / NADPH / H2O (currency cofactors that catalysts and transporters touch ubiquitously), pass `exclude_metabolite_ids=[<kegg.compound:Cxxxxx>]` to strip them. Set-difference semantics with `metabolite_ids` — exclude wins on overlap (silent). Per-arm scope: exclude applies on BOTH metabolism + transport arms (mirrors `metabolite_ids`). KG namespace is `kegg.compound:` (not `chebi:`).

- Transport rows are direction-agnostic. The `Tcdb_family_transports_metabolite` edge does not distinguish substrate from product, and the metabolism arm's `Reaction_has_metabolite` edge doesn't either (KEGG equation order is arbitrary). To distinguish substrate vs product, layer transcriptional evidence (`differential_expression_by_gene`) and functional annotation (`gene_overview` Pfam / KEGG KO names like `*-synthase` vs `*-permease`).

```mistake
genes_by_metabolite(metabolite_ids=[...], organism=..., substrate_depth=['substrate_confirmed'])  # retired value — raises with a rename pointer
```

```correction
genes_by_metabolite(metabolite_ids=[...], organism=..., substrate_depth=['most_specific'])  # valid values: most_specific, inherited
```

```mistake
genes_by_metabolite(metabolite_ids=['C00064'])  # then treating `C00064` in `not_found` as 'no such metabolite'
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
in the form you passed. Exclude-wins-on-overlap is computed on the canonical IDs, so `metabolite_ids=['C00064'], exclude_metabolite_ids=['kegg.compound:C00064']` excludes.

```

- See `docs://analysis/metabolites` for the 3 source pipelines decision tree (metabolism / transport / metabolomics) and the transport trust ladder, and `docs://guide/concepts` for the chemistry layer overview.

- `not_found.organism` is set when the `organism` name resolves to zero organisms — check it before reading an empty result as 'no chemistry here'.

- `limit` defaults to covering p75 of typical (metabolite × organism) UNION row distributions; coenzyme-tail queries (ATP, water) should page with `offset`.

## Package import equivalent

```python
from multiomics_explorer import genes_by_metabolite

result = genes_by_metabolite(metabolite_ids=..., organism=...)
# returns dict with keys: total_matching, returned, offset, truncated, warnings, resolved_aliases, not_found, not_matched, by_metabolite, by_evidence_source, by_substrate_depth, top_reactions, top_reactions_truncated, top_tcdb_families, top_tcdb_families_truncated, top_gene_categories, top_genes, top_genes_truncated, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
