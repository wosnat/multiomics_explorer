# examples

Runnable collateral for `docs://analysis/enrichment`'s code examples.

## `pathway_enrichment.py`

Five scenarios exercising the enrichment package end-to-end.

```bash
uv run python examples/pathway_enrichment.py --scenario landscape
uv run python examples/pathway_enrichment.py --scenario de
uv run python examples/pathway_enrichment.py --scenario cluster
uv run python examples/pathway_enrichment.py --scenario ortholog
uv run python examples/pathway_enrichment.py --scenario custom --locus-tags PMM0001,PMM0002
```

Exercised by `tests/integration/test_examples.py` under `-m kg`.
