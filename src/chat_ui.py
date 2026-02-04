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

from .config import settings
from .weaviate.client import get_weaviate_client
from .weaviate.embeddings import embed_text
from .elysia_agents import ElysiaRAGSystem, ELYSIA_AVAILABLE
from .skills import SkillRegistry, DEFAULT_SKILL
from .skills import api as skills_api

# Initialize skill registry for prompt injection
_skill_registry = SkillRegistry()

logger = logging.getLogger(__name__)


# Global state
_weaviate_client = None
_elysia_system = None
_db_path = Path(__file__).parent.parent / "chat_history.db"


class OutputCapture:
    """Capture stdout and parse Rich panel output into structured events."""

    def __init__(self, queue: Queue, original_stdout):
        self.queue = queue
        self.original_stdout = original_stdout
        self.buffer = ""
        self.current_panel_type = None
        self.current_panel_content = []
        self.encoding = 'utf-8'
        self.errors = 'replace'
        self.mode = 'w'
        self.name = '<capture>'

    def write(self, text: str):
        """Capture and process output while also printing to original stdout."""
        # Also write to original stdout so we see it in console
        if self.original_stdout:
            self.original_stdout.write(text)
            self.original_stdout.flush()

        self.buffer += text

        # Process complete lines immediately
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._process_line(line)

        return len(text)

    def _process_line(self, line: str):
        """Parse a line and emit structured events."""
        # Strip ANSI codes for analysis
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()

        if not clean:
            return

        # Detect panel boundaries and types based on Rich panel titles
        if "User prompt" in clean:
            self._emit_panel()
            self.current_panel_type = "user_prompt"
        elif "Assistant response" in clean:
            self._emit_panel()
            self.current_panel_type = "assistant"
        elif "Current Decision" in clean:
            self._emit_panel()
            self.current_panel_type = "decision"
        elif "Thinking..." in clean:
            self._emit_panel()
            self.queue.put({"type": "status", "content": "Thinking..."})
        elif "Running " in clean and "..." in clean:
            self._emit_panel()
            self.queue.put({"type": "status", "content": clean.strip("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ ")})
        elif "Summarizing..." in clean:
            self._emit_panel()
            self.queue.put({"type": "status", "content": "Summarizing..."})
        elif clean.startswith("╭") or clean.startswith("╰"):
            # Panel border - ignore but don't add to content
            pass
        elif clean.startswith("│"):
            # Panel content line
            content = clean[1:].strip() if len(clean) > 1 else ""
            # Remove trailing border character if present
            if content.endswith("│"):
                content = content[:-1].strip()
            if content and self.current_panel_type:
                self.current_panel_content.append(content)
        elif self.current_panel_type and clean and not clean.startswith("─"):
            # Content line without border
            self.current_panel_content.append(clean)

    def _emit_panel(self):
        """Emit the current panel as an event."""
        if self.current_panel_type and self.current_panel_content:
            # Filter out "Node:" lines from decision panels (internal Elysia detail)
            if self.current_panel_type == "decision":
                filtered_content = [
                    line for line in self.current_panel_content
                    if not line.startswith("Node:")
                ]
                content = "\n".join(filtered_content).strip()
            else:
                content = "\n".join(self.current_panel_content).strip()

            if content:
                panel_type = self.current_panel_type

                # Detect intermediate "thinking aloud" assistant responses
                if panel_type == "assistant" and self._is_thinking_aloud(content):
                    panel_type = "thinking_aloud"

                self.queue.put({
                    "type": panel_type,
                    "content": content
                })
        self.current_panel_type = None
        self.current_panel_content = []

    def _is_thinking_aloud(self, content: str) -> bool:
        """Detect if an assistant response is an intermediate 'thinking aloud' message."""
        # Short responses that describe actions being taken
        if len(content) > 400:
            return False

        content_lower = content.lower()

        # Patterns indicating intermediate responses
        thinking_patterns = [
            "i will now",
            "i will search",
            "i will retrieve",
            "i will look",
            "i will find",
            "i will provide",
            "i will analyze",
            "i will examine",
            "i have searched",
            "i have retrieved",
            "i have found",
            "i have analyzed",
            "let me search",
            "let me retrieve",
            "let me find",
            "let me look",
            "let me analyze",
            "searching for",
            "retrieving",
            "looking for",
            "analyzing",
        ]

        return any(pattern in content_lower for pattern in thinking_patterns)

    def flush(self):
        """Flush remaining content."""
        if self.original_stdout:
            self.original_stdout.flush()
        if self.buffer:
            self._process_line(self.buffer)
            self.buffer = ""
        self._emit_panel()

    def fileno(self):
        """Return file descriptor for compatibility."""
        if self.original_stdout:
            return self.original_stdout.fileno()
        return -1

    def isatty(self):
        """Check if output is a TTY."""
        if self.original_stdout:
            return self.original_stdout.isatty()
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    global _weaviate_client, _elysia_system

    # Startup
    init_db()

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

    yield  # App is running

    # Shutdown
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
    provider: str = "ollama"  # "ollama" or "openai"
    model: str = "alibayram/smollm3:latest"


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    llm_settings: Optional[LLMSettings] = None  # Optional override per request


