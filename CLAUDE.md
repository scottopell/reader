# Claude Code Instructions for Reader

## Project Overview

Reader is a self-hosted reading curation system. It aggregates content from
email newsletters, RSS feeds, and manual URLs, scores articles using Claude, and
generates text bundles for e-reader devices.

This is a single-user, self-hosted application. Do not over-engineer for
multi-tenancy or scale.

## spEARS Methodology

This project follows spEARS (Simple Project with EARS). All specifications live
in `specs/`.

### Key Rules

1. **Requirements are in `specs/reading-curation/requirements.md`** - 18
   requirements (REQ-RC-001 to REQ-RC-018)
2. **Use the `update-reqs` agent** when modifying any `specs/**/*.md` files
3. **Reference requirement IDs** in code comments and tests:

   ```python
   # REQ-RC-004: LLM scoring implementation
   def score_article(article: Article) -> Score:
   ```

4. **Update `executive.md` status** when implementing requirements
5. **Never delete requirements** - deprecate them instead

### Traceability

Every requirement should be traceable via grep:

```bash
rg "REQ-RC-001"  # Should find: requirements.md, design.md, executive.md, code, tests
```

## Technology Stack

| Category | Choice |
|----------|--------|
| Runtime | Python 3.12+ |
| Package manager | uv |
| Web framework | FastAPI |
| Validation | Pydantic v2 |
| HTTP client | httpx |
| Database | SQLite (stdlib sqlite3) |
| Formatting | Ruff (format) |
| Linting | Ruff (lint) |
| Type checking | mypy --strict + pyright strict |
| Testing | pytest + hypothesis |
| Project layout | src/ layout |
| Dev tasks | ./dev.py (PEP 723) |

### Key Libraries

- `fastapi`, `uvicorn` - Web framework and ASGI server
- `pydantic`, `pydantic-settings` - Validation and config
- `httpx` - Async HTTP client
- `feedparser` - RSS parsing
- `readability-lxml` - Content extraction
- `anthropic` - Claude API
- `jinja2` - Templates
- `passlib[bcrypt]` - Password hashing

## Architecture Decisions

These decisions are final. Do not revisit without explicit user request.

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | SQLite | Single-user, self-hosted |
| Content storage | Markdown | Preserves formatting, converts to plain text |
| Bundle format | Individual .txt files in ZIP | E-reader navigation |
| Auth default | HTTP Basic Auth (random creds) | Secure by default |
| API auth | Bearer token via `API_KEY` env var | iOS Shortcuts support |
| Workflow | Pull-based | User selects and downloads, no auto-push |
| Inbox filter | p50+ by default | Reduces noise, "Show All" available |

## What NOT to Build

These were explicitly rejected or deferred:

- **Source tiers** (auto-send vs llm-curated) - Rejected
- **Duplicate detection** - Not wanted
- **Context-based bundling** (commute/evening modes) - Deferred
- **Cloudflare Zero Trust integration** - App must stand alone
- **Multi-user support** - Single user only
- **Push notifications** - Pull-based only

## Coding Conventions

### General

- Keep it simple. This is a personal tool, not enterprise software.
- Prefer stdlib over external dependencies where reasonable.
- SQLite is fine. Do not suggest PostgreSQL.
- No ORM required. Raw SQL with parameterized queries is acceptable.

### File Structure

```text
reader/
├── dev.py                    # PEP 723 task runner (./dev.py <cmd>)
├── pyproject.toml            # Project config, dependencies, tool settings
├── src/reader/
│   ├── __init__.py
│   ├── cli.py                # CLI entry point
│   ├── config.py             # Pydantic settings
│   ├── models/               # Pydantic models
│   │   ├── article.py        # Article, ArticleCreate, ArticleScore
│   │   ├── source.py         # FeedSource
│   │   └── scoring.py        # ScoringRequest, ScoringResponse
│   ├── db/                   # Database layer
│   │   ├── connection.py     # SQLite connection
│   │   ├── repository.py     # ArticleRepository
│   │   ├── migrate.py        # Schema migrations
│   │   └── reset.py          # Database reset
│   ├── auth/                 # REQ-RC-016
│   │   ├── credentials.py    # Credential generation
│   │   └── middleware.py     # FastAPI auth dependencies
│   ├── ingestion/            # REQ-RC-001, REQ-RC-002, REQ-RC-003
│   │   ├── email.py          # IMAP ingestion
│   │   └── rss.py            # RSS ingestion
│   ├── extraction/           # REQ-RC-006
│   │   └── readability.py    # Content extraction
│   ├── scoring/              # REQ-RC-004, REQ-RC-005
│   │   ├── llm.py            # Claude API scoring
│   │   └── prompts.py        # Prompt management
│   ├── bundle/               # REQ-RC-007, REQ-RC-009
│   │   └── generator.py      # Bundle generation
│   └── web/                  # REQ-RC-008 through REQ-RC-015, REQ-RC-017, REQ-RC-018
│       ├── app.py            # FastAPI app
│       ├── routes/           # Route handlers
│       │   ├── inbox.py      # Inbox view
│       │   └── api.py        # API endpoints
│       ├── templates/        # Jinja2 templates
│       └── static/           # Static assets
├── tests/                    # pytest tests
└── specs/                    # spEARS specifications
```

### Error Handling

- Log errors with context, don't swallow them
- Content extraction failures should flag article for manual review (REQ-RC-006)
- API errors should return appropriate HTTP status codes

### Security

- Never log passwords or API keys
- Validate and sanitize all user input
- Use parameterized SQL queries

## Testing

Reference requirement IDs in test names:

```python
def test_req_rc_004_article_scoring():
    """REQ-RC-004: Articles receive 1-10 relevance score"""
    ...
```

## Common Tasks

### Adding a new feed source type

1. Add ingestion handler in `src/ingestion/`
2. Update `feed_sources` table if needed
3. Add UI controls in settings (REQ-RC-015)
4. Update `executive.md` if new requirement needed

### Modifying the scoring prompt

1. Create new prompt version in `prompt_versions` table
2. Set `is_active = 1` for new version
3. Old scores retain their `prompt_version` reference (REQ-RC-005)

## Development Workflow

### Setup

```bash
# Install dependencies
uv sync --dev

# Run migrations
./dev.py db-migrate

# Start dev server (generates credentials on first run)
./dev.py serve
```

### Common Commands

```bash
./dev.py fmt          # Format code with ruff
./dev.py lint         # Lint with ruff
./dev.py typecheck    # Run mypy and pyright
./dev.py test         # Run pytest
./dev.py check        # fmt --check + lint + typecheck (CI)
./dev.py serve        # Start dev server with hot reload
./dev.py db-migrate   # Run migrations
./dev.py db-reset     # Reset database (deletes data)
```

### Type Hints

- **Mandatory** at module boundaries (function signatures, class attributes)
- **Mandatory** for Pydantic models (network boundaries)
- Use `Annotated` for FastAPI dependencies
- Both mypy --strict and pyright strict must pass

### Testing

- Use pytest + pytest-asyncio for async tests
- Use hypothesis for property-based tests where natural (e.g., score validation)
- Reference requirement IDs in test docstrings
