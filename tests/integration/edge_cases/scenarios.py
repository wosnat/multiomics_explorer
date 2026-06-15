"""Per-tool degenerate-input scenarios for the corner-case matrix.

Each builder returns a list of Scenario tuples. A tool's baseline call is the
minimal valid invocation; each scenario substitutes ONE degenerate value.
"""
from dataclasses import dataclass, field
from fastmcp.exceptions import ToolError
from tests.integration.edge_cases import fixtures as fx


@dataclass
class Scenario:
    label: str
    kwargs: dict
    expects_error: type | None = None
    input_ids: list = field(default_factory=list)


def genes_by_ontology_scenarios():
    return [
        Scenario(
            "genome_only_organism",
            dict(ontology="cyanorak_role",
                 term_ids=["cyanorak.role:D.1.5"],
                 organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "expression_layer_empty_organism",
            dict(ontology="cyanorak_role",
                 term_ids=["cyanorak.role:D.1.5"],
                 organism=fx.EXPRESSION_LAYER_EMPTY_ORGANISM)),
        Scenario(
            # 'go' is not a valid ontology key — split into go_bp/go_mf/go_cc
            # (scenario fix). go:9999999 is an unknown term within go_bp.
            "unknown_term",
            dict(ontology="go_bp", term_ids=[fx.UNKNOWN_ONTOLOGY_TERM],
                 organism=fx.CONTROL_ORGANISM),
            input_ids=[fx.UNKNOWN_ONTOLOGY_TERM]),
    ]


def gene_overview_scenarios():
    # gene_overview is gene-only: locus_tags are globally unique, no `organism`
    # param (scenario fix — see Task 3.1 triage).
    return [
        Scenario(
            "unknown_locus",
            dict(locus_tags=[fx.UNKNOWN_LOCUS]),
            input_ids=[fx.UNKNOWN_LOCUS]),
        Scenario(
            "mixed_batch",
            dict(locus_tags=fx.MIXED_LOCUS_BATCH),
            input_ids=fx.MIXED_LOCUS_BATCH),
        Scenario(
            "gene_no_de",
            dict(locus_tags=[fx.GENE_NO_DE]),
            input_ids=[fx.GENE_NO_DE]),
    ]


def differential_expression_by_gene_scenarios():
    return [
        Scenario(
            "genome_only_organism",
            dict(organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "expression_layer_empty_organism",
            dict(organism=fx.EXPRESSION_LAYER_EMPTY_ORGANISM)),
        Scenario(
            "gene_no_de",
            dict(organism=fx.CONTROL_ORGANISM, locus_tags=[fx.GENE_NO_DE]),
            input_ids=[fx.GENE_NO_DE]),
        Scenario(
            "offset_past_end",
            dict(organism=fx.CONTROL_ORGANISM, offset=fx.OFFSET_PAST_END)),
    ]


def list_organisms_scenarios():
    return [
        Scenario(
            "unknown_organism_name",
            dict(organism_names=["Nonexistus fakeii"]),
            input_ids=["Nonexistus fakeii"]),
    ]


# Registry: tool name -> builder. Phase 4 fills the rest.
SCENARIO_BUILDERS = {
    "genes_by_ontology": genes_by_ontology_scenarios,
    "gene_overview": gene_overview_scenarios,
    "differential_expression_by_gene": differential_expression_by_gene_scenarios,
    "list_organisms": list_organisms_scenarios,
}
