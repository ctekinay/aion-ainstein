// Vite entry point for the archimate-viewer template project.
//
// PURPOSE: Mounts the ArchiMateViewer component from template.jsx into the
// browser DOM. Required by Vite — index.html loads this file as the module entry.
//
// LOCATION — templates/archimate-viewer/
// Part of the self-contained Vite project that the MCP server copies to
// ~/.cache/archimate-preview/project/ before starting the dev server.
// This file is copied verbatim; it is not modified during VIEWS injection
// (only template.jsx receives data injection).
//
// RELATIONS
// - Loaded by:   templates/archimate-viewer/index.html
// - Renders:     templates/archimate-viewer/template.jsx (ArchiMateViewer)
// - Managed by:  mcp/visual-preview/src/index.ts (syncTemplateFiles)

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import ArchiMateViewer from './template.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ArchiMateViewer />
  </StrictMode>,
)
