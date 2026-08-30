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
InterPro entry, NCBIfam family -> InterPro entry, KEGG term -> BRITE
category). A `router` link (InterPro -> EC / CAZy; NCBIfam TIGR*
family -> TIGR role) is a recall-biased cross-reference for finding
candidate terms — never use it to assign a gene a function; verbose
`router_ambiguous` flags InterPro entries whose router links fan out
or whose type is not FAMILY. Walk bridges only in the stored
direction. TIGR roles (`tigr.role:`) are a 2-level hierarchy —
main roles at level 0 (slug ids), sub-roles at level 1 (numeric
ids) — so `parents[]` / `children[]` apply to them.

IDs absent from the KG land in `not_found`. `organism` scopes
`genes_by_organism` and adds `organism_gene_count` per row.

Routing: `genes_by_ontology(term_ids=[...])` for the annotated genes;
`search_ontology` to find term IDs (browse or Lucene); target IDs in
`links_out` feed back into this tool for a bridge walk;
docs://ontologies/{key} for how each ontology is built and read.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| term_ids | list[string] | — | Self-prefixed term IDs, any ontology mix (e.g. 'go:0006979', 'tcdb:3.A.1', 'interpro:IPR000362', 'pfam:PF00005', 'kegg.pathway:ko00010'). Rows return in input order. Bare ids accepted (e.g. 'ko00910', 'GO:0006979') — see `resolved_aliases`. |
| organism | string \| None | None | Organism to scope genes_by_organism to (resolved like every other tool: 'MED4' -> 'Prochlorococcus MED4'; unknown/ambiguous raises). Rows gain organism_gene_count (subtree). Default: all organisms. |
| link_kinds | list[string ('composition', 'membership', 'router')] \| None | None | Keep links_out of these kinds: 'composition' = built from target (tcdb/merops -> pfam); 'membership' = belongs to (pfam/ncbifam -> interpro, kegg -> brite); 'router' = recall-biased (interpro -> ec/cazy, ncbifam TIGR* -> tigr.role). Default all. |
| verbose | bool | False | Add `properties` (every node prop), `links_out[].props` (curated_tcids, member_id_count, router_ambiguous) and `genes_by_organism`. Default compact. |
| limit | int | 50 | Max rows (found terms) to return. |
| offset | int | 0 | Number of found rows to skip for pagination. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, not_found, by_ontology, links_out_total, by_link_kind, resolved_aliases, warnings, results
```

- **total_matching** (int): Term IDs found in the KG (e.g. 5)
- **returned** (int): Rows in this response (after limit/offset)
- **offset** (int): Offset into the found rows
- **truncated** (bool): True if total_matching > offset + returned
- **not_found** (list[string]): Input term IDs with no node in the KG
- **by_ontology** (list[OntologyTermDetailsByOntology]): Found terms per ontology
- **links_out_total** (int): Total links_out entries across returned rows
- **by_link_kind** (list[OntologyTermDetailsByLinkKind]): links_out entries per link_kind
- **resolved_aliases** (object): Bare term_ids (e.g. 'ko00910', 'GO:0006979') coerced to canonical CURIEs, {input: [canonical]}. Empty when none were coerced.
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
| organism_gene_count | int \| None (optional) | Genes of `organism` in this term's SUBTREE (term + descendants; same scope as gene_count and as search_ontology.organism_gene_count). Only when organism set. |
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
| cleavage_p1_residues | string \| list[string] \| None (optional) | MEROPS preferred P1 residues (sparse: merops) |
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
ontology_term_details(term_ids=["tcdb:3.A.1", "merops.family:S14", "interpro:IPR000362", "ncbifam:TIGR00254", "go:0006979", "bogus:xyz"])
```

*Rows come back in input order; `bogus:xyz` lands in not_found. children[] is capped (children_total / children_truncated say how much was cut); links_out[] lists the forward bridges of each term — here the NCBIfam family shows its InterPro membership link and its two TigrRole router links.*

