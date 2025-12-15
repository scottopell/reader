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

WHEN the web application starts
THE SYSTEM SHALL initialize background workers for RSS and email ingestion

WHEN RSS feed check interval elapses
THE SYSTEM SHALL poll configured RSS feeds for new entries

WHEN a feed source check interval elapses
THE SYSTEM SHALL execute ingestion for that source without blocking web requests

WHEN RSS entry lacks full content
THE SYSTEM SHALL fetch the linked article URL

THE SYSTEM SHALL respect robots.txt and use polite crawling (1-5s delays)

WHEN background ingestion encounters errors
THE SYSTEM SHALL log error details and continue processing other sources

WHEN the web application shuts down
THE SYSTEM SHALL gracefully stop background workers

**Rationale:** Users want blog content from sources without email subscriptions
delivered automatically without manual intervention. Background workers enable
periodic ingestion while keeping the web interface responsive, and polite
crawling maintains access.

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

**DEPRECATED:** Replaced by REQ-RC-024 through REQ-RC-028 (Elo-based pairwise comparison)

WHEN new article content is extracted
THE SYSTEM SHALL score relevance 1-10 using Claude API

THE SYSTEM SHALL include brief reasoning with each score

THE SYSTEM SHALL estimate reading time category (quick/medium/deep)

**Rationale:** Users want automated filtering based on their interests, reducing
daily curation from ~20min to <5min.

**Deprecation Reason:** Absolute 1-10 scoring produces clustered scores around
6-8 with poor discrimination. Pairwise Elo comparisons provide better relative
ranking.

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
THE SYSTEM SHALL display articles from the current prompt generation sorted by score (highest first)

THE SYSTEM SHALL show for each article: title, source, score, reading time
estimate, and LLM reasoning

THE SYSTEM SHALL display articles from the previous 5 prompt generations with muted visual treatment

THE SYSTEM SHALL hide articles from prompt generations older than the previous 5

**Rationale:** Users want to quickly scan and cherry-pick interesting articles
with AI reasoning visible, focused on articles scored with the current prompt while
preserving recent history without infinite clutter.

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
THE SYSTEM SHALL display all articles with faceted filtering by prompt generation and rating

THE SYSTEM SHALL provide dual sort options: LLM score and user rating

THE SYSTEM SHALL persist the user's filter preference

**Rationale:** Reduces noise by default while keeping everything accessible with
flexible views for retroactive refinement and historical analysis.

---

### REQ-RC-013: Monitor Scoring Accuracy

WHEN user accesses the stats page
THE SYSTEM SHALL display percentage of thumbs-up ratings in high-scored versus low-scored articles per generation

THE SYSTEM SHALL display generation-over-generation improvement trends

THE SYSTEM SHALL show how rating patterns change across prompt generations

**Rationale:** Users want visibility into scoring performance to understand how
prompt refinement improves relevance detection over time.

---

### REQ-RC-014: Collect User Feedback via Ratings

WHEN user provides thumbs up or thumbs down rating on an article
THE SYSTEM SHALL store the rating alongside the LLM score

WHEN user provides rating and enters heuristic-refiner mode
THE SYSTEM SHALL flag the article as having contributed refinement feedback

THE SYSTEM SHALL link the article to the prompt generation record if feedback produced a refinement

**Rationale:** Users want to directly influence scoring improvements through simple
thumbs up/down signals without requiring developer access to prompt editing.

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

WHEN DANGEROUS_NO_WEB_AUTH_MODE=1 is set
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

### REQ-RC-019: Characterize Articles for Refinement

WHEN user enters heuristic-refiner mode for an article
THE SYSTEM SHALL issue an LLM call to characterize the article

THE SYSTEM SHALL return a 5-Whats scorecard containing: topic, writing style, depth, emotional impact, and writing level

THE SYSTEM SHALL display the characterization above the article content

**Rationale:** Users want structured characterization to guide their feedback,
making it easier to articulate what they liked or disliked about an article.

---

### REQ-RC-020: Collect Heuristic-Refiner Feedback

WHEN user provides thumbs rating
THE SYSTEM SHALL prompt user to optionally enter heuristic-refiner mode

WHEN user enters heuristic-refiner mode
THE SYSTEM SHALL display 5-Whats characterization above article content

THE SYSTEM SHALL display feedback text box in hideable modal

