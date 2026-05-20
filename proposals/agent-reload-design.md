# Agent & Persona Reload — Current Design

**Status:** Implemented / current behavior (not a proposal). Describes
how AInstein responds to plugin/registry changes today.
**Citations:** by symbol name, not line numbers, so this does not rot as
files shift. Migration/program context and the evidence map are in
[plugin-migration-retrospective.md](plugin-migration-retrospective.md).

---

## 1. Summary — three distinct paths

There is no single "reload" in AInstein. Three independent things react
to a plugin/registry change, with **deliberately different** liveness:

| Path | Trigger | Liveness |
|---|---|---|
| **Persona classification** (intent routing + cross-plugin skill-tag union) | registry `load()`/`reload()` | **Live** — rebuilt via keyed `on_reload` |
| **Agent MCP tool sets** after a plugin enable/disable toggle | skills-UI toggle | **Restart-required** — accepted limitation |
| **Agent MCP tool sets** after an LLM model switch | `set_llm_settings` | **Live** — re-derived; no longer stripped |

Rationale for the asymmetry is in §3 (why the toggle path is not live)
and §4 (why the model-switch path had to be).

## 2. Persona reload — live, keyed (implemented)

**Mechanism.** `MultiPluginRegistry` holds reload callbacks in a
**keyed dict** (`_reload_callbacks: dict[str, Callable]`).
`on_reload(callback, *, key=None)` is **register-or-replace**:
registering under an existing key replaces the prior callback;
`key=None` generates a unique key (back-compat for any unkeyed
registrant). `_fire_reload_callbacks()` iterates the dict's values in
insertion order at the end of every real `load()`.

**The one registrant.** `Persona` registers
`Persona._build_classification_prompt` under **`key="persona"`**. On any
registry load/reload it rebuilds the classification prompt, including
`_build_skill_tags_addendum()` — the union of every enabled plugin's
classification tags across the whole bundled set (kernel + domain
plugins). This is the cross-plugin contribution surface; the split into
three plugins did not change its behavior because the addendum is keyed
plugin-agnostically.

**Why keyed, not a list.** Re-instantiating `Persona` on the
process-wide registry would, with a plain list, append a second
callback and leak the old one (each instance is a distinct callable, so
dedupe-by-identity would not help). Keying by **component role**
(`"persona"`), not instance identity, means a re-instantiated Persona's
hook supersedes the prior one — zero accumulation by construction.

**Old-instance semantics (intended).** When a new `Persona` registers
`key="persona"` and replaces the old, an old instance still serving an
in-flight request is de-registered; a reload during that request will
not rebuild the *old* instance's prompt. This is intended — the old
instance is being torn down and its next query would use the new
instance anyway. Stated in the `on_reload` docstring.

## 3. Agent MCP tool set on plugin toggle — restart-required (accepted)

When an operator enables/disables a plugin/skill via the skills UI, the
**Persona** picks it up on the next query (§2), but the **agents'** MCP
tool sets do **not** live-rebuild. A server restart re-derives them.
This is an **accepted limitation**, not a defect. The canonical
statement lives as the agent-side-reload-gap NOTE in `chat_ui.py`
(near the lifespan agent construction).

**Why it is not built:**
- Plugin enable/disable is an infrequent operator action, not a
  per-query hot path.
- A live rebuild needs a sync→async bridge (`on_reload` fires from sync
  `load()`; MCP tool discovery is async), a multi-global atomic swap of
  the agent/label/pixel-map tuple, and in-flight-request snapshot
  semantics. Its worst-case failure is **silent desync of the VSCode
  pixel-agents extension**, and there is no headless pixel-agents test
  harness to gate that risk.
- The cost/complexity and silent cross-extension failure mode exceed the
  value of avoiding a restart for a rare action. No validated
  requirement demands live rebuild.

If a concrete operator requirement ever makes a restart unacceptable,
the proceed-path design is: lazy dirty-flag rebuilt at the next request
boundary (never mid-query); the agent reference brought into the same
request-start snapshot as labels + pixel map; the agent-rebuild hook
registered under `key="agents"` via the same keyed `on_reload` contract
so it cannot leak. It is **not** built today.

## 4. Model switch — re-derives MCP tools (implemented)

A separate, previously-silent bug: switching the LLM model
(`set_llm_settings`) rebuilds every agent. Before the fix,
`_rebuild_agents()` reconstructed agents **without** their plugin MCP
tools, so a model switch silently stripped every MCP-backed capability
(`/archimate-viewer`, etc.) — a regression of working state on a common
action, with no error or log.

**Fix (implemented).** Per-agent MCP discovery is one module-level
`async _discover_agent_mcp_tools()` consumed by **both** construction
sites so they cannot drift:
- the `lifespan` startup path, and
- `set_llm_settings`, which `await`s `_discover_agent_mcp_tools()` and
  passes the bundles into a still-sync
  `_rebuild_agents(mcp_tools_by_agent=...)`.

`_rebuild_agents` stays synchronous (no caller-context constraint); the
`await` lives where the async context already exists. Swap
frequency/shape and the pixel posture are unchanged — the fix only makes
the post-swap agents *correct*, never stripped.

## 5. Reload triggers & ordering

- `load()` — one-time load; idempotent; fires `_fire_reload_callbacks()`
  at the end of a real load.
- `reload()` — explicit re-read after on-disk registry mutations (the
  skills-UI toggle path uses this); also fires callbacks.
- **Kernel-policy ordering (Amendment 4).** Within `load()`, a
  `role: kernel` skill marked `enabled: false` in registry YAML is
  force-enabled (with a warning) **before** `conflicts_with`/precedence
  resolution and before reload callbacks fire — so the Persona addendum
  rebuilt by the `key="persona"` callback always sees the corrected,
  policy-enforced skill set.

## 6. What is intentionally NOT live, and why (one place)

Only the **agent MCP tool set on a plugin toggle** (§3) is
restart-required. Persona (§2) and the model-switch MCP path (§4) are
live. The asymmetry is deliberate and bounded: the live paths are
either cheap and safe (Persona prompt rebuild) or fix a real
regression (model switch); the non-live path's only failure mode is a
rare missed pickup that a restart resolves, versus a complex mechanism
whose failure is silent and crosses into a separate extension.

## 7. Verification

- Keyed `on_reload` register-or-replace + unkeyed back-compat: covered
  in `tests/test_multi_registry.py` (register twice under one key →
  exactly one callback fires).
- Model-switch MCP re-derivation: regression tests assert each routed
  bundle reaches its agent and the shared discovery helper keys every
  agent type.
- Full suite green; the authoritative count + per-phase evidence map is
  in [plugin-migration-retrospective.md](plugin-migration-retrospective.md)
  §C.1 (kept there so a number does not rot in two places).

---

> Related cleanup, not done here: the agent-side-reload-gap NOTE in
> `chat_ui.py` still cites "RFC §9" — that RFC
> (`plugin-architecture-migration.md`) was deleted. The *behavior* it
> describes is correct and canonical; only the citation is stale. Flag
> for a follow-up code-comment touch-up (out of scope for this doc
> rewrite).
