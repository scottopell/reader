"""Tests for search functionality.

REQ-RC-011: Find Past Articles
"""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from reader.db.repository import ArticleRepository


class TestSearchSanitization:
    """Test that search handles arbitrary input without crashing."""

    @given(st.text(max_size=100))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_search_handles_arbitrary_text(self, query: str) -> None:
        """REQ-RC-011: Search should not crash on any input.

        Property: For any string input, search() returns a list (possibly empty)
        without raising an exception.
        """
        repo = ArticleRepository()
        # Should not raise any exception
        result = repo.search(query)
        assert isinstance(result, list)

    @pytest.mark.parametrize(
        "query",
        [
            "*",  # FTS5 wildcard
            "**",
            '"',  # Quote
            '""',
            "OR",  # FTS5 operators
            "AND",
            "NOT",
            "NEAR",
            "()",  # Parentheses
            "((()))",
            "test OR crash",
            '"unmatched',
            "col:value",  # Column filter syntax
            "-excluded",  # Negation
            "^prefix",  # Prefix operator
            "",  # Empty
            "   ",  # Whitespace only
            "\n\t",  # Special whitespace
        ],
    )
    def test_search_handles_special_characters(self, query: str) -> None:
        """REQ-RC-011: Search should handle FTS5 special syntax safely."""
        repo = ArticleRepository()
        result = repo.search(query)
        assert isinstance(result, list)
