"""LLM-based article scoring.

REQ-RC-004: Understand Relevance of Each Article
REQ-RC-005: Track Scoring Prompt Changes Over Time
"""

import json
import logging

import httpx
from anthropic import Anthropic

from reader.config import LLMBackend, get_settings
from reader.models.article import ReadingTimeCategory
from reader.models.scoring import ScoringRequest, ScoringResponse
from reader.scoring.prompts import DEFAULT_PROMPT

logger = logging.getLogger(__name__)

# Preview length for scoring (first ~500 words)
CONTENT_PREVIEW_WORDS = 500


class ScoringError(Exception):
    """Error during article scoring."""


def _build_prompt(request: ScoringRequest) -> str:
    """Build the scoring prompt from template and request."""
    return DEFAULT_PROMPT.format(
        title=request.title,
        source=request.source,
        content_preview=request.content_preview,
    )


def _parse_response(text: str) -> ScoringResponse:
    """Parse LLM response JSON into ScoringResponse."""
    # Find JSON in response (may have surrounding text)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ScoringError(f"No JSON found in response: {text[:200]}")

    json_str = text[start:end]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ScoringError(f"Invalid JSON in response: {e}") from e

    # Validate and convert reading_time
    reading_time_str = data.get("reading_time", "medium")
    try:
        reading_time = ReadingTimeCategory(reading_time_str)
    except ValueError:
        reading_time = ReadingTimeCategory.MEDIUM

    # Clamp score to valid range
    score = float(data.get("score", 5))
    score = max(1.0, min(10.0, score))

    return ScoringResponse(
        score=score,
        reasoning=data.get("reasoning", "No reasoning provided"),
        reading_time=reading_time,
        tags=data.get("tags", [])[:5],  # Max 5 tags
    )


async def score_with_anthropic(prompt: str) -> str:
    """Score using Anthropic Claude API."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ScoringError("READER_ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text  # type: ignore[union-attr]


async def score_with_ollama(prompt: str) -> str:
    """Score using Ollama API."""
    settings = get_settings()
    url = f"{settings.ollama_base_url}/api/generate"

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            url,
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
        )
        response.raise_for_status()
        data: dict[str, str] = response.json()
        return data.get("response", "")


async def score_article(request: ScoringRequest) -> ScoringResponse:
    """Score an article using the configured LLM backend.

    REQ-RC-004: WHEN new article content is extracted
    THE SYSTEM SHALL score relevance 1-10 using Claude API
    THE SYSTEM SHALL include brief reasoning with each score
    THE SYSTEM SHALL estimate reading time category
    """
    settings = get_settings()
    prompt = _build_prompt(request)

    logger.info(
        "Scoring article %d with %s (%s)",
        request.article_id,
        settings.llm_backend.value,
        settings.ollama_model
        if settings.llm_backend == LLMBackend.OLLAMA
        else settings.anthropic_model,
    )

    try:
        if settings.llm_backend == LLMBackend.ANTHROPIC:
            response_text = await score_with_anthropic(prompt)
        else:
            response_text = await score_with_ollama(prompt)

        return _parse_response(response_text)
    except httpx.HTTPError as e:
        raise ScoringError(f"HTTP error calling LLM: {e}") from e
    except Exception as e:
        raise ScoringError(f"Error scoring article: {e}") from e


def get_content_preview(content: str, max_words: int = CONTENT_PREVIEW_WORDS) -> str:
    """Get first N words of content for scoring."""
    words = content.split()
    if len(words) <= max_words:
        return content
    return " ".join(words[:max_words]) + "..."
