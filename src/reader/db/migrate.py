"""Database migrations for Reader."""

from reader.db.connection import get_connection

# Schema from design.md
SCHEMA = """
-- REQ-RC-001, REQ-RC-002, REQ-RC-003, REQ-RC-006: Article storage
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  url TEXT,
  content_markdown TEXT NOT NULL,
  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  -- REQ-RC-004: LLM scoring
  llm_score REAL,
  llm_reasoning TEXT,
  reading_time_category TEXT,
  word_count INTEGER,
  tags TEXT,

  -- REQ-RC-005: Prompt versioning (DEPRECATED: use generation_id)
  prompt_version TEXT,
  scored_at TIMESTAMP,

  -- REQ-RC-005, REQ-RC-008: Prompt generation tracking
  generation_id INTEGER,

  -- REQ-RC-014: User decision tracking
  user_decision TEXT DEFAULT 'pending',
  decided_at TIMESTAMP,

  -- REQ-RC-014: User rating (thumbs up/down: -1, 0, 1)
  user_rating SMALLINT DEFAULT 0,
  rating_refined BOOLEAN DEFAULT 0,
  rated_at TIMESTAMP,

  -- REQ-RC-009: Bundle tracking
  in_bundle BOOLEAN DEFAULT 0,
  bundle_added_at TIMESTAMP,

  -- REQ-RC-006: Extraction status
  extraction_status TEXT DEFAULT 'success',
  extraction_error TEXT,

  FOREIGN KEY (generation_id) REFERENCES prompt_generations(id)
);

CREATE INDEX IF NOT EXISTS idx_articles_score ON articles(llm_score DESC);
CREATE INDEX IF NOT EXISTS idx_articles_received ON articles(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_decision ON articles(user_decision);
CREATE INDEX IF NOT EXISTS idx_articles_bundle ON articles(in_bundle);
CREATE INDEX IF NOT EXISTS idx_articles_generation ON articles(generation_id);
CREATE INDEX IF NOT EXISTS idx_articles_rating ON articles(user_rating);

-- REQ-RC-011: Full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
  title, content_markdown, tags,
  content='articles',
  content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
  INSERT INTO articles_fts(rowid, title, content_markdown, tags)
  VALUES (new.id, new.title, new.content_markdown, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, content_markdown, tags)
  VALUES('delete', old.id, old.title, old.content_markdown, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, content_markdown, tags)
  VALUES('delete', old.id, old.title, old.content_markdown, old.tags);
  INSERT INTO articles_fts(rowid, title, content_markdown, tags)
  VALUES (new.id, new.title, new.content_markdown, new.tags);
END;

-- REQ-RC-015: Feed source configuration
CREATE TABLE IF NOT EXISTS feed_sources (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  identifier TEXT NOT NULL,
  display_name TEXT,
  enabled BOOLEAN DEFAULT 1,
  last_checked TIMESTAMP,
  check_interval_hours INTEGER DEFAULT 6,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- REQ-RC-005: Prompt version tracking (DEPRECATED: use prompt_generations)
CREATE TABLE IF NOT EXISTS prompt_versions (
  id INTEGER PRIMARY KEY,
  version TEXT NOT NULL UNIQUE,
  prompt_text TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_active BOOLEAN DEFAULT 0
);

-- REQ-RC-005, REQ-RC-021, REQ-RC-022: Prompt generation tracking
CREATE TABLE IF NOT EXISTS prompt_generations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_text TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  diff_from_previous TEXT,
  feedback_count INTEGER DEFAULT 0,
  is_active BOOLEAN DEFAULT 0
);

-- REQ-RC-019, REQ-RC-020, REQ-RC-021: Heuristic-refiner feedback
CREATE TABLE IF NOT EXISTS heuristic_feedback (
  id INTEGER PRIMARY KEY,
  article_id INTEGER NOT NULL,
  feedback_text TEXT NOT NULL,
  characterization_json TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  generation_id INTEGER,

  FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
  FOREIGN KEY (generation_id) REFERENCES prompt_generations(id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_article ON heuristic_feedback(article_id);
CREATE INDEX IF NOT EXISTS idx_feedback_generation ON heuristic_feedback(generation_id);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON heuristic_feedback(created_at);

-- REQ-RC-023: Application settings
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- REQ-RC-013: Eval metrics (updated for generation-based analysis)
CREATE TABLE IF NOT EXISTS eval_metrics (
  id INTEGER PRIMARY KEY,
  generation_id INTEGER,
  date DATE,
  total_articles INTEGER,
  high_scored_articles INTEGER,
  low_scored_articles INTEGER,
  high_scored_thumbs_up INTEGER,
  low_scored_thumbs_up INTEGER,
  precision_high REAL,
  precision_low REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (generation_id) REFERENCES prompt_generations(id)
);

-- REQ-RC-016: Auth credentials
CREATE TABLE IF NOT EXISTS auth_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def migrate() -> None:
    """Run database migrations."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    print("✓ Database migrations complete")


if __name__ == "__main__":
    migrate()
