"""Tests for agent construction, skill routing, and capability gaps.

Verifies that:
- All three agents build correctly with the expected tool sets
- Skill registry routes tags to the correct execution model
- Execution model routing in chat_ui picks the right agent
- SessionContext iteration limits work
- capability_gaps CRUD works end-to-end
- No tag collisions between generation and archimate skills
"""

import sqlite3
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from aion.agents import SessionContext
from aion.config import settings
from aion.skills.registry import get_skill_registry

# ── SessionContext tests ──


class TestSessionContext:

    def test_defaults(self):
        ctx = SessionContext()
        assert ctx.conversation_id is None
        assert ctx.system_prompt == ""
        assert ctx.tool_call_count == 0
        assert ctx.max_tool_calls == 4
        assert ctx.retrieved_objects == []

    def test_check_iteration_limit_increments(self):
        ctx = SessionContext(max_tool_calls=3)
        assert ctx.check_iteration_limit() is False  # call 1 <= 3
        assert ctx.check_iteration_limit() is False  # call 2 <= 3
        assert ctx.check_iteration_limit() is False  # call 3 <= 3
        assert ctx.check_iteration_limit() is True   # call 4 > 3
        assert ctx.tool_call_count == 4

    def test_emit_event_with_queue(self):
        q = Queue()
        ctx = SessionContext(event_queue=q)
        ctx.emit_event({"type": "status", "content": "test"})
        assert q.get_nowait() == {"type": "status", "content": "test"}

    def test_emit_event_without_queue(self):
        ctx = SessionContext()
        # Should not raise
        ctx.emit_event({"type": "status", "content": "test"})

    def test_system_prompt_field(self):
        ctx = SessionContext(system_prompt="You are a test agent.")
        assert ctx.system_prompt == "You are a test agent."

    def test_search_cache_default_empty(self):
        ctx = SessionContext()
        assert ctx._search_cache == {}

    def test_search_cache_scoped_to_instance(self):
        """Each SessionContext has its own cache — no cross-request leakage."""
        ctx1 = SessionContext()
        ctx1._search_cache["adr:ADR.27:0027"] = [{"title": "TLS"}]
        ctx2 = SessionContext()
        assert ctx2._search_cache == {}

    def test_step_index_default_none(self):
        ctx = SessionContext()
        assert ctx.step_index is None

    def test_step_index_set(self):
        ctx = SessionContext(step_index=2)
        assert ctx.step_index == 2


class TestProcessHistory:
    """Regression tests for process_history truncation boundary logic."""

    def _make_tool_pair(self, call_id: str):
        from pydantic_ai.messages import ModelResponse, ModelRequest, ToolCallPart, ToolReturnPart
        response = ModelResponse(parts=[
            ToolCallPart(tool_name="some_tool", args="{}", tool_call_id=call_id)
        ])
        request = ModelRequest(parts=[
            ToolReturnPart(tool_name="some_tool", content="result", tool_call_id=call_id)
        ])
        return response, request

    def _make_ctx(self, summary=None):
        ctx = MagicMock()
        ctx.deps.running_summary = summary
        return ctx

    def test_no_orphaned_tool_return_after_truncation(self):
        """Truncation must not leave a ToolReturnPart at position 0.

        Regression test for Bug V: repo analysis 7-tool-call sequence (with
        retries) produces >16 messages, triggering truncation. Without the
        ToolReturnPart boundary fix, the orphaned tool result crashes the
        OpenAI API with HTTP 400: 'messages with role tool must be a response
        to a preceding message with tool_calls'.
        """
        from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart
        from aion.agents import process_history

        # 10 tool call pairs (20 msgs) + 1 user msg = 21 total.
        # MAX_HISTORY_PAIRS=8 → max_msgs=16 → truncation WILL trigger.
        messages = [ModelRequest(parts=[UserPromptPart(content="Analyze repo")])]
        for i in range(10):
            resp, req = self._make_tool_pair(f"call_{i}")
            messages.append(resp)
            messages.append(req)

        assert len(messages) == 21  # confirm truncation will trigger

        result = process_history(self._make_ctx(), messages)

        first = result[0]
        is_orphaned = (
            isinstance(first, ModelRequest)
            and bool(first.parts)
            and all(isinstance(p, ToolReturnPart) for p in first.parts)
        )
        assert not is_orphaned, (
            "First message after truncation is an orphaned tool return. "
            "OpenAI rejects this with HTTP 400."
        )

    def test_truncation_does_not_split_normal_turn(self):
        """Truncation landing on a ModelResponse still backs up correctly — no regression."""
        from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart
        from aion.agents import process_history

        messages = [ModelRequest(parts=[UserPromptPart(content="Q")])]
        for i in range(10):
            resp, req = self._make_tool_pair(f"call_{i}")
            messages.append(resp)
            messages.append(req)

        result = process_history(self._make_ctx(), messages)

        assert not isinstance(result[0], ModelResponse), (
            "Truncation left a ModelResponse at position 0 — missing its user request."
        )


