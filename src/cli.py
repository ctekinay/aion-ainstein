"""Command-line interface for the AION-AINSTEIN RAG system."""

import asyncio
import logging
import sys
import warnings
from pathlib import Path
from typing import Optional

# Suppress deprecation warnings from external dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="spacy")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="uvicorn")

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import settings
from .weaviate.client import get_weaviate_client, weaviate_client
from .weaviate.collections import CollectionManager
from .weaviate.ingestion import DataIngestionPipeline
from .agents import OrchestratorAgent

# Set up logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# CLI app
app = typer.Typer(
    name="aion",
    help="AION-AINSTEIN: Multi-Agent RAG System for Energy System Architecture",
    add_completion=False,
)
console = Console()


# Valid OpenAI models supported by Weaviate
VALID_OPENAI_CHAT_MODELS = [
    "gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-3.5-turbo-1106",
    "gpt-4", "gpt-4-32k", "gpt-4-1106-preview", "gpt-4o", "gpt-4o-mini",
    "gpt-5.1", "gpt-5.2", "gpt-5.2-chat-latest",
]
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

    # OpenAI settings
    api_key_status = "OK" if settings.openai_api_key else "[red]MISSING[/red]"
    api_key_display = f"{settings.openai_api_key[:10]}..." if settings.openai_api_key else "[red]Not set[/red]"
    table.add_row("OPENAI_API_KEY", api_key_display, api_key_status)

    embedding_status = "OK" if settings.openai_embedding_model in VALID_OPENAI_EMBEDDING_MODELS else "[red]INVALID[/red]"
    table.add_row("OPENAI_EMBEDDING_MODEL", settings.openai_embedding_model, embedding_status)

    chat_status = "OK" if settings.openai_chat_model in VALID_OPENAI_CHAT_MODELS else "[red]INVALID[/red]"
    table.add_row("OPENAI_CHAT_MODEL", settings.openai_chat_model, chat_status)

    console.print(table)

    # Show validation errors
    errors = []
    if not settings.openai_api_key:
        errors.append("OPENAI_API_KEY is not set")
    if settings.openai_embedding_model not in VALID_OPENAI_EMBEDDING_MODELS:
        errors.append(f"OPENAI_EMBEDDING_MODEL '{settings.openai_embedding_model}' is not valid. Use one of: {', '.join(VALID_OPENAI_EMBEDDING_MODELS)}")
    if settings.openai_chat_model not in VALID_OPENAI_CHAT_MODELS:
        errors.append(f"OPENAI_CHAT_MODEL '{settings.openai_chat_model}' is not valid. Use one of: {', '.join(VALID_OPENAI_CHAT_MODELS)}")

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
    include_openai: bool = typer.Option(
        False, "--include-openai", "-o", help="Also create and populate OpenAI-embedded collections for comparison"
    ),
    batch_size: int = typer.Option(
        20, "--batch-size", "-b", help="Batch size for Ollama/Nomic collections (smaller = slower but avoids timeout)"
    ),
    openai_batch_size: int = typer.Option(
        100, "--openai-batch-size", help="Batch size for OpenAI collections (can be larger since API is fast)"
    ),
    enable_chunking: bool = typer.Option(
        False, "--chunking", "-c", help="Enable hierarchical section-based chunking for better retrieval quality"
    ),
):
    """Initialize Weaviate collections and ingest data."""
    console.print(Panel("Initializing AION-AINSTEIN RAG System", style="bold blue"))

    # Show current configuration
    console.print("\n[bold]Current Configuration:[/bold]")
    console.print(f"  LLM_PROVIDER: {settings.llm_provider}")
    if settings.llm_provider == "ollama":
        console.print(f"  OLLAMA_MODEL: {settings.ollama_model}")
        console.print(f"  OLLAMA_EMBEDDING_MODEL: {settings.ollama_embedding_model}")
    else:
        console.print(f"  OPENAI_CHAT_MODEL: {settings.openai_chat_model}")
        console.print(f"  OPENAI_EMBEDDING_MODEL: {settings.openai_embedding_model}")
    console.print(f"  Batch sizes: Ollama={batch_size}, OpenAI={openai_batch_size}")
    if enable_chunking:
        console.print(f"  [green]Chunking: ENABLED (section-level chunks for better retrieval)[/green]")
    else:
        console.print(f"  Chunking: disabled (use --chunking to enable)")
    if include_openai:
        console.print(f"  [blue]Including OpenAI collections for comparison[/blue]")

    # Validate configuration before proceeding
    errors = []

    # OpenAI settings only required if provider is openai OR if --include-openai flag is used
    needs_openai = settings.llm_provider == "openai" or include_openai

    if needs_openai:
        if not settings.openai_api_key:
            errors.append("OPENAI_API_KEY is not set in .env file (required for OpenAI provider or --include-openai)")
        if settings.openai_chat_model not in VALID_OPENAI_CHAT_MODELS:
            errors.append(
                f"OPENAI_CHAT_MODEL '{settings.openai_chat_model}' is not valid.\n"
                f"    Valid models: {', '.join(VALID_OPENAI_CHAT_MODELS)}\n"
                f"    Please update your .env file."
            )
        if settings.openai_embedding_model not in VALID_OPENAI_EMBEDDING_MODELS:
            errors.append(
                f"OPENAI_EMBEDDING_MODEL '{settings.openai_embedding_model}' is not valid.\n"
                f"    Valid models: {', '.join(VALID_OPENAI_EMBEDDING_MODELS)}"
            )

    if errors:
        console.print("\n[bold red]Configuration Errors:[/bold red]")
        for error in errors:
            console.print(f"  [red]• {error}[/red]")
        console.print("\n[yellow]Please check your .env file and ensure it contains:[/yellow]")
        console.print("  OPENAI_API_KEY=sk-your-key-here")
        console.print("  OPENAI_EMBEDDING_MODEL=text-embedding-3-small")
        console.print("  OPENAI_CHAT_MODEL=gpt-4o-mini")
        raise typer.Exit(1)

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
            # Run ingestion
            if include_openai:
                progress.update(task, description="Running data ingestion (including OpenAI collections)...")
            else:
                progress.update(task, description="Running data ingestion...")
            pipeline = DataIngestionPipeline(client)
            stats = pipeline.run_full_ingestion(
                recreate_collections=recreate,
                batch_size=batch_size,
                openai_batch_size=openai_batch_size,
                include_openai=include_openai,
                enable_chunking=enable_chunking,
            )

            progress.update(task, description="[green]Ingestion complete!")

        finally:
            client.close()

    # Display stats
    table = Table(title="Ingestion Statistics")
    table.add_column("Collection", style="cyan")
    table.add_column("Documents (Local)", style="green")
    if include_openai:
        table.add_column("Documents (OpenAI)", style="blue")

    if include_openai:
        table.add_row("Vocabulary Concepts", str(stats.get("vocabulary", 0)), str(stats.get("vocabulary_openai", 0)))
        table.add_row("ADRs", str(stats.get("adr", 0)), str(stats.get("adr_openai", 0)))
        table.add_row("Principles", str(stats.get("principle", 0)), str(stats.get("principle_openai", 0)))
        table.add_row("Policy Documents", str(stats.get("policy", 0)), str(stats.get("policy_openai", 0)))
    else:
        table.add_row("Vocabulary Concepts", str(stats.get("vocabulary", 0)))
        table.add_row("ADRs", str(stats.get("adr", 0)))
        table.add_row("Principles", str(stats.get("principle", 0)))
        table.add_row("Policy Documents", str(stats.get("policy", 0)))

    console.print(table)

    if stats.get("chunking_enabled"):
        console.print("\n[green]✓ Chunking was enabled - documents split into section-level chunks[/green]")

    if stats.get("errors"):
        console.print("\n[yellow]Errors encountered:")
        for error in stats["errors"]:
            console.print(f"  - {error}")


