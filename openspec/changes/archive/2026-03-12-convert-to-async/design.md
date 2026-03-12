## Context

The API is built on FastAPI which supports async request handlers natively. However, the current implementation uses synchronous functions throughout:
- API endpoints are `def` functions (not `async def`)
- Service layer uses synchronous SQLModel queries (`session.exec(select(...))`)
- Database session is obtained via sync generator `get_session()`

This means each request blocks an event loop thread while waiting for database I/O, limiting concurrent request throughput.

## Goals / Non-Goals

**Goals:**
- Convert all API endpoints to async handlers
- Convert all service layer functions to async with async database queries
- Ensure no breaking changes to external API contracts
- Maintain CLI functionality

**Non-Goals:**
- Change database schema or data model
- Add new API endpoints or capabilities
- Switch database backends (Postgres remains)
- Implement connection pooling optimizations (deferred)

## Decisions

### 1. Use SQLModel async support over raw SQLAlchemy async

**Decision:** Use SQLModel's async capabilities (via `AsyncSession` and async engine)

**Rationale:** The codebase already uses SQLModel. SQLModel has async support in recent versions via `sqlmodel.ext.asyncio`. Using raw SQLAlchemy async would require more refactoring.

**Alternatives considered:**
- Raw SQLAlchemy async: Would require converting all ORM models and queries, more invasive
- Keep sync: Does not achieve performance goals

### 2. Dual sync/async session support during transition

**Decision:** Maintain both sync and async session mechanisms during migration

**Rationale:** 
- CLI currently uses sync sessions
- Allows incremental migration
- Easy rollback if issues arise

**Alternatives considered:**
- Full async-only: Would require comprehensive CLI refactoring
- Feature flag: Adds complexity for temporary need

### 3. Async queries via `session.execute()` with `select()`

**Decision:** Use `await session.execute(select(...))` pattern for async queries

**Rationale:** SQLModel's async support uses this pattern. It's well-documented and consistent with SQLAlchemy async.

**Alternatives considered:**
- SQLModel async session methods: Less documentation, less stable
- Raw SQL: Loses ORM benefits

### 4. Keep same endpoint signatures and response models

**Decision:** No changes to request/response schemas

**Rationale:** External API should remain identical. Only internal implementation changes.

## Risks / Trade-offs

**[Risk]** Async session lifecycle management complexity
→ **Mitigation:** Use FastAPI's `AsyncSession` dependency injection pattern which handles cleanup automatically

**[Risk]** Performance regression if async is not properly awaited
→ **Mitigation:** Type hints and code review; run existing tests to verify

**[Risk]** CLI breaks during transition
→ **Mitigation:** Keep sync session support; use `run_sync` or sync wrappers where needed

**[Risk]** Existing tests rely on sync session
→ **Mitigation:** Update test fixtures to use async sessions; ensure tests pass in async mode

## Migration Plan

1. **Phase 1: Infrastructure** (db.py, deps.py)
   - Add async engine and async sessionmaker
   - Add `get_async_session()` dependency
   - Keep existing sync infrastructure

2. **Phase 2: Service layer** (services/*.py)
   - Convert each service module to async
   - Use `await session.execute(select(...))` 
   - Test each service independently

3. **Phase 3: API layer** (api/*.py)
   - Convert `def` to `async def` endpoints
   - Use `await` for service calls
   - Verify endpoints work via curl/tests

4. **Phase 4: CLI and cleanup**
   - Update CLI to work with async services (sync wrappers or async-native)
   - Remove sync code if no longer needed
   - Full integration testing

**Rollback:** Revert to sync functions; async changes are internal only.
