"""Unified API response gateway for enterprise-grade LLM output.

This module provides:
- normalize_and_validate_response(): Single entry point for all UI API responses
- CLI delimiter protocol for deterministic JSON extraction
- Structured mode context tracking (triggers, versions, etc.)
- Failure UX with controlled error messages and request IDs
- Integration with Weaviate for items_total population

Architecture:
    User UI → your backend → Elysia CLI (LLM + retrieval) → raw text →
    normalize_and_validate_response() → your UI

This module sits at the UI boundary as the "API contract layer".
"""

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal, Optional

from .response_schema import (
    CURRENT_SCHEMA_VERSION,
    ReasonCode,
    ResponseMetrics,
    ResponseParser,
    ResponseValidator,
    StructuredResponse,
)

logger = logging.getLogger(__name__)

# =============================================================================
# CLI Delimiter Protocol
# =============================================================================

# Explicit delimiters for structured mode output
# These markers allow deterministic extraction even when CLI adds metadata/banners
JSON_START_MARKER = "<<<JSON>>>"
JSON_END_MARKER = "<<<END_JSON>>>"

# Alternative: fenced JSON block (more common, less explicit)
FENCED_JSON_PATTERN = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL)

# Marker-based extraction pattern
MARKER_JSON_PATTERN = re.compile(
    rf'{re.escape(JSON_START_MARKER)}\s*(\{{.*?\}})\s*{re.escape(JSON_END_MARKER)}',
    re.DOTALL
)


def extract_json_with_delimiters(
    raw_text: str,
    strict: bool = False
) -> tuple[Optional[str], str]:
    """Extract JSON using CLI delimiter protocol.

    Priority order:
    1. Explicit markers (<<<JSON>>>...<<<END_JSON>>>)
    2. Fenced JSON block (```json...```)
    3. Raw JSON (entire response is JSON)
    4. Embedded JSON object (regex extraction)

    Args:
        raw_text: Raw CLI output text
        strict: If True, only accept marker-delimited or raw JSON

    Returns:
        Tuple of (extracted_json_str or None, extraction_method)
    """
    if not raw_text:
        return None, "empty_input"

    text = raw_text.strip()

    # Method 1: Explicit markers (highest confidence)
    match = MARKER_JSON_PATTERN.search(text)
    if match:
        return match.group(1).strip(), "marker_delimited"

    # Method 2: Try raw JSON parse (entire text is JSON)
    if text.startswith('{') and text.endswith('}'):
        try:
            json.loads(text)
            return text, "raw_json"
        except json.JSONDecodeError:
            pass

    # In strict mode, reject anything else
    if strict:
        return None, "strict_rejected"

    # Method 3: Fenced JSON block
    match = FENCED_JSON_PATTERN.search(text)
    if match:
        return match.group(1).strip(), "fenced_json"

    # Method 4: Use ResponseParser's extraction (handles embedded JSON)
    extracted = ResponseParser.extract_json(text)
    if extracted:
        return extracted, "embedded_json"

    return None, "no_json_found"


# =============================================================================
# Structured Mode Context
# =============================================================================

# Current prompt version for correlation
PROMPT_VERSION = "1.0.0"


@dataclass
class StructuredModeContext:
    """Context for structured mode processing.

    Captures all metadata needed to diagnose regressions:
    - Which skills were active
    - Which triggers matched
    - What versions are in use
    - Processing stage reached
    """
    structured_mode: bool
    active_skill_names: list[str] = field(default_factory=list)
    matched_triggers: list[str] = field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    schema_version: str = CURRENT_SCHEMA_VERSION
    model_id: Optional[str] = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Processing metadata (filled during processing)
    extraction_method: Optional[str] = None
    parse_stage: Optional[str] = None
    reason_code: Optional[ReasonCode] = None
    latency_ms: Optional[int] = None

    def to_log_dict(self) -> dict:
        """Convert to dictionary for structured logging."""
        return {
            "request_id": self.request_id,
            "structured_mode": self.structured_mode,
            "active_skills": self.active_skill_names,
            "matched_triggers": self.matched_triggers,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "extraction_method": self.extraction_method,
            "parse_stage": self.parse_stage,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "latency_ms": self.latency_ms,
        }


