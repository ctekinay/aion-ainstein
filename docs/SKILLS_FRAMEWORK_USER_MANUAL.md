# AInstein Skills Framework - User Manual

## Table of Contents

1. [Introduction](#introduction)
2. [What Are Skills?](#what-are-skills)
3. [Quick Start Guide](#quick-start-guide)
4. [For Non-Technical Users](#for-non-technical-users)
   - [Identity Configuration](#identity-configuration)
5. [For Technical Users](#for-technical-users)
   - [Tool Return Fields](#tool-return-fields)
6. [Configuration Reference](#configuration-reference)
7. [Troubleshooting](#troubleshooting)
8. [Future Roadmap](#future-roadmap)
9. [Changelog](#changelog)

---

## Introduction

The Skills Framework allows you to customize AInstein's behavior without modifying code. Skills define:

- **How AInstein responds** (rules and guidelines)
- **When AInstein abstains** from answering (quality thresholds)
- **How much context** AInstein uses (retrieval and truncation limits)

All configuration is done through simple YAML and Markdown files.

---

## What Are Skills?

A **Skill** is a package of instructions and configuration that tells AInstein how to behave in specific situations. Think of it like a "personality module" or "expert mode" that can be activated.

### Current Skills

| Skill | Purpose | Status |
|-------|---------|--------|
| `rag-quality-assurance` | Prevents hallucination, requires citations, controls retrieval quality | Active (auto-enabled) |

### Skill Components

Each skill consists of:

```
skills/
├── registry.yaml              # Which skills exist and when they activate
└── rag-quality-assurance/     # Skill folder
    ├── SKILL.md               # Behavioral rules (injected into prompts)
    └── references/
        └── thresholds.yaml    # Numeric configuration values
```

---

## Quick Start Guide

### Viewing Current Configuration

1. Open `skills/rag-quality-assurance/references/thresholds.yaml`
2. View all configurable values with explanatory comments

### Making Changes

1. Edit the YAML file
2. Save
3. Restart AInstein (`Ctrl+C` then restart the server)
4. Changes take effect immediately

### Example: Making AInstein More Strict

To make AInstein abstain more often (higher quality, lower coverage):

```yaml
# In thresholds.yaml
abstention:
  distance_threshold: 0.3      # Was 0.5 - now requires closer matches
  min_query_coverage: 0.4      # Was 0.2 - now requires more term coverage
```

---

## For Non-Technical Users

### What You Can Change (Without Coding)

| Setting | What It Does | Default | File |
|---------|--------------|---------|------|
| Distance threshold | How similar documents must be to answer | 0.5 | thresholds.yaml |
| Query coverage | How many query words must appear in results | 0.2 | thresholds.yaml |
| ADR retrieval limit | Maximum ADRs to search | 8 | thresholds.yaml |
| Content truncation | How much text per document | 800 chars | thresholds.yaml |
| Citation rules | How AInstein cites sources | See below | SKILL.md |

### Step-by-Step: Editing Configuration

#### Option 1: Using a Text Editor

1. Navigate to: `skills/rag-quality-assurance/references/`
2. Open `thresholds.yaml` in any text editor (Notepad, VS Code, etc.)
3. Find the value you want to change
4. Edit the number (keep the format: `key: value`)
5. Save the file
6. Restart AInstein

#### Option 2: Using VS Code

1. Open the project folder in VS Code
2. Navigate to `skills/rag-quality-assurance/references/thresholds.yaml`
3. Edit values directly
4. `Ctrl+S` to save
5. Restart the server

### Understanding the Values

#### Abstention Thresholds

```yaml
abstention:
  distance_threshold: 0.5    # Range: 0.0 to 1.0
  min_query_coverage: 0.2    # Range: 0.0 to 1.0
```

| Value | Effect |
|-------|--------|
| **Lower** distance_threshold | AInstein is pickier, abstains more often |
| **Higher** distance_threshold | AInstein answers more liberally |
| **Lower** query_coverage | AInstein answers even if few query words match |
| **Higher** query_coverage | AInstein requires more query words to be found |

#### Retrieval Limits

```yaml
retrieval_limits:
  adr: 8           # How many ADRs to search
  principle: 6     # How many principles to search
  policy: 4        # How many policies to search
  vocabulary: 4    # How many vocabulary terms to search
```

**Trade-off**: More documents = better coverage but slower response and more token usage.

#### Truncation Limits

```yaml
truncation:
  content_max_chars: 800      # Full content display
  elysia_content_chars: 500   # Context snippets
  elysia_summary_chars: 300   # Summaries
  max_context_results: 10     # Total docs in LLM context
```

**Trade-off**: More characters = more context but higher cost and potential context overflow.

### Editing Behavioral Rules

The `SKILL.md` file contains instructions that are injected into AInstein's prompt. You can edit this to change how AInstein behaves.

**Location**: `skills/rag-quality-assurance/SKILL.md`

**Example changes you might make**:

- Add new citation requirements
- Change the abstention message
- Add domain-specific rules

**Format**: Markdown with YAML frontmatter

```markdown
---
name: rag-quality-assurance
description: Your description here
---

# Your Rules Here

## Section 1
- Rule 1
- Rule 2

## Section 2
...
```

### Identity Configuration

The `SKILL.md` file includes an **Identity** section that controls how AInstein identifies itself. This is important because the underlying Elysia framework has its own built-in identity that says "I am Elysia".

**Current identity rules** (in `skills/rag-quality-assurance/SKILL.md`):

```markdown
## Identity

You are **AInstein**, the Energy System Architecture AI Assistant at Alliander.

**Critical Identity Rules:**
- Always identify yourself as "AInstein" when asked who you are
- NEVER identify as "Elysia", "Weaviate", or any other framework name
- NEVER mention internal implementation details (Elysia framework, decision trees, etc.)
- Your purpose is to help architects and engineers navigate Alliander's architecture knowledge base
```

**Why this matters**: Without these rules, AInstein might respond "I am Elysia" when asked "Who are you?" because of the underlying framework's default prompt.

---

## For Technical Users

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Query                               │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   SkillRegistry                              │
│  - Loads registry.yaml                                       │
│  - Determines which skills to activate                       │
│  - Returns active skills based on query triggers             │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    SkillLoader                               │
│  - Parses SKILL.md (YAML frontmatter + Markdown)            │
│  - Loads references/thresholds.yaml                          │
│  - Caches loaded skills                                      │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        │                                   │
        ▼                                   ▼
┌───────────────────┐             ┌───────────────────┐
│ Prompt Injection  │             │ Threshold Config  │
│ - SKILL.md body   │             │ - Abstention      │
│ - Added to system │             │ - Retrieval       │
│   prompt          │             │ - Truncation      │
└───────────────────┘             └───────────────────┘
```

### Key Classes

| Class | Location | Purpose |
|-------|----------|---------|
| `SkillLoader` | `src/skills/loader.py` | Parses SKILL.md, loads YAML configs |
| `SkillRegistry` | `src/skills/registry.py` | Manages activation triggers |
| `Skill` | `src/skills/loader.py` | Data class for loaded skill |

### Integration Points

| File | Function/Area | What It Does |
|------|--------------|--------------|
| `src/elysia_agents.py` | Module-level | Initializes `_skill_registry` singleton |
| `src/elysia_agents.py` | `_get_abstention_thresholds()` | Loads distance_threshold and min_query_coverage |
| `src/elysia_agents.py` | `_register_tools()` | Loads truncation config for tool responses |
| `src/elysia_agents.py` | `_direct_query()` | Loads retrieval limits, truncation, injects skill content |
| `src/chat_ui.py` | Module-level | Initializes `_skill_registry` singleton |
| `src/chat_ui.py` | `retrieve_documents()` | Loads retrieval limits and truncation config |
| `src/chat_ui.py` | `get_llm_response()` | Injects skill content into system prompts |

### Key Constants

| Constant | Location | Purpose |
|----------|----------|---------|
| `DEFAULT_SKILL` | `src/skills/__init__.py` | Single source of truth for default skill name (`"rag-quality-assurance"`) |

### Adding a New Skill

#### 1. Create Skill Directory

```bash
mkdir -p skills/my-new-skill/references
```

#### 2. Create SKILL.md

```markdown
---
name: my-new-skill
description: Description of what this skill does
---

# My New Skill

## Rules
1. Rule one
2. Rule two
```

#### 3. Create thresholds.yaml (optional)

```yaml
# Custom thresholds for this skill
my_custom_threshold: 0.7
```

#### 4. Register in registry.yaml

```yaml
skills:
  - name: rag-quality-assurance
    path: rag-quality-assurance/SKILL.md
    enabled: true
    auto_activate: true
    triggers: [...]

  - name: my-new-skill
    path: my-new-skill/SKILL.md
    description: "My custom skill"
    enabled: true
    auto_activate: false      # Only activate on triggers
    triggers:
      - "keyword1"
      - "keyword2"
```

#### 5. Use in Code (if needed)

```python
from src.skills import SkillRegistry, DEFAULT_SKILL

registry = SkillRegistry()
content = registry.get_all_skill_content(query)
thresholds = registry.loader.get_thresholds("my-new-skill")
```

### API Reference

#### SkillLoader

```python
loader = SkillLoader(skills_dir=Path("skills"))

# Load a skill
skill = loader.load_skill("rag-quality-assurance")

# Get injectable content
content = loader.get_skill_content("rag-quality-assurance")

# Get thresholds
thresholds = loader.get_thresholds("rag-quality-assurance")

# Get specific configs
distance, coverage = loader.get_abstention_thresholds("rag-quality-assurance")
limits = loader.get_retrieval_limits("rag-quality-assurance")
truncation = loader.get_truncation("rag-quality-assurance")

# Clear cache (after editing files)
loader.clear_cache()
```

#### SkillRegistry

```python
registry = SkillRegistry()

# Get skills that should activate for a query
skills = registry.get_active_skills("What ADRs exist?")

# Get combined content for prompt injection
content = registry.get_all_skill_content("What ADRs exist?")

# List all registered skills
all_skills = registry.list_skills()

# Reload after editing files
registry.reload()
```

### Tool Return Fields

The Elysia tools return structured data that AInstein uses to answer questions. Each tool returns specific fields:

| Tool | Returns |
|------|---------|
| `search_architecture_decisions()` | `title`, `adr_number`, `file_path`, `status`, `context`, `decision`, `consequences` |
| `search_principles()` | `title`, `principle_number`, `file_path`, `content`, `doc_type` |
| `search_policies()` | `title`, `file_path`, `content`, `file_type` |
| `list_all_adrs()` | `title`, `adr_number`, `status`, `file_path` |
| `list_all_principles()` | `title`, `principle_number`, `file_path`, `type` |
| `search_vocabulary()` | `label`, `definition`, `vocabulary`, `uri` |

**Key identification fields**:
- `adr_number`: e.g., `"ADR-0021"` - allows citing specific ADRs
- `principle_number`: e.g., `"PCP-0010"` - allows citing specific principles
- `file_path`: Full path to source document - allows users to find original files

---

## Configuration Reference

### Complete thresholds.yaml Structure

```yaml
# =============================================================================
# RAG Quality Assurance Thresholds
# Edit these values to tune AInstein's behavior
# =============================================================================

# -----------------------------------------------------------------------------
# ABSTENTION THRESHOLDS
# Controls when AInstein refuses to answer
# -----------------------------------------------------------------------------
abstention:
  # Maximum vector distance for relevance (0.0 = exact match, 1.0 = unrelated)
  # If the best matching document exceeds this distance, AInstein abstains
  # Lower = more strict, Higher = more lenient
  distance_threshold: 0.5

  # Minimum fraction of query words that must appear in retrieved documents
  # If coverage is below this, AInstein abstains
  # Lower = more lenient, Higher = more strict
  min_query_coverage: 0.2

# -----------------------------------------------------------------------------
# RETRIEVAL LIMITS
# Maximum documents to fetch per collection type
# -----------------------------------------------------------------------------
retrieval_limits:
  adr: 8           # Architectural Decision Records
  principle: 6     # Architecture/Governance Principles
  policy: 4        # Policy Documents
  vocabulary: 4    # SKOS Vocabulary Terms

# -----------------------------------------------------------------------------
# TRUNCATION LIMITS
# Maximum characters of content to include
# -----------------------------------------------------------------------------
truncation:
  # For chat_ui.py comparison mode - full content display
  content_max_chars: 800

  # For elysia_agents.py - context/decision snippets in tool responses
  elysia_content_chars: 500

  # For summaries and consequences sections
  elysia_summary_chars: 300

  # Maximum number of results to include in LLM context
  max_context_results: 10

# -----------------------------------------------------------------------------
# CONFIDENCE SCORING
# For future use - confidence calculation weights
# -----------------------------------------------------------------------------
confidence:
  min_source_confidence: 0.3
  distance_weight: 0.6
  keyword_weight: 0.4
```

### registry.yaml Structure

```yaml
version: "1.0"

skills:
  - name: skill-name              # Unique identifier
    path: folder/SKILL.md         # Relative path to SKILL.md
    description: "Description"    # Human-readable description
    enabled: true                 # Whether skill is active
    auto_activate: true           # Always inject (vs. trigger-based)
    triggers:                     # Keywords that activate this skill
      - "keyword1"
      - "keyword2"
```

### SKILL.md Structure

```markdown
---
name: skill-name
description: >
  Multi-line description
  of what this skill does
---

# Skill Title

## Section 1

Instructions that will be injected into the system prompt.

## Section 2

More instructions...
```

---

## Troubleshooting

### Changes Not Taking Effect

**Problem**: Edited thresholds.yaml but AInstein behavior didn't change.

**Solutions**:
1. Restart the server (skills are cached at startup)
2. Check for YAML syntax errors (use a YAML validator)
3. Verify file path is correct

### Skill Not Activating

**Problem**: Created a new skill but it's not being used.

**Checklist**:
1. Is it registered in `registry.yaml`?
2. Is `enabled: true`?
3. Is `auto_activate: true` OR does query contain a trigger word?
4. Is the SKILL.md path correct?

### YAML Syntax Errors

**Common mistakes**:
```yaml
# WRONG - missing space after colon
distance_threshold:0.5

# CORRECT
distance_threshold: 0.5

# WRONG - tabs instead of spaces
abstention:
	distance_threshold: 0.5

# CORRECT - use spaces
abstention:
  distance_threshold: 0.5
```

### Viewing Active Skills (Debug)

Add this to your code to see which skills are active:

```python
from src.skills import SkillRegistry

registry = SkillRegistry()
skills = registry.get_active_skills("your query here")
for skill in skills:
    print(f"Active: {skill.name}")
```

---

## Future Roadmap

### Current Limitations

| Feature | Status | Notes |
|---------|--------|-------|
| Web UI for skills management | Not available | Must edit files directly |
| Skills API endpoints | Not available | No REST API for CRUD |
| Hot reload | Partial | `registry.reload()` exists but no automatic file watcher |
| Progressive loading | Not available | Full skill content loaded at startup |
| Skill versioning | Not available | No version control |
| A/B testing | Not available | Cannot compare skill configs |

**Note on Hot Reload**: You can programmatically reload skills using `registry.reload()`, but there's no automatic file watcher. After editing files, either restart the server or call `reload()` in your code.

### Planned Features

> **Architecture Decision**: Skills UI will extend the existing FastAPI server (`chat_ui.py`)
> with new `/api/skills/*` endpoints. The UI will be HTML/JS pages calling these endpoints.
> See [SKILLS_UI_TODO.md](./SKILLS_UI_TODO.md) for full implementation plan.

1. **Skills Management UI** (MVP)
   - View all registered skills
   - Edit thresholds via web interface (sliders + input fields)
   - Enable/disable skills with toggle
   - **Testing panel** - preview skill behavior before applying
   - Config backup before writes

2. **REST API for Skills** (integrated into `chat_ui.py`)
   - `GET /api/skills` - List all skills
   - `GET /api/skills/{name}` - Get skill details
   - `PUT /api/skills/{name}/thresholds` - Update thresholds
   - `POST /api/skills/{name}/test` - Test skill with sample query
   - `POST /api/skills/{name}/validate` - Validate config syntax
   - `POST /api/skills/{name}/reload` - Hot reload skill

3. **Progressive Loading** ⭐ *Key Architecture Improvement*

   Similar to MCP's lazy loading but optimized for skills. Instead of loading all
   skill content at startup (which consumes context), use three-level staged loading:

   | Level | What Loads | When | Tokens |
   |-------|------------|------|--------|
   | 1. Discovery | Name, description, triggers only | Startup | ~50/skill |
   | 2. Activation | Full SKILL.md content | Query matches triggers | 2,000-5,000 |
   | 3. Execution | Specific references (thresholds, examples) | Task requires them | Variable |

   **Benefits**:
   - 95% reduction in initial context consumption
   - Support for many skills without context penalty
   - Skills can include large reference materials without cost until used

   **Comparison to MCP Lazy Loading**:
   - MCP solved tool definition bloat (125k tokens for Docker's 135 tools)
   - Progressive loading solves skill content bloat (many skills × 2-5k tokens each)
   - Both use on-demand discovery; skills use trigger-based activation

4. **Hot Reload**
   - File watcher for skill changes
   - Automatic cache invalidation
   - No server restart required

4. **Skill Validation CLI**
   ```bash
   python -m src.cli validate-skills
   # Output: ✓ rag-quality-assurance: valid
   ```

---

## Summary

The Skills Framework provides a **no-code way** to customize AInstein's behavior:

| Audience | What You Edit | Purpose |
|----------|--------------|---------|
| Business users | `thresholds.yaml` values | Tune quality vs. coverage |
| Domain experts | `SKILL.md` rules | Add domain-specific instructions |
| Developers | Python integration | Build new skill types |

**Key files**:
- `skills/registry.yaml` - Which skills exist
- `skills/rag-quality-assurance/SKILL.md` - Behavioral rules
- `skills/rag-quality-assurance/references/thresholds.yaml` - Numeric config

**After editing**: Restart the server for changes to take effect.

---

*Document Version: 1.3*
*Last Updated: February 2026*
*Applies to: AInstein Skills Framework v1.0*

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.3 | Feb 2026 | Architecture decision: Skills UI will extend FastAPI (not Streamlit) |
| 1.2 | Feb 2026 | Added Progressive Loading roadmap, updated UI MVP with testing panel |
| 1.1 | Feb 2026 | Added Identity Configuration, Tool Return Fields, fixed Integration Points table |
| 1.0 | Feb 2026 | Initial release |
