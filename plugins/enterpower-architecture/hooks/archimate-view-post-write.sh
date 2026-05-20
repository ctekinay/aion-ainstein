#!/usr/bin/env bash
# PostToolUse hook — Write tool
# When the assistant writes templates/archimate-viewer/template.jsx, syncs the file to
# the Vite work directory so HMR picks up the change automatically.
#
# Register in the host settings file (project-level) or settings.json:
#   "hooks": {
#     "PostToolUse": [{
#       "matcher": "Write",
#       "hooks": [{ "type": "command", "command": "hooks/archimate-view-post-write.sh" }]
#     }]
#   }

set -euo pipefail

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c \
  "import sys, json; print(json.load(sys.stdin).get('tool_name', ''))" 2>/dev/null || true)

[[ "$TOOL_NAME" == "Write" ]] || exit 0

FILE_PATH=$(echo "$INPUT" | python3 -c \
  "import sys, json; print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))" 2>/dev/null || true)

# Only act on writes to the archimate viewer template
[[ "$FILE_PATH" == */templates/archimate-viewer/template.jsx ]] || exit 0

WORK_DIR="$HOME/.cache/archimate-preview/project"

# Only sync if the preview is running (work dir exists and has node_modules)
[[ -d "$WORK_DIR/node_modules" ]] || exit 0

cp "$FILE_PATH" "$WORK_DIR/template.jsx"
echo "[archimate-view-post-write] synced template.jsx to preview work directory" >&2