class TestSearchCaching:
    """Test that RAG agent tool wrapper caching prevents retry spirals."""

    def _build_mock_toolkit(self):
        """Build a RAGToolkit with mocked Weaviate client."""
        from aion.tools.rag_search import RAGToolkit

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.config.get.return_value.properties = []
        mock_client.collections.exists.return_value = True
        mock_client.collections.get.return_value = mock_collection

        mock_obj = MagicMock()
        mock_obj.properties = {
            "title": "Use TLS", "content": "TLS content",
            "file_path": "/doc/0027.md", "adr_number": "0027",
            "doc_type": "adr", "status": "proposed",
        }
        mock_result = MagicMock()
        mock_result.objects = [mock_obj]
        mock_collection.query.fetch_objects.return_value = mock_result

        toolkit = RAGToolkit(mock_client)
        return toolkit, mock_collection

    def _mock_model(self):
        """Patch build_pydantic_ai_model to avoid needing a real API key."""
        return patch.object(
            type(settings), "build_pydantic_ai_model",
            return_value="test",
        )

    def _get_tool_fn(self, agent, name):
        """Get a tool's function from the Pydantic AI agent."""
        return agent._function_toolset.tools[name].function

    def test_tool_wrapper_cache_prevents_duplicate_weaviate_calls(self):
        """Second call to search_architecture_decisions with same params
        returns cached result without hitting Weaviate again."""
        from aion.agents.rag_agent import _build_rag_agent

        toolkit, mock_collection = self._build_mock_toolkit()
        with self._mock_model():
            agent = _build_rag_agent(toolkit)
        search_fn = self._get_tool_fn(agent, "search_architecture_decisions")

        ctx = SessionContext(doc_refs=["ADR.27"], max_tool_calls=15)
        mock_run_ctx = MagicMock()
        mock_run_ctx.deps = ctx

        # First call — hits Weaviate
        result1 = search_fn(mock_run_ctx, "0027", 10)
        first_call_count = mock_collection.query.fetch_objects.call_count
        assert first_call_count >= 1

        # Second call — should return cached, no new Weaviate call
        result2 = search_fn(mock_run_ctx, "0027", 10)
        assert mock_collection.query.fetch_objects.call_count == first_call_count
        assert result2 is result1

    def test_cache_hit_does_not_burn_tool_call_slot(self):
        """Cached lookups must not increment tool_call_count."""
        from aion.agents.rag_agent import _build_rag_agent

        toolkit, _ = self._build_mock_toolkit()
        with self._mock_model():
            agent = _build_rag_agent(toolkit)
        search_fn = self._get_tool_fn(agent, "search_architecture_decisions")

        ctx = SessionContext(doc_refs=["ADR.27"], max_tool_calls=15)
        mock_run_ctx = MagicMock()
        mock_run_ctx.deps = ctx

        # First call increments counter
        search_fn(mock_run_ctx, "0027", 10)
        count_after_first = ctx.tool_call_count

        # Second call (cached) should NOT increment
        search_fn(mock_run_ctx, "0027", 10)
        assert ctx.tool_call_count == count_after_first

    def test_different_limits_produce_different_cache_entries(self):
        """limit=5 vs limit=10 must not collide in cache."""
        ctx = SessionContext(doc_refs=["ADR.27"])
        key_5 = f"adr:{','.join(sorted(ctx.doc_refs))}:0027:5"
        key_10 = f"adr:{','.join(sorted(ctx.doc_refs))}:0027:10"
        assert key_5 != key_10

    def test_different_search_types_different_cache_keys(self):
        """ADR and PCP searches don't collide even with same doc_refs."""
        ctx = SessionContext(doc_refs=["ADR.27"])
        adr_key = f"adr:{','.join(sorted(ctx.doc_refs))}:0027:10"
        pcp_key = f"pcp:{','.join(sorted(ctx.doc_refs))}:0027:10"
        assert adr_key != pcp_key


