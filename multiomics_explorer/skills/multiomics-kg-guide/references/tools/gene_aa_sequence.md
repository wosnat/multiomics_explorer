# gene_aa_sequence

## What it does

Return amino-acid sequences for a batch of genes, export-optimized for BLAST / HMMER / alignment. Set fasta=true for one multi-FASTA blob; sequence-length stats cover the full match (page-independent). not_found = locus_tag absent from KG; not_matched = gene exists but its sequence is null.

Routing: feed locus_tags from `resolve_gene` / `gene_overview` / `genes_by_function`; this is the terminal export step (pair with fasta=true for external tools).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags. Cross-organism OK (globally unique). E.g. ['ACZ81_08860', 'PMM0001']. |
| fasta | bool | False | If true, omit per-row `sequence` and return one multi-FASTA blob in the envelope instead (no duplication). |
| summary | bool | False | If true, return envelope only (results=[]); sugar for limit=0. |
| limit | int | 25 | Max results. |
| offset | int | 0 | Rows to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_matching, returned, truncated, by_organism, sequence_length_stats, not_found, not_matched, fasta, results
```

- **total_matching** (int): Input locus_tags resolving to a gene with a sequence. E.g. 2.
- **returned** (int): Rows in this response (0 when summary=true). E.g. 2.
- **truncated** (bool): True when more matched rows exist beyond this page (offset + returned < total_matching).
- **by_organism** (list[OrganismCount]): Matched-gene count per organism, sorted desc. E.g. [{'organism_name': 'Alteromonas macleodii HOT1A3', 'count': 2}].
- **sequence_length_stats** (SequenceLengthStats): Amino-acid-length distribution over ALL matched genes (page-independent — stable across limit/offset).
- **not_found** (list[string]): Input locus_tags absent from the KG. Distinct from not_matched (those exist but lack a sequence). E.g. ['NOTAREAL'].
- **not_matched** (list[string]): Locus_tags whose gene exists but has a null sequence (expression-only, no genome match). Distinct from not_found. E.g. ['SYNW1755'].
- **fasta** (string): Multi-FASTA blob covering the returned page (non-empty only when fasta=true; '' otherwise). Header: '>{locus_tag} {organism_name}|{protein_id}|{product}'.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (globally unique). E.g. 'ACZ81_08860'. |
| organism_name | string | Organism the gene belongs to. E.g. 'Alteromonas macleodii HOT1A3'. |
| gene_name | string \| None (optional) | Short gene name, often null. E.g. 'dnaN'. |
| product | string \| None (optional) | Protein product description. E.g. 'DNA polymerase III subunit beta'. |
| protein_id | string \| None (optional) | Protein accession used in the FASTA header. E.g. 'WP_011469022.1'. |
| sequence_length | int | Amino-acid length of the sequence. E.g. 487. |
| sequence | string \| None (optional) | Amino-acid sequence string. Null when fasta=true (carried by the envelope `fasta` blob instead). E.g. 'MKFTI...'. |

## Few-shot examples

### Example 1: Amino-acid sequences for a batch of genes (rows carry the sequence)

```example-call
gene_aa_sequence(locus_tags=["ACZ81_08860", "ACZ81_08855"])
```

```example-response
{
  "total_matching": 2,
  "returned": 2,
  "truncated": false,
  "by_organism": [{"organism_name": "Alteromonas macleodii HOT1A3", "count": 2}],
  "sequence_length_stats": {"count": 2, "min": 178, "q1": 178.0, "median": 178.0, "q3": 487.0, "max": 487, "mean": 332.5},
  "not_found": [],
  "not_matched": [],
  "fasta": "",
  "results": [
    {
      "locus_tag": "ACZ81_08855",
      "organism_name": "Alteromonas macleodii HOT1A3",
      "gene_name": null,
      "product": "hypothetical protein",
      "protein_id": "WP_049586664.1",
      "sequence_length": 178,
      "sequence": "MLSVAAGGLTLAALGVIYKSWRAQASTYLYLGLVVWLVAAVCWSYAQGWEFGVLYALCIPSILVWPFIAFNQTHLPQPKNVPQPRSFDFSRRTVLGNIANYIVVLVVLLVVSVLLTL..."
    },
    {
      "locus_tag": "ACZ81_08860",
      "organism_name": "Alteromonas macleodii HOT1A3",
      "gene_name": null,
      "product": "PepSY-associated TM helix domain-containing protein",
      "protein_id": "WP_061485747.1",
      "sequence_length": 487,
      "sequence": "MDKITKQNALNAHTWVGVFLSVLLFLVCLSGTVAVFHLEFERWEQPHIEEMKNVSPDVVEKAMDTFLAQNTQESHHLYVVFPTSDIPRLVVENDHAAYFADSEGNLLEQESVSFTEM..."
    }
  ]
}
```

### Example 2: Export-ready multi-FASTA (fasta=True moves the sequence to the envelope blob)

```example-call
gene_aa_sequence(locus_tags=["ACZ81_08860", "ACZ81_08855"], fasta=True)
```

```example-response
{
  "total_matching": 2,
  "returned": 2,
  "truncated": false,
  "by_organism": [{"organism_name": "Alteromonas macleodii HOT1A3", "count": 2}],
  "sequence_length_stats": {"count": 2, "min": 178, "q1": 178.0, "median": 178.0, "q3": 487.0, "max": 487, "mean": 332.5},
  "not_found": [],
  "not_matched": [],
  "fasta": ">ACZ81_08855 Alteromonas macleodii HOT1A3|WP_049586664.1|hypothetical protein\nMLSVAAGGLTLAALGVIYKSWRAQASTYLYLGLVVWLVA...",
  "results": [
    {
      "locus_tag": "ACZ81_08855",
      "organism_name": "Alteromonas macleodii HOT1A3",
      "gene_name": null,
      "product": "hypothetical protein",
      "protein_id": "WP_049586664.1",
      "sequence_length": 178,
      "sequence": null
    },
    {
      "locus_tag": "ACZ81_08860",
      "organism_name": "Alteromonas macleodii HOT1A3",
      "gene_name": null,
      "product": "PepSY-associated TM helix domain-containing protein",
      "protein_id": "WP_061485747.1",
      "sequence_length": 487,
      "sequence": null
    }
  ]
}
```

### Example 3: not_found vs not_matched (missing gene vs gene with no sequence)

```example-call
gene_aa_sequence(locus_tags=["ACZ81_08860", "A9601_09441", "NOTAREAL"])
```

```example-response
{
  "total_matching": 1,
  "returned": 1,
  "truncated": false,
  "by_organism": [{"organism_name": "Alteromonas macleodii HOT1A3", "count": 1}],
  "sequence_length_stats": {"count": 1, "min": 487, "q1": 487.0, "median": 487.0, "q3": 487.0, "max": 487, "mean": 487.0},
  "not_found": ["NOTAREAL"],
  "not_matched": ["A9601_09441"],
  "fasta": "",
  "results": [
    {
      "locus_tag": "ACZ81_08860",
      "organism_name": "Alteromonas macleodii HOT1A3",
      "gene_name": null,
      "product": "PepSY-associated TM helix domain-containing protein",
      "protein_id": "WP_061485747.1",
      "sequence_length": 487,
      "sequence": "MDKITKQNALNAHTWVGVFLSVLLFLVCLSGTVAVFHLEFERWEQPHIEEMKNVSPDVVEKAMDTFLAQNTQESHHLYVVFPTSDIPRLVVENDHAAYFADSEGNLLEQESVSFTEM..."
    }
  ]
}
```

### Example 4: Length stats only, no sequences transferred (summary=True)

```example-call
gene_aa_sequence(locus_tags=["ACZ81_08860", "ACZ81_08855"], summary=True)
```

### Example 5: From a text search to exported sequences

```
Step 1: genes_by_function(search_text="ABC transporter", organism="Alteromonas macleodii HOT1A3")
        -> collect locus_tags from results

