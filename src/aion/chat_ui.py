"""Simple chat UI server for AION knowledge assistant.

A clean, local chat interface that wraps the ElysiaRAGSystem.
Streams the full Elysia thinking process to the UI.
"""

import asyncio
import io
import json
import logging
import re
import sqlite3
import sys
import time
import uuid
from contextlib import asynccontextmanager, redirect_stdout, redirect_stderr
from datetime import datetime
from pathlib import Path
from typing import Optional, AsyncGenerator
from threading import Thread
from queue import Queue, Empty

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from weaviate.classes.query import Filter

from src.aion.config import settings
from src.aion.memory.session_store import (
    init_memory_tables, create_session, get_running_summary,
    update_running_summary,
)
from src.aion.memory.summarizer import generate_rolling_summary, SUMMARIZE_TRIGGER_COUNT
from src.aion.persona import Persona, PermanentLLMError
from src.aion.skills import api as skills_api
from src.aion.weaviate.client import get_weaviate_client
from src.aion.weaviate.embeddings import embed_text, close_embeddings_client
from src.aion.elysia_agents import ElysiaRAGSystem, ELYSIA_AVAILABLE
from src.aion.generation import GenerationPipeline
from src.aion.skills.registry import get_skill_registry

logger = logging.getLogger(__name__)


# Global state
_weaviate_client = None
_elysia_system = None
_generation_pipeline = None
_persona = None
_db_path = Path(__file__).parent.parent.parent / "chat_history.db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    global _weaviate_client, _elysia_system, _generation_pipeline, _persona

    # Startup
    init_db()

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
        settings.effective_tree_provider,
    ):
        try:
            import httpx
            httpx.get(f"{settings.ollama_url}/api/tags", timeout=5.0).raise_for_status()
            logger.info(f"Ollama reachable at {settings.ollama_url}")
        except Exception as e:
            logger.warning(f"Ollama not reachable at {settings.ollama_url}: {e}")

    logger.info(
        f"Config: persona={settings.effective_persona_provider}/{settings.effective_persona_model}, "
        f"tree={settings.effective_tree_provider}/{settings.effective_tree_model}"
    )

    try:
        _weaviate_client = get_weaviate_client()
        logger.info("Connected to Weaviate")
    except Exception as e:
        logger.error(f"Failed to connect to Weaviate: {e}")
        raise

    if ELYSIA_AVAILABLE:
        _elysia_system = ElysiaRAGSystem(_weaviate_client)
        logger.info("AInstein initialized with Elysia")
    else:
        logger.warning("Elysia not available - running in comparison-only mode")
        _elysia_system = None

    _generation_pipeline = GenerationPipeline(_weaviate_client)
    logger.info("Generation pipeline initialized")

    _persona = Persona()
    logger.info("Persona orchestrator initialized")

    yield  # App is running

    # Shutdown
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
    timestamp: Optional[str] = None
    sources: Optional[list[dict]] = None


class LLMSettings(BaseModel):
    """LLM provider and model settings."""
    provider: str = "ollama"  # "ollama", "github_models", or "openai"
    model: str = "gpt-oss:20b"
    # Per-component overrides (None = use global provider/model)
    persona_provider: Optional[str] = None
    persona_model: Optional[str] = None
    tree_provider: Optional[str] = None
    tree_model: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    llm_settings: Optional[LLMSettings] = None  # Optional override per request


class ComparisonRequest(BaseModel):
    """Request for side-by-side LLM comparison (Test Mode)."""
    message: str
    conversation_id: Optional[str] = None
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
    content: Optional[str] = None
    metadata: Optional[dict] = None
    body: Optional[str] = None


class ToggleRequest(BaseModel):
    enabled: bool


