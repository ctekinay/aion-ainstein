"""Command-line interface for the AInstein RAG system."""

import asyncio
import logging
import warnings
from pathlib import Path

import structlog

# Suppress deprecation warnings from external dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="uvicorn")

import typer  # noqa: E402

try:
    from rich.console import Console  # noqa: E402
    from rich.markdown import Markdown  # noqa: E402
    from rich.panel import Panel  # noqa: E402
    from rich.progress import Progress, SpinnerColumn, TextColumn  # noqa: E402
    from rich.table import Table  # noqa: E402
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False
    Console = None  # type: ignore[assignment,misc]

from aion.agents.archimate_agent import ArchiMateAgent  # noqa: E402
from aion.agents.principle_agent import PrincipleAgent  # noqa: E402
from aion.agents.rag_agent import RAGAgent  # noqa: E402
from aion.agents.vocabulary_agent import VocabularyAgent  # noqa: E402
from aion.persona import Persona  # noqa: E402
from aion.routing import ExecutionModel, get_execution_model  # noqa: E402
from aion.config import settings  # noqa: E402
from aion.ingestion.client import get_weaviate_client, weaviate_client  # noqa: E402
from aion.ingestion.collections import CollectionManager  # noqa: E402
from aion.ingestion.ingestion import DataIngestionPipeline  # noqa: E402
from aion.memory.cli import app as memory_app  # noqa: E402
from aion.registry.cli import app as registry_app  # noqa: E402

# Set up structured logging via structlog.
# All structlog loggers route through stdlib (LoggerFactory), so a single
# ProcessorFormatter on the root handler covers both structlog and unconverted
# stdlib loggers — no dual output stream during incremental migration.
_log_level_int = getattr(logging, settings.log_level.upper(), logging.INFO)

_shared_processors: list = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
]

