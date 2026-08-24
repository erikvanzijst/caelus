## Context

See `proposal.md` § Why for the motivation. What shapes the design:

- **1122 tests**, baseline runtime **~57 s** on SQLite (measured 2026-08-23).
  Two isolation mechanisms exist today: a function-scoped `db_session` fixture
  on `sqlite:///:memory:` + `StaticPool` (31 test files, plus the
  `client` / `user_client` / `paid_client` fixtures that override
  `get_session` to yield it — 26 more), and a `cli_runner` fixture using a
  file-based SQLite database in `tmp_path` with `CAELUS_DATABASE_URL`
  overridden, `get_settings.cache_clear()`, and `importlib.reload(app.db)` +
  `importlib.reload(app.cli)` (9 files). `test_build_cli.py` and
  `test_release_cli.py` additionally open `Session(db.engine)` directly (7 and
  3 sites), following whatever engine the reload produced.
- `DeploymentORM.desired_release_id` and `applied_release_id`
  (`api/app/models/core.py:384-412`) are
  `ForeignKey(..., use_alter=True, deferrable=True, initially="DEFERRED")` and
  NOT NULL. Production inserts the deployment first, naming a release that does
  not yet exist, then the release; the check fires at COMMIT. This single fact
  disqualifies the fastest isolation strategy (see Decisions).
- `api/alembic/__init__.py` exists (empty). Under pytest, `api/` is on
  `sys.path`, so the repo's `alembic/` package **shadows the installed
  `alembic` distribution**. This is why the existing migration tests drive
  Alembic as a subprocess, and any new in-suite migration run must do the same.
- The devcontainer (`.devcontainer/devcontainer.json` → `docker-compose.yml`)
  runs `postgres:16` with `POSTGRES_USER=caelus`, which is a **superuser** in
  that image — so `CREATE DATABASE` and `SET session_replication_role` are both
  available. CI uses `devcontainers/ci@v0.3` with the same spec, so the compose
  Postgres is already running there; proof is that today's `runCmd` executes
  `uv run alembic upgrade head` against `postgres:5432` and passes. Ephemeral
  runners give a pristine server every run.
- `psycopg[binary]` is already a hard dependency of `api/`. SQLAlchemy 2.0.46 /
  SQLModel 0.0.32.
- Eight test files gate on `POSTGRES_TEST_DATABASE_URL` today (the change
  renames it to `CAELUS_TEST_DATABASE_URL`). Three of them
  (`test_migration_advisory_lock.py`, `test_migration_product_visibility.py`,
  `test_migration_deployment_vars.py`) already isolate correctly using
  throwaway schemas via `PGOPTIONS=-csearch_path=…`. The other five
  (`test_deployment_release_postgres.py`, `test_deployment_vars_postgres.py`,
  `test_deployment_vars_model.py`, `test_jobs_service_postgres.py`,
  `test_worker_fork_postgres.py`) open their own engines directly onto the test
  URL and call `init_db()`.

## Goals / Non-Goals

**Goals:**

- A per-test clean slate on a shared PostgreSQL database that is cheap enough
  to keep suite runtime in the **70–90 s** budget.
- Test schema built by the **real migration chain**, so model/migration drift
  becomes a test failure.
- Isolation that works regardless of which engine a component uses — the
  dependency-injected session, `session_scope()`, the CLI's engine, worker
  threads, and forked child processes alike.
- Remove the SQLite branches without touching applied Alembic revisions.

**Non-Goals:**

- `pytest-xdist` support. The design assumes serial execution (true today).
  Parallelizing later means per-worker databases, not a different cleanup —
  see decision 9 for the measured cost and the reason schemas are the wrong
  axis here.
- Teaching the provisioner to handle a null hostname. This change only relaxes
  the column.
- Rewriting the throwaway-schema migration tests. Their pattern already works
  and is the escape hatch if row-level cleanup ever proves insufficient.

## Decisions

### 1. Isolation: session-scoped migrated database + per-test row cleanup

| | A. Rollback-per-test | B. Fresh database per test | **C. Session DB + row cleanup** | D. Per-test schema |
| --- | --- | --- | --- | --- |
| Mechanism | One shared connection, BEGIN/ROLLBACK per test; app commits become savepoint releases | `CREATE DATABASE` + full chain + `DROP` per test | Migrate once per session; empty the tables between tests | `CREATE SCHEMA` + DDL + `DROP SCHEMA CASCADE` per test |
| Cost | Fastest | ~1122 × chain ≈ 15+ min | 1.5 ms per test | ~50–150 ms DDL per test |
| Deferred FK fidelity | **Broken** | Real commits | Real commits | Real commits |

