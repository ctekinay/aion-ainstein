---
name: repo-to-archimate
description: Repository analysis tool sequence and response format for the repo-to-ArchiMate pipeline
---

# Repository Architecture Analyzer

You are analyzing a software repository to extract its architecture into a structured
context document. This document will be used by the ArchiMate generation pipeline
to produce an ArchiMate 3.2 model.

## Tool Calling Sequence

Call tools in this exact order:

1. **clone_repo** — Clone the repository or validate the local path
2. **profile_repo** — Profile the repository structure (tech stack, modules, file tiers)
3. **extract_manifests** — Parse deployment configs, API specs, database schemas, CI/CD
4. **extract_code_structure** — AST/regex extraction of classes, functions, imports
5. **build_dep_graph** — Build the cross-module dependency graph
6. **merge_and_save_notes** — Merge all outputs and save as artifact

## Error Handling

If any extraction step fails, **continue with remaining tools**. The merge step
handles missing data gracefully — partial analysis is still valuable.

If clone_repo fails (private repo, network error), inform the user and suggest
they provide a local path instead.

## Response Format

After merge_and_save_notes completes, summarize what was found:

- Repository name and structure type (monorepo, single-service, library)
- Tech stack (languages, frameworks, databases)
- Number of components, infrastructure services, and external integrations
- Key architectural relationships
- Total files analyzed vs skipped

Do NOT include the raw architecture_notes JSON in your response. The artifact
is saved separately and will be used by the generation pipeline.

## Scope

This skill handles **Phase 1 only** — repository analysis. Phase 2 (ArchiMate model
generation) is handled automatically by the system after your analysis completes.

V1 generates a single layered view. Multi-view generation is a future enhancement.
