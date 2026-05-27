# gene_neighbors

## What it does

Return each anchor gene's genomic neighborhood — genes adjacent on the same contig and organism — for operon / synteny reasoning, with strand orientation and intergenic gap. Positional only (not co-expression); fragmented assemblies yield fewer neighbors near contig ends. not_found = anchor absent from KG; not_matched = anchor exists but lacks coordinates.

Routing: feed anchors from `differential_expression_by_gene` or `genes_by_metabolite`, then chain the returned neighbor locus_tags into `gene_overview` / `gene_aa_sequence` / `differential_expression_by_gene` for operon context.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Anchor gene locus tags. Cross-organism OK. E.g. ['ACZ81_08860']. |
| window | int | 5 | Number of genes upstream AND downstream on the same contig (±N by start order). |
| max_bp_distance | int \| None | None | Optional cap: drop neighbors whose intergenic gap to the anchor exceeds this many bp. |
| same_strand | bool \| None | None | None=all neighbors; True=co-oriented only; False=opposite-strand only. Null-strand neighbors dropped when set. |
| summary | bool | False | If true, return envelope only (results=[]); sugar for limit=0. |
| limit | int | 25 | Max neighbor rows. |

## Response format

### Envelope

```expected-keys
total_matching, returned, truncated, anchors, by_organism, not_found, not_matched, warnings, results
```

- **total_matching** (int): Neighbor rows after max_bp_distance + same_strand filters (pre-limit). E.g. 2.
- **returned** (int): Rows in this response (0 when summary=true). E.g. 2.
- **truncated** (bool): True when total_matching > returned (more neighbor rows than this page).
- **anchors** (list[AnchorBlock]): One block per anchor that has coordinates, with anchor metadata and per-anchor neighbor counts.
- **by_organism** (list[OrganismCount]): Neighbor-row count per organism, sorted desc. E.g. [{'organism_name': 'Alteromonas macleodii HOT1A3', 'count': 2}].
- **not_found** (list[string]): Anchor locus_tags absent from the KG. Distinct from not_matched (those exist but lack coordinates). E.g. ['NOTAREAL'].
- **not_matched** (list[string]): Anchors that exist but lack genomic coordinates (null start/contig) → no neighborhood. Distinct from not_found. E.g. ['SYNW1755'].
- **warnings** (list[string]): Advisory notes, e.g. same_strand requested but an anchor's own strand is null → its neighbors returned unfiltered.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| anchor_locus_tag | string | Anchor gene the neighbor is reported relative to. E.g. 'ACZ81_08860'. |
| neighbor_locus_tag | string | Adjacent gene on the same contig. E.g. 'ACZ81_08850'. |
| rank_offset | int | Signed positional offset by start order; negative = upstream, positive = downstream; anchor itself excluded. E.g. -1. |
| bp_gap | int | Unsigned intergenic distance (bp) between anchor and neighbor; 0 if their intervals overlap. E.g. 10. |
| strand | string \| None (optional) | Neighbor strand, '+' or '-' (genes with coordinates carry a strand; rarely null). E.g. '+'. |
| same_strand | bool \| None (optional) | True if neighbor and anchor share a strand, False if opposite; None when either strand is null. E.g. True. |
| product | string \| None (optional) | Neighbor protein product. E.g. 'hypothetical protein'. |
| gene_name | string \| None (optional) | Neighbor short gene name, often null. E.g. 'dnaA'. |
| gene_category | string \| None (optional) | Neighbor functional category. E.g. 'unknown'. |

## Few-shot examples

### Example 1: Genes flanking an anchor on the same contig (±window by start order)

```example-call
gene_neighbors(locus_tags=["ACZ81_08860"], window=2)
```

```example-response
# rank_offset is signed: negative = upstream by start, positive = downstream.
# The anchor itself is excluded from results (it is in `anchors`).
# bp_gap is the unsigned intergenic distance (0 when intervals overlap).
# same_strand is null only if a gene's strand is null — rare: genes with coordinates carry a strand.
{
  "total_matching": 4, "returned": 4, "truncated": false,
  "anchors": [
    {"locus_tag": "ACZ81_08860", "organism_name": "Alteromonas macleodii HOT1A3", "contig": "NZ_CP012202.1", "start": 2042340, "end": 2043803, "strand": "+", "product": "PepSY-associated TM helix domain-containing protein", "neighbors_returned": 4, "dropped_null_strand": 0}
  ],
  "by_organism": [{"organism_name": "Alteromonas macleodii HOT1A3", "count": 4}],
  "not_found": [], "not_matched": [], "warnings": [],
  "results": [
    {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08850", "rank_offset": -2, "bp_gap": 556, "strand": "+", "same_strand": true, "product": "TonB-dependent siderophore receptor", "gene_name": null, "gene_category": null},
    {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08855", "rank_offset": -1, "bp_gap": 10, "strand": "+", "same_strand": true, "product": "hypothetical protein", "gene_name": null, "gene_category": null},
    {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08865", "rank_offset": 1, "bp_gap": 335, "strand": "-", "same_strand": false, "product": "demethoxyubiquinone hydroxylase family protein", "gene_name": null, "gene_category": null},
    {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08870", "rank_offset": 2, "bp_gap": 1119, "strand": "+", "same_strand": true, "product": "strictosidine synthase family protein", "gene_name": null, "gene_category": null}
  ]
}
```

