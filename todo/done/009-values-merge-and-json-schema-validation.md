# Issue 009: Values Merge, User Scope Handling, And JSON Schema Validation Utilities

## Goal
Build reusable utilities for scoped value merge and schema validation used by API and reconciler.

## Depends On
`002-sqlmodel-models-and-read-write-schemas.md`

## Scope
Create module, e.g. `api/app/services/template_values.py`, with functions:
1. `extract_user_subschema(values_schema_json)`.
2. `validate_user_values(user_values_json, values_schema_json)` against `properties.user`.
3. `merge_values_scoped(defaults, user_scope_delta, system_overrides)`.
4. `validate_merged_values(merged_values, values_schema_json)`.
5. `deep_merge` deterministic implementation.

## Rules
1. User overrides apply only under `values.user`.
2. If `values_schema_json.properties.user` missing, non-empty `user_values_json` is rejected.
3. System overrides always win over defaults and user input.
4. Reject non-object JSON payloads for user values.

## Acceptance Criteria
1. Utilities are pure and independently testable.
2. Reconciler and API use the same utility functions.

## Test Requirements
1. Unit tests for merge precedence.
2. Unit tests for optional user scope behavior.
3. Unit tests for schema rejection/acceptance cases.
4. Unit tests for edge cases: arrays, nested objects, unknown keys.
