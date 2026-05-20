# AInstein Plugin Author Guide

**Audience:** developers writing a plugin intended to be loaded by
AInstein. For the current bundled-plugin model and discovery rules, see
the "Plugins" section of the repository `README.md`.

---

## 1. Plugin layout

A plugin is a directory containing a `.ainstein-plugin/` subdirectory
with at least a `plugin.json`. Everything else is optional but
positioned at conventional locations so cross-host portability with
other plugin-supporting agentic-IDE hosts is preserved.

```
<plugin-root>/
├── .ainstein-plugin/
│   ├── plugin.json            # required
│   ├── skills-registry.yaml   # required if the plugin ships skills
│   └── thresholds.yaml        # optional — per-plugin retrieval/truncation tuning
├── .mcp.json                  # optional — legacy MCP server declarations
├── hooks/                     # optional — hook scripts
├── mcp/<server>/start.sh      # optional — stdio MCP server entry points
├── shared-references/<group>/ # optional — cross-skill reference docs
├── skills/<skill>/SKILL.md    # one per skill the plugin declares
└── templates/<name>/          # plugin-internal; AInstein doesn't read these
```

Coexists with sibling host-specific manifest directories (each agentic-IDE
host has its own `.<host>-plugin/` convention) per the locked Option 2
layout — each host has its own self-contained manifest dir, and shared
assets (`skills/`, `mcp/`, `hooks/`, `shared-references/`) live at the
plugin root for reuse across hosts.

`<plugin-root>` above is *one plugin*. The AInstein repository is the
**host**: deployed plugins live under `<repo>/plugins/<plugin-name>/`.
Three plugins are committed and bundled: `ainstein-kernel`
(`role: kernel` — always-on host behavior, non-removable),
`esa-workflow` (`role: domain`), and `enterpower-architecture`
(`role: domain` — authoritative architecture provider). Any *other*
plugin you deploy into `plugins/` is gitignored (only these three are
tracked). The repo root is **not** a plugin and is never scanned for
`.ainstein-plugin/`.

---

## 2. `.ainstein-plugin/plugin.json`

```json
{
  "name": "my-plugin",
  "runtime": "ainstein",
  "role": "domain",
  "manifest_version": "1.0",
  "version": "0.1.0",
  "description": "What the plugin does, one sentence",
  "author": {"name": "Your Team"},
  "requires_host_api": {"artifact_materialization": ">=1"},
  "hooks": "./.ainstein-plugin/hooks.json",
  "mcpServers": "./.ainstein-plugin/mcp-config.json"
}
```

* **`name`** — globally unique plugin identifier. Used as the namespace
  for `conflicts_with` declarations. Bare ASCII identifier convention
  (lowercase, hyphens OK).
* **`runtime`** — must be exactly `"ainstein"`. Plugins with a different
  runtime are skipped at discovery without error (so the same source
  tree can carry per-host manifests without cross-contamination).
* **`role`** — `"domain"` (default if omitted) or `"kernel"`. Authoring
  a normal capability plugin: use `"domain"` (or omit). `"kernel"` is
  reserved for the bundled host-behavior plugin and carries host-enforced
  policy — see *Kernel policy* below. An **unknown** role is rejected
  early at load (a typo cannot silently change host policy).
* **`manifest_version`** — manifest-contract version (defaults to
  `"1.0"` if omitted). Declares which manifest schema the plugin was
  written against; additive, so omitting it keeps legacy plugins loading.
* **`version`** — SemVer string. Surfaced in the UI plugin accordion
  header.
* **`description`** — one-line summary surfaced in the UI.
* **`author`** — object with at least `name`. Other fields ignored.
* **`requires_host_api`** — optional map of `host-capability → version
  constraint` (e.g. `{"artifact_materialization": ">=1"}`). The host
  publishes its own capability set + versions; a plugin that requires a
  capability the host does not provide fails fast with an actionable
  error. Declare this **only** for capabilities you actually use (e.g. a
  file-touching post-write hook needs `artifact_materialization`).
  Omitting it = the plugin needs no special host capability (the common
  case) and keeps filename-only semantics.
* **`hooks`** — optional. Either an inline object matching the hooks
  schema, OR a string path to a JSON file with the same schema. Relative
  paths resolve against the plugin root.
* **`mcpServers`** — optional. Inline-or-path-referenced, like `hooks`.
  AInstein also reads a plugin-root `.mcp.json` as a legacy fallback if
  the manifest field is absent.

### Kernel policy (`role: kernel`)

