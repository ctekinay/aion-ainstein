"""End-to-end tests for the /api/chat/stream pipeline.

Tests the full request flow: POST → Persona → routing → agent → SSE events.
Two tiers:
    - Mock-LLM tests (no services needed): exercise routing, event format,
      and response shaping with mocked Persona and agents.
    - Functional tests (@pytest.mark.functional): hit real Weaviate + Ollama,
      validate actual query results through the HTTP endpoint.
"""

import json
from dataclasses import field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from aion.persona import PersonaResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_persona_result(
    intent: str = "retrieval",
    rewritten_query: str = "test query",
    direct_response: str | None = None,
    skill_tags: list[str] | None = None,
    complexity: str = "simple",
) -> PersonaResult:
    return PersonaResult(
        intent=intent,
        rewritten_query=rewritten_query,
        direct_response=direct_response,
        original_message="original message",
        latency_ms=42,
        skill_tags=skill_tags or [],
        doc_refs=[],
        github_refs=[],
        complexity=complexity,
    )


def _collect_sse_events(body: bytes) -> list[dict]:
    """Parse SSE response body into a list of event dicts."""
    events = []
    for line in body.decode("utf-8").split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def _find_event(events: list[dict], event_type: str) -> dict | None:
    """Find the first event of a given type."""
    for ev in events:
        if ev.get("type") == event_type:
            return ev
    return None


