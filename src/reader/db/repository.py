"""Repository for database operations."""

import json
import sqlite3
from datetime import UTC, datetime

from reader.db.connection import get_connection
from reader.models.article import Article, ArticleCreate, ArticleScore, UserDecision
from reader.models.elo import EloComparisonCreate, EloComparisonRecord
from reader.models.scoring import (
    AppSettings,
    FiveWhats,
    HeuristicFeedback,
    HeuristicFeedbackCreate,
    PromptGeneration,
)
from reader.models.source import FeedSource, FeedSourceCreate, SourceType


class ArticleRepository:
    """Repository for article CRUD operations."""

    # REQ-RC-001, REQ-RC-002, REQ-RC-003: Create articles from various sources
    def create(self, article: ArticleCreate) -> int:
        """Create a new article and return its ID."""
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO articles (
                    source, title, url, author, content_markdown, received_at,
                    word_count, extraction_status, extraction_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.source,
                    article.title,
                    article.url,
                    article.author,
                    article.content_markdown,
                    datetime.now(UTC).isoformat(),
                    article.word_count,
                    article.extraction_status.value,
                    article.extraction_error,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    # REQ-RC-002: Check if article exists by URL (avoid re-ingesting)
    def exists_by_url(self, url: str) -> bool:
        """Check if an article with this URL already exists."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM articles WHERE url = ? LIMIT 1",
                (url,),
            ).fetchone()
            return row is not None

    # REQ-RC-010: Get single article by ID
    def get_by_id(self, article_id: int) -> Article | None:
        """Get a single article by ID."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM articles WHERE id = ?",
                (article_id,),
            ).fetchone()
            if row:
                return self._row_to_article(row)
            return None

    # REQ-RC-011: Search articles using FTS5
    def search(self, query: str, limit: int = 50) -> list[Article]:
        """Search articles by title, content, and tags.

        REQ-RC-011: WHEN user searches the archive
        THE SYSTEM SHALL search across title, source, content, and tags
        THE SYSTEM SHALL return results ranked by search match quality
        """
        if not query.strip():
            return []

        # Sanitize query for FTS5:
        # 1. Remove null bytes and control characters (cause SQL issues)
        # 2. Escape double quotes
        # 3. Wrap in quotes to treat as literal phrase
        sanitized = "".join(c for c in query if c.isprintable() or c in " \t")
        sanitized = sanitized.replace('"', '""')
        if not sanitized.strip():
            return []
        fts_query = f'"{sanitized}"'

        with get_connection() as conn:
            # Use FTS5 MATCH for full-text search, ranked by bm25
            rows = conn.execute(
                """
                SELECT articles.* FROM articles
                JOIN articles_fts ON articles.id = articles_fts.rowid
                WHERE articles_fts MATCH ?
                ORDER BY bm25(articles_fts)
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
            return [self._row_to_article(row) for row in rows]

    # REQ-RC-008, REQ-RC-027: Get articles for inbox display
    def get_inbox(self, show_all: bool = False, limit: int = 50) -> list[Article]:
        """Get articles for inbox, optionally filtered by Elo percentile.

        REQ-RC-027: Use Elo percentiles to preserve p50+ filtering behavior.
        """
        with get_connection() as conn:
            if show_all:
                rows = conn.execute(
                    """
                    SELECT * FROM articles
                    WHERE user_decision = 'pending'
                    ORDER BY elo_rating DESC NULLS LAST, received_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                # REQ-RC-012, REQ-RC-027: Filter to p50+ by Elo percentile
                # Calculate median Elo and filter to above-median articles
                median_elo = conn.execute(
                    """
                    SELECT elo_rating FROM articles
                    WHERE elo_rating IS NOT NULL
                    ORDER BY elo_rating
                    LIMIT 1
                    OFFSET (SELECT COUNT(*) FROM articles WHERE elo_rating IS NOT NULL) / 2
                    """
                ).fetchone()

                if median_elo and median_elo[0] is not None:
                    rows = conn.execute(
                        """
                        SELECT * FROM articles
                        WHERE user_decision = 'pending'
                          AND elo_rating >= ?
                        ORDER BY elo_rating DESC, received_at DESC
                        LIMIT ?
                        """,
                        (median_elo[0], limit),
                    ).fetchall()
                else:
                    # No Elo ratings yet, show all
                    rows = conn.execute(
                        """
                        SELECT * FROM articles
                        WHERE user_decision = 'pending'
                        ORDER BY received_at DESC
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()
            return [self._row_to_article(row) for row in rows]

    # REQ-RC-004: Get unscored articles
    def get_unscored(self, limit: int = 100) -> list[Article]:
        """Get articles that haven't been scored yet."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM articles
                WHERE llm_score IS NULL AND extraction_status = 'success'
                ORDER BY received_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._row_to_article(row) for row in rows]

    # REQ-RC-004: Update article with scoring results
    def update_score(self, article_id: int, score: ArticleScore) -> None:
        """Update an article with LLM scoring results."""
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE articles SET
                    llm_score = ?,
                    llm_reasoning = ?,
                    reading_time_category = ?,
                    tags = ?,
                    prompt_version = ?,
                    generation_id = ?,
                    scored_at = ?
                WHERE id = ?
                """,
                (
                    score.llm_score,
                    score.llm_reasoning,
                    score.reading_time_category.value,
                    json.dumps(score.tags),
                    score.prompt_version,
                    score.generation_id,
                    datetime.now(UTC).isoformat(),
                    article_id,
                ),
            )
            conn.commit()

    # REQ-RC-024, REQ-RC-025: Update Elo rating
    def update_elo(
        self, article_id: int, elo_rating: float, increment_comparisons: bool = True
    ) -> None:
        """Update an article's Elo rating and comparison count.

        Args:
            article_id: ID of article to update
            elo_rating: New Elo rating
            increment_comparisons: Whether to increment comparison counter
        """
        with get_connection() as conn:
            if increment_comparisons:
                conn.execute(
                    """
                    UPDATE articles SET
                        elo_rating = ?,
                        elo_comparisons = elo_comparisons + 1,
                        elo_confidence = CASE
                            WHEN elo_comparisons + 1 >= 7 THEN 1
                            ELSE 0
                        END,
                        scored_at = ?
                    WHERE id = ?
                    """,
                    (elo_rating, datetime.now(UTC).isoformat(), article_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE articles SET elo_rating = ?, scored_at = ? WHERE id = ?
                    """,
                    (elo_rating, datetime.now(UTC).isoformat(), article_id),
                )
            conn.commit()

    # REQ-RC-027: Get all Elo ratings for percentile calculation
    def get_all_elo_ratings(self) -> list[float]:
        """Get all Elo ratings from scored articles."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT elo_rating FROM articles WHERE elo_rating IS NOT NULL"
            ).fetchall()
            return [row["elo_rating"] for row in rows]

    # REQ-RC-014: Update user decision
    def update_decision(self, article_id: int, decision: UserDecision) -> None:
        """Update user decision on an article."""
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE articles SET
                    user_decision = ?,
                    decided_at = ?
                WHERE id = ?
                """,
                (decision.value, datetime.now(UTC).isoformat(), article_id),
            )
            conn.commit()

    # REQ-RC-014: Update user rating (thumbs up/down)
    def update_rating(self, article_id: int, rating: int) -> None:
        """Update user thumbs rating on an article.

        REQ-RC-014: WHEN user provides thumbs up or thumbs down rating
        THE SYSTEM SHALL store the rating alongside the LLM score

        Args:
            article_id: Article ID
            rating: -1 (thumbs down), 0 (no rating), or 1 (thumbs up)
        """
        if rating not in (-1, 0, 1):
            msg = f"Rating must be -1, 0, or 1, got {rating}"
            raise ValueError(msg)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE articles SET
                    user_rating = ?,
                    rated_at = ?
                WHERE id = ?
                """,
                (rating, datetime.now(UTC).isoformat(), article_id),
            )
            conn.commit()

    # REQ-RC-014: Mark article as having contributed refinement feedback
    def mark_rating_refined(self, article_id: int, refined: bool = True) -> None:
        """Mark article as having provided heuristic-refiner feedback.

        REQ-RC-014: WHEN user provides rating and enters heuristic-refiner mode
        THE SYSTEM SHALL flag the article as having contributed refinement feedback
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE articles SET rating_refined = ? WHERE id = ?",
                (int(refined), article_id),
            )
            conn.commit()

    # REQ-RC-009: Bundle management
    def add_to_bundle(self, article_id: int) -> None:
        """Add article to pending bundle."""
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE articles SET in_bundle = 1, bundle_added_at = ?
                WHERE id = ?
                """,
                (datetime.now(UTC).isoformat(), article_id),
            )
            conn.commit()

    def remove_from_bundle(self, article_id: int) -> None:
        """Remove article from pending bundle."""
        with get_connection() as conn:
            conn.execute(
                "UPDATE articles SET in_bundle = 0, bundle_added_at = NULL WHERE id = ?",
                (article_id,),
            )
            conn.commit()

    def get_bundled(self) -> list[Article]:
        """Get all articles in the pending bundle."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM articles WHERE in_bundle = 1 ORDER BY llm_score DESC"
            ).fetchall()
            return [self._row_to_article(row) for row in rows]

    def clear_bundle_flags(self) -> None:
        """Clear bundle flags after download."""
        with get_connection() as conn:
            conn.execute("UPDATE articles SET in_bundle = 0, bundle_added_at = NULL")
            conn.commit()

    # REQ-RC-013: Stats calculation
    def get_stats(self) -> dict[str, float | int]:
        """Calculate precision and recall metrics.

        REQ-RC-013: WHEN user accesses the stats page
        THE SYSTEM SHALL display precision (% of sent articles actually read)
        THE SYSTEM SHALL display recall (% of read articles that were auto-recommended)

        Returns:
            Dict with precision, recall, total_articles, and decision counts
        """
        with get_connection() as conn:
            # Get median score for "recommended" threshold
            median_row = conn.execute(
                "SELECT AVG(llm_score) as median FROM articles WHERE llm_score IS NOT NULL"
            ).fetchone()
            median_score = median_row["median"] if median_row and median_row["median"] else 5.0

            # Total articles with decisions
            total = conn.execute(
                "SELECT COUNT(*) as c FROM articles WHERE llm_score IS NOT NULL"
            ).fetchone()["c"]

            # Articles by decision
            read_count = conn.execute(
                "SELECT COUNT(*) as c FROM articles WHERE user_decision = 'read'"
            ).fetchone()["c"]

            sent_count = conn.execute(
                "SELECT COUNT(*) as c FROM articles WHERE user_decision = 'sent'"
            ).fetchone()["c"]

            skipped_count = conn.execute(
                "SELECT COUNT(*) as c FROM articles WHERE user_decision = 'skipped'"
            ).fetchone()["c"]

            pending_count = conn.execute(
                "SELECT COUNT(*) as c FROM articles WHERE user_decision = 'pending'"
            ).fetchone()["c"]

            # Recommended = scored at or above median
            recommended = conn.execute(
                "SELECT COUNT(*) as c FROM articles WHERE llm_score >= ?",
                (median_score,),
            ).fetchone()["c"]

            # Read that were recommended
            read_and_recommended = conn.execute(
                "SELECT COUNT(*) as c FROM articles WHERE user_decision = 'read' AND llm_score >= ?",
                (median_score,),
            ).fetchone()["c"]

            # Precision: of recommended, how many read?
            precision = (read_and_recommended / recommended * 100) if recommended > 0 else 0.0

            # Recall: of read, how many were recommended?
            recall = (read_and_recommended / read_count * 100) if read_count > 0 else 0.0

            return {
                "precision": round(precision, 1),
                "recall": round(recall, 1),
                "total_articles": total,
                "read_count": read_count,
                "sent_count": sent_count,
                "skipped_count": skipped_count,
                "pending_count": pending_count,
                "recommended_count": recommended,
                "median_score": round(median_score, 1),
            }

    def _row_to_article(self, row: sqlite3.Row) -> Article:
        """Convert a database row to an Article model."""
        tags: list[str] = json.loads(row["tags"]) if row["tags"] else []
        return Article(
            id=row["id"],
            source=row["source"],
            title=row["title"],
            url=row["url"],
            author=row["author"],
            content_markdown=row["content_markdown"],
            received_at=datetime.fromisoformat(row["received_at"]),
            word_count=row["word_count"],
            llm_score=row["llm_score"],
            llm_reasoning=row["llm_reasoning"],
            reading_time_category=row["reading_time_category"],
            tags=tags,
            prompt_version=row["prompt_version"],
            generation_id=row["generation_id"],
            scored_at=datetime.fromisoformat(row["scored_at"]) if row["scored_at"] else None,
            elo_rating=row["elo_rating"] if row["elo_rating"] is not None else 1500.0,
            elo_comparisons=row["elo_comparisons"] or 0,
            elo_confidence=bool(row["elo_confidence"]),
            user_decision=UserDecision(row["user_decision"]),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
            user_rating=row["user_rating"] or 0,
            rating_refined=bool(row["rating_refined"]),
            rated_at=datetime.fromisoformat(row["rated_at"]) if row["rated_at"] else None,
            in_bundle=bool(row["in_bundle"]),
            bundle_added_at=(
                datetime.fromisoformat(row["bundle_added_at"]) if row["bundle_added_at"] else None
            ),
            extraction_status=row["extraction_status"],
            extraction_error=row["extraction_error"],
        )


