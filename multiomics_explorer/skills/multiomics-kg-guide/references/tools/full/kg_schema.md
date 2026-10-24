# kg_schema

## What it does

Live-KG schema: node labels with property names and types, relationship types with source and target labels.

Use before writing a `run_cypher` query; for filter values use `list_filter_values`, for the entity model docs://guide/concepts.
Filters: labels, relationship_types, section.
Returns: nodes, relationships, not_found_labels, not_found_relationship_types; no row list — scope the call or it dumps the whole graph.
docs://tools/kg_schema.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| labels | list[string] \| None | None | Restrict the node section to these labels (e.g. ['Gene', 'Experiment']). Omit for every label. Unknown values land in `not_found_labels`, not an error. |
| relationship_types | list[string] \| None | None | Restrict the relationship section to these types (e.g. ['Changes_expression_of']). Omit for every type. Unknown values land in `not_found_relationship_types`, not an error. |
| section | string ('nodes', 'relationships', 'both') | both | Which half of the schema to return. 'both' (default) returns both node and relationship sections; 'nodes' / 'relationships' returns only that section (the other comes back as an empty dict). |

## Response format

### Envelope

```expected-keys
nodes, relationships, not_found_labels, not_found_relationship_types
```

- **nodes** (object): Node labels mapped to their property definitions. Each value is {'properties': {'prop_name': 'type_string', ...}}. Empty when `section='relationships'`.
- **relationships** (object): Relationship types mapped to their definitions. Each value is {'source_labels': [...], 'target_labels': [...], 'properties': {'prop_name': 'type_string', ...}, 'description': optional caveat text for edge types that carry one}. Empty when `section='nodes'`.
- **not_found_labels** (list[string]): Requested `labels` values not present in the KG. Empty when `labels` was omitted or every value matched.
- **not_found_relationship_types** (list[string]): Requested `relationship_types` values not present in the KG. Empty when `relationship_types` was omitted or every value matched.

## Few-shot examples

### Example 1: Scope the node section to one label's properties

```example-call
kg_schema(labels=['Gene'], section='nodes')
```

```example-response
{
  "nodes": {
    "Gene": {
      "properties": {
        "all_identifiers": "list",
        "alternate_functional_descriptions": "list",
        "annotation_quality": "int",
        "annotation_state": "string",
        "annotation_types": "list",
        "boolean_metric_count": "int",
        "boolean_metric_types_observed": "list",
        "catalytic_activities": "list",
        "catalyzed_metabolite_count": "int",
        "categorical_metric_count": "int",
        "categorical_metric_types_observed": "list",
        "cazy_family_count": "int",
        "closest_ortholog_genera": "list",
        "closest_ortholog_group_size": "int",
        "cluster_membership_count": "int",
        "cluster_types": "list",
        "compartments_observed": "list",
        "contig": "string",
        "contributing_sources": "list",
        "coordinate_source": "string",
        "discussed_in_publication_count": "int",
        "end": "int",
        "expression_edge_count": "int",
        "function_description": "string",
        "gene_category": "string",
        "gene_name": "string",
        "gene_summary": "string",
        "id": "string",
        "informative_annotation_types": "list",
        "interpro_entry_count": "int",
        "locus_tag": "string",
        "merops_classes": "list",
        "merops_evidence_score_max": "float",
        "merops_family_count": "int",
        "ncbifam_family_count": "int",
        "numeric_metric_count": "int",
        "numeric_metric_types_observed": "list",
        "organism_name": "string",
        "preferred_id": "string",
        "product": "string",
        "protein_family": "string",
        "protein_id": "string",
        "reaction_count": "int",
        "seed_ortholog": "string",
        "seed_ortholog_evalue": "float",
        "sequence": "string",
        "sequence_source": "string",
        "signal_peptide_type": "string",
        "significant_down_count": "int",
        "significant_up_count": "int",
        "start": "int",
        "strand": "string",
        "subcellular_localization": "string",
        "tcdb_assignment_count": "int",
        "transmembrane_regions": "list",
        "transported_metabolite_count": "int"
      }
    }
  },
  "relationships": {},
  "not_found_labels": [],
  "not_found_relationship_types": []
}
```

