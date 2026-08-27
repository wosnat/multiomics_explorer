# ontology_term_details

## What it does

Describe ontology terms in batch — identity, hierarchy (parents / children), gene reach and forward-only cross-ontology bridges, for any mix of the 17 ontologies.

Each row carries the term's name/description, `level` + `level_kind`,
`is_informative`, precomputed `gene_count` / `organism_count` /
`direct_gene_count`, the ontology's native columns (e.g. tcdb
`superfamily`, merops `catalytic_type`, interpro `interpro_type`;
absent props are stripped, not nulled), `parents[]`, `children[]`
(capped at 50, see `children_total`), and `links_out[]`.

Bridge-direction contract: `links_out` is forward-only. A
`composition` link means the source term is BUILT FROM the target
(TCDB family / MEROPS family -> Pfam domain, TCDB -> GO process);
a `membership` link means the source BELONGS TO the target (Pfam ->
InterPro entry, KEGG term -> BRITE category). A `router` link
(InterPro -> EC / CAZy) is a recall-biased cross-reference for
finding candidate terms — never use it to assign a gene a function;
verbose `router_ambiguous` flags InterPro entries whose router links
fan out or whose type is not FAMILY. Walk bridges only in the stored
direction.

IDs absent from the KG land in `not_found`. `organism` scopes
`genes_by_organism` and adds `organism_gene_count` per row.

