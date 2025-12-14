"""Inbox routes for Reader.

REQ-RC-008: Browse Articles by Relevance Score
REQ-RC-010: Read Articles Without Leaving the App
REQ-RC-011: Find Past Articles
REQ-RC-012: Focus on High-Value Articles by Default
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from reader.auth.middleware import require_basic_auth
from reader.db.repository import ArticleRepository
from reader.models.article import UserDecision
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
