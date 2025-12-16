#!/usr/bin/env -S uv run python
"""Development task runner for Reader.

Usage:
    ./dev.py <command> [args...]

Server Commands:
    start       Start development server in background
    stop        Stop development server
    status      Show server status
    restart     Restart development server
    logs        View server logs (-f to follow, -n N for last N lines)
    serve       Start server in foreground (blocking)

Quality Commands:
    fmt [target]    Format code (--check to verify only)
                    target: python, markdown, all (default: all)
    lint [target]   Lint code (--fix for python auto-fix)
                    target: python, markdown, all (default: all)
    typecheck       Run mypy and pyright
    test            Run pytest (pass additional args after)
    check           Run fmt --check, lint, and typecheck

Database Commands:
    db-migrate  Run database migrations
    db-reset    Reset database (warning: deletes data)

Ingestion Commands:
    ingest-rss       Ingest articles from all enabled RSS feeds
    load-feeds       Bulk load RSS feeds from file or arguments
    score-existing   Score all existing unscored articles with Elo

Maintenance Commands:
    clean       Stop server and remove all runtime state
    help        Show this help message
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SRC_DIR = PROJECT_ROOT / "src"
TESTS_DIR = PROJECT_ROOT / "tests"

# REQ-DW-001: Runtime state directory
DEV_DIR = PROJECT_ROOT / ".dev"
PID_FILE = DEV_DIR / "server.pid"
LOG_FILE = DEV_DIR / "server.log"

# REQ-DW-009: Internal environment configuration
DEFAULT_ENV = {
    "READER_LLM_BACKEND": "ollama",
    "READER_OLLAMA_MODEL": "gemma3n:latest",  # Use Gemma 3 (6.9B) for scoring
    "READER_SCORING_DELAY_SECONDS": "2.0",  # Throttle scoring to prevent GPU overload
    "READER_DANGEROUS_NO_WEB_AUTH_MODE": "1",  # Dev server runs without auth
}


def get_default_port() -> int:
    """Calculate deterministic port from project path.

    REQ-DW-001: Deterministic port assignment avoids conflicts between projects.
    """
    hash_bytes = hashlib.sha256(str(PROJECT_ROOT).encode()).digest()
    port_offset = int.from_bytes(hash_bytes[:2], "big") % 1000
    return 8000 + port_offset


def ensure_dev_dir() -> None:
    """Create .dev/ directory if it doesn't exist."""
    DEV_DIR.mkdir(exist_ok=True)


def read_pid() -> int | None:
    """Read PID from file, return None if not exists."""
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def write_pid(pid: int) -> None:
    """Write PID to file."""
    ensure_dev_dir()
    PID_FILE.write_text(str(pid))
    PID_FILE.chmod(0o600)


