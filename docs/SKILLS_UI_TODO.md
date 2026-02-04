# Skills UI Implementation - TODO

## Overview

This document tracks all planned work for the Skills Management UI. The goal is to allow non-technical users to configure AInstein's behavior without editing YAML files.

**Target Audience:**
- Non-technical users: Quick sliders + testing panel
- Technical users: Full configuration + rule editor

**Current State:** Phase 1 (MVP), Phase 2 (Full Configuration), and Phase 3 (Rule Editor) completed.

**Architecture Decision:** Extend existing FastAPI server (Option A)
- `chat_ui.py` already uses FastAPI - add `/api/skills/*` endpoints there
- Single deployment, consistent architecture
- Skills UI will be HTML/JS pages calling the new API endpoints

---

## Phase 1: MVP (Priority: HIGH) - COMPLETED

**Goal:** Safe configuration for non-technical users

### 1.1 Skills Dashboard

- [x] Add "Skills" button to main navigation sidebar
- [x] Create skills list component showing all registered skills
- [x] Display skill status (active/disabled) with visual indicator
- [x] Show skill metadata (name, description, auto-activate, triggers)
- [x] Implement expandable skill cards

**Files created/modified:**
- `src/skills/api.py` (new - API logic)
- `src/static/skills.html` (new - UI page)
- `src/chat_ui.py` (API endpoints + navigation)
- `src/static/index.html` (Skills button)

### 1.2 Quick Settings Sliders

- [x] Abstention Strictness slider
  - Maps to: `abstention.distance_threshold`
  - Range: 0.3 (strict) to 0.7 (lenient)
  - Default: 0.5
  - Labels: "Strict" | "Medium" | "Lenient"

- [x] Query Coverage slider
  - Maps to: `abstention.min_query_coverage`
  - Range: 0.1 (low) to 0.5 (high)
  - Default: 0.2
  - Labels: "Low" | "Medium" | "High"

- [x] Apply Changes button
- [x] Reset to Defaults button

**HTML implementation:**
```html
<input type="range" id="distance-threshold" min="0.3" max="0.7" step="0.05" value="0.5">
<input type="range" id="query-coverage" min="0.1" max="0.5" step="0.05" value="0.2">
<button onclick="applyChanges()">Apply Changes</button>
<button onclick="resetDefaults()">Reset to Defaults</button>
```

### 1.3 Testing Panel (CRITICAL)

- [x] Test query input field
- [x] "Run Test" button
- [x] Results display showing:
  - [x] Is list query detected: Yes/No
  - [x] Matched indicator (if list query)
  - [x] Specific document query detection
  - [x] Query terms extracted
  - [x] Expected behavior note
- [x] Visual pass/fail indicators

**API function needed:**
```python
def test_skill_config(query: str, config: dict) -> dict:
    """Test how a query would behave with given config."""
    return {
        "would_abstain": False,
        "reason": "OK",
        "distance": 0.32,
        "coverage": 0.67,
        "is_list_query": True,
        "matched_indicator": "exist"
    }
```

### 1.4 Config Backup

- [x] Implement backup before any write operation
- [x] Store backup as `thresholds.yaml.bak`
- [x] Add "Restore Backup" button
- [x] Timestamped backups stored

**Implementation:**
```python
def backup_config(skill_name: str) -> str:
    """Backup config before write. Returns backup path."""
    src = Path(f"skills/{skill_name}/references/thresholds.yaml")
    dst = src.with_suffix(".yaml.bak")
    shutil.copy(src, dst)
    return str(dst)
```

### 1.5 Enable/Disable Toggle - COMPLETED

- [x] Toggle switch per skill
- [x] Updates `enabled` in `registry.yaml`
- [x] Visual feedback on toggle (ACTIVE/DISABLED badges)
- [x] Requires server restart notification (warning banner)

**Implementation:**
- `src/skills/registry.py` (added `set_skill_enabled()` method)
- `src/skills/api.py` (added `toggle_skill_enabled()` function)
- `src/chat_ui.py` (added `PUT /api/skills/{name}/enabled` endpoint)
- `src/static/skills.html` (added toggle switch in skill cards, restart warning banner)

---

## Phase 2: Full Configuration Modal - COMPLETED

**Goal:** Fine-tune all parameters via UI

### 2.1 Configuration Modal

- [x] Modal dialog with overlay (vanilla JS/HTML)
- [x] Tabs for different config sections:
  - Abstention Thresholds
  - Retrieval Limits
  - Truncation Limits
  - List Query Detection

### 2.2 Abstention Thresholds Section

- [x] `distance_threshold` number input (0.0-1.0)
- [x] `min_query_coverage` number input (0.0-1.0)
- [x] Help text explaining each field
- [x] Validation: values must be in valid range

### 2.3 Retrieval Limits Section

