# examples

Runnable companions to `docs://analysis/*` guides.

## `pathway_enrichment.py`

Five scenarios exercising the enrichment package end-to-end. See `docs://analysis/enrichment`.

```bash
uv run python examples/pathway_enrichment.py --scenario landscape
uv run python examples/pathway_enrichment.py --scenario de
uv run python examples/pathway_enrichment.py --scenario cluster
uv run python examples/pathway_enrichment.py --scenario ortholog
uv run python examples/pathway_enrichment.py --scenario custom --locus-tags PMM0001,PMM0002
```

## `metabolites.py`

Eight scenarios across the three Metabolite-source pipelines (transport / gene reaction / metabolomics). See `docs://analysis/metabolites`.

```bash
uv run python examples/metabolites.py --scenario discover
uv run python examples/metabolites.py --scenario compound_to_genes
uv run python examples/metabolites.py --scenario gene_to_metabolites
uv run python examples/metabolites.py --scenario cross_feeding
uv run python examples/metabolites.py --scenario n_source_de
uv run python examples/metabolites.py --scenario tcdb_chain
uv run python examples/metabolites.py --scenario precision_tier
uv run python examples/metabolites.py --scenario measurement
```

Both scripts are exercised by `tests/integration/test_examples.py` under `-m kg`.
