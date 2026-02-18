---
name: response-formatter
description: Ensures list-based responses use structured formatting with item counts
  when returning multiple items.
---

## Response Formatter

When answering questions that return multiple items (ADRs, principles, policies, vocabulary terms), use structured list formatting.

### Format

1. **ID: [reference]** - **[Item Title]** | Status: [if available] | Owner: [if available]
2. **ID: [reference]** - **[Item Title]** | Status: [if available] | Owner: [if available]

Use numbered lists for sequential or ranked items. Use bullet points for unordered collections. List all items consecutively with NO blank lines or spacing between them — do not group or separate items by category.

### Summary Line

End every list response with a count: **Total: [N] items**

**Critical:** Count the actual number of items you listed. Do NOT calculate the count from ID ranges (e.g., ADR.00 to ADR.31 does NOT mean 32 — count only the ADRs that actually exist in the retrieved context).

### When NOT to Format as a List

- Single-item lookups (e.g., "What is ADR.21?")
- Fewer than 3 items returned
- User explicitly asks for plain text