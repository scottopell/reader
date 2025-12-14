"""FastAPI application for Reader.

REQ-RC-008 through REQ-RC-015: Web UI
REQ-RC-017, REQ-RC-018: API endpoints
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from reader.auth.credentials import ensure_credentials
from reader.db.migrate import migrate
from reader.web.routes import api, inbox
from reader.web.templates_config import STATIC_DIR


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    # Run migrations on startup
    migrate()

    # REQ-RC-016: WHEN first started THE SYSTEM SHALL log the generated credentials
    new_creds = ensure_credentials()
    if new_creds:
        username, password = new_creds
        print("\n" + "=" * 60)
        print("Generated credentials (save these!):")
        print(f"  Username: {username}")
        print(f"  Password: {password}")
        print("=" * 60 + "\n")

    yield


app = FastAPI(
    title="Reader",
    description="Self-hosted reading curation system with LLM scoring",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include routers
app.include_router(inbox.router)
app.include_router(api.router, prefix="/api")


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    """Health check endpoint for readiness probes."""
    return "ok"
