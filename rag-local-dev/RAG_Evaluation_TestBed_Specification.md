# RAG Evaluation & Test Bed: Complete Specification

## Overview

This document specifies a comprehensive evaluation framework for the RAG system. The goal is to establish measurable baselines, identify failure modes, and enable systematic improvement through iterative testing.

**Philosophy**: "You can't improve what you can't measure."

---

## Evaluation Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     RAG Evaluation Pipeline                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Test Set   │───▶│  RAG System  │───▶│   Metrics    │       │
│  │  Generation  │    │  Under Test  │    │  Calculation │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Golden     │    │  Retrieval   │    │   Reports &  │       │
│  │   Dataset    │    │    Logs      │    │  Dashboards  │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         └───────────────────┴───────────────────┘                │
│                             │                                    │
│                             ▼                                    │
│                    ┌──────────────┐                              │
│                    │   Failure    │                              │
│                    │   Analysis   │                              │
│                    └──────────────┘                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Golden Dataset Creation

### 1.1 Structure

Create file: `evaluation/golden_dataset.yaml`

```yaml
# Golden Dataset for RAG Evaluation
# Each entry has a query, expected chunks, and relevance judgments

metadata:
  version: "1.0"
  created_date: "2025-01-27"
  last_updated: "2025-01-27"
  total_queries: 100  # Target: 100+ queries for statistical significance
  annotator: "human"  # or "llm-assisted"

# Relevance scale:
# 3 = Perfect match (directly answers the query)
# 2 = Highly relevant (contains key information)
# 1 = Partially relevant (tangentially related)
# 0 = Not relevant

queries:
  # ============================================
  # CATEGORY: ADR Retrieval
  # ============================================
  
  - id: "adr-001"
    query: "What is our decision on event-driven architecture?"
    category: "adr_semantic"
    language: "en"
    expected_query_type: "semantic"
    
    relevant_chunks:
      - chunk_id: null  # Fill after indexing
        document_id: "ADR-007"
        section: "Decision"
        relevance: 3
        rationale: "Contains the actual decision on event-driven architecture"
      - chunk_id: null
        document_id: "ADR-007"
        section: "Context"
        relevance: 2
        rationale: "Provides background for the decision"
      - chunk_id: null
        document_id: "ADR-012"
        section: "Decision"
        relevance: 1
        rationale: "Related messaging pattern decision"
    
    irrelevant_chunks:
      - document_id: "ADR-003"
        rationale: "About database selection, not architecture patterns"
    
    expected_alpha: 0.8
    difficulty: "easy"
    
  - id: "adr-002"
    query: "ADR-007"
    category: "adr_exact"
    language: "en"
    expected_query_type: "exact_match"
    
    relevant_chunks:
      - document_id: "ADR-007"
        section: "*"  # All sections
        relevance: 3
        rationale: "Exact document match"
    
    expected_alpha: 0.3
    difficulty: "easy"

  - id: "adr-003"
    query: "Why did we reject microservices for the grid platform?"
    category: "adr_semantic"
    language: "en"
    expected_query_type: "semantic"
    
    relevant_chunks:
      - document_id: "ADR-015"
        section: "Consequences"
        relevance: 3
        rationale: "Discusses rejected alternatives"
    
    difficulty: "medium"
    notes: "Tests retrieval of 'negative' information (rejections)"

  # ============================================
  # CATEGORY: Principle Retrieval
  # ============================================
  
  - id: "prin-001"
    query: "What principles guide our data governance?"
    category: "principle_semantic"
    language: "en"
    expected_query_type: "semantic"
    
    relevant_chunks:
      - document_id: "PRINCIPLE-003"
        relevance: 3
      - document_id: "PRINCIPLE-017"
        relevance: 2
    
    difficulty: "easy"

  - id: "prin-002"
    query: "PRINCIPLE-012"
    category: "principle_exact"
    language: "en"
    expected_query_type: "exact_match"
    
    relevant_chunks:
      - document_id: "PRINCIPLE-012"
        section: "*"
        relevance: 3
    
    difficulty: "easy"

  # ============================================
  # CATEGORY: ArchiMate Retrieval
  # ============================================
  
  - id: "arch-001"
    query: "How do application components relate to business processes in ArchiMate?"
    category: "archimate_semantic"
    language: "en"
    expected_query_type: "semantic"
    
    relevant_chunks:
      - source_file: "archimate_spec.pdf"
        page_range: [45, 52]  # Approximate
        relevance: 3
        rationale: "Chapter on cross-layer relationships"
    
    difficulty: "medium"

  - id: "arch-002"
    query: "application component"
    category: "archimate_element"
    language: "en"
    expected_query_type: "semantic"  # Not terminology!
    
    relevant_chunks:
      - source_file: "archimate_spec.pdf"
        section: "Application Layer"
        relevance: 3
    
    difficulty: "easy"
    notes: "Tests that ArchiMate elements trigger semantic, not terminology lookup"

  - id: "arch-003"
    query: "realization relationship between application and technology"
    category: "archimate_relationship"
    language: "en"
    expected_query_type: "semantic"
    
    relevant_chunks:
      - source_file: "archimate_spec.pdf"
        section: "Relationships"
        relevance: 3
    
    difficulty: "medium"

  # ============================================
  # CATEGORY: Terminology Retrieval
  # ============================================
  
  - id: "term-001"
    query: "netbeheerder"
    category: "terminology_dutch"
    language: "nl"
    expected_query_type: "terminology"
    
    relevant_terms:
      - concept_uri: "http://example.org/ontology#netbeheerder"
        pref_label_nl: "netbeheerder"
        relevance: 3
    
    difficulty: "easy"

  - id: "term-002"
    query: "DSO"
    category: "terminology_abbreviation"
    language: "en"
    expected_query_type: "terminology"
    
    relevant_terms:
      - pref_label_en: "Distribution System Operator"
        relevance: 3
    
    difficulty: "easy"
    notes: "Tests abbreviation in terminology lookup"

  # ============================================
  # CATEGORY: Energy Domain (Semantic Triggers)
  # ============================================
  
  - id: "energy-001"
    query: "transformer protection settings"
    category: "energy_semantic"
    language: "en"
    expected_query_type: "semantic"
    
    notes: "Should trigger semantic search, not terminology"
    difficulty: "medium"

  - id: "energy-002"
    query: "netverliezen berekening methodiek"
    category: "energy_dutch"
    language: "nl"
    expected_query_type: "semantic"
    
    notes: "Dutch grid loss calculation - semantic search"
    difficulty: "medium"

  - id: "energy-003"
    query: "slimme meter data integratie"
    category: "energy_dutch"
    language: "nl"
    expected_query_type: "semantic"
    
    notes: "Smart meter integration - semantic search"
    difficulty: "medium"

  - id: "energy-004"
    query: "IEC 61968 message patterns"
    category: "energy_standards"
    language: "en"
    expected_query_type: "semantic"
    
    difficulty: "hard"
    notes: "Cross-reference between standards and ADRs"

  # ============================================
  # CATEGORY: Cross-Document Queries
  # ============================================
  
  - id: "cross-001"
    query: "How does the data object principle relate to our CIM implementation decision?"
    category: "cross_document"
    language: "en"
    expected_query_type: "semantic"
    
    relevant_chunks:
      - document_id: "PRINCIPLE-008"
        relevance: 3
      - document_id: "ADR-023"
        relevance: 3
    
    difficulty: "hard"
    notes: "Requires finding connections across document types"

  - id: "cross-002"
    query: "Which ADRs implement the separation of concerns principle?"
    category: "cross_document"
    language: "en"
    expected_query_type: "semantic"
    
    difficulty: "hard"
    notes: "Requires understanding principle-to-ADR relationships"

  # ============================================
  # CATEGORY: Negative/Edge Cases
  # ============================================
  
  - id: "neg-001"
    query: "quantum computing integration"
    category: "negative"
    language: "en"
    expected_query_type: "semantic"
    
    relevant_chunks: []  # Nothing should be highly relevant
    
    expected_behavior: "no_good_results should be true"
    difficulty: "easy"
    notes: "Tests system behavior when no relevant content exists"

  - id: "neg-002"
    query: "asdfghjkl"
    category: "negative_gibberish"
    language: "en"
    expected_query_type: "mixed"
    
    relevant_chunks: []
    
    expected_behavior: "Graceful handling of nonsense input"
    difficulty: "easy"

  - id: "edge-001"
    query: "What"
    category: "edge_short"
    language: "en"
    expected_query_type: "mixed"
    
    expected_behavior: "Should not crash, may suggest refinement"
    difficulty: "easy"

  - id: "edge-002"
    query: "Tell me everything about all the architectural decisions we've made regarding data management, integration patterns, API design, security, authentication, authorization, logging, monitoring, deployment, and infrastructure as it relates to the grid foundation model and smart metering initiatives"
    category: "edge_long"
    language: "en"
    expected_query_type: "semantic"
    
    difficulty: "hard"
    notes: "Very long query - tests handling of complex queries"

  # ============================================
  # CATEGORY: Bilingual Queries
  # ============================================
  
  - id: "lang-001"
    query: "Wat is het besluit over event-driven architectuur?"
    category: "bilingual_dutch"
    language: "nl"
    expected_query_type: "semantic"
    
    relevant_chunks:
      - document_id: "ADR-007"
        relevance: 3
    
    difficulty: "medium"
    notes: "Dutch query should find English ADR content"

  - id: "lang-002"
    query: "architectuurprincipes voor data sovereignty"
    category: "bilingual_dutch"
    language: "nl"
    expected_query_type: "semantic"
    
    difficulty: "medium"
    notes: "Mixed Dutch/English technical terms"
```

