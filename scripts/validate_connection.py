#!/usr/bin/env python3
"""Validate Neo4j connection and print basic KG statistics."""

import sys

from multiomics_explorer.kg.connection import GraphConnection


def main():
    conn = GraphConnection()

    print(f"Connecting to Neo4j at {conn._settings.neo4j_uri}...")

    if not conn.verify_connectivity():
        print("FAILED: Cannot connect to Neo4j.")
        print("Is the Docker container running? Try: docker ps | grep neo4j")
        sys.exit(1)

    print("Connected successfully!\n")

    stats = conn.get_basic_stats()
    print(f"Total nodes: {stats['total_nodes']:,}")
    print(f"Node labels ({len(stats['node_labels'])}): {', '.join(stats['node_labels'])}")
    print(f"Relationship types ({len(stats['relationship_types'])}): {', '.join(stats['relationship_types'])}")

    print("\nNode counts:")
    for label, count in sorted(stats["label_counts"].items(), key=lambda x: -x[1]):
        print(f"  {label}: {count:,}")

    conn.close()
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
