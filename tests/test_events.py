"""Tests for the typed Event dataclass and serialisation boundary.

Phase 1a.1: this is the substrate the rest of Phase 1a builds on. The
dataclass is pure additive — no production-code migration happens here,
so the full suite count must be unchanged before this file lands and
+N after, where N is the number of tests added below.
"""
from __future__ import annotations

import json
import logging

import pytest

from aion.events import Event, event_log_level


# ── Construction across every variant of the discriminated union ─────────────
# A representative kwargs payload per event type. Drives both construction
# coverage and the to_sse / from_legacy_dict tests below.

_VARIANT_FIXTURES: list[tuple[str, dict]] = [
    # Pre-existing variant + the 1a.3-preemptive instrumentation field —
    # covers the 47 dict-form emit sites' typical "type + content + elapsed_ms".
    ("status", {"agent": "rag", "content": "searching ADRs", "elapsed_ms": 1234}),
    ("decision", {"agent": "rag", "tool": "search_principles", "content": "search PCPs"}),
    ("complete", {
        "agent": "rag", "response": "12 ADRs found",
        "sources": [{"id": 1}, {"id": 2}],
        "timing": {"total_ms": 500}, "path": "tree",
    }),
    ("error", {"agent": "repo_analysis", "content": "git clone failed: not found"}),
    ("text", {"content": "Hello "}),
    ("init", {"content": "stream-init"}),
    # 1a.4-preemptive: heartbeat carries elapsed_sec (instrumentation).
    ("heartbeat", {"elapsed_sec": 9}),
    # 1a.4-preemptive: dual-provider comparison shapes (provider + sources).
    ("assistant", {
        "content": "Sure, let me look that up.",
        "provider": "ollama", "timing": {"total_ms": 100}, "sources": [{"id": 1}],
    }),
    ("thinking_aloud", {"agent": "persona", "content": "reasoning about intent"}),
    # 1a.4-preemptive: persona_intent's full shape — rewritten_query is
    # load-bearing, skill_tags/doc_refs/github_refs/latency_ms are
    # instrumentation, all live on this event type.
    ("persona_intent", {
        "intent": "retrieval",
        "rewritten_query": "What does ADR.29 decide?",
        "skill_tags": ["principle-quality"],
        "doc_refs": ["ADR.29"],
        "github_refs": [],
        "latency_ms": 850,
    }),
    # 1a.4-preemptive: artifact gains content_type + summary (frontend
    # reads both to render the artifact card).
    ("artifact", {
        "artifact_id": "abc-123", "yaml_companion_id": "abc-123-yaml",
        "filename": "model.xml", "content_type": "archimate/xml",
        "summary": "OAuth2/OIDC ArchiMate model",
    }),
    # 1a.4-preemptive: init carries the conversation + request correlation IDs.
    ("init", {
        "content": "stream-init",
        "conversation_id": "conv-42", "request_id": "req-7",
    }),
    # 1a.4-preemptive: dual-provider comparison complete carries
    # ollama_sources + openai_sources side-by-side.
    ("complete", {
        "ollama_sources": [{"id": 1}, {"id": 2}],
        "openai_sources": [{"id": 3}],
    }),
]


class TestEventConstruction:
    """Every variant of the 11-type union must construct cleanly with its
    expected fields. Catches a typo'd field name or a missing default.
    """

    @pytest.mark.parametrize("event_type,kwargs", _VARIANT_FIXTURES)
    def test_constructs_with_typical_fields(self, event_type, kwargs):
        e = Event(type=event_type, **kwargs)
        assert e.type == event_type
        for k, v in kwargs.items():
            assert getattr(e, k) == v, f"field {k!r} not set correctly"

    def test_only_type_is_required(self):
        """Every other field has a None default — minimal construction works."""
        e = Event(type="heartbeat")
        assert e.type == "heartbeat"
        assert e.agent is None
        assert e.content is None
        assert e.response is None


# ── to_sse: the FastAPI streaming-boundary serialiser ────────────────────────

