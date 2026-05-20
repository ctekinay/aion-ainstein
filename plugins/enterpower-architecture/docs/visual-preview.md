# Interactive ArchiMate Preview

The `archimate-visual-composer` skill opens a live, browser-based ArchiMate viewer via a local Vite dev server. the assistant generates the data; a fixed JSX template handles all rendering.

## Features

- ArchiMate 3.1-compliant element symbols, relation line styles, and layer colors
- Click-to-select with highlight/dim of related elements
- Side panel showing element documentation and navigable relations
- Zoom, pan, draggable elements, and layer toggle (legend as filter)
- Multi-view switcher when the model contains multiple views
- SVG export (Phase 1 — placeholder in current release)

## Trigger

After any ArchiMate model is generated or processed, the assistant will ask: _"Would you like me to open an interactive visualization of this model in the browser?"_ — unless a visualization was already requested.

You can also invoke it directly:

```
/archimate-viewer            # start or refresh the preview
/archimate-viewer stop       # stop the server
/archimate-viewer screenshot # capture the current state
```

## Setup (one-time)

```sh
cd mcp/visual-preview && npm install
```

This installs the MCP server dependencies (MCP SDK + Puppeteer). The Vite project dependencies for the viewer itself are installed automatically on first `preview_start`.
