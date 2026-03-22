"""Simple chat UI server for AION knowledge assistant.

A clean, local chat interface that wraps the RAGAgent.
Streams the agent's thinking process to the UI.
"""

import asyncio
import json
import re
import sqlite3
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from weaviate.classes.query import Filter

from aion.agents import AGENT_LABELS
from aion.agents.archimate_agent import ArchiMateAgent
from aion.agents.principle_agent import PrincipleAgent
from aion.agents.rag_agent import RAGAgent
from aion.agents.vocabulary_agent import VocabularyAgent
from aion.config import is_reasoning_model, settings
from aion.generation import GenerationPipeline, stream_synthesis_response
from aion.ingestion.client import get_weaviate_client
from aion.ingestion.embeddings import close_embeddings_client, embed_text
from aion.memory.session_store import (
    create_session,
    get_running_summary,
    init_memory_tables,
    update_running_summary,
)
from aion.memory.summarizer import generate_rolling_summary
from aion.orchestrator import MultiStepOrchestrator
from aion.persona import PermanentLLMError, Persona
from aion.pixel_agents import pixel_registry
from aion.registry.element_registry import init_registry_table
from aion.routing import ExecutionModel
from aion.routing import get_execution_model as _get_execution_model
from aion.skills import api as skills_api
from aion.text_utils import elapsed_ms, strip_think_tags
from aion.skills.loader import get_thresholds_value
from aion.tools.rag_search import _get_retrieval_limits, _get_truncation

logger = structlog.get_logger(__name__)


# Global state
_weaviate_client = None
_rag_agent = None
_vocabulary_agent = None
_archimate_agent = None
_principle_agent = None
_repo_analysis_agent = None
_generation_pipeline = None
_persona = None
_db_path = settings.db_path


def _get_connection() -> sqlite3.Connection:
    """Open a SQLite connection with thread-safety for use in async/threaded contexts."""
    return sqlite3.connect(_db_path, check_same_thread=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    global _weaviate_client, _rag_agent, _vocabulary_agent, _archimate_agent, _principle_agent, _repo_analysis_agent, _generation_pipeline, _persona

    # Startup
    init_db()

    # Apply persisted user settings (provider/model preferences from last session)
    settings.apply_user_overrides()

    # Validate configuration before connecting to services
    config_errors = settings.validate_startup()
    for err in config_errors:
        logger.error(f"Config: {err}")
    if config_errors:
        raise RuntimeError(
            f"Configuration validation failed ({len(config_errors)} error(s)). "
            "Check logs above and fix .env settings."
        )

    # Ollama reachability check (warning, not fatal)
    if "ollama" in (
        settings.effective_persona_provider,
        settings.effective_rag_provider,
        settings.effective_embedding_provider,
    ):
        try:
            import httpx
            httpx.get(f"{settings.ollama_url}/api/tags", timeout=settings.timeout_health_check).raise_for_status()
            logger.info(f"Ollama reachable at {settings.ollama_url}")
        except Exception as e:
            logger.warning(f"Ollama not reachable at {settings.ollama_url}: {e}")

    logger.info(
        f"Config: persona={settings.effective_persona_provider}/{settings.effective_persona_model}, "
        f"rag={settings.effective_rag_provider}/{settings.effective_rag_model}, "
        f"embedding={settings.effective_embedding_provider}/{settings.embedding_model}"
    )

    try:
        _weaviate_client = get_weaviate_client()
        logger.info("Connected to Weaviate")
    except Exception as e:
        logger.error(f"Failed to connect to Weaviate: {e}")
        raise

    # Embedding dimension validation — surface mismatches early
    try:
        from aion.ingestion.embeddings import get_embedding_dimension
        configured_dim = get_embedding_dimension()
        for coll_name in ["ArchitecturalDecision", "Principle", "PolicyDocument"]:
            if not _weaviate_client.collections.exists(coll_name):
                continue
            coll = _weaviate_client.collections.get(coll_name)
            sample = coll.query.fetch_objects(limit=1, include_vector=True)
            if not sample.objects or not sample.objects[0].vector:
                continue
            vec = sample.objects[0].vector
            # Handle both dict format {"default": [...]} and flat list
            if isinstance(vec, dict):
                vec = vec.get("default", [])
            stored_dim = len(vec)
            if stored_dim and stored_dim != configured_dim:
                logger.error(
                    "EMBEDDING DIMENSION MISMATCH: %s has %d-dim vectors "
                    "but %s produces %d-dim. RAG search will fail. "
                    "Either set EMBEDDING_PROVIDER to match ingestion model "
                    "or re-ingest data.",
                    coll_name, stored_dim, settings.embedding_model, configured_dim,
                )
            break  # Only need to check one collection with data
    except Exception as e:
        logger.warning("Could not validate embedding dimensions: %s", e)

    _rag_agent = RAGAgent(_weaviate_client)
    logger.info("RAGAgent initialized")

    _vocabulary_agent = VocabularyAgent(_weaviate_client)
    logger.info("VocabularyAgent initialized")

    _archimate_agent = ArchiMateAgent()
    logger.info("ArchiMateAgent initialized")

    _principle_agent = PrincipleAgent(_weaviate_client)
    logger.info("PrincipleAgent initialized")

    from aion.agents.repo_analysis_agent import RepoAnalysisAgent
    _repo_analysis_agent = RepoAnalysisAgent()
    logger.info("RepoAnalysisAgent initialized")

    _generation_pipeline = GenerationPipeline(_weaviate_client)
    logger.info("Generation pipeline initialized")

    _persona = Persona()
    logger.info("Persona orchestrator initialized")

    pixel_registry.init(pixel_agents_dir=settings.pixel_agents_dir)

    try:
        yield  # App is running
    finally:
        # Shutdown — always clean up pixel agents, even on crash
        pixel_registry.shutdown()
        close_embeddings_client()
        logger.info("Embeddings client closed")
        if _weaviate_client:
            _weaviate_client.close()
            logger.info("Weaviate connection closed")


# FastAPI app with lifespan
app = FastAPI(
    title="AInstein - Energy System Architect Assistant",
    description="Chat interface for the Alliander energy system knowledge base",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: str | None = None
    sources: list[dict] | None = None


class LLMSettings(BaseModel):
    """LLM provider and model settings."""
    provider: str = "ollama"  # "ollama", "github_models", or "openai"
    model: str = "gpt-oss:20b"
    # Per-component overrides (None = use global provider/model)
    persona_provider: str | None = None
    persona_model: str | None = None
    rag_provider: str | None = None
    rag_model: str | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    llm_settings: LLMSettings | None = None

    @field_validator("message")
    @classmethod
    def message_length(cls, v: str) -> str:
        if len(v) > 16000:
            raise ValueError("Message exceeds 16,000 character limit. Please shorten your input.")
        return v


class ComparisonRequest(BaseModel):
    """Request for side-by-side LLM comparison (Test Mode)."""
    message: str
    conversation_id: str | None = None
    ollama_model: str = "gpt-oss:20b"
    openai_model: str = "gpt-5.2"


class ChatResponse(BaseModel):
    response: str
    sources: list[dict]
    conversation_id: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    message_count: int


class ThresholdsUpdate(BaseModel):
    thresholds: dict


class SkillContentUpdate(BaseModel):
    content: str | None = None
    metadata: dict | None = None
    body: str | None = None


class ToggleRequest(BaseModel):
    enabled: bool


# Available models per provider — each provider has its own catalog.
AVAILABLE_MODELS = {
    "ollama": [
        {"id": "gpt-oss:20b", "name": "GPT-OSS (Local, 20B)"},
        {"id": "qwen3:14b", "name": "Qwen3 (Local, 14B)"},
        {"id": "qwen3:4b", "name": "Qwen3 (Local, 4B)"},
        {"id": "qwen3.5:9b", "name": "Qwen3.5 (Local, 9B)"},
    ],
    # GitHub CoPilot Models — catalog IDs use publisher/model format.
    # Full catalog: https://models.github.ai/catalog/models
    # Enterprise Copilot: 200K-1M input tokens (no free-tier 8K limit)
    "github_models": [
        {"id": "openai/gpt-5", "name": "GPT-5 (200K ctx)"},
        {"id": "openai/gpt-5-mini", "name": "GPT-5 Mini (200K ctx)"},
        {"id": "openai/gpt-5-nano", "name": "GPT-5 Nano"},
        {"id": "openai/o3", "name": "O3 (Reasoning)"},
        {"id": "openai/o4-mini", "name": "O4 Mini (Reasoning)"},
        {"id": "deepseek/deepseek-r1-0528", "name": "DeepSeek R1 (Reasoning)"},
        {"id": "xai/grok-3", "name": "Grok 3"},
        {"id": "meta/llama-4-scout-17b-16e-instruct", "name": "Llama 4 Scout 17B (10M ctx)"},
        {"id": "mistral-ai/mistral-small-2503", "name": "Mistral Small 3.1"},
    ],
    # Native OpenAI — model IDs without publisher prefix.
    "openai": [
        {"id": "gpt-5.2", "name": "GPT-5.2 (400K ctx)"},
        {"id": "gpt-5.2-pro", "name": "GPT-5.2 Pro (400K ctx)"},
        {"id": "gpt-5.1", "name": "GPT-5.1"},
        {"id": "gpt-5.1-mini", "name": "GPT-5.1 Mini"},
        {"id": "gpt-5-mini", "name": "GPT-5 Mini"},
        {"id": "gpt-5-nano", "name": "GPT-5 Nano"},
    ],
}

# Current session LLM settings (in-memory, can be overridden per request)
_current_llm_settings = LLMSettings()


# Database functions
def init_db():
    """Initialize SQLite database for conversation history."""
    conn = _get_connection()
    try:
        # WAL mode allows concurrent readers alongside a writer; set once, persists on the file.
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                sources TEXT,
                timestamp TEXT,
                timing TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)

        # Migration: Add timing column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN timing TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Migration: Add turn_summary column for structured conversation context
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN turn_summary TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Migration: Add thinking_steps column for persisting AInstein's thought process
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN thinking_steps TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Migration: Add artifact_ids column to link messages to their artifacts
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN artifact_ids TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Artifacts table — stores generated files (ArchiMate XML, etc.)
        # so the Tree can load and refine them across turns.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                turn INTEGER NOT NULL,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                content_type TEXT NOT NULL,
                summary TEXT,
                created_at TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capability_gaps (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                agent TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)

        conn.commit()
    finally:
        conn.close()

    # Memory tables (sessions, user_profiles) — same database file
    init_memory_tables(_db_path)

    # Element registry table — stable identity for generated elements
    init_registry_table(_db_path)


def save_message(conversation_id: str, role: str, content: str, sources: list[dict] = None, timing: dict = None, turn_summary: str = None, thinking_steps: list[dict] = None, artifact_ids: list[str] = None):
    """Save a message to the database."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        timestamp = datetime.now().isoformat()
        sources_json = json.dumps(sources) if sources else None
        timing_json = json.dumps(timing) if timing else None
        thinking_json = json.dumps(thinking_steps) if thinking_steps else None
        artifact_ids_json = json.dumps(artifact_ids) if artifact_ids else None

        cursor.execute(
            "INSERT INTO messages (conversation_id, role, content, sources, timestamp, timing, turn_summary, thinking_steps, artifact_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, role, content, sources_json, timestamp, timing_json, turn_summary, thinking_json, artifact_ids_json)
        )

        # Update conversation timestamp
        cursor.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (timestamp, conversation_id)
        )

        conn.commit()
    finally:
        conn.close()


def create_conversation(title: str = "New Conversation") -> str:
    """Create a new conversation and return its ID."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        conv_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        cursor.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, timestamp, timestamp)
        )

        conn.commit()
    finally:
        conn.close()
    return conv_id


