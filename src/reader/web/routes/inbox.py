"""Inbox routes for Reader.

REQ-RC-008: Browse Articles by Relevance Score
REQ-RC-010: Read Articles Without Leaving the App
REQ-RC-011: Find Past Articles
REQ-RC-012: Focus on High-Value Articles by Default
REQ-RC-013: Monitor Scoring Accuracy
REQ-RC-014: Learn from Reading Decisions
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from reader.auth.middleware import require_basic_auth
from reader.db.repository import ArticleRepository, FeedSourceRepository
from reader.models.article import UserDecision
from reader.models.source import FeedSourceCreate, SourceType
from reader.web.templates_config import templates

router = APIRouter(tags=["inbox"])


@router.get("/", response_class=HTMLResponse)
@router.get("/inbox", response_class=HTMLResponse)
async def inbox(
    request: Request,
    username: Annotated[str, Depends(require_basic_auth)],
    show_all: bool = False,
) -> HTMLResponse:
    """Display inbox with scored articles.

    REQ-RC-008: WHEN user accesses the inbox
    THE SYSTEM SHALL display all unread articles sorted by score (highest first)

    REQ-RC-012: THE SYSTEM SHALL by default show only articles scoring above the median
    """
    repo = ArticleRepository()
    articles = repo.get_inbox(show_all=show_all)

    return templates.TemplateResponse(
        request=request,
        name="inbox.html",
        context={
            "articles": articles,
            "show_all": show_all,
            "username": username,
        },
    )


@router.get("/article/{article_id}", response_class=HTMLResponse)
async def article(
    request: Request,
    article_id: int,
    _username: Annotated[str, Depends(require_basic_auth)],
) -> HTMLResponse:
    """Display a single article for reading.

    REQ-RC-010: WHEN user clicks on an article in the inbox
    THE SYSTEM SHALL display the full article content in a reading view

    REQ-RC-010: WHEN user finishes reading in-app
    THE SYSTEM SHALL mark article as 'read'
    """
    repo = ArticleRepository()
    article_obj = repo.get_by_id(article_id)

    if not article_obj:
        raise HTTPException(status_code=404, detail="Article not found")

    # Mark as read when viewing
    if article_obj.user_decision == UserDecision.PENDING:
        repo.update_decision(article_id, UserDecision.READ)
        article_obj.user_decision = UserDecision.READ

    return templates.TemplateResponse(
        request=request,
        name="article.html",
        context={"article": article_obj},
    )


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    _username: Annotated[str, Depends(require_basic_auth)],
    q: str = "",
) -> HTMLResponse:
    """Search articles by title, content, and tags.

    REQ-RC-011: WHEN user searches the archive
    THE SYSTEM SHALL search across title, source, content, and tags
    THE SYSTEM SHALL return results ranked by search match quality
    """
    repo = ArticleRepository()
    articles = repo.search(q) if q else []

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "articles": articles,
            "query": q,
        },
    )


@router.get("/stats", response_class=HTMLResponse)
async def stats(
    request: Request,
    _username: Annotated[str, Depends(require_basic_auth)],
) -> HTMLResponse:
    """Display scoring accuracy statistics.

    REQ-RC-013: WHEN user accesses the stats page
    THE SYSTEM SHALL display precision (% of sent articles actually read)
    THE SYSTEM SHALL display recall (% of read articles that were auto-recommended)
    THE SYSTEM SHALL show trends over time
    """
    repo = ArticleRepository()
    stats_data = repo.get_stats()

    return templates.TemplateResponse(
        request=request,
        name="stats.html",
        context={"stats": stats_data},
    )


@router.post("/article/{article_id}/decision")
async def update_decision(
    article_id: int,
    decision: Annotated[str, Form()],
    _username: Annotated[str, Depends(require_basic_auth)],
) -> RedirectResponse:
    """Update user decision on an article.

    REQ-RC-014: THE SYSTEM SHALL record user decisions: 'sent', 'skipped', 'read', 'pending'
    """
    repo = ArticleRepository()

    # Validate decision
    try:
        user_decision = UserDecision(decision)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid decision: {decision}") from err

    repo.update_decision(article_id, user_decision)
    return RedirectResponse(url=f"/article/{article_id}", status_code=303)


@router.post("/article/{article_id}/rating")
async def update_rating(
    article_id: int,
    rating: Annotated[int, Form()],
    _username: Annotated[str, Depends(require_basic_auth)],
) -> RedirectResponse:
    """Update user rating on an article.

    REQ-RC-014: WHEN user provides post-reading rating
    THE SYSTEM SHALL store rating alongside LLM score
    """
    repo = ArticleRepository()

    # Validate rating (1-5)
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    # Get current article to preserve decision
    article_obj = repo.get_by_id(article_id)
    if not article_obj:
        raise HTTPException(status_code=404, detail="Article not found")

    repo.update_decision(article_id, article_obj.user_decision, rating=rating)
    return RedirectResponse(url=f"/article/{article_id}", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def settings(
    request: Request,
    _username: Annotated[str, Depends(require_basic_auth)],
) -> HTMLResponse:
    """Display settings page for managing feed sources.

    REQ-RC-015: WHEN user accesses settings
    THE SYSTEM SHALL allow adding/removing RSS feed URLs
    THE SYSTEM SHALL allow specifying sender patterns to monitor
    THE SYSTEM SHALL allow enabling/disabling individual sources
    """
    repo = FeedSourceRepository()
    sources = repo.get_all()

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"sources": sources, "source_types": SourceType},
    )


@router.post("/settings/source")
async def add_source(
    source_type: Annotated[str, Form()],
    identifier: Annotated[str, Form()],
    display_name: Annotated[str, Form()] = "",
    _username: Annotated[str, Depends(require_basic_auth)] = "",
) -> RedirectResponse:
    """Add a new feed source.

    REQ-RC-015: THE SYSTEM SHALL allow adding RSS feed URLs and email sender patterns
    """
    repo = FeedSourceRepository()

    # Validate source type
    try:
        stype = SourceType(source_type)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid source type: {source_type}") from err

    source = FeedSourceCreate(
        type=stype,
        identifier=identifier.strip(),
        display_name=display_name.strip() or None,
    )
    repo.create(source)
    return RedirectResponse(url="/settings", status_code=303)


@router.post("/settings/source/{source_id}/toggle")
async def toggle_source(
    source_id: int,
    _username: Annotated[str, Depends(require_basic_auth)],
) -> RedirectResponse:
    """Toggle a feed source enabled/disabled.

    REQ-RC-015: THE SYSTEM SHALL allow enabling/disabling individual sources
    """
    repo = FeedSourceRepository()
    repo.toggle_enabled(source_id)
    return RedirectResponse(url="/settings", status_code=303)


@router.post("/settings/source/{source_id}/delete")
async def delete_source(
    source_id: int,
    _username: Annotated[str, Depends(require_basic_auth)],
) -> RedirectResponse:
    """Delete a feed source.

    REQ-RC-015: THE SYSTEM SHALL allow adding/removing RSS feed URLs
    """
    repo = FeedSourceRepository()
    repo.delete(source_id)
    return RedirectResponse(url="/settings", status_code=303)
