# Agent Instructions

This repository is a monorepo with:
- `api/`: FastAPI + SQLModel service with a Typer CLI for provisioning.
- `ui/`: React + TypeScript + MUI frontend for the API.
- `tf/`: Terraform infrastructure for deploying to Kubernetes.

## Project Goals
- Provision user-owned webapp instances on Kubernetes (pods, PVCs, ingress).
- Provide a REST API and CLI that are functionally identical.
- Model products, template versions, users, and deployments with clear ownership.

## Architecture Notes
- API and CLI are thin facades over services in `api/app/services/`.
- Provisioning is stubbed in `api/app/provisioner.py` and should be replaced with a K8s implementation.
- Product Templates are scoped to products; deployments are scoped to users.
- Authentication: All API endpoints require `X-Auth-Request-Email` header
  (injected by oauth2-proxy in production, set by frontend in local dev).
  `GET /api/me` is the session initialization endpoint. CLI uses
  `CAELUS_USER_EMAIL` env var with optional `--as-user` override.

## Quick Start
### API (`api/`)
- `cd api/`
- Install deps: `uv sync`
- Run API: `uv run --no-sync uvicorn app.main:app --reload`
- Run CLI: `uv run --no-sync python -m app.cli --help`
- Tests: `uv run --no-sync pytest`
For details, see `api/README.md`.

### UI (`ui/`)
- `cd ui/`
- Install deps: `npm install`
- Run UI: `npm run dev`
- Build: `npm run build`
For details, see `ui/README.md`.

### Terraform (`tf/`)

The Terraform infrastructure is split into two independent root modules:

- `tf/app/`: Caelus application resources (API, UI, worker, OAuth2-proxy,
  Postgres). Uses Terraform workspaces for dev (`default`) and prod (`prod`)
  environment separation.
- `tf/deps/`: Shared singleton dependencies (Keycloak, Echo). No workspaces;
  single instance shared across all environments.

Both deploy to the same k3s cluster. Deploy `tf/deps/` first, then
`tf/app/`. Each has its own `secrets.auto.tfvars` (gitignored).

For details, see `tf/README.md`, `tf/app/README.md`, `tf/deps/README.md`.

## Conventions
- Keep CLI and REST functionality in lockstep.
- Put all DB/ORM logic in `api/app/services/` and call from API + CLI (DRY).
- Use `api/app/db.py:init_db()` to create tables for dev/test.
- Prefer nested routes:
  - Templates under products: `/products/{product_id}/templates`
  - Deployments under users: `/users/{user_id}/deployments`

## Database & Migrations
- Prod DB: Postgres via `DATABASE_URL`.
- Migrations: Alembic in `api/alembic/` with `alembic.ini`.

## Testing
- API tests use FastAPI `TestClient` with sqlite temp DB.
- CLI tests use `typer.testing.CliRunner`.
- UI uses Vite; no tests are configured yet.

## Quality
- Validate inputs; return stable errors.
- Write tests for all new behavior.
- No secrets in code.

## Commit Messages
- Follow standard Git commit message style:
  - Short imperative subject line, followed by an empty line.
  - Wrap all lines at 78 characters max.
- **Quote the whole command** – wrap the entire `git commit` call in single quotes (or use `-F <file>`).
  ```bash
  git commit -m 'subject line' -m $'body line 1\nbody line 2…'
  ```
- **Escape back‑ticks/quotes** – never place unescaped `` ` `` or " " inside a `-m` argument; use `\\` or `$'…'` quoting.
- **Check exit status** – after `git commit …` verify `$? == 0`; on error abort and report before retrying.
- Explain why and what changed in the body.

## UI Conventions
- Extract React components into focused, single-responsibility files under
  `ui/src/components/`. Avoid inlining complex functionality into page-level
  components (`Dashboard.tsx`, `Admin.tsx`).
- Form field components with specialized behavior (e.g., `HostnameField`)
  should be their own component files, not inlined into the form.
- Schema-driven fields in `UserValuesForm` can be overridden by matching on
  `field.title` (case-insensitive) and rendering a custom component instead
  of the default `<TextField>`.

## Contribution Checklist
- Update or add tests for new behavior.
- Keep API + CLI parity (same features and validations).
- Update migrations for schema changes.
- Update api/README.md, ui/README.md, tf/README.md, and AGENTS.md when
  workflow changes.
