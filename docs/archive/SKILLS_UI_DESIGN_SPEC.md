# Skills Management UI - Design Specification

## Overview

This document provides detailed specifications for adding Skills Management functionality to the AInstein web interface.

---

## Current State

```
┌─────────────────────────────────────────────────────────────┐
│                    AInstein Chat UI                         │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Conversation List  │      Chat Window               │ │
│  │                     │                                 │ │
│  │  - Chat 1           │  [User message]                │ │
│  │  - Chat 2           │  [AInstein response]           │ │
│  │  - Chat 3           │                                 │ │
│  │                     │  [Input box]                   │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  [Test Mode Toggle]  [Settings]                            │
└─────────────────────────────────────────────────────────────┘
```

**Missing**: No way to view or manage skills from the UI.

---

## Proposed UI Architecture

### Navigation Enhancement

Add a new "Skills" section to the UI:

```
┌─────────────────────────────────────────────────────────────┐
│  ┌─────┐  ┌─────┐  ┌────────┐  ┌──────────┐                │
│  │ Chat │  │Skills│  │Settings│  │Test Mode │                │
│  └─────┘  └─────┘  └────────┘  └──────────┘                │
│                                                             │
│  [Active Tab Content]                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Skills Tab - Main View

### Wireframe

```
┌─────────────────────────────────────────────────────────────┐
│  SKILLS MANAGEMENT                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  REGISTERED SKILLS                          [+ New]  │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  ┌────────────────────────────────────────────────┐ │   │
│  │  │ ○ rag-quality-assurance           [ACTIVE]     │ │   │
│  │  │   Anti-hallucination rules and citation        │ │   │
│  │  │   requirements for RAG responses               │ │   │
│  │  │   Auto-activate: Yes                           │ │   │
│  │  │   [Edit] [Configure] [Disable]                 │ │   │
│  │  └────────────────────────────────────────────────┘ │   │
│  │                                                      │   │
│  │  ┌────────────────────────────────────────────────┐ │   │
│  │  │ ○ domain-expert (planned)        [DISABLED]    │ │   │
│  │  │   Energy sector terminology rules              │ │   │
│  │  │   Auto-activate: No | Triggers: cim, iec       │ │   │
│  │  │   [Edit] [Configure] [Enable]                  │ │   │
│  │  └────────────────────────────────────────────────┘ │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  QUICK SETTINGS                                      │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  Abstention Strictness   [====●=====] Medium        │   │
│  │  (distance_threshold)    0.3  0.5  0.7              │   │
│  │                                                      │   │
│  │  Query Coverage Required [====●=====] Low           │   │
│  │  (min_query_coverage)    0.1  0.2  0.4              │   │
│  │                                                      │   │
│  │  [Apply Changes]  [Reset to Defaults]               │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Component Specifications

#### 1. Skills List Component

```html
<div class="skills-list">
  <div class="skills-header">
    <h2>Registered Skills</h2>
    <button class="btn-add-skill">+ New Skill</button>
  </div>

  <div class="skill-card" data-skill="rag-quality-assurance">
    <div class="skill-status active"></div>
    <div class="skill-info">
      <h3 class="skill-name">rag-quality-assurance</h3>
      <span class="skill-badge active">ACTIVE</span>
      <p class="skill-description">Anti-hallucination rules...</p>
      <div class="skill-meta">
        <span>Auto-activate: Yes</span>
        <span>Triggers: adr, principle, architecture...</span>
      </div>
    </div>
    <div class="skill-actions">
      <button class="btn-edit">Edit Rules</button>
      <button class="btn-configure">Configure</button>
      <button class="btn-toggle">Disable</button>
    </div>
  </div>
</div>
```

#### 2. Quick Settings Sliders

```javascript
// Slider configuration
const sliders = [
  {
    id: 'distance-threshold',
    label: 'Abstention Strictness',
    configKey: 'abstention.distance_threshold',
    min: 0.1,
    max: 0.9,
    step: 0.1,
    default: 0.5,
    labels: ['Strict', 'Medium', 'Lenient'],
    description: 'Lower = more strict (abstains more often)'
  },
  {
    id: 'query-coverage',
    label: 'Query Coverage Required',
    configKey: 'abstention.min_query_coverage',
    min: 0.1,
    max: 0.5,
    step: 0.05,
    default: 0.2,
    labels: ['Low', 'Medium', 'High'],
    description: 'Higher = requires more query terms to match'
  }
];
```

---

## Skills Configuration Modal

When user clicks "Configure" on a skill:

### Wireframe

