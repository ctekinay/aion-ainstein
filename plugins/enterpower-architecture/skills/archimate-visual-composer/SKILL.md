---
name: archimate-visual-composer
description: "Composes VIEWS data from an ArchiMate Open Exchange XML model and opens it in the interactive browser viewer via the preview MCP server. Use this skill when the user wants to display, visualize, or explore an ArchiMate model in the browser."
allowed-tools:
  - mcp__preview__preview_start
  - mcp__preview__preview_update
---

# Skill: archimate-visual-composer

Generates an interactive ArchiMate visualization in the browser using the fixed reference template and the `preview` MCP server.

---

## When to use this skill

Use `archimate-visual-composer` when the user wants to **display or explore** a model in the browser:
- "show me the architecture", "visualize this model", "open in browser", "interactive viewer"
- "open the viewer", "see the model", "display the ArchiMate diagram", "explore the architecture"
- References an ArchiMate Open Exchange XML file AND wants to view, show, or explore it

**Do NOT use for these — use a different skill instead:**
- "add a view", "create a new diagram in the model", "add a viewpoint" → use `archimate-oxc-view-generator` (modifies the XML model structure)
- "generate an ArchiMate model" → use `archimate-oxc-generator` (creates model from text/docs)
- "analyze this repo and generate ArchiMate" → use `repo-to-archimate`

---

## Always offer visualization

After any ArchiMate model is generated or processed — by this skill, `archimate-oxc-generator`, or `archimate-oxc-view-generator` — **always ask the user whether they want an interactive visualization**, unless:

- The user's current message already explicitly requests a visualization or preview, or
- A preceding instruction in the same task already called for one.

Ask exactly once, concisely: _"Would you like me to open an interactive visualization of this model in the browser?"_

---

## Workflow

### Step 1 — Ensure data source

Require an ArchiMate Open Exchange XML model. If none is available:
- Coordinate with `archimate-oxc-generator` to produce one, or
- Ask the user to provide the XML.

### Step 2 — Detect existing views and ask the user

Scan the XML for `<diagram:ArchimateDiagramModel>` elements. Then:

**If no views exist:** skip to Step 3 with a single auto-generated layered view.

**If one or more views exist:** ask the user two questions before proceeding:

> **Question (a) — Which views to show?**
> The model contains the following views:
> - `<view name>` (N nodes)
> - …
>
> Options:
> 1. Show one or more of these existing views (specify which)
> 2. Create a new custom visualization instead (specify focus or viewpoint)
> 3. Show all existing views

> **Question (b) — Layout source?** *(only if the user chose existing views in (a))*
> For each selected view:
> 1. **Use the existing layout** — preserve x/y/w/h positions exactly as stored in the XML
> 2. **Recompute layout** — ignore XML positions and apply the skill's layout rules

Wait for the user's answers before continuing.

### Step 3 — Parse the XML

Extract from the XML:
- **Elements:** `identifier`, `xsi:type` (strip namespace prefix), `name`, `documentation`
- **Relations:** `identifier`, `source`, `target`, `xsi:type` (strip namespace prefix)
- **Views:** only the views selected in Step 2

If generating a new custom view, determine which elements to include based on the user's focus or viewpoint.

### Step 4 — Map to VIEWS format

Convert parsed data to the `VIEWS` object (see **Data format** below).

**If using existing layout (Step 2b option 1):**
Read `x`, `y`, `w`, `h` directly from each `<node>` element inside the view in the XML:
```xml
<node identifier="id-n-xxx" elementRef="elem-id" x="120" y="200" w="160" h="55"/>
```
Use these values as-is. Do not apply the layout rules below.

**If recomputing layout (Step 2b option 2) or generating a new view:**
Compute `x`, `y`, `w`, `h` for every element following the **Layout rules** below.

### Step 5 — Call `preview_start` or `preview_update`

**If the preview server is not yet running** (first call in the session):
```
mcp__preview__preview_start({ code: "const VIEWS = { ... };" })
```
The MCP server starts Vite, opens the browser automatically, and returns the URL. Share the URL with the user.

