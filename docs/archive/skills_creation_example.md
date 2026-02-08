# Creating a Skill: Step-by-Step Guide

This guide walks you through creating a **Response Formatter** skill using the AInstein Skills Management UI. This skill ensures that list-based responses are well-formatted with statistics and follow-up options.

---

## Overview: What We're Building

The **Response Formatter** skill will:

1. **Rich Formatting** - Ensure all list responses use proper itemization, indentation, and structure
2. **Statistics** - Add summary statistics (e.g., "Showing 12 principles total")
3. **Follow-up Questions** - Ask if the user is satisfied and offer additional options
4. **Visualization Offers** - Suggest relevant charts and graphs (pie charts, timelines, distributions)

**Triggers:** Questions like:
- "What principles exist in the system?"
- "What ADRs exist in the system?"
- "Which principles are related to data quality?"
- "List all policies about security"

---

## Prerequisites

1. AInstein server running at `http://localhost:8081`
   ```bash
   # Activate virtual environment first
   .venv312\Scripts\activate  # Windows
   source .venv312/bin/activate  # Linux/Mac

   # Start the server
   python -m src.chat_ui
   ```
2. Access to the Skills Management UI at `http://localhost:8081/skills`

---

## Step 1: Open the Skills UI

1. Open your browser and navigate to: `http://localhost:8081/skills`
2. You'll see the Skills Dashboard with existing skills listed
3. Click the **"+ New Skill"** button in the top-right corner

The **Create New Skill** wizard will open.

---

## Step 2: Basic Information (Wizard Step 1)

Fill in the basic skill metadata:

### Skill Name
```
response-formatter
```

> **Note:** Skill names must be lowercase, can contain letters, numbers, and hyphens, must start with a letter, and end with a letter or number. The UI validates this in real-time and shows ✓ when the name is valid and available.

### Description
```
Ensures list-based responses use rich formatting with statistics, follow-up questions, and visualization suggestions.
```

### Auto-Activate
- **Toggle: ON**

This skill should automatically activate when relevant queries are detected, without requiring explicit user invocation.

### Triggers (comma-separated)
```
list, what, which, how many, show all, enumerate, summarize
```

These keywords help the system identify when this skill should be applied.

### Click "Next" to proceed to Step 2.

---

## Step 3: Initial Rules (Wizard Step 2)

This is where you define the skill's behavior in markdown format. The content will be injected into the LLM's system prompt when the skill activates.

### Template Selection
- Select: **"Start from blank"**

### Skill Content (SKILL.md Body)

Copy and paste the following content into the editor:

```markdown
## Response Formatter Skill

You are enhanced with the Response Formatter skill. When answering questions that require listing items (principles, ADRs, policies, vocabulary terms, etc.), you MUST follow these formatting rules:

### 1. Rich Formatting Requirements

For ANY response that lists multiple items:

#### Use Structured Itemization
- Use numbered lists (1., 2., 3.) for sequential or ranked items
- Use bullet points (•) for unordered collections
- Use nested indentation for sub-categories or related details

#### Example Format:
```
## [Category Name] (X items total)

1. **[Item Title]** (ID: [reference])
   - Description: [brief description]
   - Owner/Source: [if applicable]
   - Status: [if applicable]

2. **[Item Title]** (ID: [reference])
   - Description: [brief description]
   ...
```

### 2. Statistics Section

Always include a statistics summary at the END of your list response:

```
---
📊 **Summary Statistics**
- Total items listed: [N]
- Categories represented: [list categories if applicable]
- Date range: [if temporal data exists]
- Most common [attribute]: [value] ([percentage]%)
```

### 3. Follow-up Questions

After providing the list and statistics, ALWAYS include:

```
---
💬 **Follow-up Options**

Was this response helpful? Here are some things I can do next:

1. **Refine the list** - Filter by specific criteria (owner, date, status)
2. **Expand details** - Show full content for any specific item
3. **Compare items** - Analyze relationships between selected items
4. **Export format** - Provide in table format, JSON, or CSV

Would you like me to proceed with any of these options?
```

### 4. Visualization Suggestions

When the data supports it, offer visualization options:

```
---
📈 **Visualization Options**

Based on this data, I can generate:

- **Pie Chart**: Distribution of [items] by [category/owner/type]
- **Timeline**: Growth of [items] over time (creation dates)
- **Bar Chart**: Comparison of [metric] across [categories]
- **Network Graph**: Relationships between [items]

Would you like me to create any of these visualizations?
```

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
```

### Click "Next" to proceed to Step 3.

---

## Step 4: Thresholds Configuration (Wizard Step 3)

Configure how the skill behaves with retrieval and abstention settings.

### Option Selection
- Select: **"Use default thresholds"**

