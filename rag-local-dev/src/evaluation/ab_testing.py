"""
A/B testing framework for comparing RAG configurations.
"""

from typing import Dict, List, Callable
from dataclasses import dataclass
import yaml
import copy
from pathlib import Path

from src.evaluation.metrics import calculate_all_metrics, RetrievalMetrics


@dataclass
class ExperimentConfig:
    name: str
    description: str
    config_overrides: Dict  # Overrides to apply to base config


@dataclass
class ExperimentResult:
    config: ExperimentConfig
    metrics: RetrievalMetrics
    detailed_results: List[Dict]


def create_experiment_variants() -> List[ExperimentConfig]:
    """
    Define experiment variants to test.
    Each variant modifies specific configuration parameters.
    """
    return [
        ExperimentConfig(
            name="baseline", description="Current production configuration", config_overrides={}
        ),
        # Alpha tuning experiments
        ExperimentConfig(
            name="alpha_high",
            description="Higher vector weight (alpha=0.9)",
            config_overrides={"search": {"default_alpha": 0.9}},
        ),
        ExperimentConfig(
            name="alpha_low",
            description="Lower vector weight (alpha=0.5)",
            config_overrides={"search": {"default_alpha": 0.5}},
        ),
        # Chunk size experiments (would require re-indexing)
        ExperimentConfig(
            name="larger_chunks",
            description="Larger chunks (600 tokens)",
            config_overrides={"chunking": {"target_chunk_tokens": 600, "max_chunk_tokens": 700}},
        ),
        ExperimentConfig(
            name="smaller_chunks",
            description="Smaller chunks (300 tokens)",
            config_overrides={"chunking": {"target_chunk_tokens": 300, "max_chunk_tokens": 400}},
        ),
        # Query type alpha presets
        ExperimentConfig(
            name="aggressive_semantic",
            description="Very high alpha for semantic queries",
            config_overrides={
                "search": {
                    "alpha_presets": {
                        "semantic": 0.95,
                        "exact_match": 0.2,
                        "terminology": 0.3,
                        "mixed": 0.7,
                    }
                }
            },
        ),
    ]


def apply_config_overrides(base_config: Dict, overrides: Dict) -> Dict:
    """Apply nested overrides to base configuration."""
    result = copy.deepcopy(base_config)

    def deep_update(d, u):
        for k, v in u.items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                deep_update(d[k], v)
            else:
                d[k] = v

    deep_update(result, overrides)
    return result


def run_ab_experiment(
    run_evaluation_fn: Callable, variants: List[ExperimentConfig] = None
) -> List[ExperimentResult]:
    """
    Run A/B experiment across multiple configuration variants.

    Note: Variants that change chunking require re-indexing,
    which this function does NOT handle automatically.
    """
    if variants is None:
        variants = create_experiment_variants()

    # Load base config
    with open("config.yaml") as f:
        base_config = yaml.safe_load(f)

    results = []

    for variant in variants:
        print(f"\n Running experiment: {variant.name}")
        print(f"   {variant.description}")

        # Apply overrides
        test_config = apply_config_overrides(base_config, variant.config_overrides)

        # Note: For proper A/B testing, you'd need to:
        # 1. Save test_config to a temp file
        # 2. Have run_evaluation_fn load from that file
        # 3. Or pass config directly to the evaluation function

        # For now, this is a simplified version
        metrics, detailed, _ = run_evaluation_fn()

        results.append(
            ExperimentResult(config=variant, metrics=metrics, detailed_results=detailed)
        )

    return results


def print_ab_results(results: List[ExperimentResult]):
    """Print A/B experiment results comparison."""
    print("\n" + "=" * 80)
    print(" A/B EXPERIMENT RESULTS")
    print("=" * 80)

    # Header
    print(
        f"\n{'Variant':<25} {'Recall@5':>10} {'MRR':>10} {'NDCG@5':>10} {'P95 Latency':>12}"
    )
    print("-" * 80)

    # Find best for each metric
    best_recall = max(r.metrics.recall_at_5 for r in results)
    best_mrr = max(r.metrics.mrr for r in results)
    best_ndcg = max(r.metrics.ndcg_at_5 for r in results)
    best_latency = min(r.metrics.p95_latency_ms for r in results)

    for result in results:
        m = result.metrics

        # Mark best values
        recall_mark = "*" if m.recall_at_5 == best_recall else " "
        mrr_mark = "*" if m.mrr == best_mrr else " "
        ndcg_mark = "*" if m.ndcg_at_5 == best_ndcg else " "
        latency_mark = "*" if m.p95_latency_ms == best_latency else " "

        print(
            f"{result.config.name:<25} "
            f"{m.recall_at_5:>9.3f}{recall_mark} "
            f"{m.mrr:>9.3f}{mrr_mark} "
            f"{m.ndcg_at_5:>9.3f}{ndcg_mark} "
            f"{m.p95_latency_ms:>10.1f}ms{latency_mark}"
        )

    print("\n* = Best in category")
