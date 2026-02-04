# Skills Directory

This directory contains Agent Skills that extend the RAG system's behavior.
Skills follow the [agentskills.io](https://agentskills.io) open standard format.

## What Are Skills?

Skills are folders of instructions and configuration that teach the system
how to behave in specific situations. They enable:

- Externalizing behavioral rules (no code changes needed)
- Configuring thresholds and limits
- Non-developers can edit rules via markdown files

## Directory Structure

```
skills/
├── registry.yaml                    # Skill registry (activation rules)
├── README.md                        # This file
└── rag-quality-assurance/           # First skill
    ├── SKILL.md                     # Main rules file (YAML frontmatter + markdown)
    └── references/
        └── thresholds.yaml          # Configuration values
```

## How Skills Work

1. **Registry** (`registry.yaml`) defines which skills exist and when they activate
2. **SKILL.md** contains behavioral rules injected into system prompts
3. **References** contain configuration values loaded at runtime

## Creating a New Skill

1. Create a folder under `skills/` with your skill name
2. Add a `SKILL.md` file with YAML frontmatter:

```yaml
---
name: my-skill-name
description: >
  What this skill does and when it should activate.
  This description helps the system know when to use it.
---

# My Skill Name

[Your instructions and rules here in markdown format]
```

3. Optionally add `references/` folder for configuration files
4. Register the skill in `registry.yaml`

## Editing Existing Skills

### Changing Thresholds

Edit `skills/rag-quality-assurance/references/thresholds.yaml`:

```yaml
abstention:
  distance_threshold: 0.5    # Increase to allow weaker matches
  min_query_coverage: 0.2    # Decrease to be more permissive
```

### Changing Behavioral Rules

Edit `skills/rag-quality-assurance/SKILL.md`:

- The YAML frontmatter (between `---` markers) controls metadata
- The markdown body contains rules injected into prompts

### Restart Required

After editing skills, restart the application to reload changes.

## Registry Configuration

The `registry.yaml` file controls skill activation:

```yaml
skills:
  - name: rag-quality-assurance
    path: rag-quality-assurance/SKILL.md
    description: "Anti-hallucination rules"
    enabled: true           # Set to false to disable
    auto_activate: true     # Always inject into prompts
    triggers:               # Additional activation keywords
      - "adr"
      - "principle"
```

## Available Skills

| Skill | Description | Auto-Activate |
|-------|-------------|---------------|
| `rag-quality-assurance` | Anti-hallucination rules and citation requirements | Yes |

## Future Skills (Planned)

- `alliander-domain-expert` - Energy sector terminology
- `skosmos-terminology` - SKOSMOS-first lookup rules
