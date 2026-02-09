"""Observability module for RAG system metrics and structured logging.

This module provides:
- Counter-based metrics (Prometheus-compatible)
- Structured logging with request_id correlation
- Metrics export (JSON and Prometheus formats)

Part of Phase 5 implementation (IR0003 Gap F).

Usage:
    from src.observability import metrics, get_logger

    # Increment counters
    metrics.increment("rag_abstention_total", labels={"reason": "no_results"})
    metrics.increment("skosmos_lookup_total")

    # Get structured logger
    logger = get_logger("skosmos_client", request_id="req-abc123")
    logger.info("lookup_complete", term="CIMXML", hit=True, latency_ms=45)
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# =============================================================================
# Metrics Registry
# =============================================================================

@dataclass
class Counter:
    """A simple counter metric with optional labels."""
    name: str
    help_text: str
    values: dict[tuple, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def increment(self, labels: Optional[dict[str, str]] = None, value: int = 1) -> None:
        """Increment counter by value."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self.values[label_key] = self.values.get(label_key, 0) + value

    def get(self, labels: Optional[dict[str, str]] = None) -> int:
        """Get current counter value."""
        label_key = tuple(sorted((labels or {}).items()))
        return self.values.get(label_key, 0)

    def reset(self) -> None:
        """Reset all counter values (for testing)."""
        with self._lock:
            self.values.clear()


@dataclass
class Histogram:
    """A simple histogram for latency measurements."""
    name: str
    help_text: str
    buckets: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    values: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float) -> None:
        """Record an observation."""
        with self._lock:
            self.values.append(value)

    def get_percentile(self, percentile: float) -> float:
        """Get a percentile value (e.g., 0.95 for p95)."""
        if not self.values:
            return 0.0
        sorted_vals = sorted(self.values)
        idx = int(len(sorted_vals) * percentile)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def reset(self) -> None:
        """Reset all values (for testing)."""
        with self._lock:
            self.values.clear()


class MetricsRegistry:
    """Central registry for all metrics."""

    def __init__(self):
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = threading.Lock()
        self._register_default_metrics()

    def _register_default_metrics(self) -> None:
        """Register all Phase 5 required metrics."""
        # Abstention metrics
        self.register_counter(
            "rag_abstention_total",
            "Total abstentions by reason"
        )

        # SKOSMOS metrics
        self.register_counter(
            "skosmos_lookup_total",
            "Total SKOSMOS lookup attempts"
        )
        self.register_counter(
            "skosmos_hit_total",
            "SKOSMOS lookups that found a concept"
        )
        self.register_counter(
            "skosmos_miss_total",
            "SKOSMOS lookups that found nothing"
        )
        self.register_counter(
            "skosmos_timeout_total",
            "SKOSMOS lookups that timed out"
        )
        self.register_counter(
            "skosmos_cache_hit_total",
            "SKOSMOS lookups served from cache"
        )

        # Embedding metrics
        self.register_counter(
            "embedding_request_total",
            "Total embedding requests"
        )
        self.register_counter(
            "embedding_fail_total",
            "Failed embedding requests"
        )
        self.register_counter(
            "embedding_fallback_total",
            "Times BM25 fallback was used due to embedding failure"
        )

        # Circuit breaker metrics
        self.register_counter(
            "circuit_breaker_trip_total",
            "Times circuit breaker tripped open"
        )

        # Latency histograms
        self.register_histogram(
            "skosmos_lookup_duration_seconds",
            "SKOSMOS lookup latency"
        )
        self.register_histogram(
            "rag_query_duration_seconds",
            "Total RAG query latency"
        )

    def register_counter(self, name: str, help_text: str) -> Counter:
        """Register a new counter metric."""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name=name, help_text=help_text)
            return self._counters[name]

    def register_histogram(self, name: str, help_text: str) -> Histogram:
        """Register a new histogram metric."""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name=name, help_text=help_text)
            return self._histograms[name]

    def increment(self, name: str, labels: Optional[dict[str, str]] = None, value: int = 1) -> None:
        """Increment a counter."""
        if name in self._counters:
            self._counters[name].increment(labels, value)

    def observe(self, name: str, value: float) -> None:
        """Record a histogram observation."""
        if name in self._histograms:
            self._histograms[name].observe(value)

    def get_counter(self, name: str) -> Optional[Counter]:
        """Get a counter by name."""
        return self._counters.get(name)

    def get_histogram(self, name: str) -> Optional[Histogram]:
        """Get a histogram by name."""
        return self._histograms.get(name)

    def to_json(self) -> dict[str, Any]:
        """Export all metrics as JSON."""
        result = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "counters": {},
            "histograms": {},
        }

        for name, counter in self._counters.items():
            if counter.values:
                result["counters"][name] = [
                    {"labels": dict(labels), "value": value}
                    for labels, value in counter.values.items()
                ]
            else:
                result["counters"][name] = []

        for name, histogram in self._histograms.items():
            result["histograms"][name] = {
                "count": len(histogram.values),
                "p50": histogram.get_percentile(0.50),
                "p95": histogram.get_percentile(0.95),
                "p99": histogram.get_percentile(0.99),
            }

        return result

    def to_prometheus(self) -> str:
        """Export all metrics in Prometheus format."""
        lines = []

        for name, counter in self._counters.items():
            lines.append(f"# HELP {name} {counter.help_text}")
            lines.append(f"# TYPE {name} counter")
            if counter.values:
                for labels, value in counter.values.items():
                    label_str = ",".join(f'{k}="{v}"' for k, v in labels) if labels else ""
                    if label_str:
                        lines.append(f"{name}{{{label_str}}} {value}")
                    else:
                        lines.append(f"{name} {value}")
            else:
                lines.append(f"{name} 0")

        for name, histogram in self._histograms.items():
            lines.append(f"# HELP {name} {histogram.help_text}")
            lines.append(f"# TYPE {name} histogram")
            # Simplified: just output count and sum
            lines.append(f"{name}_count {len(histogram.values)}")
            lines.append(f"{name}_sum {sum(histogram.values):.6f}")

        return "\n".join(lines)

    def reset_all(self) -> None:
        """Reset all metrics (for testing)."""
        for counter in self._counters.values():
            counter.reset()
        for histogram in self._histograms.values():
            histogram.reset()