# Available models per provider — each provider has its own catalog.
AVAILABLE_MODELS = {
    "ollama": [
        {"id": "gpt-oss:20b", "name": "GPT-OSS (Local, 20B)"},
        {"id": "qwen3:14b", "name": "Qwen3 (Local, 14B)"},
        {"id": "qwen3:4b", "name": "Qwen3 (Local, 4B)"},
        {"id": "alibayram/smollm3:latest", "name": "SmolLM3 (Local, 3.1B)"},
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
    conn = sqlite3.connect(_db_path)
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

    conn.commit()
    conn.close()

    # Memory tables (sessions, user_profiles) — same database file
    init_memory_tables(_db_path)


def save_message(conversation_id: str, role: str, content: str, sources: list[dict] = None, timing: dict = None, turn_summary: str = None):
    """Save a message to the database."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    timestamp = datetime.now().isoformat()
    sources_json = json.dumps(sources) if sources else None
    timing_json = json.dumps(timing) if timing else None

    cursor.execute(
        "INSERT INTO messages (conversation_id, role, content, sources, timestamp, timing, turn_summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (conversation_id, role, content, sources_json, timestamp, timing_json, turn_summary)
    )

    # Update conversation timestamp
    cursor.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (timestamp, conversation_id)
    )

    conn.commit()
    conn.close()


def create_conversation(title: str = "New Conversation") -> str:
    """Create a new conversation and return its ID."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    conv_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    cursor.execute(
        "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (conv_id, title, timestamp, timestamp)
    )

    conn.commit()
    conn.close()
    return conv_id


def get_conversation_messages(conversation_id: str) -> list[dict]:
    """Get all messages for a conversation."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT role, content, sources, timestamp, timing, turn_summary FROM messages WHERE conversation_id = ? ORDER BY timestamp",
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
        })

    conn.close()
    return messages


def get_all_conversations() -> list[dict]:
    """Get all conversations with message counts and last updated time."""
    conn = sqlite3.connect(_db_path)
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

    conn.close()
    return conversations


def update_conversation_title(conversation_id: str, title: str):
    """Update conversation title."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE conversations SET title = ? WHERE id = ?",
        (title, conversation_id)
    )

    conn.commit()
    conn.close()


def delete_conversation(conversation_id: str):
    """Delete a conversation and its messages."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    conn.commit()
    conn.close()


def delete_all_conversations():
    """Delete all conversations and messages."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages")
    cursor.execute("DELETE FROM conversations")
    cursor.execute("DELETE FROM artifacts")

    conn.commit()
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
    conn = sqlite3.connect(_db_path)
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
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    if content_type:
        cursor.execute(
            "SELECT id, filename, content, content_type, summary FROM artifacts "
            "WHERE conversation_id = ? AND content_type = ? ORDER BY turn DESC LIMIT 1",
            (conversation_id, content_type),
        )
    else:
        cursor.execute(
            "SELECT id, filename, content, content_type, summary FROM artifacts "
            "WHERE conversation_id = ? ORDER BY turn DESC LIMIT 1",
            (conversation_id,),
        )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "filename": row[1],
        "content": row[2],
        "content_type": row[3],
        "summary": row[4],
    }


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
        "(max 150 chars). Capture the key action or information conveyed — "
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

    client = OpenAI(**settings.get_openai_client_kwargs(settings.effective_persona_provider))
    model = settings.effective_persona_model

    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    model_base = model.rsplit("/", 1)[-1] if "/" in model else model
    if model_base.startswith("gpt-5"):
        kwargs["max_completion_tokens"] = 512
    else:
        kwargs["max_tokens"] = 150

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0] if response.choices else None
    text = (choice.message.content or "").strip() if choice else ""
    return text if text else None


