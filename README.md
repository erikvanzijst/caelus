# Caelus

Cloud provisioning tool with FastAPI + SQLModel + Alembic and a Typer CLI.

## Local dev
- Set `DATABASE_URL` (defaults to sqlite `./caelus.db`).
- Run API: `uvicorn app.main:app --reload`
- Run CLI (uv-managed venv): `uv run python -m app.cli --help`
