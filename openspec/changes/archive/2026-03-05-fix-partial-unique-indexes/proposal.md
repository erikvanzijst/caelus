## Why

The ORM model definitions for partial unique indexes are inconsistent across SQLite and Postgres, and one deployment uniqueness rule targets the wrong condition. This creates cross-database behavior drift and incorrect uniqueness enforcement in production paths.

## What Changes

- Add missing `postgresql_where` clauses to model partial indexes that currently define only `sqlite_where`.
- Update `DeploymentORM` partial unique indexes so active-deployment uniqueness is keyed off `status`, not `deleted_at`, including correcting `uq_deployment_active`.
- Remove the `uq_producttemplate_active` partial unique index from `ProductTemplateVersionORM` so identical templates can coexist.
- Add an Alembic migration for the index updates, generated from autogenerate and then manually refined to include only intended partial-index changes.
- Keep API and CLI behavior in lockstep by applying the same model/migration semantics for both supported databases.

## Capabilities

### New Capabilities
- `cross-database-partial-index-parity`: Ensure partial unique index behavior is intentionally aligned across SQLite and Postgres for model-level uniqueness constraints.

### Modified Capabilities
- None.

## Impact

- Affected code: `api/app/models.py`, Alembic migration files under `api/alembic/versions/`.
- Affected systems: Postgres and SQLite schema behavior for uniqueness constraints.
- API/CLI impact: No route or command surface changes, but provisioning/deployment data integrity rules become consistent and corrected.