async def _llm_summarize_ollama(prompt: str) -> str | None:
    """Summarize via Ollama API (same provider as Persona)."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
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
        text = resp.json().get("response", "").strip()
        # Strip chain-of-thought tags
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"</?think>", "", text).strip()
        return text if text else None


async def _maybe_update_summary(conversation_id: str) -> None:
    """Trigger a rolling summary update if enough messages have left the verbatim window.

    The verbatim window is defined in Persona.VERBATIM_WINDOW (6 messages).
    We summarize when SUMMARIZE_TRIGGER_COUNT (4) messages have accumulated
    beyond that window since the last summary, so roughly every 4-6 turns.
    """
    from src.aion.persona import Persona  # local import to avoid circular

    messages = get_conversation_messages(conversation_id)
    verbatim_window = Persona.VERBATIM_WINDOW

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
    # Otherwise, only summarize when SUMMARIZE_TRIGGER_COUNT new messages
    # have accumulated (we count from the last summary update by tracking
    # how many older messages exist vs what the summary likely covers).
    if current_summary and len(older_messages) < SUMMARIZE_TRIGGER_COUNT:
        return

    # Only summarize the most recent batch of older messages (the ones
    # that just left the window), not the entire history again.
    batch = older_messages[-SUMMARIZE_TRIGGER_COUNT:] if current_summary else older_messages

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


def _get_execution_model(intent: str, skill_tags: list[str] | None) -> str:
    """Determine execution path based on intent and skill registry.

    Intent is the sole routing gate. The registry's execution field
    confirms the pipeline type but never overrides intent.
    """
    if intent == "generation":
        return "generation"
    if intent == "inspect":
        return "inspect"
    if intent == "refinement" and skill_tags:
        registry = get_skill_registry()
        if registry.get_execution_model(skill_tags) == "generation":
            return "generation"
    return "tree"


def run_generation_query(
    question: str, result_queue: Queue, output_queue: Queue,
    skill_tags: list[str] | None = None,
    doc_refs: list[str] | None = None,
    conversation_id: str | None = None,
    intent: str = "generation",
):
    """Run generation pipeline in a thread, emitting events via output_queue."""
    import asyncio

    start_time = time.time()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            response, objects = loop.run_until_complete(
                _generation_pipeline.generate(
                    question,
                    skill_tags=skill_tags or [],
                    doc_refs=doc_refs,
                    conversation_id=conversation_id,
                    event_queue=output_queue,
                    intent=intent,
                )
            )
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

        total_time_ms = int((time.time() - start_time) * 1000)
        result_queue.put({
            "response": response,
            "objects": objects,
            "error": None,
            "timing": {"total_ms": total_time_ms},
        })
    except Exception as e:
        logger.exception("Generation pipeline error")
        total_time_ms = int((time.time() - start_time) * 1000)
        result_queue.put({
            "response": None,
            "objects": None,
            "error": str(e),
            "timing": {"total_ms": total_time_ms},
        })
    finally:
        output_queue.put(None)


async def stream_generation_response(
    question: str,
    skill_tags: list[str] | None = None,
    doc_refs: list[str] | None = None,
    conversation_id: str | None = None,
    intent: str = "generation",
) -> AsyncGenerator[str, None]:
    """Stream generation pipeline events as SSE, parallel to stream_elysia_response."""
    result_queue = Queue()
    output_queue = Queue()

    logger.info(f"Starting generation pipeline: {question}")

    yield f"data: {json.dumps({'type': 'status', 'content': 'Starting generation...'})}\n\n"

    thread = Thread(
        target=run_generation_query,
        args=(question, result_queue, output_queue),
        kwargs={
            "skill_tags": skill_tags,
            "doc_refs": doc_refs,
            "conversation_id": conversation_id,
            "intent": intent,
        },
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
            logger.info(f"Generation event {event_count}: {event['type']}")
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
            logger.info(f"Draining generation event {event_count}: {event['type']}")
            yield f"data: {json.dumps(event)}\n\n"
        except Empty:
            break

    logger.info(f"Generation stream complete, sent {event_count} events")

    thread.join(timeout=180)

    try:
        result = result_queue.get_nowait()
        if result["error"]:
            logger.error(f"Generation error: {result['error']}")
            yield f"data: {json.dumps({'type': 'error', 'content': result['error']})}\n\n"
        else:
            final_response = result["response"] or ""
            timing = result.get("timing", {})

            # Build sources from retrieved objects
            objects = result["objects"] or []
            sources = []
            for obj in objects[:5]:
                if not isinstance(obj, dict):
                    continue
                sources.append({
                    "type": obj.get("type", "Document"),
                    "title": obj.get("title") or "Untitled",
                    "preview": (obj.get("content") or "")[:200],
                })

            yield f"data: {json.dumps({'type': 'complete', 'response': final_response, 'sources': sources, 'timing': timing})}\n\n"
    except Empty:
        logger.error("Generation query timed out")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Generation timed out'})}\n\n"


async def stream_inspect_response(
    question: str,
    conversation_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream model inspection response as SSE events.

    Three input paths (tried in order):
    1. Load latest ArchiMate artifact from the conversation (XML or YAML)
    2. Detect a URL in the query, fetch it, validate as ArchiMate content
    3. No model found — prompt user to generate or upload
    """
    from src.aion.tools.yaml_to_xml import xml_to_yaml, _parse_and_validate

    yield f"data: {json.dumps({'type': 'status', 'content': 'Loading model...'})}\n\n"

    yaml_content = None
    source_filename = None
    source = None

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
                from src.aion.mcp.github import get_file_contents as mcp_get_file, parse_github_url
                parsed = parse_github_url(url)
                if parsed:
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Fetching from GitHub...'})}\n\n"
                    fetched = await mcp_get_file(
                        owner=parsed["owner"], repo=parsed["repo"],
                        path=parsed["path"], ref=parsed["ref"],
                    )
                    source_filename = parsed["path"].rsplit("/", 1)[-1]
                    source = f"Fetched from GitHub: {url}"
                else:
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Fetching model from URL...'})}\n\n"
                    import httpx
                    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        fetched = resp.text
                    source_filename = url.rsplit("/", 1)[-1] if "/" in url else "fetched-model.xml"
                    source = f"Fetched from URL: {url}"

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

    # Path 3: No model found
    if not yaml_content:
        yield f"data: {json.dumps({'type': 'complete', 'response': 'No ArchiMate model found in this conversation. Generate a model first, upload an ArchiMate XML/YAML file, or paste a URL to one.', 'sources': [], 'timing': {}})}\n\n"
        return

    # LLM analysis
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

    start_time = time.time()
    try:
        if settings.effective_tree_provider in ("github_models", "openai"):
            from openai import OpenAI
            client = OpenAI(**settings.get_openai_client_kwargs(settings.effective_tree_provider))
            model = settings.effective_tree_model
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            model_base = model.rsplit("/", 1)[-1] if "/" in model else model
            if model_base.startswith("gpt-5"):
                kwargs["max_completion_tokens"] = 4096
            else:
                kwargs["max_tokens"] = 2000
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0] if response.choices else None
            response_text = (choice.message.content or "").strip() if choice else ""
        else:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.effective_tree_model,
                        "prompt": f"{system_prompt}\n\n{user_prompt}",
                        "stream": False,
                        "options": {"num_predict": 2000},
                    },
                )
                resp.raise_for_status()
                response_text = resp.json().get("response", "")
                response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL)
                response_text = re.sub(r"</?think>", "", response_text).strip()

        total_ms = int((time.time() - start_time) * 1000)
        timing = {"total_ms": total_ms}

        sources = [{
            "type": "ArchiMate Model",
            "title": source_filename or "model.archimate.xml",
            "preview": f"Model with {yaml_content.count('- id:')} elements",
        }]

        logger.info(f"Inspect complete: {total_ms}ms, {len(response_text)} chars")
        yield f"data: {json.dumps({'type': 'complete', 'response': response_text, 'sources': sources, 'timing': timing})}\n\n"

    except Exception as e:
        logger.exception("Inspect LLM error")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Analysis failed: {e}'})}\n\n"


