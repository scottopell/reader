"""Tests for authentication middleware and credentials.

REQ-RC-016: Secure Access by Default
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasicCredentials

from reader.auth.credentials import (
    Credentials,
    ensure_credentials,
    generate_credentials,
    get_credentials,
    store_credentials,
    verify_password,
)
from reader.auth.middleware import require_api_key, require_basic_auth
from reader.config import Settings


@pytest.fixture
def temp_db():
    """Create an isolated in-memory database for each test."""
    import sqlite3

    from reader.db.migrate import SCHEMA

    # Use in-memory database for isolation - each test gets a fresh one
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Run migrations directly without patching
    conn.executescript(SCHEMA)
    conn.commit()

    yield conn
    conn.close()


class TestCredentialGeneration:
    """Tests for credential generation and storage."""

    def test_generate_credentials_format(self) -> None:
        """REQ-RC-016: Generated credentials should be URL-safe and sufficient length."""
        username, password = generate_credentials()

        # Username should be ~8 chars (6 bytes = ~8 base64 chars)
        assert len(username) >= 6
        # Password should be ~32 chars (24 bytes = ~32 base64 chars)
        assert len(password) >= 24

        # Should be URL-safe (no special chars that need encoding)
        assert username.replace("-", "").replace("_", "").isalnum()
        assert password.replace("-", "").replace("_", "").isalnum()

    def test_generate_credentials_unique(self) -> None:
        """Each generation should produce unique credentials."""
        user1, pass1 = generate_credentials()
        user2, pass2 = generate_credentials()

        assert user1 != user2
        assert pass1 != pass2

    def test_verify_password_correct(self) -> None:
        """REQ-RC-016: Password verification should succeed for correct password."""
        import bcrypt

        password = "test_password_123"
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        assert verify_password(password, password_hash) is True

    def test_verify_password_incorrect(self) -> None:
        """REQ-RC-016: Password verification should fail for incorrect password."""
        import bcrypt

        password = "correct_password"
        wrong_password = "wrong_password"
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        assert verify_password(wrong_password, password_hash) is False

    def test_store_and_retrieve_credentials(self, temp_db) -> None:
        """REQ-RC-016: Credentials should be stored hashed and retrievable."""
        username = "testuser"
        password = "testpass123"

        with patch("reader.auth.credentials.get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=temp_db)
            mock_conn.return_value.__exit__ = Mock(return_value=False)

            # Store credentials
            store_credentials(username, password)

            # Retrieve credentials
            creds = get_credentials()

            assert creds is not None
            assert creds.username == username
            # Password should be hashed, not plaintext
            assert creds.password_hash != password
            assert creds.password_hash.startswith("$2b$")  # bcrypt format

            # Should verify correctly
            assert verify_password(password, creds.password_hash) is True

    def test_get_credentials_none_when_empty(self, temp_db) -> None:
        """get_credentials should return None when no credentials stored."""
        with patch("reader.auth.credentials.get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=temp_db)
            mock_conn.return_value.__exit__ = Mock(return_value=False)

            creds = get_credentials()
            assert creds is None

    def test_ensure_credentials_generates_once(self, temp_db) -> None:
        """REQ-RC-016: ensure_credentials should generate only if needed."""
        with patch("reader.auth.credentials.get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=temp_db)
            mock_conn.return_value.__exit__ = Mock(return_value=False)

            # First call should generate
            result1 = ensure_credentials()
            assert result1 is not None
            username1, _password1 = result1

            # Second call should not generate (returns None)
            result2 = ensure_credentials()
            assert result2 is None

            # Stored credentials should match first generation
            creds = get_credentials()
            assert creds is not None
            assert creds.username == username1


class TestBasicAuthMiddleware:
    """Tests for HTTP Basic Auth middleware."""

    def test_bypass_mode_returns_anonymous(self) -> None:
        """REQ-RC-016: WHEN DANGEROUS_NO_WEB_AUTH_MODE=1, allow unauthenticated access."""
        with patch("reader.auth.middleware.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                dangerous_no_web_auth_mode=True,
                _env_file=None,
            )

            # No credentials provided, but bypass mode is on
            result = require_basic_auth(credentials=None)
            assert result == "anonymous"

    def test_no_credentials_raises_401(self) -> None:
        """REQ-RC-016: Missing credentials should raise 401."""
        with patch("reader.auth.middleware.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                dangerous_no_web_auth_mode=False,
                _env_file=None,
            )

            with pytest.raises(HTTPException) as exc_info:
                require_basic_auth(credentials=None)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "Authentication required"
            assert exc_info.value.headers == {"WWW-Authenticate": "Basic"}

    def test_missing_stored_credentials_raises_500(self) -> None:
        """REQ-RC-016: If credentials not configured, raise 500."""
        with (
            patch("reader.auth.middleware.get_settings") as mock_settings,
            patch("reader.auth.middleware.get_credentials") as mock_get_creds,
        ):
            mock_settings.return_value = Settings(
                dangerous_no_web_auth_mode=False,
                _env_file=None,
            )
            mock_get_creds.return_value = None

            creds = HTTPBasicCredentials(username="user", password="pass")

            with pytest.raises(HTTPException) as exc_info:
                require_basic_auth(credentials=creds)

            assert exc_info.value.status_code == 500
            assert "not configured" in exc_info.value.detail.lower()

    def test_invalid_username_raises_401(self) -> None:
        """REQ-RC-016: Invalid username should raise 401."""
        import bcrypt

        with (
            patch("reader.auth.middleware.get_settings") as mock_settings,
            patch("reader.auth.middleware.get_credentials") as mock_get_creds,
        ):
            mock_settings.return_value = Settings(
                dangerous_no_web_auth_mode=False,
                _env_file=None,
            )

            password_hash = bcrypt.hashpw(b"correct", bcrypt.gensalt()).decode()
            mock_get_creds.return_value = Credentials(
                username="validuser",
                password_hash=password_hash,
            )

            # Wrong username
            creds = HTTPBasicCredentials(username="wronguser", password="correct")

            with pytest.raises(HTTPException) as exc_info:
                require_basic_auth(credentials=creds)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "Invalid credentials"

    def test_invalid_password_raises_401(self) -> None:
        """REQ-RC-016: Invalid password should raise 401."""
        import bcrypt

        with (
            patch("reader.auth.middleware.get_settings") as mock_settings,
            patch("reader.auth.middleware.get_credentials") as mock_get_creds,
        ):
            mock_settings.return_value = Settings(
                dangerous_no_web_auth_mode=False,
                _env_file=None,
            )

            password_hash = bcrypt.hashpw(b"correct", bcrypt.gensalt()).decode()
            mock_get_creds.return_value = Credentials(
                username="validuser",
                password_hash=password_hash,
            )

            # Wrong password
            creds = HTTPBasicCredentials(username="validuser", password="wrong")

            with pytest.raises(HTTPException) as exc_info:
                require_basic_auth(credentials=creds)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "Invalid credentials"

    def test_valid_credentials_returns_username(self) -> None:
        """REQ-RC-016: Valid credentials should return username."""
        import bcrypt

        with (
            patch("reader.auth.middleware.get_settings") as mock_settings,
            patch("reader.auth.middleware.get_credentials") as mock_get_creds,
        ):
            mock_settings.return_value = Settings(
                dangerous_no_web_auth_mode=False,
                _env_file=None,
            )

            password = "correct_password"
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            mock_get_creds.return_value = Credentials(
                username="validuser",
                password_hash=password_hash,
            )

            creds = HTTPBasicCredentials(username="validuser", password=password)

            result = require_basic_auth(credentials=creds)
            assert result == "validuser"


class TestAPIKeyMiddleware:
    """Tests for API key authentication middleware."""

    def test_api_key_disabled_raises_403(self) -> None:
        """REQ-RC-016: WHEN API_KEY not set, reject all API requests."""
        with patch("reader.auth.middleware.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                api_key="",  # Empty string means disabled
                _env_file=None,
            )

            bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="some_key")

            with pytest.raises(HTTPException) as exc_info:
                require_api_key(bearer=bearer)

            assert exc_info.value.status_code == 403
            assert "disabled" in exc_info.value.detail.lower()

    def test_missing_bearer_token_raises_401(self) -> None:
        """REQ-RC-016: Missing API key should raise 401."""
        with patch("reader.auth.middleware.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                api_key="valid_key",
                _env_file=None,
            )

            with pytest.raises(HTTPException) as exc_info:
                require_api_key(bearer=None)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "API key required"
            assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    def test_invalid_api_key_raises_401(self) -> None:
        """REQ-RC-016: Invalid API key should raise 401."""
        with patch("reader.auth.middleware.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                api_key="valid_key",
                _env_file=None,
            )

            bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong_key")

            with pytest.raises(HTTPException) as exc_info:
                require_api_key(bearer=bearer)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "Invalid API key"

    def test_valid_api_key_returns_key(self) -> None:
        """REQ-RC-016: Valid API key should return the key."""
        with patch("reader.auth.middleware.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                api_key="valid_key_123",
                _env_file=None,
            )

            bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_key_123")

            result = require_api_key(bearer=bearer)
            assert result == "valid_key_123"

    def test_empty_bearer_credentials_raises_401(self) -> None:
        """REQ-RC-016: Empty bearer credentials should raise 401."""
        with patch("reader.auth.middleware.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                api_key="valid_key",
                _env_file=None,
            )

            # Bearer object exists but credentials are empty
            bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="")

            with pytest.raises(HTTPException) as exc_info:
                require_api_key(bearer=bearer)

            assert exc_info.value.status_code == 401
