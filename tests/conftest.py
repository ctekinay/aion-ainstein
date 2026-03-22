"""Shared test fixtures and markers for the AInstein test suite.

Gate structure:
    pytest -m unit          # Pre-commit: pure-logic tests, no services (<30s)
    pytest -m functional    # Pre-push: needs Weaviate + Ollama (~3-4 min)
    pytest -m "full"        # CI/nightly: everything including benchmarks (~10-15 min)

Unmarked tests are treated as unit tests (run in all gates).
"""

import os

import httpx
import pytest

# ---------------------------------------------------------------------------
# Service availability checks (cached per session)
# ---------------------------------------------------------------------------

def _check_url(url: str, timeout: float = 3.0) -> bool:
    """Synchronous HTTP health check."""
    try:
        resp = httpx.get(url, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session")
def weaviate_available() -> bool:
    return _check_url("http://localhost:8080/v1/.well-known/ready")


@pytest.fixture(scope="session")
def ollama_available() -> bool:
    return _check_url("http://localhost:11434/api/tags")


@pytest.fixture(scope="session")
def skosmos_available() -> bool:
    return _check_url("http://localhost:8090/rest/v1/esav/")


# ---------------------------------------------------------------------------
# Auto-skip for functional tests when services are down
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _skip_functional_without_services(request, weaviate_available, ollama_available):
    """Skip functional/ingestion/generation tests if services are unavailable."""
    markers = {m.name for m in request.node.iter_markers()}
    needs_services = markers & {"functional", "ingestion", "generation"}
    if not needs_services:
        return
    missing = []
    if not weaviate_available:
        missing.append("Weaviate (localhost:8080)")
    if not ollama_available:
        missing.append("Ollama (localhost:11434)")
    if missing:
        pytest.skip(f"Services unavailable: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# FAST_MODEL support — smaller Ollama model for functional tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fast_model() -> str | None:
    """Return FAST_MODEL env var if set, for cheaper functional tests."""
    return os.environ.get("FAST_MODEL")


# ---------------------------------------------------------------------------
# Weaviate client fixture (session-scoped, shared across tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def weaviate_client(weaviate_available):
    """Provide a Weaviate client for integration tests."""
    if not weaviate_available:
        pytest.skip("Weaviate not available")
    import weaviate
    client = weaviate.connect_to_local()
    yield client
    client.close()
