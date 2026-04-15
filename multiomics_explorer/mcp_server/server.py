"""MCP server for the Multiomics Knowledge Graph.

Exposes Neo4j-backed tools for gene lookup, expression analysis,
homology exploration, and raw Cypher queries.
"""

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastmcp import FastMCP

from multiomics_explorer.config.settings import get_settings
from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.mcp_server.tools import register_tools

logger = logging.getLogger(__name__)


@dataclass
class KGContext:
    conn: GraphConnection


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Manage Neo4j connection lifecycle."""
    settings = get_settings()
    conn = GraphConnection(settings)
    if not conn.verify_connectivity():
        raise RuntimeError(f"Cannot connect to Neo4j at {settings.neo4j_uri}")
    logger.info("Connected to Neo4j at %s", settings.neo4j_uri)
    try:
        yield KGContext(conn=conn)
    finally:
        conn.close()
        logger.info("Neo4j connection closed")


mcp = FastMCP(
    "multiomics-kg",
    instructions=(
        "Multi-omics knowledge graph for Prochlorococcus and Alteromonas. "
        "For detailed usage guides on any tool, read the resource at "
        "docs://tools/{tool_name} (e.g. docs://tools/list_publications). "
        "For analysis utility guides, read docs://analysis/{name} "
        "(e.g. docs://analysis/response_matrix)."
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

# --- Static resources: enrichment methodology doc and example script ---
_ANALYSIS_DIR = Path(__file__).resolve().parent.parent / "analysis"
_EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"

for _uri, _path, _name, _desc, _mime in [
    (
        "docs://analysis/enrichment",
        _ANALYSIS_DIR / "enrichment.md",
        "enrichment",
        "Methodology doc for pathway enrichment analysis",
        "text/plain",
    ),
    (
        "docs://examples/pathway_enrichment.py",
        _EXAMPLES_DIR / "pathway_enrichment.py",
        "pathway_enrichment.py",
        "Runnable example script for pathway enrichment",
        "text/x-python",
    ),
]:
    mcp.add_resource(
        FunctionResource.from_function(
            fn=(lambda p: lambda: p.read_text())(_path),
            uri=_uri,
            name=_name,
            description=_desc,
            mime_type=_mime,
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
