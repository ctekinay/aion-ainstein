#!/usr/bin/env python3
"""Regression test runner for session-based YAML test scripts.

Executes multi-turn regression scenarios derived from real user sessions.
Each YAML file describes a sequence of questions with expected routes and
content constraints.

Unlike gold standard tests (single-question evaluation), these test
interaction patterns and failure cascades observed in the field.

Usage:
    # Run all regression tests
    python tests/regression/run_regression.py

    # Run a specific session
    python tests/regression/run_regression.py --session session_meta_spiral

    # Dry run (parse and validate YAML only, no queries)
    python tests/regression/run_regression.py --dry-run

    # Debug mode (verbose output)
    python tests/regression/run_regression.py --debug
"""

import argparse
import asyncio
import logging
import re
import sys
import time
from pathlib import Path

import yaml

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


logger = logging.getLogger(__name__)


def load_session(yaml_path: Path) -> dict:
    """Load and validate a session YAML file."""
    with open(yaml_path) as f:
        session = yaml.safe_load(f)

    required_keys = ["name", "steps"]
    for key in required_keys:
        if key not in session:
            raise ValueError(f"Session {yaml_path.name} missing required key: {key}")

    for step in session["steps"]:
        if "id" not in step or "question" not in step:
            raise ValueError(f"Session {yaml_path.name}: step missing 'id' or 'question'")

    return session


def check_step_result(step: dict, response: str, actual_route: str) -> dict:
    """Check a single step's response against constraints.

    Returns:
        Dict with pass/fail status and issue details
    """
    issues = []
    expected_route = step.get("expected_route", "any")

    # Route check
    route_ok = (expected_route == "any" or actual_route == expected_route)
    if not route_ok:
        # Allow semantic/multi_hop equivalence
        if {expected_route, actual_route} <= {"semantic", "multi_hop"}:
            route_ok = True
        # Allow vocab via semantic path
        elif expected_route == "vocab" and actual_route == "semantic":
            route_ok = True

    if not route_ok:
        issues.append(f"ROUTE: expected={expected_route}, actual={actual_route}")

    # must_contain check
    response_lower = response.lower()
    for required in step.get("must_contain", []):
        if required.lower() not in response_lower:
            issues.append(f"MISSING: '{required}' not found in response")

    # must_not_contain check
    for forbidden in step.get("must_not_contain", []):
        if forbidden.lower() in response_lower:
            issues.append(f"FORBIDDEN: '{forbidden}' found in response")

    return {
        "step_id": step["id"],
        "question": step["question"],
        "route_ok": route_ok,
        "expected_route": expected_route,
        "actual_route": actual_route,
        "issues": issues,
        "pass": len(issues) == 0,
        "response_preview": response[:200] if response else "",
    }


async def run_session(session: dict, debug: bool = False) -> list[dict]:
    """Run all steps in a session and return results."""
    from src.evaluation.test_runner import query_rag

    results = []
    print(f"\n{'='*70}")
    print(f"Session: {session['name']}")
    if session.get("description"):
        print(f"  {session['description'][:100]}...")
    print(f"{'='*70}")

    for step in session["steps"]:
        step_id = step["id"]
        question = step["question"]
        print(f"\n  [{step_id}] {question[:60]}...", end=" ", flush=True)

        start = time.time()
        result = await query_rag(question, debug=debug)
        latency_ms = int((time.time() - start) * 1000)

        if result.get("error"):
            print(f"ERROR ({latency_ms}ms): {result['error'][:50]}")
            results.append({
                "step_id": step_id,
                "question": question,
                "pass": False,
                "route_ok": False,
                "expected_route": step.get("expected_route", "any"),
                "actual_route": "error",
                "issues": [f"ERROR: {result['error']}"],
                "response_preview": "",
                "latency_ms": latency_ms,
            })
            continue

        response = result.get("response", "")
        actual_route = result.get("actual_route", "semantic")

        check = check_step_result(step, response, actual_route)
        check["latency_ms"] = latency_ms
        results.append(check)

        status = "PASS" if check["pass"] else "FAIL"
        route_indicator = "R:Y" if check["route_ok"] else "R:N"
        print(f"{status} ({latency_ms}ms, {route_indicator})")

        if not check["pass"] and debug:
            for issue in check["issues"]:
                print(f"    [{issue}]")
            if debug:
                print(f"    Response: {response[:150]}...")

        if step.get("notes") and debug:
            print(f"    Note: {step['notes'][:80]}")

    return results


def print_summary(all_results: dict[str, list[dict]]):
    """Print summary of all session results."""
    print(f"\n{'='*70}")
    print("REGRESSION TEST SUMMARY")
    print(f"{'='*70}")

    total_steps = 0
    total_pass = 0
    total_route_ok = 0

    for session_name, results in all_results.items():
        session_pass = sum(1 for r in results if r["pass"])
        session_total = len(results)
        session_route_ok = sum(1 for r in results if r["route_ok"])
        total_steps += session_total
        total_pass += session_pass
        total_route_ok += session_route_ok

        status = "PASS" if session_pass == session_total else "FAIL"
        print(f"\n  {status} {session_name}: {session_pass}/{session_total} steps passed, "
              f"{session_route_ok}/{session_total} routes correct")

        # Show failures
        for r in results:
            if not r["pass"]:
                print(f"    FAIL [{r['step_id']}] {r['question'][:50]}...")
                for issue in r["issues"]:
                    print(f"      - {issue}")

    print(f"\n{'='*70}")
    print(f"TOTAL: {total_pass}/{total_steps} steps passed, "
          f"{total_route_ok}/{total_steps} routes correct")

    if total_pass == total_steps:
        print("ALL REGRESSION TESTS PASSED")
    else:
        print(f"FAILURES: {total_steps - total_pass} steps failed")
    print(f"{'='*70}")

    return total_pass == total_steps


async def main():
    parser = argparse.ArgumentParser(description="Run regression tests from YAML session scripts")
    parser.add_argument("--session", help="Run only this session (filename without .yaml)")
    parser.add_argument("--dry-run", action="store_true", help="Parse YAML only, don't run queries")
    parser.add_argument("--debug", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Find YAML files
    regression_dir = Path(__file__).parent
    if args.session:
        yaml_files = [regression_dir / f"{args.session}.yaml"]
        if not yaml_files[0].exists():
            print(f"Session not found: {yaml_files[0]}")
            return 1
    else:
        yaml_files = sorted(regression_dir.glob("session_*.yaml"))

    if not yaml_files:
        print("No regression test files found.")
        return 1

    # Load sessions
    sessions = {}
    for yaml_path in yaml_files:
        try:
            session = load_session(yaml_path)
            sessions[yaml_path.stem] = session
            print(f"Loaded: {yaml_path.name} ({len(session['steps'])} steps)")
        except Exception as e:
            print(f"Error loading {yaml_path.name}: {e}")
            return 1

    if args.dry_run:
        total_steps = sum(len(s["steps"]) for s in sessions.values())
        print(f"\nDry run: {len(sessions)} sessions, {total_steps} total steps")
        for name, session in sessions.items():
            print(f"  {name}: {session['name']}")
            for step in session["steps"]:
                route = step.get("expected_route", "any")
                print(f"    [{step['id']}] route={route}: {step['question'][:50]}...")
        return 0

    # Configure logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Run sessions
    all_results = {}
    for name, session in sessions.items():
        results = await run_session(session, debug=args.debug)
        all_results[name] = results

    # Print summary
    all_passed = print_summary(all_results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
