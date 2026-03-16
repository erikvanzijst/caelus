## Context

The Caelus platform lets users deploy applications by filling in a form driven by a JSON Schema (`values_schema_json`) on the product's template. The form is rendered by `DeployDialog` → `DeployDialogContent` → `UserValuesForm`. On submit, user values are sent to `POST /api/users/{user_id}/deployments` which stores them as `user_values_json` and enqueues a Helm reconcile job.

The backend already has a `PUT /api/users/{user_id}/deployments/{deployment_id}` endpoint backed by `update_deployment()`, but it was designed for template version upgrades — it requires `desired_template_id` to be strictly greater than the current one. The frontend has no UI to call it.

The reconciler merges three layers into final Helm values: `default_values_json` (template-level admin config like SMTP) → `user_values_json` (user-editable values) → `system_overrides` (code-injected, currently empty). The edit dialog operates exclusively on the `user_values_json` layer.

## Goals / Non-Goals

**Goals:**
- Allow users to edit their deployment's config values through the same form they used at creation
- Make the edit operation safe against concurrent reconciler runs via atomic status checks
- Reuse the existing `DeployDialog` / `DeployDialogContent` component tree with minimal edit-mode branching
- Handle hostname validation correctly — skip the availability check when the hostname hasn't changed

**Non-Goals:**
- Template version upgrades in the edit dialog (the edit flow keeps the same template version)
- Exposing `default_values_json` / admin-only values in the edit form
- Editing deployments that are in transitional states (provisioning, deleting)
- Schema evolution UX (showing "new field added" indicators) — the form simply renders the current schema's fields

## Decisions

### 1. Relax template version constraint to `<` (strict less-than)

**Decision**: Change the guard in `update_deployment()` from `desired_template_id <= current` to `desired_template_id < current`.

**Rationale**: The existing `<=` check was designed to prevent "no-op" upgrades and downgrades. But for value-only edits, the user submits the same `desired_template_id` with different `user_values_json`. Allowing equality enables this use case while still preventing downgrades.

### 2. Atomic status guard via conditional SQL UPDATE

**Decision**: Make the `update_deployment()` service update the deployment row with a `WHERE status = 'ready'` condition. If 0 rows are affected, raise an error that the API returns as 409 Conflict.

**Rationale**: Simply hiding the Edit button when status != `ready` is not sufficient — there's a race window between the user clicking Update and the request arriving. An optimistic concurrency guard at the SQL level closes this gap without requiring explicit locking. The reconciler sets status to `provisioning`/`ready`/`error`, so a conditional update on `ready` guarantees no concurrent reconcile is in flight.

**Alternative considered**: Check status in Python before updating. Rejected because it leaves a TOCTOU window.

### 3. Client-side hostname validation skip (no API changes)

**Decision**: Add an `initialHostname` prop to `HostnameField`. When the current FQDN equals `initialHostname`, skip the `GET /api/hostnames/{fqdn}` call and report `valid` directly.

**Rationale**: The hostname check API would report the deployment's own hostname as `in_use`. Rather than adding an `exclude_deployment_id` query parameter to the API (which leaks implementation details), the client simply avoids making the call when the value hasn't changed. This is correct because:
- If the hostname is unchanged, it was already validated at deployment creation
- If the user changes the hostname, the check fires normally
- If the user changes it and then reverts, the skip kicks back in

**Trade-off**: This means a hostname that became invalid for other reasons (e.g., DNS changed) won't be re-checked if the user doesn't modify it. This is acceptable because the backend validates again on submit.

### 4. Pre-populate form from deployment.user_values_json, not template defaults

**Decision**: In edit mode, pass `deployment.user_values_json` as the `defaultValuesJson` prop to `UserValuesForm`. Do not consult `template.default_values_json`.

**Rationale**: The deployment's `user_values_json` already contains the values the user provided at creation time (which may have included template defaults that were baked in). The template's `default_values_json` serves a dual purpose — seeding user-visible form defaults AND injecting admin-controlled Helm values (like SMTP config). Exposing admin values in the edit form would be incorrect. The form fields are driven by `values_schema_json` (which only describes user-editable fields), so any schema evolution (new fields, removed fields) is handled naturally: new fields appear empty, removed fields are dropped.

### 5. Change valuesToSend fallback from default_values_json to {}

**Decision**: In `DeployDialog.handleLaunch()`, change `const valuesToSend = userValues ?? canonicalTemplate?.default_values_json ?? undefined` to `const valuesToSend = userValues ?? {}`.

**Rationale**: The reconciler always merges `default_values_json` as the base layer when building Helm values. Sending the template's defaults from the client was redundant — `deep_merge(defaults, {})` produces the same result as `deep_merge(defaults, defaults)`. Removing this also prevents the latent bug where clearing a required field would silently fall back to defaults instead of triggering validation. This change applies to both create and edit modes.

### 6. DeployDialog edit mode via optional deployment prop

**Decision**: Add an optional `deployment` prop to `DeployDialog`. When present, the dialog operates in edit mode: pre-populates values, uses PUT instead of POST, shows "Update" button text, passes `deployment.hostname` as `initialHostname`.

**Rationale**: A single component with a mode flag is simpler than creating a separate `EditDeploymentDialog` — the form rendering, validation, error handling, and template fetching logic are identical. The differences are small: the mutation target (POST vs PUT), the initial values source, and the button text.

## Risks / Trade-offs

- **[Risk] Schema evolution with required fields**: If a template upgrade adds a new required field without a JSON Schema `default`, the edit form will show it as empty and submission will fail validation. This is correct behavior (the user must provide a value), but it may be confusing if they didn't initiate the template upgrade. Acceptable for now — template admins should not add required fields without defaults.
- **[Risk] Concurrent edits by admin and user**: An admin could modify the template while a user has the edit dialog open. The form would submit against the old schema, but the backend validates against the current template. If the schemas are incompatible, the backend will reject the request with a validation error. This is safe but the error message may be confusing.
- **[Trade-off] No optimistic UI for edit**: After submitting an edit, the deployment goes to `provisioning` and the user sees a progress bar. We don't show the new values immediately. This is consistent with the create flow.
