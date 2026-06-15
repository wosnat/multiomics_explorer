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


# --- Batch B (Task 4.2): enrichment + ortholog/cluster tools --------------
#
# Real IDs discovered against the live KG (2026-06-15, branch
# fix/organism-resolver-genome-only):
#   MIT0801 metabolomics experiment (no DE layer):
#     10.1128/msystems.01261-22_kujawinski_metabolomics_0801_whole_cell
#   MED4 DE experiment:
#     10.1038/ismej.2015.36_carbon_air_0036_co2_21_med4_microarray
#   MED4 clustering analysis / cluster:
#     clustering_analysis:ismej.2011.49:med4_iron_response_clusters
#     cluster:ismej.2011.49:med4_iron_response_clusters:19
#   Homolog groups:
#     cyanorak:CK_00000364  (dnaN — core, present in many organisms)
#     cyanorak:CK_00057053  (members ONLY in MIT9515 — genome-only, no DE)

_MIT0801_METAB_EXP = (
    "10.1128/msystems.01261-22_kujawinski_metabolomics_0801_whole_cell")
_MED4_DE_EXP = (
    "10.1038/ismej.2015.36_carbon_air_0036_co2_21_med4_microarray")
_MED4_ANALYSIS = "clustering_analysis:ismej.2011.49:med4_iron_response_clusters"
_MED4_CLUSTER = "cluster:ismej.2011.49:med4_iron_response_clusters:19"
_GROUP_CORE = "cyanorak:CK_00000364"          # dnaN, broadly present
_GROUP_MIT9515_ONLY = "cyanorak:CK_00057053"  # members only in no-DE organism


def pathway_enrichment_scenarios():
    # Requires organism + experiment_ids + ontology + (level | term_ids).
    # Highest-risk empty-DE probe: MIT0801's experiment is METABOLOMICS-only,
    # so the DE foreground is empty — the enrichment must yield a well-formed
    # empty envelope, not crash on empty category/term rollups. unknown +
    # genome-only experiment also bottom out at total_matching=0 (the tool
    # leaves not_found empty for unknown experiments — empty layer, no batch
    # diagnostic asserted).
    return [
        Scenario(
            "expression_layer_empty_organism",
            dict(organism=fx.EXPRESSION_LAYER_EMPTY_ORGANISM,
                 experiment_ids=[_MIT0801_METAB_EXP],
                 ontology="kegg", level=1)),
        Scenario(
            "unknown_experiment",
            dict(organism=fx.CONTROL_ORGANISM,
                 experiment_ids=[fx.UNKNOWN_EXPERIMENT_ID],
                 ontology="kegg", level=1)),
        Scenario(
            "genome_only_organism",
            dict(organism=fx.GENOME_ONLY_ORGANISM,
                 experiment_ids=[fx.UNKNOWN_EXPERIMENT_ID],
                 ontology="kegg", level=1)),
        Scenario(
            "offset_past_end",
            dict(organism=fx.CONTROL_ORGANISM,
                 experiment_ids=[_MED4_DE_EXP],
                 ontology="kegg", level=1, offset=fx.OFFSET_PAST_END)),
    ]


def cluster_enrichment_scenarios():
    # Requires analysis_id + organism + ontology + (level | term_ids). Flat
    # not_found / not_matched on analysis IDs. unknown analysis lands in
    # not_matched (KG resolves the ID-vs-organism pairing); a real MED4
    # analysis under the wrong organism (genome-only) also lands in
    # not_matched (wrong organism) — both yield empty, well-formed envelopes.
    return [
        Scenario(
            "unknown_analysis",
            dict(analysis_id=fx.UNKNOWN_CLUSTER_ID,
                 organism=fx.CONTROL_ORGANISM, ontology="kegg", level=1),
            input_ids=[fx.UNKNOWN_CLUSTER_ID]),
        Scenario(
            "analysis_wrong_organism",
            dict(analysis_id=_MED4_ANALYSIS,
                 organism=fx.GENOME_ONLY_ORGANISM, ontology="kegg", level=1),
            input_ids=[_MED4_ANALYSIS]),
    ]


def differential_expression_by_ortholog_scenarios():
    # group_ids batch, cross-organism by design. Nested not_found_groups /
    # not_matched_groups (no flat not_found) — the oracle's batch-diagnostic
    # auto-skips, so input_ids is omitted; the real check is crash-freedom and
    # a well-formed empty envelope. The MIT9515-only group is the cross-
    # organism empty-DE probe (all members live in a genome-only strain with
    # no DE layer). unknown group + mixed batch round out the axes.
    return [
        Scenario(
            "group_members_no_de_organism",
            dict(group_ids=[_GROUP_MIT9515_ONLY])),
        Scenario(
            "unknown_group",
            dict(group_ids=[fx.UNKNOWN_HOMOLOG_GROUP])),
        Scenario(
            "mixed_batch",
            dict(group_ids=[_GROUP_CORE, fx.UNKNOWN_HOMOLOG_GROUP])),
        Scenario(
            "offset_past_end",
            dict(group_ids=[_GROUP_CORE], offset=fx.OFFSET_PAST_END)),
    ]


