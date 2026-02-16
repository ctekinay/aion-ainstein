#!/usr/bin/env python3
"""Manual smoke probes — 15 queries to verify system behavior end-to-end.

Run with:  python scripts/smoke_probes.py
"""

import asyncio
import json
import logging
import sys

# Capture route-trace log lines
_trace_lines: list[str] = []

class _TraceCapture(logging.Handler):
    def emit(self, record):
        msg = record.getMessage()
        msg_lower = msg.lower()
        if "route_trace" in msg_lower or "invariant" in msg_lower or "post-filter" in msg_lower:
            _trace_lines.append(msg)

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
_handler = _TraceCapture()
logging.getLogger("src.agents.architecture_agent").addHandler(_handler)

from src.weaviate.client import weaviate_client
from src.agents.orchestrator import OrchestratorAgent

# ── Probe definitions ───────────────────────────────────────────────────────
PROBES = [
    # Canonical lookup — must be exact + Decision chunk
    {"id": 1,  "cat": "canonical", "q": "What does ADR.0012 decide about domain language? Quote the decision sentence."},
    {"id": 2,  "cat": "canonical", "q": "ADR-12 quote the decision."},
    {"id": 3,  "cat": "canonical", "q": "Show me ADR 12 decision."},
    {"id": 4,  "cat": "canonical", "q": "PCP.22 what does it state? Quote the statement."},
    # Cheeky — must NOT retrieve
    {"id": 5,  "cat": "cheeky",    "q": "I wish I had written ADR.12"},
    {"id": 6,  "cat": "cheeky",    "q": "ADR.12 is annoying"},
    {"id": 7,  "cat": "cheeky",    "q": "ADRs are boring documents"},
    # Mixed / ambiguous
    {"id": 8,  "cat": "mixed",     "q": "ADR.12?"},
    {"id": 9,  "cat": "mixed",     "q": "Can you help with ADR.12"},
    # Semantic path — must use filter, no conventions/templates
    {"id": 10, "cat": "semantic",  "q": "What principles do we have about interoperability?"},
    {"id": 11, "cat": "semantic",  "q": "Summarize our approach to CIM adoption."},
    {"id": 12, "cat": "semantic",  "q": "How do we handle semantic interoperability in ESA?"},
    # Regression traps
    {"id": 13, "cat": "regression","q": "Decision drivers of ADR.12"},
    {"id": 14, "cat": "regression","q": "List all ADRs"},
    {"id": 15, "cat": "regression","q": "How many ADRs are there?"},
]


def _drain_traces() -> list[str]:
    """Pop all captured trace lines."""
    lines = list(_trace_lines)
    _trace_lines.clear()
    return lines


async def run_probe(orchestrator, probe: dict) -> dict:
    """Run a single probe and return structured result."""
    _drain_traces()  # clear

    try:
        response = await orchestrator.query(
            probe["q"], agent_names=["architecture"]
        )
    except Exception as exc:
        return {
            "id": probe["id"],
            "cat": probe["cat"],
            "query": probe["q"],
            "error": str(exc),
        }

    traces = _drain_traces()

    # Parse the route trace JSON if present
    trace_data = {}
    for line in traces:
        if "route_trace" in line.lower():
            # Extract JSON from the log line
            try:
                json_start = line.index("{")
                trace_data = json.loads(line[json_start:])
            except (ValueError, json.JSONDecodeError):
                trace_data = {"raw": line}

    return {
        "id": probe["id"],
        "cat": probe["cat"],
        "query": probe["q"],
        "intent": trace_data.get("intent", "?"),
        "confidence": trace_data.get("confidence", "?"),
        "path": trace_data.get("path", "?"),
        "retrieval_allowed": trace_data.get("retrieval_allowed", "?"),
        "retrieval_verb": trace_data.get("retrieval_verb_present", "?"),
        "doc_refs": trace_data.get("doc_refs_detected", []),
        "doc_ref_override": trace_data.get("doc_ref_override_applied", False),
        "selected_chunk": trace_data.get("selected_chunk", "?"),
        "filters": trace_data.get("filters_applied", "?"),
        "answer_len": len(response.answer),
        "answer_preview": response.answer[:200].replace("\n", " "),
        "sources_count": len(response.agent_responses[0].sources) if response.agent_responses else 0,
        "raw_results_count": len(response.agent_responses[0].raw_results) if response.agent_responses else 0,
        "extra_traces": [t for t in traces if "route_trace" not in t.lower()],
    }


def print_result(r: dict):
    """Print a probe result in readable format."""
    status = "ERROR" if "error" in r else "OK"
    print(f"\n{'='*80}")
    print(f"PROBE {r['id']:>2} [{r['cat'].upper():>10}] — {status}")
    print(f"  Q: {r['query']}")

    if "error" in r:
        print(f"  ERROR: {r['error']}")
        return

    print(f"  Intent:    {r['intent']:<25} Confidence: {r['confidence']}")
    print(f"  Path:      {r['path']:<25} Retrieval:  allowed={r['retrieval_allowed']} verb={r['retrieval_verb']}")
    print(f"  Doc refs:  {r['doc_refs']!s:<25} Override:   {r['doc_ref_override']}")
    print(f"  Chunk:     {r['selected_chunk']:<25} Filters:    {r['filters']}")
    print(f"  Results:   {r['raw_results_count']} chunks, {r['sources_count']} sources, {r['answer_len']} chars")
    print(f"  Answer:    {r['answer_preview']}")
    if r.get("extra_traces"):
        for t in r["extra_traces"]:
            print(f"  TRACE:     {t}")


def main():
    results = []

    with weaviate_client() as client:
        orchestrator = OrchestratorAgent(client)

        for probe in PROBES:
            result = asyncio.run(run_probe(orchestrator, probe))
            results.append(result)
            print_result(result)

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    errors = [r for r in results if "error" in r]
    ok = [r for r in results if "error" not in r]
    print(f"  OK: {len(ok)}  ERRORS: {len(errors)}")

    if errors:
        print("  Failed probes:", [r["id"] for r in errors])

    # Dump full JSON for archival
    json_path = "smoke_probe_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full results written to {json_path}")


if __name__ == "__main__":
    main()