def get_conversation_messages(conversation_id: str) -> list[dict]:
    """Get all messages for a conversation."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT role, content, sources, timestamp, timing, turn_summary, thinking_steps, artifact_ids FROM messages WHERE conversation_id = ? ORDER BY timestamp",
            (conversation_id,)
        )

        messages = []
        for row in cursor.fetchall():
            messages.append({
                "role": row[0],
                "content": row[1],
                "sources": json.loads(row[2]) if row[2] else None,
                "timestamp": row[3],
                "timing": json.loads(row[4]) if row[4] else None,
                "turn_summary": row[5],
                "thinking_steps": json.loads(row[6]) if row[6] else None,
                "artifact_ids": json.loads(row[7]) if row[7] else None,
            })
    finally:
        conn.close()
    return messages


def get_artifacts_by_ids(artifact_ids: list[str]) -> list[dict]:
    """Get artifact metadata for a list of IDs."""
    if not artifact_ids:
        return []
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(artifact_ids))
        cursor.execute(
            f"SELECT id, filename, content_type, summary FROM artifacts WHERE id IN ({placeholders})",
            artifact_ids,
        )
        artifacts = []
        for row in cursor.fetchall():
            artifacts.append({
                "id": row[0], "filename": row[1],
                "content_type": row[2], "summary": row[3],
            })
    finally:
        conn.close()
    return artifacts


def get_all_conversations() -> list[dict]:
    """Get all conversations with message counts and last updated time."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) as message_count
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
        """)

        conversations = []
        for row in cursor.fetchall():
            conversations.append({
                "id": row[0],
                "title": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "message_count": row[4],
            })
    finally:
        conn.close()
    return conversations


def update_conversation_title(conversation_id: str, title: str):
    """Update conversation title."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (title, conversation_id)
        )

        conn.commit()
    finally:
        conn.close()


def delete_conversation(conversation_id: str):
    """Delete a conversation and its messages."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

        conn.commit()
    finally:
        conn.close()


def delete_all_conversations():
    """Delete all conversations and messages."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM messages")
        cursor.execute("DELETE FROM conversations")
        cursor.execute("DELETE FROM artifacts")

        conn.commit()
    finally:
        conn.close()


def save_artifact(
    conversation_id: str,
    filename: str,
    content: str,
    content_type: str,
    summary: str = "",
) -> str:
    """Save a generated artifact (ArchiMate XML, etc.) for later retrieval.

    Returns the artifact ID.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        artifact_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # Determine turn number from message count
        cursor.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        turn = cursor.fetchone()[0]

        cursor.execute(
            "INSERT INTO artifacts (id, conversation_id, turn, filename, content, content_type, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (artifact_id, conversation_id, turn, filename, content, content_type, summary, timestamp),
        )

        conn.commit()
    finally:
        conn.close()
    logger.info(f"Saved artifact {filename} ({len(content)} chars) for {conversation_id}")
    return artifact_id


def get_latest_artifact(conversation_id: str, content_type: str = None) -> dict | None:
    """Get the most recent artifact for a conversation.

    Args:
        conversation_id: The conversation to search in.
        content_type: Optional filter (e.g., "archimate/xml").

    Returns:
        Dict with id, filename, content, content_type, summary, or None.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        if content_type:
            cursor.execute(
                "SELECT id, filename, content, content_type, summary, turn FROM artifacts "
                "WHERE conversation_id = ? AND content_type = ? ORDER BY turn DESC LIMIT 1",
                (conversation_id, content_type),
            )
        else:
            cursor.execute(
                "SELECT id, filename, content, content_type, summary, turn FROM artifacts "
                "WHERE conversation_id = ? ORDER BY turn DESC LIMIT 1",
                (conversation_id,),
            )

        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "filename": row[1],
        "content": row[2],
        "content_type": row[3],
        "summary": row[4],
        "turn": row[5],
    }


# save_capability_gap and get_capability_gaps imported from aion.storage.capability_store


def _has_user_content(message: str, rewritten_query: str | None) -> bool:
    """Heuristic: does the message contain substantial pasted content?

    True when message is >2x longer than the rewritten query AND >500 chars.
    More reliable than asking the LLM to set a boolean flag.
    Tuning lever if false-positives occur: add `and message.count('\\n') > 5`
    (pasted content almost always has multiple newlines; verbose questions usually don't).
    """
    rq_len = len(rewritten_query or "")
    return len(message) > rq_len * 2 and len(message) > 500


async def _build_turn_summary(response: str, sources: list[dict]) -> str:
    """Build a structured turn summary from response and sources.

    Produces a compact semantic summary so the Persona can resolve follow-ups
    like "Is there a common theme across these?" or "2" (referring to an option).

    For listing responses, uses structured extraction (ADR/PCP ID ranges).
    For all other responses, uses an LLM call for a semantic summary.
    Falls back to source-based type counts, then 500-char truncation.
    """
    if not response:
        return ""

    # Listing responses: extract document count and ID range.
    # This is data extraction (parsing structured identifiers), not intent detection.
    adr_ids = re.findall(r'\bADR[.\s]?(\d{1,3})\b', response)
    pcp_ids = re.findall(r'\bPCP[.\s]?(\d{1,3})\b', response)

    if len(set(adr_ids)) >= 3:
        nums = sorted(set(int(x) for x in adr_ids))
        id_range = f"ADR.{nums[0]:02d} through ADR.{nums[-1]:02d}"
        return f"Listed {len(nums)} ADRs ({id_range})"

    if len(set(pcp_ids)) >= 3:
        nums = sorted(set(int(x) for x in pcp_ids))
        id_range = f"PCP.{nums[0]} through PCP.{nums[-1]}"
        return f"Listed {len(nums)} principles ({id_range})"

    # LLM summary: always attempt first. Produces a semantic one-sentence
    # summary that captures options, generated content, questions, etc.
    llm_summary = await _llm_summarize_turn(response)
    if llm_summary:
        return llm_summary

    # Fallback when LLM summary fails: source-based type count
    if sources:
        type_counts = {}
        for src in sources:
            doc_type = src.get("type", "Document")
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        parts = [f"{count} {dt}{'s' if count > 1 else ''}" for dt, count in sorted(type_counts.items())]
        return f"Retrieved {', '.join(parts)}"

    # Last resort: 500-char truncation
    return response[:500] + "..." if len(response) > 500 else response


async def _llm_summarize_turn(response: str) -> str | None:
    """Use the Persona's LLM to produce a one-sentence turn summary.

    Returns None on failure so the caller can fall back to truncation.
    """
    # Truncate input to avoid sending huge payloads (e.g., full XML models)
    text = response[:2000] if len(response) > 2000 else response

    prompt = (
        "Summarize the following assistant response in ONE concise sentence "
        "(max 400 chars). Capture the key action or information conveyed — "
        "e.g., what was generated, what options were offered, what question "
        "was asked. If the response contains numbered options, list them.\n\n"
        f"RESPONSE:\n{text}\n\nSUMMARY:"
    )

    try:
        if settings.effective_persona_provider in ("github_models", "openai"):
            return await _llm_summarize_openai(prompt)
        return await _llm_summarize_ollama(prompt)
    except Exception as e:
        logger.warning(f"LLM turn summary failed, falling back to truncation: {e}")
        return None


async def _llm_summarize_openai(prompt: str) -> str | None:
    """Summarize via OpenAI API (same provider as Persona)."""
    from openai import OpenAI

    client = OpenAI(**settings.get_openai_client_kwargs(
        settings.effective_persona_provider, timeout=settings.timeout_llm_call,
    ))
    model = settings.effective_persona_model

    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    token_limits = get_thresholds_value("get_llm_token_limits", {})
    if is_reasoning_model(model):
        kwargs["max_completion_tokens"] = token_limits.get("summarize_reasoning", 512)
    else:
        kwargs["max_tokens"] = token_limits.get("summarize_standard", 150)

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0] if response.choices else None
    text = (choice.message.content or "").strip() if choice else ""
    return text if text else None


async def _llm_summarize_ollama(prompt: str) -> str | None:
    """Summarize via Ollama API (same provider as Persona)."""
    import httpx

    async with httpx.AsyncClient(timeout=settings.timeout_llm_call) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": settings.effective_persona_model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 150},
            },
        )
        resp.raise_for_status()
        text = strip_think_tags(resp.json().get("response", ""))
        return text if text else None


async def _maybe_update_summary(conversation_id: str) -> None:
    """Trigger a rolling summary update if enough messages have left the verbatim window.

    The verbatim window is loaded from persona-orchestrator thresholds (default 20).
    We summarize when settings.summarize_trigger_count (4) messages have accumulated
    beyond that window since the last summary, so roughly every 4-6 turns.
    """
    from aion.skills.loader import SkillLoader  # local import to avoid circular

    messages = get_conversation_messages(conversation_id)
    loader = SkillLoader()
    persona_config = loader.get_thresholds("persona-orchestrator").get("persona", {})
    verbatim_window = persona_config.get("verbatim_window", 20)

    # Nothing to summarize if all messages fit in the verbatim window
    if len(messages) <= verbatim_window:
        return

    # Messages before the verbatim window that need summarizing
    older_messages = messages[:-verbatim_window]

    # Check how many unsummarized messages exist. The running summary
    # covers some earlier messages — we only need to summarize when
    # enough new ones have accumulated.
    current_summary = get_running_summary(conversation_id)

    # Heuristic: if the summary is empty, summarize all older messages.
    # Otherwise, only summarize when settings.summarize_trigger_count new messages
    # have accumulated (we count from the last summary update by tracking
    # how many older messages exist vs what the summary likely covers).
    if current_summary and len(older_messages) < settings.summarize_trigger_count:
        return

    # Only summarize the most recent batch of older messages (the ones
    # that just left the window), not the entire history again.
    batch = older_messages[-settings.summarize_trigger_count:] if current_summary else older_messages

    try:
        new_summary = await generate_rolling_summary(current_summary, batch)
        if new_summary:
            update_running_summary(conversation_id, new_summary)
            logger.info(
                f"Rolling summary updated for {conversation_id}: "
                f"{len(new_summary)} chars, {len(older_messages)} older messages"
            )
    except Exception as e:
        logger.warning(f"Rolling summary update failed: {e}")


def _query_references_artifact(query: str, intent: str, artifact: dict, artifact_age: int = 0) -> bool:
    """Check if the query references a previously loaded artifact.

    Intent-based + content-type-aware: follow_up and retrieval queries that
    mention artifact-relevant terms when there's an active artifact.
    Not routing — the Persona already classified intent. This is a content
    availability check for whether the Tree needs the artifact in its atlas.

    artifact_age: number of messages since the artifact was created.
    Used for implicit injection — recent artifacts (<=4 turns) are injected
    for follow_up intents even without explicit keyword references.
    """
    if intent not in ("follow_up", "retrieval"):
        return False
    q = query.lower()
    ct = artifact.get("content_type", "")
    if "archimate" in ct or "yaml" in ct:
        # Explicit model references — always inject regardless of age
        if any(t in q for t in ("model", "archimate", "element", "relationship", "artifact")):
            return True
        # Implicit: follow_up with a RECENT archimate artifact (within 4 turns).
        # 4 messages ≈ 2 user + 2 assistant turns — enough for "generate" →
        # "is this compliant?" → one more follow-up. Beyond that, require
        # explicit keyword references to avoid stale injection.
        if intent == "follow_up" and artifact_age <= 4:
            return True
        return False
    if "principle" in ct:
        return any(t in q for t in ("principle", "statement", "rationale", "implications", "artifact"))
    return "artifact" in q


# _get_execution_model imported from aion.routing


# ============== Unified Thread Runner Helpers ==============


def _run_agent_in_thread(
    coro_factory,
    result_queue: Queue,
    output_queue: Queue,
    label: str = "Agent",
):
    """Run an async coroutine in a new event loop inside a thread.

    Args:
        coro_factory: Callable(output_queue) -> coroutine that returns (response, objects).
        result_queue: Queue for the final result dict.
        output_queue: Queue for streaming events (passed to the factory).
        label: Log prefix for error messages.
    """
    import asyncio

    start_time = time.perf_counter()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            response, objects = loop.run_until_complete(coro_factory(output_queue))
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

        total_time_ms = elapsed_ms(start_time)
        result_queue.put({
            "response": response,
            "objects": objects,
            "error": None,
            "timing": {"total_ms": total_time_ms},
        })
    except Exception as e:
        logger.exception(f"{label} error")
        total_time_ms = elapsed_ms(start_time)
        result_queue.put({
            "response": None,
            "objects": None,
            "error": str(e),
            "timing": {"total_ms": total_time_ms},
        })
    finally:
        output_queue.put(None)


