# metabolites_by_gene

## What it does

Metabolites a gene batch reaches in ONE organism via KEGG, TCDB and GO transport (GO rows: term definitions, not gene facts).

Use for gene → compounds; mirror genes_by_metabolite; docs://analysis/transport.
Filters: locus_tags, metabolite_elements, metabolite_ids (+exclude, roles ok), ec_numbers, evidence_sources, include_tcdb_family_substrates, go_*.
Returns: by_gene, by_element, by_evidence_source(_combination), by_tcdb_route, tcdb_family_substrates_not_shown, top_metabolites; row = gene × reaction|TCDB|GO term × compound.
docs://tools/metabolites_by_gene; summary=True first for 50+ genes.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to drill into (case-sensitive). E.g. ['PMM0963', 'PMM0964', 'PMM0965'] for urease α/β/γ subunits. `not_found.locus_tags` lists tags that don't resolve to any Gene in the requested organism; `not_matched` lists tags that DO resolve but have no chemistry path (no reaction, TCDB or GO transport row). |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Must resolve to ONE organism — an ambiguous match (e.g. a genus word) raises; see list_organisms. |
| metabolite_elements | list[string] \| None | None | Filter to rows where the metabolite contains ALL of the given element symbols (AND-of-presence). E.g. `['N']` keeps only N-bearing metabolites — the headline N-source workflow primitive. `['N', 'P']` requires both. Anchored on `Metabolite.elements` (KG-A3 Hill-parsed presence list); applies uniformly to all three arms. Never substring-match on `formula` (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). `not_found.metabolite_elements` lists symbols that don't exist on any KG metabolite. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs in any form (KEGG, ChEBI, MNX, HMDB, InChIKey; bare or prefixed). Retired ids resolve (see resolved_aliases); removed compounds warn. `chebi.role:` ids reach TCDB / GO role edges. docs://analysis/transport. |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; any id form, bare or prefixed, retired ids resolve (see resolved_aliases); exclude wins on overlap. |
| ec_numbers | list[string] \| None | None | Narrow metabolism rows to those whose Reaction carries any of these EC numbers. **Metabolism arm only — does not affect TCDB or GO transport rows**, which are returned unchanged. To restrict to metabolism rows alone, combine with `evidence_sources=['metabolism']`. E.g. ['3.5.1.5'] for urease. |
| metabolite_pathway_ids | list[string] \| None | None | Filter to rows where the **metabolite** is in any of these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` (transport-extended), so applies uniformly to all three arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway annotations, route through `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)` first to obtain locus_tags. `not_found.metabolite_pathway_ids` lists IDs that don't exist as a KeggTerm. |
| mass_balance | string ('balanced', 'unbalanced') \| None | None | Narrow metabolism rows to those whose Reaction has this mass balance status. **Metabolism arm only — does not affect TCDB or GO transport rows**. Combine with `evidence_sources=['metabolism']` to restrict to metabolism rows alone. |
| gene_categories | list[string] \| None | None | Filter on `Gene.gene_category` (exact match, applies to all three arms uniformly). Use `list_filter_values(filter_type="gene_category")` for valid values. Note: somewhat redundant with `locus_tags` input; useful when locus_tags is a broad batch and you want chemistry from specific functional categories only. |
| evidence_sources | list[string ('metabolism', 'transport', 'go_transport')] \| None | None | Path selector — restricts which arms execute (metabolism, transport, go_transport). Default fires all three. `['metabolism']` skips transport rollup noise. 'metabolomics' is NOT valid here (no gene anchor); see `list_metabolites`. |
| include_tcdb_family_substrates | bool | False | TCDB arm: also walk from the gene's family / subfamily calls down to their systems' substrates (tcdb_route='family'; a recall fallback for genes with no system). Adds rows only; ignored without the transport arm. |
| go_include_ancestors | bool | False | GO route only: also return inherited rows, where a gene's GO term reaches the target through is_a ancestors (go_term_depth > 0). Default False = directly annotated terms. |
| go_namespace | list[string ('molecular_function', 'biological_process')] \| None | None | GO arm only: keep GO rows whose gene->GO edge is in these namespaces. TCDB / KEGG rows untouched. Filtered result is always a subset of the unfiltered one. |
| go_evidence | list[string] \| None | None | GO arm only: keep GO rows whose gene->GO edge evidence is in this list (e.g. ['curated']; family_inferred, domain_inferred). Unknown values raise. TCDB / KEGG rows untouched; result is a subset of the unfiltered one. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 10 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, warnings, stereo_relatives, resolved_aliases, not_found, not_matched, by_gene, by_evidence_source, by_evidence_source_combination, by_tcdb_route, tcdb_family_substrates_not_shown, tcdb_family_substrates_skipped, rows_by_go_term_depth, by_element, top_metabolites, top_reactions, top_tcdb_families, top_gene_categories, top_metabolite_pathways, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

- **total_matching** (int): Total row count after all filters, across all arms.
- **returned** (int): Number of rows in `results` (≤ `limit`).
- **offset** (int): Echo of the requested offset.
- **truncated** (bool): True when `offset + limit < total_matching`.
- **warnings** (list[string]): Diagnostics: stereo relatives (first); per gene with TCDB calls but no direct system, try include_tcdb_family_substrates=True (or superfamily-only, substrate unknown); capped starts; removed ids; locus_tag case mismatches.
- **stereo_relatives** (object): Slice metabolite id -> its stereo forms with genes in this organism (whole organism, not just these genes), e.g. {'kegg.compound:C00736': [L-Cysteine entry]}. Counts never combine across forms.
- **resolved_aliases** (object): Metabolite inputs resolved to a different canonical ID (bare, xref, secondary or retired ids), `{input: [canonical]}`, across `metabolite_ids` and `exclude_metabolite_ids`. Inputs already canonical are not listed.
- **not_found** (MbgNotFound): Inputs that did not resolve to a KG node — see model.
- **not_matched** (list[string]): Input locus_tags that resolve to a Gene in the requested organism but produced zero chemistry rows (no reaction, TCDB or GO transport path). Distinct from `not_found.locus_tags` (those don't resolve at all).
- **by_gene** (list[MbgByGene]): Per-gene rollup. One entry per input locus_tag that produced ≥1 row.
- **by_evidence_source** (list[MbgByEvidenceSource]): Frequency over `evidence_source` values present in the slice (≤3 entries).
- **by_evidence_source_combination** (list[EvidenceSourceCombination]): Gene x metabolite pairs per set of agreeing sources, pair_count desc. Agreement = independent routes naming the same pair; correlated (shared homology), so it raises confidence but does not prove. [] on empty.
- **by_tcdb_route** (list[MbgByTcdbRoute]): Frequency over `tcdb_route` across transport rows only, direct then family (≤2 entries; family only with include_tcdb_family_substrates=True).
- **tcdb_family_substrates_not_shown** (TcdbFamilySubstratesNotShown | None): Walk off: what include_tcdb_family_substrates=True would add ({genes, metabolites, rows}; zeros = nothing). Null when the walk is on (those rows are in results). Read it before concluding 'no transporter'.
- **tcdb_family_substrates_skipped** (list[TcdbFamilySubstrateSkipped]): Genes whose family-walk start was removed by the 200-substrate breadth cap (superfamily call, substrate unknown), e.g. ABC 3.A.1. Always computed.
- **rows_by_go_term_depth** (list[RowsByGoTermDepth] | None): GO route rows per `go_term_depth`, sorted by depth asc. Null unless the go_transport arm is active; depth > 0 rows need go_include_ancestors=True.
- **by_element** (list[MbgByElement]): Element-presence rollup across the metabolites the gene set touches. Singleton elements (metabolite_count < 2) are dropped, then capped to the top 10 by metabolite_count desc on detail calls; summary=True returns the full rollup. Presence-only — count of distinct compounds containing each element at all. NOT stoichiometric (no atom counts per compound; stoichiometry lives in `metabolite.formula`). NOT mass-balanced (KG carries no substrate-vs-product role on `Reaction_has_metabolite`).
- **by_element_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **top_metabolites** (list[MbgTopMetabolite]): Top 10 metabolites by gene reach in the filtered slice. The headline answer to 'what metabolites do my gene set hit most.' Drill into any entry via `list_metabolites(metabolite_ids=[id])`.
- **top_reactions** (list[MbgTopReaction]): Top 10 reactions by gene_count in the metabolism arm. Drill into any entry via `genes_by_ontology(ontology="ec", term_ids=[ec], organism=...)`.
- **top_tcdb_families** (list[MbgTopTcdbFamily]): Top 10 TCDB families by gene_count in the transport arm. Drill into any entry via `genes_by_ontology(ontology="tcdb", term_ids=[id], organism=...)`.
- **top_gene_categories** (list[MbgTopGeneCategory]): Top 10 gene categories by gene_count across all arms.
- **top_metabolite_pathways** (list[MbgTopPathway]): NEW (vs GBM): top 10 KEGG pathways the gene set's chemistry reaches, sorted by gene_count desc then pathway_metabolite_count asc. Metabolite-pathway rollup (distinct from KO-pathway annotations on `genes_by_ontology(ontology="kegg")`) — see model docstring for naming disambiguation. Drill into any entry via `list_metabolites(pathway_ids=[id])`. summary=True returns the full ranked list.
- **top_metabolite_pathways_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **no_formula_excluded** (int | None): Rows passing every other filter but dropped by `metabolite_elements` because the metabolite has no formula (generic classes like 'amino acid' never match). Null when no element filter.
- **no_formula_excluded_metabolites** (int | None): Distinct metabolites behind `no_formula_excluded` (no formula, so never match `metabolite_elements`). Null when no element filter.
- **gene_count_total** (int): Distinct input genes in the filtered slice (across all arms).
- **reaction_count_total** (int): Distinct reactions in the filtered metabolism arm.
- **transporter_count_total** (int): Distinct TcdbFamily nodes in the filtered transport arm.
- **metabolite_count_total** (int): Distinct metabolites that produced ≥1 row across all arms.

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

### Example 1: Single-gene drill-down — a direct transporter (Workflow D)

```example-call
metabolites_by_gene(locus_tags=["PMM0372"], organism="Prochlorococcus MED4", evidence_sources=["transport"])
```

### Example 2: Single-gene drill-down — superfamily-only gene (substrate unknown)

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
          by_gene[].tcdb_direct_rows vs tcdb_family_rows separates genes
          TCDB placed in a system from family-level candidates (family
          rows only with include_tcdb_family_substrates=True).

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

### Example 8: Family walk — phnD (PMM0673) has no system call, so its substrates come from subfamily tcdb:3.A.1.9

```example-call
metabolites_by_gene(locus_tags=["PMM0673"], organism="Prochlorococcus MED4", evidence_sources=["transport"], include_tcdb_family_substrates=True)
```

*Without the switch the transport arm is empty, and the warning says a family or subfamily call can reach substrates (`tcdb_family_substrates_not_shown` = 5 rows). phnD's usable call is eggNOG on subfamily tcdb:3.A.1.9 (PhnT, uptake); its DIAMOND hit is a weak tier-3 call on 3.A.1. The walk adds one `tcdb_route='family'` row per metabolite curated on a system under 3.A.1.9: orthophosphate, phosphonic acid, phosphite, phosphinate and Fe3+. `tcdb_family_id` = `attached_tcdb_id` = tcdb:3.A.1.9, `tcdb_substrate_system_count` counts the systems behind each row, and `tcdb_identity` is null because the call is eggNOG. These rows are candidates (a recall expansion), not substrate calls.*

### Example 9: Curation quirk — pstS (PMM0710) reaches triphosphate only, not orthophosphate

```example-call
metabolites_by_gene(locus_tags=["PMM0710"], organism="Prochlorococcus MED4", evidence_sources=["transport"], include_tcdb_family_substrates=True)
```

*pstS points directly at tcdb:3.A.1.7.6 ("High affinity phosphate-specific transporter, PstABCS", best hit 85.9% identity, `tcdb_calls` = all three kinds). TCDB curates that system with triphosphate only, so the one row is Triphosphate. The switch adds nothing: the family walk never starts above one of the gene's direct systems. TCDB curation is reported as-is; read `tcdb_family_name` next to the metabolite.*

### Example 10: Stereo hint — a transporter's generic substrates point at their specific forms

```example-call
metabolites_by_gene(locus_tags=["PMM0065"], organism="Prochlorococcus MED4", evidence_sources=["transport"], include_tcdb_family_substrates=True, summary=True)
```

*TCDB names substrates generically, so this gene's family rows (through subfamily tcdb:3.A.1.106) reach Cysteine (stereo form unspecified), not L-Cysteine. Envelope `stereo_relatives` is keyed by each result metabolite that has a stereo relative with MED4 genes; its counts cover the whole organism, not just PMM0065, and match `genes_by_metabolite` on the relative. Next step: `genes_by_metabolite(metabolite_ids=['kegg.compound:C00736'], organism='Prochlorococcus MED4', include_stereo_forms=True, include_tcdb_family_substrates=True)`.*

```example-response
{
  "total_matching": 40,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "warnings": [
    "Stereo forms hold more rows: Cysteine (kegg.compound:C00736) → L-Cysteine (kegg.compound:C00097): 13 reactions, 0 tra..."
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
  "resolved_aliases": {},
  "not_found": {
    "locus_tags": [],
    "organism": null,
    "metabolite_ids": [],
    "metabolite_pathway_ids": [],
    "metabolite_elements": []
  },
  "not_matched": [],
  "by_gene": [
    {
      "locus_tag": "PMM0065",
      "gene_name": "mcyH",
      "product": "ABC transporter, ATPase component",
      "rows": 40,
      "metabolite_count": 38,
      "reaction_count": 0,
      "transporter_count": 8,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 38,
      "go_transport_rows": 0,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 8
    }
  ],
  "by_evidence_source": [{"evidence_source": "transport", "count": 40}],
  "by_evidence_source_combination": [{"evidence_sources": ["transport"], "pair_count": 38}],
  "by_tcdb_route": [{"tcdb_route": "direct", "count": 2}, {"tcdb_route": "family", "count": 38}],
  "tcdb_family_substrates_not_shown": null,
  "tcdb_family_substrates_skipped": [],
  "rows_by_go_term_depth": null,
  "by_element": [
    {"element": "C", "metabolite_count": 27},
    {"element": "H", "metabolite_count": 27},
    {"element": "O", "metabolite_count": 26},
    {"element": "N", "metabolite_count": 22},
    {"element": "S", "metabolite_count": 5},
    ...
  ],
  "by_element_truncated": null,
  "top_metabolites": [
    {
      "metabolite_id": "chebi.role:23888",
      "name": "drug",
      "formula": null,
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 2,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    },
    {
      "metabolite_id": "chebi:135075",
      "name": "alphaprodine",
      "formula": "C16H23NO2",
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 1,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    },
    {
      "metabolite_id": "chebi:138159",
      "name": "chemokine ligand 24",
      "formula": null,
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 1,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    },
    {
      "metabolite_id": "chebi:25051",
      "name": "lipid As",
      "formula": null,
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 1,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    },
    {
      "metabolite_id": "chebi:36080",
      "name": "protein",
      "formula": null,
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 1,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    },
    ...
  ],
  "top_reactions": [],
  "top_tcdb_families": [
    {
      "tcdb_family_id": "tcdb:3.A.1.106",
      "tcdb_family_name": "The Lipid Exporter (LipidE) Family",
      "level_kind": "tc_subfamily",
      "tcdb_route": "family",
      "direction": "export",
      "gene_count": 1,
      "metabolite_count": 29
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.110",
      "tcdb_family_name": "The Protein-2 Exporter (Prot2E) Family",
      "level_kind": "tc_subfamily",
      "tcdb_route": "family",
      "direction": "export",
      "gene_count": 1,
      "metabolite_count": 2
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.112",
      "tcdb_family_name": "The Peptide-2 Exporter (Pep2E) Family",
      "level_kind": "tc_subfamily",
      "tcdb_route": "family",
      "direction": "export",
      "gene_count": 1,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.113",
      "tcdb_family_name": "The Peptide-3 Exporter (Pep3E) Family",
      "level_kind": "tc_subfamily",
      "tcdb_route": "family",
      "direction": "export",
      "gene_count": 1,
      "metabolite_count": 3
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.117",
      "tcdb_family_name": "The Drug Exporter-2 (DrugE2) Family",
      "level_kind": "tc_subfamily",
      "tcdb_route": "family",
      "direction": "export",
      "gene_count": 1,
      "metabolite_count": 1
    },
    ...
  ],
  "top_gene_categories": [{"category": "Transport", "gene_count": 1}],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko01053",
      "metabolite_pathway_name": "Biosynthesis of siderophore group nonribosomal peptides",
      "gene_count": 1,
      "pathway_reaction_count": 3,
      "pathway_metabolite_count": 7
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00521",
      "metabolite_pathway_name": "Streptomycin biosynthesis",
      "gene_count": 1,
      "pathway_reaction_count": 8,
      "pathway_metabolite_count": 11
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01055",
      "metabolite_pathway_name": "Biosynthesis of vancomycin group antibiotics",
      "gene_count": 1,
      "pathway_reaction_count": 4,
      "pathway_metabolite_count": 13
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00910",
      "metabolite_pathway_name": "Nitrogen metabolism",
      "gene_count": 1,
      "pathway_reaction_count": 24,
      "pathway_metabolite_count": 18
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00450",
      "metabolite_pathway_name": "Selenocompound metabolism",
      "gene_count": 1,
      "pathway_reaction_count": 13,
      "pathway_metabolite_count": 19
    },
    ...
  ],
  "top_metabolite_pathways_truncated": null,
  "no_formula_excluded": null,
  "no_formula_excluded_metabolites": null,
  "gene_count_total": 1,
  "reaction_count_total": 0,
  "transporter_count_total": 8,
  "metabolite_count_total": 38,
  "results": []
}
```

### Example 11: GO transport rows next to TCDB — PMM0970 (urtA) in MED4

```example-call
metabolites_by_gene(locus_tags=["PMM0970"], organism="Prochlorococcus MED4")
```

*TCDB rows come first: urea through both direct urea systems (tcdb:3.A.1.4.4 and 3.A.1.4.5, one row each), thiourea and hydroxyurea through 3.A.1.4.5; the two GO rows (a molecular-function and a biological-process term, both naming urea, `go_term_depth=0`) follow. `rows_by_evidence_source` carries `go_transport` alongside `transport`. A GO row is a term definition: read `go_evidence` and `go_sources` for how the gene came to carry the term.*

```example-response
{
  "total_matching": 6,
  "returned": 6,
  "offset": 0,
  "truncated": false,
  "warnings": [],
  "stereo_relatives": {},
  "resolved_aliases": {},
  "not_found": {
    "locus_tags": [],
    "organism": null,
    "metabolite_ids": [],
    "metabolite_pathway_ids": [],
    "metabolite_elements": []
  },
  "not_matched": [],
  "by_gene": [
    {
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "product": "ABC-type urea transporter, substrate binding component",
      "rows": 6,
      "metabolite_count": 3,
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 4,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    }
  ],
  "by_evidence_source": [{"evidence_source": "transport", "count": 4}, {"evidence_source": "go_transport", "count": 2}],
  "by_evidence_source_combination": [
    {"evidence_sources": ["transport"], "pair_count": 2},
    {"evidence_sources": ["go_transport", "transport"], "pair_count": 1}
  ],
  "by_tcdb_route": [{"tcdb_route": "direct", "count": 4}],
  "tcdb_family_substrates_not_shown": {"genes": 0, "metabolites": 0, "rows": 0},
  "tcdb_family_substrates_skipped": [],
  "rows_by_go_term_depth": [{"go_term_depth": 0, "count": 2}],
  "by_element": [
    {"element": "C", "metabolite_count": 3},
    {"element": "H", "metabolite_count": 3},
    {"element": "N", "metabolite_count": 3},
    {"element": "O", "metabolite_count": 2}
  ],
  "by_element_truncated": null,
  "top_metabolites": [
    {
      "metabolite_id": "kegg.compound:C00086",
      "name": "Urea",
      "formula": "CH4N2O",
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 2,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_gene_count": 1
    },
    {
      "metabolite_id": "kegg.compound:C07044",
      "name": "Hydroxyurea",
      "formula": "CH4N2O2",
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 1,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    },
    {
      "metabolite_id": "kegg.compound:C14415",
      "name": "Thiourea",
      "formula": "CH4N2S",
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 1,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    }
  ],
  "top_reactions": [],
  "top_tcdb_families": [
    {
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (<1 μM) urea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 1,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.4.5",
      "tcdb_family_name": "The high affinity urea/thiourea/hydroxyurea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 1,
      "metabolite_count": 3
    }
  ],
  "top_gene_categories": [{"category": "Stress response and adaptation", "gene_count": 1}],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko00780",
      "metabolite_pathway_name": "Biotin metabolism",
      "gene_count": 1,
      "pathway_reaction_count": 18,
      "pathway_metabolite_count": 22
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00220",
      "metabolite_pathway_name": "Arginine biosynthesis",
      "gene_count": 1,
      "pathway_reaction_count": 26,
      "pathway_metabolite_count": 24
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00998",
      "metabolite_pathway_name": "Biosynthesis of various antibiotics",
      "gene_count": 1,
      "pathway_reaction_count": 5,
      "pathway_metabolite_count": 40
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00240",
      "metabolite_pathway_name": "Pyrimidine metabolism",
      "gene_count": 1,
      "pathway_reaction_count": 73,
      "pathway_metabolite_count": 57
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00330",
      "metabolite_pathway_name": "Arginine and proline metabolism",
      "gene_count": 1,
      "pathway_reaction_count": 61,
      "pathway_metabolite_count": 60
    },
    ...
  ],
  "top_metabolite_pathways_truncated": null,
  "no_formula_excluded": null,
  "no_formula_excluded_metabolites": null,
  "gene_count_total": 1,
  "reaction_count_total": 0,
  "transporter_count_total": 2,
  "metabolite_count_total": 3,
  "results": [
    {
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "product": "ABC-type urea transporter, substrate binding component",
      "evidence_source": "transport",
      "tcdb_route": "direct",
      "tcdb_calls": ["diamond_best_hit", "diamond_tier", "eggnog"],
      "tcdb_identity": 57.1,
      "tcdb_direction": "uptake",
      "attached_tcdb_id": "tcdb:3.A.1.4.4",
      "tcdb_substrate_system_count": null,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (<1 μM) urea porter",
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
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "product": "ABC-type urea transporter, substrate binding component",
      "evidence_source": "transport",
      "tcdb_route": "direct",
      "tcdb_calls": ["diamond_tier", "eggnog"],
      "tcdb_identity": null,
      "tcdb_direction": "uptake",
      "attached_tcdb_id": "tcdb:3.A.1.4.5",
      "tcdb_substrate_system_count": null,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.4.5",
      "tcdb_family_name": "The high affinity urea/thiourea/hydroxyurea porter",
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
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "product": "ABC-type urea transporter, substrate binding component",
      "evidence_source": "transport",
      "tcdb_route": "direct",
      "tcdb_calls": ["diamond_tier", "eggnog"],
      "tcdb_identity": null,
      "tcdb_direction": "uptake",
      "attached_tcdb_id": "tcdb:3.A.1.4.5",
      "tcdb_substrate_system_count": null,
      "reaction_id": null,
      "reaction_name": null,
      "ec_numbers": null,
      "mass_balance": null,
      "tcdb_family_id": "tcdb:3.A.1.4.5",
      "tcdb_family_name": "The high affinity urea/thiourea/hydroxyurea porter",
      "go_term_id": null,
      "go_term_name": null,
      "go_namespace": null,
      "go_evidence": null,
      "go_sources": null,
      "go_term_depth": null,
      "go_axiom_term_id": null,
      "go_axiom_term_name": null,
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C07044",
      "metabolite_name": "Hydroxyurea",
      "metabolite_formula": "CH4N2O2",
      "metabolite_mass": 76.055,
      "metabolite_chebi_id": "44423"
    },
    ...
  ]
}
```

### Example 12: Inherited target — murJ (PMM0261) reaches Lipid only through an ancestor GO term (go_include_ancestors=True)

```example-call
metabolites_by_gene(locus_tags=["PMM0261"], organism="Prochlorococcus MED4", go_include_ancestors=True)
```

*Without the flag this gene has no GO rows (only TCDB). With it, the GO row names Lipid at `go_term_depth=1`: the gene's own term is lipid translocation, the ancestor that names the target is lipid transport (`go_axiom_term_id` / `go_axiom_term_name`). Inherited rows come after every direct row for the same gene set and widen toward broader targets, so treat them as recall.*

```example-response
{
  "total_matching": 1,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "warnings": [
    "No direct TCDB system call for PMM0261: their transport arm is empty, but a TCDB family or subfamily call can reach s..."
  ],
  "stereo_relatives": {},
  "resolved_aliases": {},
  "not_found": {
    "locus_tags": [],
    "organism": null,
    "metabolite_ids": [],
    "metabolite_pathway_ids": [],
    "metabolite_elements": []
  },
  "not_matched": [],
  "by_gene": [
    {
      "locus_tag": "PMM0261",
      "gene_name": "murJ",
      "product": "peptidoglycan lipid II flippase",
      "rows": 1,
      "metabolite_count": 1,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_metabolite_count": 0,
      "tcdb_assignment_count": 1
    }
  ],
  "by_evidence_source": [{"evidence_source": "go_transport", "count": 1}],
  "by_evidence_source_combination": [{"evidence_sources": ["go_transport"], "pair_count": 1}],
  "by_tcdb_route": [],
  "tcdb_family_substrates_not_shown": {"genes": 1, "metabolites": 3, "rows": 3},
  "tcdb_family_substrates_skipped": [],
  "rows_by_go_term_depth": [{"go_term_depth": 1, "count": 1}],
  "by_element": [],
  "by_element_truncated": null,
  "top_metabolites": [
    {
      "metabolite_id": "kegg.compound:C01356",
      "name": "Lipid",
      "formula": null,
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_gene_count": 0
    }
  ],
  "top_reactions": [],
  "top_tcdb_families": [],
  "top_gene_categories": [{"category": "Cell wall and membrane", "gene_count": 1}],
  "top_metabolite_pathways": [],
  "top_metabolite_pathways_truncated": null,
  "no_formula_excluded": null,
  "no_formula_excluded_metabolites": null,
  "gene_count_total": 1,
  "reaction_count_total": 0,
  "transporter_count_total": 0,
  "metabolite_count_total": 1,
  "results": [
    {
      "locus_tag": "PMM0261",
      "gene_name": "murJ",
      "product": "peptidoglycan lipid II flippase",
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
      "go_term_id": "go:0034204",
      "go_term_name": "lipid translocation",
      "go_namespace": "biological_process",
      "go_evidence": "curated",
      "go_sources": ["ncbi"],
      "go_term_depth": 1,
      "go_axiom_term_id": "go:0006869",
      "go_axiom_term_name": "lipid transport",
      "target_kind": "metabolite",
      "metabolite_id": "kegg.compound:C01356",
      "metabolite_name": "Lipid",
      "metabolite_chebi_id": "18059"
    }
  ]
}
```

### Example 13: Route agreement per gene — urtA, urtB, urtE in MED4

```example-call
metabolites_by_gene(locus_tags=["PMM0970", "PMM0971", "PMM0974"], organism="Prochlorococcus MED4", summary=True)
```

*`by_evidence_source_combination` counts (gene, metabolite) pairs by the set of routes that name them: 6 pairs TCDB only, 3 TCDB and GO (urea, once per gene), 3 GO only. Per gene, `by_gene[].multi_source_metabolite_count` says how many of its metabolites two routes reach; per metabolite, `top_metabolites[].multi_source_gene_count` says how many genes. A GO-only pair is not wrong, and a TCDB + GO pair is corroborated, not proven (the two routes share homology).*

```example-response
{
  "total_matching": 22,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "warnings": [],
  "stereo_relatives": {},
  "resolved_aliases": {},
  "not_found": {
    "locus_tags": [],
    "organism": null,
    "metabolite_ids": [],
    "metabolite_pathway_ids": [],
    "metabolite_elements": []
  },
  "not_matched": [],
  "by_gene": [
    {
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "product": "ABC-type urea transporter, substrate binding component",
      "rows": 6,
      "metabolite_count": 3,
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 4,
      "tcdb_family_rows": 0,
      "go_transport_rows": 2,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0971",
      "gene_name": "urtB",
      "product": "ABC-type urea transporter, permease component",
      "rows": 7,
      "metabolite_count": 4,
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 4,
      "tcdb_family_rows": 0,
      "go_transport_rows": 3,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    },
    {
      "locus_tag": "PMM0974",
      "gene_name": "urtE",
      "product": "ABC-type urea transporter, ATPase component UrtE",
      "rows": 9,
      "metabolite_count": 5,
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 4,
      "tcdb_family_rows": 0,
      "go_transport_rows": 5,
      "multi_source_metabolite_count": 1,
      "tcdb_assignment_count": 2
    }
  ],
  "by_evidence_source": [{"evidence_source": "transport", "count": 12}, {"evidence_source": "go_transport", "count": 10}],
  "by_evidence_source_combination": [
    {"evidence_sources": ["transport"], "pair_count": 6},
    {"evidence_sources": ["go_transport"], "pair_count": 3},
    {"evidence_sources": ["go_transport", "transport"], "pair_count": 3}
  ],
  "by_tcdb_route": [{"tcdb_route": "direct", "count": 12}],
  "tcdb_family_substrates_not_shown": {"genes": 0, "metabolites": 0, "rows": 0},
  "tcdb_family_substrates_skipped": [],
  "rows_by_go_term_depth": [{"go_term_depth": 0, "count": 10}],
  "by_element": [
    {"element": "C", "metabolite_count": 4},
    {"element": "H", "metabolite_count": 4},
    {"element": "N", "metabolite_count": 4},
    {"element": "O", "metabolite_count": 3}
  ],
  "by_element_truncated": null,
  "top_metabolites": [
    {
      "metabolite_id": "kegg.compound:C00086",
      "name": "Urea",
      "formula": "CH4N2O",
      "gene_count": 3,
      "reaction_count": 0,
      "transporter_count": 2,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 6,
      "tcdb_family_rows": 0,
      "go_transport_rows": 7,
      "multi_source_gene_count": 3
    },
    {
      "metabolite_id": "kegg.compound:C07044",
      "name": "Hydroxyurea",
      "formula": "CH4N2O2",
      "gene_count": 3,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 3,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    },
    {
      "metabolite_id": "kegg.compound:C14415",
      "name": "Thiourea",
      "formula": "CH4N2S",
      "gene_count": 3,
      "reaction_count": 0,
      "transporter_count": 1,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 3,
      "tcdb_family_rows": 0,
      "go_transport_rows": 0,
      "multi_source_gene_count": 0
    },
    {
      "metabolite_id": "chebi:22918",
      "name": "branched-chain amino acid",
      "formula": null,
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_gene_count": 0
    },
    {
      "metabolite_id": "chebi:35238",
      "name": "amino-acid zwitterion",
      "formula": null,
      "gene_count": 1,
      "reaction_count": 0,
      "transporter_count": 0,
      "metabolism_rows": 0,
      "tcdb_direct_rows": 0,
      "tcdb_family_rows": 0,
      "go_transport_rows": 1,
      "multi_source_gene_count": 0
    },
    ...
  ],
  "top_reactions": [],
  "top_tcdb_families": [
    {
      "tcdb_family_id": "tcdb:3.A.1.4.4",
      "tcdb_family_name": "The high-affinity (<1 μM) urea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 3,
      "metabolite_count": 1
    },
    {
      "tcdb_family_id": "tcdb:3.A.1.4.5",
      "tcdb_family_name": "The high affinity urea/thiourea/hydroxyurea porter",
      "level_kind": "tc_system",
      "tcdb_route": "direct",
      "direction": "uptake",
      "gene_count": 3,
      "metabolite_count": 3
    }
  ],
  "top_gene_categories": [{"category": "Stress response and adaptation", "gene_count": 3}],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko00780",
      "metabolite_pathway_name": "Biotin metabolism",
      "gene_count": 3,
      "pathway_reaction_count": 18,
      "pathway_metabolite_count": 22
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00220",
      "metabolite_pathway_name": "Arginine biosynthesis",
      "gene_count": 3,
      "pathway_reaction_count": 26,
      "pathway_metabolite_count": 24
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00998",
      "metabolite_pathway_name": "Biosynthesis of various antibiotics",
      "gene_count": 3,
      "pathway_reaction_count": 5,
      "pathway_metabolite_count": 40
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00240",
      "metabolite_pathway_name": "Pyrimidine metabolism",
      "gene_count": 3,
      "pathway_reaction_count": 73,
      "pathway_metabolite_count": 57
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00330",
      "metabolite_pathway_name": "Arginine and proline metabolism",
      "gene_count": 3,
      "pathway_reaction_count": 61,
      "pathway_metabolite_count": 60
    },
    ...
  ],
  "top_metabolite_pathways_truncated": null,
  "no_formula_excluded": null,
  "no_formula_excluded_metabolites": null,
  "gene_count_total": 3,
  "reaction_count_total": 0,
  "transporter_count_total": 2,
  "metabolite_count_total": 6,
  "results": []
}
```

## Chaining patterns

```
differential_expression_by_gene(organism=..., direction='up') → metabolites_by_gene(locus_tags=DE_genes, organism=..., metabolite_elements=['N']) (Workflow A — N-source marquee)
genes_in_cluster(cluster_ids=...) → metabolites_by_gene(locus_tags=cluster_genes, organism=...) (Workflow C — cluster chemistry characterization)
genes_by_function(search_text=..., organism=...) → metabolites_by_gene(locus_tags=function_hit_genes, organism=...) (Workflow C variant — function-search chemistry)
gene_overview(locus_tags=[...]) → per-row reaction_count/catalyzed_metabolite_count > 0 → metabolites_by_gene(locus_tags=chemistry_genes, organism=...)
gene_overview(locus_tags=[...]) → per-row transported_metabolite_count > 0 → metabolites_by_gene(locus_tags=[...], organism=..., evidence_sources=['transport']) — distinct Metabolite targets in the direct rows equal transported_metabolite_count
gene_overview(locus_tags=[...]) → per-row tcdb_assignment_count > 0 but transported_metabolite_count = 0 → metabolites_by_gene(locus_tags=[...], organism=..., evidence_sources=['transport'], include_tcdb_family_substrates=True) for family-level substrate candidates
metabolites_by_gene → top_metabolites → list_metabolites(metabolite_ids=[top_metabolite_ids]) for richer per-metabolite cross-refs (mass, formula, full pathway names)
metabolites_by_gene → top_metabolites → list_metabolites(metabolite_ids=[top_metabolite_ids], organism_names=[partner_organism]) for cross-organism presence (cross-feeding seed)
metabolites_by_gene → top_metabolites → genes_by_metabolite(metabolite_ids=[top_metabolite_ids], organism=PARTNER_ORGANISM) (cross-feeding bridge — catalysts + transporters in partner)
metabolites_by_gene → stereo_relatives → genes_by_metabolite(metabolite_ids=[generic substrate id], organism=..., include_stereo_forms=True) to join this gene's generic-form transport with the specific form's catalysts
metabolites_by_gene → top_metabolite_pathways → list_metabolites(pathway_ids=[metabolite_pathway_id]) for the full metabolite roster of the pathway (not just gene-set hits)
metabolites_by_gene → top_metabolite_pathways → genes_by_ontology(ontology='kegg', term_ids=[metabolite_pathway_id], organism=...) for gene-KO-mediated pathway annotations (different surface — see top_metabolite_pathways naming disambiguation)
metabolites_by_gene → top_metabolite_pathways → pathway_enrichment(...) when gene-set hypothesis test is the goal
metabolites_by_gene → top_reactions → genes_by_ontology(ontology='ec', term_ids=[ec_number], organism=...) for genes in adjacent reactions
metabolites_by_gene → top_tcdb_families → genes_by_ontology(ontology='tcdb', term_ids=[tcdb_family_id], organism=...) for sibling genes in the same family
metabolites_by_gene → warning / tcdb_family_substrates_skipped → gene_ontology_terms(locus_tags=[...], ontology='tcdb', organism=...) to see every gated TCDB call the gene carries (add include_weak_tcdb_hits=True for its below-gate DIAMOND hits)
metabolites_by_gene → not_matched (locus_tags with no chemistry edges) → gene_overview(locus_tags=not_matched) for annotation context (most are richly-annotated non-chemistry genes — DNA gyrase, signaling, etc. — not annotation gaps)
gene_overview(locus_tags=[...]) → evidence_sources contains 'go_transport' → metabolites_by_gene(locus_tags=[...], organism=..., evidence_sources=['go_transport']) for the GO term and target behind the tag
metabolites_by_gene → go_transport rows with target_kind='chemical_role' → genes_by_metabolite(metabolite_ids=[role id], organism=...) for every gene that reaches the same role (siderophore, xenobiotic, drug, toxin, vitamin)
```

## Common mistakes

- Gene-anchored (locus_tags → metabolites). The metabolite-anchored mirror is `genes_by_metabolite` (metabolite → genes); both share the same row class, discriminators and per-arm filter scope.

- A transporter's substrates are usually the generic, stereo-unspecified node ('Cysteine'), because TCDB names them that way; the enzymes sit on the specific form ('L-Cysteine'). Stereo forms are separate nodes and no count combines across them, so don't conclude "no enzyme uses what this gene imports" from these rows. Read envelope `stereo_relatives` (keyed by result metabolite; counts cover the whole organism, not your input genes) and per-row `stereo_relative_ids`, then route to `genes_by_metabolite(..., include_stereo_forms=True)`. Class terms and ring vs open-chain forms are never linked, so no hint is not proof of no related compound.

- Single-organism enforced (mirrors `differential_expression_by_gene` and `genes_by_metabolite`). There is no `organisms` list. For cross-organism / cross-feeding work: call MBG once on the focal organism, take `top_metabolites`, then route to `genes_by_metabolite(metabolite_ids=[...], organism=partner)` (or `list_metabolites(metabolite_ids=[...], organism_names=[partner])` for presence-only).

- `'metabolomics'` is NOT accepted in `evidence_sources` here — the Pydantic Literal allows only `('metabolism', 'transport', 'go_transport')`. The metabolomics path (`MetaboliteAssay → Metabolite`) has no Gene anchor, so a metabolomics-only metabolite contributes no rows from this tool. For measurement evidence, use `list_metabolite_assays` / `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay`. Same divergence as `genes_by_metabolite`.

- Transport rows are direct by default, exactly as on `genes_by_metabolite`: one row per gene × TC system × metabolite, from the gene's `tcdb_gate='direct'` calls only. Rank within the route by `tcdb_identity` (percent; null on eggNOG-only rows, which is not weaker), then `tcdb_calls` (eggNOG plus a DIAMOND kind is independent agreement; the two DIAMOND kinds come from one run). Distinct direct Metabolite targets per gene equal `gene_overview.transported_metabolite_count` (cynD PMM0372: 3; role rows excluded), and metabolite-side distinct direct genes, unioned over organisms, equal `list_metabolites.transporter_gene_count`.

- An empty transport arm for a gene with a TCDB call has two readings, and the warning names which one applies. (1) The gene is placed only at family or subfamily level: pass `include_tcdb_family_substrates=True` for `tcdb_route='family'` rows (phnD PMM0673 → 5 metabolites via tcdb:3.A.1.9). (2) Its only usable call is on a node curated with over 200 substrates (ABC tcdb:3.A.1, MFS tcdb:2.A.1): it is listed in `tcdb_family_substrates_skipped` and its substrate is unknown. Genes with only weak DIAMOND hits (`below_gate`) reach no substrate here; `gene_ontology_terms(..., include_weak_tcdb_hits=True)` shows them.

- Family rows are a recall expansion. The walk starts from the gene's deepest `annotated` family or subfamily call, never above one of its own direct systems, and reports every curated substrate of the systems under it (`tcdb_substrate_system_count` systems per row). TCDB curation passes through as-is: catch-all substrates ("molecule", "Peptide", "Protein") appear, and pstS (PMM0710) reaches only triphosphate because TCDB curates its Pst system that way. Most remaining noise is eggNOG family calls on genes that are not transporters. `docs://analysis/transport`.