def run_elysia_query(question: str, result_queue: Queue, output_queue: Queue,
                     skill_tags: list[str] | None = None,
                     doc_refs: list[str] | None = None,
                     conversation_id: str | None = None):
    """Run Elysia query in a thread, emitting typed events via output_queue.

    Events are emitted directly from Tree.async_run() results — no stdout
    parsing needed. See docs/MONKEY_PATCHES.md #2 for details.
    """
    import asyncio
    import time

    start_time = time.time()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            response, objects = loop.run_until_complete(
                _elysia_system.query(question, event_queue=output_queue,
                                     skill_tags=skill_tags,
                                     doc_refs=doc_refs,
                                     conversation_id=conversation_id)
            )
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

        total_time_ms = int((time.time() - start_time) * 1000)

        result_queue.put({
            "response": response,
            "objects": objects,
            "error": None,
            "timing": {"total_ms": total_time_ms},
        })
    except Exception as e:
        logger.exception("Elysia query error")
        total_time_ms = int((time.time() - start_time) * 1000)
        result_queue.put({
            "response": None,
            "objects": None,
            "error": str(e),
            "timing": {"total_ms": total_time_ms},
        })
    finally:
        output_queue.put(None)  # Signal end of output


async def stream_elysia_response(question: str,
                                 skill_tags: list[str] | None = None,
                                 doc_refs: list[str] | None = None,
                                 conversation_id: str | None = None) -> AsyncGenerator[str, None]:
    """Stream Elysia's thinking process as SSE events."""
    result_queue = Queue()
    output_queue = Queue()

    logger.info(f"Starting streaming query: {question}")

    # Send initial status
    yield f"data: {json.dumps({'type': 'status', 'content': 'Thinking...'})}\n\n"

    # Start query in background thread
    thread = Thread(target=run_elysia_query,
                    args=(question, result_queue, output_queue),
                    kwargs={"skill_tags": skill_tags, "doc_refs": doc_refs,
                            "conversation_id": conversation_id})
    thread.daemon = True
    thread.start()

    event_count = 0
    last_status_time = asyncio.get_event_loop().time()
    start_time = asyncio.get_event_loop().time()

    # Stream output events with keepalive
    while thread.is_alive():
        try:
            event = output_queue.get(timeout=0.1)
            if event is None:
                break
            event_count += 1
            logger.info(f"Streaming event {event_count}: {event['type']}")
            yield f"data: {json.dumps(event)}\n\n"
            last_status_time = asyncio.get_event_loop().time()
        except Empty:
            # Send keepalive status event every 3 seconds to show system is still working
            now = asyncio.get_event_loop().time()
            if now - last_status_time > 3:
                elapsed_sec = int(now - start_time)
                # Send actual status event so frontend can update UI
                yield f"data: {json.dumps({'type': 'heartbeat', 'elapsed_sec': elapsed_sec})}\n\n"
                last_status_time = now
            await asyncio.sleep(0.05)
            continue

    # Drain any remaining events
    while True:
        try:
            event = output_queue.get_nowait()
            if event is None:
                break
            event_count += 1
            logger.info(f"Draining event {event_count}: {event['type']}")
            yield f"data: {json.dumps(event)}\n\n"
        except Empty:
            break

    logger.info(f"Stream complete, sent {event_count} events")

    # Wait for result — 180s allows multi-tool chains with slow models
    # (gpt-5-nano: ~15s per LLM call × 5 iterations + SKOSMOS API calls)
    thread.join(timeout=180)

    try:
        result = result_queue.get_nowait()
        if result["error"]:
            logger.error(f"Query error: {result['error']}")
            yield f"data: {json.dumps({'type': 'error', 'content': result['error']})}\n\n"
        else:
            # Send final result
            objects = result["objects"] or []
            flat_objects = []
            for item in objects:
                if isinstance(item, list):
                    flat_objects.extend(item)
                elif isinstance(item, dict):
                    flat_objects.append(item)

            sources = []
            for obj in flat_objects[:5]:
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

            final_response = result['response'] or ""
            timing = result.get('timing', {})
            logger.info(f"Query complete, response length: {len(final_response)}, time: {timing.get('total_ms', 0)}ms")

            # If no events were captured, send the response as an assistant panel
            if event_count == 0 and final_response:
                yield f"data: {json.dumps({'type': 'assistant', 'content': final_response, 'timing': timing})}\n\n"

            yield f"data: {json.dumps({'type': 'complete', 'response': final_response, 'sources': sources, 'timing': timing})}\n\n"
    except Empty:
        logger.error("Query timed out")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Query timed out'})}\n\n"


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

    retrieval_start = time.time()
    all_results = []

    # Get collection names for this provider
    collections = COLLECTION_NAMES.get(provider, COLLECTION_NAMES["ollama"])

    # Retrieval limits - standard RAG configuration
    # These are application-level limits for how many documents to retrieve
    adr_limit = 8
    principle_limit = 6
    policy_limit = 4
    vocab_limit = 4
    content_max_chars = 800

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

    retrieval_time = int((time.time() - retrieval_start) * 1000)
    return all_results, context, retrieval_time


