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


# --- Batch A (Task 4.2): gene-centric tools -------------------------------

def gene_ontology_terms_scenarios():
    # Single-organism enforced; locus_tags batch. PMM1720 is a valid MED4
    # gene with no DE — still has ontology annotations (different layer), so
    # it's a benign baseline gene here. The interesting degenerate axes are
    # unknown / mixed batch (not_found) and a genome-only-organism gene set.
    return [
        Scenario(
            "unknown_locus",
            dict(locus_tags=[fx.UNKNOWN_LOCUS], organism=fx.CONTROL_ORGANISM),
            input_ids=[fx.UNKNOWN_LOCUS]),
        Scenario(
            "mixed_batch",
            dict(locus_tags=fx.MIXED_LOCUS_BATCH, organism=fx.CONTROL_ORGANISM),
            input_ids=fx.MIXED_LOCUS_BATCH),
        Scenario(
            "offset_past_end",
            dict(locus_tags=["PMM0001"], organism=fx.CONTROL_ORGANISM,
                 offset=fx.OFFSET_PAST_END)),
    ]


def gene_details_scenarios():
    # gene-only (globally-unique locus_tags), no organism param. Paginates.
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
            "offset_past_end",
            dict(locus_tags=["PMM0001"], offset=fx.OFFSET_PAST_END)),
    ]


def gene_homologs_scenarios():
    # gene-only batch (no organism). not_found is the flat diagnostic; genes
    # that exist but lack OGs land in `no_groups` (not `not_matched`), so it
    # is not asserted by the batch oracle. Paginates.
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
            "offset_past_end",
            dict(locus_tags=["PMM0001"], offset=fx.OFFSET_PAST_END)),
    ]


def gene_aa_sequence_scenarios():
    # Cross-organism gene batch. not_found = absent; not_matched = exists but
    # sequence null. Paginates.
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
            "offset_past_end",
            dict(locus_tags=["PMM0001"], offset=fx.OFFSET_PAST_END)),
    ]


def gene_neighbors_scenarios():
    # Cross-organism anchor batch. not_found = absent; not_matched = exists
    # but lacks coordinates. No offset param (window-bounded).
    return [
        Scenario(
            "unknown_locus",
            dict(locus_tags=[fx.UNKNOWN_LOCUS]),
            input_ids=[fx.UNKNOWN_LOCUS]),
        Scenario(
            "mixed_batch",
            dict(locus_tags=fx.MIXED_LOCUS_BATCH),
            input_ids=fx.MIXED_LOCUS_BATCH),
    ]


def gene_derived_metrics_scenarios():
    # Single-organism enforced gene batch. not_found = absent; not_matched =
    # exists but no DM rows after filters. PMM1720 (no-DE gene) is a plausible
    # no-DM gene too — exercises the not_matched path on a real gene.
    return [
        Scenario(
            "unknown_locus",
            dict(locus_tags=[fx.UNKNOWN_LOCUS], organism=fx.CONTROL_ORGANISM),
            input_ids=[fx.UNKNOWN_LOCUS]),
        Scenario(
            "mixed_batch",
            dict(locus_tags=fx.MIXED_LOCUS_BATCH, organism=fx.CONTROL_ORGANISM),
            input_ids=fx.MIXED_LOCUS_BATCH),
        Scenario(
            "offset_past_end",
            dict(locus_tags=["PMM0001"], organism=fx.CONTROL_ORGANISM,
                 offset=fx.OFFSET_PAST_END)),
    ]


def gene_clusters_by_gene_scenarios():
    # Single-organism enforced gene batch. not_found = absent; not_matched =
    # exists but no cluster memberships after filters.
    return [
        Scenario(
            "unknown_locus",
            dict(locus_tags=[fx.UNKNOWN_LOCUS], organism=fx.CONTROL_ORGANISM),
            input_ids=[fx.UNKNOWN_LOCUS]),
        Scenario(
            "mixed_batch",
            dict(locus_tags=fx.MIXED_LOCUS_BATCH, organism=fx.CONTROL_ORGANISM),
            input_ids=fx.MIXED_LOCUS_BATCH),
        Scenario(
            "offset_past_end",
            dict(locus_tags=["PMM0001"], organism=fx.CONTROL_ORGANISM,
                 offset=fx.OFFSET_PAST_END)),
    ]


def gene_response_profile_scenarios():
    # Gene batch summarized across DE experiments. not_found = absent;
    # genes with no expression land in `no_expression` (not `not_matched`).
    # GENE_NO_DE is the canonical no-expression gene; genome-only-organism
    # genes have no DE layer at all. Has no `total_matching` field — the
    # empty-layer oracle is shape-skipped, crash-freedom is the real check.
    return [
        Scenario(
            "unknown_locus",
            dict(locus_tags=[fx.UNKNOWN_LOCUS], organism=fx.CONTROL_ORGANISM),
            input_ids=[fx.UNKNOWN_LOCUS]),
        Scenario(
            "gene_no_de",
            dict(locus_tags=[fx.GENE_NO_DE], organism=fx.CONTROL_ORGANISM),
            input_ids=[fx.GENE_NO_DE]),
        Scenario(
            "mixed_batch",
            dict(locus_tags=fx.MIXED_LOCUS_BATCH, organism=fx.CONTROL_ORGANISM),
            input_ids=fx.MIXED_LOCUS_BATCH),
        Scenario(
            "offset_past_end",
            dict(locus_tags=["PMM0001"], organism=fx.CONTROL_ORGANISM,
                 offset=fx.OFFSET_PAST_END)),
    ]


def resolve_gene_scenarios():
    # Single-identifier (not a batch); no not_found list — an unmatched
    # identifier yields empty results / total_matching=0. Paginates.
    return [
        Scenario(
            "unknown_identifier",
            dict(identifier=fx.UNKNOWN_LOCUS)),
        Scenario(
            "offset_past_end",
            dict(identifier="PMM0001", offset=fx.OFFSET_PAST_END)),
    ]


def genes_by_function_scenarios():
    # Free-text Lucene search; no batch ID input. Degenerate axes: a query
    # term that matches nothing (empty-layer shape) and offset past end.
    return [
        Scenario(
            "no_hits_search",
            dict(search_text="zzzznonexistentfunctionzzz")),
        Scenario(
            "genome_only_organism",
            dict(search_text="transport",
                 organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "offset_past_end",
            dict(search_text="transport", offset=fx.OFFSET_PAST_END)),
    ]


# Registry: tool name -> builder. Phase 4 fills the rest.
SCENARIO_BUILDERS = {
    "genes_by_ontology": genes_by_ontology_scenarios,
    "gene_overview": gene_overview_scenarios,
    "differential_expression_by_gene": differential_expression_by_gene_scenarios,
    "list_organisms": list_organisms_scenarios,
    # Batch A
    "gene_ontology_terms": gene_ontology_terms_scenarios,
    "gene_details": gene_details_scenarios,
    "gene_homologs": gene_homologs_scenarios,
    "gene_aa_sequence": gene_aa_sequence_scenarios,
    "gene_neighbors": gene_neighbors_scenarios,
    "gene_derived_metrics": gene_derived_metrics_scenarios,
    "gene_clusters_by_gene": gene_clusters_by_gene_scenarios,
    "gene_response_profile": gene_response_profile_scenarios,
    "resolve_gene": resolve_gene_scenarios,
    "genes_by_function": genes_by_function_scenarios,
}