def create_context_from_skills(
    question: str,
    skill_registry,
    model_id: Optional[str] = None,
) -> StructuredModeContext:
    """Create structured mode context from skill registry.

    This function checks skill activation and captures which triggers matched.

    Args:
        question: User's query
        skill_registry: Skill registry instance
        model_id: Optional model identifier

    Returns:
        StructuredModeContext with all relevant metadata
    """
    # Check if response-contract skill is active
    structured_mode = skill_registry.is_skill_active("response-contract", question)

    # Collect active skills and their triggers
    active_skills = []
    matched_triggers = []

    # Check all registered skills for this query
    for entry in skill_registry.list_skills():
        skill_name = entry.get("name", "")
        if skill_registry.is_skill_active(skill_name, question):
            active_skills.append(skill_name)

            # Get the skill entry to find which trigger matched
            skill_entry = skill_registry._entries.get(skill_name)
            if skill_entry and not skill_entry.auto_activate:
                query_lower = question.lower()
                for trigger in skill_entry.triggers:
                    if trigger.lower() in query_lower:
                        matched_triggers.append(f"{skill_name}:{trigger}")

    return StructuredModeContext(
        structured_mode=structured_mode,
        active_skill_names=active_skills,
        matched_triggers=matched_triggers,
        model_id=model_id,
    )


# =============================================================================
# Failure UX
# =============================================================================

@dataclass
class FailureResponse:
    """Controlled failure response for strict mode errors."""
    message: str
    request_id: str
    error_code: str
    can_retry: bool = True

    def to_user_message(self) -> str:
        """Generate user-facing error message."""
        base_msg = f"{self.message}"
        if self.can_retry:
            base_msg += " Please try again."
        base_msg += f"\n\nReference: {self.request_id}"
        return base_msg

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "error": True,
            "message": self.message,
            "request_id": self.request_id,
            "error_code": self.error_code,
            "can_retry": self.can_retry,
        }


def create_failure_response(
    reason_code: ReasonCode,
    request_id: str,
    details: Optional[str] = None,
) -> FailureResponse:
    """Create a controlled failure response.

    Maps internal reason codes to user-friendly messages.
    """
    messages = {
        ReasonCode.INVALID_JSON: "I couldn't format the result reliably.",
        ReasonCode.SCHEMA_MISSING_FIELD: "The response was missing required information.",
        ReasonCode.SCHEMA_TYPE_ERROR: "The response contained invalid data types.",
        ReasonCode.INVARIANT_VIOLATION: "The response contained inconsistent data.",
        ReasonCode.EXTRACTION_FAILED: "I couldn't extract structured data from the response.",
        ReasonCode.REPAIR_FAILED: "I couldn't repair the response format.",
    }

    message = messages.get(reason_code, "An unexpected error occurred.")

    return FailureResponse(
        message=message,
        request_id=request_id,
        error_code=reason_code.value,
        can_retry=True,
    )


# =============================================================================
# Items Total Population
# =============================================================================

def populate_items_total_from_weaviate(
    response: StructuredResponse,
    collection_counts: dict[str, int],
) -> StructuredResponse:
    """Overwrite LLM's items_total with Weaviate count/aggregate values.

    Best practice: items_total comes from the retrieval layer (authoritative),
    not from LLM guessing.

    Args:
        response: Parsed structured response
        collection_counts: Dict of {collection_name: count} from Weaviate aggregate

    Returns:
        Updated StructuredResponse with accurate items_total
    """
    if not collection_counts:
        return response

    # Calculate total from all relevant collections
    total_items = sum(collection_counts.values())

    # Only overwrite if we have a meaningful count
    if total_items > 0:
        # If LLM provided a different value, log for debugging
        if response.items_total is not None and response.items_total != total_items:
            logger.debug(
                f"Overwriting LLM items_total={response.items_total} "
                f"with Weaviate count={total_items}"
            )

        response.items_total = total_items
        response.count_qualifier = "exact"  # Weaviate counts are authoritative

    return response


