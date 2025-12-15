"""Pairwise comparison using LLM.

REQ-RC-024: Compare Article Relevance via Pairwise Ranking
"""

import json
import logging

import httpx
from anthropic import Anthropic

from reader.config import LLMBackend, get_settings
from reader.models.elo import (
    ComparisonOutcome,
    PairwiseComparisonRequest,
    PairwiseComparisonResponse,
)

logger = logging.getLogger(__name__)

# REQ-RC-024: Pairwise comparison prompt
COMPARISON_PROMPT_TEMPLATE = """You are helping curate a personalized reading list. Compare these two articles and decide which one is MORE RELEVANT and INTERESTING to the user.

Article A: {title_a}
Source: {source_a}
Preview: {preview_a}

Article B: {title_b}
Source: {source_b}
Preview: {preview_b}

Which article is more relevant and worth reading? Consider:
- Topic relevance and substance
- Writing quality and clarity
- Practical value or insights
- Novelty and interest

Respond with valid JSON only:
{{
  "outcome": "a_wins" | "b_wins" | "tie",
  "reasoning": "Brief explanation (1-2 sentences)"
}}

If both are equally relevant, use "tie". Be decisive - prefer one unless they are truly equal."""


class ComparisonError(Exception):
    """Error during pairwise comparison."""


def _build_comparison_prompt(request: PairwiseComparisonRequest) -> str:
    """Build the comparison prompt from request data."""
    # For now, we'll use placeholders for source - will need to pass this through
    return COMPARISON_PROMPT_TEMPLATE.format(
        title_a=request.article_a_title,
        source_a="Article A",  # Will be enhanced when we have source info
        preview_a=request.article_a_preview,
        title_b=request.article_b_title,
        source_b="Article B",
        preview_b=request.article_b_preview,
    )


def _parse_comparison_response(text: str) -> PairwiseComparisonResponse:
    """Parse LLM response JSON into PairwiseComparisonResponse."""
    # Find JSON in response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ComparisonError(f"No JSON found in response: {text[:200]}")

    json_str = text[start:end]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ComparisonError(f"Invalid JSON in response: {e}") from e

    # Validate outcome
    outcome_str = data.get("outcome", "tie")
    try:
        outcome = ComparisonOutcome(outcome_str)
    except ValueError:
        logger.warning(f"Invalid outcome '{outcome_str}', defaulting to tie")
        outcome = ComparisonOutcome.TIE

    return PairwiseComparisonResponse(
        outcome=outcome,
        reasoning=data.get("reasoning", "No reasoning provided"),
    )


async def compare_with_anthropic(prompt: str) -> str:
    """Compare using Anthropic Claude API."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ComparisonError("READER_ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text  # type: ignore[union-attr]


async def compare_with_ollama(prompt: str) -> str:
    """Compare using Ollama API."""
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


async def compare_articles(request: PairwiseComparisonRequest) -> PairwiseComparisonResponse:
    """Compare two articles using LLM and return which is more relevant.

    REQ-RC-024: WHEN comparing two articles
    THE SYSTEM SHALL ask Claude which is more relevant
    THE SYSTEM SHALL return outcome (a_wins, b_wins, or tie) with reasoning

    Args:
        request: Comparison request with article IDs, titles, and previews

    Returns:
        Comparison response with outcome and reasoning

    Raises:
        ComparisonError: If comparison fails
    """
    settings = get_settings()
    prompt = _build_comparison_prompt(request)

    logger.info(
        "Comparing articles %d vs %d with %s",
        request.article_a_id,
        request.article_b_id,
        settings.llm_backend.value,
    )

    try:
        if settings.llm_backend == LLMBackend.ANTHROPIC:
            response_text = await compare_with_anthropic(prompt)
        else:
            response_text = await compare_with_ollama(prompt)

        return _parse_comparison_response(response_text)
    except httpx.HTTPError as e:
        raise ComparisonError(f"HTTP error calling LLM: {e}") from e
    except Exception as e:
        raise ComparisonError(f"Error comparing articles: {e}") from e
