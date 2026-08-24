## Why

Caelus has carried Postgres/SQLite dual-dialect support since the project
started, but **only the test suite still uses SQLite**. Production has always
run Postgres and local dev moved to Postgres with the devcontainer compose
stack. The compatibility is now a liability rather than a feature:

- **SQLite enforces no foreign keys at all here** (`app/db.py` never sets
  `PRAGMA foreign_keys=ON`), so insert-order mistakes, dangling pointers, and
  missing constraints pass the suite green and fail in production.
- The **deferred** FK checks that make the deployment/release ledger work
  (`DEFERRABLE INITIALLY DEFERRED`) only mean anything on Postgres — the check
  fires at COMMIT.
- `FOR UPDATE SKIP LOCKED` job claiming, migration advisory locks, forked
  worker connection handling, and the deployment-vars constraints each needed a
  separate `*_postgres.py` test file. Eight such files gate on
  `POSTGRES_TEST_DATABASE_URL`, which **is never set in CI** — so today the
  team's Postgres coverage is silently skipped on every run.
- The test schema comes from `SQLModel.metadata.create_all`, not Alembic, so
  nothing verifies that the migration chain matches the models or applies from
  scratch.

That last gap is already hiding a **live production bug**. The
`deployment-create-contract` capability requires the service to persist
`DeploymentORM.hostname` as `null` when the desired template has no
hostname-titled field, and `services/deployments.py:229-233,280` does exactly
that — but the Alembic chain created `deployment.hostname` NOT NULL
(`10fb17efd947_init.py:106`), so in production that path raises. The suite
cannot catch it because the models declare the column nullable and the test
schema is built from the models. The same drift exists on
`deployment.subscription_id`, in the other direction: the chain and the
`deployment-subscription-integration` spec both say NOT NULL, the model says
nullable.

## What Changes

- **BREAKING (developer-facing):** SQLite is no longer a supported database for
  Caelus. `pytest` requires a reachable Postgres; there is no non-Postgres mode
  and no skip path — the session fixture fails fast with a clear message when
  `POSTGRES_TEST_DATABASE_URL` is unset or unreachable.
- **Test suite runs on Postgres.** `conftest.py` creates the test database
  itself (idempotent `CREATE DATABASE`), migrates it once per session with the
  **real Alembic chain** (as a subprocess — `api/alembic/` shadows the
  installed `alembic` package under pytest), and gives each test a clean slate
  with `session_replication_role = replica` + `DELETE FROM` + sequence restart.
  Measured at ~1.5 ms per test versus ~50 ms for `TRUNCATE`.
- **Migration-from-scratch becomes a hard failure.** Because the test schema
  now comes from Alembic, any model/migration drift breaks the suite instead of
  passing silently.
- **Fix the two drifted columns.** A new revision relaxes
  `deployment.hostname` to nullable (aligning production with the
  already-specified null-hostname path, and leaving room for future headless
  apps with no ingress); `DeploymentORM.subscription_id` becomes non-optional
  in the model, matching the chain and the existing spec.
- **Delete the SQLite code paths**: the `is_sqlite`/`StaticPool` branch in
  `app/db.py`, `_claim_next_job_sqlite` and its dialect branch in
  `services/jobs.py`, the SQLite branch of `_claim_next_build` in
  `build_worker.py`, all ten `sqlite_where=` kwargs across `models/core.py`,
  `models/billing.py` and `models/build.py`, and the
  `dialect.name == "postgresql"` guard in `alembic/env.py`. Historical Alembic
  revisions are **not** edited.
- **Make `app/db.py`'s engine lazy** (`get_engine()` with a cache), removing the
  `importlib.reload(app.db)` / `reload(app.cli)` ritual from `conftest.py`,
  `test_build_cli.py` and `test_release_cli.py` and, with it, the undisposed
  connection-pool leak that ritual creates.
- **Ungate and rename the eight Postgres test files**, folding the
  `_postgres` suffix away now that no dialect choice exists. The four that open
  their own engines onto the test URL and call `init_db()` move onto the shared
  session engine.
- **Delete `app/db.py:init_db()`** — with the schema coming from Alembic
  nothing legitimately needs `create_all`, and its docstring already lies about
  importing models.
- **Delete the SQLite-only tests**: the advisory-lock SQLite probe, the jobs
  SQLite-fallback test, and the sqlite/postgres index-parity test.
- **CI**: one env line added to `docker-compose.yml`; `uv run alembic upgrade
  head` dropped from the `api-test` `runCmd` (it migrated a dev database no
  test reads), with conftest asserting that no engine resolves to the dev URL.
  No new service, secret, image, or dependency — `psycopg[binary]` is already
  required and the compose Postgres already runs in CI.

## Capabilities

### New Capabilities
- `postgres-only-persistence`: Postgres is the sole supported dialect. Job and
  build claiming use `FOR UPDATE SKIP LOCKED` unconditionally, partial indexes
  declare only `postgresql_where`, and the migration advisory lock is taken
  unconditionally.
- `postgres-test-database`: the contract for how the test suite obtains its
  database — created and Alembic-migrated once per session, cleaned per test at
  row level, fail-fast when no Postgres is reachable, never pointed at the dev
  database.

### Modified Capabilities
- `cross-database-partial-index-parity`: the requirement that partial unique
  index declarations carry **both** `sqlite_where` and `postgresql_where` is
  removed and replaced with a Postgres-only predicate requirement. The
  capability's three dialect-neutral requirements (status-based deployment
  uniqueness, duplicate template versions permitted, curated migration
  contents) are unchanged.
- `deployment-create-contract`: adds the schema-level requirement that
  `deployment.hostname` permits NULL, closing the contradiction with the
  existing "template schema has no hostname-titled field → persist `null`"
  scenario.

## Impact

**Application code** — `api/app/db.py` (SQLite branch removed, engine made
lazy, `init_db()` deleted), `api/app/services/jobs.py` (~75 lines of SQLite
claim SQL removed), `api/app/build_worker.py` (SQLite claim branch and its
UUID-as-hex handling), `api/app/models/core.py` / `billing.py` / `build.py`
(ten `sqlite_where=` kwargs; two column nullability declarations),
`api/alembic/env.py` (unconditional advisory lock).

**Schema** — one new Alembic revision relaxing `deployment.hostname` to
nullable. No data migration; `create_deployment` has always populated it when a
hostname exists.

**Tests** — `tests/conftest.py` reworked (session engine + cleanup fixtures);
eight gated files ungated and renamed, four of them re-pointed at the session
engine; three SQLite-only tests deleted; `tests/test_config.py:23`'s
`sqlite:///test.db` payload swapped for a Postgres URL. Every test that
hand-builds a `DeploymentORM` now runs under enforced foreign keys — the
volume of resulting breakage is the change's main unknown.

**CI / environment** — `docker-compose.yml` gains
`POSTGRES_TEST_DATABASE_URL`; `.github/workflows/ci.yml` `api-test` loses its
alembic step. `ui-test`, `catalog-lint`, `cli` and `publish-images` are
untouched. Contributors running outside the devcontainer need a reachable
Postgres whose user holds `CREATEDB`.

**Docs** — `AGENTS.md` (§Testing, §Conventions `init_db` line),
`api/README.md` (§Reconcile Queue Semantics claiming strategy, §Testing,
quickstart), `docker-compose.yml` comments.

**Dependencies** — none added or removed.

**Not in scope** — headless (ingress-free) deployments: this change only makes
the column nullable, it does not teach the provisioner to skip ingress.
Parallel test execution (`pytest-xdist`) remains unsupported; the shared test
database assumes serial execution, and parallelizing later means per-worker
databases.