```example-response
{
  "total_matching": 5,
  "returned": 5,
  "offset": 0,
  "truncated": false,
  "not_found": ["bogus:xyz"],
  "by_ontology": [
    {"ontology": "tcdb", "count": 1},
    {"ontology": "merops", "count": 1},
    {"ontology": "interpro", "count": 1},
    {"ontology": "ncbifam", "count": 1},
    {"ontology": "go_bp", "count": 1}
  ],
  "links_out_total": 138,
  "by_link_kind": [
    {"link_kind": "composition", "count": 130},
    {"link_kind": "router", "count": 7},
    {"link_kind": "membership", "count": 1}
  ],
  "warnings": [],
  "results": [
    {
      "term_id": "tcdb:3.A.1",
      "ontology": "tcdb",
      "label": "TcdbFamily",
      "name": "The ATP-binding Cassette (ABC) Superfamily",
      "description": null,
      "level": 2,
      "level_kind": "tc_family",
      "is_informative": true,
      "gene_count": 4900,
      "organism_count": 43,
      "direct_gene_count": 3910,
      "tcdb_id": "3.A.1",
      "tc_class_id": "tcdb:3",
      "member_count": 55,
      "superfamily": "ArsA ATPase (ArsA) Superfamily",
      "metabolite_count": 554,
      "parents": [{"id": "tcdb:3.A", "name": "P-P-bond-hydrolysis-driven transporters", "level": 1}],
      "children": [
        {"id": "tcdb:3.A.1.1", "name": "The Carbohydrate Uptake Transporter-1 (CUT1) Family", "level": 3},
        {"id": "tcdb:3.A.1.10", "name": "The Ferric Iron Uptake Transporter (FeT) Family", "level": 3},
        {"id": "tcdb:3.A.1.101", "name": "The Capsular Polysaccharide Exporter (CPSE) Family", "level": 3},
        {"id": "tcdb:3.A.1.103", "name": "The Lipopolysaccharide Exporter (LPSE) Family", "level": 3},
        {"id": "tcdb:3.A.1.105", "name": "The Drug Exporter-1 (DrugE1) Family", "level": 3},
        ...
      ],
      "children_total": 55,
      "children_truncated": true,
      "links_out": [
        {
          "rel": "Tcdb_family_located_in_cellular_component",
          "link_kind": "composition",
          "target_id": "go:0000139",
          "target_ontology": "go_cc",
          "target_name": "Golgi membrane"
        },
        {
          "rel": "Tcdb_family_located_in_cellular_component",
          "link_kind": "composition",
          "target_id": "go:0000324",
          "target_ontology": "go_cc",
          "target_name": "fungal-type vacuole"
        },
        {
          "rel": "Tcdb_family_located_in_cellular_component",
          "link_kind": "composition",
          "target_id": "go:0000329",
          "target_ontology": "go_cc",
          "target_name": "fungal-type vacuole membrane"
        },
        {
          "rel": "Tcdb_family_involved_in_biological_process",
          "link_kind": "composition",
          "target_id": "go:0002790",
          "target_ontology": "go_bp",
          "target_name": "peptide secretion"
        },
        {
          "rel": "Tcdb_family_enables_molecular_function",
          "link_kind": "composition",
          "target_id": "go:0004888",
          "target_ontology": "go_mf",
          "target_name": "transmembrane signaling receptor activity"
        },
        ...
      ]
    },
    {
      "term_id": "merops.family:S14",
      "ontology": "merops",
      "label": "MeropsFamily",
      "name": "ClpP endopeptidase",
      "description": null,
      "level": 1,
      "level_kind": "merops_family",
      "is_informative": true,
      "gene_count": 129,
      "organism_count": 42,
      "direct_gene_count": 129,
      "member_count": 0,
      "merops_id": "S14",
      "family_class": "peptidase",
      "catalytic_type": "serine",
      "peptidase_gene_count": 129,
      "peptidase_organism_count": 42,
      "cleavage_summary": "cleaves after Met (44%) / Leu (22%) / Gly (11%) - 27 known cleavages (0% physiological)",
      "cleavage_p1_residues": ["Met", "Leu", "Gly"],
      "known_cleavage_count": 27,
      "parents": [{"id": "merops.clan:SK", "name": "SK", "level": 0}],
      "children": [],
      "children_total": 0,
      "children_truncated": false,
      "links_out": [
        {
          "rel": "Merops_family_has_pfam_domain",
          "link_kind": "composition",
          "target_id": "pfam:PF00574",
          "target_ontology": "pfam",
          "target_name": "Clp protease"
        }
      ]
    },
    {
      "term_id": "interpro:IPR000362",
      "ontology": "interpro",
      "label": "InterproEntry",
      "name": "Fumarate lyase family",
      "description": "A number of enzymes, belonging to the lyase class, for which fumarate is a substrate, have been shown to share a shor...",
      "level": 0,
      "level_kind": null,
      "is_informative": true,
      "gene_count": 135,
      "organism_count": 43,
      "direct_gene_count": 135,
      "member_count": 4,
      "interpro_id": "IPR000362",
      "interpro_type": "FAMILY",
      "parents": [],
      "children": [
        {"id": "interpro:IPR004708", "name": "Aspartate ammonia-lyase", "level": 1},
        {"id": "interpro:IPR005677", "name": "Fumarate hydratase, class II", "level": 1},
        {"id": "interpro:IPR009049", "name": "Argininosuccinate lyase", "level": 1},
        {"id": "interpro:IPR012789", "name": "3-carboxy-cis,cis-muconate cycloisomerase-like", "level": 1}
      ],
      "children_total": 4,
      "children_truncated": false,
      "links_out": [
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:4.2.1.2",
          "target_ontology": "ec",
          "target_name": "fumarate hydratase"
        },
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:4.3.1.1",
          "target_ontology": "ec",
          "target_name": "aspartate ammonia-lyase"
        },
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:4.3.2.1",
          "target_ontology": "ec",
          "target_name": "argininosuccinate lyase"
        },
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:4.3.2.2",
          "target_ontology": "ec",
          "target_name": "adenylosuccinate lyase"
        },
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:5.5.1.2",
          "target_ontology": "ec",
          "target_name": "3-carboxy-cis,cis-muconate cycloisomerase"
        }
      ]
    },
    ...
  ]
}
```