@app.command()
def status():
    """Show the status of Weaviate collections."""
    console.print(Panel("AION-AINSTEIN System Status", style="bold blue"))

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
    agent: Optional[str] = typer.Option(
        None, "--agent", "-a", help="Specific agent to use (vocabulary, architecture, policy)"
    ),
    all_agents: bool = typer.Option(
        False, "--all", help="Query all agents"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output including sources"
    ),
):
    """Query the knowledge base using the multi-agent system."""
    console.print(Panel(f"Query: {question}", style="bold blue"))

    try:
        with weaviate_client() as client:
            orchestrator = OrchestratorAgent(client)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Processing query...", total=None)

                # Run the async query
                agent_names = [agent] if agent else None
                response = asyncio.run(
                    orchestrator.query(
                        question,
                        use_all_agents=all_agents,
                        agent_names=agent_names,
                    )
                )

                progress.update(task, description="[green]Query complete!")

            # Display routing decision
            console.print(f"\n[dim]Agents used: {', '.join(response.routing_decision.get('agents', []))}[/dim]")
            console.print(f"[dim]Routing reason: {response.routing_decision.get('reason', '')}[/dim]")
            console.print(f"[dim]Confidence: {response.confidence:.2f}[/dim]\n")

            # Display answer
            console.print(Panel(Markdown(response.answer), title="Answer", border_style="green"))

            # Display sources if verbose
            if verbose and response.agent_responses:
                console.print("\n[bold]Sources:[/bold]")
                for agent_response in response.agent_responses:
                    if agent_response.sources:
                        console.print(f"\n[cyan]{agent_response.agent_name}:[/cyan]")
                        for source in agent_response.sources[:5]:
                            title = source.get("title") or source.get("label") or "Unknown"
                            console.print(f"  - {title}")

    except Exception as e:
        console.print(f"[red]Query failed: {e}")
        logger.exception("Query error")
        raise typer.Exit(1)


