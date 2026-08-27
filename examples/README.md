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

## `ontology_terms.py`

Four scenarios on the term side of the ontology surface: browse mode (no `search_text`), multi-ontology search with lockstep paging, a mixed `ontology_term_details` batch (hierarchy + bridges + `not_found`), and a two-hop bridge walk (tcdb → pfam → interpro). See `docs://ontologies/index` and `docs://analysis/annotation_evidence`.

```bash
uv run python examples/ontology_terms.py --scenario browse_merops
uv run python examples/ontology_terms.py --scenario multi_search
uv run python examples/ontology_terms.py --scenario term_details_batch
uv run python examples/ontology_terms.py --scenario bridge_walk
```

All four scripts are exercised by `tests/integration/test_examples.py` under `-m kg`.
