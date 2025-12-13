# Reading Curation System - Technical Design

## Architecture Overview

```
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
│              │  (Flask/FastAPI)│                                │
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

Response: HTML page with article cards showing title, source, score, reading time, LLM reasoning.

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

```
Every 6 hours (configurable):
1. Connect to IMAP server
2. For each enabled email source:
   a. Search for unread emails matching sender pattern
   b. For each matching email:
      - Extract HTML body
      - Convert to Markdown (preserve headings, links, lists)
      - Insert into articles table with source='email:sender'
      - Mark email as read
3. Trigger scoring for unscored articles
```

### RSS Ingestion Flow (REQ-RC-002)

```
Every 6 hours (configurable):
1. For each enabled RSS source:
   a. Fetch RSS feed
   b. For each new entry (not in DB by URL):
      - If full content in feed: extract directly
      - Else: fetch article URL with polite delays (1-5s)
      - Apply Readability extraction
      - Convert to Markdown
      - Insert into articles table with source='rss:feed-url'
2. Trigger scoring for unscored articles
```

### LLM Scoring Flow (REQ-RC-004, REQ-RC-005)

```
For each unscored article:
1. Load active prompt version
2. Prepare request:
   - System prompt (cached): interests, preferences, scoring criteria
   - User prompt: title, source, first 500 words of content
3. Call Claude API
4. Parse JSON response: score, reasoning, reading_time, tags
5. Update article record with score, prompt_version, scored_at
```

### Bundle Generation Flow (REQ-RC-007, REQ-RC-009)

```
When user requests bundle:
1. Query articles WHERE in_bundle = 1
2. For each article:
   a. Generate .txt file:
      - Header: title, source, score, reading time
      - Separator line
      - Content (Markdown → plain text)
   b. Filename: {score}_{sanitized_title}.txt
3. Create ZIP archive of all .txt files
4. Return ZIP for download
5. Clear in_bundle flag for downloaded articles
```

## Error Handling Strategy

### Ingestion Errors
- **IMAP connection failure**: Log error, retry next cycle, alert if 3 consecutive failures
- **RSS fetch failure**: Log error, skip feed, continue with others
- **Content extraction failure**: Set extraction_status='failed', flag for manual review (REQ-RC-006)

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

**No Auth Mode:**
- Only enabled when `DANGEROUS_NO_AUTH_MODE=1` is set
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

## Implementation Notes

### REQ-RC-001: Email Ingestion
- Location: `src/ingestion/email.py` (or `src/ingestion/email.ts`)
- Use `imaplib` (Python) or `imap-simple` (Node.js)
- HTML to Markdown: `html2text` (Python) or `turndown` (Node.js)

### REQ-RC-002: RSS Ingestion
- Location: `src/ingestion/rss.py` (or `src/ingestion/rss.ts`)
- Use `feedparser` (Python) or `rss-parser` (Node.js)
- Respect `robots.txt` via `robotparser` (Python) or `robots-parser` (Node.js)

### REQ-RC-004: LLM Scoring
- Location: `src/scoring/llm.py` (or `src/scoring/llm.ts`)
- Use Anthropic SDK with prompt caching enabled
- Store prompts in DB for version tracking

### REQ-RC-006: Content Extraction
- Location: `src/extraction/readability.py` (or `src/extraction/readability.ts`)
- Use `readability-lxml` (Python) or `@mozilla/readability` (Node.js)
- Fallback chain: Readability → BeautifulSoup/cheerio → raw HTML

### REQ-RC-007: Bundle Generation
- Location: `src/bundle/generator.py` (or `src/bundle/generator.ts`)
- Markdown to plain text: strip formatting, preserve structure
- ZIP creation: `zipfile` (Python) or `archiver` (Node.js)

### REQ-RC-008 through REQ-RC-012: Web UI
- Location: `src/web/routes.py` (or `src/web/routes.ts`)
- Templates: `templates/` directory
- Framework: Flask/Jinja2 (Python) or Express/Handlebars (Node.js)

### REQ-RC-016: Authentication
- Location: `src/auth/middleware.py` (or `src/auth/middleware.ts`)
- Credential storage: `~/.config/reader/auth.db` (separate from main DB)
- Password hashing: `bcrypt`
