"""Credential generation and management.

REQ-RC-016: Secure Access by Default
"""

import secrets
from dataclasses import dataclass

from passlib.hash import bcrypt

from reader.db.connection import get_connection


@dataclass
class Credentials:
    """Generated credentials for Basic Auth."""

    username: str
    password_hash: str


def generate_credentials() -> tuple[str, str]:
    """Generate random username and password.

    Returns:
        Tuple of (username, plaintext_password).
        Password is only available at generation time.
    """
    username = secrets.token_urlsafe(6)  # ~8 chars
    password = secrets.token_urlsafe(24)  # ~32 chars
    return username, password


def store_credentials(username: str, password: str) -> None:
    """Store hashed credentials in the database."""
    password_hash = bcrypt.hash(password)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO auth_config (key, value) VALUES (?, ?)",
            ("username", username),
        )
        conn.execute(
            "INSERT OR REPLACE INTO auth_config (key, value) VALUES (?, ?)",
            ("password_hash", password_hash),
        )
        conn.commit()


def get_credentials() -> Credentials | None:
    """Get stored credentials from database."""
    with get_connection() as conn:
        username_row = conn.execute(
            "SELECT value FROM auth_config WHERE key = 'username'"
        ).fetchone()
        password_row = conn.execute(
            "SELECT value FROM auth_config WHERE key = 'password_hash'"
        ).fetchone()

        if username_row and password_row:
            return Credentials(
                username=username_row["value"],
                password_hash=password_row["value"],
            )
        return None


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.verify(password, password_hash)


def ensure_credentials() -> tuple[str, str] | None:
    """Ensure credentials exist, generating if needed.

    Returns:
        Tuple of (username, password) if newly generated, None if already exists.
    """
    existing = get_credentials()
    if existing:
        return None

    username, password = generate_credentials()
    store_credentials(username, password)
    return username, password