### Example 2: Cap the intergenic gap (drop neighbors farther than max_bp_distance bp)

```example-call
gene_neighbors(locus_tags=["ACZ81_08860"], window=2, max_bp_distance=400)
```

```example-response
# Same anchor as above: the ±2 window finds 4 neighbors, but only the two
# within 400 bp survive (bp_gap 10 and 335 kept; 556 and 1119 dropped).
{
  "total_matching": 2, "returned": 2,
  "results": [
    {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08855", "rank_offset": -1, "bp_gap": 10},
    {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08865", "rank_offset": 1, "bp_gap": 335}
  ]
}
```

### Example 3: Co-oriented neighbors only (same_strand=True)

```example-call
gene_neighbors(locus_tags=["ACZ81_08860"], window=2, same_strand=True)
```

```example-response
# Keeps only neighbors on the anchor's own strand ('+'); opposite-strand
# neighbors are dropped (here ACZ81_08865, '-'). dropped_null_strand counts
# only NULL-strand drops (0 here). Defensive: in the current build every gene
# with coordinates has a strand, so the filter is always appliable — if an
# anchor's own strand were null, its neighbors would be returned unfiltered
# with a `warnings` entry.
{
  "total_matching": 3, "returned": 3,
  "anchors": [{"locus_tag": "ACZ81_08860", "strand": "+", "neighbors_returned": 3, "dropped_null_strand": 0}],
  "warnings": [],
  "results": [
    {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08850", "rank_offset": -2, "same_strand": true},
    {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08855", "rank_offset": -1, "same_strand": true},
    {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08870", "rank_offset": 2, "same_strand": true}
  ]
}
```

### Example 4: not_found vs not_matched (missing gene vs gene with no coordinates)

```example-call
gene_neighbors(locus_tags=["ACZ81_08860", "A9601_09441", "NOTAREAL"])
```

```example-response
# A9601_09441 exists but has no contig/start coordinates -> not_matched (no
# neighborhood). NOTAREAL is absent from the KG -> not_found.
{
  "not_found": ["NOTAREAL"],
  "not_matched": ["A9601_09441"],
  "anchors": [{"locus_tag": "ACZ81_08860", "contig": "NZ_CP012202.1", "neighbors_returned": 6}]
}
```

### Example 5: Operon context for a DE hit, then enrich with overview

```
Step 1: differential_expression_by_gene(locus_tags=["ACZ81_08860"], organism="Alteromonas macleodii HOT1A3")
        -> confirm ACZ81_08860 is a DE hit

Step 2: gene_neighbors(locus_tags=["ACZ81_08860"], window=5)
        -> list flanking genes; co-oriented, tight bp_gap neighbors hint at a shared operon

Step 3: gene_overview(locus_tags=[<neighbor_locus_tags>])
        -> pull identity + data-availability for the neighbors (co-regulation must be checked,
           not assumed — positional adjacency is not co-expression)
```

## Chaining patterns

```
differential_expression_by_gene → gene_neighbors → gene_overview (operon context for a DE hit)
genes_by_metabolite → gene_neighbors (inspect what flanks a transporter / catalyst gene)
gene_neighbors → gene_aa_sequence (export the neighborhood's protein sequences)
gene_neighbors → gene_ontology_terms (functional annotations of the neighbors)
```

## Common mistakes

```mistake
Treating gene_neighbors as a co-expression / operon-membership call.
```

```correction
It reports positional adjacency only — genes next to the anchor on the same contig. Co-regulation lives in the expression / DerivedMetric tools; an operon is a hypothesis you confirm by layering DE direction + tight bp_gap + same_strand, not an output of this tool.
```

- Neighbors are scoped to the same contig and organism. Genomes are often fragmented (e.g. Alteromonas macleodii HOT1A3 has hundreds of contigs), so an anchor near a contig end returns fewer neighbors on that side — and a gene alone on its contig returns none (still reported in `anchors`).

- rank_offset gives direction (signed); bp_gap is always unsigned (use rank_offset's sign for upstream/downstream).

- not_matched (gene exists but lacks contig/start coordinates) is distinct from not_found (locus_tag absent from the KG). See docs://guide/conventions.

## Package import equivalent

```python
from multiomics_explorer import gene_neighbors

result = gene_neighbors(locus_tags=...)
# returns dict with keys: total_matching, anchors, by_organism, not_found, not_matched, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