```
┌─────────────────────────────────────────────────────────────┐
│  CONFIGURE: rag-quality-assurance                    [X]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ABSTENTION THRESHOLDS                              │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  Distance Threshold                                  │   │
│  │  ┌────────────────────────────────────────────────┐ │   │
│  │  │ 0.5                                          │▼│ │   │
│  │  └────────────────────────────────────────────────┘ │   │
│  │  ℹ️ Maximum distance for relevance (0.0-1.0)        │   │
│  │                                                      │   │
│  │  Min Query Coverage                                  │   │
│  │  ┌────────────────────────────────────────────────┐ │   │
│  │  │ 0.2                                          │▼│ │   │
│  │  └────────────────────────────────────────────────┘ │   │
│  │  ℹ️ Minimum fraction of query terms in results      │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  RETRIEVAL LIMITS                                   │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  ADRs          ┌──────┐    Principles  ┌──────┐    │   │
│  │                │  8   │                │  6   │    │   │
│  │                └──────┘                └──────┘    │   │
│  │                                                      │   │
│  │  Policies      ┌──────┐    Vocabulary  ┌──────┐    │   │
│  │                │  4   │                │  4   │    │   │
│  │                └──────┘                └──────┘    │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  TRUNCATION LIMITS                                  │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  Content Max Chars         ┌────────────────────┐   │   │
│  │                            │ 800                │   │   │
│  │                            └────────────────────┘   │   │
│  │                                                      │   │
│  │  Context Snippet Chars     ┌────────────────────┐   │   │
│  │                            │ 500                │   │   │
│  │                            └────────────────────┘   │   │
│  │                                                      │   │
│  │  Summary Chars             ┌────────────────────┐   │   │
│  │                            │ 300                │   │   │
│  │                            └────────────────────┘   │   │
│  │                                                      │   │
│  │  Max Context Results       ┌────────────────────┐   │   │
│  │                            │ 10                 │   │   │
│  │                            └────────────────────┘   │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [Cancel]                              [Save & Restart]    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Skills Rule Editor

When user clicks "Edit Rules" on a skill:

### Wireframe

```
┌─────────────────────────────────────────────────────────────┐
│  EDIT RULES: rag-quality-assurance                   [X]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  SKILL METADATA                                      │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  Name:  ┌─────────────────────────────────────────┐ │   │
│  │         │ rag-quality-assurance                   │ │   │
│  │         └─────────────────────────────────────────┘ │   │
│  │                                                      │   │
│  │  Description:                                        │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │ Ensures RAG responses meet strict quality      │ │   │
│  │  │ standards for critical decision support...     │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  BEHAVIORAL RULES (Markdown)               [Preview] │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │ # RAG Quality Assurance                        │ │   │
│  │  │                                                 │ │   │
│  │  │ ## Why This Matters                            │ │   │
│  │  │                                                 │ │   │
│  │  │ This system supports critical procurement      │ │   │
│  │  │ and architecture decisions. False information  │ │   │
│  │  │ could lead to costly mistakes.                 │ │   │
│  │  │                                                 │ │   │
│  │  │ ## Pre-Generation Quality Gate                 │ │   │
│  │  │                                                 │ │   │
│  │  │ Before generating any response, evaluate       │ │   │
│  │  │ retrieval quality using the thresholds...      │ │   │
│  │  │                                                 │ │   │
│  │  │ (continues...)                                 │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  │                                                      │   │
│  │  Line: 45  Col: 12  |  Markdown  |  UTF-8           │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ACTIVATION SETTINGS                                │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  [✓] Auto-activate (always inject into prompts)     │   │
│  │                                                      │   │
│  │  Trigger Keywords:                                   │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │ [adr] [principle] [architecture] [+]           │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [Cancel]  [Save Draft]                [Save & Restart]    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Markdown Editor Features

- **Syntax highlighting** for Markdown
- **Live preview** panel (toggle)
- **YAML frontmatter validation** (auto-generated from metadata fields)
- **Line numbers** and cursor position
- **Undo/Redo** support
- **Auto-save draft** to localStorage

---

## New Skill Creation Wizard

### Step 1: Basic Info

```
┌─────────────────────────────────────────────────────────────┐
│  CREATE NEW SKILL                               Step 1/3   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Skill Name (identifier):                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ my-custom-skill                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│  ℹ️ Use lowercase with hyphens, no spaces                   │
│                                                             │
│  Display Name:                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ My Custom Skill                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Description:                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Describe what this skill does and when it should   │   │
│  │ be activated...                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [Cancel]                                         [Next →]  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Step 2: Activation Settings

```
┌─────────────────────────────────────────────────────────────┐
│  CREATE NEW SKILL                               Step 2/3   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  When should this skill activate?                           │
│                                                             │
│  ○ Always (auto-activate on every query)                   │
│  ● Only when triggered by keywords                         │
│  ○ Manual activation only                                  │
│                                                             │
│  Trigger Keywords:                                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Enter keywords separated by commas...               │   │
│  └─────────────────────────────────────────────────────┘   │
│  ℹ️ Skill activates when query contains any of these words  │
│                                                             │
│  [← Back]                                        [Next →]   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Step 3: Initial Rules

