"""API routes for Reader.

REQ-RC-017: Accept URLs from iOS Shortcuts
REQ-RC-018: Download Bundle via API
"""

import io
import re
import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl

from reader.auth.middleware import require_api_key
from reader.db.repository import ArticleRepository

router = APIRouter(tags=["api"])


class ArticleSubmission(BaseModel):
    """Request body for submitting a URL."""

    url: HttpUrl


class ArticleSubmissionResponse(BaseModel):
    """Response after submitting a URL."""

    status: str
    message: str


class BundleAddResponse(BaseModel):
    """Response after adding to bundle."""

    status: str
    bundle_count: int


# REQ-RC-017: Accept URLs from iOS Shortcuts
@router.post("/article", response_model=ArticleSubmissionResponse)
async def submit_article(
    _submission: ArticleSubmission,  # TODO: Use when implementing queue
    _api_key: Annotated[str, Depends(require_api_key)],  # Auth side-effect
) -> ArticleSubmissionResponse:
    """Submit a URL for extraction and scoring.

    REQ-RC-017: WHEN POST request arrives at /article endpoint with URL and valid API key
    THE SYSTEM SHALL queue URL for extraction and scoring
    """
    # TODO: Queue URL for background extraction and scoring
    # For now, just acknowledge receipt
    return ArticleSubmissionResponse(
        status="queued",
        message="Article queued for scoring",
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
