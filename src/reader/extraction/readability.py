"""Content extraction using Readability.

REQ-RC-006: Extract Clean Article Content
"""

from dataclasses import dataclass
from typing import cast

import httpx
from markdownify import markdownify
from readability import Document

from reader.models.article import ExtractionStatus

# Minimum content length to consider extraction successful
MIN_CONTENT_LENGTH = 100


@dataclass
class ExtractionResult:
    """Result of content extraction from a URL."""

    title: str
    content_markdown: str
    word_count: int
    status: ExtractionStatus
    error: str | None = None


async def extract_from_url(url: str, timeout_seconds: float = 30.0) -> ExtractionResult:
    """Extract article content from a URL.

    REQ-RC-006: WHEN extracting content from HTML
    THE SYSTEM SHALL use Readability-style extraction to get article body

    REQ-RC-006: WHEN extraction fails or returns minimal content
    THE SYSTEM SHALL flag article for manual review

    REQ-RC-006: THE SYSTEM SHALL store extracted content as Markdown
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={"User-Agent": "Reader/1.0 (content curation tool)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
    except httpx.TimeoutException:
        return ExtractionResult(
            title="",
            content_markdown="",
            word_count=0,
            status=ExtractionStatus.FAILED,
            error=f"Timeout fetching URL after {timeout_seconds}s",
        )
    except httpx.HTTPStatusError as e:
        return ExtractionResult(
            title="",
            content_markdown="",
            word_count=0,
            status=ExtractionStatus.FAILED,
            error=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
        )
    except httpx.RequestError as e:
        return ExtractionResult(
            title="",
            content_markdown="",
            word_count=0,
            status=ExtractionStatus.FAILED,
            error=f"Request failed: {e}",
        )

    return extract_from_html(html)


def extract_from_html(html: str) -> ExtractionResult:
    """Extract article content from HTML string.

    Useful for email content or pre-fetched HTML.
    """
    try:
        doc = Document(html)
        title = doc.title()
        content_html = cast("str", doc.summary())
    except Exception as e:
        return ExtractionResult(
            title="",
            content_markdown="",
            word_count=0,
            status=ExtractionStatus.FAILED,
            error=f"Readability extraction failed: {e}",
        )

    # Convert HTML to Markdown
    content_markdown = markdownify(content_html, heading_style="ATX", strip=["script", "style"])

    # Clean up excessive whitespace
    content_markdown = _clean_markdown(content_markdown)

    word_count = len(content_markdown.split())

    # REQ-RC-006: Flag minimal content for manual review
    if len(content_markdown.strip()) < MIN_CONTENT_LENGTH:
        return ExtractionResult(
            title=title,
            content_markdown=content_markdown,
            word_count=word_count,
            status=ExtractionStatus.MANUAL_REVIEW,
            error="Extracted content too short, may need manual review",
        )

    return ExtractionResult(
        title=title,
        content_markdown=content_markdown,
        word_count=word_count,
        status=ExtractionStatus.SUCCESS,
    )


def _clean_markdown(text: str) -> str:
    """Clean up markdown output from markdownify."""
    lines = text.split("\n")
    cleaned: list[str] = []
    blank_count = 0

    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            blank_count += 1
            # Allow max 2 consecutive blank lines
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(stripped)

    return "\n".join(cleaned).strip()