### Example 2: A TIGR main role and its sub roles (tigr.role CURIE)

```example-call
ontology_term_details(term_ids=["tigr.role:energy_metabolism"])
```

*TigrRole is two-level: main roles use a slug CURIE (`tigr.role:energy_metabolism`, level 0, `level_kind='tigr_mainrole'`), sub roles a numeric one (`tigr.role:112`, level 1). Genes attach to sub roles only (`direct_gene_count` 0 on a main role; `gene_count` is the subtree). `ncbifam_family_count` counts the NCBIfam families whose router link points here — the NCBIfam → TigrRole bridge is recall-biased routing, not a gene-function call.*

```example-response
{
  "total_matching": 1,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "by_ontology": [{"ontology": "tigr_role", "count": 1}],
  "links_out_total": 0,
  "by_link_kind": [],
  "warnings": [],
  "results": [
    {
      "term_id": "tigr.role:energy_metabolism",
      "ontology": "tigr_role",
      "label": "TigrRole",
      "name": "Energy metabolism",
      "description": null,
      "level": 0,
      "level_kind": "tigr_mainrole",
      "is_informative": true,
      "gene_count": 7353,
      "organism_count": 43,
      "direct_gene_count": 0,
      "code": "energy_metabolism",
      "parents": [],
      "children": [
        {
          "id": "tigr.role:105",
          "name": "Energy metabolism / Biosynthesis and degradation of polysaccharides",
          "level": 1
        },
        {"id": "tigr.role:108", "name": "Energy metabolism / Aerobic", "level": 1},
        {"id": "tigr.role:109", "name": "Energy metabolism / Amino acids and amines", "level": 1},
        {"id": "tigr.role:110", "name": "Energy metabolism / Anaerobic", "level": 1},
        {
          "id": "tigr.role:111",
          "name": "Energy metabolism / ATP-proton motive force interconversion",
          "level": 1
        },
        ...
      ],
      "children_total": 16,
      "children_truncated": false,
      "links_out": []
    }
  ]
}
```

### Example 3: Only the composition bridges of a transporter family

```example-call
ontology_term_details(term_ids=["tcdb:3.A.1"], link_kinds=["composition"])
```