class TestDirectQueryFilteredDocRefs:
    """Test that _direct_query passes filtered doc_refs to each search tool."""

    def test_mixed_doc_refs_filtered_correctly(self):
        """When doc_refs has both ADR and PCP refs, each search tool
        receives only its own type."""
        from aion.agents.rag_agent import RAGAgent

        mock_client = MagicMock()
        mock_client.collections.exists.return_value = True
        mock_coll = MagicMock()
        mock_coll.config.get.return_value.properties = []
        mock_client.collections.get.return_value = mock_coll

        with patch.object(
            type(settings), "build_pydantic_ai_model", return_value="test",
        ):
            agent = RAGAgent(mock_client)

        # Mock the toolkit's search methods
        agent.toolkit.search_architecture_decisions = MagicMock(return_value=[
            {"title": "Use TLS", "content": "TLS...", "file_path": "/0027.md"},
        ])
        agent.toolkit.search_principles = MagicMock(return_value=[
            {"title": "Eventual Consistency", "content": "EC...", "file_path": "/0010.md"},
        ])

        ctx = SessionContext(
            doc_refs=["ADR.27", "PCP.10"],
            step_index=1,
        )

        # Mock the LLM call that _direct_query makes after retrieving results
        with patch.object(agent, "_generate_with_openai", return_value="Comparison result"):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                agent._direct_query("Compare ADR.27 and PCP.10", ctx)
            )

        # Assert each search received only its own refs
        agent.toolkit.search_architecture_decisions.assert_called_once()
        adr_call_kwargs = agent.toolkit.search_architecture_decisions.call_args
        assert adr_call_kwargs[1]["doc_refs"] == ["ADR.27"]

        agent.toolkit.search_principles.assert_called_once()
        pcp_call_kwargs = agent.toolkit.search_principles.call_args
        assert pcp_call_kwargs[1]["doc_refs"] == ["PCP.10"]


# ── Skill registry routing tests ──