def genes_by_homolog_group_scenarios():
    # group_ids batch. Nested not_found_groups / not_matched_groups (no flat
    # not_found) — oracle batch-diagnostic auto-skips, input_ids omitted.
    # unknown group -> empty layer; mixed batch -> partial; offset past end.
    return [
        Scenario(
            "unknown_group",
            dict(group_ids=[fx.UNKNOWN_HOMOLOG_GROUP])),
        Scenario(
            "mixed_batch",
            dict(group_ids=[_GROUP_CORE, fx.UNKNOWN_HOMOLOG_GROUP])),
        Scenario(
            "offset_past_end",
            dict(group_ids=[_GROUP_CORE], offset=fx.OFFSET_PAST_END)),
    ]


def genes_in_cluster_scenarios():
    # cluster_ids OR analysis_id (mutually exclusive — supplying both is a
    # documented ValueError -> ToolError). Nested not_found_clusters (no flat
    # not_found) — oracle batch-diagnostic auto-skips, input_ids omitted.
    return [
        Scenario(
            "unknown_cluster",
            dict(cluster_ids=[fx.UNKNOWN_CLUSTER_ID])),
        Scenario(
            "mixed_batch",
            dict(cluster_ids=[_MED4_CLUSTER, fx.UNKNOWN_CLUSTER_ID])),
        Scenario(
            "both_inputs_raises",
            dict(cluster_ids=[_MED4_CLUSTER], analysis_id=_MED4_ANALYSIS),
            expects_error=ToolError),
        Scenario(
            "offset_past_end",
            dict(analysis_id=_MED4_ANALYSIS, offset=fx.OFFSET_PAST_END)),
    ]


def search_homolog_groups_scenarios():
    # Free-text Lucene search; no batch ID input. Degenerate axes: a query
    # that matches no group (empty-layer shape, total_entries>0 but
    # total_matching=0) and offset past end of a populated result set.
    return [
        Scenario(
            "no_hits_search",
            dict(search_text="zzzznonexistentorthologzzz")),
        Scenario(
            "offset_past_end",
            dict(search_text="photosynthesis", offset=fx.OFFSET_PAST_END)),
    ]


# --- Batch C (Task 4.2): discovery / list / search tools ------------------
#
# Cross-organism discovery surfaces with optional filters. Degenerate axes:
# filter-yields-empty (genome-only organism with no pubs/exps/clusters/DMs/
# metabolites), unknown-id filter, pagination past end, and (for the search
# surfaces) a no-hit Lucene query. The empty-data-layer probe stresses the
# envelope rollups (by_organism, by_value_kind, top_*) — these must build a
# well-formed empty envelope, never crash or malform on the filtered-empty set.