```
┌─────────────────────────────────────────────────────────────┐
│  CREATE NEW SKILL                               Step 3/3   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Write the behavioral rules for this skill:                 │
│                                                             │
│  Template: ○ Blank  ● From existing skill  ○ AI-assisted   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ # My Custom Skill                                   │   │
│  │                                                      │   │
│  │ ## Purpose                                          │   │
│  │ [Describe the purpose of this skill]                │   │
│  │                                                      │   │
│  │ ## Rules                                            │   │
│  │ 1. First rule                                       │   │
│  │ 2. Second rule                                      │   │
│  │                                                      │   │
│  │ ## Prohibited Actions                               │   │
│  │ - Don't do this                                     │   │
│  │ - Don't do that                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [← Back]                                [Create Skill]     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## API Endpoints Required

### Skills CRUD API

```python
# FastAPI endpoints to add to chat_ui.py

@app.get("/api/skills")
async def list_skills():
    """List all registered skills with their status."""
    registry = SkillRegistry()
    skills = registry.list_skills()
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "enabled": s.enabled,
                "auto_activate": s.auto_activate,
                "triggers": s.triggers,
                "path": s.path,
            }
            for s in skills
        ]
    }

@app.get("/api/skills/{skill_name}")
async def get_skill(skill_name: str):
    """Get full skill details including content and thresholds."""
    loader = SkillLoader()
    skill = loader.load_skill(skill_name)
    if not skill:
        raise HTTPException(404, f"Skill not found: {skill_name}")

    return {
        "name": skill.name,
        "description": skill.description,
        "content": skill.content,  # The markdown body
        "thresholds": skill.thresholds,
        "path": str(skill.path),
    }

@app.put("/api/skills/{skill_name}/thresholds")
async def update_thresholds(skill_name: str, thresholds: dict):
    """Update skill thresholds (writes to YAML file)."""
    # Validate thresholds structure
    # Write to skills/{skill_name}/references/thresholds.yaml
    # Clear skill cache
    # Return success
    pass

@app.put("/api/skills/{skill_name}/content")
async def update_content(skill_name: str, content: str, metadata: dict):
    """Update skill content (writes to SKILL.md file)."""
    # Generate YAML frontmatter from metadata
    # Combine with markdown content
    # Write to skills/{skill_name}/SKILL.md
    # Clear skill cache
    pass

@app.post("/api/skills")
async def create_skill(skill_data: dict):
    """Create a new skill."""
    # Create directory: skills/{name}/references/
    # Create SKILL.md with content
    # Create thresholds.yaml (optional)
    # Update registry.yaml
    pass

@app.delete("/api/skills/{skill_name}")
async def delete_skill(skill_name: str):
    """Delete a skill (moves to .archive folder)."""
    # Don't actually delete - move to skills/.archive/
    # Remove from registry.yaml
    pass

@app.post("/api/skills/reload")
async def reload_skills():
    """Hot reload all skills without server restart."""
    registry = SkillRegistry()
    registry.reload()
    return {"status": "reloaded", "skills_count": len(registry.list_skills())}
```

---

## Implementation Priority

### Phase 1: Read-Only View (Low Effort)
- Skills list with status badges
- View thresholds (no editing)
- View skill content (read-only)

**Estimated effort**: 1-2 days

### Phase 2: Quick Settings (Medium Effort)
- Sliders for common thresholds
- Apply & restart button
- Reset to defaults

**Estimated effort**: 2-3 days

### Phase 3: Full Configuration (Medium Effort)
- Modal for all threshold values
- Input validation
- Save to YAML file

**Estimated effort**: 3-4 days

### Phase 4: Rule Editor (High Effort)
- Markdown editor component
- Live preview
- YAML frontmatter handling

**Estimated effort**: 4-5 days

### Phase 5: Skill Creation (High Effort)
- Creation wizard
- Directory/file generation
- Registry update

**Estimated effort**: 3-4 days

### Phase 6: Hot Reload (Medium Effort)
- File watcher on backend
- WebSocket notifications
- Auto-refresh UI

**Estimated effort**: 2-3 days

---

## Total Estimated Effort

| Phase | Features | Days |
|-------|----------|------|
| Phase 1 | Read-only view | 1-2 |
| Phase 2 | Quick settings | 2-3 |
| Phase 3 | Full configuration | 3-4 |
| Phase 4 | Rule editor | 4-5 |
| Phase 5 | Skill creation | 3-4 |
| Phase 6 | Hot reload | 2-3 |
| **Total** | **Full implementation** | **15-21 days** |

---

## Recommended MVP

For a minimum viable product, implement:

1. **Skills list** with enable/disable toggle
2. **Quick settings sliders** for 2-3 most important values
3. **Read-only view** of skill content

**MVP Effort**: 4-6 days

This gives users visibility into skills and ability to tune the most critical parameters without the complexity of full CRUD operations.