Routing: `genes_by_ontology(term_ids=[...])` for the annotated genes;
`search_ontology` to find term IDs (browse or Lucene); target IDs in
`links_out` feed back into this tool for a bridge walk;
docs://ontologies/{key} for how each ontology is built and read.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| term_ids | list[string] | — | Self-prefixed term IDs, any ontology mix (e.g. 'go:0006979', 'tcdb:3.A.1', 'merops.family:S14', 'interpro:IPR000362', 'ncbifam:NF000812', 'pfam:PF00005', 'kegg.pathway:ko00010'). Rows return in input order. |
| organism | string \| None | None | Organism to scope genes_by_organism to (resolved like every other tool: 'MED4' -> 'Prochlorococcus MED4'; unknown/ambiguous raises). Rows gain organism_gene_count (subtree). Default: all organisms. |
| link_kinds | list[string ('composition', 'membership', 'router')] \| None | None | Keep only links_out of these kinds. 'composition' = term built from target (tcdb/merops -> pfam); 'membership' = term belongs to target (pfam -> interpro, kegg -> brite); 'router' = recall-biased cross-ref (interpro -> ec/cazy). Default: all. |
| verbose | bool | False | Add `properties` (every node prop), `links_out[].props` (curated_tcids, member_id_count, router_ambiguous) and `genes_by_organism`. Default compact. |
| limit | int | 50 | Max rows (found terms) to return. |
| offset | int | 0 | Number of found rows to skip for pagination. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, not_found, by_ontology, links_out_total, by_link_kind, warnings, results
```

- **total_matching** (int): Term IDs found in the KG (e.g. 5)
- **returned** (int): Rows in this response (after limit/offset)
- **offset** (int): Offset into the found rows
- **truncated** (bool): True if total_matching > offset + returned
- **not_found** (list[string]): Input term IDs with no node in the KG
- **by_ontology** (list[OntologyTermDetailsByOntology]): Found terms per ontology
- **links_out_total** (int): Total links_out entries across returned rows
- **by_link_kind** (list[OntologyTermDetailsByLinkKind]): links_out entries per link_kind
- **warnings** (list[string]): Auto-warnings (reserved for future use; always empty)

### Per-result fields

| Field | Type | Description |
|---|---|---|
| term_id | string | Term ID as given (e.g. 'tcdb:3.A.1') |
| ontology | string | Ontology key derived from the node label (e.g. 'tcdb'; PfamClan -> 'pfam'). See docs://ontologies/{key} for how to read this ontology. |
| label | string | Neo4j node label (e.g. 'TcdbFamily') |
| name | string \| None (optional) | Term name |
| description | string \| None (optional) | Term description / definition (null when the ontology has none) |
| level | int \| None (optional) | Hierarchy level (0 = broadest); null on flat ontologies |
| level_kind | string \| None (optional) | What `level` measures, e.g. 'depth', 'tc_family' |
| is_informative | bool \| None (optional) | True iff term is not flagged is_uninformative |
| gene_count | int \| None (optional) | Subtree gene count across all organisms (precomputed) |
| organism_count | int \| None (optional) | Distinct organisms reaching this term (precomputed) |
| direct_gene_count | int \| None (optional) | Genes annotated directly to this term, excluding descendants (sparse: hierarchical ontologies) |
| organism_gene_count | int \| None (optional) | Genes of `organism` in this term's SUBTREE (term + descendants; same scope as gene_count). Only when organism set. Differs from search_ontology.organism_gene_count (direct edge). |
| code | string \| None (optional) | Category code (sparse: cog_category, cyanorak_role, tigr_role) |
| short_name | string \| None (optional) | Pfam short name, e.g. 'ABC_tran' (sparse: pfam) |
| tree | string \| None (optional) | BRITE tree name (sparse: brite) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: brite) |
| tcdb_id | string \| None (optional) | Bare TC number, e.g. '3.A.1' (sparse: tcdb) |
| tc_class_id | string \| None (optional) | Parent TC class, e.g. '3.A' (sparse: tcdb) |
| member_count | int \| None (optional) | Child/member term count (sparse: tcdb, interpro, merops) |
| superfamily | string \| None (optional) | TCDB superfamily label (sparse: tcdb) |
| metabolite_count | int \| None (optional) | Distinct metabolites attached (sparse: tcdb substrates; KEGG pathway chemistry) |
| reaction_count | int \| None (optional) | Reactions mapped to this KEGG pathway (sparse: kegg pathway terms) |
| cazy_id | string \| None (optional) | CAZy family ID (sparse: cazy) |
| psortb_id | string \| None (optional) | PSORTb localization ID (sparse: subcellular_localization) |
| signalp_id | string \| None (optional) | SignalP type ID (sparse: signal_peptide_type) |
| interpro_id | string \| None (optional) | Bare InterPro accession (sparse: interpro) |
| interpro_type | string \| None (optional) | InterPro entry type, e.g. 'FAMILY', 'DOMAIN' (sparse: interpro) |
| ncbifam_id | string \| None (optional) | Bare NCBIfam accession (sparse: ncbifam) |
| family_type | string \| None (optional) | NCBIfam family type, e.g. 'equivalog' (sparse: ncbifam) |
| gene_symbol | string \| None (optional) | NCBIfam gene symbol (sparse: ncbifam) |
| merops_id | string \| None (optional) | Bare MEROPS family ID, e.g. 'S14' (sparse: merops) |
| family_class | string \| None (optional) | MEROPS family class ('peptidase' or 'inhibitor'; sparse: merops) |
| catalytic_type | string \| None (optional) | MEROPS catalytic type, e.g. 'serine', 'metallo' (sparse: merops) |
| peptidase_gene_count | int \| None (optional) | Genes with a 'peptidase' call on this family (sparse: merops) |
| peptidase_organism_count | int \| None (optional) | Organisms with a 'peptidase' call on this family (sparse: merops) |
| cleavage_summary | string \| None (optional) | MEROPS cleavage-specificity summary (sparse: merops) |
| cleavage_p1_residues | list[string] \| None (optional) | MEROPS preferred P1 residues (sparse: merops) |
| known_cleavage_count | int \| None (optional) | Known cleavage sites recorded for this family (sparse: merops) |
| parents | list[OntologyTermRef] (optional) | Direct parent terms ({id, name, level}); [] on roots / flat ontologies |
| children | list[OntologyTermRef] (optional) | Direct child terms ({id, name, level}), capped at 50 — see children_total |
| children_total | int (optional) | Total direct children (uncapped) |
| children_truncated | bool (optional) | True when children_total > len(children) |
| links_out | list[OntologyTermLink] (optional) | Forward-only cross-ontology bridges ({rel, link_kind, target_id, target_ontology, target_name}); filtered by link_kinds |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| properties | object \| None (optional) | Every node property (verbose only) |
| genes_by_organism | list[OntologyTermGenesByOrganism] \| None (optional) | Subtree gene count per organism (verbose only; scoped to `organism` when set) |

## Few-shot examples

### Example 1: A mixed batch across ontologies, including an unknown ID

```example-call
ontology_term_details(term_ids=["tcdb:3.A.1", "merops.family:S14", "interpro:IPR000362", "ncbifam:NF000812", "go:0006979", "bogus:xyz"])
```

```example-response
# Rows come back in input order; `bogus:xyz` lands in not_found.
# children[] is capped (children_total / children_truncated say how much
# was cut); links_out[] lists the forward bridges of each term.
{
  "total_matching": 5, "returned": 5, "offset": 0, "truncated": false,
  "not_found": ["bogus:xyz"],
  "by_ontology": [{"ontology": "tcdb", "count": 1}, {"ontology": "merops", "count": 1}, {"ontology": "interpro", "count": 1}, {"ontology": "ncbifam", "count": 1}, {"ontology": "go_bp", "count": 1}],
  "links_out_total": 135,
  "by_link_kind": [{"link_kind": "composition", "count": 130}, {"link_kind": "router", "count": 5}],
  "warnings": [],
  "results": [
    {"term_id": "tcdb:3.A.1", "ontology": "tcdb", "label": "TcdbFamily", "name": "ATP-binding Cassette (ABC) Superfamily",
     "level": 2, "level_kind": "tc_family", "is_informative": true, "gene_count": 4817, "organism_count": 42,
     "direct_gene_count": 3845, "tcdb_id": "3.A.1", "tc_class_id": "3", "member_count": 55, "superfamily": "ABC", "metabolite_count": 554,
     "parents": [{"id": "tcdb:3.A", "name": "P-P-bond-hydrolysis-driven transporters"}],
     "children": [{"id": "tcdb:3.A.1.1", "name": "Carbohydrate Uptake Transporter-1 (CUT1) Family"}, "..."],
     "children_total": 55, "children_truncated": true,
     "links_out": [{"rel": "Tcdb_family_has_pfam_domain", "link_kind": "composition", "target_id": "pfam:PF00005", "target_ontology": "pfam", "target_name": "ABC transporter"}, "..."]},
    {"term_id": "merops.family:S14", "ontology": "merops", "label": "MeropsFamily", "name": "Clp protease",
     "level": 1, "level_kind": "merops_family", "is_informative": true, "gene_count": 125, "organism_count": 41,
     "merops_id": "S14", "family_class": "peptidase", "catalytic_type": "serine", "peptidase_gene_count": 121,
     "parents": [{"id": "merops.clan:SK", "name": "SK"}], "children": [], "children_total": 0, "children_truncated": false,
     "links_out": [{"rel": "Merops_family_has_pfam_domain", "link_kind": "composition", "target_id": "pfam:PF00574", "target_ontology": "pfam", "target_name": "Clp protease"}]},
    {"term_id": "interpro:IPR000362", "ontology": "interpro", "interpro_type": "FAMILY", "children_total": 4,
     "links_out": [{"rel": "Interpro_entry_related_to_ec_number", "link_kind": "router", "target_id": "ec:4.3.1.1", "target_ontology": "ec", "target_name": "Aspartate ammonia-lyase"}, "..."]},
    {"term_id": "ncbifam:NF000812", "ontology": "ncbifam", "level": 0, "family_type": "equivalog", "parents": [], "children": [], "children_total": 0, "links_out": []},
    {"term_id": "go:0006979", "ontology": "go_bp", "name": "response to oxidative stress", "level": 3, "gene_count": 1050, "organism_count": 42, "direct_gene_count": 860,
     "parents": [{"id": "go:0006950", "name": "response to stress"}], "children_total": 3, "links_out": []}
  ]
}
```

### Example 2: Only the composition bridges of a transporter family

```example-call
ontology_term_details(term_ids=["tcdb:3.A.1"], link_kinds=["composition"])
```

```example-response
# link_kinds narrows links_out (and links_out_total / by_link_kind) to the
# requested kinds; hierarchy and counts are unchanged.
{"total_matching": 1, "links_out_total": 129, "by_link_kind": [{"link_kind": "composition", "count": 129}],
 "results": [{"term_id": "tcdb:3.A.1", "links_out": [{"rel": "Tcdb_family_has_pfam_domain", "link_kind": "composition", "target_id": "pfam:PF00005", "target_ontology": "pfam", "target_name": "ABC transporter"}, "..."]}]}
