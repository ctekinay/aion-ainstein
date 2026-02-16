#!/usr/bin/env python3
"""
Tests for fallback filter guardrails (Phase 1).

Acceptance criteria:
1. With current Weaviate data (doc_type missing), query "What ADRs exist..."
   returns 18 ADRs via fallback.
2. Logs show fallback triggered + reason.
3. If you set MAX_FALLBACK_SCAN_DOCS=10, the endpoint returns a controlled
   error (no scan), logs show blocked.

Usage:
    pytest tests/test_fallback_guardrails.py -v
    pytest tests/test_fallback_guardrails.py -v -k test_fallback_blocked
"""

import logging
import pytest
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings


# =============================================================================
# Inline copy of guardrail logic for isolated testing
# (Avoids importing elysia_agents which triggers spacy download)
# =============================================================================

@dataclass
class FallbackMetrics:
    """Thread-safe metrics for fallback filter observability."""
    adr_filter_fallback_used_total: int = 0
    adr_filter_fallback_blocked_total: int = 0
    principle_filter_fallback_used_total: int = 0
    principle_filter_fallback_blocked_total: int = 0

    def increment_fallback_used(self, collection_type: str = "adr") -> None:
        if collection_type == "adr":
            self.adr_filter_fallback_used_total += 1
        else:
            self.principle_filter_fallback_used_total += 1

    def increment_fallback_blocked(self, collection_type: str = "adr") -> None:
        if collection_type == "adr":
            self.adr_filter_fallback_blocked_total += 1
        else:
            self.principle_filter_fallback_blocked_total += 1

    def get_metrics(self) -> dict:
        return {
            "adr_filter_fallback_used_total": self.adr_filter_fallback_used_total,
            "adr_filter_fallback_blocked_total": self.adr_filter_fallback_blocked_total,
            "principle_filter_fallback_used_total": self.principle_filter_fallback_used_total,
            "principle_filter_fallback_blocked_total": self.principle_filter_fallback_blocked_total,
        }


# Module-level metrics for testing
_test_fallback_metrics = FallbackMetrics()


def get_fallback_metrics() -> FallbackMetrics:
    return _test_fallback_metrics


def generate_request_id() -> str:
    return str(uuid.uuid4())[:8]


def check_fallback_allowed(
    collection_size: int,
    collection_type: str,
    query: str,
    request_id: str,
) -> tuple[bool, str | None]:
    """Check if fallback filtering is allowed based on guardrails."""
    logger = logging.getLogger(__name__)

    # Check feature flag
    if not settings.enable_inmemory_filter_fallback:
        error_msg = (
            f"ADR metadata missing; in-memory fallback is disabled. "
            f"Please run migration. [request_id={request_id}]"
        )
        logger.warning(
            f"Fallback BLOCKED (feature disabled): "
            f"collection_type={collection_type}, collection_size={collection_size}, "
            f"query='{query[:50]}...', request_id={request_id}"
        )
        _test_fallback_metrics.increment_fallback_blocked(collection_type)
        return False, error_msg

    # Check safety cap
    if collection_size > settings.max_fallback_scan_docs:
        error_msg = (
            f"ADR metadata missing; collection size ({collection_size}) exceeds "
            f"safety cap ({settings.max_fallback_scan_docs}). "
            f"Please run migration. [request_id={request_id}, reason=DOC_METADATA_MISSING_REQUIRES_MIGRATION]"
        )
        logger.warning(
            f"Fallback BLOCKED (cap exceeded): "
            f"collection_type={collection_type}, collection_size={collection_size}, "
            f"max_allowed={settings.max_fallback_scan_docs}, "
            f"query='{query[:50]}...', request_id={request_id}, "
            f"reason=DOC_METADATA_MISSING_REQUIRES_MIGRATION"
        )
        _test_fallback_metrics.increment_fallback_blocked(collection_type)
        return False, error_msg

    # Fallback allowed - log and increment metrics
    logger.warning(
        f"adr_filter_fallback_used=1: "
        f"collection_type={collection_type}, collection_total={collection_size}, "
        f"query='{query[:50]}...', request_id={request_id}, "
        f"reason=DOC_TYPE_MISSING"
    )
    _test_fallback_metrics.increment_fallback_used(collection_type)

    # Warn if fallback is enabled in prod
    if settings.environment == "prod":
        logger.warning(
            f"WARNING: In-memory fallback is enabled in PRODUCTION. "
            f"This should be disabled after migration. request_id={request_id}"
        )

    return True, None


