# Reading Curation System - Technical Design

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Input Sources                                │
├─────────────────────────────────────────────────────────────────┤
│  [Email IMAP]      [RSS Feeds]        [Manual URL API]          │
│       │                 │                    │                   │
│       └────────────────┼────────────────────┘                   │
│                        ▼                                         │
│              ┌─────────────────┐                                │
│              │ Content Extractor│                                │
│              │  (Readability)   │                                │
│              └────────┬────────┘                                │
│                       ▼                                          │
│              ┌─────────────────┐                                │
│              │   LLM Scorer    │                                │
│              │  (Claude API)   │                                │
│              └────────┬────────┘                                │
│                       ▼                                          │
│              ┌─────────────────┐                                │
│              │    SQLite DB    │                                │
│              └────────┬────────┘                                │
│                       ▼                                          │
│              ┌─────────────────┐                                │
│              │     Web UI      │                                │
│              │    (FastAPI)    │                                │
│              └────────┬────────┘                                │
│                       ▼                                          │
│              ┌─────────────────┐                                │
│              │ Bundle Generator│                                │
│              │  (.txt files)   │                                │
│              └─────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

## Data Models

### SQLite Schema

```sql
-- REQ-RC-001, REQ-RC-002, REQ-RC-003, REQ-RC-006: Article storage
CREATE TABLE articles (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,              -- 'email:sender@domain.com', 'rss:feed-url', 'manual'
  title TEXT NOT NULL,
  author TEXT,
  url TEXT,
  content_markdown TEXT NOT NULL,    -- Extracted content as Markdown
  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  -- REQ-RC-004 (DEPRECATED), REQ-RC-024, REQ-RC-025: Elo-based scoring
  llm_score REAL,                    -- DEPRECATED: 1-10 relevance score (kept for migration)
  elo_rating REAL DEFAULT 1500,      -- REQ-RC-025: Elo rating (unbounded, default 1500)
  elo_comparisons INTEGER DEFAULT 0, -- REQ-RC-028: Number of comparisons completed
  elo_confidence BOOLEAN DEFAULT 0,  -- REQ-RC-025: TRUE when >= 7 comparisons done
  llm_reasoning TEXT,                -- Brief explanation (from comparisons)
  reading_time_category TEXT,        -- 'quick', 'medium', 'deep'
  word_count INTEGER,
  tags TEXT,                         -- JSON array

  -- REQ-RC-005, REQ-RC-008: Prompt versioning and generation tracking
  prompt_version TEXT,               -- DEPRECATED: use generation_id instead
  generation_id INTEGER,             -- FK to prompt_generations (which generation scored this)
  scored_at TIMESTAMP,

  -- REQ-RC-014: User rating (thumbs up/down)
  user_rating SMALLINT,              -- -1 (thumbs down), 0 (no rating), 1 (thumbs up)
  rating_refined BOOLEAN DEFAULT 0,  -- Whether user entered heuristic-refiner for this article
  rated_at TIMESTAMP,

  -- REQ-RC-009: Bundle tracking
  in_bundle BOOLEAN DEFAULT 0,
  bundle_added_at TIMESTAMP,

  -- REQ-RC-006: Extraction status
  extraction_status TEXT DEFAULT 'success',  -- 'success', 'failed', 'manual_review'
  extraction_error TEXT,

  FOREIGN KEY (generation_id) REFERENCES prompt_generations(id)
);

CREATE INDEX idx_articles_score ON articles(llm_score DESC);
CREATE INDEX idx_articles_elo ON articles(elo_rating DESC);  -- REQ-RC-024: Sort by Elo
CREATE INDEX idx_articles_received ON articles(received_at DESC);
CREATE INDEX idx_articles_generation ON articles(generation_id);
CREATE INDEX idx_articles_rating ON articles(user_rating);
CREATE INDEX idx_articles_bundle ON articles(in_bundle);

-- REQ-RC-028: Pairwise comparison history
CREATE TABLE elo_comparisons (
  id INTEGER PRIMARY KEY,
  article_a_id INTEGER NOT NULL,     -- First article in comparison
  article_b_id INTEGER NOT NULL,     -- Second article in comparison
  winner_id INTEGER,                 -- Article that won (NULL for tie)
  llm_reasoning TEXT,                -- LLM explanation for choice
  article_a_elo_before REAL,         -- Elo rating before comparison
  article_b_elo_before REAL,
  article_a_elo_after REAL,          -- Elo rating after comparison
  article_b_elo_after REAL,
  k_factor INTEGER DEFAULT 32,       -- K-factor used in this comparison
  generation_id INTEGER,             -- Which prompt generation performed comparison
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (article_a_id) REFERENCES articles(id) ON DELETE CASCADE,
  FOREIGN KEY (article_b_id) REFERENCES articles(id) ON DELETE CASCADE,
  FOREIGN KEY (winner_id) REFERENCES articles(id) ON DELETE SET NULL,
  FOREIGN KEY (generation_id) REFERENCES prompt_generations(id)
);

CREATE INDEX idx_comparisons_article_a ON elo_comparisons(article_a_id);
CREATE INDEX idx_comparisons_article_b ON elo_comparisons(article_b_id);
CREATE INDEX idx_comparisons_generation ON elo_comparisons(generation_id);

-- REQ-RC-011: Full-text search
CREATE VIRTUAL TABLE articles_fts USING fts5(
  title, content_markdown, tags,
  content='articles',
  content_rowid='id'
);

-- REQ-RC-015: Feed source configuration
CREATE TABLE feed_sources (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,                -- 'email', 'rss'
  identifier TEXT NOT NULL,          -- Email sender pattern or RSS URL
  display_name TEXT,
  enabled BOOLEAN DEFAULT 1,
  last_checked TIMESTAMP,
  check_interval_hours INTEGER DEFAULT 6,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- REQ-RC-005, REQ-RC-021, REQ-RC-022: Prompt generation tracking
CREATE TABLE prompt_generations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Generation number (1, 2, 3, ...)
  prompt_text TEXT NOT NULL,             -- Full prompt text
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  diff_from_previous TEXT,               -- Word-diff from previous generation
  feedback_count INTEGER DEFAULT 0,      -- Number of feedback items that produced this generation
  is_active BOOLEAN DEFAULT 0            -- Currently active generation for new scoring
);

-- REQ-RC-019, REQ-RC-020, REQ-RC-021: Heuristic-refiner feedback
CREATE TABLE heuristic_feedback (
  id INTEGER PRIMARY KEY,
  article_id INTEGER NOT NULL,
  feedback_text TEXT NOT NULL,           -- User-provided feedback
  characterization_json TEXT,            -- 5-Whats result from LLM (JSON)
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  generation_id INTEGER,                 -- FK to prompt_generations (generation this feedback produced, NULL until batch runs)

  FOREIGN KEY (article_id) REFERENCES articles(id),
  FOREIGN KEY (generation_id) REFERENCES prompt_generations(id)
);

CREATE INDEX idx_feedback_article ON heuristic_feedback(article_id);
CREATE INDEX idx_feedback_generation ON heuristic_feedback(generation_id);
CREATE INDEX idx_feedback_created ON heuristic_feedback(created_at);

-- REQ-RC-023: Application settings
CREATE TABLE app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Seed default app title
INSERT INTO app_settings (key, value) VALUES ('app_title', 'nerd-reader');

-- REQ-RC-013: Eval metrics (updated for generation-based analysis)
CREATE TABLE eval_metrics (
  id INTEGER PRIMARY KEY,
  generation_id INTEGER,
  date DATE,
  total_articles INTEGER,
  high_scored_articles INTEGER,        -- Articles with score >= 7
  low_scored_articles INTEGER,         -- Articles with score < 7
  high_scored_thumbs_up INTEGER,       -- Thumbs up in high-scored
  low_scored_thumbs_up INTEGER,        -- Thumbs up in low-scored
  precision_high REAL,                 -- % thumbs up in high-scored
  precision_low REAL,                  -- % thumbs up in low-scored
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (generation_id) REFERENCES prompt_generations(id)
);

-- REQ-RC-016: Auth credentials (separate file recommended)
CREATE TABLE auth_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

## API Contracts

### Web UI Endpoints

#### GET /inbox

**REQ-RC-008, REQ-RC-012**

Returns paginated article list sorted by score.

Query params:

- `show_all=1` - Include all articles regardless of score
- `page=N` - Pagination (default: 1)

Response: HTML page with article cards showing title, source, score, reading
time, LLM reasoning.

#### GET /article/:id

**REQ-RC-010**

Returns full article reading view.

Response: HTML page with article content rendered from Markdown.

#### POST /article/:id/decision

**REQ-RC-014**

Records user decision on article.

Body: `{ "decision": "sent" | "skipped" | "read", "rating": 1-5 (optional) }`

#### GET /archive

**REQ-RC-011**

Search past articles.

Query params:

- `q=search+terms` - Search query
- `page=N` - Pagination

Response: HTML page with search results.

#### GET /stats

**REQ-RC-013**

Returns eval metrics dashboard.

Response: HTML page with precision/recall charts and trends.

#### GET /settings

**REQ-RC-015**

Manage feed sources.

Response: HTML page with source list and add/edit forms.

#### POST /settings/sources

**REQ-RC-015**

Add or update feed source.

Body:

```json
{
  "type": "email" | "rss",
  "identifier": "...",
  "display_name": "...",
  "enabled": true
}
```

### API Endpoints (API Key Required)

#### POST /api/article

**REQ-RC-003, REQ-RC-017**

Submit URL for extraction and scoring.

Headers: `Authorization: Bearer <API_KEY>`

Body: `{ "url": "https://..." }`

Response: `{ "status": "queued", "message": "Article queued for scoring" }`

#### GET /api/bundle

**REQ-RC-018**

Download bundle of selected articles.

Headers: `Authorization: Bearer <API_KEY>`

Response: ZIP file containing individual .txt files.

#### POST /api/bundle/add/:id

**REQ-RC-009**

Add article to pending bundle.

Headers: `Authorization: Bearer <API_KEY>`

Response: `{ "status": "added", "bundle_count": N }`

#### DELETE /api/bundle/remove/:id

**REQ-RC-009**

Remove article from pending bundle.

Headers: `Authorization: Bearer <API_KEY>`

Response: `{ "status": "removed", "bundle_count": N }`

## Component Interactions

### Email Ingestion Flow (REQ-RC-001)

```python
# Background task scheduled every 6 hours (configurable)
async def ingest_emails():
    sources = await get_enabled_email_sources()

    for source in sources:
        with imaplib.IMAP4_SSL(source.server) as imap:
            imap.login(source.username, source.password)
            imap.select('INBOX')

            # Search for unread emails from sender
            _, msg_ids = imap.search(None, f'(FROM "{source.sender_pattern}" UNSEEN)')

            for msg_id in msg_ids[0].split():
                # Fetch and parse email
                _, msg_data = imap.fetch(msg_id, '(RFC822)')
                email_msg = email.message_from_bytes(msg_data[0][1])

                # Extract HTML body and convert to Markdown
                html_body = extract_html_body(email_msg)
                markdown = html_to_markdown(html_body)

                # Insert article
                await article_repo.create(
                    source=f'email:{source.sender_pattern}',
                    title=email_msg['Subject'],
                    content_markdown=markdown,
                    author=email_msg['From']
                )

                # Mark as read
                imap.store(msg_id, '+FLAGS', '\\Seen')

    # Trigger scoring for unscored articles
    await score_unscored_articles()