@app.command()
def search(
    query_text: str = typer.Argument(..., help="Search query"),
    collection: str = typer.Option(
        "all", "--collection", "-c",
        help="Collection to search (vocabulary, adr, principle, policy, all)"
    ),
    limit: int = typer.Option(5, "--limit", "-n", help="Maximum results"),
):
    """Search the knowledge base directly."""
    console.print(Panel(f"Search: {query_text}", style="bold blue"))

    try:
        with weaviate_client() as client:
            orchestrator = OrchestratorAgent(client)

            if collection == "all":
                results = asyncio.run(orchestrator.search_all(query_text, limit=limit))
            else:
                agent_map = {
                    "vocabulary": orchestrator.vocabulary_agent,
                    "adr": orchestrator.architecture_agent,
                    "principle": orchestrator.architecture_agent,  # Principles are under architecture
                    "policy": orchestrator.policy_agent,
                }
                agent = agent_map.get(collection)
                if not agent:
                    console.print(f"[red]Unknown collection: {collection}")
                    raise typer.Exit(1)

                results = {collection: agent.hybrid_search(query_text, limit=limit)}

            # Display results
            for coll_name, coll_results in results.items():
                if coll_results:
                    table = Table(title=f"{coll_name.title()} Results")
                    table.add_column("Title/Label", style="cyan", max_width=40)
                    table.add_column("Preview", style="white", max_width=60)

                    for doc in coll_results:
                        title = doc.get("title") or doc.get("pref_label") or "Unknown"
                        content = doc.get("content") or doc.get("definition") or doc.get("full_text") or ""
                        preview = content[:100] + "..." if len(content) > 100 else content
                        table.add_row(title, preview)

                    console.print(table)
                    console.print()

    except Exception as e:
        console.print(f"[red]Search failed: {e}")
        raise typer.Exit(1)


@app.command()
def agents():
    """List available agents and their capabilities."""
    console.print(Panel("Available Agents", style="bold blue"))

    try:
        with weaviate_client() as client:
            orchestrator = OrchestratorAgent(client)
            agent_info = orchestrator.get_agent_info()

            for info in agent_info:
                console.print(f"\n[bold cyan]{info['name']}[/bold cyan]")
                console.print(f"  Collection: {info['collection']}")
                console.print(f"  Description: {info['description']}")

    except Exception as e:
        console.print(f"[red]Failed to list agents: {e}")
        raise typer.Exit(1)


@app.command()
def interactive():
    """Start an interactive query session."""
    console.print(Panel(
        "AION-AINSTEIN Interactive Mode\n"
        "Type 'quit' or 'exit' to end the session.\n"
        "Type 'help' for available commands.",
        style="bold blue"
    ))

    try:
        with weaviate_client() as client:
            orchestrator = OrchestratorAgent(client)

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
  agents         - List available agents
  status         - Show collection status