class FeedSourceRepository:
    """Repository for feed source CRUD operations.

    REQ-RC-015: Manage Content Sources
    """

    def create(self, source: FeedSourceCreate) -> int:
        """Create a new feed source and return its ID."""
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO feed_sources (type, identifier, display_name, enabled, check_interval_hours, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    source.type.value,
                    source.identifier,
                    source.display_name,
                    int(source.enabled),
                    source.check_interval_hours,
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_all(self) -> list[FeedSource]:
        """Get all feed sources."""
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM feed_sources ORDER BY created_at DESC").fetchall()
            return [self._row_to_source(row) for row in rows]

    def get_by_id(self, source_id: int) -> FeedSource | None:
        """Get a single feed source by ID."""
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM feed_sources WHERE id = ?", (source_id,)).fetchone()
            if row:
                return self._row_to_source(row)
            return None

    def get_enabled(self) -> list[FeedSource]:
        """Get all enabled feed sources."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM feed_sources WHERE enabled = 1 ORDER BY type, display_name"
            ).fetchall()
            return [self._row_to_source(row) for row in rows]

    def toggle_enabled(self, source_id: int) -> None:
        """Toggle the enabled status of a feed source."""
        with get_connection() as conn:
            conn.execute(
                "UPDATE feed_sources SET enabled = NOT enabled WHERE id = ?",
                (source_id,),
            )
            conn.commit()

    def delete(self, source_id: int) -> None:
        """Delete a feed source."""
        with get_connection() as conn:
            conn.execute("DELETE FROM feed_sources WHERE id = ?", (source_id,))
            conn.commit()

    def update_last_checked(self, source_id: int) -> None:
        """Update the last_checked timestamp."""
        with get_connection() as conn:
            conn.execute(
                "UPDATE feed_sources SET last_checked = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), source_id),
            )
            conn.commit()

    def _row_to_source(self, row: sqlite3.Row) -> FeedSource:
        """Convert a database row to a FeedSource model."""
        return FeedSource(
            id=row["id"],
            type=SourceType(row["type"]),
            identifier=row["identifier"],
            display_name=row["display_name"],
            enabled=bool(row["enabled"]),
            check_interval_hours=row["check_interval_hours"],
            last_checked=(
                datetime.fromisoformat(row["last_checked"]) if row["last_checked"] else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class PromptGenerationRepository:
    """Repository for prompt generation CRUD operations.

    REQ-RC-005, REQ-RC-021, REQ-RC-022: Prompt generation tracking
    """

    def get_active(self) -> PromptGeneration | None:
        """Get the currently active prompt generation."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM prompt_generations WHERE is_active = 1"
            ).fetchone()
            if row:
                return self._row_to_generation(row)
            return None

    def get_by_id(self, generation_id: int) -> PromptGeneration | None:
        """Get a prompt generation by ID."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM prompt_generations WHERE id = ?",
                (generation_id,),
            ).fetchone()
            if row:
                return self._row_to_generation(row)
            return None

    def get_all(self) -> list[PromptGeneration]:
        """Get all prompt generations ordered by ID descending."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM prompt_generations ORDER BY id DESC"
            ).fetchall()
            return [self._row_to_generation(row) for row in rows]

    def get_previous_n(self, n: int = 5) -> list[PromptGeneration]:
        """Get the previous N generations (excluding current active).

        REQ-RC-008: Display articles from the previous 5 prompt generations
        """
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM prompt_generations
                WHERE is_active = 0
                ORDER BY id DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
            return [self._row_to_generation(row) for row in rows]

    def create(
        self,
        prompt_text: str,
        diff_from_previous: str | None = None,
        feedback_count: int = 0,
        set_active: bool = True,
    ) -> int:
        """Create a new prompt generation.

        REQ-RC-021: THE SYSTEM SHALL create new prompt generation from structured LLM response

        Args:
            prompt_text: The full prompt text
            diff_from_previous: Word-diff from previous generation
            feedback_count: Number of feedback items that produced this
            set_active: Whether to set this as the active generation

        Returns:
            The ID of the created generation
        """
        with get_connection() as conn:
            if set_active:
                # Deactivate all existing generations
                conn.execute("UPDATE prompt_generations SET is_active = 0")

            cursor = conn.execute(
                """
                INSERT INTO prompt_generations (prompt_text, created_at, diff_from_previous, feedback_count, is_active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    prompt_text,
                    datetime.now(UTC).isoformat(),
                    diff_from_previous,
                    feedback_count,
                    int(set_active),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def _row_to_generation(self, row: sqlite3.Row) -> PromptGeneration:
        """Convert a database row to a PromptGeneration model."""
        return PromptGeneration(
            id=row["id"],
            prompt_text=row["prompt_text"],
            created_at=datetime.fromisoformat(row["created_at"]),
            diff_from_previous=row["diff_from_previous"],
            feedback_count=row["feedback_count"],
            is_active=bool(row["is_active"]),
        )


class HeuristicFeedbackRepository:
    """Repository for heuristic feedback CRUD operations.

    REQ-RC-019, REQ-RC-020, REQ-RC-021: Heuristic-refiner feedback
    """

    def create(self, feedback: HeuristicFeedbackCreate) -> int:
        """Create a new heuristic feedback entry.

        REQ-RC-020: WHEN user submits feedback
        THE SYSTEM SHALL store feedback with characterization and article linkage
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO heuristic_feedback (article_id, feedback_text, characterization_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    feedback.article_id,
                    feedback.feedback_text,
                    feedback.characterization_json,
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_by_article(self, article_id: int) -> HeuristicFeedback | None:
        """Get feedback for a specific article."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM heuristic_feedback WHERE article_id = ?",
                (article_id,),
            ).fetchone()
            if row:
                return self._row_to_feedback(row)
            return None

    def get_unprocessed_since(self, since: datetime) -> list[HeuristicFeedback]:
        """Get all feedback since a given time that hasn't been processed.

        REQ-RC-021: WHEN UTC midnight occurs
        THE SYSTEM SHALL collect all heuristic-refiner feedback from the past 24 hours
        """
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM heuristic_feedback
                WHERE generation_id IS NULL AND created_at >= ?
                ORDER BY created_at ASC
                """,
                (since.isoformat(),),
            ).fetchall()
            return [self._row_to_feedback(row) for row in rows]

    def get_by_generation(self, generation_id: int) -> list[HeuristicFeedback]:
        """Get all feedback items that produced a specific generation.

        REQ-RC-022: THE SYSTEM SHALL link each generation to the feedback items that produced it
        """
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM heuristic_feedback
                WHERE generation_id = ?
                ORDER BY created_at ASC
                """,
                (generation_id,),
            ).fetchall()
            return [self._row_to_feedback(row) for row in rows]

    def link_to_generation(self, feedback_ids: list[int], generation_id: int) -> None:
        """Link feedback items to the generation they produced.

        REQ-RC-021: Update all feedback items: generation_id = new_generation.id
        """
        if not feedback_ids:
            return
        with get_connection() as conn:
            placeholders = ",".join("?" * len(feedback_ids))
            conn.execute(
                f"UPDATE heuristic_feedback SET generation_id = ? WHERE id IN ({placeholders})",
                [generation_id, *feedback_ids],
            )
            conn.commit()

    def _row_to_feedback(self, row: sqlite3.Row) -> HeuristicFeedback:
        """Convert a database row to a HeuristicFeedback model."""
        characterization = None
        if row["characterization_json"]:
            try:
                char_data = json.loads(row["characterization_json"])
                characterization = FiveWhats(**char_data)
            except (json.JSONDecodeError, TypeError):
                pass  # Invalid JSON, leave as None

        return HeuristicFeedback(
            id=row["id"],
            article_id=row["article_id"],
            feedback_text=row["feedback_text"],
            characterization=characterization,
            created_at=datetime.fromisoformat(row["created_at"]),
            generation_id=row["generation_id"],
        )


class AppSettingsRepository:
    """Repository for application settings.

    REQ-RC-023: Customize Application Appearance
    """

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a setting value by key."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
            if row:
                value: str = row["value"]
                return value
            return default

    def set(self, key: str, value: str) -> None:
        """Set a setting value (insert or update)."""
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()

    def get_all(self) -> AppSettings:
        """Get all application settings as a model.

        REQ-RC-023: THE SYSTEM SHALL default application title to 'nerd-reader'
        """
        app_title = self.get("app_title", "nerd-reader") or "nerd-reader"
        return AppSettings(app_title=app_title)

    def update_app_title(self, title: str) -> None:
        """Update the application title.

        REQ-RC-023: THE SYSTEM SHALL allow customization of application title
        """
        self.set("app_title", title)


class EloComparisonRepository:
    """Repository for Elo comparison CRUD operations.

    REQ-RC-024: Compare Article Relevance via Pairwise Ranking
    REQ-RC-028: Track Comparison History for Transparency
    """

    def create(self, comparison: EloComparisonCreate) -> int:
        """Create a new Elo comparison record and return its ID."""
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO elo_comparisons (
                    article_a_id, article_b_id, winner_id, llm_reasoning,
                    article_a_elo_before, article_a_elo_after,
                    article_b_elo_before, article_b_elo_after,
                    k_factor, generation_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comparison.article_a_id,
                    comparison.article_b_id,
                    comparison.winner_id,
                    comparison.llm_reasoning,
                    comparison.article_a_elo_before,
                    comparison.article_a_elo_after,
                    comparison.article_b_elo_before,
                    comparison.article_b_elo_after,
                    comparison.k_factor,
                    comparison.generation_id,
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_by_article(self, article_id: int) -> list[EloComparisonRecord]:
        """Get all comparisons involving a specific article."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM elo_comparisons
                WHERE article_a_id = ? OR article_b_id = ?
                ORDER BY created_at DESC
                """,
                (article_id, article_id),
            ).fetchall()
            return [self._row_to_comparison(row) for row in rows]

    def get_recent(self, limit: int = 50) -> list[EloComparisonRecord]:
        """Get recent comparisons."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM elo_comparisons
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._row_to_comparison(row) for row in rows]

    def _row_to_comparison(self, row: sqlite3.Row) -> EloComparisonRecord:
        """Convert a database row to an EloComparisonRecord model."""
        return EloComparisonRecord(
            id=row["id"],
            article_a_id=row["article_a_id"],
            article_b_id=row["article_b_id"],
            winner_id=row["winner_id"],
            llm_reasoning=row["llm_reasoning"],
            article_a_elo_before=row["article_a_elo_before"],
            article_a_elo_after=row["article_a_elo_after"],
            article_b_elo_before=row["article_b_elo_before"],
            article_b_elo_after=row["article_b_elo_after"],
            k_factor=row["k_factor"],
            generation_id=row["generation_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
