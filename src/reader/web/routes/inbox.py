"""Inbox routes for Reader.

REQ-RC-008: Browse Articles by Relevance Score
REQ-RC-010: Read Articles Without Leaving the App
REQ-RC-011: Find Past Articles
REQ-RC-012: Focus on High-Value Articles by Default
REQ-RC-013: Monitor Scoring Accuracy
REQ-RC-014: Collect User Feedback via Ratings
REQ-RC-023: Customize Application Appearance
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from reader.auth.middleware import require_basic_auth
from reader.db.repository import (
    AppSettingsRepository,
    ArticleRepository,
    FeedSourceRepository,
    HeuristicFeedbackRepository,
    PromptGenerationRepository,
)
from reader.models.article import UserDecision
from reader.models.scoring import HeuristicFeedbackCreate
from reader.models.source import FeedSourceCreate, SourceType
from reader.web.templates_config import templates

router = APIRouter(tags=["inbox"])


@router.get("/", response_class=HTMLResponse)
@router.get("/inbox", response_class=HTMLResponse)
async def inbox(
    request: Request,
    username: Annotated[str, Depends(require_basic_auth)],
    show_all: bool = False,
    limit: int = 50,
) -> HTMLResponse:
    """Display inbox with scored articles.

    REQ-RC-008: WHEN user accesses the inbox
    THE SYSTEM SHALL display all unread articles sorted by score (highest first)

    REQ-RC-012: THE SYSTEM SHALL by default show only articles scoring above the median

    REQ-RC-023: THE SYSTEM SHALL display configured title in UI header and page titles
    """
    repo = ArticleRepository()
    settings_repo = AppSettingsRepository()
    articles = repo.get_inbox(show_all=show_all, limit=limit)
    app_settings = settings_repo.get_all()

    # Calculate Elo percentiles for display
    all_elo_ratings = sorted(repo.get_all_elo_ratings())
    percentiles: dict[int, int] = {}
    if all_elo_ratings:
        for article in articles:
            # Count how many ratings are below this one
            below = sum(1 for r in all_elo_ratings if r < article.elo_rating)
            percentiles[article.id] = int((below / len(all_elo_ratings)) * 100)

    return templates.TemplateResponse(
        request=request,
        name="inbox.html",
        context={
            "articles": articles,
            "show_all": show_all,
            "username": username,
            "app_settings": app_settings,
            "percentiles": percentiles,
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

    REQ-RC-023: THE SYSTEM SHALL display configured title in page titles
    """
    repo = ArticleRepository()
    settings_repo = AppSettingsRepository()
    article_obj = repo.get_by_id(article_id)
    app_settings = settings_repo.get_all()

    if not article_obj:
        raise HTTPException(status_code=404, detail="Article not found")

    # Mark as read when viewing
    if article_obj.user_decision == UserDecision.PENDING:
        repo.update_decision(article_id, UserDecision.READ)
        article_obj.user_decision = UserDecision.READ

    return templates.TemplateResponse(
        request=request,
        name="article.html",
        context={"article": article_obj, "app_settings": app_settings},
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


@router.get("/inbox/articles", response_class=JSONResponse)
async def inbox_articles(
    _username: Annotated[str, Depends(require_basic_auth)],
    offset: int = 0,
    limit: int = 50,
    show_all: bool = False,
) -> JSONResponse:
    """Get paginated list of articles for Load More functionality."""
    repo = ArticleRepository()

    # Get articles with one extra to check if there are more
    articles = repo.get_inbox(show_all=show_all, limit=limit + 1, offset=offset)
    has_more = len(articles) > limit
    articles = articles[:limit]

    # Calculate percentiles
    all_elo_ratings = sorted(repo.get_all_elo_ratings())
    items: list[dict[str, int | str | float | None]] = []

    for article in articles:
        percentile = 0
        if all_elo_ratings:
            below = sum(1 for r in all_elo_ratings if r < article.elo_rating)
            percentile = int((below / len(all_elo_ratings)) * 100)

        items.append(
            {
                "id": article.id,
                "title": article.title,
                "source": article.source,
                "elo_rating": article.elo_rating,
                "percentile": percentile,
                "reading_time_category": (
                    article.reading_time_category.value if article.reading_time_category else None
                ),
                "user_rating": article.user_rating,
                "generation_id": article.generation_id,
            }
        )

    return JSONResponse(
        content={
            "articles": items,
            "has_more": has_more,
            "next_offset": offset + limit,
        }
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
    """Update user thumbs rating on an article.

    REQ-RC-014: WHEN user provides thumbs up or thumbs down rating on an article
    THE SYSTEM SHALL store the rating alongside the LLM score

    Thumbs ratings:
        -1: Thumbs down
         0: No rating (clear)
         1: Thumbs up
    """
    repo = ArticleRepository()

    # Validate rating (-1, 0, or 1)
    if rating not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail="Rating must be -1, 0, or 1")

    # Verify article exists
    article_obj = repo.get_by_id(article_id)
    if not article_obj:
        raise HTTPException(status_code=404, detail="Article not found")

    repo.update_rating(article_id, rating)
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


# REQ-RC-019, REQ-RC-020: Heuristic-refiner routes


@router.get("/article/{article_id}/refine", response_class=HTMLResponse)
async def refine_article(
    request: Request,
    article_id: int,
    _username: Annotated[str, Depends(require_basic_auth)],
) -> HTMLResponse:
    """Display heuristic-refiner feedback form for an article.

    REQ-RC-019: WHEN user enters heuristic-refiner mode for an article
    THE SYSTEM SHALL call LLM API to characterize article using 5-Whats framework

    REQ-RC-020: THE SYSTEM SHALL present textarea for free-form feedback
    THE SYSTEM SHALL restore textarea content from localStorage if exists
    """
    from reader.refiner.characterization import CharacterizationError, characterize_article
    from reader.scoring.llm import get_content_preview

    repo = ArticleRepository()
    settings_repo = AppSettingsRepository()
    feedback_repo = HeuristicFeedbackRepository()

    article_obj = repo.get_by_id(article_id)
    app_settings = settings_repo.get_all()

    if not article_obj:
        raise HTTPException(status_code=404, detail="Article not found")

    # Check if feedback already exists
    existing_feedback = feedback_repo.get_by_article(article_id)
    if existing_feedback:
        # Redirect back to article if feedback already provided
        return templates.TemplateResponse(
            request=request,
            name="refine.html",
            context={
                "article": article_obj,
                "app_settings": app_settings,
                "existing_feedback": existing_feedback,
                "characterization": existing_feedback.characterization,
            },
        )

    # Get 5-Whats characterization
    characterization = None
    characterization_error = None
    try:
        characterization = await characterize_article(
            title=article_obj.title,
            source=article_obj.source,
            content_preview=get_content_preview(article_obj.content_markdown),
        )
    except CharacterizationError as e:
        characterization_error = str(e)

    return templates.TemplateResponse(
        request=request,
        name="refine.html",
        context={
            "article": article_obj,
            "app_settings": app_settings,
            "characterization": characterization,
            "characterization_error": characterization_error,
            "existing_feedback": None,
        },
    )


@router.post("/article/{article_id}/refine")
async def submit_refine_feedback(
    article_id: int,
    feedback_text: Annotated[str, Form()],
    characterization_json: Annotated[str, Form()] = "",
    _username: Annotated[str, Depends(require_basic_auth)] = "",
) -> RedirectResponse:
    """Submit heuristic-refiner feedback for an article.

    REQ-RC-020: WHEN user submits feedback
    THE SYSTEM SHALL store feedback with characterization and article linkage
    THE SYSTEM SHALL flag article as rating_refined = true
    THE SYSTEM SHALL clear localStorage draft
    """
    repo = ArticleRepository()
    feedback_repo = HeuristicFeedbackRepository()

    # Verify article exists
    article_obj = repo.get_by_id(article_id)
    if not article_obj:
        raise HTTPException(status_code=404, detail="Article not found")

    # Validate feedback
    if not feedback_text.strip():
        raise HTTPException(status_code=400, detail="Feedback text is required")

    # Create feedback entry
    feedback = HeuristicFeedbackCreate(
        article_id=article_id,
        feedback_text=feedback_text.strip(),
        characterization_json=characterization_json if characterization_json else None,
    )
    feedback_repo.create(feedback)

    # Mark article as having provided refinement feedback
    repo.mark_rating_refined(article_id, refined=True)

    return RedirectResponse(url=f"/article/{article_id}", status_code=303)


# REQ-RC-022: Prompt History routes


@router.get("/prompt-history", response_class=HTMLResponse)
async def prompt_history(
    request: Request,
    _username: Annotated[str, Depends(require_basic_auth)],
) -> HTMLResponse:
    """Display prompt evolution history.

    REQ-RC-022: WHEN user navigates to Prompt History page
    THE SYSTEM SHALL display all prompt generations with timestamps
    THE SYSTEM SHALL show diff between each generation and its predecessor
    """
    settings_repo = AppSettingsRepository()
    generation_repo = PromptGenerationRepository()

    app_settings = settings_repo.get_all()
    generations = generation_repo.get_all()

    return templates.TemplateResponse(
        request=request,
        name="prompt_history.html",
        context={
            "app_settings": app_settings,
            "generations": generations,
        },
    )


@router.get("/prompt-history/{generation_id}", response_class=HTMLResponse)
async def prompt_generation_detail(
    request: Request,
    generation_id: int,
    _username: Annotated[str, Depends(require_basic_auth)],
) -> HTMLResponse:
    """Display details for a specific prompt generation.

    REQ-RC-022: THE SYSTEM SHALL link each generation to the feedback items that produced it
    """
    settings_repo = AppSettingsRepository()
    generation_repo = PromptGenerationRepository()
    feedback_repo = HeuristicFeedbackRepository()

    app_settings = settings_repo.get_all()
    generation = generation_repo.get_by_id(generation_id)

    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")

    # Get feedback that produced this generation
    feedback_list = feedback_repo.get_by_generation(generation_id)

    return templates.TemplateResponse(
        request=request,
        name="prompt_generation.html",
        context={
            "app_settings": app_settings,
            "generation": generation,
            "feedback_list": feedback_list,
        },
    )
