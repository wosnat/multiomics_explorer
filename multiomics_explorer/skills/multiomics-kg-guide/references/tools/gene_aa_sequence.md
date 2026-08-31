# gene_aa_sequence

## What it does

Amino-acid sequences for a gene batch, export-shaped for BLAST / HMMER / alignment; the KG stores no nucleotide sequence.

Use as the terminal export step; for annotations use `gene_details`, for genomic context `gene_neighbors`.
Filters: locus_tags, fasta.
Returns: by_organism, sequence_length_stats, the fasta blob when fasta=True, not_found, not_matched (gene exists, sequence null); one row = (locus_tag, sequence, protein_id).
docs://tools/gene_aa_sequence; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags. Cross-organism OK (globally unique). E.g. ['ACZ81_08860', 'PMM0001']. |
| fasta | bool | False | If true, omit per-row `sequence` and return one multi-FASTA blob in the envelope instead (no duplication). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| limit | int \| None | None | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### Amino-acid sequences for a batch of genes (rows carry the sequence)

```python
gene_aa_sequence(locus_tags=["ACZ81_08860", "ACZ81_08855"])
```

## Response sketch

```expected-keys
total_matching, returned, truncated, by_organism, sequence_length_stats, not_found, not_matched, warnings, fasta, results
```

Result row: `locus_tag, organism_name, gene_name, product, protein_id, sequence_length, sequence`

## Common mistakes

- Sequences are amino-acid only — the KG stores no nucleotide sequence. There is no DNA/CDS export here.

- fasta carries the sequence in exactly one place: rows when fasta=False, the envelope `fasta` blob when fasta=True (rows then have sequence=null). Never both — do not expect the row `sequence` to be populated when fasta=True.

- sequence_length_stats and by_organism cover the full match, not just the returned page — they are stable across limit / offset. Page with `offset` to walk a large batch.

## Chaining patterns

- resolve_gene → gene_aa_sequence(fasta=True) (resolve a name, then export the sequence)
- genes_by_function → gene_aa_sequence (text hit list → AA sequences for external alignment/search)
- gene_overview → gene_aa_sequence (confirm identity, then pull the sequence)

Full reference (all examples, full response format, verbose fields): `docs://tools/gene_aa_sequence/full`
