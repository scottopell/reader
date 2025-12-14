# Development Workflow - Technical Design

## Architecture Overview

The development workflow is managed by a single `dev.py` script using PEP 723
inline script metadata. All runtime state (PIDs, logs) lives in a `.dev/`
directory that is git-ignored. The script sets all required environment
variables internally, eliminating external configuration.

## Runtime State Directory

```text
.dev/
├── server.pid      # Server process ID
└── server.log      # Server stdout/stderr
```

The `.dev/` directory:

- Created automatically on first use
- Added to `.gitignore` if not present
- Contains only runtime state, never configuration

## Port Assignment

### Deterministic Port Calculation

To avoid port conflicts between projects, the port is calculated from the
project path:

```python
import hashlib

def get_default_port(project_path: str) -> int:
    """Calculate deterministic port from project path."""
    hash_bytes = hashlib.sha256(project_path.encode()).digest()
    port_offset = int.from_bytes(hash_bytes[:2], 'big') % 1000
    return 8000 + port_offset
```

This ensures:

- Same project always gets the same port
- Different projects on the same machine get different ports
- Ports stay in the 8000-8999 range

## Process Management

### PID File Lifecycle

1. **Start**: Write PID to `.dev/server.pid` after successful fork
2. **Status**: Read PID, verify process exists via `os.kill(pid, 0)`
3. **Stop**: Read PID, send SIGTERM, wait up to 5s, send SIGKILL if needed
4. **Cleanup**: Remove PID file after process terminates

### Stale PID Detection

A stale PID exists when the PID file exists but the process does not:

```python
def is_stale_pid(pid_file: Path) -> bool:
    if not pid_file.exists():
        return False
    pid = int(pid_file.read_text())
    try:
        os.kill(pid, 0)  # Signal 0 checks existence
        return False
    except ProcessLookupError:
        return True
```

Stale PIDs are automatically cleaned up during `status`, `start`, and `stop`.

### Child Process Cleanup

The server may spawn child processes. On stop, kill the entire process group:

```python
import signal

def stop_server(pid: int) -> None:
    # Send SIGTERM to process group
    os.killpg(os.getpgid(pid), signal.SIGTERM)

    # Wait for graceful shutdown
    for _ in range(50):  # 5 seconds
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            return

    # Force kill if still running
    os.killpg(os.getpgid(pid), signal.SIGKILL)
```

## Health Check on Startup

After starting the server, poll the health endpoint:

```python
def wait_for_healthy(url: str, timeout: float = 30.0) -> bool:
    """Poll health endpoint until ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(f"{url}/health", timeout=1.0)
            if resp.status_code == 200:
                return True
        except httpx.RequestError:
            pass
        time.sleep(0.5)
    return False
```

If health check fails:

1. Kill the server process
2. Remove PID file
3. Report failure with log tail

## Environment Variables

The script sets all required environment variables before starting the server:

| Variable | Default | Purpose |
|----------|---------|---------|
| `READER_LLM_BACKEND` | `ollama` | LLM provider selection |
| `READER_API_KEY` | (optional) | API authentication key |

No external environment setup is required for basic operation.

## Command Implementations

### REQ-DW-001: `start`

1. Check for stale PID, clean up if found
2. Check if already running, report and exit if so
3. Calculate port from project path
4. Set environment variables
5. Fork server process with stdout/stderr to `.dev/server.log`
6. Write PID to `.dev/server.pid`
7. Wait for health check (30s timeout)
8. Display URL on success, cleanup on failure

### REQ-DW-002: `stop`

1. Check if PID file exists
2. Read PID, verify process exists
3. Send SIGTERM to process group
4. Wait up to 5s for graceful shutdown
5. Send SIGKILL if still running
6. Remove PID file

### REQ-DW-003: `status`

1. Check for stale PID, report and clean up if found
2. If PID file exists and process alive: display "running" with URL
3. Otherwise: display "stopped"

### REQ-DW-004: `restart`

1. Call `stop` (ignore if not running)
2. Call `start`

### REQ-DW-005: `logs`

1. If `-f` flag: `tail -f .dev/server.log`
2. Otherwise: `tail -n 50 .dev/server.log` (or `-n N` if specified)

### REQ-DW-006 through REQ-DW-010: Quality Commands

These delegate to underlying tools:

| Command | Implementation |
|---------|----------------|
| `fmt` | `uv run ruff format src tests` |
| `fmt --check` | `uv run ruff format --check src tests` |
| `lint` | `uv run ruff check src tests` |
| `typecheck` | `uv run mypy src && uv run pyright src` |
| `test` | `uv run pytest tests` |
| `check` | `fmt --check && lint && typecheck` |

### REQ-DW-011: `db-migrate`

1. Ensure database directory exists
2. Run migration logic (apply pending migrations)

### REQ-DW-012: `db-reset`

1. Prompt for confirmation (exit if declined)
2. Stop server if running
3. Delete database file
4. Run migrations

### REQ-DW-013: `clean`

1. Stop server if running
2. Remove `.dev/` directory contents

## Error Handling

All commands follow consistent error reporting:

- Exit code 0 for success
- Exit code 1 for expected failures (server not running, health check failed)
- Exit code 2 for unexpected errors (permission denied, corrupt state)

Errors are printed to stderr with context:

```text
Error: Server failed to start within 30 seconds
Last 10 lines of .dev/server.log:
[log content]
```

## Security Considerations

- PID files are created with 0600 permissions
- Log files may contain sensitive request data; consider rotation
- The script does not expose credentials on the command line
