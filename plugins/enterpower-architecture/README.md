# enterpower-architecture

**Enterprise Power — Architecture Plugin**

An AInstein plugin providing enterprise-grade architectural capabilities through a curated set of skills. It covers the full range from solution-level architecture up to enterprise-level governance.

## What this plugin does

Once loaded into a compatible AI ecosystem, it enriches the assistant with specialized skills for enterprise architecture work: generating ArchiMate models, authoring and assessing architecture principles, analyzing repositories, and opening interactive architecture visualizations directly in the browser.

## Skills

| Skill | Description |
|---|---|
| **archimate-oxc-generator** | Generates valid ArchiMate 3.2 OXC (Open Exchange) XML models from unstructured input (ADRs, architecture descriptions, code reviews, project documents). |
| **archimate-oxc-view-generator** | Produces views (diagrams) with correct layout conventions and fragment format for an existing ArchiMate 3.2 OXC (Open Exchange) model. |
| **archimate-visual-composer** | Composes an interactive browser visualization from an ArchiMate model. Clickable elements, side panel, zoom/pan, layer filtering, and SVG export. |
| **archimate-viewer** | User-invocable skill (`/archimate-viewer`) to start, update, or stop the interactive browser viewer. |
| **archimate-tools** | Validates, inspects, and merges ArchiMate 3.2 Open Exchange XML models. |
| **principle-generator** | Generates high-quality architecture and enterprise principles following a TOGAF-aligned template and quality gate. |
| **principle-quality-assessor** | Assesses an existing principle against quality criteria and produces concrete improvement recommendations. |
| **repo-to-archimate** | Analyses a software repository and converts its architecture into an ArchiMate 3.2 model via a structured pipeline. |
| **repo-architecture-explorer** | Turns a repository analysis YAML into a self-contained interactive HTML explorer with module browsing, dependency navigation, and drill-down. |

## Slash commands

| Command | What it does |
|---|---|
| `/archimate-oxc-generator` | Generate an ArchiMate 3.2 Open Exchange XML model from unstructured input |
| `/archimate-oxc-view-generator` | Add a new view or diagram to an existing Open Exchange XML model |
| `/archimate-tools validate` | Validate an Open Exchange XML model against the ArchiMate 3.2 specification |
| `/archimate-tools inspect` | Summarise elements, relationships, views, and statistics |
| `/archimate-tools merge` | Merge a view fragment into an existing model |
| `/principle-generator` | Generate a new architecture or enterprise principle |
| `/principle-quality-assessor` | Assess the quality of an existing principle and suggest improvements |
| `/repo-to-archimate` | Analyse a software repository and generate an ArchiMate 3.2 Open Exchange XML model |
| `/archimate-viewer` | Start or refresh the interactive browser viewer |
| `/archimate-viewer stop` | Stop the preview server |
| `/archimate-viewer screenshot` | Capture the current viewer state |

The remaining skills (`archimate-visual-composer`, `repo-architecture-explorer`) are activated automatically by context — no slash command needed.

## Interactive preview

The `archimate-visual-composer` skill composes `VIEWS` data from an ArchiMate model and opens it in a live browser viewer. The `archimate-viewer` skill (`/archimate-viewer`) lets you start, stop, or screenshot the viewer directly. See [docs/visual-preview.md](docs/visual-preview.md) for features, usage, and setup.

## References

Shared reference material is stored under `shared-references/` and `skills/*/references/`:

**`shared-references/`**
- `archim-3.2-element-types.md` — valid ArchiMate 3.2 element types per layer
- `archim-3.2-allowed-relations.md` — allowed relationship combinations and cross-layer rules
- `archim-3.2-visualization-mapping.md` — element and relation mapping for the interactive viewer
- `archim-3.2-visual-shaping.md` — standard element shapes and layer colors per the ArchiMate 3.2 specification
- `archim-oxc-3.1-xml-template.md` — ArchiMate Open Exchange 3.1 XML template

**`skills/*/references/`** — skill-local material (view layout conventions, classification rules, explorer template)

## Plugin structure

```
.ainstein-plugin/
  plugin.json              # AInstein plugin manifest (name, runtime, role, version)
  skills-registry.yaml     # Registry — which skills are enabled and how
  thresholds.yaml          # RAG, quality-gate, and agent tuning parameters
.mcp.json                  # MCP server registration (preview server)
docs/
  design-documents/            # Historical design specs and reference artefacts
    developer-spec-interactive-preview-plugin.md
    archimate-viewer-template.jsx
  visual-preview.md            # Interactive viewer features and usage
hooks/
  archimate-view-post-write.sh  # PostToolUse hook — syncs template writes to Vite work dir
mcp/
  visual-preview/            # MCP server (Node.js/TypeScript)
    src/index.ts             # preview_start, preview_update, preview_screenshot, preview_stop
    package.json
    tsconfig.json
shared-references/           # Shared ArchiMate reference material
skills/
  <skill-name>/
    SKILL.md                 # Skill instructions injected into the AI prompt
    references/              # Supporting reference material for the skill
    scripts/                 # Helper scripts (validation, inspection, layout)
  archimate-viewer/
    SKILL.md                 # /archimate-viewer user-invocable skill
templates/
  archimate-viewer/          # Fixed JSX reference template (data-only, never modify rendering)
    template.jsx             # ArchiMate viewer component
    main.jsx                 # React entry point
    index.html               # Vite HTML entry
    package.json             # React + Vite dependencies
    vite.config.js           # Vite configuration (port 5173)
```

## Integration

Loaded by AInstein from `plugins/`: the `.ainstein-plugin/` skills
registry and YAML configuration are consumed by the agent framework; the
MCP preview server and the PostToolUse hook are wired via `.mcp.json` and
`hooks/hooks.json` using the `${AINSTEIN_PLUGIN_ROOT}` substitution.

## Authors

Robert-Jan Peters
Laurent van Groningen
Cagri Tekinay

## Version

0.2.1
