"""Elysia-based agentic RAG system for AION-AINSTEIN.

Uses Weaviate's Elysia framework for decision tree-based tool selection
and agentic query processing.
"""

import logging
from typing import Optional, Any

from weaviate import WeaviateClient
from weaviate.classes.query import Filter

from .config import settings
from .weaviate.embeddings import embed_text

logger = logging.getLogger(__name__)

# Import elysia components
try:
    import elysia
    from elysia import tool, Tree
    ELYSIA_AVAILABLE = True
except ImportError as e:
    ELYSIA_AVAILABLE = False
    logger.warning(f"elysia-ai import failed: {e}")
except Exception as e:
    ELYSIA_AVAILABLE = False
    logger.warning(f"elysia-ai error: {e}")


class ElysiaRAGSystem:
    """Elysia-based agentic RAG system with custom tools for energy domain."""

    def __init__(self, client: WeaviateClient):
        """Initialize the Elysia RAG system.

        Args:
            client: Connected Weaviate client
        """
        if not ELYSIA_AVAILABLE:
            raise ImportError("elysia-ai package is required. Run: pip install elysia-ai")

        self.client = client
        self.tree = Tree()
        self._register_tools()

    def _register_tools(self) -> None:
        """Register custom tools for each knowledge domain."""

        # Vocabulary/SKOS search tool
        @tool(tree=self.tree)
        async def search_vocabulary(query: str, limit: int = 5) -> list[dict]:
            """Search SKOS vocabulary concepts from IEC standards (CIM, 61970, 61968, 62325).

            Use this tool when the user asks about:
            - Energy sector terminology and definitions
            - CIM (Common Information Model) concepts
            - IEC standards (61970, 61968, 62325, 62746)
            - SKOS concepts, vocabularies, or ontologies
            - Technical terms and their meanings

            Args:
                query: Search query for vocabulary concepts
                limit: Maximum number of results to return

            Returns:
                List of matching vocabulary concepts with definitions
            """
            collection = self.client.collections.get("Vocabulary")
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=0.6,
            )
            return [
                {
                    "label": obj.properties.get("pref_label", ""),
                    "definition": obj.properties.get("definition", ""),
                    "vocabulary": obj.properties.get("vocabulary_name", ""),
                    "uri": obj.properties.get("uri", ""),
                }
                for obj in results.objects
            ]

        # ADR search tool
        @tool(tree=self.tree)
        async def search_architecture_decisions(query: str, limit: int = 5) -> list[dict]:
            """Search Architectural Decision Records (ADRs) for design decisions.

            Use this tool when the user asks about:
            - Architecture decisions and their rationale
            - Design choices and tradeoffs
            - Technical decisions and their context
            - ADRs or architectural records
            - System design patterns used

            Args:
                query: Search query for architecture decisions
                limit: Maximum number of results to return

            Returns:
                List of matching ADRs with context and decisions
            """
            collection = self.client.collections.get("ArchitecturalDecision")
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=0.6,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "status": obj.properties.get("status", ""),
                    "context": obj.properties.get("context", "")[:500],
                    "decision": obj.properties.get("decision", "")[:500],
                    "consequences": obj.properties.get("consequences", "")[:300],
                }
                for obj in results.objects
            ]

        # Principles search tool
        @tool(tree=self.tree)
        async def search_principles(query: str, limit: int = 5) -> list[dict]:
            """Search architecture and governance principles.

            Use this tool when the user asks about:
            - Architecture principles and guidelines
            - Governance principles
            - Design principles and best practices
            - Standards and conventions

            Args:
                query: Search query for principles
                limit: Maximum number of results to return

            Returns:
                List of matching principles
            """
            collection = self.client.collections.get("Principle")
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=0.6,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "content": obj.properties.get("content", "")[:800],
                    "doc_type": obj.properties.get("doc_type", ""),
                }
                for obj in results.objects
            ]

        # Policy document search tool
        @tool(tree=self.tree)
        async def search_policies(query: str, limit: int = 5) -> list[dict]:
            """Search data governance and policy documents.

            Use this tool when the user asks about:
            - Data governance policies
            - Data quality requirements
            - Compliance and regulatory policies
            - Data management policies
            - Security and privacy policies

            Args:
                query: Search query for policy documents
                limit: Maximum number of results to return

            Returns:
                List of matching policy documents
            """
            collection = self.client.collections.get("PolicyDocument")
            results = collection.query.hybrid(
                query=query,
                limit=limit,
                alpha=0.6,
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "content": obj.properties.get("content", "")[:800],
                    "file_type": obj.properties.get("file_type", ""),
                }
                for obj in results.objects
            ]

        # List all ADRs tool
        @tool(tree=self.tree)
        async def list_all_adrs() -> list[dict]:
            """List all Architectural Decision Records in the system.

            Use this tool when the user asks:
            - What ADRs exist?
            - List all architecture decisions
            - Show me all ADRs
            - What decisions have been documented?

            Returns:
                Complete list of all ADRs with titles and status
            """
            collection = self.client.collections.get("ArchitecturalDecision")
            results = collection.query.fetch_objects(
                limit=100,
                return_properties=["title", "status", "file_path"],
            )
            adrs = []
            for obj in results.objects:
                title = obj.properties.get("title", "")
                file_path = obj.properties.get("file_path", "")
                # Skip templates
                if "template" in title.lower() or "template" in file_path.lower():
                    continue
                adrs.append({
                    "title": title,
                    "status": obj.properties.get("status", ""),
                    "file": file_path.split("/")[-1] if file_path else "",
                })
            return sorted(adrs, key=lambda x: x.get("file", ""))

        # List all principles tool
        @tool(tree=self.tree)
        async def list_all_principles() -> list[dict]:
            """List all architecture and governance principles.

            Use this tool when the user asks:
            - What principles exist?
            - List all principles
            - Show me the governance principles

            Returns:
                Complete list of all principles
            """
            collection = self.client.collections.get("Principle")
            results = collection.query.fetch_objects(
                limit=100,
                return_properties=["title", "doc_type"],
            )
            return [
                {
                    "title": obj.properties.get("title", ""),
                    "type": obj.properties.get("doc_type", ""),
                }
                for obj in results.objects
            ]

        # Search documents by team/owner
        @tool(tree=self.tree)
        async def search_by_team(team_name: str, query: str = "", limit: int = 10) -> list[dict]:
            """Search all documents owned by a specific team or workgroup.

            Use this tool when the user asks about documents from a specific team:
            - What documents does ESA/Energy System Architecture have?
            - Show me Data Office documents
            - What are the ESA principles and ADRs?
            - Documents from System Operations team

            This searches across ALL collection types (ADRs, Principles, Policies)
            filtered by the owning team.

            Args:
                team_name: Team name or abbreviation (e.g., "ESA", "Energy System Architecture", "Data Office")
                query: Optional search query to filter results within the team's documents
                limit: Maximum number of results per collection

            Returns:
                List of documents with their type, title, and owner info
            """
            results = []

            # Search ADRs
            try:
                adr_collection = self.client.collections.get("ArchitecturalDecision")
                if query:
                    adr_results = adr_collection.query.hybrid(
                        query=f"{team_name} {query}",
                        limit=limit,
                        alpha=0.5,
                    )
                else:
                    adr_results = adr_collection.query.fetch_objects(
                        limit=limit * 2,
                        return_properties=["title", "status", "owner_team", "owner_team_abbr", "owner_display"],
                    )

                for obj in adr_results.objects:
                    owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                    owner_display = obj.properties.get("owner_display", "")
                    if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                        results.append({
                            "type": "ADR",
                            "title": obj.properties.get("title", ""),
                            "status": obj.properties.get("status", ""),
                            "owner": owner_display or owner,
                        })
            except Exception as e:
                logger.warning(f"Error searching ADRs by team: {e}")

            # Search Principles
            try:
                principle_collection = self.client.collections.get("Principle")
                if query:
                    principle_results = principle_collection.query.hybrid(
                        query=f"{team_name} {query}",
                        limit=limit,
                        alpha=0.5,
                    )
                else:
                    principle_results = principle_collection.query.fetch_objects(
                        limit=limit * 2,
                        return_properties=["title", "doc_type", "owner_team", "owner_team_abbr", "owner_display"],
                    )

                for obj in principle_results.objects:
                    owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                    owner_display = obj.properties.get("owner_display", "")
                    if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                        results.append({
                            "type": "Principle",
                            "title": obj.properties.get("title", ""),
                            "doc_type": obj.properties.get("doc_type", ""),
                            "owner": owner_display or owner,
                        })
            except Exception as e:
                logger.warning(f"Error searching Principles by team: {e}")

            # Search Policies
            try:
                policy_collection = self.client.collections.get("PolicyDocument")
                if query:
                    policy_results = policy_collection.query.hybrid(
                        query=f"{team_name} {query}",
                        limit=limit,
                        alpha=0.5,
                    )
                else:
                    policy_results = policy_collection.query.fetch_objects(
                        limit=limit * 2,
                        return_properties=["title", "file_type", "owner_team", "owner_team_abbr", "owner_display"],
                    )

                for obj in policy_results.objects:
                    owner = obj.properties.get("owner_team", "") or obj.properties.get("owner_team_abbr", "")
                    owner_display = obj.properties.get("owner_display", "")
                    if team_name.lower() in owner.lower() or team_name.lower() in owner_display.lower():
                        results.append({
                            "type": "Policy",
                            "title": obj.properties.get("title", ""),
                            "file_type": obj.properties.get("file_type", ""),
                            "owner": owner_display or owner,
                        })
            except Exception as e:
                logger.warning(f"Error searching Policies by team: {e}")

            return results

        # Collection statistics tool
        @tool(tree=self.tree)
        async def get_collection_stats() -> dict:
            """Get statistics about all collections in the knowledge base.

            Use this tool when the user asks:
            - How many documents are there?
            - What's in the knowledge base?
            - Show me the system status
            - Collection statistics

            Returns:
                Dictionary with collection names and document counts
            """
            collections = ["Vocabulary", "ArchitecturalDecision", "Principle", "PolicyDocument"]
            stats = {}
            for name in collections:
                if self.client.collections.exists(name):
                    collection = self.client.collections.get(name)
                    aggregate = collection.aggregate.over_all(total_count=True)
                    stats[name] = aggregate.total_count
                else:
                    stats[name] = 0
            return stats

        logger.info("Registered Elysia tools: vocabulary, ADR, principles, policies, search_by_team")

    async def query(self, question: str, collection_names: Optional[list[str]] = None) -> tuple[str, list[dict]]:
        """Process a query using Elysia's decision tree.

        Args:
            question: The user's question
            collection_names: Optional list of collection names to focus on

        Returns:
            Tuple of (response text, retrieved objects)
        """
        logger.info(f"Elysia processing: {question}")

        # Always specify our collection names to bypass Elysia's metadata collection discovery
        # This avoids gRPC errors from Elysia's internal collections
        our_collections = collection_names or [
            "Vocabulary",
            "ArchitecturalDecision",
            "Principle",
            "PolicyDocument",
        ]

        try:
            response, objects = self.tree(question, collection_names=our_collections)
        except Exception as e:
            # If Elysia's tree fails, fall back to direct tool execution
            logger.warning(f"Elysia tree failed: {e}, using direct tool execution")
            response, objects = await self._direct_query(question)

        # Note: We return the raw response, but the CLI doesn't display it anymore
        # Elysia's framework already displays the answer via its "Assistant response" panels
        return response, objects

    async def _direct_query(self, question: str) -> tuple[str, list[dict]]:
        """Direct query execution bypassing Elysia tree when it fails.

        Supports both OpenAI and Ollama as LLM backends.
        Uses client-side embeddings for local collections (Ollama provider).

        Args:
            question: The user's question

        Returns:
            Tuple of (response text, retrieved objects)
        """
        question_lower = question.lower()
        all_results = []

        # Determine collection suffix based on provider
        # Local collections use client-side embeddings (Nomic via Ollama)
        # OpenAI collections use Weaviate's text2vec-openai vectorizer
        use_openai_collections = settings.llm_provider == "openai"
        suffix = "_OpenAI" if use_openai_collections else ""

        # For local collections, compute query embedding client-side
        # This is a workaround for Weaviate text2vec-ollama bug (#8406)
        query_vector = None
        if not use_openai_collections:
            try:
                query_vector = embed_text(question)
            except Exception as e:
                logger.error(f"Failed to compute query embedding: {e}")

        # Filter to exclude index/template documents
        content_filter = Filter.by_property("doc_type").equal("content")

        # Search relevant collections
        if any(term in question_lower for term in ["adr", "decision", "architecture"]):
            try:
                collection = self.client.collections.get(f"ArchitecturalDecision{suffix}")
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=5, alpha=0.6, filters=content_filter
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "ADR",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("decision", "")[:500],
                    })
            except Exception as e:
                logger.warning(f"Error searching ArchitecturalDecision{suffix}: {e}")

        if any(term in question_lower for term in ["principle", "governance", "esa"]):
            try:
                collection = self.client.collections.get(f"Principle{suffix}")
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=5, alpha=0.6, filters=content_filter
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "Principle",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:500],
                    })
            except Exception as e:
                logger.warning(f"Error searching Principle{suffix}: {e}")

        if any(term in question_lower for term in ["policy", "data governance", "compliance"]):
            try:
                collection = self.client.collections.get(f"PolicyDocument{suffix}")
                results = collection.query.hybrid(
                    query=question, vector=query_vector, limit=5, alpha=0.6
                )
                for obj in results.objects:
                    all_results.append({
                        "type": "Policy",
                        "title": obj.properties.get("title", ""),
                        "content": obj.properties.get("content", "")[:500],
                    })
            except Exception as e:
                logger.warning(f"Error searching PolicyDocument{suffix}: {e}")

        if any(term in question_lower for term in ["vocab", "concept", "definition", "cim", "iec"]):
            try:
                collection = self.client.collections.get(f"Vocabulary{suffix}")
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
                logger.warning(f"Error searching Vocabulary{suffix}: {e}")

        # If no specific collection matched, search all
        if not all_results:
            for coll_base in ["ArchitecturalDecision", "Principle", "PolicyDocument"]:
                try:
                    collection = self.client.collections.get(f"{coll_base}{suffix}")
                    results = collection.query.hybrid(
                        query=question, vector=query_vector, limit=3, alpha=0.6
                    )
                    for obj in results.objects:
                        all_results.append({
                            "type": coll_base,
                            "title": obj.properties.get("title", ""),
                            "content": obj.properties.get("content", obj.properties.get("decision", ""))[:300],
                        })
                except Exception as e:
                    logger.warning(f"Error searching {coll_base}{suffix}: {e}")

        # Build context from retrieved results
        context = "\n\n".join([
            f"[{r.get('type', 'Document')}] {r.get('title', r.get('label', 'Untitled'))}: {r.get('content', r.get('definition', ''))}"
            for r in all_results[:10]
        ])

        system_prompt = "You are a helpful assistant answering questions about architecture decisions, principles, policies, and vocabulary. Base your answers on the provided context."
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        # Generate response based on LLM provider
        if settings.llm_provider == "ollama":
            response_text = await self._generate_with_ollama(system_prompt, user_prompt)
        else:
            response_text = await self._generate_with_openai(system_prompt, user_prompt)

        return response_text, all_results

    async def _generate_with_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using Ollama API.

        SmolLM3's native context is 8K tokens. If Ollama is configured with
        larger context (32K, 256K), performance degrades significantly.

        Args:
            system_prompt: System instruction
            user_prompt: User's message with context

        Returns:
            Generated response text

        Raises:
            Exception: With actionable error message for timeout/context issues
        """
        import httpx
        import re
        import time

        # SmolLM3 native context limit
        SMOLLM3_NATIVE_CONTEXT = 8000

        start_time = time.time()
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # Estimate tokens (~4 chars per token)
        estimated_tokens = len(full_prompt) // 4
        context_exceeds_native = estimated_tokens > SMOLLM3_NATIVE_CONTEXT

        if context_exceeds_native:
            logger.warning(
                f"Context ({estimated_tokens} tokens) exceeds SmolLM3's native 8K limit. "
                f"Expect slow generation if Ollama context is set to 32K/256K."
            )

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.ollama_model,
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {"num_predict": 1000},
                    },
                )
                response.raise_for_status()
                result = response.json()
                response_text = result.get("response", "")

                # Strip <think>...</think> tags from SmolLM3 responses
                response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
                response_text = re.sub(r'</?think>', '', response_text)
                response_text = re.sub(r'\n{3,}', '\n\n', response_text)

                return response_text.strip()

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = (
                f"Ollama generation timed out after {latency_ms}ms. "
                f"Context: {estimated_tokens} tokens (SmolLM3 native: 8K). "
            )
            if context_exceeds_native:
                error_msg += (
                    "Context exceeds SmolLM3's 8K native limit. "
                    "Reduce Ollama's context length setting (e.g., from 256K to 8K/16K)."
                )
            else:
                error_msg += (
                    "Try reducing Ollama's context length setting for better performance."
                )
            raise Exception(error_msg)

        except httpx.HTTPStatusError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if "out of memory" in str(e).lower():
                raise Exception(
                    f"Ollama out of memory ({latency_ms}ms). "
                    f"Reduce Ollama's context length setting (e.g., from 256K to 32K)."
                )
            raise Exception(f"Ollama HTTP error after {latency_ms}ms: {str(e)}")

    async def _generate_with_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using OpenAI API.

        Args:
            system_prompt: System instruction
            user_prompt: User's message with context

        Returns:
            Generated response text
        """
        from openai import OpenAI

        openai_client = OpenAI(api_key=settings.openai_api_key)

        # GPT-5.x models use max_completion_tokens instead of max_tokens
        model = settings.openai_chat_model
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

        return response.choices[0].message.content

    def query_sync(self, question: str) -> str:
        """Synchronous query wrapper.

        Args:
            question: The user's question

        Returns:
            Response text from Elysia
        """
        import asyncio
        response, _ = asyncio.run(self.query(question))
        return response


def create_elysia_system(client: WeaviateClient) -> ElysiaRAGSystem:
    """Factory function to create an Elysia RAG system.

    Args:
        client: Connected Weaviate client

    Returns:
        Configured ElysiaRAGSystem instance
    """
    return ElysiaRAGSystem(client)
