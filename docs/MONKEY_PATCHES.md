# Elysia Integration Points

Check these when upgrading the `elysia-ai` package.

## 1. CitedSummarizingPrompt Docstring Patch

- **File**: `src/elysia_agents.py` (search for `_ANTI_LIST_SENTENCES`)
- **What**: Replaces anti-list instruction in DSPy prompt docstrings with
  "Format the response according to the agent description guidelines."
- **Why**: Elysia's built-in prompts forbid list formatting, conflicting
  with our skills framework's response-formatter skill.
- **Targets**: `CitedSummarizingPrompt`, `SummarizingPrompt`, `TextResponsePrompt`
- **On update**: Check if docstring text changed. If the patch logs
  "CitedSummarizingPrompt docstring changed", the anti-list text moved
  or was reworded. Inspect the new docstring and update `_ANTI_LIST_SENTENCES`.

## 2. Direct async_run() Usage (Bypasses tree.run())

- **File**: `src/elysia_agents.py` `ElysiaRAGSystem.query()` method
- **What**: Calls `tree.async_run()` directly instead of `tree()` / `tree.run()`.
- **Why**: `tree.run()` wraps `async_run()` with Rich console output that
  would need to be parsed from stdout. Direct iteration gives us typed
  result dicts with `payload_type` preserved, enabling properly typed SSE
  events without heuristic text parsing.
- **Replicates from `run()`**:
  - `self.tree.store_retrieved_objects = True`
  - `self.tree.settings.LOGGING_LEVEL_INT = 30` (suppresses Rich panels)
  - Response built from `conversation_history[-1]["content"]`
  - Objects from `self.tree.retrieved_objects`
- **On update**: Diff the new `tree.run()` source against our replicated
  setup. If `run()` adds new initialization steps before `async_run()`,
  replicate them in `query()`.
