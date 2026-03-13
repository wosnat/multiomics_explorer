"""Neo4j connection management."""

import threading
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from multiomics_explorer.config.settings import Settings, get_settings


class GraphConnection:
    """Manages Neo4j driver lifecycle and query execution."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._driver = None
        self._lock = threading.Lock()

    @property
    def driver(self):
        if self._driver is None:
            with self._lock:
                if self._driver is None:
                    self._driver = GraphDatabase.driver(
                        self._settings.neo4j_uri,
                        auth=self._settings.neo4j_auth,
                    )
        return self._driver

    def verify_connectivity(self) -> bool:
        """Check if Neo4j is reachable. Returns True if connected."""
        try:
            self.driver.verify_connectivity()
            return True
        except (ServiceUnavailable, AuthError):
            return False

    def execute_query(self, cypher: str, **params: Any) -> list[dict]:
        """Execute a read-only Cypher query and return results as list of dicts."""
        with self.driver.session() as session:
            result = session.execute_read(
                lambda tx: tx.run(cypher, **params).data()
            )
            return result

    def get_labels(self) -> list[str]:
        """Get all node labels in the graph."""
        result = self.execute_query("CALL db.labels() YIELD label RETURN label ORDER BY label")
        return [r["label"] for r in result]

    def get_relationship_types(self) -> list[str]:
        """Get all relationship types in the graph."""
        result = self.execute_query(
            "CALL db.relationshipTypes() YIELD relationshipType "
            "RETURN relationshipType ORDER BY relationshipType"
        )
        return [r["relationshipType"] for r in result]

    def get_property_keys(self) -> list[str]:
        """Get all property keys used in the graph."""
        result = self.execute_query(
            "CALL db.propertyKeys() YIELD propertyKey RETURN propertyKey ORDER BY propertyKey"
        )
        return [r["propertyKey"] for r in result]

    def get_node_count(self, label: str | None = None) -> int:
        """Get count of nodes, optionally filtered by label."""
        if label:
            result = self.execute_query(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
        else:
            result = self.execute_query("MATCH (n) RETURN count(n) AS cnt")
        return result[0]["cnt"]

    def get_basic_stats(self) -> dict:
        """Get basic graph statistics."""
        labels = self.get_labels()
        rel_types = self.get_relationship_types()
        total_nodes = self.get_node_count()

        label_counts = {}
        for label in labels:
            label_counts[label] = self.get_node_count(label)

        return {
            "total_nodes": total_nodes,
            "node_labels": labels,
            "label_counts": label_counts,
            "relationship_types": rel_types,
        }

    def close(self):
        """Close the driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