```example-response
{
  "total_matching": 1,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "by_ontology": [{"ontology": "tcdb", "count": 1}],
  "links_out_total": 129,
  "by_link_kind": [{"link_kind": "composition", "count": 129}],
  "warnings": [],
  "results": [
    {
      "term_id": "tcdb:3.A.1",
      "ontology": "tcdb",
      "label": "TcdbFamily",
      "name": "The ATP-binding Cassette (ABC) Superfamily",
      "description": null,
      "level": 2,
      "level_kind": "tc_family",
      "is_informative": true,
      "gene_count": 4900,
      "organism_count": 43,
      "direct_gene_count": 3910,
      "tcdb_id": "3.A.1",
      "tc_class_id": "tcdb:3",
      "member_count": 55,
      "superfamily": "ArsA ATPase (ArsA) Superfamily",
      "metabolite_count": 554,
      "parents": [{"id": "tcdb:3.A", "name": "P-P-bond-hydrolysis-driven transporters", "level": 1}],
      "children": [
        {"id": "tcdb:3.A.1.1", "name": "The Carbohydrate Uptake Transporter-1 (CUT1) Family", "level": 3},
        {"id": "tcdb:3.A.1.10", "name": "The Ferric Iron Uptake Transporter (FeT) Family", "level": 3},
        {"id": "tcdb:3.A.1.101", "name": "The Capsular Polysaccharide Exporter (CPSE) Family", "level": 3},
        {"id": "tcdb:3.A.1.103", "name": "The Lipopolysaccharide Exporter (LPSE) Family", "level": 3},
        {"id": "tcdb:3.A.1.105", "name": "The Drug Exporter-1 (DrugE1) Family", "level": 3},
        ...
      ],
      "children_total": 55,
      "children_truncated": true,
      "links_out": [
        {
          "rel": "Tcdb_family_located_in_cellular_component",
          "link_kind": "composition",
          "target_id": "go:0000139",
          "target_ontology": "go_cc",
          "target_name": "Golgi membrane"
        },
        {
          "rel": "Tcdb_family_located_in_cellular_component",
          "link_kind": "composition",
          "target_id": "go:0000324",
          "target_ontology": "go_cc",
          "target_name": "fungal-type vacuole"
        },
        {
          "rel": "Tcdb_family_located_in_cellular_component",
          "link_kind": "composition",
          "target_id": "go:0000329",
          "target_ontology": "go_cc",
          "target_name": "fungal-type vacuole membrane"
        },
        {
          "rel": "Tcdb_family_involved_in_biological_process",
          "link_kind": "composition",
          "target_id": "go:0002790",
          "target_ontology": "go_bp",
          "target_name": "peptide secretion"
        },
        {
          "rel": "Tcdb_family_enables_molecular_function",
          "link_kind": "composition",
          "target_id": "go:0004888",
          "target_ontology": "go_mf",
          "target_name": "transmembrane signaling receptor activity"
        },
        ...
      ]
    }
  ]
}
```

### Example 4: Verbose — every node property, link props, per-organism counts

```example-call
ontology_term_details(term_ids=["interpro:IPR000362"], verbose=True)
```

```example-response
{
  "total_matching": 1,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "by_ontology": [{"ontology": "interpro", "count": 1}],
  "links_out_total": 5,
  "by_link_kind": [{"link_kind": "router", "count": 5}],
  "warnings": [],
  "results": [
    {
      "term_id": "interpro:IPR000362",
      "ontology": "interpro",
      "label": "InterproEntry",
      "name": "Fumarate lyase family",
      "description": "A number of enzymes, belonging to the lyase class, for which fumarate is a substrate, have been shown to share a shor...",
      "level": 0,
      "level_kind": null,
      "is_informative": true,
      "gene_count": 135,
      "organism_count": 43,
      "direct_gene_count": 135,
      "member_count": 4,
      "interpro_id": "IPR000362",
      "interpro_type": "FAMILY",
      "parents": [],
      "children": [
        {"id": "interpro:IPR004708", "name": "Aspartate ammonia-lyase", "level": 1},
        {"id": "interpro:IPR005677", "name": "Fumarate hydratase, class II", "level": 1},
        {"id": "interpro:IPR009049", "name": "Argininosuccinate lyase", "level": 1},
        {"id": "interpro:IPR012789", "name": "3-carboxy-cis,cis-muconate cycloisomerase-like", "level": 1}
      ],
      "children_total": 4,
      "children_truncated": false,
      "links_out": [
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:4.2.1.2",
          "target_ontology": "ec",
          "target_name": "fumarate hydratase",
          "props": {"id": "IPR000362-related_ec-4.2.1.2", "router_ambiguous": true}
        },
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:4.3.1.1",
          "target_ontology": "ec",
          "target_name": "aspartate ammonia-lyase",
          "props": {"id": "IPR000362-related_ec-4.3.1.1", "router_ambiguous": true}
        },
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:4.3.2.1",
          "target_ontology": "ec",
          "target_name": "argininosuccinate lyase",
          "props": {"id": "IPR000362-related_ec-4.3.2.1", "router_ambiguous": true}
        },
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:4.3.2.2",
          "target_ontology": "ec",
          "target_name": "adenylosuccinate lyase",
          "props": {"id": "IPR000362-related_ec-4.3.2.2", "router_ambiguous": true}
        },
        {
          "rel": "Interpro_entry_related_to_ec_number",
          "link_kind": "router",
          "target_id": "ec:5.5.1.2",
          "target_ontology": "ec",
          "target_name": "3-carboxy-cis,cis-muconate cycloisomerase",
          "props": {"id": "IPR000362-related_ec-5.5.1.2", "router_ambiguous": true}
        }
      ],
      "properties": {
        "id": "interpro:IPR000362",
        "level": 0,
        "gene_count": 135,
        "member_count": 4,
        "organism_count": 43,
        "direct_gene_count": 135,
        "description": "A number of enzymes, belonging to the lyase class, for which fumarate is a substrate, have been shown to share a shor...",
        "name": "Fumarate lyase family",
        "interpro_id": "IPR000362",
        "interpro_type": "FAMILY",
        "preferred_id": "interpro"
      },
      "genes_by_organism": [
        {"organism": "Pseudomonas putida KT2440", "gene_count": 6},
        {"organism": "Meiothermus ruber", "gene_count": 5},
        {"organism": "Ruegeria pomeroyi DSS-3", "gene_count": 5},
        {"organism": "Alteromonas macleodii AD45", "gene_count": 3},
        {"organism": "Alteromonas macleodii ATCC27126", "gene_count": 3},
        ...
      ]
    }
  ]
}
```

