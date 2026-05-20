#!/usr/bin/env bash
# PostToolUse hook for the e2e test. Captures the stdin payload to the
# path in $WRITE_LOG so the test can verify the hook fired with the
# correct {tool_name, tool_input: {file_path}} structure.
#
# $WRITE_LOG is set by the test via the hooks config's env passthrough.
# Falls back to a noop if WRITE_LOG isn't set (manual smoke testing).
set -euo pipefail

INPUT=$(cat)

if [[ -n "${WRITE_LOG:-}" ]]; then
    echo "$INPUT" > "$WRITE_LOG"
fi
