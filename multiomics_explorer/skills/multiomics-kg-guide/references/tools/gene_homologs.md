# gene_homologs

## What it does

Get ortholog group memberships for genes.

Returns which ortholog groups each gene belongs to, ordered from most
specific (curated) to broadest. Use for gene characterization and
cross-organism bridging. A gene typically belongs to 1-3 groups.

For member genes within a group, use genes_by_homolog_group.
For text search on group names, use search_homolog_groups.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| source | string \| None | None | Filter by OG source: 'cyanorak' or 'eggnog'. |
| taxonomic_level | string \| None | None | Filter by taxonomic level. E.g. 'curated', 'Prochloraceae', 'Bacteria'. |
| max_specificity_rank | int \| None | None | Cap group breadth. 0=curated only, 1=+family, 2=+order, 3=+domain (all). |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include group metadata: member_count, organism_count, genera, has_cross_genus_members, description, functional_description. |
| limit | int | 5 | Max results. |

## Response format

### Envelope

```expected-keys
total_matching, by_organism, by_source, returned, truncated, not_found, no_groups, results
```

- **total_matching** (int): Total gene×group rows matching filters
- **by_organism** (list[HomologOrganismBreakdown]): Gene×group counts per organism, sorted by count descending
- **by_source** (list[HomologSourceBreakdown]): Gene×group counts per source, sorted by count descending
- **returned** (int): Results in this response (0 when summary=true)
- **truncated** (bool): True if total_matching > returned
- **not_found** (list[string]): Input locus_tags not in KG
- **no_groups** (list[string]): Genes that exist but have zero matching ortholog groups

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4') |
| group_id | string | Prefixed ortholog group ID for chaining to genes_by_homolog_group (e.g. 'cyanorak:CK_00000364', 'eggnog:COG0592@2') |
| consensus_gene_name | string \| None (optional) | Consensus gene name across group members (e.g. 'dnaN'). Often null. |
| consensus_product | string \| None (optional) | Consensus product across group members (e.g. 'DNA polymerase III, beta subunit') |
| taxonomic_level | string | Taxonomic scope (e.g. 'curated', 'Prochloraceae', 'Bacteria') |
| source | string | Source database (e.g. 'cyanorak', 'eggnog') |
| specificity_rank | int | Group breadth: 0=curated, 1=family, 2=order, 3=domain (e.g. 0) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| member_count | int \| None (optional) | Total genes in group (e.g. 9) |
| organism_count | int \| None (optional) | Distinct organisms in group (e.g. 9) |
| genera | list[string] \| None (optional) | Genera represented (e.g. ['Prochlorococcus', 'Synechococcus']) |
| has_cross_genus_members | string \| None (optional) | 'cross_genus' or 'single_genus' |
| description | string \| None (optional) | Group description text |
| functional_description | string \| None (optional) | Functional annotation text |

## Few-shot examples

### Example 1: Look up ortholog groups for a gene

```example-call
gene_homologs(locus_tags=["PMM0001"])
```

```example-response
{
  "total_matching": 3,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 3}],
  "by_source": [{"source": "eggnog", "count": 2}, {"source": "cyanorak", "count": 1}],
  "returned": 3, "truncated": false, "not_found": [], "no_groups": [],
  "results": [
    {"locus_tag": "PMM0001", "organism_name": "Prochlorococcus MED4", "group_id": "cyanorak:CK_00000364", "consensus_gene_name": "dnaN", "consensus_product": "DNA polymerase III, beta subunit", "taxonomic_level": "curated", "source": "cyanorak", "specificity_rank": 0},
    {"locus_tag": "PMM0001", "organism_name": "Prochlorococcus MED4", "group_id": "eggnog:1MKTR@1212", ...},
    ...
  ]
}
```

### Example 2: Batch query for multiple genes

```example-call
gene_homologs(locus_tags=["PMM0001", "PMM0845", "ALT831_RS00180"])
```

### Example 3: Filter to cyanorak groups only

```example-call
gene_homologs(locus_tags=["PMM0001"], source="cyanorak")
```

### Example 4: Summary only (no individual rows)

```example-call
gene_homologs(locus_tags=["PMM0001", "PMM0845"], summary=True)
```

### Example 5: From resolve_gene to homologs

```
Step 1: resolve_gene(identifier="dnaN")
        → collect locus_tags from results

Step 2: gene_homologs(locus_tags=["PMM0001", "PMT9312_0001", ...])
        → see which ortholog groups each gene belongs to

Step 3: genes_by_homolog_group(group_ids=["cyanorak:CK_00000364"])
        → get all member genes in a group
```

## Chaining patterns

```
resolve_gene → gene_homologs → genes_by_homolog_group
search_homolog_groups → genes_by_homolog_group → gene_homologs
```

## Common mistakes

- A gene typically belongs to 1-3 groups: cyanorak curated (Pro/Syn only), eggNOG family, eggNOG Bacteria-level COG

- not_found means the gene doesn't exist in the KG; no_groups means the gene exists but has no ortholog group membership

- For member genes within a group, use genes_by_homolog_group (not this tool)

```mistake
gene_homologs(locus_tags='PMM0001')
```

```correction
gene_homologs(locus_tags=['PMM0001']) — always a list
```

## Package import equivalent

```python
from multiomics_explorer import gene_homologs

result = gene_homologs(locus_tags=...)
# returns dict with keys: total_matching, by_organism, by_source, not_found, no_groups, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
