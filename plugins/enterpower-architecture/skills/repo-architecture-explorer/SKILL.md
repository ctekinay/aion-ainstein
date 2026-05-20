---
name: repo-architecture-explorer
description: "Generate interactive HTML architecture explorer from repo analysis YAML"
---

# Repo Architecture Explorer Skill

Generate a single self-contained `.html` file that turns a YAML architecture notes
document into a rich, interactive explorer. The output is a tiered module browser
with class/method drill-down, clickable dependency navigation, and a JSON export button.

## When to Use

- User uploads or pastes a YAML file with `type: architecture_notes`
- User asks to visualize, explore, or navigate a repo analysis output
- User wants to understand module dependencies, class structures, or system topology
- User references output from AInstein's RepoAnalysisAgent or any tool producing
  the same YAML schema (components, edges, key_classes, methods)

## Input Format

The skill expects YAML with this structure (all fields are optional except `components`):

```yaml
type: architecture_notes
meta:
  repo_name: <string>
  branch: <string>
summary:
  repo_name: <string>
  total_components: <int>
  total_files_analyzed: <int>
  tech_stack: [<string>, ...]
components:
  - id: <string>
    name: <string>
    type: <string>
    path: <string>
    source: <string>
    role: <string>
    language: <string>
    key_classes:
      - name: <string>
        bases: [<string>, ...]
        methods: [<string>, ...]
        collaborators: [<string>, ...]
edges:
  - from: <string>
    to: <string>
    relation: <string>
    evidence: <string>
deployment:
  containerized: <bool>
  orchestration: <string>
```

## Process

### 1. Parse the YAML

Read the uploaded YAML file. Extract:
- `meta` and `summary` for the header stats
- `components` array for module cards and class detail
- `edges` array for per-module dependency edge display
- `deployment` for infrastructure context

If the YAML is provided inline in the conversation (not as a file), extract it the same way.

### 2. Classify Components into Tiers

Auto-classify each component into a tier using these heuristics (in priority order):

| Signal | Tier |
|--------|------|
| `source: docker-compose` or `type: infrastructure` or name matches common infra (weaviate, postgres, redis, kafka, elasticsearch, rabbitmq, nginx, minio) | **Infrastructure** |
| Path or name contains `agent` | **Agents** |
| Path or name contains `ingest`, `chunk`, `load`, `etl`, `pipeline`, `parse` | **Data pipeline** |
| Path or name contains `diagnostic`, `eval`, `test`, `mcp`, `monitor`, `metric` | **Support** |
| Everything else | **Core services** |

These are defaults. If the user specifies custom tier assignments, respect those instead.

### 3. Read the Reference Template

Before writing any HTML, read `references/EXPLORER_TEMPLATE.md`. It contains the
complete HTML template with the CSS design system and JavaScript logic. Follow it
closely -- it is the difference between a polished deliverable and a broken page.

### 4. Generate the HTML

Build a single `.html` file by:

1. Embedding the parsed data as a `const DATA = { ... }` JSON object in a `<script>` tag
2. Embedding the tier classification as `const TIERS = [ ... ]`
3. Including all CSS and JS inline (no external dependencies)
4. Setting the page title from `meta.repo_name` or `summary.repo_name`

### 5. Apply Branding (Optional)

The default palette is neutral (purple/teal/coral/gray from the design system).
If the user requests specific branding, override the CSS custom properties:

```
--brand-primary: <color>;
--brand-secondary: <color>;
--brand-accent: <color>;
```

For Alliander branding specifically, use:
```
--brand-primary: #00A94F (Alliander green)
--brand-secondary: #1D3557 (Alliander navy)
--brand-accent: #F4A261 (warm accent)
```

Only apply branding if the user explicitly requests it. The neutral palette works
for any organization.

### 6. Save and Present

The HTML output is automatically saved as an artifact in the conversation. No
additional save step is needed — the generation pipeline handles artifact storage
and presents a download card to the user.

## Features

Every generated explorer must include:

1. **Stats row**: Summary metrics (module count, edge count, files analyzed, class
   count, tech stack, orchestration) displayed as compact stat cards at the top.
2. **Tiered module browser**: Components grouped by auto-classified tier (Agents,
   Core, Data Pipeline, Support, Infrastructure). Each module is a clickable card
   showing name and class count, with a colored left border indicating its tier.
3. **Detail panel**: When a module card is clicked, a detail panel shows:
   - Header with module name, file path, language badge, and role badge
   - Dependencies section with clickable edge pills (inbound in green, outbound
     in coral). Each pill shows "source -> target" and has a tooltip with the
     import evidence string. Clicking a pill navigates to that module.
   - Key classes as an expandable list. Each class shows its name, base classes
     (italic), and method count. Clicking a class toggles a drawer listing all
     methods in monospace.
   - Collaborators section (union across all classes in the module).
4. **Export button**: Downloads the full parsed architecture data as a JSON file.

## Quality Criteria

- All data from the YAML must be represented -- no dropped components or edges
- Dark mode support via `prefers-color-scheme` media query
- No external dependencies (fonts, CDN, etc.) -- fully self-contained
- Responsive down to 768px viewport width
- Edge pill tooltips must show the `evidence` field from the YAML edges