- [x] ADRs limit input (1-50)
- [x] Principles limit input (1-50)
- [x] Policies limit input (1-50)
- [x] Vocabulary limit input (1-50)

### 2.4 Truncation Limits Section

- [x] `content_max_chars` input
- [x] `elysia_content_chars` input
- [x] `elysia_summary_chars` input
- [x] `max_context_results` input

### 2.5 List Query Detection Section

- [x] `list_indicators` - editable list of words
- [x] `list_patterns` - editable list of regex patterns
- [x] `additional_stop_words` - editable list
- [x] Add/remove buttons for list items
- [x] Regex pattern validation

### 2.6 Validation

- [x] Implement config validation before save
- [x] Show validation errors inline
- [x] Prevent save if validation fails

**API endpoint added:**
```
POST /api/skills/{name}/validate
```

---

## Phase 3: Rule Editor - COMPLETED

**Goal:** Edit SKILL.md content via web interface

### 3.1 Markdown Editor

- [x] Full-height text area for SKILL.md content
- [ ] Syntax highlighting (deferred - not critical for MVP)
- [ ] Line numbers (deferred - not critical for MVP)
- [x] Preserve YAML frontmatter

### 3.2 Preview Panel

- [x] Side-by-side preview of rendered markdown
- [x] Live update as user types
- [x] Toggle between edit/preview modes (Split/Edit/Preview)

### 3.3 Metadata Editor

- [x] Edit skill name
- [x] Edit skill description
- [x] Edit triggers list
- [x] Toggle auto_activate

### 3.4 Save & Validate

- [x] Validate YAML frontmatter syntax
- [x] Validate markdown structure
- [x] Backup before save
- [x] Success/error feedback

**Files created/modified:**
- `src/skills/api.py` (added content management functions)
- `src/chat_ui.py` (added content API endpoints)
- `src/static/skills.html` (added Rule Editor modal)

---

## Phase 4: Skill Testing (Advanced)

**Goal:** Comprehensive testing before deployment

### 4.1 Batch Testing

- [ ] Upload/paste multiple test queries
- [ ] Run all tests with current config
- [ ] Show pass/fail summary
- [ ] Export results as CSV

### 4.2 A/B Comparison

- [ ] Compare two configs side-by-side
- [ ] Run same query against both
- [ ] Show difference in behavior
- [ ] Highlight which config is "better"

### 4.3 Historical Test Results

- [ ] Store test results with timestamp
- [ ] View past test runs
- [ ] Compare current vs. historical behavior

---

## Phase 5: Skill Creation Wizard

**Goal:** Create new skills without touching filesystem

### 5.1 Step 1: Basic Info

- [ ] Skill name input (validates folder-safe name)
- [ ] Description textarea
- [ ] Auto-activate toggle
- [ ] Triggers input (comma-separated)

### 5.2 Step 2: Initial Rules

- [ ] Template selector (blank, copy from existing)
- [ ] Basic markdown editor
- [ ] Identity section template
- [ ] Quality rules template

### 5.3 Step 3: Thresholds

- [ ] Copy from existing skill or use defaults
- [ ] Quick config sliders
- [ ] Advanced config accordion

### 5.4 Step 4: Review & Create

- [ ] Preview all settings
- [ ] Validate everything
- [ ] Create skill directory structure
- [ ] Register in registry.yaml

---

## Phase 6: Hot Reload

**Goal:** No server restart required

### 6.1 File Watcher

- [ ] Watch `skills/` directory for changes
- [ ] Detect modified files
- [ ] Trigger reload on change

### 6.2 Cache Invalidation

- [ ] Clear skill cache on file change
- [ ] Reload affected skills only
- [ ] Update UI to reflect changes

### 6.3 User Notification

- [ ] Show "Config updated" toast
- [ ] Show which skill was reloaded
- [ ] Option to undo (restore backup)

---

## Phase 7: Progressive Loading

**Goal:** Optimize context usage with many skills

### 7.1 Level 1: Discovery

- [ ] Load only skill metadata at startup
- [ ] Store in lightweight index (~50 tokens/skill)
- [ ] Expose via `get_skill_index()`

### 7.2 Level 2: Activation

- [ ] Load full SKILL.md only when triggered
- [ ] Match query against triggers
- [ ] Cache activated skills for session

### 7.3 Level 3: Execution

- [ ] Load references on-demand
- [ ] Lazy load thresholds.yaml
- [ ] Lazy load examples/data files

### 7.4 Refactor Existing Code

- [ ] Update `SkillLoader` for progressive loading
- [ ] Update `SkillRegistry` for lazy activation
- [ ] Update `elysia_agents.py` integration
- [ ] Update `chat_ui.py` integration

---

## Backend API Endpoints

### Required for UI

