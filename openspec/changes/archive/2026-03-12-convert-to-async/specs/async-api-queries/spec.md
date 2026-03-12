# async-api-queries Specification

## ADDED Requirements

### Requirement: API endpoints use async request handlers
All REST API endpoints in the FastAPI application SHALL be defined with `async def` to enable non-blocking request handling.

#### Scenario: API endpoint defined as async
- **WHEN** a developer defines a new API endpoint in `app/api/`
- **THEN** the function is declared with `async def` instead of `def`

#### Scenario: API endpoint calls async service
- **WHEN** an async endpoint handler invokes a service function
- **THEN** the call uses `await` to properly await the async service function

### Requirement: Service layer uses async database queries
All service functions that interact with the database SHALL use async SQLModel operations to avoid blocking the event loop.

#### Scenario: Service function queries database async
- **WHEN** a service function needs to query the database
- **THEN** it uses `await session.execute(select(...))` pattern with AsyncSession

#### Scenario: Service function commits transaction async
- **WHEN** a service function needs to persist changes
- **THEN** it uses `await session.commit()` with AsyncSession

### Requirement: Database session dependency provides async session
The FastAPI dependency injection system SHALL provide async database sessions to endpoint handlers.

#### Scenario: Endpoint requests async session
- **WHEN** an endpoint handler specifies `session: AsyncSession = Depends(get_async_session)`
- **THEN** FastAPI provides an AsyncSession instance

#### Scenario: Async session is properly cleaned up
- **WHEN** a request completes (success or failure)
- **THEN** the AsyncSession is automatically closed and returned to the pool

### Requirement: CLI continues to function with async services
The CLI commands SHALL continue to work correctly after services are converted to async.

#### Scenario: CLI command executes with async service
- **WHEN** a user runs a CLI command that invokes an async service
- **THEN** the command completes successfully (via sync wrapper or run_sync)

#### Scenario: CLI uses sync session
- **WHEN** a CLI command needs database access
- **THEN** it can use the synchronous session infrastructure (kept for CLI compatibility)