# =============================================================================
# Main Gateway Function
# =============================================================================

# Enforcement policies
POLICY_STRICT = "strict"   # Fail with controlled error if JSON invalid
POLICY_SOFT = "soft"       # Degrade to raw text
POLICY_LENIENT = "lenient" # Allow embedded JSON extraction


@dataclass
class GatewayResult:
    """Result from the response gateway."""
    response: str
    is_structured: bool
    context: StructuredModeContext
    structured_response: Optional[StructuredResponse] = None
    failure: Optional[FailureResponse] = None

    def to_api_response(self) -> dict:
        """Convert to API response format."""
        result = {
            "response": self.response,
            "is_structured": self.is_structured,
            "request_id": self.context.request_id,
        }

        if self.structured_response:
            result["structured_data"] = self.structured_response.to_dict()

        if self.failure:
            result["error"] = self.failure.to_dict()

        return result


def normalize_and_validate_response(
    raw_response: str,
    context: StructuredModeContext,
    policy: str = POLICY_STRICT,
    collection_counts: Optional[dict[str, int]] = None,
    retry_func: Optional[Callable[[str], str]] = None,
) -> GatewayResult:
    """Unified response gateway - all UI API responses must pass through this.

    This is the single entry point for processing LLM output before
    returning to the UI. It enforces the response contract.

    Args:
        raw_response: Raw LLM/CLI output text
        context: Structured mode context with metadata
        policy: Enforcement policy ("strict", "soft", "lenient")
        collection_counts: Optional Weaviate counts to populate items_total
        retry_func: Optional function to call for retry (receives JSON-only prompt)

    Returns:
        GatewayResult with processed response and metadata
    """
    import time
    start_time = time.time()

    metrics = ResponseMetrics.get_instance()

    # Log context for observability
    logger.info(
        f"Gateway processing: request_id={context.request_id}, "
        f"structured_mode={context.structured_mode}, "
        f"active_skills={context.active_skill_names}, "
        f"policy={policy}"
    )

    # If not in structured mode, return raw response
    if not context.structured_mode:
        context.parse_stage = "bypass"
        context.reason_code = ReasonCode.SUCCESS
        context.latency_ms = int((time.time() - start_time) * 1000)

        return GatewayResult(
            response=raw_response,
            is_structured=False,
            context=context,
        )

    # Extract JSON using CLI delimiter protocol
    strict_extraction = (policy == POLICY_STRICT)
    json_str, extraction_method = extract_json_with_delimiters(
        raw_response,
        strict=strict_extraction
    )
    context.extraction_method = extraction_method

    # If no JSON found in strict mode
    if json_str is None and policy == POLICY_STRICT:
        context.parse_stage = "extraction_failed"
        context.reason_code = ReasonCode.EXTRACTION_FAILED
        context.latency_ms = int((time.time() - start_time) * 1000)

        metrics.increment("final_failed")
        metrics.record_failure(ReasonCode.EXTRACTION_FAILED)

        failure = create_failure_response(
            ReasonCode.EXTRACTION_FAILED,
            context.request_id,
        )

        logger.warning(
            f"Extraction failed: request_id={context.request_id}, "
            f"method={extraction_method}"
        )
        logger.debug(f"Raw response (sanitized): {raw_response[:500]}")

        return GatewayResult(
            response=failure.to_user_message(),
            is_structured=False,
            context=context,
            failure=failure,
        )

    # Fallback to embedded extraction for non-strict modes
    if json_str is None:
        json_str = ResponseParser.extract_json(raw_response)
        context.extraction_method = "parser_fallback"

    # If still no JSON, handle based on policy
    if json_str is None:
        context.parse_stage = "no_json"
        context.reason_code = ReasonCode.EXTRACTION_FAILED
        context.latency_ms = int((time.time() - start_time) * 1000)

        if policy == POLICY_SOFT:
            logger.info(f"Soft mode: returning raw response for {context.request_id}")
            return GatewayResult(
                response=raw_response,
                is_structured=False,
                context=context,
            )

        # Lenient mode: also return raw
        return GatewayResult(
            response=raw_response,
            is_structured=False,
            context=context,
        )

    # Parse and validate the extracted JSON
    response, errors, reason_code = ResponseValidator.parse_and_validate(json_str)
    context.parse_stage = "validated" if response else "validation_failed"
    context.reason_code = reason_code

    if response is None:
        # Try repair
        repaired = ResponseParser.repair_json(json_str)
        if repaired:
            response, errors, reason_code = ResponseValidator.parse_and_validate(repaired)
            context.parse_stage = "repaired" if response else "repair_failed"
            context.reason_code = reason_code

    # Handle validation failure
    if response is None:
        context.latency_ms = int((time.time() - start_time) * 1000)

        metrics.increment("final_failed")
        metrics.record_failure(reason_code)

        logger.warning(
            f"Validation failed: request_id={context.request_id}, "
            f"reason={reason_code}, errors={errors}"
        )

        if policy == POLICY_STRICT:
            failure = create_failure_response(reason_code, context.request_id)
            return GatewayResult(
                response=failure.to_user_message(),
                is_structured=False,
                context=context,
                failure=failure,
            )

        # Soft/lenient: return raw response
        return GatewayResult(
            response=raw_response,
            is_structured=False,
            context=context,
        )

    # Success! Populate items_total from Weaviate if available
    if collection_counts:
        response = populate_items_total_from_weaviate(response, collection_counts)

    # Generate final response with transparency message
    transparency = response.generate_transparency_message()
    if transparency and transparency not in response.answer:
        final_response = f"{response.answer}\n\n{transparency}"
    else:
        final_response = response.answer

    context.latency_ms = int((time.time() - start_time) * 1000)

    # Record success metrics
    stage_metric = {
        "validated": "direct_parse_ok",
        "repaired": "repair_ok",
    }.get(context.parse_stage, "extract_ok")
    metrics.increment(stage_metric)

    logger.info(
        f"Gateway success: request_id={context.request_id}, "
        f"stage={context.parse_stage}, latency_ms={context.latency_ms}"
    )

    return GatewayResult(
        response=final_response,
        is_structured=True,
        context=context,
        structured_response=response,
    )