Step 2: gene_aa_sequence(locus_tags=[...], fasta=True)
        -> copy the envelope `fasta` blob straight into BLAST / HMMER / an aligner
```

## Chaining patterns

```
resolve_gene → gene_aa_sequence(fasta=True) (resolve a name, then export the sequence)
genes_by_function → gene_aa_sequence (text hit list → AA sequences for external alignment/search)
gene_overview → gene_aa_sequence (confirm identity, then pull the sequence)
```

## Common mistakes

- Sequences are amino-acid only — the KG stores no nucleotide sequence. There is no DNA/CDS export here.

- fasta carries the sequence in exactly one place: rows when fasta=False, the envelope `fasta` blob when fasta=True (rows then have sequence=null). Never both — do not expect the row `sequence` to be populated when fasta=True.

- sequence_length_stats and by_organism cover the full match, not just the returned page — they are stable across limit / offset. Page with `offset` to walk a large batch.

- not_matched (gene exists but `sequence` is null, ~3% of genes — expression-only, no genome match) is distinct from not_found (locus_tag absent from the KG). See docs://guide/conventions.

## Package import equivalent

```python
from multiomics_explorer import gene_aa_sequence

result = gene_aa_sequence(locus_tags=...)
# returns dict with keys: total_matching, returned, truncated, by_organism, sequence_length_stats, not_found, not_matched, fasta, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
