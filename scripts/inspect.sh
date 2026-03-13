#!/usr/bin/env bash
# Launch the MCP Inspector for the multiomics-kg server.
#
# Usage:
#   ./scripts/inspect.sh             # debug mode (shows Cypher in responses)
#   ./scripts/inspect.sh --nodebug   # without Cypher queries in responses

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

export DEBUG_QUERIES=true
for arg in "$@"; do
    if [[ "$arg" == "--nodebug" ]]; then
        unset DEBUG_QUERIES
    fi
done

if [[ -n "${DEBUG_QUERIES:-}" ]]; then
    echo "Debug mode: Cypher queries will appear in tool responses"
fi

exec npx @modelcontextprotocol/inspector \
    uv run --directory "$PROJECT_DIR" multiomics-kg-mcp
