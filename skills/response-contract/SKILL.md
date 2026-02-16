---
name: response-contract
description: Enforce structured JSON output for RAG responses where count transparency and completeness must be explicit.
auto_activate: false
triggers:
  - list
  - how many
  - what adrs
  - what principles
  - what policies
  - show all
  - enumerate
  - count
  - total
---

# SKILL: response-contract

## Purpose

Enforce structured JSON output for RAG responses where count transparency and completeness must be explicit. This skill ensures users always know:
- How many items are being shown
- How many items exist in total
- Whether the count is exact, approximate, or a lower bound

## When to Use

**Activate this skill for:**
- List queries (users ask for items, ADRs, principles, records)
- Count queries (users ask how many exist, how many are shown)
- Any response where partial display is possible (pagination, truncation, top-k)

**Do NOT activate for:**
- Purely conversational answers with no itemization
- Single-item lookups (e.g., "What is ADR.21?")
- Creative writing or open-ended brainstorming

## Output Contract

The assistant MUST return valid JSON matching schema_version 1.0:

```json
{
    "schema_version": "1.0",
    "answer": "Your detailed response text here",
    "items_shown": 5,
    "items_total": 18,
    "count_qualifier": "exact",
    "sources": [
        {"title": "ADR.21", "type": "ADR"},
        {"title": "PCP.10", "type": "Principle"}
    ]
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Always "1.0" |
| `answer` | string | The complete response text |
| `items_shown` | integer | Number of items mentioned in the answer |
| `items_total` | integer or null | Total items in database (from COLLECTION COUNTS) |
| `count_qualifier` | string or null | "exact", "at_least", or "approx" |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `transparency_statement` | string | Explicit statement about completeness |
| `sources` | array | List of source documents referenced |

## Invariants

The runtime validation engine enforces these invariants:

1. **`items_shown >= 0`** - Cannot show negative items
2. **`items_total >= items_shown`** (when items_total is not null) - Total must include shown
3. **`count_qualifier` must be valid** - One of: "exact", "at_least", "approx", or null
4. **No prose outside JSON** - Response must be pure JSON, no markdown wrapping

## Count Qualifier Semantics

| Qualifier | Meaning | When to Use |
|-----------|---------|-------------|
| `"exact"` | The total is precisely known | Database count is exact |
| `"at_least"` | The total is a lower bound | More items may exist |
| `"approx"` | The total is an estimate | Sampling or estimation used |
| `null` | Total is unknown | Cannot determine count |

## Examples

### List Query Example

**Query:** "What ADRs exist?"

**Response:**
```json
{
    "schema_version": "1.0",
    "answer": "Here are the Architectural Decision Records (ADRs):\n\n1. **ADR.21** - Event-driven architecture\n2. **ADR.22** - API versioning strategy\n3. **ADR.23** - Database selection\n...",
    "items_shown": 10,
    "items_total": 18,
    "count_qualifier": "exact",
    "sources": [
        {"title": "ADR.21", "type": "ADR"},
        {"title": "ADR.22", "type": "ADR"}
    ]
}
```

### Count Query Example

**Query:** "How many principles are there?"

**Response:**
```json
{
    "schema_version": "1.0",
    "answer": "There are 15 principles in the knowledge base covering areas such as security, scalability, and maintainability.",
    "items_shown": 0,
    "items_total": 15,
    "count_qualifier": "exact",
    "sources": []
}
```

### Unknown Total Example

**Query:** "What vocabulary terms relate to CIM?"

**Response:**
```json
{
    "schema_version": "1.0",
    "answer": "Here are vocabulary terms related to CIM:\n\n1. **CommonInformationModel** - ...\n2. **CIMProfile** - ...",
    "items_shown": 5,
    "items_total": null,
    "count_qualifier": null,
    "transparency_statement": "These are the top matching terms. The total count is not available for filtered queries.",
    "sources": []
}
```

## Validation and Fallbacks

All parsing, validation, normalization, fallbacks, caching, and metrics are implemented in:

```
src/response_schema.py
```

The runtime engine performs:
1. **Direct JSON parse** - Try parsing as pure JSON
2. **JSON extraction** - Extract JSON from markdown if wrapped
3. **Deterministic repair** - Fix trailing commas, balance braces
4. **Final failure** - Return with reason codes

## Observability

The runtime engine emits:
- **Counters:** `direct_parse_ok`, `repair_ok`, `extract_ok`, `final_failed`
- **Reason codes:** `invalid_json`, `schema_missing_field`, `invariant_violation`
- **Latency:** Per-stage timing in milliseconds

Access via:
```python
from src.response_schema import get_parse_stats
stats = get_parse_stats()
print(f"Success rate: {stats['slo']['success_rate']:.2%}")
```

## Integration Notes

This skill works in conjunction with:
- **response-formatter** - Provides rich formatting within the `answer` field
- **rag-quality-assurance** - Ensures accurate citations in `sources`

The skills are complementary: response-contract enforces the JSON structure, while other skills guide the content quality within that structure.
