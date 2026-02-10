#!/usr/bin/env bash
set -e
# Ensure dependencies are up to date (no‑dev packages)
uv sync --no-dev
# Run the FastAPI app
exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000
