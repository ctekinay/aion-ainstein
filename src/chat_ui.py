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

from .config import settings
from .weaviate.client import get_weaviate_client
from .weaviate.embeddings import embed_text
from .elysia_agents import ElysiaRAGSystem, ELYSIA_AVAILABLE

logger = logging.getLogger(__name__)

# ============== Token Counting and Context Management ==============

# SmolLM3 context window is ~8K tokens. Reserve space for system prompt + response.
SMOLLM3_MAX_CONTEXT_TOKENS = 8000
SMOLLM3_RESERVED_TOKENS = 1500  # For system prompt (~300) + response (~1000) + buffer
SMOLLM3_MAX_INPUT_TOKENS = SMOLLM3_MAX_CONTEXT_TOKENS - SMOLLM3_RESERVED_TOKENS  # ~6500 tokens


def estimate_tokens(text: str) -> int:
    """Estimate token count using character-based approximation.

    Uses ~4 characters per token as a rough estimate.
    This is conservative and works without external dependencies.

    Args:
        text: The text to estimate tokens for

    Returns:
        Estimated token count
    """
    if not text:
        return 0
    # ~4 chars per token is a reasonable approximation for English text
    # SmolLM3 uses a similar tokenizer to LLaMA
    return len(text) // 4


def truncate_context(context: str, max_tokens: int = SMOLLM3_MAX_INPUT_TOKENS) -> tuple[str, bool]:
    """Truncate context to fit within token limit.

    Preserves complete documents where possible by truncating at document boundaries.

    Args:
        context: The context string to truncate
        max_tokens: Maximum tokens allowed

    Returns:
        Tuple of (truncated_context, was_truncated)
    """
    current_tokens = estimate_tokens(context)

    if current_tokens <= max_tokens:
        return context, False

    # Split by document boundaries (double newlines)
    documents = context.split("\n\n")

    truncated_docs = []
    total_tokens = 0

    for doc in documents:
        doc_tokens = estimate_tokens(doc)
        if total_tokens + doc_tokens + 2 <= max_tokens:  # +2 for newlines
            truncated_docs.append(doc)
            total_tokens += doc_tokens + 2
        else:
            # Try to fit a partial document if we have space
            remaining_tokens = max_tokens - total_tokens - 50  # Buffer for truncation message
            if remaining_tokens > 100:  # Only include if meaningful
                # Truncate at word boundary
                max_chars = remaining_tokens * 4
                truncated_doc = doc[:max_chars].rsplit(" ", 1)[0] + "..."
                truncated_docs.append(truncated_doc)
            break

    truncated_context = "\n\n".join(truncated_docs)

    logger.warning(
        f"Context truncated: {current_tokens} -> {estimate_tokens(truncated_context)} tokens "
        f"({len(documents)} -> {len(truncated_docs)} documents)"
    )

    return truncated_context, True

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
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)

    conn.commit()
    conn.close()