class ComparisonRequest(BaseModel):
    """Request for side-by-side LLM comparison (Test Mode)."""
    message: str
    conversation_id: Optional[str] = None
    ollama_model: str = "alibayram/smollm3:latest"
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


# Available models configuration
AVAILABLE_MODELS = {
    "ollama": [
        {"id": "alibayram/smollm3:latest", "name": "SmolLM3 (Local, 3.1B)"},
        {"id": "qwen3:4b", "name": "Qwen3 (Local, 4B)"},
    ],
    "openai": [
        {"id": "gpt-5.2", "name": "GPT-5.2 (Latest)"},
        {"id": "gpt-5.1", "name": "GPT-5.1"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini (Budget)"},
        {"id": "gpt-4o", "name": "GPT-4o"},
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

    conn.commit()
    conn.close()


def save_message(conversation_id: str, role: str, content: str, sources: list[dict] = None, timing: dict = None):
    """Save a message to the database."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    timestamp = datetime.now().isoformat()
    sources_json = json.dumps(sources) if sources else None
    timing_json = json.dumps(timing) if timing else None

    cursor.execute(
        "INSERT INTO messages (conversation_id, role, content, sources, timestamp, timing) VALUES (?, ?, ?, ?, ?, ?)",
        (conversation_id, role, content, sources_json, timestamp, timing_json)
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
        "SELECT role, content, sources, timestamp, timing FROM messages WHERE conversation_id = ? ORDER BY timestamp",
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

    conn.commit()
    conn.close()


def run_elysia_query(question: str, result_queue: Queue, output_queue: Queue):
    """Run Elysia query in a thread, capturing console output via stdout/stderr redirect."""
    import sys
    import asyncio
    import os
    import time

    # Track timing
    start_time = time.time()

    # Redirect both stdout and stderr to capture all Rich console output
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    stdout_capture = OutputCapture(output_queue, original_stdout)
    stderr_capture = OutputCapture(output_queue, original_stderr)

    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    # Also set environment variable to force Rich to use simple output
    original_term = os.environ.get('TERM', '')
    os.environ['TERM'] = 'dumb'

    try:
        # Run the query synchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            response, objects = loop.run_until_complete(_elysia_system.query(question))
        finally:
            # Clean up pending tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

        # Flush any remaining output
        stdout_capture.flush()
        stderr_capture.flush()

        # Calculate total time
        total_time_ms = int((time.time() - start_time) * 1000)

        result_queue.put({
            "response": response,
            "objects": objects,
            "error": None,
            "timing": {
                "total_ms": total_time_ms,
            }
        })
    except Exception as e:
        stdout_capture.flush()
        stderr_capture.flush()
        logger.exception("Elysia query error")
        total_time_ms = int((time.time() - start_time) * 1000)
        result_queue.put({
            "response": None,
            "objects": None,
            "error": str(e),
            "timing": {"total_ms": total_time_ms}
        })
    finally:
        # Restore original stdout/stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        os.environ['TERM'] = original_term
        output_queue.put(None)  # Signal end of output


async def stream_elysia_response(question: str) -> AsyncGenerator[str, None]:
    """Stream Elysia's thinking process as SSE events."""
    result_queue = Queue()
    output_queue = Queue()

    logger.info(f"Starting streaming query: {question}")

    # Send initial status
    yield f"data: {json.dumps({'type': 'status', 'content': 'Thinking...'})}\n\n"

    # Start query in background thread
    thread = Thread(target=run_elysia_query, args=(question, result_queue, output_queue))
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

    # Wait for result
    thread.join(timeout=60)

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

    # Retrieval limits - loaded from skill configuration
    retrieval_limits = _skill_registry.loader.get_retrieval_limits(DEFAULT_SKILL)
    adr_limit = retrieval_limits.get("adr", 8)
    principle_limit = retrieval_limits.get("principle", 6)
    policy_limit = retrieval_limits.get("policy", 4)
    vocab_limit = retrieval_limits.get("vocabulary", 4)

    # Truncation limits - loaded from skill configuration
    truncation = _skill_registry.loader.get_truncation(DEFAULT_SKILL)
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
        openai_client = OpenAI(api_key=settings.openai_api_key)

        # GPT-5.x models use max_completion_tokens instead of max_tokens
        completion_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if model.startswith("gpt-5"):
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
        # Get skill content for prompt injection
        skill_content = _skill_registry.get_all_skill_content(question)

        # OpenAI system prompt - standard RAG instruction
        openai_system_prompt = "You are a helpful assistant answering questions about architecture decisions, principles, policies, and vocabulary. Base your answers on the provided context. Be concise but thorough. When referencing ADRs, use the format ADR.XX (e.g., ADR.21). When referencing Principles, use the format PCP.XX (e.g., PCP.10)."

        # SmolLM3 system prompt - much more explicit instructions
        # Small models need very clear, direct instructions to follow RAG patterns
        ollama_system_prompt = """You are an assistant that ONLY answers based on the provided context.

IMPORTANT RULES:
1. ONLY use information from the context below to answer
2. If the context contains the answer, provide it directly with specific details
3. If the context does NOT contain the answer, say "I don't have information about that in the provided context"
4. Do NOT make up information or give general advice
5. Be concise and cite specific items from the context
6. When referencing ADRs, use the format ADR.XX (e.g., ADR.21)
7. When referencing Principles, use the format PCP.XX (e.g., PCP.10)"""

        # Inject skill rules if available
        if skill_content:
            openai_system_prompt = f"{openai_system_prompt}\n\n{skill_content}"
            ollama_system_prompt = f"{ollama_system_prompt}\n\n{skill_content}"

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
    global _elysia_system

    if not _elysia_system:
        raise HTTPException(status_code=503, detail="System not initialized")

    # Create or use existing conversation
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = create_conversation()

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

        final_response = None
        final_sources = []
        final_timing = None

        async for event in stream_elysia_response(request.message):
            yield event

            # Parse event to capture final response for saving
            try:
                data = json.loads(event.replace("data: ", "").strip())
                if data.get("type") == "complete":
                    final_response = data.get("response")
                    final_sources = data.get("sources", [])
                    final_timing = data.get("timing")
            except:
                pass

        # Save assistant response with timing
        if final_response:
            save_message(conversation_id, "assistant", final_response, final_sources, final_timing)

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
    global _elysia_system

    if not _elysia_system:
        raise HTTPException(status_code=503, detail="System not initialized")

    # Create or use existing conversation
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = create_conversation()

    # Save user message
    save_message(conversation_id, "user", request.message)

    # Update conversation title from first message
    messages = get_conversation_messages(conversation_id)
    if len(messages) == 1:
        title = request.message[:50] + "..." if len(request.message) > 50 else request.message
        update_conversation_title(conversation_id, title)

    try:
        # Query Elysia system
        response, objects = await _elysia_system.query(request.message)

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

        # Save assistant response
        save_message(conversation_id, "assistant", response, sources)

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
        },
        "available_providers": ["ollama", "openai"],
        "available_models": AVAILABLE_MODELS,
    }


@app.post("/api/settings/llm")
async def set_llm_settings(llm_settings: LLMSettings):
    """Update LLM settings."""
    global _current_llm_settings

    # Validate provider
    if llm_settings.provider not in ["ollama", "openai"]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    # Update settings
    _current_llm_settings = llm_settings

    # Also update the global config settings
    settings.llm_provider = llm_settings.provider
    if llm_settings.provider == "ollama":
        settings.ollama_model = llm_settings.model
        settings.ollama_embedding_model = llm_settings.model
    else:
        settings.openai_chat_model = llm_settings.model

    logger.info(f"LLM settings updated: provider={llm_settings.provider}, model={llm_settings.model}")

    return {
        "status": "updated",
        "provider": llm_settings.provider,
        "model": llm_settings.model,
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


# =============================================================================
# Skills Management API
# =============================================================================


class ThresholdsUpdate(BaseModel):
    """Request model for updating skill thresholds."""
    thresholds: dict


class TestQueryRequest(BaseModel):
    """Request model for testing a query against skill config."""
    query: str


@app.get("/api/skills")
async def api_list_skills():
    """List all registered skills."""
    try:
        return {"skills": skills_api.list_skills()}
    except Exception as e:
        logger.error(f"Error listing skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/skills/{skill_name}")
async def api_get_skill(skill_name: str):
    """Get detailed information about a specific skill."""
    try:
        return skills_api.get_skill(skill_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting skill {skill_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/skills/{skill_name}/thresholds")
async def api_get_thresholds(skill_name: str):
    """Get thresholds for a specific skill."""
    try:
        return {"thresholds": skills_api.get_thresholds(skill_name)}
    except Exception as e:
        logger.error(f"Error getting thresholds for {skill_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/skills/{skill_name}/thresholds")
async def api_update_thresholds(skill_name: str, update: ThresholdsUpdate):
    """Update thresholds for a skill."""
    try:
        result = skills_api.update_thresholds(skill_name, update.thresholds)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating thresholds for {skill_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/skills/{skill_name}/test")
async def api_test_query(skill_name: str, request: TestQueryRequest):
    """Test how a query would behave with the skill's config."""
    try:
        return skills_api.test_query(skill_name, request.query)
    except Exception as e:
        logger.error(f"Error testing query for {skill_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/skills/{skill_name}/backup")
async def api_backup_config(skill_name: str):
    """Create a backup of the skill's configuration."""
    try:
        backup_path = skills_api.backup_config(skill_name)
        return {"success": True, "backup_path": backup_path}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error backing up {skill_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/skills/{skill_name}/restore")
async def api_restore_config(skill_name: str):
    """Restore a skill's configuration from the most recent backup."""
    try:
        thresholds = skills_api.restore_config(skill_name)
        return {"success": True, "thresholds": thresholds}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error restoring {skill_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/skills/{skill_name}/validate")
async def api_validate_thresholds(skill_name: str, request: Request):
    """Validate thresholds configuration without saving."""
    try:
        body = await request.json()
        thresholds = body.get("thresholds", {})
        is_valid, errors = skills_api.validate_thresholds(thresholds)
        return {"valid": is_valid, "errors": errors}
    except Exception as e:
        logger.error(f"Error validating {skill_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/skills/reload")
async def api_reload_skills():
    """Reload all skills from disk."""
    try:
        return skills_api.reload_skills()
    except Exception as e:
        logger.error(f"Error reloading skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills", response_class=HTMLResponse)
async def skills_page():
    """Serve the Skills Management UI page."""
    static_dir = Path(__file__).parent / "static"
    skills_path = static_dir / "skills.html"
    if skills_path.exists():
        return HTMLResponse(skills_path.read_text(encoding="utf-8"))
    else:
        return HTMLResponse("<h1>Skills UI</h1><p>skills.html not found.</p>")


# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def run_server(host: str = "127.0.0.1", port: int = 8081):
    """Run the chat server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
