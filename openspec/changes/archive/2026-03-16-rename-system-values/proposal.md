## Why

The field `default_values_json` on `ProductTemplateVersion` conflates two distinct purposes: seeding user-visible form defaults and injecting admin-controlled Helm values outside user control (SMTP config, ingress settings, etc.). This dual purpose creates confusion — the deploy dialog currently receives the full `default_values_json` even though most of its contents are admin-only infrastructure config that users should never see or modify.

The reconciler's merge chain (`default_values_json` -> `user_values_json` -> `system_overrides`) already treats it as a system base layer. Renaming it to `system_values_json` makes its role explicit. User-visible form defaults belong in the JSON Schema's `default` annotations on `values_schema_json`, not in a separate field.

This change also removes `_build_system_overrides()` from the reconciler, which is a no-op stub returning `{}`.

## What Changes

- **Rename**: `default_values_json` -> `system_values_json` across the entire stack (DB column, ORM model, API models, CLI flags, frontend types, admin UI)
- **Remove from deploy flow**: Drop the `defaultValuesJson` prop from `DeployDialogContent` and `UserValuesForm` — these components no longer need system values. Form field defaults come from JSON Schema `default` annotations instead.
- **Simplify reconciler**: Remove `_build_system_overrides()` and pass `None` as the third argument to `merge_values_scoped()`
- **Admin UI labels**: Rename "Default values" labels to "System values" in `TemplateTabNew` and `TemplateTabReadOnly`

## Capabilities

### New Capabilities
- `system-values-rename`: The coordinated rename and cleanup across all layers

### Modified Capabilities
- `deploy-dialog-shared`: `DeployDialogContent` drops the `defaultValuesJson` prop
- `hostname-field-ui` (via `UserValuesForm`): `UserValuesForm` drops the `defaultValuesJson` prop; form field defaults come from JSON Schema `default` annotations only
- `admin-schema-preview`: Admin template editors use `system_values_json` field name and "System values" label

## Impact

- **Code**: Models, CLI, reconciler, API routes, frontend types, components, admin UI, tests — approximately 54 touchpoints across 34 files (mechanical rename)
- **APIs**: `ProductTemplateVersion` read/write models use `system_values_json` instead of `default_values_json`. This is a breaking API change.
- **Dependencies**: None
- **Systems**: Alembic migration to rename the DB column
- **Admin action required**: Any user-visible form defaults currently in `default_values_json` should be moved to JSON Schema `default` annotations in `values_schema_json` before or during this change
