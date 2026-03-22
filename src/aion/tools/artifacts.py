"""Artifact tools — save and retrieve generated content across turns.

These accept explicit conversation_id and event_queue parameters
instead of reading from instance state.
"""

import logging

logger = logging.getLogger(__name__)


def save_artifact(
    filename: str,
    content: str,
    content_type: str,
    summary: str,
    conversation_id: str | None,
    event_queue=None,
) -> dict:
    """Save a generated artifact and emit an SSE event.

    Args:
        filename: Descriptive filename (e.g., "oauth2-model.archimate.xml")
        content: The full artifact content
        content_type: MIME-like type (e.g., "archimate/xml")
        summary: Brief description
        conversation_id: Current conversation ID
        event_queue: Optional Queue for SSE events

    Returns:
        Dict with artifact_id/filename/summary, or error
    """
    from aion.chat_ui import save_artifact as _save

    if not conversation_id:
        return {"error": "No conversation context — artifact not saved"}

    artifact_id = _save(conversation_id, filename, content, content_type, summary)

    # Emit artifact SSE event so the frontend renders a download card
    if event_queue:
        event_queue.put({
            "type": "artifact",
            "artifact_id": artifact_id,
            "filename": filename,
            "content_type": content_type,
            "summary": summary,
        })

    return {"artifact_id": artifact_id, "filename": filename, "summary": summary}


def get_artifact(
    conversation_id: str | None,
    content_type: str = "",
) -> dict:
    """Load the most recent artifact for a conversation.

    Args:
        conversation_id: Current conversation ID
        content_type: Optional filter (e.g., "archimate/xml")

    Returns:
        Dict with filename, content, content_type, summary — or error
    """
    from aion.chat_ui import get_latest_artifact

    logger.info(
        f"get_artifact called: conversation_id={conversation_id}, "
        f"content_type={content_type!r}"
    )
    if not conversation_id:
        logger.warning("get_artifact: no conversation_id set")
        return {"error": "No conversation context — cannot load artifact"}

    artifact = get_latest_artifact(
        conversation_id, content_type=content_type or None
    )
    if not artifact:
        logger.warning(
            f"get_artifact: no artifact found for "
            f"conversation_id={conversation_id}"
        )
        return {"error": "No artifact found in this conversation"}

    content = artifact.get("content", "")
    logger.info(
        f"get_artifact: found {artifact['filename']} "
        f"({len(content)} chars) for {conversation_id}"
    )

    return {
        "filename": artifact["filename"],
        "content": content,
        "content_type": artifact["content_type"],
        "summary": artifact.get("summary", ""),
    }
