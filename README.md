# Reader

A self-hosted reading curation system that aggregates content from email newsletters, RSS feeds, and manual URLs, scores articles for relevance using Claude, and generates bundles for e-reader devices.

## Problem

Consuming high-quality technical content during commutes without:
- Manual pre-filtering overhead (decision fatigue before reading)
- Scrolling through low-signal firehose content
- Dealing with web scraper anti-bot measures
- Missing interesting articles buried in noise

## Solution

Reader automates content discovery and filtering:

1. **Aggregate** - Pull content from email newsletters (sidesteps anti-scraper issues), RSS feeds, and manual URL submissions
2. **Score** - Claude rates each article 1-10 for relevance with reasoning visible
3. **Browse** - Web UI shows score-sorted inbox, defaulting to top 50% articles
4. **Select** - Pick what looks interesting, add to bundle
5. **Transfer** - Download individual .txt files for e-reader

## Features

- Email newsletter ingestion via IMAP
- RSS feed polling with polite crawling
- iOS Shortcuts integration for manual URLs
- LLM scoring with prompt versioning
- Score-sorted inbox with filtering
- In-app reading view
- Full-text archive search
- Precision/recall metrics dashboard
- Individual .txt bundle generation
- HTTP Basic Auth by default

## Quick Start

```bash
# Clone and install dependencies
git clone <repo-url>
cd reader
# ... installation steps TBD

# Start the server (generates random credentials on first run)
./reader serve

# Check the logs for generated credentials:
# Generated credentials: username=abc12345 password=...

# Access web UI at http://localhost:8080
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for scoring |
| `IMAP_HOST` | No | Email server hostname |
| `IMAP_USER` | No | Email username |
| `IMAP_PASS` | No | Email password |
| `API_KEY` | No | API key for iOS Shortcuts. If unset, API endpoints disabled |
| `DANGEROUS_NO_AUTH_MODE` | No | Set to `1` to disable authentication (dev only) |

### Database

SQLite database stored at `~/.config/reader/reader.db` (configurable via `READER_DB_PATH`).

## Architecture

```
[Email/RSS/Manual URL]
         │
         ▼
  [Content Extraction]
         │
         ▼
    [LLM Scoring]
         │
         ▼
     [SQLite DB]
         │
         ▼
      [Web UI]
         │
         ▼
 [Bundle Generator]
```

## API Endpoints

### Web UI (HTTP Basic Auth)

- `GET /inbox` - Browse scored articles
- `GET /article/:id` - Read article in-app
- `GET /archive` - Search past articles
- `GET /stats` - View precision/recall metrics
- `GET /settings` - Manage feed sources

### API (API Key Required)

- `POST /api/article` - Submit URL for scoring
- `GET /api/bundle` - Download article bundle (ZIP)
- `POST /api/bundle/add/:id` - Add article to bundle
- `DELETE /api/bundle/remove/:id` - Remove from bundle

## iOS Shortcuts

### Save Article

```
POST https://your-server/api/article
Authorization: Bearer <API_KEY>
Content-Type: application/json

{"url": "<shared-url>"}
```

### Download Bundle

```
GET https://your-server/api/bundle
Authorization: Bearer <API_KEY>

→ Returns: bundle.zip containing individual .txt files
```

## Development

See [SPEARS.md](SPEARS.md) for the requirements methodology used in this project.

Specifications live in `specs/reading-curation/`:
- `requirements.md` - EARS-formatted requirements
- `design.md` - Technical architecture
- `executive.md` - Status tracking

## License

MIT