- Every result row has the same key set — cross-arm fields are explicitly `None` on rows from the other arm (metabolism rows have `tcdb_route`/`tcdb_calls`/`tcdb_identity`/`tcdb_direction`/`tcdb_family_id`/`tcdb_family_name` = None; transport rows have `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` = None). Use `row['tcdb_route']` (KeyError-free) rather than `row.get('tcdb_route')` if the difference matters.

- Reaction-arm rows are NOT directional — KG reactions carry neither a substrate-vs-product role on `Reaction_has_metabolite` nor an `is_reversible` flag. Read `evidence_source='metabolism'` rows as 'gene catalyses a reaction *involving* this metabolite,' never as 'produces X' / 'consumes Y' / 'reversibly interconverts'. The KG limitation is permanent (KEGG lacks both upstream).

- `metabolite_elements` never matches a metabolite with no formula (empty `elements`). These are mostly generic classes such as 'amino acid', 'dipeptide' or 'Polyamine', so an element filter can silently drop N-bearing transport substrates. When the filter is set, the envelope reports the loss: `no_formula_excluded` (rows) and `no_formula_excluded_metabolites` (distinct metabolites) that pass every other filter but have no formula, plus a `warnings` entry. Re-run without `metabolite_elements` to inspect them.

- `by_element` envelope is presence-only — count of distinct metabolites containing each element at all. NOT stoichiometric (atom counts live in `metabolite.formula`); NOT mass-balanced (KG `Reaction_has_metabolite` is undirected and carries no substrate/product role).

