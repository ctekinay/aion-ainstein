"""Typed event model for AInstein's in-process event stream.

Events are typed objects *in-process* and serialised only at the outermost
FastAPI streaming boundary (``StreamingResponse``). This module is the
single source of truth for the event vocabulary.

The pre-Phase-1a code emitted SSE-formatted strings (``data: {json}\\n\\n``)
at every emit site and then ``json.loads``'d them back inside in-process
consumers (`chat_ui._capture_event`, the orchestrator's step loop) — a pure
round-trip that became the structural risk for any nested-agent work
(Phase 2's planner-as-tools). The typed-Event substrate retires that risk
by making the typed object the in-process medium and confining
serialisation to one site.

See:
    - ``SessionContext.emit_event`` — the boundary where events enter the
      queue and tee to structlog.
    - ``chat_ui._capture_event`` — the in-process consumer (Phase 1a.5).
    - ``Event.to_sse`` — the FastAPI streaming-boundary serialiser.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Literal

logger = logging.getLogger(__name__)


# ── The 11-variant event-type union ─────────────────────────────────────────
#
# Audited against (post-Phase-0 tree):
#   - chat_ui.py:2520 ``thinking_types`` set
#   - chat_ui.py:2524-2640 ``_capture_event`` branches
#   - every ``emit_event`` call across src/aion/agents/
#   - every ``yield f"data:"`` site in chat_ui.py + orchestrator.py
#
# NOT included (those are data-accumulator payload tags on
# ``ctx_.deps.retrieved_objects.append({"type": ...})``, not SSE events):
#   architecture_notes, dep_graph, code_structure, clone_result,
#   manifests, api_call, org.
#
# ``thinking_aloud`` has a consumer branch in ``_capture_event`` but no
# current emitter — keep in the union for compatibility; flag for a later
# cleanup phase if no emitter is added.
EventType = Literal[
    "status",
    "decision",
    "complete",
    "error",
    "text",
    "init",
    "heartbeat",
    "assistant",
    "thinking_aloud",
    "persona_intent",
    "artifact",
]


@dataclass
class Event:
    """A typed event flowing through the AInstein in-process event stream.

    Common fields (``type``, ``agent``, ``content``) apply across all
    event types. Specialised fields are populated only for specific
    event types and remain ``None`` otherwise. Fields are intentionally
    nullable so ``to_sse`` can omit them from the serialised payload,
    keeping the wire-format compact and forward-compatible.
    """

    # Common across all event types.
    type: EventType
    agent: str | None = None
    content: str | None = None

    # ``complete`` — terminal event with the final response payload.
    response: str | None = None
    sources: list[dict] | None = None
    timing: dict | None = None
    path: str | None = None  # routing path taken (analytics)

    # ``artifact`` — generated file metadata.
    artifact_id: str | None = None
    yaml_companion_id: str | None = None
    filename: str | None = None

    # ``persona_intent`` — the persona's classified intent label.
    intent: str | None = None

    # ``decision`` — tool/sub-task picked by an agent. Populated by
    # ``_rewrite_decision`` when None (see Phase 1a.6).
    tool: str | None = None

    # ── Instrumentation fields (preserved during Phase 1a migration) ───────
    # Set by 47 emit sites across the agents (see Phase 1a.3.2 preemptive
    # audit). No known in-process consumer as of Phase 1a audit
    # (verified against chat_ui._capture_event, orchestrator, pixel_agents,
    # and src/aion/static/ frontend JS — all clean). Preserved for SSE
    # wire-format fidelity in case an external observability consumer
    # (browser DevTools, log analytics) reads it. Cleanup candidate for
    # Phase 1b after dogfood-week confirms no external consumer.
    elapsed_ms: int | None = None

    # ── 1a.4 raw-yield migration: load-bearing UI fields ───────────────────
    # Fields with verified frontend consumers in src/aion/static/. These
    # are NOT preserved-for-fidelity orphans — they're real semantic
    # payload that the UI reads. Documented per event type below.

    # ``artifact`` events: filename/summary/content_type describe a
    # generated artifact (ArchiMate XML, HTML explorer, principle doc).
    # The frontend's artifact card renderer reads ``content_type`` to
    # decide which preview to show, and ``summary`` for the metadata line.
    content_type: str | None = None
    summary: str | None = None

    # ``init`` events (stream start) carry the conversation + request
    # correlation IDs. The frontend reads ``conversation_id`` from the
    # first event of every stream to set ``currentConversationId``.
    # ``request_id`` is currently only used in console.log on the
    # frontend but kept structurally for log/trace correlation.
    conversation_id: str | None = None
    request_id: str | None = None

    # Dual-provider comparison events (``assistant`` and ``error`` types).
    # The frontend uses ``provider`` to look up the per-provider response
    # container (``<provider>-response`` DOM element). ``ollama_sources``
    # and ``openai_sources`` populate the dual-provider source panels via
    # ``showProviderSources(provider, sources)``.
    provider: str | None = None
    ollama_sources: list[dict] | None = None
    openai_sources: list[dict] | None = None

    # ``persona_intent`` events carry the persona's classified intent +
    # query rewrite. The frontend displays ``rewritten_query`` to the
    # architect so they can see what the system actually searched for.
    rewritten_query: str | None = None

    # ── 1a.4 raw-yield migration: instrumentation fields ───────────────────
    # Set by the migrated yield sites but with NO known in-process consumer
    # (verified against chat_ui._capture_event, orchestrator, pixel_agents,
    # and src/aion/static/ frontend JS — all clean). Preserved for SSE
    # wire-format fidelity; cleanup candidate for Phase 1b after the
    # dogfood-week confirms no external consumer.

    # ``heartbeat`` events: elapsed seconds since stream start, sent
    # every ~3s while a long-running operation runs. Pre-1a yielded as
    # a heartbeat payload; no frontend consumer reads it.
    elapsed_sec: int | None = None

    # ``persona_intent`` instrumentation fields. The persona event
    # carries these alongside ``rewritten_query`` (above, load-bearing)
    # but neither frontend JS nor in-process consumers read them.
    skill_tags: list[str] | None = None
    doc_refs: list[str] | None = None
    github_refs: list[str] | None = None
    latency_ms: int | None = None

    def to_sse(self) -> str:
        """Serialise for the FastAPI streaming boundary.

        Single use site: the outermost ``StreamingResponse`` generator.
        Internal consumers read the typed object directly via attribute
        access — never via ``json.loads(event.to_sse())``. ``None`` fields
        are omitted from the payload (keeps the wire-format compact and
        matches the pre-1a behaviour of dict-emission, which only ever
        carried fields the emitter explicitly set).
        """
        payload = {k: v for k, v in asdict(self).items() if v is not None}
        return f"data: {json.dumps(payload)}\n\n"

    @classmethod
    def from_legacy_dict(cls, d: dict) -> Event:
        """Migration helper: build an ``Event`` from a legacy dict shape.

        Used only during Phase 1a to bridge old (dict) and new (typed)
        emit patterns at the ``SessionContext.emit_event`` shim. Removed
        in the final commit of Phase 1a once the deprecation warning
        stops firing across the codebase.

        Intentionally lenient about unknown keys (silently ignored) so
        a partial migration doesn't crash the queue. Unknown keys are
        a signal that some emitter is using a field outside the declared
        union — flag and add to the dataclass rather than working around
        it via the lenient drop.
        """
        known = {
            "type", "agent", "content",
            "response", "sources", "timing", "path",
            "artifact_id", "yaml_companion_id", "filename",
            "intent",
            "tool",
            # 1a.3-preemptive instrumentation:
            "elapsed_ms",
            # 1a.4-preemptive load-bearing (frontend-consumed):
            "content_type", "summary",
            "conversation_id", "request_id",
            "provider", "ollama_sources", "openai_sources",
            "rewritten_query",
            # 1a.4-preemptive instrumentation (preserved):
            "elapsed_sec",
            "skill_tags", "doc_refs", "github_refs", "latency_ms",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


# ── Tee-to-logs severity mapping ────────────────────────────────────────────
#
# ``SessionContext.emit_event`` tees every event to structlog at the level
# below by default. Callers may override via ``log_level=`` (e.g.
# ``check_iteration_limit`` emits ``type=status`` at WARNING — see Phase
# 1a.2.b for the override pattern).
_TYPE_TO_LEVEL: dict[str, int] = {
    "status": logging.INFO,
    "decision": logging.INFO,
    "complete": logging.DEBUG,
    "error": logging.ERROR,
    "text": logging.DEBUG,
    "init": logging.DEBUG,
    "heartbeat": logging.DEBUG,
    "assistant": logging.DEBUG,
    "thinking_aloud": logging.DEBUG,
    "persona_intent": logging.INFO,
    "artifact": logging.INFO,
}


def event_log_level(event: Event) -> int:
    """Default log level for an event.

    Used by ``SessionContext.emit_event`` to tee events to structlog.
    Unknown event types fall back to ``logging.INFO`` rather than
    raising — defensive because the dict-accept shim during migration
    might surface a type not yet in the union.
    """
    return _TYPE_TO_LEVEL.get(event.type, logging.INFO)