### Example 2: Scope the relationship section to one type

```example-call
kg_schema(section='relationships', relationship_types=['Changes_expression_of'])
```

```example-response
{
  "nodes": {},
  "relationships": {
    "Changes_expression_of": {
      "source_labels": ["Experiment", "InvestigativeProcess"],
      "target_labels": ["BiologicalEntity", "Entity", "Gene", "NamedThing"],
      "properties": {
        "adjusted_p_value": "float",
        "expression_direction": "string",
        "expression_status": "string",
        "growth_phase": "string",
        "id": "string",
        "log2_fold_change": "float",
        "rank_by_effect": "int",
        "significant": "string",
        "time_point": "string",
        "time_point_hours": "float",
        "time_point_order": "int"
      }
    }
  },
  "not_found_labels": [],
  "not_found_relationship_types": []
}
```

### Example 3: GO transport edges — scope to one relationship type and read its caveat

```example-call
kg_schema(section='relationships', relationship_types=['Molecular_function_transports_metabolite'])
```

*The edge description carries the reading rule: GO defines the term as a transporter activity whose primary input is the compound (a term definition, not a gene fact), only the term's own axiom is stated, and filtered targets return empty by curation. The four GO edge types and `Tcdb_family_transports_chemical_role` are listed together under `section='relationships'`.*

```example-response
{
  "nodes": {},
  "relationships": {
    "Molecular_function_transports_metabolite": {
      "source_labels": ["BiologicalEntity", "BiologicalProcessOrActivity", "Entity", "MolecularFunction", "NamedThing"],
      "target_labels": ["Entity", "Metabolite", "NamedThing"],
      "properties": {"go_chebi_ids": "list"},
      "description": "GO defines this molecular-function term as a transporter activity whose primary input (RO:0004009) is this compound. ..."
    }
  },
  "not_found_labels": [],
  "not_found_relationship_types": []
}
```

## Chaining patterns

```
kg_schema → run_cypher
kg_schema(relationship_types=['Biological_process_transports_metabolite', ...]) → run_cypher over Gene → GO term → Metabolite (examples: docs://analysis/transport)
```

## Common mistakes

- Calling kg_schema() with no arguments dumps every node label and relationship type in the KG (100+ KB) — pass labels / relationship_types / section to scope the call to what you actually need before validating a run_cypher query.

- Schema does not include node counts — use run_cypher for counts (or kg_release_info for the headline gene / organism / experiment / paper counts)

- This is the one tool whose result is not a list envelope: no total_matching / results, just {nodes, relationships} keyed by label / relationship type. Ontology memberships are relationships (Gene_has_tcdb_family, Gene_involved_in_biological_process, ...), never Gene properties.

- Property types are Neo4j storage types (string / int / float / list / bool) — the meaning of each property lives on the tool pages (docs://tools/{tool}) and ontology pages (docs://ontologies/{key}), and vocabularies in list_filter_values.

```mistake
kg_schema() to discover valid organism or category filter values
```

```correction
list_filter_values() for categorical filter options; list_organisms() for organism details
```

- The GO transport edges (`Molecular_function_transports_metabolite`, `Biological_process_transports_metabolite` and the two `_chemical_role` variants) connect a GO term to a Metabolite or ChemicalRole. Molecular-function nodes do not carry the `GeneOntology` label biological-process nodes carry, so derive the namespace from `type(edge)`, not from node labels. Read each edge description for its caveat before querying; the tools `genes_by_metabolite` and `metabolites_by_gene` already label these rows.

## Package import equivalent

```python
from multiomics_explorer import kg_schema

result = kg_schema()
# returns dict with keys: nodes, relationships, not_found_labels, not_found_relationship_types
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
