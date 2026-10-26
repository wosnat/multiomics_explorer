# genes_by_metabolite

## What it does

Metabolite / `chebi.role:` IDs to genes in ONE organism via KEGG, TCDB and GO transport (GO rows: term definitions, not gene facts).

Use for compound → genes; mirror metabolites_by_gene; docs://analysis/transport.
Filters: metabolite_ids (+exclude, +stereo), ec_numbers, metabolite_pathway_ids, evidence_sources, include_tcdb_family_substrates, go_*.
Returns: by_metabolite, by_evidence_source(_combination), by_tcdb_route, tcdb_family_substrates_not_shown, top_genes/reactions/tcdb_families; row = gene × reaction|TCDB node|GO term × compound.
docs://tools/genes_by_metabolite; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| metabolite_ids | list[string] | — | Metabolite IDs in any form (KEGG, ChEBI, MNX, HMDB, InChIKey; bare or prefixed). Retired ids resolve (see resolved_aliases); removed compounds warn. `chebi.role:` ids reach TCDB / GO role edges. docs://analysis/transport. |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Must resolve to ONE organism — an ambiguous match (e.g. a genus word) raises; see list_organisms. |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; any id form, bare or prefixed, retired ids resolve (see resolved_aliases); exclude wins on overlap. |
| ec_numbers | list[string] \| None | None | Narrow metabolism rows to those whose Reaction carries any of these EC numbers. **Metabolism arm only — does not affect TCDB or GO transport rows**, which are returned unchanged. To restrict to metabolism rows alone, combine with `evidence_sources=['metabolism']`. E.g. ['6.3.1.2'] for glutamine synthetase. |
| metabolite_pathway_ids | list[string] \| None | None | Filter to rows where the **metabolite** is in any of these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` (transport-extended), so applies uniformly to all three arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway annotations, route through `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)` first to obtain locus_tags. `not_found.metabolite_pathway_ids` lists IDs that don't exist as a KeggTerm. |
| mass_balance | string ('balanced', 'unbalanced') \| None | None | Narrow metabolism rows to those whose Reaction has this mass balance status. **Metabolism arm only — does not affect TCDB or GO transport rows**. Combine with `evidence_sources=['metabolism']` to restrict to metabolism rows alone. |
| gene_categories | list[string] \| None | None | Filter on `Gene.gene_category` (exact match, applies to all three arms uniformly). Use `list_filter_values(filter_type="gene_category")` to discover valid values. |
| evidence_sources | list[string ('metabolism', 'transport', 'go_transport')] \| None | None | Path selector — restricts which arms execute (metabolism, transport, go_transport). Default fires all three. `['metabolism']` skips transport rollup noise. 'metabolomics' is NOT valid here (no gene anchor); see `list_metabolites`. |
| include_tcdb_family_substrates | bool | False | TCDB arm: also walk from the gene's family / subfamily calls down to their systems' substrates (tcdb_route='family'; a recall fallback for genes with no system). Adds rows only; ignored without the transport arm. |
| go_include_ancestors | bool | False | GO route only: also return inherited rows, where a gene's GO term reaches the target through is_a ancestors (go_term_depth > 0). Default False = directly annotated terms. |
| go_namespace | list[string ('molecular_function', 'biological_process')] \| None | None | GO arm only: keep GO rows whose gene->GO edge is in these namespaces. TCDB / KEGG rows untouched. Filtered result is always a subset of the unfiltered one. |
| go_evidence | list[string] \| None | None | GO arm only: keep GO rows whose gene->GO edge evidence is in this list (e.g. ['curated']; family_inferred, domain_inferred). Unknown values raise. TCDB / KEGG rows untouched; result is a subset of the unfiltered one. |
| include_stereo_forms | bool | False | Also query the generic <-> specific stereo forms of each metabolite_id (e.g. Cysteine <-> L-Cysteine; TCDB lists generic names, KEGG reactions use specific forms). Added rows carry via_stereo_form_of. Enantiomers are never added. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 10 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, warnings, stereo_relatives, stereo_forms_added, resolved_aliases, not_found, not_matched, by_metabolite, by_evidence_source, by_evidence_source_combination, by_tcdb_route, tcdb_family_substrates_not_shown, tcdb_family_substrates_skipped, rows_by_go_term_depth, top_reactions, top_tcdb_families, top_gene_categories, top_genes, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

- **total_matching** (int): Total row count after all filters, across all arms.
- **returned** (int): Number of rows in `results` (≤ `limit`).
- **offset** (int): Echo of the requested offset.
- **truncated** (bool): True when `offset + limit < total_matching`.
- **warnings** (list[string]): Diagnostics: stereo relatives with rows (first); genes reachable only via a family call (pass include_tcdb_family_substrates=True); breadth-capped superfamily starts; removed / chemical-role ids; unknown gene_categories.
- **stereo_relatives** (object): Input id -> its stereo forms with rows in this organism under the same filters, e.g. {'kegg.compound:C00736': [L-Cysteine entry]}. Counts never combine across forms. Empty with include_stereo_forms=True.
- **stereo_forms_added** (object): include_stereo_forms=True: input id -> stereo forms added to the query (e.g. {'kegg.compound:C00736': ['kegg.compound:C00097']}). Added ids with no rows are not in not_matched.
- **resolved_aliases** (object): Metabolite inputs resolved to a different canonical ID (bare, xref, secondary or retired ids), `{input: [canonical]}`, across `metabolite_ids` and `exclude_metabolite_ids`. Inputs already canonical are not listed.
- **not_found** (GbmNotFound): Inputs that did not resolve to a KG node — see model.
- **not_matched** (list[string]): Input metabolite_ids that exist as Metabolite nodes but produced zero rows in this organism slice (under the active filters). Distinct from `not_found.metabolite_ids` (those don't exist at all).
- **by_metabolite** (list[GbmByMetabolite]): Per-metabolite rollup. One entry per input metabolite_id that produced ≥1 row.
- **by_evidence_source** (list[GbmByEvidenceSource]): Frequency over `evidence_source` values present in the slice (≤3 entries).
- **by_evidence_source_combination** (list[EvidenceSourceCombination]): Gene x metabolite pairs per set of agreeing sources, pair_count desc. Agreement = independent routes naming the same pair; correlated (shared homology), so it raises confidence but does not prove. [] on empty.
- **by_tcdb_route** (list[GbmByTcdbRoute]): Frequency over `tcdb_route` across transport rows only, direct then family (≤2 entries; family only with include_tcdb_family_substrates=True).
- **tcdb_family_substrates_not_shown** (TcdbFamilySubstratesNotShown | None): Walk off: what include_tcdb_family_substrates=True would add ({genes, metabolites, rows}; zeros = nothing). Null when the walk is on (those rows are in results). Read it before concluding 'no transporter'.
- **tcdb_family_substrates_skipped** (list[TcdbFamilySubstrateSkipped]): Genes whose family-walk start was removed by the 200-substrate breadth cap (superfamily call, substrate unknown), e.g. ABC 3.A.1. Always computed.
- **rows_by_go_term_depth** (list[RowsByGoTermDepth] | None): GO route rows per `go_term_depth`, sorted by depth asc. Null unless the go_transport arm is active; depth > 0 rows need go_include_ancestors=True.
- **top_reactions** (list[GbmTopReaction]): Top 10 reactions by gene_count in the metabolism arm. summary=True returns the full ranked list.
- **top_reactions_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **top_tcdb_families** (list[GbmTopTcdbFamily]): Top 10 TCDB families by gene_count in the transport arm. summary=True returns the full ranked list.
- **top_tcdb_families_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **top_gene_categories** (list[GbmTopGeneCategory]): Top 10 gene categories by gene_count across all arms.
- **top_genes** (list[GbmTopGene]): Top 10 genes by combined reaction + transporter breadth (GO rows in go_transport_rows). summary=True returns the full ranked list.
- **top_genes_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **gene_count_total** (int): Distinct genes in the filtered slice (across all arms).
- **reaction_count_total** (int): Distinct reactions in the filtered metabolism arm.
- **transporter_count_total** (int): Distinct TcdbFamily nodes in the filtered transport arm.
- **metabolite_count_total** (int): Distinct metabolite_ids that produced ≥1 row.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0974' for MED4 urtE). |
| gene_name | string \| None (optional) | Curated gene name (e.g. 'urtE'); often null. |
| product | string \| None (optional) | Annotated gene product description (high-signal short label, e.g. 'ABC-type urea transporter, ATPase component UrtE'). |
| evidence_source | string ('metabolism', 'transport', 'go_transport') | Path to the metabolite: 'metabolism' = `Gene → Reaction → Metabolite`; 'transport' = `Gene → TCDB node → Metabolite` (see `tcdb_route`); 'go_transport' = `Gene → GO term → target`. Metabolomics has no gene anchor here. |
| tcdb_route | string ('direct', 'family') \| None (optional) | Transport rows only. 'direct' = the gene's tcdb_gate='direct' edge onto a TCDB system curated with the metabolite. 'family' = opt-in walk (include_tcdb_family_substrates) from a family / subfamily call down to its systems. |
| tcdb_calls | list[string] \| None (optional) | Transport rows only. Call kinds on the gene's gated TCDB edges along the row node's lineage, in precedence order (e.g. ['diamond_best_hit', 'eggnog']). The two diamond kinds are one source; only eggnog + diamond is independent agreement. |
| tcdb_identity | float \| None (optional) | Transport rows only. Percent identity of the row's representative TCDB edge (best hit > tier > eggnog); on family rows the gene's edge to the attached node. Null when that edge is eggnog. Rank within a route by it. |
| tcdb_direction | string ('uptake', 'export', 'unknown') \| None (optional) | Transport rows only. TCDB-stated `direction` of the row's node (the system; on family rows the attached node). Node-level, not a per-gene fact. |
| attached_tcdb_id | string \| None (optional) | Transport rows only. The TC node the gene's edge points at (e.g. 'tcdb:3.A.1.9'). Equals `tcdb_family_id` on direct and family rows. |
| tcdb_substrate_system_count | int \| None (optional) | Family rows only (null on direct rows): number of descendant TCDB systems of the attached node curated with this metabolite (e.g. 5). |
| reaction_id | string \| None (optional) | Full prefixed Reaction ID (e.g. 'kegg.reaction:R00253'). Metabolism rows only — see class-level note on undirected, non-reversible interpretation. |
| reaction_name | string \| None (optional) | Reaction systematic name + KEGG equation (raw KEGG value, can be lengthy; a small fraction of reactions have empty `''`). Metabolism rows only — see class-level note on undirected, non-reversible interpretation. |
| ec_numbers | list[string] \| None (optional) | EC classification(s) for this reaction. Empty list on reactions without an EC annotation. None on transport rows. |
| mass_balance | string ('balanced', 'unbalanced') \| None (optional) | Reaction mass-balance status. None on transport rows. |
| tcdb_family_id | string \| None (optional) | Full prefixed TcdbFamily ID (e.g. 'tcdb:3.A.1.4.5'). Transport rows only. |
| tcdb_family_name | string \| None (optional) | Name of `tcdb_family_id` (the system on direct rows, the attached family / subfamily on family rows), e.g. 'High affinity phosphate-specific transporter, PstABCS'. Transport rows only. |
| go_term_id | string \| None (optional) | GO route rows only. The gene's own GO term (e.g. 'go:0015891'). A term definition, not a gene fact: the term names the target; the gene is annotated to the term. |
| go_term_name | string \| None (optional) | Name of `go_term_id` (e.g. 'siderophore transport'). GO route rows only. |
| go_namespace | string ('molecular_function', 'biological_process') \| None (optional) | GO route rows only. Namespace of the term. BP terms are broader than MF ones (a process, not a specific activity). |
| go_evidence | string \| None (optional) | GO route rows only. Evidence class of the gene→GO annotation (e.g. 'curated'). |
| go_sources | list[string] \| None (optional) | GO route rows only. Annotation sources behind the gene→GO edge (e.g. ['ncbi']). |
| go_term_depth | int \| None (optional) | GO route rows only. 0 = the gene's own term names the target; n = is_a hops up to the naming ancestor (inherited; needs go_include_ancestors=True). |
| go_axiom_term_id | string \| None (optional) | GO route rows only. Term that names the target: the gene's own term at depth 0, the ancestor when inherited. |
| go_axiom_term_name | string \| None (optional) | Name of `go_axiom_term_id`. GO route rows only. |
| target_kind | string ('metabolite', 'chemical_role') \| None (optional) | What `metabolite_id` is: a 'metabolite' or a 'chemical_role' (e.g. siderophore, chebi.role:26672). Roles have no formula or mass. |
| metabolite_id | string | Full prefixed Metabolite ID (e.g. 'kegg.compound:C00086'). |
| metabolite_name | string | Metabolite display name (e.g. 'Urea'). |
| metabolite_formula | string \| None (optional) | Hill-notation formula; null on a minority of metabolites (transport-only ChEBI generics). |
| metabolite_mass | float \| None (optional) | Monoisotopic mass (Da); null on a minority of metabolites. |
| metabolite_chebi_id | string \| None (optional) | ChEBI numeric ID; populated on most metabolites. |
| via_stereo_form_of | string \| None (optional) | genes_by_metabolite with include_stereo_forms=True: the input id this row's metabolite is a stereo form of (e.g. 'kegg.compound:C00736'). Absent on rows for inputs. |
| stereo_relative_ids | list[string] \| None (optional) | metabolites_by_gene: stereo forms of this row's metabolite with genes in this organism (e.g. ['kegg.compound:C00097']); counts in envelope stereo_relatives. Absent when none. |
| go_chebi_ids | list[string] \| None (optional) | ChEBI ids carried by the GO term (e.g. ['CHEBI:26672']). Verbose, GO route rows only. |

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
| tcdb_level_kind | string ('tc_class', 'tc_subclass', 'tc_family', 'tc_subfamily', 'tc_system') \| None (optional) | TCDB hierarchy level of `tcdb_family_id` (ontology convention): always 'tc_system' on direct rows; 'tc_family' / 'tc_subfamily' on family rows. Verbose, transport rows only. |
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

### Example 3: Empty direct arm is not "no transporter" — orthophosphate in MED4 reads the family-substrates hint

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00009"], organism="Prochlorococcus MED4", evidence_sources=["transport"], summary=True)
```