class TestToSSE:
    def test_emits_data_prefix_and_double_newline(self):
        """SSE wire-format: ``data: <json>\\n\\n``. Matches the pre-1a
        emit shape so the browser-side consumer never notices the swap.
        """
        e = Event(type="status", agent="rag", content="hi")
        line = e.to_sse()
        assert line.startswith("data: ")
        assert line.endswith("\n\n")

    def test_payload_is_valid_json(self):
        e = Event(type="complete", agent="rag", response="r", path="tree")
        line = e.to_sse()
        payload = json.loads(line[len("data: ") :].rstrip("\n"))
        assert payload["type"] == "complete"
        assert payload["agent"] == "rag"
        assert payload["response"] == "r"
        assert payload["path"] == "tree"

    def test_none_fields_omitted_from_payload(self):
        """None fields must NOT appear in the serialised payload — keeps
        the wire-format compact and matches the pre-1a behaviour of dicts
        only carrying fields the emitter set.
        """
        e = Event(type="status", agent="rag", content="hi")
        payload = json.loads(e.to_sse()[len("data: ") :].rstrip("\n"))
        # Only the three populated fields appear.
        assert set(payload.keys()) == {"type", "agent", "content"}
        # Sanity: none of the specialised fields leak through as None.
        assert "response" not in payload
        assert "tool" not in payload
        assert "artifact_id" not in payload

    @pytest.mark.parametrize("event_type,kwargs", _VARIANT_FIXTURES)
    def test_roundtrips_for_every_variant(self, event_type, kwargs):
        """Every variant must round-trip through to_sse → json.loads →
        from_legacy_dict back to a structurally-equal Event.
        """
        original = Event(type=event_type, **kwargs)
        payload = json.loads(original.to_sse()[len("data: ") :].rstrip("\n"))
        roundtrip = Event.from_legacy_dict(payload)
        assert roundtrip == original


# ── from_legacy_dict: the migration bridge ───────────────────────────────────

class TestFromLegacyDict:
    """Used during Phase 1a to bridge dict-emit sites that haven't migrated
    yet. Removed at the end of Phase 1a when the dict-accept shim is
    removed from ``SessionContext.emit_event``.
    """

    def test_constructs_from_minimal_dict(self):
        e = Event.from_legacy_dict({"type": "status", "content": "hi"})
        assert e.type == "status"
        assert e.content == "hi"

    def test_ignores_unknown_keys(self):
        """A partial migration may carry an unknown field (e.g. a payload
        tag from an upstream extractor). The shim must not crash on it —
        the field is silently dropped, and the surrounding logging
        (Phase 1a.2.b) surfaces the unknown-shape call site so it can be
        cleaned up.
        """
        e = Event.from_legacy_dict({
            "type": "status",
            "agent": "rag",
            "totally_unknown_field": "ignored",
            "another_unknown": 42,
        })
        assert e.type == "status"
        assert e.agent == "rag"
        # No AttributeError, no exception.

    @pytest.mark.parametrize("event_type,kwargs", _VARIANT_FIXTURES)
    def test_constructs_for_every_variant(self, event_type, kwargs):
        d = {"type": event_type, **kwargs}
        e = Event.from_legacy_dict(d)
        assert e.type == event_type
        for k, v in kwargs.items():
            assert getattr(e, k) == v


# ── event_log_level: the tee-to-logs severity mapping ────────────────────────

