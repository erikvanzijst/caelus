## 1. Database Infrastructure

- [ ] 1.1 Add async engine using `create_async_engine` in `app/db.py`
- [ ] 1.2 Add `async_sessionmaker` for AsyncSession creation in `app/db.py`
- [ ] 1.3 Add `get_async_session()` async generator dependency in `app/db.py`
- [ ] 1.4 Keep existing sync engine and `get_session()` for CLI compatibility

## 2. Service Layer - Products

- [ ] 2.1 Convert `app/services/products.py` to async functions
- [ ] 2.2 Update `session.exec(select(...))` to `await session.execute(select(...))`
- [ ] 2.3 Update `session.commit()` to `await session.commit()`
- [ ] 2.4 Update `session.refresh()` to `await session.refresh()`

## 3. Service Layer - Templates

- [ ] 3.1 Convert `app/services/templates.py` to async functions
- [ ] 3.2 Update all database operations to async patterns

## 4. Service Layer - Users

- [ ] 4.1 Convert `app/services/users.py` to async functions
- [ ] 4.2 Update all database operations to async patterns

## 5. Service Layer - Deployments

- [ ] 5.1 Convert `app/services/deployments.py` to async functions
- [ ] 5.2 Update all database operations to async patterns

## 6. Service Layer - Jobs

- [ ] 6.1 Convert `app/services/jobs.py` to async functions
- [ ] 6.2 Update all database operations to async patterns

## 7. API Layer - Products

- [ ] 7.1 Convert `app/api/products.py` endpoints from `def` to `async def`
- [ ] 7.2 Update service calls to use `await`
- [ ] 7.3 Change `Session = Depends(get_session)` to `AsyncSession = Depends(get_async_session)`

## 8. API Layer - Users

- [ ] 8.1 Convert `app/api/users.py` endpoints from `def` to `async def`
- [ ] 8.2 Update service calls to use `await`
- [ ] 8.3 Change to async session dependency

## 9. CLI Compatibility

- [ ] 9.1 Verify CLI commands still work with sync session infrastructure
- [ ] 9.2 Update CLI if needed to use sync wrappers or keep using sync sessions

## 10. Testing

- [ ] 10.1 Run existing API tests to verify async conversion works
- [ ] 10.2 Run existing CLI tests to verify compatibility
- [ ] 10.3 Manually test API endpoints via curl or Swagger UI
