"""RepoAnalysisAgent — Pydantic AI agent for repository architecture extraction.

Analyzes GitHub repos or local codebases and produces a structured
architecture_notes document. Zero LLM tokens for extraction — the LLM
only orchestrates tool calls.
"""

import logging
import time

import yaml
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage
from queue import Queue

from aion.agents import AGENT_LABELS, SessionContext, _get_max_tool_calls, process_history
from aion.config import settings
from aion.skills.registry import get_skill_registry
from aion.text_utils import elapsed_ms
from aion.tools.artifacts import save_artifact as _save_artifact
from aion.tools.repo_analysis import (
    clone_repo as _clone_repo,
    git_diff_stats as _git_diff_stats,
    merge_architecture_notes as _merge_notes,
    profile_repo as _profile_repo,
)
from aion.tools.repo_extractors import (
    build_dep_graph as _build_dep_graph,
    extract_code_structure as _extract_code_structure,
    extract_manifests as _extract_manifests,
)

logger = logging.getLogger(__name__)


def _get_skill_content(skill_tags: list[str] | None = None) -> str:
    """Load skill content for the repo-analysis skill."""
    registry = get_skill_registry()
    return registry.get_skill_content(active_tags=skill_tags or ["repo-analysis"])


def _build_repo_analysis_agent() -> Agent[SessionContext, str]:
    """Build the Pydantic AI agent with repo analysis tools."""
    agent: Agent[SessionContext, str] = Agent(
        model=settings.build_pydantic_ai_model("tree"),
        deps_type=SessionContext,
        retries=1,
        history_processors=[process_history],
    )

    @agent.system_prompt
    def dynamic_system_prompt(ctx: RunContext[SessionContext]) -> str:
        return ctx.deps.system_prompt

    @agent.tool
    def clone_repo(ctx_: RunContext[SessionContext], url_or_path: str) -> dict:
        """Clone a GitHub repository or validate a local path.
        ALWAYS call this first with the URL or path the user provided.

        Args:
            url_or_path: GitHub URL (https://...) or local directory path.
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        ctx_.deps.emit_event({
            "type": "decision",
            "content": f"Decision: clone_repo Reasoning: Cloning repository from {url_or_path[:80]}",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        result = _clone_repo(url_or_path)
        if "error" in result:
            error_msg = result["error"]
            # Detect auth failures and provide actionable guidance
            if any(hint in error_msg.lower() for hint in
                   ("authentication", "could not read username", "permission denied", "404")):
                error_msg += " This may be a private repository. Try providing a local path instead."
            ctx_.deps.emit_event({"type": "status", "content": f"Clone failed: {error_msg}",
                                  "elapsed_ms": elapsed_ms(ctx_.deps._query_start)})
        else:
            ctx_.deps.emit_event({"type": "status", "content": f"Repository cloned: {result['repo_name']}",
                                  "elapsed_ms": elapsed_ms(ctx_.deps._query_start)})
        ctx_.deps.retrieved_objects.append({"type": "clone_result", **result})
        return result

    @agent.tool
    def profile_repo(ctx_: RunContext[SessionContext], repo_path: str) -> dict:
        """Profile the repository structure — detect tech stack, modules, and classify files.
        Call this after clone_repo to understand the repository layout.

        Args:
            repo_path: Absolute path to the cloned repository.
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: profile_repo Reasoning: Profiling repository structure",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        result = _profile_repo(repo_path)
        t1 = result['file_tier_counts'].get('T1', 0)
        t2 = result['file_tier_counts'].get('T2', 0)
        ctx_.deps.emit_event({
            "type": "status",
            "content": (f"Profile complete: {result['total_files']} files "
                        f"({t1} T1 critical, {t2} T2 relevant), "
                        f"structure: {result.get('structure_type', 'unknown')}"),
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        ctx_.deps.retrieved_objects.append({"type": "profile", **result})
        return result

    @agent.tool
    def extract_manifests(ctx_: RunContext[SessionContext], repo_path: str) -> dict:
        """Extract deployment topology, API definitions, database schemas, CI/CD config,
        and package dependencies from manifest files.
        Call this after profile_repo.

        Args:
            repo_path: Absolute path to the cloned repository.
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: extract_manifests Reasoning: Extracting manifest files",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        # Need the profile from retrieved_objects
        profile = None
        for obj in ctx_.deps.retrieved_objects:
            if obj.get("type") == "profile":
                profile = obj
                break
        if not profile:
            return {"error": "No profile found. Call profile_repo first."}
        result = _extract_manifests(repo_path, profile)
        sections = [k for k, v in result.items() if v]
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Extracted {len(sections)} manifest sections",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        ctx_.deps.retrieved_objects.append({"type": "manifests", **result})
        return result

    @agent.tool
    def extract_code_structure(ctx_: RunContext[SessionContext], repo_path: str) -> dict:
        """Extract code structure using AST parsing (Python) and regex (JS/TS/Java/Go).
        Produces class hierarchies, function signatures, and import graphs.
        Call this after profile_repo.

        Args:
            repo_path: Absolute path to the cloned repository.
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: extract_code_structure Reasoning: Analyzing code structure via AST",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        profile = None
        for obj in ctx_.deps.retrieved_objects:
            if obj.get("type") == "profile":
                profile = obj
                break
        if not profile:
            return {"error": "No profile found. Call profile_repo first."}
        result = _extract_code_structure(repo_path, profile)
        stats = result.get("stats", {})
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Analyzed {stats.get('processed', 0)} files, {len(result.get('modules', []))} modules",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        ctx_.deps.retrieved_objects.append({"type": "code_structure", **result})
        return result

    @agent.tool
    def build_dep_graph(ctx_: RunContext[SessionContext]) -> dict:
        """Build the cross-module dependency graph from code imports and manifest data.
        Call this after extract_manifests and extract_code_structure.
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: build_dep_graph Reasoning: Building dependency graph",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        code_structure = None
        manifests = None
        for obj in ctx_.deps.retrieved_objects:
            if obj.get("type") == "code_structure":
                code_structure = obj
            elif obj.get("type") == "manifests":
                manifests = obj
        if not code_structure or not manifests:
            return {"error": "Missing code_structure or manifests. Call extraction tools first."}
        result = _build_dep_graph(code_structure, manifests)
        ctx_.deps.emit_event({
            "type": "status",
            "content": f"Graph: {len(result.get('nodes', []))} nodes, {len(result.get('edges', []))} edges",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        ctx_.deps.retrieved_objects.append({"type": "dep_graph", **result})
        return result

    @agent.tool
    def merge_and_save_notes(ctx_: RunContext[SessionContext]) -> dict:
        """Merge all extraction outputs into architecture_notes and save as artifact.
        Call this LAST after all extraction tools have completed.
        """
        if ctx_.deps.check_iteration_limit():
            return {"error": "Tool call limit reached"}
        ctx_.deps.emit_event({
            "type": "decision",
            "content": "Decision: merge_and_save_notes Reasoning: Merging architecture analysis",
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        profile = manifests = code_structure = dep_graph = clone_result = None
        for obj in ctx_.deps.retrieved_objects:
            t = obj.get("type")
            if t == "profile":
                profile = obj
            elif t == "manifests":
                manifests = obj
            elif t == "code_structure":
                code_structure = obj
            elif t == "dep_graph":
                dep_graph = obj
            elif t == "clone_result":
                clone_result = obj

        if not all([profile, manifests, code_structure, dep_graph]):
            return {"error": "Missing extraction data. Run all extraction tools first."}

        # Derive base_branch and diff stats for the v1.0 template
        base_branch = None
        diff_stats = None
        if clone_result:
            base_branch = clone_result.get("default_branch")
            repo_path = clone_result.get("repo_path")
            if base_branch and repo_path:
                diff_stats = _git_diff_stats(repo_path, base_branch) or None

        merged = _merge_notes(
            profile, manifests, code_structure, dep_graph,
            clone_result=clone_result, base_branch=base_branch, diff_stats=diff_stats,
        )

        # Save as artifact for Phase 2 handoff
        if ctx_.deps.conversation_id:
            summary_text = (
                f"Repository architecture analysis: {merged.get('summary', {}).get('repo_name', 'unknown')} — "
                f"{merged.get('summary', {}).get('total_components', 0)} components, "
                f"{merged.get('summary', {}).get('total_infrastructure', 0)} infrastructure"
            )
            _save_artifact(
                "architecture_notes.yaml",
                yaml.dump(merged, default_flow_style=False, allow_unicode=True, sort_keys=False),
                "repo-analysis/yaml",
                summary_text,
                ctx_.deps.conversation_id,
                ctx_.deps.event_queue,
            )

        ctx_.deps.emit_event({
            "type": "status",
            "content": (f"Architecture notes saved: {merged.get('summary', {}).get('total_components', 0)} components, "
                        f"{merged.get('summary', {}).get('total_edges', 0)} relationships"),
            "elapsed_ms": elapsed_ms(ctx_.deps._query_start),
        })
        ctx_.deps.retrieved_objects.append(merged)
        return {"status": "saved", "summary": merged.get("summary", {})}

    return agent


class RepoAnalysisAgent:
    """Pydantic AI agent for repository architecture extraction."""

    def __init__(self):
        self._agent = _build_repo_analysis_agent()

    async def query(
        self,
        question: str,
        event_queue: Queue | None = None,
        skill_tags: list[str] | None = None,
        doc_refs: list[str] | None = None,
        conversation_id: str | None = None,
        message_history: list[ModelMessage] | None = None,
        running_summary: str | None = None,
    ) -> tuple[str, list[dict]]:
        """Process a repo analysis query."""
        skill_content = _get_skill_content(skill_tags=skill_tags or ["repo-analysis"])

        ctx = SessionContext(
            conversation_id=conversation_id,
            event_queue=event_queue,
            doc_refs=doc_refs or [],
            skill_tags=skill_tags or [],
            agent_label=AGENT_LABELS["repo_analysis_agent"],
            system_prompt=self._build_system_prompt(skill_content),
            _query_start=time.perf_counter(),
            max_tool_calls=_get_max_tool_calls("repo_analysis_agent", 12),
            running_summary=running_summary,
        )

        logger.info("RepoAnalysisAgent processing: %s", question[:200])
        logger.info("repo_analysis_agent_model model=%s", self._agent.model.model_name)

        try:
            result = await self._agent.run(question, deps=ctx, message_history=message_history or [])
            response = result.output
        except Exception as e:
            logger.exception("RepoAnalysisAgent error")
            response = f"I encountered an error during repository analysis: {e}"

        elapsed = elapsed_ms(ctx._query_start)
        logger.info("RepoAnalysisAgent complete: %d ms, %d tool calls", elapsed, ctx.tool_call_count)

        return response, ctx.retrieved_objects

    @staticmethod
    def _build_system_prompt(skill_content: str) -> str:
        parts = [
            "You are AInstein, the Energy System Architecture AI Assistant at Alliander.",
            "",
            "Your role is to analyze software repositories and extract their architecture "
            "into a structured context document for ArchiMate model generation.",
        ]
        if skill_content:
            parts.extend(["", skill_content])
        parts.extend([
            "",
            "Guidelines:",
            "- Call tools in this exact order: clone_repo → profile_repo → extract_manifests → "
            "extract_code_structure → build_dep_graph → merge_and_save_notes",
            "- If any extraction step fails, continue with remaining tools (graceful degradation)",
            "- After merge_and_save_notes, summarize what was found: components, infrastructure, "
            "tech stack, and key relationships",
            "- Include the repository profile summary in your response",
        ])
        return "\n".join(parts)
