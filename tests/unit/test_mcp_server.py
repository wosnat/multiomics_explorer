"""P3: Tests for MCP server lifespan, KGContext, and doc resources — no Neo4j needed."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from multiomics_explorer.mcp_server.server import KGContext, lifespan, mcp


class TestKGContext:
    def test_holds_connection(self):
        """KGContext dataclass should store the connection reference."""
        mock_conn = MagicMock()
        ctx = KGContext(conn=mock_conn)
        assert ctx.conn is mock_conn


class TestLifespan:
    @pytest.mark.asyncio
    async def test_creates_and_closes_connection(self):
        """Lifespan should create a GraphConnection, yield it, then close."""
        mock_conn = MagicMock()
        mock_conn.verify_connectivity.return_value = True

        with patch(
            "multiomics_explorer.mcp_server.server.GraphConnection",
            return_value=mock_conn,
        ), patch(
            "multiomics_explorer.mcp_server.server.get_settings",
            return_value=MagicMock(),
        ):
            mock_server = MagicMock()
            async with lifespan(mock_server) as ctx:
                assert isinstance(ctx, KGContext)
                assert ctx.conn is mock_conn

            mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_when_neo4j_unreachable(self):
        """Lifespan should raise RuntimeError if Neo4j is unreachable."""
        mock_conn = MagicMock()
        mock_conn.verify_connectivity.return_value = False

        with patch(
            "multiomics_explorer.mcp_server.server.GraphConnection",
            return_value=mock_conn,
        ), patch(
            "multiomics_explorer.mcp_server.server.get_settings",
            return_value=MagicMock(neo4j_uri="bolt://localhost:7687"),
        ):
            with pytest.raises(RuntimeError, match="Cannot connect"):
                async with lifespan(MagicMock()):
                    pass


# --- Documentation resources ---

_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "multiomics_explorer" / "skills" / "multiomics-kg-guide" / "references"
)

# Expected resources derived from doc files on disk
_EXPECTED_TOOL_RESOURCES = {
    f"docs://tools/{p.stem}" for p in (_SKILLS_DIR / "tools").glob("*.md")
}
_EXPECTED_ANALYSIS_RESOURCES = {
    f"docs://analysis/{p.stem}" for p in (_SKILLS_DIR / "analysis").glob("*.md")
}
_EXPECTED_RESOURCES = _EXPECTED_TOOL_RESOURCES | _EXPECTED_ANALYSIS_RESOURCES


class TestDocResources:
    @pytest.mark.asyncio
    async def test_no_resource_templates(self):
        """All doc resources should be static, not templates."""
        templates = await mcp._local_provider._list_resource_templates()
        doc_templates = [
            t for t in templates
            if str(t.uriTemplate).startswith("docs://")
        ]
        assert doc_templates == [], (
            f"Doc resources should be static, not templates: {doc_templates}"
        )

    @pytest.mark.asyncio
    async def test_all_doc_files_registered(self):
        """Every .md file in tools/ and analysis/ dirs has a static resource."""
        resources = await mcp._local_provider._list_resources()
        registered_uris = {str(r.uri) for r in resources}
        missing = _EXPECTED_RESOURCES - registered_uris
        assert not missing, f"Doc files without resources: {missing}"

    @pytest.mark.asyncio
    async def test_no_extra_resources(self):
        """No stale resources pointing to non-existent doc files."""
        resources = await mcp._local_provider._list_resources()
        registered_uris = {
            str(r.uri) for r in resources
            if str(r.uri).startswith("docs://")
        }
        extra = registered_uris - _EXPECTED_RESOURCES
        assert not extra, f"Resources without doc files: {extra}"

    @pytest.mark.asyncio
    async def test_resource_count(self):
        """Sanity check: at least 20 tool docs + 3 analysis docs."""
        resources = await mcp._local_provider._list_resources()
        doc_resources = [
            r for r in resources
            if str(r.uri).startswith("docs://")
        ]
        assert len(doc_resources) >= 23

    @pytest.mark.asyncio
    async def test_resources_return_content(self):
        """Each registered doc resource returns non-empty content."""
        for uri in sorted(_EXPECTED_RESOURCES):
            resource = await mcp._local_provider.get_resource(uri)
            content = await resource.read()
            assert content, f"Empty content for {uri}"
