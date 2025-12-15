"""Article models."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReadingTimeCategory(str, Enum):
    """Estimated reading time category."""

    QUICK = "quick"  # <5 min
    MEDIUM = "medium"  # 5-15 min
    DEEP = "deep"  # 15+ min


class UserDecision(str, Enum):
    """User decision on an article."""

    PENDING = "pending"
    SENT = "sent"
    SKIPPED = "skipped"
    READ = "read"


class ExtractionStatus(str, Enum):
    """Content extraction status."""

    SUCCESS = "success"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


# REQ-RC-014: Thumbs rating values
class ThumbsRating(int, Enum):
    """User rating using thumbs up/down system."""

    DOWN = -1  # Thumbs down
    NONE = 0  # No rating
    UP = 1  # Thumbs up


class ArticleCreate(BaseModel):
    """Data required to create a new article."""

    source: str = Field(description="Source identifier, e.g., 'email:sender@domain.com'")
    title: str = Field(description="Article title")
    url: str | None = Field(default=None, description="Original article URL")
    author: str | None = Field(default=None, description="Article author")
    content_markdown: str = Field(description="Article content as Markdown")
    word_count: int | None = Field(default=None, description="Word count")
    extraction_status: ExtractionStatus = Field(
        default=ExtractionStatus.SUCCESS, description="Extraction status"
    )
    extraction_error: str | None = Field(default=None, description="Extraction error message")


class ArticleScore(BaseModel):
    """LLM scoring results for an article."""

    llm_score: float = Field(ge=1.0, le=10.0, description="Relevance score 1-10")
    llm_reasoning: str = Field(description="Brief explanation of score")
    reading_time_category: ReadingTimeCategory = Field(description="Estimated reading time")
    tags: list[str] = Field(default_factory=list, description="Suggested tags")
    prompt_version: str = Field(description="Prompt version used for scoring (DEPRECATED)")
    generation_id: int | None = Field(default=None, description="Prompt generation ID")


class Article(BaseModel):
    """Full article model with all fields."""

    id: int
    source: str
    title: str
    url: str | None = None
    author: str | None = None
    content_markdown: str
    received_at: datetime
    word_count: int | None = None

    # Scoring (REQ-RC-004)
    llm_score: float | None = None
    llm_reasoning: str | None = None
    reading_time_category: ReadingTimeCategory | None = None
    tags: list[str] = Field(default_factory=list)
    scored_at: datetime | None = None

    # REQ-RC-005: Prompt versioning (DEPRECATED: use generation_id)
    prompt_version: str | None = None

    # REQ-RC-005, REQ-RC-008: Prompt generation tracking
    generation_id: int | None = None

    # REQ-RC-024, REQ-RC-025: Elo-based pairwise comparison scoring
    elo_rating: float = Field(default=1500.0, description="Elo rating from pairwise comparisons")
    elo_comparisons: int = Field(default=0, description="Number of pairwise comparisons completed")
    elo_confidence: bool = Field(
        default=False, description="Whether article has stable Elo (7+ comparisons)"
    )

    # User decisions (REQ-RC-014)
    user_decision: UserDecision = UserDecision.PENDING
    decided_at: datetime | None = None

    # REQ-RC-014: User rating (thumbs up/down: -1, 0, 1)
    user_rating: int = Field(default=0, ge=-1, le=1)
    rating_refined: bool = False
    rated_at: datetime | None = None

    # Bundle (REQ-RC-009)
    in_bundle: bool = False
    bundle_added_at: datetime | None = None

    # Extraction status (REQ-RC-006)
    extraction_status: ExtractionStatus = ExtractionStatus.SUCCESS
    extraction_error: str | None = None