def is_process_running(pid: int) -> bool:
    """Check if a process is running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it
        return True


def cleanup_stale_pid() -> bool:
    """Remove stale PID file if process is not running.

    REQ-DW-003: Detect and report stale state from crashed processes.
    Returns True if stale PID was cleaned up.
    """
    pid = read_pid()
    if pid is None:
        return False
    if not is_process_running(pid):
        PID_FILE.unlink(missing_ok=True)
        return True
    return False


def get_server_url(port: int) -> str:
    """Get the server URL."""
    return f"http://127.0.0.1:{port}"


def wait_for_healthy(port: int, timeout: float = 30.0) -> bool:
    """Poll health endpoint until ready.

    REQ-DW-001: Health check confirms server is ready to serve requests.
    """
    import httpx

    url = f"{get_server_url(port)}/health"
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code == 200:
                return True
        except httpx.RequestError:
            pass
        time.sleep(0.5)
    return False


def stop_process(pid: int, timeout: float = 5.0) -> bool:
    """Stop a process gracefully, force kill if needed.

    REQ-DW-002: Graceful shutdown with timeout, then force termination.
    """
    if not is_process_running(pid):
        return True

    # Try to get process group for child cleanup
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        # Fall back to killing just the main process
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True

    # Wait for graceful shutdown
    start = time.time()
    while time.time() - start < timeout:
        if not is_process_running(pid):
            return True
        time.sleep(0.1)

    # Force kill if still running
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)

    return not is_process_running(pid)


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[bytes]:
    """Run a command, printing it first."""
    print(f"\n→ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=PROJECT_ROOT, check=check)


# =============================================================================
# Server Commands (REQ-DW-001 through REQ-DW-005)
# =============================================================================


def cmd_start(port: int | None = None) -> int:
    """Start development server in background.

    REQ-DW-001: Start Development Without Manual Configuration
    """
    # Check for stale PID
    if cleanup_stale_pid():
        print("Cleaned up stale PID file from crashed server")

    # Check if already running
    pid = read_pid()
    if pid is not None and is_process_running(pid):
        actual_port = port or get_default_port()
        print(f"Server already running (PID {pid})")
        print(f"  URL: {get_server_url(actual_port)}")
        return 0

    # Determine port
    actual_port = port or get_default_port()

    # Ensure .dev/ exists
    ensure_dev_dir()

    # Set up environment
    env = os.environ.copy()
    for key, value in DEFAULT_ENV.items():
        if key not in env:
            env[key] = value

    # Start server in background
    print(f"Starting server on port {actual_port}...")

    with LOG_FILE.open("w") as log_file:
        # Start in new process group for clean shutdown
        process = subprocess.Popen(
            [
                "uv",
                "run",
                "uvicorn",
                "reader.web.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(actual_port),
                "--reload",
            ],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=PROJECT_ROOT,
            env=env,
            start_new_session=True,
        )

    # Write PID
    write_pid(process.pid)

    # Wait for health check
    print("Waiting for server to become healthy...")
    if wait_for_healthy(actual_port):
        print(f"✓ Server started (PID {process.pid})")
        print(f"  URL: {get_server_url(actual_port)}")
        return 0
    else:
        print("✗ Server failed to become healthy within 30 seconds")
        print("\nLast 20 lines of log:")
        cmd_logs(lines=20)

        # Cleanup
        stop_process(process.pid)
        PID_FILE.unlink(missing_ok=True)
        return 1


def cmd_stop() -> int:
    """Stop development server.

    REQ-DW-002: Stop the Server Cleanly
    """
    # Check for stale PID
    if cleanup_stale_pid():
        print("Cleaned up stale PID file (server was not running)")
        return 0

    pid = read_pid()
    if pid is None:
        print("Server is not running")
        return 0

    if not is_process_running(pid):
        print("Server is not running (cleaning up PID file)")
        PID_FILE.unlink(missing_ok=True)
        return 0

    print(f"Stopping server (PID {pid})...")
    if stop_process(pid):
        PID_FILE.unlink(missing_ok=True)
        print("✓ Server stopped")
        return 0
    else:
        print("✗ Failed to stop server")
        return 1


def cmd_status() -> int:
    """Show server status.

    REQ-DW-003: Check Server Status at a Glance
    """
    # Check for stale PID
    if cleanup_stale_pid():
        print("Status: stopped (cleaned up stale PID)")
        return 0

    pid = read_pid()
    if pid is None:
        print("Status: stopped")
        return 0

    if not is_process_running(pid):
        PID_FILE.unlink(missing_ok=True)
        print("Status: stopped (cleaned up stale PID)")
        return 0

    port = get_default_port()
    print("Status: running")
    print(f"  PID: {pid}")
    print(f"  URL: {get_server_url(port)}")
    print(f"  Log: {LOG_FILE}")
    return 0


def cmd_restart(port: int | None = None) -> int:
    """Restart development server.

    REQ-DW-004: Restart Server After Code Changes
    """
    print("Restarting server...")
    cmd_stop()
    return cmd_start(port=port)


def cmd_logs(follow: bool = False, lines: int = 50) -> int:
    """View server logs.

    REQ-DW-005: View Server Logs for Debugging
    """
    if not LOG_FILE.exists():
        print("No log file found. Server may not have been started yet.")
        return 1

    if follow:
        # Use tail -f for following
        with contextlib.suppress(KeyboardInterrupt):
            subprocess.run(["tail", "-f", str(LOG_FILE)], check=True)
        return 0
    else:
        # Show last N lines
        try:
            result = subprocess.run(
                ["tail", "-n", str(lines), str(LOG_FILE)],
                capture_output=True,
                text=True,
            )
            print(result.stdout, end="")
            return 0
        except subprocess.CalledProcessError:
            return 1


def cmd_serve(host: str = "127.0.0.1", port: int | None = None, reload: bool = True) -> int:
    """Start development server in foreground (blocking)."""
    actual_port = port or get_default_port()

    # Set up environment
    env = os.environ.copy()
    for key, value in DEFAULT_ENV.items():
        if key not in env:
            env[key] = value

    cmd = [
        "uv",
        "run",
        "uvicorn",
        "reader.web.app:app",
        "--host",
        host,
        "--port",
        str(actual_port),
    ]
    if reload:
        cmd.append("--reload")

    print(f"Starting server on {get_server_url(actual_port)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, check=False)
    return result.returncode


# =============================================================================
# Quality Commands (REQ-DW-006 through REQ-DW-010)
# =============================================================================


def cmd_fmt_python(check: bool = False) -> int:
    """Format Python code with ruff."""
    args = ["uv", "run", "ruff", "format"]
    if check:
        args.append("--check")
    args.append(".")
    result = run(args, check=False)
    return result.returncode


def cmd_fmt_markdown(check: bool = False) -> int:
    """Format Markdown files with rumdl."""
    args = ["uvx", "rumdl", "check", "."] if check else ["uvx", "rumdl", "fmt", "."]
    result = run(args, check=False)
    return result.returncode


def cmd_fmt(target: str = "all", check: bool = False) -> int:
    """Format code with ruff and rumdl.

    REQ-DW-006: Format Code Consistently
    """
    if target == "python":
        return cmd_fmt_python(check=check)
    elif target == "markdown":
        return cmd_fmt_markdown(check=check)
    else:  # all
        print("=== Formatting Python ===")
        python_rc = cmd_fmt_python(check=check)
        print("\n=== Formatting Markdown ===")
        markdown_rc = cmd_fmt_markdown(check=check)
        if python_rc != 0 or markdown_rc != 0:
            return 1
        return 0


def cmd_lint_python(fix: bool = False) -> int:
    """Lint Python code with ruff."""
    args = ["uv", "run", "ruff", "check"]
    if fix:
        args.append("--fix")
    args.append(".")
    result = run(args, check=False)
    return result.returncode


def cmd_lint_markdown() -> int:
    """Lint Markdown files with rumdl."""
    result = run(["uvx", "rumdl", "check", "."], check=False)
    if result.returncode != 0:
        print("Run './dev.py fmt markdown' to auto-fix")
    return result.returncode


def cmd_lint(target: str = "all", fix: bool = False) -> int:
    """Lint code with ruff and rumdl.

    REQ-DW-007: Catch Code Quality Issues Early
    """
    if target == "python":
        return cmd_lint_python(fix=fix)
    elif target == "markdown":
        return cmd_lint_markdown()
    else:  # all
        print("=== Linting Python ===")
        python_rc = cmd_lint_python(fix=fix)
        print("\n=== Linting Markdown ===")
        markdown_rc = cmd_lint_markdown()
        if python_rc != 0 or markdown_rc != 0:
            return 1
        return 0


def cmd_typecheck() -> int:
    """Run both mypy and pyright.

    REQ-DW-008: Catch Type Errors Before Runtime
    """
    print("\n=== Running mypy ===")
    mypy_result = run(["uv", "run", "mypy", "src"], check=False)

    print("\n=== Running pyright ===")
    pyright_result = run(["uv", "run", "pyright"], check=False)

    if mypy_result.returncode != 0 or pyright_result.returncode != 0:
        return 1
    return 0


def cmd_test(args: list[str] | None = None) -> int:
    """Run pytest with optional arguments.

    REQ-DW-009: Run Tests Reliably
    """
    cmd = ["uv", "run", "pytest"]
    if args:
        cmd.extend(args)
    result = run(cmd, check=False)
    return result.returncode


def cmd_check() -> int:
    """Run all checks: fmt --check, lint, typecheck.

    REQ-DW-010: Verify All Quality Checks Pass
    """
    print("=== Checking Python format ===")
    py_fmt_rc = cmd_fmt_python(check=True)

    print("\n=== Checking Markdown format ===")
    md_fmt_rc = cmd_fmt_markdown(check=True)

    print("\n=== Linting Python ===")
    py_lint_rc = cmd_lint_python()

    print("\n=== Linting Markdown ===")
    md_lint_rc = cmd_lint_markdown()

    print("\n=== Checking types ===")
    type_rc = cmd_typecheck()

    if any([py_fmt_rc, md_fmt_rc, py_lint_rc, md_lint_rc, type_rc]):
        print("\n✗ Some checks failed")
        return 1

    print("\n✓ All checks passed")
    return 0


# =============================================================================
# Database Commands (REQ-DW-011, REQ-DW-012)
# =============================================================================


def cmd_db_migrate() -> int:
    """Run database migrations.

    REQ-DW-011: Initialize Database Schema
    """
    result = run(["uv", "run", "python", "-m", "reader.db.migrate"], check=False)
    return result.returncode


def cmd_db_reset() -> int:
    """Reset database (deletes all data).

    REQ-DW-012: Reset Database to Clean State
    """
    print("⚠️  This will delete all data. Are you sure? [y/N] ", end="")
    confirm = input().strip().lower()
    if confirm != "y":
        print("Aborted.")
        return 1

    result = run(["uv", "run", "python", "-m", "reader.db.reset"], check=False)
    return result.returncode


# =============================================================================
# Ingestion Commands (REQ-RC-001, REQ-RC-002)
# =============================================================================


def cmd_ingest_rss() -> int:
    """Ingest articles from all enabled RSS feeds.

    REQ-RC-002: Discover New Content from RSS Feeds
    """
    # Set up environment with dev defaults
    env = os.environ.copy()
    for key, value in DEFAULT_ENV.items():
        if key not in env:
            env[key] = value

    print("\n→ uv run python -m reader.ingestion.rss")
    result = subprocess.run(
        ["uv", "run", "python", "-m", "reader.ingestion.rss"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )
    return result.returncode


def cmd_score_existing() -> int:
    """Score all existing unscored articles using Elo pairwise comparisons.

    REQ-RC-024: Elo-based pairwise comparison scoring
    """
    # Set up environment with dev defaults
    env = os.environ.copy()
    for key, value in DEFAULT_ENV.items():
        if key not in env:
            env[key] = value

    print("\n→ uv run python -c [scoring script]")
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-c",
            """
