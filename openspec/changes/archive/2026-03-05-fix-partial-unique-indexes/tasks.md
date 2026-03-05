## 1. Align ORM Partial Index Definitions

- [x] 1.1 Audit partial unique indexes in `api/app/models.py` and identify every index with `sqlite_where` but missing `postgresql_where`.
- [x] 1.2 Add `postgresql_where` predicates for the identified indexes with equivalent filtering semantics.
- [x] 1.3 Update the two `DeploymentORM` partial unique indexes to use `status`-based predicates and modify `uq_deployment_active` accordingly.
- [x] 1.4 Remove the `uq_producttemplate_active` partial unique index from `ProductTemplateVersionORM`.

## 2. Create and Curate Alembic Migration

- [x] 2.1 Run Alembic autogenerate to create a migration revision capturing model/index deltas.
- [x] 2.2 Manually edit the generated revision so upgrade includes only intended partial index drop/create/remove operations.
- [x] 2.3 Ensure migration downgrade is coherent for the changed indexes (including restored prior indexes where rollback policy requires it).
- [x] 2.4 Verify the migration file contains no unrelated schema or data changes.

## 3. Validate Behavior and Prevent Regression

- [x] 3.1 Add or update API/DB tests to verify status-based deployment active uniqueness behavior.
- [x] 3.2 Add or update tests to verify identical product template versions are allowed after dropping `uq_producttemplate_active`.
- [x] 3.3 Add or update tests (or assertions) validating cross-database partial index parity intent in model metadata.
- [x] 3.4 Run relevant test suites and report results.
