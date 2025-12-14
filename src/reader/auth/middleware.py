"""Authentication middleware for FastAPI.

REQ-RC-016: Secure Access by Default
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)

from reader.auth.credentials import get_credentials, verify_password
from reader.config import get_settings

basic_security = HTTPBasic(auto_error=False)
bearer_security = HTTPBearer(auto_error=False)


def require_basic_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic_security)],
) -> str:
    """Require HTTP Basic Auth for web UI routes.

    REQ-RC-016: THE SYSTEM SHALL default to HTTP Basic Auth

    Returns:
        The authenticated username.

    Raises:
        HTTPException: If authentication fails.
    """
    settings = get_settings()

    # REQ-RC-016: WHEN DANGEROUS_NO_WEB_AUTH_MODE=1 is set
    # THE SYSTEM SHALL allow unauthenticated web UI route access
    if settings.dangerous_no_web_auth_mode:
        return "anonymous"

    # No credentials provided - prompt for auth
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    stored = get_credentials()
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not configured. Run db-migrate first.",
        )

    # Use constant-time comparison to prevent timing attacks
    username_correct = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        stored.username.encode("utf-8"),
    )
    password_correct = verify_password(credentials.password, stored.password_hash)

    if not (username_correct and password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


def require_api_key(
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_security)],
) -> str:
    """Require API key for API routes.

    REQ-RC-016: WHEN API_KEY environment variable is set
    THE SYSTEM SHALL accept that key in Authorization header for API endpoints

    Returns:
        The API key.

    Raises:
        HTTPException: If API key is missing or invalid.
    """
    settings = get_settings()

    # REQ-RC-016: WHEN API_KEY is not set
    # THE SYSTEM SHALL reject all API key authentication attempts
    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API access is disabled. Set API_KEY environment variable.",
        )

    if not bearer or not bearer.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time comparison
    if not secrets.compare_digest(bearer.credentials, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return bearer.credentials