**If the preview server is already running** (subsequent calls):
```
mcp__preview__preview_update({ code: "const VIEWS = { ... };" })
```
Vite HMR pushes the new data to the browser page if it is open. After calling this, always ask the user:

> "The diagram has been updated. Do you see it in your browser at **http://localhost:5173**? If you closed that tab, let me know and I will reopen it for you."

If the user confirms the browser tab is closed or not visible, call `preview_start` (not `preview_update`) — this reopens the browser page automatically.

### Step 6 — Iterate

If the user requests changes (add element, adjust layout, switch view):
- Update the `VIEWS` data only
- Call `mcp__preview__preview_update({ code: "const VIEWS = { ... };" })`
- Follow the notification instruction from Step 5 above

### Step 7 — Deliver

Provide the localhost URL. Offer to also export the ArchiMate XML as a downloadable file if not already done.

---

## Data format

the assistant's only output is the `VIEWS` object. The template rendering logic is fixed and must never be modified.

```typescript
type LayerKey = "motivation" | "strategy" | "business" | "application" | "technology";

type ElementData = {
  id: string;       // Unique short identifier, e.g. "ba1", "ac3"
  name: string;     // Display name from XML
  type: ElementType;// Exact ArchiMate type string — see table below
  layer: LayerKey;  // Derived from element type — see table below
  x: number;        // Canvas X coordinate
  y: number;        // Canvas Y coordinate
  w: number;        // Width — see layout rules
  h: number;        // Height — see layout rules
  doc: string;      // Documentation from XML, empty string if absent
};

type RelationData = {
  from: string;     // Source element id
  to: string;       // Target element id
  type: RelationType; // Exact relation type string — see table below
};

type ViewData = {
  label: string;          // Human-readable view name
  elements: ElementData[];
  relations: RelationData[];
};

type Views = Record<string, ViewData>;
```

---

## Element types, layer keys, and relation types

**Before generating any `VIEWS` data, read:**
`../../shared-references/archimate-shared/archim-3.2-visualization-mapping.md`

That file defines which ArchiMate element types the viewer supports, how they map to viewer layer keys (`motivation`, `strategy`, `business`, `application`, `technology`), and which relation types are rendered. Do not proceed without reading it.

---

## Layout rules

### Layer band Y positions

Place bands top to bottom in this order: Motivation → Strategy → Business → Application → Technology.

Compute band positions dynamically: each band starts 60px below the bottom of the previous band. Seed the first band at y = 20.

| Layer | Approximate starting Y (single-row band) |
|---|---|
| motivation | 20 |
| strategy | ~160 |
| business | ~280 |
| application | ~560 |
| technology | ~720 |

Adjust downstream bands upward or downward when a band is absent or unusually tall.

### Element placement within a band

- Place elements left-to-right with a **20px horizontal gap**.
- Wrap to the next row when accumulated width exceeds **960px**; row-to-row gap: **16px**.
- All elements in the same row share the same `y` value.

### Element dimensions

| Element category | Default w | Default h |
|---|---|---|
| Most elements | 160 | 48 |
| Short name (≤ 12 chars) | 120 | 48 |
| Long name (> 28 chars) | 200–220 | 54 |
| `BusinessObject`, `DataObject`, `Artifact` | 120 | 44 |
| `Node`, `ApplicationComponent` | 170 | 52 |

### Large models (50+ elements)

For models with 50 or more elements, note in the response that auto-layout via `dagre` or `elkjs` is recommended and that the MCP server can be configured to apply it. Provide best-effort manual layout in the interim.

---

## Prohibitions

- **Never** modify `LAYER`, `REL_STYLES`, `MarkerDefs`, `ArchiIcon`, or any rendering logic in `template.jsx`.
- **Never** add inline styles or custom rendering attributes to individual elements.
- **Never** add imports or dependencies to the template beyond what is already present.
- Only populate the `VIEWS` data structure.
