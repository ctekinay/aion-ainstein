"""Pre-Persona slash-command parser.

AInstein had no slash-command surface before the plugin migration —
every chat message was sent to the Persona classifier for intent
detection. Plugins now declare user-invocable skills (the
``inject_mode: on_demand`` set per D3 in the migration RFC), and a
``/<skill-name> [args]`` message bypasses the classifier and routes
directly to the agent for that skill.

The parser is intentionally minimal:

* One regex (``^/([a-z][a-z0-9_-]*)(?:\\s+(.*?))?\\s*$``) — slash, then a
  Python-identifier-like skill name, then optional whitespace-separated
  args.
* Validates the parsed name against
  ``MultiPluginRegistry.invocable_skills()`` — anything not in that set
  returns ``None`` so the caller forwards to the Persona unchanged.
* No magic: the parser doesn't try to be clever about quoting, escaping,
  or shell-style argument parsing. ``cmd.args`` is the verbatim string
  that followed the command name, ready to be handed to the agent
  as-is.

Pre-Persona placement (inside ``chat_ui.event_generator``, before
``_persona.process(...)``) is what makes ``/foo bar`` cheap — no LLM
classification call on a path the user has already disambiguated.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aion.skills.multi_registry import MultiPluginRegistry

logger = logging.getLogger(__name__)


_COMMAND_RE = re.compile(r"^/([a-z][a-z0-9_-]*)(?:\s+(.*?))?\s*$")


@dataclass
class SlashCommand:
    """Parsed slash-command invocation."""

    skill_name: str
    args: str
    raw_message: str


class SlashRouter:
    """Stateless parser bound to a ``MultiPluginRegistry`` for validation."""

    def __init__(self, multi_registry: "MultiPluginRegistry"):
        self._multi = multi_registry

    def parse(self, message: str) -> SlashCommand | None:
        """Parse a message and return a ``SlashCommand`` iff it names an
        invocable skill.

        Returns ``None`` (so the caller continues with the Persona path) when:

        * The message doesn't match the slash-command regex (most chat input).
        * The parsed name doesn't correspond to any registered skill.
        * The named skill exists but isn't user-invocable (per D3, a skill
          is invocable iff ``inject_mode == "on_demand"`` — this excludes
          always-loaded framework skills like identity, RAG quality
          assurance, document ontology, response formatter, persona
          orchestrator).
        """
        if not isinstance(message, str):
            return None

        match = _COMMAND_RE.match(message)
        if not match:
            return None

        name = match.group(1)
        args = match.group(2) or ""

        # Validate against the on-demand set.
        invocable_names = {e.name for e in self._multi.invocable_skills()}
        if name not in invocable_names:
            logger.debug(
                "Slash command /%s: name not in invocable_skills() — forwarding to Persona",
                name,
            )
            return None

        return SlashCommand(skill_name=name, args=args, raw_message=message)
