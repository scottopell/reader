"""Inbox routes for Reader.

REQ-RC-008: Browse Articles by Relevance Score
REQ-RC-012: Focus on High-Value Articles by Default
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from reader.auth.middleware import require_basic_auth
from reader.db.repository import ArticleRepository
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
