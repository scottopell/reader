"""Authentication module for Reader."""

from reader.auth.credentials import generate_credentials, get_credentials
from reader.auth.middleware import require_api_key, require_basic_auth

__all__ = [
    "generate_credentials",
    "get_credentials",
    "require_api_key",
    "require_basic_auth",
]
