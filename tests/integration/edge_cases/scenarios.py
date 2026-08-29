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
        # --- annotation-trust surface (PR 3a) ---
        Scenario(
            # KEGG edges carry sources + evidence only — max_tier is not one
            # of its axes, so validation must raise before any query runs.
            "unsupported_trust_axis",
            dict(ontology="kegg", organism=fx.CONTROL_ORGANISM, level=1,
                 max_tier=2),
            expects_error=ToolError),
        Scenario(
            "call_class_on_non_merops",
            dict(ontology="tcdb", organism=fx.CONTROL_ORGANISM, level=2,
                 call_class=["peptidase"]),
            expects_error=ToolError),
        Scenario(
            "interpro_type_on_non_interpro",
            dict(ontology="tcdb", organism=fx.CONTROL_ORGANISM, level=2,
                 interpro_type="FAMILY"),
            expects_error=ToolError),
        Scenario(
            # tier is null on eggNOG-only TCDB edges; max_tier keeps them and
            # the envelope must show the explicit "null" bucket + a warning.
            "max_tier_keeps_tier_null_rows",
            dict(ontology="tcdb", organism=fx.CONTROL_ORGANISM, level=2,
                 max_tier=3)),
        Scenario(
            # every MEROPS row in a cyanobacterium is a dead homolog at most —
            # filtering to peptidase can legitimately empty the result.
            "call_class_zero_rows",
            dict(ontology="merops", organism=fx.GENOME_ONLY_ORGANISM, level=0,
                 call_class=["peptidase"])),
        Scenario(
            "interpro_stratum_with_no_terms",
            dict(ontology="interpro", organism=fx.GENOME_ONLY_ORGANISM,
                 level=0, interpro_type="PTM")),
        Scenario(
            "min_evidence_score_above_every_edge",
            dict(ontology="tcdb", organism=fx.CONTROL_ORGANISM, level=2,
                 min_evidence_score=1.1)),
        Scenario(
            "ncbifam_genome_only_organism",
            dict(ontology="ncbifam", organism=fx.GENOME_ONLY_ORGANISM,
                 level=0)),
        Scenario(
            # A facet must narrow term_ids mode too — enrichment forces the
            # caller to name an InterPro stratum, so it cannot be a no-op
            # here. A stratum that matches none of the input terms is an
            # empty envelope, not an error.
            "term_ids_with_a_facet_that_matches_nothing",
            dict(ontology="interpro", organism=fx.CONTROL_ORGANISM,
                 term_ids=["interpro:IPR027417"], interpro_type="PTM",
                 min_gene_set_size=0)),
        Scenario(
            "term_ids_with_a_facet_the_ontology_does_not_own",
            dict(ontology="interpro", organism=fx.CONTROL_ORGANISM,
                 term_ids=["interpro:IPR027417"], tree="transporters"),
            expects_error=ToolError),
        Scenario(
            # Compact (default) mode must still carry the trust envelope:
            # by_tier's null bucket and the tier-null auto-warning are the
            # only place a compact reader meets tier at all.
            "tier_null_bucket_visible_in_compact",
            dict(ontology="tcdb", organism=fx.CONTROL_ORGANISM, level=2,
                 max_tier=3, verbose=False)),
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
        # --- annotation-trust surface (PR 3a) ---
        Scenario(
            # Cyanobacterial gene with no MEROPS / NCBIfam signal: the new
            # columns must default ([] / 0) and merops_evidence_score_max
            # must stay null rather than coalescing to 0.
            "gene_without_protease_or_family_signal",
            dict(locus_tags=[fx.GENE_NO_DE]),
            input_ids=[fx.GENE_NO_DE]),
        Scenario(
            "gene_with_merops_call",
            dict(locus_tags=["MIT1002_03660"]),
            input_ids=["MIT1002_03660"]),
        # --- backlog 3.4: TCDB / CAZy family counts ---
        Scenario(
            # Alteromonas gene with CAZy calls but no TCDB call:
            # cazy_family_count=4, tcdb_family_count=0.
            "gene_with_cazy_only",
            dict(locus_tags=["HP15_1897"]),
            input_ids=["HP15_1897"]),
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


