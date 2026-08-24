## 1. Plumbing: a PostgreSQL test database owned by the suite

- [x] 1.1 Add `CAELUS_TEST_DATABASE_URL=postgresql+psycopg://caelus:caelus@postgres:5432/caelus_test` to the `app` service environment in `docker-compose.yml`; verify by rebuilding the devcontainer and confirming `echo $CAELUS_TEST_DATABASE_URL` prints it inside the container
- [x] 1.2 Add a session-scoped conftest fixture that resolves `CAELUS_TEST_DATABASE_URL`, opens an admin connection with the dbname swapped to `postgres`, and issues an idempotent `CREATE DATABASE` (checking `pg_database` first); verify by dropping `caelus_test` and confirming a bare `pytest -x tests/test_config.py` recreates it
- [x] 1.3 Make that fixture fail fast with a message naming the variable and the expected server when the URL is unset, unreachable, or the user lacks `CREATEDB`; verify by running `CAELUS_TEST_DATABASE_URL= pytest` and confirming the run errors out rather than skipping or passing
- [x] 1.4 Have the fixture run `alembic upgrade head` as a subprocess (console script, `cwd=api/`, `CAELUS_DATABASE_URL` set to the test URL in the subprocess env, per design decision 5); verify by dropping `caelus_test` and confirming a run leaves `alembic_version` at head
- [x] 1.5 Snapshot the table list from `information_schema` filtered to `table_schema='public'` and excluding `alembic_version`, and the sequence list from `pg_sequences`; verify the snapshot contains `deployment_var`'s identity sequence (which is `GENERATED ALWAYS AS IDENTITY`, not a serial)
- [x] 1.6 Assert at session start that no engine the suite will use resolves to the dev `caelus` URL, failing with the offending URL; verify by temporarily pointing `CAELUS_DATABASE_URL` at the dev database and confirming the run aborts with that message

## 2. Plumbing: per-test clean slate

- [x] 2.1 Rework `db_session` into a function-scoped `Session` on a session-scoped engine against the test database, dropping `echo=True`; verify the existing non-DB tests still pass
- [x] 2.2 Implement the cleanup on a dedicated connection: `SET session_replication_role = replica`, `DELETE FROM` each snapshotted table, `ALTER SEQUENCE … RESTART` each snapshotted sequence, `SET session_replication_role = origin`; verify with a two-test file where the first commits rows and the second asserts every table is empty
- [x] 2.3 Verify the cleanup recovers from a failing test: add a temporary test that commits rows then raises, and confirm the next test still starts empty
- [x] 2.4 Verify identity reset: add a temporary test asserting a freshly created product gets `id=1` after a preceding test created several products
- [x] 2.5 Verify the cleanup leaves throwaway schemas alone: run `pytest tests/test_migration_deployment_vars.py tests/test_vars_service.py` together and confirm neither interferes with the other
- [x] 2.6 Time the suite (`pytest --durations=0`) and confirm total runtime lands inside the 70-90 s budget; if cleanup is the outlier, check the snapshot is not picking up non-`public` tables

## 3. Lazy engine, replacing the reload ritual

- [x] 3.1 Replace the module-level `engine` in `api/app/db.py` with a cached `get_engine()`, routing `session_scope()` and `get_session()` through it; verify `uv run --no-sync python -m app.cli --help` and `uvicorn app.main:app` both still start
- [x] 3.2 Update every reader of `db.engine` as a module attribute to call `get_engine()`; verify with `grep -rn "db\.engine" api/` returning no hits outside the tests updated in 3.4
- [x] 3.3 Rewrite `cli_runner` to set `CAELUS_DATABASE_URL` to the test URL and take its clean slate from the shared cleanup, dropping `importlib.reload(app.db)` / `reload(app.cli)` and `get_settings.cache_clear()` where no longer needed; verify `pytest tests/test_build_cli.py tests/test_release_cli.py` passes
- [x] 3.4 Remove the reload dance and the `Session(db.engine)` module-attribute reads from `tests/test_build_cli.py` (7 sites) and `tests/test_release_cli.py` (3 sites); verify both files pass in isolation and in a full run
- [x] 3.5 Confirm no pool leak remains: run the full suite and check `SELECT count(*) FROM pg_stat_activity WHERE datname='caelus_test'` stays bounded rather than growing with the CLI test count