| Endpoint | Method | Purpose | Phase | Status |
|----------|--------|---------|-------|--------|
| `/api/skills` | GET | List all skills | 1 | Done |
| `/api/skills/{name}` | GET | Get skill details | 1 | Done |
| `/api/skills/{name}/thresholds` | GET | Get thresholds | 1 | Done |
| `/api/skills/{name}/thresholds` | PUT | Update thresholds | 1 | Done |
| `/api/skills/{name}/test` | POST | Test with query | 1 | Done |
| `/api/skills/{name}/backup` | POST | Create backup | 1 | Done |
| `/api/skills/{name}/restore` | POST | Restore from backup | 1 | Done |
| `/api/skills/{name}/enabled` | PUT | Toggle skill enabled | 1.5 | Done |
| `/api/skills/{name}/validate` | POST | Validate config | 2 | Done |
| `/api/skills/{name}/content` | GET | Get SKILL.md | 3 | Done |
| `/api/skills/{name}/content` | PUT | Update SKILL.md | 3 | Done |
| `/api/skills/defaults` | GET | Get default values | 3 | Done |
| `/api/skills` | POST | Create new skill | 5 | - |
| `/api/skills/{name}` | DELETE | Delete skill | 5 | - |
| `/api/skills/reload` | POST | Hot reload all | 6 | Done |

### Implementation Decision

**✅ Option A: Extend FastAPI (SELECTED)**
- Add `/api/skills/*` endpoints to existing `chat_ui.py`
- Single server, consistent architecture, simpler deployment
- Skills UI will be HTML/JS page calling new endpoints
- API can also be used by CLI tools and scripts

**❌ Option B: Separate Streamlit (NOT SELECTED)**
- Would require running two servers (FastAPI + Streamlit)
- Streamlit is faster for prototyping sliders/forms
- More complex deployment
- Could be reconsidered if UI iteration speed becomes critical

---

## File Structure

```
src/
├── chat_ui.py                   # Existing - add /api/skills/* endpoints here
├── skills/
│   ├── __init__.py              # Existing
│   ├── loader.py                # Existing (modify for Phase 7)
│   ├── registry.py              # Existing (modify for Phase 7)
│   ├── api.py                   # NEW: Skills API logic (called by chat_ui.py)
│   └── progressive.py           # Phase 7 (new)
static/
├── index.html                   # Existing chat UI
├── skills.html                  # NEW: Skills admin page (Phase 1)
├── skills.js                    # NEW: JavaScript for skills UI (Phase 1)
├── skills-editor.html           # NEW: SKILL.md editor (Phase 3)
└── css/
    └── skills.css               # NEW: Styles for skills pages
```

---

## Dependencies

### Required (Already Installed)

- `fastapi` - Already used in chat_ui.py
- `pyyaml` - Already installed
- `shutil` - stdlib

### Frontend (No Install Needed)

- Vanilla JavaScript or lightweight library (Alpine.js, htmx)
- CSS framework optional (Bootstrap, Tailwind via CDN)

### Optional

- `watchdog` - for file watching (Phase 6)

---

## Effort Estimates

| Phase | Features | Effort | Priority |
|-------|----------|--------|----------|
| 1. MVP | Dashboard + Sliders + Testing + Backup | 5-7 days | HIGH |
| 2. Full Config | Modal + All inputs + Validation | 3-4 days | HIGH |
| 3. Rule Editor | Markdown editor + Preview | 4-5 days | MEDIUM |
| 4. Advanced Testing | Batch + A/B + History | 3-4 days | LOW |
| 5. Skill Creation | Wizard + Templates | 3-4 days | MEDIUM |
| 6. Hot Reload | File watcher + Cache | 2-3 days | MEDIUM |
| 7. Progressive Loading | Three-level loading | 4-5 days | HIGH (future) |

**Total estimated effort:** 24-32 days

---

## Success Criteria

### Phase 1 Complete When:

- [ ] Non-technical user can adjust abstention strictness via slider
- [ ] User can test a query and see if it would abstain
- [ ] Config is backed up before any change
- [ ] User can restore previous config with one click

### Full Implementation Complete When:

- [ ] All config values editable via UI
- [ ] SKILL.md editable with preview
- [ ] New skills can be created via wizard
- [ ] No server restart needed for config changes
- [ ] Progressive loading supports 20+ skills without context bloat

---

## References

- [Skills Framework User Manual](./SKILLS_FRAMEWORK_USER_MANUAL.md)
- [Skills UI Design Spec](./SKILLS_UI_DESIGN_SPEC.md)
- [MCP Tool Search - Context Optimization](https://venturebeat.com/orchestration/claude-code-just-got-updated-with-one-of-the-most-requested-user-features)
- [Agent Skills Standard](https://nayakpplaban.medium.com/agent-skills-standard-for-smarter-ai-bde76ea61c13)

---

*Last Updated: February 2026*
*Architecture Decision: FastAPI (extend chat_ui.py) - Feb 2026*
