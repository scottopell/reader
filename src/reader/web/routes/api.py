"""API routes for Reader.

REQ-RC-017: Accept URLs from iOS Shortcuts
REQ-RC-018: Download Bundle via API
"""

import io
import logging
import re
import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl

from reader.auth.middleware import require_api_key
from reader.db.repository import ArticleRepository
from reader.extraction.readability import extract_from_url
from reader.models.article import ArticleCreate, ArticleScore, ExtractionStatus
from reader.models.scoring import ScoringRequest
from reader.scoring.llm import ScoringError, get_content_preview, score_article

router = APIRouter(tags=["api"])
logger = logging.getLogger(__name__)


class ArticleSubmission(BaseModel):
    """Request body for submitting a URL."""

    url: HttpUrl


class ArticleSubmissionResponse(BaseModel):
    """Response after submitting a URL."""

    status: str
    message: str
    article_id: int | None = None
    score: float | None = None


class BundleAddResponse(BaseModel):
    """Response after adding to bundle."""

    status: str
    bundle_count: int


# REQ-RC-017: Accept URLs from iOS Shortcuts
@router.post("/article", response_model=ArticleSubmissionResponse)
async def submit_article(
    submission: ArticleSubmission,
    _api_key: Annotated[str, Depends(require_api_key)],  # Auth side-effect
) -> ArticleSubmissionResponse:
    """Submit a URL for extraction and scoring.

    REQ-RC-003: WHEN user submits a URL via API endpoint
    THE SYSTEM SHALL queue the URL for content extraction and scoring

    REQ-RC-017: WHEN POST request arrives at /article endpoint with URL and valid API key
    THE SYSTEM SHALL queue URL for extraction and scoring
    """
    url = str(submission.url)
    logger.info("Received URL submission: %s", url)

    # REQ-RC-006: Extract content from URL
    extraction = await extract_from_url(url)

    # Create article in database
    repo = ArticleRepository()
    article_data = ArticleCreate(
        source=f"url:{submission.url.host or 'unknown'}",
        title=extraction.title or "Untitled",
        url=url,
        content_markdown=extraction.content_markdown,
        word_count=extraction.word_count,
        extraction_status=extraction.status,
        extraction_error=extraction.error,
    )
    article_id = repo.create(article_data)
    logger.info("Created article %d: %s", article_id, extraction.title)

    # If extraction failed, return early
    if extraction.status == ExtractionStatus.FAILED:
        return ArticleSubmissionResponse(
            status="extraction_failed",
            message=f"Failed to extract content: {extraction.error}",
            article_id=article_id,
        )

    if extraction.status == ExtractionStatus.MANUAL_REVIEW:
        return ArticleSubmissionResponse(
            status="manual_review",
            message="Article saved but content too short, may need manual review",
            article_id=article_id,
        )

    # REQ-RC-004: Score with LLM
    try:
        scoring_request = ScoringRequest(
            article_id=article_id,
            title=extraction.title,
            source=article_data.source,
            content_preview=get_content_preview(extraction.content_markdown),
        )
        scoring_result = await score_article(scoring_request)

        # Update article with score
        # REQ-RC-005: Track which prompt version/generation scored this article
        score_data = ArticleScore(
            llm_score=scoring_result.response.score,
            llm_reasoning=scoring_result.response.reasoning,
            reading_time_category=scoring_result.response.reading_time,
            tags=scoring_result.response.tags,
            prompt_version=scoring_result.response.prompt_version,
            generation_id=scoring_result.generation_id,
        )
        repo.update_score(article_id, score_data)
        logger.info("Scored article %d: %.1f", article_id, scoring_result.response.score)

        return ArticleSubmissionResponse(
            status="success",
            message=f"Article scored: {scoring_result.response.score:.1f}/10 - {scoring_result.response.reasoning}",
            article_id=article_id,
            score=scoring_result.response.score,
        )
    except ScoringError as e:
        logger.warning("Scoring failed for article %d: %s", article_id, e)
        return ArticleSubmissionResponse(
            status="scoring_failed",
            message=f"Article saved but scoring failed: {e}",
            article_id=article_id,
        )


