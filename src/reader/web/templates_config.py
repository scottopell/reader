"""Jinja2 templates configuration."""

from pathlib import Path

import markdown as md
from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def render_markdown(text: str) -> str:
    """Convert markdown to HTML."""
    result: str = md.markdown(
        text,
        extensions=["fenced_code", "tables", "nl2br"],
    )
    return result


# Add custom filter for markdown rendering
# pyright: reportUnknownMemberType=false
templates.env.filters["markdown"] = render_markdown
