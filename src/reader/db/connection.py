"""Database connection management."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from reader.config import get_settings


def get_db_path() -> Path:
    """Get the database path, creating parent directories if needed."""
    settings = get_settings()
    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Get a database connection with WAL mode enabled."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()