def list_publications_scenarios():
    # Cross-organism. FLAT not_found on publication_dois -> input_ids set.
    # genome-only organism has 0 publications -> empty layer, rollups empty.
    return [
        Scenario(
            "genome_only_organism",
            dict(organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "unknown_publication_doi",
            dict(publication_dois=[fx.UNKNOWN_PUBLICATION_DOI]),
            input_ids=[fx.UNKNOWN_PUBLICATION_DOI]),
        Scenario(
            "offset_past_end",
            dict(offset=fx.OFFSET_PAST_END)),
    ]


def list_experiments_scenarios():
    # Cross-organism. FLAT not_found on experiment_ids -> input_ids set.
    # genome-only organism has 0 experiments -> empty layer. summary path also
    # builds breakdowns from an empty set; probe it too.
    return [
        Scenario(
            "genome_only_organism",
            dict(organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "genome_only_organism_summary",
            dict(organism=fx.GENOME_ONLY_ORGANISM, summary=True)),
        Scenario(
            "unknown_experiment_id",
            dict(experiment_ids=[fx.UNKNOWN_EXPERIMENT_ID]),
            input_ids=[fx.UNKNOWN_EXPERIMENT_ID]),
        Scenario(
            "offset_past_end",
            dict(offset=fx.OFFSET_PAST_END)),
    ]


def list_clustering_analyses_scenarios():
    # Cross-organism. NO not_found/not_matched on this response model -> no
    # input_ids; empty-layer shape + crash-freedom are the checks. genome-only
    # organism (MIT9515) has 0 clustering analyses (verified). analysis_ids
    # filter on an unknown id also bottoms out at total_matching=0.
    return [
        Scenario(
            "genome_only_organism",
            dict(organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "unknown_analysis_id",
            dict(analysis_ids=[fx.UNKNOWN_CLUSTER_ID])),
        Scenario(
            "offset_past_end",
            dict(offset=fx.OFFSET_PAST_END)),
    ]


def list_derived_metrics_scenarios():
    # Cross-organism. NO flat not_found (derived_metric_ids filter just yields
    # empty) -> no input_ids. genome-only organism has no DMs (no expression
    # layer). The DM-rich rollups (by_value_kind, by_metric_type, by_compartment)
    # must build empty on the filtered-empty set.
    return [
        Scenario(
            "genome_only_organism",
            dict(organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "unknown_derived_metric_id",
            dict(derived_metric_ids=[fx.UNKNOWN_DERIVED_METRIC_ID])),
        Scenario(
            "offset_past_end",
            dict(offset=fx.OFFSET_PAST_END)),
    ]


def list_metabolites_scenarios():
    # Cross-organism. Structured not_found (MetNotFound buckets) -> oracle
    # batch-diagnostic auto-skips, input_ids omitted. unknown metabolite_ids
    # -> empty layer; organism_names filter on genome-only organism (no
    # metabolomics) -> empty; search_text no-hit; offset past end.
    return [
        Scenario(
            "unknown_metabolite_id",
            dict(metabolite_ids=[fx.UNKNOWN_METABOLITE_ID])),
        Scenario(
            "genome_only_organism",
            dict(organism_names=[fx.GENOME_ONLY_ORGANISM])),
        Scenario(
            "no_hits_search",
            dict(search_text="zzzznonexistentmetabolitezzz")),
    ]


def list_metabolite_assays_scenarios():
    # Cross-organism. Structured not_found (LmaNotFound buckets) -> oracle
    # batch-diagnostic auto-skips, input_ids omitted. genome-only organism has
    # no MetaboliteAssay nodes -> empty layer; the rich rollups (by_organism,
    # by_value_kind, by_detection_status) must build empty. unknown assay_ids
    # and offset round out the axes.
    return [
        Scenario(
            "genome_only_organism",
            dict(organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "unknown_assay_id",
            dict(assay_ids=["assay_does_not_exist"])),
        Scenario(
            "offset_past_end",
            dict(offset=fx.OFFSET_PAST_END)),
    ]


def search_ontology_scenarios():
    # Free-text Lucene search; no batch ID input. Degenerate axes: a query
    # that matches no term (empty-layer shape: total_entries>0 but
    # total_matching=0) and offset past end of a populated result set.
    return [
        Scenario(
            "no_hits_search",
            dict(search_text="zzzznonexistentontologytermzzz", ontology="kegg")),
        Scenario(
            "offset_past_end",
            dict(search_text="transport", ontology="kegg",
                 offset=fx.OFFSET_PAST_END)),
    ]


def ontology_landscape_scenarios():
    # organism is REQUIRED. genome-only organism (genome present, no
    # expression layer) is the key probe: experiment-weighted coverage paths
    # must not crash when there are no quantified genes. unknown experiment_ids
    # weighting on a control organism also bottoms out at empty weighting.
    return [
        Scenario(
            "genome_only_organism",
            dict(organism=fx.GENOME_ONLY_ORGANISM, ontology="kegg")),
        Scenario(
            "genome_only_organism_experiment_weighted",
            dict(organism=fx.GENOME_ONLY_ORGANISM, ontology="kegg",
                 experiment_ids=[fx.UNKNOWN_EXPERIMENT_ID])),
        Scenario(
            "unknown_experiment_weighting",
            dict(organism=fx.CONTROL_ORGANISM, ontology="kegg",
                 experiment_ids=[fx.UNKNOWN_EXPERIMENT_ID])),
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
    # Batch B
    "pathway_enrichment": pathway_enrichment_scenarios,
    "cluster_enrichment": cluster_enrichment_scenarios,
    "differential_expression_by_ortholog": differential_expression_by_ortholog_scenarios,
    "genes_by_homolog_group": genes_by_homolog_group_scenarios,
    "genes_in_cluster": genes_in_cluster_scenarios,
    "search_homolog_groups": search_homolog_groups_scenarios,
    # Batch C
    "list_publications": list_publications_scenarios,
    "list_experiments": list_experiments_scenarios,
    "list_clustering_analyses": list_clustering_analyses_scenarios,
    "list_derived_metrics": list_derived_metrics_scenarios,
    "list_metabolites": list_metabolites_scenarios,
    "list_metabolite_assays": list_metabolite_assays_scenarios,
    "search_ontology": search_ontology_scenarios,
    "ontology_landscape": ontology_landscape_scenarios,
}