## 4. Schema truth: resolve the model/migration drift

- [x] 4.1 Add an Alembic revision relaxing `deployment.hostname` to nullable, with a working `downgrade` that restores NOT NULL; verify `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` round-trips against a throwaway database
- [x] 4.2 Change `DeploymentORM.subscription_id` (`api/app/models/core.py:527`) to non-optional `int` with `nullable=False`, matching the chain and the `deployment-subscription-integration` spec; verify the session fixture's migrated schema and the model metadata now agree on both columns
- [x] 4.3 Teach `make_deployment_with_release` to build a free plan + subscription (deriving the product from `desired_template_id`) when the caller passes no `subscription_id`; verify all ten existing call sites pass unchanged
- [x] 4.4 Add a test covering the previously-broken path: create a deployment from a template whose schema declares no hostname-titled field and assert it persists with `hostname` null (spec `deployment-create-contract`, requirement "The stored hostname column permits no value")
- [x] 4.5 Add a regression check that the Alembic chain and the model metadata produce the same schema, so future drift fails loudly rather than at the next dialect change; verify it fails when 4.2 is reverted

## 5. Discovery run

- [x] 5.1 Run the full suite against PostgreSQL and capture the failure list; the suite going red here is expected
- [x] 5.2 Triage each failure as test bug or application bug, recording the application bugs separately rather than fixing them silently under a test-cleanup commit
- [x] 5.3 Fix the test-side failures — orphan-row inserts now caught by enforced foreign keys, hand-built ORM rows that should use `make_deployment_with_release`, hex-string UUIDs, naive datetimes, integer-range assumptions; verify the suite reaches green
- [x] 5.4 Report the application bugs found (if any) with a recommendation on whether each is fixed in this change or split out

## 6. Ungate and rename the PostgreSQL test files

- [x] 6.1 Remove the `POSTGRES_TEST_DATABASE_URL` `skipif` marks and now-unneeded env reads from all eight gated files: `test_deployment_release_postgres.py`, `test_jobs_service_postgres.py`, `test_worker_fork_postgres.py`, `test_migration_advisory_lock.py`, `test_migration_product_visibility.py`, `test_deployment_vars_model.py`, `test_deployment_vars_postgres.py`, `test_migration_deployment_vars.py`; verify `pytest --collect-only | grep -c skipped` reports no skips from these files
- [x] 6.2 Move `test_deployment_release_postgres.py`, `test_deployment_vars_postgres.py`, `test_deployment_vars_model.py` and `test_jobs_service_postgres.py` off their module-scoped engines and `init_db()` calls onto the session engine and shared cleanup; verify each passes standalone and in a full run
- [x] 6.3 Point `test_worker_fork_postgres.py` at the session URL while keeping its own engine (its subject is what a fork inherits from a pool) and dispose what it creates; verify it still reproduces the inherited-pool failure for the non-disposing child
- [x] 6.4 Leave the three throwaway-schema migration tests' isolation mechanism unchanged; verify they still create and drop their schemas cleanly alongside the shared cleanup
- [x] 6.5 Rename the ungated files to drop the `_postgres` suffix, merging `test_jobs_service_postgres.py` into `test_jobs_service.py` rather than renaming onto an occupied name; verify the full suite passes and no file name implies a dialect choice

## 7. Delete the SQLite code paths

