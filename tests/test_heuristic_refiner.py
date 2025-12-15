"""Tests for heuristic-refiner system.

REQ-RC-014: Collect User Feedback via Ratings
REQ-RC-019: Characterize Articles for Refinement
REQ-RC-020: Collect Heuristic-Refiner Feedback
REQ-RC-021: Refine Prompts from Daily Feedback
REQ-RC-022: Display Prompt Evolution History
REQ-RC-023: Customize Application Appearance
"""

import pytest

from reader.db.repository import (
    AppSettingsRepository,
    ArticleRepository,
    HeuristicFeedbackRepository,
    PromptGenerationRepository,
)
from reader.models.article import ArticleCreate, ThumbsRating
from reader.models.scoring import HeuristicFeedbackCreate


class TestThumbsRating:
    """REQ-RC-014: Tests for thumbs up/down rating system."""

    def test_thumbs_rating_values(self) -> None:
        """REQ-RC-014: Thumbs ratings should be -1, 0, or 1."""
        assert ThumbsRating.DOWN == -1
        assert ThumbsRating.NONE == 0
        assert ThumbsRating.UP == 1

    def test_update_rating_thumbs_up(self) -> None:
        """REQ-RC-014: Can set thumbs up rating."""
        repo = ArticleRepository()

        # Create article
        article = ArticleCreate(
            source="test:source",
            title="Test Article",
            content_markdown="Test content",
        )
        article_id = repo.create(article)

        # Set thumbs up
        repo.update_rating(article_id, 1)

        # Verify
        result = repo.get_by_id(article_id)
        assert result is not None
        assert result.user_rating == 1

    def test_update_rating_thumbs_down(self) -> None:
        """REQ-RC-014: Can set thumbs down rating."""
        repo = ArticleRepository()

        article = ArticleCreate(
            source="test:source",
            title="Test Article",
            content_markdown="Test content",
        )
        article_id = repo.create(article)

        repo.update_rating(article_id, -1)

        result = repo.get_by_id(article_id)
        assert result is not None
        assert result.user_rating == -1

    def test_update_rating_clear(self) -> None:
        """REQ-RC-014: Can clear rating."""
        repo = ArticleRepository()

        article = ArticleCreate(
            source="test:source",
            title="Test Article",
            content_markdown="Test content",
        )
        article_id = repo.create(article)

        repo.update_rating(article_id, 1)
        repo.update_rating(article_id, 0)

        result = repo.get_by_id(article_id)
        assert result is not None
        assert result.user_rating == 0

    def test_update_rating_invalid_value(self) -> None:
        """REQ-RC-014: Invalid ratings should raise error."""
        repo = ArticleRepository()

        article = ArticleCreate(
            source="test:source",
            title="Test Article",
            content_markdown="Test content",
        )
        article_id = repo.create(article)

        with pytest.raises(ValueError):
            repo.update_rating(article_id, 5)

        with pytest.raises(ValueError):
            repo.update_rating(article_id, -2)


class TestPromptGenerations:
    """REQ-RC-021, REQ-RC-022: Tests for prompt generation system."""

    def test_create_generation(self) -> None:
        """REQ-RC-021: Can create prompt generations."""
        repo = PromptGenerationRepository()

        gen_id = repo.create(
            prompt_text="Test prompt",
            diff_from_previous=None,
            feedback_count=0,
            set_active=True,
        )
        assert gen_id > 0

        gen = repo.get_by_id(gen_id)
        assert gen is not None
        assert gen.prompt_text == "Test prompt"
        assert gen.is_active is True

    def test_get_active_generation(self) -> None:
        """REQ-RC-021: Can get active generation."""
        repo = PromptGenerationRepository()

        # Create first generation
        gen1_id = repo.create(
            prompt_text="Generation 1",
            set_active=True,
        )

        # Create second generation as active
        gen2_id = repo.create(
            prompt_text="Generation 2",
            set_active=True,
        )

        # Only gen2 should be active
        active = repo.get_active()
        assert active is not None
        assert active.id == gen2_id
        assert active.is_active is True

        # gen1 should be inactive
        gen1 = repo.get_by_id(gen1_id)
        assert gen1 is not None
        assert gen1.is_active is False

    def test_get_all_generations(self) -> None:
        """REQ-RC-022: Can list all generations."""
        repo = PromptGenerationRepository()

        repo.create(prompt_text="Gen 1")
        repo.create(prompt_text="Gen 2")
        repo.create(prompt_text="Gen 3")

        generations = repo.get_all()
        assert len(generations) == 3
        # Ordered by ID descending
        assert generations[0].prompt_text == "Gen 3"
        assert generations[2].prompt_text == "Gen 1"


