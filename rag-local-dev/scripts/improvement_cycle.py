"""
Automated improvement cycle for RAG system.
Identifies issues, suggests fixes, and tracks progress over time.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import json
from datetime import datetime
import logging

from scripts.run_evaluation import run_evaluation, save_results
from src.evaluation.failure_analysis import (
    analyze_failures,
    generate_failure_report,
    suggest_improvements,
)
from src.evaluation.metrics import print_metrics_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_baseline():
    """Load the baseline metrics for comparison."""
    baseline_path = Path(__file__).parent.parent / "evaluation" / "baseline_metrics.json"
    if baseline_path.exists():
        with open(baseline_path) as f:
            return json.load(f)
    return None


def save_baseline(metrics):
    """Save current metrics as new baseline."""
    baseline_path = Path(__file__).parent.parent / "evaluation" / "baseline_metrics.json"
    with open(baseline_path, "w") as f:
        json.dump(vars(metrics), f, indent=2)
    logger.info(f"Saved new baseline to {baseline_path}")


def compare_to_baseline(current_metrics, baseline: dict) -> dict:
    """Compare current metrics to baseline."""
    if not baseline:
        return None

    comparisons = {}
    current = vars(current_metrics)

    for key in current:
        if key in baseline:
            current_val = current[key]
            baseline_val = baseline[key]

            if isinstance(current_val, (int, float)) and isinstance(baseline_val, (int, float)):
                diff = current_val - baseline_val
                pct_change = (diff / baseline_val * 100) if baseline_val != 0 else 0

                comparisons[key] = {
                    "current": current_val,
                    "baseline": baseline_val,
                    "diff": diff,
                    "pct_change": pct_change,
                    "improved": diff > 0
                    if key
                    not in [
                        "no_results_rate",
                        "low_confidence_rate",
                        "mean_latency_ms",
                        "p95_latency_ms",
                    ]
                    else diff < 0,
                }

    return comparisons


def print_comparison(comparisons: dict):
    """Print comparison to baseline."""
    if not comparisons:
        print("\n No baseline to compare against.")
        return

    print("\n" + "=" * 60)
    print(" COMPARISON TO BASELINE")
    print("=" * 60)

    for key, comp in comparisons.items():
        indicator = "[+]" if comp["improved"] else "[-]" if comp["diff"] != 0 else "[=]"
        sign = "+" if comp["diff"] > 0 else ""

        # Only show significant metrics
        if key in [
            "recall_at_5",
            "recall_at_10",
            "mrr",
            "ndcg_at_5",
            "precision_at_5",
            "query_type_accuracy",
            "mean_latency_ms",
            "no_results_rate",
        ]:
            print(
                f"  {indicator} {key}: {comp['current']:.3f} "
                f"(was {comp['baseline']:.3f}, {sign}{comp['diff']:.3f}, {sign}{comp['pct_change']:.1f}%)"
            )


def run_improvement_cycle(set_baseline: bool = False, verbose: bool = False):
    """
    Run one improvement cycle:
    1. Run evaluation
    2. Analyze failures
    3. Compare to baseline
    4. Generate suggestions
    """
    print("\n STARTING IMPROVEMENT CYCLE")
    print("=" * 60)

    # Run evaluation
    logger.info("Running evaluation...")
    metrics, results, failures = run_evaluation(verbose=verbose)

    if not metrics:
        print("No results to evaluate. Exiting.")
        return

    # Print metrics
    print_metrics_report(metrics)

    # Compare to baseline
    baseline = load_baseline()
    comparisons = compare_to_baseline(metrics, baseline)
    print_comparison(comparisons)

    # Analyze failures
    logger.info("Analyzing failures...")
    analysis = analyze_failures(results)
    print(generate_failure_report(analysis))

    # Generate suggestions
    print("\n IMPROVEMENT SUGGESTIONS:")
    suggestions = suggest_improvements(analysis)
    for i, suggestion in enumerate(suggestions, 1):
        print(f"\n{i}. {suggestion}")

    # Save results
    save_results(metrics, results, failures)

    # Optionally set as new baseline
    if set_baseline:
        save_baseline(metrics)

    # Summary
    print("\n" + "=" * 60)
    print(" CYCLE SUMMARY")
    print("=" * 60)
    print(f"  Recall@5:  {metrics.recall_at_5:.3f}")
    print(f"  MRR:       {metrics.mrr:.3f}")
    print(f"  Failures:  {analysis['failure_rate']:.1%}")

    if baseline and comparisons:
        recall_improved = comparisons.get("recall_at_5", {}).get("improved", False)
        print(f"  vs Baseline: {'Improved' if recall_improved else 'Regressed'}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run RAG improvement cycle")
    parser.add_argument(
        "--set-baseline", action="store_true", help="Set current results as new baseline"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    run_improvement_cycle(set_baseline=args.set_baseline, verbose=args.verbose)


if __name__ == "__main__":
    main()