The default thresholds work well for this formatting skill since it primarily modifies output presentation rather than retrieval behavior.

Alternatively, you can select **"Copy from existing skill"** and choose `rag-quality-assurance` to inherit proven settings.

### Quick Settings (if customizing)

If you want to customize:

| Setting | Recommended Value | Reason |
|---------|------------------|--------|
| Distance Threshold | 0.5 (Medium) | Allow reasonable flexibility |
| Query Coverage | 0.2 (Low) | List queries often have broad terms |

#### Understanding Thresholds

| Threshold | Low Value | High Value |
|-----------|-----------|------------|
| **Distance** | More strict matching (skill activates less) | More lenient (skill activates more often) |
| **Query Coverage** | Activates even with few keyword matches | Requires more keywords to match |

> **Tip:** For a formatting skill like this one that should apply broadly, consider using slightly higher thresholds to ensure it activates on most list queries.

### Click "Next" to proceed to Step 4.

---

## Step 5: Review & Create (Wizard Step 4)

Review all your settings before creating the skill:

### Review Checklist

| Section | Value |
|---------|-------|
| **Name** | `response-formatter` |
| **Description** | Ensures list-based responses use rich formatting... |
| **Auto-Activate** | Yes |
| **Triggers** | list, what, which, how many, show all, enumerate, summarize |
| **Thresholds** | Default values |

### Validation

The wizard will automatically validate:
- ✅ Skill name is unique and valid
- ✅ Description is provided
- ✅ SKILL.md content is valid markdown
- ✅ Thresholds are within acceptable ranges

### Create the Skill

Click the **"Create Skill"** button.

You should see a success message:
```
✅ Skill "response-formatter" created successfully!
```

### Files Created

The wizard automatically creates the following directory structure:

```
skills/
└── response-formatter/
    ├── SKILL.md                    # Your rules content (markdown)
    └── references/
        └── thresholds.yaml         # Threshold configuration
```

Additionally, an entry is added to `skills/registry.yaml`:
```yaml
- name: response-formatter
  path: response-formatter/SKILL.md
  description: "Ensures list-based responses use rich formatting..."
  enabled: true
  auto_activate: true
  triggers:
    - "list"
    - "what"
    - "which"
    # ... etc
```

---

## Step 6: Verify the Skill

After creation, verify your skill is properly configured:

### 6.1 Check the Skills List

1. Return to the Skills Dashboard
2. Find **"response-formatter"** in the list
3. Verify it shows as **ACTIVE** (green badge)

### 6.2 Expand the Skill Card

Click on the skill card to expand it and verify:
- Description matches what you entered
- Triggers are correctly listed
- Auto-activate is enabled

### 6.3 Test the Skill

1. Click the **"Test"** button on the skill card
2. Enter a test query:
   ```
   What principles exist in the system?
   ```
3. Click **"Run Test"**
4. Verify the response shows:
   - ✅ List query detected: Yes
   - ✅ Skill would activate: Yes
   - ✅ Matched trigger: "what"

---

## Step 7: Test in Chat Interface

Now test the skill in the actual chat interface:

1. Navigate to `http://localhost:8081` (main chat)
2. Enter a list query:
   ```
   What ADRs exist in the system related to data governance?
   ```
3. Verify the response includes:
   - ✅ Numbered/bulleted list with proper indentation
   - ✅ Statistics summary at the end
   - ✅ Follow-up options section
   - ✅ Visualization suggestions (if applicable)

### Example Expected Output

```
## Data Governance ADRs (5 items total)

1. **ADR.15 - Data Classification Standard** (Status: Accepted)
   - Description: Defines data classification levels for the organization
   - Owner: Data Governance Team
   - Created: 2024-03-15

2. **ADR.22 - Data Retention Policy** (Status: Accepted)
   - Description: Specifies retention periods for different data types
   - Owner: Legal & Compliance
   - Created: 2024-05-20

3. **ADR.31 - Data Quality Framework** (Status: Draft)
   - Description: Framework for measuring and improving data quality
   - Owner: Data Engineering
   - Created: 2024-08-10

[... more items ...]

---
📊 **Summary Statistics**
- Total items listed: 5
- Status breakdown: 4 Accepted, 1 Draft
- Date range: March 2024 - August 2024
- Primary owner: Data Governance Team (40%)

---
💬 **Follow-up Options**

Was this response helpful? Here are some things I can do next:

1. **Refine the list** - Filter by status, owner, or date range
2. **Expand details** - Show full content for any specific ADR
3. **Compare items** - Analyze relationships between these ADRs
4. **Export format** - Provide in table format, JSON, or CSV

Would you like me to proceed with any of these options?

---
📈 **Visualization Options**

Based on this data, I can generate:

- **Pie Chart**: Distribution of ADRs by owner team
- **Timeline**: ADR creation dates over time
- **Status Chart**: Breakdown by acceptance status

Would you like me to create any of these visualizations?
```