### Example 5: Scope the per-organism count to one organism

```example-call
ontology_term_details(term_ids=["go:0006979", "tcdb:3.A.1"], organism="MED4", verbose=True)
```

*With organism= set ('MED4' resolves to 'Prochlorococcus MED4'), compact rows gain organism_gene_count (subtree count, term + descendants — the same number search_ontology(organism=...) shows: 65 for tcdb:3.A.1 on both tools) and the verbose genes_by_organism[] holds only that organism.*

```example-response
{
  "total_matching": 2,
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "by_ontology": [{"ontology": "go_bp", "count": 1}, {"ontology": "tcdb", "count": 1}],
  "links_out_total": 129,
  "by_link_kind": [{"link_kind": "composition", "count": 129}],
  "warnings": [],
  "results": [
    {
      "term_id": "go:0006979",
      "ontology": "go_bp",
      "label": "BiologicalProcess",
      "name": "response to oxidative stress",
      "description": null,
      "level": 3,
      "level_kind": null,
      "is_informative": true,
      "gene_count": 1067,
      "organism_count": 43,
      "direct_gene_count": 875,
      "organism_gene_count": 18,
      "parents": [{"id": "go:0006950", "name": "response to stress", "level": 2}],
      "children": [
        {"id": "go:0000302", "name": "response to reactive oxygen species", "level": 4},
        {"id": "go:0033194", "name": "response to hydroperoxide", "level": 4},
        {"id": "go:0034599", "name": "cellular response to oxidative stress", "level": 4}
      ],
      "children_total": 3,
      "children_truncated": false,
      "links_out": [],
      "properties": {
        "id": "go:0006979",
        "level": 3,
        "gene_count": 1067,
        "organism_count": 43,
        "direct_gene_count": 875,
        "name": "response to oxidative stress",
        "preferred_id": "go"
      },
      "genes_by_organism": [{"organism": "Prochlorococcus MED4", "gene_count": 18}]
    },
    {
      "term_id": "tcdb:3.A.1",
      "ontology": "tcdb",
      "label": "TcdbFamily",
      "name": "The ATP-binding Cassette (ABC) Superfamily",
      "description": null,
      "level": 2,
      "level_kind": "tc_family",
      "is_informative": true,
      "gene_count": 4900,
      "organism_count": 43,
      "direct_gene_count": 3910,
      "organism_gene_count": 65,
      "tcdb_id": "3.A.1",
      "tc_class_id": "tcdb:3",
      "member_count": 55,
      "superfamily": "ArsA ATPase (ArsA) Superfamily",
      "metabolite_count": 554,
      "parents": [{"id": "tcdb:3.A", "name": "P-P-bond-hydrolysis-driven transporters", "level": 1}],
      "children": [
        {"id": "tcdb:3.A.1.1", "name": "The Carbohydrate Uptake Transporter-1 (CUT1) Family", "level": 3},
        {"id": "tcdb:3.A.1.10", "name": "The Ferric Iron Uptake Transporter (FeT) Family", "level": 3},
        {"id": "tcdb:3.A.1.101", "name": "The Capsular Polysaccharide Exporter (CPSE) Family", "level": 3},
        {"id": "tcdb:3.A.1.103", "name": "The Lipopolysaccharide Exporter (LPSE) Family", "level": 3},
        {"id": "tcdb:3.A.1.105", "name": "The Drug Exporter-1 (DrugE1) Family", "level": 3},
        ...
      ],
      "children_total": 55,
      "children_truncated": true,
      "links_out": [
        {
          "rel": "Tcdb_family_located_in_cellular_component",
          "link_kind": "composition",
          "target_id": "go:0000139",
          "target_ontology": "go_cc",
          "target_name": "Golgi membrane",
          "props": {
            "id": "3.A.1-has_go-GO:0000139",
            "curated_tcids": ["3.A.1.201.13", "3.A.1.201.50", "3.A.1.204.12", "3.A.1.211.10", "3.A.1.211.9"]
          }
        },
        {
          "rel": "Tcdb_family_located_in_cellular_component",
          "link_kind": "composition",
          "target_id": "go:0000324",
          "target_ontology": "go_cc",
          "target_name": "fungal-type vacuole",
          "props": {"id": "3.A.1-has_go-GO:0000324", "curated_tcids": ["3.A.1.208.12"]}
        },
        {
          "rel": "Tcdb_family_located_in_cellular_component",
          "link_kind": "composition",
          "target_id": "go:0000329",
          "target_ontology": "go_cc",
          "target_name": "fungal-type vacuole membrane",
          "props": {"id": "3.A.1-has_go-GO:0000329", "curated_tcids": ["3.A.1.208.16", "3.A.1.208.18", "3.A.1.210.2"]}
        },
        {
          "rel": "Tcdb_family_involved_in_biological_process",
          "link_kind": "composition",
          "target_id": "go:0002790",
          "target_ontology": "go_bp",
          "target_name": "peptide secretion",
          "props": {"id": "3.A.1-has_go-GO:0002790", "curated_tcids": ["3.A.1.211.1"]}
        },
        {
          "rel": "Tcdb_family_enables_molecular_function",
          "link_kind": "composition",
          "target_id": "go:0004888",
          "target_ontology": "go_mf",
          "target_name": "transmembrane signaling receptor activity",
          "props": {"id": "3.A.1-has_go-GO:0004888", "curated_tcids": ["3.A.1.204.1"]}
        },
        ...
      ],
      "properties": {
        "level_kind": "tc_family",
        "tcdb_id": "3.A.1",
        "gene_count": 4900,
        "member_count": 55,
        "direct_gene_count": 3910,
        "superfamily": "ArsA ATPase (ArsA) Superfamily",
        "preferred_id": "tcdb",
        "id": "tcdb:3.A.1",
        "tc_class_id": "tcdb:3",
        "level": 2,
        "organism_count": 43,
        "name": "The ATP-binding Cassette (ABC) Superfamily",
        "metabolite_count": 554
      },
      "genes_by_organism": [{"organism": "Prochlorococcus MED4", "gene_count": 65}]
    }
  ]
}
```

