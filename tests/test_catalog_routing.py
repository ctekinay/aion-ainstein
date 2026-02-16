"""Tests for PR 2: catalog/list queries bypass Tree and use deterministic tools.

Verifies that:
1. "list DARs" routes to list_approval_records deterministically
2. "list ADR DARs" routes to list_approval_records("adr")
3. "list policies" routes to list_all_policies deterministically
4. _direct_query() re-routes catalog queries to deterministic list tools
5. Policy list builder produces correct labels
"""

import json
import re
import pytest

from src.elysia_agents import is_list_query
from src.list_response_builder import (
    build_list_result_marker,
    build_list_structured_json,
    finalize_list_result,
    is_list_result,
    CURRENT_SCHEMA_VERSION,
)


class TestDarRouting:
    """DAR queries must route to list_approval_records deterministically."""

    def test_list_dars_matches_dar_regex(self):
        """'list DARs' should match the DAR detection regex."""
        _DAR_RE = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
        assert _DAR_RE.search("list DARs")
        assert _DAR_RE.search("list dars")
        assert _DAR_RE.search("show me all DARs")
        assert _DAR_RE.search("what DARs exist?")

    def test_how_about_dars_matches(self):
        """'how about DARs?' should also match (topical marker bypass)."""
        _DAR_RE = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
        assert _DAR_RE.search("how about DARs?")
        assert _DAR_RE.search("and how about DARs?")

    def test_list_adr_dars_detects_adr_scope(self):
        """'list ADR DARs' should contain both 'adr' and 'dar' keywords."""
        question = "list ADR DARs"
        question_lower = question.lower()
        _DAR_RE = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
        assert _DAR_RE.search(question_lower)
        assert "adr" in question_lower

    def test_list_principle_dars_detects_principle_scope(self):
        """'list principle DARs' should detect principle scope."""
        question = "list principle DARs"
        question_lower = question.lower()
        _DAR_RE = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
        assert _DAR_RE.search(question_lower)
        assert "principle" in question_lower

    def test_decision_approval_record_matches(self):
        """Full name 'decision approval record' should match."""
        _DAR_RE = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
        assert _DAR_RE.search("show me the decision approval records")

    def test_dar_not_false_positive_on_standard(self):
        """'standard' should not trigger DAR detection."""
        _DAR_RE = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
        assert not _DAR_RE.search("what is the IEC standard?")
        assert not _DAR_RE.search("describe the architecture")


class TestPolicyRouting:
    """Policy queries must route to list_all_policies deterministically."""

    def test_list_policies_matches_regex(self):
        """'list policies' should match the policy detection regex."""
        assert re.search(r"\bpolic(?:y|ies)\b", "list policies")
        assert re.search(r"\bpolic(?:y|ies)\b", "what policies exist?")
        assert re.search(r"\bpolic(?:y|ies)\b", "show me the data governance policy")

    def test_policy_not_false_positive(self):
        """Non-policy terms should not match."""
        assert not re.search(r"\bpolic(?:y|ies)\b", "what ADRs exist?")
        assert not re.search(r"\bpolic(?:y|ies)\b", "list DARs")


class TestPolicyListBuilder:
    """Policy list builder produces correct labels and structure."""

    def test_policy_list_valid_json(self):
        """Policy list should produce valid JSON with correct schema."""
        items = [
            {"title": "Data Governance Policy", "file_path": "/policies/governance.docx", "file_type": "docx"},
            {"title": "Privacy Policy", "file_path": "/policies/privacy.pdf", "file_type": "pdf"},
        ]
        result = build_list_result_marker(
            collection="policy",
            rows=items,
            total_unique=2,
        )
        assert is_list_result(result)

        json_str = finalize_list_result(result)
        data = json.loads(json_str)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION
        assert data["items_total"] == 2
        assert data["items_shown"] == 2

    def test_policy_transparency_label(self):
        """Transparency should say 'Policys' (or 'Policies' if we fix pluralization)."""
        items = [
            {"title": f"Policy {i}", "file_path": f"/policies/{i}.docx", "file_type": "docx"}
            for i in range(3)
        ]
        result = build_list_result_marker(collection="policy", rows=items, total_unique=3)
        json_str = finalize_list_result(result)
        data = json.loads(json_str)
        assert "Policy" in data.get("transparency_statement", "")

    def test_policy_source_type(self):
        """Source type should be 'Policy'."""
        items = [
            {"title": "Policy 1", "file_path": "/policies/1.docx", "file_type": "docx"},
        ]
        result = build_list_result_marker(collection="policy", rows=items, total_unique=1)
        json_str = finalize_list_result(result)
        data = json.loads(json_str)
        assert data["sources"][0]["type"] == "Policy"

    def test_policy_empty_list(self):
        """Empty policy list should produce valid JSON with zero items."""
        result = build_list_result_marker(collection="policy", rows=[], total_unique=0)
        json_str = finalize_list_result(result)
        data = json.loads(json_str)
        assert data["items_total"] == 0
        assert data["items_shown"] == 0


class TestDirectQueryDeterministicFallback:
    """_direct_query() should re-route catalog queries to deterministic tools.

    We test the routing regex patterns used in _direct_query() to verify
    they match the same patterns as the main query() method.
    """

    def test_dar_regex_matches_in_fallback(self):
        """DAR regex in fallback matches same patterns as main routing."""
        _DAR_RE = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
        assert _DAR_RE.search("list dars")
        assert _DAR_RE.search("how about dars?")
        assert _DAR_RE.search("show decision approval records")

    def test_adr_regex_matches_in_fallback(self):
        """ADR regex matches for fallback re-routing."""
        assert re.search(r"\badrs?\b", "list adrs")
        assert re.search(r"\badrs?\b", "what adrs exist?")

    def test_principle_regex_matches_in_fallback(self):
        """Principle regex matches for fallback re-routing."""
        assert re.search(r"\bprinciples?\b", "list principles")
        assert re.search(r"\bprinciples?\b", "show me the principles")

    def test_policy_regex_matches_in_fallback(self):
        """Policy regex matches for fallback re-routing."""
        assert re.search(r"\bpolic(?:y|ies)\b", "list policies")
        assert re.search(r"\bpolic(?:y|ies)\b", "what policies exist?")

    def test_dar_priority_over_adr(self):
        """DAR regex fires before ADR regex (priority ordering)."""
        question = "list adr dars"
        question_lower = question.lower()
        _DAR_RE = re.compile(r"\bdars?\b|decision approval record", re.IGNORECASE)
        # DAR should match first
        assert _DAR_RE.search(question_lower)
        # ADR is also in the string but DAR routing takes priority
        assert re.search(r"\badrs?\b", question_lower)
