# gene_details

## What it does

Get all properties for genes.

This is a deep-dive tool — use gene_overview for the common case.
Returns all Gene node properties including sparse fields
(catalytic_activities, transporter_classification, cazy_ids, etc.).

For organism taxonomy, use list_organisms. For homologs, use
gene_homologs. For ontology annotations, use gene_ontology_terms.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'sync_0001']. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_matching, returned, offset, truncated, not_found, results
```

- **total_matching** (int): Genes found from input locus_tags
- **returned** (int): Results in this response (0 when summary=true)
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > returned
- **not_found** (list[string]): Input locus_tags not in KG

## Few-shot examples

### Example 1: Full properties for a single gene

```example-call
gene_details(locus_tags=["PMM0001"])
```

```example-response
{
  "total_matching": 1,
  "returned": 1, "truncated": false, "not_found": [],
  "results": [
    {"locus_tag": "PMM0001", "gene_name": "dnaN", "product": "DNA polymerase III, beta subunit", "organism_name": "Prochlorococcus MED4", "gene_category": "DNA replication", "annotation_quality": 3, "ec_numbers": ["2.7.7.7"], "cog_categories": ["L"], "kegg_ids": ["K02338"], ...}
  ]
}
```

### Example 2: Batch deep-dive

```example-call
gene_details(locus_tags=["PMM0001", "ALT831_RS00180"])
```

### Example 3: Just check existence (summary only)

```example-call
gene_details(locus_tags=["PMM0001", "FAKE_GENE"], summary=True)
```

```example-response
{
  "total_matching": 1,
  "returned": 0, "truncated": true, "not_found": ["FAKE_GENE"],
  "results": []
}
```

### Example 4: From gene_overview to deep-dive

```
Step 1: gene_overview(locus_tags=["PMM0001", "PMM0845"])
        → see annotation_types, expression counts, ortholog summary

Step 2: gene_details(locus_tags=["PMM0001"])
        → inspect all properties including sparse fields
        (catalytic_activities, transporter_classification, cazy_ids, etc.)
```

## Chaining patterns

```
gene_overview → gene_details
resolve_gene → gene_details
genes_by_function → gene_details
```

## Common mistakes

- This returns ALL Gene node properties via g{.*} — for the common case, use gene_overview which returns curated fields

- Sparse fields (ec_numbers, cazy_ids, transporter_classification) are only present when the gene has them — check with gene_overview first

```mistake
gene_details(locus_tags='PMM0001')
```

```correction
gene_details(locus_tags=['PMM0001']) — always a list
```

## Package import equivalent

```python
from multiomics_explorer import gene_details

result = gene_details(locus_tags=...)
# returns dict with keys: total_matching, offset, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