class TestInstrumentationFields:
    """Instrumentation fields preserved during Phase 1a migration.

    These fields are set by emit sites but have no known in-process
    consumer (verified during the 1a.3 and 1a.4 preemptive audits).
    They remain in the dataclass + serialised payload for SSE
    wire-format fidelity; Phase 1b will drop any field a dogfood-week
    confirms is unused externally too.
    """

    def test_elapsed_ms_round_trips(self):
        """Set on 47 emit sites — must round-trip through to_sse and
        from_legacy_dict identically.
        """
        e = Event(type="decision", agent="rag", content="search", elapsed_ms=4321)
        payload = json.loads(e.to_sse()[len("data: ") :].rstrip("\n"))
        assert payload["elapsed_ms"] == 4321
        roundtrip = Event.from_legacy_dict(payload)
        assert roundtrip.elapsed_ms == 4321

    def test_elapsed_ms_defaults_none(self):
        """Optional — omitting it does not break construction."""
        e = Event(type="status", content="no instrumentation")
        assert e.elapsed_ms is None
        # And it's omitted from the SSE payload when None.
        payload = json.loads(e.to_sse()[len("data: ") :].rstrip("\n"))
        assert "elapsed_ms" not in payload

    @pytest.mark.parametrize("field,value", [
        # 1a.4-preemptive instrumentation fields. No known in-process
        # consumer; round-trip pins emit-site fidelity.
        ("elapsed_sec", 9),
        ("skill_tags", ["principle-quality", "archimate"]),
        ("doc_refs", ["ADR.29", "PCP.10"]),
        ("github_refs", ["alice/myrepo"]),
        ("latency_ms", 850),
    ])
    def test_1a4_instrumentation_field_round_trips(self, field, value):
        e = Event(type="status", **{field: value})
        payload = json.loads(e.to_sse()[len("data: ") :].rstrip("\n"))
        assert payload[field] == value
        roundtrip = Event.from_legacy_dict(payload)
        assert getattr(roundtrip, field) == value

    @pytest.mark.parametrize("field,value", [
        # 1a.4-preemptive instrumentation defaults. None ⇒ omitted from SSE.
        ("elapsed_sec", 9),
        ("skill_tags", ["x"]),
        ("doc_refs", ["x"]),
        ("github_refs", ["x"]),
        ("latency_ms", 100),
    ])
    def test_1a4_instrumentation_field_omitted_when_unset(self, field, value):
        e = Event(type="status", content="no instrumentation")
        # default must be None
        assert getattr(e, field) is None
        # and absent from the serialised payload
        payload = json.loads(e.to_sse()[len("data: ") :].rstrip("\n"))
        assert field not in payload


class TestLoadBearingFields:
    """1a.4-preemptive load-bearing fields — these have frontend consumers
    (verified at audit time against ``src/aion/static/``). They MUST
    round-trip cleanly through the SSE boundary or the UI breaks.
    """

    @pytest.mark.parametrize("field,value", [
        # artifact event
        ("content_type", "archimate/xml"),
        ("summary", "OAuth2/OIDC ArchiMate model"),
        # init / complete events
        ("conversation_id", "conv-42"),
        ("request_id", "req-7"),
        # dual-provider comparison
        ("provider", "ollama"),
        ("ollama_sources", [{"id": 1}, {"id": 2}]),
        ("openai_sources", [{"id": 3}]),
        # persona_intent
        ("rewritten_query", "What does ADR.29 decide?"),
    ])
    def test_load_bearing_field_round_trips(self, field, value):
        e = Event(type="status", **{field: value})
        payload = json.loads(e.to_sse()[len("data: ") :].rstrip("\n"))
        assert payload[field] == value
        # And the legacy-dict bridge preserves it.
        roundtrip = Event.from_legacy_dict(payload)
        assert getattr(roundtrip, field) == value


class TestEventLogLevel:
    """Default severity per type. Used by ``SessionContext.emit_event`` to
    tee events to structlog. Callers override via ``log_level=`` (e.g.
    ``check_iteration_limit`` emits a status event at WARNING — see 1a.2.b).
    """

    @pytest.mark.parametrize("event_type,expected_level", [
        # INFO: routine progress / decisions / persona / artifacts.
        ("status", logging.INFO),
        ("decision", logging.INFO),
        ("persona_intent", logging.INFO),
        ("artifact", logging.INFO),
        # ERROR: terminal failures.
        ("error", logging.ERROR),
        # DEBUG: high-volume / internal / token-stream.
        ("complete", logging.DEBUG),
        ("text", logging.DEBUG),
        ("init", logging.DEBUG),
        ("heartbeat", logging.DEBUG),
        ("assistant", logging.DEBUG),
        ("thinking_aloud", logging.DEBUG),
    ])
    def test_default_level_per_type(self, event_type, expected_level):
        e = Event(type=event_type)
        assert event_log_level(e) == expected_level

    def test_unknown_type_defaults_to_info_not_raise(self):
        """Defensive against the dict-accept shim surfacing a type not yet
        in the declared union. The validator at startup is the place that
        catches the unknown literal — event_log_level must not crash.
        """
        # Construct via the lenient shim so we don't fight the type system.
        e = Event.from_legacy_dict({"type": "future_unknown_type_name"})
        # Type is a Literal but Python doesn't enforce at runtime — value sits.
        assert event_log_level(e) == logging.INFO
