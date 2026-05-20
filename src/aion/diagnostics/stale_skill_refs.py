"""Startup warning for string literals in ``src/aion/`` that look like
skill names but don't resolve to any currently-loaded skill.

Catches the ISS-002 class of bug — a hardcoded ``skill_entry.name ==
"<name>"`` gate that silently goes False when the skill is renamed — at
the first server boot after the rename, not at user-query time.

Warn-only. Never raises. Never blocks startup. Promotion to fail-fast
is later-phase work (Phase 1b), once the exclusion set is mature; for
now, warn-only is the contract.

Exclusion-set rule (hard): exclusions are ONLY for strings that LOOK
like skill names but aren't (tags, ExecutionModel values, filename
patterns, agent identifiers). Never add a real skill name to the
exclusion list — doing so would silently mask future stale-references
to that very skill.
"""
from __future__ import annotations

import logging
import pathlib
import re

logger = logging.getLogger(__name__)


# Behaviour-gating skill-name prefixes. These are the prefixes whose
# kebab-case literals in ``src/`` have historically been used to gate
# code paths (the ISS-002 pattern). Deliberately NOT included:
# ``rag-`` and ``persona-`` — the codebase uses those prefixes for
# non-skill config keys (e.g. ``rag-provider``, ``persona-model``),
# which would produce too many false positives.
_GATING_PREFIXES = (
    "archimate-",
    "principle-",
    "repo-",
    "skosmos-",
    "vocabulary-",
)

# Verified non-skill literals. Each entry must be audited against
# ``registry.list_skills()`` before being added — see module docstring.
_EXCLUSIONS = {
    # ExecutionModel value (routing.py) AND a Persona-emitted skill tag —
    # not a skill name. Skill is ``repo-to-archimate``.
    "repo-analysis",
    # Persona-emitted skill tag for the principle quality-assessor flow —
    # the actual skill is ``principle-quality-assessor``.
    "principle-quality",
    # Filename-pattern indicators used by markdown_loader to detect
    # ADR/PCP template files for ingestion exclusion — not skill names.
    "principle-template",
    "principle-decision-template",
    # Value of a ``"trigger"`` metadata field in repo_analysis.py's
    # architecture-notes envelope — identifies the calling agent, not a skill.
    "repo-analysis-agent",
}

# Match kebab-case identifiers inside string literals. Anchored on the
# quote character so we don't match comments or bare prose. The leading
# class is restricted to a-z so we don't match version strings like
# ``"2.0-alpha"``.
_LITERAL_RE = re.compile(r"""["']([a-z][a-z0-9]+-[a-z0-9-]+)["']""")


def warn_on_stale_skill_refs(
    loaded_skill_names: set[str],
    src_root: str | pathlib.Path = "src/aion",
) -> dict[str, set[str]]:
    """Scan ``src_root`` for skill-name-shaped literals not in the loaded set.

    Args:
        loaded_skill_names: result of ``{e.name for e in registry.list_skills()}``.
        src_root: path to scan (default ``"src/aion"``).

    Returns:
        Mapping of stale candidate name → set of source files where it
        appears. Returned to support testing; in production the side
        effect (one WARNING per candidate) is what callers rely on.

    Side effects:
        Logs one ``WARNING`` per stale candidate. Never raises.
    """
    findings: dict[str, set[str]] = {}
    root = pathlib.Path(src_root)
    if not root.exists():
        # No-op when the path doesn't exist (e.g. tests running from an
        # unexpected cwd). The diagnostic is non-essential, never fatal.
        return findings

    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Unreadable files are not the validator's concern.
            continue
        for match in _LITERAL_RE.finditer(text):
            name = match.group(1)
            if not name.startswith(_GATING_PREFIXES):
                continue
            if name in _EXCLUSIONS or name in loaded_skill_names:
                continue
            findings.setdefault(name, set()).add(str(path))

    for name, files in sorted(findings.items()):
        logger.warning(
            "stale-skill-ref: %r resembles a skill name but is not a "
            "loaded skill (referenced in: %s)",
            name,
            ", ".join(sorted(files)),
        )

    return findings
