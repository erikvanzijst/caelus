## Context

`ProductTemplateVersion.default_values_json` is a JSON column that stores Helm values merged as a base layer during reconciliation. The reconciler builds final Helm values via:

```
merged = deep_merge(default_values_json, user_values_json)
merged = deep_merge(merged, system_overrides)  <-- always {}
```

In practice, `default_values_json` is used by admins to inject infrastructure config that users don't control — SMTP relay settings, ingress class, database toggles, persistence config. For example, the Nextcloud template injects:

```json
{
  "nextcloud": {
    "mail": {
      "smtp": { "host": "smtp.mailer.svc.cluster.local", "port": 25 }
    }
  },
  "internalDatabase": { "enabled": false },
  "postgresql": { "enabled": true }
}
```

None of this belongs in a user-facing form. The name `default_values_json` implies "defaults for the user to override" when its actual role is "system base layer the user never sees."

The frontend currently receives `default_values_json` in API responses and feeds it to the deploy dialog as form pre-population. This is redundant (the reconciler applies it anyway) and potentially confusing (admin-only values appear as form defaults). Change A (edit-deployment-config) already stops using it in the deploy flow. This change completes the cleanup.

## Goals / Non-Goals

**Goals:**
- Make the field name reflect its actual purpose (system/admin config, not user defaults)
- Remove `default_values_json` / `defaultValuesJson` from deploy-flow components where it no longer belongs
- Simplify the reconciler by removing the no-op `_build_system_overrides()`
- Keep admin functionality intact — admins can still set and view system values

**Non-Goals:**
- Removing system_values_json from the API entirely (admins need it for template management)
- Migrating existing default annotations into JSON Schema defaults (separate operational task)
- Changing the reconciler merge semantics (order and behavior stay the same)
- Splitting system_values_json into separate "admin defaults" and "infrastructure config" fields

## Decisions

### 1. Rename to `system_values_json`

**Decision**: Rename the field to `system_values_json` across all layers.

**Rationale**: "System values" accurately describes the field's role — values injected by the system (admin/platform) that form the base layer for Helm deployments. Alternative names considered:
- `base_values_json` — too generic, doesn't convey admin ownership
- `admin_values_json` — conflates the role (system config) with the actor (admin)
- `platform_values_json` — acceptable but less clear than "system"
- `template_values_json` — confusing since `values_schema_json` is also template-level

### 2. Column rename via Alembic migration

**Decision**: Use `op.alter_column(..., new_column_name=...)` to rename the DB column in-place.

**Rationale**: A rename is a metadata-only operation in both Postgres and SQLite — no data copy needed. This is safer and faster than creating a new column, copying data, and dropping the old one. The migration is backward-incompatible (old code can't read the new column name), but this is acceptable for a coordinated deploy.

### 3. Remove defaultValuesJson prop from DeployDialogContent and UserValuesForm

**Decision**: Remove the `defaultValuesJson` prop from both components. `UserValuesForm` seeds form fields using only JSON Schema `default` annotations (`field.default`).

**Rationale**: After Change A, the deploy dialog no longer passes `default_values_json` to these components (it passes `deployment.user_values_json` in edit mode and `{}` in create mode). The admin preview in `TemplateTabNew` and `TemplateTabReadOnly` also passed it, but the preview should show what the user sees — a form driven by the schema alone. Removing the prop eliminates the incorrect coupling entirely.

**Impact on form defaults**: The `flattenDefaults()` function and the `defaults` lookup in `UserValuesForm` are removed. Form fields use `field.default` from the schema instead. This means any user-visible defaults currently set only in `default_values_json` (not in the schema) will stop appearing in the form. Admins should move those to JSON Schema `default` annotations.

### 4. Remove `_build_system_overrides()` from reconciler

**Decision**: Delete the method and pass `None` as the third argument to `merge_values_scoped()`.

**Rationale**: The method is a no-op stub that returns `{}`. It was a placeholder for future system-injected overrides (e.g., resource limits, node selectors). If that need arises, it can be re-added. Until then, dead code should be removed. `merge_values_scoped()` already handles `None` gracefully.

### 5. Keep system_values_json in API read models

**Decision**: Keep `system_values_json` in `ProductTemplateVersionRead` (returned by the API).

**Rationale**: The admin UI needs to display current system values in `TemplateTabReadOnly`. Only the deploy-flow components stop using it. The field is still returned by the API but is simply not consumed by user-facing frontend code.

## Risks / Trade-offs

- **[Risk] Breaking API change**: Renaming the field in API models is a breaking change for any external API consumers. Acceptable since this is an internal platform with no external consumers.
- **[Risk] Existing templates with user-visible defaults**: Templates that rely on `default_values_json` to seed user form fields (rather than JSON Schema `default` annotations) will lose those form defaults. Admins need to migrate them to schema defaults. The reconciler still applies system values correctly — only the form pre-population is affected.
- **[Trade-off] CLI flag rename**: Existing admin scripts using `--default-values-json` or `--default-values-file` will break. Acceptable for an internal tool; update scripts alongside the code change.