class TestSkillRouting:

    def test_archimate_tag_routes_to_generation(self):
        """archimate tag should route to generation (for model creation)."""
        r = get_skill_registry()
        assert r.get_execution_model(["archimate"]) == "generation"

    def test_validate_tag_routes_to_archimate(self):
        """validate tag should route to archimate agent."""
        r = get_skill_registry()
        assert r.get_execution_model(["validate"]) == "archimate"

    def test_inspect_tag_routes_to_archimate(self):
        r = get_skill_registry()
        assert r.get_execution_model(["inspect"]) == "archimate"

    def test_merge_tag_routes_to_archimate(self):
        r = get_skill_registry()
        assert r.get_execution_model(["merge"]) == "archimate"

    def test_archimate_model_tag_routes_to_archimate(self):
        r = get_skill_registry()
        assert r.get_execution_model(["archimate-model"]) == "archimate"

    def test_vocabulary_tag_routes_to_vocabulary(self):
        r = get_skill_registry()
        assert r.get_execution_model(["vocabulary"]) == "vocabulary"

    def test_skosmos_tag_routes_to_vocabulary(self):
        r = get_skill_registry()
        assert r.get_execution_model(["skosmos"]) == "vocabulary"

    def test_empty_tags_route_to_tree(self):
        r = get_skill_registry()
        assert r.get_execution_model([]) == "tree"

    def test_unknown_tag_routes_to_tree(self):
        r = get_skill_registry()
        assert r.get_execution_model(["nonexistent-tag"]) == "tree"

    def test_no_tag_collision_between_generation_and_archimate(self):
        """Generation and archimate-tools skills must not share tags.

        If they share tags, generation always wins (checked first),
        making the archimate agent unreachable for those tags.
        """
        r = get_skill_registry()
        entries = {e.name: e for e in r.list_skills()}

        gen_entry = entries.get("archimate-generator")
        tools_entry = entries.get("archimate-tools")
        assert gen_entry is not None, "archimate-generator skill missing"
        assert tools_entry is not None, "archimate-tools skill missing"

        gen_tags = set(gen_entry.tags)
        tools_tags = set(tools_entry.tags)
        overlap = gen_tags & tools_tags
        assert overlap == set(), (
            f"Tag collision between generation and archimate-tools: {overlap}. "
            f"These tags will always route to generation, making archimate agent unreachable."
        )

    def test_archimate_tools_skill_registered(self):
        """archimate-tools should be in the registry with execution=archimate."""
        r = get_skill_registry()
        entry = r.get_skill_entry("archimate-tools")
        assert entry is not None
        assert entry.execution == "archimate"
        assert entry.enabled is True

    def test_generate_principle_tag_routes_to_principle(self):
        """generate-principle tag must route to PrincipleAgent, not RAGAgent."""
        r = get_skill_registry()
        assert r.get_execution_model(["generate-principle"]) == "principle"

    def test_principle_quality_tag_routes_to_principle(self):
        """principle-quality tag routes to PrincipleAgent execution model."""
        r = get_skill_registry()
        assert r.get_execution_model(["principle-quality"]) == "principle"

    def test_principle_generator_skill_registered(self):
        """principle-generator skill must be enabled with execution=principle."""
        r = get_skill_registry()
        entry = r.get_skill_entry("principle-generator")
        assert entry is not None
        assert entry.execution == "principle"
        assert entry.enabled is True
        assert "generate-principle" in entry.tags

    def test_principle_quality_assessor_skill_registered(self):
        """principle-quality-assessor skill must be enabled with execution=principle."""
        r = get_skill_registry()
        entry = r.get_skill_entry("principle-quality-assessor")
        assert entry is not None
        assert entry.enabled is True
        assert entry.inject_into_tree is False
        assert entry.execution == "principle"
        assert "principle-quality" in entry.tags

    def test_no_tag_collision_between_principle_skills(self):
        """principle-generator and principle-quality-assessor must not share tags."""
        r = get_skill_registry()
        entries = {e.name: e for e in r.list_skills()}
        gen = entries.get("principle-generator")
        assessor = entries.get("principle-quality-assessor")
        assert gen is not None
        assert assessor is not None
        overlap = set(gen.tags) & set(assessor.tags)
        assert overlap == set(), f"Tag collision between principle skills: {overlap}"


# ── Execution model routing tests (chat_ui._get_execution_model) ──


