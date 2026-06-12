"""MCP server for the Multiomics Knowledge Graph.

Exposes Neo4j-backed tools for gene lookup, expression analysis,
homology exploration, and raw Cypher queries.
"""

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastmcp import FastMCP

from multiomics_explorer.api.functions import _get_explorer_version, kg_release_info
from multiomics_explorer.config.settings import get_settings
from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.mcp_server.tools import register_tools

logger = logging.getLogger(__name__)


@dataclass
class KGContext:
    conn: GraphConnection
    kg_compat_report: dict  # api.kg_release_info shape, cached at lifespan startup


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Manage Neo4j connection lifecycle.

    Also runs the KG↔explorer compatibility check once at startup and
    caches the report on KGContext. The kg_release_info MCP tool reads
    from this cache. Per design spec
    docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md §9.
    """
    settings = get_settings()
    conn = GraphConnection(settings)
    if not conn.verify_connectivity():
        raise RuntimeError(f"Cannot connect to Neo4j at {settings.neo4j_uri}")
    logger.info("Connected to Neo4j at %s", settings.neo4j_uri)

    # KG compatibility check — defensive: never block startup on this.
    try:
        report = kg_release_info(conn)
    except Exception as e:
        logger.warning("KG compatibility check failed to evaluate: %s", e)
        report = {
            "verdict": "unknown",
            "summary": f"Check could not run: {e}",
            "explorer_version": _get_explorer_version(),
            "kg": {},
            "asserts": [],
        }

    if report["verdict"] == "ok":
        logger.info("KG compat: %s", report["summary"])
    else:
        logger.warning("KG compat: %s", report["summary"])

    try:
        yield KGContext(conn=conn, kg_compat_report=report)
    finally:
        conn.close()
        logger.info("Neo4j connection closed")


mcp = FastMCP(
    "multiomics-kg",
    instructions=(
        "Multi-omics knowledge graph for Prochlorococcus and Alteromonas "
        "(41 tools across gene/sequence/expression/ortholog/ontology/cluster/"
        "chemistry/metabolomics/enrichment).\n\n"
        "First call: kg_release_info — verifies your KG release matches what this "
        "explorer-MCP version expects. Surfaces the KG's identity (version, "
        "built_at, counts) and a verdict (ok / warn / unknown).\n\n"
        "Start here:\n"
        "  docs://guide/start_here  — pick the right tool for your question\n"
        "  docs://guide/concepts    — KG data model (Gene, Experiment, "
        "DerivedMetric, Metabolite, MetaboliteAssay, Reaction, ontology terms)\n"
        "  docs://guide/conventions — cross-tool semantics: not_found vs "
        "not_matched, tested-absent rows, exclude-wins-on-overlap, "
        "rankable-gated filters, AQ / informative_only defaults\n"
        "  docs://guide/python_api  — scripting against the Python package: "
        "import topology, return shapes, DataFrames, connection management, "
        "worked recipes\n\n"
        "Per-tool: docs://tools/{tool_name}     "
        "(e.g. docs://tools/differential_expression_by_gene)\n"
        "Analysis: docs://analysis/{name}       "
        "(e.g. docs://analysis/enrichment, docs://analysis/metabolites)\n"
        "Examples: docs://examples/{file}       "
        "(e.g. docs://examples/pathway_enrichment.py, "
        "docs://examples/metabolites.py)"
    ),
    lifespan=lifespan,
)

register_tools(mcp)


# --- Documentation resources: per-tool and per-analysis guides ---
from pathlib import Path

from fastmcp.resources.function_resource import FunctionResource

_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent
    / "skills" / "multiomics-kg-guide" / "references"
)

_DOC_DIRS = {
    "docs://tools": (_SKILLS_DIR / "tools", "Usage guide for the {stem} tool"),
    "docs://analysis": (_SKILLS_DIR / "analysis", "Usage guide for the {stem} analysis utility"),
    "docs://guide": (_SKILLS_DIR / "guide", "Cross-tool guide: {stem}"),
}

for uri_prefix, (doc_dir, desc_template) in _DOC_DIRS.items():
    for md_file in sorted(doc_dir.glob("*.md")):
        stem = md_file.stem
        uri = f"{uri_prefix}/{stem}"

        def _make_reader(path: Path):
            return lambda: path.read_text()

        resource = FunctionResource.from_function(
            fn=_make_reader(md_file),
            uri=uri,
            name=stem,
            description=desc_template.format(stem=stem),
            mime_type="text/plain",
        )
        mcp.add_resource(resource)

# --- Static resources: example scripts (not auto-discovered from .md files) ---
_EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"

for example_name, example_description in [
    ("pathway_enrichment.py", "Runnable example script for pathway enrichment"),
    (
        "metabolites.py",
        "Runnable metabolites workflow examples (3 source pipelines × 7 scenarios)",
    ),
]:
    mcp.add_resource(
        FunctionResource.from_function(
            fn=(lambda p: lambda: p.read_text())(_EXAMPLES_DIR / example_name),
            uri=f"docs://examples/{example_name}",
            name=example_name,
            description=example_description,
            mime_type="text/x-python",
        )
    )


def main():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
