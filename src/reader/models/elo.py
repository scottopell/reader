"""Elo-based pairwise comparison models.

REQ-RC-024: Compare Article Relevance via Pairwise Ranking
REQ-RC-025: Initialize Elo Scores for New Articles
REQ-RC-028: Track Comparison History for Transparency
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ComparisonOutcome(str, Enum):
    """Outcome of a pairwise comparison."""

    A_WINS = "a_wins"
    B_WINS = "b_wins"
    TIE = "tie"


class PairwiseComparisonRequest(BaseModel):
    """Request to compare two articles."""

    article_a_id: int
    article_b_id: int
    article_a_title: str
    article_b_title: str
    article_a_preview: str
    article_b_preview: str


class PairwiseComparisonResponse(BaseModel):
    """Response from LLM comparing two articles."""

    outcome: ComparisonOutcome = Field(
        description="Which article is more relevant: a_wins, b_wins, or tie"
    )
    reasoning: str = Field(description="Brief explanation of the comparison")


class EloUpdate(BaseModel):
    """Elo rating updates for both articles after comparison."""

    article_a_id: int
    article_b_id: int
    article_a_elo_before: float
    article_a_elo_after: float
    article_b_elo_before: float
    article_b_elo_after: float
    k_factor: float
    outcome: ComparisonOutcome


class EloComparisonRecord(BaseModel):
    """Record of a single pairwise comparison."""

    id: int
    article_a_id: int
    article_b_id: int
    winner_id: int | None
    llm_reasoning: str
    article_a_elo_before: float
    article_a_elo_after: float
    article_b_elo_before: float
    article_b_elo_after: float
    k_factor: float
    generation_id: int | None
    created_at: datetime


class EloComparisonCreate(BaseModel):
    """Data required to create an Elo comparison record."""

    article_a_id: int
    article_b_id: int
    winner_id: int | None
    llm_reasoning: str
    article_a_elo_before: float
    article_a_elo_after: float
    article_b_elo_before: float
    article_b_elo_after: float
    k_factor: float
    generation_id: int | None = None
