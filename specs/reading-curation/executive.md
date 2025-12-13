# Reading Curation System - Executive Summary

## Requirements Summary

The Reading Curation System solves decision fatigue for busy technical professionals by automating content discovery and filtering. Users receive articles from three sources: email newsletters (handling paywalled content like Matt Levine and Substacks), RSS feeds (for blogs without email options), and manual URL submission via iOS Shortcuts share sheet. Each article is automatically scored 1-10 by Claude with reasoning visible, reducing daily curation time from 20 minutes to under 5 minutes. Users browse a score-sorted inbox showing only high-value articles by default, select what interests them, and download bundles as individual text files for transfer to e-reader devices. The system tracks reading decisions to provide precision and recall metrics, helping users tune scoring prompts over time. In-app reading and full-text search across archives support reference lookups. Security defaults to HTTP Basic Auth with randomly generated credentials, with explicit opt-out required for unauthenticated access.

## Technical Summary

Self-hosted FastAPI service on Python 3.12+ with three ingestion paths: IMAP monitoring for email newsletters with HTML-to-Markdown conversion, polite RSS polling via feedparser respecting robots.txt with 1-5 second delays, and API endpoint for iOS Shortcuts integration. Content extraction uses readability-lxml with manual review flags for failures. Anthropic SDK scores each article with versioned prompts, storing prompt IDs alongside scores to enable re-scoring after prompt changes. SQLite database stores articles, scores, and reading decisions. Frontend displays score-sorted article inbox with LLM reasoning, filtering via Pydantic v2 validated queries, and selection controls. Bundle generation creates individual text files per article including metadata. Statistics dashboard calculates precision (percentage of sent articles actually read) and recall (percentage of read articles that were auto-recommended) over time. Authentication uses HTTP Basic Auth by default with random credential generation logged at startup, plus optional API key for programmatic access via environment variable, with explicit dangerous mode flag required to disable security. Development environment uses uv for package management, PEP 723 dev.py for task automation, strict type checking via mypy and pyright, Ruff for linting and formatting, and pytest with hypothesis for property-based testing. Async HTTP operations via httpx. Source code follows src/ layout pattern.

## Status Summary

| Requirement | Status | Notes |
|-------------|--------|-------|
| **REQ-RC-001:** Discover New Content from Email Newsletters | ❌ Not Started | Email ingestion pipeline |
| **REQ-RC-002:** Discover New Content from RSS Feeds | ❌ Not Started | RSS polling with polite crawling |
| **REQ-RC-003:** Add Articles Manually via URL | ❌ Not Started | API endpoint for iOS Shortcuts |
| **REQ-RC-004:** Understand Relevance of Each Article | ❌ Not Started | Claude API scoring integration |
| **REQ-RC-005:** Track Scoring Prompt Changes Over Time | ❌ Not Started | Prompt versioning system |
| **REQ-RC-006:** Extract Clean Article Content | ❌ Not Started | Readability extraction |
| **REQ-RC-007:** Create Reading Bundle for E-Reader | ❌ Not Started | Text file bundle generation |
| **REQ-RC-008:** Browse Articles by Relevance Score | ❌ Not Started | Score-sorted inbox view |
| **REQ-RC-009:** Select Articles for Device Transfer | ❌ Not Started | Selection and bundle queueing |
| **REQ-RC-010:** Read Articles Without Leaving the App | ❌ Not Started | In-app reading view |
| **REQ-RC-011:** Find Past Articles | ❌ Not Started | Archive search functionality |
| **REQ-RC-012:** Focus on High-Value Articles by Default | ❌ Not Started | Median score filtering |
| **REQ-RC-013:** Monitor Scoring Accuracy | ❌ Not Started | Precision/recall dashboard |
| **REQ-RC-014:** Learn from Reading Decisions | ❌ Not Started | Decision tracking system |
| **REQ-RC-015:** Manage Content Sources | ❌ Not Started | Settings UI for sources |
| **REQ-RC-016:** Secure Access by Default | ❌ Not Started | HTTP Basic Auth with random credentials |
| **REQ-RC-017:** Accept URLs from iOS Shortcuts | ❌ Not Started | POST /article endpoint |
| **REQ-RC-018:** Download Bundle via API | ❌ Not Started | GET /bundle endpoint |

**Progress:** 0 of 18 complete