# =============================================================================
# JSON Prompt Instructions with Delimiter Protocol
# =============================================================================

STRUCTURED_MODE_INSTRUCTIONS = f"""
OUTPUT FORMAT REQUIREMENT:
You MUST output ONLY valid JSON. No prose, no explanations outside the JSON.

Use this exact format:
{JSON_START_MARKER}
{{
    "schema_version": "{CURRENT_SCHEMA_VERSION}",
    "answer": "Your response text here",
    "items_shown": <integer: number of items in your answer>,
    "items_total": <integer or null: total from COLLECTION COUNTS>,
    "count_qualifier": "exact" | "at_least" | "approx" | null,
    "sources": [{{"title": "...", "type": "ADR|Principle|Policy|Vocabulary"}}]
}}
{JSON_END_MARKER}

RULES:
- Response MUST be wrapped in {JSON_START_MARKER} and {JSON_END_MARKER} markers
- JSON MUST be valid - no trailing commas, properly quoted strings
- items_shown: count of items you mention in your answer
- items_total: use the EXACT value from COLLECTION COUNTS (do not estimate)
- If you're unsure of total count, set items_total to null
"""


def get_structured_mode_system_prompt(base_prompt: str) -> str:
    """Inject structured mode instructions into system prompt.

    Args:
        base_prompt: Base system prompt

    Returns:
        Enhanced prompt with structured mode instructions
    """
    return f"{base_prompt}\n\n{STRUCTURED_MODE_INSTRUCTIONS}"


# =============================================================================
# Convenience Functions
# =============================================================================

def log_gateway_stats() -> dict:
    """Get gateway statistics for observability dashboards."""
    metrics = ResponseMetrics.get_instance()
    stats = metrics.get_stats()

    return {
        "parsing": stats,
        "prompt_version": PROMPT_VERSION,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "json_markers": {
            "start": JSON_START_MARKER,
            "end": JSON_END_MARKER,
        },
    }
