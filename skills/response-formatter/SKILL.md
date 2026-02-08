---
name: response-formatter
description: Ensures list-based responses use rich formatting with statistics, follow-up
  questions, and visualization suggestions.
auto_activate: false
triggers:
- list
- what
- which
- how many
- show all
- enumerate
- summarize
---

## Response Formatter Skill

You are enhanced with the Response Formatter skill. When answering questions that require listing items (principles, ADRs, policies, vocabulary terms, etc.), you MUST follow these formatting rules:

### 1. Rich Formatting Requirements

For ANY response that lists multiple items:

#### Use Structured Itemization
- Use numbered lists (1., 2., 3.) for sequential or ranked items
- Use bullet points for unordered collections
- Use nested indentation for sub-categories or related details

#### Example Format:

## [Category Name] (X items total)

1. **[Item Title]** (ID: [reference])
   - Description: [brief description]
   - Owner/Source: [if applicable]
   - Status: [if applicable]

2. **[Item Title]** (ID: [reference])
   - Description: [brief description]

### 2. Statistics Section

Always include a statistics summary at the END of your list response:

---
**Summary Statistics**
- Total items listed: [N]
- Categories represented: [list categories if applicable]
- Date range: [if temporal data exists]
- Most common [attribute]: [value] ([percentage]%)

### 3. Follow-up Questions

After providing the list and statistics, ALWAYS include:

---
**Follow-up Options**

Was this response helpful? Here are some things I can do next:

1. **Refine the list** - Filter by specific criteria (owner, date, status)
2. **Expand details** - Show full content for any specific item
3. **Compare items** - Analyze relationships between selected items
4. **Export format** - Provide in table format, JSON, or CSV

Would you like me to proceed with any of these options?

### 4. Visualization Suggestions

When the data supports it, offer visualization options:

---
**Visualization Options**

Based on this data, I can generate:

- **Pie Chart**: Distribution of [items] by [category/owner/type]
- **Timeline**: Growth of [items] over time (creation dates)
- **Bar Chart**: Comparison of [metric] across [categories]
- **Network Graph**: Relationships between [items]

Would you like me to create any of these visualizations?

### 5. Triggering Conditions

Apply this formatting when the user query:
- Asks "what", "which", "how many", "list", "show all", "enumerate"
- Requests information about multiple ADRs, principles, policies, or vocabulary terms
- Asks for summaries or overviews of document collections

### 6. Exceptions

Do NOT apply rich formatting when:
- User asks about a single specific item (e.g., "What is ADR.21?")
- User explicitly requests plain text or minimal formatting
- The response contains fewer than 3 items