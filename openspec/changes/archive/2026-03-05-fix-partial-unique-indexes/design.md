## Context

`api/app/models.py` defines several partial unique indexes used to enforce logical uniqueness for soft-deleted and stateful records. The project supports both SQLite (tests/local) and Postgres (production), but some indexes currently define only `sqlite_where`, creating divergent behavior. Additionally, `DeploymentORM` currently ties active uniqueness to `deleted_at` in places where business logic depends on `status`, and `ProductTemplateVersionORM` has a partial unique index that now conflicts with the need to allow duplicate templates.

Because partial index DDL differs by backend and Alembic autogenerate is unreliable for partial index deltas, migration changes need controlled manual refinement after autogenerate produces a baseline.

## Goals / Non-Goals

**Goals:**
- Ensure model-level partial unique indexes define equivalent predicates for both SQLite and Postgres where applicable.
- Correct deployment active uniqueness semantics to use `status` predicates.
- Remove `uq_producttemplate_active` from `ProductTemplateVersionORM`.
- Deliver an Alembic migration that applies only the intended index changes and is safe across supported environments.

**Non-Goals:**
- Redesign deployment lifecycle statuses or business workflows.
- Change REST/CLI route structure or command interfaces.
- Refactor unrelated ORM models, constraints, or naming conventions.

## Decisions

1. Keep index declarations as the source of truth in ORM models and align backend-specific predicates there.
- Rationale: API and CLI both rely on service/model behavior; aligning declarations avoids backend drift.
- Alternative considered: backend-specific raw SQL migrations only. Rejected because model/schema intent would remain inconsistent.

2. Change `DeploymentORM` partial unique predicates to use `status` and update `uq_deployment_active` accordingly.
- Rationale: active uniqueness should reflect runtime state, not soft-delete flag alone.
- Alternative considered: preserve `deleted_at` predicate and add application-level checks. Rejected due to weaker DB-level enforcement.

3. Remove `uq_producttemplate_active` entirely.
- Rationale: product template versions must permit multiple identical templates.
- Alternative considered: relax predicate/columns while keeping index. Rejected because uniqueness itself is no longer desired.

4. Generate migration via `alembic revision --autogenerate`, then manually edit to only include intended partial-index operations.
- Rationale: autogenerate provides naming/metadata baseline, but partial index diffs often need explicit drop/create ordering and backend-aware predicates.
- Alternative considered: hand-written migration from scratch. Rejected to reduce mismatch risk with current metadata snapshot.

## Risks / Trade-offs

- [Alembic detects extra unrelated diffs] -> Manually prune migration to only target index operations in scope.
- [Incorrect drop/create order causes migration failure] -> Use explicit index names and deterministic operation order (drop old before create new).
- [SQLite and Postgres predicates diverge again later] -> Require both `sqlite_where` and `postgresql_where` in model definitions where partial behavior is needed, and keep migration consistent.
- [Existing data violates new uniqueness semantics] -> Validate deployment rows for active-status duplicates before applying in constrained environments.

## Migration Plan

1. Update ORM index definitions in `api/app/models.py`:
- add missing `postgresql_where` clauses,
- update `DeploymentORM` partial unique predicates to use `status`,
- remove `uq_producttemplate_active`.
2. Run Alembic autogenerate to create a revision.
3. Manually edit revision to retain only expected index drops/creates/removals and correct partial predicates.
4. Validate migration with upgrade on SQLite and Postgres-compatible metadata assumptions.
5. Verify downgrade restores prior index state as defined by migration strategy.

## Open Questions

- Which exact deployment statuses qualify as “active” for uniqueness (for example, `pending` and `running` vs only `running`)?
- Should downgrade restore `uq_producttemplate_active` for strict reversibility, or keep downgrade limited where rollback policy allows forward-only migrations?
