"""MCP tool implementations for the Multiomics Knowledge Graph."""

import json
import logging
import re
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

import multiomics_explorer.api.functions as api
from multiomics_explorer.kg.connection import GraphConnection

logger = logging.getLogger(__name__)


def _conn(ctx: Context) -> GraphConnection:
    """Get the Neo4j connection from lifespan context."""
    return ctx.request_context.lifespan_context.conn


def _fmt(results: list[dict], limit: int | None = None) -> str:
    """Format query results as JSON string."""
    if limit is not None:
        results = results[:limit]
    return json.dumps(results, indent=2, default=str)


def _group_by_organism(results: list[dict]) -> dict:
    """Group gene results by organism_strain. Returns {organism: [genes], ...}."""
    grouped: dict[str, list[dict]] = {}
    for row in results:
        org = row.get("organism_strain", "Unknown")
        entry = {k: v for k, v in row.items() if k != "organism_strain"}
        grouped.setdefault(org, []).append(entry)
    return grouped


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
        annotations={"readOnlyHint": True},
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

    class ListFilterValuesResponse(BaseModel):
        filter_type: str = Field(description="The filter type returned (e.g. 'gene_category')")
        total_entries: int = Field(description="Total distinct values for this filter (e.g. 26)")
        returned: int = Field(description="Number of results returned (e.g. 26)")
        truncated: bool = Field(description="True if total_entries > returned")
        results: list[FilterValueResult] = Field(default_factory=list)

    @mcp.tool(
        tags={"filters", "discovery"},
        annotations={"readOnlyHint": True},
    )
    async def list_filter_values(
        ctx: Context,
        filter_type: Annotated[Literal["gene_category"], Field(
            description="Which filter's valid values to return. "
            "'gene_category': values for the category filter in genes_by_function.",
        )] = "gene_category",
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
        genus: str | None = Field(default=None, description="Genus (e.g. 'Prochlorococcus', 'Alteromonas')")
        species: str | None = Field(default=None, description="Binomial species name (e.g. 'Prochlorococcus marinus')")
        strain: str | None = Field(default=None, description="Strain identifier (e.g. 'MED4', 'EZ55')")
        clade: str | None = Field(default=None, description="Ecotype clade, Prochlorococcus-specific (e.g. 'HLI', 'LLIV')")
        ncbi_taxon_id: int | None = Field(default=None, description="NCBI Taxonomy ID for cross-referencing external databases (e.g. 59919)")
        gene_count: int = Field(description="Number of genes in the KG for this organism (e.g. 1976)")
        publication_count: int = Field(description="Number of publications studying this organism (e.g. 11)")
        experiment_count: int = Field(description="Total experiments across all publications (e.g. 46)")
        treatment_types: list[str] = Field(default_factory=list, description="Distinct treatment types studied (e.g. ['coculture', 'light_stress', 'nitrogen_stress'])")
        omics_types: list[str] = Field(default_factory=list, description="Distinct omics types available (e.g. ['RNASEQ', 'PROTEOMICS'])")
        # verbose-only fields
        family: str | None = Field(default=None, description="Taxonomic family (e.g. 'Prochlorococcaceae')")
        order: str | None = Field(default=None, description="Taxonomic order (e.g. 'Synechococcales')")
        tax_class: str | None = Field(default=None, description="Taxonomic class (e.g. 'Cyanophyceae')")
        phylum: str | None = Field(default=None, description="Taxonomic phylum (e.g. 'Cyanobacteriota')")
        kingdom: str | None = Field(default=None, description="Taxonomic kingdom (e.g. 'Bacillati')")
        superkingdom: str | None = Field(default=None, description="Taxonomic superkingdom (e.g. 'Bacteria')")
        lineage: str | None = Field(default=None, description="Full NCBI taxonomy lineage string (e.g. 'cellular organisms; Bacteria; ...; Prochlorococcus marinus')")

    class ListOrganismsResponse(BaseModel):
        total_entries: int = Field(description="Total organisms in the KG")
        returned: int = Field(description="Number of results returned")
        truncated: bool = Field(description="True if results were truncated by limit")
        results: list[OrganismResult]

    @mcp.tool(
        tags={"organisms", "discovery"},
        annotations={"readOnlyHint": True},
    )
    async def list_organisms(
        ctx: Context,
        verbose: Annotated[bool, Field(
            description="Include full taxonomy hierarchy "
            "(family, order, class, phylum, kingdom, superkingdom, lineage).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
    ) -> ListOrganismsResponse:
        """List all organisms with sequenced genomes in the knowledge graph.

        Returns taxonomy, gene counts, and publication counts for each organism.
        Use the returned organism names as filter values in genes_by_function,
        resolve_gene, genes_by_ontology, list_publications, etc. The organism
        filter uses partial matching — "MED4", "Prochlorococcus MED4", and
        "Prochlorococcus" all work.
        """
        await ctx.info(f"list_organisms verbose={verbose} limit={limit}")
        try:
            conn = _conn(ctx)
            result = api.list_organisms(verbose=verbose, limit=limit, conn=conn)
            organisms = [OrganismResult(**r) for r in result["results"]]
            response = ListOrganismsResponse(
                total_entries=result["total_entries"],
                returned=result["returned"],
                truncated=result["truncated"],
                results=organisms,
            )
            await ctx.info(f"Returning {response.returned} of {response.total_entries} organisms")
            return response
        except Exception as e:
            await ctx.error(f"list_organisms unexpected error: {e}")
            raise ToolError(f"Error in list_organisms: {e}")

    class GeneMatch(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        gene_name: str | None = Field(default=None, description="Gene name (e.g. 'dnaN')")
        product: str | None = Field(default=None, description="Gene product (e.g. 'DNA polymerase III, beta subunit')")
        organism_strain: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")

    class ResolveOrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        gene_count: int = Field(description="Number of matching genes in this organism (e.g. 1)")

    class ResolveGeneResponse(BaseModel):
        total_matching: int = Field(description="Total genes matching identifier + organism filter (e.g. 3)")
        by_organism: list[ResolveOrganismBreakdown] = Field(description="Match counts per organism, sorted by count descending")
        returned: int = Field(description="Genes in this response (e.g. 3)")
        truncated: bool = Field(description="True if total_matching > returned")
        results: list[GeneMatch] = Field(description="Matching genes sorted by organism_strain, locus_tag")

    @mcp.tool(
        tags={"genes", "discovery"},
        annotations={"readOnlyHint": True},
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
    ) -> ResolveGeneResponse:
        """Resolve a gene identifier to matching genes in the knowledge graph.

        Matching is case-insensitive — 'pmm0001', 'PMM0001', and 'Pmm0001'
        all work. Use the returned locus_tags with gene_overview,
        get_gene_details, gene_homologs, or gene_ontology_terms. The organism
        filter uses case-insensitive partial matching — 'MED4' and
        'Prochlorococcus MED4' both work.
        """
        await ctx.info(f"resolve_gene identifier={identifier} organism={organism}")
        try:
            conn = _conn(ctx)
            result = api.resolve_gene(
                identifier, organism=organism, limit=limit, conn=conn,
            )
            genes = [GeneMatch(**r) for r in result["results"]]
            by_organism = [ResolveOrganismBreakdown(**b) for b in result["by_organism"]]
            return ResolveGeneResponse(
                total_matching=result["total_matching"],
                by_organism=by_organism,
                returned=result["returned"],
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
        organism: str = Field(description="Organism strain (e.g. 'Prochlorococcus MED4')")
        count: int = Field(description="Number of matching genes")

    class FunctionCategoryBreakdown(BaseModel):
        category: str = Field(description="Gene category (e.g. 'Photosynthesis')")
        count: int = Field(description="Number of matching genes")

    class GenesByFunctionResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        gene_name: str | None = Field(default=None, description="Gene name (e.g. 'dnaN')")
        product: str | None = Field(default=None, description="Gene product (e.g. 'DNA polymerase III subunit beta')")
        organism_strain: str = Field(description="Organism strain (e.g. 'Prochlorococcus MED4')")
        gene_category: str | None = Field(default=None, description="Functional category (e.g. 'Photosynthesis')")
        annotation_quality: int = Field(description="Annotation quality 0-3 (3=best)")
        score: float = Field(description="Fulltext relevance score")
        # verbose only
        function_description: str | None = Field(default=None, description="Functional description text")
        gene_summary: str | None = Field(default=None, description="Combined gene annotation summary")

    class GenesByFunctionResponse(BaseModel):
        total_entries: int = Field(description="Total genes matching search text (before filters)")
        total_matching: int = Field(description="Total genes matching search + all filters")
        by_organism: list[FunctionOrganismBreakdown] = Field(description="Gene counts per organism, sorted desc")
        by_category: list[FunctionCategoryBreakdown] = Field(description="Gene counts per category, sorted desc")
        score_max: float | None = Field(default=None, description="Highest relevance score (null if 0 matches)")
        score_median: float | None = Field(default=None, description="Median relevance score (null if 0 matches)")
        returned: int = Field(description="Number of results returned")
        truncated: bool = Field(description="True when total_matching > returned")
        results: list[GenesByFunctionResult] = Field(description="Gene results ranked by relevance")

    @mcp.tool(
        tags={"genes", "discovery"},
        annotations={"readOnlyHint": True},
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
                summary=summary, verbose=verbose, limit=limit, conn=conn,
            )
            by_organism = [FunctionOrganismBreakdown(**b) for b in data["by_organism"]]
            by_category = [FunctionCategoryBreakdown(**b) for b in data["by_category"]]
            results = [GenesByFunctionResult(**r) for r in data["results"]]
            response = GenesByFunctionResponse(
                total_entries=data["total_entries"],
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_category=by_category,
                score_max=data["score_max"],
                score_median=data["score_median"],
                returned=data["returned"],
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of {response.total_matching} "
                           f"matching genes ({response.total_entries} before filters)")
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
        organism_strain: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")
        annotation_types: list[str] = Field(default_factory=list, description="Ontology types with annotations (e.g. ['go_bp', 'ec', 'kegg'])")
        expression_edge_count: int = Field(default=0, description="Number of expression data points (e.g. 36)")
        significant_up_count: int = Field(default=0, description="Significant up-regulated DE observations (e.g. 3)")
        significant_down_count: int = Field(default=0, description="Significant down-regulated DE observations (e.g. 2)")
        closest_ortholog_group_size: int | None = Field(default=None, description="Size of tightest ortholog group (e.g. 9)")
        closest_ortholog_genera: list[str] | None = Field(default=None, description="Genera in tightest ortholog group (e.g. ['Prochlorococcus', 'Synechococcus'])")
        # verbose-only
        gene_summary: str | None = Field(default=None, description="Concatenated summary text (e.g. 'dnaN :: DNA polymerase III subunit beta :: Alternative locus ID')")
        function_description: str | None = Field(default=None, description="Curated functional description (e.g. 'Alternative locus ID')")
        all_identifiers: list[str] | None = Field(default=None, description="Cross-references: UniProt, CyanorakID, RefSeq, etc. (e.g. ['CK_Pro_MED4_00845', 'Q7V1M0', 'WP_011132479.1'])")

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
        returned: int = Field(description="Results in this response (0 when summary=true)")
        truncated: bool = Field(description="True if total_matching > returned")
        not_found: list[str] = Field(default_factory=list, description="Input locus_tags not in KG")
        results: list[GeneOverviewResult] = Field(default_factory=list, description="One row per gene")

    @mcp.tool(
        tags={"genes"},
        annotations={"readOnlyHint": True},
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
    ) -> GeneOverviewResponse:
        """Get an overview of genes: identity and data availability signals.

        Use after resolve_gene, genes_by_function, genes_by_ontology, or
        gene_homologs to understand what each gene is and what follow-up
        data exists.
        """
        await ctx.info(f"gene_overview locus_tags={locus_tags} summary={summary}")
        try:
            conn = _conn(ctx)
            data = api.gene_overview(
                locus_tags, summary=summary, verbose=verbose,
                limit=limit, conn=conn,
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
                returned=data["returned"],
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

    @mcp.tool()
    def get_gene_details(ctx: Context, gene_id: str) -> str:
        """Get all properties for a gene.

        This is a deep-dive tool — use gene_overview for the common case.
        Returns all Gene node properties including sparse fields
        (catalytic_activities, transporter_classification, cazy_ids, etc.).

        For organism taxonomy, use list_organisms. For homologs, use
        gene_homologs. For ontology annotations, use gene_ontology_terms.

        Args:
            gene_id: Gene locus_tag (e.g. "PMM0001", "sync_0001").
        """
        logger.info("get_gene_details gene_id=%s", gene_id)
        try:
            conn = _conn(ctx)
            result = api.get_gene_details(gene_id, conn=conn)
            if result is None:
                return f"Gene '{gene_id}' not found."
            return _fmt([result])
        except ValueError as e:
            logger.warning("get_gene_details error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("get_gene_details unexpected error: %s", e)
            return f"Error in get_gene_details: {e}"

    # --- gene_homologs ---

    class GeneHomologResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        organism_strain: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")
        group_id: str = Field(description="Ortholog group identifier (e.g. 'CK_00000364', 'COG0592@2')")
        consensus_gene_name: str | None = Field(default=None, description="Consensus gene name across group members (e.g. 'dnaN'). Often null.")
        consensus_product: str | None = Field(default=None, description="Consensus product across group members (e.g. 'DNA polymerase III, beta subunit')")
        taxonomic_level: str = Field(description="Taxonomic scope (e.g. 'curated', 'Prochloraceae', 'Bacteria')")
        source: str = Field(description="Source database (e.g. 'cyanorak', 'eggnog')")
        # verbose-only
        specificity_rank: int | None = Field(default=None, description="Group breadth: 0=curated, 1=family, 2=order, 3=domain (e.g. 0)")
        member_count: int | None = Field(default=None, description="Total genes in group (e.g. 9)")
        organism_count: int | None = Field(default=None, description="Distinct organisms in group (e.g. 9)")
        genera: list[str] | None = Field(default=None, description="Genera represented (e.g. ['Prochlorococcus', 'Synechococcus'])")
        has_cross_genus_members: str | None = Field(default=None, description="'cross_genus' or 'single_genus'")

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
        truncated: bool = Field(description="True if total_matching > returned")
        not_found: list[str] = Field(default_factory=list, description="Input locus_tags not in KG")
        no_groups: list[str] = Field(default_factory=list, description="Genes that exist but have zero matching ortholog groups")
        results: list[GeneHomologResult] = Field(default_factory=list, description="One row per gene × ortholog group")

    @mcp.tool(
        tags={"genes", "homology"},
        annotations={"readOnlyHint": True},
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
            description="Include group metadata: specificity_rank, member_count, "
            "organism_count, genera, has_cross_genus_members.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
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
                summary=summary, verbose=verbose, limit=limit, conn=conn,
            )
            by_organism = [HomologOrganismBreakdown(**b) for b in data["by_organism"]]
            by_source = [HomologSourceBreakdown(**b) for b in data["by_source"]]
            results = [GeneHomologResult(**r) for r in data["results"]]
            response = GeneHomologsResponse(
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_source=by_source,
                returned=data["returned"],
                truncated=data["truncated"],
                not_found=data["not_found"],
                no_groups=data["no_groups"],
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
        annotations={"readOnlyHint": True},
    )
    async def run_cypher(
        ctx: Context,
        query: Annotated[str, Field(
            description="Cypher query string. Write operations are blocked. "
            "A LIMIT clause is added automatically if absent.",
        )],
        limit: Annotated[int, Field(
            description="Max results (default 25, max 200).",
            ge=1,
            le=200,
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

    class SearchOntologyResponse(BaseModel):
        total_entries: int = Field(description="Total terms in this ontology (e.g. 847)")
        total_matching: int = Field(description="Terms matching the search (e.g. 31)")
        score_max: float | None = Field(default=None, description="Highest relevance score (null if 0 matches, e.g. 5.23)")
        score_median: float | None = Field(default=None, description="Median relevance score (null if 0 matches, e.g. 2.1)")
        returned: int = Field(description="Results in this response (0 when summary=true)")
        truncated: bool = Field(description="True if total_matching > returned")
        results: list[SearchOntologyResult] = Field(
            default_factory=list, description="One row per matching term",
        )

    @mcp.tool(
        tags={"ontology"},
        annotations={"readOnlyHint": True},
    )
    async def search_ontology(
        ctx: Context,
        search_text: Annotated[str, Field(
            description="Search query (Lucene syntax). "
            "E.g. 'replication', 'oxido*', 'transport AND membrane'.",
        )],
        ontology: Annotated[str, Field(
            description="Ontology to search: 'go_bp', 'go_mf', 'go_cc', "
            "'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam'.",
        )],
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
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
                limit=limit, conn=conn,
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
        gene_name: str | None = Field(default=None, description="Gene name (e.g. 'dnaN')")
        product: str | None = Field(default=None, description="Gene product (e.g. 'DNA polymerase III, beta subunit')")
        organism_strain: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")
        gene_category: str | None = Field(default=None, description="Functional category (e.g. 'Replication and repair')")
        # verbose only
        matched_terms: list[str] | None = Field(default=None, description="Input term IDs this gene was matched through (e.g. ['go:0006260'])")
        gene_summary: str | None = Field(default=None, description="Concatenated summary text")
        function_description: str | None = Field(default=None, description="Curated functional description")

    class OntologyOrganismBreakdown(BaseModel):
        organism: str = Field(description="Organism strain (e.g. 'Prochlorococcus MED4')")
        count: int = Field(description="Number of matching genes (e.g. 131)")

    class OntologyCategoryBreakdown(BaseModel):
        category: str = Field(description="Gene category (e.g. 'Replication and repair')")
        count: int = Field(description="Number of matching genes (e.g. 321)")

    class OntologyTermBreakdown(BaseModel):
        term_id: str = Field(description="Input term ID (e.g. 'go:0006260')")
        count: int = Field(description="Genes annotated to this term or descendants (e.g. 411)")

    class GenesByOntologyResponse(BaseModel):
        total_matching: int = Field(description="Distinct genes matching (e.g. 1742)")
        by_organism: list[OntologyOrganismBreakdown] = Field(description="Gene counts per organism, sorted desc")
        by_category: list[OntologyCategoryBreakdown] = Field(description="Gene counts per gene_category, sorted desc")
        by_term: list[OntologyTermBreakdown] = Field(description="Gene counts per input term, sorted desc (can overlap)")
        returned: int = Field(description="Results in this response (0 when summary=true)")
        truncated: bool = Field(description="True if total_matching > returned")
        results: list[GenesByOntologyResult] = Field(
            default_factory=list, description="One row per distinct gene",
        )

    @mcp.tool(
        tags={"genes", "ontology"},
        annotations={"readOnlyHint": True},
    )
    async def genes_by_ontology(
        ctx: Context,
        term_ids: Annotated[list[str], Field(
            description="Ontology term IDs (from search_ontology). "
            "E.g. ['go:0006260', 'go:0006412'].",
        )],
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "kegg", "ec",
            "cog_category", "cyanorak_role", "tigr_role", "pfam",
        ], Field(
            description="Ontology the term IDs belong to.",
        )],
        organism: Annotated[str | None, Field(
            description="Filter by organism (case-insensitive substring). "
            "E.g. 'MED4', 'Alteromonas'. "
            "Use list_organisms to see valid values.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include matched_terms, gene_summary, function_description.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
    ) -> GenesByOntologyResponse:
        """Find genes annotated to ontology terms, with hierarchy expansion.

        Takes term IDs from search_ontology and finds all genes annotated to
        those terms or any descendant terms in the ontology hierarchy.
        Results are distinct genes (deduplicated across terms).

        For term discovery, use search_ontology first.
        For per-gene ontology details, use gene_ontology_terms.
        """
        await ctx.info(f"genes_by_ontology term_ids={term_ids} ontology={ontology} organism={organism}")
        try:
            conn = _conn(ctx)
            data = api.genes_by_ontology(
                term_ids, ontology, organism=organism,
                summary=summary, verbose=verbose, limit=limit, conn=conn,
            )
            by_organism = [OntologyOrganismBreakdown(**b) for b in data["by_organism"]]
            by_category = [OntologyCategoryBreakdown(**b) for b in data["by_category"]]
            by_term = [OntologyTermBreakdown(**b) for b in data["by_term"]]
            results = [GenesByOntologyResult(**r) for r in data["results"]]
            return GenesByOntologyResponse(
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_category=by_category,
                by_term=by_term,
                returned=data["returned"],
                truncated=data["truncated"],
                results=results,
            )
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
        ontology_type: str | None = Field(default=None, description="Ontology type when querying all (e.g. 'go_bp')")
        # verbose-only
        organism_strain: str | None = Field(default=None, description="Organism (e.g. 'Prochlorococcus MED4')")

    class OntologyTypeBreakdown(BaseModel):
        ontology_type: str = Field(description="Ontology type (e.g. 'go_bp', 'kegg')")
        term_count: int = Field(description="Total leaf terms in this ontology (e.g. 12)")
        gene_count: int = Field(description="Input genes with at least one term in this ontology (e.g. 8)")

    class TermBreakdown(BaseModel):
        term_id: str = Field(description="Ontology term ID (e.g. 'go:0015979')")
        term_name: str = Field(description="Term name (e.g. 'photosynthesis')")
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
        truncated: bool = Field(description="True if total_matching > returned")
        not_found: list[str] = Field(default_factory=list, description="Input locus_tags not in KG")
        no_terms: list[str] = Field(default_factory=list, description="Input locus_tags in KG but with no terms for queried ontology")
        results: list[OntologyTermRow] = Field(default_factory=list, description="One row per gene × term")

    @mcp.tool(
        tags={"genes", "ontology"},
        annotations={"readOnlyHint": True},
    )
    async def gene_ontology_terms(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags to look up. "
            "E.g. ['PMM0001', 'PMM0845'].",
        )],
        ontology: Annotated[
            Literal["go_bp", "go_mf", "go_cc", "kegg", "ec",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam"] | None,
            Field(description="Filter to one ontology. None returns all."),
        ] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include organism_strain per row.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
    ) -> GeneOntologyTermsResponse:
        """Get ontology annotations for genes. One row per gene × term.

        Returns the most specific (leaf) terms only — redundant ancestor terms
        are excluded. Use ontology param to filter to one type, or omit for all.

        For the reverse direction (find genes annotated to a term, with hierarchy
        expansion), use genes_by_ontology. Use search_ontology to find terms by text.
        """
        await ctx.info(f"gene_ontology_terms locus_tags={locus_tags} ontology={ontology}")
        try:
            conn = _conn(ctx)
            data = api.gene_ontology_terms(
                locus_tags, ontology=ontology,
                summary=summary, verbose=verbose, limit=limit, conn=conn,
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
        omics_types: list[str] = Field(default=[], description="Omics data types (e.g. RNASEQ, PROTEOMICS)")
        score: float | None = Field(default=None, description="Lucene relevance score (only with search_text)")
        abstract: str | None = Field(default=None, description="Publication abstract (only with verbose=True)")
        description: str | None = Field(default=None, description="Curated study description (only with verbose=True)")

    class PubOrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        publication_count: int = Field(description="Number of publications studying this organism (e.g. 11)")

    class PubTreatmentTypeBreakdown(BaseModel):
        treatment_type: str = Field(description="Treatment category (e.g. 'coculture')")
        publication_count: int = Field(description="Number of publications (e.g. 5)")

    class PubOmicsTypeBreakdown(BaseModel):
        omics_type: str = Field(description="Omics platform (e.g. 'RNASEQ')")
        publication_count: int = Field(description="Number of publications (e.g. 12)")

    class ListPublicationsResponse(BaseModel):
        total_entries: int = Field(description="Total publications in KG (unfiltered)")
        total_matching: int = Field(description="Publications matching filters")
        by_organism: list[PubOrganismBreakdown] = Field(description="Publication counts per organism, sorted by count descending")
        by_treatment_type: list[PubTreatmentTypeBreakdown] = Field(description="Publication counts per treatment type, sorted by count descending")
        by_omics_type: list[PubOmicsTypeBreakdown] = Field(description="Publication counts per omics platform, sorted by count descending")
        returned: int = Field(description="Publications in this response")
        truncated: bool = Field(description="True if total_matching > returned")
        results: list[PublicationResult]

    @mcp.tool(
        tags={"publications", "discovery"},
        annotations={"readOnlyHint": True},
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
        search_text: Annotated[str | None, Field(
            description="Free-text search on title, abstract, and description "
            "(Lucene syntax). E.g. 'nitrogen', 'co-culture AND phage'.",
        )] = None,
        author: Annotated[str | None, Field(
            description="Filter by author name (case-insensitive). "
            "E.g. 'Sher', 'Chisholm'.",
        )] = None,
        verbose: Annotated[bool, Field(
            description="Include abstract and description. "
            "Default compact for routing.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max results.", ge=1,
        )] = 5,
    ) -> ListPublicationsResponse:
        """List publications with expression data in the knowledge graph.

        Returns publication metadata and experiment summaries. Use this as
        an entry point to discover what studies exist, then drill into
        specific experiments with list_experiments or genes with genes_by_function.
        """
        await ctx.info(f"list_publications organism={organism} treatment_type={treatment_type} "
                       f"search_text={search_text} author={author}")
        try:
            conn = _conn(ctx)
            result = api.list_publications(
                organism=organism, treatment_type=treatment_type,
                search_text=search_text, author=author,
                verbose=verbose, limit=limit, conn=conn,
            )
            results = [PublicationResult(**r) for r in result["results"]]
            by_organism = [PubOrganismBreakdown(**b) for b in result["by_organism"]]
            by_treatment_type = [PubTreatmentTypeBreakdown(**b) for b in result["by_treatment_type"]]
            by_omics_type = [PubOmicsTypeBreakdown(**b) for b in result["by_omics_type"]]
            response = ListPublicationsResponse(
                total_entries=result["total_entries"],
                total_matching=result["total_matching"],
                by_organism=by_organism,
                by_treatment_type=by_treatment_type,
                by_omics_type=by_omics_type,
                returned=result["returned"],
                truncated=result["truncated"],
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
        gene_count: int = Field(description="Total genes with expression data at this time point (e.g. 1696)")
        genes_by_status: GeneStatusBreakdown = Field(description="Gene counts by expression status at this time point")

    class ExperimentResult(BaseModel):
        # compact fields (always returned)
        experiment_id: str = Field(description="Experiment identifier (e.g. '10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq')")
        experiment_name: str = Field(description="Experiment display name (e.g. 'MED4 Coculture with Alteromonas HOT1A3 vs Pro99 medium growth conditions (RNASEQ)')")
        publication_doi: str = Field(description="Publication DOI (e.g. '10.1038/ismej.2016.70')")
        organism_strain: str = Field(description="Profiled organism (e.g. 'Prochlorococcus MED4')")
        treatment_type: str = Field(description="Treatment category (e.g. 'coculture', 'nitrogen_stress')")
        coculture_partner: str | None = Field(default=None, description="Interacting organism — coculture partner or phage. Null when no interacting organism (e.g. 'Alteromonas macleodii HOT1A3', 'Phage')")
        omics_type: str = Field(description="Omics platform (e.g. 'RNASEQ', 'MICROARRAY', 'PROTEOMICS')")
        is_time_course: bool = Field(description="Whether experiment has multiple time points")
        table_scope: str | None = Field(default=None, description="What genes the source DE table contains. Values: all_detected_genes, significant_any_timepoint, significant_only, top_n, filtered_subset. Critical for interpreting missing genes.")
        table_scope_detail: str | None = Field(default=None, description="Free-text clarification of table_scope (e.g. 'FDR < 0.05 and |logFC| > 0.8')")
        gene_count: int = Field(description="Total genes with expression data (e.g. 1696)")
        genes_by_status: GeneStatusBreakdown = Field(description="Gene counts by expression status")
        timepoints: list[TimePoint] | None = Field(default=None, description="Per-timepoint gene counts. Omitted for non-time-course experiments.")
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

    class OrganismBreakdown(BaseModel):
        organism_strain: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
        experiment_count: int = Field(description="Number of experiments for this organism (e.g. 46)")

    class TreatmentTypeBreakdown(BaseModel):
        treatment_type: str = Field(description="Treatment category (e.g. 'coculture')")
        experiment_count: int = Field(description="Number of experiments (e.g. 16)")

    class OmicsTypeBreakdown(BaseModel):
        omics_type: str = Field(description="Omics platform (e.g. 'RNASEQ')")
        experiment_count: int = Field(description="Number of experiments (e.g. 48)")

    class PublicationBreakdown(BaseModel):
        publication_doi: str = Field(description="Publication DOI (e.g. '10.1038/ismej.2016.70')")
        experiment_count: int = Field(description="Number of experiments from this publication (e.g. 5)")

    class TableScopeBreakdown(BaseModel):
        table_scope: str = Field(description="Table scope value (e.g. 'all_detected_genes', 'significant_only')")
        experiment_count: int = Field(description="Number of experiments with this scope (e.g. 22)")

    class ListExperimentsResponse(BaseModel):
        total_entries: int = Field(description="Total experiments in the KG (unfiltered)")
        total_matching: int = Field(description="Experiments matching filters")
        returned: int = Field(description="Number of results returned (0 when summary=true)")
        truncated: bool = Field(description="True if results were truncated by limit or summary=true")
        by_organism: list[OrganismBreakdown] = Field(description="Experiment counts per organism, sorted by count descending")
        by_treatment_type: list[TreatmentTypeBreakdown] = Field(description="Experiment counts per treatment type, sorted by count descending")
        by_omics_type: list[OmicsTypeBreakdown] = Field(description="Experiment counts per omics platform, sorted by count descending")
        by_publication: list[PublicationBreakdown] = Field(description="Experiment counts per publication, sorted by count descending")
        by_table_scope: list[TableScopeBreakdown] = Field(description="Experiment counts per table scope, sorted by count descending")
        time_course_count: int = Field(description="Number of time-course experiments in matching set")
        score_max: float | None = Field(default=None, description="Max Lucene relevance score, present only when search_text is used (e.g. 4.52)")
        score_median: float | None = Field(default=None, description="Median Lucene relevance score, present only when search_text is used (e.g. 1.23)")
        results: list[ExperimentResult] = Field(description="Individual experiments (empty when summary=true)")

    @mcp.tool(
        tags={"experiments", "expression", "discovery"},
        annotations={"readOnlyHint": True},
    )
    async def list_experiments(
        ctx: Context,
        organism: Annotated[str | None, Field(
            description="Filter by organism name (case-insensitive partial match "
            "on profiled organism and coculture partner). "
            "E.g. 'MED4', 'Alteromonas'.",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Filter by treatment type(s) (case-insensitive exact match). "
            "E.g. ['coculture', 'nitrogen_stress']. "
            "Use list_filter_values to see valid values.",
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
    ) -> ListExperimentsResponse:
        """List differential expression experiments in the knowledge graph.

        Returns summary breakdowns (by organism, treatment type, omics type,
        table scope) plus individual experiments. Use summary=true to see only
        breakdowns, then drill into detail with filters.

        table_scope indicates what genes each experiment's source DE table
        contains — critical for interpreting missing genes. Use
        table_scope=['all_detected_genes'] to restrict to experiments that
        report all assayed genes (fair for cross-experiment comparison).
        """
        await ctx.info(f"list_experiments summary={summary} organism={organism} "
                       f"treatment_type={treatment_type} search_text={search_text}")
        try:
            conn = _conn(ctx)
            result = api.list_experiments(
                organism=organism, treatment_type=treatment_type,
                omics_type=omics_type, publication_doi=publication_doi,
                coculture_partner=coculture_partner, search_text=search_text,
                time_course_only=time_course_only, table_scope=table_scope,
                summary=summary,
                verbose=verbose, limit=limit, conn=conn,
            )

            # Build breakdown models
            by_organism = [OrganismBreakdown(**b) for b in result["by_organism"]]
            by_treatment_type = [TreatmentTypeBreakdown(**b) for b in result["by_treatment_type"]]
            by_omics_type = [OmicsTypeBreakdown(**b) for b in result["by_omics_type"]]
            by_publication = [PublicationBreakdown(**b) for b in result["by_publication"]]
            by_table_scope = [TableScopeBreakdown(**b) for b in result["by_table_scope"]]

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
                truncated=result["truncated"],
                by_organism=by_organism,
                by_treatment_type=by_treatment_type,
                by_omics_type=by_omics_type,
                by_publication=by_publication,
                by_table_scope=by_table_scope,
                time_course_count=result["time_course_count"],
                score_max=result.get("score_max"),
                score_median=result.get("score_median"),
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

    class ExpressionByExperiment(BaseModel):
        experiment_id: str = Field(
            description="Experiment ID (e.g. '10.1101/2025.11.24.690089_...')",
        )
        experiment_name: str = Field(
            description="Human-readable name"
            " (e.g. 'HOT1A3 PRO99-lowN nutrient starvation (RNASEQ)')",
        )
        treatment_type: str = Field(
            description="Treatment category"
            " (e.g. 'nitrogen_stress', 'coculture')",
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
        treatment_type: str = Field(
            description="Treatment type from experiment"
            " (e.g. 'nitrogen_stress')",
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
        expression_status: Literal[
            "significant_up", "significant_down", "not_significant"
        ] = Field(
            description="Significance call using publication-specific"
            " threshold (e.g. 'significant_up')",
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

    class DifferentialExpressionByGeneResponse(BaseModel):
        organism_strain: str = Field(
            description="Single organism for all results"
            " (e.g. 'Alteromonas macleodii HOT1A3')",
        )
        matching_genes: int = Field(
            description="Distinct genes in results after filters (e.g. 5)",
        )
        total_rows: int = Field(
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
        truncated: bool = Field(
            description="True if total_rows > returned",
        )
        results: list[ExpressionRow] = Field(default_factory=list)

    @mcp.tool(
        tags={"expression", "genes"},
        annotations={"readOnlyHint": True},
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
                summary=summary,
                verbose=verbose,
                limit=limit,
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
                organism_strain=data["organism_strain"],
                matching_genes=data["matching_genes"],
                total_rows=data["total_rows"],
                rows_by_status=ExpressionStatusBreakdown(
                    **data["rows_by_status"]
                ),
                median_abs_log2fc=data["median_abs_log2fc"],
                max_abs_log2fc=data["max_abs_log2fc"],
                experiment_count=data["experiment_count"],
                rows_by_treatment_type=data["rows_by_treatment_type"],
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
                f"Returning {response.returned} of {response.total_rows}"
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
        returned: int = Field(description="Results in this response (0 when summary=true)")
        truncated: bool = Field(description="True if total_matching > returned")
        results: list[SearchHomologGroupsResult] = Field(
            default_factory=list, description="One row per matching ortholog group")

    @mcp.tool(
        tags={"homology", "search"},
        annotations={"readOnlyHint": True},
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
                summary=summary, verbose=verbose, limit=limit, conn=conn,
            )
            by_source = [SearchHomologGroupsSourceBreakdown(**b) for b in data["by_source"]]
            by_level = [SearchHomologGroupsLevelBreakdown(**b) for b in data["by_level"]]
            results = [SearchHomologGroupsResult(**r) for r in data["results"]]
            response = SearchHomologGroupsResponse(
                total_entries=data["total_entries"],
                total_matching=data["total_matching"],
                by_source=by_source,
                by_level=by_level,
                score_max=data["score_max"],
                score_median=data["score_median"],
                returned=data["returned"],
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
