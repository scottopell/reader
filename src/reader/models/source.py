"""Feed source models."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Type of content source."""

    EMAIL = "email"
    RSS = "rss"


class FeedSourceCreate(BaseModel):
    """Data required to create a new feed source."""

    type: SourceType = Field(description="Source type: 'email' or 'rss'")
    identifier: str = Field(description="Email sender pattern or RSS URL")
    display_name: str | None = Field(default=None, description="Human-readable name")
    enabled: bool = Field(default=True, description="Whether source is active")
    check_interval_hours: int = Field(default=6, ge=1, le=168, description="Check interval")


class FeedSource(FeedSourceCreate):
    """Full feed source model with all fields."""

    id: int
    last_checked: datetime | None = None
    created_at: datetime
