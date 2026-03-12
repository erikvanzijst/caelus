# Outcome: Cancelled

**Date:** 2026-03-12
**Status:** Cancelled — refactor deemed unnecessary after analysis.
**Related commit:** `create_product` endpoint fix using `run_in_threadpool`

## Decision

After thorough re-evaluation of the proposal, design, and codebase, the
convert-to-async change was cancelled. The cost/benefit analysis does not
justify the refactor for Caelus's scale and usage patterns.

## Rationale

### FastAPI already handles sync endpoint concurrency

The key misunderstanding in the original proposal was that sync `def` endpoints
block concurrent request handling. They do not. FastAPI (via Starlette)
automatically dispatches sync `def` endpoint handlers to a **thread pool**
(default 40 threads via `anyio.CapacityLimiter`). This means:

- Each incoming request to a sync endpoint gets its own thread.
- The event loop is never blocked.
- Concurrent requests are handled in parallel without any async code.

This is the standard concurrency model for sync WSGI applications
(Gunicorn/uWSGI with thread workers) and FastAPI preserves it automatically.

### Async conversion would be costly with low payoff

The refactor would require changes across every layer of the stack:

1. **Database layer** (`db.py`): New async engine (`create_async_engine` with
   `asyncpg`), async sessionmaker, async session dependency. Must maintain dual
   sync/async session infrastructure because the CLI remains sync.

2. **Dependency injection** (`deps.py`): `get_current_user()` performs DB
   queries via session and would need full async conversion.

3. **All service modules** (6 files, ~860 lines): Every function becomes
   `async def`, every `session.exec()` becomes
   `await session.execute(select(...))` with different return type semantics
   (Row objects requiring `.scalars().all()` instead of direct model instances).

4. **All API routes** (2 files): Convert to `async def`, add `await` to all
   service calls, switch session dependency.

5. **ORM models** (`models.py`): All SQLModel `Relationship()` fields use
   default lazy loading. Async SQLAlchemy raises `MissingGreenlet` on lazy
   attribute access. Every relationship access path would need auditing and
   explicit `selectinload()` or `lazy="selectin"` configuration.

6. **Test infrastructure** (`conftest.py` + all test files): `TestClient` works
   with sync sessions. Full async testing would require `pytest-asyncio`,
   `httpx.AsyncClient`, `aiosqlite` (not in deps), and rewritten fixtures.

7. **CLI** (`cli.py`, 595 lines): Uses `session_scope()` context manager and
   calls service functions directly. The worker loop is a blocking polling loop
   with `subprocess.run()` calls to kubectl/helm. Would need either:
   - Permanent dual sync/async session infrastructure, or
   - Full async CLI rewrite (unjustifiable — CLI gains nothing from async).

8. **Blocking I/O in services**: `products.py` does file I/O (icon saving),
   `images.py` does CPU-bound PIL processing, `provisioner.py` does
   `subprocess.run()`. All would need `asyncio.to_thread()` wrapping in an
   async context.

### Async only wins at scale we don't need

The async event loop model wins over threading when:

- **Thousands of concurrent connections** — threads carry ~8MB stack overhead
  each; coroutines are ~KB. At 40 concurrent requests, this is irrelevant.
- **High-latency I/O fan-out** — e.g., each request makes 10 parallel external
  API calls. Caelus endpoints do single DB queries.

Caelus is an internal provisioning tool, not a high-traffic public API. The
40-thread pool handles our expected concurrency comfortably. If we ever need
more, running multiple uvicorn worker processes (`--workers N`) is simpler than
an async rewrite.

### What was actually fixed instead

The codebase had exactly **one** concurrency issue: `create_product` in
`api/products.py` was defined as `async def` (needed for `await request.form()`
multipart parsing) but called the sync service function
`product_service.create_product()` directly. This blocked the event loop during
that endpoint's DB and file I/O operations.

Fix applied: wrap the blocking call in `run_in_threadpool()` from
`starlette.concurrency`. This is the same mechanism FastAPI uses internally for
sync `def` endpoints. The endpoint remains `async def` for the form parsing,
and the blocking work runs safely in a thread.

```python
product = await run_in_threadpool(
    product_service.create_product, session, payload, icon_data
)
```

### Previous implementation attempt

A prior attempt to implement this change was abandoned without successful
outcome, which prompted this re-evaluation. The breadcrumbs of that attempt
remain in `db.py` (an unused `async_sessionmaker` import) and `pyproject.toml`
(an unused `asyncpg` dependency).

## If this comes back up

Before reopening this change, the following conditions should all be true:

1. **Measured bottleneck**: Profiling shows that thread pool exhaustion under
   real load is causing request queuing or timeouts.
2. **Scale justification**: Expected concurrent connections exceed what
   `--workers N` can handle cost-effectively.
3. **CLI separation**: The CLI/worker has been separated into its own process
   or package, eliminating the dual sync/async session maintenance burden.
4. **SQLModel async maturity**: SQLModel's async support
   (`sqlmodel.ext.asyncio`) has stabilized with clear documentation and
   community adoption patterns.

Without these, the simpler path is to increase `--workers` or add a reverse
proxy load balancer in front of multiple uvicorn instances.