# --- Slice 4 (2026-08-27) fixtures ------------------------------------------
# OrganismTaxon whose four annotation rollups are all 0 (treatment taxon,
# 0 genes) -> must be EXCLUDED from list_organisms.top_annotation_capability.
# MATCH (o:OrganismTaxon) WHERE coalesce(o.peptidase_gene_count,0)=0
#   AND coalesce(o.nonpeptidase_homolog_gene_count,0)=0
#   AND coalesce(o.interpro_gene_count,0)=0 AND coalesce(o.ncbifam_gene_count,0)=0
#   RETURN o.preferred_name
_ALL_ZERO_ROLLUP_ORGANISM = "Phage"
# The Steglich 2010 mRNA-decay analysis: a characterization experiment with
# `treatment_type == ['rna_decay']` (KG contract v2: dense, non-empty) — must be a
# well-formed row on both cluster tools, never a ToolError.
# MATCH (ca:ClusteringAnalysis) WHERE ca.cluster_type = 'decay_pattern' RETURN ca.id
_DECAY_ANALYSIS_ID = "clustering_analysis:gb-2010-11-5-r54:decay_clusters"
_DECAY_ANALYSIS_GENE = "PMM2072"    # MED4 gene inside one of its clusters


def list_organisms_scenarios():
    return [
        Scenario(
            "unknown_organism_name",
            dict(organism_names=["Nonexistus fakeii"]),
            input_ids=["Nonexistus fakeii"]),
        # Slice 4 (spec §8): a subset whose only member has all-zero
        # annotation rollups -> top_annotation_capability == [] but the row
        # itself is still returned (coverage counts are for reading).
        Scenario(
            "all_zero_annotation_rollups_subset",
            dict(organism_names=[_ALL_ZERO_ROLLUP_ORGANISM]),
            input_ids=[_ALL_ZERO_ROLLUP_ORGANISM]),
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
        # --- annotation-trust surface (PR 3a) ---
        Scenario(
            # No ontology in the set carries max_tier -> hard raise.
            "multi_ontology_all_skipped",
            dict(locus_tags=["PMM0001"], organism=fx.CONTROL_ORGANISM,
                 ontology=["kegg", "go_bp"], max_tier=2),
            expects_error=ToolError),
        Scenario(
            # Some carry it -> apply where possible, skip the rest + warn.
            "multi_ontology_partial_skip",
            dict(locus_tags=["PMM0001"], organism=fx.CONTROL_ORGANISM,
                 ontology=["tcdb", "kegg"], max_tier=2)),
        Scenario(
            "facet_owner_absent_from_set",
            dict(locus_tags=["PMM0001"], organism=fx.CONTROL_ORGANISM,
                 ontology=["kegg", "tcdb"], interpro_type="FAMILY"),
            expects_error=ToolError),
        Scenario(
            "unknown_ontology_in_list",
            dict(locus_tags=["PMM0001"], organism=fx.CONTROL_ORGANISM,
                 ontology=["not_an_ontology"]),
            expects_error=ToolError),
        Scenario(
            # PMM0392 has superseded TCDB attachments; the leaf rows must be
            # most-specific-only by default and gain the labelled rows here.
            "include_superseded_tcdb_leaf",
            dict(locus_tags=["PMM0392"], organism=fx.CONTROL_ORGANISM,
                 ontology=["tcdb"], mode="leaf", include_superseded=True)),
        Scenario(
            "merops_call_class_zero_rows",
            dict(locus_tags=["PMM0001"], organism=fx.CONTROL_ORGANISM,
                 ontology=["merops"], call_class=["peptidase"])),
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
        # Axis 4 (null props): a valid gene whose strand/start/contig are null
        # cannot be positioned — must land in not_matched, never crash.
        Scenario(
            "anchor_null_coordinates",
            dict(locus_tags=[fx.GENE_NO_COORDINATES]),
            input_ids=[fx.GENE_NO_COORDINATES]),
        # And the documented same_strand path on a null-strand anchor must not
        # crash (warn + unfiltered).
        Scenario(
            "anchor_null_strand_same_strand_filter",
            dict(locus_tags=[fx.GENE_NO_COORDINATES], same_strand=True),
            input_ids=[fx.GENE_NO_COORDINATES]),
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
        # Slice 4 (spec §3.4 v1.2): the treatment-less characterization
        # analysis (treatment_type == ['rna_decay']) — was a ToolError on the
        # first KG-SYNC-006 build (null list); now a well-formed row.
        Scenario(
            "characterization_analysis_no_treatment",
            dict(locus_tags=[_DECAY_ANALYSIS_GENE], organism=fx.CONTROL_ORGANISM,
                 analysis_ids=[_DECAY_ANALYSIS_ID]),
            input_ids=[_DECAY_ANALYSIS_GENE]),
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
        # --- annotation-trust surface (PR 3a) ---
        Scenario(
            # InterPro mixes 8 non-comparable strata; ORA over the union is
            # meaningless, so the stratum is required.
            "interpro_without_stratum",
            dict(organism=fx.CONTROL_ORGANISM,
                 experiment_ids=[_MED4_DE_EXP], ontology="interpro", level=0),
            expects_error=ToolError),
        Scenario(
            "interpro_stratum_with_no_testable_terms",
            dict(organism=fx.CONTROL_ORGANISM,
                 experiment_ids=[_MED4_DE_EXP], ontology="interpro", level=0,
                 interpro_type="PTM")),
        Scenario(
            "unsupported_trust_axis",
            dict(organism=fx.CONTROL_ORGANISM,
                 experiment_ids=[_MED4_DE_EXP], ontology="kegg", level=1,
                 max_tier=2),
            expects_error=ToolError),
        Scenario(
            # Filters shape the tested sets AND the background identically.
            "trust_filtered_background",
            dict(organism=fx.CONTROL_ORGANISM,
                 experiment_ids=[_MED4_DE_EXP], ontology="tcdb", level=2,
                 max_tier=2)),
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
        # --- annotation-trust surface (PR 3a) ---
        Scenario(
            "interpro_without_stratum",
            dict(analysis_id=_MED4_ANALYSIS, organism=fx.CONTROL_ORGANISM,
                 ontology="interpro", level=0),
            expects_error=ToolError),
        Scenario(
            "unsupported_trust_axis",
            dict(analysis_id=_MED4_ANALYSIS, organism=fx.CONTROL_ORGANISM,
                 ontology="kegg", level=1, max_tier=2),
            expects_error=ToolError),
        Scenario(
            "merops_call_class_zero_rows",
            dict(analysis_id=_MED4_ANALYSIS, organism=fx.CONTROL_ORGANISM,
                 ontology="merops", level=0, call_class=["peptidase"])),
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
        # Slice 4 (spec §3.4 v1.2): characterization analysis with
        # treatment_type == ['rna_decay'] -> well-formed row, never a raise.
        Scenario(
            "characterization_analysis_no_treatment",
            dict(analysis_ids=[_DECAY_ANALYSIS_ID])),
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
        Scenario(
            # backlog 3.2: bare KEGG C-number coerced to kegg.compound:C00064
            # via xrefs before the builder runs; must not land in not_found.
            "bare_metabolite_id",
            dict(metabolite_ids=[_BARE_KEGG_ID])),
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
        Scenario(
            # backlog 3.2: bare metabolite id coerced before the builder runs.
            "bare_metabolite_id",
            dict(metabolite_ids=[_BARE_PEP_ID])),
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
        # --- annotation-trust surface (PR 3a) ---
        Scenario(
            "no_hits_new_ontology",
            dict(search_text="zzzznonexistentontologytermzzz",
                 ontology="merops")),
        Scenario(
            "interpro_type_facet",
            dict(search_text="kinase", ontology="interpro",
                 interpro_type="DOMAIN")),
        Scenario(
            "interpro_type_on_non_interpro",
            dict(search_text="transport", ontology="kegg",
                 interpro_type="DOMAIN"),
            expects_error=ToolError),
        Scenario(
            "ncbifam_search",
            dict(search_text="protein", ontology="ncbifam")),
        # --- PR 3b: browse mode + multi-ontology ---
        Scenario(
            # No search_text = browse; a level no MEROPS term reaches gives
            # the empty-layer shape (total_entries>0, total_matching=0).
            "browse_level_with_no_terms",
            dict(ontology="merops", level=99)),
        Scenario(
            "browse_offset_past_end",
            dict(ontology="merops", level=1, offset=fx.OFFSET_PAST_END)),
        Scenario(
            "browse_min_gene_count_above_max",
            dict(ontology="tcdb", min_gene_count=10_000_000)),
        Scenario(
            # Genome-only organism scope: every org_gene_count is 0.
            "browse_genome_only_organism_scope",
            dict(ontology="merops", organism=fx.GENOME_ONLY_ORGANISM,
                 min_gene_count=1)),
        Scenario(
            "browse_empty_string_search_text",
            dict(search_text="", ontology="merops", level=1)),
        Scenario(
            # ontology=None fans out to all 17 registry keys in browse mode;
            # limit=1 keeps one row per ontology (lockstep paging) so the
            # envelope is populated, not a summary=True empty results list.
            "browse_all_ontologies_fanout",
            dict(ontology=None, limit=1)),
        Scenario(
            "multi_no_hits",
            dict(search_text="zzzznonexistentontologytermzzz",
                 ontology=["go_bp", "tcdb", "merops"])),
        Scenario(
            "multi_unknown_ontology_name",
            dict(search_text="transport", ontology=["go_bp", "nope"]),
            expects_error=ToolError),
        Scenario(
            "multi_facet_owner_absent",
            dict(search_text="kinase", ontology=["kegg", "tcdb"],
                 interpro_type="DOMAIN"),
            expects_error=ToolError),
        Scenario(
            "multi_tree_owner_absent",
            dict(search_text="transport", ontology=["kegg", "tcdb"],
                 tree="transporters"),
            expects_error=ToolError),
        Scenario(
            "multi_offset_past_end",
            dict(search_text="transport", ontology=["go_bp", "tcdb"],
                 offset=fx.OFFSET_PAST_END)),
    ]