```

### Background Worker Lifecycle (REQ-RC-002)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio

# Global state for background tasks
background_tasks: set[asyncio.Task] = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage background worker lifecycle aligned with FastAPI startup/shutdown."""
    # Startup: Initialize background workers
    logger.info("Starting background ingestion workers")

    # Create background tasks
    rss_task = asyncio.create_task(periodic_rss_ingestion())
    email_task = asyncio.create_task(periodic_email_ingestion())

    # Track tasks to prevent garbage collection
    background_tasks.add(rss_task)
    background_tasks.add(email_task)

    # Add done callbacks for cleanup
    rss_task.add_done_callback(background_tasks.discard)
    email_task.add_done_callback(background_tasks.discard)

    yield  # Application runs

    # Shutdown: Cancel background workers gracefully
    logger.info("Stopping background ingestion workers")
    for task in background_tasks:
        task.cancel()

    # Wait for tasks to complete cancellation
    await asyncio.gather(*background_tasks, return_exceptions=True)
    logger.info("All background workers stopped")

# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

async def periodic_rss_ingestion():
    """REQ-RC-002: Background worker for RSS feed ingestion."""
    while True:
        try:
            await ingest_rss()
        except asyncio.CancelledError:
            logger.info("RSS ingestion worker cancelled")
            raise  # Re-raise to allow proper cleanup
        except Exception as e:
            logger.error(f"RSS ingestion failed: {e}", exc_info=True)
            # Continue processing - don't crash the worker

        # Sleep until next check (default 2 hours)
        await asyncio.sleep(settings.rss_check_interval_seconds)

async def periodic_email_ingestion():
    """REQ-RC-002: Background worker for email ingestion."""
    while True:
        try:
            await ingest_emails()
        except asyncio.CancelledError:
            logger.info("Email ingestion worker cancelled")
            raise
        except Exception as e:
            logger.error(f"Email ingestion failed: {e}", exc_info=True)

        await asyncio.sleep(settings.email_check_interval_seconds)
```

