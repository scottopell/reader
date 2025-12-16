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
    prompt_version: str = Field(description="Prompt version used for this scoring (DEPRECATED)")


class PromptVersion(BaseModel):
    """A versioned scoring prompt (DEPRECATED: use PromptGeneration)."""

    id: int
    version: str = Field(description="Version identifier, e.g., 'v1'")
    prompt_text: str = Field(description="Full prompt template")
    created_at: datetime
    is_active: bool = Field(default=False, description="Whether this is the active prompt")


# REQ-RC-005, REQ-RC-021, REQ-RC-022: Prompt generation model
class PromptGeneration(BaseModel):
    """A prompt generation produced by the heuristic-refiner system.

    Generations are immutable, sequential, and self-describing.
    """

    id: int = Field(description="Generation number (1, 2, 3, ...)")
    prompt_text: str = Field(description="Full prompt text")
    created_at: datetime
    diff_from_previous: str | None = Field(
        default=None, description="Word-diff from previous generation"
    )
    feedback_count: int = Field(
        default=0, description="Number of feedback items that produced this"
    )
    is_active: bool = Field(
        default=False, description="Currently active generation for new scoring"
    )


# REQ-RC-019: 5-Whats characterization
class FiveWhats(BaseModel):
    """5-Whats article characterization for heuristic-refiner.

    REQ-RC-019: THE SYSTEM SHALL return a 5-Whats scorecard containing:
    topic, writing style, depth, emotional impact, and writing level
    """

    topic: str = Field(description="What is the article about?")
    style: str = Field(description="What writing style is used?")
    depth: str = Field(description="How deep is the coverage?")
    emotion: str = Field(description="What emotional impact does it have?")
    level: str = Field(description="What reading level is it written at?")


# REQ-RC-019, REQ-RC-020, REQ-RC-021: Heuristic feedback
class HeuristicFeedback(BaseModel):
    """User feedback collected via heuristic-refiner system."""

    id: int
    article_id: int
    feedback_text: str = Field(description="User-provided feedback text")
    characterization: FiveWhats | None = Field(
        default=None, description="5-Whats characterization from LLM"
    )
    created_at: datetime
    generation_id: int | None = Field(
        default=None, description="Generation this feedback produced (NULL until batch runs)"
    )


class HeuristicFeedbackCreate(BaseModel):
    """Data required to create heuristic feedback."""

    article_id: int
    feedback_text: str = Field(description="User-provided feedback text")
    characterization_json: str | None = Field(
        default=None, description="5-Whats JSON from characterization"
    )


# REQ-RC-023: App settings
class AppSettings(BaseModel):
    """Application settings from app_settings table."""

    app_title: str = Field(default="nerd-reader", description="Application title")
