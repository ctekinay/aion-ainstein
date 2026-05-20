#!/usr/bin/env bash
# Stub MCP server entry point. Uses the same Python interpreter that's
# running pytest so the mcp SDK is already importable (no separate
# venv setup needed for the fixture).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON:-python3}" "$HERE/server.py"
