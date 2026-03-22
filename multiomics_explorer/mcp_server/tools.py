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

    @mcp.tool()
    def get_schema(ctx: Context) -> str:
        """Get the knowledge graph schema: node types with counts, relationship types with
        source/target labels, and property names. Use this first to understand what's queryable."""
        logger.info("get_schema")
        try:
            from multiomics_explorer.kg.schema import load_schema_from_neo4j

            conn = _conn(ctx)
            schema = load_schema_from_neo4j(conn)
            return schema.to_prompt_string()
        except ValueError as e:
            logger.warning("get_schema error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("get_schema unexpected error: %s", e)
            return f"Error in get_schema: {e}"

    @mcp.tool()
    def list_filter_values(ctx: Context) -> str:
        """List valid values for categorical filters used across tools.

        Returns:
        - gene_categories: values for the category filter on search_genes
          (e.g. "Photosynthesis", "Transport", "Stress response and adaptation")
        """
        logger.info("list_filter_values")
        try:
            lc = ctx.request_context.lifespan_context
            cached = getattr(lc, "_filter_values_cache", None)
            if cached is not None:
                return cached

            conn = _conn(ctx)
            result = api.list_filter_values(conn=conn)
            response = json.dumps(result, indent=2, default=str)
            lc._filter_values_cache = response
            return response
        except ValueError as e:
            logger.warning("list_filter_values error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("list_filter_values unexpected error: %s", e)
            return f"Error in list_filter_values: {e}"

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
        )] = 50,
    ) -> ListOrganismsResponse:
        """List all organisms with sequenced genomes in the knowledge graph.

        Returns taxonomy, gene counts, and publication counts for each organism.
        Use the returned organism names as filter values in search_genes,
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
                returned=len(organisms),
                truncated=result["total_entries"] > len(organisms),
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

    class ResolveGeneResponse(BaseModel):
        total_matching: int = Field(description="Total genes matching identifier + organism filter (e.g. 3)")
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
        )] = 50,
    ) -> ResolveGeneResponse:
        """Resolve a gene identifier to matching genes in the knowledge graph.

        Matching is case-insensitive — 'pmm0001', 'PMM0001', and 'Pmm0001'
        all work. Use the returned locus_tags with gene_overview,
        get_gene_details, get_homologs, or gene_ontology_terms. The organism
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
            return ResolveGeneResponse(
                total_matching=result["total_matching"],
                returned=len(genes),
                truncated=result["total_matching"] > len(genes),
                results=genes,
            )
        except ValueError as e:
            await ctx.warning(f"resolve_gene error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"resolve_gene unexpected error: {e}")
            raise ToolError(f"Error in resolve_gene: {e}")

    @mcp.tool()
    def search_genes(
        ctx: Context,
        search_text: str,
        organism: str | None = None,
        category: str | None = None,
        min_quality: int = 0,
        deduplicate: bool = False,
        limit: int = 10,
    ) -> str:
        """Free-text search across gene functional annotations using full-text index.
        Supports Lucene syntax: "DNA repair", nitrogen AND transport, iron*, dnaN~.

        Args:
            search_text: Free-text query (Lucene syntax supported).
            organism: Optional organism filter (e.g. "MED4", "Prochlorococcus MED4").
                Use list_organisms to see all valid organisms.
            category: Optional gene_category filter (e.g. "Photosynthesis", "Transport").
                Use list_filter_values to see all valid categories. Invalid values
                return empty results (no validation).
            min_quality: Minimum annotation_quality (0-3).
                0 = hypothetical, no function info;
                1 = hypothetical but has function description;
                2 = real product name;
                3 = well-annotated (product + GO/KEGG/EC/Pfam).
                Use 2 to skip hypothetical proteins.
            deduplicate: If True, collapse orthologs by ortholog group and return
                one representative per group with collapsed_count and
                group_organisms summary. Counts reflect hits within the result
                set, not total group membership — use get_homologs for full
                ortholog inventory.
            limit: Max results (default 10, max 50). When deduplicate=True, the
                limit applies to the pre-dedup query, so fewer rows may be
                returned after collapsing.
        """
        logger.info("search_genes search_text=%s organism=%s category=%s deduplicate=%s limit=%d",
                    search_text, organism, category, deduplicate, limit)
        try:
            conn = _conn(ctx)
            limit = min(limit, 50)
            results = api.search_genes(
                search_text, organism=organism,
                category=category, min_quality=min_quality,
                deduplicate=deduplicate, conn=conn,
            )
            results = results[:limit]
            if not results:
                return json.dumps({
                    "results": [], "total": 0, "query": search_text,
                })
            return json.dumps({
                "results": results, "total": len(results), "query": search_text,
            }, indent=2, default=str)
        except ValueError as e:
            logger.warning("search_genes error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("search_genes unexpected error: %s", e)
            return f"Error in search_genes: {e}"

    @mcp.tool()
    def gene_overview(ctx: Context, gene_ids: list[str], limit: int = 50) -> str:
        """Get an overview of one or more genes: identity and data availability.

        Use this after resolve_gene, search_genes, genes_by_ontology, or
        get_homologs to understand what each gene is and what follow-up data
        exists.

        Returns one row per gene with routing signals:
        - annotation_types: which ontology types have annotations
          → use gene_ontology_terms with the relevant type
        - expression_edge_count + significant_expression_count: whether
          expression data exists and how much is significant
        - closest_ortholog_group_size + closest_ortholog_genera: whether
          orthologs exist and in which genera
          → use get_homologs for full membership

        Args:
            gene_ids: List of gene locus_tags.
                      Use resolve_gene to find locus_tags from other identifiers.
            limit: Max genes to return (default 50).
        """
        logger.info("gene_overview gene_ids=%s limit=%d", gene_ids, limit)
        try:
            conn = _conn(ctx)
            rows = api.gene_overview(gene_ids, conn=conn)
            if not rows:
                return "No genes found for the given locus_tags."
            return _fmt(rows, limit=limit)
        except ValueError as e:
            logger.warning("gene_overview error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("gene_overview unexpected error: %s", e)
            return f"Error in gene_overview: {e}"

    @mcp.tool()
    def get_gene_details(ctx: Context, gene_id: str) -> str:
        """Get all properties for a gene.

        This is a deep-dive tool — use gene_overview for the common case.
        Returns all Gene node properties including sparse fields
        (catalytic_activities, transporter_classification, cazy_ids, etc.).

        For organism taxonomy, use list_organisms. For homologs, use
        get_homologs. For ontology annotations, use gene_ontology_terms.

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

    def _no_groups_msg(gene_id, source, taxonomic_level, max_specificity_rank):
        msg = f"No ortholog groups found for '{gene_id}'"
        filters = []
        if source:
            filters.append(f"source={source}")
        if taxonomic_level:
            filters.append(f"taxonomic_level={taxonomic_level}")
        if max_specificity_rank is not None:
            filters.append(f"max_specificity_rank={max_specificity_rank}")
        if filters:
            msg += f" with constraints: {', '.join(filters)}"
        return msg + "."

    @mcp.tool()
    def get_homologs(
        ctx: Context,
        gene_id: str,
        source: str | None = None,
        taxonomic_level: str | None = None,
        max_specificity_rank: int | None = None,
        exclude_paralogs: bool = True,
        include_members: bool = False,
        member_limit: int = 50,
    ) -> str:
        """Find orthologs of a gene, grouped by ortholog group.

        Returns ortholog groups the gene belongs to, ordered from most specific
        (curated) to broadest (Bacteria-level COG). Each group includes its
        consensus function, member/organism counts, and genera.

        By default returns group summaries only. Set include_members=True to
        get the full list of member genes per group.

        Args:
            gene_id: Gene locus_tag (e.g. "PMM0001").
            source: Filter by OG source: "cyanorak" or "eggnog".
            taxonomic_level: Filter by level: "curated", "Prochloraceae",
                "Synechococcus", "Alteromonadaceae", "Cyanobacteria",
                "Gammaproteobacteria", "Bacteria".
            max_specificity_rank: Cap breadth — 0=curated only, 1=+family,
                2=+order, 3=+domain (all). Overrides source/taxonomic_level.
            exclude_paralogs: If True (default), exclude members from the same
                organism strain as the query gene. Set False to include paralogs.
                Only applies when include_members=True.
            include_members: If True, include full member gene lists per group.
                Default False returns group summaries (counts, consensus function,
                genera) without individual member genes.
            member_limit: Max members returned per group (default 50, max 200).
                Only applies when include_members=True. Groups exceeding the
                limit include a "truncated" flag.

        Raises:
            ValueError if source is not in {"cyanorak", "eggnog"} or
            taxonomic_level is not in {"curated", "Prochloraceae",
            "Synechococcus", "Alteromonadaceae", "Cyanobacteria",
            "Gammaproteobacteria", "Bacteria"} or max_specificity_rank
            is not in 0-3 or member_limit is not in 1-200.

        Notes:
            - member_count and organism_count are total group counts from the
              KG (include paralogs). When exclude_paralogs is True, the
              returned members list may be smaller than member_count.
            - Expression query tools are being rebuilt for the new schema.
            - A gene typically belongs to 1-3 groups: one Cyanorak curated
              cluster (Pro/Syn only), one eggNOG family-level OG, and one
              eggNOG Bacteria-level COG.
        """
        logger.info("get_homologs gene_id=%s source=%s taxonomic_level=%s include_members=%s",
                    gene_id, source, taxonomic_level, include_members)
        try:
            conn = _conn(ctx)
            result = api.get_homologs(
                gene_id, source=source,
                taxonomic_level=taxonomic_level,
                max_specificity_rank=max_specificity_rank,
                exclude_paralogs=exclude_paralogs,
                include_members=include_members,
                member_limit=member_limit, conn=conn,
            )
            if not result["ortholog_groups"]:
                return _no_groups_msg(gene_id, source, taxonomic_level, max_specificity_rank)
            return json.dumps(result, indent=2, default=str)
        except ValueError as e:
            logger.warning("get_homologs error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("get_homologs unexpected error: %s", e)
            return f"Error in get_homologs: {e}"

    @mcp.tool()
    def run_cypher(ctx: Context, query: str, limit: int = 25) -> str:
        """Execute a raw Cypher query against the knowledge graph (read-only).

        Use this as an escape hatch when the other tools don't cover your query.
        Write operations are blocked (regex keyword filter + read-only transaction).

        Args:
            query: Cypher query string. A LIMIT clause will be added if not present.
            limit: Max results (default 25, max 200).
        """
        logger.info("run_cypher limit=%d", limit)
        try:
            limit = min(limit, 200)

            # Add LIMIT if not present
            if not re.search(r"\bLIMIT\b", query, re.IGNORECASE):
                query = query.rstrip().rstrip(";")
                query += f"\nLIMIT {limit}"

            conn = _conn(ctx)
            results = api.run_cypher(query, conn=conn)
            if not results:
                return "Query returned no results."
            return _fmt(results, limit=limit)
        except ValueError as e:
            logger.warning("run_cypher error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("run_cypher unexpected error: %s", e)
            return f"Error in run_cypher: {e}"

    @mcp.tool()
    def search_ontology(
        ctx: Context,
        search_text: str,
        ontology: str,
        limit: int = 25,
    ) -> str:
        """Browse ontology terms by text search (fuzzy, Lucene syntax).

        Use this to discover ontology term IDs, then pass them to
        genes_by_ontology to find genes.

        Supports Lucene query syntax: fuzzy matching (~), wildcards (*),
        exact phrases ("..."), boolean operators (AND, OR).

        Args:
            search_text: Search query against term names. Examples:
                "DNA replication" — phrase match
                "replicat~" — fuzzy match
                "oxido*" — wildcard
                "transport AND membrane" — boolean
            ontology: Which ontology to search. One of:
                "go_bp" (biological process), "go_mf" (molecular function),
                "go_cc" (cellular component), "kegg", "ec",
                "cog_category" (COG functional categories),
                "cyanorak_role" (Cyanorak functional roles),
                "tigr_role" (TIGR functional roles),
                "pfam" (Pfam protein domains and clans).
                For KEGG, searches across all levels — level is encoded in
                the returned ID prefix:
                  kegg.category:    (e.g. "Metabolism")
                  kegg.subcategory: (e.g. "Carbohydrate metabolism")
                  kegg.pathway:     (e.g. "Glycolysis")
                  kegg.orthology:   (e.g. "K00001 alcohol dehydrogenase")
            limit: Max results (default 25).
        """
        logger.info("search_ontology search_text=%s ontology=%s limit=%d",
                    search_text, ontology, limit)
        try:
            conn = _conn(ctx)
            results = api.search_ontology(search_text, ontology, conn=conn)
            results = results[:limit]
            if not results:
                return json.dumps({
                    "results": [], "total": 0, "query": search_text,
                })
            return json.dumps({
                "results": results, "total": len(results), "query": search_text,
            }, indent=2, default=str)
        except ValueError as e:
            logger.warning("search_ontology error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("search_ontology unexpected error: %s", e)
            return f"Error in search_ontology: {e}"

    @mcp.tool()
    def genes_by_ontology(
        ctx: Context,
        term_ids: list[str],
        ontology: str,
        organism: str | None = None,
        limit: int = 25,
    ) -> str:
        """Find genes annotated to ontology terms, with hierarchy expansion.

        Takes ontology term IDs (from search_ontology) and finds all genes
        annotated to those terms or any of their descendant terms in the
        ontology hierarchy.

        Args:
            term_ids: One or more ontology term IDs (from search_ontology).
            ontology: Which ontology the IDs belong to. One of:
                "go_bp" (biological process), "go_mf" (molecular function),
                "go_cc" (cellular component), "kegg", "ec",
                "cog_category", "cyanorak_role", "tigr_role", "pfam".
            organism: Optional organism filter (fuzzy match on strain name).
            limit: Max gene results (default 25).
        """
        logger.info("genes_by_ontology term_ids=%s ontology=%s organism=%s limit=%d",
                    term_ids, ontology, organism, limit)
        try:
            conn = _conn(ctx)
            results = api.genes_by_ontology(term_ids, ontology, organism=organism, conn=conn)
            results = results[:limit]
            if not results:
                return json.dumps({"results": {}, "total": 0})
            grouped = _group_by_organism(results)
            return json.dumps(
                {"results": grouped, "total": len(results)},
                indent=2, default=str,
            )
        except ValueError as e:
            logger.warning("genes_by_ontology error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("genes_by_ontology unexpected error: %s", e)
            return f"Error in genes_by_ontology: {e}"

    @mcp.tool()
    def gene_ontology_terms(
        ctx: Context,
        gene_id: str,
        ontology: str,
        leaf_only: bool = True,
        limit: int = 50,
    ) -> str:
        """Get ontology annotations for a gene.

        Returns the ontology terms a gene is annotated to. By default returns
        only the most specific (leaf) terms — those that are not ancestors of
        other terms the gene is annotated to.

        Args:
            gene_id: Gene locus_tag (e.g. "PMM0001").
            ontology: Which ontology to return. One of:
                "go_bp" (biological process), "go_mf" (molecular function),
                "go_cc" (cellular component), "kegg", "ec",
                "cog_category", "cyanorak_role", "tigr_role", "pfam".
            leaf_only: If True (default), return only the most specific terms.
                If False, return all annotations.
            limit: Max results (default 50). Relevant mainly with
                leaf_only=False, which can return many ancestor terms.
        """
        logger.info("gene_ontology_terms gene_id=%s ontology=%s leaf_only=%s limit=%d",
                    gene_id, ontology, leaf_only, limit)
        try:
            conn = _conn(ctx)
            results = api.gene_ontology_terms(gene_id, ontology, leaf_only=leaf_only, conn=conn)
            results = results[:limit]
            if not results:
                return json.dumps({"results": [], "total": 0})
            return json.dumps({
                "results": results, "total": len(results),
            }, indent=2, default=str)
        except ValueError as e:
            logger.warning("gene_ontology_terms error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("gene_ontology_terms unexpected error: %s", e)
            return f"Error in gene_ontology_terms: {e}"

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

    class ListPublicationsResponse(BaseModel):
        total_entries: int = Field(description="Total publications in KG (unfiltered)")
        total_matching: int = Field(description="Publications matching filters")
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
        )] = 50,
    ) -> ListPublicationsResponse:
        """List publications with expression data in the knowledge graph.

        Returns publication metadata and experiment summaries. Use this as
        an entry point to discover what studies exist, then drill into
        specific experiments with list_experiments or genes with search_genes.
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
            response = ListPublicationsResponse(
                total_entries=result["total_entries"],
                total_matching=result["total_matching"],
                returned=len(results),
                truncated=result["total_matching"] > len(results),
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

    # --- list_experiments (v2 pattern: unified response, summary/detail modes) ---

    class TimePoint(BaseModel):
        label: str | None = Field(default=None, description="Time point label, null if unlabeled (e.g. '24h', '5h extended darkness (40h)')")
        order: int = Field(description="Sort order within experiment (e.g. 1, 2, 3)")
        hours: float | None = Field(default=None, description="Time in hours, null if unknown (e.g. 24.0)")
        total: int = Field(description="Total genes with expression data at this time point (e.g. 1696)")
        significant: int = Field(description="Genes with significant differential expression (e.g. 423)")

    class ExperimentResult(BaseModel):
        # compact fields (always returned)
        experiment_id: str = Field(description="Experiment identifier (e.g. '10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq')")
        publication_doi: str = Field(description="Publication DOI (e.g. '10.1038/ismej.2016.70')")
        organism_strain: str = Field(description="Profiled organism (e.g. 'Prochlorococcus MED4')")
        treatment_type: str = Field(description="Treatment category (e.g. 'coculture', 'nitrogen_stress')")
        coculture_partner: str | None = Field(default=None, description="Interacting organism — coculture partner or phage. Null when no interacting organism (e.g. 'Alteromonas macleodii HOT1A3', 'Phage')")
        omics_type: str = Field(description="Omics platform (e.g. 'RNASEQ', 'MICROARRAY', 'PROTEOMICS')")
        is_time_course: bool = Field(description="Whether experiment has multiple time points")
        time_points: list[TimePoint] | None = Field(default=None, description="Per-time-point gene counts. Omitted for non-time-course experiments.")
        gene_count: int = Field(description="Total genes with expression data (e.g. 1696)")
        significant_count: int = Field(description="Genes with significant differential expression (e.g. 423)")
        score: float | None = Field(default=None, description="Lucene relevance score, present only when search_text is used (e.g. 2.45)")
        # verbose-only fields
        name: str | None = Field(default=None, description="Experiment display name (e.g. 'MED4 Coculture with Alteromonas HOT1A3 vs Pro99 medium growth conditions (RNASEQ)')")
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

    class ListExperimentsResponse(BaseModel):
        total_entries: int = Field(description="Total experiments in the KG (unfiltered)")
        total_matching: int = Field(description="Experiments matching filters")
        returned: int = Field(description="Number of results returned (0 in summary mode)")
        truncated: bool = Field(description="True if results were truncated by limit, or summary mode")
        by_organism: list[OrganismBreakdown] = Field(description="Experiment counts per organism, sorted by count descending")
        by_treatment_type: list[TreatmentTypeBreakdown] = Field(description="Experiment counts per treatment type, sorted by count descending")
        by_omics_type: list[OmicsTypeBreakdown] = Field(description="Experiment counts per omics platform, sorted by count descending")
        by_publication: list[PublicationBreakdown] = Field(description="Experiment counts per publication, sorted by count descending")
        time_course_count: int = Field(description="Number of time-course experiments in matching set")
        score_max: float | None = Field(default=None, description="Max Lucene relevance score, present only when search_text is used (e.g. 4.52)")
        score_median: float | None = Field(default=None, description="Median Lucene relevance score, present only when search_text is used (e.g. 1.23)")
        results: list[ExperimentResult] = Field(description="Individual experiments (empty in summary mode, populated in detail mode)")

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
        mode: Annotated[Literal["summary", "detail"], Field(
            description="'summary' returns breakdowns by organism, treatment type, "
            "and omics type to guide filtering. 'detail' returns individual "
            "experiments with gene counts. Start with summary to orient, "
            "then use detail with filters.",
        )] = "summary",
        verbose: Annotated[bool, Field(
            description="Detail mode only. Include experiment name, publication "
            "title, treatment/control descriptions, and experimental conditions "
            "(light, medium, temperature, statistical test, context).",
        )] = False,
        limit: Annotated[int, Field(
            description="Detail mode only. Max results.", ge=1,
        )] = 50,
    ) -> ListExperimentsResponse:
        """List differential expression experiments in the knowledge graph.

        Start with mode='summary' to see experiment counts by organism, treatment
        type, and omics type. Then use mode='detail' with filters to browse
        individual experiments. Pass experiment IDs to query_expression for
        gene-level results.
        """
        await ctx.info(f"list_experiments mode={mode} organism={organism} "
                       f"treatment_type={treatment_type} search_text={search_text}")
        try:
            conn = _conn(ctx)
            result = api.list_experiments(
                organism=organism, treatment_type=treatment_type,
                omics_type=omics_type, publication_doi=publication_doi,
                coculture_partner=coculture_partner, search_text=search_text,
                time_course_only=time_course_only,
                mode=mode,
                verbose=verbose, limit=limit, conn=conn,
            )

            # Build breakdown models
            by_organism = [OrganismBreakdown(**b) for b in result["by_organism"]]
            by_treatment_type = [TreatmentTypeBreakdown(**b) for b in result["by_treatment_type"]]
            by_omics_type = [OmicsTypeBreakdown(**b) for b in result["by_omics_type"]]
            by_publication = [PublicationBreakdown(**b) for b in result["by_publication"]]

            # Build result models (empty list in summary mode)
            experiments = []
            for r in result["results"]:
                tp_data = r.get("time_points")
                tp_list = [TimePoint(**tp) for tp in tp_data] if tp_data else None
                experiments.append(ExperimentResult(
                    **{k: v for k, v in r.items() if k != "time_points"},
                    time_points=tp_list,
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