THE SYSTEM SHALL preserve feedback text across browser refresh

WHEN user submits feedback
THE SYSTEM SHALL store feedback with characterization and article linkage

**Rationale:** Users want to provide contextual feedback on articles to improve
scoring, with the option to give detailed input when motivated without forcing it
for every rating.

---

### REQ-RC-021: Refine Prompts from Daily Feedback

WHEN UTC midnight occurs
THE SYSTEM SHALL collect all heuristic-refiner feedback from the past 24 hours

WHEN feedback exists
THE SYSTEM SHALL issue refinement LLM call with current prompt and all characterization-feedback pairs

THE SYSTEM SHALL create new prompt generation from structured LLM response

THE SYSTEM SHALL record diff between previous and new prompt

WHEN no feedback exists in the 24-hour window
THE SYSTEM SHALL take no action and continue using the current generation

**Rationale:** Users want daily evolution of scoring heuristics based on their
feedback without manual prompt editing, creating a closed feedback loop that
continuously improves relevance detection.

---

### REQ-RC-022: Display Prompt Evolution History

THE SYSTEM SHALL provide top-level navigation to Prompt History page

THE SYSTEM SHALL display all prompt generations with timestamps

THE SYSTEM SHALL display inline word-diff between adjacent generations

THE SYSTEM SHALL link each generation to the feedback items that produced it

**Rationale:** Users want visibility into how their feedback shaped prompt
evolution, building trust in the refinement system and understanding scoring
changes.

---

### REQ-RC-023: Customize Application Appearance

THE SYSTEM SHALL allow customization of application title

THE SYSTEM SHALL default application title to 'nerd-reader'

THE SYSTEM SHALL display configured title in UI header and page titles

**Rationale:** Users want to personalize their reading interface, making the
application feel like their own curation tool.

---

### REQ-RC-024: Compare Article Relevance via Pairwise Ranking

WHEN new article content is extracted
THE SYSTEM SHALL perform pairwise comparisons with existing scored articles

WHEN comparing two articles
THE SYSTEM SHALL present both to Claude asking which is more relevant to user interests

THE SYSTEM SHALL update Elo ratings for both articles based on comparison outcome

**Rationale:** Users want better discrimination between articles. Pairwise
comparisons force the LLM to make relative judgments, avoiding score clustering
around 6-8 that occurs with absolute 1-10 ratings.

---

### REQ-RC-025: Initialize Elo Scores for New Articles

WHEN new article enters the system
THE SYSTEM SHALL assign initial Elo rating of 1500

WHEN article completes initial comparison rounds
THE SYSTEM SHALL mark article as having stable Elo confidence

**Rationale:** Users want new articles to start at a neutral baseline rating,
allowing the comparison system to quickly establish their true relevance through
pairwise contests.

---

### REQ-RC-026: Select Comparison Opponents Strategically

WHEN selecting opponents for new article
THE SYSTEM SHALL choose 7 random articles from scored articles

WHEN fewer than 7 scored articles exist
THE SYSTEM SHALL compare against all available scored articles

THE SYSTEM SHALL prefer articles from the current prompt generation as opponents

**Rationale:** Users want efficient convergence to accurate ratings. Seven
comparisons provide statistical confidence while limiting API costs. Recent
articles better represent current interests.

---

### REQ-RC-027: Display Normalized Elo Scores to Users

WHEN displaying article scores in UI
THE SYSTEM SHALL map Elo ratings to percentile ranks

WHEN user filters by "above median"
THE SYSTEM SHALL show articles with percentile >= 50

THE SYSTEM SHALL display percentile rank alongside raw Elo rating

**Rationale:** Users understand percentiles intuitively. Raw Elo values (e.g.,
1450-1650) are meaningless without context. Percentile mapping preserves
existing "p50+" filtering behavior.

---

### REQ-RC-028: Track Comparison History for Transparency

WHEN pairwise comparison completes
THE SYSTEM SHALL record which articles were compared

THE SYSTEM SHALL record comparison outcome and LLM reasoning

THE SYSTEM SHALL record Elo rating changes for both articles

WHEN user views article details
THE SYSTEM SHALL show comparison history and confidence level

**Rationale:** Users want to understand why articles received their ratings.
Comparison history provides transparency into the ranking process and builds
trust in the system.

---