### 1.2 Golden Dataset Population Script

Create file: `scripts/populate_golden_dataset.py`

```python
"""
Populate golden dataset with actual chunk IDs after indexing.
Run this after index_documents.py to link queries to real chunks.
"""

import yaml
import psycopg2
from pathlib import Path
import os


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def get_connection(config):
    return psycopg2.connect(
        host=config["database"]["host"],
        port=config["database"]["port"],
        dbname=config["database"]["name"],
        user=config["database"]["user"],
        password=os.environ.get("RAG_DB_PASSWORD", "")
    )


def find_chunk_ids(conn, document_id: str, section: str = None) -> list:
    """Find chunk IDs for a document, optionally filtered by section."""
    query = "SELECT id FROM chunks WHERE document_id = %s"
    params = [document_id]
    
    if section and section != "*":
        query += " AND section_header = %s"
        params.append(section)
    
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [row[0] for row in cur.fetchall()]


def find_term_ids(conn, pref_label: str = None, concept_uri: str = None) -> list:
    """Find terminology IDs by label or URI."""
    if concept_uri:
        query = "SELECT id FROM terminology WHERE concept_uri = %s"
        params = [concept_uri]
    elif pref_label:
        query = "SELECT id FROM terminology WHERE pref_label_en ILIKE %s OR pref_label_nl ILIKE %s"
        params = [f"%{pref_label}%", f"%{pref_label}%"]
    else:
        return []
    
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [row[0] for row in cur.fetchall()]


def populate_golden_dataset():
    config = load_config()
    conn = get_connection(config)
    
    # Load golden dataset
    golden_path = Path("evaluation/golden_dataset.yaml")
    with open(golden_path) as f:
        golden = yaml.safe_load(f)
    
    updated_count = 0
    
    for query_entry in golden.get("queries", []):
        # Populate chunk IDs for relevant chunks
        for chunk in query_entry.get("relevant_chunks", []):
            if chunk.get("document_id"):
                chunk_ids = find_chunk_ids(
                    conn, 
                    chunk["document_id"], 
                    chunk.get("section")
                )
                if chunk_ids:
                    chunk["chunk_ids"] = chunk_ids
                    updated_count += 1
        
        # Populate term IDs for relevant terms
        for term in query_entry.get("relevant_terms", []):
            term_ids = find_term_ids(
                conn,
                pref_label=term.get("pref_label_en") or term.get("pref_label_nl"),
                concept_uri=term.get("concept_uri")
            )
            if term_ids:
                term["term_ids"] = term_ids
                updated_count += 1
    
    # Save updated golden dataset
    output_path = Path("evaluation/golden_dataset_populated.yaml")
    with open(output_path, "w") as f:
        yaml.dump(golden, f, default_flow_style=False, allow_unicode=True)
    
    print(f"Updated {updated_count} entries")
    print(f"Saved to {output_path}")
    
    conn.close()


if __name__ == "__main__":
    populate_golden_dataset()
```