---

## Step 8: Fine-Tuning (Optional)

If the skill isn't behaving as expected, you can adjust it:

### Edit the Rules

1. Click the **"Edit Rules"** button on the skill card
2. Modify the SKILL.md content
3. Click **"Save"**

### Adjust Thresholds

1. Click the **"Configure"** button
2. Adjust the sliders or detailed settings
3. Click **"Save Changes"**

### Disable Temporarily

1. Toggle the **Enabled** switch to off
2. A warning banner will appear: "Restart the server for changes to take full effect"
3. Restart the server to apply the change

### Backup and Restore

The system automatically creates backups when you edit skills:

**Manual Backup:**
1. Click **"Configure"** on the skill card
2. Click **"Create Backup"**
3. Backups are stored as timestamped `.bak` files

**Restore from Backup:**
1. Click **"Configure"** on the skill card
2. Click **"Restore from Backup"**
3. The most recent backup will be restored

### Delete a Skill

1. Click the red **"Delete"** button on the skill card
2. Confirm the deletion in the dialog
3. The skill files are moved to `skills/.deleted/` (recoverable)

> **Note:** The default skill (`rag-quality-assurance`) cannot be deleted.

---

## Troubleshooting

### Skill Not Activating

**Problem:** The skill doesn't seem to apply to list queries.

**Solutions:**
1. Verify auto-activate is enabled
2. Check triggers match your query terms
3. Test using the skill's test panel
4. Restart the server if you just created the skill

### Formatting Not Applied

**Problem:** Responses don't include the rich formatting.

**Solutions:**
1. Ensure the SKILL.md content is valid markdown
2. Check that the query matches triggering conditions
3. Verify the skill is enabled (ACTIVE badge)
4. Review the skill content for clear, imperative instructions

### Statistics Missing

**Problem:** Responses lack the statistics section.

**Solutions:**
1. Ensure the SKILL.md explicitly instructs to include statistics
2. Verify the query returns multiple items (3+ required)
3. Check if the LLM has access to metadata for statistics

### Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| Name validation fails | Use only `a-z`, `0-9`, `-`; start with letter, end with letter/number |
| Skill not in list | Refresh the page or restart server |
| 503 Service Unavailable | Ensure correct venv is activated and Elysia is installed |
| Changes not taking effect | Some changes require server restart |
| Can't delete skill | Default skill (`rag-quality-assurance`) cannot be deleted |

---

## Summary

You've successfully created a **Response Formatter** skill that:

1. ✅ Activates automatically on list-based queries
2. ✅ Enforces rich formatting with proper structure
3. ✅ Includes summary statistics
4. ✅ Provides follow-up options
5. ✅ Suggests relevant visualizations

This skill enhances the user experience by making list responses more readable, actionable, and insightful.

---

## Next Steps

### Skill Ideas to Try

| Skill Name | Purpose |
|------------|---------|
| `adr-deep-dive` | Provides detailed analysis when user asks about specific ADRs |
| `principle-checker` | Validates if a proposed solution aligns with existing principles |
| `vocabulary-explainer` | Adds context and examples when vocabulary terms are mentioned |
| `comparison-mode` | Formats side-by-side comparisons when user asks to compare items |
| `code-reviewer` | Applies coding standards when reviewing code snippets |

### Enhancement Ideas

- **Add visualization backend:** Implement actual chart generation (using matplotlib, plotly, or similar) for the visualization suggestions
- **Customize triggers:** Add domain-specific trigger words for your organization
- **A/B testing:** Compare user satisfaction with and without the formatter skill
- **Combine skills:** Create skills that work together (e.g., formatter + validator)

### Learn More

- Review the default `rag-quality-assurance` skill for advanced patterns
- Check `skills/registry.yaml` for all registered skills
- Explore the `thresholds.yaml` format for fine-grained control

---

## Appendix: Skill File Formats

### SKILL.md Structure

```markdown
---
name: skill-name
description: Brief description
auto_activate: true
triggers:
  - keyword1
  - keyword2
---

# Skill Title

Your skill instructions in markdown...
```

### thresholds.yaml Structure

```yaml
# Skill Thresholds Configuration
abstention:
  distance_threshold: 0.5
  min_query_coverage: 0.2
  list_indicators: [...]
  additional_stop_words: [...]

retrieval_limits:
  adr: 5
  principle: 5
  policy: 3
  vocabulary: 10

truncation:
  content_max_chars: 4000
  max_context_results: 10
```

---

*Created with AInstein Skills Management UI v1.0*
