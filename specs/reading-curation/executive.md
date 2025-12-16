# Reading Curation System - Executive Summary

## Requirements Summary

The Reading Curation System solves decision fatigue for busy technical
professionals by automating content discovery and filtering with self-improving
AI scoring. Users receive articles from three sources: email newsletters
(handling paywalled content like Matt Levine and Substacks), RSS feeds (for
blogs without email options), and manual URL submission via iOS Shortcuts share
sheet. Each article is automatically scored via Elo-based pairwise comparisons
(replacing deprecated 1-10 absolute scoring) where Claude compares each new
article against 7 existing articles to establish relative relevance ranking,
reducing daily curation time from 20 minutes to under 5 minutes. Users browse a
score-sorted inbox showing only high-value articles by default, focused on the
current prompt generation with previous 5 generations visible but muted. Users
rate articles with thumbs up/down and optionally provide structured feedback
through the heuristic-refiner system, which characterizes articles via 5-Whats
analysis (topic, style, depth, emotion, level) and collects user input. At UTC
midnight daily, all feedback from the past 24 hours is batched and sent to a
refinement LLM that evolves the scoring prompt, creating a new generation. Users
can review prompt evolution history with inline word-diffs and trace each
generation to the feedback that produced it. The system provides
generation-aware statistics showing how rating patterns improve over time.
In-app reading, full-text search across archives, and customizable application
branding support personalization. Security defaults to HTTP Basic Auth with
randomly generated credentials, with explicit opt-out required for
unauthenticated access.

## Technical Summary

Self-hosted FastAPI service on Python 3.12+ with three ingestion paths: IMAP
monitoring for email newsletters with HTML-to-Markdown conversion, polite RSS
polling via feedparser respecting robots.txt with 1-5 second delays, and API
endpoint for iOS Shortcuts integration. Content extraction uses readability-lxml
with manual review flags for failures. Anthropic SDK performs Elo-based pairwise
comparisons where each new article is compared against 7 randomly-selected
opponents from the current prompt generation, asking Claude "which is more
relevant?" for each pair and updating both articles' Elo ratings using standard
chess-style formulas (K-factor 32, initial rating 1500). After 7 comparisons,
articles are marked as having stable confidence. SQLite stores articles with Elo
ratings, comparison history, prompt generations, and heuristic feedback.
Heuristic-refiner system collects thumbs up/down ratings with optional
structured feedback via 5-Whats characterization (LLM-generated: topic, style,
depth, emotion, level). Daily batch job at UTC midnight collects past 24 hours
of feedback, calls refinement LLM to evolve scoring prompt, creates new
generation with word-diff from previous, and links feedback to generation.
Frontend displays generation-aware inbox (current generation prominent, previous
5 muted, older hidden) with Elo ratings mapped to percentile ranks for intuitive
interpretation (e.g., "1523 Elo, 73rd percentile"). Comparison history
accessible per article showing pairwise contests and outcomes. All view provides
faceted filtering by generation and rating, dual sort by Elo percentile or user
rating. Prompt history page shows evolution with inline word-diffs and feedback
traceability. Statistics dashboard tracks generation-over-generation improvement
via thumbs-up percentages in high-scored versus low-scored articles, with Elo
distribution histograms. Bundle generation creates individual text files per
article. App settings table stores customizable application title.
Authentication uses HTTP Basic Auth by default with random credential generation
logged at startup, plus optional API key for programmatic access via environment
variable, with explicit dangerous mode flag required to disable security.
Development environment uses uv for package management, PEP 723 dev.py for task
automation, strict type checking via mypy and pyright, Ruff for linting and
formatting, and pytest with hypothesis for property-based testing. Async HTTP
operations via httpx. Source code follows src/ layout pattern.

## Status Summary