```

### Example 3: Verbose — every node property, link props, per-organism counts

```example-call
ontology_term_details(term_ids=["interpro:IPR000362"], verbose=True)
```

```example-response
# verbose adds `properties` (the whole node), `links_out[].props`
# (curated_tcids on TCDB links, member_id_count on MEROPS → Pfam,
# router_ambiguous on InterPro router links) and genes_by_organism[].
{"results": [
  {"term_id": "interpro:IPR000362", "ontology": "interpro", "interpro_type": "FAMILY",
   "properties": {"id": "interpro:IPR000362", "interpro_id": "IPR000362", "interpro_type": "FAMILY", "member_count": 4, "gene_count": 51, "...": "..."},
   "links_out": [{"rel": "Interpro_entry_related_to_ec_number", "link_kind": "router", "target_id": "ec:4.3.1.1", "target_ontology": "ec", "target_name": "Aspartate ammonia-lyase", "props": {"router_ambiguous": true}}, "..."],
   "genes_by_organism": [{"organism": "MED4", "gene_count": 1}, {"organism": "MIT1002", "gene_count": 2}, "..."]}
]}
```

### Example 4: Scope the per-organism count to one organism

```example-call
ontology_term_details(term_ids=["go:0006979", "tcdb:3.A.1"], organism="MED4", verbose=True)
```

```example-response
# With organism= set ('MED4' resolves to 'Prochlorococcus MED4'), compact
# rows gain organism_gene_count (SUBTREE count — search_ontology's
# organism_gene_count is the direct edge: 57 for tcdb:3.A.1) and the
# verbose genes_by_organism[] holds only that organism.
{"results": [
  {"term_id": "go:0006979", "gene_count": 1050, "organism_gene_count": 18, "genes_by_organism": [{"organism": "Prochlorococcus MED4", "gene_count": 18}]},
  {"term_id": "tcdb:3.A.1", "gene_count": 4817, "organism_gene_count": 65, "genes_by_organism": [{"organism": "Prochlorococcus MED4", "gene_count": 65}]}
]}
```

### Example 5: From an enrichment table to term context to genes

```
Step 1: pathway_enrichment(organism="MED4", experiment_ids=["EXP042"], ontology="tcdb", level=2)
        → term_ids of the enriched families (e.g. "tcdb:3.A.1")