[bold]Query modifiers:[/bold]
  @vocabulary <question>    - Query only vocabulary agent
  @architecture <question>  - Query only architecture agent
  @policy <question>        - Query only policy agent
  @all <question>           - Query all agents
                        """)
                        continue

                    if user_input.lower() == "agents":
                        for info in orchestrator.get_agent_info():
                            console.print(f"  [cyan]{info['name']}[/cyan]: {info['description'][:60]}...")
                        continue

                    if user_input.lower() == "status":
                        manager = CollectionManager(client)
                        stats = manager.get_collection_stats()
                        for name, info in stats.items():
                            status = f"{info['count']} docs" if info["exists"] else "not created"
                            console.print(f"  {name}: {status}")
                        continue

                    # Parse agent directive
                    agent_names = None
                    use_all = False

                    if user_input.startswith("@"):
                        parts = user_input.split(" ", 1)
                        directive = parts[0][1:].lower()
                        user_input = parts[1] if len(parts) > 1 else ""

                        if directive == "all":
                            use_all = True
                        elif directive in ("vocabulary", "architecture", "policy"):
                            agent_names = [directive]

                    if not user_input:
                        console.print("[yellow]Please provide a question.[/yellow]")
                        continue

                    # Process query
                    with console.status("Thinking...", spinner="dots"):
                        response = asyncio.run(
                            orchestrator.query(
                                user_input,
                                use_all_agents=use_all,
                                agent_names=agent_names,
                            )
                        )

                    # Display response
                    console.print(f"\n[dim]Agents: {', '.join(response.routing_decision.get('agents', []))} | Confidence: {response.confidence:.2f}[/dim]")
                    console.print(Panel(Markdown(response.answer), border_style="green"))

                except KeyboardInterrupt:
                    console.print("\n[dim]Use 'quit' to exit.[/dim]")
                    continue

    except Exception as e:
        console.print(f"[red]Error: {e}")
        raise typer.Exit(1)


@app.command()
def elysia():
    """Start Elysia agentic RAG interactive session (decision tree-based)."""
    console.print(Panel(
        "AION-AINSTEIN Agent Mode\n"
        "Using agentic decision tree framework\n"
        "Type 'quit' or 'exit' to end the session.",
        style="bold magenta"
    ))

    try:
        from .elysia_agents import ElysiaRAGSystem, ELYSIA_AVAILABLE, configure_elysia_from_settings

        if not ELYSIA_AVAILABLE:
            console.print("[red]Elysia not installed. Run: pip install elysia-ai[/red]")
            raise typer.Exit(1)

        with weaviate_client() as client:
            configure_elysia_from_settings()
            elysia_system = ElysiaRAGSystem(client)
            console.print("[green]Agent system initialized with custom tools[/green]")
            console.print("[dim]Available tools: search_vocabulary, search_architecture_decisions,[/dim]")
            console.print("[dim]                  search_principles, search_policies, list_all_adrs,[/dim]")
            console.print("[dim]                  list_all_principles, get_collection_stats[/dim]\n")

            while True:
                try:
                    user_input = console.input("\n[bold magenta]AInstein>[/bold magenta] ").strip()

                    if not user_input:
                        continue

                    if user_input.lower() in ("quit", "exit", "q"):
                        console.print("[dim]Goodbye![/dim]")
                        break

                    # Process with Elysia
                    with console.status("Thinking...", spinner="dots"):
                        response, objects = asyncio.run(elysia_system.query(user_input))

                    # Note: Elysia's framework already displays the response via its "Assistant response" panels
                    # No need to display the concatenated response again - it would be redundant

                    if objects:
                        console.print(f"[dim]Retrieved {len(objects)} objects[/dim]")

                except KeyboardInterrupt:
                    console.print("\n[dim]Use 'quit' to exit.[/dim]")
                    continue

    except ImportError as e:
        console.print(f"[red]Elysia import error: {e}[/red]")
        console.print("[yellow]Make sure to install: pip install elysia-ai dspy-ai[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}")
        logger.exception("Elysia error")
        raise typer.Exit(1)


@app.command()
def start_elysia_server():
    """Start the full Elysia web application."""
    console.print(Panel("Starting AInstein Web Server", style="bold magenta"))

    try:
        import subprocess
        console.print("[dim]Running: elysia start[/dim]")
        console.print("[yellow]Note: Configure your API keys in the Elysia settings page[/yellow]")
        subprocess.run(["elysia", "start"], check=True)
    except FileNotFoundError:
        console.print("[red]Elysia CLI not found. Install with: pip install elysia-ai[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to start Elysia: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def chat(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8081, "--port", "-p", help="Port to bind to"),
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
        from .chat_ui import app as chat_app

        console.print("[green]Starting server...[/green]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        # Use asyncio loop instead of uvloop for Elysia compatibility
        # (Elysia's tree patching doesn't work with uvloop)
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
    categories: Optional[str] = typer.Option(
        None, "--categories", "-c",
        help="Comma-separated list of categories to test (vocabulary,adr,principle,cross_domain,general)"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output file path for detailed JSON results"
    ),
    base_url: str = typer.Option(
        "http://127.0.0.1:8081", "--url", "-u",
        help="Base URL of the chat API server"
    ),
):
    """Run evaluation comparing Ollama vs OpenAI RAG performance.

    IMPORTANT: The chat server must be running before running evaluation.
    Start it with: python -m src.cli chat

    Example usage:
        python -m src.cli evaluate
        python -m src.cli evaluate --categories vocabulary,adr
        python -m src.cli evaluate --output results.json
    """
    import asyncio
    from .evaluation import RAGEvaluator

    console.print(Panel(
        "[bold]RAG Evaluation: Ollama vs OpenAI[/bold]\n\n"
        "Comparing retrieval quality, latency, and answer quality",
        title="AION-AINSTEIN Evaluation",
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
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        if response.status_code != 200:
            raise Exception("Server not healthy")
    except Exception:
        console.print("[red]Error: Chat server is not running![/red]")
        console.print("[yellow]Start it with: python -m src.cli chat[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]Connected to server at {base_url}[/green]\n")

    # Run evaluation
    evaluator = RAGEvaluator(base_url=base_url)

    async def run_evaluation():
        return await evaluator.run_all(categories=category_list)

    console.print("[dim]Running evaluation (this may take several minutes)...[/dim]")

    try:
        results = asyncio.run(run_evaluation())
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