# REQ-RC-018: Download Bundle via API
@router.get("/bundle")
async def download_bundle(
    _api_key: Annotated[str, Depends(require_api_key)],  # Auth side-effect
) -> StreamingResponse:
    """Download bundle of selected articles as ZIP.

    REQ-RC-018: WHEN GET request arrives at /bundle endpoint with valid API key
    THE SYSTEM SHALL return ZIP file containing individual .txt articles
    """
    repo = ArticleRepository()
    articles = repo.get_bundled()

    # Create in-memory ZIP file
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for article in articles:
            # REQ-RC-007: Include title, source, reading time, score, and content
            header = f"""Title: {article.title}
Source: {article.source}
Score: {article.llm_score or "N/A"}/10
Reading Time: {article.reading_time_category or "unknown"}

{"=" * 80}

"""
            # Simple markdown to plain text (basic conversion)
            content = header + article.content_markdown

            # Sanitize filename
            safe_title = re.sub(r"[^\w\s-]", "", article.title)[:50].strip()
            score_prefix = f"{article.llm_score:.1f}" if article.llm_score else "0.0"
            filename = f"{score_prefix}_{safe_title}.txt"

            zip_file.writestr(filename, content)

    # Reset buffer position
    zip_buffer.seek(0)

    # Clear in_bundle flag after download
    repo.clear_bundle_flags()

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=reading_bundle.zip"},
    )


class ArticleListItem(BaseModel):
    """Article summary for list display."""

    id: int
    title: str
    source: str
    elo_rating: float
    percentile: int
    reading_time_category: str | None
    user_rating: int
    generation_id: int | None


class ArticleListResponse(BaseModel):
    """Response for article list endpoint."""

    articles: list[ArticleListItem]
    has_more: bool
    next_offset: int


@router.get("/articles", response_model=ArticleListResponse)
async def list_articles(
    _api_key: Annotated[str, Depends(require_api_key)],
    offset: int = 0,
    limit: int = 50,
    show_all: bool = False,
) -> ArticleListResponse:
    """Get paginated list of articles for inbox display."""
    repo = ArticleRepository()

    # Get articles with one extra to check if there are more
    articles = repo.get_inbox(show_all=show_all, limit=limit + 1, offset=offset)
    has_more = len(articles) > limit
    articles = articles[:limit]

    # Calculate percentiles
    all_elo_ratings = sorted(repo.get_all_elo_ratings())
    items: list[ArticleListItem] = []

    for article in articles:
        percentile = 0
        if all_elo_ratings:
            below = sum(1 for r in all_elo_ratings if r < article.elo_rating)
            percentile = int((below / len(all_elo_ratings)) * 100)

        items.append(
            ArticleListItem(
                id=article.id,
                title=article.title,
                source=article.source,
                elo_rating=article.elo_rating,
                percentile=percentile,
                reading_time_category=(
                    article.reading_time_category.value if article.reading_time_category else None
                ),
                user_rating=article.user_rating,
                generation_id=article.generation_id,
            )
        )

    return ArticleListResponse(
        articles=items,
        has_more=has_more,
        next_offset=offset + limit,
    )


@router.post("/bundle/add/{article_id}", response_model=BundleAddResponse)
async def add_to_bundle(
    article_id: int,
    _api_key: Annotated[str, Depends(require_api_key)],  # Auth side-effect
) -> BundleAddResponse:
    """Add article to pending bundle."""
    repo = ArticleRepository()
    repo.add_to_bundle(article_id)
    bundle_count = len(repo.get_bundled())
    return BundleAddResponse(status="added", bundle_count=bundle_count)


@router.delete("/bundle/remove/{article_id}", response_model=BundleAddResponse)
async def remove_from_bundle(
    article_id: int,
    _api_key: Annotated[str, Depends(require_api_key)],  # Auth side-effect
) -> BundleAddResponse:
    """Remove article from pending bundle."""
    repo = ArticleRepository()
    repo.remove_from_bundle(article_id)
    bundle_count = len(repo.get_bundled())
    return BundleAddResponse(status="removed", bundle_count=bundle_count)
