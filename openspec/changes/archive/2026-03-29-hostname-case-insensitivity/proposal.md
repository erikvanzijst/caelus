## Why

The `/api/hostnames` endpoint currently performs case-sensitive hostname comparisons, which incorrectly allows duplicate hostnames that differ only in case (e.g., `Foo.dev.deprutser.be` vs `foo.dev.deprutser.be`). DNS is case-insensitive by RFC standards, so this creates a bug where users can provision multiple deployments with the same hostname using different capitalization, leading to DNS conflicts and unpredictable routing.

## What Changes

- Normalize all hostname comparisons to lowercase in the validation service
- Add a database migration to enforce lowercase hostnames at the storage layer
- Add a migration to deduplicate existing hostnames that differ only in case
- Update the unique index on `hostname` to use case-insensitive collation (PostgreSQL) or lower() expression (SQLite)
- Add tests for case-insensitive hostname validation

**BREAKING**: Existing deployments with mixed-case hostnames will be normalized to lowercase. This should be transparent to users but may require a brief maintenance window.

## Capabilities

### New Capabilities

### Modified Capabilities

- **hostname-validation**: Hostname availability checks must be case-insensitive to match DNS behavior
- **deployment-provisioning**: Hostname storage must enforce lowercase normalization

## Impact

- **Code**: `api/app/services/hostnames.py` - `_check_available()` function
- **Database**: `deployment` table `hostname` column - add lowercase constraint and deduplication
- **API**: `/api/hostnames/{fqdn}` endpoint behavior changes (case-insensitive)
- **Tests**: `api/tests/test_hostnames.py` - add case-insensitivity test cases
- **Migrations**: New Alembic migration for schema changes and data cleanup