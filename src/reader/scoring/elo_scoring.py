"""Main Elo-based article scoring orchestration.

REQ-RC-024: Compare Article Relevance via Pairwise Ranking
REQ-RC-025: Initialize Elo Scores for New Articles
REQ-RC-026: Select Comparison Opponents Strategically
"""

import asyncio
import logging
import random

from reader.db.repository import ArticleRepository, EloComparisonRepository
from reader.models.article import Article
from reader.models.elo import ComparisonOutcome, EloComparisonCreate, PairwiseComparisonRequest
from reader.scoring.elo import (
    COMPARISONS_FOR_CONFIDENCE,
    DEFAULT_ELO_RATING,
    DEFAULT_K_FACTOR,
    create_elo_update,
)
from reader.scoring.pairwise import ComparisonError, compare_articles
from reader.scoring.prompts import get_active_generation

logger = logging.getLogger(__name__)


def select_opponents(
    article_repo: ArticleRepository, exclude_id: int, generation_id: int | None, count: int = 7
) -> list[Article]:
    """Select opponent articles for pairwise comparisons.

    REQ-RC-026: SELECT random articles from scored articles
    THE SYSTEM SHALL prefer articles from current prompt generation

    Args:
        article_repo: Article repository
        exclude_id: Article ID to exclude (the new article)
        generation_id: Current generation ID to prefer
        count: Number of opponents to select

    Returns:
        List of opponent articles (may be fewer than count if not enough articles)
    """
    # Get all scored articles (with Elo ratings) except the new one
    all_scored = article_repo.get_unscored(limit=1000)  # Reuse query, will filter below

    # Actually we need a better query - let me get all articles with elo_rating
    # For now, let's use a simple approach
    article_repo_conn = article_repo
    from reader.db.connection import get_connection

    with get_connection() as conn:
        # Prefer articles from current generation
        if generation_id:
            rows = conn.execute(
                """
                SELECT * FROM articles
                WHERE id != ? AND elo_rating IS NOT NULL AND generation_id = ?
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (exclude_id, generation_id, count),
            ).fetchall()

            articles = [article_repo._row_to_article(row) for row in rows]

            # If we don't have enough from current generation, add more from any generation
            if len(articles) < count:
                additional_needed = count - len(articles)
                rows = conn.execute(
                    """
                    SELECT * FROM articles
                    WHERE id != ? AND elo_rating IS NOT NULL
                    ORDER BY RANDOM()
                    LIMIT ?
                    """,
                    (exclude_id, additional_needed),
                ).fetchall()
                articles.extend([article_repo._row_to_article(row) for row in rows])
        else:
            # No generation preference, just get random scored articles
            rows = conn.execute(
                """
                SELECT * FROM articles
                WHERE id != ? AND elo_rating IS NOT NULL
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (exclude_id, count),
            ).fetchall()
            articles = [article_repo._row_to_article(row) for row in rows]

    return articles


async def score_article_with_elo(article_id: int) -> tuple[int, list[str]]:
    """Score a new article using Elo-based pairwise comparisons.

    REQ-RC-024: WHEN new article extracted
    THE SYSTEM SHALL perform pairwise comparisons with existing articles
    THE SYSTEM SHALL update Elo ratings based on outcomes

    REQ-RC-025: WHEN new article enters
    THE SYSTEM SHALL assign initial Elo 1500

    REQ-RC-026: WHEN selecting opponents
    THE SYSTEM SHALL select 7 random articles from scored articles

    Args:
        article_id: ID of article to score

    Returns:
        Tuple of (comparisons_completed, errors)
    """
    article_repo = ArticleRepository()
    elo_repo = EloComparisonRepository()

    # Get the article
    article = article_repo.get_by_id(article_id)
    if not article:
        return 0, [f"Article {article_id} not found"]

    # Get active generation for tracking
    _, generation_id = get_active_generation()

    # Select opponents (REQ-RC-026: 7 comparisons for confidence)
    opponents = select_opponents(
        article_repo, article_id, generation_id, count=COMPARISONS_FOR_CONFIDENCE
    )

    if not opponents:
        # No existing articles to compare with - this is the first article
        logger.info("Article %d is first article, no comparisons possible", article_id)
        return 0, []

    logger.info(
        "Scoring article %d with %d pairwise comparisons (requested %d)",
        article_id,
        len(opponents),
        COMPARISONS_FOR_CONFIDENCE,
    )

    # Perform comparisons
    errors = []
    comparisons_completed = 0

    for opponent in opponents:
        try:
            # Create comparison request
            comparison_request = PairwiseComparisonRequest(
                article_a_id=article_id,
                article_b_id=opponent.id,
                article_a_title=article.title,
                article_b_title=opponent.title,
                article_a_preview=article.content_markdown[
                    :500
                ],  # First 500 chars as preview
                article_b_preview=opponent.content_markdown[:500],
            )

            # Compare articles using LLM
            comparison_result = await compare_articles(comparison_request)

            # Calculate Elo updates
            current_elo = article.elo_rating or DEFAULT_ELO_RATING
            opponent_elo = opponent.elo_rating or DEFAULT_ELO_RATING

            elo_update = create_elo_update(
                article_a_id=article_id,
                article_b_id=opponent.id,
                rating_a=current_elo,
                rating_b=opponent_elo,
                outcome=comparison_result.outcome,
                k_factor=DEFAULT_K_FACTOR,
            )

            # Update article ratings in database
            article_repo.update_elo(article_id, elo_update.article_a_elo_after)
            article_repo.update_elo(opponent.id, elo_update.article_b_elo_after)

            # Determine winner_id for record
            if comparison_result.outcome == ComparisonOutcome.A_WINS:
                winner_id = article_id
            elif comparison_result.outcome == ComparisonOutcome.B_WINS:
                winner_id = opponent.id
            else:  # TIE
                winner_id = None

            # Record comparison in database (REQ-RC-028: Track comparison history)
            elo_comparison = EloComparisonCreate(
                article_a_id=article_id,
                article_b_id=opponent.id,
                winner_id=winner_id,
                llm_reasoning=comparison_result.reasoning,
                article_a_elo_before=elo_update.article_a_elo_before,
                article_a_elo_after=elo_update.article_a_elo_after,
                article_b_elo_before=elo_update.article_b_elo_before,
                article_b_elo_after=elo_update.article_b_elo_after,
                k_factor=elo_update.k_factor,
                generation_id=generation_id,
            )
            elo_repo.create(elo_comparison)

            # Update current Elo for next comparison
            article.elo_rating = elo_update.article_a_elo_after
            comparisons_completed += 1

            logger.info(
                "Comparison %d/%d: Article %d (%.1f → %.1f) vs %d (%.1f → %.1f) - %s",
                comparisons_completed,
                len(opponents),
                article_id,
                elo_update.article_a_elo_before,
                elo_update.article_a_elo_after,
                opponent.id,
                elo_update.article_b_elo_before,
                elo_update.article_b_elo_after,
                comparison_result.outcome.value,
            )

        except ComparisonError as e:
            error_msg = f"Comparison with article {opponent.id} failed: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)
            continue

    logger.info(
        "Scored article %d: %d comparisons completed, final Elo: %.1f",
        article_id,
        comparisons_completed,
        article.elo_rating or DEFAULT_ELO_RATING,
    )

    return comparisons_completed, errors
