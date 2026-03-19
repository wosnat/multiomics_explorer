#!/usr/bin/env bash
# Launch the MCP Inspector for the multiomics-kg server.
#
# Usage:
#   ./scripts/inspect.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

exec env LOG_LEVEL=DEBUG npx @modelcontextprotocol/inspector \
    uv run --directory "$PROJECT_DIR" multiomics-kg-mcp