---

## 2. Metrics Framework

### 2.1 Core Metrics

Create file: `src/evaluation/metrics.py`

```python
"""
Comprehensive metrics for RAG evaluation.
"""

from typing import List, Dict, Set, Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class RetrievalMetrics:
    """Container for all retrieval metrics."""
    
    # Recall metrics
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    recall_at_20: float
    
    # Precision metrics
    precision_at_1: float
    precision_at_5: float
    precision_at_10: float
    
    # Ranking metrics
    mrr: float  # Mean Reciprocal Rank
    ndcg_at_5: float  # Normalized Discounted Cumulative Gain
    ndcg_at_10: float
    map_score: float  # Mean Average Precision
    
    # Classification metrics (for query type detection)
    query_type_accuracy: float
    language_detection_accuracy: float
    
    # Latency metrics
    mean_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    
    # Coverage metrics
    no_results_rate: float  # % of queries with no results
    low_confidence_rate: float  # % of queries below confidence threshold


def recall_at_k(retrieved_ids: List[int], relevant_ids: Set[int], k: int) -> float:
    """
    Calculate Recall@K.
    
    Recall@K = |relevant ∩ retrieved@K| / |relevant|
    """
    if not relevant_ids:
        return 1.0  # If nothing is relevant, perfect recall by definition
    
    retrieved_at_k = set(retrieved_ids[:k])
    hits = len(retrieved_at_k & relevant_ids)
    return hits / len(relevant_ids)


def precision_at_k(retrieved_ids: List[int], relevant_ids: Set[int], k: int) -> float:
    """
    Calculate Precision@K.
    
    Precision@K = |relevant ∩ retrieved@K| / K
    """
    if k == 0:
        return 0.0
    
    retrieved_at_k = set(retrieved_ids[:k])
    hits = len(retrieved_at_k & relevant_ids)
    return hits / k


def mean_reciprocal_rank(retrieved_ids: List[int], relevant_ids: Set[int]) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR).
    
    MRR = 1 / rank of first relevant result
    """
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def dcg_at_k(relevance_scores: List[float], k: int) -> float:
    """
    Calculate Discounted Cumulative Gain at K.
    
    DCG@K = Σ (2^rel_i - 1) / log2(i + 2)
    """
    dcg = 0.0
    for i, rel in enumerate(relevance_scores[:k]):
        dcg += (2 ** rel - 1) / np.log2(i + 2)
    return dcg


def ndcg_at_k(
    retrieved_ids: List[int], 
    relevance_map: Dict[int, float],  # chunk_id -> relevance score
    k: int
) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain at K.
    
    NDCG@K = DCG@K / IDCG@K
    """
    # Get relevance scores for retrieved documents
    retrieved_relevance = [relevance_map.get(doc_id, 0) for doc_id in retrieved_ids[:k]]
    
    # Calculate DCG
    dcg = dcg_at_k(retrieved_relevance, k)
    
    # Calculate ideal DCG (sorted by relevance)
    ideal_relevance = sorted(relevance_map.values(), reverse=True)[:k]
    idcg = dcg_at_k(ideal_relevance, k)
    
    if idcg == 0:
        return 0.0
    
    return dcg / idcg


def average_precision(retrieved_ids: List[int], relevant_ids: Set[int]) -> float:
    """
    Calculate Average Precision for a single query.
    
    AP = (1/|relevant|) * Σ (Precision@k * rel(k))
    """
    if not relevant_ids:
        return 1.0
    
    num_relevant = 0
    precision_sum = 0.0
    
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in relevant_ids:
            num_relevant += 1
            precision_sum += num_relevant / (i + 1)
    
    return precision_sum / len(relevant_ids)


def calculate_all_metrics(
    results: List[Dict],  # List of {query_id, retrieved_ids, relevant_ids, relevance_map, ...}
    confidence_threshold: float = 0.4
) -> RetrievalMetrics:
    """
    Calculate all metrics across a set of query results.
    """
    n = len(results)
    if n == 0:
        raise ValueError("No results to evaluate")
    
    # Aggregate metrics
    recall_1 = []
    recall_5 = []
    recall_10 = []
    recall_20 = []
    precision_1 = []
    precision_5 = []
    precision_10 = []
    mrr_scores = []
    ndcg_5 = []
    ndcg_10 = []
    ap_scores = []
    latencies = []
    query_type_correct = []
    language_correct = []
    no_results = 0
    low_confidence = 0
    
    for r in results:
        retrieved = r["retrieved_ids"]
        relevant = set(r["relevant_ids"])
        relevance_map = r.get("relevance_map", {rid: 1.0 for rid in relevant})
        
        # Recall
        recall_1.append(recall_at_k(retrieved, relevant, 1))
        recall_5.append(recall_at_k(retrieved, relevant, 5))
        recall_10.append(recall_at_k(retrieved, relevant, 10))
        recall_20.append(recall_at_k(retrieved, relevant, 20))
        
        # Precision
        precision_1.append(precision_at_k(retrieved, relevant, 1))
        precision_5.append(precision_at_k(retrieved, relevant, 5))
        precision_10.append(precision_at_k(retrieved, relevant, 10))
        
        # Ranking
        mrr_scores.append(mean_reciprocal_rank(retrieved, relevant))
        ndcg_5.append(ndcg_at_k(retrieved, relevance_map, 5))
        ndcg_10.append(ndcg_at_k(retrieved, relevance_map, 10))
        ap_scores.append(average_precision(retrieved, relevant))
        
        # Latency
        if "latency_ms" in r:
            latencies.append(r["latency_ms"])
        
        # Query type accuracy
        if "expected_query_type" in r and "detected_query_type" in r:
            query_type_correct.append(
                1 if r["expected_query_type"] == r["detected_query_type"] else 0
            )
        
        # Language detection accuracy
        if "expected_language" in r and "detected_language" in r:
            language_correct.append(
                1 if r["expected_language"] == r["detected_language"] else 0
            )
        
        # Coverage
        if len(retrieved) == 0:
            no_results += 1
        if r.get("confidence", 1.0) < confidence_threshold:
            low_confidence += 1
    
    # Calculate latency percentiles
    latencies_sorted = sorted(latencies) if latencies else [0]
    
    return RetrievalMetrics(
        recall_at_1=np.mean(recall_1),
        recall_at_5=np.mean(recall_5),
        recall_at_10=np.mean(recall_10),
        recall_at_20=np.mean(recall_20),
        precision_at_1=np.mean(precision_1),
        precision_at_5=np.mean(precision_5),
        precision_at_10=np.mean(precision_10),
        mrr=np.mean(mrr_scores),
        ndcg_at_5=np.mean(ndcg_5),
        ndcg_at_10=np.mean(ndcg_10),
        map_score=np.mean(ap_scores),
        query_type_accuracy=np.mean(query_type_correct) if query_type_correct else 0.0,
        language_detection_accuracy=np.mean(language_correct) if language_correct else 0.0,
        mean_latency_ms=np.mean(latencies) if latencies else 0.0,
        p50_latency_ms=np.percentile(latencies_sorted, 50),
        p95_latency_ms=np.percentile(latencies_sorted, 95),
        p99_latency_ms=np.percentile(latencies_sorted, 99),
        no_results_rate=no_results / n,
        low_confidence_rate=low_confidence / n,
    )


def print_metrics_report(metrics: RetrievalMetrics, title: str = "Evaluation Results"):
    """Print a formatted metrics report."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print('=' * 60)
    
    print("\n📊 RECALL METRICS")
    print(f"   Recall@1:  {metrics.recall_at_1:.3f}")
    print(f"   Recall@5:  {metrics.recall_at_5:.3f}")
    print(f"   Recall@10: {metrics.recall_at_10:.3f}")
    print(f"   Recall@20: {metrics.recall_at_20:.3f}")
    
    print("\n🎯 PRECISION METRICS")
    print(f"   Precision@1:  {metrics.precision_at_1:.3f}")
    print(f"   Precision@5:  {metrics.precision_at_5:.3f}")
    print(f"   Precision@10: {metrics.precision_at_10:.3f}")
    
    print("\n📈 RANKING METRICS")
    print(f"   MRR:      {metrics.mrr:.3f}")
    print(f"   NDCG@5:   {metrics.ndcg_at_5:.3f}")
    print(f"   NDCG@10:  {metrics.ndcg_at_10:.3f}")
    print(f"   MAP:      {metrics.map_score:.3f}")
    
    print("\n🏷️ CLASSIFICATION ACCURACY")
    print(f"   Query Type Detection: {metrics.query_type_accuracy:.1%}")
    print(f"   Language Detection:   {metrics.language_detection_accuracy:.1%}")
    
    print("\n⏱️ LATENCY")
    print(f"   Mean:  {metrics.mean_latency_ms:.1f} ms")
    print(f"   P50:   {metrics.p50_latency_ms:.1f} ms")
    print(f"   P95:   {metrics.p95_latency_ms:.1f} ms")
    print(f"   P99:   {metrics.p99_latency_ms:.1f} ms")
    
    print("\n📉 COVERAGE")
    print(f"   No Results Rate:     {metrics.no_results_rate:.1%}")
    print(f"   Low Confidence Rate: {metrics.low_confidence_rate:.1%}")
    
    print('=' * 60)
```

