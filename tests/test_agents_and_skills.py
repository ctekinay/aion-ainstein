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

    def test_principle_quality_tag_routes_to_tree(self):
        """principle-quality tag stays on RAGAgent (tree) — skill is injected, no separate agent."""
        r = get_skill_registry()
        assert r.get_execution_model(["principle-quality"]) == "tree"

    def test_principle_generator_skill_registered(self):
        """principle-generator skill must be enabled with execution=principle."""
        r = get_skill_registry()
        entry = r.get_skill_entry("principle-generator")
        assert entry is not None
        assert entry.execution == "principle"
        assert entry.enabled is True
        assert "generate-principle" in entry.tags

    def test_principle_quality_assessor_skill_registered(self):
        """principle-quality-assessor skill must be enabled with inject_into_tree=True."""
        r = get_skill_registry()
        entry = r.get_skill_entry("principle-quality-assessor")
        assert entry is not None
        assert entry.enabled is True
        assert entry.inject_into_tree is True
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

    def test_generation_intent_ignores_tags(self):
        assert self._get_execution_model("generation", ["vocabulary"]) == "generation"

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

    def test_principle_quality_tag_stays_on_tree(self):
        """principle-quality is skill injection only — RAGAgent handles it."""
        assert self._get_execution_model("retrieval", ["principle-quality"]) == "tree"

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
            "list_all_adrs",
            "list_all_principles",
            "list_all_policies",
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
        prompt = ArchiMateAgent._build_system_prompt("skill content here", None)
        assert "AInstein" in prompt
        assert "ArchiMate" in prompt
        assert "get_artifact FIRST" in prompt
        assert "skill content here" in prompt

    def test_archimate_agent_system_prompt_with_artifact(self):
        from aion.agents.archimate_agent import ArchiMateAgent
        prompt = ArchiMateAgent._build_system_prompt("", "artifact xml here")
        assert "artifact xml here" in prompt

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
        prompt = PrincipleAgent._build_system_prompt("skill content here", None)
        assert "AInstein" in prompt
        assert "principle" in prompt.lower()
        assert "skill content here" in prompt

    def test_principle_agent_system_prompt_with_artifact(self):
        from aion.agents.principle_agent import PrincipleAgent
        prompt = PrincipleAgent._build_system_prompt("", "previous principle text")
        assert "previous principle text" in prompt
