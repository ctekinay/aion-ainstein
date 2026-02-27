"""Domain-specific tool wrappers for Elysia Tree integration.

Each module provides sync functions that are registered as async @tool
handlers in elysia_agents.py. Tools handle mechanical work (XML validation,
API calls) that is deterministic, token-expensive, or error-prone when
done by the LLM in-context.
"""
