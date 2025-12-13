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

  -- REQ-RC-004: LLM scoring
  llm_score REAL,                    -- 1-10 relevance score
  llm_reasoning TEXT,                -- Brief explanation
  reading_time_category TEXT,        -- 'quick', 'medium', 'deep'
  word_count INTEGER,
  tags TEXT,                         -- JSON array

  -- REQ-RC-005: Prompt versioning
  prompt_version TEXT,               -- Which prompt produced this score
  scored_at TIMESTAMP,

  -- REQ-RC-014: User decision tracking
  user_decision TEXT DEFAULT 'pending',  -- 'sent', 'skipped', 'read', 'pending'
  user_rating INTEGER,               -- Optional post-reading rating (1-5)
  decided_at TIMESTAMP,

  -- REQ-RC-009: Bundle tracking
  in_bundle BOOLEAN DEFAULT 0,
  bundle_added_at TIMESTAMP,

  -- REQ-RC-006: Extraction status
  extraction_status TEXT DEFAULT 'success',  -- 'success', 'failed', 'manual_review'
  extraction_error TEXT
);

CREATE INDEX idx_articles_score ON articles(llm_score DESC);
CREATE INDEX idx_articles_received ON articles(received_at DESC);
CREATE INDEX idx_articles_decision ON articles(user_decision);
CREATE INDEX idx_articles_bundle ON articles(in_bundle);

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

-- REQ-RC-005: Prompt version tracking
CREATE TABLE prompt_versions (
  id INTEGER PRIMARY KEY,
  version TEXT NOT NULL UNIQUE,      -- 'v1', 'v2', etc.
  prompt_text TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_active BOOLEAN DEFAULT 0
);

-- REQ-RC-013: Eval metrics
CREATE TABLE eval_metrics (
  id INTEGER PRIMARY KEY,
  date DATE UNIQUE,
  total_articles INTEGER,
  articles_sent INTEGER,
  articles_read INTEGER,
  articles_skipped INTEGER,
  precision REAL,                    -- % of sent actually read
  recall REAL,                       -- % of read that were high-scored
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

Body: `{ "type": "email" | "rss", "identifier": "...", "display_name": "...", "enabled": true }`

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

### RSS Ingestion Flow (REQ-RC-002)

```python
# Background task scheduled every 6 hours (configurable)
async def ingest_rss():
    sources = await get_enabled_rss_sources()

    async with httpx.AsyncClient(timeout=30.0) as client:
        for source in sources:
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

    # Trigger scoring for unscored articles
    await score_unscored_articles()
```

### LLM Scoring Flow (REQ-RC-004, REQ-RC-005)

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

## Error Handling Strategy

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
