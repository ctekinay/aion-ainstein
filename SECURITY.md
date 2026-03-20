# Security — Known Dependency Vulnerabilities

This document tracks known vulnerabilities in transitive dependencies,
their risk assessment, and resolution status.

---

## Open

No open vulnerabilities.

---

## Resolved

### CVE-2025-69872 — diskcache (removed)
- **Resolved:** Removed with Elysia dependency chain (`elysia-ai → dspy-ai → dspy → diskcache`)
- Elysia was replaced with Pydantic AI agents; `diskcache` is no longer a dependency

### authlib — alg:none signature bypass
- **Resolved:** Bumped 1.6.6 → 1.6.9 in `uv.lock`

### pip — path traversal (CVE in pip < 26.0)
- **Resolved:** Bumped 25.3 → 26.0.1 in `uv.lock`

### python-multipart — GHSA-cfh3-3jmp-rvhc
- **Resolved:** `elysia-ai==0.2.8` previously pinned `python-multipart==0.0.18`; override was required
- Elysia removed; `python-multipart` is now pulled by `fastapi` at a safe version (>=0.0.20)
