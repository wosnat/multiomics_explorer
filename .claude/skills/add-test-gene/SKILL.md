---
name: add-test-gene
description: Add new gene examples to the correctness test fixtures and test suite. Use when you want to cover additional organisms, annotation edge cases, or specific genes.
disable-model-invocation: true
argument-hint: "[locus_tag or description like 'hypothetical from RSP50']"
---

# Add New Gene Examples to Test Suite

You are adding new gene(s) to the test fixture set and creating corresponding test cases.

## What the user wants

`$ARGUMENTS` — either:
- A specific locus_tag (e.g., `PMM0845`, `SYNW0001`)
- A description of what to find (e.g., `hypothetical from RSP50`, `gene with many GO terms from EZ55`)

## Step 1: Find the gene(s)

Gene annotation source files are at:
```
/home/osnat/github/multiomics_biocypher_kg/cache/data/{Organism}/genomes/{Genome}/gene_annotations_merged.json
```

Available organisms/genomes:
- Prochlorococcus: MED4, MIT9312, MIT9301, AS9601, NATL1A, NATL2A, RSP50
- Alteromonas: MIT1002, EZ55, HOT1A3
- Synechococcus: WH8102, CC9311

Each file is a JSON dict keyed by locus_tag. If the user gave a locus_tag, read it directly. If they gave a description, search the appropriate file(s) to find a matching gene.

Check the gene is not already in the fixtures:
```bash
grep -c "locus_tag" tests/fixtures/gene_data.py
grep "the_locus_tag" tests/fixtures/gene_data.py
```

## Step 2: Add to fixture generator

Edit `scripts/build_test_fixtures.py` in the gene selection section (~line 136-222):

- For a specific locus_tag: `SELECTED_GENES.append(get_gene("Organism/Genome", "LOCUS_TAG"))`
- For a criteria-based search: use `find_gene("Organism/Genome", has_gene_name=True, ...)` with appropriate filters

Available `find_gene` filters: `has_gene_name`, `is_hypothetical`, `has_ec`, `min_ec_count`, `has_partial_ec`, `min_identifiers`, `prefer_minimal`, `prefer_rich`.

## Step 3: Regenerate fixtures

```bash
python scripts/build_test_fixtures.py
```

This overwrites `tests/fixtures/gene_data.py` with the updated gene set. Verify the new gene appears:
```bash
grep "new_locus_tag" tests/fixtures/gene_data.py
```

## Step 4: Add unit tests

Edit `tests/unit/test_tool_correctness.py`. The parameterized tests (e.g., `test_single_gene_lookup_all_fixtures`) automatically pick up new fixture genes. But consider adding specific tests if the new gene covers a novel edge case:

- Gene with unusual properties (many GO terms, special characters in product, etc.)
- Gene that exercises a tool path not yet covered
- Gene with known expression data or homologs

Pattern for adding a specific test:
```python
def test_new_edge_case_name(self, tool_fns, mock_ctx):
    gene = GENES_BY_LOCUS["NEW_LOCUS_TAG"]
    _conn_from(mock_ctx).execute_query.return_value = [as_resolve_gene_result(gene)]
    result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier=gene["locus_tag"]))
    assert len(result["results"]) == 1
    # ... specific assertions for the edge case
```

## Step 5: Add KG integration tests

Edit `tests/integration/test_tool_correctness_kg.py`. Parameterized tests auto-include new fixtures. Add specific tests if needed.

Remember: KG text fields use char escaping (`'` -> `^`, `|` -> `,`). Use `_kg_escape()` for text comparisons.

## Step 6: Add eval/regression cases

Edit `tests/evals/cases.yaml` — append new entries:

```yaml
- id: descriptive_case_id
  tool: resolve_gene  # or search_genes, get_gene_details, etc.
  desc: What this case verifies
  params:
    identifier: NEW_LOCUS_TAG
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain]
    row0:
      locus_tag: NEW_LOCUS_TAG
```

## Step 7: Verify

```bash
# Unit tests
pytest tests/unit/test_tool_correctness.py -v

# KG integration tests
pytest tests/integration/test_tool_correctness_kg.py -v -m kg

# Regenerate regression baselines for new cases
pytest tests/regression/ --force-regen -m kg

# Verify baselines pass
pytest tests/regression/ -m kg
```

## Reference: current fixture genes

The current fixture set covers 16 genes. Run this to see them:
```bash
grep '"locus_tag":' tests/fixtures/gene_data.py
```

Axes already covered: well-annotated, hypothetical, multiple ECs, partial EC, many identifiers, gene_name=locus_tag, no gene_name, all 3 organisms, 8 strains.

When adding genes, prefer ones that cover a **new** axis not already represented (e.g., a new organism/strain, a gene with expression data, a gene with unique functional annotations).
