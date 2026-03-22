---
name: response-formatter
description: Per-collection formatting templates for list responses, field visibility rules, and response style guidelines.
---

# Response Formatter

When answering questions that return multiple items, use the formatting template for the specific collection. Each collection has its own fields and format — do not mix templates across collections.

---

## Listing Formats by Collection

### Architecture Decision Records (ADRs)

```
1. **ADR.[number]** — [title] | Status: [status]
```

Fields: `adr_number`, `title`, `status`
Example:
```
1. **ADR.00** — Use Markdown Architectural Decision Records | Status: accepted
2. **ADR.12** — Use CIM (IEC 61970/61968/62325) as default domain language | Status: accepted
```

### Architecture Principles (PCPs)

```
1. **PCP.[number]** — [title] | Status: [status]
```

Fields: `principle_number`, `title`, `status`
Example:
```
1. **PCP.10** — Use the Dutch Grid Code as regulatory input | Status: accepted
2. **PCP.11** — Support Energy Transition Legislation | Status: accepted
```

### Policy Documents

```
1. [title] — Owner: [owner_team]
```

Fields: `title`, `owner_team`
No ID prefix — policies do not have numbered identifiers. No bold on titles. No file paths, no file types.
Example:
```
1. Alliander Data en Informatie Governance Beleid — Owner: Data Office
2. Alliander Privacy Beleid — Owner: Corporate Governance
```

### Vocabulary Terms

```
1. **[preferred_label]** — [definition] | Ontology: [source_ontology]
```

Fields: `preferred_label`, `definition`, `source_ontology`
Example:
```
1. **ActivePower** — Rate of flow of energy | Ontology: IEC 61970 (CIM)
2. **ConnectivityNode** — A point where conducting equipment are connected | Ontology: IEC 61970 (CIM)
```

### Team-based Search Results

```
1. **[ID]** — [title] | Collection: [collection_name]
```

When `search_by_team` returns results across collections, include the collection name so the user knows the source. Use the appropriate ID field for each item (adr_number, principle_number, or title for policies).

---

## General Rules

### Summary Line
End every list response with a count: **Total: [N] items**


**Critical:** Count the actual number of items you listed. Do NOT calculate the count from ID ranges (e.g., ADR.00 to ADR.31 does NOT mean 32 — count only the items that actually exist in the retrieved context).

### List Style

Use numbered lists for sequential or ranked items. Use bullet points for unordered collections. No gaps between items in the list.

### When NOT to Format as a List
- Single-item lookups (e.g., "What is ADR.21?") — use prose
- Fewer than 3 items returned — use prose
- User explicitly asks for plain text

### Field Visibility
Only show fields that exist in the data. If a field is empty or missing, omit it and its label entirely — **except** fields marked as required below.

**Required fields:** Always include `| Status: [status]` for ADRs and PCPs, even if the value is empty or missing. Architects need to see the status field to identify data gaps that need attention.

## Response Style

- Never include preparatory or transitional phrases like "I am preparing...", "Let me summarize...", or "I will now present...". Start directly with the substantive answer.
- Do not repeat the user's question back to them.
