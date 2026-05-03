"""MCP tool implementations for the Multiomics Knowledge Graph."""

import logging
import re
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

import multiomics_explorer.api.functions as api
from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.constants import VALID_CLUSTER_TYPES, VALID_OMICS_TYPES

logger = logging.getLogger(__name__)


def _conn(ctx: Context) -> GraphConnection:
    """Get the Neo4j connection from lifespan context."""
    return ctx.request_context.lifespan_context.conn



# ---------------------------------------------------------------------------
# pathway_enrichment response models (module-level for direct importability)
# ---------------------------------------------------------------------------

class PathwayEnrichmentResult(BaseModel):
    cluster: str = Field(
        description="Cluster key '{experiment_id}|{timepoint}|{direction}'"
    )
    experiment_id: str = Field(description="Experiment identifier")
    name: str | None = Field(
        default=None, description="Experiment display name"
    )
    timepoint: str = Field(
        description="Timepoint label; 'NA' for experiments without timepoints"
    )
    timepoint_hours: float | None = Field(
        default=None,
        description="Numeric time in hours",
    )
    timepoint_order: int | None = Field(
        default=None, description="Integer ordinal of the timepoint"
    )
    direction: str = Field(
        description="Expression direction: 'up' or 'down'"
    )
    omics_type: str | None = Field(
        default=None,
        description="Experiment omics type (transcriptomics, proteomics, ...)",
    )
    table_scope: str | None = Field(
        default=None, description="Coarse table_scope classifier"
    )
    treatment_type: list[str] | None = Field(
        default=None, description="Treatment-type tags"
    )
    background_factors: list[str] | None = Field(
        default=None, description="Background-condition tags"
    )
    is_time_course: bool | None = Field(
        default=None, description="True for time-course experiments"
    )
    growth_phase: str | None = Field(
        default=None,
        description="Physiological state of the culture at this timepoint. Timepoint-level, not gene-specific.",
    )
    term_id: str = Field(description="Ontology term ID")
    term_name: str = Field(description="Ontology term display name")
    level: int | None = Field(
        default=None, description="Hierarchy depth of the term (0 = root)"
    )
    tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
    tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
    gene_ratio: str = Field(
        description="'k/n' string — DE genes in pathway over total DE genes in cluster (clusterProfiler: GeneRatio)"
    )
    gene_ratio_numeric: float = Field(
        description="k/n as float"
    )
    bg_ratio: str = Field(
        description="'M/N' string — pathway members over background size (clusterProfiler: BgRatio)"
    )
    bg_ratio_numeric: float = Field(
        description="M/N as float"
    )
    rich_factor: float = Field(
        description="k/M — fraction of pathway's background members that are DE (clusterProfiler: RichFactor)"
    )
    fold_enrichment: float = Field(
        description="(k/n) / (M/N) — observed over null (clusterProfiler: FoldEnrichment)"
    )
    pvalue: float = Field(
        description="Fisher-exact p-value (one-sided enrichment)"
    )
    p_adjust: float = Field(
        description="Benjamini-Hochberg FDR within cluster (clusterProfiler: p.adjust)"
    )
    count: int = Field(
        description="k — DE genes in pathway (clusterProfiler: Count)"
    )
    bg_count: int = Field(
        description="M — pathway members in cluster's background"
    )
    signed_score: float = Field(
        description="sign * -log10(p_adjust); sign from direction (up: +, down: -)"
    )
    foreground_gene_ids: list[str] | None = Field(
        default=None,
        description="Verbose only: the k DE genes in this pathway (clusterProfiler: geneID split)",
    )
    background_gene_ids: list[str] | None = Field(
        default=None,
        description="Verbose only: pathway members in background NOT in DE set (non-overlapping complement)",
    )


class PathwayEnrichmentByExperiment(BaseModel):
    experiment_id: str = Field(description="Experiment identifier")
    name: str | None = Field(default=None, description="Experiment display name")
    omics_type: str | None = Field(default=None, description="Omics type")
    table_scope: str | None = Field(default=None, description="table_scope classifier")
    treatment_type: list[str] | None = Field(default=None, description="Treatment tags")
    background_factors: list[str] | None = Field(default=None, description="Background condition tags")
    is_time_course: bool | None = Field(default=None, description="Time-course flag")
    n_tests: int = Field(description="Total Fisher tests across this experiment's clusters")
    n_significant: int = Field(description="Tests with p_adjust below cutoff")
    n_clusters: int = Field(description="Distinct clusters contributed by this experiment")


class PathwayEnrichmentByDirection(BaseModel):
    direction: str = Field(description="Expression direction: 'up' or 'down'")
    n_tests: int = Field(description="Total tests for this direction")
    n_significant: int = Field(description="Significant tests for this direction")


class PathwayEnrichmentByOmicsType(BaseModel):
    omics_type: str = Field(description="Omics type")
    n_tests: int = Field(description="Total tests for this omics type")
    n_significant: int = Field(description="Significant tests for this omics type")


class PathwayEnrichmentClusterSummary(BaseModel):
    n_clusters: int = Field(description="Total clusters produced")
    n_tests_min: int = Field(description="Min tests per cluster")
    n_tests_median: float = Field(description="Median tests per cluster")
    n_tests_max: int = Field(description="Max tests per cluster")
    n_significant_min: int = Field(description="Min significant tests per cluster")
    n_significant_median: float = Field(description="Median significant tests per cluster")
    n_significant_max: int = Field(description="Max significant tests per cluster")
    universe_size_min: int = Field(description="Min background size across clusters")
    universe_size_median: float = Field(description="Median background size")
    universe_size_max: int = Field(description="Max background size")


class PathwayEnrichmentTopCluster(BaseModel):
    cluster: str = Field(description="Cluster key")
    experiment_id: str = Field(description="Experiment identifier")
    name: str | None = Field(default=None, description="Experiment display name")
    timepoint: str = Field(description="Timepoint label")
    timepoint_hours: float | None = Field(default=None, description="Hours")
    timepoint_order: int | None = Field(default=None, description="Ordinal")
    direction: str = Field(description="Expression direction")
    omics_type: str | None = Field(default=None, description="Omics type")
    table_scope: str | None = Field(default=None, description="table_scope")
    treatment_type: list[str] | None = Field(default=None, description="Treatment tags")
    background_factors: list[str] | None = Field(default=None, description="Background tags")
    is_time_course: bool | None = Field(default=None, description="Time-course flag")
    n_tests: int = Field(description="Tests in this cluster")
    n_significant: int = Field(description="Significant tests in this cluster")
    universe_size: int = Field(description="Cluster's background size")
    min_padj: float = Field(description="Smallest p_adjust within this cluster")


class PathwayEnrichmentTopPathway(BaseModel):
    cluster: str = Field(description="Cluster key")
    term_id: str = Field(description="Ontology term ID")
    term_name: str = Field(description="Ontology term name")
    p_adjust: float = Field(description="BH-adjusted p-value")
    signed_score: float = Field(description="Signed score")


class PathwayEnrichmentTermValidation(BaseModel):
    not_found: list[str] = Field(
        default_factory=list,
        description="term_ids absent from the KG entirely",
    )
    wrong_ontology: list[str] = Field(
        default_factory=list,
        description="term_ids present but in a different ontology label",
    )
    wrong_level: list[str] = Field(
        default_factory=list,
        description="term_ids in the ontology but at the wrong level",
    )
    filtered_out: list[str] = Field(
        default_factory=list,
        description="term_ids valid but excluded by size bounds (irrelevant here since wide bounds are used internally)",
    )


class PathwayEnrichmentClusterSkipped(BaseModel):
    cluster: str = Field(description="Cluster key that was skipped")
    reason: str = Field(
        description="Skip reason: 'empty_gene_set' | 'no_pathways_in_size_range' | 'empty_background'"
    )


class PathwayEnrichmentResponse(BaseModel):
    organism_name: str = Field(description="Single organism")
    ontology: str = Field(description="Ontology used")
    level: int | None = Field(default=None, description="Hierarchy level used (or None for term_ids-only)")
    total_matching: int = Field(
        description="Total (cluster x term) rows pre-pagination; equals Fisher tests run"
    )
    returned: int = Field(description="Rows in this response")
    truncated: bool = Field(description="True when total_matching exceeds offset+returned")
    offset: int = Field(default=0, description="Pagination offset")
    n_significant: int = Field(description="Rows with p_adjust below pvalue_cutoff")
    by_experiment: list[PathwayEnrichmentByExperiment] = Field(
        default_factory=list, description="Per-experiment tests + significance"
    )
    by_direction: list[PathwayEnrichmentByDirection] = Field(
        default_factory=list, description="Per-direction aggregates"
    )
    by_omics_type: list[PathwayEnrichmentByOmicsType] = Field(
        default_factory=list, description="Per-omics-type aggregates"
    )
    cluster_summary: PathwayEnrichmentClusterSummary = Field(
        description="Distribution stats across clusters"
    )
    top_clusters_by_min_padj: list[PathwayEnrichmentTopCluster] = Field(
        default_factory=list, description="Top 5 clusters by smallest p_adjust"
    )
    top_pathways_by_padj: list[PathwayEnrichmentTopPathway] = Field(
        default_factory=list, description="Top 10 pathways by p_adjust across all clusters"
    )
    not_found: list[str] = Field(
        default_factory=list, description="Requested experiment_ids absent from KG"
    )
    not_matched: list[str] = Field(
        default_factory=list, description="Experiment IDs found but wrong organism"
    )
    no_expression: list[str] = Field(
        default_factory=list, description="Experiments matching organism but with no DE rows"
    )
    term_validation: PathwayEnrichmentTermValidation = Field(
        description="Namespaced passthrough of term_id validation from genes_by_ontology"
    )
    clusters_skipped: list[PathwayEnrichmentClusterSkipped] = Field(
        default_factory=list, description="Clusters that produced no rows, with reason"
    )
    enrichment_params: dict | None = Field(
        default=None,
        description="ORA parameters used for this call. See docs://analysis/enrichment.",
    )
    results: list[PathwayEnrichmentResult] = Field(
        default_factory=list, description="Long-format result rows (one Fisher test per row)"
    )


# ---------------------------------------------------------------------------
# cluster_enrichment response models (module-level for direct importability)
# ---------------------------------------------------------------------------

class ClusterEnrichmentResult(BaseModel):
    cluster: str = Field(description="Cluster name from the clustering analysis")
    cluster_id: str = Field(description="Cluster ID from KG")
    term_id: str = Field(description="Ontology term ID")
    term_name: str = Field(description="Ontology term display name")
    level: int | None = Field(default=None, description="Hierarchy depth (0 = root)")
    tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
    tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
    gene_ratio: str = Field(
        description="'k/n' string — cluster genes in pathway over total cluster genes (clusterProfiler: GeneRatio)"
    )
    gene_ratio_numeric: float = Field(description="k/n as float")
    bg_ratio: str = Field(
        description="'M/N' string — pathway members over background size (clusterProfiler: BgRatio)"
    )
    bg_ratio_numeric: float = Field(description="M/N as float")
    rich_factor: float = Field(
        description="k/M — fraction of pathway's background members in cluster (clusterProfiler: RichFactor)"
    )
    fold_enrichment: float = Field(
        description="(k/n) / (M/N) — observed over null (clusterProfiler: FoldEnrichment)"
    )
    pvalue: float = Field(description="Fisher-exact p-value (one-sided enrichment)")
    p_adjust: float = Field(
        description="Benjamini-Hochberg FDR within cluster (clusterProfiler: p.adjust)"
    )
    count: int = Field(description="k — cluster genes in pathway (clusterProfiler: Count)")
    bg_count: int = Field(description="M — pathway members in cluster's background")
    # Verbose fields
    cluster_functional_description: str | None = Field(
        default=None, description="Verbose: functional description of cluster"
    )
    cluster_expression_dynamics: str | None = Field(
        default=None, description="Verbose: expression dynamics of cluster"
    )
    cluster_temporal_pattern: str | None = Field(
        default=None, description="Verbose: temporal pattern of cluster"
    )
    cluster_member_count: int | None = Field(
        default=None, description="Verbose: total genes in this cluster"
    )


class ClusterEnrichmentByCluster(BaseModel):
    cluster_id: str = Field(description="Cluster ID")
    cluster_name: str = Field(description="Cluster name")
    member_count: int = Field(description="Genes in cluster")
    significant_terms: int = Field(description="Terms with p_adjust below cutoff")


class ClusterEnrichmentByTerm(BaseModel):
    term_id: str = Field(description="Term ID")
    term_name: str = Field(description="Term name")
    n_clusters: int = Field(description="Clusters where this term is significant")


class ClusterEnrichmentClusterSkipped(BaseModel):
    cluster_id: str = Field(description="Cluster ID")
    cluster_name: str = Field(description="Cluster name")
    member_count: int | None = Field(default=None, description="Genes in cluster")
    reason: str = Field(description="Why skipped")


class ClusterEnrichmentResponse(BaseModel):
    analysis_id: str | None = Field(default=None, description="Clustering analysis ID")
    analysis_name: str | None = Field(default=None, description="Clustering analysis name")
    organism_name: str = Field(description="Single organism")
    cluster_method: str | None = Field(default=None, description="Clustering method")
    cluster_type: str | None = Field(default=None, description="Cluster type")
    omics_type: str | None = Field(default=None, description="Omics type")
    treatment_type: list[str] = Field(default_factory=list, description="Treatment types")
    background_factors: list[str] = Field(default_factory=list, description="Background factors")
    growth_phases: list[str] = Field(default_factory=list, description="Growth phases")
    experiment_ids: list[str] = Field(default_factory=list, description="Linked experiment IDs")
    ontology: str = Field(description="Ontology used")
    level: int | None = Field(default=None, description="Hierarchy level")
    tree: str | None = Field(default=None, description="BRITE tree (if applicable)")
    total_matching: int = Field(description="Total Fisher tests run")
    returned: int = Field(description="Rows in this response")
    truncated: bool = Field(description="True when total_matching exceeds offset+returned")
    offset: int = Field(default=0, description="Pagination offset")
    n_significant: int = Field(description="Rows with p_adjust below cutoff")
    by_cluster: list[ClusterEnrichmentByCluster] = Field(
        default_factory=list, description="Per-cluster significance counts"
    )
    by_term: list[ClusterEnrichmentByTerm] = Field(
        default_factory=list, description="Top terms by number of clusters"
    )
    clusters_tested: int = Field(description="Clusters passing size filter")
    not_found: list[str] = Field(default_factory=list, description="Analysis IDs absent from KG")
    not_matched: list[str] = Field(default_factory=list, description="Analysis IDs wrong organism")
    clusters_skipped: list[ClusterEnrichmentClusterSkipped] = Field(
        default_factory=list, description="Clusters filtered out or producing no rows"
    )
    term_validation: PathwayEnrichmentTermValidation = Field(
        description="Namespaced passthrough of term_id validation from genes_by_ontology"
    )
    enrichment_params: dict | None = Field(
        default=None,
        description="ORA parameters used for this call. See docs://analysis/enrichment.",
    )
    results: list[ClusterEnrichmentResult] = Field(
        default_factory=list, description="Long-format result rows"
    )


# ---------------------------------------------------------------------------
# list_metabolites response models (module-level for direct importability)
# ---------------------------------------------------------------------------

class MetaboliteResult(BaseModel):
    # compact
    metabolite_id: str = Field(description="Full prefixed ID (e.g. 'kegg.compound:C00031'). 85% kegg.compound, 15% chebi (TCDB-only substrates).")
    name: str = Field(description="Metabolite name (e.g. 'D-Glucose', 'L-Glutamate')")
    formula: str | None = Field(default=None, description="Hill-notation chemical formula (e.g. 'C6H12O6'). Null on ~9% of metabolites (mostly TCDB-curated generic substrates).")
    elements: list[str] = Field(default_factory=list, description="Sorted unique element symbols present in formula (e.g. ['C','H','O']). Empty when formula is null. Filter on this — never on `formula` substring (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N').")
    mass: float | None = Field(default=None, description="Monoisotopic mass in Da (e.g. 180.156). Null on ~22% of metabolites.")
    gene_count: int = Field(default=0, description="Distinct genes reachable via Gene → Reaction → Metabolite OR Gene → TcdbFamily → Metabolite (UNION post-TCDB; e.g. 320 for glucose). When > 0, drill in via genes_by_metabolite(metabolite_ids=[id], organism=...). All metabolites have gene_count > 0 today (post-2026-05-03 transport-arm fix); the future metabolomics-DM spec will introduce metabolites measured without any gene path, which will surface here with gene_count=0 — 0 ≠ 'absent from KG'.")
    organism_count: int = Field(default=0, description="Distinct organisms reaching this metabolite via any chemistry path (e.g. 31 for ATP). When > 0, narrow with organism_names filter.")
    transporter_count: int = Field(default=0, description="Distinct `tc_specificity` leaf TcdbFamily nodes annotated as transporting this metabolite (e.g. 17 for glucose, 229 for sodium). Scoped to leaves so the count reflects 'actual transporter systems' rather than counting ancestor families that inherit the substrate via the 2026-05-03 rollup. Source: TCDB-CAZy ontology.")
    evidence_sources: list[str] = Field(default_factory=list, description="Path provenance — values from {'metabolism', 'transport'}. 'metabolism' = at least one Reaction in KG involves this compound; 'transport' = at least one TcdbFamily curates this as substrate. 'metabolomics' is reserved for the future metabolomics-DM spec — no row carries it today. E.g. ['metabolism', 'transport'].")
    chebi_id: str | None = Field(default=None, description="ChEBI ID (raw numeric, e.g. '4167'). Populated on 90% of metabolites overall — 100% of the 452 chebi:-IDed transport-only metabolites (extracted from the ID itself), plus the kegg.compound:-IDed metabolites that cross-ref ChEBI.")
    pathway_ids: list[str] = Field(default_factory=list, description="KEGG pathway memberships (e.g. ['kegg.pathway:ko00010', 'kegg.pathway:ko01100']). Empty when no Metabolite_in_pathway edges. Drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...).")
    pathway_count: int = Field(default=0, description="Distinct count of KEGG pathways this metabolite is in (e.g. 5). Routing signal — when > 0, drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...) for genes annotated to those pathways. Equal to size(pathway_ids).")
    score: float | None = Field(default=None, description="Lucene relevance score (only with `search`).")

    # verbose
    inchikey: str | None = Field(default=None, description="InChIKey structural fingerprint (e.g. 'WQZGKKKJIJFFOK-GASJEMHNSA-N'). Verbose only.")
    smiles: str | None = Field(default=None, description="SMILES structural string (e.g. 'OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O'). Verbose only.")
    mnxm_id: str | None = Field(default=None, description="MetaNetX canonical ID (e.g. 'MNXM1364061'). Verbose only — populated on 100% of metabolites.")
    hmdb_id: str | None = Field(default=None, description="HMDB ID (e.g. 'HMDB0304632'). Verbose only — populated on 47%.")
    pathway_names: list[str] | None = Field(default=None, description="Pathway names aligned with pathway_ids (verbose only).")


class MetTopOrganism(BaseModel):
    organism_name: str = Field(description="Organism name (e.g. 'Ruegeria pomeroyi DSS-3')")
    count: int = Field(description="Number of matched metabolites this organism reaches (e.g. 1271)")


class MetTopPathway(BaseModel):
    pathway_id: str = Field(description="KEGG pathway ID (e.g. 'kegg.pathway:ko01100')")
    pathway_name: str = Field(description="Pathway name (e.g. 'Metabolic pathways')")
    count: int = Field(description="Number of matched metabolites in this pathway (e.g. 870)")


class MetEvidenceSourceBreakdown(BaseModel):
    evidence_source: str = Field(description="Evidence path (e.g. 'metabolism', 'transport')")
    count: int = Field(description="Number of matched metabolites with this evidence source (e.g. 1212). Sums to > total_matching when metabolites carry multiple sources.")


class MetXrefCoverage(BaseModel):
    with_chebi: int = Field(description="Matched metabolites with chebi_id (e.g. 1386)")
    with_hmdb: int = Field(description="Matched metabolites with hmdb_id (e.g. 849)")
    with_mnxm: int = Field(description="Matched metabolites with mnxm_id (e.g. 1563 — typically full coverage)")


class MetMassStats(BaseModel):
    mass_min: float | None = Field(default=None, description="Minimum mass across matched metabolites (e.g. 18.039). Null when no matched metabolite has a mass.")
    mass_median: float | None = Field(default=None, description="Median mass (e.g. 328.192).")
    mass_max: float | None = Field(default=None, description="Maximum mass (e.g. 5227.103).")


class MetNotFound(BaseModel):
    metabolite_ids: list[str] = Field(default_factory=list, description="Input metabolite_ids that don't exist in the KG (e.g. ['kegg.compound:C99999']).")
    organism_names: list[str] = Field(default_factory=list, description="Input organism_names with no matching OrganismTaxon (e.g. ['Bogus organism']).")
    pathway_ids: list[str] = Field(default_factory=list, description="Input pathway_ids with no matching KeggTerm (e.g. ['kegg.pathway:bogus']).")


class ListMetabolitesResponse(BaseModel):
    total_entries: int = Field(description="Total Metabolite nodes in KG (unfiltered, 3,025 today)")
    total_matching: int = Field(description="Metabolites matching filters")
    top_organisms: list[MetTopOrganism] = Field(default_factory=list, description="Top 10 organisms by metabolite count (within matched set), sorted desc")
    top_pathways: list[MetTopPathway] = Field(default_factory=list, description="Top 10 pathways by metabolite count (within matched set), sorted desc")
    by_evidence_source: list[MetEvidenceSourceBreakdown] = Field(default_factory=list, description="Frequency of evidence_sources values across matched set. Today: at most 2 entries (metabolism, transport).")
    xref_coverage: MetXrefCoverage = Field(description="Cross-ref ID coverage within matched set")
    mass_stats: MetMassStats = Field(description="Mass distribution within matched set")
    score_max: float | None = Field(default=None, description="Max Lucene score (only with search)")
    score_median: float | None = Field(default=None, description="Median Lucene score (only with search)")
    returned: int = Field(description="Metabolites in this response")
    offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
    truncated: bool = Field(description="True if total_matching > returned")
    not_found: MetNotFound = Field(default_factory=MetNotFound, description="Per-filter buckets for unknown input IDs")
    results: list[MetaboliteResult] = Field(default_factory=list)