def list_filter_values_scenarios():
    # No entity input; the degenerate axes are the vocabulary-backed filter
    # types (ControlledVocabulary read -> pivot fallback -> warning) and the
    # `ontology` scope. An unknown filter_type is a documented raise.
    return [
        Scenario("evidence", dict(filter_type="evidence")),
        Scenario("sources", dict(filter_type="sources")),
        Scenario("call_class", dict(filter_type="call_class")),
        Scenario("interpro_type", dict(filter_type="interpro_type")),
        Scenario("attachment_depth", dict(filter_type="attachment_depth")),
        Scenario("trust_axes_scoped",
                 dict(filter_type="trust_axes", ontology="kegg")),
        Scenario("link_kinds", dict(filter_type="link_kinds")),
        Scenario("unknown_filter_type",
                 dict(filter_type="not_a_filter_type"),
                 expects_error=ToolError),
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
        # --- annotation-trust surface (PR 3a) ---
        Scenario(
            "interpro_stratum_rows",
            dict(organism=fx.CONTROL_ORGANISM, ontology="interpro")),
        Scenario(
            "multi_ontology_list",
            dict(organism=fx.CONTROL_ORGANISM,
                 ontology=["tcdb", "merops", "ncbifam"])),
        Scenario(
            "unknown_ontology_in_list",
            dict(organism=fx.CONTROL_ORGANISM, ontology=["not_an_ontology"]),
            expects_error=ToolError),
        Scenario(
            "call_class_on_non_merops",
            dict(organism=fx.CONTROL_ORGANISM, ontology="tcdb",
                 call_class=["peptidase"]),
            expects_error=ToolError),
        Scenario(
            "merops_call_class_genome_only",
            dict(organism=fx.GENOME_ONLY_ORGANISM, ontology="merops",
                 call_class=["peptidase"])),
    ]


