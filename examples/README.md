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

Seven scenarios across the three Metabolite-source pipelines (transport / gene reaction / metabolomics). See `docs://analysis/metabolites`.

```bash
uv run python examples/metabolites.py --scenario discover
uv run python examples/metabolites.py --scenario compound_to_genes
uv run python examples/metabolites.py --scenario gene_to_metabolites
uv run python examples/metabolites.py --scenario cross_feeding
uv run python examples/metabolites.py --scenario n_source_de
uv run python examples/metabolites.py --scenario tcdb_chain
uv run python examples/metabolites.py --scenario measurement
```

## `annotation_evidence.py`

Four scenarios exercising the annotation-trust surface (evidence / evidence_score / tier / call_class / interpro_type) across the 17 supported ontologies. See `docs://analysis/annotation_evidence`.

```bash
uv run python examples/annotation_evidence.py --scenario merops_call_class
uv run python examples/annotation_evidence.py --scenario tcdb_attachment_depth
uv run python examples/annotation_evidence.py --scenario interpro_enrichment
uv run python examples/annotation_evidence.py --scenario trust_filtered_tcdb
```

All three scripts are exercised by `tests/integration/test_examples.py` under `-m kg`.