---

## 3. Evaluation Runner

Create file: `scripts/run_evaluation.py`

```python
"""
Main evaluation script.
Runs the full evaluation pipeline against the golden dataset.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
import json
import psycopg2
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import logging

from src.embedding.factory import get_embedder
from src.search.retrieval_tool import RetrievalTool
from src.evaluation.metrics import calculate_all_metrics, print_metrics_report, RetrievalMetrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def load_golden_dataset():
    """Load the populated golden dataset."""
    path = Path("evaluation/golden_dataset_populated.yaml")
    if not path.exists():
        path = Path("evaluation/golden_dataset.yaml")
        logger.warning("Using unpopulated golden dataset - chunk IDs may be missing")
    
    with open(path) as f:
        return yaml.safe_load(f)


def get_connection(config):
    return psycopg2.connect(
        host=config["database"]["host"],
        port=config["database"]["port"],
        dbname=config["database"]["name"],
        user=config["database"]["user"],
        password=os.environ.get("RAG_DB_PASSWORD", "")
    )


def collect_relevant_ids(query_entry: dict) -> tuple:
    """Extract relevant chunk IDs and relevance scores from golden dataset entry."""
    relevant_ids = set()
    relevance_map = {}
    
    for chunk in query_entry.get("relevant_chunks", []):
        chunk_ids = chunk.get("chunk_ids", [])
        relevance = chunk.get("relevance", 1)
        
        for cid in chunk_ids:
            relevant_ids.add(cid)
            relevance_map[cid] = relevance
    
    return relevant_ids, relevance_map


def run_single_query(
    tool: RetrievalTool, 
    query_entry: dict, 
    config: dict
) -> dict:
    """Run a single query and collect results."""
    query = query_entry["query"]
    expected_type = query_entry.get("expected_query_type")
    expected_lang = query_entry.get("language")
    
    # Execute search
    result = tool.search(
        query=query,
        max_chunks=20,  # Retrieve more for recall@20
        include_terminology=True
    )
    
    # Collect relevant IDs
    relevant_ids, relevance_map = collect_relevant_ids(query_entry)
    
    return {
        "query_id": query_entry["id"],
        "query": query,
        "category": query_entry.get("category"),
        "retrieved_ids": [c.chunk_id for c in result.chunks],
        "retrieved_scores": [c.score for c in result.chunks],
        "relevant_ids": list(relevant_ids),
        "relevance_map": relevance_map,
        "expected_query_type": expected_type,
        "detected_query_type": result.query_type_detected,
        "expected_language": expected_lang,
        "detected_language": None,  # Would need to extract from preprocessing
        "confidence": result.confidence,
        "no_good_results": result.no_good_results,
        "latency_ms": result.latency_ms,
    }


def run_evaluation(
    filter_category: str = None,
    filter_difficulty: str = None,
    verbose: bool = False
) -> tuple:
    """
    Run full evaluation.
    
    Args:
        filter_category: Only run queries matching this category
        filter_difficulty: Only run queries matching this difficulty
        verbose: Print details for each query
    
    Returns:
        (metrics, detailed_results)
    """
    config = load_config()
    golden = load_golden_dataset()
    
    conn = get_connection(config)
    embedder = get_embedder(config)
    tool = RetrievalTool(conn, embedder, config)
    
    queries = golden.get("queries", [])
    
    # Apply filters
    if filter_category:
        queries = [q for q in queries if q.get("category") == filter_category]
    if filter_difficulty:
        queries = [q for q in queries if q.get("difficulty") == filter_difficulty]
    
    logger.info(f"Running evaluation on {len(queries)} queries...")
    
    results = []
    failures = []
    
    for i, query_entry in enumerate(queries):
        try:
            result = run_single_query(tool, query_entry, config)
            results.append(result)
            
            if verbose:
                relevant = set(result["relevant_ids"])
                retrieved = result["retrieved_ids"][:5]
                hits = len(set(retrieved) & relevant)
                print(f"  [{i+1}/{len(queries)}] {query_entry['id']}: "
                      f"R@5={hits}/{len(relevant)} "
                      f"type={result['detected_query_type']} "
                      f"conf={result['confidence']:.2f}")
        
        except Exception as e:
            logger.error(f"Failed on query {query_entry['id']}: {e}")
            failures.append({"query_id": query_entry["id"], "error": str(e)})
    
    conn.close()
    
    # Calculate metrics
    metrics = calculate_all_metrics(results)
    
    return metrics, results, failures


def run_evaluation_by_category(verbose: bool = False) -> Dict[str, RetrievalMetrics]:
    """Run evaluation broken down by category."""
    config = load_config()
    golden = load_golden_dataset()
    
    # Get unique categories
    categories = set(q.get("category") for q in golden.get("queries", []))
    categories.discard(None)
    
    category_metrics = {}
    
    for category in sorted(categories):
        logger.info(f"\nEvaluating category: {category}")
        metrics, _, _ = run_evaluation(filter_category=category, verbose=verbose)
        category_metrics[category] = metrics
    
    return category_metrics


def save_results(metrics: RetrievalMetrics, results: List[Dict], failures: List[Dict]):
    """Save evaluation results to files."""
    output_dir = Path("evaluation/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save metrics
    metrics_file = output_dir / f"metrics_{timestamp}.json"
    with open(metrics_file, "w") as f:
        json.dump(vars(metrics), f, indent=2)
    
    # Save detailed results
    results_file = output_dir / f"results_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Save failures
    if failures:
        failures_file = output_dir / f"failures_{timestamp}.json"
        with open(failures_file, "w") as f:
            json.dump(failures, f, indent=2)
    
    logger.info(f"Results saved to {output_dir}")
    return metrics_file, results_file


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Run RAG evaluation")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--difficulty", help="Filter by difficulty")
    parser.add_argument("--by-category", action="store_true", help="Break down by category")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--save", action="store_true", help="Save results to files")
    
    args = parser.parse_args()
    
    if args.by_category:
        category_metrics = run_evaluation_by_category(verbose=args.verbose)
        
        print("\n" + "=" * 60)
        print(" RESULTS BY CATEGORY")
        print("=" * 60)
        
        for category, metrics in category_metrics.items():
            print(f"\n📁 {category}")
            print(f"   Recall@5: {metrics.recall_at_5:.3f}  "
                  f"MRR: {metrics.mrr:.3f}  "
                  f"NDCG@5: {metrics.ndcg_at_5:.3f}")
    else:
        metrics, results, failures = run_evaluation(
            filter_category=args.category,
            filter_difficulty=args.difficulty,
            verbose=args.verbose
        )
        
        print_metrics_report(metrics)
        
        if failures:
            print(f"\n⚠️ {len(failures)} queries failed")
            for f in failures[:5]:
                print(f"   - {f['query_id']}: {f['error']}")
        
        if args.save:
            save_results(metrics, results, failures)


if __name__ == "__main__":
    main()
```

