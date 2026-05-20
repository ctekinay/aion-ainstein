---
name: archimate-tools
description: Fixture ArchiMate tooling. Shadows enterpower-architecture's same-named skill via conflicts_with.
---

# archimate-tools (fixture)

This skill exists only in the e2e fixture. It deliberately shares its
name with `enterpower-architecture/archimate-tools` to exercise the
duplicate-skill collision handling: name conflict at load resolves via
`conflicts_with` auto-disable, and the user-initiated re-enable flow
exercises the preflight + HTTP 409 surface.

When loaded together with `enterpower-architecture`, this skill
auto-disables (declaring side, per the locked semantics). Attempts to
re-enable it through the plugin-scoped API raise `DuplicateSkillError`.