### RSS Ingestion Flow (REQ-RC-002)

```python
async def ingest_rss():
    """Ingest articles from enabled RSS sources."""
    sources = await get_enabled_rss_sources()

    async with httpx.AsyncClient(timeout=30.0) as client:
        for source in sources:
            # REQ-RC-002: Check source-specific interval
            if not should_check_source(source):
                continue

            try:
                # Fetch and parse RSS feed
                feed = feedparser.parse(source.url)

                for entry in feed.entries:
                    # Skip if already in database
                    if await article_repo.exists_by_url(entry.link):
                        continue

                    # Extract content
                    if hasattr(entry, 'content') and entry.content:
                        # Full content in feed
                        html = entry.content[0].value
                        markdown = html_to_markdown(html)
                    else:
                        # Fetch article URL with polite delay
                        await asyncio.sleep(random.uniform(1.0, 5.0))
                        response = await client.get(entry.link)

                        # Apply Readability extraction
                        doc = readability.Document(response.text)
                        html = doc.summary()
                        markdown = html_to_markdown(html)

                    # Insert article
                    await article_repo.create(
                        source=f'rss:{source.url}',
                        title=entry.title,
                        url=entry.link,
                        author=entry.get('author'),
                        content_markdown=markdown
                    )

                # Update last_checked timestamp
                await update_source_check_time(source.id)

            except Exception as e:
                # REQ-RC-002: Log but don't crash - continue with other sources
                logger.error(f"Failed to ingest RSS source {source.url}: {e}")
                continue

    # Trigger scoring for unscored articles
    await score_unscored_articles()

def should_check_source(source) -> bool:
    """REQ-RC-002: Respect per-source check_interval_hours setting."""
    if source.last_checked is None:
        return True

    elapsed_hours = (datetime.utcnow() - source.last_checked).total_seconds() / 3600
    return elapsed_hours >= source.check_interval_hours
```

### LLM Scoring Flow (REQ-RC-004 DEPRECATED, REQ-RC-005)

**DEPRECATED:** This absolute 1-10 scoring is replaced by REQ-RC-024 Elo-based pairwise comparisons.

```python
async def score_unscored_articles():
    articles = await article_repo.get_unscored()
    prompt_version = await get_active_prompt_version()

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    for article in articles:
        # Prepare prompts
        system_prompt = [
            {
                "type": "text",
                "text": prompt_version.system_text,
                "cache_control": {"type": "ephemeral"}  # Cache system prompt
            }
        ]

        user_prompt = f"""
Title: {article.title}
Source: {article.source}
Content (first 500 words):
{article.content_markdown[:2000]}
"""

        # Call Claude API with structured output
        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": ScoringResponseSchema
            }
        )

        # Parse JSON response
        result = json.loads(response.content[0].text)

        # Update article with scoring results
        await article_repo.update_score(
            article_id=article.id,
            llm_score=result['score'],
            llm_reasoning=result['reasoning'],
            reading_time_category=result['reading_time'],
            tags=json.dumps(result['tags']),
            prompt_version=prompt_version.version,
            scored_at=datetime.utcnow()
        )
```

### Elo-Based Pairwise Scoring Flow (REQ-RC-024, REQ-RC-025, REQ-RC-026, REQ-RC-028)