---

## 4. Failure Analysis

Create file: `src/evaluation/failure_analysis.py`

```python
"""
Failure analysis tools for identifying and categorizing retrieval failures.
"""

from typing import List, Dict, Set
from dataclasses import dataclass
from collections import defaultdict
import json


@dataclass
class FailureCase:
    query_id: str
    query: str
    category: str
    failure_type: str
    expected_docs: List[str]
    retrieved_docs: List[str]
    confidence: float
    notes: str


def classify_failure(result: Dict) -> str:
    """
    Classify the type of failure.
    
    Failure types:
    - "complete_miss": No relevant documents in top 10
    - "partial_miss": Some relevant documents missing from top 10
    - "ranking_error": Relevant documents present but poorly ranked
    - "type_misclassification": Query type incorrectly detected
    - "low_confidence": Good results but low confidence score
    - "false_positive": Irrelevant documents ranked highly
    """
    relevant = set(result.get("relevant_ids", []))
    retrieved = result.get("retrieved_ids", [])[:10]
    retrieved_set = set(retrieved)
    
    if not relevant:
        return "no_ground_truth"
    
    hits = retrieved_set & relevant
    
    if len(hits) == 0:
        return "complete_miss"
    
    if len(hits) < len(relevant):
        # Check if missing docs are just ranked lower
        all_retrieved = set(result.get("retrieved_ids", []))
        if relevant.issubset(all_retrieved):
            return "ranking_error"
        return "partial_miss"
    
    # Check ranking quality
    first_relevant_rank = None
    for i, doc_id in enumerate(retrieved):
        if doc_id in relevant:
            first_relevant_rank = i
            break
    
    if first_relevant_rank and first_relevant_rank > 2:
        return "ranking_error"
    
    # Check query type
    if result.get("expected_query_type") != result.get("detected_query_type"):
        return "type_misclassification"
    
    # Check confidence
    if result.get("confidence", 1.0) < 0.4:
        return "low_confidence"
    
    return "success"


def analyze_failures(results: List[Dict], threshold_recall: float = 0.8) -> Dict:
    """
    Analyze failures across all results.
    
    Returns breakdown of failure types and problematic queries.
    """
    failure_counts = defaultdict(int)
    failure_cases = defaultdict(list)
    
    for result in results:
        failure_type = classify_failure(result)
        failure_counts[failure_type] += 1
        
        if failure_type != "success":
            failure_cases[failure_type].append({
                "query_id": result["query_id"],
                "query": result["query"],
                "category": result.get("category"),
                "relevant_ids": result.get("relevant_ids", []),
                "retrieved_ids": result.get("retrieved_ids", [])[:10],
                "confidence": result.get("confidence"),
                "detected_type": result.get("detected_query_type"),
                "expected_type": result.get("expected_query_type"),
            })
    
    return {
        "total_queries": len(results),
        "failure_counts": dict(failure_counts),
        "failure_rate": 1 - (failure_counts["success"] / len(results)) if results else 0,
        "failure_cases": dict(failure_cases),
    }


def generate_failure_report(analysis: Dict) -> str:
    """Generate a human-readable failure report."""
    lines = []
    lines.append("=" * 60)
    lines.append(" FAILURE ANALYSIS REPORT")
    lines.append("=" * 60)
    
    lines.append(f"\nTotal Queries: {analysis['total_queries']}")
    lines.append(f"Overall Failure Rate: {analysis['failure_rate']:.1%}")
    
    lines.append("\n📊 FAILURE BREAKDOWN:")
    for failure_type, count in sorted(analysis["failure_counts"].items()):
        pct = count / analysis["total_queries"] * 100
        lines.append(f"   {failure_type}: {count} ({pct:.1f}%)")
    
    lines.append("\n🔍 SAMPLE FAILURES BY TYPE:")
    for failure_type, cases in analysis["failure_cases"].items():
        lines.append(f"\n  [{failure_type}]")
        for case in cases[:3]:  # Show top 3 examples
            lines.append(f"    Query: {case['query'][:50]}...")
            lines.append(f"    Category: {case['category']}")
            lines.append(f"    Expected: {case['relevant_ids'][:3]}")
            lines.append(f"    Retrieved: {case['retrieved_ids'][:3]}")
            lines.append("")
    
    return "\n".join(lines)


def suggest_improvements(analysis: Dict) -> List[str]:
    """Suggest improvements based on failure analysis."""
    suggestions = []
    
    counts = analysis["failure_counts"]
    total = analysis["total_queries"]
    
    # Complete misses
    if counts.get("complete_miss", 0) / total > 0.1:
        suggestions.append(
            "HIGH COMPLETE MISS RATE: Consider:\n"
            "  - Reviewing chunking strategy (chunks may be too small/large)\n"
            "  - Checking embedding model quality for your domain\n"
            "  - Adjusting alpha toward more lexical search (lower alpha)"
        )
    
    # Ranking errors
    if counts.get("ranking_error", 0) / total > 0.15:
        suggestions.append(
            "HIGH RANKING ERROR RATE: Consider:\n"
            "  - Adding a reranker (cross-encoder)\n"
            "  - Tuning alpha per query type\n"
            "  - Improving chunk context (add more document metadata)"
        )
    
    # Type misclassification
    if counts.get("type_misclassification", 0) / total > 0.1:
        suggestions.append(
            "HIGH TYPE MISCLASSIFICATION: Consider:\n"
            "  - Expanding semantic trigger terms in config\n"
            "  - Adjusting query type detection heuristics\n"
            "  - Adding more domain-specific patterns"
        )
    
    # Low confidence
    if counts.get("low_confidence", 0) / total > 0.2:
        suggestions.append(
            "HIGH LOW CONFIDENCE RATE: Consider:\n"
            "  - Reviewing embedding model fit for your content\n"
            "  - Checking chunk quality (contextual prefixes)\n"
            "  - Adjusting confidence threshold"
        )
    
    if not suggestions:
        suggestions.append("✓ No major issues detected. Consider fine-tuning for edge cases.")
    
    return suggestions
```

