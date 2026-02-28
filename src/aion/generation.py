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
from queue import Queue
from typing import Optional

from weaviate import WeaviateClient
from weaviate.classes.query import Filter, MetadataQuery

from src.aion.config import settings
from src.aion.skills.loader import SkillLoader
from src.aion.skills.registry import get_skill_registry
from src.aion.tools.archimate import validate_archimate as _validate_archimate
from src.aion.weaviate.embeddings import embed_text

logger = logging.getLogger(__name__)

# Validation tool dispatch — maps registry validation_tool names to callables.
# New generation skills register their validator here.
_VALIDATION_TOOLS = {
    "validate_archimate": _validate_archimate,
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
    ) -> tuple[str, list[dict]]:
        """Run the generation pipeline.

        Args:
            query: The user's rewritten query from the Persona.
            skill_tags: Active skill tags (e.g., ["archimate"]).
            doc_refs: Structured document references (e.g., ["ADR.29"]).
            conversation_id: For artifact storage.
            event_queue: Optional Queue for SSE status events.

        Returns:
            Tuple of (response text with embedded content, source objects).
        """
        start = time.perf_counter()

        # Look up the generation skill from the registry
        registry = get_skill_registry()
        skill_entry = registry.get_generation_skill(skill_tags)
        if not skill_entry:
            return "No generation skill found for the requested tags.", []

        # Step 1: Fetch source content
        self._emit(event_queue, "status", "Retrieving source content...", start)
        sources, source_text = await self._fetch_content(query, doc_refs)

        if not source_text:
            return (
                "Could not retrieve source content for generation. "
                "Please specify which document to use (e.g., ADR.29)."
            ), []

        logger.info(
            f"[generation] source content: {len(source_text)} chars "
            f"from {len(sources)} sources"
        )

        # Step 2: Build prompt — load ONLY the generation skill, not all skills.
        # The "always" skills (identity, QA, ontology, formatter) are designed
        # for the Tree's retrieval path and are irrelevant for direct generation.
        loader = SkillLoader()
        skill = loader.load_skill(skill_entry.name)
        system_prompt = skill.content if skill else ""
        user_prompt = (
            f"SOURCE CONTENT:\n{source_text}\n\n"
            f"USER REQUEST:\n{query}\n\n"
            f"Respond with ONLY the XML document starting with <?xml. "
            f"Do not include tool calls, commentary, or any other text."
        )

        # Step 3: LLM call
        self._emit(event_queue, "status", "Generating...", start)
        raw_output = await self._call_llm(system_prompt, user_prompt)

        if not raw_output:
            return "The model did not produce output. Try a cloud model for generation tasks.", []

        # Step 4: Validate (if the skill declares a validation tool)
        validation_result = None
        if skill_entry.validation_tool:
            validator = _VALIDATION_TOOLS.get(skill_entry.validation_tool)
            if validator:
                raw_output, validation_result = await self._validate_with_retry(
                    raw_output, validator, system_prompt, user_prompt,
                    event_queue, start,
                )

        # Step 5: Save artifact and emit download event
        if conversation_id:
            self._emit(event_queue, "status", "Saving artifact...", start)
            artifact_info = self._save_artifact(
                conversation_id, raw_output,
                skill_entry, validation_result, doc_refs,
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
        prompt_est = (len(system_prompt) + len(user_prompt)) // 4
        logger.info(
            f"[generation] COMPLETE: refs={refs}, model={model}, "
            f"prompt=~{prompt_est}tok, source={len(source_text)}ch, "
            f"elements={ec}, relationships={rc}, valid={valid}, "
            f"total={total_ms}ms"
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

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Make a single LLM call using the Tree's configured provider."""
        provider = settings.effective_tree_provider
        if provider in ("github_models", "openai"):
            return await self._call_openai(system_prompt, user_prompt)
        return await self._call_ollama(system_prompt, user_prompt)

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
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
        if usage:
            logger.info(
                f"[generation] LLM response: {len(text)} chars, {duration_ms}ms, "
                f"tokens: prompt={usage.prompt_tokens}, "
                f"completion={usage.completion_tokens}, "
                f"total={usage.total_tokens}"
            )
        else:
            logger.info(f"[generation] LLM response: {len(text)} chars, {duration_ms}ms")

        return text

    async def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
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
            text = response.json().get("response", "")
        duration_ms = int((time.perf_counter() - start) * 1000)

        # Strip <think> tags from reasoning models
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"</?think>", "", text)
        text = text.strip()

        logger.info(f"[generation] LLM response: {len(text)} chars, {duration_ms}ms")

        return text

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
    ) -> tuple[str, dict]:
        """Validate generated output, retrying on errors."""
        xml = self._extract_xml(raw_output)
        if not xml:
            return raw_output, {"valid": False, "errors": ["No XML found in output"]}

        xml = self._sanitize_xml(xml)

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
            if attempt < max_retries:
                logger.info(f"Validation failed (attempt {attempt + 1}), retrying: {errors}")
                self._emit(event_queue, "status", "Fixing validation errors...", start)
                retry_prompt = (
                    f"{user_prompt}\n\n"
                    f"PREVIOUS OUTPUT HAD ERRORS — fix these:\n"
                    + "\n".join(f"- {e}" for e in errors[:10])
                    + "\n\nGenerate the corrected output now."
                )
                new_output = await self._call_llm(system_prompt, retry_prompt)
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
    ) -> dict | None:
        """Save the generated content as an artifact.

        Returns dict with id, filename, content_type, summary on success.
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