def save_message(conversation_id: str, role: str, content: str, sources: list[dict] = None):
    """Save a message to the database."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    timestamp = datetime.now().isoformat()
    sources_json = json.dumps(sources) if sources else None

    cursor.execute(
        "INSERT INTO messages (conversation_id, role, content, sources, timestamp) VALUES (?, ?, ?, ?, ?)",
        (conversation_id, role, content, sources_json, timestamp)
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
        "SELECT role, content, sources, timestamp FROM messages WHERE conversation_id = ? ORDER BY timestamp",
        (conversation_id,)
    )

    messages = []
    for row in cursor.fetchall():
        messages.append({
            "role": row[0],
            "content": row[1],
            "sources": json.loads(row[2]) if row[2] else None,
            "timestamp": row[3],
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

        result_queue.put({"response": response, "objects": objects, "error": None})
    except Exception as e:
        stdout_capture.flush()
        stderr_capture.flush()
        logger.exception("Elysia query error")
        result_queue.put({"response": None, "objects": None, "error": str(e)})
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
            # Send keepalive comment every 2 seconds
            now = asyncio.get_event_loop().time()
            if now - last_status_time > 2:
                yield f": keepalive\n\n"
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
            logger.info(f"Query complete, response length: {len(final_response)}")

            # If no events were captured, send the response as an assistant panel
            if event_count == 0 and final_response:
                yield f"data: {json.dumps({'type': 'assistant', 'content': final_response})}\n\n"

            yield f"data: {json.dumps({'type': 'complete', 'response': final_response, 'sources': sources})}\n\n"
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

    Args:
        question: The user's question
        provider: "ollama" for Nomic embeddings, "openai" for OpenAI embeddings

    Returns:
        Tuple of (retrieved objects, context string, retrieval time in ms)
    """
    global _weaviate_client

    retrieval_start = time.time()
    question_lower = question.lower()
    all_results = []

    # Get collection names for this provider
    collections = COLLECTION_NAMES.get(provider, COLLECTION_NAMES["ollama"])

    # For Ollama provider, compute query embedding client-side
    # WORKAROUND for Weaviate text2vec-ollama bug (#8406)
    query_vector = None
    if provider == "ollama":
        try:
            query_vector = embed_text(question)
        except Exception as e:
            logger.error(f"Failed to compute query embedding: {e}")

    # Known index/template titles to skip
    INDEX_TITLES = {
        'Decision Approval Record List',
        'Energy System Architecture - Decision Records',
        'What conventions to use in writing ADRs?',
        '{short title, representative of solved problem and found solution}'
    }

    # Search relevant collections based on question keywords
    # For Ollama provider, pass query_vector to hybrid search (workaround for text2vec-ollama bug)
    if any(term in question_lower for term in ["adr", "decision", "architecture"]):
        try:
            collection = _weaviate_client.collections.get(collections["adr"])

            # For "list all" type queries, fetch documents directly instead of semantic search
            is_list_query = any(term in question_lower for term in ["list", "all", "count", "how many"])

            if is_list_query:
                # Fetch all ADRs and filter to real ones
                results = collection.query.fetch_objects(limit=50)
                for obj in results.objects:
                    title = obj.properties.get("title", "")
                    if title in INDEX_TITLES or title.startswith('{'):
                        continue
                    decision = obj.properties.get("decision", "")
                    if not decision or len(decision) < 50:
                        continue
                    all_results.append({
                        "type": "ADR",
                        "title": title,
                        "content": decision[:600],
                    })
            else:
                # Regular semantic search
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=10, alpha=0.5
                )
                for obj in results.objects:
                    title = obj.properties.get("title", "")
                    if title in INDEX_TITLES or title.startswith('{'):
                        continue
                    content = obj.properties.get("full_text", "") or obj.properties.get("decision", "")
                    if len(content) < 100:
                        continue
                    all_results.append({
                        "type": "ADR",
                        "title": title,
                        "content": content[:800],
                    })
        except Exception as e:
            logger.warning(f"Error searching {collections['adr']}: {e}")

    if any(term in question_lower for term in ["principle", "governance", "esa"]):
        try:
            collection = _weaviate_client.collections.get(collections["principle"])
            results = collection.query.hybrid(
                query=question, vector=query_vector, limit=8, alpha=0.5
            )
            for obj in results.objects:
                content = obj.properties.get("full_text", "") or obj.properties.get("content", "")
                if len(content) < 50:
                    continue
                all_results.append({
                    "type": "Principle",
                    "title": obj.properties.get("title", ""),
                    "content": content[:800],
                })
        except Exception as e:
            logger.warning(f"Error searching {collections['principle']}: {e}")

    if any(term in question_lower for term in ["policy", "data governance", "compliance"]):
        try:
            collection = _weaviate_client.collections.get(collections["policy"])
            results = collection.query.hybrid(
                query=question, vector=query_vector, limit=8, alpha=0.5
            )
            for obj in results.objects:
                content = obj.properties.get("full_text", "") or obj.properties.get("content", "")
                if len(content) < 50:
                    continue
                all_results.append({
                    "type": "Policy",
                    "title": obj.properties.get("title", ""),
                    "content": content[:800],
                })
        except Exception as e:
            logger.warning(f"Error searching {collections['policy']}: {e}")

    if any(term in question_lower for term in ["vocab", "concept", "definition", "cim", "iec"]):
        try:
            collection = _weaviate_client.collections.get(collections["vocabulary"])
            results = collection.query.hybrid(
                query=question, vector=query_vector, limit=5, alpha=0.6
            )
            for obj in results.objects:
                all_results.append({
                    "type": "Vocabulary",
                    "label": obj.properties.get("pref_label", ""),
                    "definition": obj.properties.get("definition", ""),
                })
        except Exception as e:
            logger.warning(f"Error searching {collections['vocabulary']}: {e}")

    # If no specific collection matched, search all
    if not all_results:
        for coll_type in ["adr", "principle", "policy"]:
            try:
                coll_name = collections[coll_type]
                collection = _weaviate_client.collections.get(coll_name)
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=5, alpha=0.5
                )
                for obj in results.objects:
                    content = obj.properties.get("full_text", "") or obj.properties.get("content", "") or obj.properties.get("decision", "")
                    if len(content) < 50:
                        continue
                    all_results.append({
                        "type": coll_type.upper() if coll_type == "adr" else coll_type.title(),
                        "title": obj.properties.get("title", ""),
                        "content": content[:600],
                    })
            except Exception as e:
                logger.warning(f"Error searching {coll_name}: {e}")

    # Build context from retrieved results
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
    """Generate response using Ollama API with timing and context truncation.

    Automatically truncates context to fit within SmolLM3's ~8K token context window.

    Returns:
        Tuple of (response text, timing dict with truncation info)
    """
    import httpx

    start_time = time.time()

    # Combine and check total prompt size
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    original_tokens = estimate_tokens(full_prompt)

    # Truncate if needed (system prompt + user prompt combined)
    truncated_prompt, was_truncated = truncate_context(full_prompt, SMOLLM3_MAX_INPUT_TOKENS)

    if was_truncated:
        logger.info(
            f"SmolLM3 prompt truncated: {original_tokens} -> {estimate_tokens(truncated_prompt)} tokens"
        )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": truncated_prompt,
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
                "context_truncated": was_truncated,
                "original_tokens": original_tokens,
                "used_tokens": estimate_tokens(truncated_prompt),
            }

            # Strip <think> tags from response
            response_text = strip_think_tags(result.get("response", ""))
            return response_text, timing
    except Exception as e:
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
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

        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1000,
        )

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

        async for event in stream_elysia_response(request.message):
            yield event

            # Parse event to capture final response for saving
            try:
                data = json.loads(event.replace("data: ", "").strip())
                if data.get("type") == "complete":
                    final_response = data.get("response")
                    final_sources = data.get("sources", [])
            except:
                pass

        # Save assistant response
        if final_response:
            save_message(conversation_id, "assistant", final_response, final_sources)

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
