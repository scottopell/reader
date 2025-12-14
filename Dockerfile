# Multi-stage build for Reader application
# Stage 1: Builder - Install dependencies with uv
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Build dependencies with uv (deterministic, frozen lockfile)
RUN uv sync --frozen --no-dev

# Stage 2: Runtime - Slim image with only runtime dependencies
FROM python:3.13-slim

WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 reader

# Install only runtime dependencies
RUN pip install --no-cache-dir uvicorn[standard]

# Copy virtual environment from builder
COPY --from=builder /app/.venv ./.venv

# Copy source code
COPY src ./src

# Create data directory for database with proper permissions
RUN mkdir -p /data && chown -R reader:reader /data /app

# Switch to non-root user
USER reader

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    READER_DB_PATH=/data/reader.db \
    READER_HOST=0.0.0.0 \
    READER_PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# Start application
CMD ["uvicorn", "reader.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
