FROM bitnami/kubectl AS kubectl
FROM d3fk/helm:latest AS helm

FROM python:3.13-slim
COPY --from=kubectl /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/kubectl
COPY --from=helm /helm /usr/local/bin/helm

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends postgresql-client

RUN pip install uv

RUN mkdir /app
WORKDIR /app
COPY . .
RUN uv sync --no-dev --frozen
RUN uv pip install . --no-deps

EXPOSE 8000

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
