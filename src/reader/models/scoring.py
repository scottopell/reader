"""Scoring-related models."""

from datetime import datetime

from pydantic import BaseModel, Field

from reader.models.article import ReadingTimeCategory


class ScoringRequest(BaseModel):
    """Request to score an article."""

    article_id: int
    title: str
    source: str
    content_preview: str = Field(description="First ~500 words of content")


class ScoringResponse(BaseModel):
    """Response from LLM scoring."""

    score: float = Field(ge=1.0, le=10.0, description="Relevance score 1-10")
    reasoning: str = Field(description="Brief explanation of score")
    reading_time: ReadingTimeCategory = Field(description="Estimated reading time")
    tags: list[str] = Field(default_factory=list, max_length=5, description="Suggested tags")
    prompt_version: str = Field(description="Prompt version used for this scoring")


class PromptVersion(BaseModel):
    """A versioned scoring prompt."""

    id: int
    version: str = Field(description="Version identifier, e.g., 'v1'")
    prompt_text: str = Field(description="Full prompt template")
    created_at: datetime
    is_active: bool = Field(default=False, description="Whether this is the active prompt")
