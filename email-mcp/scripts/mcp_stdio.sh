#!/usr/bin/env bash
# Cursor MCP stdio entry: resolves project root from this script (avoids broken cwd / ${workspaceFolder}).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}"
# Let email-mcp/.env (and optional env from Cursor mcp.json) control Gmail — do not force stub here.
exec "$ROOT/.venv/bin/python" -m app.mcp_server.server
