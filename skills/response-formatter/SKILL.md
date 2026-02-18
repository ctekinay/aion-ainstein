---
name: response-formatter
description: Ensures list-based responses use structured formatting with item counts when returning multiple items.
---

## Response Formatter

When answering questions that return multiple items (ADRs, principles, policies, vocabulary terms), use structured list formatting.

### Format

1. **[Item Title]** (ID: [reference])
   - Status: [if available]
   - Description: [brief description]

2. **[Item Title]** (ID: [reference])
   - Status: [if available]
   - Description: [brief description]

Use numbered lists for sequential or ranked items. Use bullet points for unordered collections.

### Summary Line

End every list response with a count: **Total: [N] items**

### When NOT to Format as a List

- Single-item lookups (e.g., "What is ADR.21?")
- Fewer than 3 items returned
- User explicitly asks for plain text

