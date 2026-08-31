# gene_details

## What it does

Every Gene node property for a locus-tag batch — sequence, gene_summary, function_description, catalytic_activities, contributing_sources, coordinates.

Use when triage counts are not enough; for routing use `gene_overview`. Ontology and chemistry are edges, not properties — use `gene_ontology_terms` / `metabolites_by_gene`.
Filters: locus_tags.
Returns: total_matching, not_found, warnings; one row = one gene's full property dict.
docs://tools/gene_details; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'sync_0001']. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| limit | int \| None | None | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### Full properties for a single gene

```python
gene_details(locus_tags=["PMM0001"])
```

## Response sketch

```expected-keys
total_matching, returned, offset, truncated, not_found, warnings, results
```

## Common mistakes

- annotation_quality / min_quality semantics shifted in 2026-05 KG release. Existing notebooks using min_quality may select a different gene set than before. See docs://guide/conventions.

- This returns ALL Gene node properties via g{.*} — for the common case, use gene_overview which returns curated fields with routing signals.

- What this adds over gene_overview: the amino-acid `sequence`, genome coordinates (`contig`, `start`, `end`, `strand`, `protein_id`), the free-text `gene_summary` / `function_description` / `alternate_functional_descriptions`, sparse `catalytic_activities` (present on a minority of genes), `contributing_sources`, `seed_ortholog` + `seed_ortholog_evalue`, `all_identifiers`, `subcellular_localization`, and the full set of precomputed per-kind DM counts.

## Chaining patterns

- gene_overview → gene_details
- resolve_gene → gene_details
- genes_by_function → gene_details
- gene_details → gene_ontology_terms(locus_tags=[...], ontology=['ec', 'kegg']) — the EC numbers / KO terms behind a gene live on edges, not on the node.
- gene_details → metabolites_by_gene — when reaction_count / transported_metabolite_count are non-zero, list the metabolites this gene's reactions involve / its TCDB families transport. Single-gene chemistry deep-dive. See docs://analysis/metabolites.
- gene_details → gene_homologs(locus_tags=[...]) for ortholog group memberships, and list_organisms for the organism's taxonomy and capability rollups

Full reference (all examples, full response format, verbose fields): `docs://tools/gene_details/full`
