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

  -- REQ-RC-005: Prompt versioning
  prompt_version TEXT,
  scored_at TIMESTAMP,

  -- REQ-RC-014: User decision tracking
  user_decision TEXT DEFAULT 'pending',
  user_rating INTEGER,
  decided_at TIMESTAMP,

  -- REQ-RC-009: Bundle tracking
  in_bundle BOOLEAN DEFAULT 0,
  bundle_added_at TIMESTAMP,

  -- REQ-RC-006: Extraction status
  extraction_status TEXT DEFAULT 'success',
  extraction_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_articles_score ON articles(llm_score DESC);
CREATE INDEX IF NOT EXISTS idx_articles_received ON articles(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_decision ON articles(user_decision);
CREATE INDEX IF NOT EXISTS idx_articles_bundle ON articles(in_bundle);

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

-- REQ-RC-005: Prompt version tracking
CREATE TABLE IF NOT EXISTS prompt_versions (
  id INTEGER PRIMARY KEY,
  version TEXT NOT NULL UNIQUE,
  prompt_text TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_active BOOLEAN DEFAULT 0
);

-- REQ-RC-013: Eval metrics
CREATE TABLE IF NOT EXISTS eval_metrics (
  id INTEGER PRIMARY KEY,
  date DATE UNIQUE,
  total_articles INTEGER,
  articles_sent INTEGER,
  articles_read INTEGER,
  articles_skipped INTEGER,
  precision REAL,
  recall REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
