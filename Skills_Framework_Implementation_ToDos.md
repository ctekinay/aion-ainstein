# Skills Framework Implementation - TODO List

> **Purpose**: Externalize hardcoded rules, thresholds, and prompts using the Agent Skills open standard format (agentskills.io).
>
> **Branch**: Create a new feature branch for this implementation
>
> **Date**: 2026-02-04

---

## Overview

### Problem
Currently, behavioral rules, abstention thresholds, and system prompts are hardcoded across multiple files:

| Component | Current Location | Status |
|-----------|------------------|--------|
| Abstention thresholds | `src/elysia_agents.py:17-18` | Hardcoded |
| Main system prompt | `src/elysia_agents.py:652` | Hardcoded |
| Comparison prompts | `src/chat_ui.py:951, 955` | Hardcoded |
| Retrieval limits | `src/chat_ui.py:691-694` | Hardcoded |

### Solution
Implement a Skills framework that:
1. Externalizes rules to editable markdown/YAML files
2. Allows non-developers to modify behavior without code changes
3. Follows the `agentskills.io` open standard format
4. Injects skill content into system prompts at runtime

### End State
| Component | After Implementation |
|-----------|---------------------|
| Abstention thresholds | Loaded from `skills/rag-quality-assurance/references/thresholds.yaml` |
| Main system prompt | Skill-injected from `skills/rag-quality-assurance/SKILL.md` |
| Comparison prompts | Skill-injected from `skills/rag-quality-assurance/SKILL.md` |
| Retrieval limits | Loaded from `skills/rag-quality-assurance/references/thresholds.yaml` |

---

## Phase 1: Setup

| # | Task | Details | Status |
|---|------|---------|--------|
| 1.1 | Create new branch | `git checkout -b feature/skills-framework` | [ ] |

---

## Phase 2: Skills Directory Structure

| # | Task | File/Directory | Description | Status |
|---|------|----------------|-------------|--------|
| 2.1 | Create skills directory | `skills/` | Root directory for all skills | [ ] |
| 2.2 | Create RAG quality skill folder | `skills/rag-quality-assurance/` | First skill | [ ] |
| 2.3 | Create main skill file | `skills/rag-quality-assurance/SKILL.md` | YAML frontmatter + behavioral rules | [ ] |
| 2.4 | Create references folder | `skills/rag-quality-assurance/references/` | Supporting config files | [ ] |
| 2.5 | Create thresholds config | `skills/rag-quality-assurance/references/thresholds.yaml` | Abstention thresholds, retrieval limits | [ ] |
| 2.6 | Create skills registry | `skills/registry.yaml` | Skill metadata, activation triggers | [ ] |

### Expected Structure
```
skills/
├── registry.yaml
├── README.md
└── rag-quality-assurance/
    ├── SKILL.md
    └── references/
        └── thresholds.yaml
```

---

## Phase 3: SkillLoader Module

| # | Task | File | Description | Status |
|---|------|------|-------------|--------|
| 3.1 | Create skills package | `src/skills/__init__.py` | Package exports | [ ] |
| 3.2 | Create skill loader | `src/skills/loader.py` | Parse SKILL.md, load references, extract thresholds | [ ] |
| 3.3 | Create registry manager | `src/skills/registry.py` | Read registry.yaml, manage skill activation | [ ] |

### Expected Structure
```
src/skills/
├── __init__.py
├── loader.py
└── registry.py
```

### Key Functions
- `SkillLoader.load_skill(skill_path)` - Parse SKILL.md and return skill object
- `SkillLoader.get_skill_content(skill_name)` - Get injectable prompt content
- `SkillLoader.get_thresholds(skill_name)` - Get threshold configuration
- `SkillRegistry.get_active_skills(query)` - Get skills that should activate for a query

---

## Phase 4: Integration - Prompt Injection

| # | Task | File | What Changes | Status |
|---|------|------|--------------|--------|
| 4.1 | Inject skills into main prompt | `src/elysia_agents.py` | Line ~652: System prompt becomes skill-injectable | [ ] |
| 4.2 | Inject skills into OpenAI comparison prompt | `src/chat_ui.py` | Line 951: OpenAI prompt becomes skill-injectable | [ ] |
| 4.3 | Inject skills into Ollama comparison prompt | `src/chat_ui.py` | Line 955: Ollama prompt becomes skill-injectable | [ ] |

### Integration Pattern
```python
# Before (hardcoded)
system_prompt = """You are AInstein..."""

# After (skill-injectable)
from src.skills import SkillLoader

loader = SkillLoader()
skill_rules = loader.get_skill_content("rag-quality-assurance")

system_prompt = f"""You are AInstein...

{skill_rules}
"""
```

---

## Phase 5: Integration - Threshold Externalization

