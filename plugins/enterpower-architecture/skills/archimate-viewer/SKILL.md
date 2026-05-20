---
name: archimate-viewer
description: Start, update, or stop the interactive ArchiMate viewer in the browser
allowed-tools:
  - mcp__preview__preview_start
  - mcp__preview__preview_update
  - mcp__preview__preview_stop
  - mcp__preview__preview_screenshot
---

Manage the interactive ArchiMate viewer preview. Requires an ArchiMate Open Exchange XML model — use `archimate-oxc-generator` or `archimate-oxc-view-generator` first if none is available.

**Usage**

- `/archimate-viewer` — generate VIEWS data from the current model and open the browser preview
- `/archimate-viewer stop` — stop the preview server
- `/archimate-viewer screenshot` — take a screenshot of the current state for verification

**What this does**

1. Reads the available ArchiMate XML model (or asks for one)
2. Parses elements, relations, and views into the `VIEWS` data structure
3. Calls `preview_start` (or `preview_update` if already running) with the VIEWS data
4. Opens the viewer at `http://localhost:5173`

The viewer is read-only — it renders fixed ArchiMate symbols, layer colors, and relation styles from the reference template. Only the data changes.

**Arguments**

`$ARGUMENTS`
