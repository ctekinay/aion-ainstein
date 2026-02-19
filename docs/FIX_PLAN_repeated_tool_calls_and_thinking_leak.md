# Fix Plan: Repeated Tool Calls & Thinking Step Leak

**Date:** 2026-02-19
**Trigger:** "Please show them all" PCP query — 63s, 7× `search_principles`, final answer leaking into thinking steps

---

## Issue A — Repeated identical `search_principles` calls (PRIORITY)

### Root cause 1: `recursion_limit` regression

Commit `299d923` ("Fix Elysia decision tree loop causing repeated responses") set
`self.tree.tree_data.recursion_limit = 2` to prevent exactly this behavior.

That line was **lost** when commit `e21c576` ("Replace OutputCapture with direct
Tree.async_run() iteration") rewrote `__init__` and `query()`. The current code
at `elysia_agents.py:205` is just:

```python
self.tree = Tree()
```

Elysia's `Tree.__init__` hardcodes `recursion_limit=5` (see
`venv312/.../elysia/tree/tree.py:152`), so the Tree now gets 5 full iterations
to loop before being forced to summarize — enough for 7 tool calls.

### Root cause 2: Tree not routing to `list_all_principles`

`list_all_principles` **does** exist (`elysia_agents.py:545-572`). Its docstring
includes trigger phrases like *"What principles exist?"*, *"List all principles"*,
*"Show me the governance principles"*. The `search_principles` docstring even
says at line 409: `"List all principles" → use list_all_principles tool instead`.

Despite this, the Tree still routes to `search_principles` for *"Please show them
all"*. Two contributing factors:

1. **Missing trigger phrase.** The docstring doesn't include "show them all" /
   "show all" / "display all" — these are the phrases the user actually used.
   `list_all_adrs` has the same gap but gets routed correctly because "What ADRs
   exist?" is a more natural phrasing.

2. **Weak return schema.** `list_all_principles` returns only `title` and `doc_type`.
   Compare `list_all_adrs` which returns `title`, `status`, and `file` (filename).
   `list_all_principles` should return `principle_number` too, since that's how
   users identify principles (PCP.10, PCP.22, etc.).

   **Note:** The Principle collection does NOT have a `status` property (only ADRs
   do). Available properties are: `title`, `principle_number`, `content`, `doc_type`,
   `full_text`, plus ownership/chunk properties.

### Proposed changes

#### Change A1 — Restore recursion_limit (elysia_agents.py:205)

After `self.tree = Tree()`, add:

```python
# Limit: 4 iterations covers the most complex realistic pattern
# (search 3 collections + summarize). Default 5 allows the Tree
# to loop on the same tool when cited_summarize doesn't signal
# termination. 4 allows all legitimate multi-collection queries
# while preventing the 5th repetition that's always a loop.
self.tree.tree_data.recursion_limit = 4
```

#### Change A2 — Add recursion logging back (elysia_agents.py, after the async for loop ~line 791)

After `self.tree.settings.LOGGING_LEVEL_INT = original_log_level`, add:

```python
iterations = self.tree.tree_data.num_trees_completed
limit = self.tree.tree_data.recursion_limit
if iterations >= limit:
    logger.warning(f"Elysia tree hit recursion limit ({iterations}/{limit})")
else:
    logger.debug(f"Elysia tree completed in {iterations} iteration(s)")
```

#### Change A3 — Improve list_all_principles tool (elysia_agents.py:545-572)

**Docstring** — add "show all" variants and strengthen the routing hint:

```python
async def list_all_principles() -> list[dict]:
    """List ALL architecture and governance principles (PCPs) in the system.

    ALWAYS use this tool (never search_principles) when the user wants to see,
    enumerate, or count principles rather than search for specific content:
    - "What principles exist?", "List all principles", "Show all principles"
    - "Show me the governance principles", "Please show them all"
    - "How many principles are there?", "Display all PCPs"

    Returns all principles with PCP number, title, and doc_type.
    PCP numbering: PCP.10-20 (ESA), PCP.21-30 (Business), PCP.31-40 (Data Office).

    Returns:
        Complete list of all principles with PCP numbers
    """
```

**Return properties** — add `principle_number`:

```python
results = collection.query.fetch_objects(
    limit=100,
    return_properties=["title", "principle_number", "doc_type"],
)
return sorted(
    [
        {
            "pcp_number": obj.properties.get("principle_number", ""),
            "title": obj.properties.get("title", ""),
            "type": obj.properties.get("doc_type", ""),
        }
        for obj in results.objects
    ],
    key=lambda x: x.get("pcp_number", ""),
)
```