def register_tools(mcp: FastMCP):
    """Register all KG tools with the MCP server."""

    class KgSchemaResponse(BaseModel):
        nodes: dict[str, dict] = Field(
            description="Node labels mapped to their property definitions. "
                        "Each value is {'properties': {'prop_name': 'type_string', ...}}."
        )
        relationships: dict[str, dict] = Field(
            description="Relationship types mapped to their definitions. "
                        "Each value is {'source_labels': [...], 'target_labels': [...], "
                        "'properties': {'prop_name': 'type_string', ...}}."
        )

    @mcp.tool(
        tags={"utility", "schema"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def kg_schema(ctx: Context) -> KgSchemaResponse:
        """Get the knowledge graph schema: node labels with property names/types,
        and relationship types with source/target labels.

        Use this before run_cypher to understand what labels and properties are queryable.
        """
        await ctx.info("kg_schema")
        try:
            data = api.kg_schema(conn=_conn(ctx))
            return KgSchemaResponse(**data)
        except Exception as e:
            await ctx.error(f"kg_schema unexpected error: {e}")
            raise ToolError(f"Error in kg_schema: {e}")

    class FilterValueResult(BaseModel):
        value: str = Field(
            description="Filter value (e.g. 'Photosynthesis', 'Transport', 'Unknown')"
        )
        count: int = Field(
            description="Number of genes/items with this value (e.g. 770)"
        )
        tree_code: str | None = Field(
            default=None,
            description="BRITE tree code (sparse: only for brite_tree filter, e.g. 'ko01000')",
        )

    class ListFilterValuesResponse(BaseModel):
        filter_type: str = Field(description="The filter type returned (e.g. 'gene_category')")
        total_entries: int = Field(description="Total distinct values for this filter (e.g. 26)")
        returned: int = Field(description="Number of results returned (e.g. 26)")
        truncated: bool = Field(description="True if total_entries > returned")
        results: list[FilterValueResult] = Field(default_factory=list)

    @mcp.tool(
        tags={"filters", "discovery"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def list_filter_values(
        ctx: Context,
        filter_type: Annotated[
            Literal["gene_category", "brite_tree", "growth_phase",
                    "metric_type", "value_kind", "compartment"],
            Field(description=(
                "Which categorical filter to enumerate. "
                "'gene_category' / 'brite_tree' / 'growth_phase'; "
                "'metric_type' / 'value_kind' / 'compartment' (DerivedMetric "
                "discovery)."
            )),
        ] = "gene_category",
    ) -> ListFilterValuesResponse:
        """List valid values for categorical filters used across tools.

        Returns valid values and counts for the requested filter type.
        Use the returned values as filter parameters in `genes_by_function`
        (category filter).
        """
        await ctx.info(f"list_filter_values filter_type={filter_type}")
        try:
            conn = _conn(ctx)
            data = api.list_filter_values(filter_type=filter_type, conn=conn)
            results = [FilterValueResult(**r) for r in data["results"]]
            response = ListFilterValuesResponse(**{**data, "results": results})
            await ctx.info(f"Returning {response.total_entries} values for {filter_type}")
            return response
        except ValueError as e:
            await ctx.warning(f"list_filter_values error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"list_filter_values unexpected error: {e}")
            raise ToolError(f"Error in list_filter_values: {e}")

    class OrganismResult(BaseModel):
        organism_name: str = Field(description="Display name (e.g. 'Prochlorococcus MED4'). Use for organism filters in other tools.")
        organism_type: str = Field(description="Classification: 'genome_strain', 'treatment', or 'reference_proteome_match'")
        genus: str | None = Field(default=None, description="Genus (e.g. 'Prochlorococcus', 'Alteromonas')")
        species: str | None = Field(default=None, description="Binomial species name (e.g. 'Prochlorococcus marinus')")
        strain: str | None = Field(default=None, description="Strain identifier (e.g. 'MED4', 'EZ55')")
        clade: str | None = Field(default=None, description="Ecotype clade, Prochlorococcus-specific (e.g. 'HLI', 'LLIV')")
        ncbi_taxon_id: int | None = Field(default=None, description="NCBI Taxonomy ID for cross-referencing external databases (e.g. 59919)")
        gene_count: int = Field(description="Number of genes in the KG for this organism (e.g. 1976)")
        publication_count: int = Field(description="Number of publications studying this organism (e.g. 11)")
        experiment_count: int = Field(description="Total experiments across all publications (e.g. 46)")
        treatment_types: list[str] = Field(default_factory=list, description="Distinct treatment types studied (e.g. ['coculture', 'light_stress', 'nitrogen_stress'])")
        background_factors: list[str] = Field(default_factory=list, description="Distinct background factors across experiments (e.g. ['axenic', 'continuous_light', 'diel_cycle'])")
        omics_types: list[str] = Field(default_factory=list, description="Distinct omics types available (e.g. ['RNASEQ', 'PROTEOMICS'])")
        clustering_analysis_count: int = Field(default=0, description="Number of clustering analyses for this organism (e.g. 4)")
        cluster_types: list[str] = Field(default_factory=list, description="Distinct cluster types (e.g. ['condition_comparison', 'diel'])")
        growth_phases: list[str] = Field(default_factory=list, description="Distinct growth phases across experiments (e.g. ['exponential', 'nutrient_limited']). Physiological state of the culture at sampling — timepoint-level, not gene-specific.")
        # verbose-only fields
        family: str | None = Field(default=None, description="Taxonomic family (e.g. 'Prochlorococcaceae')")
        order: str | None = Field(default=None, description="Taxonomic order (e.g. 'Synechococcales')")
        tax_class: str | None = Field(default=None, description="Taxonomic class (e.g. 'Cyanophyceae')")
        phylum: str | None = Field(default=None, description="Taxonomic phylum (e.g. 'Cyanobacteriota')")
        kingdom: str | None = Field(default=None, description="Taxonomic kingdom (e.g. 'Bacillati')")
        superkingdom: str | None = Field(default=None, description="Taxonomic superkingdom (e.g. 'Bacteria')")
        lineage: str | None = Field(default=None, description="Full NCBI taxonomy lineage string (e.g. 'cellular organisms; Bacteria; ...; Prochlorococcus marinus')")
        cluster_count: int | None = Field(default=None, description="Total gene clusters across analyses (only with verbose=True, e.g. 35)")
        # DM compact fields
        derived_metric_count: int = Field(default=0, description="Total DerivedMetric annotations on this organism's experiments (0 when none).")
        derived_metric_value_kinds: list[str] = Field(default_factory=list, description="Subset of {numeric, boolean, categorical} present across this organism's DMs. Use to route to genes_by_{numeric,boolean,categorical}_metric.")
        compartments: list[str] = Field(default_factory=list, description="Wet-lab compartments measured for this organism (e.g. ['whole_cell', 'vesicle']).")
        # Chemistry rollups (slice 1)
        reaction_count: int = Field(default=0, description="Distinct reactions catalyzed by genes in this organism (e.g. 943). When > 0, drill in via list_metabolites(organism_names=[organism_name]) to enumerate metabolites this organism is capable of metabolizing.")
        metabolite_count: int = Field(default=0, description="Distinct metabolites this organism's genes can act on (e.g. 1039). Capability signal — does NOT mean these metabolites were measured. Today reflects gene catalysis only; will grow to include transport substrates when the TCDB-CAZy ontology ships, with no schema change. When > 0, drill in via list_metabolites(organism_names=[organism_name]).")
        # DM verbose-only fields
        derived_metric_gene_count: int | None = Field(default=None, description="Total gene-level DM annotation count (verbose-only).")
        derived_metric_types: list[str] | None = Field(default=None, description="Distinct metric_type tags observed (verbose-only).")
        # sparse reference fields (reference_proteome_match only)
        reference_database: str | None = Field(default=None, description="Reference database used for matching (e.g. 'MarRef v6'). Only on reference_proteome_match organisms.")
        reference_proteome: str | None = Field(default=None, description="Accession of matched reference proteome (e.g. 'GCA_003513035.1'). Only on reference_proteome_match organisms.")

    class OrgClusterTypeBreakdown(BaseModel):
        cluster_type: str = Field(description="Cluster type (e.g. 'condition_comparison')")
        count: int = Field(description="Number of organisms with this cluster type (e.g. 4)")

    class OrgTypeBreakdown(BaseModel):
        organism_type: str = Field(description="Organism type (e.g. 'genome_strain')")
        count: int = Field(description="Number of organisms of this type (e.g. 25)")

    class OrgValueKindBreakdown(BaseModel):
        value_kind: str = Field(description="DerivedMetric value kind (e.g. 'numeric', 'boolean', 'categorical')")
        count: int = Field(description="Number of DerivedMetrics with this value_kind across matched organisms.")

    class OrgMetricTypeBreakdown(BaseModel):
        metric_type: str = Field(description="DerivedMetric type (e.g. 'diel_rhythmicity', 'darkness_survival_class')")
        count: int = Field(description="Number of DerivedMetrics with this metric_type across matched organisms.")

    class OrgCompartmentBreakdown(BaseModel):
        compartment: str = Field(description="Wet-lab compartment (e.g. 'whole_cell', 'vesicle')")
        count: int = Field(description="Number of DerivedMetrics in this compartment across matched organisms.")

    class OrgMetabolicCapabilityBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        reaction_count: int = Field(description="Distinct reactions catalyzed by this organism's genes (e.g. 943)")
        metabolite_count: int = Field(description="Distinct metabolites this organism's genes can act on (e.g. 1039). Same semantics as OrganismResult.metabolite_count.")

    class ListOrganismsResponse(BaseModel):
        total_entries: int = Field(description="Total organisms in the KG")
        total_matching: int = Field(description="Organisms matching the filter (= total_entries when no filter)")
        by_cluster_type: list[OrgClusterTypeBreakdown] = Field(default_factory=list, description="Organism counts per cluster type over the matched set, sorted by count descending")
        by_organism_type: list[OrgTypeBreakdown] = Field(default_factory=list, description="Organism counts per type over the matched set, sorted by count descending")
        by_value_kind: list[OrgValueKindBreakdown] = Field(default_factory=list, description="DM value_kind frequency rollup across matched organisms. Each entry: {value_kind, count}.")
        by_metric_type: list[OrgMetricTypeBreakdown] = Field(default_factory=list, description="DM metric_type frequency rollup across matched organisms. Each entry: {metric_type, count}.")
        by_compartment: list[OrgCompartmentBreakdown] = Field(default_factory=list, description="Wet-lab compartment frequency rollup across matched organisms. Each entry: {compartment, count}.")
        by_metabolic_capability: list[OrgMetabolicCapabilityBreakdown] = Field(default_factory=list, description="Top 10 organisms by metabolite_count (within matched set), sorted desc. Filter excludes organisms with zero chemistry. [] when no matched organism has chemistry. Use list_metabolites(organism_names=[organism_name]) on top entries to enumerate their metabolites.")
        returned: int = Field(description="Number of results returned")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if total_matching > offset + returned")
        not_found: list[str] = Field(default_factory=list, description="organism_names inputs that didn't match any organism (case-insensitive); [] when no filter")
        results: list[OrganismResult]

    @mcp.tool(
        tags={"organisms", "discovery"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def list_organisms(
        ctx: Context,
        organism_names: Annotated[list[str] | None, Field(
            description=(
                "Filter by exact organism preferred_name (case-insensitive). "
                "Pass values from a prior list_organisms call or another "
                "tool's organism_name field. Unknown names are reported in "
                "not_found rather than raising."
            ),
        )] = None,
        compartment: Annotated[str | None, Field(
            description="Filter to organisms with at least one experiment in this wet-lab compartment (e.g. 'vesicle', 'whole_cell'). Use list_filter_values(filter_type='compartment') to enumerate valid values.",
        )] = None,
        summary: Annotated[bool, Field(
            description="Return summary fields only (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include full taxonomy hierarchy "
            "(family, order, class, phylum, kingdom, superkingdom, lineage).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> ListOrganismsResponse:
        """List organisms in the knowledge graph, optionally filtered by name or compartment.

        Returns taxonomy, gene counts, publication counts, and organism_type
        for each organism. organism_type classifies each organism as
        'genome_strain', 'treatment', or 'reference_proteome_match'.
        Reference proteome match organisms also include reference_database
        and reference_proteome fields.

        Use the returned organism names as filter values in genes_by_function,
        resolve_gene, genes_by_ontology, list_publications, etc. The organism
        filter on those tools uses partial matching — "MED4",
        "Prochlorococcus MED4", and "Prochlorococcus" all work. The
        organism_names filter on this tool uses exact match (case-
        insensitive) on preferred_name; unknown names are reported in
        not_found.

        After this tool, scope deeper queries to the chosen organism: use the
        locus_tags filter on per-gene tools (gene_overview, gene_homologs)
        and the organism filter on gene_ontology_terms, list_experiments,
        and list_publications. Use list_filter_values for categorical
        field enumeration.
        """
        await ctx.info(
            f"list_organisms organism_names={organism_names} compartment={compartment} "
            f"summary={summary} verbose={verbose} limit={limit} offset={offset}"
        )
        try:
            conn = _conn(ctx)
            result = api.list_organisms(
                organism_names=organism_names,
                compartment=compartment,
                summary=summary,
                verbose=verbose,
                limit=limit,
                offset=offset,
                conn=conn,
            )
            organisms = [OrganismResult(**r) for r in result["results"]]
            by_cluster_type = [OrgClusterTypeBreakdown(**b) for b in result.get("by_cluster_type", [])]
            by_organism_type = [OrgTypeBreakdown(**b) for b in result.get("by_organism_type", [])]
            by_value_kind = [OrgValueKindBreakdown(**b) for b in result.get("by_value_kind", [])]
            by_metric_type = [OrgMetricTypeBreakdown(**b) for b in result.get("by_metric_type", [])]
            by_compartment = [OrgCompartmentBreakdown(**b) for b in result.get("by_compartment", [])]
            by_metabolic_capability = [
                OrgMetabolicCapabilityBreakdown(**b)
                for b in result.get("by_metabolic_capability", [])
            ]
            response = ListOrganismsResponse(
                total_entries=result["total_entries"],
                total_matching=result["total_matching"],
                by_cluster_type=by_cluster_type,
                by_organism_type=by_organism_type,
                by_value_kind=by_value_kind,
                by_metric_type=by_metric_type,
                by_compartment=by_compartment,
                by_metabolic_capability=by_metabolic_capability,
                returned=result["returned"],
                offset=result.get("offset", 0),
                truncated=result["truncated"],
                not_found=result.get("not_found", []),
                results=organisms,
            )
            await ctx.info(
                f"Returning {response.returned} of {response.total_matching} matched "
                f"({response.total_entries} in KG) organisms"
            )
            return response
        except Exception as e:
            await ctx.error(f"list_organisms unexpected error: {e}")
            raise ToolError(f"Error in list_organisms: {e}")

    class GeneMatch(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        gene_name: str | None = Field(default=None, description="Gene name (e.g. 'dnaN')")
        product: str | None = Field(default=None, description="Gene product (e.g. 'DNA polymerase III, beta subunit')")
        organism_name: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")

    class ResolveOrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        count: int = Field(description="Number of matching genes in this organism (e.g. 1)")

    class ResolveGeneResponse(BaseModel):
        total_matching: int = Field(description="Total genes matching identifier + organism filter (e.g. 3)")
        by_organism: list[ResolveOrganismBreakdown] = Field(description="Match counts per organism, sorted by count descending")
        returned: int = Field(description="Genes in this response (e.g. 3)")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if total_matching > returned")
        results: list[GeneMatch] = Field(description="Matching genes sorted by organism_name, locus_tag")

    @mcp.tool(
        tags={"genes", "discovery"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def resolve_gene(
        ctx: Context,
        identifier: Annotated[str, Field(
            description="Gene identifier (case-insensitive) — locus_tag "
            "(e.g. 'PMM0001'), gene name (e.g. 'dnaN'), old locus tag, "
            "or RefSeq protein ID.",
        )],
        organism: Annotated[str | None, Field(
            description="Filter by organism (case-insensitive partial match). "
            "E.g. 'MED4', 'Prochlorococcus MED4'.",
        )] = None,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> ResolveGeneResponse:
        """Resolve a gene identifier to matching genes in the knowledge graph.

        Matching is case-insensitive — 'pmm0001', 'PMM0001', and 'Pmm0001'
        all work. Use the returned locus_tags with gene_overview,
        gene_details, gene_homologs, or gene_ontology_terms. The organism
        filter uses case-insensitive partial matching — 'MED4' and
        'Prochlorococcus MED4' both work.
        """
        await ctx.info(f"resolve_gene identifier={identifier} organism={organism} offset={offset}")
        try:
            conn = _conn(ctx)
            result = api.resolve_gene(
                identifier, organism=organism, limit=limit, offset=offset, conn=conn,
            )
            genes = [GeneMatch(**r) for r in result["results"]]
            by_organism = [ResolveOrganismBreakdown(**b) for b in result["by_organism"]]
            return ResolveGeneResponse(
                total_matching=result["total_matching"],
                by_organism=by_organism,
                returned=result["returned"],
                offset=result.get("offset", 0),
                truncated=result["truncated"],
                results=genes,
            )
        except ValueError as e:
            await ctx.warning(f"resolve_gene error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"resolve_gene unexpected error: {e}")
            raise ToolError(f"Error in resolve_gene: {e}")

    # --- genes_by_function ---

    class FunctionOrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        count: int = Field(description="Number of matching genes")

    class FunctionCategoryBreakdown(BaseModel):
        category: str = Field(description="Gene category (e.g. 'Photosynthesis')")
        count: int = Field(description="Number of matching genes")

    class GenesByFunctionResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        gene_name: str | None = Field(default=None, description="Gene name (e.g. 'dnaN')")
        product: str | None = Field(default=None, description="Gene product (e.g. 'DNA polymerase III subunit beta')")
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        gene_category: str | None = Field(default=None, description="Functional category (e.g. 'Photosynthesis')")
        annotation_quality: int = Field(description="Annotation quality 0-3 (3=best)")
        score: float = Field(description="Fulltext relevance score")
        # verbose only
        function_description: str | None = Field(default=None, description="Functional description text")
        gene_summary: str | None = Field(default=None, description="Combined gene annotation summary")

    class GenesByFunctionResponse(BaseModel):
        total_search_hits: int = Field(description="Total genes matching search text (before organism/category/quality filters)")
        total_matching: int = Field(description="Total genes matching search + all filters")
        by_organism: list[FunctionOrganismBreakdown] = Field(description="Gene counts per organism, sorted desc")
        by_category: list[FunctionCategoryBreakdown] = Field(description="Gene counts per category, sorted desc")
        score_max: float | None = Field(default=None, description="Highest relevance score (null if 0 matches)")
        score_median: float | None = Field(default=None, description="Median relevance score (null if 0 matches)")
        returned: int = Field(description="Number of results returned")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True when total_matching > returned")
        results: list[GenesByFunctionResult] = Field(description="Gene results ranked by relevance")

    @mcp.tool(
        tags={"genes", "discovery"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def genes_by_function(
        ctx: Context,
        search_text: Annotated[str, Field(
            description="Free-text query (Lucene syntax supported). "
            "E.g. 'photosystem', 'nitrogen AND transport', 'dnaN~'.",
        )],
        organism: Annotated[str | None, Field(
            description="Filter by organism (case-insensitive substring). "
            "E.g. 'MED4', 'Prochlorococcus MED4'. "
            "Use list_organisms to see valid values.",
        )] = None,
        category: Annotated[str | None, Field(
            description="Filter by gene_category. "
            "E.g. 'Photosynthesis', 'Transport'. "
            "Use list_filter_values to see valid values.",
        )] = None,
        min_quality: Annotated[int, Field(
            description="Minimum annotation_quality (0-3). "
            "0=hypothetical, 1=has description, 2=named product, "
            "3=well-annotated. Use 2 to skip hypothetical proteins.",
            ge=0, le=3,
        )] = 0,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include function_description and gene_summary.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> GenesByFunctionResponse:
        """Search genes by functional annotation text.

        Full-text search across gene names, products, and functional
        descriptions. Supports Lucene syntax: quoted phrases, AND/OR,
        wildcards (*), fuzzy (~). Results ranked by relevance score.

        For ontology-based search, use genes_by_ontology.
        For gene details, use gene_overview.
        """
        await ctx.info(f"genes_by_function search_text={search_text} organism={organism} "
                       f"category={category} min_quality={min_quality}")
        try:
            conn = _conn(ctx)
            data = api.genes_by_function(
                search_text, organism=organism,
                category=category, min_quality=min_quality,
                summary=summary, verbose=verbose, limit=limit, offset=offset, conn=conn,
            )
            by_organism = [FunctionOrganismBreakdown(**b) for b in data["by_organism"]]
            by_category = [FunctionCategoryBreakdown(**b) for b in data["by_category"]]
            results = [GenesByFunctionResult(**r) for r in data["results"]]
            response = GenesByFunctionResponse(
                total_search_hits=data["total_search_hits"],
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_category=by_category,
                score_max=data["score_max"],
                score_median=data["score_median"],
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of {response.total_matching} "
                           f"matching genes ({response.total_search_hits} search hits before filters)")
            return response
        except ValueError as e:
            await ctx.warning(f"genes_by_function error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"genes_by_function unexpected error: {e}")
            raise ToolError(f"Error in genes_by_function: {e}")

    # --- gene_overview ---

    class GeneOverviewResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        gene_name: str | None = Field(default=None, description="Gene name (e.g. 'dnaN')")
        product: str | None = Field(default=None, description="Gene product (e.g. 'DNA polymerase III subunit beta')")
        gene_category: str | None = Field(default=None, description="Functional category (e.g. 'Replication and repair')")
        annotation_quality: int | None = Field(default=None, description="Annotation quality score 0-3 (e.g. 3)")
        organism_name: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")
        annotation_types: list[str] = Field(default_factory=list, description="Ontology source types where this gene has at least one annotation (e.g. ['go_bp', 'ec', 'kegg']). Presence-only — does NOT indicate content informativeness; a 'cog_category' entry may be 'Function unknown'. For term content, call gene_ontology_terms.")
        expression_edge_count: int = Field(default=0, description="Number of expression data points (e.g. 36). When > 0, drill into differential_expression_by_gene or gene_response_profile.")
        significant_up_count: int = Field(default=0, description="Significant up-regulated DE observations (e.g. 3). When > 0, use differential_expression_by_gene with direction='up' for per-experiment detail.")
        significant_down_count: int = Field(default=0, description="Significant down-regulated DE observations (e.g. 2). When > 0, use differential_expression_by_gene with direction='down' for per-experiment detail.")
        closest_ortholog_group_size: int | None = Field(default=None, description="Size of tightest ortholog group (e.g. 9). Use gene_homologs for full per-group membership and source/level metadata.")
        closest_ortholog_genera: list[str] | None = Field(default=None, description="Genera in tightest ortholog group (e.g. ['Prochlorococcus', 'Synechococcus']). Use gene_homologs for full membership; genes_by_homolog_group to expand a specific group.")
        cluster_membership_count: int = Field(default=0, description="Number of cluster memberships (e.g. 3). When > 0, drill into gene_clusters_by_gene for per-cluster details.")
        cluster_types: list[str] = Field(default_factory=list, description="Distinct cluster types (e.g. ['condition_comparison', 'diel']). Use gene_clusters_by_gene with cluster_type filter to scope drill-down.")
        # Compact DM fields (always present)
        derived_metric_count: int = Field(
            default=0,
            description="Total DerivedMetric annotations on this gene (sum across numeric/boolean/categorical kinds).",
        )
        derived_metric_value_kinds: list[str] = Field(
            default_factory=list,
            description="Subset of {numeric, boolean, categorical} where this gene has DM annotations. Use to route to genes_by_{kind}_metric drill-downs.",
        )
        # verbose-only
        gene_summary: str | None = Field(default=None, description="Concatenated summary text (e.g. 'prmA :: ribosomal protein L11 methyltransferase :: Methylates ribosomal protein L11')")
        function_description: str | None = Field(default=None, description="Curated functional description (e.g. 'Methylates ribosomal protein L11'). May be null when no curated text exists.")
        all_identifiers: list[str] | None = Field(default=None, description="Cross-references: UniProt, CyanorakID, RefSeq, etc. (e.g. ['CK_Pro_MED4_00845', 'Q7V1M0', 'WP_011132479.1'])")
        # Verbose-only DM fields (None on compact responses)
        numeric_metric_count: int | None = Field(default=None, description="Numeric DM count (verbose).")
        boolean_metric_count: int | None = Field(default=None, description="Boolean DM count (verbose).")
        categorical_metric_count: int | None = Field(default=None, description="Categorical DM count (verbose).")
        numeric_metric_types_observed: list[str] | None = Field(default=None, description="Numeric metric_types observed (verbose).")
        boolean_metric_types_observed: list[str] | None = Field(default=None, description="Boolean metric_types observed (verbose).")
        categorical_metric_types_observed: list[str] | None = Field(default=None, description="Categorical metric_types observed (verbose).")
        compartments_observed: list[str] | None = Field(default=None, description="DM compartments observed for this gene (verbose).")

    class OverviewOrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        count: int = Field(description="Genes from this organism (e.g. 3)")

    class OverviewCategoryBreakdown(BaseModel):
        category: str = Field(description="Gene category (e.g. 'Photosynthesis')")
        count: int = Field(description="Genes in this category (e.g. 5)")

    class OverviewAnnotationTypeBreakdown(BaseModel):
        annotation_type: str = Field(description="Ontology type (e.g. 'go_bp', 'ec', 'kegg')")
        count: int = Field(description="Genes with this annotation type (e.g. 12)")

    class GeneOverviewResponse(BaseModel):
        total_matching: int = Field(description="Genes found in KG from input locus_tags")
        by_organism: list[OverviewOrganismBreakdown] = Field(description="Gene counts per organism, sorted desc")
        by_category: list[OverviewCategoryBreakdown] = Field(description="Gene counts per category, sorted desc")
        by_annotation_type: list[OverviewAnnotationTypeBreakdown] = Field(description="Gene counts per annotation type, sorted desc")
        has_expression: int = Field(description="Genes with expression data (expression_edge_count > 0)")
        has_significant_expression: int = Field(description="Genes with significant DE observations")
        has_orthologs: int = Field(description="Genes with ortholog group membership")
        has_clusters: int = Field(description="Genes with cluster membership")
        has_derived_metrics: int = Field(
            default=0,
            description="Count of requested locus_tags carrying any DM annotation.",
        )
        returned: int = Field(description="Results in this response (0 when summary=true)")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if total_matching > returned")
        not_found: list[str] = Field(default_factory=list, description="Input locus_tags not in KG")
        results: list[GeneOverviewResult] = Field(default_factory=list, description="One row per gene")

    @mcp.tool(
        tags={"genes"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def gene_overview(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags to look up. "
            "E.g. ['PMM0001', 'PMM0845'].",
        )],
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include gene_summary, function_description, all_identifiers.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> GeneOverviewResponse:
        """Get an overview of genes: identity and data availability signals.

        Use after resolve_gene, genes_by_function, genes_by_ontology, or
        gene_homologs to understand what each gene is and what follow-up
        data exists.

        After this tool, drill into the rich axes when the per-gene signal
        is present: gene_ontology_terms (when annotation_types is non-empty),
        gene_homologs (when closest_ortholog_group_size > 0),
        gene_clusters_by_gene (when cluster_membership_count > 0),
        differential_expression_by_gene or gene_response_profile (when
        expression_edge_count > 0), gene_derived_metrics (when
        derived_metric_count > 0).
        """
        await ctx.info(f"gene_overview locus_tags={locus_tags} summary={summary}")
        try:
            conn = _conn(ctx)
            data = api.gene_overview(
                locus_tags, summary=summary, verbose=verbose,
                limit=limit, offset=offset, conn=conn,
            )
            by_organism = [OverviewOrganismBreakdown(**b) for b in data["by_organism"]]
            by_category = [OverviewCategoryBreakdown(**b) for b in data["by_category"]]
            by_annotation_type = [OverviewAnnotationTypeBreakdown(**b) for b in data["by_annotation_type"]]
            results = [GeneOverviewResult(**r) for r in data["results"]]
            return GeneOverviewResponse(
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_category=by_category,
                by_annotation_type=by_annotation_type,
                has_expression=data["has_expression"],
                has_significant_expression=data["has_significant_expression"],
                has_orthologs=data["has_orthologs"],
                has_clusters=data["has_clusters"],
                has_derived_metrics=data["has_derived_metrics"],
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                not_found=data["not_found"],
                results=results,
            )
        except ValueError as e:
            await ctx.warning(f"gene_overview error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_overview unexpected error: {e}")
            raise ToolError(f"Error in gene_overview: {e}")

    class GeneDetailResponse(BaseModel):
        total_matching: int = Field(description="Genes found from input locus_tags")
        returned: int = Field(description="Results in this response (0 when summary=true)")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if total_matching > returned")
        not_found: list[str] = Field(default_factory=list, description="Input locus_tags not in KG")
        results: list[dict] = Field(default_factory=list, description="One row per gene — all Gene node properties via g{.*}. ~30 fields including locus_tag, gene_name, product, organism_name, gene_category, annotation_quality, function_description, catalytic_activities, ec_numbers, etc. Sparse fields only present when populated. TCDB and CAZy memberships traverse Gene_has_tcdb_family / Gene_has_cazy_family edges instead.")

    @mcp.tool(
        tags={"genes"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def gene_details(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags to look up. "
            "E.g. ['PMM0001', 'sync_0001'].",
        )],
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> GeneDetailResponse:
        """Get all properties for genes.

        This is a deep-dive tool — use gene_overview for the common case.
        Returns all Gene node properties including sparse fields
        (catalytic_activities, ec_numbers, etc.). TCDB and CAZy memberships
        live on Gene_has_tcdb_family / Gene_has_cazy_family edges instead.

        For organism taxonomy, use list_organisms. For homologs, use
        gene_homologs. For ontology annotations, use gene_ontology_terms.
        """
        await ctx.info(f"gene_details locus_tags={locus_tags} summary={summary}")
        try:
            conn = _conn(ctx)
            data = api.gene_details(
                locus_tags, summary=summary, limit=limit, offset=offset, conn=conn,
            )
            return GeneDetailResponse(**data)
        except ValueError as e:
            await ctx.warning(f"gene_details error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_details unexpected error: {e}")
            raise ToolError(f"Error in gene_details: {e}")

    # --- shared models ---

    class OntologyBreakdown(BaseModel):
        id: str = Field(description="Ontology term ID (e.g. 'cyanorak.role:G.3')")
        name: str = Field(description="Ontology term name (e.g. 'Energy metabolism > Electron transport')")
        count: int = Field(description="Groups with this annotation (e.g. 42)")

    # --- gene_homologs ---

    class GeneHomologResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        organism_name: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")
        group_id: str = Field(description="Prefixed ortholog group ID for chaining to genes_by_homolog_group (e.g. 'cyanorak:CK_00000364', 'eggnog:COG0592@2')")
        consensus_gene_name: str | None = Field(default=None, description="Consensus gene name across group members (e.g. 'dnaN'). Often null.")
        consensus_product: str | None = Field(default=None, description="Consensus product across group members (e.g. 'DNA polymerase III, beta subunit')")
        taxonomic_level: str = Field(description="Taxonomic scope (e.g. 'curated', 'Prochloraceae', 'Bacteria')")
        source: str = Field(description="Source database (e.g. 'cyanorak', 'eggnog')")
        specificity_rank: int = Field(description="Group breadth: 0=curated, 1=family, 2=order, 3=domain (e.g. 0)")
        # verbose-only
        member_count: int | None = Field(default=None, description="Total genes in group (e.g. 9)")
        organism_count: int | None = Field(default=None, description="Distinct organisms in group (e.g. 9)")
        genera: list[str] | None = Field(default=None, description="Genera represented (e.g. ['Prochlorococcus', 'Synechococcus'])")
        has_cross_genus_members: str | None = Field(default=None, description="'cross_genus' or 'single_genus'")
        description: str | None = Field(default=None, description="Group description text")
        functional_description: str | None = Field(default=None, description="Functional annotation text")
        cyanorak_roles: list[dict] | None = Field(default=None,
            description="Consensus Cyanorak roles [{id, name}]. Verbose only.")
        cog_categories: list[dict] | None = Field(default=None,
            description="Consensus COG categories [{id, name}]. Verbose only.")

    class HomologOrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        count: int = Field(description="Gene×group rows for this organism (e.g. 3)")

    class HomologSourceBreakdown(BaseModel):
        source: str = Field(description="OG source (e.g. 'cyanorak')")
        count: int = Field(description="Gene×group rows from this source (e.g. 5)")

    class GeneHomologsResponse(BaseModel):
        total_matching: int = Field(description="Total gene×group rows matching filters")
        by_organism: list[HomologOrganismBreakdown] = Field(description="Gene×group counts per organism, sorted by count descending")
        by_source: list[HomologSourceBreakdown] = Field(description="Gene×group counts per source, sorted by count descending")
        returned: int = Field(description="Results in this response (0 when summary=true)")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if total_matching > returned")
        not_found: list[str] = Field(default_factory=list, description="Input locus_tags not in KG")
        no_groups: list[str] = Field(default_factory=list, description="Genes that exist but have zero matching ortholog groups")
        top_cyanorak_roles: list[OntologyBreakdown] = Field(
            default_factory=list,
            description="Top 5 CyanorakRole annotations by frequency")
        top_cog_categories: list[OntologyBreakdown] = Field(
            default_factory=list,
            description="Top 5 CogFunctionalCategory annotations by frequency")
        results: list[GeneHomologResult] = Field(default_factory=list, description="One row per gene × ortholog group")

    @mcp.tool(
        tags={"genes", "homology"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def gene_homologs(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags to look up. "
            "E.g. ['PMM0001', 'PMM0845'].",
        )],
        source: Annotated[str | None, Field(
            description="Filter by OG source: 'cyanorak' or 'eggnog'.",
        )] = None,
        taxonomic_level: Annotated[str | None, Field(
            description="Filter by taxonomic level. "
            "E.g. 'curated', 'Prochloraceae', 'Bacteria'.",
        )] = None,
        max_specificity_rank: Annotated[int | None, Field(
            description="Cap group breadth. 0=curated only, 1=+family, "
            "2=+order, 3=+domain (all).",
            ge=0, le=3,
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include group metadata: member_count, "
            "organism_count, genera, has_cross_genus_members, "
            "description, functional_description.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> GeneHomologsResponse:
        """Get ortholog group memberships for genes.

        Returns which ortholog groups each gene belongs to, ordered from most
        specific (curated) to broadest. Use for gene characterization and
        cross-organism bridging. A gene typically belongs to 1-3 groups.

        For member genes within a group, use genes_by_homolog_group.
        For text search on group names, use search_homolog_groups.
        """
        await ctx.info(f"gene_homologs locus_tags={locus_tags} source={source} "
                       f"taxonomic_level={taxonomic_level}")
        try:
            conn = _conn(ctx)
            data = api.gene_homologs(
                locus_tags, source=source,
                taxonomic_level=taxonomic_level,
                max_specificity_rank=max_specificity_rank,
                summary=summary, verbose=verbose, limit=limit, offset=offset, conn=conn,
            )
            by_organism = [HomologOrganismBreakdown(**b) for b in data["by_organism"]]
            by_source = [HomologSourceBreakdown(**b) for b in data["by_source"]]
            top_cr = [OntologyBreakdown(**b) for b in data.get("top_cyanorak_roles", [])]
            top_cc = [OntologyBreakdown(**b) for b in data.get("top_cog_categories", [])]
            results = [GeneHomologResult(**r) for r in data["results"]]
            response = GeneHomologsResponse(
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_source=by_source,
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                not_found=data["not_found"],
                no_groups=data["no_groups"],
                top_cyanorak_roles=top_cr,
                top_cog_categories=top_cc,
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of {response.total_matching} "
                           f"gene×group rows ({len(response.not_found)} not found, "
                           f"{len(response.no_groups)} no groups)")
            return response
        except ValueError as e:
            await ctx.warning(f"gene_homologs error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_homologs unexpected error: {e}")
            raise ToolError(f"Error in gene_homologs: {e}")

    class RunCypherResponse(BaseModel):
        returned: int = Field(description="Number of rows returned (e.g. 12)")
        truncated: bool = Field(
            description="True when returned == limit (more rows may exist)"
        )
        warnings: list[str] = Field(
            default_factory=list,
            description="Schema or property warnings from CyVer (non-blocking). "
            "Empty list means query is fully valid against the current KG schema.",
        )
        results: list[dict] = Field(
            default_factory=list,
            description="Raw query results, one dict per row",
        )

    @mcp.tool(
        tags={"raw", "escape-hatch"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def run_cypher(
        ctx: Context,
        query: Annotated[str, Field(
            description="Cypher query string. Write operations are blocked. "
            "A LIMIT clause is added automatically if absent.",
        )],
        limit: Annotated[int, Field(
            description="Max results.",
            ge=1,
        )] = 25,
    ) -> RunCypherResponse:
        """Execute a raw Cypher query against the knowledge graph (read-only).

        Use this as an escape hatch when other tools don't cover your query.
        Write operations are blocked. Queries are validated for syntax and schema
        correctness before execution — warnings are returned in the response.
        """
        await ctx.info(f"run_cypher limit={limit}")
        try:
            conn = _conn(ctx)
            data = api.run_cypher(query, limit=limit, conn=conn)
            response = RunCypherResponse(**data)
            await ctx.info(
                f"Returning {response.returned} rows"
                + (f" ({len(response.warnings)} warnings)" if response.warnings else "")
            )
            return response
        except ValueError as e:
            await ctx.warning(f"run_cypher error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"run_cypher unexpected error: {e}")
            raise ToolError(f"Error in run_cypher: {e}")

    # --- search_ontology ---

    class SearchOntologyResult(BaseModel):
        id: str = Field(description="Term ID (e.g. 'go:0006260')")
        name: str = Field(description="Term name (e.g. 'DNA replication')")
        score: float = Field(description="Fulltext relevance score (e.g. 5.23)")
        level: int = Field(description="Hierarchy level of this term (0 = broadest)")
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")

    class SearchOntologyResponse(BaseModel):
        total_entries: int = Field(description="Total terms in this ontology (e.g. 847)")
        total_matching: int = Field(description="Terms matching the search (e.g. 31)")
        score_max: float | None = Field(default=None, description="Highest relevance score (null if 0 matches, e.g. 5.23)")
        score_median: float | None = Field(default=None, description="Median relevance score (null if 0 matches, e.g. 2.1)")
        returned: int = Field(description="Results in this response (0 when summary=true)")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if total_matching > returned")
        results: list[SearchOntologyResult] = Field(
            default_factory=list, description="One row per matching term",
        )

    @mcp.tool(
        tags={"ontology"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def search_ontology(
        ctx: Context,
        search_text: Annotated[str, Field(
            description="Search query (Lucene syntax). "
            "E.g. 'replication', 'oxido*', 'transport AND membrane'.",
        )],
        ontology: Annotated[str, Field(
            description="Ontology to search: 'go_bp', 'go_mf', 'go_cc', "
            "'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite'.",
        )],
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
        level: Annotated[int | None, Field(
            description="Filter to terms at this hierarchy level. 0 = broadest.",
            ge=0,
        )] = None,
        tree: Annotated[str | None, Field(
            description="BRITE tree name filter (e.g. 'transporters'). "
            "Only valid when ontology='brite'.",
        )] = None,
    ) -> SearchOntologyResponse:
        """Browse ontology terms by text search (fuzzy, Lucene syntax).

        Returns term IDs for use with genes_by_ontology. Supports fuzzy (~),
        wildcards (*), exact phrases ("..."), boolean (AND, OR).
        """
        await ctx.info(f"search_ontology search_text={search_text!r} ontology={ontology}")
        try:
            conn = _conn(ctx)
            data = api.search_ontology(
                search_text, ontology, summary=summary,
                limit=limit, offset=offset,
                level=level, tree=tree, conn=conn,
            )
            results = [SearchOntologyResult(**r) for r in data["results"]]
            return SearchOntologyResponse(**{**data, "results": results})
        except ValueError as e:
            await ctx.warning(f"search_ontology error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"search_ontology unexpected error: {e}")
            raise ToolError(f"Error in search_ontology: {e}")

    # --- genes_by_ontology ---

    class GenesByOntologyResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        gene_name: str | None = Field(default=None,
            description="Gene name (e.g. 'dnaN')")
        product: str | None = Field(default=None,
            description="Gene product (e.g. 'DNA polymerase III, beta subunit')")
        gene_category: str | None = Field(default=None,
            description="Functional category (e.g. 'Replication and repair')")
        term_id: str = Field(description="Ontology term ID (e.g. 'go:0050896')")
        term_name: str = Field(description="Term name (e.g. 'response to stimulus')")
        level: int = Field(description="Hierarchy level of this term (0 = broadest)")
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
        # verbose only
        function_description: str | None = Field(default=None,
            description="Curated functional description (verbose only)")
        level_is_best_effort: bool | None = Field(default=None,
            description="True when GO term's level is best-effort min-path "
                        "(sparse: absent for non-GO or non-best-effort; "
                        "verbose only)")

    class OntologyCategoryBreakdown(BaseModel):
        category: str = Field(description="gene_category value (e.g. 'Replication and repair')")
        count: int = Field(description="Distinct gene count (e.g. 101)")

    class OntologyLevelBreakdown(BaseModel):
        level: int = Field(description="Hierarchy level (e.g. 1)")
        n_terms: int = Field(description="Distinct terms at this level")
        n_genes: int = Field(description="Distinct genes reached via this level")
        row_count: int = Field(description="(gene × term) rows at this level")

    class OntologyTermBreakdown(BaseModel):
        term_id: str = Field(description="Term ID (e.g. 'go:0050896')")
        term_name: str = Field(description="Term name (e.g. 'response to stimulus')")
        count: int = Field(description="Distinct gene count (e.g. 152)")

    class GenesByOntologyResponse(BaseModel):
        ontology: str = Field(description="Echo of input ontology (e.g. 'go_bp')")
        organism_name: str = Field(description="Single organism for all results")
        total_matching: int = Field(description="(gene × term) row count matching all filters")
        total_genes: int = Field(description="Distinct genes across results")
        total_terms: int = Field(description="Distinct terms emitted")
        total_categories: int = Field(description="Distinct gene_category values")
        genes_per_term_min: int = Field(description="Fewest genes in any surviving term")
        genes_per_term_median: float = Field(description="Median genes per term")
        genes_per_term_max: int = Field(description="Most genes in any surviving term")
        terms_per_gene_min: int = Field(description="Fewest terms for any gene")
        terms_per_gene_median: float = Field(description="Median terms per gene")
        terms_per_gene_max: int = Field(description="Most terms for any gene")
        by_category: list[OntologyCategoryBreakdown] = Field(
            description="Distinct-gene counts per gene_category, sorted desc")
        by_level: list[OntologyLevelBreakdown] = Field(
            description="Per-level summary, sorted by level asc")
        top_terms: list[OntologyTermBreakdown] = Field(
            description="Top 5 terms by distinct-gene count, tie-break term_id asc")
        n_best_effort_terms: int = Field(
            description="Distinct best-effort terms (GO-only marker; 0 for other ontologies)")
        not_found: list[str] = Field(default_factory=list,
            description="Input term_ids absent from the KG entirely")
        wrong_ontology: list[str] = Field(default_factory=list,
            description="Input term_ids present but in a different ontology label")
        wrong_level: list[str] = Field(default_factory=list,
            description="Input term_ids in the ontology but at wrong level (Mode 3 only)")
        filtered_out: list[str] = Field(default_factory=list,
            description="Input term_ids valid but outside [min, max]_gene_set_size")
        returned: int = Field(description="Rows in this response")
        offset: int = Field(default=0, description="Offset into full result set")
        truncated: bool = Field(description="True when total_matching > offset + returned")
        results: list[GenesByOntologyResult] = Field(
            default_factory=list,
            description="One row per (gene × term) pair")

    @mcp.tool(
        tags={"genes", "ontology", "enrichment"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def genes_by_ontology(
        ctx: Context,
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
        ], Field(
            description="Ontology for these term_ids / this level.",
        )],
        organism: Annotated[str, Field(
            description="Organism (case-insensitive substring match, e.g. 'MED4'). "
                        "Required — single-valued. Use list_organisms for valid values.",
        )],
        tree: Annotated[str | None, Field(
            description="BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'.",
        )] = None,
        level: Annotated[int | None, Field(
            description="Hierarchy level to roll UP to. 0 = broadest. "
                        "At least one of `level` or `term_ids` must be provided.",
            ge=0,
        )] = None,
        term_ids: Annotated[list[str] | None, Field(
            description="Ontology term IDs (from search_ontology). "
                        "Mode 1 (no `level`): expand DOWN from each input term. "
                        "Mode 3 (with `level`): scope rollup to these level-N terms.",
        )] = None,
        min_gene_set_size: Annotated[int, Field(
            description="Exclude terms with fewer organism-scoped genes than this.",
            ge=0,
        )] = 5,
        max_gene_set_size: Annotated[int, Field(
            description="Exclude terms with more organism-scoped genes than this.",
            ge=1,
        )] = 500,
        summary: Annotated[bool, Field(
            description="If true, omit `results` (envelope only).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include function_description and sparse level_is_best_effort.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max rows returned. Default 500 — this tool feeds enrichment.",
            ge=1,
        )] = 500,
        offset: Annotated[int, Field(
            description="Skip N rows before limit", ge=0,
        )] = 0,
    ) -> GenesByOntologyResponse:
        """Find (gene × term) pairs for an ontology, scoped by terms and/or level.

        Three modes:
        - term_ids only → gene discovery by pathway (walk DOWN).
        - level only → pathway definitions at level N (walk UP).
        - level + term_ids → scoped rollup (walk UP, restrict to given terms).

        Single-organism enforced. Default `limit=500` because this tool feeds
        enrichment (pathway_enrichment). For term discovery, chain from
        search_ontology. For per-gene ontology details, use gene_ontology_terms.
        """
        await ctx.info(
            f"genes_by_ontology ontology={ontology} organism={organism} "
            f"level={level} term_ids_count={len(term_ids) if term_ids else 0}"
        )
        try:
            conn = _conn(ctx)
            data = api.genes_by_ontology(
                ontology=ontology, organism=organism,
                level=level, term_ids=term_ids,
                min_gene_set_size=min_gene_set_size,
                max_gene_set_size=max_gene_set_size,
                summary=summary, verbose=verbose,
                limit=limit, offset=offset,
                tree=tree, conn=conn,
            )
            if data["wrong_ontology"]:
                await ctx.warning(
                    f"genes_by_ontology: {len(data['wrong_ontology'])} "
                    f"term_ids in wrong ontology (see response.wrong_ontology)"
                )
            if data["wrong_level"]:
                await ctx.warning(
                    f"genes_by_ontology: {len(data['wrong_level'])} "
                    f"term_ids at wrong level (see response.wrong_level)"
                )
            return GenesByOntologyResponse(**data)
        except ValueError as e:
            await ctx.warning(f"genes_by_ontology error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"genes_by_ontology unexpected error: {e}")
            raise ToolError(f"Error in genes_by_ontology: {e}")

    class OntologyTermRow(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        term_id: str = Field(description="Ontology term ID (e.g. 'go:0006260')")
        term_name: str = Field(description="Term name (e.g. 'DNA replication')")
        level: int = Field(description="Hierarchy level of this term (0 = broadest)")
        ontology_type: str | None = Field(default=None, description="Ontology type when querying all (e.g. 'go_bp')")
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
        # verbose-only
        organism_name: str | None = Field(default=None, description="Organism (e.g. 'Prochlorococcus MED4')")

    class OntologyTypeBreakdown(BaseModel):
        ontology_type: str = Field(description="Ontology type (e.g. 'go_bp', 'kegg')")
        term_count: int = Field(description="Total leaf terms in this ontology (e.g. 12)")
        gene_count: int = Field(description="Input genes with at least one term in this ontology (e.g. 8)")
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")

    class TermBreakdown(BaseModel):
        term_id: str = Field(description="Ontology term ID (e.g. 'go:0015979')")
        term_name: str = Field(description="Term name (e.g. 'photosynthesis')")
        level: int = Field(description="Hierarchy level of this term (0 = broadest)")
        ontology_type: str = Field(description="Ontology type (e.g. 'go_bp')")
        count: int = Field(description="Genes annotated to this term (e.g. 4)")

    class GeneOntologyTermsResponse(BaseModel):
        total_matching: int = Field(description="Total gene × term annotation rows")
        total_genes: int = Field(description="Distinct genes with at least one term")
        total_terms: int = Field(description="Distinct terms across all input genes")
        by_ontology: list[OntologyTypeBreakdown] = Field(description="Per ontology type: term + gene counts, sorted by term_count desc")
        by_term: list[TermBreakdown] = Field(description="Gene counts per term, sorted desc — shows shared terms across input genes")
        terms_per_gene_min: int = Field(description="Fewest leaf terms on any gene with terms (e.g. 1)")
        terms_per_gene_max: int = Field(description="Most leaf terms on any gene with terms (e.g. 15)")
        terms_per_gene_median: float = Field(description="Median leaf terms per gene with terms (e.g. 6.0)")
        returned: int = Field(description="Results in this response (0 when summary=true)")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if total_matching > returned")
        not_found: list[str] = Field(default_factory=list, description="Input locus_tags not in KG")
        no_terms: list[str] = Field(default_factory=list, description="Input locus_tags in KG but with no terms for queried ontology")
        results: list[OntologyTermRow] = Field(default_factory=list, description="One row per gene × term")

    @mcp.tool(
        tags={"genes", "ontology"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def gene_ontology_terms(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags to look up. "
            "E.g. ['PMM0001', 'PMM0845'].",
        )],
        organism: Annotated[str, Field(
            description="Organism (case-insensitive substring match, e.g. 'MED4'). Required — single-valued.",
        )],
        ontology: Annotated[
            Literal["go_bp", "go_mf", "go_cc", "kegg", "ec",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite"] | None,
            Field(description="Filter to one ontology. None returns all."),
        ] = None,
        mode: Annotated[Literal["leaf", "rollup"], Field(
            description="'leaf' returns most-specific annotations (default). "
                        "'rollup' walks up to ancestors at the given level.",
        )] = "leaf",
        level: Annotated[int | None, Field(
            description="Hierarchy level. In leaf mode: filter to leaves at this level. "
                        "In rollup mode: required — target ancestor level (0 = broadest).",
            ge=0,
        )] = None,
        tree: Annotated[str | None, Field(
            description="BRITE tree name filter. Only valid when ontology='brite'.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include organism_name per row.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> GeneOntologyTermsResponse:
        """Get ontology annotations for genes. One row per gene × term.

        In leaf mode (default), returns the most specific annotations only —
        redundant ancestor terms are excluded. In rollup mode, walks up to
        ancestors at the given level.

        Use ontology param to filter to one type, or omit for all.
        For the reverse direction (find genes annotated to a term, with hierarchy
        expansion), use genes_by_ontology. Use search_ontology to find terms by text.
        """
        await ctx.info(
            f"gene_ontology_terms locus_tags={locus_tags} organism={organism} "
            f"ontology={ontology} mode={mode} level={level}"
        )
        try:
            conn = _conn(ctx)
            data = api.gene_ontology_terms(
                locus_tags, organism=organism, ontology=ontology,
                mode=mode, level=level, tree=tree,
                summary=summary, verbose=verbose, limit=limit, offset=offset, conn=conn,
            )
            results = [OntologyTermRow(**r) for r in data["results"]]
            by_ontology = [OntologyTypeBreakdown(**b) for b in data["by_ontology"]]
            by_term = [TermBreakdown(**b) for b in data["by_term"]]
            return GeneOntologyTermsResponse(
                **{**data, "results": results, "by_ontology": by_ontology, "by_term": by_term},
            )
        except ValueError as e:
            await ctx.warning(f"gene_ontology_terms error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_ontology_terms unexpected error: {e}")
            raise ToolError(f"Error in gene_ontology_terms: {e}")

    class PublicationResult(BaseModel):
        doi: str
        title: str
        authors: list[str]
        year: int
        journal: str | None = None
        study_type: str | None = None
        organisms: list[str] = Field(default=[], description="Organisms studied in this publication")
        experiment_count: int = Field(default=0, description="Number of experiments in KG from this publication")
        treatment_types: list[str] = Field(default=[], description="Experiment treatment types (e.g. coculture, nitrogen_stress)")
        background_factors: list[str] = Field(default_factory=list, description="Distinct background factors across experiments (e.g. ['axenic', 'diel_cycle'])")
        omics_types: list[str] = Field(default=[], description="Omics data types (e.g. RNASEQ, PROTEOMICS)")
        clustering_analysis_count: int = Field(default=0, description="Number of clustering analyses from this publication (e.g. 4)")
        cluster_types: list[str] = Field(default_factory=list, description="Distinct cluster types (e.g. ['condition_comparison'])")
        growth_phases: list[str] = Field(default_factory=list, description="Distinct growth phases across experiments. Physiological state of the culture at sampling — timepoint-level, not gene-specific.")
        derived_metric_count: int = Field(default=0, description="Number of DerivedMetric nodes from this publication (e.g. 3)")
        derived_metric_value_kinds: list[str] = Field(default_factory=list, description="Value kinds of DerivedMetrics in this publication (e.g. ['numeric', 'boolean'])")
        compartments: list[str] = Field(default_factory=list, description="Wet-lab compartments measured in this publication (e.g. ['whole_cell', 'vesicle'])")
        score: float | None = Field(default=None, description="Lucene relevance score (only with search_text)")

        abstract: str | None = Field(default=None, description="Publication abstract (only with verbose=True)")
        description: str | None = Field(default=None, description="Curated study description (only with verbose=True)")
        cluster_count: int | None = Field(default=None, description="Total gene clusters across analyses (only with verbose=True, e.g. 20)")
        derived_metric_gene_count: int | None = Field(default=None, description="Total genes annotated by DerivedMetrics in this publication (only with verbose=True)")
        derived_metric_types: list[str] | None = Field(default=None, description="Distinct DerivedMetric types in this publication (only with verbose=True, e.g. ['diel_rhythmicity'])")

    class PubOrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        count: int = Field(description="Number of publications studying this organism (e.g. 11)")

    class PubTreatmentTypeBreakdown(BaseModel):
        treatment_type: str = Field(description="Treatment category (e.g. 'coculture')")
        count: int = Field(description="Number of publications (e.g. 5)")

    class PubOmicsTypeBreakdown(BaseModel):
        omics_type: str = Field(description="Omics platform (e.g. 'RNASEQ')")
        count: int = Field(description="Number of publications (e.g. 12)")

    class PubBackgroundFactorBreakdown(BaseModel):
        background_factor: str = Field(description="Background factor (e.g. 'axenic', 'diel_cycle')")
        count: int = Field(description="Number of publications (e.g. 5)")

    class PubClusterTypeBreakdown(BaseModel):
        cluster_type: str = Field(description="Cluster type (e.g. 'condition_comparison')")
        count: int = Field(description="Number of publications (e.g. 4)")

    class PubValueKindBreakdown(BaseModel):
        value_kind: str = Field(description="DerivedMetric value kind (e.g. 'numeric', 'boolean', 'categorical')")
        count: int = Field(description="Number of publications with this value kind (e.g. 3)")

    class PubMetricTypeBreakdown(BaseModel):
        metric_type: str = Field(description="DerivedMetric type (e.g. 'diel_rhythmicity', 'darkness_survival_class')")
        count: int = Field(description="Number of publications with this metric type (e.g. 2)")

    class PubCompartmentBreakdown(BaseModel):
        compartment: str = Field(description="Wet-lab compartment (e.g. 'whole_cell', 'vesicle')")
        count: int = Field(description="Number of publications with this compartment (e.g. 5)")

    class ListPublicationsResponse(BaseModel):
        total_entries: int = Field(description="Total publications in KG (unfiltered)")
        total_matching: int = Field(description="Publications matching filters")
        by_organism: list[PubOrganismBreakdown] = Field(description="Publication counts per organism, sorted by count descending")
        by_treatment_type: list[PubTreatmentTypeBreakdown] = Field(description="Publication counts per treatment type, sorted by count descending")
        by_background_factors: list[PubBackgroundFactorBreakdown] = Field(description="Publication counts per background factor, sorted by count descending")
        by_omics_type: list[PubOmicsTypeBreakdown] = Field(description="Publication counts per omics platform, sorted by count descending")
        by_cluster_type: list[PubClusterTypeBreakdown] = Field(default_factory=list, description="Publication counts per cluster type, sorted by count descending")
        by_value_kind: list[PubValueKindBreakdown] = Field(default_factory=list, description="DerivedMetric value kind frequency rollup across matched publications. Each entry: {value_kind, count}.")
        by_metric_type: list[PubMetricTypeBreakdown] = Field(default_factory=list, description="DerivedMetric type frequency rollup across matched publications. Each entry: {metric_type, count}.")
        by_compartment: list[PubCompartmentBreakdown] = Field(default_factory=list, description="Wet-lab compartment frequency rollup across matched publications. Each entry: {compartment, count}.")
        returned: int = Field(description="Publications in this response")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if total_matching > returned")
        not_found: list[str] = Field(default_factory=list, description="Input publication_dois that did not match any Publication node (empty unless publication_dois was provided)")
        results: list[PublicationResult]

    @mcp.tool(
        tags={"publications", "discovery"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def list_publications(
        ctx: Context,
        organism: Annotated[str | None, Field(
            description="Filter by organism name (case-insensitive). "
            "E.g. 'MED4', 'HOT1A3'.",
        )] = None,
        treatment_type: Annotated[str | None, Field(
            description="Filter by experiment treatment type. "
            "Use list_filter_values for valid values.",
        )] = None,
        background_factors: Annotated[str | None, Field(
            description="Filter by background factor (case-insensitive exact match). "
            "E.g. 'axenic'.",
        )] = None,
        growth_phases: Annotated[str | None, Field(
            description="Filter by growth phase (case-insensitive). "
            "E.g. 'exponential', 'nutrient_limited'.",
        )] = None,
        search_text: Annotated[str | None, Field(
            description="Free-text search on title, abstract, and description "
            "(Lucene syntax). E.g. 'nitrogen', 'co-culture AND phage'.",
        )] = None,
        author: Annotated[str | None, Field(
            description="Filter by author name (case-insensitive). "
            "E.g. 'Sher', 'Chisholm'.",
        )] = None,
        publication_dois: Annotated[list[str] | None, Field(
            description="Restrict to specific publications by DOI (case-insensitive). "
            "Combines with other filters via AND. `not_found` in the response "
            "lists any provided DOIs that did not match. Mirrors the filter "
            "shape on sibling list_* tools (list_experiments.experiment_ids).",
        )] = None,
        compartment: Annotated[str | None, Field(
            description="Filter to publications with at least one experiment in this "
            "wet-lab compartment (e.g. 'vesicle', 'whole_cell'). "
            "Use list_filter_values(filter_type='compartment') to enumerate valid values.",
        )] = None,
        verbose: Annotated[bool, Field(
            description="Include abstract and description. "
            "Default compact for routing.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> ListPublicationsResponse:
        """List publications with expression data in the knowledge graph.

        Returns publication metadata and experiment summaries. Use this as
        an entry point to discover what studies exist.

        After this tool, drill in via:
        - list_experiments(publication_doi=[doi]) for per-experiment detail
        - genes_by_function(organism=...) / genes_by_ontology(organism=..., term_ids=...) for gene discovery scoped to the publication's organism(s)
        - list_clustering_analyses(publication_doi=[doi]) for clustering analyses
        - list_derived_metrics(publication_doi=[doi]) for non-DE evidence
        """
        await ctx.info(f"list_publications organism={organism} treatment_type={treatment_type} "
                       f"growth_phases={growth_phases} search_text={search_text} author={author} "
                       f"compartment={compartment} offset={offset}")
        try:
            conn = _conn(ctx)
            result = api.list_publications(
                organism=organism, treatment_type=treatment_type,
                background_factors=background_factors,
                growth_phases=growth_phases,
                search_text=search_text, author=author,
                publication_dois=publication_dois,
                compartment=compartment,
                verbose=verbose, limit=limit, offset=offset, conn=conn,
            )
            results = [PublicationResult(**r) for r in result["results"]]
            by_organism = [PubOrganismBreakdown(**b) for b in result["by_organism"]]
            by_treatment_type = [PubTreatmentTypeBreakdown(**b) for b in result["by_treatment_type"]]
            by_background_factors = [PubBackgroundFactorBreakdown(**b) for b in result["by_background_factors"]]
            by_omics_type = [PubOmicsTypeBreakdown(**b) for b in result["by_omics_type"]]
            by_cluster_type = [PubClusterTypeBreakdown(**b) for b in result.get("by_cluster_type", [])]
            by_value_kind = [PubValueKindBreakdown(**b) for b in result.get("by_value_kind", [])]
            by_metric_type = [PubMetricTypeBreakdown(**b) for b in result.get("by_metric_type", [])]
            by_compartment = [PubCompartmentBreakdown(**b) for b in result.get("by_compartment", [])]
            response = ListPublicationsResponse(
                total_entries=result["total_entries"],
                total_matching=result["total_matching"],
                by_organism=by_organism,
                by_treatment_type=by_treatment_type,
                by_background_factors=by_background_factors,
                by_omics_type=by_omics_type,
                by_cluster_type=by_cluster_type,
                by_value_kind=by_value_kind,
                by_metric_type=by_metric_type,
                by_compartment=by_compartment,
                returned=result["returned"],
                offset=result.get("offset", 0),
                truncated=result["truncated"],
                not_found=result.get("not_found", []),
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of {response.total_matching} "
                           f"matching publications ({response.total_entries} total in KG)")
            return response
        except ValueError as e:
            await ctx.warning(f"list_publications error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"list_publications unexpected error: {e}")
            raise ToolError(f"Error in list_publications: {e}")

    # --- list_experiments ---

    class GeneStatusBreakdown(BaseModel):
        significant_up: int = Field(default=0, description="Genes with significant upregulation (e.g. 245)")
        significant_down: int = Field(default=0, description="Genes with significant downregulation (e.g. 178)")
        not_significant: int = Field(default=0, description="Genes not meeting significance threshold (e.g. 1273)")

    class TimePoint(BaseModel):
        timepoint: str | None = Field(default=None, description="Time point label, null if unlabeled (e.g. '24h', '5h extended darkness (40h)')")
        timepoint_order: int = Field(description="Sort order within experiment (e.g. 1, 2, 3)")
        timepoint_hours: float | None = Field(default=None, description="Time in hours, null if unknown (e.g. 24.0)")
        growth_phase: str | None = Field(default=None, description="Growth phase observed at this timepoint (e.g. 'exponential', 'nutrient_limited', 'death'). Null when not annotated.")
        gene_count: int = Field(description="Total genes with expression data at this time point (e.g. 1696)")
        genes_by_status: GeneStatusBreakdown = Field(description="Gene counts by expression status at this time point")

    class ExperimentResult(BaseModel):
        # compact fields (always returned)
        experiment_id: str = Field(description="Experiment identifier (e.g. '10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq')")
        experiment_name: str = Field(description="Experiment display name (e.g. 'MED4 Coculture with Alteromonas HOT1A3 vs Pro99 medium growth conditions (RNASEQ)')")
        publication_doi: str = Field(description="Publication DOI (e.g. '10.1038/ismej.2016.70')")
        authors: list[str] = Field(default_factory=list, description="Publication authors (e.g. ['Smith J', 'Jones K']). Sourced from Publication.authors via the Has_experiment edge — no need to join with list_publications for author attribution.")
        organism_name: str = Field(description="Profiled organism (e.g. 'Prochlorococcus MED4')")
        treatment_type: list[str] = Field(description="Treatment categories (e.g. ['coculture'], ['nitrogen_stress', 'coculture'])")
        background_factors: list[str] = Field(default_factory=list, description="Background experimental factors (e.g. ['axenic', 'continuous_light']). Empty list when none specified.")
        coculture_partner: str | None = Field(default=None, description="Interacting organism — coculture partner or phage. Null when no interacting organism (e.g. 'Alteromonas macleodii HOT1A3', 'Phage')")
        omics_type: str = Field(description="Omics platform (e.g. 'RNASEQ', 'MICROARRAY', 'PROTEOMICS')")
        is_time_course: bool = Field(description="Whether experiment has multiple time points")
        table_scope: str | None = Field(default=None, description="What genes the source DE table contains. Values: all_detected_genes, significant_any_timepoint, significant_only, top_n, filtered_subset. Critical for interpreting missing genes.")
        table_scope_detail: str | None = Field(default=None, description="Free-text clarification of table_scope (e.g. 'FDR < 0.05 and |logFC| > 0.8')")
        gene_count: int = Field(description="Cumulative row count across timepoints (= sum(time_point_totals) for time-course experiments). For a 6-TP experiment with 1697 genes/TP, gene_count=10182. For non-time-course experiments equals distinct_gene_count.")
        distinct_gene_count: int = Field(description="Distinct gene count across the experiment — number of distinct gene IDs with at least one measurement edge, regardless of timepoint. Use for detection-power / pathway-background sizing. distinct_gene_count <= gene_count; for the same 6-TP example, distinct_gene_count=1697 vs gene_count=10182.")
        genes_by_status: GeneStatusBreakdown = Field(description="Gene counts by expression status")
        timepoints: list[TimePoint] | None = Field(default=None, description="Per-timepoint gene counts. Omitted for non-time-course experiments.")
        clustering_analysis_count: int = Field(default=0, description="Number of clustering analyses for this experiment (e.g. 4)")
        cluster_types: list[str] = Field(default_factory=list, description="Distinct cluster types (e.g. ['condition_comparison'])")
        growth_phases: list[str] = Field(default_factory=list, description="Distinct growth phases in this experiment. Physiological state of the culture at sampling — timepoint-level, not gene-specific.")
        derived_metric_count: int = Field(default=0, description="Number of DerivedMetrics associated with this experiment (e.g. 4)")
        derived_metric_value_kinds: list[str] = Field(default_factory=list, description="Distinct DerivedMetric value kinds for this experiment (e.g. ['numeric', 'boolean'])")
        compartment: str | None = Field(default=None, description="Wet-lab fraction this experiment profiles (e.g. 'whole_cell', 'vesicle', 'exoproteome'). Scalar per experiment.")
        score: float | None = Field(default=None, description="Lucene relevance score, present only when search_text is used (e.g. 2.45)")
        # verbose-only fields
        publication_title: str | None = Field(default=None, description="Publication title")
        treatment: str | None = Field(default=None, description="Treatment description (e.g. 'Coculture with Alteromonas HOT1A3')")
        control: str | None = Field(default=None, description="Control description (e.g. 'Pro99 medium growth conditions')")
        light_condition: str | None = Field(default=None, description="Light regime (e.g. 'continuous light')")
        light_intensity: str | None = Field(default=None, description="Light intensity (e.g. '10 umol photons m-2 s-1')")
        medium: str | None = Field(default=None, description="Growth medium (e.g. 'Pro99')")
        temperature: str | None = Field(default=None, description="Temperature (e.g. '24C')")
        statistical_test: str | None = Field(default=None, description="Statistical method (e.g. 'Rockhopper')")
        experimental_context: str | None = Field(default=None, description="Context summary (e.g. 'in Pro99 medium under continuous light')")
        cluster_count: int | None = Field(default=None, description="Total gene clusters across analyses (only with verbose=True, e.g. 20)")
        derived_metric_gene_count: int | None = Field(default=None, description="Number of distinct genes with DerivedMetric annotations in this experiment (only with verbose=True, e.g. 450)")
        derived_metric_types: list[str] | None = Field(default=None, description="Distinct DerivedMetric metric_type values for this experiment (only with verbose=True, e.g. ['damping_ratio', 'diel_amplitude'])")
        reports_derived_metric_types: list[str] | None = Field(default=None, description="DerivedMetric types reported by (not just associated with) this experiment (only with verbose=True)")

    class OrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        count: int = Field(description="Number of experiments for this organism (e.g. 46)")

    class TreatmentTypeBreakdown(BaseModel):
        treatment_type: str = Field(description="Treatment category (e.g. 'coculture')")
        count: int = Field(description="Number of experiments (e.g. 16)")

    class BackgroundFactorBreakdown(BaseModel):
        background_factor: str = Field(description="Background factor (e.g. 'axenic', 'diel_cycle')")
        count: int = Field(description="Number of experiments (e.g. 14)")

    class OmicsTypeBreakdown(BaseModel):
        omics_type: str = Field(description="Omics platform (e.g. 'RNASEQ')")
        count: int = Field(description="Number of experiments (e.g. 48)")

    class PublicationBreakdown(BaseModel):
        publication_doi: str = Field(description="Publication DOI (e.g. '10.1038/ismej.2016.70')")
        count: int = Field(description="Number of experiments from this publication (e.g. 5)")

    class TableScopeBreakdown(BaseModel):
        table_scope: str = Field(description="Table scope value (e.g. 'all_detected_genes', 'significant_only')")
        count: int = Field(description="Number of experiments with this scope (e.g. 22)")

    class ClusterTypeBreakdown(BaseModel):
        cluster_type: str = Field(description="Cluster type (e.g. 'condition_comparison')")
        count: int = Field(description="Number of experiments with this cluster type (e.g. 7)")

    class GrowthPhaseBreakdown(BaseModel):
        growth_phase: str = Field(description="Growth phase (e.g. 'exponential'). Physiological state of the culture at sampling — timepoint-level, not gene-specific.")
        count: int = Field(description="Number of experiments with this growth phase")

    class ExpValueKindBreakdown(BaseModel):
        value_kind: str = Field(description="DerivedMetric value kind (e.g. 'numeric', 'boolean', 'categorical')")
        count: int = Field(description="Number of experiments whose DMs include this value kind (e.g. 15)")

    class ExpMetricTypeBreakdown(BaseModel):
        metric_type: str = Field(description="DerivedMetric type name (e.g. 'damping_ratio', 'diel_amplitude_protein_log2')")
        count: int = Field(description="Number of experiments associated with DMs of this type (e.g. 4)")

    class ExpCompartmentBreakdown(BaseModel):
        compartment: str = Field(description="Wet-lab fraction (e.g. 'whole_cell', 'vesicle', 'exoproteome')")
        count: int = Field(description="Number of experiments in this compartment (e.g. 160)")

    class ListExperimentsResponse(BaseModel):
        total_entries: int = Field(description="Total experiments in the KG (unfiltered)")
        total_matching: int = Field(description="Experiments matching filters")
        returned: int = Field(description="Number of results returned (0 when summary=true)")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if results were truncated by limit or summary=true")
        by_organism: list[OrganismBreakdown] = Field(description="Experiment counts per organism, sorted by count descending")
        by_treatment_type: list[TreatmentTypeBreakdown] = Field(description="Experiment counts per treatment type, sorted by count descending")
        by_background_factors: list[BackgroundFactorBreakdown] = Field(description="Experiment counts per background factor, sorted by count descending")
        by_omics_type: list[OmicsTypeBreakdown] = Field(description="Experiment counts per omics platform, sorted by count descending")
        by_publication: list[PublicationBreakdown] = Field(description="Experiment counts per publication, sorted by count descending")
        by_table_scope: list[TableScopeBreakdown] = Field(description="Experiment counts per table scope, sorted by count descending")
        by_cluster_type: list[ClusterTypeBreakdown] = Field(default_factory=list, description="Experiment counts per cluster type, sorted by count descending")
        by_growth_phase: list[GrowthPhaseBreakdown] = Field(default_factory=list, description="Experiment counts per growth phase, sorted by count descending")
        by_value_kind: list[ExpValueKindBreakdown] = Field(default_factory=list, description="Experiment counts by DerivedMetric value_kind across matching experiments")
        by_metric_type: list[ExpMetricTypeBreakdown] = Field(default_factory=list, description="Experiment counts by DerivedMetric metric_type across matching experiments")
        by_compartment: list[ExpCompartmentBreakdown] = Field(default_factory=list, description="Experiment counts per wet-lab compartment (e.g. whole_cell, vesicle, exoproteome)")
        time_course_count: int = Field(description="Number of time-course experiments in matching set")
        score_max: float | None = Field(default=None, description="Max Lucene relevance score, present only when search_text is used (e.g. 4.52)")
        score_median: float | None = Field(default=None, description="Median Lucene relevance score, present only when search_text is used (e.g. 1.23)")
        not_found: list[str] = Field(default_factory=list, description="Input experiment_ids that did not match any Experiment node (empty unless experiment_ids was provided)")
        results: list[ExperimentResult] = Field(description="Individual experiments (empty when summary=true)")

    @mcp.tool(
        tags={"experiments", "expression", "discovery"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def list_experiments(
        ctx: Context,
        organism: Annotated[str | None, Field(
            description=(
                "Filter to experiments where this organism is the profiled "
                "organism (case-insensitive substring on organism_name). "
                "For partner-side filtering, use coculture_partner=; the two "
                "filters AND-compose."
            ),
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Filter by treatment type(s) (case-insensitive exact match). "
            "E.g. ['coculture', 'nitrogen_stress']. "
            "Use list_filter_values to see valid values.",
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Filter by background experimental factors (case-insensitive exact match). "
            "E.g. ['axenic', 'diel_cycle']. "
            "Background factors describe experimental context beyond the primary treatment.",
        )] = None,
        growth_phases: Annotated[list[str] | None, Field(
            description="Filter by growth phase(s) (case-insensitive). "
            "Physiological state of the culture at sampling time. "
            "E.g. ['exponential', 'nutrient_limited'].",
        )] = None,
        omics_type: Annotated[list[str] | None, Field(
            description="Filter by omics platform(s) (case-insensitive). "
            "E.g. ['RNASEQ', 'PROTEOMICS'].",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Filter by publication DOI(s) (case-insensitive exact match). "
            "Get DOIs from list_publications. "
            "E.g. ['10.1038/ismej.2016.70'].",
        )] = None,
        coculture_partner: Annotated[str | None, Field(
            description="Filter by coculture partner organism (case-insensitive "
            "partial match). Narrows coculture experiments. "
            "E.g. 'Alteromonas', 'HOT1A3'.",
        )] = None,
        search_text: Annotated[str | None, Field(
            description="Free-text search on experiment name, treatment, control, "
            "experimental context, and light condition (Lucene fulltext, "
            "case-insensitive). E.g. 'continuous light', 'diel'.",
        )] = None,
        time_course_only: Annotated[bool, Field(
            description="If true, return only time-course experiments "
            "(multiple time points).",
        )] = False,
        table_scope: Annotated[list[str] | None, Field(
            description="Filter by table scope — what genes the source DE table "
            "contains. Values: 'all_detected_genes', "
            "'significant_any_timepoint', 'significant_only', 'top_n', "
            "'filtered_subset'. E.g. ['all_detected_genes'] for fair "
            "cross-experiment comparison.",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Restrict to specific experiments by id (exact match). "
            "Combines with other filters via AND. `not_found` in the response "
            "lists any provided ids that did not match. Mirrors the filter "
            "shape on sibling tools (pathway_enrichment, ontology_landscape).",
        )] = None,
        compartment: Annotated[str | None, Field(
            description="Filter by wet-lab fraction (exact match on scalar "
            "Experiment.compartment). E.g. 'whole_cell', 'vesicle', "
            "'exoproteome'. Use list_filter_values(filter_type='compartment') "
            "to enumerate valid values.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary breakdowns (by organism, "
            "treatment type, omics type, table scope) with no individual "
            "experiments. Use to orient before drilling into detail.",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include publication title, "
            "treatment/control descriptions, and experimental conditions "
            "(light, medium, temperature, statistical test, context).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> ListExperimentsResponse:
        """List differential expression experiments in the knowledge graph.

        Returns summary breakdowns (by organism, treatment type, omics type,
        table scope) plus individual experiments. Use summary=true to see only
        breakdowns, then drill into detail with filters.

        table_scope indicates what genes each experiment's source DE table
        contains — critical for interpreting missing genes. Use
        table_scope=['all_detected_genes'] to restrict to experiments that
        report all assayed genes (fair for cross-experiment comparison).

        After this tool, drill in via:
        - differential_expression_by_gene(experiment_ids=[id]) for per-gene DE
        - list_clustering_analyses(experiment_ids=[id]) for clusters built from this experiment
        - list_derived_metrics(experiment_ids=[id]) for DM evidence on this experiment
        - pathway_enrichment(experiment_ids=[id]) for ORA on DE results
        """
        await ctx.info(f"list_experiments summary={summary} organism={organism} "
                       f"treatment_type={treatment_type} search_text={search_text}")
        try:
            conn = _conn(ctx)
            result = api.list_experiments(
                organism=organism, treatment_type=treatment_type,
                background_factors=background_factors,
                growth_phases=growth_phases,
                omics_type=omics_type, publication_doi=publication_doi,
                coculture_partner=coculture_partner, search_text=search_text,
                time_course_only=time_course_only, table_scope=table_scope,
                experiment_ids=experiment_ids, compartment=compartment,
                summary=summary,
                verbose=verbose, limit=limit, offset=offset, conn=conn,
            )

            # Build breakdown models
            by_organism = [OrganismBreakdown(**b) for b in result["by_organism"]]
            by_treatment_type = [TreatmentTypeBreakdown(**b) for b in result["by_treatment_type"]]
            by_background_factors = [BackgroundFactorBreakdown(**b) for b in result["by_background_factors"]]
            by_omics_type = [OmicsTypeBreakdown(**b) for b in result["by_omics_type"]]
            by_publication = [PublicationBreakdown(**b) for b in result["by_publication"]]
            by_table_scope = [TableScopeBreakdown(**b) for b in result["by_table_scope"]]
            by_cluster_type = [ClusterTypeBreakdown(**b) for b in result.get("by_cluster_type", [])]
            by_growth_phase = [GrowthPhaseBreakdown(**b) for b in result.get("by_growth_phase", [])]
            by_value_kind = [ExpValueKindBreakdown(**b) for b in result.get("by_value_kind", [])]
            by_metric_type = [ExpMetricTypeBreakdown(**b) for b in result.get("by_metric_type", [])]
            by_compartment = [ExpCompartmentBreakdown(**b) for b in result.get("by_compartment", [])]

            # Build result models (empty list when summary=True)
            experiments = []
            for r in result["results"]:
                tp_data = r.get("timepoints")
                tp_list = (
                    [TimePoint(genes_by_status=GeneStatusBreakdown(**tp.pop("genes_by_status")), **tp)
                     for tp in tp_data]
                    if tp_data else None
                )
                gbs = GeneStatusBreakdown(**r.pop("genes_by_status"))
                experiments.append(ExperimentResult(
                    **{k: v for k, v in r.items() if k != "timepoints"},
                    genes_by_status=gbs,
                    timepoints=tp_list,
                ))

            response = ListExperimentsResponse(
                total_entries=result["total_entries"],
                total_matching=result["total_matching"],
                returned=result["returned"],
                offset=result.get("offset", 0),
                truncated=result["truncated"],
                by_organism=by_organism,
                by_treatment_type=by_treatment_type,
                by_background_factors=by_background_factors,
                by_omics_type=by_omics_type,
                by_publication=by_publication,
                by_table_scope=by_table_scope,
                by_cluster_type=by_cluster_type,
                by_growth_phase=by_growth_phase,
                by_value_kind=by_value_kind,
                by_metric_type=by_metric_type,
                by_compartment=by_compartment,
                time_course_count=result["time_course_count"],
                score_max=result.get("score_max"),
                score_median=result.get("score_median"),
                not_found=result.get("not_found", []),
                results=experiments,
            )
            await ctx.info(f"Returning {response.returned} of {response.total_matching} "
                           f"matching experiments ({response.total_entries} total in KG)")
            return response
        except ValueError as e:
            await ctx.warning(f"list_experiments error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"list_experiments unexpected error: {e}")
            raise ToolError(f"Error in list_experiments: {e}")

    # ------------------------------------------------------------------
    # Differential expression by gene
    # ------------------------------------------------------------------

    class ExpressionStatusBreakdown(BaseModel):
        significant_up: int = Field(
            default=0,
            description="Rows with significant upregulation (e.g. 3)",
        )
        significant_down: int = Field(
            default=0,
            description="Rows with significant downregulation (e.g. 1)",
        )
        not_significant: int = Field(
            default=0,
            description="Rows not meeting significance threshold (e.g. 12)",
        )

    class ExpressionTimepoint(BaseModel):
        timepoint: str | None = Field(
            description="Timepoint label (e.g. 'day 18', 'days 60+89')."
            " Null when edge has no label.",
        )
        timepoint_hours: float | None = Field(
            description="Hours numeric value (e.g. 432.0)."
            " Null for non-numeric labels like 'days 60+89'.",
        )
        timepoint_order: int = Field(
            description="Sort key for time course reconstruction (e.g. 1)",
        )
        matching_genes: int = Field(
            description="Distinct genes at this timepoint (e.g. 5)",
        )
        rows_by_status: ExpressionStatusBreakdown = Field(
            description="Row counts by expression_status at this timepoint",
        )
        growth_phase: str | None = Field(
            default=None,
            description="Physiological state at this timepoint. Timepoint-level, not gene-specific.",
        )

    class ExpressionByExperiment(BaseModel):
        experiment_id: str = Field(
            description="Experiment ID (e.g. '10.1101/2025.11.24.690089_...')",
        )
        experiment_name: str = Field(
            description="Human-readable name"
            " (e.g. 'HOT1A3 PRO99-lowN nutrient starvation (RNASEQ)')",
        )
        treatment_type: list[str] = Field(
            description="Treatment categories"
            " (e.g. ['nitrogen_stress'], ['nitrogen_stress', 'coculture'])",
        )
        background_factors: list[str] = Field(
            default_factory=list,
            description="Background experimental factors",
        )
        omics_type: str = Field(
            description="Omics type (e.g. 'RNASEQ', 'PROTEOMICS')",
        )
        coculture_partner: str | None = Field(
            default=None,
            description="Coculture partner organism, if applicable",
        )
        is_time_course: str = Field(
            description="'true' or 'false'",
        )
        table_scope: str = Field(
            description="What genes the source DE table contains."
            " Values: all_detected_genes, significant_any_timepoint,"
            " significant_only, top_n, filtered_subset."
            " Critical for interpreting missing genes.",
        )
        table_scope_detail: str | None = Field(
            default=None,
            description="Free-text clarification of table_scope"
            " (e.g. 'Top 50% of genes by expression level').",
        )
        matching_genes: int = Field(
            description="Distinct genes with data in this experiment (e.g. 5)",
        )
        rows_by_status: ExpressionStatusBreakdown = Field(
            description="Row counts by expression_status across all timepoints",
        )
        timepoints: list[ExpressionTimepoint] | None = Field(
            default=None,
            description="Per-timepoint breakdown, sorted by timepoint_order."
            " Null for non-time-course experiments.",
        )

    class ExpressionTopCategory(BaseModel):
        category: str = Field(
            description="Gene category (e.g. 'Signal transduction')",
        )
        total_genes: int = Field(
            description="All input genes in this category (e.g. 2)",
        )
        significant_genes: int = Field(
            description="Genes with at least one significant row (e.g. 2)",
        )

    class ExpressionRow(BaseModel):
        # Compact (always present)
        locus_tag: str = Field(
            description="Gene locus tag (e.g. 'ACZ81_01830')",
        )
        gene_name: str | None = Field(
            description="Gene name (e.g. 'amtB'). Null if unannotated.",
        )
        experiment_id: str = Field(
            description="Experiment ID (e.g. '10.1101/2025.11.24.690089_...')",
        )
        treatment_type: list[str] = Field(
            description="Treatment types from experiment"
            " (e.g. ['nitrogen_stress'])",
        )
        timepoint: str | None = Field(
            description="Timepoint label (e.g. 'days 60+89')."
            " Null when edge has no label.",
        )
        timepoint_hours: float | None = Field(
            description="Numeric hours (e.g. 432.0)."
            " Null for non-numeric labels.",
        )
        timepoint_order: int = Field(
            description="Sort key for time course order (e.g. 3)",
        )
        log2fc: float = Field(
            description="Log2 fold change (e.g. 3.591). Positive = up.",
        )
        padj: float | None = Field(
            description="Adjusted p-value (e.g. 1.13e-12)."
            " Null if not computed.",
        )
        rank: int = Field(
            description="Rank by |log2FC| within experiment x timepoint;"
            " 1 = strongest (e.g. 77)",
        )
        rank_up: int | None = Field(
            default=None,
            description="Rank by |log2FC| among significant_up genes"
            " within experiment x timepoint."
            " Null if not significant_up. 1 = strongest.",
        )
        rank_down: int | None = Field(
            default=None,
            description="Rank by |log2FC| among significant_down genes"
            " within experiment x timepoint."
            " Null if not significant_down. 1 = strongest.",
        )
        expression_status: Literal[
            "significant_up", "significant_down", "not_significant"
        ] = Field(
            description="Significance call using publication-specific"
            " threshold (e.g. 'significant_up')",
        )
        growth_phase: str | None = Field(
            default=None,
            description="Physiological state of the culture at this timepoint "
            "(e.g. 'exponential', 'nutrient_limited'). "
            "Timepoint-level condition — not gene-specific.",
        )
        # Verbose (present when verbose=True)
        product: str | None = Field(
            default=None,
            description="Gene product description"
            " (e.g. 'Ammonium transporter')",
        )
        experiment_name: str | None = Field(
            default=None,
            description="Human-readable experiment name",
        )
        treatment: str | None = Field(
            default=None,
            description="Treatment details"
            " (e.g. 'PRO99-lowN nutrient starvation')",
        )
        gene_category: str | None = Field(
            default=None,
            description="Gene functional category"
            " (e.g. 'Inorganic ion transport')",
        )
        omics_type: str | None = Field(
            default=None,
            description="Omics type (e.g. 'RNASEQ')",
        )
        coculture_partner: str | None = Field(
            default=None,
            description="Coculture partner organism, if applicable",
        )
        table_scope: str | None = Field(
            default=None,
            description="What genes the source DE table contains"
            " (e.g. 'all_detected_genes'). Verbose only.",
        )
        table_scope_detail: str | None = Field(
            default=None,
            description="Free-text clarification of table_scope."
            " Verbose only.",
        )
        background_factors: list[str] = Field(
            default_factory=list,
            description="Background experimental factors."
            " Verbose only.",
        )

    class DifferentialExpressionByGeneResponse(BaseModel):
        organism_name: str = Field(
            description="Single organism for all results"
            " (e.g. 'Alteromonas macleodii HOT1A3')",
        )
        matching_genes: int = Field(
            description="Distinct genes in results after filters (e.g. 5)",
        )
        total_matching: int = Field(
            description="Total gene x experiment x timepoint rows"
            " matching filters (e.g. 15)",
        )
        rows_by_status: ExpressionStatusBreakdown = Field(
            description="Row counts by expression_status across all results",
        )
        median_abs_log2fc: float | None = Field(
            description="Median |log2FC| for significant rows only"
            " (e.g. 1.978). Null if no significant rows.",
        )
        max_abs_log2fc: float | None = Field(
            description="Max |log2FC| for significant rows only"
            " (e.g. 3.591). Null if no significant rows.",
        )
        experiment_count: int = Field(
            description="Number of experiments in results (e.g. 1)",
        )
        rows_by_treatment_type: dict[str, int] = Field(
            description="Row counts by treatment type"
            " (e.g. {'nitrogen_stress': 15})",
        )
        rows_by_background_factors: dict[str, int] = Field(
            description="Row counts by background factor"
            " (e.g. {'axenic': 10, 'diel_cycle': 5})",
        )
        rows_by_growth_phase: dict[str, int] = Field(
            default_factory=dict,
            description="Row counts by growth phase. Growth phase is a timepoint-level condition, not gene-specific.",
        )
        by_table_scope: dict[str, int] = Field(
            description="Row counts by experiment table_scope"
            " (e.g. {'all_detected_genes': 100, 'significant_only': 50})."
            " Shows data completeness across experiments.",
        )
        top_categories: list[ExpressionTopCategory] = Field(
            description="Top gene categories by significant gene count,"
            " max 5",
        )
        experiments: list[ExpressionByExperiment] = Field(
            description="Per-experiment summary with nested timepoint"
            " breakdown, sorted by significant row count desc",
        )
        not_found: list[str] = Field(
            default_factory=list,
            description="Input locus_tags not found in KG",
        )
        no_expression: list[str] = Field(
            default_factory=list,
            description="Locus tags in KG but with no expression data"
            " matching filters",
        )
        returned: int = Field(
            description="Rows in results (e.g. 5)",
        )
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(
            description="True if total_matching > returned",
        )
        results: list[ExpressionRow] = Field(default_factory=list)

    @mcp.tool(
        tags={"expression", "genes"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def differential_expression_by_gene(
        ctx: Context,
        organism: Annotated[str | None, Field(
            description="Organism name or partial match (e.g. 'MED4', "
                        "'Prochlorococcus MED4'). Fuzzy word-based matching "
                        "(same as list_experiments). "
                        "Get valid names from list_organisms.",
        )] = None,
        locus_tags: Annotated[list[str] | None, Field(
            description="Gene locus tags. E.g. ['PMM0001', 'PMM0845']. "
                        "Get these from resolve_gene / gene_overview.",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Experiment IDs to restrict to. "
                        "Get these from list_experiments.",
        )] = None,
        direction: Annotated[Literal["up", "down"] | None, Field(
            description="Filter by expression direction.",
        )] = None,
        significant_only: Annotated[bool, Field(
            description="If true, return only statistically significant"
                        " results.",
        )] = False,
        growth_phases: Annotated[list[str] | None, Field(
            description="Filter by growth phase(s) at sampling time (case-insensitive, edge-level). "
            "Isolates specific-phase rows from multi-phase experiments. "
            "E.g. ['exponential'].",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields"
                        " (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Add product, experiment_name, treatment, "
                        "gene_category, omics_type, coculture_partner"
                        " to each row.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> DifferentialExpressionByGeneResponse:
        """Gene-centric differential expression. One row per gene x experiment x timepoint.

        Returns summary statistics (always) + top results sorted by |log2FC|
        (strongest effects first). Default limit=5 gives a quick overview.
        Set summary=True for counts only, or increase limit for more rows.

        At least one of organism, locus_tags, or experiment_ids is required.
        All inputs must refer to the same organism — call once per organism.

        When organism is the only filter, it scopes to that organism's full
        expression data (e.g. MED4 = 47K edges). Combine with summary=True or
        significant_only=True + limit for manageable results.

        The expression_status field uses the publication-specific threshold from
        each experiment's original paper (not a uniform padj<0.05 cutoff).

        For cross-organism comparison via ortholog groups, use
        differential_expression_by_ortholog.
        """
        await ctx.info(
            f"differential_expression_by_gene"
            f" organism={organism} locus_tags={locus_tags}"
            f" limit={limit} summary={summary}"
        )
        try:
            conn = _conn(ctx)
            data = api.differential_expression_by_gene(
                organism=organism,
                locus_tags=locus_tags,
                experiment_ids=experiment_ids,
                direction=direction,
                significant_only=significant_only,
                growth_phases=growth_phases,
                summary=summary,
                verbose=verbose,
                limit=limit,
                offset=offset,
                conn=conn,
            )

            # Build nested Pydantic models
            exp_models = []
            for exp in data["experiments"]:
                tp_models = None
                if exp.get("timepoints") is not None:
                    tp_models = [
                        ExpressionTimepoint(
                            **{
                                **tp,
                                "rows_by_status": ExpressionStatusBreakdown(
                                    **tp["rows_by_status"]
                                ),
                            }
                        )
                        for tp in exp["timepoints"]
                    ]
                exp_models.append(
                    ExpressionByExperiment(
                        **{
                            **{k: v for k, v in exp.items()
                               if k != "timepoints" and k != "rows_by_status"},
                            "rows_by_status": ExpressionStatusBreakdown(
                                **exp["rows_by_status"]
                            ),
                            "timepoints": tp_models,
                        }
                    )
                )

            top_cat_models = [
                ExpressionTopCategory(**c) for c in data["top_categories"]
            ]
            result_models = [
                ExpressionRow(**r) for r in data["results"]
            ]

            response = DifferentialExpressionByGeneResponse(
                organism_name=data["organism_name"],
                matching_genes=data["matching_genes"],
                total_matching=data["total_matching"],
                rows_by_status=ExpressionStatusBreakdown(
                    **data["rows_by_status"]
                ),
                median_abs_log2fc=data["median_abs_log2fc"],
                max_abs_log2fc=data["max_abs_log2fc"],
                experiment_count=data["experiment_count"],
                offset=data.get("offset", 0),
                rows_by_treatment_type=data["rows_by_treatment_type"],
                rows_by_background_factors=data["rows_by_background_factors"],
                rows_by_growth_phase=data.get("rows_by_growth_phase", {}),
                by_table_scope=data["by_table_scope"],
                top_categories=top_cat_models,
                experiments=exp_models,
                not_found=data["not_found"],
                no_expression=data["no_expression"],
                returned=data["returned"],
                truncated=data["truncated"],
                results=result_models,
            )
            await ctx.info(
                f"Returning {response.returned} of {response.total_matching}"
                f" rows ({response.experiment_count} experiments)"
            )
            return response
        except ValueError as e:
            await ctx.warning(
                f"differential_expression_by_gene error: {e}"
            )
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(
                f"differential_expression_by_gene unexpected error: {e}"
            )
            raise ToolError(
                f"Error in differential_expression_by_gene: {e}"
            )

    # ------------------------------------------------------------------
    # search_homolog_groups
    # ------------------------------------------------------------------

    class SearchHomologGroupsResult(BaseModel):
        group_id: str = Field(description="OG identifier (e.g. 'cyanorak:CK_00000570')")
        group_name: str = Field(description="Raw OG name (e.g. 'CK_00000570')")
        consensus_gene_name: str | None = Field(default=None,
            description="Consensus gene name (e.g. 'psbB'). Often null.")
        consensus_product: str = Field(
            description="Consensus product (e.g. 'photosystem II chlorophyll-binding protein CP47')")
        source: str = Field(description="Source database (e.g. 'cyanorak')")
        taxonomic_level: str = Field(description="Taxonomic scope (e.g. 'curated')")
        specificity_rank: int = Field(description="0=curated, 1=family, 2=order, 3=domain (e.g. 0)")
        member_count: int = Field(description="Total genes in group (e.g. 9)")
        organism_count: int = Field(description="Distinct organisms (e.g. 9)")
        score: float = Field(description="Lucene relevance score (e.g. 5.23)")
        # verbose-only
        description: str | None = Field(default=None,
            description="Functional narrative from eggNOG (e.g. 'photosynthesis')")
        functional_description: str | None = Field(default=None,
            description="Derived from member gene roles (e.g. 'Photosynthesis and respiration > Photosystem II')")
        genera: list[str] | None = Field(default=None,
            description="Genera represented (e.g. ['Prochlorococcus', 'Synechococcus'])")
        has_cross_genus_members: str | None = Field(default=None,
            description="'cross_genus' or 'single_genus'")
        cyanorak_roles: list[dict] | None = Field(default=None,
            description="Consensus Cyanorak roles [{id, name}]. Verbose only.")
        cog_categories: list[dict] | None = Field(default=None,
            description="Consensus COG categories [{id, name}]. Verbose only.")

    class SearchHomologGroupsSourceBreakdown(BaseModel):
        source: str = Field(description="OG source (e.g. 'cyanorak')")
        count: int = Field(description="Groups from this source (e.g. 237)")

    class SearchHomologGroupsLevelBreakdown(BaseModel):
        taxonomic_level: str = Field(description="Taxonomic level (e.g. 'curated')")
        count: int = Field(description="Groups at this level (e.g. 237)")

    class SearchHomologGroupsResponse(BaseModel):
        total_entries: int = Field(description="Total OrthologGroup nodes in KG (e.g. 21122)")
        total_matching: int = Field(description="Groups matching search + filters (e.g. 884)")
        by_source: list[SearchHomologGroupsSourceBreakdown] = Field(
            description="Groups per source, sorted by count desc")
        by_level: list[SearchHomologGroupsLevelBreakdown] = Field(
            description="Groups per taxonomic level, sorted by count desc")
        score_max: float | None = Field(default=None,
            description="Highest Lucene score (null if 0 matches, e.g. 6.13)")
        score_median: float | None = Field(default=None,
            description="Median Lucene score (null if 0 matches, e.g. 1.06)")
        top_cyanorak_roles: list[OntologyBreakdown] = Field(
            default_factory=list,
            description="Top 5 CyanorakRole annotations by frequency")
        top_cog_categories: list[OntologyBreakdown] = Field(
            default_factory=list,
            description="Top 5 CogFunctionalCategory annotations by frequency")
        returned: int = Field(description="Results in this response (0 when summary=true)")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(description="True if total_matching > returned")
        results: list[SearchHomologGroupsResult] = Field(
            default_factory=list, description="One row per matching ortholog group")

    @mcp.tool(
        tags={"homology", "search"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def search_homolog_groups(
        ctx: Context,
        search_text: Annotated[str, Field(
            description="Search query (Lucene syntax). Searches consensus_product, "
            "consensus_gene_name, description, functional_description.",
        )],
        source: Annotated[str | None, Field(
            description="Filter by OG source: 'cyanorak' or 'eggnog'.",
        )] = None,
        taxonomic_level: Annotated[str | None, Field(
            description="Filter by taxonomic level. "
            "E.g. 'curated', 'Prochloraceae', 'Bacteria'.",
        )] = None,
        max_specificity_rank: Annotated[int | None, Field(
            description="Cap group breadth. 0=curated only, 1=+family, "
            "2=+order, 3=+domain (all).",
            ge=0, le=3,
        )] = None,
        cyanorak_roles: Annotated[list[str] | None, Field(
            description="Filter by CyanorakRole term IDs. OR within list. "
            "E.g. ['cyanorak.role:G.3', 'cyanorak.role:J.8'].",
        )] = None,
        cog_categories: Annotated[list[str] | None, Field(
            description="Filter by CogFunctionalCategory term IDs. OR within list. "
            "E.g. ['cog.category:C', 'cog.category:J'].",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include description, functional_description, genera, "
            "has_cross_genus_members in results.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> SearchHomologGroupsResponse:
        """Search ortholog groups by text (Lucene). Returns group IDs for
        use with genes_by_homolog_group.

        Searches across consensus_product, consensus_gene_name, description,
        and functional_description fields.
        """
        await ctx.info(f"search_homolog_groups search_text={search_text!r} "
                       f"source={source} limit={limit}")
        try:
            conn = _conn(ctx)
            data = api.search_homolog_groups(
                search_text, source=source,
                taxonomic_level=taxonomic_level,
                max_specificity_rank=max_specificity_rank,
                cyanorak_roles=cyanorak_roles,
                cog_categories=cog_categories,
                summary=summary, verbose=verbose, limit=limit, offset=offset, conn=conn,
            )
            by_source = [SearchHomologGroupsSourceBreakdown(**b) for b in data["by_source"]]
            by_level = [SearchHomologGroupsLevelBreakdown(**b) for b in data["by_level"]]
            top_cr = [OntologyBreakdown(**b) for b in data.get("top_cyanorak_roles", [])]
            top_cc = [OntologyBreakdown(**b) for b in data.get("top_cog_categories", [])]
            results = [SearchHomologGroupsResult(**r) for r in data["results"]]
            response = SearchHomologGroupsResponse(
                total_entries=data["total_entries"],
                total_matching=data["total_matching"],
                by_source=by_source,
                by_level=by_level,
                score_max=data["score_max"],
                score_median=data["score_median"],
                top_cyanorak_roles=top_cr,
                top_cog_categories=top_cc,
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of {response.total_matching} groups")
            return response
        except ValueError as e:
            await ctx.warning(f"search_homolog_groups error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"search_homolog_groups unexpected error: {e}")
            raise ToolError(f"Error in search_homolog_groups: {e}")

    # -----------------------------------------------------------------
    # genes_by_homolog_group
    # -----------------------------------------------------------------

    class GenesByHomologGroupResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0315')")
        gene_name: str | None = Field(default=None,
            description="Gene name (e.g. 'psbB')")
        product: str | None = Field(default=None,
            description="Gene product (e.g. 'photosystem II chlorophyll-binding protein CP47')")
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4')")
        gene_category: str | None = Field(default=None,
            description="Functional category (e.g. 'Photosynthesis')")
        group_id: str = Field(
            description="Ortholog group ID (e.g. 'cyanorak:CK_00000570')")
        # verbose only
        gene_summary: str | None = Field(default=None,
            description="Concatenated summary text")
        function_description: str | None = Field(default=None,
            description="Curated functional description")
        consensus_product: str | None = Field(default=None,
            description="Group consensus product (e.g. 'photosystem II chlorophyll-binding protein CP47')")
        source: str | None = Field(default=None,
            description="OG source (e.g. 'cyanorak')")

    class HomologGroupOrganismBreakdown(BaseModel):
        organism_name: str = Field(
            description="Organism name (e.g. 'Prochlorococcus MED4')")
        count: int = Field(description="Member genes from this organism")

    class HomologGroupCategoryBreakdown(BaseModel):
        category: str = Field(
            description="Gene category (e.g. 'Photosynthesis')")
        count: int = Field(description="Member genes in this category")

    class HomologGroupGroupBreakdown(BaseModel):
        group_id: str = Field(
            description="Ortholog group ID (e.g. 'cyanorak:CK_00000570')")
        count: int = Field(description="Member genes in this group")

    class GenesByHomologGroupResponse(BaseModel):
        total_matching: int = Field(
            description="Gene×group rows matching filters (e.g. 33)")
        total_genes: int = Field(
            description="Distinct genes (a gene in 2 input groups counted once, e.g. 30)")
        total_categories: int = Field(
            description="Distinct gene categories (e.g. 12)")
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        genes_per_group_max: int = Field(
            description="Largest group's gene count (e.g. 13)")
        genes_per_group_median: float = Field(
            description="Median gene count across groups (e.g. 3.0)")
        by_organism: list[HomologGroupOrganismBreakdown] = Field(
            description="Member counts per organism, sorted by count desc (all)")
        top_categories: list[HomologGroupCategoryBreakdown] = Field(
            description="Top 5 gene categories by member count, sorted by count desc")
        top_groups: list[HomologGroupGroupBreakdown] = Field(
            description="Top 5 groups by member count, sorted by count desc")
        not_found_groups: list[str] = Field(default_factory=list,
            description="Input group_ids not found in KG")
        not_matched_groups: list[str] = Field(default_factory=list,
            description="Groups that exist but have 0 member genes after organism filter")
        not_found_organisms: list[str] = Field(default_factory=list,
            description="Organism filter values matching zero Gene nodes in KG")
        not_matched_organisms: list[str] = Field(default_factory=list,
            description="Organisms in KG but with zero genes in the requested groups")
        returned: int = Field(description="Results in this response")
        truncated: bool = Field(
            description="True if total_matching > returned")
        results: list[GenesByHomologGroupResult] = Field(
            default_factory=list, description="One row per gene × group")

    @mcp.tool(
        tags={"genes", "homology"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def genes_by_homolog_group(
        ctx: Context,
        group_ids: Annotated[list[str], Field(
            description="Ortholog group IDs (from search_homolog_groups or "
            "gene_homologs). E.g. ['cyanorak:CK_00000570'].",
        )],
        organisms: Annotated[list[str] | None, Field(
            description="Filter by organisms (case-insensitive substring, each entry "
            "matched independently). E.g. ['MED4', 'AS9601']. "
            "Use list_organisms to see valid values.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include gene_summary, function_description, "
            "consensus_product, source in results.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> GenesByHomologGroupResponse:
        """Find member genes of ortholog groups.

        Takes group IDs from search_homolog_groups or gene_homologs and
        returns member genes per organism. One row per gene × group.

        Two list filters — each reports not_found + not_matched:
        - group_ids: ortholog groups (required)
        - organisms: restrict to specific organisms

        For group discovery by text, use search_homolog_groups first.
        For gene → group direction, use gene_homologs.
        For expression by ortholog groups, use differential_expression_by_ortholog.
        """
        await ctx.info(f"genes_by_homolog_group group_ids={group_ids} organisms={organisms}")
        try:
            conn = _conn(ctx)
            data = api.genes_by_homolog_group(
                group_ids, organisms=organisms,
                summary=summary, verbose=verbose, limit=limit, offset=offset, conn=conn,
            )
            by_organism = [HomologGroupOrganismBreakdown(**b) for b in data["by_organism"]]
            top_categories = [HomologGroupCategoryBreakdown(**b) for b in data["top_categories"]]
            top_groups = [HomologGroupGroupBreakdown(**b) for b in data["top_groups"]]
            results = [GenesByHomologGroupResult(**r) for r in data["results"]]
            response = GenesByHomologGroupResponse(
                total_matching=data["total_matching"],
                total_genes=data["total_genes"],
                total_categories=data["total_categories"],
                genes_per_group_max=data["genes_per_group_max"],
                genes_per_group_median=data["genes_per_group_median"],
                by_organism=by_organism,
                top_categories=top_categories,
                top_groups=top_groups,
                not_found_groups=data["not_found_groups"],
                not_matched_groups=data["not_matched_groups"],
                not_found_organisms=data["not_found_organisms"],
                not_matched_organisms=data["not_matched_organisms"],
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of {response.total_matching} gene×group rows")
            return response
        except ValueError as e:
            await ctx.warning(f"genes_by_homolog_group error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"genes_by_homolog_group unexpected error: {e}")
            raise ToolError(f"Error in genes_by_homolog_group: {e}")

    # -----------------------------------------------------------------
    # differential_expression_by_ortholog
    # -----------------------------------------------------------------

    class DifferentialExpressionByOrthologResult(BaseModel):
        # --- always present ---
        group_id: str = Field(
            description="Ortholog group ID"
            " (e.g. 'cyanorak:CK_00000570')",
        )
        consensus_gene_name: str | None = Field(
            description="Short gene name (e.g. 'psbB')."
            " Null for hypotheticals.",
        )
        consensus_product: str = Field(
            description="Group product description"
            " (e.g. 'photosystem II chlorophyll-binding protein CP47')",
        )
        experiment_id: str = Field(
            description="Experiment ID",
        )
        treatment_type: list[str] = Field(
            description="Treatment categories"
            " (e.g. ['nitrogen_limitation'])",
        )
        background_factors: list[str] = Field(
            default_factory=list,
            description="Background experimental factors",
        )
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4')",
        )
        coculture_partner: str | None = Field(
            default=None,
            description="Coculture partner organism, if applicable",
        )
        timepoint: str | None = Field(
            description="Timepoint label (e.g. '24h')."
            " Null when edge has no label.",
        )
        timepoint_hours: float | None = Field(
            description="Numeric hours (e.g. 24.0)."
            " Null for non-numeric labels.",
        )
        timepoint_order: int = Field(
            description="Sort key for time course order (e.g. 3)",
        )
        genes_with_expression: int = Field(
            description="Group members with expression at this timepoint",
        )
        total_genes: int = Field(
            description="Total group members in this organism (computed)",
        )
        significant_up: int = Field(
            description="Genes significantly upregulated",
        )
        significant_down: int = Field(
            description="Genes significantly downregulated",
        )
        not_significant: int = Field(
            description="Genes not meeting significance threshold",
        )
        growth_phase: str | None = Field(
            default=None,
            description="Physiological state of the culture at this timepoint "
            "(e.g. 'exponential', 'nutrient_limited'). "
            "Timepoint-level condition — not gene-specific.",
        )
        # --- verbose only ---
        experiment_name: str | None = Field(
            default=None,
            description="Human-readable experiment name. Verbose only.",
        )
        treatment: str | None = Field(
            default=None,
            description="Detailed treatment string. Verbose only.",
        )
        omics_type: str | None = Field(
            default=None,
            description="Omics type (e.g. 'RNASEQ'). Verbose only.",
        )
        table_scope: str | None = Field(
            default=None,
            description="What genes the DE table contains. Verbose only.",
        )
        table_scope_detail: str | None = Field(
            default=None,
            description="Free-text clarification of table_scope."
            " Verbose only.",
        )

    class DifferentialExpressionByOrthologTopGroup(BaseModel):
        group_id: str = Field(
            description="Ortholog group ID",
        )
        consensus_gene_name: str | None = Field(
            description="Short gene name",
        )
        consensus_product: str = Field(
            description="Group product description",
        )
        significant_genes: int = Field(
            description="Distinct significant genes in this group",
        )
        total_genes: int = Field(
            description="Distinct genes with expression in this group",
        )

    class DifferentialExpressionByOrthologTopExperiment(BaseModel):
        experiment_id: str = Field(
            description="Experiment ID",
        )
        treatment_type: list[str] = Field(
            description="Treatment categories",
        )
        background_factors: list[str] = Field(
            default_factory=list,
            description="Background experimental factors",
        )
        organism_name: str = Field(
            description="Organism name",
        )
        significant_genes: int = Field(
            description="Distinct significant genes in this experiment"
            " across groups",
        )

    class DEByOrthologOrganismBreakdown(BaseModel):
        organism_name: str = Field(
            description="Organism name (e.g. 'Prochlorococcus MED4')",
        )
        count: int = Field(
            description="Rows for this organism",
        )

    class DifferentialExpressionByOrthologResponse(BaseModel):
        total_matching: int = Field(
            description="Gene x experiment x timepoint rows"
            " matching all filters",
        )
        matching_genes: int = Field(
            description="Distinct genes with expression",
        )
        matching_groups: int = Field(
            description="Distinct groups with >=1 gene having expression",
        )
        experiment_count: int = Field(
            description="Distinct experiments in results",
        )
        median_abs_log2fc: float | None = Field(
            description="Median |log2FC| for significant rows."
            " Null if none.",
        )
        max_abs_log2fc: float | None = Field(
            description="Max |log2FC| for significant rows."
            " Null if none.",
        )
        results: list[DifferentialExpressionByOrthologResult] = Field(
            default_factory=list,
        )
        returned: int = Field(
            description="Rows in results",
        )
        offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
        truncated: bool = Field(
            description="True if more results exist than returned",
        )
        by_organism: list[DEByOrthologOrganismBreakdown] = Field(
            description="Rows per organism, sorted by count desc",
        )
        rows_by_status: dict[str, int] = Field(
            description="{significant_up, significant_down,"
            " not_significant}",
        )
        rows_by_treatment_type: dict[str, int] = Field(
            description="Row counts by treatment type",
        )
        rows_by_background_factors: dict[str, int] = Field(
            description="Row counts by background factor",
        )
        rows_by_growth_phase: dict[str, int] = Field(
            default_factory=dict,
            description="Row counts by growth phase. Growth phase is a timepoint-level condition, not gene-specific.",
        )
        by_table_scope: dict[str, int] = Field(
            description="Row counts by experiment table_scope",
        )
        top_groups: list[DifferentialExpressionByOrthologTopGroup] = Field(
            default_factory=list,
            description="Top 5 groups by significant gene count",
        )
        top_experiments: list[DifferentialExpressionByOrthologTopExperiment] = Field(
            default_factory=list,
            description="Top 5 experiments by significant gene count",
        )
        not_found_groups: list[str] = Field(
            default_factory=list,
            description="Input group_ids not found in KG",
        )
        not_matched_groups: list[str] = Field(
            default_factory=list,
            description="Groups that exist but have 0 expression"
            " matching filters",
        )
        not_found_organisms: list[str] = Field(
            default_factory=list,
            description="Organism filter values matching zero genes in KG",
        )
        not_matched_organisms: list[str] = Field(
            default_factory=list,
            description="Organisms in KG but with zero expression"
            " in groups",
        )
        not_found_experiments: list[str] = Field(
            default_factory=list,
            description="Experiment IDs not found in KG",
        )
        not_matched_experiments: list[str] = Field(
            default_factory=list,
            description="Experiments that exist but have 0 expression"
            " edges to group members",
        )

    @mcp.tool(
        tags={"expression", "homology"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def differential_expression_by_ortholog(
        ctx: Context,
        group_ids: Annotated[list[str], Field(
            description="Ortholog group IDs (from search_homolog_groups or "
            "gene_homologs). E.g. ['cyanorak:CK_00000570'].",
        )],
        organisms: Annotated[list[str] | None, Field(
            description="Filter by organisms (case-insensitive substring, "
            "OR semantics). E.g. ['MED4', 'MIT9313']. "
            "Use list_organisms to see valid values.",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Filter to these experiments. "
            "Get IDs from list_experiments.",
        )] = None,
        direction: Annotated[Literal["up", "down"] | None, Field(
            description="Filter by expression direction.",
        )] = None,
        significant_only: Annotated[bool, Field(
            description="If true, return only statistically significant"
            " rows.",
        )] = False,
        growth_phases: Annotated[list[str] | None, Field(
            description="Filter by growth phase(s) at sampling time (case-insensitive, edge-level). "
            "Isolates specific-phase rows from multi-phase experiments. "
            "E.g. ['exponential'].",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields"
            " (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Add experiment_name, treatment, omics_type, "
            "table_scope, table_scope_detail to each row.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max result rows.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> DifferentialExpressionByOrthologResponse:
        """Differential expression framed by ortholog groups.

        Cross-organism by design — results at group x experiment x timepoint
        granularity showing how many group members respond. Gene counts,
        not individual genes.

        Returns summary statistics (always) + top results sorted by significant
        gene count. Default limit=5 gives a quick overview.
        Set summary=True for counts only, or increase limit for more rows.

        Three list filters — each reports not_found + not_matched:
        - group_ids (required): ortholog groups
        - organisms: restrict to specific organisms
        - experiment_ids: restrict to specific experiments

        For group discovery, use search_homolog_groups first.
        For group membership without expression, use genes_by_homolog_group.
        For per-gene expression, use differential_expression_by_gene.
        """
        await ctx.info(
            f"differential_expression_by_ortholog"
            f" group_ids={group_ids} limit={limit}"
        )
        try:
            conn = _conn(ctx)
            data = api.differential_expression_by_ortholog(
                group_ids=group_ids,
                organisms=organisms,
                experiment_ids=experiment_ids,
                direction=direction,
                significant_only=significant_only,
                growth_phases=growth_phases,
                summary=summary,
                verbose=verbose,
                limit=limit,
                offset=offset,
                conn=conn,
            )
            # Build Pydantic models from dict results
            top_groups = [
                DifferentialExpressionByOrthologTopGroup(**g)
                for g in data["top_groups"]
            ]
            top_experiments = [
                DifferentialExpressionByOrthologTopExperiment(**e)
                for e in data["top_experiments"]
            ]
            results = [
                DifferentialExpressionByOrthologResult(**r)
                for r in data["results"]
            ]

            response = DifferentialExpressionByOrthologResponse(
                total_matching=data["total_matching"],
                matching_genes=data["matching_genes"],
                matching_groups=data["matching_groups"],
                experiment_count=data["experiment_count"],
                median_abs_log2fc=data["median_abs_log2fc"],
                max_abs_log2fc=data["max_abs_log2fc"],
                results=results,
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                by_organism=[DEByOrthologOrganismBreakdown(**b) for b in data["by_organism"]],
                rows_by_status=data["rows_by_status"],
                rows_by_treatment_type=data["rows_by_treatment_type"],
                rows_by_background_factors=data["rows_by_background_factors"],
                rows_by_growth_phase=data.get("rows_by_growth_phase", {}),
                by_table_scope=data["by_table_scope"],
                top_groups=top_groups,
                top_experiments=top_experiments,
                not_found_groups=data["not_found_groups"],
                not_matched_groups=data["not_matched_groups"],
                not_found_organisms=data["not_found_organisms"],
                not_matched_organisms=data["not_matched_organisms"],
                not_found_experiments=data["not_found_experiments"],
                not_matched_experiments=data["not_matched_experiments"],
            )
            await ctx.info(
                f"Returning {response.returned} rows"
                f" ({response.matching_groups} groups,"
                f" {response.experiment_count} experiments)"
            )
            return response
        except ValueError as e:
            await ctx.warning(
                f"differential_expression_by_ortholog error: {e}"
            )
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(
                f"differential_expression_by_ortholog unexpected error: {e}"
            )
            raise ToolError(
                f"Error in differential_expression_by_ortholog: {e}"
            )

    # --- gene_response_profile ---

    class GeneResponseGroupSummary(BaseModel):
        experiments_total: int = Field(description="Total experiments for this group in the organism (e.g. 4)")
        experiments_tested: int = Field(description="Experiments where this gene has expression edges (e.g. 3)")
        experiments_up: int = Field(description="Experiments with significant_up in at least one timepoint (e.g. 3)")
        experiments_down: int = Field(description="Experiments with significant_down in at least one timepoint (e.g. 0)")
        timepoints_total: int = Field(description="Total timepoints across experiments for this group (e.g. 14)")
        timepoints_tested: int = Field(description="Timepoints where gene has an expression edge (e.g. 8)")
        timepoints_up: int = Field(description="Timepoints where gene is significant_up (e.g. 8)")
        timepoints_down: int = Field(description="Timepoints where gene is significant_down (e.g. 0)")
        up_best_rank: int | None = Field(default=None, description="Best (lowest) rank_up across significant_up timepoints. 1 = strongest. Present only when experiments_up > 0.")
        up_median_rank: float | None = Field(default=None, description="Median rank_up across significant_up timepoints. Present only when experiments_up > 0.")
        up_max_log2fc: float | None = Field(default=None, description="Largest positive log2FC across significant_up timepoints. Present only when experiments_up > 0.")
        down_best_rank: int | None = Field(default=None, description="Best (lowest) rank_down across significant_down timepoints. 1 = strongest. Present only when experiments_down > 0.")
        down_median_rank: float | None = Field(default=None, description="Median rank_down across significant_down timepoints. Present only when experiments_down > 0.")
        down_max_log2fc: float | None = Field(default=None, description="Most negative log2FC across significant_down timepoints. Present only when experiments_down > 0.")

    class GeneResponseProfileResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0370')")
        gene_name: str | None = Field(description="Gene name (e.g. 'cynA'). Null if unannotated.")
        product: str | None = Field(description="Gene product description (e.g. 'cyanate transporter')")
        gene_category: str | None = Field(description="Functional category (e.g. 'Inorganic ion transport')")
        groups_responded: list[str] = Field(description="Groups where gene is significant in at least one timepoint")
        groups_not_responded: list[str] = Field(description="Groups where expression edges exist but none significant")
        groups_tested_not_responded: list[str] = Field(description="Groups where all experiments use full-coverage scope (significant_only/significant_any_timepoint) but gene has no expression edge — inferred as tested, not significant")
        groups_not_known: list[str] = Field(description="Groups with no expression edge for this gene and scope does not confirm coverage")
        response_summary: dict[str, GeneResponseGroupSummary] = Field(description="Per-group detail. Keys are treatment types or experiment IDs depending on group_by.")

    class GeneResponseProfileResponse(BaseModel):
        organism_name: str | None = Field(description="Resolved organism name")
        genes_queried: int = Field(description="Count of input locus_tags (e.g. 17)")
        genes_with_response: int = Field(description="Genes with at least one significant expression edge (e.g. 15)")
        not_found: list[str] = Field(default_factory=list, description="Input locus_tags not found in KG")
        no_expression: list[str] = Field(default_factory=list, description="Gene exists but has zero expression edges")
        returned: int = Field(description="Genes in results after pagination (e.g. 15)")
        offset: int = Field(description="Offset into paginated gene list (e.g. 0)")
        truncated: bool = Field(description="True if more genes available beyond returned + offset")
        results: list[GeneResponseProfileResult] = Field(default_factory=list)

    @mcp.tool(
        tags={"expression", "gene"},
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    async def gene_response_profile(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(description="Gene locus tags. E.g. ['PMM0370', 'PMM0920']. Get these from resolve_gene / gene_overview.")],
        organism: Annotated[str | None, Field(description="Organism name for validation (optional). Inferred from genes. Fuzzy word-based matching.")] = None,
        treatment_types: Annotated[list[str] | None, Field(description="Filter to specific treatment types.")] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Filter by background experimental factors "
            "(case-insensitive exact match). "
            "E.g. ['axenic', 'diel_cycle'].",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(description="Restrict to specific experiments. Get these from list_experiments.")] = None,
        group_by: Annotated[Literal["treatment_type", "experiment"], Field(description="Group response summary by treatment_type (aggregates across experiments) or experiment (one entry per experiment).")] = "treatment_type",
        limit: Annotated[int, Field(description="Max genes returned.", ge=1)] = 50,
        offset: Annotated[int, Field(description="Skip N genes for pagination.", ge=0)] = 0,
    ) -> GeneResponseProfileResponse:
        """Cross-experiment gene response profile.

        Summarizes how each gene responds across all experiments. One result
        per gene with response_summary showing per-treatment (or per-experiment)
        statistics: how many experiments/timepoints the gene was tested in,
        how many it responded in (up/down), and rank/log2fc stats for
        significant responses.

        Results sorted by response breadth: genes responding to most groups
        first, then by experiment count, then by timepoint count.

        Use differential_expression_by_gene to drill into temporal patterns
        within a specific experiment.
        """
        await ctx.info(f"gene_response_profile locus_tags={locus_tags} group_by={group_by} limit={limit}")
        try:
            conn = _conn(ctx)
            data = api.gene_response_profile(
                locus_tags=locus_tags, organism=organism,
                treatment_types=treatment_types,
                background_factors=background_factors,
                experiment_ids=experiment_ids,
                group_by=group_by, limit=limit, offset=offset, conn=conn,
            )
            data["results"] = [
                GeneResponseProfileResult(
                    **{
                        **{k: v for k, v in r.items() if k != "response_summary"},
                        "response_summary": {
                            gk: GeneResponseGroupSummary(**gv)
                            for gk, gv in r["response_summary"].items()
                        },
                    }
                )
                for r in data["results"]
            ]
            response = GeneResponseProfileResponse(**data)
            await ctx.info(f"Returning {response.returned} of {response.genes_queried} genes ({response.genes_with_response} with response)")
            return response
        except ValueError as e:
            await ctx.warning(f"gene_response_profile error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_response_profile unexpected error: {e}")
            raise ToolError(f"Error in gene_response_profile: {e}")

    # -----------------------------------------------------------------
    # list_clustering_analyses
    # -----------------------------------------------------------------

    class GeneClusterOrganismBreakdown(BaseModel):
        organism_name: str
        count: int

    class GeneClusterTypeBreakdown(BaseModel):
        cluster_type: str
        count: int

    class GeneClusterTreatmentBreakdown(BaseModel):
        treatment_type: str
        count: int

    class GeneClusterBackgroundFactorBreakdown(BaseModel):
        background_factor: str
        count: int

    class GeneClusterOmicsBreakdown(BaseModel):
        omics_type: str
        count: int

    class InlineCluster(BaseModel):
        cluster_id: str = Field(
            description="GeneCluster node ID (e.g. 'cluster:msb4100087:med4:up_n_transport')")
        name: str = Field(
            description="Cluster name (e.g. 'MED4 cluster 1 (up, N transport)')")
        member_count: int = Field(
            description="Number of genes in this cluster")
        # verbose-only
        functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE")
        expression_dynamics: str | None = Field(default=None,
            description="Expression dynamics label (e.g. 'periodic in L:D only')")
        temporal_pattern: str | None = Field(default=None,
            description="Detailed temporal pattern description")

    class ListClusteringAnalysesResult(BaseModel):
        analysis_id: str = Field(
            description="ClusteringAnalysis node ID (e.g. 'ca:msb4100087:med4:nitrogen')")
        name: str = Field(
            description="Analysis name (e.g. 'MED4 nitrogen stress response clustering')")
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4')")
        cluster_method: str | None = Field(default=None,
            description="Clustering method (e.g. 'K-means', 'fuzzy c-means')")
        cluster_type: str = Field(
            description="Cluster category (e.g. 'condition_comparison')")
        cluster_count: int = Field(
            description="Number of clusters in this analysis")
        total_gene_count: int = Field(
            description="Total genes across all clusters")
        treatment_type: list[str] = Field(
            description="Treatment types (e.g. ['nitrogen_stress'])")
        growth_phases: list[str] = Field(default_factory=list, description="Distinct growth phases. Physiological state of the culture at sampling — timepoint-level, not gene-specific.")
        background_factors: list[str] = Field(default_factory=list,
            description="Background experimental factors (e.g. ['axenic', 'continuous_light'])")
        omics_type: str | None = Field(default=None,
            description="Omics data type (e.g. 'MICROARRAY')")
        experiment_ids: list[str] = Field(default_factory=list,
            description="Linked experiment IDs")
        clusters: list["InlineCluster"] = Field(default_factory=list,
            description="Clusters belonging to this analysis")
        score: float | None = Field(default=None,
            description="Lucene relevance score (only when search_text used)")
        # verbose-only
        treatment: str | None = Field(default=None,
            description="Free-text condition description")
        light_condition: str | None = Field(default=None,
            description="Light regime (e.g. 'diel_cycle')")
        experimental_context: str | None = Field(default=None,
            description="Full experimental context description")

    class ListClusteringAnalysesResponse(BaseModel):
        total_entries: int = Field(
            description="Total analyses in KG (before filters)")
        total_matching: int = Field(
            description="Analyses matching current filters")
        by_organism: list["GeneClusterOrganismBreakdown"] = Field(
            description="Analyses per organism")
        by_cluster_type: list["GeneClusterTypeBreakdown"] = Field(
            description="Analyses per cluster type")
        by_treatment_type: list["GeneClusterTreatmentBreakdown"] = Field(
            description="Analyses per treatment type")
        by_background_factors: list["GeneClusterBackgroundFactorBreakdown"] = Field(
            description="Analyses per background factor")
        by_omics_type: list["GeneClusterOmicsBreakdown"] = Field(
            description="Analyses per omics type")
        by_growth_phase: list["GrowthPhaseBreakdown"] = Field(
            default_factory=list, description="Analysis counts per growth phase, sorted by count descending")
        score_max: float | None = Field(default=None,
            description="Highest Lucene score (search only)")
        score_median: float | None = Field(default=None,
            description="Median Lucene score (search only)")
        returned: int = Field(description="Results in this response")
        offset: int = Field(default=0, description="Offset into result set")
        truncated: bool = Field(
            description="True if total_matching > offset + returned")
        results: list["ListClusteringAnalysesResult"] = Field(
            default_factory=list, description="One row per clustering analysis")

    @mcp.tool(
        tags={"clusters", "search"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def list_clustering_analyses(
        ctx: Context,
        search_text: Annotated[str | None, Field(
            description="Lucene full-text query over analysis name, cluster names, "
            "functional/behavioral descriptions, experimental_context. "
            "Results ranked by score.",
        )] = None,
        organism: Annotated[str | None, Field(
            description="Filter by organism (case-insensitive partial match).",
        )] = None,
        cluster_type: Annotated[str | None, Field(
            description="Filter: " + ", ".join(f"'{v}'" for v in sorted(VALID_CLUSTER_TYPES)) + ".",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Filter by treatment type(s). E.g. ['nitrogen_stress'].",
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Filter by background factors. "
            "E.g. ['axenic', 'diel_cycle'].",
        )] = None,
        growth_phases: Annotated[list[str] | None, Field(
            description="Filter by growth phase(s) (case-insensitive). "
            "Physiological state of the culture at sampling time. "
            "E.g. ['exponential', 'nutrient_limited'].",
        )] = None,
        omics_type: Annotated[str | None, Field(
            description="Filter: " + ", ".join(f"'{v}'" for v in sorted(VALID_OMICS_TYPES)) + ".",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Filter by publication DOI(s).",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Filter by experiment IDs.",
        )] = None,
        analysis_ids: Annotated[list[str] | None, Field(
            description="Filter by analysis IDs.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include treatment, light_condition, experimental_context "
            "on analyses; functional_description, expression_dynamics, "
            "temporal_pattern on inline clusters.",
        )] = False,
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0)] = 0,
    ) -> ListClusteringAnalysesResponse:
        """Browse, search, and filter clustering analyses.

        Each analysis groups related gene clusters from one study/organism.
        Inline clusters are included in each result row.

        After this tool, drill in via:
        - genes_in_cluster(cluster_ids=[id]) for per-cluster member genes
        - genes_in_cluster(analysis_id=...) for all clusters from one analysis
        - gene_clusters_by_gene(locus_tags=[...], analysis_ids=[id]) to scope a
          per-gene cluster lookup to this analysis
        """
        await ctx.info(f"list_clustering_analyses search_text={search_text!r} "
                       f"organism={organism} limit={limit}")
        try:
            conn = _conn(ctx)
            data = api.list_clustering_analyses(
                search_text=search_text, organism=organism,
                cluster_type=cluster_type, treatment_type=treatment_type,
                background_factors=background_factors,
                growth_phases=growth_phases,
                omics_type=omics_type, publication_doi=publication_doi,
                experiment_ids=experiment_ids, analysis_ids=analysis_ids,
                summary=summary, verbose=verbose, limit=limit, offset=offset,
                conn=conn,
            )
            by_organism = [GeneClusterOrganismBreakdown(**b)
                           for b in data["by_organism"]]
            by_cluster_type = [GeneClusterTypeBreakdown(**b)
                               for b in data["by_cluster_type"]]
            by_treatment_type = [GeneClusterTreatmentBreakdown(**b)
                                 for b in data["by_treatment_type"]]
            by_background_factors = [GeneClusterBackgroundFactorBreakdown(**b)
                                     for b in data["by_background_factors"]]
            by_omics_type = [GeneClusterOmicsBreakdown(**b)
                             for b in data["by_omics_type"]]
            by_growth_phase = [GrowthPhaseBreakdown(**b)
                               for b in data.get("by_growth_phase", [])]
            results = [
                ListClusteringAnalysesResult(
                    **{k: v for k, v in r.items() if k != "clusters"},
                    clusters=[InlineCluster(**c) for c in r.get("clusters", [])],
                )
                for r in data["results"]
            ]
            response = ListClusteringAnalysesResponse(
                total_entries=data["total_entries"],
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_cluster_type=by_cluster_type,
                by_treatment_type=by_treatment_type,
                by_background_factors=by_background_factors,
                by_omics_type=by_omics_type,
                by_growth_phase=by_growth_phase,
                score_max=data.get("score_max"),
                score_median=data.get("score_median"),
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of "
                           f"{response.total_matching} analyses")
            return response
        except ValueError as e:
            await ctx.warning(f"list_clustering_analyses error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"list_clustering_analyses unexpected error: {e}")
            raise ToolError(f"Error in list_clustering_analyses: {e}")

    # ── gene_derived_metrics breakdowns ────────────────────────────────

    class GeneDmValueKindBreakdown(BaseModel):
        value_kind: Literal["numeric", "boolean", "categorical"] = Field(
            description="DM value kind.")
        count: int = Field(description="Rows of this value_kind.")

    class GeneDmMetricTypeBreakdown(BaseModel):
        metric_type: str = Field(description="DM metric_type tag.")
        count: int = Field(description="Rows of this metric_type.")

    class GeneDmMetricBreakdown(BaseModel):
        derived_metric_id: str = Field(description="Unique DM id.")
        name: str = Field(description="Human-readable DM name.")
        metric_type: str = Field(description="Category tag.")
        value_kind: Literal["numeric", "boolean", "categorical"] = Field(
            description="Routes to the matching genes_by_*_metric drill-down.")
        count: int = Field(description="Rows contributed by this DM.")

    class GeneDmCompartmentBreakdown(BaseModel):
        compartment: str = Field(
            description="Sample compartment ('whole_cell', 'vesicle', etc.).")
        count: int = Field(description="Rows in this compartment.")

    class GeneDmTreatmentBreakdown(BaseModel):
        treatment_type: str = Field(description="Treatment type.")
        count: int = Field(description="Rows touching this treatment.")

    class GeneDmBackgroundFactorBreakdown(BaseModel):
        background_factor: str = Field(description="Background experimental factor.")
        count: int = Field(description="Rows under this factor.")

    class GeneDmPublicationBreakdown(BaseModel):
        publication_doi: str = Field(description="Parent publication DOI.")
        count: int = Field(description="Rows from this publication.")

    class GeneDerivedMetricsResult(BaseModel):
        # ── compact (always populated by api/) ──────────────────────────
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM1714').")
        gene_name: str | None = Field(
            default=None,
            description="Gene name (e.g. 'dnaN') — null when KG has no name.")
        derived_metric_id: str = Field(
            description="Unique parent-DM id. Pass to `derived_metric_ids` "
                        "on genes_by_*_metric drill-downs to pin this exact "
                        "DM. metric_type, compartment, publication_doi etc. "
                        "are available in verbose mode or via "
                        "list_derived_metrics(derived_metric_ids=[...]).")
        value_kind: Literal["numeric", "boolean", "categorical"] = Field(
            description="Determines how to interpret `value`. Routes to the "
                        "matching genes_by_*_metric drill-down.")
        name: str = Field(
            description="Human-readable DM name (e.g. 'Transcript:protein "
                        "amplitude ratio'). Saves a round-trip to "
                        "list_derived_metrics for opaque metric_type codes.")
        value: float | str = Field(
            description="Polymorphic measurement: float on numeric rows, "
                        "'true'/'false' string on boolean rows, category "
                        "string on categorical rows. Branch on `value_kind`.")
        rankable: bool = Field(
            description="Echoed from parent DM. True iff this row's `value` "
                        "carries rank/percentile/bucket extras.")
        has_p_value: bool = Field(
            description="Echoed from parent DM. True iff adjusted_p_value/"
                        "significant carry data. No DM in current KG has p-values.")
        rank_by_metric: int | None = Field(
            default=None,
            description="Rank by metric value (1 = highest). Populated only "
                        "when parent DM rankable=True.")
        metric_percentile: float | None = Field(
            default=None,
            description="Percentile within metric distribution (0-100). "
                        "Same gate as rank_by_metric.")
        metric_bucket: str | None = Field(
            default=None,
            description="Bucket label ('top_decile', 'top_quartile', 'mid', "
                        "'low'). Same gate as rank_by_metric.")
        adjusted_p_value: float | None = Field(
            default=None,
            description="BH-adjusted p-value. Populated only when parent DM "
                        "has_p_value=True. No DM in current KG has p-values; "
                        "Cypher RETURN omits this column today.")
        significant: bool | None = Field(
            default=None,
            description="Significance flag at the DM's p_value_threshold. "
                        "Same gate as adjusted_p_value.")
        # ── verbose adds (default None / [] when verbose=False) ─────────
        metric_type: str | None = Field(
            default=None,
            description="Category tag for this DM (e.g. 'damping_ratio'). "
                        "Verbose only.")
        field_description: str | None = Field(
            default=None,
            description="Detailed explanation of what this DM measures. "
                        "Verbose only.")
        unit: str | None = Field(
            default=None,
            description="Measurement unit (e.g. 'hours', 'log2'). "
                        "Verbose only.")
        allowed_categories: list[str] | None = Field(
            default=None,
            description="Valid category strings — non-null only on "
                        "categorical rows. Verbose only.")
        compartment: str | None = Field(
            default=None,
            description="Sample compartment. Verbose only.")
        treatment_type: list[str] = Field(
            default_factory=list,
            description="Treatment type(s) for the parent experiment. "
                        "Verbose only.")
        background_factors: list[str] = Field(
            default_factory=list,
            description="Background experimental factors (may be empty). "
                        "Verbose only.")
        publication_doi: str | None = Field(
            default=None,
            description="Parent publication DOI. Verbose only.")
        treatment: str | None = Field(
            default=None,
            description="Treatment description in plain language. Verbose only.")
        light_condition: str | None = Field(
            default=None,
            description="Light regime. Verbose only.")
        experimental_context: str | None = Field(
            default=None,
            description="Longer experimental setup description. Verbose only.")
        p_value: float | None = Field(
            default=None,
            description="Raw p-value. Populated only when parent DM "
                        "has_p_value=True (none in current KG). Verbose only.")

    class GeneDerivedMetricsResponse(BaseModel):
        total_matching: int = Field(
            description="Gene × DM rows matching all filters.")
        total_derived_metrics: int = Field(
            description="Distinct DMs touching the input genes after filters.")
        genes_with_metrics: int = Field(
            description="Input genes with >=1 matching DM row.")
        genes_without_metrics: int = Field(
            description="Input genes present in KG but with zero matching "
                        "DM rows after filters.")
        not_found: list[str] = Field(
            default_factory=list,
            description="Input locus_tags absent from the KG (echo).")
        not_matched: list[str] = Field(
            default_factory=list,
            description="Input locus_tags in KG but with zero DM rows after "
                        "filters (includes kind-mismatch when value_kind set).")
        by_value_kind: list[GeneDmValueKindBreakdown] = Field(
            description="Rows per value_kind.")
        by_metric_type: list[GeneDmMetricTypeBreakdown] = Field(
            description="Rows per metric_type — coarse rollup; same "
                        "metric_type may aggregate across publications.")
        by_metric: list[GeneDmMetricBreakdown] = Field(
            description="Rows per unique DerivedMetric — fine breakdown that "
                        "disambiguates within a metric_type. Each entry "
                        "embeds name, metric_type, and value_kind so "
                        "derived_metric_ids can be picked for downstream "
                        "drill-down. Sorted by count desc.")
        by_compartment: list[GeneDmCompartmentBreakdown] = Field(
            description="Rows per compartment.")
        by_treatment_type: list[GeneDmTreatmentBreakdown] = Field(
            description="Rows per treatment_type (flattened).")
        by_background_factors: list[GeneDmBackgroundFactorBreakdown] = Field(
            description="Rows per background factor (flattened).")
        by_publication: list[GeneDmPublicationBreakdown] = Field(
            description="Rows per parent publication.")
        returned: int = Field(description="Length of results list.")
        offset: int = Field(default=0, description="Pagination offset used.")
        truncated: bool = Field(
            description="True when total_matching > offset + returned.")
        results: list[GeneDerivedMetricsResult] = Field(
            default_factory=list,
            description="One row per gene × DM. Empty when summary=True.")

    # -----------------------------------------------------------------
    # list_derived_metrics
    # -----------------------------------------------------------------

    class ListDerivedMetricsResult(BaseModel):
        derived_metric_id: str = Field(
            description=(
                "Unique id for this DerivedMetric. Pass to `derived_metric_ids` "
                "on drill-down tools (gene_derived_metrics, genes_by_*_metric) "
                "to select this exact DM."
            ),
        )
        name: str = Field(
            description=(
                "Human-readable DM name "
                "(e.g. 'Transcript:protein amplitude ratio')."
            ),
        )
        metric_type: str = Field(
            description=(
                "Category tag identifying what is measured "
                "(e.g. 'diel_amplitude_protein_log2'). The same metric_type may "
                "appear across organisms / publications — pair with organism or "
                "publication_doi when that matters, or use derived_metric_id to "
                "pin one specific DM."
            ),
        )
        value_kind: Literal["numeric", "boolean", "categorical"] = Field(
            description=(
                "Routes to the correct drill-down tool: 'numeric' → "
                "genes_by_numeric_metric, 'boolean' → genes_by_boolean_metric, "
                "'categorical' → genes_by_categorical_metric."
            ),
        )
        rankable: bool = Field(
            description=(
                "True if this DM supports rank / percentile / bucket analysis "
                "on genes_by_numeric_metric. When False, the `bucket`, "
                "`min_percentile`, `max_percentile`, and `max_rank` filters on "
                "that drill-down do not apply — passing them with only "
                "non-rankable DMs raises; mixing rankable + non-rankable drops "
                "the non-rankable ones and lists them in the drill-down's "
                "`excluded_derived_metrics`."
            ),
        )
        has_p_value: bool = Field(
            description=(
                "True if this DM carries statistical p-values, enabling "
                "`significant_only` and `max_adjusted_p_value` on drill-downs. "
                "No DM in the current KG has p-values."
            ),
        )
        unit: str = Field(
            description=(
                "Measurement unit for numeric DMs (e.g. 'hours', 'log2'). "
                "Empty string for boolean and categorical DMs."
            ),
        )
        allowed_categories: list[str] | None = Field(
            description=(
                "Valid category strings for this DM. Non-null only when "
                "value_kind='categorical'; pass a subset as `categories` to "
                "genes_by_categorical_metric."
            ),
        )
        field_description: str = Field(
            description=(
                "Detailed explanation of what this DM measures and how to "
                "interpret its values."
            ),
        )
        organism_name: str = Field(
            description=(
                "Full organism name (e.g. 'Prochlorococcus MED4', "
                "'Alteromonas macleodii MIT1002')."
            ),
        )
        experiment_id: str = Field(
            description=(
                "Parent Experiment node id. Look up context via list_experiments."
            ),
        )
        publication_doi: str = Field(
            description="Parent publication DOI (e.g. '10.1128/mSystems.00040-18').",
        )
        compartment: str = Field(
            description=(
                "Sample compartment or scope (e.g. 'whole_cell', 'vesicle', "
                "'exoproteome', 'spent_medium', 'lysate')."
            ),
        )
        omics_type: str = Field(
            description=(
                "Omics assay type (e.g. 'RNASEQ', 'PROTEOME', "
                "'PAIRED_RNASEQ_PROTEOME')."
            ),
        )
        treatment_type: list[str] = Field(
            description="Treatment type(s) (e.g. ['diel'], ['darkness']).",
        )
        background_factors: list[str] = Field(
            description=(
                "Background experimental factors (e.g. ['axenic'], "
                "['coculture', 'diel']). May be empty."
            ),
        )
        total_gene_count: int = Field(
            description=(
                "Number of distinct genes with at least one measurement for "
                "this DM."
            ),
        )
        growth_phases: list[str] = Field(
            description=(
                "Growth phase(s) this DM pertains to (e.g. ['darkness']). "
                "May be empty."
            ),
        )
        score: float | None = Field(
            default=None,
            description=(
                "Full-text relevance score; present only when search_text was "
                "provided."
            ),
        )
        treatment: str | None = Field(
            default=None,
            description="Treatment description in plain language (verbose mode only).",
        )
        light_condition: str | None = Field(
            default=None,
            description="Light regime (e.g. 'light:dark cycle'; verbose mode only).",
        )
        experimental_context: str | None = Field(
            default=None,
            description=(
                "Longer description of the experimental setup that produced "
                "this DM (verbose mode only)."
            ),
        )
        p_value_threshold: float | None = Field(
            default=None,
            description=(
                "Threshold that defines statistical significance for this DM. "
                "Non-null only when has_p_value=True (verbose mode only; no DM "
                "in current KG has a threshold)."
            ),
        )

    class ListDerivedMetricsResponse(BaseModel):
        total_entries: int = Field(description="Total DMs in the KG (unfiltered baseline).")
        total_matching: int = Field(description="DMs matching all applied filters.")
        by_organism: list[dict] = Field(
            description=(
                "Counts per organism (list of {organism_name, count}, "
                "sorted by count desc)."
            ),
        )
        by_value_kind: list[dict] = Field(
            description="Counts per value_kind (list of {value_kind, count}).",
        )
        by_metric_type: list[dict] = Field(
            description="Counts per metric_type (list of {metric_type, count}).",
        )
        by_compartment: list[dict] = Field(
            description="Counts per compartment (list of {compartment, count}).",
        )
        by_omics_type: list[dict] = Field(
            description="Counts per omics_type (list of {omics_type, count}).",
        )
        by_treatment_type: list[dict] = Field(
            description=(
                "Counts per treatment_type (list of {treatment_type, count}; "
                "DM treatment_type lists are flattened before counting)."
            ),
        )
        by_background_factors: list[dict] = Field(
            description=(
                "Counts per background_factor (list of "
                "{background_factor, count}; flattened)."
            ),
        )
        by_growth_phase: list[dict] = Field(
            description=(
                "Counts per growth_phase (list of {growth_phase, count}; "
                "flattened)."
            ),
        )
        score_max: float | None = Field(
            default=None,
            description=(
                "Max relevance score; present only when search_text was provided."
            ),
        )
        score_median: float | None = Field(
            default=None,
            description=(
                "Median relevance score; present only when search_text was "
                "provided."
            ),
        )
        returned: int = Field(description="Number of rows in results.")
        offset: int = Field(description="Pagination offset used for this call.")
        truncated: bool = Field(
            description=(
                "True when total_matching > returned (more rows available — "
                "paginate with offset)."
            ),
        )
        results: list["ListDerivedMetricsResult"] = Field(
            description="Matching DerivedMetric entries. Empty when summary=True.",
        )

    @mcp.tool(
        tags={"derived-metrics", "discovery", "catalog"},
        annotations={"readOnlyHint": True},
    )
    async def list_derived_metrics(
        ctx: Context,
        search_text: Annotated[str | None, Field(
            description=(
                "Full-text search over DM name and field_description. "
                "Examples: 'diel amplitude', 'darkness survival', 'peak time'."
            ),
        )] = None,
        organism: Annotated[str | None, Field(
            description=(
                "Organism to filter by. Accepts short strain code "
                "('MED4', 'NATL2A', 'MIT1002') or full name "
                "('Prochlorococcus MED4'). Case-insensitive substring match."
            ),
        )] = None,
        metric_types: Annotated[list[str] | None, Field(
            description=(
                "Filter by metric_type tags (e.g. 'diel_amplitude_protein_log2', "
                "'periodic_in_coculture_LD'). The same metric_type may appear "
                "across organisms / publications — use derived_metric_ids to "
                "pin one specific DM when that matters."
            ),
        )] = None,
        value_kind: Annotated[Literal["numeric", "boolean", "categorical"] | None, Field(
            description=(
                "Filter by value kind. Determines which drill-down tool "
                "applies: 'numeric' → genes_by_numeric_metric, 'boolean' → "
                "genes_by_boolean_metric, 'categorical' → "
                "genes_by_categorical_metric."
            ),
        )] = None,
        compartment: Annotated[str | None, Field(
            description=(
                "Sample compartment / scope. Current values: 'whole_cell', "
                "'vesicle', 'exoproteome', 'spent_medium', 'lysate'."
            ),
        )] = None,
        omics_type: Annotated[str | None, Field(
            description=(
                "Omics assay type. Examples: 'RNASEQ', 'PROTEOME', "
                "'PAIRED_RNASEQ_PROTEOME'. Case-insensitive."
            ),
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description=(
                "Treatment type(s) to match. Returns DMs whose treatment_type "
                "list overlaps ANY of the given values (e.g. 'diel', "
                "'darkness', 'nitrogen_starvation'). Case-insensitive."
            ),
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description=(
                "Background experimental factor(s) to match (e.g. 'axenic', "
                "'coculture', 'diel'). Returns DMs overlapping ANY given "
                "value. Case-insensitive."
            ),
        )] = None,
        growth_phases: Annotated[list[str] | None, Field(
            description=(
                "Growth phase(s) to match (e.g. 'darkness', 'exponential'). "
                "Case-insensitive."
            ),
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description=(
                "Filter by one or more publication DOIs "
                "(e.g. '10.1128/mSystems.00040-18'). Exact match."
            ),
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Filter by one or more Experiment node ids.",
        )] = None,
        derived_metric_ids: Annotated[list[str] | None, Field(
            description=(
                "Look up specific DMs by their unique id (matches "
                "`derived_metric_id` on each result). Use to pin one DM when "
                "the same metric_type appears across publications or "
                "organisms."
            ),
        )] = None,
        rankable: Annotated[bool | None, Field(
            description=(
                "Filter to DMs that support rank / percentile / bucket "
                "analysis. Set to True before calling genes_by_numeric_metric "
                "with `bucket`, `min_percentile`, `max_percentile`, or "
                "`max_rank` — those filters require rankable=True on every "
                "selected DM."
            ),
        )] = None,
        has_p_value: Annotated[bool | None, Field(
            description=(
                "Filter to DMs that carry statistical p-values. Set to True "
                "before using `significant_only` or `max_adjusted_p_value` on "
                "drill-downs. No DM in the current KG carries p-values, so "
                "has_p_value=True returns zero rows today — kept available "
                "because the drill-down p-value filters raise when no "
                "selected DM supports them."
            ),
        )] = None,
        summary: Annotated[bool, Field(
            description=(
                "Return summary fields only (counts and breakdowns, no "
                "individual results). Use for quick orientation."
            ),
        )] = False,
        verbose: Annotated[bool, Field(
            description=(
                "Include detailed text fields per result: treatment, "
                "light_condition, experimental_context. "
                "(p_value_threshold is reserved for future DMs with "
                "statistical significance; always null in current data.)"
            ),
        )] = False,
        limit: Annotated[int, Field(
            description="Max results to return. Paginate with offset.", ge=1,
        )] = 20,
        offset: Annotated[int, Field(
            description="Pagination offset (starting row, 0-indexed).", ge=0,
        )] = 0,
    ) -> ListDerivedMetricsResponse:
        """Discover DerivedMetric (DM) nodes — column-level scalar summaries
        of gene behavior (e.g. rhythmicity flags, diel amplitudes,
        darkness-survival class) that sit alongside DE and gene clusters as
        non-DE evidence.

        Call this first, before `gene_derived_metrics` or the three
        `genes_by_{kind}_metric` drill-downs. Inspect `value_kind` (routes
        you to the right drill-down), `rankable` (gates bucket / percentile
        / rank filters), `has_p_value` (gates significance filters), and
        `allowed_categories` (for categorical DMs) here — drill-down tools
        will raise if you pass filters that the selected DM set doesn't
        support.

        After this tool, drill in via:
        - gene_derived_metrics(locus_tags=[...]) for per-gene DM lookup across all kinds
        - genes_by_numeric_metric(derived_metric_ids=[id], ...) for numeric drill-down
        - genes_by_boolean_metric(derived_metric_ids=[id], ...) for flag drill-down
        - genes_by_categorical_metric(derived_metric_ids=[id], ...) for categorical drill-down
        """
        await ctx.info(f"list_derived_metrics search_text={search_text!r} "
                       f"organism={organism} limit={limit}")
        conn = _conn(ctx)
        try:
            data = api.list_derived_metrics(
                search_text=search_text, organism=organism,
                metric_types=metric_types, value_kind=value_kind,
                compartment=compartment, omics_type=omics_type,
                treatment_type=treatment_type,
                background_factors=background_factors,
                growth_phases=growth_phases, publication_doi=publication_doi,
                experiment_ids=experiment_ids,
                derived_metric_ids=derived_metric_ids,
                rankable=rankable, has_p_value=has_p_value,
                summary=summary, verbose=verbose,
                limit=limit, offset=offset,
                conn=conn,
            )
        except ValueError as exc:
            await ctx.warning(f"list_derived_metrics error: {exc}")
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            await ctx.error(f"Error in list_derived_metrics: {exc}")
            raise ToolError(f"Error in list_derived_metrics: {exc}") from exc
        return ListDerivedMetricsResponse(**data)

    # ── gene_clusters_by_gene ──────────────────────────────────────────

    class GeneClusterAnalysisBreakdown(BaseModel):
        analysis_id: str = Field(description="Clustering analysis ID")
        count: int = Field(description="Rows for this analysis")

    class GeneClustersByGeneResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0370')")
        gene_name: str | None = Field(default=None,
            description="Gene name (e.g. 'cynA')")
        cluster_id: str = Field(
            description="Cluster node ID (e.g. 'cluster:msb4100087:med4:up_n_transport')")
        cluster_name: str = Field(
            description="Cluster name (e.g. 'MED4 cluster 1 (up, N transport)')")
        cluster_type: str = Field(
            description="Cluster category (e.g. 'condition_comparison')")
        membership_score: float | None = Field(default=None,
            description="Fuzzy membership score (null for K-means)")
        analysis_id: str = Field(
            description="Clustering analysis ID")
        analysis_name: str = Field(
            description="Clustering analysis name")
        treatment_type: list[str] = Field(
            description="Treatment types for this cluster")
        background_factors: list[str] = Field(default_factory=list,
            description="Background experimental factors")
        # verbose-only
        cluster_method: str | None = Field(default=None,
            description="Clustering method (e.g. 'K-means')")
        member_count: int | None = Field(default=None,
            description="Total genes in this cluster")
        cluster_functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE (cluster-level)")
        cluster_expression_dynamics: str | None = Field(default=None,
            description="Expression dynamics label (e.g. 'periodic in L:D only')")
        cluster_temporal_pattern: str | None = Field(default=None,
            description="Detailed temporal pattern description (cluster-level)")
        treatment: str | None = Field(default=None,
            description="Free-text condition description")
        light_condition: str | None = Field(default=None,
            description="Light regime")
        experimental_context: str | None = Field(default=None,
            description="Full experimental context description")
        p_value: float | None = Field(default=None,
            description="Assignment p-value (null for most methods)")

    class GeneClustersByGeneResponse(BaseModel):
        total_matching: int = Field(
            description="Gene × cluster rows matching filters")
        total_clusters: int = Field(
            description="Distinct clusters matched")
        genes_with_clusters: int = Field(
            description="Input genes with at least one cluster membership")
        genes_without_clusters: int = Field(
            description="Input genes with zero memberships after filters")
        not_found: list[str] = Field(default_factory=list,
            description="Locus tags not found in KG")
        not_matched: list[str] = Field(default_factory=list,
            description="Locus tags in KG but no cluster memberships after filters")
        by_cluster_type: list["GeneClusterTypeBreakdown"] = Field(
            description="Rows per cluster type")
        by_treatment_type: list["GeneClusterTreatmentBreakdown"] = Field(
            description="Rows per treatment type")
        by_background_factors: list["GeneClusterBackgroundFactorBreakdown"] = Field(
            description="Rows per background factor")
        by_analysis: list["GeneClusterAnalysisBreakdown"] = Field(
            description="Rows per clustering analysis")
        returned: int = Field(description="Results in this response")
        offset: int = Field(default=0, description="Offset into result set")
        truncated: bool = Field(
            description="True if total_matching > offset + returned")
        results: list["GeneClustersByGeneResult"] = Field(
            default_factory=list, description="One row per gene × cluster")

    @mcp.tool(
        tags={"clusters", "genes"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                      "idempotentHint": True, "openWorldHint": False},
    )
    async def gene_clusters_by_gene(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags (e.g. ['PMM0370', 'PMM0920']).",
        )],
        organism: Annotated[str | None, Field(
            description="Organism name (case-insensitive partial match); "
            "inferred from genes if omitted. Single organism enforced.",
        )] = None,
        cluster_type: Annotated[str | None, Field(
            description="Filter: " + ", ".join(f"'{v}'" for v in sorted(VALID_CLUSTER_TYPES)) + ".",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Filter by treatment type(s).",
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Filter by background factors.",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Filter by publication DOI(s).",
        )] = None,
        analysis_ids: Annotated[list[str] | None, Field(
            description="Filter by clustering analysis IDs.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include cluster_method, member_count, "
            "cluster_functional_description, cluster_expression_dynamics, "
            "cluster_temporal_pattern, treatment, light_condition, "
            "experimental_context, p_value.",
        )] = False,
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0)] = 0,
    ) -> GeneClustersByGeneResponse:
        """Find which gene clusters contain the given genes.

        Gene-centric lookup: 'what clusters are these genes in?'
        Single organism enforced. One row per gene × cluster.

        Use list_clustering_analyses for discovery by text search.
        Use genes_in_cluster to drill into a cluster's full membership.
        """
        await ctx.info(f"gene_clusters_by_gene locus_tags={locus_tags} "
                       f"organism={organism}")
        try:
            conn = _conn(ctx)
            data = api.gene_clusters_by_gene(
                locus_tags, organism=organism,
                cluster_type=cluster_type, treatment_type=treatment_type,
                background_factors=background_factors,
                publication_doi=publication_doi,
                analysis_ids=analysis_ids,
                summary=summary, verbose=verbose, limit=limit, offset=offset,
                conn=conn,
            )
            by_cluster_type = [GeneClusterTypeBreakdown(**b)
                               for b in data["by_cluster_type"]]
            by_treatment_type = [GeneClusterTreatmentBreakdown(**b)
                                 for b in data["by_treatment_type"]]
            by_background_factors = [GeneClusterBackgroundFactorBreakdown(**b)
                                     for b in data["by_background_factors"]]
            by_analysis = [GeneClusterAnalysisBreakdown(**b)
                           for b in data["by_analysis"]]
            results = [GeneClustersByGeneResult(**r) for r in data["results"]]
            response = GeneClustersByGeneResponse(
                total_matching=data["total_matching"],
                total_clusters=data["total_clusters"],
                genes_with_clusters=data["genes_with_clusters"],
                genes_without_clusters=data["genes_without_clusters"],
                not_found=data["not_found"],
                not_matched=data["not_matched"],
                by_cluster_type=by_cluster_type,
                by_treatment_type=by_treatment_type,
                by_background_factors=by_background_factors,
                by_analysis=by_analysis,
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of "
                           f"{response.total_matching} gene×cluster rows")
            return response
        except ValueError as e:
            await ctx.warning(f"gene_clusters_by_gene error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_clusters_by_gene unexpected error: {e}")
            raise ToolError(f"Error in gene_clusters_by_gene: {e}")

    # ── gene_derived_metrics ───────────────────────────────────────────

    @mcp.tool(
        tags={"derived-metrics", "genes", "batch"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def gene_derived_metrics(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags to look up (e.g. ['PMM1714', "
                        "'PMM0001']). Required, non-empty. Single organism "
                        "enforced — locus_tags must all resolve to the same "
                        "organism (or pair with `organism` to disambiguate).",
        )],
        organism: Annotated[str | None, Field(
            description="Organism to scope to. Accepts short strain code "
                        "('MED4', 'NATL2A', 'MIT1002') or full name. "
                        "Case-insensitive substring match. Inferred from "
                        "locus_tags when omitted.",
        )] = None,
        metric_types: Annotated[list[str] | None, Field(
            description="Filter by metric_type tags (e.g. "
                        "'diel_amplitude_protein_log2'). Same metric_type may "
                        "appear across publications — pair with publication_doi "
                        "or use derived_metric_ids to pin one specific DM.",
        )] = None,
        value_kind: Annotated[
            Literal["numeric", "boolean", "categorical"] | None, Field(
                description="Restrict to one DM kind. Each kind has a "
                            "different `value` column type — 'numeric' → "
                            "float, 'boolean' → 'true'/'false', "
                            "'categorical' → category string.",
            )] = None,
        compartment: Annotated[str | None, Field(
            description="Filter to DMs from one sample compartment "
                        "('whole_cell', 'vesicle', 'exoproteome', "
                        "'spent_medium', 'lysate'). Exact match.",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Treatment type(s) to match. Returns DMs whose "
                        "treatment_type list overlaps ANY of the given "
                        "values. Case-insensitive.",
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Background experimental factor(s) to match. "
                        "ANY-overlap. Case-insensitive.",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Filter by one or more publication DOIs. Exact match.",
        )] = None,
        derived_metric_ids: Annotated[list[str] | None, Field(
            description="Look up specific DMs by their unique id. Use to "
                        "pin one DM when the same metric_type appears across "
                        "publications. Pair with `list_derived_metrics`.",
        )] = None,
        summary: Annotated[bool, Field(
            description="Return summary fields only (counts, breakdowns, "
                        "not_found / not_matched). Sugar for limit=0; results=[].",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include detailed text fields per row: treatment, "
                        "light_condition, experimental_context, plus raw "
                        "p_value when parent DM has_p_value=True.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max rows to return. Paginate with offset. Use "
                        "`summary=True` for summary-only (sets limit=0 "
                        "internally).",
            ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Pagination offset (starting row, 0-indexed).", ge=0,
        )] = 0,
    ) -> GeneDerivedMetricsResponse:
        """Polymorphic `value` column — branch on `value_kind` per row; consult `list_derived_metrics(value_kind=...)` first to know which DMs exist and whether numeric rows carry rank/percentile/bucket extras (rankable gate) or `adjusted_p_value`/`significant` (has_p_value gate).

        Gene-centric batch lookup for DerivedMetric annotations — one row
        per gene × DM. `value` is `float` on numeric rows, `'true'`/'false'`
        on boolean rows, category string on categorical rows. Numeric extras
        (rank_by_metric, metric_percentile, metric_bucket) are populated
        only when the parent DM is rankable; null otherwise. Same gate for
        adjusted_p_value / significant on has_p_value DMs (none in the
        current KG).

        Single organism enforced. not_found (locus_tag absent from KG) and
        not_matched (in KG but no DM rows after filters — includes
        kind-mismatch when value_kind is set) make empty rows diagnosable.
        For edge-level numeric filters (bucket / percentile / rank / value
        thresholds), pivot to genes_by_numeric_metric.
        """
        await ctx.info(f"gene_derived_metrics locus_tags={locus_tags} "
                       f"organism={organism}")
        try:
            conn = _conn(ctx)
            data = api.gene_derived_metrics(
                locus_tags, organism=organism,
                metric_types=metric_types, value_kind=value_kind,
                compartment=compartment, treatment_type=treatment_type,
                background_factors=background_factors,
                publication_doi=publication_doi,
                derived_metric_ids=derived_metric_ids,
                summary=summary, verbose=verbose,
                limit=limit, offset=offset, conn=conn,
            )
            # Build breakdowns + results into NEW locals (don't mutate data)
            by_value_kind = [GeneDmValueKindBreakdown(**b)
                             for b in data["by_value_kind"]]
            by_metric_type = [GeneDmMetricTypeBreakdown(**b)
                              for b in data["by_metric_type"]]
            by_metric = [GeneDmMetricBreakdown(**b)
                         for b in data["by_metric"]]
            by_compartment = [GeneDmCompartmentBreakdown(**b)
                              for b in data["by_compartment"]]
            by_treatment_type = [GeneDmTreatmentBreakdown(**b)
                                 for b in data["by_treatment_type"]]
            by_background_factors = [GeneDmBackgroundFactorBreakdown(**b)
                                     for b in data["by_background_factors"]]
            by_publication = [GeneDmPublicationBreakdown(**b)
                              for b in data["by_publication"]]
            results = [GeneDerivedMetricsResult(**r) for r in data["results"]]
            response = GeneDerivedMetricsResponse(
                total_matching=data["total_matching"],
                total_derived_metrics=data["total_derived_metrics"],
                genes_with_metrics=data["genes_with_metrics"],
                genes_without_metrics=data["genes_without_metrics"],
                not_found=data["not_found"],
                not_matched=data["not_matched"],
                by_value_kind=by_value_kind,
                by_metric_type=by_metric_type,
                by_metric=by_metric,
                by_compartment=by_compartment,
                by_treatment_type=by_treatment_type,
                by_background_factors=by_background_factors,
                by_publication=by_publication,
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of "
                           f"{response.total_matching} gene×DM rows")
            return response
        except ValueError as e:
            await ctx.warning(f"gene_derived_metrics error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_derived_metrics unexpected error: {e}")
            raise ToolError(f"Error in gene_derived_metrics: {e}")

    # ── genes_in_cluster ───────────────────────────────────────────────

    class GenesInClusterResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0370')")
        gene_name: str | None = Field(default=None,
            description="Gene name (e.g. 'cynA')")
        product: str | None = Field(default=None,
            description="Gene product (e.g. 'cyanate ABC transporter')")
        gene_category: str | None = Field(default=None,
            description="Functional category (e.g. 'N-metabolism')")
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4')")
        cluster_id: str = Field(
            description="Cluster node ID")
        cluster_name: str = Field(
            description="Cluster name")
        membership_score: float | None = Field(default=None,
            description="Fuzzy membership score (null for K-means)")
        # verbose-only
        gene_function_description: str | None = Field(default=None,
            description="Gene functional description (gene-level)")
        gene_summary: str | None = Field(default=None,
            description="Gene summary text (gene-level)")
        p_value: float | None = Field(default=None,
            description="Assignment p-value (edge-level)")
        cluster_functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE (cluster-level)")
        cluster_expression_dynamics: str | None = Field(default=None,
            description="Expression dynamics label (e.g. 'periodic in L:D only')")
        cluster_temporal_pattern: str | None = Field(default=None,
            description="Detailed temporal pattern description (cluster-level)")

    class GenesInClusterClusterBreakdown(BaseModel):
        cluster_id: str = Field(description="Cluster node ID")
        cluster_name: str = Field(description="Cluster name")
        count: int = Field(description="Member genes in this cluster")

    class GenesInClusterCategoryBreakdown(BaseModel):
        category: str = Field(description="Gene category")
        count: int = Field(description="Genes in this category")

    class GenesInClusterResponse(BaseModel):
        total_matching: int = Field(
            description="Gene × cluster rows")
        analysis_name: str | None = Field(default=None,
            description="Analysis name (when queried by analysis_id)")
        by_organism: list[GeneClusterOrganismBreakdown] = Field(
            description="Members per organism")
        by_cluster: list[GenesInClusterClusterBreakdown] = Field(
            description="Members per cluster")
        top_categories: list[GenesInClusterCategoryBreakdown] = Field(
            description="Top 5 gene categories by count")
        genes_per_cluster_max: int = Field(
            description="Largest cluster's gene count")
        genes_per_cluster_median: float = Field(
            description="Median gene count across clusters")
        not_found_clusters: list[str] = Field(default_factory=list,
            description="Cluster IDs not found in KG")
        not_matched_clusters: list[str] = Field(default_factory=list,
            description="Clusters found but no members after organism filter")
        not_matched_organism: str | None = Field(default=None,
            description="Organism that didn't match any cluster's organism")
        returned: int = Field(description="Results in this response")
        offset: int = Field(default=0, description="Offset into result set")
        truncated: bool = Field(
            description="True if total_matching > offset + returned")
        results: list[GenesInClusterResult] = Field(
            default_factory=list, description="One row per gene × cluster")

    @mcp.tool(
        tags={"clusters", "genes"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                      "idempotentHint": True, "openWorldHint": False},
    )
    async def genes_in_cluster(
        ctx: Context,
        cluster_ids: Annotated[list[str] | None, Field(
            description="GeneCluster node IDs (from list_clustering_analyses "
            "or gene_clusters_by_gene). Provide this OR analysis_id.",
        )] = None,
        analysis_id: Annotated[str | None, Field(
            description="ClusteringAnalysis node ID — returns all genes in "
            "all clusters of this analysis. Provide this OR cluster_ids.",
        )] = None,
        organism: Annotated[str | None, Field(
            description="Filter by organism (case-insensitive partial match). "
            "Single organism enforced.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include gene_function_description, gene_summary (gene-level), "
            "p_value (edge-level), cluster_functional_description, "
            "cluster_expression_dynamics, cluster_temporal_pattern (cluster-level).",
        )] = False,
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0)] = 0,
    ) -> GenesInClusterResponse:
        """Get member genes of gene clusters.

        Takes cluster IDs or an analysis ID and returns member genes.
        One row per gene × cluster. Provide cluster_ids OR analysis_id (not both).

        For analysis discovery, use list_clustering_analyses first.
        For gene → cluster direction, use gene_clusters_by_gene.
        """
        await ctx.info(f"genes_in_cluster cluster_ids={cluster_ids} "
                       f"analysis_id={analysis_id} organism={organism}")
        try:
            conn = _conn(ctx)
            data = api.genes_in_cluster(
                cluster_ids=cluster_ids, analysis_id=analysis_id,
                organism=organism,
                summary=summary, verbose=verbose, limit=limit, offset=offset,
                conn=conn,
            )
            by_organism = [GeneClusterOrganismBreakdown(**b)
                           for b in data["by_organism"]]
            by_cluster = [GenesInClusterClusterBreakdown(**b)
                          for b in data["by_cluster"]]
            top_categories = [GenesInClusterCategoryBreakdown(**b)
                              for b in data["top_categories"]]
            results = [GenesInClusterResult(**r) for r in data["results"]]
            response = GenesInClusterResponse(
                total_matching=data["total_matching"],
                analysis_name=data.get("analysis_name"),
                by_organism=by_organism,
                by_cluster=by_cluster,
                top_categories=top_categories,
                genes_per_cluster_max=data["genes_per_cluster_max"],
                genes_per_cluster_median=data["genes_per_cluster_median"],
                not_found_clusters=data["not_found_clusters"],
                not_matched_clusters=data["not_matched_clusters"],
                not_matched_organism=data.get("not_matched_organism"),
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of "
                           f"{response.total_matching} gene×cluster rows")
            return response
        except ValueError as e:
            await ctx.warning(f"genes_in_cluster error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"genes_in_cluster unexpected error: {e}")
            raise ToolError(f"Error in genes_in_cluster: {e}")

    class ExampleTerm(BaseModel):
        term_id: str = Field(description="Ontology term ID (e.g. 'go:0044238')")
        name: str = Field(description="Ontology term name")
        n_genes: int = Field(description="Genes at this term in this organism")

    class OntologyLandscapeRow(BaseModel):
        ontology_type: str = Field(description="Ontology key (e.g. 'cyanorak_role')")
        level: int = Field(description="Hierarchy level; 0 = broadest")
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
        relevance_rank: int = Field(
            description="1-indexed rank by spec_score; stable under pagination",
        )
        n_terms_with_genes: int
        n_genes_at_level: int
        genome_coverage: float = Field(
            description="n_genes_at_level / organism_gene_count",
        )
        min_genes_per_term: int
        q1_genes_per_term: float
        median_genes_per_term: float
        q3_genes_per_term: float
        max_genes_per_term: int
        n_levels_in_ontology: int = Field(
            description="Levels this ontology spans (1 = flat)",
        )
        best_effort_share: float | None = Field(
            default=None,
            description="Fraction of reached terms flagged level_is_best_effort "
                        "(GO only; None for others)",
        )
        example_terms: list[ExampleTerm] | None = Field(
            default=None,
            description="Top 3 terms by gene count (verbose only)",
        )
        min_exp_coverage: float | None = Field(default=None)
        median_exp_coverage: float | None = Field(default=None)
        max_exp_coverage: float | None = Field(default=None)
        n_experiments_with_coverage: int | None = Field(default=None)

    class OntologySummary(BaseModel):
        best_level: int
        best_genome_coverage: float
        best_relevance_rank: int
        n_levels: int
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")

    class OntologyLandscapeResponse(BaseModel):
        organism_name: str
        organism_gene_count: int
        n_ontologies: int
        by_ontology: dict[str, OntologySummary] = Field(default_factory=dict)
        not_found: list[str] = Field(default_factory=list)
        not_matched: list[str] = Field(default_factory=list)
        total_matching: int
        returned: int
        truncated: bool
        offset: int = 0
        results: list[OntologyLandscapeRow] = Field(default_factory=list)

    @mcp.tool(
        tags={"ontology", "enrichment"},
        annotations={"readOnlyHint": True},
    )
    async def ontology_landscape(
        ctx: Context,
        organism: Annotated[str, Field(
            description="Organism (fuzzy match, e.g. 'MED4').",
        )],
        ontology: Annotated[
            Literal["go_bp", "go_mf", "go_cc", "ec", "kegg",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite"] | None,
            Field(description="If None, surveys all 10 ontologies."),
        ] = None,
        tree: Annotated[str | None, Field(
            description="BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'.",
        )] = None,
        experiment_ids: Annotated[
            list[str] | None,
            Field(description="Restrict coverage computation to genes "
                              "quantified in these experiments."),
        ] = None,
        summary: Annotated[bool, Field(
            description="If true, omit per-row results (by_ontology only).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include example_terms (top 3 terms per level).",
        )] = False,
        limit: Annotated[int | None, Field(
            description="Max rows returned. None (default) returns all rows; "
                        "set an integer to truncate.",
            ge=1,
        )] = None,
        offset: Annotated[int, Field(description="Skip N rows before limit", ge=0)] = 0,
        min_gene_set_size: Annotated[int, Field(
            description="Exclude terms with fewer genes than this (default 5).",
            ge=1,
        )] = 5,
        max_gene_set_size: Annotated[int, Field(
            description="Exclude terms with more genes than this (default 500).",
            ge=1,
        )] = 500,
    ) -> OntologyLandscapeResponse:
        """Rank (ontology x level) combinations by enrichment suitability.

        Per-(ontology x level) stats: term-size distribution, genome coverage,
        best-effort share (GO). Ranked by coverage x size_factor(median) with
        sweet-spot [5, 50] median genes-per-term. Default ontology=None surveys
        all 9 ontologies. Pass experiment_ids to weight by coverage of those
        experiments' quantified genes. See docs://tools/ontology_landscape.
        """
        await ctx.info(f"ontology_landscape organism={organism} ontology={ontology}")
        try:
            conn = _conn(ctx)
            data = api.ontology_landscape(
                organism=organism, ontology=ontology,
                experiment_ids=experiment_ids,
                summary=summary, verbose=verbose,
                limit=limit, offset=offset,
                min_gene_set_size=min_gene_set_size,
                max_gene_set_size=max_gene_set_size,
                tree=tree, conn=conn,
            )
            return OntologyLandscapeResponse(**data)
        except ValueError as e:
            await ctx.warning(f"ontology_landscape error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"ontology_landscape unexpected error: {e}")
            raise ToolError(f"Error in ontology_landscape: {e}")

    @mcp.tool(
        tags={"enrichment", "ontology", "expression"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def pathway_enrichment(
        ctx: Context,
        organism: Annotated[str, Field(
            description="Organism (case-insensitive fuzzy match, e.g. 'MED4'). Single-organism enforced.",
        )],
        experiment_ids: Annotated[list[str], Field(
            description="Experiments to pull DE from. Get IDs from list_experiments.",
        )],
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
        ], Field(
            description="Ontology for pathway definitions. Run ontology_landscape first to rank by relevance.",
        )],
        tree: Annotated[str | None, Field(
            description="BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'.",
        )] = None,
        level: Annotated[int | None, Field(
            description="Hierarchy level (0 = root). At least one of level or term_ids required.",
            ge=0,
        )] = None,
        term_ids: Annotated[list[str] | None, Field(
            description="Specific term IDs to test. Combines with level to scope rollup.",
        )] = None,
        direction: Annotated[Literal["up", "down", "both"], Field(
            description="DE direction(s) to include in gene_sets.",
        )] = "both",
        significant_only: Annotated[bool, Field(
            description="If true, only significant DE rows count as foreground.",
        )] = True,
        background: Annotated[str | list[str], Field(
            description="'table_scope' (default, per-cluster), 'organism', or explicit locus_tag list.",
        )] = "table_scope",
        min_gene_set_size: Annotated[int, Field(
            description="Per-cluster M filter: drop pathways with fewer members in the background.",
            ge=0,
        )] = 5,
        max_gene_set_size: Annotated[int | None, Field(
            description="Per-cluster M filter upper bound. None disables.",
            ge=1,
        )] = 500,
        pvalue_cutoff: Annotated[float, Field(
            description="Significance threshold for `p_adjust`.",
            gt=0, lt=1,
        )] = 0.05,
        timepoint_filter: Annotated[list[str] | None, Field(
            description="Restrict to these timepoint labels. Useful for 10+ timepoint experiments.",
        )] = None,
        growth_phases: Annotated[list[str] | None, Field(
            description="Filter DE results by growth phase(s) before enrichment (case-insensitive). "
            "E.g. ['exponential'].",
        )] = None,
        summary: Annotated[bool, Field(
            description="If true, omit results (envelope only).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max rows returned. Default 100 — top hits by p_adjust globally.",
            ge=1,
        )] = 100,
        offset: Annotated[int, Field(
            description="Skip N rows before limit.",
            ge=0,
        )] = 0,
    ) -> PathwayEnrichmentResponse:
        """Pathway over-representation analysis from DE results (Fisher + BH).

        See docs://analysis/enrichment for methodology;
        docs://examples/pathway_enrichment.py for runnable code (covers
        EnrichmentResult accessors, custom term2gene, compareCluster export).
        """
        await ctx.info(
            f"pathway_enrichment organism={organism} experiments={len(experiment_ids)} "
            f"ontology={ontology} level={level}"
        )
        try:
            conn = _conn(ctx)
            result = api.pathway_enrichment(
                organism=organism,
                experiment_ids=experiment_ids,
                ontology=ontology,
                level=level,
                term_ids=term_ids,
                direction=direction,
                significant_only=significant_only,
                background=background,
                min_gene_set_size=min_gene_set_size,
                max_gene_set_size=max_gene_set_size,
                pvalue_cutoff=pvalue_cutoff,
                timepoint_filter=timepoint_filter,
                growth_phases=growth_phases,
                tree=tree,
                conn=conn,
            )
        except ValueError as e:
            raise ToolError(str(e)) from e

        envelope = result.to_envelope(summary=summary, limit=limit, offset=offset)

        # Emit warnings on non-empty validation buckets
        warnings = []
        if envelope["not_found"]:
            warnings.append(f"{len(envelope['not_found'])} experiment_ids not_found")
        if envelope["not_matched"]:
            warnings.append(f"{len(envelope['not_matched'])} not_matched (wrong organism)")
        if envelope.get("no_expression"):
            warnings.append(f"{len(envelope['no_expression'])} no_expression (no DE rows)")
        tv = envelope.get("term_validation", {})
        for key in ("not_found", "wrong_ontology", "wrong_level"):
            if tv.get(key):
                warnings.append(f"{len(tv[key])} term_ids {key}")
        if envelope.get("clusters_skipped"):
            warnings.append(f"{len(envelope['clusters_skipped'])} clusters skipped")
        if warnings:
            await ctx.warning("; ".join(warnings))

        return PathwayEnrichmentResponse(**envelope)

    @mcp.tool(
        tags={"enrichment", "clustering", "ontology"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def cluster_enrichment(
        ctx: Context,
        analysis_id: Annotated[str, Field(description="Clustering analysis ID. Get from list_clustering_analyses.")],
        organism: Annotated[str, Field(description="Organism (case-insensitive fuzzy match). Single-organism enforced.")],
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
        ], Field(description="Ontology for pathway definitions. Run ontology_landscape first.")],
        tree: Annotated[str | None, Field(description="BRITE tree name filter. Only valid when ontology='brite'.")] = None,
        level: Annotated[int | None, Field(description="Hierarchy level (0 = root). At least one of level or term_ids required.", ge=0)] = None,
        term_ids: Annotated[list[str] | None, Field(description="Specific term IDs to test.")] = None,
        background: Annotated[str | list[str], Field(description="'cluster_union' (default), 'organism', or explicit locus_tag list.")] = "cluster_union",
        min_gene_set_size: Annotated[int, Field(description="Per-cluster M filter: drop pathways with fewer members.", ge=0)] = 5,
        max_gene_set_size: Annotated[int | None, Field(description="Per-cluster M filter upper bound. None disables.", ge=1)] = 500,
        min_cluster_size: Annotated[int, Field(description="Skip clusters with fewer members than this.", ge=0)] = 3,
        max_cluster_size: Annotated[int | None, Field(description="Skip clusters with more members. None disables.", ge=1)] = None,
        pvalue_cutoff: Annotated[float, Field(description="Significance threshold for p_adjust.", gt=0, lt=1)] = 0.05,
        summary: Annotated[bool, Field(description="If true, omit results (envelope only).")] = False,
        limit: Annotated[int, Field(description="Max rows returned.", ge=1)] = 5,
        offset: Annotated[int, Field(description="Skip N rows before limit.", ge=0)] = 0,
    ) -> ClusterEnrichmentResponse:
        """Cluster-membership over-representation analysis (Fisher + BH).

        Runs ORA on every cluster in a clustering analysis. Use
        list_clustering_analyses to find analysis IDs. Background
        defaults to the union of all clustered genes.
        See docs://analysis/enrichment for methodology;
        docs://examples/pathway_enrichment.py for runnable code (the custom
        term2gene path covers cluster-membership enrichment).
        """
        await ctx.info(
            f"cluster_enrichment analysis_id={analysis_id} "
            f"ontology={ontology} level={level}"
        )
        try:
            conn = _conn(ctx)
            result = api.cluster_enrichment(
                analysis_id=analysis_id,
                organism=organism,
                ontology=ontology,
                level=level,
                term_ids=term_ids,
                tree=tree,
                background=background,
                min_gene_set_size=min_gene_set_size,
                max_gene_set_size=max_gene_set_size,
                min_cluster_size=min_cluster_size,
                max_cluster_size=max_cluster_size,
                pvalue_cutoff=pvalue_cutoff,
                conn=conn,
            )
        except ValueError as e:
            raise ToolError(str(e)) from e

        envelope = result.to_envelope(summary=summary, limit=limit, offset=offset)

        # Emit warnings
        warnings = []
        if envelope.get("not_found"):
            warnings.append(f"{len(envelope['not_found'])} not_found")
        if envelope.get("not_matched"):
            warnings.append(f"{len(envelope['not_matched'])} not_matched (wrong organism)")
        tv = envelope.get("term_validation", {})
        for key in ("not_found", "wrong_ontology", "wrong_level"):
            if tv.get(key):
                warnings.append(f"{len(tv[key])} term_ids {key}")
        if envelope.get("clusters_skipped"):
            warnings.append(f"{len(envelope['clusters_skipped'])} clusters skipped")
        if warnings:
            await ctx.warning("; ".join(warnings))

        return ClusterEnrichmentResponse(**envelope)

    # ── genes_by_numeric_metric breakdowns ─────────────────────────────

    class GenesByNumericMetricOrganismBreakdown(BaseModel):
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4').")
        count: int = Field(description="Rows from this organism in current result.")

    class GenesByNumericMetricCompartmentBreakdown(BaseModel):
        compartment: str = Field(description="Sample compartment.")
        count: int = Field(description="Rows in this compartment.")

    class GenesByNumericMetricPublicationBreakdown(BaseModel):
        publication_doi: str = Field(description="Parent publication DOI.")
        count: int = Field(description="Rows from this publication.")

    class GenesByNumericMetricExperimentBreakdown(BaseModel):
        experiment_id: str = Field(description="Parent experiment id.")
        count: int = Field(description="Rows from this experiment.")

    class GenesByNumericMetricCategoryBreakdown(BaseModel):
        gene_category: str = Field(description="Gene functional category.")
        count: int = Field(description="Rows in this category.")

    class GenesByNumericMetricBreakdown(BaseModel):
        """Per-DM rollup: filtered-slice value distribution + full-DM context."""
        derived_metric_id: str = Field(description="Unique DM id.")
        name: str = Field(description="DM human label.")
        metric_type: str = Field(description="Category tag.")
        value_kind: Literal["numeric"] = Field(
            description="Always 'numeric' in this tool; kept for cross-tool "
                        "row-shape consistency.")
        count: int = Field(
            description="Rows contributed by this DM after filters.")
        # Filtered slice (query-time)
        value_min: float | None = Field(
            default=None, description="Min `r.value` in filtered slice.")
        value_q1: float | None = Field(
            default=None, description="Q1 of `r.value` in filtered slice.")
        value_median: float | None = Field(
            default=None, description="Median of `r.value` in filtered slice.")
        value_q3: float | None = Field(
            default=None, description="Q3 of `r.value` in filtered slice.")
        value_max: float | None = Field(
            default=None, description="Max `r.value` in filtered slice.")
        # Full DM (precomputed dm.value_*)
        dm_value_min: float | None = Field(
            default=None,
            description="Full-DM min (precomputed `dm.value_min`). Always "
                        "populated for numeric DMs after the 2026-04-26 KG "
                        "rebuild.")
        dm_value_q1: float | None = Field(
            default=None,
            description="Full-DM Q1 (precomputed `dm.value_q1`).")
        dm_value_median: float | None = Field(
            default=None,
            description="Full-DM median (precomputed `dm.value_median`).")
        dm_value_q3: float | None = Field(
            default=None,
            description="Full-DM Q3 (precomputed `dm.value_q3`).")
        dm_value_max: float | None = Field(
            default=None,
            description="Full-DM max (precomputed `dm.value_max`).")
        # Rank distribution (filtered, rankable-only)
        rank_min: int | None = Field(
            default=None,
            description="Min rank in filtered slice. Null on non-rankable DMs.")
        rank_max: int | None = Field(
            default=None,
            description="Max rank in filtered slice. Null on non-rankable DMs.")

    class ExcludedDerivedMetric(BaseModel):
        derived_metric_id: str = Field(description="DM id that was excluded.")
        metric_type: str = Field(description="DM metric_type tag.")
        rankable: bool = Field(description="DM `rankable` flag.")
        has_p_value: bool = Field(description="DM `has_p_value` flag.")
        reason: str = Field(
            description="Human-readable explanation, e.g. "
                        "'non-rankable; bucket filter does not apply'.")

    # ── genes_by_numeric_metric per-row result ─────────────────────────

    class GenesByNumericMetricResult(BaseModel):
        # Identity / routing (5)
        locus_tag: str = Field(
            description="Gene locus tag (e.g. 'PMM1545').")
        gene_name: str | None = Field(
            default=None,
            description="Gene name (e.g. 'rpsH'); null when KG has none.")
        product: str | None = Field(
            default=None,
            description="Gene product (e.g. '30S ribosomal protein S8').")
        gene_category: str | None = Field(
            default=None,
            description="Functional category (e.g. 'Translation').")
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4').")
        # DM identity (2)
        derived_metric_id: str = Field(
            description="Unique parent-DM id.")
        name: str = Field(description="DM human label.")
        # Gate echoes (3) — sourced from parent DM, coerced to Python bool
        value_kind: Literal["numeric"] = Field(
            description="Always 'numeric' for this tool; kept for cross-tool "
                        "row-shape consistency with `gene_derived_metrics`.")
        rankable: bool = Field(
            description="Echoed from parent DM; True iff "
                        "`rank_by_metric`/`metric_percentile`/`metric_bucket` "
                        "carry data.")
        has_p_value: bool = Field(
            description="Echoed from parent DM; True iff "
                        "`adjusted_p_value`/`significant` carry data (none "
                        "in current KG).")
        # Numeric value (4)
        value: float = Field(description="Measurement value.")
        rank_by_metric: int | None = Field(
            default=None,
            description="Rank by value (1=highest). Populated only when "
                        "rankable=True.")
        metric_percentile: float | None = Field(
            default=None,
            description="Percentile (0-100). Same gate as rank_by_metric.")
        metric_bucket: str | None = Field(
            default=None,
            description="Bucket label (top_decile / top_quartile / mid / "
                        "low). Same gate.")
        # Pydantic-only forward-compat (2; not in current Cypher RETURN)
        adjusted_p_value: float | None = Field(
            default=None,
            description="BH-adjusted p-value. Populated only when "
                        "has_p_value=True. None in current KG.")
        significant: bool | None = Field(
            default=None,
            description="Significance flag. Same gate as adjusted_p_value.")
        # ── Verbose adds (default None / [] when verbose=False) ─────────
        metric_type: str | None = Field(
            default=None,
            description="Category tag. Verbose only.")
        field_description: str | None = Field(
            default=None,
            description="Detailed explanation of what this DM measures. "
                        "Verbose only.")
        unit: str | None = Field(
            default=None,
            description="Measurement unit. Verbose only.")
        compartment: str | None = Field(
            default=None,
            description="Sample compartment. Verbose only.")
        experiment_id: str | None = Field(
            default=None,
            description="Parent experiment id. Verbose only.")
        publication_doi: str | None = Field(
            default=None,
            description="Parent publication DOI. Verbose only.")
        treatment_type: list[str] = Field(
            default_factory=list,
            description="Treatment type(s). Verbose only.")
        background_factors: list[str] = Field(
            default_factory=list,
            description="Background factor(s). Verbose only.")
        treatment: str | None = Field(
            default=None,
            description="Treatment description in plain language. Verbose only.")
        light_condition: str | None = Field(
            default=None,
            description="Light regime. Verbose only.")
        experimental_context: str | None = Field(
            default=None,
            description="Longer experimental setup description. Verbose only.")
        gene_function_description: str | None = Field(
            default=None,
            description="Gene functional description (gene-level). Verbose only.")
        gene_summary: str | None = Field(
            default=None,
            description="Gene summary text (gene-level). Verbose only.")
        p_value: float | None = Field(
            default=None,
            description="Raw p-value; gated on has_p_value=True. Verbose "
                        "only. None in current KG.")

    # ── genes_by_numeric_metric envelope ───────────────────────────────

    class GenesByNumericMetricResponse(BaseModel):
        total_matching: int = Field(
            description="Rows after all filters + gate exclusion.")
        total_derived_metrics: int = Field(
            description="Distinct DMs contributing rows.")
        total_genes: int = Field(description="Distinct genes in results.")
        by_organism: list[GenesByNumericMetricOrganismBreakdown] = Field(
            default_factory=list, description="Rows per organism.")
        by_compartment: list[GenesByNumericMetricCompartmentBreakdown] = Field(
            default_factory=list, description="Rows per compartment.")
        by_publication: list[GenesByNumericMetricPublicationBreakdown] = Field(
            default_factory=list, description="Rows per publication.")
        by_experiment: list[GenesByNumericMetricExperimentBreakdown] = Field(
            default_factory=list, description="Rows per experiment.")
        by_metric: list[GenesByNumericMetricBreakdown] = Field(
            default_factory=list,
            description="Per-DM rollup: filtered-slice value distribution + "
                        "full-DM context. Sorted by count desc.")
        top_categories: list[GenesByNumericMetricCategoryBreakdown] = Field(
            default_factory=list,
            description="Top 5 gene categories by count.")
        genes_per_metric_max: int = Field(
            default=0, description="Largest per-DM gene count.")
        genes_per_metric_median: float = Field(
            default=0.0, description="Median per-DM gene count.")
        not_found_ids: list[str] = Field(
            default_factory=list,
            description="`derived_metric_ids` inputs not present in KG.")
        not_matched_ids: list[str] = Field(
            default_factory=list,
            description="`derived_metric_ids` in KG but produced 0 rows after "
                        "edge-level filters (excludes gate-excluded DMs).")
        not_found_metric_types: list[str] = Field(
            default_factory=list,
            description="`metric_types` inputs that match no DM after scoping.")
        not_matched_metric_types: list[str] = Field(
            default_factory=list,
            description="`metric_types` whose DMs produced 0 rows.")
        not_matched_organism: str | None = Field(
            default=None,
            description="`organism` arg that matched no surviving DM.")
        excluded_derived_metrics: list[ExcludedDerivedMetric] = Field(
            default_factory=list,
            description="DMs dropped by rankable / has_p_value gate. Always "
                        "present (empty list when no exclusions).")
        warnings: list[str] = Field(
            default_factory=list,
            description="Human-readable summary of excluded_derived_metrics.")
        returned: int = Field(description="Length of results list.")
        offset: int = Field(default=0, description="Pagination offset used.")
        truncated: bool = Field(
            description="True when total_matching > offset + returned.")
        results: list[GenesByNumericMetricResult] = Field(
            default_factory=list,
            description="One row per gene × DM. Empty when summary=True.")

    @mcp.tool(
        tags={"derived-metrics", "genes", "drill-down", "numeric"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def genes_by_numeric_metric(
        ctx: Context,
        # ── Selection (exactly one required, mutually exclusive) ────────
        derived_metric_ids: Annotated[list[str] | None, Field(
            description="DerivedMetric node IDs to drill into. Use when the "
                        "same `metric_type` appears across publications / "
                        "organisms and you need to pin one. Discover IDs via "
                        "`list_derived_metrics`. Mutually exclusive with "
                        "`metric_types`.",
        )] = None,
        metric_types: Annotated[list[str] | None, Field(
            description="Metric-type tags (e.g. ['damping_ratio', "
                        "'diel_amplitude_protein_log2']). Unions every DM "
                        "carrying that tag, then narrows by scoping filters. "
                        "Same tag can appear across organisms (e.g. "
                        "'cell_abundance_biovolume_normalized' is on both "
                        "MIT9312 and MIT9313 today). Mutually exclusive with "
                        "`derived_metric_ids`.",
        )] = None,
        # ── DM-scoping filters (intersected with selection) ─────────────
        organism: Annotated[str | None, Field(
            description="Organism to scope the DM set to. Accepts short strain "
                        "code ('MED4', 'NATL2A', 'MIT9312') or full name. "
                        "Case-insensitive substring match. Single-organism is "
                        "**not** enforced — omit to drill across all "
                        "organisms a metric_type spans.",
        )] = None,
        locus_tags: Annotated[list[str] | None, Field(
            description="Restrict drill-down to a specific gene set (e.g. DE "
                        "hits from `differential_expression_by_gene`). Filter "
                        "on `g.locus_tag IN $locus_tags` post-MATCH. Genes "
                        "with no edge for the selected DM produce no row "
                        "(silent — surfaced via `total_genes` shortfall).",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Scope to DMs from one or more experiments.",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Scope to DMs from one or more publications.",
        )] = None,
        compartment: Annotated[str | None, Field(
            description="Sample compartment ('whole_cell', 'vesicle', "
                        "'exoproteome', 'spent_medium', 'lysate'). Exact match.",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Treatment type(s) (e.g. ['diel', 'compartment']). "
                        "ANY-overlap. Case-insensitive.",
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Background factor(s) (e.g. ['axenic', 'light']). "
                        "ANY-overlap. Case-insensitive.",
        )] = None,
        growth_phases: Annotated[list[str] | None, Field(
            description="Growth phase(s). ANY-overlap. Case-insensitive.",
        )] = None,
        # ── Edge-level filters: always-available (any numeric DM) ───────
        min_value: Annotated[float | None, Field(
            description="Lower bound on `r.value`. Always applicable — no gate. "
                        "Use for raw-threshold queries on non-rankable DMs "
                        "(e.g. mascot probability >= 99).",
        )] = None,
        max_value: Annotated[float | None, Field(
            description="Upper bound on `r.value`. Always applicable.",
        )] = None,
        # ── Edge-level filters: RANKABLE-GATED ──────────────────────────
        min_percentile: Annotated[float | None, Field(
            description="Lower bound on `r.metric_percentile` (0-100). "
                        "**Rankable-gated** — raises if every selected DM has "
                        "`rankable=False`. Soft-excludes non-rankable DMs from "
                        "mixed input, surfaced in `excluded_derived_metrics`.",
            ge=0, le=100,
        )] = None,
        max_percentile: Annotated[float | None, Field(
            description="Upper bound on `r.metric_percentile`. "
                        "**Rankable-gated.**",
            ge=0, le=100,
        )] = None,
        bucket: Annotated[list[str] | None, Field(
            description="Bucket label(s) — subset of "
                        "{'top_decile','top_quartile','mid','low'}. "
                        "**Rankable-gated.** Today's KG buckets correspond to "
                        "decile / quartile splits computed at import time per "
                        "DM.",
        )] = None,
        max_rank: Annotated[int | None, Field(
            description="Cap on `r.rank_by_metric` (1 = highest). Use for "
                        "top-N drill-down. **Rankable-gated.**",
            ge=1,
        )] = None,
        # ── Edge-level filters: HAS_P_VALUE-GATED ───────────────────────
        significant_only: Annotated[bool, Field(
            description="Filter to `r.significant=true`. **has_p_value-gated** "
                        "— raises against today's KG (no DM has p-values yet). "
                        "Forward-compat surface; check "
                        "`list_derived_metrics(has_p_value=True)` before using.",
        )] = False,
        max_adjusted_p_value: Annotated[float | None, Field(
            description="Upper bound on `r.adjusted_p_value`. "
                        "**has_p_value-gated**.",
            ge=0, le=1,
        )] = None,
        # ── Result-size controls ────────────────────────────────────────
        summary: Annotated[bool, Field(
            description="Return summary fields only (counts, breakdowns, "
                        "by_metric, diagnostics). Sugar for limit=0; "
                        "results=[].",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include heavy text fields per row: "
                        "gene_function_description, gene_summary, plus DM "
                        "context (metric_type, field_description, unit, "
                        "compartment, experiment_id, publication_doi, "
                        "treatment_type, background_factors, treatment, "
                        "light_condition, experimental_context). p_value (raw) "
                        "is reserved for future has_p_value DMs.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max rows to return. Paginate with `offset`. Use "
                        "`summary=True` for summary-only (sets limit=0).",
            ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Pagination offset (starting row, 0-indexed).",
            ge=0,
        )] = 0,
    ) -> GenesByNumericMetricResponse:
        """Pass `derived_metric_ids` XOR `metric_types` (one required); rankable-gated filters (`bucket`, `min/max_percentile`, `max_rank`) raise if every selected DM has `rankable=False` and soft-exclude on mixed input — inspect `list_derived_metrics(value_kind='numeric', rankable=True)` first to see which DMs support which filters.

        Numeric DM drill-down — one row per gene × DM. `r.value` (float) is
        always returned; `rank_by_metric` / `metric_percentile` /
        `metric_bucket` are populated only on rows from rankable DMs (null
        otherwise — same shape as `gene_derived_metrics`). Cross-organism by
        design; envelope `by_organism` and per-row `organism_name` make
        cross-strain rows self-describing. The `by_metric` envelope rollup
        pairs filtered-slice value distribution with full-DM distribution
        (precomputed) so callers can read "your top-decile slice 12.2-25.3
        out of full DM range 0-28" directly.

        `excluded_derived_metrics` + `warnings` envelope keys are the
        primary diagnostic when a real DM produces zero rows; check these
        before assuming the result is empty for biological reasons.
        """
        selection_size = (
            len(derived_metric_ids) if derived_metric_ids is not None
            else (len(metric_types) if metric_types is not None else 0)
        )
        gate_filters_present = [
            name for name, val in (
                ("min_percentile", min_percentile),
                ("max_percentile", max_percentile),
                ("bucket", bucket),
                ("max_rank", max_rank),
                ("significant_only", significant_only or None),
                ("max_adjusted_p_value", max_adjusted_p_value),
            ) if val is not None
        ]
        await ctx.info(
            f"genes_by_numeric_metric selection_size={selection_size} "
            f"gate_filters={gate_filters_present}"
        )
        try:
            conn = _conn(ctx)
            data = api.genes_by_numeric_metric(
                derived_metric_ids=derived_metric_ids,
                metric_types=metric_types,
                organism=organism,
                locus_tags=locus_tags,
                experiment_ids=experiment_ids,
                publication_doi=publication_doi,
                compartment=compartment,
                treatment_type=treatment_type,
                background_factors=background_factors,
                growth_phases=growth_phases,
                min_value=min_value,
                max_value=max_value,
                min_percentile=min_percentile,
                max_percentile=max_percentile,
                bucket=bucket,
                max_rank=max_rank,
                significant_only=significant_only,
                max_adjusted_p_value=max_adjusted_p_value,
                summary=summary,
                verbose=verbose,
                limit=limit,
                offset=offset,
                conn=conn,
            )
        except ValueError as e:
            await ctx.warning(f"genes_by_numeric_metric error: {e}")
            raise ToolError(str(e)) from e
        except Exception as e:
            await ctx.error(f"genes_by_numeric_metric unexpected error: {e}")
            raise ToolError(f"Error in genes_by_numeric_metric: {e}")

        if data["excluded_derived_metrics"]:
            await ctx.warning(
                f"{len(data['excluded_derived_metrics'])} DM(s) excluded; "
                "see `excluded_derived_metrics` in envelope"
            )

        # Build response in NEW LOCAL VARIABLES — don't mutate `data`.
        by_organism = [GenesByNumericMetricOrganismBreakdown(**x)
                       for x in data["by_organism"]]
        by_compartment = [GenesByNumericMetricCompartmentBreakdown(**x)
                          for x in data["by_compartment"]]
        by_publication = [GenesByNumericMetricPublicationBreakdown(**x)
                          for x in data["by_publication"]]
        by_experiment = [GenesByNumericMetricExperimentBreakdown(**x)
                         for x in data["by_experiment"]]
        by_metric = [GenesByNumericMetricBreakdown(**x)
                     for x in data["by_metric"]]
        top_categories = [GenesByNumericMetricCategoryBreakdown(**x)
                          for x in data["top_categories"]]
        excluded_derived_metrics = [ExcludedDerivedMetric(**x)
                                    for x in data["excluded_derived_metrics"]]
        results = [GenesByNumericMetricResult(**r) for r in data["results"]]

        response = GenesByNumericMetricResponse(
            total_matching=data["total_matching"],
            total_derived_metrics=data["total_derived_metrics"],
            total_genes=data["total_genes"],
            by_organism=by_organism,
            by_compartment=by_compartment,
            by_publication=by_publication,
            by_experiment=by_experiment,
            by_metric=by_metric,
            top_categories=top_categories,
            genes_per_metric_max=data["genes_per_metric_max"],
            genes_per_metric_median=data["genes_per_metric_median"],
            not_found_ids=data["not_found_ids"],
            not_matched_ids=data["not_matched_ids"],
            not_found_metric_types=data["not_found_metric_types"],
            not_matched_metric_types=data["not_matched_metric_types"],
            not_matched_organism=data.get("not_matched_organism"),
            excluded_derived_metrics=excluded_derived_metrics,
            warnings=data["warnings"],
            returned=data["returned"],
            offset=data.get("offset", 0),
            truncated=data["truncated"],
            results=results,
        )
        await ctx.info(
            f"Returning {response.returned} of {response.total_matching} "
            f"gene×DM rows"
        )
        return response

    # ── genes_by_boolean_metric Pydantic models ────────────────────────

    class GenesByBooleanMetricValueBreakdown(BaseModel):
        value: str = Field(
            description="Edge value: 'true' or 'false' (string-typed bool).")
        count: int = Field(description="Rows with this value.")

    class GenesByBooleanMetricBreakdown(BaseModel):
        """Per-DM rollup: filtered-slice + full-DM positive/negative tallies."""
        derived_metric_id: str = Field(description="Unique DM id.")
        name: str = Field(description="DM human label.")
        metric_type: str = Field(description="Category tag.")
        value_kind: Literal["boolean"] = Field(
            description="Always 'boolean' in this tool.")
        count: int = Field(
            description="Rows contributed by this DM after filters.")
        # Filtered slice (query-time)
        true_count: int = Field(
            description="Rows in filtered slice with r.value='true'.")
        false_count: int = Field(
            description="Rows in filtered slice with r.value='false' "
                        "(always 0 today — positive-only KG storage).")
        # Full DM (precomputed)
        dm_total_gene_count: int = Field(
            description="Full-DM total gene count (precomputed "
                        "`dm.total_gene_count`).")
        dm_true_count: int = Field(
            description="Full-DM positive tally (precomputed "
                        "`dm.flag_true_count`).")
        dm_false_count: int = Field(
            description="Full-DM negative tally (precomputed "
                        "`dm.flag_false_count` — always 0 today).")

    class GenesByBooleanMetricResult(BaseModel):
        # Identity / routing (5)
        locus_tag: str = Field(
            description="Gene locus tag (e.g. 'PMM0090').")
        gene_name: str | None = Field(
            default=None, description="Gene symbol; null when KG has none.")
        product: str | None = Field(
            default=None, description="Gene product.")
        gene_category: str | None = Field(
            default=None, description="Coarse functional category.")
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4').")
        # DM identity (2)
        derived_metric_id: str = Field(description="Unique parent-DM id.")
        name: str = Field(description="DM human label.")
        # Gate echoes (3) — kept for cross-tool row-shape consistency
        value_kind: Literal["boolean"] = Field(
            description="Always 'boolean' for this tool; kept for cross-tool "
                        "row-shape consistency with `genes_by_numeric_metric`.")
        rankable: bool = Field(
            description="DM-level rankable flag (always False today for "
                        "boolean DMs).")
        has_p_value: bool = Field(
            description="DM-level p-value flag (always False today for "
                        "boolean DMs).")
        # Edge value (1)
        value: str = Field(
            description="'true' or 'false' (string-typed bool — see KG-spec "
                        "BioCypher constraint).")
        # ── Verbose adds (default None) ─────────────────────────────────
        metric_type: str | None = Field(
            default=None, description="Category tag. Verbose only.")
        field_description: str | None = Field(
            default=None,
            description="Detailed explanation of what this DM measures. "
                        "Verbose only.")
        unit: str | None = Field(
            default=None,
            description="Measurement unit (typically null for boolean DMs). "
                        "Verbose only.")
        compartment: str | None = Field(
            default=None,
            description="Sample compartment. Verbose only.")
        experiment_id: str | None = Field(
            default=None, description="Parent experiment id. Verbose only.")
        publication_doi: str | None = Field(
            default=None, description="Parent publication DOI. Verbose only.")
        treatment_type: list[str] | None = Field(
            default=None,
            description="Treatment type(s). Verbose only.")
        background_factors: list[str] | None = Field(
            default=None,
            description="Background factor(s). Verbose only.")
        treatment: str | None = Field(
            default=None,
            description="Treatment description in plain language. Verbose only.")
        light_condition: str | None = Field(
            default=None, description="Light regime. Verbose only.")
        experimental_context: str | None = Field(
            default=None,
            description="Longer experimental setup description. Verbose only.")
        gene_function_description: str | None = Field(
            default=None,
            description="Gene functional description (gene-level). Verbose only.")
        gene_summary: str | None = Field(
            default=None,
            description="Gene summary text (gene-level). Verbose only.")

    class GenesByBooleanMetricResponse(BaseModel):
        total_matching: int = Field(
            description="Rows post-filter (gene × DM pairs).")
        total_derived_metrics: int = Field(
            description="Distinct DMs contributing rows.")
        total_genes: int = Field(description="Distinct genes in results.")
        by_organism: list[GenesByNumericMetricOrganismBreakdown] = Field(
            default_factory=list, description="Rows per organism.")
        by_compartment: list[GenesByNumericMetricCompartmentBreakdown] = Field(
            default_factory=list, description="Rows per compartment.")
        by_publication: list[GenesByNumericMetricPublicationBreakdown] = Field(
            default_factory=list, description="Rows per publication.")
        by_experiment: list[GenesByNumericMetricExperimentBreakdown] = Field(
            default_factory=list, description="Rows per experiment.")
        by_value: list[GenesByBooleanMetricValueBreakdown] = Field(
            default_factory=list,
            description="Frequency rollup of `r.value` across surviving rows. "
                        "Today every row is 'true' (positive-only KG storage).")
        top_categories: list[GenesByNumericMetricCategoryBreakdown] = Field(
            default_factory=list, description="Top 5 gene categories by count.")
        by_metric: list[GenesByBooleanMetricBreakdown] = Field(
            default_factory=list,
            description="Per-DM rollup: filtered-slice true/false counts + "
                        "full-DM precomputed tallies. Sorted by count desc.")
        genes_per_metric_max: int = Field(
            default=0, description="Largest per-DM gene count.")
        genes_per_metric_median: float = Field(
            default=0.0, description="Median per-DM gene count.")
        not_found_ids: list[str] = Field(
            default_factory=list,
            description="`derived_metric_ids` inputs not present in KG (or "
                        "scoped out / wrong value_kind).")
        not_matched_ids: list[str] = Field(
            default_factory=list,
            description="`derived_metric_ids` in KG but produced 0 rows after "
                        "edge-level filters.")
        not_found_metric_types: list[str] = Field(
            default_factory=list,
            description="`metric_types` inputs that match no DM after scoping.")
        not_matched_metric_types: list[str] = Field(
            default_factory=list,
            description="`metric_types` whose DMs produced 0 rows.")
        not_matched_organism: str | None = Field(
            default=None,
            description="`organism` arg that matched no surviving DM.")
        excluded_derived_metrics: list[ExcludedDerivedMetric] = Field(
            default_factory=list,
            description="Always [] for boolean DMs (no rankable / has_p_value "
                        "gates). Kept for cross-tool envelope-shape "
                        "consistency.")
        warnings: list[str] = Field(
            default_factory=list,
            description="Always [] for boolean DMs. Kept for cross-tool "
                        "envelope-shape consistency.")
        returned: int = Field(description="Length of results list.")
        offset: int = Field(default=0, description="Pagination offset used.")
        truncated: bool = Field(
            description="True when total_matching > offset + returned.")
        results: list[GenesByBooleanMetricResult] = Field(
            default_factory=list,
            description="One row per gene × DM. Empty when summary=True.")

    @mcp.tool(
        tags={"derived_metric", "boolean", "drill_down"},
        annotations={"readOnlyHint": True},
    )
    async def genes_by_boolean_metric(
        ctx: Context,
        # ── Selection (exactly one required, mutually exclusive) ────────
        derived_metric_ids: Annotated[list[str] | None, Field(
            description="Boolean DerivedMetric node IDs. Use when the same "
                        "`metric_type` appears across organisms / publications "
                        "and you need to pin one. Discover IDs via "
                        "`list_derived_metrics(value_kind='boolean')`. "
                        "Mutually exclusive with `metric_types`. Wrong-kind "
                        "IDs (numeric / categorical) surface silently in "
                        "`not_found_ids`.",
        )] = None,
        metric_types: Annotated[list[str] | None, Field(
            description="Boolean metric-type tags (e.g. "
                        "['vesicle_proteome_member', "
                        "'periodic_in_coculture_LD']). Unions every DM "
                        "carrying that tag, then narrows by scoping filters. "
                        "Same tag can appear across organisms (e.g. "
                        "'vesicle_proteome_member' is on both MED4 + MIT9313). "
                        "Mutually exclusive with `derived_metric_ids`.",
        )] = None,
        # ── DM-scoping filters (intersected with selection) ─────────────
        organism: Annotated[str | None, Field(
            description="Organism to scope the DM set to. Accepts short "
                        "strain code ('MED4', 'NATL2A', 'MIT9313') or full "
                        "name. Case-insensitive substring match. "
                        "Single-organism is **not** enforced — omit to drill "
                        "across all organisms a metric_type spans.",
        )] = None,
        locus_tags: Annotated[list[str] | None, Field(
            description="Restrict drill-down to a specific gene set (e.g. DE "
                        "hits from `differential_expression_by_gene`). Filter "
                        "on `g.locus_tag IN $locus_tags` post-MATCH. Genes "
                        "with no edge for the selected DM produce no row.",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Scope to DMs from one or more experiments.",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Scope to DMs from one or more publications.",
        )] = None,
        compartment: Annotated[str | None, Field(
            description="Sample compartment ('whole_cell', 'vesicle', "
                        "'exoproteome', 'spent_medium', 'lysate'). Exact "
                        "match.",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Treatment type(s) (e.g. ['diel']). ANY-overlap. "
                        "Case-insensitive.",
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Background factor(s) (e.g. ['axenic', 'light']). "
                        "ANY-overlap. Case-insensitive.",
        )] = None,
        growth_phases: Annotated[list[str] | None, Field(
            description="Growth phase(s). ANY-overlap. Case-insensitive.",
        )] = None,
        # ── Edge-level filter (kind-specific) ───────────────────────────
        flag: Annotated[bool | None, Field(
            description="Filter on `r.value`: True keeps `'true'` edges, "
                        "False keeps `'false'` edges. Coerced to the "
                        "string-typed bool stored in the KG (BioCypher "
                        "constraint). **flag=False returns zero rows today** "
                        "— current KG stores only positive (true) edges; "
                        "inspect `by_metric[*].dm_false_count` (always 0 "
                        "today) before assuming a gene is 'not flagged'.",
        )] = None,
        # ── Result-size controls ────────────────────────────────────────
        summary: Annotated[bool, Field(
            description="Return summary fields only (counts, breakdowns, "
                        "by_metric, diagnostics). Sugar for limit=0; "
                        "results=[].",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include heavy text fields per row: "
                        "gene_function_description, gene_summary, plus DM "
                        "context (metric_type, field_description, unit, "
                        "compartment, experiment_id, publication_doi, "
                        "treatment_type, background_factors, treatment, "
                        "light_condition, experimental_context).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max rows to return. Paginate with `offset`. Use "
                        "`summary=True` for summary-only (sets limit=0).",
            ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Pagination offset (starting row, 0-indexed).",
            ge=0,
        )] = 0,
    ) -> GenesByBooleanMetricResponse:
        """Pass `derived_metric_ids` XOR `metric_types` (one required); wrong-kind IDs (numeric / categorical) surface silently in `not_found_ids` — inspect `list_derived_metrics(value_kind='boolean')` first to pick valid boolean DMs.

        Boolean DM drill-down — one row per gene × DM × edge value. `r.value`
        is the string-typed bool ('true' / 'false'). Cross-organism by
        design; envelope `by_organism` and per-row `organism_name` make
        cross-strain rows self-describing. The `by_metric` envelope rollup
        pairs filtered-slice true/false tallies with full-DM precomputed
        counts (`dm_true_count`, `dm_false_count`) so callers can read "32
        of 32 MED4 vesicle-proteome members" directly.

        **Positive-only storage gotcha:** every current boolean DM has
        `dm.flag_false_count=0`; `flag=False` returns zero rows today. The
        `by_metric[*].dm_false_count` echo makes this self-evident without
        a follow-up call.

        `excluded_derived_metrics` and `warnings` are always `[]` (no
        rankable / has_p_value gates apply to boolean DMs); kept as
        envelope keys for cross-tool shape consistency with
        `genes_by_numeric_metric`.
        """
        selection_size = (
            len(derived_metric_ids) if derived_metric_ids is not None
            else (len(metric_types) if metric_types is not None else 0)
        )
        await ctx.info(
            f"genes_by_boolean_metric selection_size={selection_size} "
            f"flag={flag}"
        )
        try:
            conn = _conn(ctx)
            data = api.genes_by_boolean_metric(
                derived_metric_ids=derived_metric_ids,
                metric_types=metric_types,
                organism=organism,
                locus_tags=locus_tags,
                experiment_ids=experiment_ids,
                publication_doi=publication_doi,
                compartment=compartment,
                treatment_type=treatment_type,
                background_factors=background_factors,
                growth_phases=growth_phases,
                flag=flag,
                summary=summary,
                verbose=verbose,
                limit=limit,
                offset=offset,
                conn=conn,
            )
        except ValueError as e:
            await ctx.warning(f"genes_by_boolean_metric error: {e}")
            raise ToolError(str(e)) from e
        except Exception as e:
            await ctx.error(f"genes_by_boolean_metric unexpected error: {e}")
            raise ToolError(f"Error in genes_by_boolean_metric: {e}")

        # Build response in NEW LOCAL VARIABLES — don't mutate `data`.
        by_organism = [GenesByNumericMetricOrganismBreakdown(**x)
                       for x in data["by_organism"]]
        by_compartment = [GenesByNumericMetricCompartmentBreakdown(**x)
                          for x in data["by_compartment"]]
        by_publication = [GenesByNumericMetricPublicationBreakdown(**x)
                          for x in data["by_publication"]]
        by_experiment = [GenesByNumericMetricExperimentBreakdown(**x)
                         for x in data["by_experiment"]]
        by_value = [GenesByBooleanMetricValueBreakdown(**x)
                    for x in data["by_value"]]
        top_categories = [GenesByNumericMetricCategoryBreakdown(**x)
                          for x in data["top_categories"]]
        by_metric = [GenesByBooleanMetricBreakdown(**x)
                     for x in data["by_metric"]]
        excluded_derived_metrics = [ExcludedDerivedMetric(**x)
                                    for x in data["excluded_derived_metrics"]]
        results = [GenesByBooleanMetricResult(**r) for r in data["results"]]

        response = GenesByBooleanMetricResponse(
            total_matching=data["total_matching"],
            total_derived_metrics=data["total_derived_metrics"],
            total_genes=data["total_genes"],
            by_organism=by_organism,
            by_compartment=by_compartment,
            by_publication=by_publication,
            by_experiment=by_experiment,
            by_value=by_value,
            top_categories=top_categories,
            by_metric=by_metric,
            genes_per_metric_max=data["genes_per_metric_max"],
            genes_per_metric_median=data["genes_per_metric_median"],
            not_found_ids=data["not_found_ids"],
            not_matched_ids=data["not_matched_ids"],
            not_found_metric_types=data["not_found_metric_types"],
            not_matched_metric_types=data["not_matched_metric_types"],
            not_matched_organism=data.get("not_matched_organism"),
            excluded_derived_metrics=excluded_derived_metrics,
            warnings=data["warnings"],
            returned=data["returned"],
            offset=data.get("offset", 0),
            truncated=data["truncated"],
            results=results,
        )
        await ctx.info(
            f"Returning {response.returned} of {response.total_matching} "
            f"gene×DM rows"
        )
        return response

    # ── genes_by_categorical_metric Pydantic models ────────────────────

    class GenesByCategoricalMetricCategoryFreq(BaseModel):
        category: str = Field(description="Category label.")
        count: int = Field(description="Rows with this category.")

    class GenesByCategoricalMetricBreakdown(BaseModel):
        """Per-DM rollup: filtered-slice category histogram + full-DM context."""
        derived_metric_id: str = Field(description="Unique DM id.")
        name: str = Field(description="DM human label.")
        metric_type: str = Field(description="Category tag.")
        value_kind: Literal["categorical"] = Field(
            description="Always 'categorical' in this tool.")
        count: int = Field(
            description="Rows contributed by this DM after filters.")
        # Filtered slice (query-time)
        by_category: list[GenesByCategoricalMetricCategoryFreq] = Field(
            default_factory=list,
            description="Filtered-slice per-DM frequency, computed via "
                        "`apoc.coll.frequencies` on filtered rows.")
        allowed_categories: list[str] = Field(
            default_factory=list,
            description="Schema-declared full set (`dm.allowed_categories`); "
                        "may be a superset of observed categories.")
        # Full DM (precomputed)
        dm_total_gene_count: int = Field(
            description="Full-DM total gene count (precomputed "
                        "`dm.total_gene_count`).")
        dm_by_category: list[GenesByCategoricalMetricCategoryFreq] = Field(
            default_factory=list,
            description="Full-DM histogram, zip of `dm.category_labels` + "
                        "`dm.category_counts`. Includes only observed "
                        "categories (may be a strict subset of "
                        "`allowed_categories`).")

    class GenesByCategoricalMetricResult(BaseModel):
        # Identity / routing (5)
        locus_tag: str = Field(
            description="Gene locus tag (e.g. 'PMM0097').")
        gene_name: str | None = Field(
            default=None, description="Gene symbol; null when KG has none.")
        product: str | None = Field(
            default=None, description="Gene product.")
        gene_category: str | None = Field(
            default=None, description="Coarse functional category.")
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4').")
        # DM identity (2)
        derived_metric_id: str = Field(description="Unique parent-DM id.")
        name: str = Field(description="DM human label.")
        # Gate echoes (3) — kept for cross-tool row-shape consistency
        value_kind: Literal["categorical"] = Field(
            description="Always 'categorical' for this tool; kept for "
                        "cross-tool row-shape consistency with "
                        "`genes_by_numeric_metric`.")
        rankable: bool = Field(
            description="DM-level rankable flag (always False today for "
                        "categorical DMs).")
        has_p_value: bool = Field(
            description="DM-level p-value flag (always False today for "
                        "categorical DMs).")
        # Edge value (1)
        value: str = Field(
            description="Category label (one of the parent DM's "
                        "`allowed_categories`).")
        # ── Verbose adds (default None) ─────────────────────────────────
        metric_type: str | None = Field(
            default=None, description="Category tag. Verbose only.")
        field_description: str | None = Field(
            default=None,
            description="Detailed explanation of what this DM measures. "
                        "Verbose only.")
        unit: str | None = Field(
            default=None,
            description="Measurement unit (typically null for categorical "
                        "DMs). Verbose only.")
        compartment: str | None = Field(
            default=None, description="Sample compartment. Verbose only.")
        experiment_id: str | None = Field(
            default=None, description="Parent experiment id. Verbose only.")
        publication_doi: str | None = Field(
            default=None, description="Parent publication DOI. Verbose only.")
        treatment_type: list[str] | None = Field(
            default=None,
            description="Treatment type(s). Verbose only.")
        background_factors: list[str] | None = Field(
            default=None,
            description="Background factor(s). Verbose only.")
        treatment: str | None = Field(
            default=None,
            description="Treatment description in plain language. Verbose only.")
        light_condition: str | None = Field(
            default=None, description="Light regime. Verbose only.")
        experimental_context: str | None = Field(
            default=None,
            description="Longer experimental setup description. Verbose only.")
        gene_function_description: str | None = Field(
            default=None,
            description="Gene functional description (gene-level). Verbose only.")
        gene_summary: str | None = Field(
            default=None,
            description="Gene summary text (gene-level). Verbose only.")
        allowed_categories: list[str] | None = Field(
            default=None,
            description="Schema-declared full set for this row's parent DM. "
                        "Verbose only.")

    class GenesByCategoricalMetricResponse(BaseModel):
        total_matching: int = Field(
            description="Rows post-filter (gene × DM pairs).")
        total_derived_metrics: int = Field(
            description="Distinct DMs contributing rows.")
        total_genes: int = Field(description="Distinct genes in results.")
        by_organism: list[GenesByNumericMetricOrganismBreakdown] = Field(
            default_factory=list, description="Rows per organism.")
        by_compartment: list[GenesByNumericMetricCompartmentBreakdown] = Field(
            default_factory=list, description="Rows per compartment.")
        by_publication: list[GenesByNumericMetricPublicationBreakdown] = Field(
            default_factory=list, description="Rows per publication.")
        by_experiment: list[GenesByNumericMetricExperimentBreakdown] = Field(
            default_factory=list, description="Rows per experiment.")
        by_category: list[GenesByCategoricalMetricCategoryFreq] = Field(
            default_factory=list,
            description="Frequency rollup of `r.value` across surviving rows. "
                        "Cross-DM unioned — a category present in two DMs sums.")
        top_categories: list[GenesByNumericMetricCategoryBreakdown] = Field(
            default_factory=list, description="Top 5 gene categories by count.")
        by_metric: list[GenesByCategoricalMetricBreakdown] = Field(
            default_factory=list,
            description="Per-DM rollup: filtered-slice category histogram + "
                        "full-DM precomputed histogram. Sorted by count desc.")
        genes_per_metric_max: int = Field(
            default=0, description="Largest per-DM gene count.")
        genes_per_metric_median: float = Field(
            default=0.0, description="Median per-DM gene count.")
        not_found_ids: list[str] = Field(
            default_factory=list,
            description="`derived_metric_ids` inputs not present in KG (or "
                        "scoped out / wrong value_kind).")
        not_matched_ids: list[str] = Field(
            default_factory=list,
            description="`derived_metric_ids` in KG but produced 0 rows after "
                        "edge-level filters.")
        not_found_metric_types: list[str] = Field(
            default_factory=list,
            description="`metric_types` inputs that match no DM after scoping.")
        not_matched_metric_types: list[str] = Field(
            default_factory=list,
            description="`metric_types` whose DMs produced 0 rows.")
        not_matched_organism: str | None = Field(
            default=None,
            description="`organism` arg that matched no surviving DM.")
        excluded_derived_metrics: list[ExcludedDerivedMetric] = Field(
            default_factory=list,
            description="Always [] for categorical DMs (no rankable / "
                        "has_p_value gates). Kept for cross-tool envelope-shape "
                        "consistency.")
        warnings: list[str] = Field(
            default_factory=list,
            description="Always [] for categorical DMs. Kept for cross-tool "
                        "envelope-shape consistency.")
        returned: int = Field(description="Length of results list.")
        offset: int = Field(default=0, description="Pagination offset used.")
        truncated: bool = Field(
            description="True when total_matching > offset + returned.")
        results: list[GenesByCategoricalMetricResult] = Field(
            default_factory=list,
            description="One row per gene × DM. Empty when summary=True.")

    @mcp.tool(
        tags={"derived_metric", "categorical", "drill_down"},
        annotations={"readOnlyHint": True},
    )
    async def genes_by_categorical_metric(
        ctx: Context,
        # ── Selection (exactly one required, mutually exclusive) ────────
        derived_metric_ids: Annotated[list[str] | None, Field(
            description="Categorical DerivedMetric node IDs. Use when the "
                        "same `metric_type` appears across organisms / "
                        "publications and you need to pin one. Discover IDs "
                        "via `list_derived_metrics(value_kind='categorical')`."
                        " Mutually exclusive with `metric_types`. Wrong-kind "
                        "IDs (numeric / boolean) surface silently in "
                        "`not_found_ids`.",
        )] = None,
        metric_types: Annotated[list[str] | None, Field(
            description="Categorical metric-type tags (e.g. "
                        "['predicted_subcellular_localization', "
                        "'darkness_survival_class']). Unions every DM "
                        "carrying that tag, then narrows by scoping filters. "
                        "Same tag can appear across organisms (e.g. "
                        "'predicted_subcellular_localization' is on both "
                        "MED4 + MIT9313). Mutually exclusive with "
                        "`derived_metric_ids`.",
        )] = None,
        # ── DM-scoping filters (intersected with selection) ─────────────
        organism: Annotated[str | None, Field(
            description="Organism to scope the DM set to. Accepts short "
                        "strain code ('MED4', 'NATL2A', 'MIT9313') or full "
                        "name. Case-insensitive substring match. "
                        "Single-organism is **not** enforced — omit to drill "
                        "across all organisms a metric_type spans.",
        )] = None,
        locus_tags: Annotated[list[str] | None, Field(
            description="Restrict drill-down to a specific gene set (e.g. DE "
                        "hits from `differential_expression_by_gene`). Filter "
                        "on `g.locus_tag IN $locus_tags` post-MATCH. Genes "
                        "with no edge for the selected DM produce no row.",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Scope to DMs from one or more experiments.",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Scope to DMs from one or more publications.",
        )] = None,
        compartment: Annotated[str | None, Field(
            description="Sample compartment ('whole_cell', 'vesicle', "
                        "'exoproteome', 'spent_medium', 'lysate'). Exact "
                        "match.",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Treatment type(s). ANY-overlap. Case-insensitive.",
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Background factor(s). ANY-overlap. Case-insensitive.",
        )] = None,
        growth_phases: Annotated[list[str] | None, Field(
            description="Growth phase(s). ANY-overlap. Case-insensitive.",
        )] = None,
        # ── Edge-level filter (kind-specific) ───────────────────────────
        categories: Annotated[list[str] | None, Field(
            description="Filter on `r.value`: keep rows whose value is in "
                        "this set. Validated against the union of the "
                        "selected DMs' `allowed_categories` — unknown "
                        "values raise `ValueError` listing the allowed set. "
                        "E.g. ['Outer Membrane', 'Periplasmic'] for "
                        "`predicted_subcellular_localization`.",
        )] = None,
        # ── Result-size controls ────────────────────────────────────────
        summary: Annotated[bool, Field(
            description="Return summary fields only (counts, breakdowns, "
                        "by_metric, diagnostics). Sugar for limit=0; "
                        "results=[].",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include heavy text fields per row: "
                        "gene_function_description, gene_summary, "
                        "allowed_categories, plus DM context (metric_type, "
                        "field_description, unit, compartment, experiment_id, "
                        "publication_doi, treatment_type, background_factors, "
                        "treatment, light_condition, experimental_context).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max rows to return. Paginate with `offset`. Use "
                        "`summary=True` for summary-only (sets limit=0).",
            ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Pagination offset (starting row, 0-indexed).",
            ge=0,
        )] = 0,
    ) -> GenesByCategoricalMetricResponse:
        """Pass `derived_metric_ids` XOR `metric_types` (one required); `categories` must be a subset of the union of selected DMs' `allowed_categories` (raises with the allowed set listed otherwise) — inspect `list_derived_metrics(value_kind='categorical')` first to see each DM's allowed set.

        Categorical DM drill-down — one row per gene × DM × edge value.
        `r.value` is a category label. Cross-organism by design; envelope
        `by_organism` and per-row `organism_name` make cross-strain rows
        self-describing. The `by_metric` envelope rollup pairs filtered-slice
        category histogram (`by_category`) with full-DM precomputed
        histogram (`dm_by_category`) plus the schema-declared
        `allowed_categories` so callers can detect declared-but-unobserved
        categories without an extra call.

        Wrong-kind IDs (numeric / boolean) surface silently in
        `not_found_ids` — inspect `list_derived_metrics(value_kind='categorical')`
        first to pick valid categorical DMs.

        `excluded_derived_metrics` and `warnings` are always `[]` (no
        rankable / has_p_value gates apply to categorical DMs); kept as
        envelope keys for cross-tool shape consistency with
        `genes_by_numeric_metric`.
        """
        selection_size = (
            len(derived_metric_ids) if derived_metric_ids is not None
            else (len(metric_types) if metric_types is not None else 0)
        )
        await ctx.info(
            f"genes_by_categorical_metric selection_size={selection_size} "
            f"categories={categories}"
        )
        try:
            conn = _conn(ctx)
            data = api.genes_by_categorical_metric(
                derived_metric_ids=derived_metric_ids,
                metric_types=metric_types,
                organism=organism,
                locus_tags=locus_tags,
                experiment_ids=experiment_ids,
                publication_doi=publication_doi,
                compartment=compartment,
                treatment_type=treatment_type,
                background_factors=background_factors,
                growth_phases=growth_phases,
                categories=categories,
                summary=summary,
                verbose=verbose,
                limit=limit,
                offset=offset,
                conn=conn,
            )
        except ValueError as e:
            await ctx.warning(f"genes_by_categorical_metric error: {e}")
            raise ToolError(str(e)) from e
        except Exception as e:
            await ctx.error(
                f"genes_by_categorical_metric unexpected error: {e}")
            raise ToolError(f"Error in genes_by_categorical_metric: {e}")

        # Build response in NEW LOCAL VARIABLES — don't mutate `data`.
        by_organism = [GenesByNumericMetricOrganismBreakdown(**x)
                       for x in data["by_organism"]]
        by_compartment = [GenesByNumericMetricCompartmentBreakdown(**x)
                          for x in data["by_compartment"]]
        by_publication = [GenesByNumericMetricPublicationBreakdown(**x)
                          for x in data["by_publication"]]
        by_experiment = [GenesByNumericMetricExperimentBreakdown(**x)
                         for x in data["by_experiment"]]
        by_category = [GenesByCategoricalMetricCategoryFreq(**x)
                       for x in data["by_category"]]
        top_categories = [GenesByNumericMetricCategoryBreakdown(**x)
                          for x in data["top_categories"]]
        by_metric = [GenesByCategoricalMetricBreakdown(**x)
                     for x in data["by_metric"]]
        excluded_derived_metrics = [ExcludedDerivedMetric(**x)
                                    for x in data["excluded_derived_metrics"]]
        results = [GenesByCategoricalMetricResult(**r) for r in data["results"]]

        response = GenesByCategoricalMetricResponse(
            total_matching=data["total_matching"],
            total_derived_metrics=data["total_derived_metrics"],
            total_genes=data["total_genes"],
            by_organism=by_organism,
            by_compartment=by_compartment,
            by_publication=by_publication,
            by_experiment=by_experiment,
            by_category=by_category,
            top_categories=top_categories,
            by_metric=by_metric,
            genes_per_metric_max=data["genes_per_metric_max"],
            genes_per_metric_median=data["genes_per_metric_median"],
            not_found_ids=data["not_found_ids"],
            not_matched_ids=data["not_matched_ids"],
            not_found_metric_types=data["not_found_metric_types"],
            not_matched_metric_types=data["not_matched_metric_types"],
            not_matched_organism=data.get("not_matched_organism"),
            excluded_derived_metrics=excluded_derived_metrics,
            warnings=data["warnings"],
            returned=data["returned"],
            offset=data.get("offset", 0),
            truncated=data["truncated"],
            results=results,
        )
        await ctx.info(
            f"Returning {response.returned} of {response.total_matching} "
            f"gene×DM rows"
        )
        return response

    # --- list_metabolites ---

    @mcp.tool(
        tags={"metabolites", "chemistry", "discovery"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def list_metabolites(
        ctx: Context,
        search: Annotated[str | None, Field(
            description="Free-text search on metabolite name (Lucene syntax). "
            "Index covers Metabolite.name only — element/formula composition "
            "is filtered through `elements` (presence list), not search. "
            "E.g. 'glucose', 'phosphate AND amino'.",
        )] = None,
        metabolite_ids: Annotated[list[str] | None, Field(
            description="Restrict to specific metabolites by full prefixed ID "
            "(case-sensitive). E.g. ['kegg.compound:C00031', 'kegg.compound:C00002']. "
            "Combines with other filters via AND. `not_found.metabolite_ids` "
            "lists any IDs that don't exist in the KG.",
        )] = None,
        kegg_compound_ids: Annotated[list[str] | None, Field(
            description="Filter by raw KEGG C-numbers (e.g. ['C00031']). "
            "Convenience over `metabolite_ids` when working with KEGG-anchored "
            "data; the prefixed equivalent is `kegg.compound:C*`.",
        )] = None,
        chebi_ids: Annotated[list[str] | None, Field(
            description="Filter by raw ChEBI numeric IDs (e.g. ['4167', '15422']). "
            "90% of Metabolite nodes carry a `chebi_id`.",
        )] = None,
        hmdb_ids: Annotated[list[str] | None, Field(
            description="Filter by raw HMDB IDs (e.g. ['HMDB0000122']). "
            "47% coverage.",
        )] = None,
        mnxm_ids: Annotated[list[str] | None, Field(
            description="Filter by raw MetaNetX IDs (e.g. ['MNXM1364061']). "
            "100% coverage — every Metabolite has a `mnxm_id`.",
        )] = None,
        elements: Annotated[list[str] | None, Field(
            description="Element-presence filter (Hill-notation symbols). "
            "AND of presence — ['N', 'P'] matches metabolites containing BOTH. "
            "Replaces error-prone formula-substring matching. Empty/null "
            "formula metabolites (~10%) never match. E.g. ['N'] for "
            "nitrogen-containing metabolites (yields 1,563 today).",
        )] = None,
        mass_min: Annotated[float | None, Field(
            description="Minimum monoisotopic mass (Da). Excludes metabolites "
            "with null `mass` (~22%). E.g. 60.0.",
        )] = None,
        mass_max: Annotated[float | None, Field(
            description="Maximum monoisotopic mass (Da). E.g. 1000.0.",
        )] = None,
        organism_names: Annotated[list[str] | None, Field(
            description="Restrict to metabolites reachable by these organisms "
            "(case-insensitive on `preferred_name`). UNION semantics — a "
            "metabolite reached by ANY listed organism qualifies. Joined via "
            "`Organism_has_metabolite` (catalysis OR transport post-TCDB). "
            "E.g. ['Prochlorococcus MED4']. `not_found.organism_names` lists "
            "any unknown names.",
        )] = None,
        pathway_ids: Annotated[list[str] | None, Field(
            description="Filter by KEGG pathway membership (`KeggTerm.id`). "
            "E.g. ['kegg.pathway:ko00910'] for nitrogen metabolism. Joined via "
            "`Metabolite_in_pathway` (transport-extended post-TCDB; 395 distinct "
            "pathways are metabolite-reachable). `not_found.pathway_ids` lists "
            "any IDs that don't exist as a KeggTerm.",
        )] = None,
        evidence_sources: Annotated[
            list[Literal["metabolism", "transport", "metabolomics"]] | None,
            Field(
                description="Filter by evidence path. Set-membership ANY semantics "
                "— ['transport'] returns transport-only AND dual (1,097 today). "
                "Valid values: 'metabolism' (catalysis-reachable), 'transport' "
                "(TCDB-curated substrate). `'metabolomics'` is accepted as a "
                "filter value for forward-compat with the future metabolomics-DM "
                "spec; no row matches yet. Other values raise at the MCP "
                "boundary (Pydantic Literal validation).",
            ),
        ] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include heavy-text and structural-fingerprint fields "
            "(inchikey, smiles, mnxm_id, hmdb_id, pathway_names).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> ListMetabolitesResponse:
        """Browse and filter metabolites in the chemistry layer.

        **Direction-agnostic.** Joins through `Reaction_has_metabolite` and
        (post-TCDB) `Tcdb_family_transports_metabolite` are direction-agnostic —
        a metabolite that is *produced* and one that is *consumed* surface
        identically. KEGG equation order is arbitrary. To distinguish, layer
        transcriptional evidence (`differential_expression_by_gene`) and
        functional annotation (`gene_overview` Pfam/KO `*-synthase` vs
        `*-permease`).

        After this tool, drill in via:
        - genes_by_metabolite(metabolite_ids=[id], organism=...) — find the
          catalysts / transporters per organism (replaces what would
          otherwise be an inline per-row top-N gene list here)
        - gene_metabolic_role(locus_tags=[...], organism=..., metabolite_elements=...) — gene-centric chemistry
        - genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...) — pathway → genes
        """
        await ctx.info(
            f"list_metabolites search={search} metabolite_ids={metabolite_ids} "
            f"elements={elements} organism_names={organism_names} "
            f"pathway_ids={pathway_ids} evidence_sources={evidence_sources} "
            f"summary={summary} verbose={verbose} limit={limit} offset={offset}"
        )
        try:
            conn = _conn(ctx)
            result = api.list_metabolites(
                search=search,
                metabolite_ids=metabolite_ids,
                kegg_compound_ids=kegg_compound_ids,
                chebi_ids=chebi_ids,
                hmdb_ids=hmdb_ids,
                mnxm_ids=mnxm_ids,
                elements=elements,
                mass_min=mass_min,
                mass_max=mass_max,
                organism_names=organism_names,
                pathway_ids=pathway_ids,
                evidence_sources=evidence_sources,
                summary=summary,
                verbose=verbose,
                limit=limit,
                offset=offset,
                conn=conn,
            )
            results = [MetaboliteResult(**r) for r in result["results"]]
            top_organisms = [MetTopOrganism(**b) for b in result["top_organisms"]]
            top_pathways = [MetTopPathway(**b) for b in result["top_pathways"]]
            by_evidence_source = [
                MetEvidenceSourceBreakdown(**b)
                for b in result["by_evidence_source"]
            ]
            xref_coverage = MetXrefCoverage(**result["xref_coverage"])
            mass_stats = MetMassStats(**result["mass_stats"])
            not_found = MetNotFound(**result["not_found"])
            response = ListMetabolitesResponse(
                total_entries=result["total_entries"],
                total_matching=result["total_matching"],
                top_organisms=top_organisms,
                top_pathways=top_pathways,
                by_evidence_source=by_evidence_source,
                xref_coverage=xref_coverage,
                mass_stats=mass_stats,
                score_max=result.get("score_max"),
                score_median=result.get("score_median"),
                returned=result["returned"],
                offset=result.get("offset", 0),
                truncated=result["truncated"],
                not_found=not_found,
                results=results,
            )
            await ctx.info(
                f"Returning {response.returned} of {response.total_matching} "
                f"matching metabolites ({response.total_entries} total in KG)"
            )
            return response
        except ValueError as e:
            await ctx.warning(f"list_metabolites error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"list_metabolites unexpected error: {e}")
            raise ToolError(f"Error in list_metabolites: {e}")