*No MED4 gene points directly at a TC system curated with orthophosphate, so the transport arm is empty. The envelope still says what the opt-in walk would add: `tcdb_family_substrates_not_shown` = {genes: 4, metabolites: 1, rows: 4} (phnC, phnD, phnE, PMM0717 through subfamily tcdb:3.A.1.9), and the leading warning names `include_tcdb_family_substrates=True`. The Pst genes (pstA/B/C/S) are absent: their direct system tcdb:3.A.1.7.6 is curated by TCDB with triphosphate only, and no walk starts above a direct system. `tcdb_family_substrates_skipped` lists genes whose only call is on the ABC superfamily tcdb:3.A.1 (over 200 substrates, substrate unknown).*

```example-response
{
  "total_matching": 0,
  "returned": 0,
  "offset": 0,
  "truncated": false,
  "warnings": [
    "No gene reaches these metabolites through a direct TCDB system call in this organism. 4 genes reach these metabolites..."
  ],
  "stereo_relatives": {},
  "stereo_forms_added": {},
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": ["kegg.compound:C00009"],
  "by_metabolite": [],
  "by_evidence_source": [],
  "by_evidence_source_combination": [],
  "by_tcdb_route": [],
  "tcdb_family_substrates_not_shown": {"genes": 4, "metabolites": 1, "rows": 4},
  "tcdb_family_substrates_skipped": [
    {"locus_tag": "PMM0449", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0450", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0913", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0977", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546}
  ],
  "rows_by_go_term_depth": null,
  "top_reactions": [],
  "top_reactions_truncated": null,
  "top_tcdb_families": [],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [],
  "top_genes": [],
  "top_genes_truncated": null,
  "gene_count_total": 0,
  "reaction_count_total": 0,
  "transporter_count_total": 0,
  "metabolite_count_total": 0,
  "results": []
}
```