```python
async def score_new_article_via_elo(article_id: int):
    """
    Score new article using pairwise Elo comparisons.
    REQ-RC-024: Perform pairwise comparisons
    REQ-RC-025: Initialize at 1500, mark confidence after 7 rounds
    REQ-RC-026: Select 7 random opponents, prefer current generation
    """
    article = await article_repo.get_by_id(article_id)
    generation = await get_active_generation()

    # REQ-RC-025: Initialize new article at Elo 1500
    await article_repo.update_elo(article_id, elo_rating=1500.0, elo_comparisons=0)

    # REQ-RC-026: Select 7 opponents (or all if < 7 available)
    opponents = await select_comparison_opponents(
        generation_id=generation.id,
        count=7
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    for opponent in opponents:
        # Perform pairwise comparison
        result = await compare_articles(client, article, opponent, generation)

        # REQ-RC-028: Record comparison before Elo update
        comparison = await elo_comparison_repo.create(
            article_a_id=article.id,
            article_b_id=opponent.id,
            winner_id=result.winner_id,
            llm_reasoning=result.reasoning,
            article_a_elo_before=article.elo_rating,
            article_b_elo_before=opponent.elo_rating,
            generation_id=generation.id
        )

        # Calculate new Elo ratings using standard formula
        new_elo_a, new_elo_b = calculate_elo_update(
            rating_a=article.elo_rating,
            rating_b=opponent.elo_rating,
            outcome=result.outcome,  # 1.0 (A wins), 0.5 (tie), 0.0 (B wins)
            k_factor=32
        )

        # Update both articles' Elo ratings
        await article_repo.update_elo(
            article.id,
            elo_rating=new_elo_a,
            elo_comparisons=article.elo_comparisons + 1
        )
        await article_repo.update_elo(
            opponent.id,
            elo_rating=new_elo_b,
            elo_comparisons=opponent.elo_comparisons + 1
        )

        # REQ-RC-028: Record final Elo values
        await elo_comparison_repo.update_final_elos(
            comparison.id,
            article_a_elo_after=new_elo_a,
            article_b_elo_after=new_elo_b
        )

        # Update local object for next iteration
        article.elo_rating = new_elo_a
        article.elo_comparisons += 1

        # Respect scoring delay between comparisons
        await asyncio.sleep(settings.scoring_delay_seconds)

    # REQ-RC-025: Mark as confident after 7 comparisons
    if article.elo_comparisons >= 7:
        await article_repo.update_elo_confidence(article.id, confident=True)


async def select_comparison_opponents(
    generation_id: int,
    count: int
) -> list[Article]:
    """
    REQ-RC-026: Select opponents for comparison.
    Prefer articles from current generation, fall back to any scored articles.
    """
    # First try: articles from current generation with Elo confidence
    candidates = await article_repo.query("""
        SELECT * FROM articles
        WHERE generation_id = ?
        AND elo_confidence = 1
        ORDER BY RANDOM()
        LIMIT ?
    """, generation_id, count)

    # If insufficient, add any scored articles
    if len(candidates) < count:
        additional = await article_repo.query("""
            SELECT * FROM articles
            WHERE elo_comparisons > 0
            AND id NOT IN (?)
            ORDER BY RANDOM()
            LIMIT ?
        """, [c.id for c in candidates], count - len(candidates))
        candidates.extend(additional)

    return candidates


async def compare_articles(
    client: anthropic.AsyncAnthropic,
    article_a: Article,
    article_b: Article,
    generation: PromptGeneration
) -> ComparisonResult:
    """
    REQ-RC-024: Ask LLM which article is more relevant.
    Returns outcome: 1.0 (A wins), 0.5 (tie), 0.0 (B wins).
    """
    system_prompt = [
        {
            "type": "text",
            "text": generation.prompt_text,
            "cache_control": {"type": "ephemeral"}
        }
    ]

    user_prompt = f"""
Compare these two articles and determine which is MORE RELEVANT to the user's interests.
Respond with: "A", "B", or "TIE".

Article A:
Title: {article_a.title}
Source: {article_a.source}
Content: {article_a.content_markdown[:1000]}

Article B:
Title: {article_b.title}
Source: {article_b.source}
Content: {article_b.content_markdown[:1000]}

Which article is more relevant? Provide:
1. Choice: A, B, or TIE
2. Reasoning: Brief explanation (1-2 sentences)
"""

    response = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=256,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        response_format={
            "type": "json_schema",
            "json_schema": ComparisonResponseSchema
        }
    )

    result = json.loads(response.content[0].text)

    # Map choice to Elo outcome
    if result['choice'] == 'A':
        outcome = 1.0
        winner_id = article_a.id
    elif result['choice'] == 'B':
        outcome = 0.0
        winner_id = article_b.id
    else:  # TIE
        outcome = 0.5
        winner_id = None

    return ComparisonResult(
        outcome=outcome,
        winner_id=winner_id,
        reasoning=result['reasoning']
    )


def calculate_elo_update(
    rating_a: float,
    rating_b: float,
    outcome: float,
    k_factor: int = 32
) -> tuple[float, float]:
    """
    Standard Elo rating calculation.

    Args:
        rating_a: Current Elo rating of article A
        rating_b: Current Elo rating of article B
        outcome: 1.0 if A wins, 0.5 if tie, 0.0 if B wins
        k_factor: How much ratings change (32 is standard for chess)

    Returns:
        (new_rating_a, new_rating_b)
    """
    # Expected score for A
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    # Expected score for B
    expected_b = 1 - expected_a

    # Actual outcomes
    actual_a = outcome
    actual_b = 1 - outcome

    # New ratings
    new_rating_a = rating_a + k_factor * (actual_a - expected_a)
    new_rating_b = rating_b + k_factor * (actual_b - expected_b)

    return (new_rating_a, new_rating_b)
```

### Elo-to-Percentile Mapping (REQ-RC-027)

```python
async def get_elo_percentile(elo_rating: float) -> float:
    """
    REQ-RC-027: Map Elo rating to percentile rank.

    Returns value 0-100 representing what percentage of articles
    this article outranks.
    """
    # Count articles with lower Elo ratings
    result = await db.query_one("""
        SELECT
            COUNT(*) FILTER (WHERE elo_rating < ?) as below,
            COUNT(*) as total
        FROM articles
        WHERE elo_confidence = 1
    """, elo_rating)

    if result.total == 0:
        return 50.0  # Default to median if no scored articles

    percentile = (result.below / result.total) * 100
    return percentile


async def get_articles_above_median() -> list[Article]:
    """
    REQ-RC-027, REQ-RC-012: Get articles with percentile >= 50.
    Used for default inbox filtering.
    """
    # Calculate median Elo rating
    median_elo = await db.query_one("""
        SELECT elo_rating
        FROM articles
        WHERE elo_confidence = 1
        ORDER BY elo_rating
        LIMIT 1
        OFFSET (SELECT COUNT(*) FROM articles WHERE elo_confidence = 1) / 2
    """)

    # Fetch articles above median
    articles = await db.query("""
        SELECT *, elo_rating
        FROM articles
        WHERE elo_confidence = 1
        AND elo_rating >= ?
        ORDER BY elo_rating DESC
    """, median_elo.elo_rating)

    # Add percentile to each article for display
    for article in articles:
        article.percentile = await get_elo_percentile(article.elo_rating)

    return articles


# Pydantic model for UI display
class ArticleWithPercentile(BaseModel):
    """REQ-RC-027: Article with normalized Elo display."""
    id: int
    title: str
    elo_rating: float          # Raw Elo (e.g., 1523.4)
    percentile: float          # User-facing rank (e.g., 73.2)
    elo_comparisons: int       # Number of comparisons (confidence indicator)
    elo_confidence: bool       # Whether >= 7 comparisons done
```

