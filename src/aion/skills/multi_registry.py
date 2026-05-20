"""Multi-plugin skill registry — aggregates N per-plugin SkillRegistry instances.

Replaces the single-tree `SkillRegistry` singleton. Each plugin discovered by
`PluginLoader.discover()` gets its own `SkillRegistry` constructed from the
plugin's paths; the `MultiPluginRegistry` orchestrates lookups, write-routing,
duplicate detection, and `conflicts_with` auto-disable across them.

## Atomic-swap on reload

Consumers that cache derived state from the registry (e.g. the per-agent
MCP tool bundle, Persona's classification prompt) register via
``on_reload(callback)``. When the registry reloads, every callback fires
in registration order.

The standard pattern for consumers — particularly the agent factory — is:

    # ✅ correct: build the new dict fully, then swap by single assignment
    new_agents = {k: build_agent(k, ...) for k in AGENT_TYPES}
    _agents = new_agents

    # ❌ wrong: in-place mutation briefly exposes a half-built dict to readers
    for k in AGENT_TYPES:
        _agents[k] = build_agent(k, ...)

The single-statement reassignment is GIL-protected; in-flight queries that
captured the old `_agents` reference at request start complete against that
snapshot. Toggles take effect on the next request.

## Conflict resolution

Each skill entry can declare ``conflicts_with: ["<plugin>/<skill>"]`` —
skill-scoped pairs, not plugin-scoped. After all plugins are parsed:

1. For each enabled entry with `conflicts_with`, check whether each declared
   `(plugin, skill)` peer is loaded AND enabled in its own plugin's registry.
   If so, this entry is auto-disabled in-memory (the YAML on disk is
   unchanged). Tie-breaker: auto-disable applies only to the declaring side.
2. After auto-disable resolution, build the `skill_name → plugin_name` owner
   map. Any *remaining* duplicate name across plugins raises
   ``DuplicateSkillError`` — both plugin names appear in the error message.

**Reciprocal-declaration refinement.** When two entries declare ``conflicts_with``
against each other, the algorithm processes plugins sequentially in load order.
The first plugin processed self-disables (its target is enabled), and the second
plugin's declaration then finds its target already disabled and stays enabled.
This is a deliberate refinement of the plan's "declaring side always loses"
phrasing: load-order-wins prevents the pathological double-disable that would
make the skill unavailable to anyone. Practically, the in-tree bundled
plugins (e.g. ``enterpower-architecture``, the authoritative architecture
provider) load last (env-var paths → ``~/.ainstein/plugins/*`` →
in-tree), so an external plugin's reciprocal declaration self-disables
first and the bundled provider survives — which matches the plan's intent
for the common case.

The UI/API enable endpoint runs a separate preflight dup-check before
persisting a user's "re-enable a shadowed skill" action; bypass that
preflight and the next server start surfaces ``DuplicateSkillError``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from aion.skills.loader import Skill, SkillLoader
from aion.skills.plugin import Plugin
from aion.skills.plugin_loader import PluginLoader
from aion.skills.registry import SkillGroupEntry, SkillRegistry, SkillRegistryEntry

if TYPE_CHECKING:
    from aion.routing import ExecutionModel

logger = logging.getLogger(__name__)


class DuplicateSkillError(RuntimeError):
    """Raised when more than one enabled plugin declares the same skill name.

    The error message includes every plugin claiming the skill so the operator
    can resolve via ``conflicts_with`` or by disabling one plugin's copy.
    """


class MultiPluginRegistry:
    """Aggregate registry over N plugins with explicit ownership tracking."""

    def __init__(self) -> None:
        # Insertion order matters: it's the resolution/iteration order for
        # reads. ``add_plugin`` preserves it (Python dict ordering is stable).
        self._registries: dict[str, SkillRegistry] = {}
        self._plugin_objects: dict[str, Plugin | None] = {}
        self._skill_owner: dict[str, str] = {}
        # Keyed by stable component role (e.g. "persona"), NOT instance id —
        # re-registration under the same key replaces, so a re-instantiated
        # component's hook supersedes its prior one with zero accumulation.
        # Dict preserves insertion order → fire order matches registration.
        self._reload_callbacks: dict[str, Callable[[], None]] = {}
        self._auto_key_seq = 0
        self._loaded = False

    # -- plugin registration --------------------------------------------------

    def add_plugin_from_object(self, plugin: Plugin) -> None:
        """Register a plugin discovered via ``PluginLoader.discover()``."""
        if plugin.name in self._registries:
            raise ValueError(
                f"Plugin name collision: {plugin.name!r} is already registered. "
                f"Two discovered plugins share the same manifest 'name' field."
            )
        self._registries[plugin.name] = SkillRegistry(
            skills_dir=plugin.skills_dir,
            registry_path=plugin.registry_path,
            thresholds_path=plugin.thresholds_path,
            shared_refs_dir=plugin.shared_refs_dir,
        )
        self._plugin_objects[plugin.name] = plugin

    # -- loading --------------------------------------------------------------

    def load(self) -> None:
        """Load all per-plugin registries, resolve ``conflicts_with``, build the owner map.

        Idempotent: if already loaded, returns immediately without firing
        callbacks. Use ``reload()`` for an explicit re-read after disk
        mutations.

        Fires every ``on_reload`` callback at the end of a real load. Raises
        ``DuplicateSkillError`` if two enabled plugins declare the same skill
        name after ``conflicts_with`` resolution.
        """
        if self._loaded:
            return

        for reg in self._registries.values():
            reg.load_registry()

        # Kernel policy (load-time enforcement, Amendment 4): a role:kernel
        # plugin's skills are implicitly always-loaded. If its registry
        # YAML marks a kernel skill disabled (config drift / mistaken
        # edit), force it enabled here with a loud warning. The mutation
        # paths already REJECT a runtime disable of a kernel skill; at
        # load there is no user action to reject, so we self-heal rather
        # than silently honor the disable — silently honoring it would
        # defeat non-removability exactly where it is least visible.
        # Domain plugins are untouched (a disabled domain skill stays
        # disabled — the paired positive control proves this is kernel
        # policy firing, not force-enable-everything).
        for plugin_name, reg in self._registries.items():
            if not self._is_kernel_plugin(plugin_name):
                continue
            for entry in reg.list_skills():
                if not entry.enabled:
                    entry.enabled = True
                    logger.warning(
                        "Kernel policy: %s/%s was disabled in registry YAML; "
                        "forcing enabled (kernel is non-removable / "
                        "implicitly always-loaded).",
                        plugin_name, entry.name,
                    )

        # Phase-2 capability-scoped provider-precedence resolver (runs
        # BEFORE the legacy conflicts_with loop). Inert until a skill
        # declares a non-empty `capability` — when none do (today), this
        # is a no-op and the legacy path below runs byte-identically
        # (Phase-0 goldens hold). Capability-scoped, NOT plugin-scoped;
        # deterministic tie-break, NOT discovery order; kernel-role
        # plugins excluded from domain-provider precedence.
        self._resolve_capability_precedence()

        # Conflict resolution: declaring side auto-disables when its target is enabled.
        for plugin_name, reg in self._registries.items():
            for entry in reg.list_skills():
                if not entry.enabled:
                    continue
                for cw in entry.conflicts_with:
                    target = self._parse_conflict_target(cw)
                    if target is None:
                        logger.warning(
                            "Skill %s/%s has malformed conflicts_with entry %r — skipping",
                            plugin_name, entry.name, cw,
                        )
                        continue
                    peer_plugin, peer_skill = target
                    peer_reg = self._registries.get(peer_plugin)
                    if peer_reg is None:
                        continue
                    peer_entry = peer_reg.get_skill_entry(peer_skill)
                    if peer_entry is not None and peer_entry.enabled:
                        if self._is_kernel_plugin(plugin_name):
                            # Kernel policy: kernel-role plugins are
                            # non-shadowable — never auto-disabled by
                            # conflicts_with (defensive; kernel skills are
                            # framework and should not declare it anyway).
                            logger.info(
                                "Kernel %s/%s exempt from conflicts_with auto-disable",
                                plugin_name, entry.name,
                            )
                            continue
                        entry.enabled = False
                        logger.info(
                            "Auto-disabled %s/%s (declares conflicts_with %s, which is loaded and enabled)",
                            plugin_name, entry.name, cw,
                        )
                        break  # one match is enough

        # Build owner map; raise on any duplicate name still enabled.
        self._skill_owner = {}
        for plugin_name, reg in self._registries.items():
            for entry in reg.list_skills():
                if not entry.enabled:
                    continue
                prior_owner = self._skill_owner.get(entry.name)
                if prior_owner is not None:
                    raise DuplicateSkillError(
                        f"Duplicate enabled skill '{entry.name}' declared by plugins: "
                        f"{prior_owner!r} and {plugin_name!r}. Resolve via "
                        f"'conflicts_with: [<plugin>/<skill>]' on one side, or by "
                        f"disabling one plugin's copy."
                    )
                self._skill_owner[entry.name] = plugin_name

        self._loaded = True
        self._fire_reload_callbacks()

    def _resolve_capability_precedence(self) -> None:
        """Capability-scoped provider-precedence resolution (Phase 2, A1).

        For each declared ``capability``, among ENABLED providers across
        all loaded plugins, the winner is chosen deterministically and the
        losers are disabled in-memory (same loser semantics as the legacy
        conflicts_with auto-disable — losers stay visible/attributed under
        their owning plugin via the existing UI machinery, just disabled).

        Rules (locked, approved design):
          * capability-scoped, NOT plugin-scoped;
          * ``role: kernel`` plugins do NOT participate in domain-provider
            precedence (their skills are skipped here);
          * ``lifecycle == "removed"`` providers are excluded entirely;
          * winner key = ``(-provider_precedence, plugin_name, skill_name)``
            — explicit + deterministic, NEVER discovery/filesystem order;
          * an equal-top-precedence tie is a config smell → WARNING naming
            all tied providers (visible, not silent); winner still
            deterministic via the (plugin, skill) tiebreak;
          * selecting a ``deprecated-superseded`` winner logs INFO (drives
            the Phase-6 lifecycle).

        Inert when no entry declares a non-empty ``capability`` (today's
        state) → the legacy ``conflicts_with`` loop runs byte-identically.
        ``conflicts_with`` is the *legacy migration input* (A2): it is left
        to the loop below; this resolver owns explicit-capability skills.
        """
        # Collect enabled, non-removed, capability-declaring providers.
        # provider = (capability, plugin_name, entry)
        providers: dict[str, list[tuple[str, SkillRegistryEntry]]] = {}
        for plugin_name, reg in self._registries.items():
            plugin_obj = self._plugin_objects.get(plugin_name)
            is_kernel = plugin_obj is not None and getattr(
                plugin_obj, "role", "domain"
            ) == "kernel"
            if is_kernel:
                continue  # kernel never competes for domain-provider precedence
            for entry in reg.list_skills():
                if not entry.enabled:
                    continue
                cap = (entry.capability or "").strip()
                if not cap:
                    continue  # no explicit capability → legacy path
                if entry.lifecycle == "removed":
                    entry.enabled = False
                    continue
                providers.setdefault(cap, []).append((plugin_name, entry))

        for cap, plist in providers.items():
            if len(plist) < 2:
                continue  # single provider — nothing to resolve
            ordered = sorted(
                plist,
                key=lambda pe: (-pe[1].provider_precedence, pe[0], pe[1].name),
            )
            top_prec = ordered[0][1].provider_precedence
            tied = [pe for pe in ordered if pe[1].provider_precedence == top_prec]
            if len(tied) > 1:
                logger.warning(
                    "Provider-precedence tie for capability %r at precedence "
                    "%d among %s — resolved deterministically to %s/%s by "
                    "(plugin, skill); declare distinct provider_precedence to "
                    "remove this ambiguity.",
                    cap, top_prec,
                    [f"{p}/{e.name}" for p, e in tied],
                    ordered[0][0], ordered[0][1].name,
                )
            winner_plugin, winner_entry = ordered[0]
            if winner_entry.lifecycle == "deprecated-superseded":
                logger.info(
                    "Capability %r resolved to a deprecated-superseded "
                    "provider %s/%s — Phase-6 lifecycle should retire it.",
                    cap, winner_plugin, winner_entry.name,
                )
            for plugin_name, entry in ordered[1:]:
                entry.enabled = False
                logger.info(
                    "Provider-precedence: %s/%s disabled — capability %r won "
                    "by %s/%s (precedence %d >= %d).",
                    plugin_name, entry.name, cap,
                    winner_plugin, winner_entry.name,
                    winner_entry.provider_precedence, entry.provider_precedence,
                )

    def _is_kernel_plugin(self, plugin_name: str) -> bool:
        """True iff ``plugin_name`` declares ``role: kernel``.

        Kernel policy (host-enforced): non-removable, non-shadowable
        (never disabled by conflicts_with or provider-precedence),
        implicitly always-loaded, and rejected by every enable/disable
        mutation path. Same uniform plugin mechanism — kernel-ness is a
        declared role the host enforces, not a second code path.
        """
        p = self._plugin_objects.get(plugin_name)
        return p is not None and getattr(p, "role", "domain") == "kernel"

    @staticmethod
    def _parse_conflict_target(cw: str) -> tuple[str, str] | None:
        """Parse ``<plugin>/<skill>`` shorthand. Returns None on malformed input."""
        if not isinstance(cw, str) or "/" not in cw:
            return None
        plugin, skill = cw.split("/", 1)
        plugin = plugin.strip()
        skill = skill.strip()
        if not plugin or not skill:
            return None
        return plugin, skill

    def reload(self) -> None:
        """Re-read every plugin's registry from disk and rebuild state.

        Used after the UI mutates a registry file (set_skill_enabled /
        set_group_enabled) so in-memory state matches disk.
        """
        self._loaded = False
        self._skill_owner.clear()
        for reg in self._registries.values():
            reg.reload()
        self.load()

    # -- reload observer -----------------------------------------------------

    def on_reload(self, callback: Callable[[], None], *, key: str | None = None) -> None:
        """Register a callback to fire after each successful ``load()``.

        Used by Persona (and, if live agent rebuild is ever added, the
        agent factory) to rebuild cached state when plugins are toggled.
        Callbacks fire in registration order; exceptions are logged and
        swallowed so one bad consumer can't break the signal for others.

        ``key`` is the **stable component role** (e.g. ``"persona"``), not
        the instance. Re-registering under the same key **replaces** the
        prior callback — so a re-instantiated component's hook supersedes
        its old one instead of accumulating (the prior callback-leak bug:
        a new ``Persona()`` has a different ``id(self)``, so dedup-by-
        instance would not have fixed it). ``key=None`` generates a unique
        auto-key, preserving the unkeyed-registrant contract without
        leaking the keyed ones.

        Old-instance semantics (intended, not emergent): when a new
        component registers under an existing key and replaces the old
        callback, the old instance — possibly still serving an in-flight
        request — is de-registered, so a reload during that request will
        not rebuild the *old* instance's state. This is correct: the old
        instance is being torn down and the next query uses the new one.
        """
        if key is None:
            key = f"__auto_{self._auto_key_seq}"
            self._auto_key_seq += 1
        self._reload_callbacks[key] = callback

    def _fire_reload_callbacks(self) -> None:
        for cb in list(self._reload_callbacks.values()):
            try:
                cb()
            except Exception:
                logger.exception("on_reload callback raised — swallowing to protect peers")

    # -- ownership / introspection -------------------------------------------

    def get_owner(self, skill_name: str) -> str | None:
        """Return the plugin name that owns the (enabled) skill, or None."""
        if not self._loaded:
            self.load()
        return self._skill_owner.get(skill_name)

    def list_plugins(self) -> list[str]:
        """Plugin names in load order."""
        return list(self._registries.keys())

    def get_plugin(self, name: str) -> Plugin | None:
        """Return the Plugin object for a registered plugin, or None if unknown."""
        return self._plugin_objects.get(name)

    def get_loader_for_skill(self, skill_name: str) -> SkillLoader | None:
        """Return the SkillLoader of the plugin that defines the skill.

        Resolves to the enabled owner first; falls back to the first plugin
        (in load order) that *defines* the skill — this covers disabled
        skills the UI still inspects/edits. Returns None if no plugin
        declares the skill at all.

        Replaces the legacy ``SkillLoader()`` no-arg construction in
        persona/generation/api, which relied on the deleted
        ``DEFAULT_SKILLS_DIR``. Each plugin's loader is rooted at that
        plugin's own ``skills_dir``, so skill content resolves from the
        owning plugin's directory rather than a single hardcoded path.
        """
        if not self._loaded:
            self.load()
        owner = self._skill_owner.get(skill_name)
        if owner is not None:
            return self._registries[owner].loader
        for reg in self._registries.values():
            if reg.get_skill_entry(skill_name) is not None:
                return reg.loader
        return None

    def invocable_skills(self) -> list[SkillRegistryEntry]:
        """Skills eligible as ``/<name>`` slash commands.

        Convention (per the migration plan): a skill is invocable iff it is
        enabled AND has ``inject_mode == "on_demand"``. This excludes
        every always-loaded skill regardless of owner — the kernel set
        (ainstein-identity, persona-orchestrator, rag-quality-assurance,
        response-formatter) plus always-mode domain skills such as
        esa-document-ontology (now in esa-workflow) — without a denylist.
        """
        if not self._loaded:
            self.load()
        return [
            e for e in self.list_skills()
            if e.enabled and e.inject_mode == "on_demand"
        ]

    # -- Named contribution accessors (Phase 2, hard part A) -----------------
    #
    # The kernel *aggregates*; domain plugins *contribute*. These name the
    # four previously-implicit contribution surfaces. Each returns exactly
    # what its prior inline consumer computed — pure refactor behind
    # identical outputs (Phase-0 goldens are the gate). invocable_skills()
    # above is the slash surface; get_execution_model is the routing one.

    def classification_tags(self) -> dict[str, str]:
        """Persona classification-tag surface: ``tag -> primary description``.

        Exactly the aggregation Persona._build_skill_tags_addendum did
        inline (moved here so the kernel-consumes-plugin-tags coupling is
        an explicit, named contract — the untested intersection the plan
        flagged): enabled on_demand skills; a skill declaring ANY canonical
        tag drops ALL its tags (synonym-filter); longest description wins
        per tag. Identical output → addendum stays byte-identical.
        """
        from aion.persona import _CANONICAL_SKILL_TAGS

        tag_to_descs: dict[str, list[str]] = {}
        for entry in self.list_skills():
            if not entry.enabled or entry.inject_mode != "on_demand":
                continue
            if any(tag in _CANONICAL_SKILL_TAGS for tag in entry.tags):
                continue
            for tag in entry.tags:
                tag_to_descs.setdefault(tag, []).append(entry.description or "")
        return {
            tag: (max(descs, key=len) if descs else "")
            for tag, descs in tag_to_descs.items()
        }

    def execution_routes(self, skill_tags) -> "ExecutionModel":
        """Named agent-routing contribution accessor.

        Alias of ``get_execution_model`` (identical output) — names the
        routing surface per the contribution model without changing
        behavior. Callers may use either; both resolve cross-plugin
        first-non-tree-wins as today.
        """
        return self.get_execution_model(skill_tags)

    def mcp_contributions(self, agent_type: str) -> list[tuple[str, str]]:
        """Named MCP-tool contribution accessor: ``(plugin, server)`` pairs
        routed to ``agent_type``. Delegates to the existing
        ``mcp_servers_for_agent`` implementation (identical output) so the
        registry owns the named contract per the contribution model.
        """
        from aion.mcp.tool_bridge import mcp_servers_for_agent

        return mcp_servers_for_agent(agent_type, self)

    # -- SkillRegistry-compatible API ----------------------------------------
    #
    # The following methods preserve the API surface of the old SkillRegistry
    # so existing callers (chat_ui, routing, agents, tools) work unchanged
    # via the get_skill_registry() backward-compat alias.

    def list_skills(self) -> list[SkillRegistryEntry]:
        """All entries across all plugins (enabled and disabled)."""
        if not self._loaded:
            self.load()
        out: list[SkillRegistryEntry] = []
        for reg in self._registries.values():
            out.extend(reg.list_skills())
        return out

    def list_groups(self) -> list[SkillGroupEntry]:
        """All groups across all plugins."""
        if not self._loaded:
            self.load()
        out: list[SkillGroupEntry] = []
        for reg in self._registries.values():
            out.extend(reg.list_groups())
        return out

    def get_skill_entry(self, skill_name: str) -> SkillRegistryEntry | None:
        """Find an entry by name across plugins. Prefers the owning plugin."""
        if not self._loaded:
            self.load()
        owner = self._skill_owner.get(skill_name)
        if owner is not None:
            return self._registries[owner].get_skill_entry(skill_name)
        # Disabled or not in owner map — search all registries.
        for reg in self._registries.values():
            entry = reg.get_skill_entry(skill_name)
            if entry is not None:
                return entry
        return None

    def is_skill_active(self, skill_name: str) -> bool:
        if not self._loaded:
            self.load()
        return skill_name in self._skill_owner

    def get_active_skills(self) -> list[Skill]:
        """Loaded Skill objects across all plugins (enabled only)."""
        if not self._loaded:
            self.load()
        out: list[Skill] = []
        for reg in self._registries.values():
            out.extend(reg.get_active_skills())
        return out

    def get_all_skill_content(self) -> str:
        """Backward-compat wrapper — equivalent to get_skill_content(None)."""
        return self.get_skill_content(active_tags=None)

    def get_skill_content(self, active_tags=None) -> str:
        """Concatenated skill content across all plugins.

        Each plugin's contribution is its own ``get_skill_content`` output;
        plugins are joined by the standard ``---`` separator. Empty plugin
        outputs are skipped.
        """
        if not self._loaded:
            self.load()
        parts = [
            reg.get_skill_content(active_tags=active_tags)
            for reg in self._registries.values()
        ]
        return "\n\n---\n\n".join(p for p in parts if p)

    def get_execution_model(self, skill_tags) -> "ExecutionModel":
        """Determine routing across plugins; first non-tree match wins."""
        if not self._loaded:
            self.load()
        for reg in self._registries.values():
            result = reg.get_execution_model(skill_tags)
            if result != "tree":
                return result
        return "tree"  # type: ignore[return-value]

    def get_generation_skill(self, skill_tags) -> SkillRegistryEntry | None:
        """First generation skill across plugins whose tags overlap."""
        if not self._loaded:
            self.load()
        for reg in self._registries.values():
            result = reg.get_generation_skill(skill_tags)
            if result is not None:
                return result
        return None

    def get_skill_tuning(self, skill_name: str, getter_name: str, default):
        """Read plugin-tuning via the owning plugin's loader.

        Replaces the old ``registry.loader.<getter>("<skill>")`` pattern;
        routes through whichever plugin actually owns the named skill.
        If no plugin owns the skill (missing or disabled everywhere),
        returns the default.
        """
        if not self._loaded:
            self.load()
        owner = self._skill_owner.get(skill_name)
        if owner is None:
            # No plugin has this skill enabled. SkillRegistry.get_skill_tuning
            # already returns ``default`` for missing/disabled entries, so the
            # owner-less case has no work to do beyond returning ``default``.
            return default
        return self._registries[owner].get_skill_tuning(skill_name, getter_name, default)

    # -- write routing (enable/disable) --------------------------------------

    def set_skill_enabled(self, skill_name: str, enabled: bool) -> bool:
        """Persist the enable/disable to the owning plugin's registry file.

        When ``enabled=True``, runs a preflight dup-check: if another plugin
        already has the same skill name enabled, raise ``DuplicateSkillError``
        BEFORE writing. The UI/API layer catches this and returns HTTP 409
        with the conflict pair instead of letting the next server start fail.
        """
        if not self._loaded:
            self.load()

        owning_plugin = self._find_plugin_for_skill(skill_name)
        if owning_plugin is None:
            raise ValueError(f"Skill not found in any plugin: {skill_name}")

        if not enabled and self._is_kernel_plugin(owning_plugin):
            raise ValueError(
                f"Kernel policy: skill {skill_name!r} belongs to kernel-role "
                f"plugin {owning_plugin!r} and cannot be disabled (kernel is "
                f"non-removable / implicitly always-loaded)."
            )

        if enabled:
            # Pre-flight: would enabling this create a duplicate?
            for other_name, other_reg in self._registries.items():
                if other_name == owning_plugin:
                    continue
                other_entry = other_reg.get_skill_entry(skill_name)
                if other_entry is not None and other_entry.enabled:
                    raise DuplicateSkillError(
                        f"Enabling '{skill_name}' in plugin {owning_plugin!r} would conflict "
                        f"with already-enabled {other_name!r}/{skill_name}. Disable the "
                        f"other plugin's copy first, or add 'conflicts_with: "
                        f"[{other_name}/{skill_name}]' to the entry being enabled."
                    )

        result = self._registries[owning_plugin].set_skill_enabled(skill_name, enabled)
        self.reload()
        return result

    def set_group_enabled(self, group_name: str, enabled: bool) -> bool:
        if not self._loaded:
            self.load()
        for plugin_name, reg in self._registries.items():
            if any(g.name == group_name for g in reg.list_groups()):
                if not enabled and self._is_kernel_plugin(plugin_name):
                    raise ValueError(
                        f"Kernel policy: group {group_name!r} belongs to "
                        f"kernel-role plugin {plugin_name!r} and cannot be "
                        f"disabled (kernel is non-removable)."
                    )
                result = reg.set_group_enabled(group_name, enabled)
                self.reload()
                return result
        raise ValueError(f"Group not found in any plugin: {group_name}")

    def find_plugin_for_skill(self, skill_name: str) -> str | None:
        """Find the FIRST plugin that defines this skill (enabled or disabled).

        Distinct from ``get_owner`` (which only returns the currently-enabled
        owner). Returns the FIRST plugin in load order whose registry has an
        entry by this name — which is correct only when the name is unique
        across plugins. For attribution that must be correct under name
        collisions, use ``iter_plugin_skills`` (which yields tuples carrying
        the plugin attribution from the iteration context, not a lookup).
        Kept for the legacy single-plugin write path; new callers should
        prefer iter_plugin_skills + plugin_has_skill.
        """
        for plugin_name, reg in self._registries.items():
            if reg.get_skill_entry(skill_name) is not None:
                return plugin_name
        return None

    # Backwards-compat alias for the private name used internally.
    _find_plugin_for_skill = find_plugin_for_skill

    def iter_plugin_skills(self):
        """Yield ``(plugin_name, SkillRegistryEntry)`` pairs across all plugins.

        Attribution comes from the iteration context, NOT a name lookup —
        so collisions don't misattribute. Two plugins declaring the same
        skill name yield two tuples, each carrying its correct plugin
        name. The API layer uses this to build the UI's per-plugin
        accordion and skill counts without the ``find_plugin_for_skill``
        first-match-wins bug.

        Triggers lazy ``load()`` for symmetry with other read accessors
        (list_skills, get_owner, etc.) — without this, direct callers
        would see YAML-state entries unaffected by ``conflicts_with``
        resolution.
        """
        if not self._loaded:
            self.load()
        for plugin_name, reg in self._registries.items():
            for entry in reg.list_skills():
                yield plugin_name, entry

    def plugin_has_skill(self, plugin_name: str, skill_name: str) -> bool:
        """True iff the named plugin's registry defines an entry by this name.

        Distinct from ``find_plugin_for_skill`` — this checks within a
        SPECIFIC plugin's registry, returning False for collisions where
        the skill exists in some OTHER plugin but not this one.
        """
        reg = self._registries.get(plugin_name)
        if reg is None:
            return False
        return reg.get_skill_entry(skill_name) is not None

    def set_skill_enabled_in_plugin(
        self, plugin_name: str, skill_name: str, enabled: bool,
    ) -> bool:
        """Plugin-scoped enable/disable with explicit routing + preflight.

        Avoids the ``find_plugin_for_skill`` name-collision attribution
        bug — the caller specifies which plugin's registry to mutate.
        The duplicate-skill preflight (commit 3's locked semantics)
        still runs: enabling a shadowed skill while another plugin's
        copy is enabled raises ``DuplicateSkillError`` BEFORE persisting.
        """
        if not self._loaded:
            self.load()

        reg = self._registries.get(plugin_name)
        if reg is None:
            raise ValueError(f"Plugin not loaded: {plugin_name!r}")
        if reg.get_skill_entry(skill_name) is None:
            raise ValueError(
                f"Plugin {plugin_name!r} does not define skill {skill_name!r}"
            )

        if not enabled and self._is_kernel_plugin(plugin_name):
            raise ValueError(
                f"Kernel policy: {plugin_name!r}/{skill_name!r} is in a "
                f"kernel-role plugin and cannot be disabled (kernel is "
                f"non-removable / implicitly always-loaded)."
            )

        if enabled:
            # Preflight: would enabling create a duplicate enabled skill?
            for other_name, other_reg in self._registries.items():
                if other_name == plugin_name:
                    continue
                other_entry = other_reg.get_skill_entry(skill_name)
                if other_entry is not None and other_entry.enabled:
                    raise DuplicateSkillError(
                        f"Enabling '{skill_name}' in plugin {plugin_name!r} would conflict "
                        f"with already-enabled {other_name!r}/{skill_name}. Disable the "
                        f"other plugin's copy first, or add 'conflicts_with: "
                        f"[{other_name}/{skill_name}]' to the entry being enabled."
                    )

        result = reg.set_skill_enabled(skill_name, enabled)
        self.reload()
        return result


# ---------------------------------------------------------------------- singleton

_global_multi: MultiPluginRegistry | None = None


def _require_kernel_plugin(plugins: list[Plugin]) -> None:
    """Kernel-presence startup invariant (Amendment 4 / plan Phase-4).

    At least one discovered plugin must declare ``role: kernel``.
    AInstein's always-on host behavior (identity, persona, formatter,
    RAG quality, document ontology) lives in the kernel plugin; a
    deployment with only domain plugins can route nothing. This is a
    deployment-contract check enforced at the singleton/discovery path
    ONLY — not in ``load()``, which unit tests call directly with
    synthetic domain-only registries (those legitimately have no kernel
    and must keep loading).
    """
    if not any(getattr(p, "role", "domain") == "kernel" for p in plugins):
        names = sorted(p.name for p in plugins)
        raise RuntimeError(
            "No `role: kernel` plugin discovered. AInstein requires the "
            "`ainstein-kernel` plugin — the always-on host behavior "
            "(identity, persona, formatter, RAG quality, document "
            f"ontology). Discovered plugins: {names or '[]'}. Verify "
            "`plugins/ainstein-kernel/` exists with `\"role\": \"kernel\"` "
            "in its `.ainstein-plugin/plugin.json`, or supply a kernel "
            "plugin via the AINSTEIN_PLUGINS env var or "
            "`~/.ainstein/plugins/<name>/`."
        )


def get_multi_registry() -> MultiPluginRegistry:
    """Get the process-wide MultiPluginRegistry singleton.

    On first call, discovers plugins via env var + ``~/.ainstein/plugins/`` +
    ``<repo>/plugins/*/``. The bundled plugins live at
    ``<repo>/plugins/{ainstein-kernel, esa-workflow,
    enterpower-architecture}/`` and are normally found by the in-tree scan.
    ``ainstein-kernel`` (``role: kernel``) carries the always-on host
    behavior and is the minimum required plugin. Two startup fail-fasts:
    (1) discovery returns empty (no manifests anywhere); (2) discovery
    finds plugins but NONE declares ``role: kernel`` — a domain-only
    deployment can route nothing, so this is rejected explicitly rather
    than booting a host with no identity/persona/RAG-quality behavior.
    """
    global _global_multi
    if _global_multi is None:
        multi = MultiPluginRegistry()
        plugins = PluginLoader.discover()
        if not plugins:
            raise RuntimeError(
                "No plugins discovered. AInstein requires at least the "
                "`ainstein-kernel` plugin (role: kernel — the always-on host "
                "behavior) with `.ainstein-plugin/plugin.json`. The bundled "
                "plugins should live at `<repo>/plugins/{ainstein-kernel, "
                "esa-workflow, enterpower-architecture}/` — verify "
                "`plugins/ainstein-kernel/` has not been moved or deleted. "
                "External plugins can also be added via the AINSTEIN_PLUGINS "
                "env var or by placing them under `~/.ainstein/plugins/<name>/`."
            )
        _require_kernel_plugin(plugins)
        for plugin in plugins:
            multi.add_plugin_from_object(plugin)
        multi.load()
        _global_multi = multi
    return _global_multi


def _reset_multi_registry_for_tests() -> None:
    """Drop the cached singleton. Tests call this between scenarios."""
    global _global_multi
    _global_multi = None
