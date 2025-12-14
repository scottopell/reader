# Reading Curation System

## User Story

As a busy technical professional, I need to aggregate content from email
newsletters, RSS feeds, and manual URLs, have it scored for relevance by an LLM,
and pull curated bundles to my e-reader so that I can consume high-quality
reading without decision fatigue.

## Requirements

### REQ-RC-001: Discover New Content from Email Newsletters

WHEN an email arrives at the configured reading inbox
THE SYSTEM SHALL extract article content from the email body

WHEN email contains HTML
THE SYSTEM SHALL convert to Markdown preserving structure

**Rationale:** Users want newsletter content (Matt Levine, paid Substacks)
without anti-scraper issues. Email handles paywalled content naturally.

---

### REQ-RC-002: Discover New Content from RSS Feeds

WHEN RSS feed check interval elapses
THE SYSTEM SHALL poll configured RSS feeds for new entries

WHEN RSS entry lacks full content
THE SYSTEM SHALL fetch the linked article URL

THE SYSTEM SHALL respect robots.txt and use polite crawling (1-5s delays)

**Rationale:** Users want blog content from sources without email subscriptions.
Polite crawling maintains access.

---

### REQ-RC-003: Add Articles Manually via URL

WHEN user submits a URL via API endpoint
THE SYSTEM SHALL queue the URL for content extraction and scoring

WHEN content extraction succeeds
THE SYSTEM SHALL notify user "Article queued for scoring"

**Rationale:** Users want to add one-off articles from anywhere via iOS
Shortcuts share sheet.

---

### REQ-RC-004: Understand Relevance of Each Article

WHEN new article content is extracted
THE SYSTEM SHALL score relevance 1-10 using Claude API

THE SYSTEM SHALL include brief reasoning with each score

THE SYSTEM SHALL estimate reading time category (quick/medium/deep)

**Rationale:** Users want automated filtering based on their interests, reducing
daily curation from ~20min to <5min.

---

### REQ-RC-005: Track Scoring Prompt Changes Over Time

WHEN article is scored
THE SYSTEM SHALL record which prompt version was used

WHEN prompt is updated
THE SYSTEM SHALL allow re-scoring articles with new prompt

**Rationale:** Users want to understand which prompt version produced which
scores for calibration.

---

### REQ-RC-006: Extract Clean Article Content

WHEN extracting content from HTML
THE SYSTEM SHALL use Readability-style extraction to get article body

WHEN extraction fails or returns minimal content
THE SYSTEM SHALL flag article for manual review

THE SYSTEM SHALL store extracted content as Markdown

**Rationale:** Quality extraction is critical - users can't score or read
garbage content.

---

### REQ-RC-007: Create Reading Bundle for E-Reader

WHEN user requests bundle generation
THE SYSTEM SHALL create individual .txt files for each selected article

THE SYSTEM SHALL include for each article: title, source, reading time, score,
and content

**Rationale:** Users want to transfer selected articles to X4 e-reader as
separate files for easy navigation.

---

### REQ-RC-008: Browse Articles by Relevance Score

WHEN user accesses the inbox
THE SYSTEM SHALL display all unread articles sorted by score (highest first)

THE SYSTEM SHALL show for each article: title, source, score, reading time
estimate, and LLM reasoning

**Rationale:** Users want to quickly scan and cherry-pick interesting articles
with AI reasoning visible.

---

### REQ-RC-009: Select Articles for Device Transfer

WHEN user selects one or more articles
THE SYSTEM SHALL add them to the pending device bundle

WHEN user requests bundle download
THE SYSTEM SHALL generate individual .txt files for each selected article

**Rationale:** Pull-based workflow - users browse, select, then download when
ready.

---

### REQ-RC-010: Read Articles Without Leaving the App

WHEN user clicks on an article in the inbox
THE SYSTEM SHALL display the full article content in a reading view

WHEN user finishes reading in-app
THE SYSTEM SHALL mark article as 'read'

**Rationale:** Users sometimes want to read inline without going to the
e-reader.

---

### REQ-RC-011: Find Past Articles

WHEN user searches the archive
THE SYSTEM SHALL search across title, source, content, and tags

THE SYSTEM SHALL return results ranked by search match quality

**Rationale:** Users want to find past articles they remember reading or want to
reference, with the best matches appearing first.

---

### REQ-RC-012: Focus on High-Value Articles by Default

THE SYSTEM SHALL by default show only articles scoring above the median (p50+)

WHEN user clicks "Show All"
THE SYSTEM SHALL display all articles regardless of score

THE SYSTEM SHALL persist the user's filter preference

**Rationale:** Reduces noise by default while keeping everything accessible.

---

### REQ-RC-013: Monitor Scoring Accuracy

WHEN user accesses the stats page
THE SYSTEM SHALL display precision (% of sent articles actually read)

THE SYSTEM SHALL display recall (% of read articles that were auto-recommended)

THE SYSTEM SHALL show trends over time

**Rationale:** Users want visibility into scoring performance to tune prompts.

---

### REQ-RC-014: Learn from Reading Decisions

THE SYSTEM SHALL record user decisions: 'sent', 'skipped', 'read', 'pending'

WHEN user provides post-reading rating
THE SYSTEM SHALL store rating alongside LLM score

**Rationale:** Users want precision/recall analysis to improve scoring over
time.

---

### REQ-RC-015: Manage Content Sources

WHEN user accesses settings
THE SYSTEM SHALL allow adding/removing RSS feed URLs

WHEN user configures email source
THE SYSTEM SHALL allow specifying sender patterns to monitor

THE SYSTEM SHALL allow enabling/disabling individual sources

**Rationale:** Users want to manage sources without code changes.

---

### REQ-RC-016: Secure Access by Default

THE SYSTEM SHALL default to HTTP Basic Auth with randomly generated
username+password

WHEN DANGEROUS_NO_WEB AUTH_MODE=1 is set
THE SYSTEM SHALL allow unauthenticated web UI route access

WHEN API_KEY environment variable is set
THE SYSTEM SHALL accept that key in Authorization header for API endpoints

WHEN API_KEY is not set
THE SYSTEM SHALL reject all API key authentication attempts

WHEN first started
THE SYSTEM SHALL log the generated credentials

**Rationale:** Secure by default without infrastructure assumptions. Explicit
opt-out for dev/testing.

---

### REQ-RC-017: Accept URLs from iOS Shortcuts

WHEN POST request arrives at /article endpoint with URL and valid API key
THE SYSTEM SHALL queue URL for extraction and scoring

THE SYSTEM SHALL return confirmation for Shortcuts notification

**Rationale:** "Share to reading list" workflow from Safari or any iOS app.

---

### REQ-RC-018: Download Bundle via API

WHEN GET request arrives at /bundle endpoint with valid API key
THE SYSTEM SHALL return ZIP file containing individual .txt articles

THE SYSTEM SHALL include only articles marked for device bundle

**Rationale:** iOS Shortcuts can fetch bundle and save to Files app for X4
transfer.

---