def _extract_sources(objects: list, simple: bool = False) -> list[dict]:
    """Build source list from retrieved objects.

    Args:
        objects: Raw objects from agent result (may contain nested lists).
        simple: If True, use simple extraction (generation pipeline).
                If False, flatten nested lists and handle multi-field content.
    """
    display_limit = _get_truncation().get("source_display_limit", 35)

    if simple:
        sources = []
        for obj in objects[:display_limit]:
            if not isinstance(obj, dict):
                continue
            sources.append({
                "type": obj.get("type", "Document"),
                "title": obj.get("title") or "Untitled",
                "preview": (obj.get("content") or "")[:200],
            })
        return sources

    flat_objects = []
    for item in objects:
        if isinstance(item, list):
            flat_objects.extend(item)
        elif isinstance(item, dict):
            flat_objects.append(item)

    sources = []
    for obj in flat_objects[:display_limit]:
        if not isinstance(obj, dict):
            continue
        source = {
            "type": obj.get("type", "Document"),
            "title": obj.get("title") or obj.get("label") or "Untitled",
        }
        content = obj.get("content") or obj.get("definition") or obj.get("decision") or ""
        if content:
            source["preview"] = content[:200] + "..." if len(content) > 200 else content
        sources.append(source)
    return sources


async def _stream_agent_response(
    coro_factory,
    label: str,
    initial_status: str,
    agent_key: str = "",
    join_timeout: int = settings.timeout_agent_default,
    simple_sources: bool = False,
    emit_assistant_event: bool = True,
) -> AsyncGenerator[str, None]:
    """Generic SSE streaming for any agent that returns (response, objects).

    Args:
        coro_factory: Callable(output_queue) -> coroutine returning (response, objects).
        label: Log prefix (e.g., "RAG", "Vocabulary", "ArchiMate", "Generation").
        initial_status: First SSE status message to send.
        agent_key: Key into AGENT_LABELS for the agent field on the initial status event.
        join_timeout: Thread join timeout in seconds.
        simple_sources: Use simple source extraction (generation) vs. flattened (agents).
        emit_assistant_event: Whether to emit an 'assistant' event when no streaming events
                              were captured but a response exists.
    """
    result_queue = Queue()
    output_queue = Queue()

    logger.info(f"Starting {label} query")

    init_event: dict = {"type": "status", "content": initial_status}
    if agent_key:
        init_event["agent"] = AGENT_LABELS.get(agent_key, agent_key)
    yield f"data: {json.dumps(init_event)}\n\n"

    thread = Thread(
        target=_run_agent_in_thread,
        args=(coro_factory, result_queue, output_queue, label),
    )
    thread.daemon = True
    thread.start()

    event_count = 0
    last_status_time = asyncio.get_event_loop().time()
    start_time = asyncio.get_event_loop().time()

    while thread.is_alive():
        try:
            event = output_queue.get(timeout=0.1)
            if event is None:
                break
            event_count += 1
            logger.info(f"{label} event {event_count}: {event['type']}")
            yield f"data: {json.dumps(event)}\n\n"
            last_status_time = asyncio.get_event_loop().time()
        except Empty:
            now = asyncio.get_event_loop().time()
            if now - last_status_time > 3:
                elapsed_sec = int(now - start_time)
                yield f"data: {json.dumps({'type': 'heartbeat', 'elapsed_sec': elapsed_sec})}\n\n"
                last_status_time = now
            await asyncio.sleep(0.05)
            continue

    # Drain remaining events
    while True:
        try:
            event = output_queue.get_nowait()
            if event is None:
                break
            event_count += 1
            logger.info(f"Draining {label} event {event_count}: {event['type']}")
            yield f"data: {json.dumps(event)}\n\n"
        except Empty:
            break

    logger.info(f"{label} stream complete, sent {event_count} events")

    thread.join(timeout=join_timeout)

    try:
        result = result_queue.get_nowait()
        if result["error"]:
            logger.error(f"{label} error: {result['error']}")
            yield f"data: {json.dumps({'type': 'error', 'content': result['error']})}\n\n"
        else:
            final_response = result["response"] or ""
            timing = result.get("timing", {})
            objects = result["objects"] or []

            sources = _extract_sources(objects, simple=simple_sources)

            logger.info(f"{label} complete, response length: {len(final_response)}, time: {timing.get('total_ms', 0)}ms")

            if emit_assistant_event and event_count == 0 and final_response:
                yield f"data: {json.dumps({'type': 'assistant', 'content': final_response, 'timing': timing})}\n\n"

            yield f"data: {json.dumps({'type': 'complete', 'response': final_response, 'sources': sources, 'timing': timing})}\n\n"
    except Empty:
        logger.error(f"{label} timed out")
        yield f"data: {json.dumps({'type': 'error', 'content': f'{label} timed out'})}\n\n"


async def stream_generation_response(
    question: str,
    skill_tags: list[str] | None = None,
    doc_refs: list[str] | None = None,
    github_refs: list[str] | None = None,
    conversation_id: str | None = None,
    intent: str = "generation",
    source_text: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream generation pipeline events as SSE."""
    def factory(output_queue):
        return _generation_pipeline.generate(
            question,
            skill_tags=skill_tags or [],
            doc_refs=doc_refs,
            github_refs=github_refs,
            conversation_id=conversation_id,
            event_queue=output_queue,
            intent=intent,
            source_text=source_text,
        )
    async for event in _stream_agent_response(
        factory, label="Generation", initial_status="Starting generation...", agent_key="archimate_agent",
        join_timeout=settings.timeout_agent_multi_tool, simple_sources=True, emit_assistant_event=False,
    ):
        yield event


async def stream_inspect_response(
    question: str,
    conversation_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream inspection response as SSE events.

    Three input paths (tried in order):
    1. Load latest ArchiMate artifact from the conversation (XML or YAML)
    2. Detect a URL in the query: repo root → README analysis,
       file URL → ArchiMate validation, generic URL → httpx fetch
    3. No model found — prompt user to generate or upload
    """
    from aion.tools.yaml_to_xml import _parse_and_validate, xml_to_yaml

    yield f"data: {json.dumps({'type': 'status', 'content': 'Loading model...'})}\n\n"

    yaml_content = None
    source_filename = None
    source = None
    content_type = "archimate"  # "archimate", "github_repo", or "github_file"
    github_content = None

    # Path 1: Load latest artifact from conversation (try XML first, then YAML)
    artifact = None
    if conversation_id:
        artifact = get_latest_artifact(conversation_id, content_type="archimate/xml")
        if not artifact:
            artifact = get_latest_artifact(conversation_id, content_type="text/yaml")

    if artifact:
        if artifact["content_type"] == "text/yaml":
            yaml_content = artifact["content"]
        else:
            try:
                yaml_content = xml_to_yaml(artifact["content"])
            except ValueError as e:
                yield f"data: {json.dumps({'type': 'complete', 'response': f'Failed to parse the ArchiMate model: {e}', 'sources': [], 'timing': {}})}\n\n"
                return
        source_filename = artifact.get("filename", "model.archimate.xml")
        source = f"Artifact: {source_filename}"

    # Path 2: Detect URL in the query and fetch content
    if not yaml_content:
        url_match = re.search(r'https?://\S+', question)
        if url_match:
            url = url_match.group(0).rstrip('.,;:)')
            try:
                from aion.mcp.github import (
                    get_file_contents as mcp_get_file,
                )
                from aion.mcp.github import (
                    get_org_overview,
                    get_repo_metadata,
                    get_repo_readme,
                    list_directory,
                    parse_github_url,
                )
                parsed = parse_github_url(url)
                if parsed and parsed.get("type") == "org":
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Fetching organization info...'})}\n\n"
                    github_content = await get_org_overview(parsed["owner"])
                    source_filename = parsed["owner"]
                    source = f"GitHub org/user: {parsed['owner']}"
                    content_type = "github_org"
                    logger.info(f"Fetched org overview for {parsed['owner']} ({len(github_content)} chars)")
                elif parsed and parsed.get("type") == "repo":
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Fetching repository info...'})}\n\n"
                    # Parallel fetch: metadata, README, and directory listing
                    metadata_task = asyncio.ensure_future(
                        get_repo_metadata(parsed["owner"], parsed["repo"])
                    )
                    readme_task = asyncio.ensure_future(
                        get_repo_readme(parsed["owner"], parsed["repo"], parsed["ref"])
                    )
                    dir_task = asyncio.ensure_future(
                        list_directory(parsed["owner"], parsed["repo"], "", parsed["ref"])
                    )
                    metadata = readme = dir_listing = ""
                    for name, task in [("metadata", metadata_task), ("README", readme_task), ("directory", dir_task)]:
                        try:
                            result = await task
                            if name == "metadata":
                                metadata = result
                            elif name == "README":
                                readme = result
                            else:
                                dir_listing = result
                        except Exception as e:
                            logger.warning(f"Repo {name} fetch failed: {e}")
                    if not metadata and not readme and not dir_listing:
                        raise ValueError(f"Could not fetch any content from {parsed['owner']}/{parsed['repo']}")
                    # Assemble context for LLM
                    parts = []
                    if metadata:
                        parts.append(f"REPOSITORY METADATA:\n{metadata}")
                    if dir_listing:
                        parts.append(f"ROOT DIRECTORY:\n{dir_listing}")
                    if readme:
                        max_readme = settings.max_readme_chars
                        if len(readme) > max_readme:
                            readme = readme[:max_readme] + "\n\n[README truncated]"
                        parts.append(f"README.md:\n{readme}")
                    github_content = "\n\n---\n\n".join(parts)
                    source_filename = f"{parsed['owner']}/{parsed['repo']}"
                    source = f"GitHub repo: {parsed['owner']}/{parsed['repo']}@{parsed['ref']}"
                    content_type = "github_repo"
                    logger.info(f"Fetched repo info for {parsed['owner']}/{parsed['repo']}@{parsed['ref']} ({len(github_content)} chars)")
                elif parsed:
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Fetching from GitHub...'})}\n\n"
                    fetched = await mcp_get_file(
                        owner=parsed["owner"], repo=parsed["repo"],
                        path=parsed["path"], ref=parsed["ref"],
                    )
                    source_filename = parsed["path"].rsplit("/", 1)[-1]
                    source = f"Fetched from GitHub: {url}"
                    # Non-ArchiMate file: analyze generically
                    is_archimate = source_filename.endswith((".xml", ".yaml", ".yml"))
                    if not is_archimate:
                        binary_exts = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz", ".whl", ".pyc"}
                        ext = "." + source_filename.rsplit(".", 1)[-1].lower() if "." in source_filename else ""
                        if ext in binary_exts:
                            raise ValueError(f"Binary files ({ext}) cannot be analyzed. Try a text-based file instead.")
                        github_content = fetched
                        content_type = "github_file"
                else:
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Fetching model from URL...'})}\n\n"
                    import httpx
                    async with httpx.AsyncClient(timeout=settings.timeout_llm_call, follow_redirects=True) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        fetched = resp.text
                    source_filename = url.rsplit("/", 1)[-1] if "/" in url else "fetched-model.xml"
                    source = f"Fetched from URL: {url}"

                if content_type == "archimate":
                    is_yaml = source_filename.endswith((".yaml", ".yml"))
                    is_xml = source_filename.endswith(".xml")

                    if not is_yaml and not is_xml:
                        raise ValueError(
                            f"Unsupported file type: {source_filename}. "
                            "The inspect pipeline supports ArchiMate XML (.xml) and YAML (.yaml, .yml) files."
                        )

                    if is_yaml:
                        _parse_and_validate(fetched)
                        yaml_content = fetched
                        if conversation_id:
                            save_artifact(conversation_id, source_filename, fetched, "text/yaml", f"Fetched from: {url}")
                    else:
                        yaml_content = xml_to_yaml(fetched)
                        if conversation_id:
                            save_artifact(conversation_id, source_filename, fetched, "archimate/xml", f"Fetched from: {url}")

                    logger.info(f"Fetched ArchiMate model from URL: {url} ({len(fetched)} chars)")
            except ValueError as e:
                yield f"data: {json.dumps({'type': 'complete', 'response': f'Failed to fetch model: {e}', 'sources': [], 'timing': {}})}\n\n"
                return
            except Exception as e:
                yield f"data: {json.dumps({'type': 'complete', 'response': f'Failed to fetch URL: {e}', 'sources': [], 'timing': {}})}\n\n"
                return

    # Path 3: No model found (only for ArchiMate — GitHub content skips this)
    if content_type == "archimate" and not yaml_content:
        yield f"data: {json.dumps({'type': 'complete', 'response': 'No ArchiMate model found in this conversation. Generate a model first, upload an ArchiMate XML/YAML file, or paste a URL to one.', 'sources': [], 'timing': {}})}\n\n"
        return

    # LLM analysis — branched prompts, shared LLM call
    if content_type == "github_org":
        yield f"data: {json.dumps({'type': 'status', 'content': 'Analyzing organization...'})}\n\n"
        system_prompt = (
            "You are AInstein, the Energy System Architecture AI Assistant. "
            "You are reviewing a GitHub organization or user profile. "
            "Summarize what this organization does, their key repositories, "
            "technologies used, and any notable projects or patterns. "
            "Be specific — reference actual repository names and descriptions. "
            "Use markdown formatting for readability."
        )
        user_prompt = f"[Source: {source}]\n\n{github_content}\n\nQUESTION: {question}"
        source_info = {
            "type": "GitHub Organization",
            "title": source_filename,
            "preview": github_content[:200] if github_content else "",
        }
    elif content_type == "github_repo":
        yield f"data: {json.dumps({'type': 'status', 'content': 'Analyzing repository...'})}\n\n"
        system_prompt = (
            "You are AInstein, the Energy System Architecture AI Assistant. "
            "You are reviewing a GitHub repository. "
            "Analyze the repository metadata, directory structure, and README. "
            "Summarize what this project does, its architecture, key components, "
            "technologies used, and any notable patterns. "
            "Be specific — reference actual content from the repository. "
            "Use markdown formatting for readability."
        )
        user_prompt = f"[Source: {source}]\n\n{github_content}\n\nQUESTION: {question}"
        source_info = {
            "type": "GitHub Repository",
            "title": source_filename,
            "preview": github_content[:200] if github_content else "",
        }
    elif content_type == "github_file":
        yield f"data: {json.dumps({'type': 'status', 'content': 'Analyzing file...'})}\n\n"
        ext = source_filename.rsplit(".", 1)[-1] if "." in source_filename else "text"
        system_prompt = (
            "You are AInstein, the Energy System Architecture AI Assistant. "
            "You are reviewing a file from a GitHub repository. "
            "Analyze the file content and explain its purpose, structure, "
            "and key patterns. Be specific — reference actual code or content. "
            "Use markdown formatting for readability."
        )
        user_prompt = f"[Source: {source}]\n\nFILE: {source_filename}\n```{ext}\n{github_content}```\n\nQUESTION: {question}"
        source_info = {
            "type": "GitHub File",
            "title": source_filename,
            "preview": github_content[:200] if github_content else "",
        }
    else:
        yield f"data: {json.dumps({'type': 'status', 'content': 'Analyzing model...'})}\n\n"
        system_prompt = (
            "You are AInstein, reviewing an ArchiMate model. "
            "The model has been converted to a compact YAML representation that "
            "contains all elements and relationships. View definitions (diagram "
            "layouts) are intentionally omitted for efficiency — they contain "
            "positioning data, not semantic content. "
            "Analyze the elements and relationships directly. "
            "Never state that views are missing, that content is incomplete, or "
            "that you cannot access the model — you have everything needed for "
            "semantic analysis. "
            "Be specific — reference element names, types, and relationships from the model. "
            "Use markdown formatting for readability."
        )
        user_prompt = f"[Source: {source}]\n\nARCHIMATE MODEL (YAML):\n```yaml\n{yaml_content}```\n\nQUESTION: {question}"
        source_info = {
            "type": "ArchiMate Model",
            "title": source_filename or "model.archimate.xml",
            "preview": f"Model with {yaml_content.count('- id:')} elements",
        }

    start_time = time.perf_counter()
    try:
        if settings.effective_rag_provider in ("github_models", "openai"):
            from openai import OpenAI
            client = OpenAI(**settings.get_openai_client_kwargs(
                settings.effective_rag_provider, timeout=settings.timeout_llm_inspect,
            ))
            model = settings.effective_rag_model
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            token_limits = get_thresholds_value("get_llm_token_limits", {})
            if is_reasoning_model(model):
                kwargs["max_completion_tokens"] = token_limits.get("chat_review_reasoning", 4096)
            else:
                kwargs["max_tokens"] = token_limits.get("chat_review_standard", 2000)
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0] if response.choices else None
            response_text = (choice.message.content or "").strip() if choice else ""
        else:
            import httpx
            async with httpx.AsyncClient(timeout=settings.timeout_llm_inspect) as client:
                resp = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.effective_rag_model,
                        "prompt": f"{system_prompt}\n\n{user_prompt}",
                        "stream": False,
                        "options": {"num_predict": 2000},
                    },
                )
                resp.raise_for_status()
                response_text = strip_think_tags(resp.json().get("response", ""))

        total_ms = elapsed_ms(start_time)
        timing = {"total_ms": total_ms}

        sources = [source_info]

        logger.info(f"Inspect complete: {total_ms}ms, {len(response_text)} chars")
        yield f"data: {json.dumps({'type': 'complete', 'response': response_text, 'sources': sources, 'timing': timing})}\n\n"

    except Exception as e:
        logger.exception("Inspect LLM error")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Analysis failed: {e}'})}\n\n"