| Requirement | Status | Notes |
|-------------|--------|-------|
| **REQ-RC-001:** Discover New Content from Email Newsletters | ⏭️ Stub Only | email.py has TODO comments, no IMAP implementation |
| **REQ-RC-002:** Discover New Content from RSS Feeds | ✅ Complete | rss.py with feedparser, robots.txt compliance, polite delays, scoring; background workers implemented in app.py |
| **REQ-RC-003:** Add Articles Manually via URL | ✅ Complete | POST /api/article extracts, scores, and stores articles |
| **REQ-RC-004:** Understand Relevance of Each Article | ✅ Complete | llm.py with Ollama and Anthropic backends, JSON response parsing |
| **REQ-RC-005:** Track Scoring Prompt Changes Over Time | ✅ Complete | prompts.py manages versions + generations; get_active_generation() seeding; ArticleScore includes generation_id |
| **REQ-RC-006:** Extract Clean Article Content | ✅ Complete | readability.py with readability-lxml + markdownify, failure flagging |
| **REQ-RC-007:** Create Reading Bundle for E-Reader | ✅ Complete | api.py download_bundle creates ZIP of .txt files |
| **REQ-RC-008:** Browse Articles by Relevance Score | ✅ Complete | inbox.html shows generation badges; muted styling for previous generations in CSS |
| **REQ-RC-009:** Select Articles for Device Transfer | ✅ Complete | api.py add_to_bundle/remove_from_bundle endpoints |
| **REQ-RC-010:** Read Articles Without Leaving the App | ✅ Complete | GET /article/{id} with markdown rendering, auto-marks as read |
| **REQ-RC-011:** Find Past Articles | ✅ Complete | FTS5 search via /search route, input sanitization, property-based tests |
| **REQ-RC-012:** Focus on High-Value Articles by Default | ✅ Complete | Median filtering exists; generation badges visible in inbox |
| **REQ-RC-013:** Monitor Scoring Accuracy | ✅ Complete | Stats page exists; eval_metrics table redesigned for generation-based analysis |
| **REQ-RC-014:** Collect User Feedback via Ratings | ✅ Complete | Thumbs up/down UI in article.html; user_rating as SMALLINT -1/0/1; rating_refined column; refiner prompt after rating |
| **REQ-RC-015:** Manage Content Sources | ✅ Complete | /settings page with add/remove/toggle for RSS and email sources |
| **REQ-RC-016:** Secure Access by Default | ✅ Complete | credentials.py generates random creds, middleware.py enforces auth |
| **REQ-RC-017:** Accept URLs from iOS Shortcuts | ✅ Complete | POST /api/article with full extract→score→store pipeline |
| **REQ-RC-018:** Download Bundle via API | ✅ Complete | GET /api/bundle endpoint returns ZIP |
| **REQ-RC-019:** Characterize Articles for Refinement | ✅ Complete | characterization.py with 5-Whats LLM prompt; FiveWhats model in scoring.py |
| **REQ-RC-020:** Collect Heuristic-Refiner Feedback | ✅ Complete | /article/{id}/refine route; refine.html with localStorage persistence; HeuristicFeedbackRepository |
| **REQ-RC-021:** Refine Prompts from Daily Feedback | ✅ Complete | batch.py with refinement LLM, diff computation; run_daily_refinement(); schedule placeholder |
| **REQ-RC-022:** Display Prompt Evolution History | ✅ Complete | /prompt-history route; prompt_history.html with inline word-diff; generation detail page |
| **REQ-RC-023:** Customize Application Appearance | ✅ Complete | app_settings table; AppSettingsRepository; app_title in templates |
| **REQ-RC-024:** Compare Article Relevance via Pairwise Ranking | ✅ Complete | elo.py implements pairwise comparisons with Claude API |
| **REQ-RC-025:** Initialize Elo Scores for New Articles | ✅ Complete | Articles default to 1500; stable rating after 7 comparisons (checked via elo_comparisons >= 7) |
| **REQ-RC-026:** Select Comparison Opponents Strategically | ✅ Complete | Selects 7 random opponents from current generation |
| **REQ-RC-027:** Display Normalized Elo Scores to Users | ✅ Complete | Percentile badges (p0-p100) with color coding in inbox; /inbox/articles JSON endpoint; Load More pagination |
| **REQ-RC-028:** Track Comparison History for Transparency | ✅ Complete | elo_comparisons table stores all pairwise contests with outcomes and Elo deltas |

**Progress:** 27 complete, 0 in progress, 0 not started, 1 stub (REQ-RC-001
email)
