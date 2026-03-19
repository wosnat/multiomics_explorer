"""MCP server for the Multiomics Knowledge Graph.

Exposes Neo4j-backed tools for gene lookup, expression analysis,
homology exploration, and raw Cypher queries.
"""

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

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
    instructions="Multi-omics knowledge graph for Prochlorococcus and Alteromonas",
    lifespan=lifespan,
)

register_tools(mcp)


def main():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