- [x] 7.1 Delete the `is_sqlite` / `StaticPool` / `check_same_thread` branch from `api/app/db.py` (lines 16-18, 23-25); verify the suite passes and `grep -rn sqlite api/app/` no longer hits `db.py`
- [x] 7.2 Delete `app/db.py:init_db()` and update its two callers-of-record in docs (`AGENTS.md:125`, `api/README.md:1172`); verify `grep -rn init_db api/` returns nothing
- [x] 7.3 Delete `_claim_next_job_sqlite`, `_SQLITE_CLAIMABLE_PREDICATE` and the dialect branch in `claim_next_job` (`api/app/services/jobs.py:196-275`), folding `_claim_next_job_postgres` back into the private claim implementation; verify the ungated concurrent-claim test passes
- [x] 7.4 Delete the SQLite branch of `_claim_next_build` and its UUID-as-hex-string handling (`api/app/build_worker.py:138-159+`); verify the build worker tests pass
- [x] 7.5 Remove all ten `sqlite_where=` kwargs from `api/app/models/core.py` (7), `api/app/models/build.py` (2) and `api/app/models/billing.py` (1), keeping `postgresql_where`; verify `grep -rn sqlite_where api/app/` returns nothing and the partial-index tests still pass
- [x] 7.6 Make the migration advisory lock unconditional in `api/alembic/env.py:78` by removing the `dialect.name == "postgresql"` guard; verify the concurrent-upgrade serialization test passes
- [x] 7.7 Leave `api/alembic/versions/*.py` untouched, including their `sqlite_where=` kwargs; verify with `git diff --stat api/alembic/versions/` showing only the new revision from 4.1

## 8. Delete the SQLite-only tests

- [x] 8.1 Delete `test_sqlite_migrations_run_without_attempting_the_advisory_lock` from `tests/test_migration_advisory_lock.py` plus the `PROBE_REVISION` / `SQL_ECHO_INI` machinery that exists only for it, keeping what the PostgreSQL test still uses; verify the remaining test passes
- [x] 8.2 Delete `test_claim_next_job_uses_sqlite_fallback_and_handles_empty_queue` and the `"(sqlite)"` log assertions and comments from `tests/test_jobs_service.py`; verify the merged PostgreSQL coverage from 6.5 still covers the empty-queue case
- [x] 8.3 Delete `test_partial_indexes_with_sqlite_where_define_postgres_where` (`tests/test_models_constraints.py:305`), whose purpose disappears with the parity requirement; verify the rest of the file passes
- [x] 8.4 Replace the `sqlite:///test.db` payload at `tests/test_config.py:23` with a PostgreSQL URL; verify the config test passes
- [x] 8.5 Delete the stray zero-byte `caelus.db` at the repo root; verify `git status` stays clean (it is already gitignored)

## 9. CI and docs

- [x] 9.1 Drop `uv run alembic upgrade head` from the `api-test` `runCmd` in `.github/workflows/ci.yml`, leaving `cd api && uv sync && uv run pytest -s`; verify the job passes end to end on a pushed branch
- [x] 9.2 Confirm `ui-test`, `catalog-lint`, `cli` and `publish-images` are untouched; verify with `git diff .github/workflows/ci.yml` showing changes only inside `api-test`
- [x] 9.3 Update `AGENTS.md` § Testing ("API tests use FastAPI `TestClient` with sqlite temp DB") and the § Conventions `init_db` line; verify no reference to SQLite remains with `grep -rni sqlite AGENTS.md`
- [x] 9.4 Update `api/README.md`: the § Reconcile Queue Semantics claiming-strategy bullet and `POSTGRES_TEST_DATABASE_URL` conditional wording, and the § Testing section (test database created and migrated by conftest); verify `grep -rni sqlite api/README.md` returns nothing
- [x] 9.5 Document running the suite outside the devcontainer — `docker compose up -d postgres`, set `CAELUS_TEST_DATABASE_URL`, and the `CREATEDB`/superuser requirement — in `api/README.md` and a `docker-compose.yml` comment; verify by following the instructions from a shell outside the container
- [x] 9.6 Run the full suite one final time from a clean state (drop `caelus_test` first) and confirm it is green inside the runtime budget
