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
        ctx = KGContext(conn=mock_conn, kg_compat_report={"verdict": "ok"})
        assert ctx.conn is mock_conn

    def test_holds_compat_report(self):
        """KGContext dataclass should store the kg_compat_report reference."""
        mock_conn = MagicMock()
        report = {"verdict": "ok", "summary": "all good"}
        ctx = KGContext(conn=mock_conn, kg_compat_report=report)
        assert ctx.kg_compat_report is report


_FAKE_REPORT = {"verdict": "ok", "summary": "KG matches", "kg": {}, "asserts": []}


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
        ), patch(
            "multiomics_explorer.mcp_server.server.kg_release_info",
            return_value=_FAKE_REPORT,
        ):
            mock_server = MagicMock()
            async with lifespan(mock_server) as ctx:
                assert isinstance(ctx, KGContext)
                assert ctx.conn is mock_conn
                assert ctx.kg_compat_report is _FAKE_REPORT

            mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_compat_report_cached_on_context(self):
        """Lifespan should cache the kg_release_info report on KGContext."""
        mock_conn = MagicMock()
        mock_conn.verify_connectivity.return_value = True
        custom_report = {"verdict": "warn", "summary": "minor mismatch", "kg": {}, "asserts": []}

        with patch(
            "multiomics_explorer.mcp_server.server.GraphConnection",
            return_value=mock_conn,
        ), patch(
            "multiomics_explorer.mcp_server.server.get_settings",
            return_value=MagicMock(),
        ), patch(
            "multiomics_explorer.mcp_server.server.kg_release_info",
            return_value=custom_report,
        ):
            async with lifespan(MagicMock()) as ctx:
                assert ctx.kg_compat_report["verdict"] == "warn"

    @pytest.mark.asyncio
    async def test_compat_report_falls_back_on_exception(self):
        """Lifespan should cache a fallback report when kg_release_info raises."""
        mock_conn = MagicMock()
        mock_conn.verify_connectivity.return_value = True

        with patch(
            "multiomics_explorer.mcp_server.server.GraphConnection",
            return_value=mock_conn,
        ), patch(
            "multiomics_explorer.mcp_server.server.get_settings",
            return_value=MagicMock(),
        ), patch(
            "multiomics_explorer.mcp_server.server.kg_release_info",
            side_effect=RuntimeError("boom"),
        ), patch(
            "multiomics_explorer.mcp_server.server._get_explorer_version",
            return_value="0.0.0",
        ):
            async with lifespan(MagicMock()) as ctx:
                assert ctx.kg_compat_report["verdict"] == "unknown"
                assert "boom" in ctx.kg_compat_report["summary"]

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
_EXPECTED_GUIDE_RESOURCES = {
    f"docs://guide/{p.stem}" for p in (_SKILLS_DIR / "guide").glob("*.md")
}
# Example scripts served explicitly (not auto-discovered from .md files)
_EXPECTED_EXAMPLE_RESOURCES = {
    "docs://examples/pathway_enrichment.py",
    "docs://examples/metabolites.py",
}
_EXPECTED_RESOURCES = (
    _EXPECTED_TOOL_RESOURCES
    | _EXPECTED_ANALYSIS_RESOURCES
    | _EXPECTED_GUIDE_RESOURCES
    | _EXPECTED_EXAMPLE_RESOURCES
)


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