Step 2: ontology_term_details(term_ids=["tcdb:3.A.1", "tcdb:2.A.1"])
        → parents / children / links_out (Pfam domains, GO terms) and
          gene_count vs member_count to judge how broad each family is

Step 3: genes_by_ontology(ontology="tcdb", organism="MED4", term_ids=["tcdb:3.A.1.1"])
        → the member genes of a child family picked from children[]
```

### Example 6: Two-hop bridge walk (tcdb → pfam → interpro)

```
Step 1: ontology_term_details(term_ids=["tcdb:3.A.1"], link_kinds=["composition"])
        → collect links_out[].target_id where target_ontology == "pfam"

Step 2: ontology_term_details(term_ids=["pfam:PF00005", "pfam:PF00664"], link_kinds=["membership"])
        → links_out[].target_id where target_ontology == "interpro"

Bridges are forward-only: each hop reads links_out on the *source* term.
Runnable version: docs://examples/ontology_terms.py --scenario bridge_walk
```

## Chaining patterns

```
search_ontology(ontology=[...]) → ontology_term_details(term_ids=[...]) — search or browse first, then inspect the hits' hierarchy and bridges
pathway_enrichment / cluster_enrichment → ontology_term_details(term_ids=[enriched term_ids]) — what is this enriched term, how broad, what is it built from
ontology_term_details → genes_by_ontology(ontology=<row.ontology>, term_ids=[child.id], organism=...) — pick a child from children[] and expand it to genes
ontology_term_details(link_kinds=['composition']) → ontology_term_details(term_ids=[links_out[].target_id]) — hop across bridges (tcdb → pfam → interpro)
gene_ontology_terms(locus_tags=[...]) → ontology_term_details(term_ids=[row.term_id]) — from a gene's terms to the terms' context
discussed_by_publication(publication_dois=[...]) → ontology_term_details(term_ids=[kegg.pathway ids]) — context for pathways a paper names
```

## Common mistakes

- Term IDs are self-prefixed CURIEs and the ontology is inferred from the node label — pass `go:0006979`, `tcdb:3.A.1`, `merops.family:S14`, `pfam:PF00005` / `pfam.clan:CL0023`, `kegg.pathway:ko00910`, `interpro:IPR000362`, `ncbifam:NF000812`, `ec:1.1.1.1`, `cazy:GT2`. There is no `ontology=` param; a bare accession without its prefix lands in `not_found`.

- `not_found` means no node with that ID exists in any registered ontology label. It is not a filter miss — `link_kinds` can empty `links_out` but never removes the row.

- `links_out` is forward-only (composition / membership / router from the source term). To find which TCDB families are built from a given Pfam domain you need the reverse direction, which this tool does not carry — see docs://analysis/annotation_evidence for the run_cypher form.

- `router` links (InterPro → EC / CAZy) are recall-biased cross-references. `router_ambiguous=True` (verbose) means the entry maps to several targets or is not a FAMILY-type entry. Never assign the target function to a gene from a router link — read the gene's own EC / CAZy edge.

- `children` is capped at 50 per term; read `children_total` / `children_truncated` and drill with `search_ontology(ontology=[...], level=<child level>)` or `genes_by_ontology(term_ids=[...])` (hierarchy expansion DOWN) for the full set.

- `gene_count` / `organism_count` are subtree-inclusive on hierarchical labels and direct on flat ones; `direct_gene_count` is node-local and absent (not null) on flat labels and on PfamClan / BriteCategory — see docs://ontologies/{ontology} for what each count means there.

- `member_count` (TCDB, MEROPS, InterPro) is the upstream database's family size, not a KG gene count.

- A compact column that is missing on the node is absent, not null: GO rows carry only `direct_gene_count` from their compact extras, Pfam rows `short_name`, KEGG `reaction_count` / `metabolite_count` only on pathway terms (absent on KO / module rows). Do not treat an absent key as `0`.

- `limit` / `offset` page the *found* rows (input order); `total_matching` counts found terms, not input IDs. There is no `summary` mode — batches are small by design (≤ 50 IDs per call is the comfortable range).

- `organism=` scopes `genes_by_organism` (verbose) and adds `organism_gene_count` to compact rows; it does not filter rows out — a term with zero genes in that organism still returns with `organism_gene_count: 0`. The name resolves like every other tool (`'MED4'` → `'Prochlorococcus MED4'`; unknown or ambiguous raises).

- `organism_gene_count` here is the SUBTREE count (term + descendants, same scope as `gene_count`). `search_ontology.organism_gene_count` is the term's DIRECT gene edge only — the two differ on hierarchical ontologies (`tcdb:3.A.1` in MED4: 65 here vs 57 in search_ontology). Do not compare them across tools.

```mistake
ontology_term_details(term_ids=['3.A.1'])  # bare TC number
```

```correction
ontology_term_details(term_ids=['tcdb:3.A.1'])  # self-prefixed CURIE
```

```mistake
ontology_term_details(term_ids=['tcdb:3.A.1'])  # expecting the member genes
```

```correction
genes_by_ontology(ontology='tcdb', term_ids=['tcdb:3.A.1'], organism='MED4')  # term → genes; ontology_term_details is term → hierarchy / bridges / counts
```

## Package import equivalent

```python
from multiomics_explorer import ontology_term_details

result = ontology_term_details(term_ids=...)
# returns dict with keys: total_matching, offset, not_found, by_ontology, links_out_total, by_link_kind, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
