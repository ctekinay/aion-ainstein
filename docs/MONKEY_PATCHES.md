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

## 3. Tree LLM Provider Override (`_configure_tree_provider`)

- **File**: `src/elysia_agents.py` `ElysiaRAGSystem._configure_tree_provider()`
- **What**: Overrides Elysia's `settings.BASE_PROVIDER`, `BASE_MODEL`,
  `COMPLEX_PROVIDER`, `COMPLEX_MODEL`, and `MODEL_API_BASE` with AInstein's
  config values. Resets `tree._base_lm` and `tree._complex_lm` (private
  lazy-loaded `dspy.LM` instances) to `None` to force reload.
- **Why**: Elysia's `smart_setup()` auto-detects `OPENAI_API_KEY` in the
  environment and defaults to gpt-4.1/gpt-4.1-mini, ignoring AInstein's
  `LLM_PROVIDER` and `OPENAI_CHAT_MODEL` settings. Without this override,
  the Tree uses OpenAI even when the user selects Ollama mode.
- **Depends on** (elysia/tree/tree.py):
  - `tree._base_lm` — private attribute, initialized to `None` in `__init__`
    (line ~136), lazy-loaded via `@property base_lm` (line ~196)
  - `tree._complex_lm` — same pattern (line ~137, property at line ~205)
  - `tree.settings.BASE_PROVIDER`, `BASE_MODEL`, `COMPLEX_PROVIDER`,
    `COMPLEX_MODEL`, `MODEL_API_BASE` — read by `load_base_lm()` /
    `load_complex_lm()` in elysia/config.py
- **Ollama provider**: Uses `ollama_chat` (not `ollama`) so litellm routes
  to `/api/chat` instead of `/api/generate`. The completion endpoint enforces
  JSON parsing that fails with models like gpt-oss:20b. Elysia's own
  validation only checks `base_provider == "ollama"`, so `ollama_chat`
  bypasses that check — we set `MODEL_API_BASE` explicitly anyway.
- **On update**: Check if `_base_lm` / `_complex_lm` attribute names or
  lazy-loading pattern changed. If Elysia adds a `configure()` method or
  public API for resetting LM objects, prefer that over direct attribute
  access. Search for `_base_lm` in the new tree.py source. Also check if
  Elysia adds `ollama_chat` to its provider validation.