- There is no `top_genes` envelope field. The per-gene rollup IS `by_gene` (one entry per input locus_tag that produced at least one row; a gene with zero rows does not appear; it is listed in `not_matched`. Populated identically in summary and detail modes — `rows` / `metabolite_count` / `reaction_count` / `transporter_count` / `metabolism_rows` / `tcdb_direct_rows` / `tcdb_family_rows` / `tcdb_assignment_count`). The compound-anchored counterpart `top_metabolites` exists (sorted by gene_count); there's no symmetric `top_genes` because gene-anchored aggregation already lives in `by_gene`. Inspect the actual response shape before assuming a field — don't extrapolate from `genes_by_metabolite.top_genes` (different tool, different shape) or `top_*` patterns on other tools.

- `gene_categories` filter is partially redundant with `locus_tags` input (since the input already constrains the gene set). It's useful only as further narrowing within a broad batch — e.g. `locus_tags=DE_genes, gene_categories=['Transport and binding']` to slice DE chemistry to transport-classified genes only. Don't use it as the primary anchor.

- `ec_numbers` and `mass_balance` are metabolism-arm-only filters — they DO NOT suppress TCDB or GO transport rows, which pass through unchanged. To restrict to metabolism alone, combine with `evidence_sources=['metabolism']`. Symmetrically, `include_tcdb_family_substrates` widens TCDB transport rows only and `go_include_ancestors` the GO route only. Per-arm filter scope is predictable + composable; it is NOT soft-exclude. `metabolite_elements`, `metabolite_ids`, `metabolite_pathway_ids`, and `gene_categories` are the only filters that narrow all three arms uniformly.