# --- Batch D (Task 4.2): metabolite/assay drill-downs + discusses ---------
#
# Real IDs discovered against the live KG (2026-06-15, branch
# fix/organism-resolver-genome-only):
#   Metabolites:
#     kegg.compound:C00086  urea — gene catalysts + transporters in MED4
#     kegg.compound:C00074  PEP — measured (18 quantifies + 2 flags edges)
#     kegg.compound:C00001  H2O — EXISTS as Metabolite, ZERO assay edges
#                                  (assays_by_metabolite not_matched probe)
#   Assays (from test_mcp_tools.py §7 baselines):
#     metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:
#       cellular_concentration                       (numeric, 64 edges)
#     metabolite_assay:msystems.01261-22:presence_flags_table_s2:
#       presence_flag_intracellular                  (boolean, 93 edges)
#   Publications:
#     10.1038/ismej.2016.70  discusses genes + pathways (baseline)
#     10.1126/science.1243457 / 10.1128/mbio.03425-22 /
#       10.1128/mSystems.00008-17  present but NO discusses edge (not_matched)
#
# Chemistry is genome-derived and present in every organism with genes (even
# the genome-only MIT9515 has 1222 catalyzing genes), so an "empty chemistry
# layer via organism" probe is not achievable — the empty-shape probes here
# lean on unknown/unlinked metabolite IDs and offset-past-end instead. The
# genome-only-organism probe still exercises the single-organism drill-down
# path on a no-DE strain (crash-freedom).

_UREA_ID = "kegg.compound:C00086"          # gene catalysts + transporters (MED4)
_PEP_ID = "kegg.compound:C00074"           # measured: 18 quantifies + 2 flags
_H2O_NO_ASSAY_ID = "kegg.compound:C00001"  # Metabolite node, zero assay edges
_NUMERIC_ASSAY = (
    "metabolite_assay:pnas.2213271120:"
    "metabolites_intracellular_mit9313:cellular_concentration")
_BOOLEAN_ASSAY = (
    "metabolite_assay:msystems.01261-22:"
    "presence_flags_table_s2:presence_flag_intracellular")
