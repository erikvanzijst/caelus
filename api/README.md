# Caelus API: Agent Onboarding Guide

This document is for engineers and coding agents who need to become productive in
this API codebase quickly.

## What This Project Is

`api/` is the control plane for provisioning user-owned web app instances on
Kubernetes.

It exposes two interfaces over the same business logic:
- FastAPI REST endpoints (`app/api/*.py`)
- Typer CLI commands (`app/cli.py`)

Core design rule: API and CLI are functionally equivalent for product/user/template/
deployment lifecycle operations. Both call the same service layer.

## Design Goals

- Keep API and CLI behavior in lockstep.
- Keep HTTP/CLI layers thin; put domain logic in `app/services/`.
- Treat database as source of truth for desired deployment state.
- Reconcile desired state to platform state through a queue-driven workflow.
- Enforce ownership boundaries: templates are scoped under products.
- Enforce ownership boundaries: deployments are scoped under users.

## Codebase Map

- `app/main.py`: FastAPI app wiring, routers, exception handlers.
- `app/cli.py`: Typer CLI commands; mirrors REST operations.
- `app/models.py`: SQLModel ORM + API read/write models.
- `app/db.py`: engine/session helpers and DB init.
- `app/api/`: REST route handlers.
- `app/services/`: domain services (single source of behavior).
- `app/services/reconcile.py`: deployment reconciliation orchestration.
- `app/services/jobs.py`: reconcile job queue operations.
- `app/provisioner.py`: Kubernetes/Helm adapter facade.
- `app/proc.py`: subprocess runner wrapper + command error normalization.
- `alembic/`: database migration history.
- `tests/`: API, CLI, service, and adapter tests.

## Authentication

All API endpoints (except `/api/docs` and `/api/static`) require
authentication via the `X-Auth-Request-Email` header. Endpoints return
`404` when the header is absent.

### How it works

- In production, Traefik routes requests through oauth2-proxy, which
  injects `X-Auth-Request-Email` after Keycloak authentication.
- In local development, the frontend sets this header from localStorage
  after the user enters their email in the dialog.
- The backend trusts the header unconditionally — behavior is identical
  regardless of header source.

### GET /api/me

Session initialization endpoint. Returns the authenticated user or `404`.

- If the email matches an existing user: returns `200` with `UserRead`.
- If the email is new: auto-creates a user record, returns `200`.
- If no header: returns `404`.
- Email matching is case-insensitive.

### FastAPI dependency: `get_current_user`

Defined in `app/deps.py`. Resolves `X-Auth-Request-Email` to a `UserORM`
with auto-creation. Injected into all endpoint functions via
`Depends(get_current_user)`.

### CLI authentication

The CLI authenticates via the `CAELUS_USER_EMAIL` environment variable.
An optional `--as-user` flag overrides the env var:

```bash
# Via environment variable
export CAELUS_USER_EMAIL=alice@example.com
caelus list-users

# Via flag (overrides env var)
caelus --as-user bob@example.com list-users
```

Commands that require user context exit with code 1 and a clear error
when neither is configured.

## Request Flow (How Work Actually Moves)

1. API or CLI receives a command.
2. Facade calls a service in `app/services/`.
3. Service validates input and persists desired state.
4. For deployment-changing operations, service enqueues a reconcile job.
5. Reconciler applies/deletes resources via provisioner adapters.
6. Deployment status and reconcile metadata are persisted back to DB.

## API and CLI Parity

Parity is achieved by sharing service functions, not by duplicating logic.

REST routes:
- Products: `POST/GET /products`, `GET/PUT/DELETE /products/{product_id}`
- Templates: `POST/GET /products/{product_id}/templates`,
  `GET/DELETE /products/{product_id}/templates/{template_id}`
- Users: `POST/GET /users`, `GET/DELETE /users/{user_id}`
- Deployments: `POST/GET /users/{user_id}/deployments`,
  `GET/PUT/DELETE /users/{user_id}/deployments/{deployment_id}`
- Admin: `GET /deployments` (admin-only, all non-deleted deployments)

CLI equivalents (`caelus ...`):
- `create-user`, `list-users`, `get-user`, `delete-user`
- `create-product`, `list-products`, `get-product`, `update-product`, `delete-product`
- `create-template`, `list-templates`, `get-template`, `delete-template`
- `create-deployment`, `list-deployments`, `get-deployment`,
  `update-deployment`, `delete-deployment`
- `reconcile` (CLI-only operational command to run one reconcile pass)

Example:

```bash
caelus --help
caelus create-user alice@example.com
```

CLI output contract:
- Successful command output on stdout is YAML-encoded entity payloads (single
  object or list, mirroring REST JSON responses).
- Logs and errors are emitted on stderr.

**yq filtering tip**

The CLI prints YAML‑encoded entities to stdout. You can pipe that output through `yq` to extract only the fields you care about.
For example:

```bash
caelus list-deployments | yq -y '.[] | {id, domainname, status}'
id: 1
domainname: hello3.app.deprutser.be
status: deleted
---
id: 2
domainname: test3.example.com
status: deleting
```

This works for any `caelus` command that returns a YAML list or object.

