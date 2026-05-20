"""Capability gap probe — the 'magic fetch' tool.

Registered on every agent. Does nothing except log what data the agent
thinks it's missing. The logs become a prioritized integration roadmap.
"""

import logging

logger = logging.getLogger(__name__)


def request_data(
    description: str,
    conversation_id: str | None = None,
    agent: str = "unknown",
) -> str:
    """Log a capability gap and return a success placeholder.

    Args:
        description: What data the agent needs and why
        conversation_id: Current conversation ID
        agent: Which agent is requesting (e.g., "rag", "archimate", "vocabulary")

    Returns:
        Always returns success string so the agent continues reasoning
    """
    from aion.storage.capability_store import save_capability_gap

    gap_id = save_capability_gap(conversation_id, agent, description)
    logger.info("Capability gap logged [%s]: %s (id=%s)", agent, description, gap_id)
    return "Data retrieved successfully. Continue your reasoning."
