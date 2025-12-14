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
    prompt_version: str = Field(description="Prompt version used for scoring")


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
    prompt_version: str | None = None
    scored_at: datetime | None = None

    # User decisions (REQ-RC-014)
    user_decision: UserDecision = UserDecision.PENDING
    user_rating: int | None = Field(default=None, ge=1, le=5)
    decided_at: datetime | None = None

    # Bundle (REQ-RC-009)
    in_bundle: bool = False
    bundle_added_at: datetime | None = None

    # Extraction status (REQ-RC-006)
    extraction_status: ExtractionStatus = ExtractionStatus.SUCCESS
    extraction_error: str | None = None
