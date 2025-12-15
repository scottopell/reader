"""Article characterization using 5-Whats analysis.

REQ-RC-019: Characterize Articles for Refinement
"""

import json
import logging

import httpx
from anthropic import Anthropic

from reader.config import LLMBackend, get_settings
from reader.models.scoring import FiveWhats

logger = logging.getLogger(__name__)

CHARACTERIZATION_PROMPT = """Analyze this article and provide a 5-Whats characterization:

Title: {title}
Source: {source}
Content preview: {content_preview}

Provide 5 characterizations about this article. Each should be a brief phrase (2-5 words):

1. Topic: What is this article about? (e.g., "Rust memory management", "startup funding")
2. Style: What writing style is used? (e.g., "tutorial", "opinion piece", "news report", "deep dive")
3. Depth: How deep is the coverage? (e.g., "surface level", "intermediate", "expert level")
4. Emotion: What emotional impact does it have? (e.g., "neutral/informative", "exciting", "concerning", "inspiring")
5. Level: What reading level is it written at? (e.g., "beginner friendly", "intermediate", "advanced technical")

Respond in JSON format:
{{
  "topic": "...",
  "style": "...",
  "depth": "...",
  "emotion": "...",
  "level": "..."
}}"""


class CharacterizationError(Exception):
    """Error during article characterization."""


async def characterize_with_anthropic(prompt: str) -> str:
    """Characterize using Anthropic Claude API."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise CharacterizationError("READER_ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text  # type: ignore[union-attr]


async def characterize_with_ollama(prompt: str) -> str:
    """Characterize using Ollama API."""
    settings = get_settings()
    url = f"{settings.ollama_base_url}/api/generate"

    async with httpx.AsyncClient(timeout=60.0) as client:
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


def _parse_characterization(text: str) -> FiveWhats:
    """Parse LLM response JSON into FiveWhats model."""
    # Find JSON in response (may have surrounding text)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise CharacterizationError(f"No JSON found in response: {text[:200]}")

    json_str = text[start:end]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise CharacterizationError(f"Invalid JSON in response: {e}") from e

    return FiveWhats(
        topic=data.get("topic", "unknown"),
        style=data.get("style", "unknown"),
        depth=data.get("depth", "unknown"),
        emotion=data.get("emotion", "unknown"),
        level=data.get("level", "unknown"),
    )


async def characterize_article(
    title: str,
    source: str,
    content_preview: str,
) -> FiveWhats:
    """Characterize an article using the 5-Whats framework.

    REQ-RC-019: WHEN user enters heuristic-refiner mode for an article
    THE SYSTEM SHALL call LLM API to characterize the article using 5-Whats framework:
    - What is the article about? (topic)
    - What writing style is used? (style)
    - How deep is the coverage? (depth)
    - What emotional impact does it have? (emotion)
    - What reading level is it written at? (level)

    Returns:
        FiveWhats model with characterization results
    """
    settings = get_settings()

    prompt = CHARACTERIZATION_PROMPT.format(
        title=title,
        source=source,
        content_preview=content_preview,
    )

    logger.info(
        "Characterizing article '%s' with %s",
        title[:50],
        settings.llm_backend.value,
    )

    try:
        if settings.llm_backend == LLMBackend.ANTHROPIC:
            response_text = await characterize_with_anthropic(prompt)
        else:
            response_text = await characterize_with_ollama(prompt)

        return _parse_characterization(response_text)
    except httpx.HTTPError as e:
        raise CharacterizationError(f"HTTP error calling LLM: {e}") from e
    except Exception as e:
        if isinstance(e, CharacterizationError):
            raise
        raise CharacterizationError(f"Error characterizing article: {e}") from e
