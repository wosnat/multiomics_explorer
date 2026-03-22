# KG change spec: resolve_gene

## Summary

No new KG changes needed. Documents existing KG dependencies.

## KG dependencies

### Nodes

| Node | Properties used | Notes |
|---|---|---|
| Gene | locus_tag, gene_name, product, organism_strain, all_identifiers | Identity resolution across multiple ID types |

### Indexes

- Gene nodes are matched via property equality (`locus_tag`, `gene_name`)
  and list containment (`all_identifiers`). No fulltext index — exact match.

### No changes needed

The Gene node schema already supports resolve_gene. The `all_identifiers`
list property contains old locus tags, RefSeq protein IDs, and other
cross-references populated by the KG build pipeline.