- `top_metabolite_pathways` here means *KEGG pathways the gene set's chemistry reaches* (via `Reaction_in_kegg_pathway` + `Metabolite_in_pathway`). These are NOT the same as gene-KO-mediated pathway annotations (where pathway membership is asserted by the gene's KO assignment) — those live in `genes_by_ontology(ontology='kegg', term_ids=[...], organism=...)`. The two are distinct surfaces: chemistry-reach (this tool) vs KO-annotation (`genes_by_ontology`). For metabolic pathway analysis with a hypothesis test, use `pathway_enrichment` instead.

- `metabolite_elements` is presence-only AND-of (not formula substring). `['N']` keeps metabolites whose `Metabolite.elements` Hill-parsed list contains 'N'. `['N', 'P']` requires BOTH N and P. Never substring-match on `formula` — Hill notation has element-clash footguns: `'Cl'` contains `'C'`, `'Na'` contains `'N'`. Use the `metabolite_elements` filter, never grep `formula`.

- Use `summary=True` for batch DE inputs (50+ locus_tags). Detail rows can exceed 1,000 quickly once family rows are on; the envelope rollups (top_metabolites, top_metabolite_pathways, top_reactions, top_tcdb_families, by_element, by_gene, top_gene_categories) are the actually-useful artifact at that scale.