async def stream_rag_response(question: str,
                                 skill_tags: list[str] | None = None,
                                 doc_refs: list[str] | None = None,
                                 conversation_id: str | None = None,
                                 artifact_context: str | None = None,
                                 complexity: str | None = None) -> AsyncGenerator[str, None]:
    """Stream RAGAgent's thinking process as SSE events."""
    def factory(output_queue):
        return _rag_agent.query(
            question, event_queue=output_queue,
            skill_tags=skill_tags, doc_refs=doc_refs,
            conversation_id=conversation_id,
            artifact_context=artifact_context,
            complexity=complexity,
        )
    # 180s allows multi-tool chains with slow models
    # (gpt-5-nano: ~15s per LLM call × 5 iterations + SKOSMOS API calls)
    async for event in _stream_agent_response(
        factory, label="RAG", initial_status="Searching knowledge base...", agent_key="rag_agent",
        join_timeout=settings.timeout_agent_multi_tool,
    ):
        yield event


async def stream_vocabulary_response(question: str,
                                     skill_tags: list[str] | None = None,
                                     doc_refs: list[str] | None = None,
                                     conversation_id: str | None = None) -> AsyncGenerator[str, None]:
    """Stream VocabularyAgent's thinking process as SSE events."""
    def factory(output_queue):
        return _vocabulary_agent.query(
            question, event_queue=output_queue,
            skill_tags=skill_tags, doc_refs=doc_refs,
            conversation_id=conversation_id,
        )
    async for event in _stream_agent_response(
        factory, label="Vocabulary", initial_status="Looking up vocabulary...", agent_key="vocabulary_agent",
    ):
        yield event


# ============== ArchiMate Agent Streaming ==============


async def stream_principle_response(question: str,
                                    skill_tags: list[str] | None = None,
                                    doc_refs: list[str] | None = None,
                                    conversation_id: str | None = None,
                                    artifact_context: str | None = None) -> AsyncGenerator[str, None]:
    """Stream PrincipleAgent's thinking process as SSE events."""
    def factory(output_queue):
        return _principle_agent.query(
            question, event_queue=output_queue,
            skill_tags=skill_tags, doc_refs=doc_refs,
            conversation_id=conversation_id,
            artifact_context=artifact_context,
        )
    is_assessment = skill_tags and "principle-quality" in skill_tags
    status = "Assessing principle quality..." if is_assessment else "Generating principle..."
    async for event in _stream_agent_response(
        factory, label="Principle", initial_status=status, agent_key="principle_agent",
    ):
        yield event


async def stream_archimate_response(question: str,
                                    skill_tags: list[str] | None = None,
                                    doc_refs: list[str] | None = None,
                                    conversation_id: str | None = None,
                                    artifact_context: str | None = None) -> AsyncGenerator[str, None]:
    """Stream ArchiMateAgent's thinking process as SSE events."""
    def factory(output_queue):
        return _archimate_agent.query(
            question, event_queue=output_queue,
            skill_tags=skill_tags, doc_refs=doc_refs,
            conversation_id=conversation_id,
            artifact_context=artifact_context,
        )
    async for event in _stream_agent_response(
        factory, label="ArchiMate", initial_status="Processing ArchiMate model...", agent_key="archimate_agent",
    ):
        yield event


