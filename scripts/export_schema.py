#!/usr/bin/env python3
"""Export the KG schema as JSON or as an LLM prompt string."""

import argparse
import json
import sys

from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.schema import load_schema_from_neo4j


def main():
    parser = argparse.ArgumentParser(description="Export KG schema")
    parser.add_argument("--format", choices=["json", "prompt"], default="json")
    args = parser.parse_args()

    conn = GraphConnection()
    if not conn.verify_connectivity():
        print("Cannot connect to Neo4j.", file=sys.stderr)
        sys.exit(1)

    schema = load_schema_from_neo4j(conn)

    if args.format == "json":
        data = {
            "nodes": {
                label: {"count": n.count, "properties": n.properties}
                for label, n in schema.nodes.items()
            },
            "relationships": {
                rt: {
                    "source_labels": r.source_labels,
                    "target_labels": r.target_labels,
                    "properties": r.properties,
                }
                for rt, r in schema.relationships.items()
            },
        }
        print(json.dumps(data, indent=2))
    else:
        print(schema.to_prompt_string())

    conn.close()


if __name__ == "__main__":
    main()
