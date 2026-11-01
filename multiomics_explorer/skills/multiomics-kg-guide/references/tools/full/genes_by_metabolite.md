# genes_by_metabolite

## What it does

Metabolite / `chebi.role:` IDs to genes in ONE organism via KEGG, TCDB, GO transport (GO rows = term definitions, not gene facts).

Use for compound → genes; mirror metabolites_by_gene; TCDB rows = direct systems, empty ≠ no transporter (see tcdb_family_substrates_not_shown); docs://analysis/transport.
Filters: metabolite_ids (+exclude, +stereo), evidence_sources, include_tcdb_family_substrates, go_*.
Returns: by_metabolite, by_evidence_source(_combination), by_tcdb_route, top_genes/reactions/tcdb_families; row = gene × route × compound.
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
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's full page, docs://tools/{tool}/full. |
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
- **warnings** (list[string]): Diagnostics: stereo relatives with rows (first); genes reachable only via a family call (pass include_tcdb_family_substrates=True); removed / chemical-role ids; unknown gene_categories.
- **stereo_relatives** (object): Input id -> its stereo forms with rows in this organism under the same filters, e.g. {'kegg.compound:C00736': [L-Cysteine entry]}. Counts never combine across forms. Empty with include_stereo_forms=True.
- **stereo_forms_added** (object): include_stereo_forms=True: input id -> stereo forms added to the query (e.g. {'kegg.compound:C00736': ['kegg.compound:C00097']}). Added ids with no rows are not in not_matched.
- **resolved_aliases** (object): Metabolite inputs resolved to a different canonical ID (bare, xref, secondary or retired ids), `{input: [canonical]}`, across `metabolite_ids` and `exclude_metabolite_ids`. Inputs already canonical are not listed.
- **not_found** (GbmNotFound): Inputs that did not resolve to a KG node — see model.
- **not_matched** (list[string]): Input metabolite_ids that exist as Metabolite nodes but produced zero rows in this organism slice (under the active filters). Distinct from `not_found.metabolite_ids` (those don't exist at all).
- **by_metabolite** (list[GbmByMetabolite]): Per-metabolite rollup. One entry per input metabolite_id that produced ≥1 row.
- **by_evidence_source** (list[GbmByEvidenceSource]): Frequency over `evidence_source` values present in the slice (≤3 entries).
- **by_evidence_source_combination** (list[EvidenceSourceCombination]): Gene x metabolite pairs per set of routes naming them, pair_count desc. Routes share homology, so agreement raises confidence but does not prove. [] on empty.
- **by_tcdb_route** (list[GbmByTcdbRoute]): Frequency over `tcdb_route` across transport rows only, direct then family (≤2 entries; family only with include_tcdb_family_substrates=True).
- **tcdb_family_substrates_not_shown** (TcdbFamilySubstratesNotShown | None): Walk off: what include_tcdb_family_substrates=True would add ({genes, metabolites, rows}; zeros = nothing). Null when the walk is on (those rows are in results). Read it before concluding 'no transporter'.
- **tcdb_family_substrates_skipped** (list[TcdbFamilySubstrateSkipped]): Genes whose family-walk start (e.g. ABC 3.A.1) was removed by the 200-substrate breadth cap and carries a queried metabolite. ABC genes recur for most compounds: read as 'substrate unknown', not as candidates for this one.
- **rows_by_go_term_depth** (list[RowsByGoTermDepth] | None): GO route rows per `go_term_depth`, sorted by depth asc. Null unless the go_transport arm is active; depth > 0 rows need go_include_ancestors=True.
- **top_reactions** (list[GbmTopReaction]): Top 10 reactions by gene_count in the metabolism arm. summary=True returns the full ranked list.
- **top_reactions_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **top_tcdb_families** (list[GbmTopTcdbFamily]): Top 10 TCDB families by gene_count in the transport arm. summary=True returns the full ranked list.
- **top_tcdb_families_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **top_gene_categories** (list[GbmTopGeneCategory]): Top 10 gene categories by gene_count across all arms.
- **top_genes** (list[GbmTopGene]): Top 10 genes by reaction_count + transporter_count; GO-only genes rank last (their GO rows are counted in go_transport_rows). summary=True returns the full ranked list.
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
| tcdb_direction | string ('uptake', 'export', 'unknown') \| None (optional) | Transport rows only. TCDB-stated `direction` of the row's node (the system; on family rows the attached node). Node-level, not per gene. Set only by ABC uptake numbering or a system's own name; family rows mostly read 'unknown'. |
| attached_tcdb_id | string \| None (optional) | Transport rows only. The TC node the gene's edge points at (e.g. 'tcdb:3.A.1.9'). Equals `tcdb_family_id` on direct and family rows. |
| tcdb_substrate_system_count | int \| None (optional) | Family rows only (null on direct rows): number of descendant TCDB systems of the attached node curated with this metabolite (e.g. 5). |
| reaction_id | string \| None (optional) | Full prefixed Reaction ID (e.g. 'kegg.reaction:R00253'). Metabolism rows only — see class-level note on undirected, non-reversible interpretation. |
| reaction_name | string \| None (optional) | Reaction systematic name + KEGG equation (raw KEGG value, can be lengthy; a small fraction of reactions have empty `''`). Metabolism rows only — see class-level note on undirected, non-reversible interpretation. |
| ec_numbers | list[string] \| None (optional) | EC classification(s) for this reaction. Empty list on reactions without an EC annotation. None on TCDB and GO rows. |
| mass_balance | string ('balanced', 'unbalanced') \| None (optional) | Reaction mass-balance status. None on TCDB and GO rows. |
| tcdb_family_id | string \| None (optional) | Full prefixed TcdbFamily ID (e.g. 'tcdb:3.A.1.4.5'). Transport rows only. |
| tcdb_family_name | string \| None (optional) | TCDB name of `tcdb_family_id`; for a subfamily or system TCDB left unnamed, the nearest named ancestor's name plus '— subfamily <id>' / '— system <id>'. Transport rows only. |
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
| metabolite_structure_kind | string ('defined', 'generic', 'polymer') \| None (optional) | 'defined' (one molecule), 'generic' (a compound class, e.g. 'Peptide', 'Fatty acid') or 'polymer'. Null on chemical-role targets. |
| via_stereo_form_of | string \| None (optional) | genes_by_metabolite with include_stereo_forms=True: the input id this row's metabolite is a stereo form of (e.g. 'kegg.compound:C00736'). Absent on rows for inputs. |
| stereo_relative_ids | list[string] \| None (optional) | metabolites_by_gene: stereo forms of this row's metabolite with genes in this organism (e.g. ['kegg.compound:C00097']); counts in envelope stereo_relatives. Absent when none. |

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
| go_chebi_ids | list[string] \| None (optional) | ChEBI ids carried by the GO term (e.g. ['CHEBI:26672']). Verbose, GO route rows only. |

## Few-shot examples

### Example 1: Discovery → drill-down — urea catalysts and transporters in MED4

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4")
```

*25 rows across the three routes, each tagged by `evidence_source`, in order: 4 metabolism rows (ureA/B/C on urease R00131, plus speB on agmatinase R01157, which also releases urea), 10 TCDB rows and 11 GO rows. TCDB rows are direct systems by default (`tcdb_route='direct'`): urtA-E (PMM0970-PMM0974) on the two urea systems tcdb:3.A.1.4.4 / 3.A.1.4.5, sorted by `tcdb_identity`, each with `tcdb_calls` and `tcdb_direction` ('uptake', TCDB-stated, node-level). A GO row is a GO term that GO defines as moving urea, carried by the gene (`go_term_id`, `go_namespace`, `go_evidence`); urtA carries go:0033221 'ATPase-coupled urea transmembrane transporter activity' (molecular function) and 'urea transport' (biological process). GO rows never add to `transporter_count_total`. `by_evidence_source_combination` shows where the routes agree: 5 (gene, urea) pairs named by TCDB and GO together (urtA-E) and 4 by KEGG alone. TCDB and GO share homology, so agreement raises confidence and does not prove transport.*

### Example 2: Cross-feeding pair — call once per organism, intersect locus_tags client-side

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
  "warnings": ["No gene reaches these metabolites through a direct TCDB system call in this organism. 4 genes rea..."],
  "...": "15 empty fields omitted",
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": ["kegg.compound:C00009"],
  "tcdb_family_substrates_not_shown": {"genes": 4, "metabolites": 1, "rows": 4},
  "tcdb_family_substrates_skipped": [
    {"locus_tag": "PMM0449", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 547},
    {"locus_tag": "PMM0450", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 547},
    {"locus_tag": "PMM0913", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 547},
    ...
  ],
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
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4", ec_numbers=["3.5.1.5"])
```

*`ec_numbers` narrows the metabolism arm only; TCDB and GO rows come back unchanged. Urea in MED4 drops from 25 to 24 rows: the 3 urease rows (ureA/B/C, R00131) stay, speB (agmatinase, EC 3.5.3.1) drops out, and the 10 TCDB + 11 GO rows remain. To restrict to metabolism alone, add evidence_sources=['metabolism'].*

### Example 8: Generic substrate — Cysteine in MED4 has no reactions; the stereo hint names L-Cysteine

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00736"], organism="Prochlorococcus MED4", summary=True)
```

*TCDB names substrates generically, so Cysteine (stereo form unspecified) carries the transport edges and 0 reactions; KEGG reactions use L-Cysteine. In MED4 no gene points directly at a Cysteine system: `tcdb_family_substrates_not_shown` counts 5 genes the family walk would add. `stereo_relatives` lists L-Cysteine with its MED4 counts (exactly what this tool reports for it), and the stereo warning comes first in `warnings`. (`by_metabolite` is empty here — no direct rows — so there is no entry for `stereo_relative_ids` to mark.) D-Cysteine is not hinted: it has no MED4 genes.*

```example-response
{
  "total_matching": 0,
  "returned": 0,
  "offset": 0,
  "truncated": false,
  "warnings": [
    "Stereo forms hold more rows: Cysteine (kegg.compound:C00736) → L-Cysteine (kegg.compound:C00097):...",
    "No gene reaches these metabolites through a direct TCDB system call in this organism. 5 genes rea..."
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
  "...": "14 empty fields omitted",
  "not_found": {"metabolite_ids": [], "organism": null, "metabolite_pathway_ids": []},
  "not_matched": ["kegg.compound:C00736"],
  "tcdb_family_substrates_not_shown": {"genes": 5, "metabolites": 1, "rows": 5},
  "tcdb_family_substrates_skipped": [
    {"locus_tag": "PMM0449", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 547},
    {"locus_tag": "PMM0450", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 547},
    {"locus_tag": "PMM0913", "tcdb_id": "tcdb:3.A.1", "tcdb_substrate_count": 547},
    ...
  ],
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

### Example 11: Role target — siderophore transporters in Alteromonas mediterranea AltDE1 (target_kind='chemical_role')

```example-call
genes_by_metabolite(metabolite_ids=["chebi.role:26672"], organism="Alteromonas mediterranea AltDE1", evidence_sources=["go_transport"], limit=5)
```

*`chebi.role:<n>` ids are valid inputs. A role row is a class, not a compound: `target_kind='chemical_role'`, `metabolite_id` is the role id, formula and mass are absent, and roles are not propagated to metabolites. The same role id also reaches TCDB role edges. In AltDE1 those are family-level only: the default call adds no TCDB rows, and the warning plus `tcdb_family_substrates_not_shown` (5 genes) point at `include_tcdb_family_substrates=True`. Use the exact strain `Alteromonas mediterranea AltDE1` (the shorter `AltDE` string also word-matches AltDE1 genes).*

### Example 12: Inherited rows are opt-in — go_include_ancestors=True adds is_a-ancestor rows, tagged with the term that names the target

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C01356"], organism="Prochlorococcus MED4", evidence_sources=["go_transport"], go_include_ancestors=True)
```

*Direct rows (`go_term_depth=0`) first; inherited rows follow with `go_term_depth` = number of is_a hops, `go_axiom_term_id` / `go_axiom_term_name` naming the ancestor that carries the target, and `go_term_id` still the gene's own term. A (gene, target) already reached directly through GO is not repeated as an inherited row. Inherited rows are a recall expansion: they widen to broader targets than the gene's own term names. Compare against the default call before using them.*

### Example 13: Narrow the GO arm — molecular-function terms with curated gene evidence only

```example-call
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4", go_namespace=["molecular_function"], go_evidence=["curated"], summary=True)
```

*Keeps 4 of the 11 urea GO rows (the biological-process rows drop out). The KEGG and TCDB rows are untouched, so `total_matching` falls from 25 to 18 only by the GO rows removed. Allowed `go_evidence` values: `list_filter_values`.*

## Chaining patterns

```
list_metabolites(...) → genes_by_metabolite(metabolite_ids=[chosen_ids], organism=...)
list_metabolites (per-row `transporter_gene_count > 0`) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['transport']) — distinct genes in the transport rows, summed over organisms, equal that count
differential_expression_by_gene(...) → top hits → metabolites_by_gene(locus_tags=...) → genes_by_metabolite for the symmetric metabolite-anchored view
N-source survey: list_metabolites(elements=['N']) → genes_by_metabolite(metabolite_ids=[N-bearing IDs], organism=...) for catalysts + transporters
Cross-feeding: genes_by_metabolite called once per organism on the same metabolite_ids; intersect/diff locus_tag result sets client-side
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

- An empty TCDB arm is not "no transporter". TCDB rows are direct systems by default, and many genes are placed by TCDB only at family or subfamily level (`tcdb_gate='annotated'`), which never produces a default row. Read `tcdb_family_substrates_not_shown` and the warning, then re-run with `include_tcdb_family_substrates=True`: orthophosphate in MED4 has 0 direct genes, and the walk adds phnC/D/E and PMM0717 through subfamily tcdb:3.A.1.9. `tcdb_family_substrates_skipped` lists genes whose only call is on a superfamily curated with over 200 substrates (ABC tcdb:3.A.1, MFS tcdb:2.A.1) and whose superfamily carries the queried compound in at least one system. ABC tcdb:3.A.1 carries hundreds of substrates, so its genes recur across many compounds: read them as "substrate unknown", not "candidate for this compound". See `docs://analysis/transport`.

- A `go_transport` row is a GO term definition, not a gene fact. GO defines the term (for example go:0033221 "ATPase-coupled urea transmembrane transporter activity") as moving the target; the gene carries the term. Whether the gene deserves the term is the gene → GO edge's `go_sources` / `go_evidence` (`curated`, `family_inferred`, `domain_inferred`). Rank by `go_evidence`; do not read every row as a measured transporter. GO rows never feed `transporter_count_total`, `top_tcdb_families` or `by_tcdb_route`; those stay TCDB-only.

- Biological-process (BP) is not molecular-function (MF). A BP term such as "iron ion transport" also covers storage, regulation and accessory subunits, so a gene carrying one is not necessarily a transporter: MED4 `ftn` (ferritin) reaches iron through that BP term. Read `go_namespace` and prefer MF rows when the question is "which gene is the transporter"; BP rows answer "which genes the literature or annotation links to this transport process".

- 0 reactions on a generic substrate does not mean no enzymes. Stereo forms are separate nodes and no count combines across them: TCDB names substrates generically ('Cysteine', `kegg.compound:C00736`), so transport sits there; KEGG reactions use the specific form (L-Cysteine, `kegg.compound:C00097`), so catalysis sits there. Read envelope `stereo_relatives` (organism-scoped counts per relative, under your filters; only relatives with genes here) and the stereo warning, then re-run with `include_stereo_forms=True` for a transport ↔ catalysis join. Keep the single id for exact-form or D-amino-acid questions: a generic's specific forms can include the D-form. Class terms ('amino acid') and ring vs open-chain forms are never linked, so no hint is not proof of no related compound; search by name with `list_metabolites(search_text=...)`.

- Rank TCDB direct rows (a `tcdb_gate='direct'` call on a TC system that TCDB curates with the compound; one row per gene × system × metabolite) by `tcdb_identity` (DIAMOND identity in percent of the row's representative call; null when that call is eggNOG), then by `tcdb_calls` (eggNOG plus a DIAMOND kind is independent agreement; `diamond_tier` and `diamond_best_hit` come from one DIAMOND run, so the two together are one source). Never filter on `tcdb_identity`: an eggNOG-only row is not weaker for reading null.

- Family rows (`tcdb_route='family'`) are a recall expansion, not a substrate call. The walk runs from the gene's deepest `annotated` family or subfamily down to every TC system under it and reports the systems' curated substrates, one row per gene × attached node × metabolite (`tcdb_family_id` = `attached_tcdb_id` = the family itself; `tcdb_substrate_system_count` = systems under it curated with the metabolite). It never starts above a gene's own direct system, so a gene with a direct call keeps exactly its system's substrates. TCDB curation is taken as-is: the Pst phosphate system tcdb:3.A.1.7.6 is curated with triphosphate only, so pstA/B/C/S do not reach orthophosphate (the system name still says phosphate), and catch-all substrates ("Peptide", "Protein") pass through. Most remaining noise is eggNOG family calls on genes that are not transporters at all.

- Direction is thin. `tcdb_direction` (`uptake` / `export` / `unknown`) is TCDB's direction for the row's node, not a per-gene measurement, and most nodes read `unknown` (it comes from ABC uptake numbering or a system's own TCDB name; family and subfamily names never set it). KEGG reaction rows are not directional at all: the KG carries no substrate-vs-product role and no reversibility flag, so read a metabolism row as "catalyses a reaction involving this metabolite", never "produces" or "consumes". GO rows carry no direction. To tell uptake from export or substrate from product, layer `differential_expression_by_gene` and functional annotation (`gene_overview`).

- Distinct direct genes across the transport rows, unioned over organisms, equal `list_metabolites.transporter_gene_count`, and gene-side, distinct direct Metabolite targets equal `gene_overview.transported_metabolite_count` (role rows excluded). Family rows are not in either count. Genes with only weak DIAMOND hits (`tcdb_gate='below_gate'`) never reach a substrate here; `gene_ontology_terms(..., include_weak_tcdb_hits=True)` shows them.

- Rows from all three arms share one schema. Fields that belong to another arm are `None` (`tcdb_*` on KEGG and GO rows; `reaction_*`, `ec_numbers` and `mass_balance` on TCDB and GO rows; `go_*` on KEGG and TCDB rows). Null optional fields (`gene_name`; formula, mass and ChEBI id on role rows) can be left out of a row entirely, so read them with `row.get(...)`. Branch on `evidence_source`.

- Filters are scoped per arm. `ec_numbers` and `mass_balance` narrow the metabolism arm only; TCDB and GO rows come back unchanged. `include_tcdb_family_substrates` widens TCDB only; `go_include_ancestors`, `go_namespace` and `go_evidence` touch GO only (set while `evidence_sources` excludes `go_transport`, they are ignored with a warning; a filtered result is always a subset of the unfiltered one). `metabolite_ids`, `exclude_metabolite_ids`, `metabolite_pathway_ids` and `gene_categories` apply to all three arms. To restrict to one arm, set `evidence_sources` explicitly.

- `go_include_ancestors=True` is the only way inherited GO rows appear; the default is direct rows only. Inherited rows widen to broader targets than the gene's own term names, so compare against the default call.

- When the result is dominated by ATP / ADP / NADH / NADPH / H2O (currency cofactors that catalysts and transporters touch ubiquitously), pass `exclude_metabolite_ids=[<kegg.compound:Cxxxxx>]` to strip them. Exclude wins on overlap with `metabolite_ids` (silent) and applies to all three arms.

- An empty transport answer for H+, Na+ or a placeholder / upper-level class (ion, monoatomic cation, molecule, ...) is curation, not biology: those targets were deliberately removed from the GO route and the TCDB substrate route. The lists are `Schema_info.go_transport_excluded_targets` and `Schema_info.tcdb_substrate_excluded_targets` (both surfaced by `kg_release_info`); a warning naming the route(s) fires when you ask for one. Only KEGG rows can still answer (H+ has 250 metabolism rows in MED4).

- A multi-source pair is corroborated, not proven. `by_evidence_source_combination` and `multi_source_gene_count` / `multi_source_metabolite_count` count the (gene, metabolite) pairs that two or more routes name, but GO terms often arrive through InterPro2GO or eggNOG, which share homology with the TCDB calls, so agreement raises confidence without being independent confirmation. Disagreement is often naming granularity (a GO class target vs a TCDB specific compound); a single-source pair is not wrong. `transport` counts as one route whether its rows are direct or family; family rows join the combinations only when `include_tcdb_family_substrates=True`. See `docs://analysis/transport`.

- Metabolite-anchored (metabolite → genes). The gene-anchored mirror is `metabolites_by_gene` (locus_tags → metabolites); both share the same row class, discriminators and per-arm filter scope, so read whichever matches your anchor rather than post-filtering the other.

- Single organism per call. There is no `organisms` list. For cross-organism / cross-feeding work, call once per organism with the same metabolite_ids and combine locus_tag result sets client-side.

- `'metabolomics'` is not accepted in `evidence_sources` here (allowed: `metabolism`, `transport`, `go_transport`). Measurements have no gene anchor, so a measured-only metabolite returns no rows from this tool; use `list_metabolite_assays` / `assays_by_metabolite` for measurement evidence.

- TCDB-class filtering does NOT belong here. There is no `tcdb_class_ids` parameter. TCDB is a first-class ontology — for "all genes in TCDB class 3.A.1 (ABC superfamily) for organism X", route through `genes_by_ontology(ontology='tcdb', term_ids=['tcdb:3.A.1'], organism=...)`. From here the drill-out path is `top_tcdb_families[i].tcdb_family_id` → `genes_by_ontology(ontology='tcdb', term_ids=[that_id], organism=...)`.

- `not_found.metabolite_ids` vs `not_matched`. `not_found.metabolite_ids` = IDs that don't exist as a Metabolite node at all (typo, wrong prefix, ChEBI ID not in our KG). `not_matched` = IDs whose Metabolite exists but produced zero rows in this organism slice under the active filters (e.g. transport-only metabolite curated for non-MED4 strains). Don't conflate them — `not_matched` may go to zero by relaxing filters or swapping organism; `not_found` won't.

- A row with `metabolite_structure_kind='generic'` names a compound class (e.g. fatty acid, peptide), not one molecule — read it as "some member of this class".

```mistake
genes_by_metabolite(metabolite_ids=[...], organism=...)  # 0 transport rows, then reporting 'no transporter for X'
```

```correction
genes_by_metabolite(metabolite_ids=[...], organism=..., include_tcdb_family_substrates=True)  # after reading tcdb_family_substrates_not_shown; family rows are candidates, not calls
```

```mistake
genes_by_metabolite(metabolite_ids=['C00064'], ...)  # then treating `C00064` in `not_found` as 'no such metabolite'
```

```correction
IDs in any form (bare, prefixed, ChEBI / HMDB / MNX / InChIKey, retired) resolve before the query; read `resolved_aliases`. `chebi.role:<n>` ids, and the `chebi:` id of a role, resolve to the role and return role rows. Removed compounds warn. See docs://analysis/metabolites, 'Metabolite ID forms'.
```

- See `docs://analysis/metabolites` (evidence sources: metabolism, TCDB transport, GO transport, metabolomics) and `docs://analysis/transport` for reading the transport routes; `docs://guide/concepts` has the chemistry layer overview.

- `not_found.organism` is set when the `organism` name resolves to zero organisms — check it before reading an empty result as 'no chemistry here'.

- `limit` defaults to 10. One metabolite often has more rows than that (urea in MED4: 25), so call `summary=True` first, then page with `offset`.

## Package import equivalent

```python
from multiomics_explorer import genes_by_metabolite

result = genes_by_metabolite(metabolite_ids=..., organism=...)
# returns dict with keys: total_matching, returned, offset, truncated, warnings, stereo_relatives, stereo_forms_added, resolved_aliases, not_found, not_matched, by_metabolite, by_evidence_source, by_evidence_source_combination, by_tcdb_route, tcdb_family_substrates_not_shown, tcdb_family_substrates_skipped, rows_by_go_term_depth, top_reactions, top_reactions_truncated, top_tcdb_families, top_tcdb_families_truncated, top_gene_categories, top_genes, top_genes_truncated, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