---

## 5. Continuous Improvement Pipeline

Create file: `scripts/improvement_cycle.py`

```python
"""
Automated improvement cycle for RAG system.
Identifies issues, suggests fixes, and tracks progress over time.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import datetime
from pathlib import Path
import logging

from scripts.run_evaluation import run_evaluation, save_results
from src.evaluation.failure_analysis import analyze_failures, generate_failure_report, suggest_improvements
from src.evaluation.metrics import print_metrics_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_baseline():
    """Load the baseline metrics for comparison."""
    baseline_path = Path("evaluation/baseline_metrics.json")
    if baseline_path.exists():
        with open(baseline_path) as f:
            return json.load(f)
    return None


def save_baseline(metrics):
    """Save current metrics as new baseline."""
    baseline_path = Path("evaluation/baseline_metrics.json")
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
                    "improved": diff > 0 if key not in ["no_results_rate", "low_confidence_rate", 
                                                         "mean_latency_ms", "p95_latency_ms"] else diff < 0
                }
    
    return comparisons


def print_comparison(comparisons: dict):
    """Print comparison to baseline."""
    if not comparisons:
        print("\n📊 No baseline to compare against.")
        return
    
    print("\n" + "=" * 60)
    print(" COMPARISON TO BASELINE")
    print("=" * 60)
    
    for key, comp in comparisons.items():
        indicator = "✅" if comp["improved"] else "❌" if comp["diff"] != 0 else "➖"
        sign = "+" if comp["diff"] > 0 else ""
        
        # Only show significant metrics
        if key in ["recall_at_5", "recall_at_10", "mrr", "ndcg_at_5", "precision_at_5",
                   "query_type_accuracy", "mean_latency_ms", "no_results_rate"]:
            print(f"  {indicator} {key}: {comp['current']:.3f} "
                  f"(was {comp['baseline']:.3f}, {sign}{comp['diff']:.3f}, {sign}{comp['pct_change']:.1f}%)")


def run_improvement_cycle(set_baseline: bool = False, verbose: bool = False):
    """
    Run one improvement cycle:
    1. Run evaluation
    2. Analyze failures
    3. Compare to baseline
    4. Generate suggestions
    """
    print("\n🔄 STARTING IMPROVEMENT CYCLE")
    print("=" * 60)
    
    # Run evaluation
    logger.info("Running evaluation...")
    metrics, results, failures = run_evaluation(verbose=verbose)
    
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
    print("\n💡 IMPROVEMENT SUGGESTIONS:")
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
    
    if baseline:
        recall_improved = comparisons["recall_at_5"]["improved"]
        print(f"  vs Baseline: {'📈 Improved' if recall_improved else '📉 Regressed'}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Run RAG improvement cycle")
    parser.add_argument("--set-baseline", action="store_true", 
                        help="Set current results as new baseline")
    parser.add_argument("--verbose", "-v", action="store_true", 
                        help="Verbose output")
    
    args = parser.parse_args()
    
    run_improvement_cycle(
        set_baseline=args.set_baseline,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
```