structlog.configure(
    processors=_shared_processors + [
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=structlog.make_filtering_bound_logger(_log_level_int),
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

_formatter = structlog.stdlib.ProcessorFormatter(
    processors=[
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.dev.ConsoleRenderer(),
    ],
    foreign_pre_chain=_shared_processors,
)
_handler = logging.StreamHandler()
_handler.setFormatter(_formatter)
_root_logger = logging.getLogger()
_root_logger.handlers = [_handler]
_root_logger.setLevel(_log_level_int)

logger = structlog.get_logger(__name__)

# CLI app
app = typer.Typer(
    name="aion",
    help="AInstein: Multi-Agent RAG System for Energy System Architecture",
    add_completion=False,
)
app.add_typer(memory_app, name="memory")
app.add_typer(registry_app, name="registry")
console = Console()


VALID_OPENAI_EMBEDDING_MODELS = [
    "text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"
]


@app.command()
def config():
    """Show current configuration (for debugging)."""
    console.print(Panel("Current Configuration", style="bold blue"))

    table = Table(title="Settings")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Status", style="yellow")

    # Weaviate settings
    table.add_row("WEAVIATE_URL", settings.weaviate_url, "OK")
    table.add_row("WEAVIATE_IS_LOCAL", str(settings.weaviate_is_local), "OK")

    # Global LLM settings
    table.add_row("LLM_PROVIDER", settings.llm_provider, "Global default")

    # Ollama
    table.add_row("OLLAMA_MODEL", settings.ollama_model, "OK")
    table.add_row("OLLAMA_EMBEDDING_MODEL", settings.ollama_embedding_model, "OK")

    def _mask_key(key: str | None) -> str:
        if not key:
            return "[dim]Not set[/dim]"
        if len(key) < 12:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    # GitHub Models
    gh_key_status = "OK" if settings.github_models_api_key else "[dim]Not set[/dim]"
    table.add_row("GITHUB_MODELS_API_KEY", _mask_key(settings.github_models_api_key), gh_key_status)
    table.add_row("GITHUB_MODELS_MODEL", settings.github_models_model, "OK")

    # OpenAI
    api_key_status = "OK" if settings.openai_api_key else "[dim]Not set[/dim]"
    table.add_row("OPENAI_API_KEY", _mask_key(settings.openai_api_key), api_key_status)
    table.add_row("OPENAI_CHAT_MODEL", settings.openai_chat_model, "OK")

    # Per-component overrides (only show when set)
    if settings.persona_provider or settings.persona_model:
        table.add_row("", "", "")
        table.add_row("PERSONA_PROVIDER", settings.effective_persona_provider, "Override")
        table.add_row("PERSONA_MODEL", settings.effective_persona_model, "Override")
    if settings.rag_provider or settings.rag_model:
        table.add_row("RAG_PROVIDER", settings.effective_rag_provider, "Override")
        table.add_row("RAG_MODEL", settings.effective_rag_model, "Override")

    # Effective configuration summary
    table.add_row("", "", "")
    table.add_row("Effective Persona", f"{settings.effective_persona_provider} / {settings.effective_persona_model}", "[dim]Resolved[/dim]")
    table.add_row("Effective RAG", f"{settings.effective_rag_provider} / {settings.effective_rag_model}", "[dim]Resolved[/dim]")

    console.print(table)

    # Run startup validation
    errors = settings.validate_startup()

    if errors:
        console.print("\n[bold red]Configuration Errors:[/bold red]")
        for error in errors:
            console.print(f"  [red]• {error}[/red]")
        console.print("\n[yellow]Fix these in your .env file and try again.[/yellow]")
    else:
        console.print("\n[green]Configuration is valid![/green]")


@app.command()
def init(
    recreate: bool = typer.Option(
        False, "--recreate", "-r", help="Recreate collections if they exist"
    ),
    batch_size: int = typer.Option(
        20, "--batch-size", "-b", help="Batch size for ingestion (smaller = slower but avoids timeout)"
    ),
    chunked: bool = typer.Option(
        False, "--chunked", help="Use section-based chunking (multiple chunks per document)"
    ),
):
    """Initialize Weaviate collections and ingest data."""
    console.print(Panel("Initializing AInstein RAG System", style="bold blue"))

    # Show current configuration
    console.print("\n[bold]Current Configuration:[/bold]")
    console.print(f"  LLM_PROVIDER: {settings.llm_provider}")
    console.print(f"  OLLAMA_EMBEDDING_MODEL: {settings.ollama_embedding_model}")
    console.print(f"  Batch size: {batch_size}")
    if chunked:
        console.print("  [blue]Chunked ingestion: section-based splitting enabled[/blue]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Connect to Weaviate
        task = progress.add_task("Connecting to Weaviate...", total=None)
        try:
            client = get_weaviate_client()
            progress.update(task, description="[green]Connected to Weaviate")
        except Exception as e:
            console.print(f"[red]Failed to connect to Weaviate: {e}")
            console.print("\n[yellow]Make sure Weaviate is running:")
            console.print("  docker compose up -d")
            raise typer.Exit(1)

        try:
            progress.update(task, description="Running data ingestion...")
            pipeline = DataIngestionPipeline(client)
            stats = pipeline.run_full_ingestion(
                recreate_collections=recreate,
                batch_size=batch_size,
                chunked=chunked,
            )

            progress.update(task, description="[green]Ingestion complete!")

        finally:
            client.close()

    # Display stats
    table = Table(title="Ingestion Statistics")
    table.add_column("Collection", style="cyan")
    table.add_column("Documents", style="green")

    table.add_row("Vocabulary Concepts", str(stats.get("vocabulary", 0)))
    table.add_row("ADRs", str(stats.get("adr", 0)))
    table.add_row("Principles", str(stats.get("principle", 0)))
    table.add_row("Policy Documents", str(stats.get("policy", 0)))

    console.print(table)

    if stats.get("errors"):
        console.print("\n[yellow]Errors encountered:")
        for error in stats["errors"]:
            console.print(f"  - {error}")


@app.command()
def status():
    """Show the status of Weaviate collections."""
    console.print(Panel("AInstein System Status", style="bold blue"))

    try:
        with weaviate_client() as client:
            manager = CollectionManager(client)
            stats = manager.get_collection_stats()

            table = Table(title="Collection Status")
            table.add_column("Collection", style="cyan")
            table.add_column("Exists", style="green")
            table.add_column("Document Count", style="yellow")

            for name, info in stats.items():
                exists = "Yes" if info["exists"] else "No"
                count = str(info["count"]) if info["exists"] else "-"
                table.add_row(name, exists, count)

            console.print(table)

    except Exception as e:
        console.print(f"[red]Failed to get status: {e}")
        raise typer.Exit(1)


@app.command()
def query(
    question: str = typer.Argument(..., help="Question to ask the system"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output including sources"
    ),
    persona: bool = typer.Option(
        False, "--persona", "-p",
        help="Route through the AInstein Persona (intent classification, orchestration)"
    ),
):
    """Query the knowledge base.

    By default, queries go directly to the RAG Agent (bypasses Persona).
    Use --persona to enable intent classification, multi-step orchestration,
    and routing to specialized agents (vocabulary, ArchiMate, principles).
    """
    console.print(Panel(f"Query: {question}", style="bold blue"))

    if persona:
        asyncio.run(_query_with_persona(question, verbose))
    else:
        console.print("[dim]Direct RAG mode (no Persona). Use --persona for full routing.[/dim]")
        _query_direct(question, verbose)


def _query_direct(question: str, verbose: bool):
    """Direct RAG query — bypasses Persona entirely."""
    try:
        with weaviate_client() as client:
            rag = RAGAgent(client)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Processing query...", total=None)
                response_text, results = asyncio.run(rag.query(question))
                progress.update(task, description="[green]Query complete!")

            console.print(Panel(Markdown(response_text), title="Answer", border_style="green"))
            _print_sources(results, verbose)

    except Exception as e:
        console.print(f"[red]Query failed: {e}")
        logger.exception("Query error")
        raise typer.Exit(1)


async def _query_with_persona(question: str, verbose: bool):
    """Full Persona pipeline — intent classification, routing, orchestration."""
    try:
        persona_instance = Persona()

        with console.status("Persona classifying intent...", spinner="dots"):
            result = await persona_instance.process(question, conversation_history=[])

        # Show classification
        table = Table(title="Persona Classification", show_header=False)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Intent", result.intent)
        table.add_row("Complexity", result.complexity)
        table.add_row("Skill Tags", ", ".join(result.skill_tags) if result.skill_tags else "[dim]none[/dim]")
        table.add_row("Doc Refs", ", ".join(result.doc_refs) if result.doc_refs else "[dim]none[/dim]")
        if result.steps:
            for i, step in enumerate(result.steps):
                table.add_row(f"Step {i + 1}", step.query)
        table.add_row("Latency", f"{result.latency_ms} ms")
        console.print(table)

        # Direct response (identity, off_topic, clarification)
        if result.direct_response:
            console.print(Panel(Markdown(result.direct_response), title="Direct Response", border_style="green"))
            return

        execution_model = get_execution_model(result.intent, result.skill_tags)
        console.print(f"[dim]Execution model: {execution_model}[/dim]\n")

        with weaviate_client() as client:
            if execution_model == ExecutionModel.VOCABULARY:
                agent = VocabularyAgent(client)
                with console.status("Vocabulary agent working...", spinner="dots"):
                    response, objects = await agent.query(
                        result.rewritten_query,
                        skill_tags=result.skill_tags,
                        doc_refs=result.doc_refs,
                    )
            elif execution_model == ExecutionModel.PRINCIPLE:
                agent = PrincipleAgent(client)
                with console.status("Principle agent working...", spinner="dots"):
                    response, objects = await agent.query(
                        result.rewritten_query,
                        skill_tags=result.skill_tags,
                        doc_refs=result.doc_refs,
                    )
            elif execution_model == ExecutionModel.ARCHIMATE:
                archimate = ArchiMateAgent()
                with console.status("ArchiMate agent working...", spinner="dots"):
                    response, objects = await archimate.query(
                        result.rewritten_query,
                        skill_tags=result.skill_tags,
                        doc_refs=result.doc_refs,
                    )
            elif result.complexity == "multi-step" and result.steps:
                response, objects = await _run_orchestrated(
                    client, question, result, verbose,
                )
            else:
                rag = RAGAgent(client)
                with console.status("RAG agent working...", spinner="dots"):
                    response, objects = await rag.query(
                        result.rewritten_query,
                        skill_tags=result.skill_tags,
                        doc_refs=result.doc_refs,
                        complexity=result.complexity,
                    )

        console.print(Panel(Markdown(response), title="Answer", border_style="green"))
        _print_sources(objects, verbose)

    except Exception as e:
        console.print(f"[red]Query failed: {e}")
        logger.exception("Query error")
        raise typer.Exit(1)


async def _run_orchestrated(
    client, original_question: str, result, verbose: bool,
) -> tuple[str, list[dict]]:
    """Execute multi-step orchestration from the CLI."""
    from aion.generation import stream_synthesis_response

    rag = RAGAgent(client)
    steps = result.steps
    step_results: list[str] = []
    all_objects: list[dict] = []

    for i, step in enumerate(steps):
        console.print(f"[bold]Step {i + 1}/{len(steps)}:[/bold] {step.query}")
        with console.status("  Searching knowledge base...", spinner="dots"):
            step_response, step_objects = await rag.query(
                step.query,
                skill_tags=step.skill_tags,
                doc_refs=step.doc_refs,
            )
        if step_response:
            step_results.append(step_response)
            all_objects.extend(step_objects)
        console.print(f"  [green]Done[/green] ({len(step_objects)} objects)")

    if not step_results:
        return "No results found for any step.", all_objects

    # Combine and synthesize
    combined = "\n\n".join(
        f"--- Result {i + 1}: {step.query} ---\n\n{text}"
        for i, (step, text) in enumerate(zip(steps, step_results))
    )

    console.print("\n[bold]Synthesizing results...[/bold]")
    accumulated: list[str] = []
    async for token in stream_synthesis_response(
        original_question, combined, result.synthesis_instruction,
    ):
        accumulated.append(token)

    synthesis = "".join(accumulated) or "Synthesis produced no output."
    return synthesis, all_objects


def _print_sources(results: list[dict] | None, verbose: bool):
    """Print source documents if verbose mode is enabled."""
    if not verbose or not results:
        return
    console.print("\n[bold]Sources:[/bold]")
    for r in results[:10]:
        if isinstance(r, dict):
            title = r.get("title") or r.get("label") or "Unknown"
            doc_type = r.get("type", "")
            console.print(f"  - [{doc_type}] {title}")
        elif isinstance(r, list):
            for item in r[:5]:
                if isinstance(item, dict):
                    title = item.get("title") or item.get("label") or "Unknown"
                    doc_type = item.get("type", "")
                    console.print(f"  - [{doc_type}] {title}")


@app.command()
def search(
    query_text: str = typer.Argument(..., help="Search query"),
    collection: str = typer.Option(
        "all", "--collection", "-c",
        help="Collection to search (vocabulary, adr, principle, policy, all)"
    ),
    limit: int = typer.Option(5, "--limit", "-n", help="Maximum results"),
):
    """Search the knowledge base directly via hybrid search."""
    console.print(Panel(f"Search: {query_text}", style="bold blue"))

    try:
        from aion.ingestion.embeddings import embed_text

        with weaviate_client() as client:
            # Always compute client-side embeddings
            query_vector = None
            try:
                query_vector = embed_text(query_text)
            except Exception as e:
                logger.warning(f"Failed to compute query embedding: {e}")

            collection_map = {
                "vocabulary": "Vocabulary",
                "adr": "ArchitecturalDecision",
                "principle": "Principle",
                "policy": "PolicyDocument",
            }

            if collection == "all":
                search_collections = list(collection_map.items())
            elif collection in collection_map:
                search_collections = [(collection, collection_map[collection])]
            else:
                console.print(f"[red]Unknown collection: {collection}")
                raise typer.Exit(1)

            for coll_name, coll_base in search_collections:
                try:
                    wv_collection = client.collections.get(coll_base)
                    results = wv_collection.query.hybrid(
                        query=query_text,
                        vector=query_vector,
                        limit=limit,
                        alpha=settings.alpha_default,
                    )

                    if results.objects:
                        table = Table(title=f"{coll_name.title()} Results")
                        table.add_column("Title/Label", style="cyan", max_width=40)
                        table.add_column("Preview", style="white", max_width=60)

                        for obj in results.objects:
                            props = obj.properties
                            title = props.get("title") or props.get("pref_label") or "Unknown"
                            content = props.get("content") or props.get("definition") or props.get("full_text") or ""
                            preview = content[:100] + "..." if len(content) > 100 else content
                            table.add_row(title, preview)

                        console.print(table)
                        console.print()
                except Exception as e:
                    logger.warning(f"Search failed for {coll_base}: {e}")

    except Exception as e:
        console.print(f"[red]Search failed: {e}")
        raise typer.Exit(1)


@app.command()
def agents():
    """List available knowledge domains and collections."""
    console.print(Panel("Knowledge Domains", style="bold blue"))

    domains = [
        ("Vocabulary", "Vocabulary", "SKOS/OWL vocabulary concepts from IEC standards (CIM, 61970, 61968, 62325)"),
        ("Architecture", "ArchitecturalDecision", "Architectural Decision Records (ADRs) and design rationale"),
        ("Principles", "Principle", "Architecture and governance principles (ESA + Data Office)"),
        ("Policy", "PolicyDocument", "Data governance and compliance policy documents"),
    ]

    for name, collection, description in domains:
        console.print(f"\n[bold cyan]{name}[/bold cyan]")
        console.print(f"  Collection: {collection}")
        console.print(f"  {description}")


@app.command()
def interactive():
    """Start an interactive query session."""
    console.print(Panel(
        "AInstein Interactive Mode\n"
        "Type 'quit' or 'exit' to end the session.\n"
        "Type 'help' for available commands.",
        style="bold blue"
    ))

    try:
        with weaviate_client() as client:
            rag = RAGAgent(client)

            while True:
                try:
                    user_input = console.input("\n[bold green]Question>[/bold green] ").strip()

                    if not user_input:
                        continue

                    if user_input.lower() in ("quit", "exit", "q"):
                        console.print("[dim]Goodbye![/dim]")
                        break

                    if user_input.lower() == "help":
                        console.print("""
[bold]Available commands:[/bold]
  quit, exit, q  - Exit interactive mode
  help           - Show this help message
  status         - Show collection status

[bold]Just type your question to query the knowledge base.[/bold]
                        """)
                        continue

                    if user_input.lower() == "status":
                        manager = CollectionManager(client)
                        stats = manager.get_collection_stats()
                        for name, info in stats.items():
                            status = f"{info['count']} docs" if info["exists"] else "not created"
                            console.print(f"  {name}: {status}")
                        continue

                    # Process query
                    with console.status("Thinking...", spinner="dots"):
                        response_text, results = asyncio.run(rag.query(user_input))

                    # Display response
                    result_count = len(results) if results else 0
                    console.print(f"\n[dim]Retrieved {result_count} documents[/dim]")
                    console.print(Panel(Markdown(response_text), border_style="green"))

                except KeyboardInterrupt:
                    console.print("\n[dim]Use 'quit' to exit.[/dim]")
                    continue

    except Exception as e:
        console.print(f"[red]Error: {e}")
        raise typer.Exit(1)


@app.command()
def rag():
    """Start RAG agent interactive session (Pydantic AI-based)."""
    console.print(Panel(
        "AInstein RAG Agent Mode\n"
        "Using Pydantic AI agent with RAG tools\n"
        "Type 'quit' or 'exit' to end the session.",
        style="bold magenta"
    ))

    try:
        with weaviate_client() as client:
            rag_agent = RAGAgent(client)
            console.print("[green]RAG agent initialized[/green]")
            console.print("[dim]Available tools: search_architecture_decisions, search_principles,[/dim]")
            console.print("[dim]  search_policies, list_adrs, list_principles,[/dim]")
            console.print("[dim]  list_policies, list_dars, search_by_team, request_data[/dim]\n")

            while True:
                try:
                    user_input = console.input("\n[bold magenta]RAG>[/bold magenta] ").strip()

                    if not user_input:
                        continue

                    if user_input.lower() in ("quit", "exit", "q"):
                        console.print("[dim]Goodbye![/dim]")
                        break

                    with console.status("RAG agent thinking...", spinner="dots"):
                        response, objects = asyncio.run(rag_agent.query(user_input))

                    console.print(Panel(Markdown(response), border_style="green"))

                    if objects:
                        console.print(f"[dim]Retrieved {len(objects)} objects[/dim]")

                except KeyboardInterrupt:
                    console.print("\n[dim]Use 'quit' to exit.[/dim]")
                    continue

    except Exception as e:
        console.print(f"[red]Error: {e}")
        logger.exception("RAG agent error")
        raise typer.Exit(1)


@app.command()
def vocabulary(
    query_text: str = typer.Argument(..., help="Vocabulary term to look up"),
):
    """Search SKOSMOS vocabulary (bypasses Persona and RAG Agent)."""
    try:
        with weaviate_client() as client:
            agent = VocabularyAgent(client)
            with console.status("Looking up vocabulary...", spinner="dots"):
                response, objects = asyncio.run(agent.query(query_text))

            console.print(Panel(Markdown(response), border_style="cyan"))

            if objects:
                console.print(f"[dim]Retrieved {len(objects)} KB objects (Tier 2 fallback)[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}")
        logger.exception("Vocabulary agent error")
        raise typer.Exit(1)


@app.command()
def archimate(
    query_text: str = typer.Argument(..., help="ArchiMate query (validate, inspect, merge)"),
):
    """Query the ArchiMate agent (bypasses Persona and RAG Agent)."""
    try:
        agent = ArchiMateAgent()
        with console.status("Processing ArchiMate model...", spinner="dots"):
            response, objects = asyncio.run(agent.query(query_text))

        console.print(Panel(Markdown(response), border_style="cyan"))

        if objects:
            console.print(f"[dim]Retrieved {len(objects)} objects[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}")
        logger.exception("ArchiMate agent error")
        raise typer.Exit(1)


@app.command(name="capability-report")
def capability_report(
    limit: int = typer.Option(100, "--limit", "-n", help="Maximum gaps to show"),
):
    """Show logged capability gaps from request_data tool calls."""
    from aion.storage.capability_store import get_capability_gaps

    gaps = get_capability_gaps(limit=limit)

    if not gaps:
        console.print("[dim]No capability gaps logged yet.[/dim]")
        return

    # Summary by agent
    by_agent: dict[str, int] = {}
    for gap in gaps:
        agent = gap.get("agent", "unknown")
        by_agent[agent] = by_agent.get(agent, 0) + 1

    summary_table = Table(title=f"Capability Gaps ({len(gaps)} total)")
    summary_table.add_column("Agent", style="cyan")
    summary_table.add_column("Count", style="yellow")
    for agent, count in sorted(by_agent.items(), key=lambda x: -x[1]):
        summary_table.add_row(agent, str(count))
    console.print(summary_table)

    # Detail table
    detail_table = Table(title="Recent Gaps")
    detail_table.add_column("Agent", style="cyan", max_width=12)
    detail_table.add_column("Description", style="white", max_width=60)
    detail_table.add_column("Time", style="dim", max_width=20)
    for gap in gaps[:20]:
        detail_table.add_row(
            gap.get("agent", "?"),
            gap.get("description", "")[:60],
            gap.get("created_at", "")[:19],
        )
    console.print(detail_table)


@app.command()
def chat(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(settings.server_port, "--port", "-p", help="Port to bind to"),
):
    """Start the local chat web interface.

    A clean, simple chat UI for AInstein - Energy System Architect Assistant.
    Access at http://localhost:8081 after starting.
    """
    console.print(Panel(
        "AInstein - Energy System Architect Assistant\n"
        f"Starting web interface at http://{host}:{port}",
        style="bold cyan"
    ))

    try:
        import uvicorn

        from aion.chat_ui import app as chat_app

        console.print("[green]Starting server...[/green]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        uvicorn.run(chat_app, host=host, port=port, log_level="info", loop="asyncio")

    except ImportError as e:
        console.print(f"[red]Import error: {e}[/red]")
        console.print("[yellow]Make sure uvicorn is installed: pip install uvicorn[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to start chat server: {e}[/red]")
        logger.exception("Chat server error")
        raise typer.Exit(1)


@app.command()
def evaluate(
    categories: str | None = typer.Option(
        None, "--categories", "-c",
        help="Comma-separated list of categories to test (vocabulary,adr,principle,cross_domain,general)"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o",
        help="Output file path for detailed JSON results"
    ),
    base_url: str = typer.Option(
        f"http://127.0.0.1:{settings.server_port}", "--url", "-u",
        help="Base URL of the chat API server"
    ),
):
    """Run evaluation comparing Ollama vs OpenAI RAG performance.

    IMPORTANT: The chat server must be running before running evaluation.
    Start it with: python -m aion.cli chat

    Example usage:
        python -m aion.cli evaluate
        python -m aion.cli evaluate --categories vocabulary,adr
        python -m aion.cli evaluate --output results.json
    """
    import asyncio

    from aion.evaluation import RAGEvaluator

    console.print(Panel(
        "[bold]RAG Evaluation: Ollama vs OpenAI[/bold]\n\n"
        "Comparing retrieval quality, latency, and answer quality",
        title="AInstein Evaluation",
        style="bold blue"
    ))

    # Parse categories
    category_list = None
    if categories:
        category_list = [c.strip() for c in categories.split(",")]
        console.print(f"[dim]Filtering by categories: {category_list}[/dim]")

    # Check if server is running
    import httpx
    try:
        response = httpx.get(f"{base_url}/health", timeout=settings.timeout_health_check)
        if response.status_code != 200:
            raise Exception("Server not healthy")
    except Exception:
        console.print("[red]Error: Chat server is not running![/red]")
        console.print("[yellow]Start it with: python -m aion.cli chat[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]Connected to server at {base_url}[/green]\n")

    # Run evaluation
    evaluator = RAGEvaluator(base_url=base_url)

    async def run_evaluation():
        return await evaluator.run_all(categories=category_list)

    console.print("[dim]Running evaluation (this may take several minutes)...[/dim]")

    try:
        asyncio.run(run_evaluation())
        console.print("[green]Evaluation complete![/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Evaluation error")
        raise typer.Exit(1)

    # Display summary
    summary = evaluator.get_summary()

    console.print("\n[bold]Evaluation Summary[/bold]\n")

    # Create comparison table
    table = Table(title="Provider Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Ollama (Local)", style="yellow")
    table.add_column("OpenAI (Cloud)", style="green")

    ollama = summary["ollama"]
    openai = summary["openai"]

    table.add_row(
        "Total Test Cases",
        str(ollama["total_cases"]),
        str(openai["total_cases"])
    )
    table.add_row(
        "Successful",
        str(ollama["successful"]),
        str(openai["successful"])
    )
    table.add_row(
        "Errors",
        str(ollama["errors"]),
        str(openai["errors"])
    )
    table.add_row(
        "Avg Term Recall",
        f"{ollama['avg_term_recall']:.1%}",
        f"{openai['avg_term_recall']:.1%}"
    )
    table.add_row(
        "Avg Source Recall",
        f"{ollama['avg_source_recall']:.1%}",
        f"{openai['avg_source_recall']:.1%}"
    )
    table.add_row(
        "Avg Retrieval Latency",
        f"{ollama['avg_retrieval_latency_ms']}ms",
        f"{openai['avg_retrieval_latency_ms']}ms"
    )
    table.add_row(
        "Avg Generation Latency",
        f"{ollama['avg_generation_latency_ms']}ms",
        f"{openai['avg_generation_latency_ms']}ms"
    )
    table.add_row(
        "Avg Total Latency",
        f"{ollama['avg_total_latency_ms']}ms",
        f"{openai['avg_total_latency_ms']}ms"
    )

    if ollama.get("context_truncations", 0) > 0:
        table.add_row(
            "Context Truncations",
            f"[yellow]{ollama['context_truncations']}[/yellow]",
            "N/A"
        )

    console.print(table)

    # Show per-test-case results
    console.print("\n[bold]Per-Test-Case Results[/bold]\n")

    results_table = Table(title="Individual Test Cases")
    results_table.add_column("ID", style="dim")
    results_table.add_column("Category")
    results_table.add_column("Ollama Term Recall", style="yellow")
    results_table.add_column("OpenAI Term Recall", style="green")
    results_table.add_column("Ollama Latency", style="yellow")
    results_table.add_column("OpenAI Latency", style="green")

    for result in evaluator.results:
        ollama_recall = f"{result.ollama.term_recall:.0%}" if result.ollama and not result.ollama.error else "ERR"
        openai_recall = f"{result.openai.term_recall:.0%}" if result.openai and not result.openai.error else "ERR"
        ollama_latency = f"{result.ollama.total_latency_ms}ms" if result.ollama else "N/A"
        openai_latency = f"{result.openai.total_latency_ms}ms" if result.openai else "N/A"

        results_table.add_row(
            result.test_case_id,
            result.category,
            ollama_recall,
            openai_recall,
            ollama_latency,
            openai_latency
        )

    console.print(results_table)

    # Export if requested
    if output:
        evaluator.export_results(output)
        console.print(f"\n[green]Detailed results exported to: {output}[/green]")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
