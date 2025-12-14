"""RSS feed ingestion.

REQ-RC-002: Discover New Content from RSS Feeds
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx

from reader.db.repository import ArticleRepository, FeedSourceRepository
from reader.extraction.readability import extract_from_html, extract_from_url
from reader.models.article import ArticleCreate, ArticleScore, ExtractionStatus
from reader.models.scoring import ScoringRequest
from reader.models.source import FeedSource, SourceType
from reader.scoring.llm import ScoringError, get_content_preview, score_article

logger = logging.getLogger(__name__)

# REQ-RC-002: Polite crawling delays
MIN_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 5.0

# User agent for polite crawling
USER_AGENT = "Reader/1.0 (content curation tool; +https://github.com/scottopell/reader)"


@dataclass
class RSSEntry:
    """Parsed RSS entry."""

    title: str
    link: str
    author: str | None
    content_html: str | None  # Full content if available in feed
    published: datetime | None


@dataclass
class IngestionResult:
    """Result of ingesting a single feed."""

    source_id: int
    feed_url: str
    entries_found: int
    entries_new: int
    entries_scored: int
    errors: list[str]


def _parse_entry(entry: Any) -> RSSEntry:
    """Parse a feedparser entry into our model.

    Uses Any type because feedparser doesn't have type stubs and
    FeedParserDict is effectively untyped.
    """
    # Get content - try multiple places feeds put it
    content_html: str | None = None
    if hasattr(entry, "content") and entry.content:
        content_list: list[dict[str, Any]] = entry.content
        content_html = str(content_list[0].get("value", ""))
    elif hasattr(entry, "summary"):
        content_html = str(entry.summary)

    # Parse published date
    published: datetime | None = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            time_tuple: tuple[int, ...] = entry.published_parsed[:6]
            published = datetime(
                time_tuple[0],  # year
                time_tuple[1],  # month
                time_tuple[2],  # day
                time_tuple[3],  # hour
                time_tuple[4],  # minute
                time_tuple[5],  # second
                tzinfo=UTC,
            )
        except (ValueError, TypeError, IndexError):
            pass

    return RSSEntry(
        title=str(entry.get("title", "Untitled")),
        link=str(entry.get("link", "")),
        author=entry.get("author"),
        content_html=content_html,
        published=published,
    )


def _can_fetch(url: str, robot_parsers: dict[str, RobotFileParser | None]) -> bool:
    """Check robots.txt to see if we can fetch this URL.

    REQ-RC-002: THE SYSTEM SHALL respect robots.txt
    """
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Cache robot parser per domain
    if base_url not in robot_parsers:
        rp = RobotFileParser()
        robots_url = f"{base_url}/robots.txt"
        try:
            rp.set_url(robots_url)
            rp.read()
            robot_parsers[base_url] = rp
        except Exception:
            # If we can't read robots.txt, assume allowed
            robot_parsers[base_url] = None

    parser = robot_parsers[base_url]
    if parser is None:
        return True

    return parser.can_fetch(USER_AGENT, url)


async def _polite_delay() -> None:
    """Add a polite delay between requests.

    REQ-RC-002: THE SYSTEM SHALL use polite crawling (1-5s delays)
    """
    delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
    await asyncio.sleep(delay)


async def _process_entry(
    entry: RSSEntry,
    source: FeedSource,
    article_repo: ArticleRepository,
    robot_parsers: dict[str, RobotFileParser | None],
    _client: httpx.AsyncClient,
) -> tuple[int | None, str | None]:
    """Process a single RSS entry.

    Returns (article_id, error_message) - article_id is None if skipped/failed.
    """
    # Skip if already in database
    if article_repo.exists_by_url(entry.link):
        return None, None

    # Check robots.txt
    if not _can_fetch(entry.link, robot_parsers):
        logger.info("Skipping %s - disallowed by robots.txt", entry.link)
        return None, f"Blocked by robots.txt: {entry.link}"

    # Try to extract content
    if entry.content_html and len(entry.content_html) > 200:
        # Full content available in feed
        extraction = extract_from_html(entry.content_html)
        # Use entry title if extraction didn't find one
        if not extraction.title:
            extraction = type(extraction)(
                title=entry.title,
                content_markdown=extraction.content_markdown,
                word_count=extraction.word_count,
                status=extraction.status,
                error=extraction.error,
            )
    else:
        # Need to fetch the article
        await _polite_delay()
        extraction = await extract_from_url(entry.link)
        # Use entry title if extraction didn't find one
        if not extraction.title:
            extraction = type(extraction)(
                title=entry.title,
                content_markdown=extraction.content_markdown,
                word_count=extraction.word_count,
                status=extraction.status,
                error=extraction.error,
            )

    # Create article
    article_data = ArticleCreate(
        source=f"rss:{source.identifier}",
        title=extraction.title or entry.title,
        url=entry.link,
        author=entry.author,
        content_markdown=extraction.content_markdown,
        word_count=extraction.word_count,
        extraction_status=extraction.status,
        extraction_error=extraction.error,
    )
    article_id = article_repo.create(article_data)
    logger.info("Created article %d from RSS: %s", article_id, entry.title)

    return article_id, None


async def _score_article(article_id: int, article_repo: ArticleRepository) -> bool:
    """Score an article with the LLM. Returns True on success."""
    article = article_repo.get_by_id(article_id)
    if not article:
        return False

    # Skip scoring if extraction failed
    if article.extraction_status != ExtractionStatus.SUCCESS.value:
        return False

    try:
        scoring_request = ScoringRequest(
            article_id=article_id,
            title=article.title,
            source=article.source,
            content_preview=get_content_preview(article.content_markdown),
        )
        scoring_response = await score_article(scoring_request)

        score_data = ArticleScore(
            llm_score=scoring_response.score,
            llm_reasoning=scoring_response.reasoning,
            reading_time_category=scoring_response.reading_time,
            tags=scoring_response.tags,
            prompt_version=scoring_response.prompt_version,
        )
        article_repo.update_score(article_id, score_data)
        logger.info("Scored article %d: %.1f", article_id, scoring_response.score)
        return True
    except ScoringError as e:
        logger.warning("Scoring failed for article %d: %s", article_id, e)
        return False


async def ingest_feed(source: FeedSource) -> IngestionResult:
    """Ingest articles from a single RSS feed.

    REQ-RC-002: WHEN RSS feed check interval elapses
    THE SYSTEM SHALL poll configured RSS feeds for new entries
    """
    result = IngestionResult(
        source_id=source.id,
        feed_url=source.identifier,
        entries_found=0,
        entries_new=0,
        entries_scored=0,
        errors=[],
    )

    logger.info("Ingesting RSS feed: %s", source.identifier)

    # Parse feed - feedparser is untyped, so we cast to Any
    try:
        feed = cast("Any", feedparser).parse(source.identifier)
        if feed.bozo and not feed.entries:
            result.errors.append(f"Feed parse error: {feed.bozo_exception}")
            return result
    except Exception as e:
        result.errors.append(f"Failed to parse feed: {e}")
        return result

    feed_entries: list[Any] = list(feed.entries)
    entries = [_parse_entry(e) for e in feed_entries]
    result.entries_found = len(entries)

    # Filter out entries without links
    entries = [e for e in entries if e.link]

    article_repo = ArticleRepository()
    source_repo = FeedSourceRepository()
    robot_parsers: dict[str, RobotFileParser | None] = {}

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        new_article_ids: list[int] = []

        for entry in entries:
            article_id, error = await _process_entry(
                entry, source, article_repo, robot_parsers, client
            )
            if error:
                result.errors.append(error)
            if article_id:
                result.entries_new += 1
                new_article_ids.append(article_id)

        # Score new articles
        for article_id in new_article_ids:
            if await _score_article(article_id, article_repo):
                result.entries_scored += 1

    # Update last_checked timestamp
    source_repo.update_last_checked(source.id)

    logger.info(
        "Feed %s: found=%d new=%d scored=%d errors=%d",
        source.identifier,
        result.entries_found,
        result.entries_new,
        result.entries_scored,
        len(result.errors),
    )

    return result


async def ingest_all_rss() -> list[IngestionResult]:
    """Ingest articles from all enabled RSS feeds.

    REQ-RC-002: Main entry point for RSS ingestion.
    Runs sequentially to be polite to servers.
    """
    source_repo = FeedSourceRepository()
    sources = source_repo.get_enabled()

    # Filter to RSS sources only
    rss_sources = [s for s in sources if s.type == SourceType.RSS]

    if not rss_sources:
        logger.info("No enabled RSS feeds configured")
        return []

    logger.info("Starting RSS ingestion for %d feeds", len(rss_sources))

    results: list[IngestionResult] = []
    for source in rss_sources:
        result = await ingest_feed(source)
        results.append(result)
        # Add delay between feeds to be polite
        if source != rss_sources[-1]:
            await _polite_delay()

    total_new = sum(r.entries_new for r in results)
    total_scored = sum(r.entries_scored for r in results)
    logger.info("RSS ingestion complete: %d new articles, %d scored", total_new, total_scored)

    return results


if __name__ == "__main__":
    import sys

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run ingestion
    results = asyncio.run(ingest_all_rss())

    # Print summary
    total_found = sum(r.entries_found for r in results)
    total_new = sum(r.entries_new for r in results)
    total_scored = sum(r.entries_scored for r in results)
    total_errors = sum(len(r.errors) for r in results)

    print("\nRSS Ingestion Summary:")
    print(f"  Feeds processed: {len(results)}")
    print(f"  Entries found: {total_found}")
    print(f"  New articles: {total_new}")
    print(f"  Articles scored: {total_scored}")
    print(f"  Errors: {total_errors}")

    if total_errors > 0:
        print("\nErrors:")
        for result in results:
            for error in result.errors:
                print(f"  [{result.feed_url}] {error}")

    sys.exit(0 if total_errors == 0 else 1)
