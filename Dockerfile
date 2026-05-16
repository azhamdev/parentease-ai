# Stage 1: Build
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY . .
# Compile .py untuk performa
RUN uv run python -m compileall .

# Stage 2: Runtime
FROM python:3.12-slim
WORKDIR /app

# Copy virtualenv dari build stage
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app .

# Buat user non-root
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD uv run python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]