class TestExecutionModelRouting:

    def _get_execution_model(self, intent, skill_tags):
        """Import and call the routing function."""
        from aion.routing import get_execution_model
        return get_execution_model(intent, skill_tags)

    def test_generation_intent(self):
        assert self._get_execution_model("generation", []) == "generation"

    def test_generation_with_specialist_tags_overrides(self):
        assert self._get_execution_model("generation", ["vocabulary"]) == "vocabulary"

    def test_inspect_intent(self):
        assert self._get_execution_model("inspect", []) == "inspect"

    def test_vocabulary_tags(self):
        assert self._get_execution_model("retrieval", ["vocabulary"]) == "vocabulary"

    def test_archimate_tool_tags(self):
        assert self._get_execution_model("retrieval", ["validate"]) == "archimate"

    def test_archimate_model_tag(self):
        assert self._get_execution_model("retrieval", ["archimate-model"]) == "archimate"

    def test_refinement_with_archimate_generation_tags(self):
        """Refinement with archimate tag should route to generation (model creation)."""
        assert self._get_execution_model("refinement", ["archimate"]) == "generation"

    def test_refinement_with_archimate_tool_tags(self):
        """Refinement with validate tag should route to archimate agent."""
        assert self._get_execution_model("refinement", ["validate"]) == "archimate"

    def test_no_tags_routes_to_tree(self):
        assert self._get_execution_model("retrieval", []) == "tree"

    def test_none_tags_routes_to_tree(self):
        assert self._get_execution_model("retrieval", None) == "tree"

    def test_unknown_intent_with_no_matching_tags(self):
        assert self._get_execution_model("unknown", ["random"]) == "tree"

    def test_generate_principle_tag_routes_to_principle(self):
        assert self._get_execution_model("retrieval", ["generate-principle"]) == "principle"

    def test_principle_quality_tag_routes_to_principle(self):
        """principle-quality routes to PrincipleAgent."""
        assert self._get_execution_model("retrieval", ["principle-quality"]) == "principle"

    def test_refinement_with_generate_principle_routes_to_principle(self):
        assert self._get_execution_model("refinement", ["generate-principle"]) == "principle"


# ── Agent construction tests ──


