"""pytest configuration and shared fixtures."""

import os
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def use_test_database() -> Iterator[None]:
    """Use an isolated in-memory database for all tests.

    This fixture runs automatically for all tests to ensure they
    don't affect the real database.
    """
    from reader.db.migrate import SCHEMA

    # Create in-memory database with updated schema
    test_conn = sqlite3.connect(":memory:", check_same_thread=False)
    test_conn.row_factory = sqlite3.Row
    test_conn.executescript(SCHEMA)
    test_conn.commit()

    @contextmanager
    def mock_get_connection() -> Iterator[sqlite3.Connection]:
        """Return the test connection as a context manager."""
        yield test_conn

    # Patch in all modules that import get_connection
    with (
        patch("reader.db.connection.get_connection", mock_get_connection),
        patch("reader.db.repository.get_connection", mock_get_connection),
        patch("reader.scoring.prompts.get_connection", mock_get_connection),
        patch("reader.auth.credentials.get_connection", mock_get_connection),
    ):
        yield

    test_conn.close()


@pytest.fixture
def temp_db_file() -> Iterator[str]:
    """Create a temporary database file for tests that need file-based DB."""
    from pathlib import Path

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    Path(path).unlink()