---

## 6. A/B Testing Framework

Create file: `src/evaluation/ab_testing.py`

```python
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
            name="baseline",
            description="Current production configuration",
            config_overrides={}
        ),
        
        # Alpha tuning experiments
        ExperimentConfig(
            name="alpha_high",
            description="Higher vector weight (alpha=0.9)",
            config_overrides={"search": {"default_alpha": 0.9}}
        ),
        ExperimentConfig(
            name="alpha_low",
            description="Lower vector weight (alpha=0.5)",
            config_overrides={"search": {"default_alpha": 0.5}}
        ),
        
        # Chunk size experiments (would require re-indexing)
        ExperimentConfig(
            name="larger_chunks",
            description="Larger chunks (600 tokens)",
            config_overrides={"chunking": {"target_chunk_tokens": 600, "max_chunk_tokens": 700}}
        ),
        ExperimentConfig(
            name="smaller_chunks",
            description="Smaller chunks (300 tokens)",
            config_overrides={"chunking": {"target_chunk_tokens": 300, "max_chunk_tokens": 400}}
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
                        "mixed": 0.7
                    }
                }
            }
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
    run_evaluation_fn: Callable,
    variants: List[ExperimentConfig] = None
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
        print(f"\n🧪 Running experiment: {variant.name}")
        print(f"   {variant.description}")
        
        # Apply overrides
        test_config = apply_config_overrides(base_config, variant.config_overrides)
        
        # Note: For proper A/B testing, you'd need to:
        # 1. Save test_config to a temp file
        # 2. Have run_evaluation_fn load from that file
        # 3. Or pass config directly to the evaluation function
        
        # For now, this is a simplified version
        metrics, detailed, _ = run_evaluation_fn()
        
        results.append(ExperimentResult(
            config=variant,
            metrics=metrics,
            detailed_results=detailed
        ))
    
    return results


def print_ab_results(results: List[ExperimentResult]):
    """Print A/B experiment results comparison."""
    print("\n" + "=" * 80)
    print(" A/B EXPERIMENT RESULTS")
    print("=" * 80)
    
    # Header
    print(f"\n{'Variant':<25} {'Recall@5':>10} {'MRR':>10} {'NDCG@5':>10} {'P95 Latency':>12}")
    print("-" * 80)
    
    # Find best for each metric
    best_recall = max(r.metrics.recall_at_5 for r in results)
    best_mrr = max(r.metrics.mrr for r in results)
    best_ndcg = max(r.metrics.ndcg_at_5 for r in results)
    best_latency = min(r.metrics.p95_latency_ms for r in results)
    
    for result in results:
        m = result.metrics
        
        # Mark best values
        recall_mark = "★" if m.recall_at_5 == best_recall else " "
        mrr_mark = "★" if m.mrr == best_mrr else " "
        ndcg_mark = "★" if m.ndcg_at_5 == best_ndcg else " "
        latency_mark = "★" if m.p95_latency_ms == best_latency else " "
        
        print(f"{result.config.name:<25} "
              f"{m.recall_at_5:>9.3f}{recall_mark} "
              f"{m.mrr:>9.3f}{mrr_mark} "
              f"{m.ndcg_at_5:>9.3f}{ndcg_mark} "
              f"{m.p95_latency_ms:>10.1f}ms{latency_mark}")
    
    print("\n★ = Best in category")
```

