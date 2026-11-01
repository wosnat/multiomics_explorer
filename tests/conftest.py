"""Shared fixtures for tests.

Integration tests connecting to Neo4j are marked with @pytest.mark.kg
and auto-skip if Neo4j is not reachable. The connection resolves like the
MCP server's: NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD from env or .env
(default bolt://localhost:7687, no auth); --neo4j-url overrides the URI.
"""

import pytest
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable


def pytest_addoption(parser):
    parser.addoption(
        "--neo4j-url",
        default=None,
        help="Bolt URL for the Neo4j instance (default: NEO4J_URI from "
        "env / .env, else bolt://localhost:7687)",
    )


@pytest.fixture(scope="session")
def neo4j_driver(request):
    """Neo4j driver fixture. Skips test if Neo4j is unreachable."""
    from multiomics_explorer.config.settings import Settings

    settings = Settings()
    url = request.config.getoption("--neo4j-url") or settings.neo4j_uri
    try:
        driver = GraphDatabase.driver(url, auth=settings.neo4j_auth)
        driver.verify_connectivity()
    except (ServiceUnavailable, Exception) as e:
        pytest.skip(f"Neo4j not available at {url}: {e}")
        return
    yield driver
    driver.close()


@pytest.fixture(scope="session")
def run_query(neo4j_driver):
    """Helper: run a Cypher query and return results as list of dicts."""
    def _run(cypher, **params):
        with neo4j_driver.session() as session:
            return session.run(cypher, **params).data()
    return _run


@pytest.fixture(scope="session")
def kg_count(run_query):
    """Live scalar from the KG, for count assertions that must never be
    pinned to a literal (paper batches flip them). The query must RETURN
    exactly one row with one column."""
    def _count(cypher, **params):
        rows = run_query(cypher, **params)
        assert len(rows) == 1, f"kg_count expects one row, got {len(rows)}"
        return next(iter(rows[0].values()))
    return _count


@pytest.fixture(scope="session")
def conn(neo4j_driver):
    """GraphConnection wrapping the session-scoped neo4j_driver."""
    from multiomics_explorer.config.settings import Settings
    from multiomics_explorer.kg.connection import GraphConnection

    settings = Settings()
    connection = GraphConnection(settings)
    connection._driver = neo4j_driver
    yield connection
