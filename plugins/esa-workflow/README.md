# esa-workflow

**ESA Workflow — ESA-specific capability + document ontology**

`role: domain`. ESA-specific behaviour that is *not* generic host
behaviour: SKOSMOS vocabulary lookup and the ESA ADR/PCP/DAR document
ontology.

## What this plugin does

Provides ESA-internal terminology/definition lookup (via the SKOSMOS
REST API) and the ESA document ontology that drives ADR/PCP/DAR naming,
numbering, relationships, and the "document N is ambiguous"
disambiguation. It is a domain plugin because this knowledge is
ESA-specific, not part of the generic AInstein host.

## Skills

| Skill | inject_mode | Slash | Description |
|---|---|---|---|
| **skosmos-vocabulary** | on_demand | `/skosmos-vocabulary` | Vocabulary and terminology lookup via the SKOSMOS REST API |
| **esa-document-ontology** | always | — | ADR/PCP/DAR naming, numbering, relationships, disambiguation. Consumed at ingestion (`_load_principle_owner_map`) and per query for "document N" disambiguation |

## Slash commands

| Command | What it does |
|---|---|
| `/skosmos-vocabulary` | Look up a term/definition via the SKOSMOS REST API |

`esa-document-ontology` has no slash command — it is `inject_mode:
always` host-adjacent behaviour, injected on every turn so retrieval and
disambiguation see the ESA document taxonomy.

## Design note — esa-document-ontology placement

`esa-document-ontology` previously lived in `ainstein-kernel` (Phase-4
Decision 2: it is ingestion- and disambiguation-critical). It was moved
here by explicit author decision because the ESA document ontology is
**ESA-specific**, not generic host behaviour. Owned consequence: it is
no longer kernel-protected (it can be disabled), and a deployment
*without* `esa-workflow` loses ADR/PCP/DAR disambiguation. It remains
`inject_mode: always` so behaviour is preserved whenever this plugin is
enabled.

## References

`esa-document-ontology/references/registry-index.md` — the condensed ESA
document registry, resolved through the owning plugin's loader (not a
repo-root path). No cross-skill shared references in this plugin (the
two skills do not share `.md` reference files), so there is no
`shared-references/` directory.

## Plugin structure

```
.ainstein-plugin/
  plugin.json              # manifest: name, runtime, role=domain, version, manifest_version
  skills-registry.yaml     # skosmos-vocabulary (on_demand) + esa-document-ontology (always)
  thresholds.yaml          # per-plugin tuning (currently none required)
skills/
  skosmos-vocabulary/SKILL.md
  esa-document-ontology/
    SKILL.md
    references/registry-index.md
README.md
```

## Integration

Loaded by AInstein from `plugins/` as a domain plugin. See the
repository `README.md` "Plugins" section for discovery rules and the
full bundled set.

## Authors

Alliander — Enterprise Systems Architecture (ESA)

## Version

0.1.0