class TestAgentConstruction:
    """Test that agents build correctly with expected tool sets.

    These tests verify the _build_*_agent() factory functions produce
    agents with the correct number and names of tools. We patch
    settings.build_pydantic_ai_model at the module level where each
    agent imports it.
    """

    def _get_tool_names(self, agent) -> set[str]:
        """Extract registered tool names from a Pydantic AI Agent."""
        toolset = getattr(agent, '_function_toolset', None)
        if toolset and hasattr(toolset, 'tools'):
            # tools is a dict {name: Tool}
            return set(toolset.tools.keys())
        return set()

    def _mock_model(self):
        """Patch build_pydantic_ai_model to return a test string."""
        return patch.object(
            type(settings), "build_pydantic_ai_model",
            return_value="test",
        )

    def test_archimate_agent_has_6_tools(self):
        with self._mock_model():
            from aion.agents.archimate_agent import _build_archimate_agent
            agent = _build_archimate_agent()
        tools = self._get_tool_names(agent)
        expected = {
            "validate_archimate",
            "inspect_archimate_model",
            "merge_archimate_view",
            "save_artifact",
            "get_artifact",
            "request_data",
        }
        assert tools == expected, f"ArchiMateAgent tools mismatch: got {tools}, expected {expected}"

    def test_rag_agent_has_8_tools(self):
        mock_client = MagicMock()
        with self._mock_model():
            from aion.agents.rag_agent import _build_rag_agent
            from aion.tools.rag_search import RAGToolkit
            toolkit = RAGToolkit(mock_client)
            agent = _build_rag_agent(toolkit)
        tools = self._get_tool_names(agent)
        expected = {
            "search_architecture_decisions",
            "search_principles",
            "search_policies",
            "list_adrs",
            "list_principles",
            "list_policies",
            "list_dars",
            "search_by_team",
            "request_data",
        }
        assert tools == expected, f"RAGAgent tools mismatch: got {tools}, expected {expected}"

    def test_vocabulary_agent_has_5_tools_with_client(self):
        mock_client = MagicMock()
        with self._mock_model():
            from aion.agents.vocabulary_agent import _build_vocabulary_agent
            from aion.tools.rag_search import RAGToolkit
            toolkit = RAGToolkit(mock_client)
            agent = _build_vocabulary_agent(toolkit)
        tools = self._get_tool_names(agent)
        expected = {
            "skosmos_search",
            "skosmos_concept_details",
            "skosmos_list_vocabularies",
            "search_knowledge_base",
            "request_data",
        }
        assert tools == expected, f"VocabularyAgent tools mismatch: got {tools}, expected {expected}"

    def test_vocabulary_agent_has_4_tools_without_client(self):
        with self._mock_model():
            from aion.agents.vocabulary_agent import _build_vocabulary_agent
            agent = _build_vocabulary_agent(None)
        tools = self._get_tool_names(agent)
        expected = {
            "skosmos_search",
            "skosmos_concept_details",
            "skosmos_list_vocabularies",
            "request_data",
        }
        assert tools == expected, f"VocabularyAgent (no client) tools mismatch: got {tools}, expected {expected}"

    def test_rag_agent_does_not_have_archimate_tools(self):
        """RAG agent should NOT have ArchiMate or artifact tools."""
        mock_client = MagicMock()
        with self._mock_model():
            from aion.agents.rag_agent import _build_rag_agent
            from aion.tools.rag_search import RAGToolkit
            toolkit = RAGToolkit(mock_client)
            agent = _build_rag_agent(toolkit)
        tools = self._get_tool_names(agent)
        forbidden = {
            "validate_archimate",
            "inspect_archimate_model",
            "merge_archimate_view",
            "save_artifact",
            "get_artifact",
            "get_collection_stats",
        }
        overlap = tools & forbidden
        assert overlap == set(), (
            f"RAG agent still has non-RAG tools: {overlap}. "
            f"These should be on the ArchiMateAgent."
        )

    def test_principle_agent_has_5_tools(self):
        mock_client = MagicMock()
        with self._mock_model():
            from aion.agents.principle_agent import _build_principle_agent
            from aion.tools.rag_search import RAGToolkit
            toolkit = RAGToolkit(mock_client)
            agent = _build_principle_agent(toolkit)
        tools = self._get_tool_names(agent)
        expected = {
            "search_principles",
            "list_principles",
            "search_related_principles",
            "validate_principle_structure",
            "save_principle",
            "get_principle",
            "request_data",
        }
        assert tools == expected, f"PrincipleAgent tools mismatch: got {tools}, expected {expected}"

    def test_all_agents_have_request_data(self):
        """Every agent must have the request_data capability gap probe."""
        mock_client = MagicMock()

        with self._mock_model():
            from aion.agents.archimate_agent import _build_archimate_agent
            from aion.agents.principle_agent import _build_principle_agent
            from aion.agents.rag_agent import _build_rag_agent
            from aion.agents.vocabulary_agent import _build_vocabulary_agent
            from aion.tools.rag_search import RAGToolkit

            toolkit = RAGToolkit(mock_client)
            agents = [
                ("archimate", _build_archimate_agent()),
                ("rag", _build_rag_agent(toolkit)),
                ("vocabulary", _build_vocabulary_agent(toolkit)),
                ("principle", _build_principle_agent(toolkit)),
            ]

        for name, agent in agents:
            tools = self._get_tool_names(agent)
            assert "request_data" in tools, f"{name} agent missing request_data tool"


# ── Capability gaps CRUD tests ──


