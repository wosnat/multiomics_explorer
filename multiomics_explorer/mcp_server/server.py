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
        "(42 tools).\n\n"
        "First call: kg_release_info — KG identity + compatibility verdict.\n"
        "Directory: docs://index — every docs:// page with its ~token size "
        "and when to read it. Start with docs://guide/start_here (~5k tok) "
        "to pick a tool.\n\n"
        "Habits: summary=True first on list/discovery tools (cheap envelope, "
        "no rows); docs://tools/{tool} is a ~1k-tok brief — append /full "
        "only when you need every worked example; docs://guide/conventions "
        "(~12k) for cross-tool semantics; "
        "docs://analysis/{enrichment,metabolites,annotation_evidence,"
        "expression,derived_metrics} for methodology."
    ),
    lifespan=lifespan,
)

register_tools(mcp)


# --- Documentation resources: per-tool and per-analysis guides ---
# Order-dependent: resource registration below needs `mcp` already built.
from pathlib import Path  # noqa: E402

from fastmcp.resources.function_resource import FunctionResource  # noqa: E402

_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent
    / "skills" / "multiomics-kg-guide" / "references"
)

# Registration order (llm-review 2b.4 D1/D5): index, guide, tools (brief),
# tools (full), analysis, ontologies, examples. `_DOC_DIRS` order matters —
# it drives the guide/tools/analysis/ontologies loops below, with the
# `/full` tool pages spliced in between tools and analysis.
_DOC_DIRS = {
    "docs://guide": (_SKILLS_DIR / "guide", "Cross-tool guide: {stem}"),
    "docs://tools": (_SKILLS_DIR / "tools", "Usage guide for the {stem} tool"),
    "docs://analysis": (_SKILLS_DIR / "analysis", "Usage guide for the {stem} analysis utility"),
    "docs://ontologies": (_SKILLS_DIR / "ontologies", "Ontology reference: {stem}"),
}


def _make_reader(path: Path):
    return lambda: path.read_text(encoding="utf-8")


def _register_doc_dir(uri_prefix: str, doc_dir: Path, desc_template: str) -> None:
    for md_file in sorted(doc_dir.glob("*.md")):
        stem = md_file.stem
        resource = FunctionResource.from_function(
            fn=_make_reader(md_file),
            uri=f"{uri_prefix}/{stem}",
            name=stem,
            description=desc_template.format(stem=stem),
            mime_type="text/plain",
        )
        mcp.add_resource(resource)


# docs://index — directory of every docs:// page, registered first so it's
# always the first resource a client sees when listing.
mcp.add_resource(
    FunctionResource.from_function(
        fn=_make_reader(_SKILLS_DIR / "index.md"),
        uri="docs://index",
        name="index",
        description="Directory of every docs:// page with size and read-when",
        mime_type="text/plain",
    )
)

_register_doc_dir("docs://guide", *_DOC_DIRS["docs://guide"])
_register_doc_dir("docs://tools", *_DOC_DIRS["docs://tools"])

# Full-length tool pages (references/tools/full/*.md) — served at
# docs://tools/{name}/full, right after the brief pages.
_FULL_DIR = _SKILLS_DIR / "tools" / "full"
for md_file in sorted(_FULL_DIR.glob("*.md")):
    mcp.add_resource(
        FunctionResource.from_function(
            fn=_make_reader(md_file),
            uri=f"docs://tools/{md_file.stem}/full",
            name=f"{md_file.stem}_full",
            description=f"Full reference for the {md_file.stem} tool (all examples, full response format)",
            mime_type="text/plain",
        )
    )

_register_doc_dir("docs://analysis", *_DOC_DIRS["docs://analysis"])
_register_doc_dir("docs://ontologies", *_DOC_DIRS["docs://ontologies"])

# --- Static resources: example scripts (not auto-discovered from .md files) ---
_EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"

for example_name, example_description in [
    ("pathway_enrichment.py", "Runnable example script for pathway enrichment"),
    (
        "metabolites.py",
        "Runnable metabolites workflow examples (3 source pipelines × 7 scenarios)",
    ),
    (
        "ontology_terms.py",
        "Runnable ontology term-side examples (browse, multi-ontology search, "
        "term details, bridge walk)",
    ),
    (
        "annotation_evidence.py",
        "Runnable annotation-trust examples (evidence ladder, trust filters, "
        "InterPro-typed enrichment)",
    ),
]:
    mcp.add_resource(
        FunctionResource.from_function(
            fn=(lambda p: lambda: p.read_text(encoding="utf-8"))(_EXAMPLES_DIR / example_name),
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
