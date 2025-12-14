"""Article repository for database operations."""

import json
import sqlite3
from datetime import UTC, datetime

from reader.db.connection import get_connection
from reader.models.article import Article, ArticleCreate, ArticleScore, UserDecision


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

    # REQ-RC-008: Get articles for inbox display
    def get_inbox(self, show_all: bool = False, limit: int = 50) -> list[Article]:
        """Get articles for inbox, optionally filtered by median score."""
        with get_connection() as conn:
            if show_all:
                rows = conn.execute(
                    """
                    SELECT * FROM articles
                    WHERE user_decision = 'pending'
                    ORDER BY llm_score DESC NULLS LAST, received_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                # REQ-RC-012: Filter to p50+ by default
                rows = conn.execute(
                    """
                    SELECT * FROM articles
                    WHERE user_decision = 'pending'
                      AND llm_score >= (
                          SELECT AVG(llm_score) FROM articles WHERE llm_score IS NOT NULL
                      )
                    ORDER BY llm_score DESC, received_at DESC
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
                    scored_at = ?
                WHERE id = ?
                """,
                (
                    score.llm_score,
                    score.llm_reasoning,
                    score.reading_time_category.value,
                    json.dumps(score.tags),
                    score.prompt_version,
                    datetime.now(UTC).isoformat(),
                    article_id,
                ),
            )
            conn.commit()

    # REQ-RC-014: Update user decision
    def update_decision(
        self, article_id: int, decision: UserDecision, rating: int | None = None
    ) -> None:
        """Update user decision on an article."""
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE articles SET
                    user_decision = ?,
                    user_rating = ?,
                    decided_at = ?
                WHERE id = ?
                """,
                (decision.value, rating, datetime.now(UTC).isoformat(), article_id),
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
            scored_at=datetime.fromisoformat(row["scored_at"]) if row["scored_at"] else None,
            user_decision=UserDecision(row["user_decision"]),
            user_rating=row["user_rating"],
            decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
            in_bundle=bool(row["in_bundle"]),
            bundle_added_at=(
                datetime.fromisoformat(row["bundle_added_at"]) if row["bundle_added_at"] else None
            ),
            extraction_status=row["extraction_status"],
            extraction_error=row["extraction_error"],
        )
