"""Elo rating calculation and pairwise comparison logic.

REQ-RC-024: Compare Article Relevance via Pairwise Ranking
REQ-RC-025: Initialize Elo Scores for New Articles
REQ-RC-026: Select Comparison Opponents Strategically
REQ-RC-027: Display Normalized Elo Scores to Users
"""

import math
from collections.abc import Sequence

from reader.models.elo import ComparisonOutcome, EloUpdate

# REQ-RC-025: Initial Elo rating for new articles
DEFAULT_ELO_RATING = 1500.0

# REQ-RC-024: K-factor for Elo updates (chess standard)
DEFAULT_K_FACTOR = 32.0

# REQ-RC-026: Number of comparisons to establish confidence
COMPARISONS_FOR_CONFIDENCE = 7


def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    """Calculate expected score for article A vs article B.

    REQ-RC-024: Use standard chess Elo expected score formula.

    Args:
        rating_a: Current Elo rating of article A
        rating_b: Current Elo rating of article B

    Returns:
        Expected score for A (0.0 to 1.0)
    """
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def calculate_elo_update(
    rating_a: float,
    rating_b: float,
    outcome: ComparisonOutcome,
    k_factor: float = DEFAULT_K_FACTOR,
) -> tuple[float, float]:
    """Calculate new Elo ratings after a pairwise comparison.

    REQ-RC-024: Update Elo ratings based on comparison outcome using standard formula.

    Args:
        rating_a: Current Elo rating of article A
        rating_b: Current Elo rating of article B
        outcome: Result of comparison (A_WINS, B_WINS, or TIE)
        k_factor: How much ratings change (higher = more volatile)

    Returns:
        Tuple of (new_rating_a, new_rating_b)
    """
    expected_a = calculate_expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a

    # Convert outcome to actual scores
    if outcome == ComparisonOutcome.A_WINS:
        actual_a, actual_b = 1.0, 0.0
    elif outcome == ComparisonOutcome.B_WINS:
        actual_a, actual_b = 0.0, 1.0
    else:  # TIE
        actual_a, actual_b = 0.5, 0.5

    # Calculate new ratings
    new_rating_a = rating_a + k_factor * (actual_a - expected_a)
    new_rating_b = rating_b + k_factor * (actual_b - expected_b)

    return new_rating_a, new_rating_b


def create_elo_update(
    article_a_id: int,
    article_b_id: int,
    rating_a: float,
    rating_b: float,
    outcome: ComparisonOutcome,
    k_factor: float = DEFAULT_K_FACTOR,
) -> EloUpdate:
    """Create an EloUpdate object with calculated new ratings.

    REQ-RC-024: Package Elo updates for persistence.

    Args:
        article_a_id: ID of article A
        article_b_id: ID of article B
        rating_a: Current Elo rating of article A
        rating_b: Current Elo rating of article B
        outcome: Result of comparison
        k_factor: K-factor for rating volatility

    Returns:
        EloUpdate with before/after ratings
    """
    new_rating_a, new_rating_b = calculate_elo_update(rating_a, rating_b, outcome, k_factor)

    return EloUpdate(
        article_a_id=article_a_id,
        article_b_id=article_b_id,
        article_a_elo_before=rating_a,
        article_a_elo_after=new_rating_a,
        article_b_elo_before=rating_b,
        article_b_elo_after=new_rating_b,
        k_factor=k_factor,
        outcome=outcome,
    )


def calculate_percentile(rating: float, all_ratings: Sequence[float]) -> float:
    """Calculate percentile rank for a given Elo rating.

    REQ-RC-027: Map unbounded Elo scores to 0-100 percentile for user display.

    Args:
        rating: Elo rating to rank
        all_ratings: All Elo ratings in the system

    Returns:
        Percentile rank (0.0 to 100.0)
    """
    if not all_ratings:
        return 50.0  # No comparison possible, return median

    count_below = sum(1 for r in all_ratings if r < rating)
    count_equal = sum(1 for r in all_ratings if r == rating)

    # Use average rank for tied values
    percentile = ((count_below + count_equal / 2.0) / len(all_ratings)) * 100.0

    return min(100.0, max(0.0, percentile))


def is_above_median(rating: float, all_ratings: Sequence[float]) -> bool:
    """Check if a rating is above the median (p50+).

    REQ-RC-027: Preserve REQ-RC-012 inbox filtering behavior with Elo percentiles.

    Args:
        rating: Elo rating to check
        all_ratings: All Elo ratings in the system

    Returns:
        True if rating is at or above the 50th percentile
    """
    percentile = calculate_percentile(rating, all_ratings)
    return percentile >= 50.0