# Global metrics instance
metrics = MetricsRegistry()


# =============================================================================
# Structured Logging
# =============================================================================

class StructuredLogger:
    """Logger that outputs structured JSON logs with request_id correlation."""

    def __init__(self, component: str, request_id: Optional[str] = None):
        self.component = component
        self.request_id = request_id
        self._logger = logging.getLogger(f"ainstein.{component}")

    def _format(self, level: str, event: str, **kwargs) -> str:
        """Format a log entry as JSON."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "component": self.component,
            "event": event,
        }
        if self.request_id:
            entry["request_id"] = self.request_id
        entry.update(kwargs)
        return json.dumps(entry)

    def info(self, event: str, **kwargs) -> None:
        """Log an INFO level event."""
        self._logger.info(self._format("INFO", event, **kwargs))

    def warn(self, event: str, **kwargs) -> None:
        """Log a WARN level event."""
        self._logger.warning(self._format("WARN", event, **kwargs))

    def error(self, event: str, **kwargs) -> None:
        """Log an ERROR level event."""
        self._logger.error(self._format("ERROR", event, **kwargs))

    def debug(self, event: str, **kwargs) -> None:
        """Log a DEBUG level event."""
        self._logger.debug(self._format("DEBUG", event, **kwargs))


def get_logger(component: str, request_id: Optional[str] = None) -> StructuredLogger:
    """Get a structured logger for a component.

    Args:
        component: Name of the component (e.g., "skosmos_client", "elysia_agents")
        request_id: Optional request ID for correlation

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(component, request_id)


# =============================================================================
# Circuit Breaker State (for Gap D metrics)
# =============================================================================

class CircuitBreakerState:
    """Track circuit breaker state for observability."""

    def __init__(self):
        self._states: dict[str, str] = {}
        self._lock = threading.Lock()

    def set_state(self, service: str, state: str) -> None:
        """Set circuit breaker state for a service."""
        with self._lock:
            self._states[service] = state

    def get_state(self, service: str) -> str:
        """Get circuit breaker state for a service."""
        return self._states.get(service, "closed")

    def get_all_states(self) -> dict[str, str]:
        """Get all circuit breaker states."""
        with self._lock:
            return dict(self._states)


# Global circuit breaker state tracker
circuit_breaker_state = CircuitBreakerState()
