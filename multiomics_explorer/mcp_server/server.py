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


# --- About-mode resources: per-tool documentation ---
from pathlib import Path

_TOOLS_DOCS_DIR = (
    Path(__file__).resolve().parent.parent
    / "skills" / "multiomics-kg-guide" / "references" / "tools"
)


@mcp.resource("docs://tools/{tool_name}")
def tool_docs(tool_name: str) -> str:
    """Usage guide for a specific tool: parameters, response format, examples, chaining patterns."""
    path = _TOOLS_DOCS_DIR / f"{tool_name}.md"
    if not path.exists():
        return f"No documentation found for tool '{tool_name}'."
    return path.read_text()


_ANALYSIS_DOCS_DIR = (
    Path(__file__).resolve().parent.parent
    / "skills" / "multiomics-kg-guide" / "references" / "analysis"
)


@mcp.resource("docs://analysis/{name}")
def analysis_docs(name: str) -> str:
    """Usage guide for an analysis utility: parameters, response format, examples, chaining patterns."""
    path = _ANALYSIS_DOCS_DIR / f"{name}.md"
    if not path.exists():
        return f"No documentation found for analysis function '{name}'."
    return path.read_text()


def main():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
