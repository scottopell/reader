#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
Development task runner for Reader.

Usage:
    ./dev.py <command> [args...]

Commands:
    fmt         Format code with ruff
    lint        Lint code with ruff
    typecheck   Run mypy and pyright
    test        Run pytest
    check       Run fmt --check, lint, and typecheck
    serve       Start development server
    db-migrate  Run database migrations
    db-reset    Reset database (warning: deletes data)
    help        Show this help message
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SRC_DIR = PROJECT_ROOT / "src"
TESTS_DIR = PROJECT_ROOT / "tests"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[bytes]:
    """Run a command, printing it first."""
    print(f"\n→ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=PROJECT_ROOT, check=check)


def cmd_fmt(check: bool = False) -> int:
    """Format code with ruff."""
    args = ["uv", "run", "ruff", "format"]
    if check:
        args.append("--check")
    args.append(".")
    result = run(args, check=False)
    return result.returncode


def cmd_lint(fix: bool = False) -> int:
    """Lint code with ruff."""
    args = ["uv", "run", "ruff", "check"]
    if fix:
        args.append("--fix")
    args.append(".")
    result = run(args, check=False)
    return result.returncode


def cmd_typecheck() -> int:
    """Run both mypy and pyright."""
    print("\n=== Running mypy ===")
    mypy_result = run(["uv", "run", "mypy", "src"], check=False)

    print("\n=== Running pyright ===")
    pyright_result = run(["uv", "run", "pyright"], check=False)

    if mypy_result.returncode != 0 or pyright_result.returncode != 0:
        return 1
    return 0


def cmd_test(args: list[str] | None = None) -> int:
    """Run pytest with optional arguments."""
    cmd = ["uv", "run", "pytest"]
    if args:
        cmd.extend(args)
    result = run(cmd, check=False)
    return result.returncode


def cmd_check() -> int:
    """Run all checks: fmt --check, lint, typecheck."""
    print("=== Checking format ===")
    fmt_rc = cmd_fmt(check=True)

    print("\n=== Checking lint ===")
    lint_rc = cmd_lint()

    print("\n=== Checking types ===")
    type_rc = cmd_typecheck()

    if fmt_rc != 0 or lint_rc != 0 or type_rc != 0:
        print("\n❌ Some checks failed")
        return 1

    print("\n✓ All checks passed")
    return 0


def cmd_serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = True) -> int:
    """Start development server."""
    cmd = [
        "uv",
        "run",
        "uvicorn",
        "reader.web.app:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")
    result = run(cmd, check=False)
    return result.returncode


def cmd_db_migrate() -> int:
    """Run database migrations."""
    result = run(["uv", "run", "python", "-m", "reader.db.migrate"], check=False)
    return result.returncode


def cmd_db_reset() -> int:
    """Reset database (deletes all data)."""
    print("⚠️  This will delete all data. Are you sure? [y/N] ", end="")
    confirm = input().strip().lower()
    if confirm != "y":
        print("Aborted.")
        return 1

    result = run(["uv", "run", "python", "-m", "reader.db.reset"], check=False)
    return result.returncode


def cmd_help() -> int:
    """Show help message."""
    print(__doc__)
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        return cmd_help()

    command = sys.argv[1]
    args = sys.argv[2:]

    match command:
        case "fmt":
            check = "--check" in args
            return cmd_fmt(check=check)
        case "lint":
            fix = "--fix" in args
            return cmd_lint(fix=fix)
        case "typecheck":
            return cmd_typecheck()
        case "test":
            return cmd_test(args if args else None)
        case "check":
            return cmd_check()
        case "serve":
            host = "127.0.0.1"
            port = 8000
            reload = "--no-reload" not in args
            for i, arg in enumerate(args):
                if arg == "--host" and i + 1 < len(args):
                    host = args[i + 1]
                elif arg == "--port" and i + 1 < len(args):
                    port = int(args[i + 1])
            return cmd_serve(host=host, port=port, reload=reload)
        case "db-migrate":
            return cmd_db_migrate()
        case "db-reset":
            return cmd_db_reset()
        case "help" | "--help" | "-h":
            return cmd_help()
        case _:
            print(f"Unknown command: {command}")
            return cmd_help()


if __name__ == "__main__":
    sys.exit(main())
