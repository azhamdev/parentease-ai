# ==========================================
# Stage 1: Build
# ==========================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app

# Force uv to use the system's Python 3.12 and compile bytecode directly
ENV UV_PYTHON=python3.12
ENV UV_COMPILE_BYTECODE=1

# Install system dependencies required to compile native extensions (like tokie/chonkie)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first to leverage Docker caching
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# Copy the rest of the application source code
COPY . .

# Compile .py files for performance optimization
RUN uv run python -m compileall .

# ==========================================
# Stage 2: Runtime
# ==========================================
FROM python:3.12-slim
WORKDIR /app

# Add the virtual environment's bin directory to the PATH.
# This eliminates the need to install or run 'uv' in the production image.
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Copy virtualenv and compiled application from the build stage
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app /app

# Create a secure non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

# Healthcheck updated to use the system python directly via the activated venv path
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

# Run uvicorn directly out of the copied virtual environment
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]