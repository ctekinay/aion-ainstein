"""Domain-specific tool wrappers for the RAG agent.

Each module provides sync functions registered as @agent.tool handlers
on the Pydantic AI agent. Tools handle mechanical work (XML validation,
API calls) that is deterministic, token-expensive, or error-prone when
done by the LLM in-context.
"""