---

## 7. Project Structure Update

Add these files to your project:

```
rag-local-dev/
├── evaluation/
│   ├── golden_dataset.yaml           # Ground truth queries and relevance
│   ├── golden_dataset_populated.yaml # Auto-generated with chunk IDs
│   ├── baseline_metrics.json         # Current baseline for comparison
│   └── results/                       # Evaluation run outputs
│       ├── metrics_YYYYMMDD_HHMMSS.json
│       └── results_YYYYMMDD_HHMMSS.json
├── src/
│   └── evaluation/
│       ├── __init__.py
│       ├── metrics.py                # Metric calculations
│       ├── failure_analysis.py       # Failure classification
│       └── ab_testing.py             # A/B testing framework
└── scripts/
    ├── populate_golden_dataset.py    # Link queries to chunk IDs
    ├── run_evaluation.py             # Main evaluation runner
    └── improvement_cycle.py          # Continuous improvement
```

---

## 8. Evaluation Workflow

### Initial Setup

```bash
# 1. Create golden dataset (manually edit evaluation/golden_dataset.yaml)

# 2. Index documents
python scripts/index_documents.py

# 3. Populate golden dataset with chunk IDs
python scripts/populate_golden_dataset.py

# 4. Run initial evaluation and set baseline
python scripts/improvement_cycle.py --set-baseline
```

### Regular Improvement Cycle

```bash
# Run evaluation and compare to baseline
python scripts/improvement_cycle.py -v

# Run evaluation by category
python scripts/run_evaluation.py --by-category

# Run evaluation for specific category
python scripts/run_evaluation.py --category adr_semantic -v
```

### After Making Changes

```bash
# 1. Make configuration changes (alpha tuning, etc.)
# 2. Run improvement cycle to see impact
python scripts/improvement_cycle.py -v

# 3. If improved, set new baseline
python scripts/improvement_cycle.py --set-baseline
```

---

## 9. Success Criteria

### Phase 1: Baseline Establishment
- [ ] Golden dataset created with 50+ queries
- [ ] All queries have relevance judgments
- [ ] Baseline metrics recorded

### Phase 2: Target Metrics
| Metric | Target | Stretch Goal |
|--------|--------|--------------|
| Recall@5 | > 0.70 | > 0.85 |
| Recall@10 | > 0.85 | > 0.95 |
| MRR | > 0.60 | > 0.75 |
| NDCG@5 | > 0.65 | > 0.80 |
| Query Type Accuracy | > 0.90 | > 0.95 |
| P95 Latency | < 500ms | < 200ms |
| No Results Rate | < 5% | < 2% |

### Phase 3: Continuous Improvement
- [ ] Weekly evaluation runs
- [ ] Failure analysis after each run
- [ ] A/B testing for major changes
- [ ] Baseline updated when metrics improve

---

## 10. Key Principles

1. **Measure before optimizing**: Always establish baseline metrics first.

2. **Golden dataset is sacred**: Invest time in creating high-quality relevance judgments. Poor ground truth = meaningless metrics.

3. **Failure analysis over aggregate metrics**: A 0.75 Recall@5 hides important information. Understanding *why* queries fail is more valuable.

4. **Test one change at a time**: When tuning, change one parameter, measure, then decide.

5. **Category-specific analysis**: Overall metrics can mask category-specific problems. Always break down by query type.

6. **Automate the cycle**: Make evaluation easy to run so it becomes habit, not chore.
