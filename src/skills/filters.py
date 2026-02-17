"""Stub filter module — returns None (no filtering).

Real implementations can be added later without changing the interface.
"""

from typing import Any, Optional


def build_document_filter(**kwargs: Any) -> Optional[Any]:
    """Build a Weaviate document filter. Stub: returns None."""
    return None


def build_intent_aware_filter(**kwargs: Any) -> Optional[Any]:
    """Build an intent-aware filter. Stub: returns None."""
    return None