class TestHeuristicFeedback:
    """REQ-RC-019, REQ-RC-020: Tests for heuristic feedback collection."""

    def test_create_feedback(self) -> None:
        """REQ-RC-020: Can create heuristic feedback."""
        article_repo = ArticleRepository()
        feedback_repo = HeuristicFeedbackRepository()

        # Create article
        article = ArticleCreate(
            source="test:source",
            title="Test Article",
            content_markdown="Test content",
        )
        article_id = article_repo.create(article)

        # Create feedback
        feedback = HeuristicFeedbackCreate(
            article_id=article_id,
            feedback_text="I liked this because of the technical depth",
        )
        feedback_id = feedback_repo.create(feedback)
        assert feedback_id > 0

        # Verify
        result = feedback_repo.get_by_article(article_id)
        assert result is not None
        assert result.feedback_text == "I liked this because of the technical depth"

    def test_create_feedback_with_characterization(self) -> None:
        """REQ-RC-019: Feedback can include 5-Whats characterization."""
        article_repo = ArticleRepository()
        feedback_repo = HeuristicFeedbackRepository()

        article = ArticleCreate(
            source="test:source",
            title="Test Article",
            content_markdown="Test content",
        )
        article_id = article_repo.create(article)

        char_json = '{"topic":"Rust memory","style":"tutorial","depth":"deep","emotion":"neutral","level":"intermediate"}'
        feedback = HeuristicFeedbackCreate(
            article_id=article_id,
            feedback_text="Great tutorial",
            characterization_json=char_json,
        )
        feedback_repo.create(feedback)

        result = feedback_repo.get_by_article(article_id)
        assert result is not None
        assert result.characterization is not None
        assert result.characterization.topic == "Rust memory"
        assert result.characterization.style == "tutorial"

    def test_link_feedback_to_generation(self) -> None:
        """REQ-RC-021: Feedback can be linked to generations."""
        article_repo = ArticleRepository()
        feedback_repo = HeuristicFeedbackRepository()
        gen_repo = PromptGenerationRepository()

        # Create article
        article = ArticleCreate(
            source="test:source",
            title="Test Article",
            content_markdown="Test content",
        )
        article_id = article_repo.create(article)

        # Create feedback
        feedback = HeuristicFeedbackCreate(
            article_id=article_id,
            feedback_text="Test feedback",
        )
        feedback_id = feedback_repo.create(feedback)

        # Create generation
        gen_id = gen_repo.create(
            prompt_text="New prompt",
            feedback_count=1,
        )

        # Link feedback
        feedback_repo.link_to_generation([feedback_id], gen_id)

        # Verify
        linked = feedback_repo.get_by_generation(gen_id)
        assert len(linked) == 1
        assert linked[0].id == feedback_id


class TestAppSettings:
    """REQ-RC-023: Tests for application settings."""

    def test_get_default_title(self) -> None:
        """REQ-RC-023: Default title should be 'nerd-reader'."""
        repo = AppSettingsRepository()
        settings = repo.get_all()
        assert settings.app_title == "nerd-reader"

    def test_update_title(self) -> None:
        """REQ-RC-023: Can update application title."""
        repo = AppSettingsRepository()

        repo.update_app_title("My Custom Reader")

        settings = repo.get_all()
        assert settings.app_title == "My Custom Reader"

    def test_get_set_arbitrary_setting(self) -> None:
        """REQ-RC-023: Can store arbitrary settings."""
        repo = AppSettingsRepository()

        repo.set("custom_key", "custom_value")

        value = repo.get("custom_key")
        assert value == "custom_value"

    def test_get_nonexistent_setting_default(self) -> None:
        """REQ-RC-023: Nonexistent settings return default."""
        repo = AppSettingsRepository()

        value = repo.get("nonexistent", "default_value")
        assert value == "default_value"


class TestRatingRefined:
    """REQ-RC-014: Tests for rating_refined flag."""

    def test_mark_rating_refined(self) -> None:
        """REQ-RC-014: Can mark article as having provided refinement feedback."""
        repo = ArticleRepository()

        article = ArticleCreate(
            source="test:source",
            title="Test Article",
            content_markdown="Test content",
        )
        article_id = repo.create(article)

        # Initially not refined
        result = repo.get_by_id(article_id)
        assert result is not None
        assert result.rating_refined is False

        # Mark as refined
        repo.mark_rating_refined(article_id, refined=True)

        result = repo.get_by_id(article_id)
        assert result is not None
        assert result.rating_refined is True