## Product Icon and Static File Serving

### Static File Endpoint
- `GET /api/static/{path}` serves files from `STATIC_PATH` (configurable via `STATIC_PATH` env var, defaults to `./static`).
- Path traversal outside `STATIC_PATH` is blocked.
- Responses include `ETag` headers and support `If-None-Match` for `304 Not Modified`.
- Public access (no auth required).

### Product Icon Workflow
- **Create with icon**: `POST /api/products` accepts multipart form with:
  - `payload`: JSON object with product data (`name`, `description`, `template_id`)
  - `icon`: optional image file
- Atomic create: if icon processing fails, no product is persisted.
- Icon processing: decode, normalize orientation, center-crop to square, downscale to max 256x256, output PNG.
- Icon size limit: 10MB max.
- Resolution limit: 2048x2048 max source dimensions.
- Icon files are immutable and content-addressed: uploads are stored as content-hash files, and existing files remain.

### Icon Endpoints
- `PUT /api/products/{product_id}/icon`: Upload/replace icon for existing product.
- `GET /api/products/{product_id}/icon`: Returns `302` redirect to `/api/static/{rel_icon_path}` or `404` if no icon.

### Configuration
- `STATIC_PATH`: Root directory for static files (default: `./static` in dev, `/var/static` in production).
- Static files are served at `/api/static`.

## Core Data Model

### User

- Identity: `email` (unique among non-deleted users).
- Soft deletion: `deleted_at`.
- Role: `is_admin` exists in schema (policy hooks for future use).

### Product

- Represents an application family (e.g. Nextcloud).
- Fields: `name` (active-unique), `description`, optional canonical `template_id`, optional `icon_url`.
- Owns many template versions.
- Icon support: Products can have an icon uploaded. The icon is stored as an immutable file in `STATIC_PATH/icons/` with a content-hash filename. The API exposes `icon_url` (absolute path like `/api/static/icons/<sha1>.png`) in read responses but does not expose the internal `rel_icon_path` field.

### ProductTemplateVersion

- Scoped to one product.
- Chart identity: `chart_ref`, `chart_version`, optional immutable `chart_digest`.
- Values contract includes `system_values_json`.
- Values contract includes `values_schema_json`.
- Values contract includes `capabilities_json`.
- Soft deletion via `deleted_at`.

### Deployment

- Scoped to one user.
- Points to desired template (`desired_template_id`) and last applied template
  (`applied_template_id`).
- Stable runtime identity: `name` (Helm release name, max 27 chars) and
  `namespace` (K8s namespace, max 30 chars), both DNS-label-safe.
- User values are stored in `user_values_json`.
- Tracks workflow metadata: `status`, `generation`, `last_error`,
  `last_reconcile_at`, `deleted_at`.

### DeploymentReconcileJob

- Queue item for reconciliation work.
- Lifecycle: `queued -> running -> done|failed`.
- Reasons: `create|update|delete`.
- Unique partial index prevents multiple open jobs (`queued` or `running`) per
  deployment.

## Critical Invariants

- Active user emails are unique (`deleted_at IS NULL` scoped uniqueness).
- Active product names are unique (`deleted_at IS NULL` scoped uniqueness).
- Active template `(chart_ref, chart_version, product_id)` combinations are
  unique.
- Only one open reconcile job (`queued` or `running`) may exist per deployment.
- Hostnames are unique and case-insensitive for deployments that are not in `deleted` status.
  Hostnames are normalized to lowercase on storage, and uniqueness is enforced via a
  functional index on `LOWER(hostname)`.
- Deployment identity requires DNS-safe `name` (max 27 chars) and `namespace`
  (max 30 chars). Active deployments have a unique `(namespace, name)` pair.
- Kubernetes namespace is `deployment.namespace`; Helm release name is
  `deployment.name`.

## Deployment Lifecycle and State Transitions

### Create

- `create_deployment()` validates user + template + user values.
- REST/CLI create payloads do not accept top-level `hostname`.
- Service derives persisted `hostname` from `user_values_json` by recursively
  scanning template `values_schema_json` for the first field whose `title`
  matches `hostname` case-insensitively.
- Hostnames are normalized to lowercase before validation and storage.
- Generates `name` from product name + random suffix, and `namespace` from
  user email + random suffix.
- Persists deployment with status `provisioning`.
- Enqueues job with reason `create`.

### Update (Upgrade)

- Only allows forward template changes (`desired_template_id` must increase).
- Allowed from `ready` or `error` status (not during `provisioning` or `deleting`).
- Requires same product lineage between current and target template.
- REST/CLI update inputs do not accept top-level `hostname`.
- Service re-derives persisted `hostname` from effective
  `user_values_json` using the same recursive schema-title rule as create.
- Hostnames are normalized to lowercase before validation and storage.
- Revalidates values against target schema.
- Sets status `provisioning`, increments `generation`, enqueues `update` job.

### Delete

- Marks status `deleting`, sets `deleted_at`, increments `generation`.
- Enqueues `delete` job.
- Repeated delete is idempotent if already `deleting`/`deleted`.
- `GET` on a deleted deployment returns `404`.

