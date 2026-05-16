# ==========================================
# Stage 1: Build
# ==========================================
# Use standard Python from Docker Hub instead of astral-sh/uv from GHCR
FROM python:3.13-slim AS build
WORKDIR /app

# Install uv using pip to bypass ghcr.io timeout issues
RUN pip install --no-cache-dir uv

# Force uv to use the system's Python 3.13 and compile bytecode directly
ENV UV_PYTHON=python3.13
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