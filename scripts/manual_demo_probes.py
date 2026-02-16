#!/usr/bin/env python3
"""Manual demo validation — 10 probes against live Weaviate.

Runs ArchitectureAgent.query() directly (not via orchestrator) to capture
ROUTE_TRACE logs and validate Demo v1 invariants D1-D10.

Includes follow-up binding (probe 10) which requires stateful last_doc_refs.

Run with:  python scripts/manual_demo_probes.py
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
        if "ROUTE_TRACE" in msg or "INVARIANT" in msg or "post-filter" in msg:
            _trace_lines.append(msg)


logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
_handler = _TraceCapture()
logging.getLogger("src.agents.architecture_agent").addHandler(_handler)

from src.weaviate.client import weaviate_client
from src.agents.architecture_agent import ArchitectureAgent

# ── Probe definitions ───────────────────────────────────────────────────────
# Each probe has:
#   id, invariant (D1-D10), query, expected_path, expected_winner,
#   extra kwargs (like last_doc_refs), and notes on what to check.

PROBES = [
    {
        "id": 1,
        "invariant": "D1",
        "q": "What does ADR.0012 decide?",
        "expect_path": "lookup_exact",
        "expect_winner": "lookup_doc",
        "expect_no_hybrid": True,
        "note": "Prefixed doc ref → exact lookup, no hybrid",
    },
    {
        "id": 2,
        "invariant": "D2/D3",
        "q": "What does 0022 decide?",
        "expect_path": ["lookup_exact", None],  # resolved or clarification (no trace)
        "expect_no_hybrid": True,
        "note": "Bare number → resolved or clarification, no hybrid",
    },
    {
        "id": 3,
        "invariant": "D3/R2",
        "q": "What does 22 decide?",
        "expect_path": ["lookup_exact", None],  # depends on collision
        "expect_no_hybrid": True,
        "note": "Bare number with possible collision → clarification format check",
    },
    {
        "id": 4,
        "invariant": "D5",
        "q": "I wish I had written ADR.12",
        "expect_path": "conversational",
        "expect_winner": None,
        "expect_no_hybrid": True,
        "note": "Cheeky → conversational, no retrieval",
    },
    {
        "id": 5,
        "invariant": "D6",
        "q": "List all ADRs",
        "expect_path": "list",
        "expect_winner": "list",
        "note": "Unscoped list → list path, high confidence",
    },
    {
        "id": 6,
        "invariant": "D7",
        "q": "List principles about interoperability",
        "expect_path": "hybrid",
        "expect_winner": "semantic_answer",
        "note": "Scoped list → semantic, NOT list dump",
    },
    {
        "id": 7,
        "invariant": "D8",
        "q": "How many ADRs are there?",
        "expect_path": "count",
        "expect_winner": "count",
        "note": "Count query → count path",
    },
    {
        "id": 8,
        "invariant": "D9",
        "q": "What security patterns are used?",
        "expect_path": "hybrid",
        "expect_winner": "semantic_answer",
        "note": "Semantic → hybrid + filters",
    },
    {
        "id": 9,
        "invariant": "D1",
        "q": "Tell me about ADR.12",
        "expect_path": "lookup_exact",
        "expect_winner": "lookup_doc",
        "expect_no_hybrid": True,
        "note": "Retrieval verb + prefixed ref → lookup",
    },
    # Probe 10 is special: it uses last_doc_refs from probe 9's result
    {
        "id": 10,
        "invariant": "follow-up",
        "q": "Show it",
        "expect_path": "lookup_exact",
        "expect_winner": "lookup_doc",
        "expect_no_hybrid": True,
        "note": "Follow-up with last_doc_refs → binds to previous ref",
        "last_doc_refs_from": 9,  # use doc_refs from probe 9's trace
    },
]


def _drain_traces() -> list[str]:
    lines = list(_trace_lines)
    _trace_lines.clear()
    return lines


async def run_probe(agent, probe: dict, last_doc_refs=None) -> dict:
    """Run a single probe and return structured result."""
    _drain_traces()

    kwargs = {}
    if last_doc_refs:
        kwargs["last_doc_refs"] = last_doc_refs

    try:
        response = await agent.query(probe["q"], **kwargs)
    except Exception as exc:
        return {
            "id": probe["id"],
            "invariant": probe["invariant"],
            "query": probe["q"],
            "error": str(exc),
            "note": probe.get("note", ""),
        }

    traces = _drain_traces()

    # Parse route trace
    trace_data = {}
    for line in traces:
        if "ROUTE_TRACE" in line:
            try:
                json_start = line.index("{")
                trace_data = json.loads(line[json_start:])
            except (ValueError, json.JSONDecodeError):
                trace_data = {"raw": line}

    # Check expectations
    actual_path = trace_data.get("path", "?")
    actual_winner = trace_data.get("winner", "?")

    expect_path = probe.get("expect_path")
    if isinstance(expect_path, list):
        path_ok = actual_path in expect_path or actual_path == "?"
    elif expect_path:
        path_ok = actual_path == expect_path
    else:
        path_ok = True

    expect_winner = probe.get("expect_winner")
    winner_ok = (not expect_winner) or actual_winner == expect_winner

    return {
        "id": probe["id"],
        "invariant": probe["invariant"],
        "query": probe["q"],
        "actual_path": actual_path,
        "actual_winner": actual_winner,
        "path_ok": path_ok,
        "winner_ok": winner_ok,
        "confidence": response.confidence,
        "answer_len": len(response.answer),
        "answer_preview": response.answer[:200].replace("\n", " "),
        "doc_refs_detected": trace_data.get("doc_refs_detected", []),
        "signals": trace_data.get("signals", {}),
        "scores": trace_data.get("scores", {}),
        "note": probe.get("note", ""),
        "extra_traces": [t for t in traces if "ROUTE_TRACE" not in t],
    }


def print_result(r: dict):
    status = "ERROR" if "error" in r else ("PASS" if r.get("path_ok") and r.get("winner_ok") else "FAIL")
    icon = {"PASS": "+", "FAIL": "!", "ERROR": "X"}[status]

    print(f"\n{'='*80}")
    print(f"[{icon}] PROBE {r['id']:>2} [{r['invariant']:>10}] — {status}")
    print(f"  Q: {r['query']}")
    print(f"  Note: {r['note']}")

    if "error" in r:
        print(f"  ERROR: {r['error']}")
        return

    print(f"  Path:      {r['actual_path']:<20} (ok={r['path_ok']})")
    print(f"  Winner:    {r['actual_winner']:<20} (ok={r['winner_ok']})")
    print(f"  Conf:      {r['confidence']}")
    print(f"  Doc refs:  {r['doc_refs_detected']}")
    print(f"  Answer:    {r['answer_preview']}")
    if r.get("extra_traces"):
        for t in r["extra_traces"]:
            print(f"  TRACE:     {t}")


def main():
    results = []
    doc_refs_cache = {}  # probe_id → doc_refs from trace

    with weaviate_client() as client:
        agent = ArchitectureAgent(client)

        for probe in PROBES:
            # Resolve last_doc_refs if needed
            last_doc_refs = None
            from_id = probe.get("last_doc_refs_from")
            if from_id and from_id in doc_refs_cache:
                last_doc_refs = doc_refs_cache[from_id]

            result = asyncio.run(run_probe(agent, probe, last_doc_refs))
            results.append(result)
            print_result(result)

            # Cache doc_refs for follow-up probes
            if result.get("doc_refs_detected"):
                refs = [
                    {"canonical_id": ref, "prefix": ref.split(".")[0], "number_value": ""}
                    for ref in result["doc_refs_detected"]
                ]
                doc_refs_cache[probe["id"]] = refs

    # Summary
    print(f"\n{'='*80}")
    print("DEMO v1 MANUAL VALIDATION SUMMARY")
    print(f"{'='*80}")
    errors = [r for r in results if "error" in r]
    passes = [r for r in results if r.get("path_ok") and r.get("winner_ok") and "error" not in r]
    fails = [r for r in results if (not r.get("path_ok") or not r.get("winner_ok")) and "error" not in r]
    print(f"  PASS: {len(passes)}  FAIL: {len(fails)}  ERROR: {len(errors)}")

    if fails:
        print(f"  Failed: {[r['id'] for r in fails]}")
    if errors:
        print(f"  Errors: {[r['id'] for r in errors]}")

    json_path = "manual_demo_probe_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full results → {json_path}")
    print(f"  Compare with gold suite: python -m pytest tests/test_gold_routing_suite.py -v")


if __name__ == "__main__":
    main()
