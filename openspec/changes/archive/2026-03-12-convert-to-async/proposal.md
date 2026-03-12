## Why

FastAPI natively supports async request handlers, but our API endpoints are currently synchronous functions that block the event loop during database operations. This limits throughput and prevents us from handling concurrent requests efficiently. Converting to async will improve performance under load.

## What Changes

- Add async database engine and session management in `app/db.py`
- Convert all service layer functions from sync to async, using async SQLModel queries (`await session.execute()`)
- Convert all API endpoint handlers from `def` to `async def`
- Update dependency injection to provide async sessions via `get_async_session()`
- Ensure CLI commands continue to work (may use sync wrappers or async-native approach)

## Capabilities

### New Capabilities
(None - this is an implementation optimization with no external API changes)

### Modified Capabilities
(None - all existing behavior is preserved)

## Impact

- `app/db.py`: Add async engine, async sessionmaker, and async session dependency
- `app/services/*.py`: Convert all functions to async with `await` for DB operations
- `app/api/*.py`: Convert all endpoint handlers to `async def`
- `app/deps.py`: Add async session dependency
- `app/cli.py`: Ensure CLI continues to work with async changes
