FROM python:3.11-slim AS builder

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock .
RUN uv sync --no-dev --frozen

FROM python:3.11-slim

RUN pip install uv && \
    useradd -m -u 1000 appuser

WORKDIR /app

COPY --from=builder /app/.venv .venv
COPY app/ app/

ENV PATH="/app/.venv/bin:$PATH"
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/docs')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