### Example 6: From an enrichment table to term context to genes

```
Step 1: pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="tcdb", level=2)
        → term_ids of the enriched families (e.g. "tcdb:3.A.1")

Step 2: ontology_term_details(term_ids=["tcdb:3.A.1", "tcdb:2.A.1"])
        → parents / children / links_out (Pfam domains, GO terms) and
          gene_count vs member_count to judge how broad each family is

Step 3: genes_by_ontology(ontology="tcdb", organism="MED4", term_ids=["tcdb:3.A.1.1"])
        → the member genes of a child family picked from children[]
```

### Example 7: Three-hop bridge walk (tcdb → pfam → interpro) and the NCBIfam → TIGR role router

```
Step 1: ontology_term_details(term_ids=["tcdb:3.A.1"], link_kinds=["composition"])
        → collect links_out[].target_id where target_ontology == "pfam"

Step 2: ontology_term_details(term_ids=["pfam:PF00005", "pfam:PF00664"], link_kinds=["membership"])
        → links_out[].target_id where target_ontology == "interpro"

Step 3: ontology_term_details(term_ids=["ncbifam:TIGR00254"], link_kinds=["router"])
        → links_out[].target_id of kind "router" are TigrRole sub roles
          (tigr.role:264, tigr.role:710); drop link_kinds to also see
          the membership link into interpro:IPR000160

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

- Term IDs are self-prefixed CURIEs and the ontology is inferred from the node label — pass `go:0006979`, `tcdb:3.A.1`, `merops.family:S14`, `pfam:PF00005` / `pfam.clan:CL0023`, `kegg.pathway:ko00910`, `kegg.orthology:K02338`, `interpro:IPR000362`, `ncbifam:TIGR00254` / `ncbifam:NF006762`, `tigr.role:energy_metabolism` (main role) / `tigr.role:112` (sub role), `ec:1.1.1.1`, `cazy:GT2`. There is no `ontology=` param; a bare accession without its prefix lands in `not_found`.

- `not_found` means no node with that ID exists in any registered ontology label. It is not a filter miss — `link_kinds` can empty `links_out` but never removes the row.

- `links_out` is forward-only (composition / membership / router from the source term). To find which TCDB families are built from a given Pfam domain you need the reverse direction, which this tool does not carry — see docs://analysis/annotation_evidence for the run_cypher form.

- `router` links are recall-biased cross-references: InterPro → EC / CAZy (`Interpro_entry_related_to_*`) and NCBIfam → TigrRole (`Ncbifam_family_has_tigr_role`, targets like `tigr.role:264`). `router_ambiguous=True` (verbose, InterPro only) means the entry maps to several targets or is not a FAMILY-type entry. Never assign the target function to a gene from a router link — read the gene's own EC / CAZy / TIGR-role edge. NCBIfam → InterPro (`Ncbifam_family_in_interpro_entry`) is a `membership` link, not a router.

- `children` is capped at 50 per term; read `children_total` / `children_truncated` and drill with `search_ontology(ontology=[...], level=<child level>)` or `genes_by_ontology(term_ids=[...])` (hierarchy expansion DOWN) for the full set.

- `gene_count` / `organism_count` are subtree-inclusive on hierarchical labels and direct on flat ones; `direct_gene_count` is node-local and absent (not null) on flat labels and on PfamClan / BriteCategory — see docs://ontologies/{ontology} for what each count means there.

- `member_count` (TCDB, MEROPS, InterPro) is the upstream database's family size, not a KG gene count.

- A compact column that is missing on the node is absent, not null: GO rows carry only `direct_gene_count` from their compact extras, Pfam rows `short_name`, KEGG `reaction_count` / `metabolite_count` only on pathway terms (absent on KO / module rows). Do not treat an absent key as `0`.

- `limit` / `offset` page the *found* rows (input order); `total_matching` counts found terms, not input IDs. Default `limit=50`: a batch with more than 50 found IDs comes back `truncated: true` with the first 50 — pass `limit=None` (or a larger limit) or page with `offset`; `not_found` is always complete regardless of paging. There is no `summary` mode.

- Link rows have two shapes. Compact: `{rel, link_kind, target_id, target_ontology, target_name}`. `verbose=True` adds `props` per link (`curated_tcids` on TCDB → Pfam, `member_id_count` on MEROPS → Pfam, `router_ambiguous` on InterPro routers; plain `id` elsewhere) plus `properties` (the whole node) and `genes_by_organism[]` on the row. `link_kinds` filters links in both shapes.

- `organism=` scopes `genes_by_organism` (verbose) and adds `organism_gene_count` to compact rows; it does not filter rows out — a term with zero genes in that organism still returns with `organism_gene_count: 0`. The name resolves like every other tool (`'MED4'` → `'Prochlorococcus MED4'`; unknown or ambiguous raises).

- `organism_gene_count` is the subtree count (term + descendants, same scope as `gene_count`), identical to `search_ontology(organism=...).organism_gene_count` (`tcdb:3.A.1` in MED4: 65 on both). The node-local number is `direct_gene_count` (hierarchical labels only).

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
# returns dict with keys: total_matching, returned, offset, truncated, not_found, by_ontology, links_out_total, by_link_kind, resolved_aliases, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