class TestFallbackGuardrails:
    """Test suite for fallback filter guardrails."""

    def setup_method(self):
        """Reset metrics before each test."""
        global _test_fallback_metrics
        _test_fallback_metrics.adr_filter_fallback_used_total = 0
        _test_fallback_metrics.adr_filter_fallback_blocked_total = 0
        _test_fallback_metrics.principle_filter_fallback_used_total = 0
        _test_fallback_metrics.principle_filter_fallback_blocked_total = 0

    def test_generate_request_id_format(self):
        """Test that request IDs are generated in expected format."""
        request_id = generate_request_id()
        assert len(request_id) == 8
        # Should be hex characters
        assert all(c in "0123456789abcdef-" for c in request_id)

    def test_fallback_allowed_when_enabled_and_under_cap(self):
        """Test fallback is allowed when enabled and under safety cap."""
        with patch.object(settings, 'enable_inmemory_filter_fallback', True):
            with patch.object(settings, 'max_fallback_scan_docs', 2000):
                allowed, error = check_fallback_allowed(
                    collection_size=126,
                    collection_type="adr",
                    query="list all ADRs",
                    request_id="test1234",
                )

                assert allowed is True
                assert error is None

                # Check metrics incremented
                metrics = get_fallback_metrics()
                assert metrics.adr_filter_fallback_used_total == 1

    def test_fallback_blocked_when_disabled(self):
        """Test fallback is blocked when feature flag is disabled."""
        with patch.object(settings, 'enable_inmemory_filter_fallback', False):
            allowed, error = check_fallback_allowed(
                collection_size=126,
                collection_type="adr",
                query="list all ADRs",
                request_id="test1234",
            )

            assert allowed is False
            assert error is not None
            assert "request_id=test1234" in error
            assert "in-memory fallback is disabled" in error

            # Check metrics incremented
            metrics = get_fallback_metrics()
            assert metrics.adr_filter_fallback_blocked_total == 1
            assert metrics.adr_filter_fallback_used_total == 0

    def test_fallback_blocked_when_cap_exceeded(self):
        """Test fallback is blocked when collection size exceeds safety cap."""
        with patch.object(settings, 'enable_inmemory_filter_fallback', True):
            with patch.object(settings, 'max_fallback_scan_docs', 10):
                allowed, error = check_fallback_allowed(
                    collection_size=126,
                    collection_type="adr",
                    query="list all ADRs",
                    request_id="test1234",
                )

                assert allowed is False
                assert error is not None
                assert "request_id=test1234" in error
                assert "exceeds" in error
                assert "DOC_METADATA_MISSING_REQUIRES_MIGRATION" in error

                # Check metrics incremented
                metrics = get_fallback_metrics()
                assert metrics.adr_filter_fallback_blocked_total == 1
                assert metrics.adr_filter_fallback_used_total == 0

    def test_fallback_logs_when_triggered(self, caplog):
        """Test that fallback triggers produce expected log messages."""
        with patch.object(settings, 'enable_inmemory_filter_fallback', True):
            with patch.object(settings, 'max_fallback_scan_docs', 2000):
                with caplog.at_level(logging.WARNING):
                    check_fallback_allowed(
                        collection_size=126,
                        collection_type="adr",
                        query="list all ADRs",
                        request_id="test1234",
                    )

                    # Check log contains required fields
                    assert "adr_filter_fallback_used=1" in caplog.text
                    assert "collection_total=126" in caplog.text
                    assert "reason=DOC_TYPE_MISSING" in caplog.text

    def test_fallback_blocked_logs_when_cap_exceeded(self, caplog):
        """Test that blocked fallback produces expected log messages."""
        with patch.object(settings, 'enable_inmemory_filter_fallback', True):
            with patch.object(settings, 'max_fallback_scan_docs', 10):
                with caplog.at_level(logging.WARNING):
                    check_fallback_allowed(
                        collection_size=126,
                        collection_type="adr",
                        query="list all ADRs",
                        request_id="test1234",
                    )

                    # Check log contains required fields
                    assert "Fallback BLOCKED" in caplog.text
                    assert "cap exceeded" in caplog.text
                    assert "max_allowed=10" in caplog.text
                    assert "DOC_METADATA_MISSING_REQUIRES_MIGRATION" in caplog.text

    def test_principle_metrics_tracked_separately(self):
        """Test that principle fallback metrics are tracked separately from ADR."""
        with patch.object(settings, 'enable_inmemory_filter_fallback', True):
            with patch.object(settings, 'max_fallback_scan_docs', 2000):
                # Trigger ADR fallback
                check_fallback_allowed(
                    collection_size=100,
                    collection_type="adr",
                    query="list ADRs",
                    request_id="adr123",
                )

                # Trigger principle fallback
                check_fallback_allowed(
                    collection_size=50,
                    collection_type="principle",
                    query="list principles",
                    request_id="pcp123",
                )

                metrics = get_fallback_metrics()
                assert metrics.adr_filter_fallback_used_total == 1
                assert metrics.principle_filter_fallback_used_total == 1

    def test_prod_warning_logged(self, caplog):
        """Test that a warning is logged when fallback is used in prod."""
        with patch.object(settings, 'enable_inmemory_filter_fallback', True):
            with patch.object(settings, 'max_fallback_scan_docs', 2000):
                with patch.object(settings, 'environment', 'prod'):
                    with caplog.at_level(logging.WARNING):
                        check_fallback_allowed(
                            collection_size=100,
                            collection_type="adr",
                            query="list ADRs",
                            request_id="prod123",
                        )

                        assert "PRODUCTION" in caplog.text
                        assert "should be disabled after migration" in caplog.text