### Reconcile Outcome

- Apply path: ensure namespace, `helm upgrade --install` -> status `ready` and
  `applied_template_id = desired_template_id`.
- Delete path: `helm uninstall`, delete namespace -> status `deleted`.
- Failure path: catches exception, stores status `error` and `last_error`.

## Reconcile Queue Semantics

- Enqueue runs inside same transaction as deployment mutation.
- Claiming strategy on Postgres uses `FOR UPDATE SKIP LOCKED`.
- Claiming strategy on SQLite uses `UPDATE ... RETURNING` fallback.
- Guarantees no double claim for same job under parallel workers (covered by
  tests, including Postgres integration test when `POSTGRES_TEST_DATABASE_URL`
  is set).

## Provisioning Boundary

`app/provisioner.py` is the boundary to external systems.

- `KubeAdapter`: namespace existence/create/delete via `kubectl`.
- `HelmAdapter`: install/upgrade/uninstall/status via `helm`.
- `Provisioner`: facade used by reconciler.

Important:
- Command execution is centralized in `app/proc.py`.
- Adapter errors are normalized into `AdapterCommandError` with truncated detail.

## Values and Schema Rules

User-editable values are intentionally scoped under `values.user.*`.

Rules enforced by `app/services/template_values.py`:
- `user_values_json` must be an object.
- If user values are provided, template schema must define `properties.user`.
- Final Helm values are merged as `defaults` + `{ "user": user_values }` +
  `system_overrides`.
- Final merged object is validated against full template schema.

## Error Handling

Domain exceptions live in `app/services/errors.py`:
- `IntegrityException` -> HTTP 409
- `DeploymentInProgressException` -> HTTP 409
- `NotFoundException` -> HTTP 404

FastAPI exception mapping is registered in `app/api/utils.py`.
CLI catches domain exceptions and exits with code `1`.

## Logging

- Shared logging setup: `app/logging_config.py`.
- Configured at API and CLI entrypoints.
- Colorized levels on TTY (disabled if `NO_COLOR` is set).
- Level control via `CAELUS_LOG_LEVEL` (default `INFO`).
- High-signal logs cover external commands and provisioning actions.
- High-signal logs cover reconcile start/fail/finish.
- High-signal logs cover job queue operations.
- High-signal logs cover deployment mutation side effects.

## Local Development

From `api/`:

- Install deps: `uv sync`
- Run API: `uvicorn app.main:app --host 0.0.0.0 --reload`
- Run CLI help: `caelus --help`
- Run tests: `pytest`

Docs UI:
- `GET /` redirects to `/docs`.

## Database and Migrations

- Runtime DB URL: `DATABASE_URL` (defaults to local SQLite file).
- Create tables for dev/test: `app.db.init_db(engine)`.
- Alembic config: `alembic.ini`, scripts in `alembic/versions/`.

Migration commands:
- New migration: `alembic revision --autogenerate -m "message"`
- Upgrade DB: `alembic upgrade head`

### Migration Runbook

Before applying migrations in production:

1. **Check for conflicts**: Some migrations include pre-flight checks that detect
   data conflicts (e.g., case-only duplicate hostnames). Review migration output
   for warnings.

2. **Backup**: Ensure database backups are current before running migrations.

3. **Apply in order**: Migrations are sequential. Run `alembic upgrade head` to
   apply all pending migrations.

4. **Verify**: After migration, verify application health and run smoke tests.

5. **Rollback**: If issues occur, `alembic downgrade -1` reverses the last migration.
   Test rollback procedures in staging before production deployment.

## Testing Strategy

- `tests/test_api.py`: REST behavior and validation.
- `tests/test_cli.py`: CLI parity and error handling.
- `tests/test_deployments.py`: deployment mutation semantics.
- `tests/test_reconcile_service.py`: reconcile state transitions.
- `tests/test_jobs_service.py`: queue/claim/mark semantics.
- `tests/test_jobs_service_postgres.py`: concurrent claim behavior on Postgres.
- `tests/test_platform_adapters.py`: Kubernetes/Helm adapter behavior.

## Conventions for Contributors

- Keep API + CLI features in parity.
- Put business logic in `app/services/`; keep facades thin.
- Add/adjust tests for any behavior change.
- Keep ownership scopes explicit in routes and queries.
- Prefer stable domain errors over ad hoc exceptions.
- Update migrations when schema changes.

## Known Gaps and Current TODOs

- Namespace lifecycle is still exposed on `Provisioner`; intended direction is to
  make install/uninstall manage namespaces transparently.
- API create-deployment route has a TODO note to tighten product/template scope
  validation at facade level (service already validates template existence).
- Test setup currently uses file-backed SQLite in `tests/conftest.py`.

## First 30 Minutes for a New Agent

1. Read `app/models.py` to understand entities and constraints.
2. Read `app/services/deployments.py`, `jobs.py`, `reconcile.py` in that order.
3. Skim `app/provisioner.py` and `app/proc.py` for external-system behavior.
4. Run `pytest` and inspect failing tests if any.
5. For feature work, implement in services first, then expose in both API and CLI.
