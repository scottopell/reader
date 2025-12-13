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
├── src/
│   ├── ingestion/      # REQ-RC-001, REQ-RC-002, REQ-RC-003
│   ├── extraction/     # REQ-RC-006
│   ├── scoring/        # REQ-RC-004, REQ-RC-005
│   ├── web/            # REQ-RC-008 through REQ-RC-015
│   ├── api/            # REQ-RC-017, REQ-RC-018
│   ├── bundle/         # REQ-RC-007, REQ-RC-009
│   └── auth/           # REQ-RC-016
├── templates/          # HTML templates
├── specs/              # spEARS specifications
└── tests/
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

### Running background jobs

Ingestion and scoring run on a schedule (systemd timer or cron). The web server
does not run these - they are separate processes.
