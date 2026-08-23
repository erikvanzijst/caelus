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
- **Two different things are called "the CLI".** `caelus` (`api/app/cli.py`) is
  the *operator* tool: it runs in-process against the database and services, and
  every reference to "CLI" elsewhere in this file means that one. `freepod`
  (`cli/`) is the *end-user client*: a separately installable package that talks
  to a deployed platform over HTTP, imports nothing from `api/`, and shares no
  code with it.
- Provisioning is stubbed in `api/app/provisioner.py` and should be replaced with a K8s implementation.
- Product Templates are scoped to products; deployments are scoped to users.
- **Builds** are a standalone subsystem: a build turns an uploaded project
  archive into a container image and is owned by a **user**. Nothing
  auto-deploys a build — the client submits a successful build's `image` to the
  deployment create/update endpoint itself, and may pass that build's
  `build_id` alongside it. Since `deployment_release`, that `build_id` is
  recorded on the release row, so a build does have an explicit link to a
  deployment; ownership still runs through the user, and
  `_validate_build_reference` checks only that the caller owns the build.
  Nothing currently stops one build being named by releases of *different*
  deployments — an image is technically reusable that way, it is not the
  intended case, and rejecting it is an open item. There are now two
  worker processes: `caelus worker` (reconcile queue) and `caelus build-worker`
  (builds), the latter running each build as a Kubernetes Job in a
  per-environment `caelus-builds*` namespace. Builds are addressed under their
  owner — `/api/users/{user_id}/builds*` — like every other user-owned
  resource; there is no root-level `/api/builds`, and no `user_id` query
  parameter. See `api/README.md` § Builds.
- **Vars are the single channel into a pod's environment.** A deployment's
  `vars` become environment variables in its container;
  `deployment.user_values_json` configures the **chart**, not the process, and
  nothing fans one out into the other. Which channel a property takes is a
  marker on the *one* template schema (`x-caelus-target: chart | runtime`,
  defaulting to `chart`), from which the server derives a chart projection and
  a vars projection — there is no second schema and no second namespace. A var
  marked `x-caelus-sensitive` is write-only: reads omit its `value` entirely,
  for everyone including administrators. Values are encrypted at rest under a
  rotatable keyring that the API and `caelus worker` must both hold; both
  refuse to start when theirs cannot cover what is stored. See
  `api/README.md` § Deployment Vars.
- Products are either **curated** (declared in `products/catalog/<slug>.yaml`,
  reconciled into the database on rollout, and read-only through the API, CLI,
  and admin UI apart from `visibility`) or **non-curated** (database-authored).
  Only `CatalogReconciler` writes `product.curated` and `product.slug`.
  See `api/README.md` § Product Catalog.
- Authentication: All API endpoints require `X-Auth-Request-Email` header
  (injected by oauth2-proxy in production, set by frontend in local dev).
  `GET /api/me` is the session initialization endpoint. CLI uses
  `CAELUS_USER_EMAIL` env var with optional `--as-user` override.

## Quick Start
Each project owns its own `.venv`, which uv resolves from the working
directory. There is no shared environment: run tooling through `uv run` from
the directory it belongs to.

### API (`api/`)
- `cd api/`
- Install deps: `uv sync`
- Run API: `uv run --no-sync uvicorn app.main:app --reload`
- Run CLI: `uv run --no-sync python -m app.cli --help`
- Tests: `uv run --no-sync pytest`
For details, see `api/README.md`.

### Client CLI (`cli/`)
- `cd cli/`
- Install deps: `uv sync`
- Run: `uv run freepod --help`
- Tests: `uv run pytest`
Targets the environment recorded in `.freepod.json` when run from a project,
and `prod` otherwise. `--env dev` overrides both; `FREEPOD_ENV=dev` only moves
the default for directories that hold no project, so it cannot pull a command
away from the environment its project lives on. For details, see
`cli/DEVELOPMENT.md` — the invariants, the platform contracts, and the
reasoning. `cli/README.md` is the package's PyPI landing page, written for end
users; keep internals out of it.

Published to PyPI as `freepod`, on its own release cadence: bump
`__version__` in `cli/src/freepod/__init__.py` — the single source, which
`pyproject.toml` reads through Hatch — and push a `freepod-v*` tag. No commit
to `master` publishes the client. See `cli/DEVELOPMENT.md` § CI and releasing.

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
- `tf/deps/`: Shared singleton dependencies (Keycloak, Echo, monitoring, and
  Garage — the S3 object store at `blob.freepod.eu`). No workspaces;
  single instance shared across all environments.

Both deploy to the same k3s cluster. Deploy `tf/deps/` first, then
`tf/app/`. Each has its own `secrets.auto.tfvars` (gitignored).

For details, see `tf/README.md`, `tf/app/README.md`, `tf/deps/README.md`.

## Conventions
- Keep CLI and REST functionality in lockstep. **Exception**: the `caelus
  catalog` command group (`apply`, `curate`, `lint`) is intentionally CLI-only
  and requires no REST equivalent. These are operator and build tooling rather
  than tenant-facing surface — `apply` is invoked by an init container during
  rollout, and `lint` runs in CI with no database. The write guards they depend
  on live in `api/app/services/`, so REST, CLI, and the admin UI still enforce
  identical rules and no parity gap is introduced.
- Put all DB/ORM logic in `api/app/services/` and call from API + CLI (DRY).
- Use `api/app/db.py:init_db()` to create tables for dev/test.
- Build logs are stored as `bytea`, not text, and served as raw bytes:
  container output is tenant-controlled and may contain invalid UTF-8 or NUL
  bytes, which Postgres `text` cannot store at all. Do not decode it on the
  way in or out.
- Prefer nested routes:
  - Templates under products: `/products/{product_id}/templates`
  - Deployments under users: `/users/{user_id}/deployments`
  - Releases under deployments:
    `/users/{user_id}/deployments/{deployment_id}/releases`, addressed by the
    per-deployment release **number** rather than the `uuid4`
  - Builds under users: `/users/{user_id}/builds`
  - Vars under deployments, by **phase** and key:
    `/users/{user_id}/deployments/{deployment_id}/vars/{phase}[/{key}]`. The
    phase (`runtime`, the only one so far) is a path segment because it is part
    of a var's identity, not a filter over a set — and it is a phase, never an
    environment: a staging app is its own deployment.

## Database & Migrations
- Prod DB: Postgres via `DATABASE_URL`.
- Migrations: Alembic in `api/alembic/` with `alembic.ini`.

## Testing
- API tests use FastAPI `TestClient` with sqlite temp DB.
- CLI tests use `typer.testing.CliRunner`.
- UI uses Vite with Vitest + Testing Library (`cd ui && npm test`).

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
- `UserValuesForm` partitions its submission by each field's `target`:
  chart values through `onChange`, runtime vars through `onVarsChange`. A
  sensitive field renders empty and submits **no entry at all** when untouched
  — an empty string is a real value and would wipe the stored secret.

## Contribution Checklist
- Update or add tests for new behavior.
- Keep API + `caelus` CLI parity (same features and validations).
- When an API contract changes, check whether `freepod` (`cli/`) depends on it.
  It ships on its own cadence, so it must learn values from the platform at
  runtime rather than embedding them — a constant baked into the client is
  wrong the first time the platform retunes it.
- Update migrations for schema changes.
- Update api/README.md, ui/README.md, cli/DEVELOPMENT.md, tf/README.md, and
  AGENTS.md when workflow changes. `cli/README.md` changes only when the
  end-user surface does — it ships to PyPI as the package's landing page.
