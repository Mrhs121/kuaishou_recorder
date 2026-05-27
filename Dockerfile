# ── Stage 1: Build frontend ────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim

# ffmpeg for recording
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# uv for fast dependency install
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cache layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

# Copy application code
COPY kuaishou_recorder.py browser_cookies.py ./
COPY server/ ./server/

# Copy frontend build output
COPY --from=frontend-build /app/frontend/dist ./server/static/

# Create directories for config and recordings
RUN mkdir -p /recordings /root/.kuaishou_recorder

# Default recording save path (can be overridden at runtime)
ENV RECORDER_SAVE_PATH=/recordings

EXPOSE 8000

# Use uv to run, so dependencies from venv are available
CMD ["uv", "run", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
