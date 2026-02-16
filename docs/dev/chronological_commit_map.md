# Chronological Commit Map

> Full history from `main`, sorted chronologically.
> 297 commits, 2026-01-31 to 2026-02-16.

---

## Phase 1: Foundation — LLM Stack & UI (Jan 31 – Feb 2)

*Dual-stack LLM support, Ollama/OpenAI integration, embedding fixes, basic UI.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 1 | Jan 31 11:24 | `e5f6000` | feat: Add dual-stack LLM comparison (Test Mode) | Side-by-side Local vs OpenAI RAG comparison: 8 Weaviate collections (4 local + 4 OpenAI), dual vectorizers (Nomic + OpenAI), dual generative (SmolLM3 + GPT-4o-mini), `/api/chat/stream/compare` endpoint with parallel retrieval, SSE streaming with timing metrics, Test Mode toggle UI with split-screen panels. **+4194 lines across 9 files.** | LLM |
| 2 | Jan 31 13:51 | `2892af6` | Add token counting, context truncation, and evaluation framework | Token estimation (~4 chars/token), context truncation at document boundaries for SmolLM3's 8K window, truncation warning in UI, evaluation framework with 10 test cases, CLI `evaluate` command comparing Ollama vs OpenAI with metrics (term recall, source recall, latency). | LLM |
| 3 | Jan 31 14:28 | `8eae84a` | Add health endpoint and fix evaluation command | `/health` endpoint for service monitoring. Makes Elysia optional (comparison-only mode). Fixes Unicode encoding issue in evaluation CLI. | API |
| 4 | Jan 31 22:16 | `0e2b6fd` | Add Ollama LLM support and chunked document loading | Ollama support in IntentClassifier and ElysiaRAGSystem. Hierarchical chunked loading in document_loader.py and markdown_loader.py. Weaviate client handles Ollama vs OpenAI headers. **+488 lines across 5 files.** | LLM |
| 5 | Jan 31 22:25 | `b850e25` | Add Delete All Conversations button to UI | `delete_all_conversations()` function, `DELETE /api/conversations` endpoint, Delete All button with trash icon and confirmation dialog in sidebar. | UI |
| 6 | Jan 31 23:07 | `298c04c` | Fix Weaviate text2vec-ollama bug with client-side embeddings workaround | **Workaround for Weaviate bug #8406**: module ignores apiEndpoint in Docker. Solution: bypass Weaviate vectorizer, handle embeddings client-side via `embeddings.py` using Ollama `/api/embed`. Verified with 5223 concepts + 156 documents. | Embedding |
| 7 | Feb 1 11:38 | `956868a` | Fix SmolLM3 response quality: strip think tags and improve prompt | Strip `<think>` tags from SmolLM3 responses, explicit RAG-style prompt for small models, structured prompt format forcing context-based answers. Known limitation: ~9s embedding + ~70s generation on CPU. | LLM |
| 8 | Feb 1 11:44 | `ffaa263` | Add GPT-5.x model support, default to GPT-5.2 | GPT-5 model family (gpt-5.2, gpt-5.1, gpt-5.2-chat-latest). Updated defaults from gpt-4o-mini to gpt-5.2. | LLM |
| 9 | Feb 1 11:56 | `7ccbf19` | Fix retrieval quality: filter index files, handle list queries | Filter out index/template files from ADR search, use `full_text` as primary content source, detect "list all" queries and fetch documents directly, increase content limits (500→800), lower alpha to 0.5. | Retrieval |
| 10 | Feb 1 12:10 | `b8afefb` | Refactor retrieval to use proper RAG: metadata filters instead of static code | Replace hardcoded INDEX_TITLES and keyword-based routing with `doc_type` property (content/index/template), `_classify_adr_document()` method, Weaviate native `Filter.by_property()`. Let embeddings determine relevance. **+182/−121 lines.** | Retrieval |
| 11 | Feb 2 08:53 | `32feddf` | Fix embedding timeouts: add retry logic and reduce batch sizes | Increase timeout 60s→300s, retry with MAX_RETRIES=3 and exponential backoff, one-at-a-time fallback, reduce Ollama batch 20→5 and OpenAI batch 100→50. | Embedding |
| 12 | Feb 2 11:23 | `bc58120` | Fix UI text width: make conversation text use full container width | CSS `white-space: pre-wrap → normal`, `formatMessageText()` for HTML escaping + paragraph preservation. Also adds `TECHNICAL_HANDOVER.md` (359 lines). | UI |
| 13 | Feb 2 11:26 | `83eaff0` | Fix OpenAI GPT-5.x and Elysia fallback query issues | `max_completion_tokens` for GPT-5.x (instead of `max_tokens`), fix Elysia `_direct_query` to use client-side embeddings for local collections, provider-specific collection routing, `doc_type` filtering. | LLM |
| 14 | Feb 2 11:34 | `bc641c7` | Fix UI: preserve line breaks for list formatting | Previous fix destroyed list formatting by converting newlines to spaces. Now all newlines become `<br>` tags. | UI |
| 15 | Feb 2 11:49 | `315f1ee` | Fix SmolLM3 timeout and think tag issues in Test Mode | Reduce retrieval limits for Ollama (11 vs OpenAI 22), reduce content per doc (800→400 chars for Ollama), strip `<think>` tags in Elysia, increase timeout 60s→120s. | LLM |
| 16 | Feb 2 12:39 | `76a44a4` | Make retrieval limits configurable instead of hardcoded | Add `retrieval_limit_*`, `retrieval_content_max_chars`, `ollama_context_length` to settings. Configurable via `.env`. | Config |
| 17 | Feb 2 12:56 | `ef360e8` | Add Ollama error handling with actionable messages | Remove retrieval_limit settings (don't mask issues), context size monitoring vs 8K limit, timeout handling with guidance on Ollama settings, OOM detection with context length suggestions. | LLM |
| 18 | Feb 2 13:04 | `322de30` | Fix UI: preserve line breaks for list formatting | Render markdown lists as HTML `<ul>`/`<ol>`, change `<span>` to `<div>` for block layout, add CSS for formatted lists. | UI |
| 19 | Feb 2 15:27 | `8aaf177` | Remove context limit checks — let Ollama handle it | Remove `SMOLLM3_MAX_CONTEXT_TOKENS`, `estimate_tokens()`, `truncate_context()`. Simplify generate_with_ollama. Let Ollama manage limits server-side. **−165 lines.** | LLM |
| 20 | Feb 2 16:01 | `665dd99` | Add timing metrics to non-test mode Elysia responses | Track total response time in `run_elysia_query()`, forward timing via SSE, timing badge in panel footer (T: Xms), color-coded: green (<5s), yellow (>15s). | Observability |

---

## Phase 2: RAG Quality & Test Infrastructure (Feb 2 – Feb 3)

*Gold standard test questions, automated test runner, diagnostic tooling.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 21 | Feb 2 16:37 | `ef32026` | Add comprehensive RAG quality diagnostic plan and inspector tool | 4-phase plan (baseline → retrieval → generation → optimization), `retrieval_inspector.py` CLI tool for querying collections, comparing alpha values, running diagnostic suite. **+567 lines.** | Testing |
| 22 | Feb 2 17:14 | `ffa66fd` | Add 40 gold standard test questions for RAG evaluation | 8 vocabulary, 12 ADR, 6 principle, 6 policy, 5 cross-domain, 3 negative/edge case questions with difficulty ratings and expected answers. | Testing |
| 23 | Feb 2 18:52 | `d7cfe5e` | Add Qwen3 model support and fix UI formatting issues | Qwen3:4b to available models, fix timing badge for Rich-parsed responses, unwrap paragraphs from Rich 80-char wrapping, expand bullet regex for Unicode chars (•, ◦, ▸). | LLM |
| 24 | Feb 2 18:53 | `752ea93` | Add ESA data: decisions, principles, vocabularies, and archimate | ADRs from esa-main-artifacts (~22 decisions), architecture principles (~40), LIDO-BWBR0050714 vocabulary, archimate vocabulary. Updates to existing vocabularies. **+8720 lines, 92 files.** | Data |
| 25 | Feb 2 20:02 | `1252057` | Add Qwen3 model support and fix UI formatting issues | Gold Standard v2.0 (47 questions, 10 categories), standardized alpha values in config.py (`alpha_default: 0.5`, `alpha_vocabulary: 0.6`, etc.), centralized across all agents/modules. | LLM |
| 26 | Feb 2 20:11 | `8b938e8` | Add automated RAG quality test runner | Runs 25 gold standard questions, keyword-based scoring, hallucination detection, accuracy by category/difficulty, `--quick` mode (10 questions), JSON reports to `test_results/`. | Testing |
| 27 | Feb 2 20:41 | `779a958` | Fix Elysia fallback path for client-side embeddings | Add Vocabulary to fallback search, expand vocab keywords ("what is", "define", "meaning"), fix test_runner port (8000→8081). | Embedding |
| 28 | Feb 2 21:09 | `117a13a` | Fix test_runner SSE streaming and add debug mode | Proper httpx streaming for SSE, 180s timeout, `--debug` flag showing raw SSE events, better error/timeout handling. | Testing |
| 29 | Feb 2 21:14 | `6ac31d8` | Add provider auto-switching to test_runner via API | Sets provider via `/api/settings/llm` before tests, `--openai` shortcut, `--model` flag (e.g., qwen3:4b, gpt-4o). | Testing |
| 30 | Feb 2 21:34 | `33c8d0a` | Fix test_runner to use JSON endpoint instead of SSE | Switch from streaming SSE parsing to simple JSON parsing (returns `{response, sources, conversation_id}`). | Testing |
| 31 | Feb 2 21:38 | `a256169` | Expand check_no_answer phrases for better negative test detection | Add "does not include", "cannot provide an answer", "no specific", "outside the scope", "no relevant" etc. to detection phrases. | Testing |
| 32 | Feb 2 22:09 | `ae0d253` | Add service health checks and timeout handling to test runner | `check_service_health()` for Ollama/chat server/Weaviate, `--check-only` and `--skip-health-check` flags, consecutive timeout detection with model suggestions. | Testing |
| 33 | Feb 2 22:18 | `ca80251` | Increase Ollama timeout to 5 min and remove invalid D1 test | Timeouts 120s→300s in elysia_agents and chat_ui, test runner 180s→330s. Remove D1 (ESA) test — answer not in KB. | Config |
| 34 | Feb 2 22:23 | `632d085` | Refactor test_runner to query RAG directly without chat server | Replace HTTP calls with direct `ElysiaRAGSystem` calls. Only needs Weaviate + Ollama/OpenAI running (no chat server). | Testing |
| 35 | Feb 2 22:44 | `62cbd73` | Suppress Elysia verbose output during tests, add --verbose flag | `suppress_stdout()` context manager silences Elysia's decision tree output. `--verbose/-v` flag to show reasoning for debugging. | Testing |
| 36 | Feb 2 23:02 | `dcad1c9` | Fix output suppression to use OS-level file descriptor redirection | Replace `sys.stdout` redirect with `os.dup2` to `/dev/null` to suppress Rich console output. | Testing |
| 37 | Feb 2 23:09 | `571a3c4` | Fix OpenAI model field name (openai_chat_model) | One-line fix in test_runner.py. | Config |
| 38 | Feb 3 07:53 | `42ff062` | Expand check_no_answer phrases to catch more valid negative responses | Add "there is no", "there are no", "does not appear", "based on the provided context" patterns. | Testing |
| 39 | Feb 3 07:58 | `97a2767` | Update system prompt with AInstein identity | Name: AInstein, Company: Alliander, Role: ESA AI Assistant. Guidelines for grounded responses, proper ADR referencing, stating when info is unavailable. | Identity |
| 40 | Feb 3 08:08 | `1be991d` | Treat empty responses as valid 'no answer' for negative tests | Responses <10 chars count as valid "I don't know" for negative tests. Refusing to answer is better than hallucinating. | Testing |

---

## Phase 3: Abstention & Hallucination Prevention (Feb 3)

*Confidence-based abstention, ID extraction, chunking module.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 41 | Feb 3 08:53 | `0d5255c` | Add RAG diagnostic framework with layered analysis | `rag_diagnostics.py`: chunk/doc size analysis, retrieval quality testing, alpha tuning (0.0–1.0), grounding checks. Hallucination detection in test_runner. **+603 lines.** | Testing |
| 42 | Feb 3 10:00 | `da780c3` | Add confidence-based abstention layer to prevent hallucination | **KEY FEATURE**: `should_abstain()` with distance threshold (0.5), exact ADR number matching, query term coverage. `get_abstention_response()` with user feedback. Weaviate hybrid queries request metadata (score, distance). "ADR-0050 was not found" instead of hallucinated ADR. **+116 lines.** | Abstention |
| 43 | Feb 3 11:07 | `7ce3d4b` | Add ADR-0001: Confidence-Based Abstention for Hallucination Prevention | Decision record documenting the problem, solution (multi-layer abstention), implementation, architecture mapping, codebase references, remaining TODOs (SKOSMOS, clarification flow). | Docs |
| 44 | Feb 3 11:14 | `2ef4379` | Fix false positive hallucination detection for abstention responses | Abstention responses mention ADRs to say they don't exist ("ADR-0050 was not found"). Skip hallucination detection when abstention indicators present. | Abstention |
| 45 | Feb 3 11:48 | `0ef2089` | Extract ADR number from filename to prevent hallucination | Extract number from filename (e.g., "0012" from "0012-name.md"), store as `adr_number` in Weaviate, prepend to title ("ADR-0012: Use CIM..."), include in `full_text`. **Requires collection re-creation.** | Ingestion |
| 46 | Feb 3 12:06 | `2d8f7d8` | Add principle number extraction to prevent hallucination | Mirror of ADR number extraction for principles: `principle_number` field, title prefix "PCP-{number}:", Weaviate property. | Ingestion |
| 47 | Feb 3 16:46 | `3dd6875` | Fix UI issues: list numbering, timing display position, and persistence | Fix markdown `<ol>` start attribute, move timing badge to header (like TEST MODE), persist timing in messages table across page refreshes. | UI |
| 48 | Feb 3 16:56 | `a526146` | Add heartbeat indicator to prevent silent processing appearance | Backend: periodic 'heartbeat' SSE events every 3s with elapsed time. Frontend: "Still processing... (Xs elapsed)" with pulse animation. Prevents "broken" appearance during long generation. | UI |
| 49 | Feb 3 17:18 | `506a570` | Update ADR/Principle ID format to match official registry | Change "ADR-0021" → "ADR.21" and "PCP-0010" → "PCP.10" (official format). Both formats in `full_text` for flexible querying. | Data |
| 50 | Feb 3 17:29 | `ef1f26f` | Add chunking module, RAG audit report, and test results | Hybrid chunking module (`src/chunking/`) with document-aware strategies (models, strategies, vector_store). RAG Implementation Audit doc. Evaluation test results. **+4862 lines, 16 files.** | Ingestion |
| 51 | Feb 3 17:33 | `bb13ff8` | Add RAG evaluation framework and golden dataset | RAG Evaluation TestBed specification, golden dataset (YAML), populate/improvement scripts, failure analysis, A/B testing modules, baseline metrics. **+7318 lines.** | Testing |
| 52 | Feb 3 21:03 | `1600ea3` | Distinguish Decision Approval Records from actual ADRs/Principles | `decision_approval_record` classification for NNNND-*.md files. Different title prefix: "ADR.20D (Approval Record)" vs "ADR.20". Same logic for Principles. Fixes double-counting (38→19 ADRs). | Ingestion |
| 53 | Feb 3 21:53 | `ae7d6ae` | Update data artifacts and documentation structure | Update do-artifacts index, remove Dutch governance principles (moved/consolidated), rename ADR template, add esa-main-artifacts README, remove Elysia reference docs. | Data |

---

## Phase 4: Skills Framework (Feb 4 – Feb 5)

*Externalize rules/thresholds to skills, Skills UI (5 phases), security fixes.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 54 | Feb 4 08:40 | `ce7c506` | Add Skills Framework Implementation TODO document | 26 tasks across 8 phases: skills directory, SkillLoader, prompt injection, threshold externalization, testing. | Docs |
| 55 | Feb 4 08:50 | `13095ca` | Remove vendor-specific references from TODO document | "Claude Skills" → "Agent Skills (agentskills.io)", generic branch naming. | Docs |
| 56 | Feb 4 09:45 | `8149406` | Implement Skills Framework for externalizing rules and thresholds | **KEY FEATURE**: `skills/` directory with `rag-quality-assurance` skill (SKILL.md, thresholds.yaml, registry.yaml). `src/skills/` module (loader.py, registry.py). Inject skill content into system prompts. Load abstention thresholds from config. **+785 lines, 10 files.** | Skills |
| 57 | Feb 4 11:18 | `5539b56` | Fix remaining hardcoded values in Skills Framework | DEFAULT_SKILL constant, use in elysia_agents/chat_ui. Add `content_max_chars` to thresholds. Make `_direct_query()` use skill-loaded retrieval limits. | Skills |
| 58 | Feb 4 11:28 | `a8b9b79` | Externalize all content truncation values to skill config | Truncation section in thresholds.yaml: `content_max_chars: 800`, `elysia_content_chars: 500`, `elysia_summary_chars: 300`. `get_truncation()` method. All `[:500]`, `[:300]`, `[:800]` replaced with config. | Skills |
| 59 | Feb 4 11:32 | `09d8d46` | Add max_context_results to skill config | Externalize the `[:10]` context limit. Now configurable via thresholds.yaml. | Skills |
| 60 | Feb 4 11:46 | `c299ddf` | Fix identity and content visibility issues | AInstein identity rules in SKILL.md. Add `adr_number`, `principle_number`, `file_path` to tool return fields. Agent identifies as "AInstein" and references docs by ID. | Identity |
| 61 | Feb 4 11:56 | `3ff943b` | Merge skills framework manual | Merge commit. | Merge |
| 62 | Feb 4 11:58 | `8c1555e` | Update Skills Framework manual with corrections | Replace stale line numbers, add Identity Configuration section, add DEFAULT_SKILL docs, add Tool Return Fields table, clarify Hot Reload status, version 1.1. | Docs |
| 63 | Feb 4 12:53 | `9779749` | Add comprehensive Skills Framework user manual | Covers non-technical and technical users, YAML configuration reference, step-by-step editing, API reference, troubleshooting. **+562 lines.** | Docs |
| 64 | Feb 4 12:56 | `99b71c1` | Add detailed Skills Management UI design specification | Complete wireframes, skill creation wizard (3-step), API endpoint specs, implementation priority phases. **+556 lines.** | Docs |
| 65 | Feb 4 14:20 | `0725510` | Add Progressive Loading to Skills Framework roadmap | 3-level progressive loading: Discovery (~50 tokens) → Activation (full SKILL.md) → Execution (on-demand). Compare with MCP lazy loading. | Docs |
| 66 | Feb 4 14:24 | `2d07a10` | Add comprehensive Skills UI implementation TODO | 7 phases: MVP → Full Config → Rule Editor → Advanced Testing → Creation Wizard → Hot Reload → Progressive Loading. **+431 lines.** | Docs |
| 67 | Feb 4 14:50 | `a627011` | Externalize list query detection to Skills Framework | `list_indicators`, `list_patterns`, `additional_stop_words` in thresholds.yaml. `get_list_query_config()` in SkillLoader. Fixes LIST-type queries incorrectly abstaining. | Skills |
| 68 | Feb 4 14:57 | `271e4d0` | Merge manual corrections from handover branch | Merge commit. | Merge |
| 69 | Feb 4 15:07 | `7fe9c08` | Fix misplaced import in elysia_agents.py | Move `embed_text` import to top of file. | Bugfix |
| 70 | Feb 4 15:25 | `430bb45` | Add comprehensive Ollama setup documentation to README | Fix `OLLAMA_EMBEDDING_MODEL`, Ollama as default provider, detailed setup/troubleshooting, architecture diagram, LLM provider config table, Linux notes. **+236 lines.** | Docs |
| 71 | Feb 4 15:26 | `efc0111` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 72 | Feb 4 15:30 | `005a578` | Implement Skills UI MVP (Phase 1) | **KEY FEATURE**: Backend `src/skills/api.py` (list, get, update, validate, backup, restore, test, reload). 9 FastAPI endpoints. Frontend `skills.html`: skills list, quick settings sliders, testing panel, backup/restore, dark theme. **+1224 lines.** | Skills UI |
| 73 | Feb 4 15:30 | `3fc4abb` | Add Qwen3 models to Ollama alternatives | qwen3:4b (2.6GB) and qwen3:8b (5GB) in README alternatives table. | Config |
| 74 | Feb 4 15:43 | `768825c` | Fix skills API import location in chat_ui.py | Move import to top of file to avoid import timing issues. | Bugfix |
| 75 | Feb 4 15:44 | `8620b35` | Fix Windows encoding error when reading skills.html | Explicitly specify UTF-8 encoding for `read_text()` (Windows default is cp1252). | Bugfix |
| 76 | Feb 4 15:52 | `fc62bb4` | Add Skills button to main chat UI sidebar | "Skills" button between Settings and Delete All, navigates to `/skills`. | UI |
| 77 | Feb 4 16:08 | `299d923` | Fix Elysia decision tree loop causing repeated responses | Reduce `recursion_limit` from 5 to 2. Root cause: `cited_summarize` doesn't signal termination, causing 4-5 repeated responses and ~74s queries. | Bugfix |
| 78 | Feb 4 17:19 | `e8b5886` | Implement Skills UI Phase 2: Full Configuration Modal | Modal with tabs: Abstention Thresholds, Retrieval Limits, Truncation Limits, List Query Detection. Real-time validation, regex pattern validation, keyboard shortcuts. `/api/skills/{name}/validate` endpoint. **+807 lines.** | Skills UI |
| 79 | Feb 4 17:40 | `8ba5574` | Fix critical bugs from code review | P0: Fix data structure mismatch (list_query_detection key). P1: Fix `switchTab()` Firefox bug (implicit event). P2: Server-side regex validation for list_indicators/patterns. P3: Loading states for buttons. | Bugfix |
| 80 | Feb 4 17:54 | `62844bd` | Improve code quality from remaining review items | Dynamic `currentSkill` from API, centralized DEFAULTS constants, backup cleanup (keep last 5), extract magic numbers, null checks. | Quality |
| 81 | Feb 4 18:19 | `27e5d3f` | Update Skills UI architecture docs and tune RAG thresholds | FastAPI architecture decision, revised file structure. Lower `distance_threshold` 0.5→0.4 for stricter relevance. Simplify thresholds.yaml formatting. | Docs |
| 82 | Feb 4 18:25 | `21df2c8` | Resolve merge conflict in SKILLS_UI_TODO.md | Keep remote version with Phase 1 & 2 marked completed. | Merge |
| 83 | Feb 4 18:43 | `e649dfb` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 84 | Feb 4 21:32 | `8dbe992` | Implement Skills UI Phase 3: Rule Editor | **KEY FEATURE**: Edit SKILL.md via web interface. Backend: get/update/validate/backup/restore content. 4 new endpoints. Frontend: Rule Editor modal, metadata editor, markdown textarea, live preview, split/edit/preview toggle. **+959 lines.** | Skills UI |
| 85 | Feb 4 21:33 | `9158940` | Update TODO: Mark Phase 3 Rule Editor as completed | TODO tracking update. | Docs |
| 86 | Feb 4 22:13 | `9fae574` | Fix Phase 3 code review issues | Null check for `restoreRules()`, consolidated Escape key handler for multiple modals, `escapeYamlString()` helper for special characters. | Bugfix |
| 87 | Feb 4 22:22 | `1f006bf` | Improve code quality from Phase 3 review | Extract `SKILLS_DIR` constant (removes 7 repetitions), `get_defaults()` API endpoint, debounce for live preview (150ms), null check for `validateRules()`. | Quality |
| 88 | Feb 4 22:23 | `23764e2` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 89 | Feb 4 22:30 | `6f45830` | Fix defaults API: frontend now loads from backend | Backend: `DEFAULT_LIST_INDICATORS`, `DEFAULT_ADDITIONAL_STOP_WORDS` constants. Frontend: `loadDefaults()` from `/api/skills/defaults`. Backend is single source of truth. | Skills UI |
| 90 | Feb 4 22:39 | `c1d87f5` | Implement Skills UI Phase 1.5: Enable/Disable Toggle | Toggle switch on skill cards. `set_skill_enabled()` updates registry.yaml. `PUT /api/skills/{name}/enabled` endpoint. ACTIVE/DISABLED badges, restart warning banner. **+253 lines.** | Skills UI |
| 91 | Feb 4 22:43 | `9a4742d` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 92 | Feb 4 22:49 | `5b59fea` | Fix Phase 1.5 code review issues | Rewrite `set_skill_enabled()` for targeted line editing (preserves YAML comments). Backup before modify. XSS fixes: `escapeHtml()`, `escapeAttr()`, event delegation via `data-skill-name`. | Bugfix |
| 93 | Feb 4 23:05 | `6af051f` | Implement Skills UI Phase 5: Skill Creation Wizard | **KEY FEATURE**: 4-step wizard: Basic Info → Initial Rules → Thresholds → Review & Create. Backend: `POST /api/skills` (create), `DELETE /api/skills/{name}`, template selection, name validation. Targeted line editing for registry.yaml. **+1337 lines.** | Skills UI |
| 94 | Feb 4 23:16 | `dca5218` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 95 | Feb 4 23:18 | `c84ec75` | Fix Phase 5 security vulnerabilities and add delete UI | **CRITICAL**: Path traversal in `delete_skill()` — `_validate_skill_reference()` + resolved path check. Path traversal in `_create_thresholds_content()`. YAML injection protection with `_escape_yaml_string()`. Delete button with confirmation. | Security |
| 96 | Feb 4 23:24 | `094c7e6` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 97 | Feb 4 23:30 | `626b83b` | Fix path traversal in ALL skill API endpoints | FastAPI PathParam regex `^[a-z][a-z0-9-]*[a-z0-9]$` on all 13 `skill_name` parameters. Prevents `../` attacks at API boundary. | Security |
| 98 | Feb 4 23:32 | `54fc3f1` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 99 | Feb 4 23:43 | `1ae4798` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 100 | Feb 4 23:54 | `571359b` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 101 | Feb 5 00:10 | `40cf0ae` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 102 | Feb 5 00:19 | `d336781` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 103 | Feb 5 07:15 | `7012d6b` | Add step-by-step skill creation guide with response-formatter example | Tutorial for creating Response Formatter skill via wizard: all 4 steps, complete SKILL.md content, testing, troubleshooting. **+418 lines.** | Docs |
| 104 | Feb 5 07:57 | `d5a0a07` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 105 | Feb 5 08:25 | `9af5722` | Merge branch skills-framework-WdLfB | Merge commit. | Merge |
| 106 | Feb 5 11:31 | `7eba23d` | Add Reload Skills button and response-formatter example skill | Reload button in warning banner. Response-formatter skill as working example. Extended creation guide with server commands, file structure, threshold explanations. **+553 lines.** | Skills UI |
| 107 | Feb 5 11:36 | `3833a75` | Add light/dark theme toggle to Skills UI | Light theme CSS variables, toggle button (sun/moon icons), syncs with main UI via localStorage, system preference fallback. | UI |
| 108 | Feb 5 11:49 | `f998de6` | Fix enable/disable skill persistence bug and improve UX | **Critical bug**: disabled skills re-enabled after reload (YAML parser uses LAST value for duplicate keys). Rewrite `set_skill_enabled()` to remove ALL duplicate `enabled:` lines. Auto-reload after toggle. | Bugfix |

---

## Phase 5: DAR Filtering & Production Hardening (Feb 6 – Feb 7)

*DAR distinction, skills-based filtering, async fixes, transparency-first retrieval.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 109 | Feb 6 15:19 | `e97a21a` | Update Skills UI color scheme to Alliander green | Primary colors blue (#2563eb) → green (#10b981), updated dark and light themes. | UI |
| 110 | Feb 6 20:16 | `76249eb` | Fix SkillRegistry singleton pattern for state synchronization | `get_skill_registry()` singleton function. All modules (chat_ui, elysia_agents, api) share same instance. Fixes UI toggle not affecting RAG system. | Bugfix |
| 111 | Feb 6 20:57 | `7e15f93` | macOS setup improvements and UI theme update | Weaviate 1.28.2→1.34.11, updated Python deps, default model gpt-oss:20b, rebrand CLI from 'start-elysia-server' to 'chat', emerald green theme for main UI, favicon, rename 10 policy docs (remove spaces). | DevEx |
| 112 | Feb 6 21:04 | `3e4f8c3` | Update Ollama model settings to include installed models | Add gpt-oss:20b and qwen3:14b, set gpt-oss:20b as default (was smollm3), reorder by capability. | Config |
| 113 | Feb 6 21:08 | `9e23e74` | Fix 4 critical bugs in Skills framework | **Bug 1 (CRITICAL)**: Missing logger in api.py → NameError. **Bug 2 (HIGH)**: Multiple SkillRegistry instances → state sync issues, fixed with singleton. **Bug 3**: Duplicate reloadSkills(). **Bug 4**: Null reference in reloadSkills(). | Bugfix |
| 114 | Feb 6 21:19 | `1e25782` | Merge latest changes from skills-framework-WdLfB | Merge with conflict resolution in chat_ui.py and elysia_agents.py. | Merge |
| 115 | Feb 6 21:26 | `c14d219` | Re-apply model settings: Add gpt-oss:20b and qwen3:14b | Settings lost during merge, re-applied. | Config |
| 116 | Feb 6 21:51 | `d478374` | Fix DAR/Principle double-counting: Exclude DARs from ingestion | Skip NNNND-*.md files in `load_adrs()` and `load_principles()`. Fixes 38→19 ADR count. | Ingestion |
| 117 | Feb 6 21:57 | `0f2cf92` | Revert hardcoded DAR filtering — will implement via skills instead | Reverts commit d478374. DARs contain valuable approval/governance data. Proper solution: Weaviate filters in skills. | Revert |
| 118 | Feb 6 21:58 | `d1f13da` | Implement skills-based DAR filtering (proper solution) | **KEY FEATURE**: `filters` section in thresholds.yaml. `_build_document_filter()` with query-aware filtering: default excludes DARs; approval queries include them. "List all principles" = 19 results; "Who approved X?" = includes DARs. | Skills |
| 119 | Feb 6 22:26 | `62dec82` | Fix CRITICAL: Replace hardcoded filters with shared skills-based filter module | `src/skills/filters.py` as shared module. Elysia mode now uses `build_document_filter()` instead of hardcoded filter. Consistent filtering across both paths. | Skills |
| 120 | Feb 6 22:28 | `cb8262b` | Clean up: Remove outdated decision and update skills registry | Remove outdated flexibility service provider decision, update registry config. | Cleanup |
| 121 | Feb 6 22:36 | `ac91c0f` | Improve filter module: exports, patterns, and dedupe | Export `build_document_filter` in `skills/__init__.py`. Add approval patterns: "sign off", "reviewed by", "stakeholders". Remove redundant keywords. | Skills |
| 122 | Feb 6 23:02 | `4aba868` | Fix CRITICAL bug: Use skill.thresholds instead of skill.config | Skill dataclass has `thresholds` attribute, not `config`. Was causing AttributeError. | Bugfix |
| 123 | Feb 6 23:09 | `f774af4` | Add null check for skill loading in build_document_filter | Prevent AttributeError if skill fails to load. | Bugfix |
| 124 | Feb 7 10:32 | `396e16d` | Fix uvloop incompatibility with Elysia tree by using asyncio loop | **KEY FIX**: Elysia tree's patching mechanism incompatible with uvloop, causing slow "direct tool execution" mode. Force `loop="asyncio"` in uvicorn. Query times ~42s → ~3-8s. | Async |
| 125 | Feb 7 11:36 | `1a67755` | Increase retrieval limits and add catalog_fetch_limit config | ADR 8→20, principle 6→12, policy 4→8, vocab 4→8. `catalog_fetch_limit: 100` for future "list all" bypass. Interim fix for incomplete list results. | Config |
| 126 | Feb 7 11:42 | `c1717db` | Implement transparency-first retrieval with collection counts | **KEY FEATURE**: `is_list_query()` for catalog detection, `get_collection_count()` for totals, `fetch_objects()` for list queries instead of hybrid search. LLM receives "showing X of Y total". Fix embedding model bug (was incorrectly changed when switching chat models). | Retrieval |
| 127 | Feb 7 12:17 | `678d09d` | Move index.md and README to doc directory | Relocate from `data/esa-main-artifacts/` to `doc/` for better organization. | Cleanup |
| 128 | Feb 7 12:19 | `a03950d` | Add backup files to gitignore and clean up existing backups | `*.bak*` pattern in .gitignore. Remove existing .bak files from skills/. | Cleanup |
| 129 | Feb 7 12:19 | `4cde37f` | Remove tracked backup files from response-formatter skill | Remove previously tracked .bak files (redundant with git history). | Cleanup |
| 130 | Feb 7 20:16 | `55ae832` | Fix minor issues from code review | Count display uses `truncated_results` (what LLM sees). Add count tracking to fallback search. Cache compiled regex patterns (`_compiled_list_patterns`). | Quality |
| 131 | Feb 7 20:53 | `457eb43` | Fix Elysia tools missing DAR/index/template filters | **Root cause of DARs in results**: Elysia tools (`list_all_adrs`, `list_all_principles`) had NO filtering. Now use `build_document_filter()`. Log transparency (X of Y total). | Bugfix |
| 132 | Feb 7 21:18 | `a297c57` | Inject skills into Elysia and enable chunked ingestion | Inject response-formatter skill into Elysia's LLM calls via `change_agent_description()`. Enable chunked loading with `--chunking` CLI flag. `_chunk_to_adr_dict()` and `_chunk_to_principle_dict()` helpers. **+233 lines.** | Skills |
| 133 | Feb 7 21:49 | `1ec6ea2` | Fix principle_number extraction in chunked ingestion | Add `principle_number` parameter to `_chunk_to_principle_dict()`, extract from `source_file` using regex. | Ingestion |
| 134 | Feb 7 22:24 | `64d71fe` | Fix vectorizer errors and improve transparency in LLM responses | All Elysia tools now compute query embeddings before hybrid search (collections use `Vectorizers.NONE`). Explicit "X of Y total" instructions in system prompt. | LLM |
| 135 | Feb 7 22:34 | `b173c0f` | Add counting tool and fix test thresholds for 11/11 pass rate | `count_documents` tool for Elysia: dedicated, filtered, supports counting by type. Fix test thresholds for chunking variance. Aims for 100% pass rate. | Testing |
| 136 | Feb 7 22:43 | `77f0896` | Add comprehensive implementation quality test suite | 11 tests across 5 suites: Skills Injection (3), DAR Filtering (2), Principle Numbers (2), Chunking Quality (2), Transparency & Counts (2). Rich console output, JSON export. **+841 lines.** | Testing |
| 137 | Feb 7 22:44 | `24ec92f` | Update .gitignore to exclude database and venv files | `venv[0-9]*/`, `*.db`, `*.sqlite`, `*.sqlite3` patterns. | Cleanup |
| 138 | Feb 7 23:18 | `d844ea9` | Fix principle_number extraction in chunked mode and test client management | Extract 4-digit number from filename, fix test Weaviate client (use `get_weaviate_client()` instead of context manager). 6/11 tests passing (54.5%). | Ingestion |
| 139 | Feb 7 23:19 | `0255de2` | Remove duplicate principle_number extraction after rebase | Remove redundant extraction code (already implemented in 1ec6ea2). | Cleanup |

---

## Phase 6: Structured Response & Response Gateway (Feb 7 – Feb 8)

*JSON schema, response gateway, LLM client abstraction, retry logic, concurrency.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 140 | Feb 7 23:26 | `fd34503` | Add enterprise-grade structured JSON response schema | **KEY FEATURE**: `src/response_schema.py` with `StructuredResponse` dataclass (answer, items_shown, items_total, count_qualifier, sources). Invariant validation, fallback parsing chain (direct → extract → repair). **+362 lines.** | Response |
| 141 | Feb 7 23:45 | `ab2a930` | Add P3 metrics tracking, caching, and P4 schema versioning | `ResponseMetrics` singleton with thread-safe counters. `ResponseCache` LRU with TTL (5min online, 1hr CI). Schema versioning (CURRENT_SCHEMA_VERSION="1.0"). **+505 lines.** | Response |
| 142 | Feb 8 00:02 | `98e43ed` | Add technical implementation document for structured response system | Architecture overview, component details, P3 metrics/caching, P4 versioning, integration guide, API reference, SLO definitions. **+696 lines.** | Docs |
| 143 | Feb 8 00:17 | `62fa8b5` | Enhance documentation with deep-dive sections and operations guide | JSON repair algorithm, concurrency model with double-checked locking, thread safety guarantees, performance benchmarks, troubleshooting guide, rollback strategy. **+383 lines.** | Docs |
| 144 | Feb 8 00:18 | `23e1415` | Fix commit hash in documentation | One-line fix. | Docs |
| 145 | Feb 8 00:36 | `1a98ed9` | Add response-contract skill for structured JSON output | Triggers on list/count queries, documents JSON schema contract (schema_version 1.0), explains invariants, shows examples. Works with response-formatter and rag-quality-assurance. **+196 lines.** | Skills |
| 146 | Feb 8 00:45 | `c1ff04b` | Add comprehensive deep-dive document explaining implementation rationale | Problem (regex fragility), solution (structured JSON), component breakdown with code examples, design decisions, flow diagrams. **+782 lines.** | Docs |
| 147 | Feb 8 01:14 | `8771c06` | Address lead dev's 9-point documentation review | Non-Goals section, regex usage clarity, trigger routing risks, sources field contract, items_total null guidance, SLO targets (99.5%), security/privacy for caching. **+306 lines.** | Docs |
| 148 | Feb 8 01:41 | `c7aba55` | Add explicit BM25 fallback when embedding generation fails | When Ollama embedding fails, fall back to keyword-only BM25 search instead of passing None vector. Graceful degradation with `use_keyword_only` flag. | Retrieval |
| 149 | Feb 8 01:43 | `588ead6` | Add ADR documenting explicit BM25 fallback on embedding failure | Rationale: zero vector fallback is harmful (not neutral), BM25 is correct degradation path. Future improvements P1-P3. | Docs |
| 150 | Feb 8 01:54 | `fe033cd` | Fix ADR factual error and add scope clarification | `embed_text()` does NOT have retry logic (only `embed_batch`). Scope: Ollama vectorizer-none path only. | Docs |
| 151 | Feb 8 13:10 | `afcf176` | Formalize 3-layer architecture and improve ingestion efficiency | **KEY FEATURE**: Skip templates/indexes at ingestion time. `ARCHITECTURE.md` documenting 3-layer separation: Domain Knowledge (/data), Behavior Rules (/skills), Project Decisions (/docs/implementation-records). | Architecture |
| 152 | Feb 8 13:19 | `8a68772` | Link ARCHITECTURE.md from main README | Reference to architecture docs after ASCII diagram. | Docs |
| 153 | Feb 8 13:38 | `e6e5b97` | Consolidate and reorganize technical documentation | Merge 2 structured response docs → 1. Convert TODO → STATUS. Rename manual → guide. Archive historical docs. Add `docs/README.md` as entry point. | Docs |
| 154 | Feb 8 15:11 | `cfd6a01` | Add redirect headers and doc lifecycle note | Archived header in SKILLS_UI_TODO.md, doc lifecycle note in README. | Docs |
| 155 | Feb 8 15:47 | `3372ba0` | Rename implementation records from ADR to IR format | ADR-xxxx-* → IR0001-*, IR0002-*. Distinguishes internal project decisions (IR) from ESA ADRs in RAG. | Docs |
| 156 | Feb 8 16:29 | `d583974` | Clarify ADR-0050 is a fictional ESA ADR test case | Distinguish test case ADR (domain knowledge) from implementation records (IR). | Docs |
| 157 | Feb 8 18:23 | `b88eaa7` | Add unified LaTeX specification document | Consolidates ARCHITECTURE, STRUCTURED_RESPONSE, SKILLS_USER_GUIDE, SKILLS_UI_STATUS into single professional LaTeX document. **+1622 lines.** | Docs |
| 158 | Feb 8 19:10 | `aeac05e` | Add docs/archive/ to gitignore | Exclude archived docs from version control. | Cleanup |
| 159 | Feb 8 20:30 | `f2d327b` | Wire structured response contract into main path | **KEY FIX**: Response-contract was only enforced in fallback (`_direct_query`), not main Elysia tree path. Add `is_skill_active()`, `postprocess_llm_output()`, strict/soft enforcement. 220+ lines of tests. | Response |
| 160 | Feb 8 20:46 | `03deb3a` | Add unified API response gateway module | **KEY FEATURE**: `src/response_gateway.py` — CLI delimiter protocol (`<<<JSON>>>...<<<END_JSON>>>`), structured mode context, controlled failure UX, Weaviate integration for `items_total`. `normalize_and_validate_response()` entry point. **+581 lines.** | Response |
| 161 | Feb 8 20:55 | `45a480c` | Add LLM client abstraction and response gateway smoke tests | `src/llm_client.py`: `ElysiaClient` (agentic RAG), `DirectLLMClient` (fallback), `ResilientLLMClient` (failover). Factory `create_llm_client()`. Smoke tests for strict mode. **+949 lines.** | Response |
| 162 | Feb 8 20:58 | `d07b8f1` | Add Response Gateway and LLM Client sections to LaTeX spec | Response Gateway + LLM Client sections, Key Source Modules appendix, version 1.2. | Docs |
| 163 | Feb 8 21:11 | `3a84a6f` | Implement retry logic and API improvements in response gateway | Retry when strict mode fails extraction/validation with RETRY_PROMPT. Track retry_attempted/ok/failed metrics. Document strict mode JSON acceptance rules. Public `get_matched_triggers()` API. **+402 lines.** | Response |
| 164 | Feb 8 21:16 | `7eedf0a` | Wire retry_func and fix concurrency in LLM client | Wire retry closure into ElysiaClient. **Fix concurrency**: remove shared `_tree` instance, create per-request tree. Fix `entry.name` bug (dataclass not dict). | Response |
| 165 | Feb 8 21:34 | `7ad0371` | Fix async event loop blocking with asyncio.to_thread() for Elysia Tree calls | Wrap blocking `Tree()` with `asyncio.to_thread()`, add concurrency semaphore (MAX_CONCURRENT_ELYSIA_CALLS=4), lazy semaphore init. **P1 reliability/performance fix.** | Async |
| 166 | Feb 8 21:44 | `0703441` | Fix thread safety and add timeout/configurable concurrency for Elysia | Per-request Tree instances (eliminates race condition on `change_agent_description()`). `max_concurrent_elysia_calls` (4) and `elysia_query_timeout_seconds` (120s) in config. `asyncio.wait_for()` timeouts. | Async |
| 167 | Feb 8 21:59 | `1349251` | Fix ADR filter issue and disable streaming for structured mode | Change from NOT_EQUAL to positive EQUAL (`doc_type == "content"`). Suppress intermediate streaming when `structured_mode` active. Diagnostic logging for filter counts. | Bugfix |
| 168 | Feb 8 22:15 | `1038a80` | Add fallback for filter when doc_type not set in Weaviate | When positive filter returns 0 results but collection has documents, fall back to no filter + in-memory filtering (exclude templates, indexes, DARs). | Retrieval |
| 169 | Feb 8 22:25 | `3e57541` | Disable auto-activation for response-formatter skill | `auto_activate: false`. Only activate on trigger keywords. | Skills |
| 170 | Feb 8 22:29 | `4a739a8` | Guardrails for in-memory fallback filter | Feature flag `ENABLE_INMEMORY_FILTER_FALLBACK`, safety cap `MAX_FALLBACK_SCAN_DOCS` (2000), observability (metrics, PRODUCTION warnings), controlled error response. **10 tests, +558 lines.** | Retrieval |

---

## Phase 7: Taxonomy, doc_type & Server-Side Filtering (Feb 8 – Feb 9)

*Formal doc_type taxonomy, server-side filtering, Phase 4 compliance.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 171 | Feb 8 22:33 | `59aab1c` | Doc type taxonomy and classifier tests | **KEY FEATURE**: `src/doc_type_classifier.py` with canonical taxonomy (adr, adr_approval, template, index, unknown). Classification by filename → title → content → default. **60 tests, +658 lines.** | Taxonomy |
| 172 | Feb 8 22:35 | `c633fda` | Add migration script to backfill doc_type | `scripts/migrate_doc_type.py`: paginate objects, compute doc_type via classifier, batch update, summary table. `--dry-run` support. **19 tests, +677 lines.** | Migration |
| 173 | Feb 8 22:38 | `130935f` | Server-side ADR filtering using doc_type allow-list | Allow-list approach: `doc_type == "adr" OR doc_type == "content"`. Removes NOT_EQUAL which failed with null. `build_adr_filter()`, `build_principle_filter()`. **15 new tests, +370 lines.** | Routing |
| 174 | Feb 8 22:45 | `c15edc2` | Add document identity verification script | Verifies Phase 4 invariants: 100% ADR chunks have `adr_number`/`file_path`, unique count ≈ 18, ADR.0030/0031 exist, chunks-per-ADR distribution. | Verification |
| 175 | Feb 8 23:09 | `92d225d` | Deterministic list response serialization for contract compliance | **KEY FEATURE**: `src/list_response_builder.py` — deduplicate by identity key, stable sorting, contract-compliant JSON. `items_total` = unique document count (18), not chunk count (94). Detect list queries → bypass LLM. **+944 lines.** | Routing |
| 176 | Feb 9 11:34 | `f2ed835` | Phase 4 compliance: Server-side filtering and ambiguity-safe routing | Addresses all Phase 4 gaps: Gap A (Weaviate filter verification), Gap B (identity invariants + CI mode), Gap C (ambiguity-safe routing with confidence mechanism), Gap D (fallback transparency with `count_qualifier="at_least"`). **66 new/updated tests, +1235 lines.** | Routing |

---

## Phase 8: SKOSMOS & Phase 5 (Feb 9)

*Local-first terminology verification, SKOSMOS integration, ESA taxonomy.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 177 | Feb 9 13:05 | `82ff904` | Phase 5 plan: Enterprise RAG best practices order (A→F→B→D→C/E) | IR0003 with implementation plan: correctness first (SKOSMOS) → observability → quality tuning → resilience → UX. Skeleton observability module, evaluation script, 10 golden queries. **+1100 lines.** | Docs |
| 178 | Feb 9 13:34 | `5b52617` | Add 6 enterprise acceptance conditions to IR0003 | Terminology intent detection patterns/exclusions, SKOSMOS client behavior (300ms timeout, 10min cache, ABSTAIN policy), request correlation, golden set versioning, threshold tuning harness, circuit breaker confidence. **+532 lines.** | Docs |
| 179 | Feb 9 13:59 | `f9aea62` | Phase 5 Gap A+F: SKOSMOS local-first terminology verification | **KEY FEATURE**: `src/weaviate/skosmos_client.py` with `LocalVocabularyIndex` — 8,000+ terms from 26 vocabularies. Local lookup primary, optional API fallback. Config: `skosmos_mode: local\|api\|hybrid`. `is_terminology_query()` and `verify_terminology()` tool. **35+ tests, +1404 lines.** | SKOSMOS |
| 180 | Feb 9 14:25 | `e7c5530` | Fix term extraction regex and abstention logic for Phase 5 Gap A tests | Regex for ACLineSegment/CamelCase terms, stopword filter. Abstain when terminology query has no extractable terms. | SKOSMOS |
| 181 | Feb 9 14:48 | `a88bf4a` | Clean up repo: remove stale docs and update .gitignore | Remove RAG_Implementation_Audit.md, RAG_QUALITY_DIAGNOSTIC_PLAN.md, Skills_Framework_Implementation_ToDos.md, TECHNICAL_HANDOVER.md, evaluation_results.json. **−1949 lines.** | Cleanup |
| 182 | Feb 9 14:59 | `51002d5` | Revert Gap F SKOSMOS local-first metrics from observability.py | Remove 4 SKOSMOS metrics from observability.py. | Revert |
| 183 | Feb 9 15:10 | `54d235e` | Fix critical Phase 5 regressions: pagination, counts, and contract compliance | Fix list truncation (20→all via `fetch_all_objects()` with pagination). Fix `count_documents` returning chunks not unique docs. Add deterministic COUNT query handling (`is_count_query()`). Fix strict enforcement degradation (show LLM response, not error). Add `list_approval_records()` tool. **+323 lines.** | Bugfix |
| 184 | Feb 9 16:07 | `d480232` | Add verification script for index.md, documents:, and record_type checks | Evidence for 3 checks: index.md not ingested, documents: field unused at runtime, doc_type provides deterministic separation. **+575 lines.** | Verification |
| 185 | Feb 9 16:41 | `45899da` | Rename doc/index.md to esa_doc_registry.md and add deterministic ingestion rules | Prevent registry from being skipped as index artifact. "registry" as new doc_type. Deterministic rules: ALWAYS SKIP templates/indexes in decisions/principles; ALWAYS INGEST NNNN-*.md, NNNND-*.md, esa_doc_registry.md. **+240 lines, 7 files.** | Ingestion |
| 186 | Feb 9 17:04 | `94a3b9a` | Add ESA Document Taxonomy contract and fix routing/enforcement issues | `docs/ESA_DOCUMENT_TAXONOMY.md` — authoritative contract for classification, ID parsing, filtering, routing, output labeling. Fix specific doc patterns (1-4 digits), topical/semantic markers, strict enforcement. **181 tests passing, +517 lines.** | Taxonomy |
| 187 | Feb 9 17:26 | `564c60b` | Rename index.md to esa_doc_registry.md for clarity | File rename. | Cleanup |
| 188 | Feb 9 17:41 | `d76b353` | Revert "Rename index.md to esa_doc_registry.md for clarity" | Revert of 564c60b. | Revert |
| 189 | Feb 9 17:43 | `f16da3d` | Merge branch handover-WdLfB | Merge commit. | Merge |
| 190 | Feb 9 18:08 | `070c625` | Merge branch handover-WdLfB | Merge commit. | Merge |

---

## Phase 9: Approval Extraction & Deterministic Retrieval (Feb 9)

*Deterministic approval parsing, content retrieval for specific docs, section parsing.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 191 | Feb 9 17:48 | `91552f7` | Add deterministic approval extraction and fix resource warnings | **KEY FEATURE**: `src/approval_extractor.py` — parse markdown tables for approvers (name, email, role), handle multiple approval sections, deduplication, structured JSON. Fix ResourceWarning (Weaviate sockets), fix deprecated `datetime.utcnow()`. **28 new tests, +706 lines.** | Approvals |
| 192 | Feb 9 18:18 | `5d5ee11` | Add deterministic content retrieval for specific ADR/PCP queries | Fix: "Tell me about ADR.0025" found DAR first (keyword-dense). Add `is_specific_content_query()`, `get_content_record_from_weaviate()`, `get_dar_record_from_weaviate()`. "ADR.0025" → decision content; "ADR.0025D" → DAR. **22 unit + 5 integration tests, +1373 lines.** | Retrieval |
| 193 | Feb 9 18:22 | `4491f0c` | Add document pair verification script | Script to verify document pair relationships. | Verification |
| 194 | Feb 9 19:01 | `e4eb7b3` | Update .gitignore and simplify RAG thresholds config | Unblock tests/ and test_results/ in .gitignore. ADR retrieval limit→50. Remove unused confidence/filter settings from thresholds. | Config |
| 195 | Feb 9 22:37 | `168c263` | Fix Weaviate client import and add integration test marker | Use `get_weaviate_client`, add integration pytest marker in pyproject.toml. | Testing |
| 196 | Feb 9 23:14 | `7e7738d` | Fix ADR section parser and add direct-doc response thresholds | **KEY FIX**: Heading-level aware parser — only stop at same/higher level, preserving #### subsections (fixes ADR.0025 cutoff). Add `consequences_max_chars: 4000`, `direct_doc_max_chars: 12000`. Return `full_text` in direct-doc responses. **12 acceptance tests.** | Parsing |
| 197 | Feb 9 23:36 | `5c77b45` | Fix consequences regex in loader to match ### headings and skip #### subsections | `ADR_CONSEQUENCES_PATTERN` only matched 1-2 `#` levels but 10/13 ADRs use `###`. Updated to `#{2,4}` with lookahead stopping at `##` or `###` but not `####`. | Parsing |
| 198 | Feb 9 23:39 | `86acef5` | Add regression tests for markdown loader consequences extraction | 16 tests: `###` heading with `####` subsections, `##` level, heading variants, boundary checks, real ADR.0025 integration. | Testing |
| 199 | Feb 9 23:40 | `01e82a1` | Add repo_data marker and negative control assertions to consequences tests | `@pytest.mark.repo_data`, register marker, negative controls asserting no unrelated section content leaks. | Testing |
| 200 | Feb 9 23:50 | `e3a1721` | Expand regression tests: ADR.0028, PCP.0010, heading-level boundaries | ADR.0028 (## Consequences with Pros/Cons), PCP.0010, parametrized heading-level boundary tests (5 cases), negative controls. **+164 lines.** | Testing |

---

## Phase 10: Portability & Test Runner v3 (Feb 10)

*Externalize config to YAML, gold standard v3.0, doc ID tracking.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 201 | Feb 10 08:34 | `20d0d68` | Add PCP.0011 repo-data test and end-to-end ADR.0025 regression guard | PCP.0011: nested sub-bullets (RBAC, ABAC). E2E: ADR.0025 → parse_adr_content → ContentRecord → build_content_response, asserting Governance/Transparency/Testing/MFFBAS (the truncation bug symptom). | Testing |
| 202 | Feb 10 08:38 | `87735bf` | Add DAR table extraction tests and DAR vs non-DAR smoke test | 11 tests: ADR.0025D (multi-section DAR with reverse-numbered headers, whitespace, HTML comments), ADR.0031D (headerless section), DAR vs non-DAR smoke test. | Testing |
| 203 | Feb 10 11:24 | `d219dc5` | Portability refactoring: externalize hardcoded logic to config | **KEY FEATURE**: Two-layer YAML config (`config/taxonomy.default.yaml` + ESA override). Phase 0: foundation (deep-merge, @lru_cache, modes). Phase 1: collection names → `get_collection_name()`. Phase 2: doc type → `resolve_legacy_doc_type()`. Phase 3: routing patterns → config-loaded. Phase 4: identity patterns → config-loaded. **All 423 tests pass, +874/−246, 22 files.** | Config |
| 204 | Feb 10 11:48 | `d46746d` | Gold standard test questions v3.0: route expectations and fullness tests | Expected route + allowed doc_types per question. IDs standardized to ADR.XXXX/PCP.XXXX. 3 fullness regression tests (F1-F3). Route OK? and Doc IDs OK? columns. Failure triage section. | Testing |
| 205 | Feb 10 12:11 | `06fb9db` | Refine gold standard v3.0: fullness grading and doc ID matching | F-tests accept "answer OR full_text > X chars". Doc ID variant acceptance (ADR.0025 = ADR.25). | Testing |
| 206 | Feb 10 12:20 | `de52bc1` | Test runner v3.0: route tracking, doc ID tracking, fullness tests | `RouteCapture` log handler infers actual route. Doc ID extraction with canonical normalization. Fullness regression tests (F1/F2/F3). Failure triage: routing vs retrieval vs formatter bugs. First run: 48% pass, 88% route accuracy, 64% doc IDs. **+1488 lines.** | Testing |
| 207 | Feb 10 15:02 | `b7981a4` | Fix SKILL.md description to single-line YAML format | YAML formatting fix. | Skills |
| 208 | Feb 10 17:35 | `d049407` | P0-P1 field feedback fixes: formatter fallback, PCP30 filter, meta route | **P0**: All strict-mode failure paths degrade to raw text (never "unable to format"). **PCP30 fix**: approval_extractor uses `principle_approval` for principle DARs. **P1**: New `src/meta_route.py` short-circuits questions about AInstein. Gold standard v4.0 (+11 questions, 3 categories). **26 new tests, +484 lines.** | Routing |
| 209 | Feb 10 17:58 | `3cb755a` | Add raw fallback sanitizer and session regression test framework | Sanitize raw text: strip JSON delimiters, schema fields, fenced code blocks. YAML-based regression test runner with scripted sessions from field feedback. **+651 lines.** | Response |
| 210 | Feb 10 21:52 | `9aa750b` | Wire --model flag through to Elysia Tree config (replace=True) | **KEY FIX**: Elysia's `smart_setup()` hardcodes gpt-4.1-mini when OPENAI_API_KEY detected, ignoring `--model`. Add `configure_elysia_from_settings()` with `elysia.config.configure(replace=True)`. Called at all composition roots. **+273 lines.** | Config |
| 211 | Feb 10 22:00 | `36de936` | Harden Elysia config: fail-fast in prod, signature-based idempotency | RuntimeError in prod/staging if `configure_elysia_from_settings()` not called. Idempotency guard: same config = no-op, different config = RuntimeError. **12 wiring tests.** | Config |

---

## Phase 11: Routing Hardening & Identity (Feb 11 – Feb 12)

*List routing fixes, follow-up binding, scope gating, AInstein identity, compare route, definitional route.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 212 | Feb 11 09:40 | `af40667` | Quality fixes: doc IDs, routing, grounding gate, multi-hop, UI streaming | BatchApproval doc ID D-suffix. Routing: decision/reasoning queries not stolen by vocab route. Grounding gate: reject when Tree retrieves zero docs. Multi-hop cross-domain retrieval. Semantic response cache (5min TTL, 100 entries). UI: complete event always shows final response. **491 tests, +3864 lines.** | Routing |
| 213 | Feb 11 09:59 | `5d519eb` | Fix template misclassification: numbered files (NNNN-*.md) are always content | ADR.0000 and ADR.0001 classified as 'template' because content mentions "template". Add filename identity rule: `^\d{4}-.*` = authoritative content, skip template heuristics. **+278 lines.** | Ingestion |
| 214 | Feb 11 10:10 | `389e648` | Fix duplicate response in UI: replace assistant panel on complete event | When complete event fires and assistant panel already exists, replace content instead of appending a second panel. | UI |
| 215 | Feb 11 11:22 | `a9e8f76` | Clean up test results: remove old v1/v2, keep v3 gold standard runs | Remove pre-v3 test results and superseded runs. Add latest v3 results for gpt-oss:20b, gpt-5.2, gpt-5-mini. | Cleanup |
| 216 | Feb 11 11:43 | `638af17` | Fix DAR listing + deterministic short-circuit + PolicyDocument guard | DAR keywords ("dar"/"dars") added to list route. Catalog queries skip `should_abstain()`. PolicyDocument graceful fallback when `doc_type` missing. Unmatched list queries default to ADRs. **+122 lines.** | Routing |
| 217 | Feb 11 11:51 | `8edef4f` | Add follow-up binding: 'list them' resolves to last mentioned subject | Per-conversation subject tracking. "list them"/"show those" resolves to last doc type (DARs, ADRs, principles, policies). **+219 lines.** | Follow-up |
| 218 | Feb 11 11:57 | `8aedf63` | Fix list transparency labels: use collection-specific names | `generate_transparency_message()` prefers pre-set statement ("Showing all 42 ADRs") over generic ("Showing all 42 items"). **+145 lines.** | Routing |
| 219 | Feb 11 15:53 | `c875485` | Harden list routing: word-boundary regex, clarification for ambiguous lists | Replace silent ADR catch-all with clarification prompt. Word-boundary regex (`\b`) for subject detection and DAR keywords (prevents "adr" matching "quadratic"). | Routing |
| 220 | Feb 11 20:05 | `ece0fe8` | Fix SSE stream abort for long-running Tree queries + DAR list formatting | Non-blocking `get_nowait()` + `asyncio.sleep()` (was blocking Queue.get). Try/except wraps entire `stream_elysia_response`. Async polling (not blocking `thread.join`). DAR label fix ("DAR" not "APPROVAL_RECORDS"). Frontend: buffer partial SSE lines, response.ok check. **+251 lines.** | Async |
| 221 | Feb 11 22:52 | `26189ab` | Fix plural ADR routing, code review hardening, blue assistant theme | `\badr\b → \badrs?\b` so "What ADRs exist?" routes to list. Stop leaking internal error details. Copy rows in DAR finalization. Assistant panel blue (was green) for contrast. | Routing |
| 222 | Feb 11 23:36 | `7cf9f01` | AInstein identity layer + DAR topical-marker routing fix | **KEY FEATURE**: 3-tier disclosure levels (L0 functional, L1 RAG detail, L2 debug). Identity detection in meta route. Response gateway scrubber (Elysia→AInstein, Weaviate→KB). Tighten SKILL.md identity rules. CLI: "Elysia>" → "AInstein>", "Elysia thinking..." → "Thinking...". **DAR fix**: collection keywords before `is_list_query()` gate. **24+15 new tests, +455 lines.** | Identity |
| 223 | Feb 12 08:31 | `bbb47fa` | Fix DAR listing regressions, add scope gating, extend follow-up resolution | **PR 1**: Skip doc_type filter for Policy/Vocabulary (no property). **PR 2**: `list_all_policies()` tool, Policy in deterministic list path, `_direct_query()` safety net. **PR 3**: Approval follow-ups, continuation phrases, LRU state cap (1000). **PR 4**: `_has_esa_cues()` prevents non-ESA queries entering pipeline. CamelCase CIM detection (12+ chars). **721 tests, +909 lines.** | Routing |
| 224 | Feb 12 08:37 | `62c6a84` | Add conceptual compare route + harden list detector precision | **PR X**: `is_conceptual_compare_query()` requires compare verb + 2+ doc-type keywords. `build_conceptual_compare_response()` returns type definitions. **PR Y**: List-intent guard (`_LIST_INTENT_RE`) requires explicit list verbs alongside doc-type keyword. **773 tests, +335 lines.** | Routing |
| 225 | Feb 12 10:07 | `ccecd4f` | Fix 'What is a DAR?' misrouted to list: add definitional doc-type route | `is_definitional_doc_type_query()` for "What is a/an X?" patterns. `build_definitional_response()` with type definition + offer to list. Gate bare DAR regex with `has_list_intent`. Add "provide" to `_LIST_INTENT_RE`. **809 tests, +190 lines.** | Routing |

---

## Phase 12: Intent-First Routing & LLM-Only Path (Feb 12 – Feb 13)

*Feature-flagged intent router, strict mode removal (P4), LLM-generated clarification (P5), ESA ontology skill.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 226 | Feb 12 09:46 | `8c839fb` | Intent-first routing, strict mode feature flags, and chunking accuracy experiment | **KEY FEATURE**: `IntentDecision` schema with heuristic + LLM classifier in `intent_router.py`. Rollback map (`docs/dev/rollback_map.md`). Runtime routing policy (`config/routing_policy.yaml`) with strict_mode, tree_enabled, etc. Chunking accuracy experiment scripts. **+89 tests.** | Routing |
| 227 | Feb 12 10:35 | `e879950` | Wire routing policy flags into actual routing logic + hierarchical settings UI | All routing_policy flags now actually control behavior (were loaded but never checked). GET/POST `/api/settings/routing` endpoints. Hierarchical settings UI with Routing tab (Strict/LLM mode cards, parent-child toggles). | Routing |
| 228 | Feb 12 14:12 | `23f0ddd` | Add chronological commit map with detailed descriptions for all 225 commits | `docs/dev/chronological_commit_map.md` with 11 phases, activity heatmap, revert impact guide. **+526 lines.** | Docs |
| 229 | Feb 12 16:36 | `b8beaf6` | Merge branch 'claude/smarter-solution-build-b66WY' | Merge commit. | Merge |
| 230 | Feb 12 15:37 | `e29d33b` | Fix routing settings UI not visible: cache headers + JS fixes | Cache-Control headers for index.html, fix `switchSettingsTab()` implicit event bug, add `.toggle-group.disabled` CSS. | Bugfix |
| 231 | Feb 12 15:50 | `97b3f91` | Add standalone /routing page for routing settings | Self-contained `/routing` page with cache prevention, hierarchical UI, sidebar button. **+657 lines.** | UI |
| 232 | Feb 12 17:04 | `3754efc` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 233 | Feb 13 11:45 | `a7d3396` | Fix reindex_full_docs.py: pass base_path to MarkdownLoader | One-line fix for MarkdownLoader API change. | Bugfix |
| 234 | Feb 13 12:45 | `72d8bed` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 235 | Feb 13 12:00 | `f76a1d9` | Fix 3 bugs in chunking experiment that skewed results | Wrong expected_doc_id for OAuth query, empty doc_id for principles in full-doc collection, tie-handling bias in conclusion. | Bugfix |
| 236 | Feb 13 13:02 | `3871405` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 237 | Feb 13 12:41 | `0420579` | Fix invalid test expectations and add experiment report | Fix 2 wrong expected doc IDs. Both strategies 5/5 (100%). Report recommends full-doc embedding for this corpus size. `docs/experiments/chunking_vs_full.md`. | Testing |
| 238 | Feb 13 13:58 | `768fc45` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 239 | Feb 13 14:30 | `ff78936` | Add comprehensive ESA document ontology analysis | Deep analysis of document ecosystem (ADRs, PCPs, DARs), naming conventions, overlapping numbering, frontmatter inconsistencies. 8-action restructuring plan. **+625 lines.** | Docs |
| 240 | Feb 13 15:53 | `f9b65f4` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 241 | Feb 13 15:55 | `f84dbad` | Rewrite Part 3: trust the LLM, enrich the data, delete the regex | Replace over-engineered restructuring plan with simpler philosophy: domain skill for LLM, enriched Weaviate metadata, delete duplicate patterns, ask clarifying questions. | Docs |
| 242 | Feb 13 15:58 | `03a9d94` | Add ESA document ontology skill (P1) | **KEY FEATURE**: `skills/esa-document-ontology/SKILL.md` — domain knowledge for ADRs/PCPs/DARs: numbering, overlapping ranges, disambiguation rules, frontmatter schemas. `auto_activate: true`. **+189 lines.** | Skills |
| 243 | Feb 13 17:00 | `1f56346` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 244 | Feb 13 16:04 | `c1af5c6` | Fix two factual issues in ontology skill | canonical_id doesn't exist in Weaviate yet (P2 deliverable). Added legacy doc_type "content" note. | Skills |
| 245 | Feb 13 17:05 | `6295b56` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 246 | Feb 13 16:13 | `ab5b771` | Add enriched metadata fields to ingestion pipeline (P2) | **KEY FEATURE**: `canonical_id`, `status`, `date`, `doc_uuid`, `dar_path` in Weaviate. Populated from frontmatter/filename in chunked and non-chunked paths. **+199 lines, 5 files.** | Ingestion |
| 247 | Feb 13 17:15 | `996bcf9` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 248 | Feb 13 16:22 | `44d40d8` | Use direct attribute access for P2 fields in chunk converters | Replace unnecessary getattr fallbacks with direct access on ChunkMetadata. | Quality |
| 249 | Feb 13 17:24 | `0438afa` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 250 | Feb 13 17:43 | `a6c299e` | P3: Delete duplicate classifiers from markdown_loader, wire to doc_type_classifier | Remove `_classify_adr_document` and `_classify_principle_document` (~130 lines) from MarkdownLoader. All 6 call sites use canonical `doc_type_classifier.py`. Extract `_clean_frontmatter_status()` helper. **−125 net lines.** | Quality |
| 251 | Feb 13 18:45 | `b1d89d4` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 252 | Feb 13 17:53 | `bf0357f` | Add TODO for PRINCIPLE_APPROVAL type on is_dar checks | Note that is_dar checks use ADR_APPROVAL for both ADR and PCP DARs. | Docs |
| 253 | Feb 13 18:54 | `8593561` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 254 | Feb 13 18:00 | `4bc773f` | Note missing P2 fields in OpenAI collection schemas | OpenAI ADR/Principle variants lack P2 fields. | Docs |
| 255 | Feb 13 19:12 | `ad4020d` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 256 | Feb 13 18:25 | `0d04124` | Drop legacy 'decision_approval_record' dual checks post re-index | Remove all backward-compat OR filters for legacy string. Simplify 5 filter locations across `approval_extractor.py`, `elysia_agents.py`, `filters.py`. **−23 net lines.** | Cleanup |
| 257 | Feb 13 18:26 | `b446e41` | Update SKILL.md legacy note (resolved) and TODO for dar_path portability | Legacy "content" doc_type no longer exists. `dar_path` portability TODO. | Docs |
| 258 | Feb 13 19:29 | `398222e` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 259 | Feb 13 18:40 | `1e9e98a` | Wire PRINCIPLE_APPROVAL through classifier, loader, agents, and filters | **KEY FIX**: Principle DARs were misclassified as "adr_approval". Now `classify_principle_document` returns `PRINCIPLE_APPROVAL`. Updated loader, elysia_agents, filters, tests. Requires re-index. | Taxonomy |
| 260 | Feb 13 19:42 | `418fbe9` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 261 | Feb 13 18:45 | `1dcb2ac` | Fix two review nits: stale TODO + excluded_types() missing PRINCIPLE_APPROVAL | Remove resolved TODO, add PRINCIPLE_APPROVAL to `excluded_types()`. | Bugfix |
| 262 | Feb 13 19:47 | `70e152c` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 263 | Feb 13 18:56 | `971d690` | Fix chunking pipeline silently discarding classified doc_type | `_create_chunk()` in strategies.py always overwrote doc_type with hardcoded default. Now respects classified value from metadata. | Bugfix |
| 264 | Feb 13 19:57 | `acbda87` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 265 | Feb 13 19:38 | `4c9be3d` | P4: Delete strict-mode routing paths, make LLM path the only flow | **KEY CHANGE**: Remove ALL 10 keyword-triggered deterministic routes (meta, approval, DAR, content, compare, definitional, list, count, terminology, cross-domain). Intent router + Elysia Tree is now the single path. **−600 lines from elysia_agents.py.** | Routing |
| 266 | Feb 13 19:55 | `9fe7f6d` | P4 followup: Delete remaining dead code | Remove `is_count_query()`, `_multi_hop_query()`, `approval_extractor.py` (1024 lines), and 3 test files. **−2,664 lines.** 680 tests pass. | Cleanup |
| 267 | Feb 13 21:26 | `23ab31e` | P5: Clean routing UI, LLM-generated clarification, threshold 0.55 | **KEY FEATURE**: Remove dead Strict/LLM mode selector from UI. `build_clarification_response()` now async — calls LLM for contextual clarifying questions (fallback to static). Confidence threshold 0.55. **−360 lines of dead UI.** | Routing |
| 268 | Feb 13 22:38 | `2ed1228` | Clean routing_policy.yaml: remove dead keys, set P5 threshold | Remove strict_mode_enabled, catalog_short_circuit, list_route_requires_list_intent. **−74 lines.** | Config |
| 269 | Feb 13 22:43 | `2cd66c1` | Merge remote P4/P5 commits, resolve routing_policy.yaml conflict | Merge commit. | Merge |
| 270 | Feb 13 21:50 | `e3c1d71` | Update routing_policy.yaml defaults to match live config | intent_router_enabled: true, intent_router_mode: llm, abstain_gate_enabled: false. | Config |

---

## Phase 13: Adversarial Testing & Measurement (Feb 14 – Feb 15)

*Adversarial stress tests, test suite v4.0, architecture analysis, measurement-first trace.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 271 | Feb 14 11:43 | `f3065b2` | Post-P6 fixes: empty response bug, dead meta code, OpenAI enablement | Reject empty answer strings, delete `is_meta_query()` and `_META_PATTERNS`, fix default model gpt-5.2→gpt-4o-mini, add P2 fields to OpenAI schemas, fix OpenAI query embedding. **−125 net lines.** 635 tests. | Bugfix |
| 272 | Feb 14 12:49 | `abf5287` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 273 | Feb 14 12:02 | `cd4fe55` | Review fixes: OpenAI HNSW config + routing policy fallback tests | Add HNSW + cosine to OpenAI collection schemas. Test hardcoded defaults when YAML absent. 640 tests. | Testing |
| 274 | Feb 14 13:03 | `2e72373` | Merge branch 'claude/codebase-review-Tdz8o' | Merge commit. | Merge |
| 275 | Feb 14 13:32 | `9e466a8` | Add adversarial stress test suite v1.0 + fix OpenAI model to gpt-5.2 | **KEY FEATURE**: 20 adversarial questions across 6 categories (Identity, OffTopic, PromptInjection, HallucinationBait, Vague, Boundary). `check_deflection()` scoring. `--adversarial` CLI flag. **+244 lines.** | Testing |
| 276 | Feb 14 13:57 | `e0bfab9` | Add full config traceability to test reports | Record chat_model, embedding_model, routing policy in JSON reports and console output. Model names in filenames. | Testing |
| 277 | Feb 14 14:41 | `493f4d6` | Replace old untraceable test reports with adversarial stress v1.0 results | Delete 7 old reports. Add 3 new adversarial v1.0 reports: gpt-5.2 85%, gpt-5-mini 85%, gpt-oss:20b 50%. | Testing |
| 278 | Feb 14 14:19 | `e95d0db` | Fix routing bugs: add intent short-circuits for LOOKUP_DOC, APPROVAL, LIST | Add `_handle_lookup_doc`, `_handle_lookup_approval`, `_handle_list` short-circuits. Entity scope hints for Tree. | Routing |
| 279 | Feb 14 20:30 | `c23901d` | Revert "Fix routing bugs: add intent short-circuits" | Revert of e95d0db. **−423 lines.** | Revert |
| 280 | Feb 15 00:58 | `f7e63b2` | Test suite v4.0: add grounded, near-miss, and RAG-adversarial questions | **KEY FEATURE**: Gold Standard v4 (29→44 questions): G1-G10 grounded summarization, R1-R5 near-miss retrieval. Adversarial v2 (20→26): RAG-specific injection, high-numbered nonexistent docs. "Top Failing IDs" table, `--ids` flag. | Testing |
| 281 | Feb 15 09:18 | `a6a45df` | Add diagnosis-by-category and dashboard to test reporting | `_classify_diagnosis()` helper, category × diagnosis cross-tab, 5-metric dashboard. First v4 OpenAI run results. **+5,433 lines.** | Testing |
| 282 | Feb 15 10:41 | `9db5772` | Add architecture analysis: domain comprehension vs. keyword routing | Technical analysis explaining why keyword-routing produces 34.5% accuracy and proposing domain-comprehension skill architecture. **+513 lines.** | Docs |
| 283 | Feb 15 11:34 | `81fd6cf` | Remove outdated Gold Standard v3 architecture analysis | Superseded by v4 analysis. **−513 lines.** | Cleanup |

---

## Phase 14: Trace Infrastructure & Production Fixes (Feb 15)

*Request-scoped QueryTrace, list-mode gating, smoke tests, provider fixes, frontmatter restructure.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 284 | Feb 15 16:02 | `2f9298a` | Implement measurement-first trace + list-mode gating (P1-P7) | **KEY FEATURE**: `QueryTrace` with `TraceStore` (bounded, TTL eviction). Gate deterministic list finalization to explicit list intent. Intent-aware retrieval filters. SKILL.md v2 with domain ontology. CI invariant tests + daily smoke suite. **+1,172 lines.** 751 tests. | Observability |
| 285 | Feb 15 16:11 | `ac59985` | Fix pytest collection errors: add pythonpath to pytest config | `pythonpath = ["."]` in pyproject.toml for `from src.` imports. | Testing |
| 286 | Feb 15 15:14 | `4cf6741` | Add RAG accuracy review comparing AInstein to blog post principles | Review against "4 approaches to cut RAG hallucinations" framework. Documents strengths (filtering, clarification) and gaps (query decomposition). **+127 lines.** | Docs |
| 287 | Feb 15 16:20 | `59108c1` | Rename TestResult/TestSuite to CheckResult/CheckSuite to fix pytest warnings | Avoid PytestCollectionWarning on dataclass names matching test discovery. | Testing |
| 288 | Feb 15 17:53 | `81b4011` | Fix smoke test failures: invariant C, tree trace coverage, list stabilization | Fix invariant C for legitimate list timeouts. Extract tool calls from Elysia tree's `tasks_completed`. Bump recursion_limit for list queries. Deterministic list intercept. | Testing |
| 289 | Feb 15 18:27 | `193373e` | Fix approval tool taxonomy and OpenAI provider binding | Reclassify `list_approval_records` as `tool_kind="lookup"`. Restore API keys after Elysia `configure(replace=True)` which wipes `API_KEYS={}`. | Bugfix |
| 290 | Feb 15 18:49 | `0db588a` | Fix OpenAI provider: guard against Elysia's load_dotenv(override=True) | **ROOT CAUSE**: Elysia's `config.py` runs `load_dotenv(override=True)` at import, clobbering `LLM_PROVIDER`. Save/restore critical env vars around import. Provider assertion gate in smoke fixture. | Bugfix |
| 291 | Feb 15 20:46 | `4329191` | Restructure esa-main-artifacts frontmatter to dct:/owl: metadata format | Convert frontmatter across all ESA decision and principle files to Dublin Core (`dct:`) and OWL (`owl:`) metadata format. **26 files.** | Data |
| 292 | Feb 15 20:46 | `205b935` | Fix smoke test teardown: suppress Rich Live, add thread cleanup guarantee | Set Elysia `LOGGING_LEVEL_INT=30` to prevent Rich spinner threads. Per-test thread cleanup fixture. | Testing |
| 293 | Feb 15 21:03 | `8f90402` | Add --include-document-chunks CLI flag for hybrid chunking mode | Threads `--include-document-chunks` through CLI → ingestion → loader to set `ChunkingConfig(index_document_level=True)`. | Ingestion |
| 294 | Feb 15 21:39 | `aa527f0` | Fix old agent query path for Ollama collections (vectorizer=none) | Add `_needs_client_side_embedding()` and `_embed_query()` to `BaseAgent`. Wire into all 5 Weaviate search call sites across base, architecture, and policy agents. | Embedding |

---

## Phase 15: ArchitectureAgent Scoring Gate (Feb 16)

*Scoring gate refactor, dead code cleanup, topic qualifier precision.*

| # | Timestamp | Commit | Message | Description | Area |
|---|-----------|--------|---------|-------------|------|
| 295 | Feb 16 10:50 | `33478db` | Refactor ArchitectureAgent routing to scoring gate architecture | **KEY FEATURE**: Replace if-else routing with `_extract_signals()` → `_score_intents()` → `_select_winner()`. `RoutingSignals` dataclass (6 boolean features). Weighted intent scoring with thresholds + margin gating. `RouteTrace` with signals/scores/winner. Defense-in-depth post-filter on `canonical_id` lookups. Orchestrator doc-ref routing hint (B1). 15-probe smoke script. **+2,270 lines, 96 tests.** | Routing |
| 296 | Feb 16 11:10 | `fa2e0d5` | Remove dead code: AGENT_CONFIDENCE_THRESHOLD and unused Intent import | Superseded by `_INTENT_THRESHOLDS` and `_SCORE_MARGIN`. `Intent` import no longer used. **−23 lines.** | Cleanup |
| 297 | Feb 16 11:43 | `1cee76f` | Remove high-entropy "on "/"for " from topic qualifier markers | Remove short prepositions prone to incidental matches. Keep high-precision: about, regarding, related to, with respect to, in terms of, concerning. | Routing |

---

## Statistics

| Metric | Count |
|--------|-------|
| Total commits | 297 |
| Merge commits | 41 |
| Substantive commits | 256 |
| Date range | Jan 31 11:24 – Feb 16 11:43 (16 days, 24h 19m) |
| Phases | 15 |

### Commits by area

| Area | Count |
|------|-------|
| Routing / Retrieval | 39 |
| Skills / Skills UI | 27 |
| Testing | 36 |
| LLM / Embedding | 19 |
| UI | 14 |
| Docs | 30 |
| Bugfix | 27 |
| Config | 15 |
| Ingestion / Parsing | 14 |
| Response / Gateway | 10 |
| Merge | 41 |
| Other (Identity, Async, Taxonomy, Cleanup, Quality, etc.) | 25 |

### Key milestones

| Timestamp | Commit | Milestone |
|-----------|--------|-----------|
| Jan 31 11:24 | `e5f6000` | First commit — dual-stack LLM |
| Feb 3 10:00 | `da780c3` | Confidence-based abstention |
| Feb 4 09:45 | `8149406` | Skills Framework implemented |
| Feb 6 21:58 | `d1f13da` | Skills-based DAR filtering |
| Feb 7 11:42 | `c1717db` | Transparency-first retrieval |
| Feb 8 20:46 | `03deb3a` | Response gateway module |
| Feb 8 22:38 | `130935f` | Server-side doc_type filtering |
| Feb 9 11:34 | `f2ed835` | Phase 4 compliance |
| Feb 9 13:59 | `f9aea62` | SKOSMOS local-first (Phase 5) |
| Feb 10 11:24 | `d219dc5` | Portability refactoring |
| Feb 11 23:36 | `7cf9f01` | AInstein identity layer |
| Feb 12 10:07 | `ccecd4f` | Definitional doc-type route |
| Feb 12 09:46 | `8c839fb` | Intent-first routing + feature flags |
| Feb 13 15:58 | `03a9d94` | ESA document ontology skill (P1) |
| Feb 13 16:13 | `ab5b771` | Enriched metadata fields (P2) |
| Feb 13 19:38 | `4c9be3d` | Delete strict-mode, LLM-only path (P4) |
| Feb 13 21:26 | `23ab31e` | LLM-generated clarification (P5) |
| Feb 15 00:58 | `f7e63b2` | Test suite v4.0 (44+26 questions) |
| Feb 15 16:02 | `2f9298a` | Measurement-first trace (QueryTrace) |
| Feb 16 10:50 | `33478db` | ArchitectureAgent scoring gate (HEAD) |

### Activity heatmap

| Date | Commits | Time span | Busiest hour |
|------|---------|-----------|--------------|
| Jan 31 | 6 | 11:24 – 23:07 | 22:00 |
| Feb 1 | 4 | 11:38 – 12:10 | 11:00 |
| Feb 2 | 30 | 08:53 – 23:09 | 21:00 – 23:00 |
| Feb 3 | 17 | 07:53 – 21:53 | 11:00 – 12:00 |
| Feb 4 | 51 | 08:40 – 23:54 | 22:00 – 23:00 |
| Feb 5 | 8 | 00:10 – 11:49 | 07:00 – 08:00 |
| Feb 6 | 15 | 15:19 – 23:09 | 21:00 – 22:00 |
| Feb 7 | 20 | 10:32 – 23:26 | 22:00 – 23:00 |
| Feb 8 | 31 | 00:02 – 23:09 | 20:00 – 22:00 |
| Feb 9 | 24 | 11:34 – 23:50 | 17:00 – 18:00 |
| Feb 10 | 11 | 08:34 – 22:00 | 11:00 – 12:00 |
| Feb 11 | 11 | 09:40 – 23:36 | 11:00 – 12:00 |
| Feb 12 | 8 | 08:31 – 17:04 | 09:00 – 10:00 |
| Feb 13 | 33 | 11:45 – 22:43 | 17:00 – 20:00 |
| Feb 14 | 10 | 11:43 – 20:30 | 13:00 – 15:00 |
| Feb 15 | 17 | 00:58 – 21:39 | 16:00 – 19:00 |
| Feb 16 | 3 | 10:50 – 11:43 | 10:00 – 12:00 |

---

## Revert Impact Guide

> **Use this section to evaluate what you'd lose when reverting to a specific commit.**

### Revert to end of Phase 3 (commit 53, `ae7d6ae`, Feb 3)

**You LOSE:**
- Skills Framework (entire `skills/` directory, `src/skills/`, Skills UI with 5 phases)
- Skills-based DAR filtering (query-aware include/exclude)
- Transparency-first retrieval with collection counts
- Response gateway (`src/response_gateway.py`) and structured JSON responses
- LLM client abstraction (`src/llm_client.py`)
- Doc_type taxonomy, migration script, server-side filtering
- Deterministic list/count/approval routing
- SKOSMOS local-first terminology verification (8,000+ terms)
- Approval extraction (`src/approval_extractor.py`)
- Specific document retrieval (content vs DAR disambiguation)
- Portability config (`config/taxonomy.default.yaml`)
- AInstein identity layer (disclosure levels, scrubber, CLI branding)
- Follow-up binding ("list them" → last mentioned subject)
- Scope gating (non-ESA query rejection)
- Compare and definitional routes
- Meta route (short-circuit questions about AInstein)
- uvloop fix (query times remain ~42s instead of ~3-8s)
- ~770 tests

**You KEEP:**
- Dual-stack LLM (Ollama + OpenAI) with Test Mode comparison
- Basic RAG retrieval with metadata filters
- Client-side embeddings workaround for Weaviate
- Evaluation framework and gold standard test questions (v2)
- Confidence-based abstention (hallucination prevention)
- ADR/principle number extraction from filenames
- Chunking module (`src/chunking/`)
- ESA data artifacts (ADRs, principles, vocabularies)
- DAR/Principle distinction (NNNND-*.md classification)
- Heartbeat indicator, timing metrics, basic UI formatting
- Health endpoint, Ollama error handling
- GPT-5.x and Qwen3 model support

### Revert to end of Phase 5 (commit 139, `0255de2`, Feb 7)

**You LOSE:**
- Structured JSON response schema and response gateway
- LLM client abstraction (ElysiaClient, DirectLLMClient, ResilientLLMClient)
- Retry logic and strict/soft enforcement
- Doc_type taxonomy with canonical classifier and migration script
- Server-side doc_type filtering (allow-list approach)
- Deterministic list serialization (`list_response_builder.py`)
- SKOSMOS local-first terminology verification
- Deterministic approval extraction
- Specific document content retrieval (content vs DAR)
- Section parser fixes (heading-level awareness)
- Portability config (taxonomy.default.yaml)
- AInstein identity layer, follow-up binding, scope gating
- Compare and definitional routes
- Meta route, gold standard v3.0+, test runner v3.0
- Elysia model wiring (`configure_elysia_from_settings()`)
- ~400 tests

**You KEEP:**
- Everything in Phase 1-3 PLUS:
- Skills Framework (full: loader, registry, thresholds.yaml, SKILL.md injection)
- Skills UI (5 phases: dashboard, config modal, rule editor, enable/disable, creation wizard)
- Skills-based DAR filtering with query-aware logic
- Transparency-first retrieval with collection counts
- uvloop fix (3-8s query times)
- Chunked ingestion with `--chunking` flag
- Security: path traversal fixes, XSS prevention
- `count_documents` Elysia tool

### Revert to end of Phase 8 (commit 190, `070c625`, Feb 9)

**You LOSE:**
- Deterministic approval extraction (`approval_extractor.py`)
- Specific document content retrieval (content vs DAR disambiguation)
- Section parser fixes (heading-level aware, consequences regex)
- Portability config (taxonomy.default.yaml, collection names)
- Gold standard v3.0+ and test runner v3.0
- Meta route (short-circuit questions about AInstein)
- Raw fallback sanitizer
- AInstein identity layer (disclosure levels, scrubber, CLI)
- Follow-up binding, scope gating
- Compare and definitional routes
- Elysia model wiring
- DAR routing hardening (word-boundary regex, list intent guard)
- SSE stream abort fix
- ~350 tests

**You KEEP:**
- Everything in Phase 1-5 PLUS:
- Structured JSON response schema (`response_schema.py`)
- Response gateway (`response_gateway.py`)
- LLM client abstraction (`llm_client.py`)
- Retry logic with strict/soft enforcement
- Doc_type taxonomy with classifier and migration script
- Server-side filtering (allow-list approach)
- Deterministic list serialization (`list_response_builder.py`)
- Phase 4 compliance (all 4 gaps addressed)
- SKOSMOS local-first terminology verification
- ESA Document Taxonomy contract
- 3-layer architecture formalization

### Revert to end of Phase 10 (commit 211, `36de936`, Feb 10)

**You LOSE:**
- AInstein identity layer (3-tier disclosure, Elysia→AInstein scrubber, CLI branding)
- Follow-up binding ("list them" → last mentioned subject)
- Scope gating (`_has_esa_cues()`, non-ESA query rejection)
- Conceptual compare route ("difference between ADR and PCP")
- Definitional doc-type route ("What is a DAR?")
- List detector hardening (list-intent guard, word-boundary regex)
- DAR routing fixes (topical markers, plural ADR regex)
- SSE stream abort fix for long Tree queries
- UI duplicate response fix
- Template misclassification fix (NNNN-*.md identity rule)
- Blue assistant theme
- ~100 tests

**You KEEP:**
- Everything in Phase 1-8 PLUS:
- Deterministic approval extraction
- Specific document content retrieval
- Section parser fixes (heading-level awareness)
- Portability config (taxonomy.default.yaml)
- Gold standard v3.0+v4.0, test runner v3.0
- Meta route (short-circuit meta questions)
- Raw fallback sanitizer
- Elysia model wiring (`configure_elysia_from_settings()`)
- Fail-fast prod config, signature-based idempotency

### Revert to end of Phase 11 (commit 225, `ccecd4f`, Feb 12)

**You LOSE:**
- Intent-first routing (`intent_router.py` IntentDecision, heuristic + LLM classifier)
- Routing policy feature flags (`config/routing_policy.yaml`)
- P4 strict-mode deletion (~3,000 lines of deterministic routes removed)
- LLM-generated clarification (P5, async `build_clarification_response()`)
- ESA document ontology skill (domain knowledge for LLM)
- P2 enriched metadata (canonical_id, status, date, doc_uuid, dar_path in Weaviate)
- PRINCIPLE_APPROVAL type wired through classifier/loader/agents/filters
- Adversarial stress test suite (26 questions, 6 categories)
- Test suite v4.0 (44 gold standard + 26 adversarial questions)
- Measurement-first QueryTrace with TraceStore
- ArchitectureAgent scoring gate (signal extraction → weighted scoring → margin gate)
- 15-probe smoke script (`scripts/smoke_probes.py`)
- Routing UI (`/routing` standalone page)
- Dublin Core / OWL frontmatter restructure
- ~140 tests

**You KEEP:**
- Everything in Phase 1-10 PLUS:
- AInstein identity layer
- Follow-up binding, scope gating
- Compare and definitional routes
- List detector hardening
- SSE stream abort fix
- Template misclassification fix

### Revert to end of Phase 13 (commit 283, `81fd6cf`, Feb 15)

**You LOSE:**
- Measurement-first QueryTrace with TraceStore (P1-P7)
- List-mode gating (deterministic list finalization gated to explicit list intent)
- Intent-aware retrieval filters
- SKILL.md v2 with domain ontology
- CI invariant tests + daily smoke suite
- Fix for Elysia's `load_dotenv(override=True)` clobbering `LLM_PROVIDER`
- Dublin Core / OWL frontmatter restructure
- `--include-document-chunks` CLI flag
- Client-side embedding fixes for old agent path (Ollama)
- ArchitectureAgent scoring gate
- ~50 tests

**You KEEP:**
- Everything in Phase 1-11 PLUS:
- Intent-first routing with feature flags
- P4 strict-mode deletion (LLM-only path)
- LLM-generated clarification (P5)
- ESA document ontology skill
- P2 enriched metadata fields
- PRINCIPLE_APPROVAL wired through
- Adversarial stress test suite v1.0
- Test suite v4.0 (44+26 questions)
- Routing UI and policy YAML