async def stream_repo_analysis_response(
    question: str,
    skill_tags: list[str] | None = None,
    conversation_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream RepoAnalysisAgent's thinking process as SSE events."""
    def factory(output_queue):
        return _repo_analysis_agent.query(
            question, event_queue=output_queue,
            skill_tags=skill_tags,
            conversation_id=conversation_id,
        )
    async for event in _stream_agent_response(
        factory, label="RepoAnalysis", initial_status="Analyzing repository...",
        agent_key="repo_analysis_agent",
        join_timeout=settings.timeout_agent_multi_tool,
    ):
        yield event


async def stream_repo_archimate_response(
    question: str,
    skill_tags: list[str] | None = None,
    conversation_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Chain repo analysis (Phase 1) → ArchiMate generation (Phase 2)."""
    assert conversation_id, "stream_repo_archimate_response requires conversation_id for artifact handoff"
    # Phase 1: Run repo analysis, forward status/decision events, suppress complete
    phase1_error = False
    phase1_response = ""
    async for event in stream_repo_analysis_response(
        question, skill_tags=skill_tags, conversation_id=conversation_id,
    ):
        try:
            data = json.loads(event.replace("data: ", "").strip())
            if data.get("type") == "complete":
                phase1_response = data.get("response", "")
                continue  # suppress Phase 1 complete — Phase 2 produces the final complete
            if data.get("type") == "error":
                # Enrich timeout errors with context
                content = data.get("content", "")
                if "timed out" in content.lower():
                    content += (
                        " The repository may have too many files for analysis. "
                        "Try pointing to a specific subdirectory (e.g., src/) instead of the repo root."
                    )
                    data["content"] = content
                    event = f"data: {json.dumps(data)}\n\n"
                yield event
                phase1_error = True
                break
        except (json.JSONDecodeError, ValueError):
            pass
        yield event

    if phase1_error:
        return

    # Retrieve the saved architecture_notes artifact
    architecture_notes = None
    if conversation_id:
        artifact = get_latest_artifact(conversation_id, content_type="repo-analysis/yaml")
        if not artifact:
            # Backwards compat: fall back to legacy JSON format
            artifact = get_latest_artifact(conversation_id, content_type="repo-analysis/json")
            if artifact:
                logger.info("repo_archimate: fell back to legacy JSON artifact for conversation %s", conversation_id)
        if artifact:
            architecture_notes = artifact["content"]

    if not architecture_notes:
        # Surface the agent's response if it contains useful error context
        detail = ""
        if phase1_response:
            detail = f" Agent response: {phase1_response[:300]}"
        yield f"data: {json.dumps({'type': 'error', 'content': f'Repository analysis did not produce architecture notes. The agent may have encountered an error during extraction.{detail}'})}\n\n"
        return

    # Phase transition indicator
    yield f"data: {json.dumps({'type': 'status', 'agent': AGENT_LABELS['repo_analysis_agent'], 'content': 'Analysis complete. Generating ArchiMate model...'})}\n\n"

    # Phase 2: Feed architecture_notes as source_text to generation pipeline
    async for event in stream_generation_response(
        question,
        skill_tags=["archimate"],
        conversation_id=conversation_id,
        source_text=architecture_notes,
    ):
        yield event


# ============== Test Mode: LLM Comparison Functions ==============

# Collection name mappings for each provider
COLLECTION_NAMES = {
    "ollama": {
        "adr": "ArchitecturalDecision",
        "principle": "Principle",
        "policy": "PolicyDocument",
        "vocabulary": "Vocabulary",
    },
    "openai": {
        "adr": "ArchitecturalDecision_OpenAI",
        "principle": "Principle_OpenAI",
        "policy": "PolicyDocument_OpenAI",
        "vocabulary": "Vocabulary_OpenAI",
    },
}


async def perform_retrieval(question: str, provider: str = "ollama") -> tuple[list[dict], str, int]:
    """Perform retrieval from Weaviate using provider-specific collections.

    Uses Weaviate native filters to exclude index and template documents.
    Relies on semantic search via embeddings rather than keyword-based routing.

    Args:
        question: The user's question
        provider: "ollama" for Nomic embeddings, "openai" for OpenAI embeddings

    Returns:
        Tuple of (retrieved objects, context string, retrieval time in ms)
    """
    global _weaviate_client

    retrieval_start = time.perf_counter()
    all_results = []

    # Get collection names for this provider
    collections = COLLECTION_NAMES.get(provider, COLLECTION_NAMES["ollama"])

    # Retrieval limits — read from thresholds.yaml at call time
    limits = _get_retrieval_limits()
    truncation = _get_truncation()
    adr_limit = limits.get("adr", 8)
    principle_limit = limits.get("principle", 6)
    policy_limit = limits.get("policy", 4)
    vocab_limit = limits.get("vocabulary", 4)
    content_max_chars = truncation.get("content_max_chars", 800)

    # For Ollama provider, compute query embedding client-side
    # WORKAROUND for Weaviate text2vec-ollama bug (#8406)
    query_vector = None
    if provider == "ollama":
        try:
            query_vector = embed_text(question)
        except Exception as e:
            logger.error(f"Failed to compute query embedding: {e}")

    # Weaviate filter to exclude index and template documents
    # Only retrieve actual content documents
    content_filter = Filter.by_property("doc_type").equal("content")

    # Search all document collections and let semantic search determine relevance
    # This is the industry-standard RAG approach: embeddings handle routing, not keywords

    # Search ADRs
    try:
        collection = _weaviate_client.collections.get(collections["adr"])
        results = collection.query.hybrid(
            query=question,
            vector=query_vector,
            limit=adr_limit,
            alpha=settings.alpha_default,  # Configurable in config.py
            filters=content_filter,
        )
        for obj in results.objects:
            content = obj.properties.get("full_text", "") or obj.properties.get("decision", "")
            all_results.append({
                "type": "ADR",
                "title": obj.properties.get("title", ""),
                "content": content[:content_max_chars],
                "doc_type": obj.properties.get("doc_type", ""),
            })
    except Exception as e:
        logger.warning(f"Error searching {collections['adr']}: {e}")

    # Search Principles
    try:
        collection = _weaviate_client.collections.get(collections["principle"])
        results = collection.query.hybrid(
            query=question,
            vector=query_vector,
            limit=principle_limit,
            alpha=settings.alpha_default,
            filters=content_filter,
        )
        for obj in results.objects:
            content = obj.properties.get("full_text", "") or obj.properties.get("content", "")
            all_results.append({
                "type": "Principle",
                "title": obj.properties.get("title", ""),
                "content": content[:content_max_chars],
                "doc_type": obj.properties.get("doc_type", ""),
            })
    except Exception as e:
        logger.warning(f"Error searching {collections['principle']}: {e}")

    # Search Policies
    try:
        collection = _weaviate_client.collections.get(collections["policy"])
        results = collection.query.hybrid(
            query=question,
            vector=query_vector,
            limit=policy_limit,
            alpha=settings.alpha_default,
        )
        for obj in results.objects:
            content = obj.properties.get("full_text", "") or obj.properties.get("content", "")
            all_results.append({
                "type": "Policy",
                "title": obj.properties.get("title", ""),
                "content": content[:content_max_chars],
            })
    except Exception as e:
        logger.warning(f"Error searching {collections['policy']}: {e}")

    # Search Vocabulary
    try:
        collection = _weaviate_client.collections.get(collections["vocabulary"])
        results = collection.query.hybrid(
            query=question,
            vector=query_vector,
            limit=vocab_limit,
            alpha=settings.alpha_vocabulary,  # Configurable in config.py
        )
        for obj in results.objects:
            all_results.append({
                "type": "Vocabulary",
                "label": obj.properties.get("pref_label", ""),
                "definition": obj.properties.get("definition", ""),
            })
    except Exception as e:
        logger.warning(f"Error searching {collections['vocabulary']}: {e}")

    # Build context from retrieved results
    # Sort by relevance (order returned from Weaviate hybrid search)
    context = "\n\n".join([
        f"[{r.get('type', 'Document')}] {r.get('title', r.get('label', 'Untitled'))}: {r.get('content', r.get('definition', ''))}"
        for r in all_results[:10]
    ])

    retrieval_time = elapsed_ms(retrieval_start)
    return all_results, context, retrieval_time



async def generate_with_ollama(system_prompt: str, user_prompt: str, model: str) -> tuple[str, dict]:
    """Generate response using Ollama API with timing.

    Returns:
        Tuple of (response text, timing dict)

    Raises:
        Exception: With actionable error message for timeout/connection issues
    """
    import httpx

    start_time = time.perf_counter()
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    try:
        async with httpx.AsyncClient(timeout=settings.timeout_long_running) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {"num_predict": 1000},
                },
            )
            response.raise_for_status()
            result = response.json()

            latency_ms = elapsed_ms(start_time)

            timing = {
                "latency_ms": latency_ms,
            }

            # Strip <think> tags from response
            response_text = strip_think_tags(result.get("response", ""))
            return response_text, timing

    except httpx.TimeoutException:
        latency_ms = elapsed_ms(start_time)
        raise Exception(
            f"Ollama generation timed out after {latency_ms}ms. "
            "Check Ollama settings or try a smaller context length."
        )

    except httpx.HTTPStatusError as e:
        latency_ms = elapsed_ms(start_time)
        raise Exception(f"Ollama HTTP error after {latency_ms}ms: {str(e)}")

    except Exception as e:
        latency_ms = elapsed_ms(start_time)
        raise Exception(f"Ollama error after {latency_ms}ms: {str(e)}")


async def generate_with_openai(system_prompt: str, user_prompt: str, model: str) -> tuple[str, dict]:
    """Generate response using OpenAI API with timing.

    Returns:
        Tuple of (response text, timing dict)
    """
    from openai import OpenAI

    start_time = time.perf_counter()

    try:
        openai_client = OpenAI(**settings.get_openai_client_kwargs(
            timeout=settings.timeout_long_running,
        ))

        token_limits = get_thresholds_value("get_llm_token_limits", {})
        completion_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if is_reasoning_model(model):
            completion_kwargs["max_completion_tokens"] = token_limits.get("direct_reasoning", 1000)
        else:
            completion_kwargs["max_tokens"] = token_limits.get("direct_standard", 1000)

        response = openai_client.chat.completions.create(**completion_kwargs)

        latency_ms = elapsed_ms(start_time)

        return response.choices[0].message.content, {"latency_ms": latency_ms}
    except Exception as e:
        latency_ms = elapsed_ms(start_time)
        raise Exception(f"OpenAI error after {latency_ms}ms: {str(e)}")


async def stream_comparison_response(
    question: str,
    ollama_model: str,
    openai_model: str
) -> AsyncGenerator[str, None]:
    """Stream comparison responses from both Ollama and OpenAI.

    Performs separate retrievals using provider-specific collections:
    - Ollama: Uses Nomic embeddings (local collections)
    - OpenAI: Uses OpenAI text-embedding-3-small (OpenAI collections)
    """
    logger.info(f"Starting comparison query: {question}")

    # Send initial status
    yield f"data: {json.dumps({'type': 'status', 'content': 'Retrieving context from both embedding systems...'})}\n\n"

    try:
        # Perform parallel retrievals from both collection sets
        async def retrieve_ollama():
            return await perform_retrieval(question, provider="ollama")

        async def retrieve_openai():
            return await perform_retrieval(question, provider="openai")

        # Run both retrievals in parallel
        ollama_retrieval_task = asyncio.create_task(retrieve_ollama())
        openai_retrieval_task = asyncio.create_task(retrieve_openai())

        ollama_results, ollama_context, ollama_retrieval_time = await ollama_retrieval_task
        openai_results, openai_context, openai_retrieval_time = await openai_retrieval_task

        logger.info(
            f"Retrieval complete - Ollama: {len(ollama_results)} results in {ollama_retrieval_time}ms, "
            f"OpenAI: {len(openai_results)} results in {openai_retrieval_time}ms"
        )
        yield f"data: {json.dumps({'type': 'status', 'content': f'Retrieved {len(ollama_results)} (local) + {len(openai_results)} (OpenAI) documents. Generating responses...'})}\n\n"

        # Build prompts with provider-specific contexts
        # OpenAI system prompt - standard RAG instruction
        openai_system_prompt = "You are a helpful assistant answering questions about architecture decisions, principles, policies, and vocabulary. Base your answers on the provided context. Be concise but thorough."

        # SmolLM3 system prompt - much more explicit instructions
        # Small models need very clear, direct instructions to follow RAG patterns
        ollama_system_prompt = """You are an assistant that ONLY answers based on the provided context.

IMPORTANT RULES:
1. ONLY use information from the context below to answer
2. If the context contains the answer, provide it directly with specific details
3. If the context does NOT contain the answer, say "I don't have information about that in the provided context"
4. Do NOT make up information or give general advice
5. Be concise and cite specific items from the context"""

        # Create tasks for both LLMs with their respective contexts
        async def get_ollama_response():
            try:
                # More structured prompt for SmolLM3
                user_prompt = f"""CONTEXT (use ONLY this information to answer):
{ollama_context}

USER QUESTION: {question}

Based on the context above, provide a direct answer:"""
                response, timing = await generate_with_ollama(ollama_system_prompt, user_prompt, ollama_model)
                timing["retrieval_ms"] = ollama_retrieval_time
                return ("ollama", response, timing, None, ollama_results)
            except Exception as e:
                return ("ollama", None, {"latency_ms": 0, "retrieval_ms": ollama_retrieval_time}, str(e), ollama_results)

        async def get_openai_response():
            try:
                user_prompt = f"Context:\n{openai_context}\n\nQuestion: {question}"
                response, timing = await generate_with_openai(openai_system_prompt, user_prompt, openai_model)
                timing["retrieval_ms"] = openai_retrieval_time
                return ("openai", response, timing, None, openai_results)
            except Exception as e:
                return ("openai", None, {"latency_ms": 0, "retrieval_ms": openai_retrieval_time}, str(e), openai_results)

        # Run both LLM calls in parallel
        tasks = [
            asyncio.create_task(get_ollama_response()),
            asyncio.create_task(get_openai_response()),
        ]

        # Store sources for each provider
        provider_sources = {}

        # Yield results as they complete
        for coro in asyncio.as_completed(tasks):
            provider, response, timing, error, results = await coro

            # Format sources for this provider
            sources = []
            for obj in results[:5]:
                source = {
                    "type": obj.get("type", "Document"),
                    "title": obj.get("title") or obj.get("label") or "Untitled",
                }
                content = obj.get("content") or obj.get("definition") or ""
                if content:
                    source["preview"] = content[:200] + "..." if len(content) > 200 else content
                sources.append(source)

            provider_sources[provider] = sources

            if error:
                yield f"data: {json.dumps({'type': 'error', 'provider': provider, 'content': error, 'timing': timing, 'sources': sources})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'assistant', 'provider': provider, 'content': response, 'timing': timing, 'sources': sources})}\n\n"

        # Send complete event with both source sets
        yield f"data: {json.dumps({'type': 'complete', 'ollama_sources': provider_sources.get('ollama', []), 'openai_sources': provider_sources.get('openai', [])})}\n\n"

    except Exception as e:
        logger.exception("Comparison query error")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


# API endpoints
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the chat UI."""
    static_dir = Path(__file__).parent / "static"
    index_path = static_dir / "index.html"

    if index_path.exists():
        return FileResponse(index_path)
    else:
        return HTMLResponse("<h1>AInstein</h1><p>Static files not found.</p>")


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream chat response with thinking process via SSE."""
    global _rag_agent, _persona

    if not _rag_agent:
        raise HTTPException(status_code=503, detail="System not initialized")

    # Create or use existing conversation
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = create_conversation()

    # Ensure a session record exists for this conversation
    create_session(conversation_id)

    # Save user message
    save_message(conversation_id, "user", request.message)

    # Update conversation title from first message
    messages = get_conversation_messages(conversation_id)
    if len(messages) == 1:
        title = request.message[:50] + "..." if len(request.message) > 50 else request.message
        update_conversation_title(conversation_id, title)

    async def event_generator():
        # Initialize before try/finally so the finally block can reference them on early failures
        request_id = str(uuid.uuid4())[:12]
        request_start = time.perf_counter()
        persona_result = None
        execution_model = None
        final_response = None  # also initialized below with full set, but needed here for finally

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            conversation_id=conversation_id,
        )

        try:
            # Send conversation ID first
            yield f"data: {json.dumps({'type': 'init', 'conversation_id': conversation_id, 'request_id': request_id})}\n\n"

            # Show immediate feedback while Persona classifies intent
            pixel_registry.tool_call("persona", "Classifying...", "Classifying your request...")
            yield f"data: {json.dumps({'type': 'status', 'agent': AGENT_LABELS['persona'], 'content': 'Classifying your request...'})}\n\n"

            # Run Persona intent classification and query rewriting
            try:
                persona_result = await _persona.process(
                    request.message, messages, conversation_id=conversation_id,
                )
            except PermanentLLMError as e:
                logger.error(
                    "request_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    total_ms=elapsed_ms(request_start),
                )
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                return  # finally block handles clear_contextvars

            has_user_content = _has_user_content(request.message, persona_result.rewritten_query)

            # Emit Persona classification result with latency
            persona_event = {
                "type": "persona_intent",
                "agent": AGENT_LABELS["persona"],
                "content": f"Classified as {persona_result.intent}",
                "intent": persona_result.intent,
                "rewritten_query": persona_result.rewritten_query,
                "skill_tags": persona_result.skill_tags,
                "doc_refs": persona_result.doc_refs,
                "github_refs": persona_result.github_refs,
                "latency_ms": persona_result.latency_ms,
            }
            yield f"data: {json.dumps(persona_event)}\n\n"

            # Direct response intents: respond immediately, no Tree needed
            if persona_result.direct_response is not None:
                # Speech bubble for direct-response intents
                # "identity" covers both greetings ("hi") and actual identity
                # questions ("who are you?") — check the query to disambiguate.
                _query_lower = (persona_result.rewritten_query or request.message).lower()
                _is_identity_question = any(w in _query_lower for w in ("who", "what are you", "your name"))
                _is_how_are_you = any(w in _query_lower for w in ("how are you", "how's it going", "how do you do"))
                _speech = {
                    "off_topic": "Not my area...",
                    "clarification": "What do you mean?",
                    "conversational": "Let me think...",
                }.get(persona_result.intent,
                      "I'm AInstein!" if _is_identity_question
                      else "Doing well!" if _is_how_are_you
                      else "Hi!")
                # Speech overlays on top of the classify_intent tool box
                # for greetings and identity questions only
                if persona_result.intent in ("identity", "conversational"):
                    pixel_registry.speech("persona", _speech, 2.5)
                timing = {"total_ms": elapsed_ms(request_start), "persona_ms": persona_result.latency_ms}
                yield f"data: {json.dumps({'type': 'complete', 'response': persona_result.direct_response, 'sources': [], 'timing': timing, 'path': 'direct', 'request_id': request_id})}\n\n"
                pixel_registry.idle("persona")
                save_message(
                    conversation_id, "assistant",
                    persona_result.direct_response, [], timing,
                    turn_summary=f"Direct response ({persona_result.intent})",
                )
                await _maybe_update_summary(conversation_id)
                final_response = persona_result.direct_response
                return

            # Route to the appropriate execution path based on intent.
            # Intent is the sole gate: "generation" and "refinement" (with
            # generation skill_tags) go to the direct pipeline. Everything
            # else goes to the Tree.
            execution_model = _get_execution_model(
                persona_result.intent, persona_result.skill_tags,
            )
            logger.info(
                "route_selected",
                execution_model=execution_model.value,
                intent=persona_result.intent,
                complexity=persona_result.complexity,
                has_steps=bool(persona_result.steps),
                steps_count=len(persona_result.steps),
            )

            # Build artifact context for follow-ups that reference a prior model.
            # Threaded into RAGAgent.query() where it's part of the system prompt
            # AFTER skill content injection (which does a hard overwrite).
            artifact_context = None
            if execution_model in ("tree", "archimate", "principle") and conversation_id:
                artifact = get_latest_artifact(conversation_id)
                artifact_age = 999  # default: treat as stale
                if artifact:
                    # Compute recency: how many messages since this artifact was created
                    artifact_turn = artifact.get("turn", 0)
                    conn = _get_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                            (conversation_id,),
                        )
                        current_turn = cur.fetchone()[0]
                    finally:
                        conn.close()
                    artifact_age = current_turn - artifact_turn
                if artifact and _query_references_artifact(
                    persona_result.rewritten_query or request.message,
                    persona_result.intent,
                    artifact,
                    artifact_age=artifact_age,
                ):
                    from aion.tools.yaml_to_xml import xml_to_yaml
                    content = artifact["content"]
                    if artifact["content_type"] == "archimate/xml":
                        try:
                            content = xml_to_yaml(content)
                        except ValueError:
                            pass
                    artifact_context = (
                        f"\n\n## LOADED ARTIFACT: {artifact.get('filename', 'model')}\n"
                        f"The user previously uploaded or generated this model. "
                        f"Use it as context when answering.\n\n"
                        f"```\n{content}\n```\n"
                    )
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Loading model into context...'})}\n\n"

            final_response = None
            final_sources = []
            final_timing = None
            thinking_steps = []
            artifact_ids = []

            thinking_types = {"status", "decision", "assistant", "thinking_aloud", "persona_intent"}

            # Map execution models to pixel agent characters
            exec_to_pixel = {
                ExecutionModel.TREE: "rag_agent",
                ExecutionModel.GENERATION: "archimate_agent",
                ExecutionModel.INSPECT: "archimate_agent",
                ExecutionModel.REPO_ANALYSIS: "repo_analysis_agent",
                ExecutionModel.VOCABULARY: "vocabulary_agent",
                ExecutionModel.ARCHIMATE: "archimate_agent",
                ExecutionModel.PRINCIPLE: "principle_agent",
                ExecutionModel.REFINEMENT: "archimate_agent",
            }
            # Track which pixel agent is active — derived from execution model.
            current_pixel_agent = exec_to_pixel.get(execution_model, "rag_agent")

            def _capture_event(event):
                """Extract persistent data from an SSE event and forward to Pixel Agents."""
                nonlocal final_response, final_sources, final_timing, current_pixel_agent
                try:
                    data = json.loads(event.replace("data: ", "").strip())
                    evt_type = data.get("type")

                    if evt_type == "complete":
                        final_response = data.get("response")
                        final_sources = data.get("sources", [])
                        final_timing = data.get("timing")
                        # Show a speech bubble on the agent that produced the answer
                        if final_response:
                            snippet = final_response[:80].split("\n")[0]
                            if len(final_response) > 80:
                                snippet += "..."
                            pixel_registry.speech(current_pixel_agent, snippet, 3.0)
                        # All agents go idle on completion
                        for agent_key in exec_to_pixel.values():
                            pixel_registry.idle(agent_key)
                        pixel_registry.idle("persona")
                        pixel_registry.idle("orchestrator")
                    elif evt_type == "status":
                        content = data.get("content", "")
                        agent = data.get("agent", "")
                        thinking_steps.append({"text": content, "type": evt_type, "agent": agent})
                        # Phase transition: repo analysis → ArchiMate generation
                        # Switch pixel agent so Phase 2 events animate the ArchiMate character
                        if (agent == AGENT_LABELS.get("repo_analysis_agent") and
                                "Generating ArchiMate" in content):
                            pixel_registry.idle("repo_analysis_agent")
                            current_pixel_agent = "archimate_agent"
                            pixel_registry.speech("archimate_agent", "Generating model!", 2.5)
                        # Route pixel agent animations with human-readable labels
                        if agent == AGENT_LABELS["persona"]:
                            pixel_registry.tool_call("persona", "Classifying...", content)
                        elif agent == AGENT_LABELS["orchestrator"]:
                            pixel_registry.tool_call("orchestrator", "Orchestrating...", content)
                            pixel_registry.tool_call(current_pixel_agent, "Assigning...", content)
                        elif agent == AGENT_LABELS["synthesis"]:
                            pixel_registry.tool_call(current_pixel_agent, "Synthesizing...", content)
                        elif content.startswith("Found "):
                            pixel_registry.tool_result(current_pixel_agent, content)
                        else:
                            pixel_registry.tool_call(current_pixel_agent, "Searching...", content)
                    elif evt_type == "decision":
                        content = data.get("content", "")
                        agent = data.get("agent", "")
                        thinking_steps.append({"text": content, "type": evt_type, "agent": agent})
                        # decision content is now human-readable (rewritten by emit_event)
                        raw_tool = data.get("tool", content.split(" ")[0] if content else "unknown")
                        # Map raw tool names to human-readable labels
                        tool_labels = {
                            # RAG agent
                            "search_principles": "Searching principles...",
                            "search_architecture_decisions": "Searching ADRs...",
                            "search_policies": "Searching policies...",
                            "list_principles": "Listing principles...",
                            "list_adrs": "Listing ADRs...",
                            "list_policies": "Listing policies...",
                            "list_dars": "Listing approval records...",
                            "search_by_team": "Searching by team...",
                            # Principle agent
                            "search_related_principles": "Finding related...",
                            "get_principle": "Reading principle...",
                            "validate_principle_structure": "Validating...",
                            "save_principle": "Saving principle...",
                            # Vocabulary agent
                            "skosmos_search": "Searching vocabulary...",
                            "skosmos_concept_details": "Reading concept...",
                            "skosmos_list_vocabularies": "Listing vocabularies...",
                            "search_knowledge_base": "Searching KB...",
                            # Repo analysis agent
                            "clone_repo": "Cloning repository...",
                            "profile_repo": "Profiling structure...",
                            "extract_manifests": "Extracting manifests...",
                            "extract_code_structure": "Analyzing code...",
                            "build_dep_graph": "Building dependencies...",
                            "merge_and_save_notes": "Saving analysis...",
                            # ArchiMate agent
                            "validate_archimate": "Validating model...",
                            "inspect_archimate_model": "Inspecting model...",
                            "merge_archimate_view": "Merging view...",
                            "save_artifact": "Saving artifact...",
                            "get_artifact": "Loading artifact...",
                            # Shared
                            "request_data": "Requesting data...",
                        }
                        tool_label = tool_labels.get(raw_tool, f"{raw_tool}...")
                        pixel_registry.tool_call(current_pixel_agent, tool_label, content)
                    elif evt_type == "persona_intent":
                        agent = data.get("agent", AGENT_LABELS["persona"])
                        thinking_steps.append({"text": data.get("content", ""), "type": evt_type, "agent": agent})
                        # Complete the classify_intent tool and hand off to the agent.
                        pixel_registry.tool_result("persona", f"Intent: {data.get('intent', 'unknown')}")
                        pixel_registry.idle("persona")
                        if execution_model:
                            pixel_registry.speech(current_pixel_agent, "Working on it!", 2.5)
                            pixel_registry.tool_call(current_pixel_agent, "Processing...", f"Handling {data.get('intent', 'query')}...")
                    elif evt_type in thinking_types:
                        thinking_steps.append({"text": data.get("content", ""), "type": evt_type, "agent": data.get("agent", "")})
                    elif evt_type == "artifact":
                        aid = data.get("artifact_id")
                        if aid:
                            artifact_ids.append(aid)
                        yaml_aid = data.get("yaml_companion_id")
                        if yaml_aid:
                            artifact_ids.append(yaml_aid)
                        pixel_registry.tool_call("archimate_agent", "Generating model...",
                                                 data.get("filename", "artifact"))
                    elif evt_type == "error":
                        for agent_key in exec_to_pixel.values():
                            pixel_registry.idle(agent_key)
                        pixel_registry.idle("persona")
                        pixel_registry.idle("orchestrator")
                except (json.JSONDecodeError, ValueError):
                    pass

            if execution_model == ExecutionModel.GENERATION:
                async for event in stream_generation_response(
                    persona_result.rewritten_query,
                    skill_tags=persona_result.skill_tags,
                    doc_refs=persona_result.doc_refs,
                    github_refs=persona_result.github_refs,
                    conversation_id=conversation_id,
                    intent=persona_result.intent,
                ):
                    yield event
                    _capture_event(event)
            elif execution_model == ExecutionModel.INSPECT:
                async for event in stream_inspect_response(
                    persona_result.rewritten_query,
                    conversation_id=conversation_id,
                ):
                    yield event
                    _capture_event(event)
            elif execution_model == ExecutionModel.VOCABULARY:
                async for event in stream_vocabulary_response(
                    persona_result.rewritten_query,
                    skill_tags=persona_result.skill_tags,
                    doc_refs=persona_result.doc_refs,
                    conversation_id=conversation_id,
                ):
                    yield event
                    _capture_event(event)
            elif execution_model == ExecutionModel.ARCHIMATE:
                async for event in stream_archimate_response(
                    persona_result.rewritten_query,
                    skill_tags=persona_result.skill_tags,
                    doc_refs=persona_result.doc_refs,
                    conversation_id=conversation_id,
                    artifact_context=artifact_context,
                ):
                    yield event
                    _capture_event(event)
            elif execution_model == ExecutionModel.PRINCIPLE:
                async for event in stream_principle_response(
                    persona_result.rewritten_query,
                    skill_tags=persona_result.skill_tags,
                    doc_refs=persona_result.doc_refs,
                    conversation_id=conversation_id,
                    artifact_context=artifact_context,
                ):
                    yield event
                    _capture_event(event)
            elif execution_model == ExecutionModel.REPO_ANALYSIS:
                async for event in stream_repo_archimate_response(
                    persona_result.rewritten_query,
                    skill_tags=persona_result.skill_tags,
                    conversation_id=conversation_id,
                ):
                    yield event
                    _capture_event(event)
            else:
                # --- RAG execution path ---
                if persona_result.complexity == "multi-step" and persona_result.steps:
                    # Phase 2: orchestrated multi-step execution — each step is a separate
                    # RAG call; results are labeled and combined before synthesis.
                    orchestrator = MultiStepOrchestrator()
                    async for event in orchestrator.run(
                        persona_result,
                        request.message,
                        conversation_id,
                        artifact_context,
                    ):
                        yield event
                        _capture_event(event)
                else:
                    # Phase 1: single RAG + optional synthesis (steps == [])
                    # Hold the complete event so synthesis can replace it if needed.
                    # All other events are streamed to the client immediately.
                    _pending_complete: str | None = None
                    async for event in stream_rag_response(
                        persona_result.rewritten_query,
                        skill_tags=persona_result.skill_tags,
                        doc_refs=persona_result.doc_refs,
                        conversation_id=conversation_id,
                        artifact_context=artifact_context,
                        complexity=persona_result.complexity,
                    ):
                        try:
                            evt_data = json.loads(event.replace("data: ", "").strip())
                            if evt_data.get("type") == "complete":
                                _pending_complete = event
                                # Capture now (before yield) to populate final_response,
                                # which the synthesis condition check needs on the next line.
                                # If synthesis fires, _capture_event on its complete overwrites this.
                                _capture_event(event)
                                continue  # don't yield yet — synthesis may replace it
                        except Exception:
                            pass
                        yield event
                        _capture_event(event)

                    # Post-RAG synthesis: when Persona identified a multi-step query and
                    # the user's message contains pasted content, run a second LLM pass
                    # that receives the original message (paste intact) + KB results.
                    # synthesis_instruction defaults inside stream_synthesis_response() if None.
                    will_synthesize = (
                        persona_result.complexity == "multi-step" and has_user_content and bool(final_response)
                    )
                    logger.info(
                        "synthesis_gate",
                        triggered=will_synthesize,
                        complexity=persona_result.complexity,
                        message_len=len(request.message),
                        rewritten_len=len(persona_result.rewritten_query or ""),
                    )
                    if will_synthesize:
                        yield f"data: {json.dumps({'type': 'status', 'agent': AGENT_LABELS['synthesis'], 'content': 'Comparing your content against retrieved results...'})}\n\n"
                        accumulated: list[str] = []
                        async for chunk in stream_synthesis_response(
                            request.message, final_response, persona_result.synthesis_instruction
                        ):
                            accumulated.append(chunk)
                            yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                        synthesis_text = "".join(accumulated)
                        if synthesis_text:
                            final_response = synthesis_text
                            synthesis_event = json.dumps({
                                "type": "complete",
                                "response": synthesis_text,
                                "sources": final_sources,
                                "timing": final_timing,
                                "path": "phase1_synthesis",
                                "request_id": request_id,
                            })
                            yield f"data: {synthesis_event}\n\n"
                            _capture_event(f"data: {synthesis_event}\n\n")
                        elif _pending_complete:
                            # Synthesis produced no text — fall back to the RAG complete
                            yield _pending_complete
                    elif _pending_complete:
                        # No synthesis triggered — emit the RAG complete event
                        yield _pending_complete

            # Save assistant response with structured turn summary
            if final_response:
                if execution_model == ExecutionModel.REPO_ANALYSIS:
                    # Deterministic summary preserving repo name for follow-up context.
                    # Avoids LLM summarization which drops the repo identity.
                    repo_artifact = get_latest_artifact(conversation_id, content_type="repo-analysis/yaml")
                    if not repo_artifact:
                        repo_artifact = get_latest_artifact(conversation_id, content_type="repo-analysis/json")
                    repo_summary = repo_artifact.get("summary", "") if repo_artifact else ""
                    turn_summary = (
                        f"Generated ArchiMate model. {repo_summary} "
                        f"{final_response[:200]}"
                    ).strip()
                else:
                    turn_summary = await _build_turn_summary(final_response, final_sources)
                save_message(
                    conversation_id, "assistant",
                    final_response, final_sources, final_timing,
                    turn_summary=turn_summary,
                    thinking_steps=thinking_steps or None,
                    artifact_ids=artifact_ids or None,
                )
                await _maybe_update_summary(conversation_id)

        finally:
            logger.info(
                "request_complete",
                intent=persona_result.intent if persona_result else None,
                execution_model=execution_model.value if execution_model else None,
                complexity=getattr(persona_result, "complexity", None),
                total_ms=elapsed_ms(request_start),
                persona_ms=getattr(persona_result, "latency_ms", None),
                response_chars=len(final_response) if final_response else 0,
                steps_executed=(
                    len(persona_result.steps)
                    if persona_result and persona_result.steps else 0
                ),
            )
            structlog.contextvars.clear_contextvars()
            pixel_registry.idle_all()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/api/chat/stream/compare")
async def chat_stream_compare(request: ComparisonRequest):
    """Stream comparison responses from both Ollama and OpenAI (Test Mode).

    This endpoint performs a single retrieval and sends the context to both
    LLMs in parallel, streaming the results as they complete.
    """
    global _weaviate_client

    if not _weaviate_client:
        raise HTTPException(status_code=503, detail="System not initialized")

    # Check OpenAI API key
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key not configured. Set OPENAI_API_KEY in .env file."
        )

    # Create or use existing conversation
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = create_conversation()

    # Save user message (in test mode, we save the question but not responses)
    save_message(conversation_id, "user", f"[Test Mode] {request.message}")

    async def comparison_generator():
        # Send conversation ID first
        yield f"data: {json.dumps({'type': 'init', 'conversation_id': conversation_id})}\n\n"

        # Stream comparison responses
        async for event in stream_comparison_response(
            request.message,
            request.ollama_model,
            request.openai_model
        ):
            yield event

    return StreamingResponse(
        comparison_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a chat message (non-streaming fallback)."""
    global _rag_agent, _persona

    if not _rag_agent:
        raise HTTPException(status_code=503, detail="System not initialized")

    # Create or use existing conversation
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = create_conversation()

    # Ensure a session record exists for this conversation
    create_session(conversation_id)

    # Save user message
    save_message(conversation_id, "user", request.message)

    # Update conversation title from first message
    messages = get_conversation_messages(conversation_id)
    if len(messages) == 1:
        title = request.message[:50] + "..." if len(request.message) > 50 else request.message
        update_conversation_title(conversation_id, title)

    # Run Persona intent classification
    try:
        persona_result = await _persona.process(
            request.message, messages, conversation_id=conversation_id,
        )
    except PermanentLLMError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Direct response intents: respond immediately, no Tree needed
    if persona_result.direct_response is not None:
        save_message(
            conversation_id, "assistant",
            persona_result.direct_response, [],
            turn_summary=f"Direct response ({persona_result.intent})",
        )
        await _maybe_update_summary(conversation_id)
        return ChatResponse(
            response=persona_result.direct_response,
            sources=[],
            conversation_id=conversation_id,
        )

    try:
        # Route to the appropriate agent
        execution_model = _get_execution_model(
            persona_result.intent, persona_result.skill_tags,
        )

        # Load artifact context for archimate refinements
        artifact_context = None
        if execution_model == ExecutionModel.ARCHIMATE and conversation_id:
            artifact = get_latest_artifact(conversation_id)
            if artifact:
                from aion.tools.yaml_to_xml import xml_to_yaml
                content = artifact["content"]
                if artifact["content_type"] == "archimate/xml":
                    try:
                        content = xml_to_yaml(content)
                    except ValueError:
                        pass
                artifact_context = (
                    f"\n\n## LOADED ARTIFACT: {artifact.get('filename', 'model')}\n"
                    f"The user previously uploaded or generated this model. "
                    f"Use it as context when answering.\n\n"
                    f"```\n{content}\n```\n"
                )

        if execution_model == ExecutionModel.VOCABULARY:
            response, objects = await _vocabulary_agent.query(
                persona_result.rewritten_query,
                skill_tags=persona_result.skill_tags,
                doc_refs=persona_result.doc_refs,
                conversation_id=conversation_id,
            )
        elif execution_model == ExecutionModel.ARCHIMATE:
            response, objects = await _archimate_agent.query(
                persona_result.rewritten_query,
                skill_tags=persona_result.skill_tags,
                doc_refs=persona_result.doc_refs,
                conversation_id=conversation_id,
                artifact_context=artifact_context,
            )
        elif execution_model == ExecutionModel.PRINCIPLE:
            response, objects = await _principle_agent.query(
                persona_result.rewritten_query,
                skill_tags=persona_result.skill_tags,
                doc_refs=persona_result.doc_refs,
                conversation_id=conversation_id,
                artifact_context=artifact_context,
            )
        else:
            response, objects = await _rag_agent.query(
                persona_result.rewritten_query,
                skill_tags=persona_result.skill_tags,
                doc_refs=persona_result.doc_refs,
                conversation_id=conversation_id,
            )

        sources = _extract_sources(objects or [])

        # Save assistant response with turn summary
        turn_summary = await _build_turn_summary(response, sources)
        save_message(conversation_id, "assistant", response, sources, turn_summary=turn_summary)
        await _maybe_update_summary(conversation_id)

        return ChatResponse(
            response=response,
            sources=sources,
            conversation_id=conversation_id,
        )

    except Exception as e:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversations")
async def list_conversations():
    """List all conversations."""
    return get_all_conversations()


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a specific conversation with messages."""
    messages = get_conversation_messages(conversation_id)
    conversations = get_all_conversations()

    conv = next((c for c in conversations if c["id"] == conversation_id), None)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Resolve artifact IDs to full metadata for each message
    for msg in messages:
        if msg.get("artifact_ids"):
            msg["artifacts"] = get_artifacts_by_ids(msg["artifact_ids"])
        else:
            msg["artifacts"] = []

    return {
        "id": conversation_id,
        "title": conv["title"],
        "messages": messages,
    }


@app.delete("/api/conversations/{conversation_id}")
async def remove_conversation(conversation_id: str):
    """Delete a conversation."""
    delete_conversation(conversation_id)
    return {"status": "deleted"}


@app.delete("/api/conversations")
async def remove_all_conversations():
    """Delete all conversations."""
    delete_all_conversations()
    return {"status": "all_deleted"}


@app.get("/api/artifact/{artifact_id}/download")
async def download_artifact(artifact_id: str):
    """Download an artifact by ID as a file."""
    from fastapi.responses import Response

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT filename, content, content_type FROM artifacts WHERE id = ?",
            (artifact_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return {"error": "Artifact not found"}

    filename, content, content_type = row

    # Map custom MIME types to standard ones for download
    mime = "application/xml" if content_type == "archimate/xml" else "text/plain"

    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/chat/upload")
async def upload_file(request: Request):
    """Upload an ArchiMate model file (.xml, .yaml, .yml) for inspection.

    Accepts multipart form data with 'file' and optional 'conversation_id'.
    Validates the file based on extension: XML via xml_to_yaml(), YAML via
    _parse_and_validate(). Stores as artifact and returns metadata.
    """
    from aion.tools.yaml_to_xml import _parse_and_validate, xml_to_yaml

    form = await request.form()
    file = form.get("file")
    conversation_id = form.get("conversation_id")

    if not file or not hasattr(file, "filename"):
        raise HTTPException(status_code=400, detail="No file uploaded")

    filename = file.filename or "uploaded-model.xml"
    content = (await file.read()).decode("utf-8")
    await file.close()

    if filename.endswith((".yaml", ".yml")):
        try:
            _parse_and_validate(content)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid ArchiMate YAML: {e}",
            )
        content_type = "text/yaml"
    elif filename.endswith(".xml"):
        try:
            xml_to_yaml(content)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid ArchiMate XML: {e}",
            )
        content_type = "archimate/xml"
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload .xml, .yaml, or .yml",
        )

    if not conversation_id:
        conversation_id = create_conversation(f"Inspection: {filename}")

    artifact_id = save_artifact(
        conversation_id, filename, content, content_type,
        summary=f"Uploaded file: {filename}",
    )

    logger.info(f"Upload: {filename} ({content_type}) → artifact {artifact_id}")

    return {
        "conversation_id": conversation_id,
        "artifact_id": artifact_id,
        "filename": filename,
    }


@app.get("/health")
async def health():
    """Health check endpoint for service monitoring."""
    return {"status": "ok"}


@app.get("/api/status")
async def status():
    """Get system status including embedding service health."""
    embedding_ok = False
    embedding_provider = settings.effective_embedding_provider
    embedding_model = settings.embedding_model
    try:
        if embedding_provider == "ollama":
            import httpx
            httpx.get(
                f"{settings.ollama_url}/api/tags",
                timeout=settings.timeout_health_check,
            ).raise_for_status()
            embedding_ok = True
        else:
            # OpenAI embeddings — assume reachable if key is set
            embedding_ok = bool(settings.openai_api_key)
    except Exception:
        embedding_ok = False

    return {
        "status": "ok",
        "weaviate_connected": _weaviate_client is not None,
        "rag_agent_available": _rag_agent is not None,
        "vocabulary_agent_available": _vocabulary_agent is not None,
        "archimate_agent_available": _archimate_agent is not None,
        "embedding": {
            "provider": embedding_provider,
            "model": embedding_model,
            "reachable": embedding_ok,
        },
    }


# LLM Settings endpoints
@app.get("/api/settings/llm")
async def get_llm_settings():
    """Get current LLM settings and available models."""
    global _current_llm_settings
    return {
        "current": {
            "provider": _current_llm_settings.provider,
            "model": _current_llm_settings.model,
            "persona": {
                "provider": settings.effective_persona_provider,
                "model": settings.effective_persona_model,
            },
            "rag": {
                "provider": settings.effective_rag_provider,
                "model": settings.effective_rag_model,
            },
        },
        "available_providers": ["ollama", "github_models", "openai"],
        "available_models": AVAILABLE_MODELS,
    }


@app.post("/api/settings/llm")
async def set_llm_settings(llm_settings: LLMSettings):
    """Update LLM settings."""
    global _current_llm_settings

    # Validate provider
    valid_providers = ["ollama", "github_models", "openai"]
    if llm_settings.provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Invalid provider. Must be one of: {valid_providers}")

    # Update settings
    _current_llm_settings = llm_settings

    # Pin embedding provider before changing llm_provider. Weaviate vectors were
    # indexed with a specific embedding model — switching LLM provider must not
    # silently change the embedding model (causes dimension mismatch → zero results).
    # To intentionally switch embeddings, set EMBEDDING_PROVIDER in .env and re-ingest.
    if settings.embedding_provider is None:
        settings.embedding_provider = settings.effective_embedding_provider

    # Update global config settings — store model in the correct provider slot
    settings.llm_provider = llm_settings.provider
    if llm_settings.provider == "ollama":
        settings.ollama_model = llm_settings.model
    elif llm_settings.provider == "github_models":
        settings.github_models_model = llm_settings.model
    else:
        settings.openai_chat_model = llm_settings.model

    # Per-component overrides
    settings.persona_provider = llm_settings.persona_provider
    settings.persona_model = llm_settings.persona_model
    settings.rag_provider = llm_settings.rag_provider
    settings.rag_model = llm_settings.rag_model

    # Persist so settings survive server restarts
    from aion.config import _PERSISTABLE_FIELDS, _save_user_settings
    _save_user_settings({
        f: getattr(settings, f) for f in _PERSISTABLE_FIELDS
        if getattr(settings, f) is not None
    })

    logger.info(
        f"LLM settings updated: provider={llm_settings.provider}, "
        f"model={llm_settings.model}, "
        f"persona={settings.effective_persona_provider}/{settings.effective_persona_model}, "
        f"tree={settings.effective_rag_provider}/{settings.effective_rag_model}"
    )

    return {
        "status": "updated",
        "provider": llm_settings.provider,
        "model": llm_settings.model,
        "persona": {
            "provider": settings.effective_persona_provider,
            "model": settings.effective_persona_model,
        },
        "rag": {
            "provider": settings.effective_rag_provider,
            "model": settings.effective_rag_model,
        },
    }


@app.post("/api/settings/llm/add-model")
async def add_ollama_model(model_id: str):
    """Add a new Ollama model to the available models list."""
    # Check if model is already in the list
    for model in AVAILABLE_MODELS["ollama"]:
        if model["id"] == model_id:
            return {"status": "already_exists", "model": model}

    # Add new model
    new_model = {"id": model_id, "name": model_id}
    AVAILABLE_MODELS["ollama"].append(new_model)

    logger.info(f"Added new Ollama model: {model_id}")
    return {"status": "added", "model": new_model}


# ============================================================================
# Skills Management API
# ============================================================================


@app.get("/api/skills/defaults")
async def get_skill_defaults():
    """Get default configuration values for skills."""
    try:
        return skills_api.get_defaults()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/skills")
async def list_skills():
    """List all registered skills and groups."""
    try:
        return {
            "skills": skills_api.list_skills(),
            "groups": skills_api.list_groups(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/skills/groups")
async def list_groups():
    """List all registered skill groups."""
    try:
        return {"groups": skills_api.list_groups()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/skills/groups/{group_name}/enabled")
async def toggle_group(group_name: str, request: ToggleRequest):
    """Toggle group enabled/disabled status."""
    try:
        return skills_api.toggle_group_enabled(group_name, request.enabled)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/skills/{skill_name}")
async def get_skill(skill_name: str):
    """Get detailed information about a specific skill."""
    try:
        return skills_api.get_skill(skill_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/skills/{skill_name}/enabled")
async def toggle_skill(skill_name: str, request: ToggleRequest):
    """Toggle skill enabled/disabled status."""
    try:
        return skills_api.toggle_skill_enabled(skill_name, request.enabled)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/skills/{skill_name}/thresholds")
async def get_skill_thresholds(skill_name: str):
    """Get thresholds for a specific skill."""
    try:
        return {"thresholds": skills_api.get_thresholds(skill_name)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/skills/{skill_name}/thresholds")
async def update_skill_thresholds(skill_name: str, request: ThresholdsUpdate):
    """Update thresholds for a specific skill."""
    try:
        return skills_api.update_thresholds(skill_name, request.thresholds)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/skills/{skill_name}/content")
async def get_skill_content(skill_name: str):
    """Get SKILL.md content for a specific skill."""
    try:
        return skills_api.get_skill_content(skill_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/skills/{skill_name}/content")
async def update_skill_content(skill_name: str, request: SkillContentUpdate):
    """Update SKILL.md content for a specific skill."""
    try:
        return skills_api.update_skill_content(
            skill_name,
            content=request.content,
            metadata=request.metadata,
            body=request.body,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/skills/reload")
async def reload_skills():
    """Reload all skills from disk."""
    try:
        return skills_api.reload_skills()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Memory management API endpoints
# ============================================================================


@app.get("/api/memory")
async def memory_show():
    """Get current memory state: sessions, profile, message count."""
    from aion.memory.session_store import get_user_profile as _get_profile

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT session_id, conversation_id, started_at, ended_at, "
            "running_summary FROM sessions ORDER BY started_at DESC"
        )
        sessions = [
            {
                "session_id": r[0], "conversation_id": r[1],
                "started_at": r[2], "ended_at": r[3],
                "running_summary": r[4] or "",
            }
            for r in cursor.fetchall()
        ]

        cursor.execute("SELECT COUNT(*) FROM messages")
        message_count = cursor.fetchone()[0]
    finally:
        conn.close()

    return {
        "sessions": sessions,
        "user_profile": _get_profile(db_path=_db_path),
        "message_count": message_count,
    }


@app.delete("/api/memory/sessions")
async def memory_reset_sessions():
    """Clear all sessions and running summaries. Messages are preserved."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions")
        count = cursor.rowcount
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "deleted_sessions": count}


@app.delete("/api/memory/profile")
async def memory_reset_profile():
    """Delete all user profiles."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_profiles")
        count = cursor.rowcount
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "deleted_profiles": count}


@app.get("/api/memory/session/{conversation_id}")
async def memory_get_session(conversation_id: str):
    """Get the running summary for a specific conversation."""
    summary = get_running_summary(conversation_id)
    return {"conversation_id": conversation_id, "running_summary": summary}


@app.get("/skills", response_class=HTMLResponse)
async def skills_page():
    """Serve the Skills Management UI."""
    static_dir = Path(__file__).parent / "static"
    skills_path = static_dir / "skills.html"
    if skills_path.exists():
        return FileResponse(skills_path)
    return HTMLResponse("<h1>Skills UI not found</h1>")


# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def run_server(host: str = "127.0.0.1", port: int = settings.server_port):
    """Run the chat server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port, loop="asyncio")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8085)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
