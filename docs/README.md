# AInstein Documentation

This folder contains technical documentation for the AInstein RAG system.

## Core Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture overview (3-layer separation) |
| [STRUCTURED_RESPONSE.md](STRUCTURED_RESPONSE.md) | Structured JSON response validation system |
| [SKILLS_USER_GUIDE.md](SKILLS_USER_GUIDE.md) | Complete guide to the Skills Framework |
| [SKILLS_UI_STATUS.md](SKILLS_UI_STATUS.md) | Skills UI implementation status and roadmap |

## Quick Links

### For Users
- **Getting Started**: See [SKILLS_USER_GUIDE.md](SKILLS_USER_GUIDE.md) for configuring AInstein's behavior

### For Developers
- **Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md) for the 3-layer system design
- **Response Handling**: See [STRUCTURED_RESPONSE.md](STRUCTURED_RESPONSE.md) for JSON validation

### For Operations
- **Implementation Status**: See [SKILLS_UI_STATUS.md](SKILLS_UI_STATUS.md) for feature tracking
- **Implementation Decisions**: See [implementation-records/](implementation-records/) for technical ADRs

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Domain Knowledge (/data/)                          │
│ - ESA ADRs, DARs, Principles, Policies, SKOSMOS            │
│ - Embedded in Weaviate                                      │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Behavior Rules (/skills/)                          │
│ - LLM instructions, formatting, anti-hallucination          │
│ - Injected into prompts (not embedded)                      │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Project Decisions (/docs/implementation-records/)  │
│ - AInstein implementation rationale                         │
│ - Developer documentation (not embedded)                    │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Records

Technical decisions about the AInstein system itself:

| Record | Description |
|--------|-------------|
| [ADR-xxxx-confidence-based-abstention...](implementation-records/ADR-xxxx-confidence-based-abstention-for-hallucination-prevention.md) | Hallucination prevention via abstention |
| [ADR-xxxx-explicit-bm25-fallback...](implementation-records/ADR-xxxx-explicit-bm25-fallback-on-embedding-failure.md) | BM25 fallback when Ollama unavailable |

## Archived Documentation

Historical design documents and superseded content are in [archive/](archive/):

- `STRUCTURED_RESPONSE_DEEP_DIVE.md` - Merged into STRUCTURED_RESPONSE.md
- `SKILLS_UI_TODO.md` - Replaced by SKILLS_UI_STATUS.md
- `SKILLS_UI_DESIGN_SPEC.md` - Historical design reference
- `skills_creation_example.md` - Full tutorial (summarized in USER_GUIDE)

---

*Last updated: 2026-02-08*