import asyncio
import logging
from reader.db.repository import ArticleRepository
from reader.scoring.elo_scoring import score_article_with_elo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def score_all():
    repo = ArticleRepository()

    # Get articles that need scoring (elo_comparisons = 0)
    articles = repo.get_unscored(limit=10000)
    # Filter to those with elo_comparisons = 0
    from reader.db.connection import get_connection
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM articles WHERE elo_comparisons = 0 AND extraction_status = 'success' ORDER BY received_at DESC"
        ).fetchall()

    article_ids = [row[0] for row in rows]
    print(f"Found {len(article_ids)} articles to score")

    for i, article_id in enumerate(article_ids, 1):
        print(f"\\nScoring article {i}/{len(article_ids)} (ID: {article_id})")
        try:
            comparisons, errors = await score_article_with_elo(article_id)
            if errors:
                print(f"  Completed with {len(errors)} errors")
        except Exception as e:
            print(f"  Failed: {e}")

    print(f"\\nScoring complete!")

asyncio.run(score_all())
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )
    return result.returncode


def cmd_load_feeds(file_path: str | None = None, urls: list[str] | None = None) -> int:
    """Bulk load RSS feeds from file or command line arguments.

    REQ-RC-015: Manage Content Sources

    Usage:
        ./dev.py load-feeds --file feeds.txt
        ./dev.py load-feeds <url1> <url2> ...
    """
    # Import here to avoid circular deps
    try:
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-c",
                f"""
import sys
from reader.db.repository import FeedSourceRepository
from reader.models.source import FeedSourceCreate, SourceType

feeds_to_load = []

# Read from file if provided
if {file_path!r}:
    with open({file_path!r}, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith('#'):
                # Support "URL name" format or just "URL"
                parts = line.split(maxsplit=1)
                url = parts[0]
                name = parts[1] if len(parts) > 1 else None
                feeds_to_load.append((url, name))
# Otherwise use provided URLs
elif {urls!r}:
    for url in {urls!r}:
        feeds_to_load.append((url, None))

if not feeds_to_load:
    print("No feeds to load")
    sys.exit(1)

repo = FeedSourceRepository()
loaded = 0
skipped = 0

for url, name in feeds_to_load:
    # Check if already exists
    existing = [s for s in repo.get_all() if s.identifier == url]
    if existing:
        print(f"Skipping (already exists): {{url}}")
        skipped += 1
        continue

    # Create feed source
    source = FeedSourceCreate(
        type=SourceType.RSS,
        identifier=url,
        display_name=name,
        enabled=True,
        check_interval_hours=6
    )
    source_id = repo.create(source)
    print(f"Added feed {{source_id}}: {{url}}" + (f" ({{name}})" if name else ""))
    loaded += 1

print(f"\\nLoaded {{loaded}} feeds, skipped {{skipped}} duplicates")
sys.exit(0)
""",
            ],
            cwd=PROJECT_ROOT,
            check=False,
        )
        return result.returncode
    except Exception as e:
        print(f"Error loading feeds: {e}")
        return 1