### Bundle Generation Flow (REQ-RC-007, REQ-RC-009)

```python
from fastapi.responses import StreamingResponse

@app.get("/api/bundle")
async def download_bundle(api_key: str = Depends(validate_api_key)):
    articles = await article_repo.get_bundled()

    # Create in-memory ZIP file
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for article in articles:
            # Generate .txt file content
            header = f"""Title: {article.title}
Source: {article.source}
Score: {article.llm_score}/10
Reading Time: {article.reading_time_category}

{'=' * 80}

"""
            # Convert Markdown to plain text
            plain_text = markdown_to_plaintext(article.content_markdown)
            content = header + plain_text

            # Sanitize filename
            safe_title = re.sub(r'[^\w\s-]', '', article.title)[:50]
            filename = f"{article.llm_score:.1f}_{safe_title}.txt"

            # Add to ZIP
            zip_file.writestr(filename, content)

    # Reset buffer position
    zip_buffer.seek(0)

    # Clear in_bundle flag
    await article_repo.clear_bundle_flags()

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=reading_bundle.zip"}
    )
```

## Heuristic-Refiner System Design

### Architecture Decision: Generations Not Versions

**REQ-RC-005, REQ-RC-021, REQ-RC-022**

Prompt "generations" replace the concept of manually-managed "versions." Each generation represents an evolution produced by the refinement LLM based on user feedback. Generations are:

- **Immutable**: Once created, never modified
- **Sequential**: Auto-incrementing ID (1, 2, 3...)
- **Self-describing**: Include diff from previous generation
- **Traceable**: Link to feedback items that produced them

Old articles retain their generation_id to preserve historical context. New articles are always scored with the current active generation.

### Feedback Collection Flow

**REQ-RC-019, REQ-RC-020**

```text
User rates article (thumbs up/down)
  ↓
System prompts: "Enter heuristic-refiner?"
  ↓
If YES:
  ↓
  LLM characterizes article → 5-Whats JSON
  ↓
  Display modal:
    - 5-Whats scorecard (above content)
    - Feedback text box (hideable)
    - Local storage auto-save
  ↓
  User writes feedback, submits
  ↓
  Store in heuristic_feedback table:
    - article_id
    - feedback_text
    - characterization_json
    - created_at
    - generation_id = NULL (until batch runs)
  ↓
  Set article.rating_refined = 1
```

### Daily Refinement Batch

**REQ-RC-021**

```text
Cron job: UTC midnight daily
  ↓
Collect feedback from past 24 hours
  ↓
If no feedback:
  EXIT (current generation continues)
  ↓
If feedback exists:
  ↓
  Get current active generation prompt
  ↓
  Build refinement LLM request:
    System: "You are a prompt refinement specialist"
    User:
      - Current prompt text
      - Array of (characterization, feedback) pairs
    Response format: JSON with refined_prompt field
  ↓
  Call Claude API with structured output
  ↓
  Parse refined_prompt from response
  ↓
  Compute word-diff from current to refined
  ↓
  Insert new prompt_generations row:
    - prompt_text = refined_prompt
    - diff_from_previous = computed diff
    - feedback_count = count of feedback items
    - is_active = 1
  ↓
  Set previous generation is_active = 0
  ↓
  Update all feedback items: generation_id = new_generation.id
  ↓
  Log: "Generated prompt generation N from M feedback items"
```

### Generation-Aware Display

**REQ-RC-008**

Inbox display logic:

```python
current_gen = get_active_generation()
previous_5_gens = get_previous_n_generations(5)
visible_gen_ids = [current_gen.id] + [g.id for g in previous_5_gens]

articles = query("""
  SELECT * FROM articles
  WHERE generation_id IN (?)
  ORDER BY
    CASE WHEN generation_id = ? THEN 0 ELSE 1 END,  -- Current gen first
    llm_score DESC
""", visible_gen_ids, current_gen.id)

for article in articles:
  if article.generation_id == current_gen.id:
    render_normal(article)
  else:
    render_muted(article)  # Previous generations: lower opacity, smaller font
```

### All View with Facets

**REQ-RC-012**

"Show All" becomes a rich faceted view:

```text
Filters:
  - Generation: [All | Current | Gen 5 | Gen 4 | Gen 3 | Gen 2 | Gen 1]
  - Rating: [All | Thumbs Up | Thumbs Down | Unrated | Refined]

Sort:
  - LLM Score (default)
  - User Rating (thumbs up first)
```

Implementation uses query builder:

```python
def build_all_view_query(generation_filter, rating_filter, sort_by):
  query = "SELECT * FROM articles WHERE 1=1"
  params = []

  if generation_filter != 'All':
    query += " AND generation_id = ?"
    params.append(generation_filter)

  if rating_filter == 'Thumbs Up':
    query += " AND user_rating = 1"
  elif rating_filter == 'Thumbs Down':
    query += " AND user_rating = -1"
  elif rating_filter == 'Unrated':
    query += " AND user_rating = 0"
  elif rating_filter == 'Refined':
    query += " AND rating_refined = 1"

  if sort_by == 'LLM Score':
    query += " ORDER BY llm_score DESC"
  else:  # User Rating
    query += " ORDER BY user_rating DESC, llm_score DESC"

  return query, params
```