def strip_think_tags(text: str) -> str:
    """Strip <think>...</think> tags from model output.

    SmolLM3 and similar models use <think> tags for chain-of-thought reasoning.
    These should not be shown to end users.
    """
    import re
    # Remove <think>...</think> blocks (including multiline)
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Also remove any orphaned tags
    cleaned = re.sub(r'</?think>', '', cleaned)
    # Clean up extra whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


async def generate_with_ollama(system_prompt: str, user_prompt: str, model: str) -> tuple[str, dict]:
    """Generate response using Ollama API with timing.

    Returns:
        Tuple of (response text, timing dict)

    Raises:
        Exception: With actionable error message for timeout/connection issues
    """
    import httpx

    start_time = time.time()
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min for slow local models
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

            end_time = time.time()
            latency_ms = int((end_time - start_time) * 1000)

            timing = {
                "latency_ms": latency_ms,
            }

            # Strip <think> tags from response
            response_text = strip_think_tags(result.get("response", ""))
            return response_text, timing

    except httpx.TimeoutException:
        latency_ms = int((time.time() - start_time) * 1000)
        raise Exception(
            f"Ollama generation timed out after {latency_ms}ms. "
            "Check Ollama settings or try a smaller context length."
        )

    except httpx.HTTPStatusError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        raise Exception(f"Ollama HTTP error after {latency_ms}ms: {str(e)}")

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        raise Exception(f"Ollama error after {latency_ms}ms: {str(e)}")


