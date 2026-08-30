# resolve_gene

## What it does

Resolve a gene identifier (locus_tag, gene name, old locus_tag, or RefSeq protein ID) to matching Gene nodes. Matching is case-insensitive.

Routing: feed returned `locus_tag`s into `gene_overview` (data-availability triage), `gene_details` (full properties), `gene_homologs`, or `gene_ontology_terms`. The optional `organism` filter is a word-based, case-insensitive match on preferred_name + name_synonyms ('MED4' works; a genus word matches every strain).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| identifier | string | — | Gene identifier (case-insensitive) — locus_tag (e.g. 'PMM0001'), gene name (e.g. 'dnaN'), old locus tag, or RefSeq protein ID. |
| organism | string \| None | None | Organism: word-based, case-insensitive match on preferred_name + name_synonyms ('MED4' works; a genus word like 'Alteromonas' matches every strain). E.g. 'MED4', 'Prochlorococcus MED4'. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |
| summary | bool | False | Envelope only: results=[], by_organism uncapped. Use first when a name may hit many strains. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, by_organism, returned, offset, truncated, results
```

- **total_matching** (int): Total genes matching identifier + organism filter.
- **by_organism** (list[ResolveOrganismBreakdown]): Match counts per organism, sorted desc.
- **by_organism_truncated** (bool | None): True when the list was capped at 10 on a detail call — pass summary=True for the full breakdown, or organism= to narrow.
- **returned** (int): Genes in this response (0 when summary=True).
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if total_matching > returned.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN') |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III, beta subunit') |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4') |

## Few-shot examples

### Example 1: Resolve by locus_tag

```example-call
resolve_gene(identifier="PMM0001")
```

```example-response
{
  "total_matching": 1,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
  "by_organism_truncated": null,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "results": [
    {
      "locus_tag": "PMM0001",
      "gene_name": "dnaN",
      "product": "DNA polymerase III, beta subunit",
      "organism_name": "Prochlorococcus MED4"
    }
  ]
}
```

### Example 2: Resolve gene name across organisms

```example-call
resolve_gene(identifier="dnaN")
```

```example-response
{
  "total_matching": 43,
  "by_organism": [
    {"organism_name": "Alteromonas (MarRef v6)", "count": 1},
    {"organism_name": "Alteromonas macleodii AD45", "count": 1},
    {"organism_name": "Alteromonas macleodii ATCC27126", "count": 1},
    {"organism_name": "Alteromonas macleodii BGP6", "count": 1},
    {"organism_name": "Alteromonas macleodii BS11", "count": 1},
    ...
  ],
  "by_organism_truncated": true,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "results": [
    {
      "locus_tag": "DEH24_01275",
      "gene_name": "dnaN",
      "product": "DNA polymerase III subunit beta",
      "organism_name": "Alteromonas (MarRef v6)"
    },
    {
      "locus_tag": "AMBAS45_00010",
      "gene_name": "dnaN",
      "product": "DNA polymerase III subunit beta",
      "organism_name": "Alteromonas macleodii AD45"
    },
    {
      "locus_tag": "MASE_00010",
      "gene_name": "dnaN",
      "product": "DNA polymerase III subunit beta",
      "organism_name": "Alteromonas macleodii ATCC27126"
    },
    ...
  ]
}
```

### Example 3: Scoped to one organism

```example-call
resolve_gene(identifier="dnaN", organism="MED4")
```

### Example 4: Chain to gene overview

```
Step 1: resolve_gene(identifier="psbA")
        → collect locus_tags from results

Step 2: gene_overview(locus_tags=["PMM0223", "PMT9312_0225", ...])
        → compare function and data availability across organisms
        (PMM0223 / PMT9312_0225 are the MED4 / MIT9312 psbA copies;
        psbA is multi-copy in many strains, so expect several rows per organism)
```

## Chaining patterns

```
resolve_gene → gene_overview → gene_homologs
resolve_gene → gene_details
resolve_gene → gene_ontology_terms
```

## Common mistakes

- Sibling tools: resolve_gene answers 'which node is this identifier?' (locus_tag / gene_name / alias → gene rows, no annotation payload). For 'what do I know about this gene' use gene_overview(locus_tags=[...]); for 'which genes do X' use genes_by_function(search_text=...).

- Case-insensitive matching: 'pmm0001', 'PMM0001', and 'Pmm0001' all work

- The organism filter is a word-based, case-insensitive match on preferred_name + name_synonyms — 'MED4' works, as does 'Prochlorococcus MED4'. A genus word alone ('Prochlorococcus') matches every strain of that genus — here that just widens the result set (this tool never raises on ambiguity; the single-organism expression tools do).

- Two OrganismTaxon nodes share the name 'Meiothermus ruber' (a genome strain and a gene-less treatment taxon). organism='Meiothermus ruber' only ever returns genes of the genome strain — the treatment taxon has none — so the duplicate is harmless here, but do not use the name as a join key across list_organisms rows.

- not_found is not reported — an identifier with no match simply yields total_matching=0 and results=[]. See docs://guide/conventions for the not_found / not_matched shapes on batch tools.

```mistake
genes_by_function(search_text='PMM0001')  # wrong tool for ID lookup
```

```correction
resolve_gene(identifier='PMM0001')  # exact identity resolution
```

## Package import equivalent

```python
from multiomics_explorer import resolve_gene

result = resolve_gene(identifier=...)
# returns dict with keys: total_matching, by_organism, by_organism_truncated, returned, offset, truncated, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
