// Vite configuration for the archimate-viewer template project.
//
// PURPOSE: Configures the local dev server used to serve the interactive
// ArchiMate viewer during an AInstein session.
//
// LOCATION — templates/archimate-viewer/
// Copied verbatim to ~/.cache/archimate-preview/project/ by the MCP server
// alongside template.jsx, main.jsx, index.html, and package.json.
//
// PORT: 5173 is fixed. The MCP server constant PREVIEW_URL in
// mcp/visual-preview/src/index.ts must match this value.
//
// RELATIONS
// - Used by:     mcp/visual-preview/src/index.ts (startVite)
// - Registered:  .mcp.json → "preview" server

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
})
