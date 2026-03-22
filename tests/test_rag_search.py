"""Tests for RAG search utilities — general knowledge eligibility."""

import pytest

from aion.tools.rag_search import is_general_knowledge_eligible


@pytest.mark.parametrize("query,expected", [
    # General knowledge — eligible
    ("What is the strangler fig pattern?", True),
    ("How does TOGAF define principles?", True),
    ("Explain event-driven architecture", True),
    ("What is necessary for good architecture?", True),   # "necessary" must NOT match "esa"
    ("How does research inform architecture?", True),     # "research" must NOT match "esa"
    # Doc references — NOT eligible
    ("What does ADR.29 say?", False),
    ("Compare PCP.10 and PCP.20", False),
    ("What is DAR-5?", False),
    # Org-specific — NOT eligible
    ("What is Alliander's policy?", False),
    ("Is ESA's approach aligned with TOGAF?", False),
    ("What does the ESA team recommend?", False),
    ("What is ESA-specific about this?", False),
    ("What is ESAV vocabulary?", False),
    # First-person org patterns — NOT eligible
    ("How should we approach security?", False),
    ("What do we recommend for API versioning?", False),
    ("Can we use microservices?", False),
    ("What are our architecture standards?", False),
    ("Our teams need guidance on this", False),
    ("We use OAuth for authentication", False),
    ("We have decided to adopt TOGAF", False),
    ("We follow the CIM standard", False),
    ("We recommend event sourcing", False),
    ("We decided on a monorepo strategy", False),
])
def test_general_knowledge_eligibility(query, expected):
    assert is_general_knowledge_eligible(query) == expected