### Prompt History Page

**REQ-RC-022**

```text
/prompt-history route:

┌─────────────────────────────────────┐
│ Prompt History                      │
├─────────────────────────────────────┤
│ Generation 3 (Active)               │
│ Created: 2025-12-14 00:00 UTC       │
│ Feedback: 5 items                   │
│                                     │
│ Diff from Generation 2:             │
│ - You prefer [-technical-]{+accessible+} │
│   explanations                      │
│ + Avoid Xbox game development news │
│                                     │
│ [View feedback items]               │
├─────────────────────────────────────┤
│ Generation 2                        │
│ Created: 2025-12-13 00:00 UTC       │
│ Feedback: 3 items                   │
│ ...                                 │
└─────────────────────────────────────┘
```

Implementation:

```python
@app.get("/prompt-history")
async def prompt_history():
  generations = await db.query("""
    SELECT * FROM prompt_generations
    ORDER BY id DESC
  """)

  for gen in generations:
    gen.feedback_items = await db.query("""
      SELECT hf.*, a.title
      FROM heuristic_feedback hf
      JOIN articles a ON hf.article_id = a.id
      WHERE hf.generation_id = ?
    """, gen.id)

  return templates.TemplateResponse("prompt_history.html", {
    "generations": generations
  })
```

### UI Components

**REQ-RC-014, REQ-RC-019, REQ-RC-020, REQ-RC-023**

1. **Thumbs up/down rating buttons**
   - Replace 5-star rating
   - Material Design icons: thumb_up, thumb_down
   - Toggle behavior: click again to unset

2. **Heuristic-refiner entry prompt**
   - Modal or slide-up panel after rating
   - "Want to help improve scoring? [Yes] [No]"
   - "No" stores rating without feedback

3. **5-Whats scorecard display**
   - Appears above article content in sequential scroll
   - Phone-friendly: vertical cards, not table
   - JSON structure:
     ```json
     {
       "topic": "OAuth2 authentication patterns",
       "style": "Tutorial with code examples",
       "depth": "Intermediate - assumes basic auth knowledge",
       "emotion": "Informative and confidence-building",
       "level": "Technical"
     }
     ```

4. **Feedback text box modal**
   - Hideable via collapse/expand button
   - Auto-save to localStorage every 3 seconds
   - Clear on submit
   - "Cancel" restores from localStorage

5. **Generation badge**
   - Small pill next to article title: "Gen 3"
   - Current generation: accent color
   - Previous generations: muted gray

6. **Muted article styling**
   - Previous generations: 60% opacity, 0.9rem font
   - Current generation: 100% opacity, 1rem font

7. **Inline word-diff component**
   - Additions: green background, +{text}
   - Deletions: red background, strikethrough, [-text-]
   - Phone-friendly: wrap long lines

8. **App title customization**
   - Settings page: text input for app_title
   - Header: `<h1>{{ app_settings.app_title }}</h1>`
   - Page titles: `<title>{{ app_settings.app_title }} - Inbox</title>`

### User Journeys

**Journey 1: Negative feedback on poorly-scored-high article**

```text
1. User reads article scored 8/10, finds it irrelevant (Xbox game development)
2. User taps thumbs down
3. Modal appears: "Want to help improve scoring?"
4. User taps "Yes"
5. System calls Claude to characterize article
6. 5-Whats scorecard appears:
   - Topic: Xbox game tooling
   - Style: Press release
   - Depth: Surface-level
   - Emotion: Promotional
   - Level: Everyday
7. Feedback modal shows with scorecard above article
8. User types: "I don't care about Xbox game development"
9. User taps "Submit feedback"
10. Toast: "Feedback recorded. Changes apply at midnight UTC."
11. Next day (after midnight batch):
    - New generation created
    - Future Xbox articles scored lower
    - Prompt diff shows: "+ Avoid Xbox game development news"
```

**Journey 2: Positive feedback on gem (low-scored article user loved)**

```text
1. User browses All view, filters to "Low Scored" (score < 5)
2. Finds article about weather API internals, score 4/10
3. Reads article, loves it
4. User taps thumbs up
5. Modal: "Want to help improve scoring?"
6. User taps "Yes"
7. 5-Whats scorecard:
   - Topic: Weather data API design
   - Style: Deep technical walkthrough
   - Depth: Advanced - internal system details
   - Emotion: Curiosity-inducing
   - Level: Technical
8. User types: "I LOVE deep dives into API internals like this"
9. Submit
10. Next day: Prompt refined to prioritize API architecture content
```

**Journey 3: Rating without refinement**

```text
1. User reads article, taps thumbs up
2. Modal: "Want to help improve scoring?"
3. User taps "No" (in a hurry)
4. Rating stored, article.rating_refined = 0
5. Article can be refined later from All view
```

**Journey 4: Retroactive refinement from All view**

```text
1. User navigates to All view
2. Filters to "Rated but Not Refined"
3. Sees list of articles with ratings but no feedback
4. Clicks article, sees "Provide refinement feedback" button
5. Enters heuristic-refiner mode (same flow as journey 1)
```

**Journey 5: Reviewing prompt history**

```text
1. User clicks "Prompt History" in top nav
2. Sees generation list:
   - Gen 4 (Active) - 3 hours ago - 2 feedback items
   - Gen 3 - Yesterday - 5 feedback items
   - Gen 2 - 2 days ago - 3 feedback items
3. Expands Gen 3 diff:
   - Shows word-level changes from Gen 2 → Gen 3
   - Links to 5 feedback items
4. Clicks feedback item link
5. Sees original article + characterization + user's feedback text
```

### Edge Cases

**REQ-RC-019, REQ-RC-020, REQ-RC-021**

1. **No feedback in 24hr window**
   - Batch job exits early
   - Current generation remains active
   - No new generation created

