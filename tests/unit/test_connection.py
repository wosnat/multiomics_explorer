"""P3: Tests for GraphConnection error handling and lifecycle — no Neo4j needed."""

from unittest.mock import MagicMock, patch

import pytest

from multiomics_explorer.config.settings import Settings
from multiomics_explorer.kg.connection import GraphConnection


class TestConnectionErrorHandling:
    def test_invalid_uri_raises_on_use(self):
        """Driver with an unreachable host should fail verify_connectivity gracefully."""
        settings = Settings(neo4j_uri="bolt://invalid-host-that-does-not-exist:9999")
        conn = GraphConnection(settings)
        # Inject a mock driver whose verify_connectivity raises
        mock_driver = MagicMock()
        mock_driver.verify_connectivity.side_effect = Exception("unreachable")
        conn._driver = mock_driver
        assert conn.verify_connectivity() is False

    def test_verify_connectivity_returns_false_when_down(self):
        """verify_connectivity() should return False, not raise, when Neo4j is down."""
        settings = Settings(neo4j_uri="bolt://localhost:19999")
        conn = GraphConnection(settings)
        # This will try to connect to a port nothing is listening on
        assert conn.verify_connectivity() is False

    def test_context_manager_closes_driver(self):
        """Context manager __exit__ should close the driver."""
        settings = Settings(neo4j_uri="bolt://localhost:7687")
        conn = GraphConnection(settings)
        # Inject a mock driver to verify close() is called
        mock_driver = MagicMock()
        conn._driver = mock_driver

        with conn:
            assert conn._driver is not None

        mock_driver.close.assert_called_once()
        assert conn._driver is None