- `not_found.locus_tags` vs `not_matched`. `not_found.locus_tags` = locus_tags that don't resolve to any Gene in the requested organism (typo, wrong organism, gene removed in KG rebuild). `not_matched` = locus_tags that DO resolve to a Gene but have zero chemistry edges (no `Gene_catalyzes_reaction` AND no `Gene_has_tcdb_family`). Most MED4 genes fall into the `not_matched` bucket (roughly 1,170 of MED4's ~1,970 genes carry no chemistry edge) — most are richly-annotated non-chemistry genes (DNA gyrase, queG, signaling modules), not annotation gaps. Pivot via `gene_overview(locus_tags=not_matched)` for annotation context.

- When `top_metabolites` is dominated by ATP / ADP / NADH / NADPH / H2O, pass `exclude_metabolite_ids=[<kegg.compound:Cxxxxx>]` to strip the currency-cofactor noise. Set-difference semantics with `metabolite_ids` — exclude wins on overlap (silent). Per-arm scope: exclude applies on BOTH metabolism + transport arms (mirrors `metabolite_ids`). KG namespace is `kegg.compound:` (not `chebi:`).

- Direction is thin. TCDB rows carry `tcdb_direction` (`uptake` / `export` / `unknown`), which is TCDB's direction for the row's node (ABC numbering, or the nearest named node up to family level), not a per-gene call; most nodes read `unknown`. The metabolism arm's `Reaction_has_metabolite` edge does not distinguish substrate from product (KEGG equation order is arbitrary). To distinguish for a gene, layer transcriptional evidence (`differential_expression_by_gene`) and functional annotation (`gene_overview` Pfam / KEGG KO names like `*-synthase` vs `*-permease`).