**A is disqualified by this codebase.** PostgreSQL evaluates
`DEFERRABLE INITIALLY DEFERRED` constraints only at transaction end. Under the
savepoint pattern, `session.commit()` in application code becomes a SAVEPOINT
release, so the deferred check on `deployment.desired_release_id` **never
fires** — the exact bug class this change exists to catch would go silently
green. A also requires funneling every connection in the process through one
shared connection, which the `cli_runner` architecture works against.

**B is arithmetic, not judgment.** Rejected on runtime.

**C over D:** D costs 1–2.5 min of extra DDL and needs `search_path` plumbing
on every connection. C is chosen; D remains a known-good fallback if a test
ever needs schema-level freshness, because the migration tests already prove
the pattern works here.

### 2. Cleanup statement: `DELETE`, not `TRUNCATE`

Measured on this schema (13 tables, empty, `postgres:16` from the compose
stack), median per call:

| Strategy | Median | Projected over 1122 tests |
| --- | --- | --- |
| `TRUNCATE … RESTART IDENTITY CASCADE` | 50 ms | ~56 s |
| `TRUNCATE … CASCADE` | 51 ms | ~57 s |
| `TRUNCATE …` with `synchronous_commit=off` | 47 ms | ~53 s |
| **`DELETE FROM …` + `ALTER SEQUENCE … RESTART`** | **1.5 ms** | **~1.7 s** |

TRUNCATE's cost is per-table catalog and relfilenode work, so it does not
shrink because the tables are empty. At ~56 s of pure cleanup on top of the
~57 s baseline it would blow the runtime budget by itself.

DELETE also avoids a failure mode that would bite in CI. TRUNCATE needs ACCESS
EXCLUSIVE, so **a single connection idle in a transaction — even one holding
nothing but ACCESS SHARE from a plain SELECT — blocks it indefinitely**.
Verified with `lock_timeout = 3s` against one leaked reader:

```
TRUNCATE: BLOCKED -> LockNotAvailable: canceling statement due to lock timeout
DELETE  : OK in 1 ms
```

Without a `lock_timeout` that is a hang, not a failure — and leaked readers are
not hypothetical here (see decision 4).

### 3. `session_replication_role = replica` for the cleanup connection

Set on the cleanup connection only, for the duration of the cleanup, and reset
to `origin` afterwards. It suppresses FK triggers, which makes DELETE
order-independent. This is not a convenience: SQLModel's metadata contains an
unresolvable cycle among `plan` / `plan_template_version` / `product` /
`product_template_version`, so `sorted_tables` cannot produce a topological
order at all. It requires superuser — the same privilege `CREATE DATABASE`
already assumes.

The table list is snapshotted once per session from `information_schema`,
**filtered to the `public` schema** (the migration tests leave throwaway
schemas behind in the same database) and **excluding `alembic_version`**, so
migration state survives between tests.

Sequences are enumerated from `pg_sequences` rather than hand-listed:
`deployment_var.id` is `GENERATED ALWAYS AS IDENTITY`, not a serial, and would
be missed by a serial-only list. Restarting them keeps tests that assume small
integer IDs working exactly as they did on a fresh in-memory SQLite.

### 4. Lazy engine in `app/db.py`, replacing the `importlib.reload` ritual

`app/db.py` builds its engine at module import time, which is the only reason
`conftest.py` reloads the module to retarget the CLI at a different database.
Each reload builds a fresh engine and never disposes the previous one, so
undisposed pools accumulate. Today that is invisible because each `cli_runner`
test gets its own SQLite file; it becomes shared state the moment they all
point at one PostgreSQL database — and it is precisely what would have hung a
TRUNCATE-based cleanup.

Replacing the module-level `engine` with a cached `get_engine()` removes the
ritual from `conftest.py`, `test_build_cli.py` and `test_release_cli.py`,
removes the leak at its source, and makes the fixture ordering
comprehensible. Alternative considered: keep the reload and add
`db.engine.dispose()` before each one. Rejected — it patches the symptom and
leaves the fragility in place, and this change is already touching every one of
those call sites.

Callers that today read `db.engine` as a module attribute must move to
`get_engine()`; `session_scope()` and `get_session()` call it internally.

### 5. Alembic runs as a subprocess

The session fixture invokes the `alembic` console script with `cwd=api/` and
`CAELUS_DATABASE_URL` set to the test URL in the subprocess environment. This
is forced, not preferred: `api/alembic/__init__.py` shadows the installed
distribution under pytest, so an in-process `alembic.command.upgrade` import
resolves to the repo package. It is also the pattern the existing migration
tests already use, so there is one way to run migrations from tests.

Bonus: this makes "the chain applies to an empty database from scratch" a
precondition of every test run, which today is only checked against the dev
database in CI.

### 6. Nullability drift: relax `hostname`, tighten `subscription_id`

