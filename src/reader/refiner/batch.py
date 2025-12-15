"""Daily batch processing for prompt refinement.

REQ-RC-021: Refine Prompts from Daily Feedback
"""

import difflib
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
from anthropic import Anthropic

from reader.config import LLMBackend, get_settings
from reader.db.repository import (
    HeuristicFeedbackRepository,
    PromptGenerationRepository,
)
from reader.models.scoring import HeuristicFeedback, PromptGeneration

logger = logging.getLogger(__name__)

REFINEMENT_PROMPT = """You are helping refine a content curation prompt based on user feedback.

Current prompt:
---
{current_prompt}
---

User feedback from the past 24 hours ({feedback_count} items):
{feedback_items}

Based on this feedback, suggest improvements to the prompt. Consider:
- Patterns in what users liked vs disliked
- Article characteristics that correlate with positive/negative feedback
- Specific adjustments to scoring criteria or preferences

Respond in JSON format:
{{
  "analysis": "Brief analysis of the feedback patterns (2-3 sentences)",
  "changes": ["List of specific changes to make"],
  "new_prompt": "The complete updated prompt text"
}}

IMPORTANT:
- The new_prompt must be a complete, working prompt
- Preserve the JSON output format instructions in the prompt
- Make incremental improvements, not wholesale rewrites
- If no meaningful patterns emerge, return the original prompt with minimal changes"""


class RefinementError(Exception):
    """Error during prompt refinement."""


def _compute_diff(old_text: str, new_text: str) -> str:
    """Compute a word-level diff between old and new prompt.

    REQ-RC-022: THE SYSTEM SHALL compute word-level diff between each generation
    """
    old_words = old_text.split()
    new_words = new_text.split()

    diff = difflib.unified_diff(
        old_words,
        new_words,
        fromfile="previous",
        tofile="current",
        lineterm="",
        n=3,
    )

    return " ".join(diff)


def _format_feedback_items(feedback_list: list[HeuristicFeedback]) -> str:
    """Format feedback items for the refinement prompt."""
    items: list[str] = []
    for i, feedback in enumerate(feedback_list, 1):
        item_lines = [f"Feedback #{i}:"]
        item_lines.append(f"  User comment: {feedback.feedback_text}")
        if feedback.characterization:
            char = feedback.characterization
            item_lines.append(f"  Article: topic={char.topic}, style={char.style}, depth={char.depth}")
        items.append("\n".join(item_lines))
    return "\n\n".join(items)


async def refine_with_anthropic(prompt: str) -> str:
    """Refine using Anthropic Claude API."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RefinementError("READER_ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text  # type: ignore[union-attr]


async def refine_with_ollama(prompt: str) -> str:
    """Refine using Ollama API."""
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


def _parse_refinement_response(text: str) -> dict[str, str | list[str]]:
    """Parse LLM response JSON."""
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise RefinementError(f"No JSON found in response: {text[:200]}")

    json_str = text[start:end]
    try:
        data: dict[str, str | list[str]] = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise RefinementError(f"Invalid JSON in response: {e}") from e

    if "new_prompt" not in data:
        raise RefinementError("Response missing 'new_prompt' field")

    return data


async def run_daily_refinement() -> PromptGeneration | None:
    """Run daily prompt refinement batch job.

    REQ-RC-021: WHEN UTC midnight occurs
    THE SYSTEM SHALL collect all heuristic-refiner feedback from the past 24 hours

    WHEN feedback exists for processing
    THE SYSTEM SHALL call LLM with structured refinement prompt
    THE SYSTEM SHALL create new prompt generation from LLM response
    THE SYSTEM SHALL store diff from previous generation

    Returns:
        New PromptGeneration if created, None if no feedback to process
    """
    settings = get_settings()
    feedback_repo = HeuristicFeedbackRepository()
    generation_repo = PromptGenerationRepository()

    # Get feedback from past 24 hours
    since = datetime.now(UTC) - timedelta(hours=24)
    feedback_list = feedback_repo.get_unprocessed_since(since)

    if not feedback_list:
        logger.info("No feedback to process for daily refinement")
        return None

    logger.info("Processing %d feedback items for daily refinement", len(feedback_list))

    # Get current active generation
    current_gen = generation_repo.get_active()
    if not current_gen:
        logger.error("No active prompt generation found")
        return None

    # Build refinement prompt
    prompt = REFINEMENT_PROMPT.format(
        current_prompt=current_gen.prompt_text,
        feedback_count=len(feedback_list),
        feedback_items=_format_feedback_items(feedback_list),
    )

    # Call LLM
    try:
        if settings.llm_backend == LLMBackend.ANTHROPIC:
            response_text = await refine_with_anthropic(prompt)
        else:
            response_text = await refine_with_ollama(prompt)

        result = _parse_refinement_response(response_text)
    except (httpx.HTTPError, RefinementError) as e:
        logger.error("Refinement failed: %s", e)
        return None

    new_prompt_text = str(result["new_prompt"])

    # Compute diff
    diff = _compute_diff(current_gen.prompt_text, new_prompt_text)

    # Create new generation
    new_gen_id = generation_repo.create(
        prompt_text=new_prompt_text,
        diff_from_previous=diff,
        feedback_count=len(feedback_list),
        set_active=True,
    )

    # Link feedback to new generation
    feedback_ids = [f.id for f in feedback_list]
    feedback_repo.link_to_generation(feedback_ids, new_gen_id)

    logger.info(
        "Created new prompt generation %d from %d feedback items",
        new_gen_id,
        len(feedback_list),
    )

    # Retrieve and return the new generation
    return generation_repo.get_by_id(new_gen_id)


def schedule_midnight_job() -> None:
    """Schedule the midnight refinement job.

    This should be called during app startup to schedule the daily job.
    The actual scheduling mechanism depends on the deployment environment.
    """
    # For now, this is a placeholder. In production, this would:
    # 1. Calculate time until next UTC midnight
    # 2. Schedule run_daily_refinement() to run at that time
    # 3. Reschedule for the next day after completion
    #
    # Options include:
    # - APScheduler
    # - Celery beat
    # - System cron
    # - Kubernetes CronJob
    logger.info("Midnight refinement job scheduling placeholder - implement per deployment")