| # | Task | File | What Changes | Status |
|---|------|------|--------------|--------|
| 5.1 | Remove hardcoded `DISTANCE_THRESHOLD` | `src/elysia_agents.py` | Line 17: Load from skill config | [ ] |
| 5.2 | Remove hardcoded `MIN_QUERY_COVERAGE` | `src/elysia_agents.py` | Line 18: Load from skill config | [ ] |
| 5.3 | Remove hardcoded retrieval limits | `src/chat_ui.py` | Lines 691-694: Load from skill config | [ ] |
| 5.4 | Update `should_abstain()` | `src/elysia_agents.py` | Use skill-loaded thresholds | [ ] |

### Integration Pattern
```python
# Before (hardcoded)
DISTANCE_THRESHOLD = 0.5
MIN_QUERY_COVERAGE = 0.2

# After (skill-loaded)
from src.skills import SkillLoader

loader = SkillLoader()
thresholds = loader.get_thresholds("rag-quality-assurance")

DISTANCE_THRESHOLD = thresholds.get("distance_threshold", 0.5)
MIN_QUERY_COVERAGE = thresholds.get("min_query_coverage", 0.2)
```

---

## Phase 6: Testing

| # | Task | Description | Status |
|---|------|-------------|--------|
| 6.1 | Test skill parsing | Verify SKILL.md YAML frontmatter + markdown body parsed correctly | [ ] |
| 6.2 | Test threshold loading | Verify thresholds loaded from `references/thresholds.yaml` | [ ] |
| 6.3 | Test prompt injection | Verify skill rules appear in system prompts | [ ] |
| 6.4 | Test abstention logic | Verify `should_abstain()` works with externalized thresholds | [ ] |
| 6.5 | Test comparison mode | Verify both OpenAI and Ollama prompts get skill injection | [ ] |

### Test Cases
1. **Skill Loading**: Load `rag-quality-assurance` skill, verify name and description parsed
2. **Threshold Loading**: Verify `distance_threshold: 0.5` loaded correctly
3. **Prompt Injection**: Ask a question, verify skill rules in system prompt
4. **Abstention**: Ask irrelevant question, verify abstention still works
5. **Comparison Mode**: Run comparison, verify both models get same skill rules

---

## Phase 7: Documentation

| # | Task | File | Description | Status |
|---|------|------|-------------|--------|
| 7.1 | Update ADR | `docs/decisions/ADR-xxxx-confidence-based-abstention...md` | Document skills implementation | [ ] |
| 7.2 | Add skills README | `skills/README.md` | How to create/edit skills (for non-devs) | [ ] |

### Skills README Contents
- What are skills?
- How to edit existing skills
- How to create new skills
- YAML frontmatter format
- Threshold configuration format

---

## Phase 8: Commit & Push

| # | Task | Description | Status |
|---|------|-------------|--------|
| 8.1 | Commit changes | Clear commit message describing skills framework | [ ] |
| 8.2 | Push to branch | `git push -u origin feature/skills-framework` | [ ] |

---

## Summary

| Phase | Tasks | Effort | Status |
|-------|-------|--------|--------|
| Phase 1: Setup | 1 | Low | [ ] |
| Phase 2: Skills Directory | 6 | Low | [ ] |
| Phase 3: SkillLoader Module | 3 | Medium | [ ] |
| Phase 4: Prompt Injection | 3 | Medium | [ ] |
| Phase 5: Threshold Externalization | 4 | Medium | [ ] |
| Phase 6: Testing | 5 | Medium | [ ] |
| Phase 7: Documentation | 2 | Low | [ ] |
| Phase 8: Commit & Push | 2 | Low | [ ] |
| **Total** | **26 tasks** | | |

---

## Files Summary

### New Files
```
skills/
├── registry.yaml
├── README.md
└── rag-quality-assurance/
    ├── SKILL.md
    └── references/
        └── thresholds.yaml

src/skills/
├── __init__.py
├── loader.py
└── registry.py
```

### Modified Files
```
src/elysia_agents.py    → Skill injection + externalized thresholds
src/chat_ui.py          → Skill injection + externalized limits
docs/decisions/ADR-xxxx...md → Updated documentation
```

### Unchanged Files
```
src/agents/base.py
src/agents/architecture_agent.py
src/agents/vocabulary_agent.py
src/agents/policy_agent.py
src/agents/orchestrator.py
src/weaviate/*
src/loaders/*
src/config.py
```

---

## Future Considerations

### Additional Skills (Not in Scope)
- `alliander-domain-expert` - Energy sector terminology rules
- `citation-format` - ADR.XX, PCP.XX formatting rules
- `skosmos-terminology` - SKOSMOS-first lookup rules

### Potential Enhancements
- Skill versioning
- A/B testing with different skill configurations
- Skill validation CLI command
- Hot-reload skills without restart
