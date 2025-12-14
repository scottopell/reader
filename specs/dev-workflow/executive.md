# Development Workflow - Executive Summary

## Requirements Summary

The development workflow provides simple commands for managing the Reader
development environment. Developers start, stop, and monitor the server with
single commands. The system handles all configuration internally, eliminating
the need to set environment variables or remember port numbers. Code quality
commands (format, lint, typecheck, test) provide fast feedback during
development. Database commands simplify schema setup and reset operations.

## Technical Summary

A single `dev.py` script manages all development tasks using PEP 723 inline
metadata. Runtime state (PIDs, logs) lives in a `.dev/` directory that is
git-ignored. Port assignment uses SHA256 hashing of the project path to avoid
conflicts between multiple projects. Process management includes health checks
on startup, graceful shutdown with timeout, and stale PID detection. Quality
commands delegate to ruff (format, lint), mypy/pyright (typecheck), and pytest
(test). All environment variables are set internally by the script.

## Status Summary

| Requirement | Status | Notes |
|-------------|--------|-------|
| **REQ-DW-001:** Start Development Without Manual Configuration | ✅ Complete | `./dev.py start` with health check |
| **REQ-DW-002:** Stop the Server Cleanly | ✅ Complete | `./dev.py stop` with graceful shutdown |
| **REQ-DW-003:** Check Server Status at a Glance | ✅ Complete | `./dev.py status` with stale PID detection |
| **REQ-DW-004:** Restart Server After Code Changes | ✅ Complete | `./dev.py restart` |
| **REQ-DW-005:** View Server Logs for Debugging | ✅ Complete | `./dev.py logs [-f] [-n N]` |
| **REQ-DW-006:** Format Code Consistently | ✅ Complete | `./dev.py fmt [--check]` |
| **REQ-DW-007:** Catch Code Quality Issues Early | ✅ Complete | `./dev.py lint [--fix]` |
| **REQ-DW-008:** Catch Type Errors Before Runtime | ✅ Complete | `./dev.py typecheck` |
| **REQ-DW-009:** Run Tests Reliably | ✅ Complete | `./dev.py test [args]` |
| **REQ-DW-010:** Verify All Quality Checks Pass | ✅ Complete | `./dev.py check` |
| **REQ-DW-011:** Initialize Database Schema | ✅ Complete | `./dev.py db-migrate` |
| **REQ-DW-012:** Reset Database to Clean State | ✅ Complete | `./dev.py db-reset` |
| **REQ-DW-013:** Clean Up Development State | ✅ Complete | `./dev.py clean` |

**Progress:** 13 of 13 complete