The drift was verified by applying the chain to an empty PostgreSQL, building a
second database from `SQLModel.metadata.create_all`, and diffing columns,
indexes and constraints. Two columns differ and **nothing else does** — every
other column, index, constraint, partial predicate and deferrable FK matches
exactly.

| Column | Alembic chain | Models | Resolution |
| --- | --- | --- | --- |
| `deployment.hostname` | NOT NULL | nullable | New revision relaxes the column |
| `deployment.subscription_id` | NOT NULL | nullable | Model declaration tightened |

`hostname` goes the models' way because the models are right and the schema is
wrong: `deployment-create-contract` already requires the service to persist
`null` when the desired template declares no hostname-titled field, and
`services/deployments.py:229-233,280` does exactly that — so that path raises
in production today. Relaxing the column fixes a live bug and leaves room for
future headless (ingress-free) apps.

`subscription_id` goes the chain's way because the chain, production, and the
`deployment-subscription-integration` spec all agree it is NOT NULL; only the
model disagrees. Consequence: `make_deployment_with_release` must supply a
subscription. It will build a free plan + subscription when the caller passes
no `subscription_id`, deriving the product from `desired_template_id`, so the
ten existing call sites need no change.

### 7. CI: drop the alembic step, assert against the dev database

`uv run alembic upgrade head` is removed from the `api-test` `runCmd`: it
migrated the dev `caelus` database, which no test reads, and conftest now owns
creating and migrating the test database. Migration-from-scratch coverage moves
to the session fixture and the ungated migration tests.

The consequence needs insurance. With the dev database no longer migrated in
CI, anything that accidentally reaches the default engine hits an *unmigrated*
database and fails obscurely. `app/main.py:_lifespan` (`api/app/main.py:41-52`)
calls `verify_keyring(next(sessions))` on startup and resolves the session
through `app.dependency_overrides`; the `client` fixtures override it, so
`TestClient(app)` under those fixtures is safe — but that holds *because of the
override*, not because startup is inert. Any `TestClient(app)` without the
override would reach the module-level engine. Conftest therefore asserts at
session start that no engine resolves to the dev URL, turning an obscure
failure into a named one.

Readiness ordering is unchanged: conftest's first database contact happens
after `uv sync`, tens of seconds after the postgres container starts — the same
implicit ordering the current alembic step already relies on. A
`pg_isready` loop is not added preemptively.

### 8. Ungated files join the shared database rather than managing their own

The three throwaway-schema migration tests are left alone; they never touch
`public` and coexist with the cleanup by construction (which is why the table
snapshot is schema-filtered). The other five stop calling `init_db()` and stop
building module-scoped engines onto the test URL, moving instead to the session
engine and the shared per-test cleanup. Their unique-token seeding becomes
redundant once each test starts empty, but removing it is not required for
correctness.

`test_worker_fork_postgres.py` is the exception that keeps its own engine: its
subject is what a forked child inherits from the parent's pool, so it must
construct the pool it forks across. It moves to the session URL and disposes
what it creates.

Files are renamed as part of the ungate, since a `_postgres` suffix implies a
dialect choice that no longer exists. `test_jobs_service_postgres.py` merges
into `test_jobs_service.py` rather than being renamed onto an occupied name.

### 9. Parallel execution is deferred, and the path is per-worker databases

Out of scope here (see Non-Goals), but the design should not close the door,
and the escape route is worth recording while the measurements are fresh.
Timed against the compose `postgres:16` on 2026-08-24:

| Operation | Measured |
| --- | --- |
| Full 23-revision chain into an empty database | **0.70 s** |
| `CREATE DATABASE … TEMPLATE <already-migrated>` | **0.039 s** |

So the future shape is: migrate one template database once, then clone it per
worker at ~40 ms. Eight workers cost about a second of setup in total. The
per-test cleanup from decisions 2 and 3 is unchanged — it simply runs against
each worker's own database. In `conftest.py` this is roughly twenty lines: key
the database name off `PYTEST_XDIST_WORKER` (`gw0`, `gw1`, …), and have one
worker migrate the template while the others wait on a `filelock.FileLock`,
since xdist has no session-scoped-once hook. The table and sequence snapshots
need no change.

**Per-worker databases, not per-worker schemas**, for two reasons specific to
this codebase:

- **One knob versus many.** `CAELUS_DATABASE_URL` is already threaded through
  settings into `get_engine()`, the Alembic subprocess environment, and forked
  children, so changing the database name per worker makes every engine follow
  automatically. `search_path` has no equivalent single channel: it would have
  to be set on `get_engine()`'s connect args *and* as `PGOPTIONS` for the
  subprocess *and* on any raw psycopg connection. Missing one silently writes
  into `public` from two workers at once — a failure that presents as
  flakiness rather than as an error.