def _find_events(events: list[dict], event_type: str) -> list[dict]:
    """Find all events of a given type."""
    return [ev for ev in events if ev.get("type") == event_type]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def _mock_lifespan(tmp_path):
    """Bypass the full lifespan (Weaviate, Ollama, etc.) for mock tests."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    import aion.chat_ui as chat_ui_mod
    import aion.memory.session_store as session_store_mod
    import aion.registry.element_registry as registry_mod
    original = chat_ui_mod.app.router.lifespan_context
    chat_ui_mod.app.router.lifespan_context = _noop_lifespan
    # Use a temp database so tests don't pollute the real one
    test_db = str(tmp_path / "test_chat.db")
    original_db_path = chat_ui_mod._db_path
    original_session_db = session_store_mod._DB_PATH
    original_registry_db = registry_mod._DB_PATH
    chat_ui_mod._db_path = test_db
    session_store_mod._DB_PATH = test_db
    registry_mod._DB_PATH = test_db
    # Initialize the database tables (normally done in lifespan)
    chat_ui_mod.init_db()
    # Initialize globals that the endpoint expects
    chat_ui_mod._persona = MagicMock()
    chat_ui_mod._rag_agent = MagicMock()
    chat_ui_mod._vocabulary_agent = MagicMock()
    chat_ui_mod._archimate_agent = MagicMock()
    chat_ui_mod._principle_agent = MagicMock()
    chat_ui_mod._repo_analysis_agent = MagicMock()
    chat_ui_mod._generation_pipeline = MagicMock()
    yield chat_ui_mod
    chat_ui_mod.app.router.lifespan_context = original
    chat_ui_mod._db_path = original_db_path
    session_store_mod._DB_PATH = original_session_db
    registry_mod._DB_PATH = original_registry_db


@pytest.fixture()
async def client(_mock_lifespan):
    """Async HTTP client wired to the FastAPI app."""
    from aion.chat_ui import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Mock E2E Tests ────────────────────────────────────────────────────────────

class TestDirectResponsePath:
    """Tests for intents that bypass agents and respond directly."""

    @pytest.mark.asyncio
    async def test_identity_returns_direct_response(self, client, _mock_lifespan):
        """'Who are you?' → direct response, no agent execution."""
        persona_result = _make_persona_result(
            intent="identity",
            direct_response="I'm AInstein, the Energy System Architecture AI Assistant.",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        resp = await client.post("/api/chat/stream", json={"message": "Who are you?"})
        assert resp.status_code == 200

        events = _collect_sse_events(resp.content)
        # Must have init, persona_intent, and complete
        assert _find_event(events, "init") is not None
        persona_ev = _find_event(events, "persona_intent")
        assert persona_ev is not None
        assert persona_ev["intent"] == "identity"

        complete = _find_event(events, "complete")
        assert complete is not None
        assert complete["path"] == "direct"
        assert "AInstein" in complete["response"]

    @pytest.mark.asyncio
    async def test_conversational_returns_direct_response(self, client, _mock_lifespan):
        """Generic question → conversational intent, no RAG."""
        persona_result = _make_persona_result(
            intent="conversational",
            direct_response="When removing a microservice, consider data migration...",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        resp = await client.post(
            "/api/chat/stream",
            json={"message": "What should I consider when removing a microservice?"},
        )
        events = _collect_sse_events(resp.content)
        complete = _find_event(events, "complete")
        assert complete is not None
        assert complete["path"] == "direct"
        # No status/decision events from agents
        assert _find_events(events, "decision") == []

    @pytest.mark.asyncio
    async def test_off_topic_returns_direct_response(self, client, _mock_lifespan):
        """Off-topic question → polite decline, no RAG."""
        persona_result = _make_persona_result(
            intent="off_topic",
            direct_response="I'm focused on architecture topics. How can I help with that?",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        resp = await client.post(
            "/api/chat/stream",
            json={"message": "What's the weather?"},
        )
        events = _collect_sse_events(resp.content)
        complete = _find_event(events, "complete")
        assert complete["path"] == "direct"


class TestSSEEventSequence:
    """Tests for SSE event ordering and format."""

    @pytest.mark.asyncio
    async def test_event_sequence_for_direct_response(self, client, _mock_lifespan):
        """Direct response must emit: init → status → persona_intent → complete."""
        persona_result = _make_persona_result(
            intent="identity",
            direct_response="I'm AInstein.",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        resp = await client.post("/api/chat/stream", json={"message": "Hi"})
        events = _collect_sse_events(resp.content)
        types = [ev["type"] for ev in events]

        assert types[0] == "init"
        # status (classifying) comes before persona_intent
        assert "status" in types
        assert "persona_intent" in types
        assert "complete" in types
        # Ordering: init before persona_intent before complete
        init_idx = types.index("init")
        persona_idx = types.index("persona_intent")
        complete_idx = types.index("complete")
        assert init_idx < persona_idx < complete_idx

    @pytest.mark.asyncio
    async def test_init_event_contains_conversation_id(self, client, _mock_lifespan):
        """The init event must include a conversation_id for the frontend."""
        persona_result = _make_persona_result(
            intent="identity", direct_response="Hello.",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        resp = await client.post("/api/chat/stream", json={"message": "Hi"})
        events = _collect_sse_events(resp.content)
        init = _find_event(events, "init")
        assert "conversation_id" in init
        assert "request_id" in init

    @pytest.mark.asyncio
    async def test_persona_event_contains_classification_fields(self, client, _mock_lifespan):
        """persona_intent event must have intent, skill_tags, latency_ms."""
        persona_result = _make_persona_result(
            intent="retrieval",
            skill_tags=["archimate"],
            direct_response="Here are the results.",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        resp = await client.post("/api/chat/stream", json={"message": "Test"})
        events = _collect_sse_events(resp.content)
        persona_ev = _find_event(events, "persona_intent")
        assert persona_ev["intent"] == "retrieval"
        assert persona_ev["skill_tags"] == ["archimate"]
        assert "latency_ms" in persona_ev


class TestRAGPath:
    """Tests for the RAG retrieval path with mocked agent."""

    @pytest.mark.asyncio
    async def test_retrieval_routes_to_rag_agent(self, client, _mock_lifespan):
        """Retrieval intent should reach the RAG agent."""
        persona_result = _make_persona_result(
            intent="retrieval",
            rewritten_query="List all ADRs",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        # Mock stream_rag_response to emit a controlled complete event
        async def mock_rag_stream(*args, **kwargs):
            yield f"data: {json.dumps({'type': 'status', 'agent': 'RAG Agent', 'content': 'Searching...'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'response': '18 ADRs found.', 'sources': [{'title': 'ADR.01'}], 'timing': {'total_ms': 500}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag_stream):
            resp = await client.post(
                "/api/chat/stream",
                json={"message": "What ADRs exist?"},
            )

        events = _collect_sse_events(resp.content)
        complete = _find_event(events, "complete")
        assert complete is not None
        assert "18 ADRs" in complete["response"]

    @pytest.mark.asyncio
    async def test_rag_error_emits_error_event(self, client, _mock_lifespan):
        """If the RAG agent errors, an error event must be emitted."""
        persona_result = _make_persona_result(intent="retrieval")
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        async def mock_rag_error(*args, **kwargs):
            yield f"data: {json.dumps({'type': 'error', 'content': 'Weaviate connection failed'})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag_error):
            resp = await client.post(
                "/api/chat/stream",
                json={"message": "What ADRs exist?"},
            )

        events = _collect_sse_events(resp.content)
        error = _find_event(events, "error")
        assert error is not None
        assert "Weaviate" in error["content"]


class TestGeneralKnowledgeFallbackE2E:
    """Tests for the general knowledge fallback through the pipeline."""

    @pytest.mark.asyncio
    async def test_fallback_includes_disclaimer_prefix(self, client, _mock_lifespan):
        """When RAG abstains on a generic query, the fallback response
        must include the programmatic disclaimer prefix."""
        persona_result = _make_persona_result(
            intent="retrieval",
            rewritten_query="What is the strangler fig pattern?",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        fallback_response = (
            "**Note:** This answer draws on general architecture knowledge"
            " — the knowledge base did not contain specific documents on this topic.\n\n"
            "The strangler fig pattern is a migration strategy...\n\n"
            "---\n*For organization-specific guidance, try asking about specific "
            "ADRs, principles, or policies in the knowledge base.*"
        )

        async def mock_rag_with_fallback(*args, **kwargs):
            yield f"data: {json.dumps({'type': 'complete', 'response': fallback_response, 'sources': [], 'timing': {'total_ms': 800}})}\n\n"

        with patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag_with_fallback):
            resp = await client.post(
                "/api/chat/stream",
                json={"message": "What is the strangler fig pattern?"},
            )

        events = _collect_sse_events(resp.content)
        complete = _find_event(events, "complete")
        assert complete is not None
        assert "**Note:**" in complete["response"]
        assert "general architecture knowledge" in complete["response"]
        assert "strangler fig" in complete["response"]


class TestInputValidation:
    """Tests for request validation at the endpoint level."""

    @pytest.mark.asyncio
    async def test_empty_message_accepted(self, client, _mock_lifespan):
        """Empty messages should reach the Persona (it decides what to do)."""
        persona_result = _make_persona_result(
            intent="clarification",
            direct_response="Could you please provide more details?",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        resp = await client.post("/api/chat/stream", json={"message": ""})
        # Empty string is valid — Persona handles it
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_oversized_message_rejected(self, client, _mock_lifespan):
        """Messages over 16K chars should be rejected with 422."""
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "x" * 16001},
        )
        assert resp.status_code == 422


class TestConversationPersistence:
    """Tests that verify conversation state is properly managed."""

    @pytest.mark.asyncio
    async def test_conversation_id_returned_and_reusable(self, client, _mock_lifespan):
        """First message creates a conversation_id; second message can reuse it."""
        persona_result = _make_persona_result(
            intent="identity", direct_response="I'm AInstein.",
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        # First message — no conversation_id provided
        resp1 = await client.post("/api/chat/stream", json={"message": "Hi"})
        events1 = _collect_sse_events(resp1.content)
        init1 = _find_event(events1, "init")
        conv_id = init1["conversation_id"]
        assert conv_id is not None

        # Second message — reuse the conversation_id
        resp2 = await client.post(
            "/api/chat/stream",
            json={"message": "Thanks", "conversation_id": conv_id},
        )
        events2 = _collect_sse_events(resp2.content)
        init2 = _find_event(events2, "init")
        assert init2["conversation_id"] == conv_id


# ── Multi-Agent Routing Tests ─────────────────────────────────────────────────

class TestRepoAnalysisRouting:
    """Tests that verify repo analysis intent routes through the full chain."""

    @pytest.mark.asyncio
    async def test_repo_analysis_routes_to_stream_repo_archimate(self, client, _mock_lifespan):
        """generation + repo-analysis tag → ExecutionModel.REPO_ANALYSIS → stream_repo_archimate_response."""
        persona_result = _make_persona_result(
            intent="generation",
            rewritten_query="Analyze https://github.com/Org/repo/tree/feature/foo and generate ArchiMate",
            skill_tags=["repo-analysis"],
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        call_log = []

        async def mock_repo_archimate(*args, **kwargs):
            call_log.append(("repo_archimate", args, kwargs))
            yield f"data: {json.dumps({'type': 'status', 'agent': 'Repository Analysis', 'content': 'Cloning repository...'})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'agent': 'Repository Analysis', 'content': 'Profile complete: 220 files'})}\n\n"
            yield f"data: {json.dumps({'type': 'status', 'agent': 'ArchiMate', 'content': 'Generating model...'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'response': 'Generated ArchiMate model with 12 elements.', 'sources': [], 'timing': {'total_ms': 5000}})}\n\n"

        with patch("aion.chat_ui.stream_repo_archimate_response", side_effect=mock_repo_archimate):
            resp = await client.post(
                "/api/chat/stream",
                json={"message": "Analyze https://github.com/Org/repo/tree/feature/foo and generate an ArchiMate model"},
            )

        events = _collect_sse_events(resp.content)

        # Verify routing: Persona classified → repo_archimate stream was called
        persona_ev = _find_event(events, "persona_intent")
        assert persona_ev["intent"] == "generation"
        assert "repo-analysis" in persona_ev["skill_tags"]

        # Verify the repo_archimate stream was actually invoked
        assert len(call_log) == 1

        # Verify status events from both phases flowed through
        status_events = _find_events(events, "status")
        status_contents = [s.get("content", "") for s in status_events]
        assert any("Cloning" in c for c in status_contents)

        complete = _find_event(events, "complete")
        assert complete is not None
        assert "12 elements" in complete["response"]

    @pytest.mark.asyncio
    async def test_repo_analysis_not_triggered_for_inspect_intent(self, client, _mock_lifespan):
        """inspect + repo-analysis tag must NOT route to REPO_ANALYSIS.
        This was the misrouting bug — 'Review this repo' classified as inspect
        should take the inspect path, not the repo analysis pipeline."""
        persona_result = _make_persona_result(
            intent="inspect",
            rewritten_query="Review https://github.com/Org/repo",
            skill_tags=["repo-analysis"],
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        repo_called = []
        inspect_called = []

        async def mock_repo(*args, **kwargs):
            repo_called.append(True)
            yield f"data: {json.dumps({'type': 'complete', 'response': 'repo analysis', 'sources': [], 'timing': {}})}\n\n"

        async def mock_inspect(*args, **kwargs):
            inspect_called.append(True)
            yield f"data: {json.dumps({'type': 'complete', 'response': 'inspect result', 'sources': [], 'timing': {}})}\n\n"

        with patch("aion.chat_ui.stream_repo_archimate_response", side_effect=mock_repo), \
             patch("aion.chat_ui.stream_inspect_response", side_effect=mock_inspect):
            resp = await client.post(
                "/api/chat/stream",
                json={"message": "Review https://github.com/Org/repo"},
            )

        # Inspect should be called, NOT repo_archimate
        assert len(inspect_called) == 1
        assert len(repo_called) == 0


class TestVocabularyRouting:
    """Tests that vocabulary queries route to the vocabulary agent."""

    @pytest.mark.asyncio
    async def test_vocabulary_skill_tag_routes_to_vocabulary_agent(self, client, _mock_lifespan):
        """retrieval + vocabulary tag → ExecutionModel.VOCABULARY."""
        persona_result = _make_persona_result(
            intent="retrieval",
            rewritten_query="Define active power",
            skill_tags=["vocabulary"],
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        call_log = []

        async def mock_vocab(*args, **kwargs):
            call_log.append(True)
            yield f"data: {json.dumps({'type': 'status', 'agent': 'Vocabulary', 'content': 'Searching SKOSMOS...'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'response': 'Active power is the rate of energy transfer.', 'sources': [{'title': 'IEC 61970'}], 'timing': {'total_ms': 200}})}\n\n"

        with patch("aion.chat_ui.stream_vocabulary_response", side_effect=mock_vocab):
            resp = await client.post(
                "/api/chat/stream",
                json={"message": "What is active power?"},
            )

        events = _collect_sse_events(resp.content)
        assert len(call_log) == 1

        complete = _find_event(events, "complete")
        assert "Active power" in complete["response"]


class TestGenerationRouting:
    """Tests that generation queries route to the generation pipeline."""

    @pytest.mark.asyncio
    async def test_generation_intent_routes_to_generation_pipeline(self, client, _mock_lifespan):
        """generation intent (without repo-analysis) → ExecutionModel.GENERATION."""
        persona_result = _make_persona_result(
            intent="generation",
            rewritten_query="Create an ArchiMate model for ADR.29",
            skill_tags=["archimate"],
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        call_log = []

        async def mock_gen(*args, **kwargs):
            call_log.append(True)
            yield f"data: {json.dumps({'type': 'status', 'content': 'Generating...'})}\n\n"
            yield f"data: {json.dumps({'type': 'artifact', 'artifact_id': 'abc123', 'filename': 'adr29.archimate.xml'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'response': 'Generated model with 8 elements.', 'sources': [], 'timing': {'total_ms': 3000}})}\n\n"

        with patch("aion.chat_ui.stream_generation_response", side_effect=mock_gen):
            resp = await client.post(
                "/api/chat/stream",
                json={"message": "Create an ArchiMate model for ADR.29"},
            )

        events = _collect_sse_events(resp.content)
        assert len(call_log) == 1

        # Should have artifact event
        artifact = _find_event(events, "artifact")
        assert artifact is not None
        assert artifact["filename"] == "adr29.archimate.xml"

        complete = _find_event(events, "complete")
        assert "8 elements" in complete["response"]

    @pytest.mark.asyncio
    async def test_generation_not_triggered_for_retrieval(self, client, _mock_lifespan):
        """retrieval + archimate tag routes to RAG (tree), NOT generation.
        The 'archimate' tag is for skill injection, not routing — retrieval
        intent always goes to the RAG agent regardless of skill tags."""
        persona_result = _make_persona_result(
            intent="retrieval",
            rewritten_query="What ArchiMate elements exist?",
            skill_tags=["archimate"],
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        gen_called = []
        rag_called = []

        async def mock_gen(*args, **kwargs):
            gen_called.append(True)
            yield f"data: {json.dumps({'type': 'complete', 'response': 'generated', 'sources': [], 'timing': {}})}\n\n"

        async def mock_rag(*args, **kwargs):
            rag_called.append(True)
            yield f"data: {json.dumps({'type': 'complete', 'response': 'RAG result about ArchiMate', 'sources': [], 'timing': {'total_ms': 300}})}\n\n"

        with patch("aion.chat_ui.stream_generation_response", side_effect=mock_gen), \
             patch("aion.chat_ui.stream_rag_response", side_effect=mock_rag):
            resp = await client.post(
                "/api/chat/stream",
                json={"message": "What ArchiMate elements exist?"},
            )

        # RAG should be called, NOT generation
        assert len(rag_called) == 1
        assert len(gen_called) == 0


class TestPrincipleRouting:
    """Tests that principle generation routes correctly."""

    @pytest.mark.asyncio
    async def test_principle_generation_routes_to_principle_agent(self, client, _mock_lifespan):
        """generation + generate-principle tag → ExecutionModel.PRINCIPLE."""
        persona_result = _make_persona_result(
            intent="retrieval",
            rewritten_query="Generate a principle on data sovereignty",
            skill_tags=["generate-principle"],
        )
        _mock_lifespan._persona.process = AsyncMock(return_value=persona_result)

        call_log = []

        async def mock_principle(*args, **kwargs):
            call_log.append(True)
            yield f"data: {json.dumps({'type': 'complete', 'response': 'PCP.42: Data Sovereignty...', 'sources': [], 'timing': {'total_ms': 1500}})}\n\n"

        with patch("aion.chat_ui.stream_principle_response", side_effect=mock_principle):
            resp = await client.post(
                "/api/chat/stream",
                json={"message": "Generate a principle on data sovereignty"},
            )

        assert len(call_log) == 1
        events = _collect_sse_events(resp.content)
        complete = _find_event(events, "complete")
        assert "PCP.42" in complete["response"]


# ── Functional E2E Tests (require Weaviate + Ollama) ──────────────────────────

@pytest.mark.functional
class TestLivePipeline:
    """E2E tests against real services. Skipped if Weaviate/Ollama unavailable."""

    @pytest.fixture()
    async def live_client(self):
        """Client using the real app with full lifespan."""
        from aion.chat_ui import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    @pytest.mark.asyncio
    async def test_live_identity_query(self, live_client):
        """'Who are you?' through the real Persona → direct response."""
        resp = await live_client.post(
            "/api/chat/stream",
            json={"message": "Who are you?"},
            timeout=30.0,
        )
        assert resp.status_code == 200
        events = _collect_sse_events(resp.content)
        complete = _find_event(events, "complete")
        assert complete is not None
        assert complete["path"] == "direct"
        assert "AInstein" in complete["response"] or "ainstein" in complete["response"].lower()

    @pytest.mark.asyncio
    async def test_live_retrieval_returns_adrs(self, live_client):
        """'What ADRs exist?' through the real pipeline → list of ADRs."""
        resp = await live_client.post(
            "/api/chat/stream",
            json={"message": "What ADRs exist in the system?"},
            timeout=60.0,
        )
        assert resp.status_code == 200
        events = _collect_sse_events(resp.content)

        persona_ev = _find_event(events, "persona_intent")
        assert persona_ev is not None
        # Intent should be retrieval or listing
        assert persona_ev["intent"] in ("retrieval", "listing", "follow_up")

        complete = _find_event(events, "complete")
        assert complete is not None
        # Should mention ADRs in the response
        assert "ADR" in complete["response"]

    @pytest.mark.asyncio
    async def test_live_off_topic_no_rag(self, live_client):
        """'What is the weather?' → off-topic, no RAG search."""
        resp = await live_client.post(
            "/api/chat/stream",
            json={"message": "What's the weather like today?"},
            timeout=30.0,
        )
        events = _collect_sse_events(resp.content)
        complete = _find_event(events, "complete")
        assert complete is not None
        assert complete["path"] == "direct"
        # Should NOT have any decision events (no agent execution)
        decisions = _find_events(events, "decision")
        assert len(decisions) == 0
