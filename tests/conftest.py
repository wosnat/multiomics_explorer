"""Shared fixtures for tests.

Integration tests connecting to Neo4j are marked with @pytest.mark.kg
and auto-skip if Neo4j is not reachable.
"""

import pytest
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable


def pytest_addoption(parser):
    parser.addoption(
        "--neo4j-url",
        default="bolt://localhost:7687",
        help="Bolt URL for the Neo4j instance (default: bolt://localhost:7687)",
    )


@pytest.fixture(scope="session")
def neo4j_driver(request):
    """Neo4j driver fixture. Skips test if Neo4j is unreachable."""
    url = request.config.getoption("--neo4j-url")
    try:
        driver = GraphDatabase.driver(url, auth=None)
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
