---
name: archimate-tools
description: "ArchiMate model validation, inspection, and merge operations. Use this skill when the user wants to validate, inspect, analyze, or merge ArchiMate 3.2 Open Exchange XML models."
---

# ArchiMate Tools

## Overview

This skill guides the ArchiMate agent when performing validation, inspection, and merge
operations on ArchiMate 3.2 Open Exchange XML models. It does NOT cover model generation
(see `archimate-generator` for that).

## Operations

### Validation

Validates ArchiMate XML against the 3.2 Open Exchange specification. Reports:

- Missing required namespaces or schema declarations
- Invalid element types (not in ArchiMate 3.2 metamodel)
- Invalid relationship types or illegal source/target combinations
- Dangling references (relationships pointing to non-existent elements)
- Structural issues (empty models, missing identifiers)

When reporting validation errors, cite specific element IDs, types, and line context.

### Inspection

Parses an ArchiMate XML model and returns a structured summary:

- Element counts by layer (Motivation, Strategy, Business, Application, Technology, etc.)
- Relationship counts by type
- View listing with element membership
- Property definitions in use
- Overall model statistics

### Merge

Merges a view fragment into an existing ArchiMate model:

- Adds new elements and relationships from the fragment
- Deduplicates by identifier — existing elements are preserved
- Adds new views without overwriting existing ones
- Reports counts of elements, relationships, and views added

## Guidelines

- Use `get_artifact` FIRST when the user references a previous model
- Always validate ArchiMate XML before saving as an artifact
- Use `save_artifact` after any model modifications
- Be specific about validation errors — cite element IDs and types
- When inspecting, organize output by ArchiMate layer for clarity