_DISCUSSES_DOI = "10.1038/ismej.2016.70"          # discusses genes + pathways
_NO_DISCUSSES_DOI = "10.1126/science.1243457"     # present, no discusses edge
_UNKNOWN_ASSAY_ID = "metabolite_assay:does_not_exist"
# backlog 3.2 (bare metabolite-ID coercion): un-prefixed forms of ids above.
_BARE_UREA_ID = "C00086"   # -> _UREA_ID
_BARE_PEP_ID = "C00074"    # -> _PEP_ID
_BARE_KEGG_ID = "C00064"   # L-glutamate, kegg.compound:C00064


def genes_by_metabolite_scenarios():
    # metabolite IDs -> gene catalysts/transporters. SINGLE-ORGANISM enforced
    # (organism required). Structured not_found (GbmNotFound) + flat
    # not_matched — the oracle's batch-diagnostic only handles flat not_found,
    # so input_ids is omitted (structured not_found auto-skips); crash-freedom
    # + empty-shape are the real checks. Urea on the genome-only (no-DE) strain
    # exercises the drill-down path on a strain that still has chemistry.
    return [
        Scenario(
            "unknown_metabolite",
            dict(metabolite_ids=[fx.UNKNOWN_METABOLITE_ID],
                 organism=fx.CONTROL_ORGANISM)),
        Scenario(
            "genome_only_organism",
            dict(metabolite_ids=[_UREA_ID],
                 organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "offset_past_end",
            dict(metabolite_ids=[_UREA_ID], organism=fx.CONTROL_ORGANISM,
                 offset=fx.OFFSET_PAST_END)),
        # TCDB substrate_depth migration (spec 2026-08-20): the retired
        # `transport_confidence` value strings are a DOCUMENTED raise with a
        # rename pointer (api ValueError -> ToolError), as is any unknown value.
        Scenario(
            "old_transport_confidence_value_substrate_confirmed",
            dict(metabolite_ids=[_UREA_ID], organism=fx.CONTROL_ORGANISM,
                 substrate_depth=["substrate_confirmed"]),
            expects_error=ToolError),
        Scenario(
            "old_transport_confidence_value_family_inferred",
            dict(metabolite_ids=[_UREA_ID], organism=fx.CONTROL_ORGANISM,
                 substrate_depth=["family_inferred"]),
            expects_error=ToolError),
        Scenario(
            "unknown_substrate_depth_value",
            dict(metabolite_ids=[_UREA_ID], organism=fx.CONTROL_ORGANISM,
                 substrate_depth=["bogus"]),
            expects_error=ToolError),
        Scenario(
            # Valid filter narrowing the transport arm on a real slice -> must
            # stay a well-formed (possibly empty) envelope, never a raise.
            "substrate_depth_most_specific_filter",
            dict(metabolite_ids=[_UREA_ID], organism=fx.CONTROL_ORGANISM,
                 substrate_depth=["most_specific"])),
        Scenario(
            # backlog 3.2: bare urea C-number resolves to _UREA_ID (same rows).
            "bare_metabolite_id",
            dict(metabolite_ids=[_BARE_UREA_ID], organism=fx.CONTROL_ORGANISM)),
    ]


def metabolites_by_gene_scenarios():
    # gene locus_tags -> metabolites. SINGLE-ORGANISM enforced. Structured
    # not_found (MbgNotFound) -> input_ids omitted. PMM1720 (the no-DE gene)
    # has zero chemistry edges (verified) -> not_matched probe on a real gene.
    return [
        Scenario(
            "unknown_locus",
            dict(locus_tags=[fx.UNKNOWN_LOCUS], organism=fx.CONTROL_ORGANISM)),
        Scenario(
            "gene_no_chemistry",
            dict(locus_tags=[fx.GENE_NO_DE], organism=fx.CONTROL_ORGANISM)),
        Scenario(
            "genome_only_organism",
            dict(locus_tags=["PMM0001"], organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "offset_past_end",
            dict(locus_tags=["PMM0963"], organism=fx.CONTROL_ORGANISM,
                 offset=fx.OFFSET_PAST_END)),
        # TCDB substrate_depth migration (mirrors GBM): retired value strings
        # + unknown values are a documented raise; the valid filter is not.
        Scenario(
            "old_transport_confidence_value_substrate_confirmed",
            dict(locus_tags=["PMM0963"], organism=fx.CONTROL_ORGANISM,
                 substrate_depth=["substrate_confirmed"]),
            expects_error=ToolError),
        Scenario(
            "old_transport_confidence_value_family_inferred",
            dict(locus_tags=["PMM0963"], organism=fx.CONTROL_ORGANISM,
                 substrate_depth=["family_inferred"]),
            expects_error=ToolError),
        Scenario(
            "unknown_substrate_depth_value",
            dict(locus_tags=["PMM0963"], organism=fx.CONTROL_ORGANISM,
                 substrate_depth=["bogus"]),
            expects_error=ToolError),
        Scenario(
            "substrate_depth_inherited_filter",
            dict(locus_tags=["PMM0963"], organism=fx.CONTROL_ORGANISM,
                 substrate_depth=["inherited"])),
        Scenario(
            # backlog 3.2: bare metabolite id as a filter is coerced first.
            "bare_metabolite_id_filter",
            dict(locus_tags=["PMM0963"], organism=fx.CONTROL_ORGANISM,
                 metabolite_ids=[_BARE_UREA_ID])),
    ]


def metabolites_by_quantifies_assay_scenarios():
    # Numeric drill-down on Assay_quantifies_metabolite. Cross-organism;
    # needs assay_ids or metabolite_ids. Structured not_found (MqaNotFound) ->
    # input_ids omitted. Unknown assay -> empty layer; unknown metabolite is a
    # filter on a real assay that strips every row -> empty filtered set
    # (assay_ids is required at the wrapper layer, so metabolite-only is not a
    # valid call — scenario fix); offset past end of a populated assay.
    return [
        Scenario(
            "unknown_assay",
            dict(assay_ids=[_UNKNOWN_ASSAY_ID])),
        Scenario(
            "unknown_metabolite_filter",
            dict(assay_ids=[_NUMERIC_ASSAY],
                 metabolite_ids=[fx.UNKNOWN_METABOLITE_ID])),
        Scenario(
            "offset_past_end",
            dict(assay_ids=[_NUMERIC_ASSAY], offset=fx.OFFSET_PAST_END)),
        Scenario(
            # backlog 3.2: bare PEP C-number coerced before the edge filter.
            "bare_metabolite_id_filter",
            dict(assay_ids=[_NUMERIC_ASSAY], metabolite_ids=[_BARE_PEP_ID])),
    ]


def metabolites_by_flags_assay_scenarios():
    # Boolean drill-down on Assay_flags_metabolite. Cross-organism. Structured
    # not_found (MfaNotFound) -> input_ids omitted. Unknown assay -> empty;
    # unknown metabolite is a filter on a real assay that strips every row
    # (assay_ids required at the wrapper layer -> metabolite-only not a valid
    # call, scenario fix); offset past end of a populated boolean assay.
    return [
        Scenario(
            "unknown_assay",
            dict(assay_ids=[_UNKNOWN_ASSAY_ID])),
        Scenario(
            "unknown_metabolite_filter",
            dict(assay_ids=[_BOOLEAN_ASSAY],
                 metabolite_ids=[fx.UNKNOWN_METABOLITE_ID])),
        Scenario(
            "offset_past_end",
            dict(assay_ids=[_BOOLEAN_ASSAY], offset=fx.OFFSET_PAST_END)),
        Scenario(
            # backlog 3.2: bare PEP C-number coerced before the edge filter.
            "bare_metabolite_id_filter",
            dict(assay_ids=[_BOOLEAN_ASSAY], metabolite_ids=[_BARE_PEP_ID])),
    ]


def assays_by_metabolite_scenarios():
    # metabolite IDs -> all measurement evidence (both arms). Cross-organism.
    # FLAT not_found (list[str]) + flat not_matched -> input_ids SET. H2O
    # (C00001) exists as a Metabolite but has zero assay edges -> not_matched
    # (the empty-after-filter probe). Unknown id -> not_found.
    return [
        Scenario(
            "unknown_metabolite",
            dict(metabolite_ids=[fx.UNKNOWN_METABOLITE_ID]),
            input_ids=[fx.UNKNOWN_METABOLITE_ID]),
        Scenario(
            "metabolite_no_measurement",
            dict(metabolite_ids=[_H2O_NO_ASSAY_ID]),
            input_ids=[_H2O_NO_ASSAY_ID]),
        Scenario(
            "offset_past_end",
            dict(metabolite_ids=[_PEP_ID], offset=fx.OFFSET_PAST_END)),
        Scenario(
            # backlog 3.2: bare PEP C-number coerced to _PEP_ID; resolved input
            # never appears in the flat not_found, so input_ids is omitted.
            "bare_metabolite_id",
            dict(metabolite_ids=[_BARE_PEP_ID])),
    ]


def discussed_by_publication_scenarios():
    # publication DOIs -> discussed genes/pathways. Cross-organism. FLAT
    # not_found + not_matched (list[str]) -> input_ids SET. Three real pubs
    # have no discusses edge (not_matched); unknown DOI -> not_found; offset
    # past end of a discussing pub.
    return [
        Scenario(
            "unknown_doi",
            dict(publication_dois=[fx.UNKNOWN_PUBLICATION_DOI]),
            input_ids=[fx.UNKNOWN_PUBLICATION_DOI]),
        Scenario(
            "doi_no_discusses_edge",
            dict(publication_dois=[_NO_DISCUSSES_DOI]),
            input_ids=[_NO_DISCUSSES_DOI]),
        Scenario(
            "offset_past_end",
            dict(publication_dois=[_DISCUSSES_DOI], offset=fx.OFFSET_PAST_END)),
    ]


# --- Batch E (Task 4.2): DerivedMetric drill-downs ------------------------
#
# DM gate properties discovered against the live KG (2026-06-15, branch
# fix/organism-resolver-genome-only):
#   genes_by_numeric_metric:
#     damping_ratio        rankable=True,  has_p_value=False, value_max=25.3
#     peak_time_protein_h  rankable=False, has_p_value=False (bucket -> raise)
#     (NO DM in the KG carries p-values -> significant_only=True -> raise)
#   genes_by_boolean_metric:
#     vesicle_proteome_member  (positive-only storage; flag=False -> 0 rows)
#   genes_by_categorical_metric:
#     predicted_subcellular_localization
#       allowed_categories incl. 'Outer Membrane','Periplasmic','Cytoplasmic',
#       'Unknown', ... ; an unknown category -> ValueError -> ToolError.
#
# All three tools surface unknown / wrong-kind DM IDs as `not_found_ids`
# (NOT a flat not_found/not_matched the batch oracle understands), so
# input_ids is left empty on every scenario. Gated-filter raises
# (rankable bucket on non-rankable DM, significant_only with no p-value DM,
# unknown category) are DOCUMENTED contract -> expects_error=ToolError.
# Impossible value thresholds / flag=False are CORRECT empty results, not
# raises — they stress the by_metric / by_value rollups on an empty slice.

_DM_RANKABLE_NUMERIC = "damping_ratio"        # rankable=True, value_max=25.3
_DM_NONRANKABLE_NUMERIC = "peak_time_protein_h"  # rankable=False -> bucket raises
_DM_BOOLEAN = "vesicle_proteome_member"       # positive-only storage
_DM_CATEGORICAL = "predicted_subcellular_localization"


def genes_by_numeric_metric_scenarios():
    return [
        Scenario(
            # Unknown DM id -> not_found_ids (no raise), empty results.
            "unknown_derived_metric_id",
            dict(derived_metric_ids=[fx.UNKNOWN_DERIVED_METRIC_ID])),
        Scenario(
            # Valid rankable DM, impossible value threshold -> empty slice,
            # well-formed envelope (by_metric rollup on zero rows). NOT a raise.
            "impossible_value_threshold",
            dict(metric_types=[_DM_RANKABLE_NUMERIC], min_value=1.0e9)),
        Scenario(
            # rankable-GATED bucket on an all-non-rankable DM -> documented raise.
            "rankable_filter_non_rankable_dm",
            dict(metric_types=[_DM_NONRANKABLE_NUMERIC], bucket=["top_decile"]),
            expects_error=ToolError),
        Scenario(
            # has_p_value-GATED significance filter, no DM carries p-values ->
            # documented raise ("raises today").
            "p_value_filter_unsupported",
            dict(metric_types=[_DM_RANKABLE_NUMERIC], significant_only=True),
            expects_error=ToolError),
        Scenario(
            "offset_past_end",
            dict(metric_types=[_DM_RANKABLE_NUMERIC], offset=fx.OFFSET_PAST_END)),
    ]


def genes_by_boolean_metric_scenarios():
    return [
        Scenario(
            # Unknown DM id -> not_found_ids, empty results (no raise).
            "unknown_derived_metric_id",
            dict(derived_metric_ids=[fx.UNKNOWN_DERIVED_METRIC_ID])),
        Scenario(
            # flag=False -> 0 rows (positive-only KG storage today). CORRECT
            # empty result, stresses by_value rollup on an empty slice.
            "flag_false_empty",
            dict(metric_types=[_DM_BOOLEAN], flag=False)),
        Scenario(
            "offset_past_end",
            dict(metric_types=[_DM_BOOLEAN], offset=fx.OFFSET_PAST_END)),
    ]


def genes_by_categorical_metric_scenarios():
    return [
        Scenario(
            # Unknown DM id -> not_found_ids, empty results (no raise).
            "unknown_derived_metric_id",
            dict(derived_metric_ids=[fx.UNKNOWN_DERIVED_METRIC_ID])),
        Scenario(
            # Unknown category -> ValueError -> ToolError (documented; message
            # lists the allowed-category union).
            "unknown_category_raises",
            dict(metric_types=[_DM_CATEGORICAL], categories=["nonsense_category"]),
            expects_error=ToolError),
        Scenario(
            # Valid DM + valid category + a locus_tag set with no membership ->
            # empty slice, well-formed by_category rollup. NOT a raise.
            "valid_category_empty_slice",
            dict(metric_types=[_DM_CATEGORICAL],
                 categories=["Outer Membrane"],
                 locus_tags=[fx.UNKNOWN_LOCUS])),
        Scenario(
            "offset_past_end",
            dict(metric_types=[_DM_CATEGORICAL],
                 categories=["Outer Membrane", "Periplasmic"],
                 offset=fx.OFFSET_PAST_END)),
    ]


# Registry: tool name -> builder. Phase 4 fills the rest.

def ontology_term_details_scenarios():
    # Batch, cross-ontology term drill-down. Degenerate axes: missing / mixed
    # batch (flat not_found), empty input (documented ToolError), a
    # link_kinds filter that removes every bridge, offset beyond the found
    # rows, and verbose on a flat-ontology term (no hierarchy, no bridges).
    return [
        Scenario(
            "unknown_term",
            dict(term_ids=[fx.UNKNOWN_ONTOLOGY_TERM]),
            input_ids=[fx.UNKNOWN_ONTOLOGY_TERM]),
        Scenario(
            "mixed_batch",
            dict(term_ids=["tcdb:3.A.1", fx.UNKNOWN_ONTOLOGY_TERM]),
            input_ids=["tcdb:3.A.1", fx.UNKNOWN_ONTOLOGY_TERM]),
        Scenario(
            "empty_term_ids",
            dict(term_ids=[]),
            expects_error=ToolError),
        Scenario(
            # go:0006979 has no bridges; a router-only filter on a TCDB family
            # strips its composition links -> links_out=[] on every row.
            "link_kinds_filters_everything_out",
            dict(term_ids=["go:0006979", "tcdb:3.A.1"], link_kinds=["router"]),
            input_ids=["go:0006979", "tcdb:3.A.1"]),
        Scenario(
            "offset_past_end",
            dict(term_ids=["tcdb:3.A.1", "go:0006979"],
                 offset=fx.OFFSET_PAST_END),
            input_ids=["tcdb:3.A.1", "go:0006979"]),
        Scenario(
            "verbose_flat_ontology_term",
            dict(term_ids=["ncbifam:NF000812"], verbose=True),
            input_ids=["ncbifam:NF000812"]),
        Scenario(
            # Genome-only organism: every term has 0 genes there; the scoped
            # count is 0, never a crash.
            "genome_only_organism_scope",
            dict(term_ids=["tcdb:3.A.1"], organism=fx.GENOME_ONLY_ORGANISM,
                 verbose=True),
            input_ids=["tcdb:3.A.1"]),
        Scenario(
            "unknown_link_kind",
            dict(term_ids=["tcdb:3.A.1"], link_kinds=["sideways"]),
            expects_error=ToolError),
    ]


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
    # Annotation-trust surface (PR 3a): the vocabulary-backed filter types
    # give list_filter_values real degenerate axes (vocab -> pivot -> warning).
    "list_filter_values": list_filter_values_scenarios,
    # Batch D
    "genes_by_metabolite": genes_by_metabolite_scenarios,
    "metabolites_by_gene": metabolites_by_gene_scenarios,
    "metabolites_by_quantifies_assay": metabolites_by_quantifies_assay_scenarios,
    "metabolites_by_flags_assay": metabolites_by_flags_assay_scenarios,
    "assays_by_metabolite": assays_by_metabolite_scenarios,
    "discussed_by_publication": discussed_by_publication_scenarios,
    # Batch E
    "genes_by_numeric_metric": genes_by_numeric_metric_scenarios,
    "genes_by_boolean_metric": genes_by_boolean_metric_scenarios,
    "genes_by_categorical_metric": genes_by_categorical_metric_scenarios,
    # Annotation-trust surface (PR 3b): term-side drill-down.
    "ontology_term_details": ontology_term_details_scenarios,
}
