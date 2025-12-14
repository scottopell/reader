"""Database module for Reader."""

from reader.db.connection import get_connection
from reader.db.repository import ArticleRepository

__all__ = ["ArticleRepository", "get_connection"]
