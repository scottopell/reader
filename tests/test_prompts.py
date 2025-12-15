"""Tests for prompt versioning.

REQ-RC-005: Track Scoring Prompt Changes Over Time
"""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from reader.db.migrate import migrate
from reader.scoring.prompts import (
    DEFAULT_PROMPT,
    DEFAULT_VERSION,
    create_prompt_version,
    get_active_prompt,
    get_prompt_by_version,
    list_prompt_versions,
)


@pytest.fixture
def temp_db() -> Generator[str]:
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    Path(path).unlink()


@pytest.fixture
def mock_db_path(temp_db: str) -> Generator[str]:
    """Patch the database path to use temp database."""
    with patch("reader.db.connection.get_db_path", return_value=temp_db):
        migrate()
        yield temp_db


@pytest.mark.usefixtures("mock_db_path")
class TestPromptVersioning:
    """REQ-RC-005: Prompt versioning tests."""

    def test_get_active_prompt_seeds_default(self) -> None:
        """REQ-RC-005: First call seeds default prompt."""
        prompt_text, version = get_active_prompt()
        assert prompt_text == DEFAULT_PROMPT
        assert version == DEFAULT_VERSION

    def test_get_active_prompt_returns_same_on_second_call(self) -> None:
        """REQ-RC-005: Subsequent calls return seeded prompt."""
        # First call seeds
        get_active_prompt()
        # Second call returns the same
        prompt_text, version = get_active_prompt()
        assert prompt_text == DEFAULT_PROMPT
        assert version == DEFAULT_VERSION

    def test_create_prompt_version(self) -> None:
        """REQ-RC-005: Can create new prompt versions."""
        # Seed default
        get_active_prompt()

        # Create v2
        new_prompt = "New prompt for {title} from {source}: {content_preview}"
        prompt_id = create_prompt_version("v2", new_prompt, set_active=True)
        assert prompt_id > 0

        # Now v2 is active
        prompt_text, version = get_active_prompt()
        assert version == "v2"
        assert prompt_text == new_prompt

    def test_create_inactive_prompt_version(self) -> None:
        """REQ-RC-005: Can create inactive prompt versions."""
        # Seed default as active
        get_active_prompt()

        # Create v2 as inactive
        new_prompt = "Draft prompt"
        create_prompt_version("v2-draft", new_prompt, set_active=False)

        # v1 still active
        _prompt_text, version = get_active_prompt()
        assert version == DEFAULT_VERSION

    def test_get_prompt_by_version(self) -> None:
        """REQ-RC-005: Can retrieve specific prompt versions."""
        # Seed default
        get_active_prompt()

        # Get v1
        prompt = get_prompt_by_version(DEFAULT_VERSION)
        assert prompt is not None
        assert prompt.version == DEFAULT_VERSION
        assert prompt.prompt_text == DEFAULT_PROMPT
        assert prompt.is_active is True

    def test_get_prompt_by_version_not_found(self) -> None:
        """REQ-RC-005: Returns None for unknown versions."""
        prompt = get_prompt_by_version("nonexistent")
        assert prompt is None

    def test_list_prompt_versions(self) -> None:
        """REQ-RC-005: Can list all prompt versions."""
        # Seed default
        get_active_prompt()

        # Create additional versions
        create_prompt_version("v2", "Prompt v2", set_active=True)
        create_prompt_version("v3-draft", "Draft prompt", set_active=False)

        versions = list_prompt_versions()
        assert len(versions) == 3

        # Most recent first
        version_names = [v.version for v in versions]
        assert "v3-draft" in version_names
        assert "v2" in version_names
        assert DEFAULT_VERSION in version_names

    def test_prompt_version_tracked_in_db(self) -> None:
        """REQ-RC-005: Verify prompt versions exist after seeding."""
        # Seed default
        get_active_prompt()

        # Check versions list
        versions = list_prompt_versions()
        assert len(versions) >= 1
        active_versions = [v for v in versions if v.is_active]
        assert len(active_versions) == 1
        assert active_versions[0].version == DEFAULT_VERSION
