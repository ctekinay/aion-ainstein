# ainstein-kernel

**AInstein Kernel — always-on host behaviour plugin**

`role: kernel`. This is the host substrate of AInstein: the always-on
behaviour that runs on every turn (identity, intent classification,
response formatting, RAG quality control). It is not an invocable
capability set — there are no slash commands here.

## What this plugin does

Loaded first and unconditionally, it gives AInstein its conversational
identity, classifies user intent and rewrites queries (the Persona),
enforces anti-hallucination/citation rules on retrieval answers, and
formats list/statistical responses. Domain capability (ArchiMate,
principles, repo analysis, ESA workflow) is contributed by separate
domain plugins; the kernel aggregates their contributions.

## Skills

| Skill | inject_mode | Description |
|---|---|---|
| **ainstein-identity** | always | Core identity rules and scope boundaries for the assistant |
| **persona-orchestrator** | always | Intent classification and query rewriting for the Persona layer |
| **rag-quality-assurance** | always | Anti-hallucination rules + citation requirements; owns the RAG retrieval/abstention/truncation thresholds |
| **response-formatter** | always | List-based responses with statistics, follow-up questions, visualization suggestions |

No slash commands — every skill is always-on host behaviour, not an
on-demand capability.

## Kernel policy (host-enforced)

Because `role: kernel`, the host enforces:

- **Non-removable / implicitly always-loaded** — kernel skills cannot be
  disabled via any mutation path; a kernel skill marked
  `enabled: false` in registry YAML is force-enabled at load with a
  warning.
- **Non-shadowable** — a domain plugin's `conflicts_with` /
  provider-precedence can never disable a kernel skill.
- **Startup fail-fast** — if discovery finds plugins but none declares
  `role: kernel`, AInstein refuses to start.

## References

`rag-quality-assurance` thresholds (abstention distance, retrieval
limits, truncation) live in `.ainstein-plugin/thresholds.yaml` and are
consumed via `get_skill_tuning("rag-quality-assurance", …)`, which
routes to this plugin. Persona conversation-history sizing
(`verbatim_window`, `message_truncation_chars`) is **system-infra** and
lives in `src/aion/config/runtime.yaml`, not here — persona context
sizing is host behaviour, not a per-plugin threshold.

## Plugin structure

```
.ainstein-plugin/
  plugin.json              # manifest: name, runtime, role=kernel, version, manifest_version
  skills-registry.yaml     # the 4 always-on kernel skills
  thresholds.yaml          # RAG abstention/retrieval/truncation tuning (rag-quality-assurance)
skills/
  ainstein-identity/SKILL.md
  persona-orchestrator/SKILL.md
  rag-quality-assurance/SKILL.md
  response-formatter/SKILL.md
README.md
```

## Integration

Loaded by AInstein from `plugins/` first and unconditionally. The repo
root is the host, not a plugin. See the repository `README.md` "Plugins"
section for the discovery rules and the full bundled set.

## Authors

Alliander — Enterprise Systems Architecture (ESA)

## Version

0.1.0