- **Advisory locks are database-scoped, not schema-scoped.** Under per-worker
  schemas, two workers running migration tests simultaneously would contend on
  the same advisory lock in the same database — cross-worker interference on
  exactly what `test_concurrent_postgres_upgrades_serialize` measures. Separate
  databases make them independent.

Schemas would be preferable only if the suite needed hundreds of parallel slots
(databases are heavier catalog objects) or could not assume `CREATEDB`; neither
applies. Note also that the throwaway-schema migration tests already occupy the
schema axis, so per-worker schemas would nest one scheme inside another.

One implementation gotcha: `CREATE DATABASE … TEMPLATE` requires that **no
other connection** is attached to the template, so the order must be migrate
the template, dispose the pool, then clone.

Finally, a warning for whoever picks this up: the most widely cited SQLAlchemy
testing recipe is "join an external transaction" / rollback-per-test, and it is
much faster than anything above. It is option A in decision 1, and it is
disqualified here — application-level `commit()` becomes a SAVEPOINT release
and the deferred foreign key on `deployment.desired_release_id` never fires.
The popular answer is the wrong one for this codebase.

Doing this later is a spec change as well as a code change: the
`postgres-test-database` requirement "Test execution is serial" would be
MODIFIED, not merely implemented around.

## Risks / Trade-offs

- **Unknown volume of foreign-key breakage** → This is the change's main
  unknown and the reason for a dedicated discovery phase. With FKs suddenly
  enforced and the schema coming from Alembic, every test that inserts orphan
  rows or leans on SQLite's type laxness fails. Each failure is a decision: fix
  the test (likely) or find a real application bug (the prize). The suite going
  red during phase 2 is the point, not a problem. Mitigation: settle the
  nullability drift (decision 6) **before** the discovery run, so its signal is
  not swamped by hand-built-deployment failures that are not test bugs.
- **PostgreSQL type strictness** → Native `uuid` rather than hex strings,
  timezone-aware datetimes, real integer ranges. Expect a handful of
  fixture/helper fixes; they surface in the same discovery run.
- **Relaxing a production NOT NULL constraint** → `deployment.hostname` becomes
  nullable in production. Mitigation: the column has always been populated by
  `create_deployment` when a hostname exists, and the relaxation is what the
  spec already requires; no data migration or backfill is involved, and the
  revision is trivially reversible.
- **`subscription_id` tightening could surface real orphans** → If any
  production deployment row somehow held a NULL, the model change would not
  itself fail (it is a declaration, not a constraint) but would misrepresent
  reality. The chain has enforced NOT NULL since `c3d4e5f6a7b8`, so this cannot
  occur.
- **Shared database means cross-test leakage if cleanup is skipped** → Any test
  that acquires a session without going through the cleaned fixture sees
  whatever the previous test left. Mitigation: the cleanup lives in the fixture
  every database-backed test already depends on, and the dev-URL assertion
  catches the other escape route.
- **Suite runtime grows** → From ~57 s to an expected 70–90 s, within the
  agreed budget. Cleanup contributes ~1.7 s; the rest is real network round
  trips replacing in-process SQLite calls.
- **No parallel execution** → Accepted (see Non-Goals). If the suite later
  outgrows serial runtime, the lever is per-worker databases cloned from a
  migrated template, which this design does not preclude and decision 9 costs
  out at ~40 ms per worker.

## Migration Plan

Phased so that the discovery run has a clean signal:

1. **Plumbing.** Session fixture (create database, subprocess-migrate, snapshot
   `public` tables and `pg_sequences`), per-test cleanup, lazy `get_engine()`,
   `cli_runner` on the test URL, `CAELUS_TEST_DATABASE_URL` in compose,
   `runCmd` cleanup, dev-URL assertion. Nothing deleted yet.
2. **Schema truth.** Land decision 6 — the hostname revision and the
   `subscription_id` model tightening, plus the `make_deployment_with_release`
   subscription default — *before* the discovery run.
3. **Discovery run.** Run the suite; triage every failure as test bug or
   application bug. Expect this to be the bulk of the work.
4. **Ungate and rename** the eight PostgreSQL files; move the five
   direct-engine files onto the session engine.
5. **Delete** the SQLite branches, `sqlite_where` kwargs, `init_db()`, and the
   SQLite-only tests.
6. **Docs and green CI.** `AGENTS.md`, `api/README.md`, compose comments;
   verify the workflow end to end.

**Rollback**: phases 1–4 are test-only and revert cleanly. Phase 2's Alembic
revision has a working `downgrade` (re-adding NOT NULL succeeds because no row
has ever held a NULL). Phase 5 is the only irreversible-in-spirit step and
lands last, after the suite is green.