```mistake
metabolites_by_gene(locus_tags=['PMM0673'], organism='MED4')  # 0 transport rows, then reporting phnD as 'no transporter'
```

```correction
metabolites_by_gene(locus_tags=['PMM0673'], organism='MED4', include_tcdb_family_substrates=True)  # after reading the warning; family rows are candidates, not calls
```

```mistake
metabolites_by_gene(metabolite_ids=['C00064'])  # then treating `C00064` in `not_found` as 'no such metabolite'
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
passed. Exclude-wins-on-overlap is computed on the canonical IDs, so currency-cofactor exclude lists in either form behave identically.

```

- See `docs://analysis/metabolites` for the 3 source pipelines decision tree (metabolism / transport / metabolomics) and how to read direct vs family TCDB rows, and `docs://guide/concepts` for the chemistry layer overview.

- `not_found.organism` is set when the `organism` name resolves to zero organisms — check it before reading an empty result as 'no chemistry here'.

- With `include_tcdb_family_substrates=True`, one gene on a broad family can fill `limit` on its own (family rows sort after direct rows): page with `offset`, or use `summary=True` and read `by_gene`.

- `evidence_sources` accepts `go_transport` here (and on `genes_by_metabolite`), alongside `metabolism` and `transport`. Default is all three. A `go_transport` row is a GO term definition, not a gene fact; whether the gene deserves the term is `go_sources` / `go_evidence`. Rows with `target_kind='chemical_role'` name a class (siderophore, xenobiotic, drug, toxin, vitamin), not a compound.

