"""FastAPI application for Reader.

REQ-RC-008 through REQ-RC-015: Web UI
REQ-RC-017, REQ-RC-018: API endpoints
REQ-RC-002: Background ingestion workers
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from reader.auth.credentials import ensure_credentials
from reader.config import get_settings
from reader.db.migrate import migrate
from reader.ingestion.rss import ingest_all_rss
from reader.refiner.batch import run_daily_refinement
from reader.web.routes import api, inbox
from reader.web.templates_config import STATIC_DIR

logger = logging.getLogger(__name__)

# Global set to track background tasks (prevent garbage collection)
background_tasks: set[asyncio.Task[None]] = set()


async def periodic_rss_ingestion() -> None:
    """REQ-RC-002: Background worker for RSS feed ingestion."""
    settings = get_settings()
    logger.info("Starting RSS ingestion background worker")

    while True:
        try:
            logger.info("Running scheduled RSS ingestion")
            await ingest_all_rss()
        except asyncio.CancelledError:
            logger.info("RSS ingestion worker cancelled")
            raise
        except Exception as e:
            logger.error(f"RSS ingestion failed: {e}", exc_info=True)

        # Sleep until next check
        await asyncio.sleep(settings.rss_check_interval_seconds)


async def periodic_prompt_refinement() -> None:
    """REQ-RC-021: Background worker for daily prompt refinement."""
    settings = get_settings()
    logger.info("Starting prompt refinement background worker")

    while True:
        try:
            logger.info("Running scheduled prompt refinement")
            result = await run_daily_refinement()
            if result:
                logger.info("Created new prompt generation %d", result.id)
            else:
                logger.info("No feedback to process for refinement")
        except asyncio.CancelledError:
            logger.info("Prompt refinement worker cancelled")
            raise
        except Exception as e:
            logger.error(f"Prompt refinement failed: {e}", exc_info=True)

        # Sleep until next check (default 24 hours)
        await asyncio.sleep(settings.refinement_interval_seconds)


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

    # REQ-RC-002: Start background ingestion workers
    logger.info("Starting background workers")
    rss_task = asyncio.create_task(periodic_rss_ingestion())
    refinement_task = asyncio.create_task(periodic_prompt_refinement())

    # Track tasks to prevent garbage collection
    background_tasks.add(rss_task)
    background_tasks.add(refinement_task)

    # Add done callback for cleanup
    rss_task.add_done_callback(background_tasks.discard)
    refinement_task.add_done_callback(background_tasks.discard)

    yield

    # REQ-RC-002: Shutdown background workers gracefully
    logger.info("Stopping background ingestion workers")
    for task in background_tasks:
        task.cancel()

    # Wait for tasks to complete cancellation
    await asyncio.gather(*background_tasks, return_exceptions=True)
    logger.info("All background workers stopped")


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
