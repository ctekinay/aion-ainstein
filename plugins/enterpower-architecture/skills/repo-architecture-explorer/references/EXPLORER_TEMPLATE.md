# Explorer Template Reference

This is the definitive reference for generating repo architecture explorer HTML files.
Follow this template closely. The output is a single self-contained `.html` file with
a tiered module browser, class/method drill-down, and JSON export.

## Document Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{REPO_NAME} Architecture Explorer</title>
  <style>/* all CSS here */</style>
</head>
<body>
  <!-- stats row -->
  <!-- export button -->
  <!-- tiered module cards -->
  <!-- detail panel -->
  <script>/* all JS here */</script>
</body>
</html>
```

## CSS Design System

### Color Palette (Neutral Default)

Use CSS custom properties so branding can be overridden in one place.

```css
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f8f7f4;
  --bg-tertiary: #f1efe8;
  --text-primary: #2c2c2a;
  --text-secondary: #5f5e5a;
  --text-tertiary: #888780;
  --border-light: rgba(0,0,0,0.08);
  --border-medium: rgba(0,0,0,0.15);
  --radius-md: 8px;
  --radius-lg: 12px;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: "SF Mono", "Fira Code", "Consolas", monospace;

  /* Tier colors */
  --color-core: #534AB7;
  --color-core-bg: #EEEDFE;
  --color-agent: #0F6E56;
  --color-agent-bg: #E1F5EE;
  --color-data: #D85A30;
  --color-data-bg: #FAECE7;
  --color-support: #888780;
  --color-support-bg: #F1EFE8;
  --color-infra: #3B8BD4;
  --color-infra-bg: #E6F1FB;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg-primary: #1a1a18;
    --bg-secondary: #242422;
    --bg-tertiary: #2c2c2a;
    --text-primary: #e8e6dd;
    --text-secondary: #b4b2a9;
    --text-tertiary: #888780;
    --border-light: rgba(255,255,255,0.08);
    --border-medium: rgba(255,255,255,0.15);
    --color-core: #AFA9EC;
    --color-core-bg: #3C3489;
    --color-agent: #5DCAA5;
    --color-agent-bg: #085041;
    --color-data: #F0997B;
    --color-data-bg: #712B13;
    --color-support: #B4B2A9;
    --color-support-bg: #444441;
    --color-infra: #85B7EB;
    --color-infra-bg: #0C447C;
  }
}
```

### Typography and Base

```css
* { margin: 0; box-sizing: border-box; }
body {
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-primary);
  background: var(--bg-primary);
  padding: 20px;
  max-width: 960px;
  margin: 0 auto;
}
```

### Component Styles

#### Stats Row

A row of metric cards at the top. Shows module count, edge count, files analyzed,
class count, tech stack, and orchestration type.

```css
.stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.stat-card {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  min-width: 80px;
}
.stat-val { font-size: 20px; font-weight: 500; }
.stat-label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
```

For non-numeric stat values (tech stack, orchestration), use `font-size: 14px`
on the value instead of 20px.

#### Export Button

Sits right-aligned below the stats row.

```css
.toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}
.export-btn {
  padding: 6px 14px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-md);
  border: 0.5px solid var(--border-medium);
  background: none;
  transition: background 0.15s;
  font-family: inherit;
}
.export-btn:hover { background: var(--bg-secondary); }
```

#### Tier Labels and Module Cards

```css
.tier-label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 16px 0 6px;
}
.mod-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.mod-card {
  background: var(--bg-secondary);
  border: 0.5px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 8px 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  min-width: 90px;
  border-left-width: 2px;
  border-left-style: solid;
}
.mod-card:hover { border-color: var(--border-medium); }
.mod-card.active { border-color: var(--border-medium); }
.mod-name { font-weight: 500; font-size: 13px; }
.mod-sub { font-size: 11px; color: var(--text-secondary); margin-top: 2px; }
```

Each card's `border-left-color` is set via JS to match its tier color.
When active, the card's `background` is set to the tier's bg color.

#### Detail Panel

Appears below the module cards when one is selected.

```css
.detail-panel {
  margin-top: 16px;
  border: 0.5px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  min-height: 100px;
}
.dp-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.dp-title { font-weight: 500; font-size: 16px; }
.dp-path {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}
.dp-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}
.dp-section { margin-bottom: 12px; }
.dp-section-title {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}
```

#### Edge Pills

Show dependencies. Inbound edges (other modules depending on this one) get a
green left border. Outbound edges (this module depends on another) get a coral
left border. Each pill is clickable and navigates to the target module.

```css
.dp-edges { display: flex; flex-wrap: wrap; gap: 4px; }
.edge-pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-secondary);
  border: 0.5px solid var(--border-light);
  cursor: pointer;
  transition: border-color 0.15s;
}
.edge-pill:hover { border-color: var(--border-medium); }
.edge-pill.in { border-left: 2px solid var(--color-agent); }
.edge-pill.out { border-left: 2px solid var(--color-data); }
```

The pill's `title` attribute should contain the edge's `evidence` string from
the YAML so users can see the import statement on hover.

#### Class List and Method Drawers

```css
.class-list { list-style: none; padding: 0; margin: 0; }
.class-item {
  font-size: 12px;
  padding: 6px 0;
  border-bottom: 0.5px solid var(--border-light);
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.class-item:last-child { border: none; }
.class-item:hover { color: var(--color-core); }
.cl-name { font-family: var(--font-mono); font-weight: 500; }
.cl-bases {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-left: 6px;
  font-style: italic;
}
.cl-methods-count {
  color: var(--text-tertiary);
  font-size: 11px;
  white-space: nowrap;
}
.method-drawer {
  padding: 4px 0 4px 16px;
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  display: none;
  line-height: 1.8;
}
.method-drawer.open { display: block; }
```

#### Utility

```css
.empty-state {
  font-size: 13px;
  color: var(--text-tertiary);
  padding: 24px 0;
  text-align: center;
}
@media (max-width: 768px) {
  .stats-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
}
```

## JavaScript Architecture

### 1. Data Embedding

The model embeds the parsed YAML as two constants at the top of the script:

```javascript
const DATA = {
  meta: { repo_name: "...", branch: "..." },
  summary: { total_components: N, total_files_analyzed: N, tech_stack: [...] },
  components: [
    {
      name: "...",
      type: "...",
      path: "...",
      source: "...",
      role: "...",
      language: "...",
      key_classes: [
        { name: "...", bases: [...], methods: [...], collaborators: [...] }
      ]
    }
  ],
  edges: [ { from: "...", to: "...", relation: "...", evidence: "..." } ],
  deployment: { containerized: true, orchestration: "..." }
};

const TIERS = [
  { label: "Agents", ids: ["agents"], color: "agent" },
  { label: "Core services", ids: ["aion", "skills", ...], color: "core" },
  { label: "Data pipeline", ids: ["ingestion", ...], color: "data" },
  { label: "Support", ids: ["diagnostics", ...], color: "support" },
  { label: "Infrastructure", ids: ["weaviate", ...], color: "infra" }
];
```

### 2. Tier Color Mapping

```javascript
const TIER_COLORS = {
  core:    { color: 'var(--color-core)',    bg: 'var(--color-core-bg)' },
  agent:   { color: 'var(--color-agent)',   bg: 'var(--color-agent-bg)' },
  data:    { color: 'var(--color-data)',    bg: 'var(--color-data-bg)' },
  support: { color: 'var(--color-support)', bg: 'var(--color-support-bg)' },
  infra:   { color: 'var(--color-infra)',   bg: 'var(--color-infra-bg)' }
};

// Build lookups
const moduleMap = {};
DATA.components.forEach(c => { moduleMap[c.name] = c; });

const tierOfModule = {};
TIERS.forEach(t => t.ids.forEach(id => { tierOfModule[id] = t.color; }));
```

### 3. Rendering the Explorer

```javascript
function renderExplorer() {
  const container = document.getElementById('explorer-tiers');
  container.innerHTML = '';
  TIERS.forEach(tier => {
    // Create tier label div
    const lbl = document.createElement('div');
    lbl.className = 'tier-label';
    lbl.textContent = tier.label;
    container.appendChild(lbl);

    // Create module card grid
    const grid = document.createElement('div');
    grid.className = 'mod-grid';
    tier.ids.forEach(id => {
      const m = moduleMap[id];
      if (!m) return;
      const card = document.createElement('div');
      card.className = 'mod-card';
      card.dataset.id = id;
      card.style.borderLeftColor = TIER_COLORS[tier.color].color;
      const cls = (m.key_classes || []).length;
      card.innerHTML = '<div class="mod-name">' + id
        + '</div><div class="mod-sub">' + cls + ' classes</div>';
      card.onclick = function() { selectModule(id); };
      grid.appendChild(card);
    });
    container.appendChild(grid);
  });
}
```

### 4. Module Selection and Detail Panel

This is the core interaction. When a card is clicked:

```javascript
let activeModule = null;

function selectModule(id) {
  activeModule = id;

  // Highlight active card, set tier bg color
  document.querySelectorAll('.mod-card').forEach(c => {
    const isActive = c.dataset.id === id;
    c.classList.toggle('active', isActive);
    if (isActive) {
      const tc = tierOfModule[id];
      c.style.background = TIER_COLORS[tc] ? TIER_COLORS[tc].bg : '';
    } else {
      c.style.background = '';
    }
  });

  const m = moduleMap[id];
  if (!m) return;
  const detail = document.getElementById('detail');
  const inEdges = DATA.edges.filter(e => e.to === id);
  const outEdges = DATA.edges.filter(e => e.from === id);
  const tc = tierOfModule[id] || 'core';

  let html = '';

  // Header: name, path, badges
  html += '<div class="dp-header">';
  html += '<span class="dp-title">' + id + '</span>';
  html += '<span class="dp-path">' + escHtml(m.path || '') + '</span>';
  if (m.language) {
    html += '<span class="dp-badge" style="background:' + TIER_COLORS[tc].bg
      + ';color:' + TIER_COLORS[tc].color + '">' + m.language + '</span>';
  }
  if (m.role) {
    html += '<span class="dp-badge" style="background:var(--bg-tertiary)'
      + ';color:var(--text-secondary)">' + m.role + '</span>';
  }
  html += '</div>';

  // Dependencies section
  if (inEdges.length || outEdges.length) {
    html += '<div class="dp-section">';
    html += '<div class="dp-section-title">Dependencies ('
      + (inEdges.length + outEdges.length) + ')</div>';
    html += '<div class="dp-edges">';
    inEdges.forEach(e => {
      html += '<span class="edge-pill in" onclick="selectModule(\''
        + e.from + '\')" title="' + escHtml(e.evidence || '')
        + '">' + e.from + ' &rarr; ' + id + '</span>';
    });
    outEdges.forEach(e => {
      html += '<span class="edge-pill out" onclick="selectModule(\''
        + e.to + '\')" title="' + escHtml(e.evidence || '')
        + '">' + id + ' &rarr; ' + e.to + '</span>';
    });
    html += '</div></div>';
  }

  // Key classes section
  const classes = m.key_classes || [];
  if (classes.length) {
    html += '<div class="dp-section">';
    html += '<div class="dp-section-title">Key classes (' + classes.length + ')</div>';
    html += '<ul class="class-list">';
    classes.forEach((c, i) => {
      const base = c.bases && c.bases.length
        ? '<span class="cl-bases">(' + escHtml(c.bases.join(', ')) + ')</span>'
        : '';
      const mc = (c.methods || []).length;
      html += '<li class="class-item" onclick="toggleMethods(\''
        + id + '-' + i + '\')">';
      html += '<span><span class="cl-name">' + escHtml(c.name)
        + '</span>' + base + '</span>';
      html += '<span class="cl-methods-count">' + mc + ' methods</span>';
      html += '</li>';
      if (mc) {
        html += '<div class="method-drawer" id="md-' + id + '-' + i + '">';
        c.methods.forEach(mth => {
          html += '<div>' + escHtml(mth) + '()</div>';
        });
        html += '</div>';
      }
    });
    html += '</ul></div>';
  } else {
    html += '<div class="dp-section">';
    html += '<div class="dp-section-title">Key classes</div>';
    html += '<div style="font-size:12px;color:var(--text-tertiary)">'
      + 'No classes extracted for this module.</div></div>';
  }

  // Collaborators section (union across all classes)
  const allCollabs = new Set();
  classes.forEach(c => (c.collaborators || []).forEach(col => allCollabs.add(col)));
  if (allCollabs.size > 0) {
    html += '<div class="dp-section">';
    html += '<div class="dp-section-title">Collaborators ('
      + allCollabs.size + ')</div>';
    html += '<div style="font-size:11px;color:var(--text-secondary)'
      + ';font-family:var(--font-mono);line-height:1.8">'
      + Array.from(allCollabs).map(escHtml).join(', ') + '</div></div>';
  }

  detail.innerHTML = html;
}
```

### 5. Utility Functions

```javascript
function toggleMethods(key) {
  const el = document.getElementById('md-' + key);
  if (el) el.classList.toggle('open');
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function exportJSON() {
  const blob = new Blob(
    [JSON.stringify(DATA, null, 2)],
    { type: 'application/json' }
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = (DATA.meta.repo_name || 'architecture') + '-data.json';
  a.click();
  URL.revokeObjectURL(url);
}
```

### 6. Initialization

```javascript
renderExplorer();
```

## Important Implementation Notes

1. **Tier classification is done by the model at generation time**, not in the JS.
   The model reads the YAML, classifies components into tiers, and embeds the
   `TIERS` array with the correct `ids` lists.

2. **All class/method data is embedded in `DATA.components`**. The JS reads
   `key_classes` from each component object.

3. **Edge direction matters**. In edge pills, "in" means another module depends
   on this one (arrow points here). "out" means this module depends on another.

4. **The `evidence` field goes in the pill's `title` attribute** so the import
   path is visible on hover without cluttering the UI.

5. **No external dependencies**. No Google Fonts, no CDN scripts, no imported
   CSS frameworks. Everything is inline in the single HTML file.

6. **Method drawers toggle on click**. Each class item click toggles a drawer
   showing all methods. The drawer ID is `md-{moduleName}-{classIndex}`.

7. **Responsive behavior**: Below 768px, stat cards switch to a 2-column grid.