2. **Conflicting feedback**
   - Example: User A says "more politics", User B says "less politics"
   - Refinement LLM receives both in same batch
   - LLM reconciles based on pattern frequency
   - If equal weight, LLM may not change that aspect

3. **LLM characterization fails**
   - API timeout or invalid response
   - Store feedback without characterization_json
   - Allow refinement batch to proceed with text-only feedback

4. **Refinement LLM returns invalid prompt**
   - JSON parsing fails or prompt too short/long
   - Log warning with raw response
   - Skip generation creation
   - Feedback remains unlinked (generation_id = NULL)
   - Retry in next batch (24hrs later)

5. **User refreshes browser mid-feedback**
   - localStorage preserves feedback text
   - Re-display modal with saved text
   - User can continue or clear

6. **Article deleted before batch runs**
   - Foreign key constraint: ON DELETE CASCADE
   - Feedback deleted automatically
   - Batch proceeds with remaining feedback

### Error Handling Strategy

### Ingestion Errors

- **IMAP connection failure**: Log error, retry next cycle, alert if 3
  consecutive failures
- **RSS fetch failure**: Log error, skip feed, continue with others
- **Content extraction failure**: Set extraction_status='failed', flag for
  manual review (REQ-RC-006)

### Scoring Errors

- **Claude API timeout**: Retry with exponential backoff (3 attempts)
- **Rate limit**: Queue for later, process in next batch
- **Invalid response**: Log raw response, skip scoring, flag for retry

### Heuristic-Refiner Errors

- **Characterization LLM timeout**: Allow feedback submission without characterization
- **Refinement LLM timeout**: Skip generation, retry next batch
- **Invalid refined prompt**: Log error, keep current generation active
- **Database constraint violation**: Roll back transaction, log error

### Authentication Errors

- **Invalid API key**: Return 401 Unauthorized
- **Invalid Basic Auth**: Return 401 with WWW-Authenticate header

## Security Considerations

### REQ-RC-016: Authentication

**HTTP Basic Auth (default):**

- On first startup, generate random username (8 chars) and password (32 chars)
- Log credentials to console: `Generated credentials: username=xxx password=yyy`
- Store hashed password in auth_config table
- All web UI routes require Basic Auth

**API Key:**

- Set via `API_KEY` environment variable
- If unset, all API endpoints return 401
- API key checked via Bearer token in Authorization header

**No Web Auth Mode:**

- Only enabled when `DANGEROUS_NO_WEB_AUTH_MODE=1` is set
- Allows web UI access _NOT_ API access.
- Logs warning on startup

### Input Validation

- URL submissions: Validate URL format, reject non-HTTP(S)
- Feed sources: Sanitize identifiers, validate RSS URL format
- Search queries: Escape for FTS5, limit query length

### Rate Limiting

- API endpoints: 100 requests/hour per API key
- Web UI: 1000 requests/hour per IP (when behind proxy)

## Performance Considerations

### Database Optimization

- SQLite WAL mode for concurrent reads
- FTS5 for fast full-text search
- Indexes on frequently queried columns (score, received_at, decision)

### LLM Cost Optimization (REQ-RC-004)

- Prompt caching: System prompt cached, only article content varies
- Batch scoring: Score up to 10 articles per API call where supported
- Estimated cost: ~$5-7/month for 100 articles/day

### Content Extraction

- Cache Readability results
- Timeout: 30s per article fetch
- Parallel fetching with concurrency limit (3)

## Technology Stack

### Runtime & Package Management

- **Python**: 3.12+ (required for latest type system features)
- **Package manager**: uv (fast dependency resolution)
- **Project layout**: src/ layout with PEP 723 inline scripts for dev tasks

### Web Framework & API

- **Framework**: FastAPI (async ASGI, auto OpenAPI docs)
- **ASGI server**: uvicorn (production server)
- **Validation**: Pydantic v2 (request/response models, settings)
- **Templates**: Jinja2 (HTML rendering)
- **Forms**: python-multipart (multipart/form-data handling)

### Data & Storage

- **Database**: SQLite (stdlib sqlite3 module, WAL mode)
- **HTTP client**: httpx (async HTTP, connection pooling)

### Content Processing

- **RSS parsing**: feedparser (RSS/Atom feed handling)
- **Content extraction**: readability-lxml (Mozilla Readability port)
- **LLM integration**: anthropic (Claude API with prompt caching)

### Code Quality

- **Formatting**: Ruff (format)
- **Linting**: Ruff (lint)
- **Type checking**: mypy --strict + pyright strict (both in CI)
- **Testing**: pytest + pytest-asyncio
- **Property testing**: hypothesis (where natural fit for domain logic)

### Dev Tooling

- **Task runner**: ./dev.py (PEP 723 inline script, no external task runner)
- **Common tasks**: format, lint, typecheck, test, run, migrate

## Implementation Notes

### REQ-RC-001: Email Ingestion

- **Location**: `src/reader/ingestion/email.py`
- **Libraries**:
  - `imaplib` (stdlib, IMAP client)
  - `email` (stdlib, email parsing)
  - `html2text` or custom HTML→Markdown converter
- **Data models**: `src/reader/models/article.py` (Pydantic models)
- **Database**: `src/reader/db/repository.py` (article repository)

### REQ-RC-002: RSS Ingestion

- **Location**: `src/reader/ingestion/rss.py`
- **Libraries**:
  - `feedparser` (RSS/Atom parsing)
  - `httpx` (async article fetching)
  - `robotparser` (stdlib, robots.txt compliance)
- **Scheduler**: Background task in FastAPI lifecycle
- **Rate limiting**: httpx client with custom timeout/retry policies

### REQ-RC-002: Background Worker Lifecycle

- **Location**: `src/reader/web/app.py` (lifespan context manager)
- **Pattern**: FastAPI lifespan with asyncio.create_task for workers
- **Libraries**:
  - `asyncio` (stdlib, task management)
  - `contextlib.asynccontextmanager` (stdlib, lifespan pattern)
