"""
Evaluation metrics for RAG system.
"""

from typing import List, Optional
from dataclasses import dataclass


@dataclass
class RetrievalMetrics:
    """Metrics for a single retrieval query."""

    recall_at_k: dict  # {k: recall_value}
    mrr: float  # Mean Reciprocal Rank
    precision_at_k: dict  # {k: precision_value}
    ndcg_at_k: dict  # {k: ndcg_value}


def calculate_recall_at_k(
    retrieved_ids: List[str], relevant_ids: List[str], k_values: List[int] = [5, 10]
) -> dict:
    """
    Calculate Recall@K for different K values.

    Args:
        retrieved_ids: List of retrieved document IDs in ranked order
        relevant_ids: List of relevant document IDs (ground truth)
        k_values: List of K values to calculate recall for

    Returns:
        Dict mapping K to recall value
    """
    if not relevant_ids:
        return {k: 0.0 for k in k_values}

    relevant_set = set(relevant_ids)
    results = {}

    for k in k_values:
        retrieved_at_k = set(retrieved_ids[:k])
        hits = len(retrieved_at_k & relevant_set)
        results[k] = hits / len(relevant_set)

    return results


def calculate_mrr(retrieved_ids: List[str], relevant_ids: List[str]) -> float:
    """
    Calculate Mean Reciprocal Rank.

    MRR is the reciprocal of the rank of the first relevant result.

    Args:
        retrieved_ids: List of retrieved document IDs in ranked order
        relevant_ids: List of relevant document IDs (ground truth)

    Returns:
        MRR score (0.0 if no relevant results found)
    """
    if not relevant_ids:
        return 0.0

    relevant_set = set(relevant_ids)

    for rank, doc_id in enumerate(retrieved_ids, 1):
        if doc_id in relevant_set:
            return 1.0 / rank

    return 0.0


def calculate_precision_at_k(
    retrieved_ids: List[str], relevant_ids: List[str], k_values: List[int] = [5, 10]
) -> dict:
    """
    Calculate Precision@K for different K values.

    Args:
        retrieved_ids: List of retrieved document IDs in ranked order
        relevant_ids: List of relevant document IDs (ground truth)
        k_values: List of K values to calculate precision for

    Returns:
        Dict mapping K to precision value
    """
    if not relevant_ids:
        return {k: 0.0 for k in k_values}

    relevant_set = set(relevant_ids)
    results = {}

    for k in k_values:
        retrieved_at_k = retrieved_ids[:k]
        if not retrieved_at_k:
            results[k] = 0.0
            continue
        hits = sum(1 for doc_id in retrieved_at_k if doc_id in relevant_set)
        results[k] = hits / len(retrieved_at_k)

    return results


def calculate_ndcg_at_k(
    retrieved_ids: List[str],
    relevant_ids: List[str],
    relevance_scores: Optional[dict] = None,
    k_values: List[int] = [5, 10],
) -> dict:
    """
    Calculate Normalized Discounted Cumulative Gain (NDCG) at K.

    Args:
        retrieved_ids: List of retrieved document IDs in ranked order
        relevant_ids: List of relevant document IDs (ground truth)
        relevance_scores: Optional dict mapping doc_id to relevance score (default: 1 for relevant)
        k_values: List of K values to calculate NDCG for

    Returns:
        Dict mapping K to NDCG value
    """
    import math

    if not relevant_ids:
        return {k: 0.0 for k in k_values}

    # Default relevance: 1 for relevant, 0 for non-relevant
    if relevance_scores is None:
        relevance_scores = {doc_id: 1.0 for doc_id in relevant_ids}

    def dcg_at_k(ranked_ids: List[str], k: int) -> float:
        dcg = 0.0
        for i, doc_id in enumerate(ranked_ids[:k], 1):
            rel = relevance_scores.get(doc_id, 0.0)
            dcg += (2**rel - 1) / math.log2(i + 1)
        return dcg

    def ideal_dcg_at_k(k: int) -> float:
        # Sort relevance scores in descending order
        sorted_scores = sorted(relevance_scores.values(), reverse=True)[:k]
        idcg = 0.0
        for i, rel in enumerate(sorted_scores, 1):
            idcg += (2**rel - 1) / math.log2(i + 1)
        return idcg

    results = {}
    for k in k_values:
        dcg = dcg_at_k(retrieved_ids, k)
        idcg = ideal_dcg_at_k(k)
        results[k] = dcg / idcg if idcg > 0 else 0.0

    return results


def evaluate_retrieval(
    retrieved_ids: List[str],
    relevant_ids: List[str],
    relevance_scores: Optional[dict] = None,
    k_values: List[int] = [5, 10],
) -> RetrievalMetrics:
    """
    Calculate all retrieval metrics for a single query.

    Args:
        retrieved_ids: List of retrieved document IDs in ranked order
        relevant_ids: List of relevant document IDs (ground truth)
        relevance_scores: Optional dict mapping doc_id to relevance score
        k_values: List of K values to calculate metrics for

    Returns:
        RetrievalMetrics dataclass with all metrics
    """
    return RetrievalMetrics(
        recall_at_k=calculate_recall_at_k(retrieved_ids, relevant_ids, k_values),
        mrr=calculate_mrr(retrieved_ids, relevant_ids),
        precision_at_k=calculate_precision_at_k(retrieved_ids, relevant_ids, k_values),
        ndcg_at_k=calculate_ndcg_at_k(retrieved_ids, relevant_ids, relevance_scores, k_values),
    )


def aggregate_metrics(all_metrics: List[RetrievalMetrics]) -> dict:
    """
    Aggregate metrics across multiple queries.

    Returns mean values for all metrics.
    """
    if not all_metrics:
        return {}

    n = len(all_metrics)

    # Get K values from first result
    k_values = list(all_metrics[0].recall_at_k.keys())

    return {
        "mean_recall": {k: sum(m.recall_at_k[k] for m in all_metrics) / n for k in k_values},
        "mean_precision": {k: sum(m.precision_at_k[k] for m in all_metrics) / n for k in k_values},
        "mean_ndcg": {k: sum(m.ndcg_at_k[k] for m in all_metrics) / n for k in k_values},
        "mean_mrr": sum(m.mrr for m in all_metrics) / n,
        "total_queries": n,
    }