class TestCapabilityGaps:

    @pytest.fixture
    def db(self, tmp_path):
        """Create an isolated SQLite database with the capability_gaps table."""
        db_path = tmp_path / "test_chat_history.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capability_gaps (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                agent TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        return db_path

    def test_save_and_get_capability_gap(self, db):
        """Round-trip: save a gap, then retrieve it."""
        with patch("aion.storage.capability_store._db_path", db):
            from aion.storage.capability_store import (
                get_capability_gaps,
                save_capability_gap,
            )

            gap_id = save_capability_gap("conv-123", "rag", "Need ENTSOE market data")
            assert gap_id  # non-empty UUID string

            gaps = get_capability_gaps(limit=10)
            assert len(gaps) == 1
            assert gaps[0]["agent"] == "rag"
            assert gaps[0]["description"] == "Need ENTSOE market data"
            assert gaps[0]["conversation_id"] == "conv-123"

    def test_multiple_gaps_ordered_by_recency(self, db):
        with patch("aion.storage.capability_store._db_path", db):
            from aion.storage.capability_store import (
                get_capability_gaps,
                save_capability_gap,
            )

            save_capability_gap("c1", "rag", "First gap")
            save_capability_gap("c1", "vocabulary", "Second gap")
            save_capability_gap("c2", "archimate", "Third gap")

            gaps = get_capability_gaps(limit=10)
            assert len(gaps) == 3
            # Most recent first
            assert gaps[0]["description"] == "Third gap"
            assert gaps[2]["description"] == "First gap"

    def test_get_gaps_respects_limit(self, db):
        with patch("aion.storage.capability_store._db_path", db):
            from aion.storage.capability_store import (
                get_capability_gaps,
                save_capability_gap,
            )

            for i in range(5):
                save_capability_gap(f"c{i}", "rag", f"Gap {i}")

            gaps = get_capability_gaps(limit=3)
            assert len(gaps) == 3

    def test_request_data_tool_logs_gap(self, db):
        """The request_data tool function should log to SQLite and return success."""
        with patch("aion.storage.capability_store._db_path", db):
            from aion.tools.capability_gaps import request_data

            result = request_data(
                description="Need real-time grid frequency data",
                conversation_id="conv-456",
                agent="rag",
            )
            assert result == "Data retrieved successfully. Continue your reasoning."

            from aion.storage.capability_store import get_capability_gaps
            gaps = get_capability_gaps()
            assert len(gaps) == 1
            assert gaps[0]["agent"] == "rag"
            assert gaps[0]["description"] == "Need real-time grid frequency data"


# ── Agent system prompt tests ──


class TestAgentSystemPrompts:

    def test_archimate_agent_system_prompt_includes_guidelines(self):
        from aion.agents.archimate_agent import ArchiMateAgent
        prompt = ArchiMateAgent._build_system_prompt("skill content here")
        assert "AInstein" in prompt
        assert "ArchiMate" in prompt
        assert "get_artifact FIRST" in prompt
        assert "skill content here" in prompt

    def test_archimate_agent_system_prompt_no_artifact_param(self):
        """_build_system_prompt does not accept artifact_context — it goes in user message."""
        import inspect
        from aion.agents.archimate_agent import ArchiMateAgent
        assert "artifact_context" not in inspect.signature(ArchiMateAgent._build_system_prompt).parameters
        prompt = ArchiMateAgent._build_system_prompt("")
        assert "AInstein" in prompt

    def test_rag_agent_system_prompt(self):
        from aion.agents.rag_agent import RAGAgent
        # RAGAgent._build_system_prompt is an instance method but only uses self for nothing
        # We can test it via a mock instance
        prompt = RAGAgent._build_system_prompt(None, "skill content", None)
        assert "AInstein" in prompt
        assert "knowledge base" in prompt
        assert "skill content" in prompt

    def test_vocabulary_agent_system_prompt(self):
        from aion.agents.vocabulary_agent import VocabularyAgent
        prompt = VocabularyAgent._build_system_prompt("vocab skill content")
        assert "AInstein" in prompt
        assert "vocabulary" in prompt
        assert "SKOSMOS" in prompt or "tiered" in prompt.lower()
        assert "vocab skill content" in prompt

    def test_principle_agent_system_prompt_includes_guidelines(self):
        from aion.agents.principle_agent import PrincipleAgent
        prompt = PrincipleAgent._build_system_prompt("skill content here")
        assert "AInstein" in prompt
        assert "principle" in prompt.lower()
        assert "skill content here" in prompt

    def test_principle_agent_system_prompt_no_artifact_param(self):
        """_build_system_prompt does not accept artifact_context — it goes in user message."""
        import inspect
        from aion.agents.principle_agent import PrincipleAgent
        assert "artifact_context" not in inspect.signature(PrincipleAgent._build_system_prompt).parameters
        prompt = PrincipleAgent._build_system_prompt("")
        assert "AInstein" in prompt
