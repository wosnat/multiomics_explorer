# gene_neighbors

## What it does

Genes flanking each anchor on the same contig and organism, with strand and intergenic gap — positional adjacency only, never co-expression.

Use for operon or synteny reasoning; for co-regulation use `differential_expression_by_gene`, for the anchor's own annotations `gene_overview`.
Filters: locus_tags, window, max_bp_distance, same_strand.
Returns: anchors, by_organism, not_found, not_matched (anchor lacks coordinates); one row = one neighbor with rank_offset, bp_gap, same_strand.
docs://tools/gene_neighbors; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Anchor gene locus tags. Cross-organism OK. E.g. ['ACZ81_08860']. |
| window | int | 5 | Number of genes upstream AND downstream on the same contig (±N by start order). |
| max_bp_distance | int \| None | None | Optional cap: drop neighbors whose intergenic gap to the anchor exceeds this many bp. |
| same_strand | bool \| None | None | None=all neighbors; True=co-oriented only; False=opposite-strand only. Null-strand neighbors dropped when set. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| limit | int \| None | None | Max rows returned (paging). |

## Example

### Genes flanking an anchor on the same contig (±window by start order)

```python
gene_neighbors(locus_tags=["ACZ81_08860"], window=2)
```

## Response sketch

```expected-keys
total_matching, returned, truncated, anchors, by_organism, not_found, not_matched, warnings, results
```

Result row: `anchor_locus_tag, neighbor_locus_tag, rank_offset, bp_gap, strand, same_strand, product, gene_name, gene_category`

## Common mistakes

```mistake
Treating gene_neighbors as a co-expression / operon-membership call.
```

```correction
It reports positional adjacency only — genes next to the anchor on the same contig. Co-regulation lives in the expression / DerivedMetric tools; an operon is a hypothesis you confirm by layering DE direction + tight bp_gap + same_strand, not an output of this tool.
```

- Neighbors are scoped to the same contig and organism. Genomes are often fragmented (e.g. Alteromonas macleodii HOT1A3 has hundreds of contigs), so an anchor near a contig end returns fewer neighbors on that side — and a gene alone on its contig returns none (still reported in `anchors`).

- rank_offset gives direction (signed); bp_gap is always unsigned (use rank_offset's sign for upstream/downstream).

## Chaining patterns

- differential_expression_by_gene → gene_neighbors → gene_overview (operon context for a DE hit)
- genes_by_metabolite → gene_neighbors (inspect what flanks a transporter / catalyst gene)
- gene_neighbors → gene_aa_sequence (export the neighborhood's protein sequences)
- gene_neighbors → gene_ontology_terms (functional annotations of the neighbors)

Full reference (all examples, full response format, verbose fields): `docs://tools/gene_neighbors/full`
