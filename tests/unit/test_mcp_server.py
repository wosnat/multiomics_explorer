"""P3: Tests for MCP server lifespan and KGContext — no Neo4j needed."""

from unittest.mock import MagicMock, patch

import pytest

from multiomics_explorer.mcp_server.server import KGContext, lifespan


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
