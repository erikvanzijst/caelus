# Issue 006: Template Service V2 And Immutability Enforcement

## Goal
Implement full template lifecycle rules for Helm metadata, schema/default values, and immutable version records.

## Depends On
`005-sqlmodel-models-and-read-write-schemas.md`

## Scope
Update `api/app/services/templates.py`:
1. Create template validates required Helm fields when provided.
2. Enforce `package_type=helm-chart` in V1.
3. Validate `values_schema_json` is valid JSON Schema object (structural check).
4. Validate `default_values_json` conforms to `values_schema_json` when both provided.
5. Prevent updates to immutable template fields after creation (service-level guard).
6. Keep soft delete behavior unchanged.

## API/CLI Parity Tasks
1. Ensure CLI create-template can accept new fields.
2. Ensure API create-template accepts same capabilities.

## Acceptance Criteria
1. Invalid schema/default combo returns stable 400/422 style error.
2. Immutable fields cannot be changed via any service path.
3. Existing listing/get behavior includes new fields.

## Test Requirements
1. Unit tests for schema validation and immutable enforcement.
2. API tests for create/list/get with new fields.
3. CLI tests for creating template with Helm metadata.