# =============================================================================
# Maintenance Commands (REQ-DW-013)
# =============================================================================


def cmd_clean() -> int:
    """Stop server and remove all runtime state.

    REQ-DW-013: Clean Up Development State
    """
    # Stop server if running
    pid = read_pid()
    if pid is not None and is_process_running(pid):
        print("Stopping server...")
        cmd_stop()

    # Remove .dev/ contents
    if DEV_DIR.exists():
        print(f"Removing {DEV_DIR}/...")
        shutil.rmtree(DEV_DIR)
        print("✓ Cleaned up development state")
    else:
        print("Nothing to clean")

    return 0


def cmd_help() -> int:
    """Show help message."""
    print(__doc__)
    return 0


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    if len(sys.argv) < 2:
        return cmd_help()

    command = sys.argv[1]
    args = sys.argv[2:]

    match command:
        # Server commands
        case "start":
            port = None
            for i, arg in enumerate(args):
                if arg == "--port" and i + 1 < len(args):
                    port = int(args[i + 1])
            return cmd_start(port=port)
        case "stop":
            return cmd_stop()
        case "status":
            return cmd_status()
        case "restart":
            port = None
            for i, arg in enumerate(args):
                if arg == "--port" and i + 1 < len(args):
                    port = int(args[i + 1])
            return cmd_restart(port=port)
        case "logs":
            follow = "-f" in args
            lines = 50
            for i, arg in enumerate(args):
                if arg == "-n" and i + 1 < len(args):
                    lines = int(args[i + 1])
            return cmd_logs(follow=follow, lines=lines)
        case "serve":
            host = "127.0.0.1"
            port = None
            reload = "--no-reload" not in args
            for i, arg in enumerate(args):
                if arg == "--host" and i + 1 < len(args):
                    host = args[i + 1]
                elif arg == "--port" and i + 1 < len(args):
                    port = int(args[i + 1])
            return cmd_serve(host=host, port=port, reload=reload)

        # Quality commands
        case "fmt":
            check = "--check" in args
            # Find target (python, markdown, all)
            target = "all"
            for arg in args:
                if arg in ("python", "markdown", "all"):
                    target = arg
                    break
            return cmd_fmt(target=target, check=check)
        case "lint":
            fix = "--fix" in args
            # Find target (python, markdown, all)
            target = "all"
            for arg in args:
                if arg in ("python", "markdown", "all"):
                    target = arg
                    break
            return cmd_lint(target=target, fix=fix)
        case "typecheck":
            return cmd_typecheck()
        case "test":
            return cmd_test(args if args else None)
        case "check":
            return cmd_check()

        # Database commands
        case "db-migrate":
            return cmd_db_migrate()
        case "db-reset":
            return cmd_db_reset()

        # Ingestion commands
        case "ingest-rss":
            return cmd_ingest_rss()
        case "score-existing":
            return cmd_score_existing()
        case "load-feeds":
            # Parse arguments
            file_path = None
            urls = []
            i = 0
            while i < len(args):
                if args[i] in ("--file", "-f") and i + 1 < len(args):
                    file_path = args[i + 1]
                    i += 2
                elif not args[i].startswith("-"):
                    urls.append(args[i])
                    i += 1
                else:
                    i += 1
            return cmd_load_feeds(file_path=file_path, urls=urls if urls else None)

        # Maintenance commands
        case "clean":
            return cmd_clean()

        # Help
        case "help" | "--help" | "-h":
            return cmd_help()
        case _:
            print(f"Unknown command: {command}")
            return cmd_help()


if __name__ == "__main__":
    sys.exit(main())