This parallels `list_all_adrs` which sorts by filename and includes structured
identifiers.

#### Change A4 — Also update the fallback `_handle_list_principles_query` (elysia_agents.py:1272-1317)

Add `principle_number` to the fallback too, for consistency:

```python
results = collection.query.fetch_objects(
    limit=100,
    return_properties=["title", "principle_number", "doc_type"],
)

for obj in results.objects:
    all_results.append({
        "type": "Principle",
        "pcp_number": obj.properties.get("principle_number", ""),
        "title": obj.properties.get("title", ""),
        "doc_type": obj.properties.get("doc_type", ""),
    })

# ...format response:
for principle in sorted(all_results, key=lambda x: x.get("pcp_number", "")):
    pcp = f"PCP.{int(principle['pcp_number'])}" if principle.get('pcp_number') else ""
    doc_type = f"({principle['doc_type']})" if principle.get('doc_type') else ""
    response_lines.append(f"- **{pcp} {principle['title']}** {doc_type}")
```

---

## Issue B — Final response leaking into thinking steps

### Root cause

`_map_tree_result_to_event` (`elysia_agents.py:837-857`) filters text events by
`payload_type`. Currently it **only** emits text events when `payload_type == "response"`:

```python
if rtype == "text":
    payload_type = payload.get("type", "")
    if payload_type != "response":
        return None
    # ...emit as {"type": "assistant", "content": content}
```

The problem: both the **intermediate narration** ("I am retrieving the principles...")
and the **final answer** ("Here is a representation of detailed content excerpts
from several Architecture Principles (PCPs): 1.") have `payload_type == "response"`.
The filter can't distinguish them.

The intermediate narration adds no value over the status events
("Running search_principles...") that already show the same information in the
thinking container.

### Proposed changes

#### Change B1 — Stop emitting text events as thinking steps (elysia_agents.py:837-857)

Replace the entire `rtype == "text"` block to skip all text events from the
thinking stream. Only `decision` and `status` events belong in the thinking
container:

```python
if rtype == "text":
    # Don't emit any text events to the thinking queue.
    # Both intermediate narration and the final answer have
    # payload_type="response", so we can't distinguish them.
    # Status events ("Running search_principles...") already
    # provide the same information as the narration text.
    return None
```

This means the `_map_tree_result_to_event` method only returns events for
`tree_update` (→ decision) and `status` (→ status) types. All text content
(intermediate and final) is captured by the `query()` method's
`last_text_content` tracker (line 769-786) for the actual answer panel.

#### Change B2 — Add temporary debug logging (optional, remove after verification)

At the top of the `rtype == "text"` branch, add:

```python
if rtype == "text":
    payload_type = payload.get("type", "")
    content_preview = ""
    objects_list = payload.get("objects", [])
    if objects_list and isinstance(objects_list[0], dict):
        content_preview = objects_list[0].get("text", "")[:80]
    logger.debug(
        f"text event payload_type={payload_type}, "
        f"preview={content_preview!r}"
    )
    return None  # Don't emit to thinking queue
```

---

## Files to modify

| File | Changes |
|------|---------|
| `src/elysia_agents.py:205` | A1: Add `self.tree.tree_data.recursion_limit = 4` |
| `src/elysia_agents.py:~793` | A2: Add recursion logging after async for loop |
| `src/elysia_agents.py:545-572` | A3: Improve docstring + add `principle_number` to return |
| `src/elysia_agents.py:1272-1317` | A4: Add `principle_number` to fallback handler |
| `src/elysia_agents.py:837-857` | B1+B2: Replace text event handler with no-op + debug log |

## Expected outcomes

- **Issue A:** Query time drops from ~63s to ~15-20s. Tree makes 1-2 tool calls
  max (calls `list_all_principles` once, then summarizes). If the Tree still
  picks `search_principles`, the recursion_limit=4 caps it at 4 calls instead
  of 7, and the improved docstrings (A3) should route it correctly in the first place.

- **Issue B:** No text content appears in the thinking container. Users see only
  decision/status steps ("Decision: search_principles", "Running search_principles...")
  followed by the final answer in the answer panel.

## Testing

1. Run the exact query from the screenshot: "Please show them all" (in the
   context of a principles conversation)
2. Verify `list_all_principles` is called (not `search_principles`)
3. Verify response includes PCP numbers (PCP.10, PCP.21, etc.)
4. Verify thinking container shows only status/decision steps, no answer text
5. Verify query completes in <20s
6. Also re-test: "What ADRs exist?" (should still work as before)
7. Also re-test: "What is PCP.22?" (should still use `search_principles`)