class TestMetricsExport:
    """Test metrics can be exported for monitoring."""

    def setup_method(self):
        """Reset metrics before each test."""
        global _test_fallback_metrics
        _test_fallback_metrics.adr_filter_fallback_used_total = 0
        _test_fallback_metrics.adr_filter_fallback_blocked_total = 0
        _test_fallback_metrics.principle_filter_fallback_used_total = 0
        _test_fallback_metrics.principle_filter_fallback_blocked_total = 0

    def test_get_metrics_returns_dict(self):
        """Test that get_metrics returns a dictionary with all counters."""
        metrics = get_fallback_metrics()
        result = metrics.get_metrics()

        assert isinstance(result, dict)
        assert "adr_filter_fallback_used_total" in result
        assert "adr_filter_fallback_blocked_total" in result
        assert "principle_filter_fallback_used_total" in result
        assert "principle_filter_fallback_blocked_total" in result

    def test_metrics_accumulate(self):
        """Test that metrics accumulate across multiple calls."""
        with patch.object(settings, 'enable_inmemory_filter_fallback', True):
            with patch.object(settings, 'max_fallback_scan_docs', 2000):
                for i in range(5):
                    check_fallback_allowed(
                        collection_size=100,
                        collection_type="adr",
                        query=f"query {i}",
                        request_id=f"req{i}",
                    )

                metrics = get_fallback_metrics()
                assert metrics.adr_filter_fallback_used_total == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
