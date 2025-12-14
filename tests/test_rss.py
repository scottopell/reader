"""Tests for RSS feed ingestion.

REQ-RC-002: Discover New Content from RSS Feeds
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from reader.ingestion.rss import (
    IngestionResult,
    RSSEntry,
    _can_fetch,
    _parse_entry,
)


class TestParseEntry:
    """Tests for _parse_entry function."""

    def test_parse_basic_entry(self) -> None:
        """Test parsing an entry with minimal fields."""
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda key, default="": {
            "title": "Test Article",
            "link": "https://example.com/article",
            "author": None,
        }.get(key, default)
        mock_entry.content = None
        mock_entry.summary = "<p>Summary text</p>"

        # Mock hasattr behavior
        def mock_hasattr(_obj: object, name: str) -> bool:
            if name == "content":
                return False
            if name == "summary":
                return True
            if name == "published_parsed":
                return False
            return False

        with patch("reader.ingestion.rss.hasattr", mock_hasattr):
            entry = _parse_entry(mock_entry)

        assert entry.title == "Test Article"
        assert entry.link == "https://example.com/article"
        assert entry.content_html == "<p>Summary text</p>"
        assert entry.published is None

    def test_parse_entry_with_content(self) -> None:
        """Test parsing an entry with full content."""
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda key, default="": {
            "title": "Full Content Article",
            "link": "https://example.com/full",
            "author": "John Doe",
        }.get(key, default)
        mock_entry.content = [{"value": "<article>Full HTML content</article>"}]
        mock_entry.published_parsed = (2024, 1, 15, 12, 0, 0, 0, 0, 0)

        entry = _parse_entry(mock_entry)

        assert entry.title == "Full Content Article"
        assert entry.link == "https://example.com/full"
        assert entry.author == "John Doe"
        assert entry.content_html == "<article>Full HTML content</article>"
        assert entry.published is not None
        assert entry.published.year == 2024
        assert entry.published.month == 1
        assert entry.published.day == 15


class TestCanFetch:
    """Tests for _can_fetch robots.txt checking."""

    def test_allows_when_no_robots(self) -> None:
        """Should allow fetching when robots.txt can't be read."""
        robot_parsers: dict[str, None] = {}

        with patch("reader.ingestion.rss.RobotFileParser") as mock_rp_class:
            mock_rp = MagicMock()
            mock_rp.read.side_effect = Exception("Connection refused")
            mock_rp_class.return_value = mock_rp

            result = _can_fetch("https://example.com/article", robot_parsers)

        assert result is True
        assert "https://example.com" in robot_parsers
        assert robot_parsers["https://example.com"] is None

    def test_respects_robots_disallow(self) -> None:
        """Should respect robots.txt Disallow rules."""
        robot_parsers: dict[str, MagicMock] = {}

        with patch("reader.ingestion.rss.RobotFileParser") as mock_rp_class:
            mock_rp = MagicMock()
            mock_rp.can_fetch.return_value = False
            mock_rp_class.return_value = mock_rp

            result = _can_fetch("https://example.com/private", robot_parsers)

        assert result is False

    def test_caches_robot_parser(self) -> None:
        """Should cache robot parsers per domain."""
        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = True
        robot_parsers: dict[str, MagicMock] = {"https://example.com": mock_rp}

        # Should use cached parser, not create new one
        result = _can_fetch("https://example.com/article", robot_parsers)

        assert result is True
        mock_rp.can_fetch.assert_called_once()


class TestRSSEntry:
    """Tests for RSSEntry dataclass."""

    def test_rss_entry_creation(self) -> None:
        """Test creating an RSSEntry."""
        entry = RSSEntry(
            title="Test",
            link="https://example.com",
            author="Author",
            content_html="<p>Content</p>",
            published=datetime(2024, 1, 1, tzinfo=UTC),
        )
        assert entry.title == "Test"
        assert entry.link == "https://example.com"
        assert entry.author == "Author"
        assert entry.content_html == "<p>Content</p>"
        assert entry.published is not None


class TestIngestionResult:
    """Tests for IngestionResult dataclass."""

    def test_ingestion_result_creation(self) -> None:
        """Test creating an IngestionResult."""
        result = IngestionResult(
            source_id=1,
            feed_url="https://example.com/feed",
            entries_found=10,
            entries_new=5,
            entries_scored=4,
            errors=["Error 1"],
        )
        assert result.source_id == 1
        assert result.entries_found == 10
        assert result.entries_new == 5
        assert result.entries_scored == 4
        assert len(result.errors) == 1

    def test_empty_result(self) -> None:
        """Test creating an empty result."""
        result = IngestionResult(
            source_id=1,
            feed_url="https://example.com/feed",
            entries_found=0,
            entries_new=0,
            entries_scored=0,
            errors=[],
        )
        assert result.entries_found == 0
        assert len(result.errors) == 0


class TestPoliteDelay:
    """Tests for polite crawling delays."""

    @pytest.mark.asyncio
    async def test_delay_within_bounds(self) -> None:
        """Delay should be between 1 and 5 seconds."""
        from reader.ingestion.rss import (
            MAX_DELAY_SECONDS,
            MIN_DELAY_SECONDS,
            _polite_delay,
        )

        # Mock sleep to capture the delay value
        delays: list[float] = []

        async def mock_sleep(delay: float) -> None:
            delays.append(delay)
            # Don't actually sleep in tests

        with patch("asyncio.sleep", mock_sleep):
            await _polite_delay()

        assert len(delays) == 1
        assert MIN_DELAY_SECONDS <= delays[0] <= MAX_DELAY_SECONDS
