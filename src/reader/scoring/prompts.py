"""Scoring prompt management.

REQ-RC-005: Track Scoring Prompt Changes Over Time
"""

import logging
from datetime import UTC, datetime

from reader.db.connection import get_connection
from reader.models.scoring import PromptVersion

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = """You are helping curate a reading list for a software engineering manager with deep technical interests.

Interests (weighted by relevance):
- Systems programming, low-level performance, kernel work
- Weather/meteorology APIs and data processing
- Engineering management frameworks and practices
- Rust, distributed systems, infrastructure
- Deep technical explanations over surface-level news
- Long-form analysis over breaking news hot-takes

Dislikes:
- Product announcements unless they reveal interesting technical decisions
- Political hot-takes and inflammatory content
- Duplicate coverage of the same story
- Clickbait headlines
- Shallow "intro to X" content (senior-level reader)

Article to score:
Title: {title}
Source: {source}
Content preview: {content_preview}

Provide:
1. Relevance score (1-10, where 10 = definitely send to reading device)
2. Brief reasoning (1-2 sentences)
3. Estimated reading time category: 'quick' (<5min), 'medium' (5-15min), 'deep' (15+ min)
4. Suggested tags (max 3)

Respond in JSON:
{{
  "score": 8,
  "reasoning": "Brief explanation here",
  "reading_time": "medium",
  "tags": ["tag1", "tag2"]
}}"""

DEFAULT_VERSION = "v1"


def get_active_prompt() -> tuple[str, str]:
    """Get the active prompt from database, or seed default if none exists.

    REQ-RC-005: WHEN scoring prompt is updated
    THE SYSTEM SHALL version the prompt and track which articles used which version

    Returns:
        Tuple of (prompt_text, version)
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT version, prompt_text FROM prompt_versions WHERE is_active = 1"
        ).fetchone()

        if row:
            return row["prompt_text"], row["version"]

        # No active prompt - seed the default
        logger.info("No active prompt found, seeding default prompt as %s", DEFAULT_VERSION)
        conn.execute(
            """
            INSERT INTO prompt_versions (version, prompt_text, created_at, is_active)
            VALUES (?, ?, ?, 1)
            """,
            (DEFAULT_VERSION, DEFAULT_PROMPT, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        return DEFAULT_PROMPT, DEFAULT_VERSION


def get_prompt_by_version(version: str) -> PromptVersion | None:
    """Get a specific prompt version from the database.

    REQ-RC-005: Support looking up historical prompt versions.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, version, prompt_text, created_at, is_active FROM prompt_versions WHERE version = ?",
            (version,),
        ).fetchone()

        if row:
            return PromptVersion(
                id=row["id"],
                version=row["version"],
                prompt_text=row["prompt_text"],
                created_at=datetime.fromisoformat(row["created_at"]),
                is_active=bool(row["is_active"]),
            )
        return None


def create_prompt_version(version: str, prompt_text: str, set_active: bool = True) -> int:
    """Create a new prompt version.

    REQ-RC-005: WHEN scoring prompt is updated
    THE SYSTEM SHALL version the prompt

    Args:
        version: Version identifier (e.g., "v2")
        prompt_text: The prompt template text
        set_active: Whether to set this as the active prompt

    Returns:
        The ID of the created prompt version
    """
    with get_connection() as conn:
        if set_active:
            # Deactivate all existing prompts
            conn.execute("UPDATE prompt_versions SET is_active = 0")

        cursor = conn.execute(
            """
            INSERT INTO prompt_versions (version, prompt_text, created_at, is_active)
            VALUES (?, ?, ?, ?)
            """,
            (version, prompt_text, datetime.now(UTC).isoformat(), int(set_active)),
        )
        conn.commit()
        return cursor.lastrowid or 0


def list_prompt_versions() -> list[PromptVersion]:
    """List all prompt versions ordered by creation date.

    REQ-RC-005: Support viewing prompt version history.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, version, prompt_text, created_at, is_active FROM prompt_versions ORDER BY created_at DESC"
        ).fetchall()

        return [
            PromptVersion(
                id=row["id"],
                version=row["version"],
                prompt_text=row["prompt_text"],
                created_at=datetime.fromisoformat(row["created_at"]),
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]