Most plugin authors never set this — it is reserved for the bundled
`ainstein-kernel` plugin, which carries AInstein's always-on host
behavior (identity, persona, formatter, RAG quality, document ontology).
The host **enforces** kernel policy; an author should understand it
because it constrains what a domain plugin can do to a kernel skill:

* **Non-removable / implicitly always-loaded.** A `role: kernel`
  plugin's skills cannot be disabled — every mutation path
  (`set_skill_enabled`, `set_skill_enabled_in_plugin`,
  `set_group_enabled`) rejects it, and a kernel skill marked
  `enabled: false` in registry YAML is **force-enabled at load** with a
  warning (config drift cannot silently remove host behavior).
* **Non-shadowable.** A domain plugin's `conflicts_with` /
  provider-precedence can never disable a kernel skill; kernel-role
  plugins are excluded from domain-provider precedence resolution.
* **Startup fail-fast.** If discovery finds plugins but **none** declares
  `role: kernel`, AInstein refuses to start (a domain-only deployment
  can route nothing). At least the kernel plugin must be present.

Practical takeaway for a domain-plugin author: you cannot shadow,
disable, or override a kernel skill. Contribute alongside it (your tags,
slash commands, routing, MCP servers aggregate with the kernel's); the
kernel is the host substrate, not a peer you can collide with.

---

## 3. `.ainstein-plugin/skills-registry.yaml`

Skills are declared either at the top level or nested inside groups
(groups bundle related skills + share a `shared_references` target).

```yaml
version: "1.0"

groups:
  - name: my-group
    description: "Group description"
    enabled: true
    inject_into_tree: true
    inject_mode: on_demand
    tags: [my-tag]
    shared_references: my-group              # → shared-references/my-group/*.md
    skills:
      - name: my-grouped-skill
        path: my-grouped-skill/SKILL.md
        description: "Member of my-group"
        load_order: 1

skills:
  - name: my-toplevel-skill
    path: my-toplevel-skill/SKILL.md
    description: "Top-level skill"
    enabled: true
    inject_into_tree: false
    inject_mode: on_demand                   # see "Slash command eligibility" below
    execution: archimate                     # see "Per-skill agent routing"
    tags: [my-tag-2]
    mcp_servers: [my-server]                 # see "Per-skill MCP routing"
    conflicts_with: [other-plugin/same-name] # see "Skill-name collisions"
```

### Required per-skill fields
* **`name`** — unique within the plugin. May collide with skills in
  other plugins (see "Skill-name collisions").
* **`path`** — relative path from the plugin's `skills/` directory to
  `SKILL.md`.
* **`description`** — one-line summary. Used by the UI and by the
  Persona's classification prompt addendum.

### Optional per-skill fields
* **`enabled`** (default `true`) — initial state. The UI can toggle this;
  the value on disk is updated via `set_skill_enabled`.
* **`inject_into_tree`** (default `true`) — when true, the skill's
  SKILL.md content is injected into agent system prompts.
* **`inject_mode`** (`"always"` or `"on_demand"`, default `"always"`) —
  controls when the skill is loaded into the agent's context AND whether
  it's available as a slash command. `"on_demand"` = invocable as
  `/<skill-name>`; `"always"` = framework-style, NOT invocable.
* **`execution`** — which agent type handles this skill when its tags
  fire. Valid values: `tree`, `archimate`, `vocabulary`, `principle`,
  `repo_analysis`, `generation`, `document_analysis`. Default `tree`.
* **`tags`** — list of tag strings used by the Persona to match user
  intent. Tags from canonical AInstein routing destinations (`archimate`,
  `vocabulary`, `principle-quality`, `generate-principle`, `repo-analysis`)
  are documented in the Persona's hardcoded prompt; new tags surface in
  the dynamic "Additional plugin tags" addendum.
* **`mcp_servers`** — list of MCP server names this skill needs. See
  "Per-skill MCP routing".
* **`conflicts_with`** — list of `<plugin>/<skill>` shorthand strings.
  See "Skill-name collisions".
* **`validation_tool`** — function name AInstein calls after generation.
* **`content_type`** — MIME type for skill-produced artifacts.
* **`load_order`** — integer sort key within a group.

---

## 4. Slash command eligibility

A skill is invocable as `/<name>` if and only if:

* it's registered in the multi-plugin registry,
* `inject_mode == "on_demand"` (per the locked decision D3 — this
  excludes always-loaded framework skills without needing a separate
  registry field), and
* the registry entry is currently `enabled`.

The slash router lives pre-Persona in `chat_ui.py:event_generator` and
short-circuits classification when the message matches
`^/<lowercase-name>[ args]$`. The args string (everything after the
first whitespace) becomes the `rewritten_query` of the synthesized
`PersonaResult`.

---

## 5. Per-skill agent routing

The `execution` field determines which agent receives the skill's
content + MCP tools. The mapping:

| `execution` value | Agent built in `chat_ui.lifespan` |
|---|---|
| `tree` (default) | `RAGAgent` |
| `archimate` | `ArchiMateAgent` |
| `vocabulary` | `VocabularyAgent` |
| `principle` | `PrincipleAgent` |
| `repo_analysis` | `RepoAnalysisAgent` |
| `document_analysis` | `DocumentAnalysisAgent` |
| `generation` | The generation pipeline (`src/aion/generation.py`) |

Plugin authors should pick the `execution` that best matches the skill's
output shape. Wrong routing produces an awkward UX (tool call mismatch)
but no functional failure.

---

## 6. Per-skill MCP routing

Each skill can declare `mcp_servers: [<server-name>, ...]`. At AInstein
startup (`lifespan`), the union of MCP servers declared by skills
routing to each agent type is computed via
`tool_bridge.mcp_servers_for_agent`. Each agent receives ONLY the tools
from servers declared by skills routing to it — preventing tool-schema
bloat across plugins.

Servers are declared in `.mcp.json` at the plugin root OR in the
manifest's `mcpServers` field. Each server has:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "bash",
      "args": ["${AINSTEIN_PLUGIN_ROOT}/mcp/my-server/start.sh"],
      "env": {"OPTIONAL": "..."},
      "cwd": "${AINSTEIN_PLUGIN_ROOT}/mcp/my-server"
    }
  }
}
```

`${AINSTEIN_PLUGIN_ROOT}` is the only substitution variable AInstein
recognizes — resolves to the absolute path of the plugin's root
directory at registration time. The variable name is intentionally
AInstein-specific so the same `.mcp.json` declaration doesn't conflict
with sibling host-specific manifests using their own variables.

### MCP server lifecycle (important)

MCP servers spawn EAGERLY at AInstein `lifespan` startup, not lazily on
first tool invocation. This is a deliberate trade-off:
`ClientSession.list_tools()` requires an initialized session, which
requires the server process to be running. The cold-start cost
(typically 5–15 s for Vite-based servers) is paid once at startup and
parallelized across all servers via `asyncio.gather`. After lifespan,
slash commands return sub-second on every invocation.

Plugin authors targeting AInstein should size their server cold-start
accordingly: too slow → measurable lifespan delay for everyone who
loads the plugin, even if they never invoke the corresponding slash
command.

---

## 7. Hooks

A plugin can declare `PostToolUse` hooks that fire when AInstein saves
an artifact (the only `Write`-style event AInstein currently emits).

```json
{
  "PostToolUse": [
    {
      "matcher": "Write",
      "hooks": [
        {
          "type": "command",
          "command": "${AINSTEIN_PLUGIN_ROOT}/hooks/my-hook.sh"
        }
      ]
    }
  ]
}
```

### Stdin payload

The hook script receives a JSON object on stdin:

```json
{"tool_name": "Write", "tool_input": {"file_path": "<artifact-filename>"}}
```

### `file_path` semantics — important caveat

AInstein stores artifacts in SQLite, not on disk. The `file_path`
passed to hooks is the artifact's **filename** (e.g. `"explorer.html"`),
NOT a real filesystem path. Scripts that need the actual content must:

* match on the filename pattern in their own `if`-guard, then
* use AInstein's artifact-download API by ID to retrieve the content
  (not yet exposed via a stable URL — defer to a future RFC).

A hook script authored against the partner agentic-IDE host's `Write`
tool semantics (where `file_path` is a real on-disk path) won't work
unchanged against AInstein — the file isn't on disk. This is documented
explicitly so plugin authors don't ship hooks that fail silently against
AInstein.

### Hook environment

Default: parent process environment minus secrets (regex-filtered:
`AINSTEIN_*`, `*_KEY`, `*_TOKEN`, `*_PASSWORD`, `*_SECRET`). Plus
`${AINSTEIN_PLUGIN_ROOT}` substituted in the `command` field.

Per-hook override: declare `"env": ["VAR1", "VAR2"]` to restrict to a
specific allowlist (still filtered for secrets — defence in depth).

### Hook lifecycle

* Spawn synchronously, 30s timeout.
* Exit code is **advisory** — non-zero is logged at INFO but doesn't
  block AInstein's artifact save.
* stderr is logged.
* No access to AInstein's in-memory state — pure stdin/stdout/exit.

---

## 8. Skill-name collisions

Two plugins can declare skills with the same name. AInstein resolves
this via the `conflicts_with` mechanism + a duplicate-check preflight.

### Behavior at load

1. Plugins are parsed in discovery order (env var → user dir → in-tree).
2. For each enabled skill with `conflicts_with: [<plugin>/<skill>]`,
   the multi-registry checks whether that exact peer is loaded AND
   enabled. If so, the declaring entry is auto-disabled IN-MEMORY (YAML
   on disk unchanged), logged at INFO.
3. After auto-disable resolution, the multi-registry builds the owner
   map. Any REMAINING duplicate name across enabled plugins raises
   `DuplicateSkillError` at startup with both plugin names in the
   message.

### Behavior at toggle

The plugin-scoped enable endpoint
`PUT /api/plugins/{plugin}/skills/{skill}/enabled` runs a duplicate-
check preflight BEFORE persisting. If enabling the target would create
a duplicate enabled skill, the API returns HTTP 409 with a structured
`detail` body naming the conflict — the UI surfaces this as an
actionable error banner.

### When to use `conflicts_with`

Declare `conflicts_with: [<other-plugin>/<same-skill-name>]` when:

* your plugin's skill is a superset/replacement for another plugin's,
  AND
* you want loads of both plugins to succeed (with your copy yielding
  to theirs).

If both plugins are equally authoritative, leave `conflicts_with` empty.
Operators can resolve manually via the UI toggle (with the preflight
catching the conflict before it fires at runtime).

### Programmatic API caveat

The legacy `PUT /api/skills/{name}/enabled` endpoint (without plugin
scope) routes to the **first plugin in load order** that defines the
named skill. Under collision, this may not target the plugin you
intended. Programmatic API consumers managing multi-plugin installs
should use the plugin-scoped `PUT /api/plugins/{plugin}/skills/{skill}/enabled`
endpoint instead — it routes explicitly and runs the dup-check
preflight.

---

## 9. Shared references

A group can declare `shared_references: <group-name>` pointing to
`<plugin-root>/shared-references/<group-name>/`. All `.md` files in
that directory are merged into each member skill's reference set —
without skill-local `references/` files duplicating the shared
content.

Use this when multiple skills in a group share boilerplate (element
type tables, allowed-relation matrices, etc.).

---

## 10. Plugin discovery

AInstein discovers plugins in this order at startup:

1. **`AINSTEIN_PLUGINS` env var** — colon-separated absolute paths.
   Each path is treated as a plugin root if it contains
   `.ainstein-plugin/`. Use this for development and CI.
2. **`~/.ainstein/plugins/*/`** — auto-discovery. Drop your plugin's
   root directory into `~/.ainstein/plugins/` and AInstein finds it
   on next start.
3. **In-tree deployment dir** — every child of `<repo>/plugins/` that
   contains `.ainstein-plugin/`. This is how the bundled
   `ainstein-kernel`, `esa-workflow`, and `enterpower-architecture`
   load, and where you can also drop a plugin for a checked-out repo.
   The repo root itself is never scanned.

In-tree is **last**, so a plugin supplied via the env var or
`~/.ainstein/plugins/` wins the `conflicts_with` tie-breaker over a
same-named in-tree skill. If discovery finds **zero** plugins AInstein
fails fast — at minimum the `ainstein-kernel` plugin (`role: kernel`)
must be present (there is no synthesized fallback).

Trust model: **loading a plugin grants it AInstein-process privileges.**
Hooks run with `os.environ` minus secrets; MCP servers are subprocesses
of AInstein. No sandboxing in this release. Don't install plugins from
sources you don't trust.

---

## 11. Source-install only

This release supports source-install plugins (env var, user-directory,
or dropped into `<repo>/plugins/`). Pip-installable plugins via
`importlib.resources` are out of scope; AInstein doesn't introspect
installed Python packages for plugin manifests.

---

## 12. References

* Current bundled-plugin model + discovery rules: repository `README.md`,
  "Plugins" section
* Reference fixture: `tests/fixtures/fake_plugin/` (smallest end-to-end
  example exercising every locked-decision path)
* Critical implementation files: `src/aion/skills/plugin.py`,
  `src/aion/skills/plugin_loader.py`, `src/aion/skills/multi_registry.py`
