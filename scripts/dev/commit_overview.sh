#!/usr/bin/env bash
# commit_overview.sh — Print stable history overview for AION-AINSTEIN
#
# Usage:
#   bash scripts/dev/commit_overview.sh
#   make rollback-map   # regenerates docs/dev/rollback_map.md header
#
set -euo pipefail

echo "============================================================"
echo "AION-AINSTEIN Commit Overview"
echo "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
echo "HEAD: $(git rev-parse --short HEAD)"
echo "============================================================"
echo ""

echo "--- Full history (last 80 commits) ---"
git log --oneline --decorate -n 80
echo ""

echo "--- Key file changes (last 40 commits) ---"
echo "Files: elysia_agents.py, chat_ui.py, response_gateway.py, markdown_loader.py"
git log --name-only --oneline -n 40 -- \
    src/elysia_agents.py \
    src/chat_ui.py \
    src/response_gateway.py \
    src/loaders/markdown_loader.py
echo ""

echo "--- Routing / strictness / meta / approval commits ---"
git log --oneline --grep="route\|routing\|strict\|abstain\|meta\|approval\|dar\|follow" -n 200
echo ""

echo "--- Intent / compare / definitional commits ---"
git log --oneline --grep="intent\|compare\|definitional\|conceptual\|clarif" -n 50
echo ""

echo "============================================================"
echo "Done."
