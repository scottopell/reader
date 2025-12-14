# Development Workflow

## User Story

As a developer, I need simple commands to manage the development server so that
I can focus on coding without managing environment variables or process details.

## Requirements

### REQ-DW-001: Start Development Without Manual Configuration

WHEN developer runs `./dev.py start`
THE SYSTEM SHALL start the FastAPI server with all required configuration
THE SYSTEM SHALL display the server URL upon successful startup
THE SYSTEM SHALL run the server in the background without blocking the terminal

WHEN the server fails to become healthy within 30 seconds
THE SYSTEM SHALL report the failure and clean up partial state

**Rationale:** Developers want to start working immediately without hunting for
environment variables or remembering port numbers.

---

### REQ-DW-002: Stop the Server Cleanly

WHEN developer runs `./dev.py stop`
THE SYSTEM SHALL terminate the server and all child processes
THE SYSTEM SHALL report if no server is currently running

WHEN a process refuses to terminate gracefully
THE SYSTEM SHALL force termination after 5 seconds

**Rationale:** Developers need to free system resources when switching contexts
or shutting down for the day.

---

### REQ-DW-003: Check Server Status at a Glance

WHEN developer runs `./dev.py status`
THE SYSTEM SHALL display whether the server is running or stopped
THE SYSTEM SHALL display the server URL when running
THE SYSTEM SHALL detect and report stale state from crashed processes

**Rationale:** Developers want quick visibility into whether the server is
available before making requests.

---

### REQ-DW-004: Restart Server After Code Changes

WHEN developer runs `./dev.py restart`
THE SYSTEM SHALL stop any running server and start a fresh instance

WHEN no server is currently running
THE SYSTEM SHALL start a new server instance

**Rationale:** After making code changes, developers need to restart quickly
without running multiple commands.

---

### REQ-DW-005: View Server Logs for Debugging

WHEN developer runs `./dev.py logs`
THE SYSTEM SHALL display recent server output

WHEN developer runs `./dev.py logs -f`
THE SYSTEM SHALL stream logs in real-time until interrupted

**Rationale:** When debugging issues, developers need to see what the server
is doing without switching to a separate terminal window.

---

### REQ-DW-006: Format Code Consistently

WHEN developer runs `./dev.py fmt`
THE SYSTEM SHALL format all source code using the project's style rules

WHEN developer runs `./dev.py fmt --check`
THE SYSTEM SHALL report formatting violations without modifying files

**Rationale:** Consistent formatting reduces code review friction and merge
conflicts.

---

### REQ-DW-007: Catch Code Quality Issues Early

WHEN developer runs `./dev.py lint`
THE SYSTEM SHALL check code for style violations and potential bugs
THE SYSTEM SHALL display violation details with file locations

**Rationale:** Catching lint issues before commit saves time and prevents CI
failures.

---

### REQ-DW-008: Catch Type Errors Before Runtime

WHEN developer runs `./dev.py typecheck`
THE SYSTEM SHALL run static type analysis
THE SYSTEM SHALL report type errors with file locations

**Rationale:** Static type checking catches bugs that would only appear at
runtime, improving code reliability.

---

### REQ-DW-009: Run Tests Reliably

WHEN developer runs `./dev.py test`
THE SYSTEM SHALL run the test suite and report results

WHEN developer provides additional arguments after `test`
THE SYSTEM SHALL pass those arguments to the test runner

**Rationale:** Running tests should be one command away, with flexibility to
focus on specific tests during development.

---

### REQ-DW-010: Verify All Quality Checks Pass

WHEN developer runs `./dev.py check`
THE SYSTEM SHALL run format check, lint, and type checking
THE SYSTEM SHALL report overall pass or fail status

**Rationale:** Before committing, developers need one command to verify all
quality gates pass.

---

### REQ-DW-011: Initialize Database Schema

WHEN developer runs `./dev.py db-migrate`
THE SYSTEM SHALL apply pending schema migrations
THE SYSTEM SHALL create the database if it does not exist

**Rationale:** New developers and fresh environments need a simple way to set
up the database.

---

### REQ-DW-012: Reset Database to Clean State

WHEN developer runs `./dev.py db-reset`
THE SYSTEM SHALL prompt for confirmation before proceeding
THE SYSTEM SHALL delete and recreate the database
THE SYSTEM SHALL apply migrations to the fresh database

**Rationale:** During development, a corrupted or cluttered database sometimes
needs a fresh start.

---

### REQ-DW-013: Clean Up Development State

WHEN developer runs `./dev.py clean`
THE SYSTEM SHALL stop any running server
THE SYSTEM SHALL remove all runtime state files

**Rationale:** When switching branches or troubleshooting, developers need to
reset to a completely clean state.