async def generate_with_openai(system_prompt: str, user_prompt: str, model: str) -> tuple[str, dict]:
    """Generate response using OpenAI API with timing.

    Returns:
        Tuple of (response text, timing dict)
    """
    from openai import OpenAI

    start_time = time.time()

    try:
        openai_client = OpenAI(**settings.get_openai_client_kwargs())

        # GPT-5.x models use max_completion_tokens instead of max_tokens
        completion_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        # gpt-5.x models use max_completion_tokens; handle publisher/ prefix
        model_base = model.rsplit("/", 1)[-1] if "/" in model else model
        if model_base.startswith("gpt-5"):
            completion_kwargs["max_completion_tokens"] = 1000
        else:
            completion_kwargs["max_tokens"] = 1000

        response = openai_client.chat.completions.create(**completion_kwargs)

        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)

        return response.choices[0].message.content, {"latency_ms": latency_ms}
    except Exception as e:
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
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
    global _elysia_system, _persona

    if not _elysia_system:
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
        # Send conversation ID first
        yield f"data: {json.dumps({'type': 'init', 'conversation_id': conversation_id})}\n\n"

        # Show immediate feedback while Persona classifies intent
        yield f"data: {json.dumps({'type': 'status', 'content': 'Thinking...'})}\n\n"

        # Run Persona intent classification and query rewriting
        try:
            persona_result = await _persona.process(
                request.message, messages, conversation_id=conversation_id,
            )
        except PermanentLLMError as e:
            logger.error(f"Permanent LLM error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return

        # Emit Persona classification result with latency
        yield f"data: {json.dumps({'type': 'persona_intent', 'intent': persona_result.intent, 'rewritten_query': persona_result.rewritten_query, 'skill_tags': persona_result.skill_tags, 'doc_refs': persona_result.doc_refs, 'latency_ms': persona_result.latency_ms})}\n\n"

        # Direct response intents: respond immediately, no Tree needed
        if persona_result.direct_response is not None:
            start_ms = time.time()
            timing = {"total_ms": int((time.time() - start_ms) * 1000)}
            yield f"data: {json.dumps({'type': 'complete', 'response': persona_result.direct_response, 'sources': [], 'timing': timing})}\n\n"
            save_message(
                conversation_id, "assistant",
                persona_result.direct_response, [], timing,
                turn_summary=f"Direct response ({persona_result.intent})",
            )
            await _maybe_update_summary(conversation_id)
            return

        # Route to the appropriate execution path based on intent.
        # Intent is the sole gate: "generation" and "refinement" (with
        # generation skill_tags) go to the direct pipeline. Everything
        # else goes to the Tree.
        execution_model = _get_execution_model(
            persona_result.intent, persona_result.skill_tags,
        )
        logger.info(f"Execution model: {execution_model} (intent={persona_result.intent})")

        final_response = None
        final_sources = []
        final_timing = None

        if execution_model == "generation":
            async for event in stream_generation_response(
                persona_result.rewritten_query,
                skill_tags=persona_result.skill_tags,
                doc_refs=persona_result.doc_refs,
                conversation_id=conversation_id,
                intent=persona_result.intent,
            ):
                yield event
                try:
                    data = json.loads(event.replace("data: ", "").strip())
                    if data.get("type") == "complete":
                        final_response = data.get("response")
                        final_sources = data.get("sources", [])
                        final_timing = data.get("timing")
                except:
                    pass
        elif execution_model == "inspect":
            async for event in stream_inspect_response(
                persona_result.rewritten_query,
                conversation_id=conversation_id,
            ):
                yield event
                try:
                    data = json.loads(event.replace("data: ", "").strip())
                    if data.get("type") == "complete":
                        final_response = data.get("response")
                        final_sources = data.get("sources", [])
                        final_timing = data.get("timing")
                except:
                    pass
        else:
            async for event in stream_elysia_response(
                persona_result.rewritten_query,
                skill_tags=persona_result.skill_tags,
                doc_refs=persona_result.doc_refs,
                conversation_id=conversation_id,
            ):
                yield event
                try:
                    data = json.loads(event.replace("data: ", "").strip())
                    if data.get("type") == "complete":
                        final_response = data.get("response")
                        final_sources = data.get("sources", [])
                        final_timing = data.get("timing")
                except:
                    pass

        # Save assistant response with structured turn summary
        if final_response:
            turn_summary = await _build_turn_summary(final_response, final_sources)
            save_message(
                conversation_id, "assistant",
                final_response, final_sources, final_timing,
                turn_summary=turn_summary,
            )
            await _maybe_update_summary(conversation_id)

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
    global _elysia_system, _persona

    if not _elysia_system:
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
        # Query Elysia system with the rewritten query
        response, objects = await _elysia_system.query(
            persona_result.rewritten_query,
            skill_tags=persona_result.skill_tags,
            doc_refs=persona_result.doc_refs,
            conversation_id=conversation_id,
        )

        # Flatten objects
        flat_objects = []
        for item in (objects or []):
            if isinstance(item, list):
                flat_objects.extend(item)
            elif isinstance(item, dict):
                flat_objects.append(item)

        # Format sources
        sources = []
        for obj in flat_objects[:5]:
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

    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT filename, content, content_type FROM artifacts WHERE id = ?",
        (artifact_id,),
    )
    row = cursor.fetchone()
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
    from src.aion.tools.yaml_to_xml import xml_to_yaml, _parse_and_validate

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
    """Get system status."""
    return {
        "status": "ok",
        "weaviate_connected": _weaviate_client is not None,
        "elysia_available": ELYSIA_AVAILABLE,
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
            "tree": {
                "provider": settings.effective_tree_provider,
                "model": settings.effective_tree_model,
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
    settings.tree_provider = llm_settings.tree_provider
    settings.tree_model = llm_settings.tree_model

    logger.info(
        f"LLM settings updated: provider={llm_settings.provider}, "
        f"model={llm_settings.model}, "
        f"persona={settings.effective_persona_provider}/{settings.effective_persona_model}, "
        f"tree={settings.effective_tree_provider}/{settings.effective_tree_model}"
    )

    return {
        "status": "updated",
        "provider": llm_settings.provider,
        "model": llm_settings.model,
        "persona": {
            "provider": settings.effective_persona_provider,
            "model": settings.effective_persona_model,
        },
        "tree": {
            "provider": settings.effective_tree_provider,
            "model": settings.effective_tree_model,
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
    from src.aion.memory.session_store import get_user_profile as _get_profile

    conn = sqlite3.connect(_db_path)
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
    conn.close()

    return {
        "sessions": sessions,
        "user_profile": _get_profile(db_path=_db_path),
        "message_count": message_count,
    }


@app.delete("/api/memory/sessions")
async def memory_reset_sessions():
    """Clear all sessions and running summaries. Messages are preserved."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return {"success": True, "deleted_sessions": count}


@app.delete("/api/memory/profile")
async def memory_reset_profile():
    """Delete all user profiles."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_profiles")
    count = cursor.rowcount
    conn.commit()
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


def run_server(host: str = "127.0.0.1", port: int = 8081):
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
