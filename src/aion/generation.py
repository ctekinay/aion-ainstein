"""Direct LLM pipeline for generation tasks.

Bypasses the Elysia Tree for tasks that need content generation
(ArchiMate XML, etc.) rather than retrieval + summarization. The
pipeline fetches source content from Weaviate, builds a prompt from
skill instructions, makes a single LLM call, validates, saves the
artifact, and returns.
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from queue import Queue
from typing import Optional

from weaviate import WeaviateClient
from weaviate.classes.query import Filter, MetadataQuery

from src.aion.config import settings
from src.aion.skills.loader import SkillLoader
from src.aion.skills.registry import get_skill_registry
from src.aion.tools.archimate import (
    LAYER_MAP,
    NS,
    TAG,
    XSI,
    validate_archimate as _validate_archimate,
)
from src.aion.tools.yaml_to_xml import yaml_to_archimate_xml
from src.aion.weaviate.embeddings import embed_text

logger = logging.getLogger(__name__)

ET.register_namespace("", NS)
ET.register_namespace("xsi", XSI)

# Validation tool dispatch — maps registry validation_tool names to callables.
# New generation skills register their validator here.
_VALIDATION_TOOLS = {
    "validate_archimate": _validate_archimate,
}

# Layer → Y coordinate for mechanical view repair layout.
# Mirrors values from skills/archimate-view-generator/references/view-layout.md.
_LAYER_Y = {
    "Motivation": 20, "Strategy": 100, "Business": 180,
    "Application": 260, "Technology": 340, "Physical": 420,
    "Implementation": 500, "Composite": 580,
}


class GenerationPipeline:
    """Direct LLM pipeline for structured content generation."""

    # Fields excluded from full-content fetches (same as ElysiaRAGSystem)
    _EXCLUDED_PROPS = frozenset({"full_text", "content_hash"})

    def __init__(self, client: WeaviateClient):
        self.client = client
        self._collection_cache: dict[str, object] = {}
        self._prop_cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        query: str,
        skill_tags: list[str],
        doc_refs: list[str] | None = None,
        conversation_id: str | None = None,
        event_queue: Queue | None = None,
        intent: str = "generation",
    ) -> tuple[str, list[dict]]:
        """Run the generation pipeline.

        Args:
            query: The user's rewritten query from the Persona.
            skill_tags: Active skill tags (e.g., ["archimate"]).
            doc_refs: Structured document references (e.g., ["ADR.29"]).
            conversation_id: For artifact storage.
            event_queue: Optional Queue for SSE status events.
            intent: "generation" (from scratch) or "refinement" (modify existing).

        Returns:
            Tuple of (response text with embedded content, source objects).
        """
        start = time.perf_counter()
        is_refinement = intent == "refinement"

        # Look up the generation skill from the registry
        registry = get_skill_registry()
        skill_entry = registry.get_generation_skill(skill_tags)
        if not skill_entry:
            return "No generation skill found for the requested tags.", []

        # Step 1: Fetch source content (for generation) or load artifact (for refinement)
        sources = []
        source_text = ""

        yaml_refinement = False
        if is_refinement and conversation_id:
            self._emit(event_queue, "status", "Loading previous artifact...", start)

            # Try YAML companion first (for YAML-pipeline refinement)
            yaml_artifact = self._load_previous_artifact_by_type(
                conversation_id, "text/yaml",
            )
            if yaml_artifact:
                source_text = yaml_artifact["content"]
                yaml_refinement = True
                logger.info(
                    f"[generation] refinement: loaded YAML companion "
                    f"'{yaml_artifact['filename']}' ({len(source_text)} chars)"
                )
            else:
                # Fall back to XML artifact (legacy models)
                artifact = self._load_previous_artifact(conversation_id, skill_entry)
                if artifact:
                    source_text = artifact["content"]
                    logger.info(
                        f"[generation] refinement: loaded artifact "
                        f"'{artifact['filename']}' ({len(source_text)} chars)"
                    )
                else:
                    logger.warning("[generation] refinement: no previous artifact found, "
                                   "falling back to source content fetch")
                    is_refinement = False  # fall back to generation mode

        if not source_text:
            self._emit(event_queue, "status", "Retrieving source content...", start)
            sources, source_text = await self._fetch_content(query, doc_refs)

        if not source_text:
            return (
                "Could not retrieve source content for generation. "
                "Please specify which document to use (e.g., ADR.29)."
            ), []

        logger.info(
            f"[generation] source content: {len(source_text)} chars "
            f"from {len(sources)} sources (refinement={is_refinement})"
        )

        # Step 2: Build prompt — load ONLY the generation skill, not all skills.
        # The "always" skills (identity, QA, ontology, formatter) are designed
        # for the Tree's retrieval path and are irrelevant for direct generation.
        loader = SkillLoader()
        skill = loader.load_skill(skill_entry.name)
        system_prompt = skill.content if skill else ""

        if is_refinement and yaml_refinement:
            user_prompt = (
                f"EXISTING MODEL YAML (do NOT remove or replace existing elements):\n"
                f"{source_text}\n\n"
                f"MODIFICATION REQUEST:\n{query}\n\n"
                f"ADD the requested elements and relationships to the existing model. "
                f"Keep ALL existing elements and relationships intact. "
                f"Return the complete modified YAML. "
                f"Do not include commentary or any other text."
            )
        elif is_refinement:
            user_prompt = (
                f"EXISTING MODEL (do NOT remove or replace existing elements):\n"
                f"{source_text}\n\n"
                f"MODIFICATION REQUEST:\n{query}\n\n"
                f"ADD the requested elements and relationships to the existing model. "
                f"Keep ALL existing elements, relationships, and views intact. "
                f"Return the complete modified model as XML starting with <?xml. "
                f"Do not include tool calls, commentary, or any other text."
            )
        else:
            user_prompt = (
                f"SOURCE CONTENT:\n{source_text}\n\n"
                f"USER REQUEST:\n{query}\n\n"
                f"Generate the YAML following the schema in your instructions. "
                f"Do not include commentary or any other text."
            )

        # Log the full prompt for debugging (refinement vs generation)
        if is_refinement:
            logger.info(
                f"[generation] REFINEMENT prompt built:\n"
                f"  system_prompt: {len(system_prompt)} chars\n"
                f"  existing model: {len(source_text)} chars\n"
                f"  modification request: {query!r}\n"
                f"  user_prompt total: {len(user_prompt)} chars\n"
                f"  est_tokens: ~{(len(system_prompt) + len(user_prompt)) // 4}"
            )
        else:
            logger.info(
                f"[generation] GENERATION prompt built:\n"
                f"  system_prompt: {len(system_prompt)} chars\n"
                f"  source content: {len(source_text)} chars from {len(sources)} sources\n"
                f"  user request: {query!r}\n"
                f"  user_prompt total: {len(user_prompt)} chars\n"
                f"  est_tokens: ~{(len(system_prompt) + len(user_prompt)) // 4}"
            )

        # Step 3: LLM call
        self._emit(event_queue, "status", "Generating...", start)
        raw_output, llm_stats = await self._call_llm(system_prompt, user_prompt)
        total_tokens = {
            "prompt_tokens": llm_stats["prompt_tokens"],
            "completion_tokens": llm_stats["completion_tokens"],
        }

        if not raw_output:
            return "The model did not produce output. Try a cloud model for generation tasks.", []

        # Step 3b: YAML → XML conversion (archimate-generator uses YAML pipeline)
        yaml_source = None
        pipeline_info = {
            "pipeline": "xml",
            "yaml_detected": False,
            "yaml_valid_first_attempt": None,
            "yaml_retry_triggered": False,
            "yaml_retry_succeeded": None,
            "yaml_fallback_to_xml": False,
            "convert_ms": None,
        }
        if skill_entry.name == "archimate-generator":
            yaml_text = self._extract_yaml(raw_output)
            if yaml_text:
                pipeline_info["yaml_detected"] = True
                convert_start = time.perf_counter()
                try:
                    raw_output, _info = yaml_to_archimate_xml(yaml_text)
                    pipeline_info["convert_ms"] = int(
                        (time.perf_counter() - convert_start) * 1000
                    )
                    pipeline_info["pipeline"] = "yaml"
                    pipeline_info["yaml_valid_first_attempt"] = True
                    yaml_source = yaml_text
                except ValueError as e:
                    pipeline_info["yaml_valid_first_attempt"] = False
                    pipeline_info["yaml_retry_triggered"] = True
                    # Log failing YAML for prompt debugging
                    logger.warning(
                        f"[generation] YAML conversion failed: {e}\n"
                        f"[generation] Failing YAML (first 500 chars): "
                        f"{yaml_text[:500]}"
                    )
                    self._emit(event_queue, "status", "Fixing YAML errors...", start)
                    retry_prompt = (
                        f"{user_prompt}\n\n"
                        f"YOUR PREVIOUS YAML HAD ERRORS:\n{e}\n\n"
                        f"Fix the errors and generate corrected YAML."
                    )
                    retry_output, retry_stats = await self._call_llm(
                        system_prompt, retry_prompt,
                    )
                    total_tokens["prompt_tokens"] += retry_stats["prompt_tokens"]
                    total_tokens["completion_tokens"] += retry_stats["completion_tokens"]
                    yaml_text = self._extract_yaml(retry_output)
                    if yaml_text:
                        convert_start = time.perf_counter()
                        try:
                            raw_output, _info = yaml_to_archimate_xml(yaml_text)
                            pipeline_info["convert_ms"] = int(
                                (time.perf_counter() - convert_start) * 1000
                            )
                            pipeline_info["pipeline"] = "yaml"
                            pipeline_info["yaml_retry_succeeded"] = True
                            yaml_source = yaml_text
                        except ValueError as e2:
                            pipeline_info["yaml_retry_succeeded"] = False
                            return f"YAML conversion failed after retry: {e2}", []
                    else:
                        pipeline_info["yaml_retry_succeeded"] = False
                        return "The model did not produce valid YAML on retry.", []
            else:
                pipeline_info["yaml_fallback_to_xml"] = True
                logger.warning(
                    "[generation] No YAML in output, falling back to XML path"
                )

        # Step 4: Validate (if the skill declares a validation tool)
        validation_result = None
        if skill_entry.validation_tool:
            validator = _VALIDATION_TOOLS.get(skill_entry.validation_tool)
            if validator:
                raw_output, validation_result = await self._validate_with_retry(
                    raw_output, validator, system_prompt, user_prompt,
                    event_queue, start, total_tokens=total_tokens,
                )

        # Step 5: Save artifact and emit download event
        artifact_info = None
        if conversation_id:
            self._emit(event_queue, "status", "Saving artifact...", start)
            artifact_info = self._save_artifact(
                conversation_id, raw_output,
                skill_entry, validation_result, doc_refs,
                yaml_source=yaml_source,
            )
            if artifact_info and event_queue:
                event_queue.put({
                    "type": "artifact",
                    "artifact_id": artifact_info["id"],
                    "filename": artifact_info["filename"],
                    "content_type": artifact_info["content_type"],
                    "summary": artifact_info["summary"],
                    "elapsed_ms": int((time.perf_counter() - start) * 1000),
                })

        # Step 6: Build response
        response = self._build_response(raw_output, validation_result)

        total_ms = int((time.perf_counter() - start) * 1000)

        # Single summary line for quick log scanning
        v = validation_result or {}
        ec = v.get("element_count", 0)
        rc = v.get("relationship_count", 0)
        valid = v.get("valid", False)
        refs = ",".join(doc_refs) if doc_refs else "semantic"
        model = settings.effective_tree_model
        pt = total_tokens["prompt_tokens"]
        ct = total_tokens["completion_tokens"]
        artifact_fn = artifact_info["filename"] if conversation_id and artifact_info else "none"
        pl = pipeline_info["pipeline"]
        yaml_ok = pipeline_info["yaml_valid_first_attempt"]
        yaml_retry = pipeline_info["yaml_retry_triggered"]
        cvt_ms = pipeline_info["convert_ms"]
        logger.info(
            f"[generation] COMPLETE: refs={refs}, model={model}, "
            f"pipeline={pl}, yaml_valid={yaml_ok}, yaml_retry={yaml_retry}, "
            f"convert_ms={cvt_ms}, "
            f"prompt={pt}tok, completion={ct}tok, "
            f"elements={ec}, relationships={rc}, valid={valid}, "
            f"artifact={artifact_fn}, total={total_ms}ms"
        )

        return response, sources

    # ------------------------------------------------------------------
    # Step 1: Content fetching
    # ------------------------------------------------------------------

    async def _fetch_content(
        self, query: str, doc_refs: list[str] | None,
    ) -> tuple[list[dict], str]:
        """Fetch source content from Weaviate.

        Primary: use doc_refs for exact document lookup (no truncation).
        Fallback: semantic search if no doc_refs.
        """
        if doc_refs:
            results = self._fetch_by_doc_refs(doc_refs)
            if results:
                text = "\n\n---\n\n".join(
                    self._format_source(r) for r in results
                )
                return results, text

        # Semantic fallback
        results = self._semantic_search(query)
        if results:
            text = "\n\n---\n\n".join(
                self._format_source(r) for r in results
            )
            return results, text

        return [], ""

    def _fetch_by_doc_refs(self, doc_refs: list[str]) -> list[dict]:
        """Fetch documents by structured references (e.g., ADR.29, PCP.22)."""
        results = []

        adr_refs = [r for r in doc_refs if r.startswith("ADR.")]
        pcp_refs = [r for r in doc_refs if r.startswith("PCP.")]

        if adr_refs:
            results.extend(self._fetch_adrs(adr_refs))
        if pcp_refs:
            results.extend(self._fetch_pcps(pcp_refs))

        return results

    def _fetch_adrs(self, adr_refs: list[str]) -> list[dict]:
        """Fetch ADR documents by reference, returning full content."""
        collection = self._get_collection("ArchitecturalDecision")
        if not collection:
            return []

        props = self._get_return_props(collection)
        is_dar = any(r.endswith("D") for r in adr_refs)
        numbers = []
        for ref in adr_refs:
            num_str = ref.split(".")[1].replace("D", "")
            try:
                numbers.append(int(num_str))
            except ValueError:
                pass

        if not numbers:
            return []

        # Build filter — range for multiple, exact for single
        if len(numbers) >= 2:
            start = str(min(numbers)).zfill(4)
            end = str(max(numbers)).zfill(4)
            adr_filter = (
                Filter.by_property("adr_number").greater_or_equal(start)
                & Filter.by_property("adr_number").less_or_equal(end)
            )
        else:
            padded = str(numbers[0]).zfill(4)
            adr_filter = Filter.by_property("adr_number").equal(padded)

        results = collection.query.fetch_objects(
            filters=adr_filter, limit=500, return_properties=props,
        )

        # Aggregate all chunks per document (generation needs full content).
        # Unlike listing/search which dedup to one entry per doc, we
        # concatenate content from all chunks of the same ADR.
        docs: dict[str, dict] = {}
        for obj in results.objects:
            num = obj.properties.get("adr_number", "")
            doc_type = obj.properties.get("doc_type", "")
            title = obj.properties.get("title", "")
            if not num:
                continue
            if not is_dar:
                if doc_type in ("adr_approval", "template", "index"):
                    continue
                if title.startswith("Decision Approval Record"):
                    continue

            if num not in docs:
                docs[num] = {k: obj.properties.get(k, "") for k in props}
            else:
                chunk_content = obj.properties.get("content", "")
                if chunk_content:
                    docs[num]["content"] = (
                        docs[num].get("content", "") + "\n\n" + chunk_content
                    )

        return sorted(docs.values(), key=lambda x: x.get("adr_number", ""))

    def _fetch_pcps(self, pcp_refs: list[str]) -> list[dict]:
        """Fetch Principle documents by reference, returning full content."""
        collection = self._get_collection("Principle")
        if not collection:
            return []

        props = self._get_return_props(collection)
        numbers = []
        for ref in pcp_refs:
            num_str = ref.split(".")[1].replace("D", "")
            try:
                numbers.append(int(num_str))
            except ValueError:
                pass

        if not numbers:
            return []

        if len(numbers) >= 2:
            start = str(min(numbers)).zfill(4)
            end = str(max(numbers)).zfill(4)
            pcp_filter = (
                Filter.by_property("principle_number").greater_or_equal(start)
                & Filter.by_property("principle_number").less_or_equal(end)
            )
        else:
            padded = str(numbers[0]).zfill(4)
            pcp_filter = Filter.by_property("principle_number").equal(padded)

        results = collection.query.fetch_objects(
            filters=pcp_filter, limit=500, return_properties=props,
        )

        # Aggregate all chunks per principle (same as _fetch_adrs)
        docs: dict[str, dict] = {}
        for obj in results.objects:
            pn = obj.properties.get("principle_number", "")
            title = obj.properties.get("title", "")
            if not pn:
                continue
            if title.startswith("Principle Approval Record"):
                continue

            if pn not in docs:
                docs[pn] = {k: obj.properties.get(k, "") for k in props}
            else:
                chunk_content = obj.properties.get("content", "")
                if chunk_content:
                    docs[pn]["content"] = (
                        docs[pn].get("content", "") + "\n\n" + chunk_content
                    )

        return sorted(docs.values(), key=lambda x: x.get("principle_number", ""))

    def _semantic_search(self, query: str, limit: int = 5) -> list[dict]:
        """Semantic search across ADR and Principle collections."""
        vector = embed_text(query)
        if not vector:
            return []

        results = []
        for coll_name in ("ArchitecturalDecision", "Principle"):
            collection = self._get_collection(coll_name)
            if not collection:
                continue
            props = self._get_return_props(collection)
            hits = collection.query.hybrid(
                query=query, vector=vector, alpha=0.5,
                limit=limit, return_properties=props,
                return_metadata=MetadataQuery(distance=True),
            )
            for obj in hits.objects:
                doc_type = obj.properties.get("doc_type", "")
                title = obj.properties.get("title", "")
                if doc_type in ("adr_approval", "template", "index"):
                    continue
                if title.startswith(("Decision Approval Record", "Principle Approval Record")):
                    continue
                results.append({k: obj.properties.get(k, "") for k in props})

        return results[:limit]

    @staticmethod
    def _format_source(source: dict) -> str:
        """Format a source document for inclusion in the LLM prompt."""
        title = source.get("title", "Untitled")
        content = source.get("content", "")
        doc_id = (
            source.get("adr_number", "")
            or source.get("principle_number", "")
            or ""
        )
        header = f"## {doc_id} — {title}" if doc_id else f"## {title}"
        return f"{header}\n\n{content}"

    # ------------------------------------------------------------------
    # Step 3: LLM call
    # ------------------------------------------------------------------

    async def _call_llm(
        self, system_prompt: str, user_prompt: str,
    ) -> tuple[str, dict]:
        """Make a single LLM call. Returns (text, token_stats)."""
        provider = settings.effective_tree_provider
        if provider in ("github_models", "openai"):
            return await self._call_openai(system_prompt, user_prompt)
        return await self._call_ollama(system_prompt, user_prompt)

    async def _call_openai(
        self, system_prompt: str, user_prompt: str,
    ) -> tuple[str, dict]:
        from openai import OpenAI

        client = OpenAI(**settings.get_openai_client_kwargs(settings.effective_tree_provider))
        model = settings.effective_tree_model

        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        # GPT-5.x reasoning models consume reasoning tokens within
        # max_completion_tokens. 16K gives room for reasoning + full XML.
        model_base = model.rsplit("/", 1)[-1] if "/" in model else model
        if model_base.startswith("gpt-5"):
            kwargs["max_completion_tokens"] = 16384
        else:
            kwargs["max_tokens"] = 8192

        max_tok = kwargs.get("max_completion_tokens", kwargs.get("max_tokens"))
        logger.info(
            f"[generation] LLM call: model={model}, "
            f"system_prompt={len(system_prompt)} chars, "
            f"user_prompt={len(user_prompt)} chars, "
            f"est_tokens=~{(len(system_prompt) + len(user_prompt)) // 4}, "
            f"max_completion_tokens={max_tok}"
        )

        start = time.perf_counter()
        response = client.chat.completions.create(**kwargs)
        duration_ms = int((time.perf_counter() - start) * 1000)

        text = response.choices[0].message.content or ""

        usage = getattr(response, "usage", None)
        token_stats = {"prompt_tokens": 0, "completion_tokens": 0}
        if usage:
            token_stats["prompt_tokens"] = usage.prompt_tokens or 0
            token_stats["completion_tokens"] = usage.completion_tokens or 0
            logger.info(
                f"[generation] LLM response: {len(text)} chars, {duration_ms}ms, "
                f"tokens: prompt={token_stats['prompt_tokens']}, "
                f"completion={token_stats['completion_tokens']}, "
                f"total={sum(token_stats.values())}"
            )
        else:
            logger.info(f"[generation] LLM response: {len(text)} chars, {duration_ms}ms")

        return text, token_stats

    async def _call_ollama(
        self, system_prompt: str, user_prompt: str,
    ) -> tuple[str, dict]:
        import httpx

        model = settings.effective_tree_model
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        logger.info(
            f"[generation] LLM call: model={model}, "
            f"system_prompt={len(system_prompt)} chars, "
            f"user_prompt={len(user_prompt)} chars, "
            f"est_tokens=~{(len(full_prompt)) // 4}, "
            f"num_predict=8192"
        )

        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {"num_predict": 8192},
                },
            )
            response.raise_for_status()
            data = response.json()
            text = data.get("response", "")
        duration_ms = int((time.perf_counter() - start) * 1000)

        # Strip <think> tags from reasoning models
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"</?think>", "", text)
        text = text.strip()

        token_stats = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
        }
        logger.info(
            f"[generation] LLM response: {len(text)} chars, {duration_ms}ms, "
            f"tokens: prompt={token_stats['prompt_tokens']}, "
            f"completion={token_stats['completion_tokens']}"
        )

        return text, token_stats

    # ------------------------------------------------------------------
    # Step 4: Validation with retry
    # ------------------------------------------------------------------

    async def _validate_with_retry(
        self,
        raw_output: str,
        validator,
        system_prompt: str,
        user_prompt: str,
        event_queue: Queue | None,
        start: float,
        max_retries: int = 2,
        total_tokens: dict | None = None,
    ) -> tuple[str, dict]:
        """Validate generated output, retrying on errors."""
        xml = self._extract_xml(raw_output)
        if not xml:
            return raw_output, {"valid": False, "errors": ["No XML found in output"]}

        xml = self._sanitize_xml(xml)
        xml = await self._repair_view(xml, event_queue, start, total_tokens)

        for attempt in range(max_retries + 1):
            self._emit(
                event_queue, "status",
                f"Validating (attempt {attempt + 1})...", start,
            )
            result = validator(xml)

            if result.get("valid"):
                logger.info(
                    f"Validation passed: {result.get('element_count')} elements, "
                    f"{result.get('relationship_count')} relationships"
                )
                return xml, result

            errors = result.get("errors", [])

            # Try mechanical sanitize before expensive LLM retry
            sanitized = self._sanitize_xml(xml)
            if sanitized != xml:
                result = validator(sanitized)
                if result.get("valid"):
                    logger.info("Sanitize fixed validation errors, skipping LLM retry")
                    return sanitized, result
                xml = sanitized  # keep sanitized version for LLM retry

            if attempt < max_retries:
                logger.info(f"Validation failed (attempt {attempt + 1}), retrying: {errors}")
                self._emit(event_queue, "status", "Fixing validation errors...", start)
                retry_prompt = (
                    f"{user_prompt}\n\n"
                    f"PREVIOUS OUTPUT HAD ERRORS — fix these:\n"
                    + "\n".join(f"- {e}" for e in errors[:10])
                    + "\n\nGenerate the corrected output now."
                )
                new_output, retry_stats = await self._call_llm(system_prompt, retry_prompt)
                if total_tokens:
                    total_tokens["prompt_tokens"] += retry_stats["prompt_tokens"]
                    total_tokens["completion_tokens"] += retry_stats["completion_tokens"]
                xml = self._sanitize_xml(self._extract_xml(new_output) or xml)
            else:
                logger.warning(f"Validation failed after {max_retries + 1} attempts: {errors}")

        return xml, result

    # ------------------------------------------------------------------
    # Step 5: Artifact save
    # ------------------------------------------------------------------

    def _save_artifact(
        self,
        conversation_id: str,
        content: str,
        skill_entry,
        validation_result: dict | None,
        doc_refs: list[str] | None = None,
        yaml_source: str | None = None,
    ) -> dict | None:
        """Save the generated content as an artifact.

        Returns dict with id, filename, content_type, summary on success.
        If yaml_source is provided, also saves a companion .yaml artifact
        for future refinement.
        """
        from src.aion.chat_ui import save_artifact

        # Only save if we have actual XML, not raw LLM text
        if "archimate" in skill_entry.name and "<model" not in content:
            logger.warning("[generation] Skipping artifact save — no XML in content")
            return None

        filename = self._derive_filename(content, doc_refs, skill_entry)
        content_type = "archimate/xml" if "archimate" in skill_entry.name else "text/plain"

        summary = ""
        if validation_result and validation_result.get("valid"):
            ec = validation_result.get("element_count", 0)
            rc = validation_result.get("relationship_count", 0)
            summary = f"{ec} elements, {rc} relationships"

        try:
            artifact_id = save_artifact(
                conversation_id, filename, content, content_type, summary,
            )
            logger.info(f"Saved generation artifact: {filename} ({artifact_id})")

            # Save companion YAML for future refinement
            if yaml_source:
                yaml_filename = filename.replace(".archimate.xml", ".archimate.yaml")
                try:
                    save_artifact(
                        conversation_id, yaml_filename, yaml_source,
                        "text/yaml", "Source YAML",
                    )
                    logger.info(f"Saved YAML companion: {yaml_filename}")
                except Exception as e:
                    logger.warning(f"Failed to save YAML companion: {e}")

            return {
                "id": artifact_id,
                "filename": filename,
                "content_type": content_type,
                "summary": summary,
            }
        except Exception as e:
            logger.warning(f"Failed to save generation artifact: {e}")
            return None

    @staticmethod
    def _derive_filename(
        content: str, doc_refs: list[str] | None, skill_entry,
    ) -> str:
        """Derive artifact filename. Priority: XML <name> > doc_refs > fallback."""
        ext = ".archimate.xml" if "archimate" in skill_entry.name else ".txt"

        # 1. Try XML model name
        name_match = re.search(r'<name xml:lang="en">(.*?)</name>', content)
        if name_match:
            name = name_match.group(1).strip()
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
            if slug:
                return f"{slug}{ext}"

        # 2. Try doc_refs
        if doc_refs:
            slug = "-".join(r.lower().replace(".", "") for r in doc_refs[:3])
            return f"{slug}{ext}"

        # 3. Fallback
        return f"model{ext}"

    # ------------------------------------------------------------------
    # Step 6: Build response
    # ------------------------------------------------------------------

    @staticmethod
    def _build_response(content: str, validation_result: dict | None) -> str:
        """Build the user-facing response with validation summary."""
        parts = []

        if validation_result:
            if validation_result.get("valid"):
                ec = validation_result.get("element_count", 0)
                rc = validation_result.get("relationship_count", 0)
                parts.append(
                    f"Generated ArchiMate 3.2 model with **{ec} elements** "
                    f"and **{rc} relationships**."
                )
            else:
                errors = validation_result.get("errors", [])
                parts.append(
                    "Generated model with validation issues:\n"
                    + "\n".join(f"- {e}" for e in errors[:5])
                )

            warnings = validation_result.get("warnings", [])
            if warnings:
                parts.append(
                    "**Warnings:**\n" + "\n".join(f"- {w}" for w in warnings[:5])
                )

        # XML goes in the artifact (already saved), not inline.
        # Only show non-XML content inline (e.g., if generation failed).
        if "<model" not in content and "<?xml" not in content:
            parts.append(content)

        parts.append(
            "The model has been saved as an artifact. You can download it "
            "and import it into Archi (File > Import > Open Exchange XML) "
            "or any ArchiMate 3.2-compliant tool."
        )

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # View repair (runs before validation)
    # ------------------------------------------------------------------

    async def _repair_view(
        self, xml: str, event_queue: Queue | None, start: float,
        total_tokens: dict | None = None,
    ) -> str:
        """Detect and repair missing view nodes and connections.

        Tier 1: Parse XML, find elements without nodes and relationships
                without connections in any view.
        Tier 2: If missing refs found, make a focused LLM call with only
                the <views> section to get repairs.
        Tier 3: If LLM call fails, mechanically add nodes/connections.
        """
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return xml  # Let validation handle parse errors

        # --- Collect model inventory ---
        elements_node = root.find(TAG("elements"))
        rels_node = root.find(TAG("relationships"))
        if elements_node is None:
            return xml

        element_ids: dict[str, str] = {}  # identifier → xsi:type
        element_names: dict[str, str] = {}  # identifier → name
        for elem in elements_node.findall(TAG("element")):
            eid = elem.get("identifier")
            if eid:
                element_ids[eid] = elem.get(f"{{{XSI}}}type", "")
                name_el = elem.find(TAG("name"))
                element_names[eid] = name_el.text if name_el is not None and name_el.text else ""

        rel_map: dict[str, tuple[str, str, str]] = {}  # id → (source, target, type)
        if rels_node is not None:
            for rel in rels_node.findall(TAG("relationship")):
                rid = rel.get("identifier")
                src = rel.get("source")
                tgt = rel.get("target")
                if rid and src and tgt:
                    rel_map[rid] = (src, tgt, rel.get(f"{{{XSI}}}type", ""))

        if not element_ids:
            return xml

        # --- Detect missing refs across all views ---
        views_node = root.find(TAG("views"))
        if views_node is None:
            return xml
        diagrams = views_node.find(TAG("diagrams"))
        if diagrams is None:
            return xml
        views = diagrams.findall(TAG("view"))
        if not views:
            return xml

        all_erefs: set[str] = set()
        # Track per-view data for the target (first) view
        target_view = views[0]
        target_vid = target_view.get("identifier", "")
        target_erefs: set[str] = set()
        target_nmap: dict[str, str] = {}  # elementRef → node identifier
        target_rrefs: set[str] = set()

        def collect_nodes(parent: ET.Element, erefs: set, nmap: dict):
            for node in parent.findall(TAG("node")):
                eref = node.get("elementRef")
                nid = node.get("identifier")
                if eref and nid:
                    erefs.add(eref)
                    nmap[eref] = nid
                collect_nodes(node, erefs, nmap)

        # Collect from all views (for "missing from ANY view" check)
        for view in views:
            v_erefs: set[str] = set()
            v_nmap: dict[str, str] = {}
            collect_nodes(view, v_erefs, v_nmap)
            all_erefs |= v_erefs
            if view is target_view:
                target_erefs = v_erefs
                target_nmap = v_nmap

        for conn in target_view.findall(TAG("connection")):
            rref = conn.get("relationshipRef")
            if rref:
                target_rrefs.add(rref)

        # Elements with zero view representation
        missing_elements = set(element_ids.keys()) - all_erefs

        # Relationships missing connections in target view (including
        # those that become representable after adding missing elements)
        future_erefs = target_erefs | missing_elements
        missing_connections = []
        for rid, (src, tgt, _rtype) in rel_map.items():
            if rid not in target_rrefs and src in future_erefs and tgt in future_erefs:
                missing_connections.append(rid)

        if not missing_elements and not missing_connections:
            logger.info("[generation] view repair: no missing refs detected")
            return xml

        logger.info(
            f"[generation] view repair: {len(missing_elements)} missing nodes, "
            f"{len(missing_connections)} missing connections"
        )
        self._emit(event_queue, "status", "Repairing view...", start)

        # --- Tier 2: Focused LLM call ---
        repaired = await self._repair_view_llm(
            xml, root, views_node,
            missing_elements, missing_connections,
            element_ids, element_names, rel_map,
            target_vid, target_nmap, total_tokens,
        )
        if repaired:
            logger.info("[generation] view repair: LLM repair successful")
            return repaired

        # --- Tier 3: Mechanical auto-repair ---
        logger.info("[generation] view repair: LLM failed, using auto-repair")
        return self._repair_view_mechanical(
            root, target_view, target_vid,
            missing_elements, missing_connections,
            element_ids, rel_map, target_nmap,
        )

    async def _repair_view_llm(
        self,
        full_xml: str,
        root: ET.Element,
        views_node: ET.Element,
        missing_elements: set[str],
        missing_connections: list[str],
        element_ids: dict[str, str],
        element_names: dict[str, str],
        rel_map: dict[str, tuple[str, str, str]],
        target_vid: str,
        target_nmap: dict[str, str],
        total_tokens: dict | None = None,
    ) -> str | None:
        """Tier 2: Focused LLM call to repair view with good layout."""
        view_num = target_vid.replace("id-v", "")

        # Build element-to-node mapping (existing + planned new)
        full_nmap = dict(target_nmap)
        for eid in missing_elements:
            code = eid.replace("id-", "")
            full_nmap[eid] = f"nv{view_num}-{code}"

        views_xml = ET.tostring(views_node, encoding="unicode")

        # Build missing-refs description
        lines = []
        if missing_elements:
            lines.append("MISSING NODES (add <node> for each):")
            for eid in sorted(missing_elements):
                etype = element_ids.get(eid, "?")
                ename = element_names.get(eid, "")
                nid = full_nmap[eid]
                lines.append(f"  - {eid} ({etype}, \"{ename}\") → node id: {nid}")

        if missing_connections:
            lines.append("\nMISSING CONNECTIONS (add <connection> for each):")
            for rid in sorted(missing_connections):
                src_eid, tgt_eid, rtype = rel_map[rid]
                src_node = full_nmap.get(src_eid, "?")
                tgt_node = full_nmap.get(tgt_eid, "?")
                rcode = rid.replace("id-", "")
                lines.append(
                    f"  - {rid} ({rtype}: {src_eid}→{tgt_eid}) → "
                    f"connection id: cv{view_num}-{rcode}, "
                    f"source: {src_node}, target: {tgt_node}"
                )

        system_prompt = (
            "You fix ArchiMate 3.2 Open Exchange XML views. You receive a <views> section "
            "and a list of missing nodes and connections. Add them to the appropriate view. "
            "Node identifier convention: nv{view}-{code}. Connection: cv{view}-{code}. "
            "Standard node size: w=\"120\" h=\"55\". Place new nodes near related existing "
            "nodes. Connection source/target reference NODE identifiers, not element IDs. "
            "Return ONLY the complete <views>...</views> section, nothing else."
        )
        user_prompt = (
            f"CURRENT VIEWS SECTION:\n{views_xml}\n\n"
            + "\n".join(lines)
            + "\n\nReturn the complete updated <views>...</views> section."
        )

        try:
            response, repair_stats = await self._call_llm(system_prompt, user_prompt)
            if total_tokens:
                total_tokens["prompt_tokens"] += repair_stats["prompt_tokens"]
                total_tokens["completion_tokens"] += repair_stats["completion_tokens"]
            if not response:
                return None

            # Extract <views>...</views> from response
            resp = response.strip()
            if "```" in resp:
                resp = re.sub(r"^```(?:xml)?\s*\n?", "", resp)
                resp = re.sub(r"\n?```\s*$", "", resp)
                resp = resp.strip()

            if "<views" not in resp or "</views>" not in resp:
                logger.warning("[generation] view repair LLM: no <views> in response")
                return None

            # Parse the repaired views to validate structure
            try:
                new_views = ET.fromstring(resp)
            except ET.ParseError:
                logger.warning("[generation] view repair LLM: response XML parse failed")
                return None

            # Splice: remove old views, append new
            root.remove(root.find(TAG("views")))
            root.append(new_views)
            return ET.tostring(root, encoding="unicode", xml_declaration=True)

        except Exception as e:
            logger.warning(f"[generation] view repair LLM failed: {e}")
            return None

    @staticmethod
    def _repair_view_mechanical(
        root: ET.Element,
        target_view: ET.Element,
        target_vid: str,
        missing_elements: set[str],
        missing_connections: list[str],
        element_ids: dict[str, str],
        rel_map: dict[str, tuple[str, str, str]],
        target_nmap: dict[str, str],
    ) -> str:
        """Tier 3: Mechanically add missing nodes/connections."""
        view_num = target_vid.replace("id-v", "")
        nmap = dict(target_nmap)

        # Find max y in existing nodes for placement below
        max_y = 0
        for node in target_view.iter(TAG("node")):
            y = int(node.get("y", "0"))
            h = int(node.get("h", "55"))
            max_y = max(max_y, y + h)

        # Place missing elements grouped by layer
        x_pos = 20
        y_pos = max_y + 40  # gap below existing content
        added_nodes = 0

        for eid in sorted(missing_elements):
            etype = element_ids.get(eid, "")
            layer = LAYER_MAP.get(etype, "Composite")
            # Use layer Y if it's below existing content, otherwise stack below
            layer_y = _LAYER_Y.get(layer, 580)
            use_y = max(layer_y, y_pos) if added_nodes == 0 else y_pos

            code = eid.replace("id-", "")
            node_id = f"nv{view_num}-{code}"

            node_el = ET.SubElement(target_view, TAG("node"))
            node_el.set("identifier", node_id)
            node_el.set("elementRef", eid)
            node_el.set(f"{{{XSI}}}type", "Element")
            node_el.set("x", str(x_pos))
            node_el.set("y", str(use_y))
            node_el.set("w", "120")
            node_el.set("h", "55")

            nmap[eid] = node_id
            added_nodes += 1
            x_pos += 160
            if x_pos > 20 + 160 * 4:  # wrap after 5 per row
                x_pos = 20
                y_pos = use_y + 80

        # Add missing connections
        added_conns = 0
        for rid in sorted(missing_connections):
            src_eid, tgt_eid, _rtype = rel_map[rid]
            src_node = nmap.get(src_eid)
            tgt_node = nmap.get(tgt_eid)
            if not src_node or not tgt_node:
                continue

            rcode = rid.replace("id-", "")
            conn_id = f"cv{view_num}-{rcode}"

            conn_el = ET.SubElement(target_view, TAG("connection"))
            conn_el.set("identifier", conn_id)
            conn_el.set("relationshipRef", rid)
            conn_el.set(f"{{{XSI}}}type", "Relationship")
            conn_el.set("source", src_node)
            conn_el.set("target", tgt_node)
            added_conns += 1

        logger.info(
            f"[generation] view repair: auto-repair added "
            f"{added_nodes} nodes, {added_conns} connections"
        )
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_xml(text: str) -> str | None:
        """Validate that the LLM response is XML.

        The LLM is instructed to return raw XML only. This method
        validates the response rather than hunting for XML in text.
        Safety nets handle models that prefix junk (hallucinated tool
        calls, code fences) before the actual XML.
        """
        if not text:
            return None

        content = text.strip()

        # Safety net: strip markdown code fences if the model disobeys
        if content.startswith("```"):
            content = re.sub(r"^```(?:xml)?\s*\n?", "", content)
            content = re.sub(r"\n?```\s*$", "", content)
            content = content.strip()

        # Safety net: strip preamble before <?xml (hallucinated tool
        # calls like <tool name="validate_archimate"/> etc.)
        if "<?xml" in content and not content.startswith("<?xml"):
            idx = content.index("<?xml")
            content = content[idx:]

        # Validate: response should be XML with a <model> root
        if content.startswith("<?xml") or content.startswith("<model"):
            if "</model>" in content:
                return content

        logger.warning(
            f"[generation] Response is not XML. "
            f"Length: {len(text)} chars. "
            f"Starts with: {text[:100]!r}"
        )
        return None

    @staticmethod
    def _extract_yaml(text: str) -> str | None:
        """Extract YAML from LLM response.

        Strips markdown code fences (even with preamble text before them)
        and validates that the content looks like ArchiMate YAML by
        requiring multiple expected keys.
        """
        if not text:
            return None

        content = text.strip()

        # Strip code fences — search for first ``` (LLM may prepend preamble)
        fence_start = content.find("```")
        if fence_start >= 0:
            content = content[fence_start:]
            content = re.sub(r"^```(?:ya?ml)?\s*\n?", "", content)
            content = re.sub(r"\n?```\s*$", "", content)
            content = content.strip()

        # Require multiple YAML keys to avoid false-positives on retrieval text
        if "elements:" in content and ("model:" in content or "relationships:" in content):
            return content
        return None

    @staticmethod
    def _sanitize_xml(xml: str) -> str:
        """Fix trivial XML syntax issues that LLMs produce.

        Escapes bare & characters that aren't already part of a valid
        XML entity reference. Runs before validation so we don't waste
        an LLM retry on a one-character fix.
        """
        original = xml
        # Escape & not already followed by amp; lt; gt; quot; apos; or #
        xml = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", xml)
        if xml != original:
            count = xml.count("&amp;") - original.count("&amp;")
            logger.info(f"[generation] sanitized {count} bare & → &amp;")
        return xml

    def _get_collection(self, base_name: str):
        """Get a Weaviate collection, trying OpenAI suffix variant."""
        if base_name in self._collection_cache:
            return self._collection_cache[base_name]

        # Try OpenAI-suffixed name first when using OpenAI provider
        if settings.effective_tree_provider in ("github_models", "openai"):
            oai_name = f"{base_name}_OpenAI"
            if self.client.collections.exists(oai_name):
                coll = self.client.collections.get(oai_name)
                self._collection_cache[base_name] = coll
                return coll

        if self.client.collections.exists(base_name):
            coll = self.client.collections.get(base_name)
            self._collection_cache[base_name] = coll
            return coll

        logger.warning(f"Collection {base_name} not found")
        return None

    def _get_return_props(self, collection) -> list[str]:
        """Get returnable property names (excludes large internal fields)."""
        name = collection.name
        if name not in self._prop_cache:
            schema_props = collection.config.get().properties
            self._prop_cache[name] = [
                p.name for p in schema_props
                if p.name not in self._EXCLUDED_PROPS
            ]
        return self._prop_cache[name]

    @staticmethod
    def _load_previous_artifact(
        conversation_id: str, skill_entry,
    ) -> dict | None:
        """Load the most recent artifact for this conversation.

        For refinement, we need the previous generation's output as the
        base to modify. Filters by content_type matching the skill.
        """
        from src.aion.chat_ui import get_latest_artifact

        content_type = (
            "archimate/xml" if "archimate" in skill_entry.name else None
        )
        return get_latest_artifact(conversation_id, content_type)

    @staticmethod
    def _load_previous_artifact_by_type(
        conversation_id: str, content_type: str,
    ) -> dict | None:
        """Load the most recent artifact of a specific content type."""
        from src.aion.chat_ui import get_latest_artifact
        return get_latest_artifact(conversation_id, content_type)

    @staticmethod
    def _emit(
        queue: Queue | None, event_type: str, content: str, start: float,
    ) -> None:
        """Emit an SSE event to the queue."""
        if queue:
            queue.put({
                "type": event_type,
                "content": content,
                "elapsed_ms": int((time.perf_counter() - start) * 1000),
            })
