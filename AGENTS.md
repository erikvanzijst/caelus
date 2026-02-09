# Agent Instructions

This repository contains a FastAPI + SQLModel service with a Typer CLI for provisioning.

## Project Goals
- Provision user-owned webapp instances on Kubernetes (pods, PVCs, ingress).
- Provide a REST API and CLI that are functionally identical.
- Model products, template versions, users, and deployments with clear ownership.

## Architecture Notes
- API and CLI are thin facades over services in `app/services/`.
- Provisioning is stubbed in `app/provisioner.py` and should be replaced with a K8s implementation.
- Templates are scoped to products; deployments are scoped to users.

## Quick Start
- Install deps: `uv sync`
- Run API: `uv run --no-sync uvicorn app.main:app --reload`
- Run CLI: `uv run --no-sync python -m app.cli --help`
- Tests: `uv run --no-sync pytest`

## Conventions
- Keep CLI and REST functionality in lockstep.
- Put all DB/ORM logic in `app/services/` and call from API + CLI (DRY).
- Use `app/db.py:init_db()` to create tables for dev/test.
- Prefer nested routes:
  - Templates under products: `/products/{product_id}/templates`
  - Deployments under users: `/users/{user_id}/deployments`

## Database & Migrations
- Dev DB: SQLite via `DATABASE_URL` (default `sqlite:///./caelus.db`).
- Prod DB: Postgres via `DATABASE_URL`.
- Migrations: Alembic in `alembic/` with `alembic.ini`.

## Testing
- API tests use FastAPI `TestClient` with sqlite temp DB.
- CLI tests use `typer.testing.CliRunner`.

## Quality
- Validate inputs; return stable errors.
- No secrets in code.

## Contribution Checklist
- Update or add tests for new behavior.
- Keep API + CLI parity (same features and validations).
- Update migrations for schema changes.
- Update README/AGENTS.md when workflow changes.