### Example 4: Opt in to the family walk — phnC/D/E and PMM0717 reach orthophosphate through subfamily tcdb:3.A.1.9

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00009"], organism="Prochlorococcus MED4", evidence_sources=["transport"], include_tcdb_family_substrates=True)
```

*The walk is a fallback for genes TCDB could not place in a system. It starts from a gene's `annotated` family or subfamily call (never a class or subclass, never above one of the gene's direct systems, never from a node curated with over 200 substrates) and walks down to the systems TCDB curates. Each row is `tcdb_route='family'` with `tcdb_family_id` = `attached_tcdb_id` = the subfamily itself (here tcdb:3.A.1.9, PhnT, uptake), and `tcdb_substrate_system_count` = the number of systems under it curated with the metabolite. phnD's own call is eggNOG on 3.A.1.9 (its DIAMOND hit is a weak tier-3 call on 3.A.1), so `tcdb_identity` is null on its row. Family rows are a recall expansion: verify them before treating the gene as an orthophosphate transporter.*

```example-response
{
  "total_matching": 4,
  "returned": 4,
  "offset": 0,
  "truncated": false,
  "warnings": [],
  "stereo_relatives": {},
  "stereo_forms_added": {},
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": [],
  "by_metabolite": [
    {
      "metabolite_id": "kegg.compound:C00009",
      "name": "Orthophosphate",
      "formula": "HO4P",
      "rows": 4,
      "gene_count": 4,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 4,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    }
  ],
  "by_evidence_source": [{"evidence_source": "transport", "count": 4}],
  "by_evidence_source_combination": [{"evidence_sources": ["transport"], "pair_count": 4}],
  "by_tcdb_route": [{"tcdb_route": "family", "count": 4}],
  "tcdb_family_substrates_not_shown": null,
  "tcdb_family_substrates_skipped": [
    {"locus_tag": "PMM0449", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0450", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0913", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0977", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546}
  ],
  "rows_by_go_term_depth": null,
  "top_reactions": [],
  "top_reactions_truncated": null,
  "top_tcdb_families": [
    {
      "tcdb_family_id": "tcdb:3.A.1.9",
      "tcdb_family_name": "The Phosphonate Uptake Transporter (PhnT) Family",
      "level_kind": "tc_subfamily",
      "tcdb_route": "family",
      "direction": "uptake",
      "gene_count": 4,
      "metabolite_count": 1
    }
  ],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [
    {"category": "Stress response and adaptation", "gene_count": 3},
    {"category": "Inorganic ion transport", "gene_count": 1}
  ],
  "top_genes": [
    {
      "locus_tag": "PMM0671",
      "gene_name": "phnE",
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 1,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    },
    {
      "locus_tag": "PMM0672",
      "gene_name": "phnC",
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 1,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    },
    {
      "locus_tag": "PMM0673",
      "gene_name": "phnD",
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 1,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    },
    {
      "locus_tag": "PMM0717",
      "gene_name": null,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 1,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    }
  ],
  "top_genes_truncated": null,
  "gene_count_total": 4,
  "reaction_count_total": 0,
  "transporter_count_total": 1,
  "metabolite_count_total": 1,
  "results": [
    {
      "locus_tag": "PMM0717",
      "product": "conserved hypothetical protein",
      "evidence_source": "transport",
      "tcdb_route": "family",
      "tcdb_calls": ["diamond_tier", "eggnog"],
      "tcdb_identity": 43.4,
      "tcdb_direction": "uptake",
      "attached_tcdb_id": "tcdb:3.A.1.9",
      "tcdb_substrate_system_count": 1,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.9",
      "tcdb_family_name": "The Phosphonate Uptake Transporter (PhnT) Family",
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C00009",
      "metabolite_name": "Orthophosphate",
      "metabolite_formula": "HO4P",
      "metabolite_mass": 95.978,
      "metabolite_chebi_id": "26078"
    },
    {
      "locus_tag": "PMM0671",
      "gene_name": "phnE",
      "product": "phosphate/phosphonate ABC type transporter, permease component",
      "evidence_source": "transport",
      "tcdb_route": "family",
      "tcdb_calls": ["eggnog"],
      "tcdb_identity": null,
      "tcdb_direction": "uptake",
      "attached_tcdb_id": "tcdb:3.A.1.9",
      "tcdb_substrate_system_count": 1,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.9",
      "tcdb_family_name": "The Phosphonate Uptake Transporter (PhnT) Family",
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C00009",
      "metabolite_name": "Orthophosphate",
      "metabolite_formula": "HO4P",
      "metabolite_mass": 95.978,
      "metabolite_chebi_id": "26078"
    },
    {
      "locus_tag": "PMM0672",
      "gene_name": "phnC",
      "product": "phosphonate ABC type transporter, ATPase component",
      "evidence_source": "transport",
      "tcdb_route": "family",
      "tcdb_calls": ["eggnog"],
      "tcdb_identity": null,
      "tcdb_direction": "uptake",
      "attached_tcdb_id": "tcdb:3.A.1.9",
      "tcdb_substrate_system_count": 1,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.9",
      "tcdb_family_name": "The Phosphonate Uptake Transporter (PhnT) Family",
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C00009",
      "metabolite_name": "Orthophosphate",
      "metabolite_formula": "HO4P",
      "metabolite_mass": 95.978,
      "metabolite_chebi_id": "26078"
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

### Example 8: Generic substrate — Cysteine in MED4 has no reactions; the stereo hint names L-Cysteine

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00736"], organism="Prochlorococcus MED4", summary=True)
```

*TCDB names substrates generically, so Cysteine (stereo form unspecified) carries the transport edges and 0 reactions; KEGG reactions use L-Cysteine. In MED4 no gene points directly at a Cysteine system: `tcdb_family_substrates_not_shown` counts 5 genes the family walk would add. `stereo_relatives` lists L-Cysteine with its MED4 counts (exactly what this tool reports for it), `by_metabolite[*].stereo_relative_ids` marks the entry, and the stereo warning comes first in `warnings`. D-Cysteine is not hinted: it has no MED4 genes.*

```example-response
{
  "total_matching": 0,
  "returned": 0,
  "offset": 0,
  "truncated": false,
  "warnings": [
    "Stereo forms hold more rows: Cysteine (kegg.compound:C00736) → L-Cysteine (kegg.compound:C00097): 13 reactions, 0 tra...",
    "No gene reaches these metabolites through a direct TCDB system call in this organism. 5 genes reach these metabolites..."
  ],
  "stereo_relatives": {
    "kegg.compound:C00736": [
      {
        "metabolite_id": "kegg.compound:C00097",
        "name": "L-Cysteine",
        "relation": "specific_form",
        "reaction_count": 13,
        "transporter_count": 0,
        "gene_count": 15
      }
    ]
  },
  "stereo_forms_added": {},
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": ["kegg.compound:C00736"],
  "by_metabolite": [],
  "by_evidence_source": [],
  "by_evidence_source_combination": [],
  "by_tcdb_route": [],
  "tcdb_family_substrates_not_shown": {"genes": 5, "metabolites": 1, "rows": 5},
  "tcdb_family_substrates_skipped": [
    {"locus_tag": "PMM0449", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0450", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0913", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0977", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546}
  ],
  "rows_by_go_term_depth": [],
  "top_reactions": [],
  "top_reactions_truncated": null,
  "top_tcdb_families": [],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [],
  "top_genes": [],
  "top_genes_truncated": null,
  "gene_count_total": 0,
  "reaction_count_total": 0,
  "transporter_count_total": 0,
  "metabolite_count_total": 0,
  "results": []
}
```

### Example 9: Cross the split — include_stereo_forms=True adds L-Cysteine's reactions, tagged via_stereo_form_of

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00736"], organism="Prochlorococcus MED4", include_stereo_forms=True, limit=3)
```

*The generic ↔ specific relatives join the query. Their rows and `by_metabolite` entries carry `via_stereo_form_of` (the input id that pulled them in), `stereo_forms_added` maps input → every relative queried (D-Cysteine is listed but has no MED4 rows, so it adds nothing and stays out of `not_matched`), and no hint fires. Enantiomers are never added. When a generic node's specific forms include a D-form (Alanine → L- and D-Alanine), both are added: check the tagged rows by `metabolite_name`.*

```example-response
{
  "total_matching": 26,
  "returned": 3,
  "offset": 0,
  "truncated": true,
  "warnings": [
    "No gene reaches these metabolites through a direct TCDB system call in this organism. 5 genes reach these metabolites..."
  ],
  "stereo_relatives": {},
  "stereo_forms_added": {"kegg.compound:C00736": ["kegg.compound:C00097", "kegg.compound:C00793"]},
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": ["kegg.compound:C00736"],
  "by_metabolite": [
    {
      "metabolite_id": "kegg.compound:C00097",
      "name": "L-Cysteine",
      "formula": "C3H7NO2S",
      "rows": 26,
      "gene_count": 15,
      "reaction_count": 13,
      "transporter_count": 0,
      "metabolism_rows": 26,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0,
      "via_stereo_form_of": "kegg.compound:C00736"
    }
  ],
  "by_evidence_source": [{"evidence_source": "metabolism", "count": 26}],
  "by_evidence_source_combination": [{"evidence_sources": ["metabolism"], "pair_count": 15}],
  "by_tcdb_route": [],
  "tcdb_family_substrates_not_shown": {"genes": 5, "metabolites": 1, "rows": 5},
  "tcdb_family_substrates_skipped": [
    {"locus_tag": "PMM0449", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0450", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0913", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0977", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546}
  ],
  "rows_by_go_term_depth": [],
  "top_reactions": [
    {
      "reaction_id": "kegg.reaction:R00899",
      "name": "L-cysteinylglycine dipeptidase; Cys-Gly + H2O <=> L-Cysteine + Glycine",
      "ec_numbers": ["3.4.11", "3.4.11.1", "3.4.11.2", "3.4.11.23", "3.4.13", ...],
      "gene_count": 3,
      "metabolite_count": 1
    },
    {
      "reaction_id": "kegg.reaction:R04859",
      "name": "O3-acetyl-L-serine:thiosulfate 2-amino-2-carboxyethyltransferase (reducing, L-cysteine-forming); O3-acetyl-L-serine a...",
      "ec_numbers": ["2.5.1.47", "2.5.1.49"],
      "gene_count": 3,
      "metabolite_count": 1
    },
    {
      "reaction_id": "kegg.reaction:R11528",
      "name": "L-cysteine:sulfur-acceptor sulfurtransferase; L-Cysteine + [Protein]-L-cysteine <=> L-Alanine + [Protein]-S-sulfanyl-...",
      "ec_numbers": ["2.8.1.7"],
      "gene_count": 3,
      "metabolite_count": 1
    },
    {
      "reaction_id": "kegg.reaction:R00782",
      "name": "L-cysteine hydrogen-sulfide-lyase (deaminating; pyruvate-forming); L-Cysteine + H2O <=> Hydrogen sulfide + Pyruvate +...",
      "ec_numbers": ["4.1.99.1", "4.4.1.1", "4.4.1.11", "4.4.1.13", "4.4.1.28", ...],
      "gene_count": 2,
      "metabolite_count": 1
    },
    {
      "reaction_id": "kegg.reaction:R00897",
      "name": "O3-acetyl-L-serine:hydrogen-sulfide 2-amino-2-carboxyethyltransferase; O3-acetyl-L-serine acetate-lyase (adding hydro...",
      "ec_numbers": ["2.5.1.47", "2.5.1.65"],
      "gene_count": 2,
      "metabolite_count": 1
    },
    ...
  ],
  "top_reactions_truncated": true,
  "top_tcdb_families": [],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [
    {"category": "Amino acid metabolism", "gene_count": 8},
    {"category": "Coenzyme metabolism", "gene_count": 3},
    {"category": "Stress response and adaptation", "gene_count": 2},
    {"category": "Post-translational modification", "gene_count": 1},
    {"category": "Translation", "gene_count": 1}
  ],
  "top_genes": [
    {
      "locus_tag": "PMM0409",
      "gene_name": "metB",
      "reaction_count": 5,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 5,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 0
    },
    {
      "locus_tag": "PMM0408",
      "gene_name": null,
      "reaction_count": 3,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 3,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 0
    },
    {
      "locus_tag": "PMM0123",
      "gene_name": "cysK",
      "reaction_count": 2,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 2,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 0
    },
    {
      "locus_tag": "PMM0170",
      "gene_name": "iscS2",
      "reaction_count": 2,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 2,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 0
    },
    {
      "locus_tag": "PMM0407",
      "gene_name": "cysK",
      "reaction_count": 2,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 2,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 0
    },
    ...
  ],
  "top_genes_truncated": true,
  "gene_count_total": 15,
  "reaction_count_total": 13,
  "transporter_count_total": 0,
  "metabolite_count_total": 1,
  "results": [
    {
      "locus_tag": "PMM0409",
      "gene_name": "metB",
      "product": "O-succinylhomoserine(thiol)-lyase",
      "evidence_source": "metabolism",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": "kegg.reaction:R00782",
      "reaction_name": "L-cysteine hydrogen-sulfide-lyase (deaminating; pyruvate-forming); L-Cysteine + H2O <=> Hydrogen sulfide + Pyruvate +...",
      "ec_numbers": ["4.1.99.1", "4.4.1.1", "4.4.1.11", "4.4.1.13", "4.4.1.28", ...],
      "mass_balance": "balanced",
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C00097",
      "metabolite_name": "L-Cysteine",
      "metabolite_formula": "C3H7NO2S",
      "metabolite_mass": 121.161,
      "metabolite_chebi_id": "17561",
      "via_stereo_form_of": "kegg.compound:C00736"
    },
    {
      "locus_tag": "PMM1670",
      "gene_name": "metC",
      "product": "cystathionine beta-lyase family aluminum resistance protein",
      "evidence_source": "metabolism",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": "kegg.reaction:R00782",
      "reaction_name": "L-cysteine hydrogen-sulfide-lyase (deaminating; pyruvate-forming); L-Cysteine + H2O <=> Hydrogen sulfide + Pyruvate +...",
      "ec_numbers": ["4.1.99.1", "4.4.1.1", "4.4.1.11", "4.4.1.13", "4.4.1.28", ...],
      "mass_balance": "balanced",
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C00097",
      "metabolite_name": "L-Cysteine",
      "metabolite_formula": "C3H7NO2S",
      "metabolite_mass": 121.161,
      "metabolite_chebi_id": "17561",
      "via_stereo_form_of": "kegg.compound:C00736"
    },
    {
      "locus_tag": "PMM0674",
      "gene_name": "aspC",
      "product": "aspartate aminotransferase",
      "evidence_source": "metabolism",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": "kegg.reaction:R00896",
      "reaction_name": "L-cysteine:2-oxoglutarate aminotransferase; L-Cysteine + 2-Oxoglutarate <=> Mercaptopyruvate + Glutamate",
      "ec_numbers": ["2.6.1.1"],
      "mass_balance": "balanced",
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C00097",
      "metabolite_name": "L-Cysteine",
      "metabolite_formula": "C3H7NO2S",
      "metabolite_mass": 121.161,
      "metabolite_chebi_id": "17561",
      "via_stereo_form_of": "kegg.compound:C00736"
    }
  ]
}
```

### Example 10: Transporter genes → their generic substrate → transport + catalysis in one call

```
Step 1: metabolites_by_gene(locus_tags=["PMM0065"],
                            organism="Prochlorococcus MED4",
                            evidence_sources=["transport"],
                            include_tcdb_family_substrates=True)
        → Cysteine kegg.compound:C00736 among the family rows (via
          subfamily tcdb:3.A.1.106); envelope
          stereo_relatives["kegg.compound:C00736"] names L-Cysteine
          with its MED4 reaction_count (catalysis lives there)

Step 2: genes_by_metabolite(metabolite_ids=["kegg.compound:C00736"],
                            organism="Prochlorococcus MED4",
                            include_stereo_forms=True,
                            include_tcdb_family_substrates=True)
        → Cysteine family-route transporters + L-Cysteine catalysts in
          one result; the L-Cysteine rows carry via_stereo_form_of
```

### Example 11: GO transport route — urea in MED4 (the GO rows sit after the KEGG and TCDB rows, labelled)

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4")
```

*Three routes in one call: metabolism, transport (TCDB) and go_transport rows, each tagged by `evidence_source`. A GO row is a GO TERM that GO defines as moving urea, carried by the gene (`go_term_id`, `go_term_name`, `go_namespace`, `go_evidence`, `go_sources`); it is not a TCDB call and never adds to `transporter_count_total`. The urtA gene PMM0970 appears with a molecular-function term (urea transmembrane transporter activity) and a biological-process term (urea transport). Read `rows_by_go_term_depth` (all depth 0 here), then `by_evidence_source`.*

```example-response
{
  "total_matching": 25,
  "returned": 10,
  "offset": 0,
  "truncated": true,
  "warnings": [],
  "stereo_relatives": {},
  "stereo_forms_added": {},
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": [],
  "by_metabolite": [
    {
      "metabolite_id": "kegg.compound:C00086",
      "name": "Urea",
      "formula": "CH4N2O",
      "rows": 25,
      "gene_count": 9,
      "reaction_count": 2,
      "transporter_count": 2,
      "metabolism_rows": 4,
      "tcdb_direct_rows": 10,
      "tcdb_family_rows": 0,
      "go_transport_rows": 11,
      "multi_source_gene_count": 5
    }
  ],
  "by_evidence_source": [
    {"evidence_source": "go_transport", "count": 11},
    {"evidence_source": "transport", "count": 10},
    {"evidence_source": "metabolism", "count": 4}
  ],
  "by_evidence_source_combination": [
    {"evidence_sources": ["go_transport", "transport"], "pair_count": 5},
    {"evidence_sources": ["metabolism"], "pair_count": 4}
  ],
  "by_tcdb_route": [{"tcdb_route": "direct", "count": 10}],
  "tcdb_family_substrates_not_shown": {"genes": 0, "metabolites": 0, "rows": 0},
  "tcdb_family_substrates_skipped": [
    {"locus_tag": "PMM0449", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0450", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0913", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0977", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546}
  ],
  "rows_by_go_term_depth": [{"go_term_depth": 0, "count": 11}],
  "top_reactions": [
    {
      "reaction_id": "kegg.reaction:R00131",
      "name": "urea amidohydrolase; Urea + H2O <=> CO2 + 2 Ammonia",
      "ec_numbers": ["3.5.1.5"],
      "gene_count": 3,
      "metabolite_count": 1
    },
    {
      "reaction_id": "kegg.reaction:R01157",
      "name": "agmatine amidinohydrolase; Agmatine + H2O <=> Putrescine + Urea",
      "ec_numbers": ["3.5.3.1", "3.5.3.11"],
      "gene_count": 1,
      "metabolite_count": 1
    }
  ],
  "top_reactions_truncated": null,
  "top_tcdb_families": [
    {
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (<1 μM) urea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 5,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.4.5",
      "tcdb_family_name": "The high affinity urea/thiourea/hydroxyurea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 5,
      "metabolite_count": 1
    }
  ],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [
    {"category": "Stress response and adaptation", "gene_count": 8},
    {"category": "Carbohydrate metabolism", "gene_count": 1}
  ],
  "top_genes": [
    {
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0971",
      "gene_name": "urtB",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0972",
      "gene_name": "urtC",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0973",
      "gene_name": "urtD",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0974",
      "gene_name": "urtE",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 3,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    ...
  ],
  "top_genes_truncated": null,
  "gene_count_total": 9,
  "reaction_count_total": 2,
  "transporter_count_total": 2,
  "metabolite_count_total": 1,
  "results": [
    {
      "locus_tag": "PMM0963",
      "gene_name": "ureC",
      "product": "urease alpha subunit",
      "evidence_source": "metabolism",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": "kegg.reaction:R00131",
      "reaction_name": "urea amidohydrolase; Urea + H2O <=> CO2 + 2 Ammonia",
      "ec_numbers": ["3.5.1.5"],
      "mass_balance": "balanced",
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C00086",
      "metabolite_name": "Urea",
      "metabolite_formula": "CH4N2O",
      "metabolite_mass": 60.056,
      "metabolite_chebi_id": "16199"
    },
    {
      "locus_tag": "PMM0964",
      "gene_name": "ureB",
      "product": "urease beta subunit",
      "evidence_source": "metabolism",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": "kegg.reaction:R00131",
      "reaction_name": "urea amidohydrolase; Urea + H2O <=> CO2 + 2 Ammonia",
      "ec_numbers": ["3.5.1.5"],
      "mass_balance": "balanced",
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C00086",
      "metabolite_name": "Urea",
      "metabolite_formula": "CH4N2O",
      "metabolite_mass": 60.056,
      "metabolite_chebi_id": "16199"
    },
    {
      "locus_tag": "PMM0965",
      "gene_name": "ureA",
      "product": "urease gamma subunit",
      "evidence_source": "metabolism",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": "kegg.reaction:R00131",
      "reaction_name": "urea amidohydrolase; Urea + H2O <=> CO2 + 2 Ammonia",
      "ec_numbers": ["3.5.1.5"],
      "mass_balance": "balanced",
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C00086",
      "metabolite_name": "Urea",
      "metabolite_formula": "CH4N2O",
      "metabolite_mass": 60.056,
      "metabolite_chebi_id": "16199"
    },
    ...
  ]
}
```

### Example 12: Role target — siderophore transporters in Alteromonas mediterranea AltDE1 (target_kind='chemical_role')

```example-call
genes_by_metabolite(metabolite_ids=["chebi.role:26672"], organism="Alteromonas mediterranea AltDE1", evidence_sources=["go_transport"], limit=5)
```

*`chebi.role:<n>` ids are valid inputs. A role row is a class, not a compound: `target_kind='chemical_role'`, `metabolite_id` is the role id, formula and mass are absent, and roles are not propagated to metabolites. The same role id also reaches TCDB role edges (from TC systems) when `evidence_sources` is left at its default. Use the exact strain `Alteromonas mediterranea AltDE1` (the shorter `AltDE` string also word-matches AltDE1 genes).*

```example-response
{
  "total_matching": 32,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "warnings": [],
  "stereo_relatives": {},
  "stereo_forms_added": {},
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": [],
  "by_metabolite": [
    {
      "metabolite_id": "chebi.role:26672",
      "name": "siderophore",
      "formula": null,
      "rows": 32,
      "gene_count": 28,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 32,
      "multi_source_gene_count": 0
    }
  ],
  "by_evidence_source": [{"evidence_source": "go_transport", "count": 32}],
  "by_evidence_source_combination": [{"evidence_sources": ["go_transport"], "pair_count": 28}],
  "by_tcdb_route": [],
  "tcdb_family_substrates_not_shown": {"genes": 0, "metabolites": 0, "rows": 0},
  "tcdb_family_substrates_skipped": [],
  "rows_by_go_term_depth": [{"go_term_depth": 0, "count": 32}],
  "top_reactions": [],
  "top_reactions_truncated": null,
  "top_tcdb_families": [],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [
    {"category": "Inorganic ion transport", "gene_count": 19},
    {"category": "Cell wall and membrane", "gene_count": 5},
    {"category": "Intracellular trafficking", "gene_count": 3},
    {"category": "Coenzyme metabolism", "gene_count": 1}
  ],
  "top_genes": [
    {
      "locus_tag": "amad1_00300",
      "gene_name": null,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 0
    },
    {
      "locus_tag": "amad1_00590",
      "gene_name": null,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 3
    },
    {
      "locus_tag": "amad1_03175",
      "gene_name": "tolC",
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "amad1_03385",
      "gene_name": "btuB",
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    },
    {
      "locus_tag": "amad1_03600",
      "gene_name": null,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    },
    ...
  ],
  "top_genes_truncated": true,
  "gene_count_total": 28,
  "reaction_count_total": 0,
  "transporter_count_total": 0,
  "metabolite_count_total": 1,
  "results": [
    {
      "locus_tag": "amad1_07080",
      "product": "TonB-dependent receptor",
      "evidence_source": "go_transport",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": "go:0015343",
      "go_term_name": "siderophore-iron transmembrane transporter activity",
      "go_namespace": "molecular_function",
      "go_evidence": "curated",
      "go_sources": ["interproscan", "ncbi"],
      "go_term_depth": 0,
      "go_axiom_term_id": "go:0015343",
      "go_axiom_term_name": "siderophore-iron transmembrane transporter activity",
      "target_kind": "chemical_role",
      "metabolite_id": "chebi.role:26672",
      "metabolite_name": "siderophore"
    },
    {
      "locus_tag": "amad1_09420",
      "product": "TonB-dependent receptor",
      "evidence_source": "go_transport",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": "go:0015343",
      "go_term_name": "siderophore-iron transmembrane transporter activity",
      "go_namespace": "molecular_function",
      "go_evidence": "curated",
      "go_sources": ["ncbi"],
      "go_term_depth": 0,
      "go_axiom_term_id": "go:0015343",
      "go_axiom_term_name": "siderophore-iron transmembrane transporter activity",
      "target_kind": "chemical_role",
      "metabolite_id": "chebi.role:26672",
      "metabolite_name": "siderophore"
    },
    {
      "locus_tag": "amad1_14745",
      "product": "TonB-dependent receptor family protein",
      "evidence_source": "go_transport",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": "go:0015343",
      "go_term_name": "siderophore-iron transmembrane transporter activity",
      "go_namespace": "molecular_function",
      "go_evidence": "curated",
      "go_sources": ["ncbi"],
      "go_term_depth": 0,
      "go_axiom_term_id": "go:0015343",
      "go_axiom_term_name": "siderophore-iron transmembrane transporter activity",
      "target_kind": "chemical_role",
      "metabolite_id": "chebi.role:26672",
      "metabolite_name": "siderophore"
    },
    ...
  ]
}
```

### Example 13: Inherited rows are opt-in — go_include_ancestors=True adds is_a-ancestor rows, tagged with the term that names the target

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C01356"], organism="Prochlorococcus MED4", evidence_sources=["go_transport"], go_include_ancestors=True)
```

*Direct rows (`go_term_depth=0`) first; inherited rows follow with `go_term_depth` = number of is_a hops, `go_axiom_term_id` / `go_axiom_term_name` naming the ancestor that carries the target, and `go_term_id` still the gene's own term. A (gene, target) already reached directly through GO is not repeated as an inherited row. Inherited rows are a recall expansion: they widen to broader targets than the gene's own term names. Compare against the default call before using them.*

```example-response
{
  "total_matching": 8,
  "returned": 8,
  "offset": 0,
  "truncated": false,
  "warnings": [],
  "stereo_relatives": {},
  "stereo_forms_added": {},
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": [],
  "by_metabolite": [
    {
      "metabolite_id": "kegg.compound:C01356",
      "name": "Lipid",
      "formula": null,
      "rows": 8,
      "gene_count": 6,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 8,
      "multi_source_gene_count": 0
    }
  ],
  "by_evidence_source": [{"evidence_source": "go_transport", "count": 8}],
  "by_evidence_source_combination": [{"evidence_sources": ["go_transport"], "pair_count": 6}],
  "by_tcdb_route": [],
  "tcdb_family_substrates_not_shown": {"genes": 0, "metabolites": 0, "rows": 0},
  "tcdb_family_substrates_skipped": [],
  "rows_by_go_term_depth": [{"go_term_depth": 0, "count": 1}, {"go_term_depth": 1, "count": 7}],
  "top_reactions": [],
  "top_reactions_truncated": null,
  "top_tcdb_families": [],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [
    {"category": "Transport", "gene_count": 3},
    {"category": "Cell wall and membrane", "gene_count": 2},
    {"category": "Secondary metabolites", "gene_count": 1}
  ],
  "top_genes": [
    {
      "locus_tag": "PMM0261",
      "gene_name": "murJ",
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    },
    {
      "locus_tag": "PMM0289",
      "gene_name": "ycf22",
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    },
    {
      "locus_tag": "PMM0561",
      "gene_name": null,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 3
    },
    {
      "locus_tag": "PMM0764",
      "gene_name": "lptB",
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    },
    {
      "locus_tag": "PMM0866",
      "gene_name": "lptC",
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 0
    },
    ...
  ],
  "top_genes_truncated": null,
  "gene_count_total": 6,
  "reaction_count_total": 0,
  "transporter_count_total": 0,
  "metabolite_count_total": 1,
  "results": [
    {
      "locus_tag": "PMM0561",
      "product": "putative ABC multidrug efflux transporter",
      "evidence_source": "go_transport",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": "go:0034040",
      "go_term_name": "ATPase-coupled lipid transmembrane transporter activity",
      "go_namespace": "molecular_function",
      "go_evidence": "curated",
      "go_sources": ["uniprot"],
      "go_term_depth": 0,
      "go_axiom_term_id": "go:0034040",
      "go_axiom_term_name": "ATPase-coupled lipid transmembrane transporter activity",
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C01356",
      "metabolite_name": "Lipid",
      "metabolite_chebi_id": "18059"
    },
    {
      "locus_tag": "PMM0764",
      "gene_name": "lptB",
      "product": "lipopolysaccharide export system, ATP-binding component LptB",
      "evidence_source": "go_transport",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": "go:0015221",
      "go_term_name": "lipopolysaccharide transmembrane transporter activity",
      "go_namespace": "molecular_function",
      "go_evidence": "curated",
      "go_sources": ["ncbi"],
      "go_term_depth": 1,
      "go_axiom_term_id": "go:0170055",
      "go_axiom_term_name": "lipid transmembrane transporter activity",
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C01356",
      "metabolite_name": "Lipid",
      "metabolite_chebi_id": "18059"
    },
    {
      "locus_tag": "PMM0866",
      "gene_name": "lptC",
      "product": "possible SMC domain N terminal domain",
      "evidence_source": "go_transport",
      "tcdb_route": null,
      "tcdb_calls": null,
      "tcdb_identity": null,
      "tcdb_direction": null,
      "attached_tcdb_id": null,
      "tcdb_substrate_system_count": null,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": null,
      "tcdb_family_name": null,
      "go_term_id": "go:0015221",
      "go_term_name": "lipopolysaccharide transmembrane transporter activity",
      "go_namespace": "molecular_function",
      "go_evidence": "curated",
      "go_sources": ["ncbi"],
      "go_term_depth": 1,
      "go_axiom_term_id": "go:0170055",
      "go_axiom_term_name": "lipid transmembrane transporter activity",
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C01356",
      "metabolite_name": "Lipid",
      "metabolite_chebi_id": "18059"
    },
    ...
  ]
}
```

### Example 14: Where the routes agree — urea in MED4, read by_evidence_source_combination

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4", summary=True)
```

*One entry per set of routes that name the same (gene, metabolite) pair: 4 from KEGG alone (the urease subunits) and 5 from TCDB and GO together (urtA–E, also counted as `multi_source_gene_count=5` on the urea `by_metabolite` entry). Agreement narrows the list to the confident core, but TCDB and GO share homology, so it raises confidence and does not prove transport. TCDB family-route rows join these combinations only when `include_tcdb_family_substrates=True`.*

```example-response
{
  "total_matching": 25,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "warnings": [],
  "stereo_relatives": {},
  "stereo_forms_added": {},
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": [],
  "by_metabolite": [
    {
      "metabolite_id": "kegg.compound:C00086",
      "name": "Urea",
      "formula": "CH4N2O",
      "rows": 25,
      "gene_count": 9,
      "reaction_count": 2,
      "transporter_count": 2,
      "metabolism_rows": 4,
      "tcdb_direct_rows": 10,
      "tcdb_family_rows": 0,
      "go_transport_rows": 11,
      "multi_source_gene_count": 5
    }
  ],
  "by_evidence_source": [
    {"evidence_source": "go_transport", "count": 11},
    {"evidence_source": "transport", "count": 10},
    {"evidence_source": "metabolism", "count": 4}
  ],
  "by_evidence_source_combination": [
    {"evidence_sources": ["go_transport", "transport"], "pair_count": 5},
    {"evidence_sources": ["metabolism"], "pair_count": 4}
  ],
  "by_tcdb_route": [{"tcdb_route": "direct", "count": 10}],
  "tcdb_family_substrates_not_shown": {"genes": 0, "metabolites": 0, "rows": 0},
  "tcdb_family_substrates_skipped": [
    {"locus_tag": "PMM0449", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0450", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0913", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0977", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546}
  ],
  "rows_by_go_term_depth": [{"go_term_depth": 0, "count": 11}],
  "top_reactions": [
    {
      "reaction_id": "kegg.reaction:R00131",
      "name": "urea amidohydrolase; Urea + H2O <=> CO2 + 2 Ammonia",
      "ec_numbers": ["3.5.1.5"],
      "gene_count": 3,
      "metabolite_count": 1
    },
    {
      "reaction_id": "kegg.reaction:R01157",
      "name": "agmatine amidinohydrolase; Agmatine + H2O <=> Putrescine + Urea",
      "ec_numbers": ["3.5.3.1", "3.5.3.11"],
      "gene_count": 1,
      "metabolite_count": 1
    }
  ],
  "top_reactions_truncated": null,
  "top_tcdb_families": [
    {
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (<1 μM) urea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 5,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.4.5",
      "tcdb_family_name": "The high affinity urea/thiourea/hydroxyurea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 5,
      "metabolite_count": 1
    }
  ],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [
    {"category": "Stress response and adaptation", "gene_count": 8},
    {"category": "Carbohydrate metabolism", "gene_count": 1}
  ],
  "top_genes": [
    {
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0971",
      "gene_name": "urtB",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0972",
      "gene_name": "urtC",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0973",
      "gene_name": "urtD",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0974",
      "gene_name": "urtE",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 3,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    ...
  ],
  "top_genes_truncated": null,
  "gene_count_total": 9,
  "reaction_count_total": 2,
  "transporter_count_total": 2,
  "metabolite_count_total": 1,
  "results": []
}
```

### Example 15: Narrow the GO arm — molecular-function terms with curated gene evidence only

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4", go_namespace=["molecular_function"], go_evidence=["curated"], summary=True)
```

*Keeps 4 of the 11 urea GO rows (the biological-process rows drop out). The KEGG and TCDB rows are untouched, so `total_matching` falls from 25 to 18 only by the GO rows removed. Allowed `go_evidence` values: `list_filter_values`.*

```example-response
{
  "total_matching": 18,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "warnings": [],
  "stereo_relatives": {},
  "stereo_forms_added": {},
  "resolved_aliases": {},
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": [],
  "by_metabolite": [
    {
      "metabolite_id": "kegg.compound:C00086",
      "name": "Urea",
      "formula": "CH4N2O",
      "rows": 18,
      "gene_count": 9,
      "reaction_count": 2,
      "transporter_count": 2,
      "metabolism_rows": 4,
      "tcdb_direct_rows": 10,
      "tcdb_family_rows": 0,
      "go_transport_rows": 4,
      "multi_source_gene_count": 4
    }
  ],
  "by_evidence_source": [
    {"evidence_source": "transport", "count": 10},
    {"evidence_source": "go_transport", "count": 4},
    {"evidence_source": "metabolism", "count": 4}
  ],
  "by_evidence_source_combination": [
    {"evidence_sources": ["go_transport", "transport"], "pair_count": 4},
    {"evidence_sources": ["metabolism"], "pair_count": 4},
    {"evidence_sources": ["transport"], "pair_count": 1}
  ],
  "by_tcdb_route": [{"tcdb_route": "direct", "count": 10}],
  "tcdb_family_substrates_not_shown": {"genes": 0, "metabolites": 0, "rows": 0},
  "tcdb_family_substrates_skipped": [
    {"locus_tag": "PMM0449", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0450", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0913", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546},
    {"locus_tag": "PMM0977", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 546}
  ],
  "rows_by_go_term_depth": [{"go_term_depth": 0, "count": 4}],
  "top_reactions": [
    {
      "reaction_id": "kegg.reaction:R00131",
      "name": "urea amidohydrolase; Urea + H2O <=> CO2 + 2 Ammonia",
      "ec_numbers": ["3.5.1.5"],
      "gene_count": 3,
      "metabolite_count": 1
    },
    {
      "reaction_id": "kegg.reaction:R01157",
      "name": "agmatine amidinohydrolase; Agmatine + H2O <=> Putrescine + Urea",
      "ec_numbers": ["3.5.3.1", "3.5.3.11"],
      "gene_count": 1,
      "metabolite_count": 1
    }
  ],
  "top_reactions_truncated": null,
  "top_tcdb_families": [
    {
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (<1 μM) urea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 5,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.4.5",
      "tcdb_family_name": "The high affinity urea/thiourea/hydroxyurea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 5,
      "metabolite_count": 1
    }
  ],
  "top_tcdb_families_truncated": null,
  "top_gene_categories": [
    {"category": "Stress response and adaptation", "gene_count": 8},
    {"category": "Carbohydrate metabolism", "gene_count": 1}
  ],
  "top_genes": [
    {
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0971",
      "gene_name": "urtB",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0972",
      "gene_name": "urtC",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0973",
      "gene_name": "urtD",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0974",
      "gene_name": "urtE",
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolite_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    ...
  ],
  "top_genes_truncated": null,
  "gene_count_total": 9,
  "reaction_count_total": 2,
  "transporter_count_total": 2,
  "metabolite_count_total": 1,
  "results": []
}
```

## Chaining patterns

```
list_metabolites(...) → genes_by_metabolite(metabolite_ids=[chosen_ids], organism=...)
list_metabolites (per-row `transporter_gene_count > 0`) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['transport']) — distinct genes in the transport rows, summed over organisms, equal that count
differential_expression_by_gene(...) → top hits → metabolites_by_gene(locus_tags=...) → genes_by_metabolite for the symmetric metabolite-anchored view
Workflow A (N-source): list_metabolites(elements=['N']) → genes_by_metabolite(metabolite_ids=[N-bearing IDs], organism=...) for catalysts + transporters
Workflow B (cross-feeding): genes_by_metabolite called once per organism on the same metabolite_ids; intersect/diff locus_tag result sets client-side
genes_by_metabolite → top_genes → differential_expression_by_gene(locus_tags=top_genes_locus_tags, organism=...) for transcriptional response
genes_by_metabolite → top_genes (tcdb_direct_rows > 0) → gene_overview(locus_tags=...) then metabolites_by_gene for the gene's full substrate set
genes_by_metabolite → warning / tcdb_family_substrates_not_shown.genes > 0 → genes_by_metabolite(same ids, organism=..., include_tcdb_family_substrates=True) for the genes TCDB placed only at family or subfamily level
genes_by_metabolite → top_genes → gene_overview(locus_tags=...) for richer per-gene routing context
genes_by_metabolite → top_tcdb_families → genes_by_ontology(ontology='tcdb', term_ids=[top_tcdb_families[i].tcdb_family_id], organism=...) for sibling genes in the same family
genes_by_metabolite → transport rows → gene_ontology_terms(locus_tags=[...], ontology='tcdb', organism=...) to see every gated TCDB call the gene carries (families and subfamilies with no substrate row here included); add include_weak_tcdb_hits=True for its below-gate DIAMOND hits
genes_by_metabolite → top_reactions → genes_by_ontology(ontology='ec', term_ids=[ec_number], organism=...) for genes in adjacent reactions
genes_by_metabolite → top_reactions / top_genes → pathway_enrichment for KEGG-pathway context
genes_by_metabolite → stereo_relatives (or the stereo warning) → genes_by_metabolite(metabolite_ids=[same ids], organism=..., include_stereo_forms=True) to join generic-form transport with specific-form catalysis
metabolites_by_gene(transporter locus_tags) → stereo_relatives → genes_by_metabolite(metabolite_ids=[generic substrate], organism=..., include_stereo_forms=True) for transporters and catalysts of the same compound
genes_by_metabolite → go_transport rows → gene_ontology_terms(locus_tags=[...], ontology='go_mf' or 'go_bp', organism=...) to see the gene's full GO annotation set around the term that names the target
genes_by_metabolite → go_transport rows (go_evidence='family_inferred' or 'domain_inferred') → gene_overview(locus_tags=...) to see which other routes (TCDB, KEGG) corroborate the gene; read `docs://analysis/transport` before treating agreement as independent evidence
list_metabolites(evidence_sources=['go_transport']) → per-row go_transport_organism_names → genes_by_metabolite(metabolite_ids=[...], organism=...) for the GO-route genes in one organism
```

## Common mistakes

- Metabolite-anchored (metabolite → genes). The gene-anchored mirror is `metabolites_by_gene` (locus_tags → metabolites); both share the same row class, discriminators and per-arm filter scope, so read whichever matches your anchor rather than post-filtering the other.

- 0 reactions on a generic substrate does not mean no enzymes. Stereo forms are separate nodes and no count combines across them: TCDB names substrates generically ('Cysteine', `kegg.compound:C00736`), so transport sits there; KEGG reactions use the specific form (L-Cysteine, `kegg.compound:C00097`), so catalysis sits there. Read envelope `stereo_relatives` (organism-scoped counts per relative, under your filters; only relatives with genes here) and the stereo warning, then re-run with `include_stereo_forms=True` for a transport ↔ catalysis join. Keep the single id for exact-form or D-amino-acid questions: a generic's specific forms can include the D-form. Class terms ('amino acid') and ring vs open-chain forms are never linked, so no hint is not proof of no related compound; search by name with `list_metabolites(search_text=...)`.

- Transport rows are direct by default: a row means the gene has a `tcdb_gate='direct'` call on a TC system (a rank-1 DIAMOND best hit at tier 1-2, a tier-1 DIAMOND call, or an eggNOG call onto a system) and TCDB curates that system with the compound. One row per gene × system × metabolite. Rank within the route by `tcdb_identity` (DIAMOND identity in percent of the row's representative call; null when that call is eggNOG), then by `tcdb_calls` (eggNOG plus a DIAMOND kind is independent agreement; `diamond_tier` and `diamond_best_hit` come from one DIAMOND run, so the two together are one source). Never filter on `tcdb_identity`: an eggNOG-only row is not weaker for reading null.

- An empty transport arm does not mean no transporter. Many genes are placed by TCDB only at family or subfamily level (`tcdb_gate='annotated'`), and those never produce a default row. Read `tcdb_family_substrates_not_shown` (what `include_tcdb_family_substrates=True` would add: genes, metabolites, rows) and the warning, then opt in. Orthophosphate in MED4 has 0 direct genes; the walk adds phnC/D/E and PMM0717 through subfamily tcdb:3.A.1.9. Genes whose only usable call is on a node curated with over 200 substrates (the ABC superfamily tcdb:3.A.1, MFS tcdb:2.A.1) are listed in `tcdb_family_substrates_skipped`: their substrate is unknown, and the walk never starts there.

- Family rows (`tcdb_route='family'`) are a recall expansion, not a substrate call. The walk runs from the gene's deepest `annotated` family or subfamily down to every TC system under it and reports the systems' curated substrates, one row per gene × attached node × metabolite (`tcdb_family_id` = `attached_tcdb_id` = the family itself; `tcdb_substrate_system_count` = systems under it curated with the metabolite). It never starts above a gene's own direct system, so a gene with a direct call keeps exactly its system's substrates. TCDB curation is taken as-is: the Pst phosphate system tcdb:3.A.1.7.6 is curated with triphosphate only, so pstA/B/C/S do not reach orthophosphate (the system name still says phosphate), and catch-all substrates ("Peptide", "Protein") pass through. Most remaining noise is eggNOG family calls on genes that are not transporters at all.

- `tcdb_direction` (`uptake` / `export` / `unknown`) is TCDB's direction for the row's node, not a per-gene measurement. It is conservative: ABC uptake numbering (subfamilies 3.A.1.1-99 and their systems) or a system's own TCDB name. Family and subfamily names never set it, so family rows read `unknown` outside the ABC uptake range. Most nodes read `unknown`. GO and KEGG rows carry no direction.

- Distinct direct genes across the transport rows, unioned over organisms, equal `list_metabolites.transporter_gene_count`, and gene-side, distinct direct Metabolite targets equal `gene_overview.transported_metabolite_count` (role rows excluded). Family rows are not in either count. Genes with only weak DIAMOND hits (`tcdb_gate='below_gate'`) never reach a substrate here; `gene_ontology_terms(..., include_weak_tcdb_hits=True)` shows them.

- Every result row has the same key set — cross-arm fields are explicitly `None` on rows from the other arm (metabolism rows have `tcdb_route`/`tcdb_calls`/`tcdb_identity`/`tcdb_direction`/`tcdb_family_id`/`tcdb_family_name` = None; transport rows have `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` = None). Use `row['tcdb_route']` (KeyError-free) rather than `row.get('tcdb_route')` if the difference matters.

- Reaction-arm rows are NOT directional — KG reactions carry neither a substrate-vs-product role on `Reaction_has_metabolite` nor an `is_reversible` flag. Read `evidence_source='metabolism'` rows as 'gene catalyses a reaction *involving* this metabolite,' never as 'produces X' / 'consumes Y' / 'reversibly interconverts'. The KG limitation is permanent (KEGG lacks both upstream).

- Filtering by `ec_numbers` does NOT restrict to metabolism only. Per-arm filter scope: `ec_numbers` and `mass_balance` narrow the metabolism arm WHERE; TCDB and GO transport rows are returned UNCHANGED (no soft-exclude). Symmetrically, `include_tcdb_family_substrates` widens TCDB transport only and `go_include_ancestors` the GO route only. To restrict to one arm, set `evidence_sources=['metabolism']` (or `['transport']` / `['go_transport']`) explicitly. `metabolite_pathway_ids` and `gene_categories` are the only filters that narrow all three arms uniformly.

- Single-organism enforced (mirrors `differential_expression_by_gene`). There is no `organisms` list. For cross-organism / cross-feeding work, call once per organism with the same metabolite_ids and combine locus_tag result sets client-side (Workflow B).

- `'metabolomics'` is NOT accepted in `evidence_sources` here — the Pydantic Literal allows only `('metabolism', 'transport', 'go_transport')`. The metabolomics path (`MetaboliteAssay → Metabolite`) has no Gene anchor, so a metabolomics-only metabolite returns no rows from this tool. To inspect measurement evidence, use `list_metabolite_assays` / `assays_by_metabolite` instead. Same `_VALID_EVIDENCE_SOURCES` validator pattern as `list_metabolites`, intentionally divergent value set per the tool's biology.

- TCDB-class filtering does NOT belong here. There is no `tcdb_class_ids` parameter. TCDB is a first-class ontology — for "all genes in TCDB class 3.A.1 (ABC superfamily) for organism X", route through `genes_by_ontology(ontology='tcdb', term_ids=['tcdb:3.A.1'], organism=...)`. From here the drill-out path is `top_tcdb_families[i].tcdb_family_id` → `genes_by_ontology(ontology='tcdb', term_ids=[that_id], organism=...)`.

- `not_found.metabolite_ids` vs `not_matched`. `not_found.metabolite_ids` = IDs that don't exist as a Metabolite node at all (typo, wrong prefix, ChEBI ID not in our KG). `not_matched` = IDs whose Metabolite exists but produced zero rows in this organism slice under the active filters (e.g. transport-only metabolite curated for non-MED4 strains). Don't conflate them — `not_matched` may go to zero by relaxing filters or swapping organism; `not_found` won't.

- When the result is dominated by ATP / ADP / NADH / NADPH / H2O (currency cofactors that catalysts and transporters touch ubiquitously), pass `exclude_metabolite_ids=[<kegg.compound:Cxxxxx>]` to strip them. Set-difference semantics with `metabolite_ids` — exclude wins on overlap (silent). Per-arm scope: exclude applies on BOTH metabolism + transport arms (mirrors `metabolite_ids`). KG namespace is `kegg.compound:` (not `chebi:`).

- Direction is thin. TCDB rows carry `tcdb_direction` from the node (often `unknown`), never a per-gene call, and the metabolism arm's `Reaction_has_metabolite` edge does not distinguish substrate from product (KEGG equation order is arbitrary). To tell uptake from export or substrate from product for a gene, layer transcriptional evidence (`differential_expression_by_gene`) and functional annotation (`gene_overview` Pfam / KEGG KO names like `*-synthase` vs `*-permease`).

```mistake
genes_by_metabolite(metabolite_ids=[...], organism=...)  # 0 transport rows, then reporting 'no transporter for X'
```

```correction
genes_by_metabolite(metabolite_ids=[...], organism=..., include_tcdb_family_substrates=True)  # after reading tcdb_family_substrates_not_shown; family rows are candidates, not calls
```

```mistake
genes_by_metabolite(metabolite_ids=['C00064'])  # then treating `C00064` in `not_found` as 'no such metabolite'
```

```correction
Metabolite IDs on `metabolite_ids` / `exclude_metabolite_ids` are normalised and
looked up in every identifier the metabolite carries before the query runs:
`C00064` / `kegg.compound:c00064` → `kegg.compound:C00064`, `CHEBI:17234` /
`17234` → `chebi:17234`; `HMDB0000122`, `MNXM732398` and bare InChIKeys resolve
the same way. Retired ids of merged or re-keyed nodes resolve to the surviving
node (`chebi:14654` → nitrate `kegg.compound:C00244`). Every input that isn't
already canonical is listed in envelope `resolved_aliases`
(`{input: [canonical, ...]}`). A removed compound whose measurements moved to
another compound, and a chemical-role id (`chebi:10004`, 'vitamin (role)'),
stay verbatim in `not_found` with a `warnings` entry naming the replacement or
the role. Other unresolved inputs stay verbatim in `not_found` in the form you
passed. Exclude-wins-on-overlap is computed on the canonical IDs, so `metabolite_ids=['C00064'], exclude_metabolite_ids=['kegg.compound:C00064']` excludes.

```

- See `docs://analysis/metabolites` for the 3 source pipelines decision tree (metabolism / transport / metabolomics) and how to read direct vs family TCDB rows, and `docs://guide/concepts` for the chemistry layer overview.

- `not_found.organism` is set when the `organism` name resolves to zero organisms — check it before reading an empty result as 'no chemistry here'.

- `limit` defaults to covering p75 of typical (metabolite × organism) UNION row distributions; coenzyme-tail queries (ATP, water) should page with `offset`.

- A `go_transport` row is a GO term definition, not a gene fact. GO defines the term (for example "urea transmembrane transporter activity") as moving the target; the gene carries the term. Whether the gene deserves the term is the gene → GO edge's `go_sources` / `go_evidence` (`curated`, `family_inferred`, `domain_inferred`). Rank by `go_evidence`, do not read every row as a measured transporter. GO rows never feed `transporter_count_total`, `top_tcdb_families` or `by_tcdb_route`; those stay TCDB-only.

- Biological-process (BP) is not molecular-function (MF). A BP term such as "iron ion transport" also covers storage, regulation and accessory subunits, so a gene carrying one is not necessarily a transporter: MED4 `ftn` (ferritin) reaches iron through that BP term. Read `go_namespace` and prefer MF rows when the question is "which gene is the transporter"; BP rows answer "which genes the literature or annotation links to this transport process".

- An empty GO answer for H+, Na+ or an upper-level class (ion, monoatomic cation, chemical entity, ...) is curation, not biology: those targets were deliberately removed from the GO route. The list is `Schema_info.go_transport_excluded_targets` (surfaced by `kg_release_info`); a warning fires when you ask for one. TCDB and KEGG rows still answer them.

- The three routes are correlated, not independent: GO terms often arrive through InterPro2GO or eggNOG, which share homology with the TCDB calls. Agreement between a `go_transport` row and a `transport` row is therefore weaker evidence than it reads, and disagreement is often naming granularity (a GO class target vs a TCDB specific compound). See `docs://analysis/transport`.

- `go_include_ancestors=True` is the only way inherited GO rows appear; the default is direct rows only. `evidence_source`-scoped filters `ec_numbers`, `mass_balance` and `include_tcdb_family_substrates` do not apply to GO rows (documented no-ops), while `exclude_metabolite_ids`, `metabolite_pathway_ids` and `gene_categories` do.

- A multi-source pair is corroborated, not proven. `by_evidence_source_combination` and `multi_source_gene_count` / `multi_source_metabolite_count` count the (gene, metabolite) pairs that two or more routes name, but the routes share homology (InterPro2GO and eggNOG vs the TCDB calls), so agreement raises confidence without being independent confirmation. A single-source pair is not wrong. `transport` counts as one route whether its rows are direct or family; family rows join the combinations only when `include_tcdb_family_substrates=True`.

- `go_namespace` and `go_evidence` narrow the GO arm only; KEGG and TCDB rows are untouched (as `include_tcdb_family_substrates` widens only TCDB rows). Set while `evidence_sources` excludes `go_transport`, they are ignored with a warning. The inherited-row dedup ignores them, so a filtered result is always a subset of the unfiltered one.

## Package import equivalent

```python
from multiomics_explorer import genes_by_metabolite

result = genes_by_metabolite(metabolite_ids=..., organism=...)
# returns dict with keys: total_matching, returned, offset, truncated, warnings, stereo_relatives, stereo_forms_added, resolved_aliases, not_found, not_matched, by_metabolite, by_evidence_source, by_evidence_source_combination, by_tcdb_route, tcdb_family_substrates_not_shown, tcdb_family_substrates_skipped, rows_by_go_term_depth, top_reactions, top_reactions_truncated, top_tcdb_families, top_tcdb_families_truncated, top_gene_categories, top_genes, top_genes_truncated, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
