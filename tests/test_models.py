"""Tests for Pydantic models."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from reader.models.article import ArticleCreate, ArticleScore, ReadingTimeCategory
from reader.models.scoring import ScoringResponse


class TestArticleCreate:
    """Tests for ArticleCreate model."""

    def test_minimal_article(self) -> None:
        """Test creating article with required fields only."""
        article = ArticleCreate(
            source="rss:https://example.com/feed",
            title="Test Article",
            content_markdown="# Hello\n\nThis is content.",
        )
        assert article.source == "rss:https://example.com/feed"
        assert article.title == "Test Article"
        assert article.url is None
        assert article.author is None

    def test_full_article(self) -> None:
        """Test creating article with all fields."""
        article = ArticleCreate(
            source="email:newsletter@example.com",
            title="Full Article",
            url="https://example.com/article",
            author="John Doe",
            content_markdown="Content here",
        )
        assert article.url == "https://example.com/article"
        assert article.author == "John Doe"


class TestArticleScore:
    """Tests for ArticleScore model."""

    def test_valid_score(self) -> None:
        """Test valid scoring data."""
        score = ArticleScore(
            llm_score=8.5,
            llm_reasoning="Great technical depth",
            reading_time_category=ReadingTimeCategory.MEDIUM,
            tags=["rust", "systems"],
            prompt_version="v1",
        )
        assert score.llm_score == 8.5
        assert len(score.tags) == 2

    def test_score_boundaries(self) -> None:
        """Test score must be between 1 and 10."""
        with pytest.raises(ValueError):
            ArticleScore(
                llm_score=0.5,  # Too low
                llm_reasoning="Test",
                reading_time_category=ReadingTimeCategory.QUICK,
                prompt_version="v1",
            )

        with pytest.raises(ValueError):
            ArticleScore(
                llm_score=10.5,  # Too high
                llm_reasoning="Test",
                reading_time_category=ReadingTimeCategory.QUICK,
                prompt_version="v1",
            )

    # Hypothesis property-based test
    @given(score=st.floats(min_value=1.0, max_value=10.0, allow_nan=False))
    def test_valid_scores_accepted(self, score: float) -> None:
        """Any score between 1 and 10 should be valid."""
        article_score = ArticleScore(
            llm_score=score,
            llm_reasoning="Test reasoning",
            reading_time_category=ReadingTimeCategory.MEDIUM,
            prompt_version="v1",
        )
        assert 1.0 <= article_score.llm_score <= 10.0


class TestScoringResponse:
    """Tests for ScoringResponse model (LLM output)."""

    def test_parse_llm_response(self) -> None:
        """Test parsing a typical LLM JSON response."""
        response = ScoringResponse(
            score=7.5,
            reasoning="Interesting analysis of distributed systems",
            reading_time=ReadingTimeCategory.DEEP,
            tags=["distributed", "architecture"],
            prompt_version="v1",
        )
        assert response.score == 7.5
        assert response.reading_time == ReadingTimeCategory.DEEP
        assert response.prompt_version == "v1"
