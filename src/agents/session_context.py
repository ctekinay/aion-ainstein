"""Session context manager for multi-turn conversation state.

Tracks document references, intents, and queries across conversation turns.
Provides anaphora detection for follow-up resolution (e.g., "show it" →
inject last doc refs).

Lives in chat_ui.py as per-conversation instances, NOT in ArchitectureAgent
(which is stateless by design with early returns on every routing path).
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """Immutable snapshot of conversation state after a turn."""

    last_doc_refs: list[dict] = field(default_factory=list)
    last_intent: str = "none"
    last_query: str = ""
    turn_count: int = 0


# Word-boundary-safe anaphora markers.
# Order matters: longer phrases first to avoid partial matches.
_ANAPHORA_MARKERS = [
    "the same", "the one", "the document", "the adr", "the principle",
    "both",
    "them", "those", "these", "that", "this", "it",
]

# Pre-compiled regex for word-boundary anaphora matching.
# Each marker is wrapped in \b...\b to prevent "item" matching "it".
_ANAPHORA_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(m) for m in _ANAPHORA_MARKERS) + r")\b",
    re.IGNORECASE,
)


class SessionContext:
    """Per-conversation session state for follow-up resolution.

    Usage in chat_ui.py:
        session = _conversation_sessions.setdefault(conv_id, SessionContext())
        resolved = session.resolve_refs(query, current_refs)
        response = await agent.query(question, last_doc_refs=resolved, ...)
        session.update(query, response.route_trace.intent, response.doc_refs)
    """

    def __init__(self) -> None:
        self.state = SessionState()

    def update(
        self,
        query: str,
        intent: str,
        doc_refs: Optional[list[dict]],
    ) -> None:
        """Update session state after a query completes.

        Called AFTER query() returns, in chat_ui.py.
        If doc_refs is empty/None, previous refs are preserved.
        """
        self.state = SessionState(
            last_doc_refs=doc_refs if doc_refs else self.state.last_doc_refs,
            last_intent=intent,
            last_query=query,
            turn_count=self.state.turn_count + 1,
        )

    def resolve_refs(
        self,
        query: str,
        current_refs: list[dict],
    ) -> list[dict]:
        """Resolve document references for a query.

        If the query has explicit refs, return them as-is.
        If the query has anaphora and no refs, inject from previous turn.
        Otherwise, return the (empty) current_refs.
        """
        if current_refs:
            return current_refs
        if self._has_anaphora(query) and self.state.last_doc_refs:
            logger.info(
                "SessionContext: anaphora detected in '%s', injecting %d ref(s)",
                query, len(self.state.last_doc_refs),
            )
            return list(self.state.last_doc_refs)
        return current_refs

    def _has_anaphora(self, query: str) -> bool:
        """Detect pronouns/demonstratives referring to previous context.

        Uses word-boundary regex to avoid false positives like
        "item" matching "it" or "thesis" matching "the".
        """
        return bool(_ANAPHORA_RE.search(query))