- **Configuration**:
  - `RSS_CHECK_INTERVAL_SECONDS` (default: 7200, 2 hours)
  - `EMAIL_CHECK_INTERVAL_SECONDS` (default: 7200, 2 hours)
- **Error handling**: Try-except in worker loop, log errors but continue
- **Shutdown**: Task cancellation with asyncio.gather for graceful cleanup
- **Task tracking**: Global set to prevent garbage collection of tasks

### REQ-RC-004: LLM Scoring

- **Location**: `src/reader/scoring/llm.py`
- **Libraries**:
  - `anthropic` (Claude API client)
  - Pydantic models for JSON schema validation
- **Prompt management**: `src/reader/scoring/prompts.py`
- **Caching**: Anthropic prompt caching via `cache_control` parameter
- **Async**: Use `anthropic.AsyncAnthropic` for non-blocking scoring

### REQ-RC-006: Content Extraction

- **Location**: `src/reader/extraction/readability.py`
- **Libraries**:
  - `readability-lxml` (primary extraction)
  - `lxml` (HTML parsing, already a readability-lxml dependency)
- **Fallback chain**: readability-lxml → lxml manual extraction → raw HTML
- **Markdown conversion**: Custom converter or `markdownify` library

### REQ-RC-007: Bundle Generation

- **Location**: `src/reader/bundle/generator.py`
- **Libraries**:
  - `zipfile` (stdlib, ZIP archive creation)
  - Custom Markdown→plain text converter (preserve structure)
- **Output**: In-memory ZIP via `io.BytesIO` for direct streaming

### REQ-RC-008 through REQ-RC-012: Web UI

- **Location**: `src/reader/web/routes/`
  - `inbox.py` (article list, scoring display)
  - `article.py` (single article view)
  - `archive.py` (search interface)
  - `stats.py` (eval metrics dashboard)
  - `settings.py` (feed source management)
- **Templates**: `src/reader/web/templates/`
- **Framework**: FastAPI with Jinja2Templates
- **Static assets**: `src/reader/web/static/`

### REQ-RC-016: Authentication

- **Location**: `src/reader/auth/`
  - `middleware.py` (FastAPI dependency injection)
  - `credentials.py` (credential generation, storage)
- **Libraries**:
  - `secrets` (stdlib, secure token generation)
  - `passlib[bcrypt]` (password hashing)
- **Storage**: `~/.config/reader/auth.db` (separate SQLite database)
- **Implementation**: FastAPI HTTPBasic security scheme + custom API key
  dependency

### REQ-RC-017, REQ-RC-018: API Endpoints

- **Location**: `src/reader/web/routes/api.py`
- **Auth**: FastAPI Depends() with custom API key validator
- **Rate limiting**: slowapi or custom middleware with in-memory token bucket

### REQ-RC-019: Article Characterization

- **Location**: `src/reader/scoring/characterization.py`
- **Libraries**:
  - `anthropic` (Claude API for 5-Whats generation)
  - Pydantic model for FiveWhats response validation
- **Prompt**: System prompt for structured characterization
- **Caching**: No caching (single-shot per article)

### REQ-RC-020: Heuristic-Refiner Feedback Collection

- **Location**: `src/reader/web/routes/feedback.py`
- **Libraries**:
  - FastAPI route handlers
  - JavaScript localStorage for feedback persistence
- **Database**: Insert into heuristic_feedback table
- **UI**: Modal component with 5-Whats display + text box

### REQ-RC-021: Daily Refinement Batch

- **Location**: `src/reader/refinement/batch.py`
- **Scheduler**: Cron job or background task with schedule library
- **Libraries**:
  - `anthropic` (refinement LLM call)
  - `difflib` (stdlib, word-diff computation)
- **Execution**: UTC midnight daily
- **Transaction**: Atomic generation creation + feedback linking

### REQ-RC-022: Prompt History Page

- **Location**: `src/reader/web/routes/prompt_history.py`
- **Libraries**:
  - Jinja2 templates for diff rendering
  - Custom diff formatter for inline word-diff
- **Query**: Join prompt_generations with heuristic_feedback

### REQ-RC-023: App Customization

- **Location**: `src/reader/web/routes/settings.py`
- **Database**: app_settings table
- **Template**: Context processor to inject app_title into all pages

### REQ-RC-024 through REQ-RC-028: Elo-Based Pairwise Scoring

- **Location**: `src/reader/scoring/elo.py`
- **Libraries**:
  - `anthropic` (Claude API for pairwise comparisons)
  - Standard library `math` for Elo calculations
- **Database**:
  - Articles table: `elo_rating`, `elo_comparisons`, `elo_confidence` columns
  - `elo_comparisons` table for history tracking
- **Repository**: `src/reader/db/elo_repository.py`
- **Data models**: `src/reader/models/scoring.py` (ComparisonResult, ArticleWithPercentile)
- **Configuration**:
  - `ELO_K_FACTOR` (default: 32, controls rating volatility)
  - `ELO_COMPARISONS_FOR_CONFIDENCE` (default: 7, minimum comparisons for stable rating)
  - `ELO_OPPONENT_COUNT` (default: 7, comparisons per new article)
- **Migration strategy**:
  - Add new columns to articles table with defaults
  - Keep `llm_score` column for backward compatibility during transition
  - Bootstrap existing articles: convert 1-10 scores to initial Elo via mapping:
    - Score 1-3: Elo 1200-1350
    - Score 4-6: Elo 1400-1550
    - Score 7-10: Elo 1600-1800
  - Mark bootstrapped articles as `elo_confidence = 0` to trigger re-comparison
  - Option 2: Leave existing articles with old scores, only apply Elo to new articles
- **UI updates**:
  - Article cards show: "Elo: 1523 (73rd percentile)" with confidence indicator
  - Comparison history link in article detail view
  - Stats page: Elo distribution histogram
