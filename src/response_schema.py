"""Structured response schema for enterprise-grade LLM output validation.

This module defines the JSON contract for LLM responses, enabling:
- Deterministic validation (not regex-based)
- Stable CI tests
- Observability (parse success rate, field distributions)
- Controlled fallback chain
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Literal

logger = logging.getLogger(__name__)


class CountQualifier(str, Enum):
    """Qualifier for count values."""
    EXACT = "exact"
    AT_LEAST = "at_least"
    APPROX = "approx"


@dataclass
class StructuredResponse:
    """Structured response schema for LLM outputs.

    This is the contract between the LLM and the application.
    All responses should be parseable into this schema.
    """
    answer: str
    items_shown: int = 0
    items_total: Optional[int] = None
    count_qualifier: Optional[Literal["exact", "at_least", "approx"]] = None
    transparency_statement: Optional[str] = None
    sources: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "answer": self.answer,
            "items_shown": self.items_shown,
            "items_total": self.items_total,
            "count_qualifier": self.count_qualifier,
            "transparency_statement": self.transparency_statement,
            "sources": self.sources,
        }

    def generate_transparency_message(self) -> str:
        """Generate a consistent transparency message from numeric fields.

        This avoids phrasing drift by generating from structured data.
        """
        if self.items_total is None:
            return ""

        if self.count_qualifier == "at_least":
            return f"Showing {self.items_shown} of at least {self.items_total} total items"
        elif self.count_qualifier == "approx":
            return f"Showing {self.items_shown} of approximately {self.items_total} total items"
        else:
            if self.items_shown < self.items_total:
                return f"Showing {self.items_shown} of {self.items_total} total items"
            else:
                return f"Showing all {self.items_total} items"


class ValidationError(Exception):
    """Raised when response validation fails."""
    pass


class ResponseValidator:
    """Validates structured responses against schema and invariants."""

    REQUIRED_FIELDS = {"answer", "items_shown"}

    @classmethod
    def validate(cls, data: dict) -> tuple[bool, list[str]]:
        """Validate response data against schema and invariants.

        Args:
            data: Dictionary to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Check required fields
        for field_name in cls.REQUIRED_FIELDS:
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")

        if errors:
            return False, errors

        # Type validation
        if not isinstance(data.get("answer"), str):
            errors.append("'answer' must be a string")

        if not isinstance(data.get("items_shown"), int):
            errors.append("'items_shown' must be an integer")
        elif data["items_shown"] < 0:
            errors.append("'items_shown' must be >= 0")

        items_total = data.get("items_total")
        if items_total is not None:
            if not isinstance(items_total, int):
                errors.append("'items_total' must be an integer or null")
            elif items_total < 0:
                errors.append("'items_total' must be >= 0")
            elif isinstance(data.get("items_shown"), int) and items_total < data["items_shown"]:
                errors.append("'items_total' must be >= 'items_shown'")

        qualifier = data.get("count_qualifier")
        if qualifier is not None:
            valid_qualifiers = {"exact", "at_least", "approx"}
            if qualifier not in valid_qualifiers:
                errors.append(f"'count_qualifier' must be one of: {valid_qualifiers}")

        return len(errors) == 0, errors

    @classmethod
    def parse_and_validate(cls, json_str: str) -> tuple[Optional[StructuredResponse], list[str]]:
        """Parse JSON string and validate.

        Args:
            json_str: JSON string to parse

        Returns:
            Tuple of (StructuredResponse or None, list of error messages)
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return None, [f"JSON parse error: {e}"]

        is_valid, errors = cls.validate(data)
        if not is_valid:
            return None, errors

        return StructuredResponse(
            answer=data["answer"],
            items_shown=data["items_shown"],
            items_total=data.get("items_total"),
            count_qualifier=data.get("count_qualifier"),
            transparency_statement=data.get("transparency_statement"),
            sources=data.get("sources", []),
        ), []


class ResponseParser:
    """Parses LLM responses with fallback chain."""

    # JSON code block pattern
    JSON_BLOCK_PATTERN = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)
    # Standalone JSON object pattern
    JSON_OBJECT_PATTERN = re.compile(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', re.DOTALL)

    @classmethod
    def extract_json(cls, text: str) -> Optional[str]:
        """Extract JSON from text, handling markdown code blocks.

        Args:
            text: Raw LLM response text

        Returns:
            Extracted JSON string or None
        """
        # Try markdown code block first
        match = cls.JSON_BLOCK_PATTERN.search(text)
        if match:
            return match.group(1).strip()

        # Try to find standalone JSON object
        match = cls.JSON_OBJECT_PATTERN.search(text)
        if match:
            return match.group(0).strip()

        return None

    @classmethod
    def repair_json(cls, broken_json: str) -> Optional[str]:
        """Attempt to repair malformed JSON.

        Common repairs:
        - Add missing closing braces
        - Fix trailing commas
        - Quote unquoted keys

        Args:
            broken_json: Potentially malformed JSON string

        Returns:
            Repaired JSON string or None if unrepairable
        """
        if not broken_json:
            return None

        repaired = broken_json.strip()

        # Remove trailing commas before closing braces/brackets
        repaired = re.sub(r',\s*([}\]])', r'\1', repaired)

        # Count braces to check balance
        open_braces = repaired.count('{')
        close_braces = repaired.count('}')

        if open_braces > close_braces:
            repaired += '}' * (open_braces - close_braces)

        # Try to parse
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            return None

    @classmethod
    def parse_with_fallbacks(cls, response_text: str) -> tuple[Optional[StructuredResponse], str]:
        """Parse response with full fallback chain.

        Fallback order:
        1. Direct JSON parse
        2. Extract JSON from markdown/text
        3. JSON repair
        4. Return parse failure info

        Args:
            response_text: Raw LLM response

        Returns:
            Tuple of (StructuredResponse or None, fallback_used or error message)
        """
        # Fallback A: Try direct parse
        response, errors = ResponseValidator.parse_and_validate(response_text)
        if response:
            return response, "direct_parse"

        # Fallback A: Try extracting JSON from text
        extracted = cls.extract_json(response_text)
        if extracted:
            response, errors = ResponseValidator.parse_and_validate(extracted)
            if response:
                return response, "extracted_json"

            # Fallback A: Try repairing extracted JSON
            repaired = cls.repair_json(extracted)
            if repaired:
                response, errors = ResponseValidator.parse_and_validate(repaired)
                if response:
                    return response, "repaired_json"

        # Fallback B would be a retry with stricter constraints (done at caller level)
        # Fallback C would be LLM-based extraction (done at caller level)

        return None, f"parse_failed: {'; '.join(errors)}"


# JSON schema for LLM system prompt
RESPONSE_SCHEMA = """
{
    "answer": "Your response text here",
    "items_shown": <number of items in this response>,
    "items_total": <total items in database, or null if unknown>,
    "count_qualifier": "exact" | "at_least" | "approx" | null,
    "sources": [{"title": "...", "type": "ADR|Principle|Policy|Vocabulary"}]
}
"""

RESPONSE_SCHEMA_INSTRUCTIONS = """
CRITICAL: You MUST respond with valid JSON matching this schema:
{
    "answer": "Your response text here",
    "items_shown": <integer: number of items mentioned in your answer>,
    "items_total": <integer or null: total items in database from COLLECTION COUNTS>,
    "count_qualifier": "exact" | "at_least" | "approx" | null,
    "sources": [{"title": "source title", "type": "ADR|Principle|Policy|Vocabulary"}]
}

Rules:
- Response MUST be valid JSON only - no markdown, no prose outside JSON
- items_shown: count of items you're showing in this answer
- items_total: the total from COLLECTION COUNTS (not your guess)
- count_qualifier: use "exact" for precise counts, "at_least" for minimums, "approx" for estimates
- If COLLECTION COUNTS says "ADR: 18 total", then items_total=18 and count_qualifier="exact"
"""