- BP is not a transporter call: a biological-process term (for example "iron ion transport") also covers storage and regulation, so a gene carrying it is not necessarily a transporter (MED4 `ftn` reaches iron this way). Check `go_namespace` and prefer molecular-function rows for "is this gene a transporter".

- An empty GO answer for H+, Na+ or an upper-level class is curation, not biology (`Schema_info.go_transport_excluded_targets`). `metabolite_elements` also drops role rows and formula-less classes from the GO arm, as it does formula-less metabolites elsewhere. The GO and TCDB routes are correlated (InterPro2GO and eggNOG share homology with the TCDB calls), so their agreement is weaker evidence than it reads: `docs://analysis/transport`.

- A multi-source pair is corroborated, not proven. `by_evidence_source_combination`, `by_gene[].multi_source_metabolite_count` and `top_metabolites[].multi_source_gene_count` count the (gene, metabolite) pairs that two or more routes name, but the routes share homology (InterPro2GO and eggNOG vs the TCDB calls), so agreement raises confidence without being independent confirmation. A single-source pair is not wrong.

- `go_namespace` and `go_evidence` narrow the GO arm only; KEGG and TCDB rows are untouched. Set while `evidence_sources` excludes `go_transport`, they are ignored with a warning. Use `go_namespace=['molecular_function']` for "is this gene a transporter".

## Package import equivalent

```python
from multiomics_explorer import metabolites_by_gene

result = metabolites_by_gene(locus_tags=..., organism=...)
# returns dict with keys: total_matching, returned, offset, truncated, warnings, stereo_relatives, resolved_aliases, not_found, not_matched, by_gene, by_evidence_source, by_evidence_source_combination, by_tcdb_route, tcdb_family_substrates_not_shown, tcdb_family_substrates_skipped, rows_by_go_term_depth, by_element, by_element_truncated, top_metabolites, top_reactions, top_tcdb_families, top_gene_categories, top_metabolite_pathways, top_metabolite_pathways_truncated, no_formula_excluded, no_formula_excluded_metabolites, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
