"""Tests for the _has_user_content heuristic in chat_ui.py.

The heuristic returns True when the user's message is >2× longer than the
Persona's rewritten query AND >500 chars. Both conditions use strict > (not >=).
"""

import pytest

from aion.chat_ui import _has_user_content


class TestHasUserContentHeuristic:
    """Boundary tests — validates strict-greater-than thresholds."""

    @pytest.mark.parametrize("msg_len, rq_len, expected", [
        # Clearly above both thresholds
        (1000, 100, True),
        (600, 200, True),
        # msg exactly 2x+1 over rewrite, above 500
        (600, 250, True),   # 600 > 500 (250*2) and 600 > 500 — both True
        # msg exactly 2x over rewrite — fails strict > for first condition
        (600, 300, False),  # 600 > 600 → False (strict)
        # msg exactly 501 — passes second threshold
        (501, 200, True),
        # msg exactly 500 — fails second threshold (strict >)
        (500, 200, False),
        # msg below 500 even with large ratio
        (499, 100, False),
        # rewrite longer than message — both conditions fail
        (100, 200, False),
        # empty rewrite — rq_len=0, so first condition is 501 > 0 (True)
        (501, None, True),
        # empty message — both conditions fail
        (0, 0, False),
    ])
    def test_boundary(self, msg_len, rq_len, expected):
        message = "x" * msg_len
        rewritten = "x" * rq_len if rq_len is not None else None
        assert _has_user_content(message, rewritten) is expected

    def test_none_rewritten_query_treated_as_empty(self):
        """None rewritten_query → rq_len=0, only 500-char threshold applies."""
        assert _has_user_content("x" * 501, None) is True
        assert _has_user_content("x" * 500, None) is False

    def test_empty_rewritten_query_treated_as_empty(self):
        assert _has_user_content("x" * 501, "") is True
