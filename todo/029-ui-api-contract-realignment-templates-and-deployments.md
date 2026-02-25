# Issue 029: UI API Contract Realignment For Templates And Deployments

## Goal
Bring `ui/` back into compatibility with the current backend API for template
and deployment workflows, without backend changes.

## Status
In progress (major contract fixes complete).

## Progress Update (2026-02-25)
Completed work:
1. Fixed template create contract mismatch:
   - UI now sends `chart_ref` and `chart_version` to
     `POST /products/{product_id}/templates`.
   - Admin form updated from legacy docker image input to chart fields.
2. Fixed template rendering mismatch:
   - Template cards now render `chart_ref:chart_version`.
3. Fixed deployment create contract mismatch:
   - UI now sends `desired_template_id` and `domainname` to
     `POST /users/{user_id}/deployments`.
4. Fixed deployment rendering mismatch:
   - Deployment cards now read product from
     `deployment.desired_template.product.name`.
   - Template display now uses `deployment.desired_template_id`.
5. Fixed API error UX:
   - Improved `requestJson` error parsing for FastAPI `detail` arrays/objects.
   - Removed `[object Object]` error rendering path.
6. Migrated away from deprecated MUI `GridLegacy`:
   - Replaced with `Grid` API in Admin and Dashboard.
7. Added deployment status visibility on dashboard cards:
   - status chip from `deployment.status`
   - last reconcile timestamp from `deployment.last_reconcile_at`
   - inline error display from `deployment.last_error`
8. Removed generation display after UX review:
   - `generation` is intentionally not shown to end users.

Touched files:
1. `ui/src/api/types.ts`
2. `ui/src/api/endpoints.ts`
3. `ui/src/api/client.ts`
4. `ui/src/pages/Admin.tsx`
5. `ui/src/pages/Dashboard.tsx`

Validation performed:
1. `npm run build` in `ui/` passes after each change set.
2. Playwright confirms:
   - template create returns `201` and list updates correctly.
   - deployment create returns `201` with payload key
     `desired_template_id`.
   - deployment cards show correct product/template values.
   - no `GridLegacy` deprecation warning remains in console.
   - deployment cards show status/reconcile/error fields correctly.

Remaining optional follow-up:
1. Improve async delete UX for deployments (pending/deleting feedback and
   auto-refresh behavior while backend reconciles deletion).
2. Add/automate UI regression checks (currently manual Playwright coverage).

## Context
Date audited: 2026-02-25  
Validation method:
1. Manual UI walkthrough via Playwright at `http://localhost:5173`.
2. Request/response inspection via browser network logs.
3. Contract verification against `http://localhost:8000/openapi.json`.

Backend is considered source-of-truth and known-good.

## Confirmed Breakages
1. Admin `Add template` flow fails.
2. Dashboard `Launch` deployment flow fails.
3. Deployment cards render stale/incorrect fields from old response shape.
4. Template cards/details render stale/incorrect fields from old template shape.
5. Deployment create error UX is not readable (`[object Object]`).

## API Contract Deltas (Current Backend)
### Templates
Route: `POST /products/{product_id}/templates`

Current request schema (`ProductTemplateVersionCreate`) uses:
1. `chart_ref` (string)
2. `chart_version` (string)
3. optional metadata fields (`chart_digest`, `version_label`,
   `default_values_json`, `values_schema_json`, `capabilities_json`)

UI currently sends:
1. `docker_image_url` (legacy field, no longer valid for this API)

Observed result:
1. Browser reports request failure (`net::ERR_FAILED`).
2. API returns `500 Internal Server Error` for legacy payload.
3. API returns `201 Created` when sending valid `chart_ref/chart_version`.

### Deployments
Route: `POST /users/{user_id}/deployments`

Current request schema (`DeploymentCreate`) requires:
1. `desired_template_id` (integer)
2. `domainname` (string)
3. optional `user_values_json` (object|null)

UI currently sends:
1. `template_id` (legacy key)
2. `domainname`

Observed result:
1. `422 Unprocessable Content`
2. Validation error indicates missing `desired_template_id`.

### Deployment Read Shape
Route: `GET /users/{user_id}/deployments`

Current response (`DeploymentRead`) includes:
1. `desired_template` (object)
2. `applied_template` (object|null)
3. status lifecycle fields (`status`, `generation`, `last_error`, etc.)

UI symptoms indicate it still expects old fields:
1. Product label shown as `Unknown product` despite data existing at
   `deployment.desired_template.product.name`.
2. Template label shown as `Template #` (id not resolved from current shape).

### Template Read Shape
Route: `GET /products/{product_id}/templates`

Current response (`ProductTemplateVersionRead`) includes:
1. `chart_ref`
2. `chart_version`
3. optional metadata fields

UI symptom:
1. Displays `No image URL` (legacy `docker_image_url` assumption).

## Scope Of Fix
1. Update frontend API types/interfaces for templates and deployments.
2. Update admin create-template payload mapping:
   - replace `docker_image_url` submit contract with `chart_ref` and
     `chart_version`.
3. Update dashboard create-deployment payload mapping:
   - use `desired_template_id` instead of `template_id`.
4. Update deployment list rendering to read nested fields from
   `desired_template` and `applied_template`.
5. Update template list/detail rendering to show chart metadata rather than
   legacy image URL field.
6. Improve error extraction/formatting so HTTP/API errors render meaningful text
   instead of object stringification.

## Non-Goals
1. No backend endpoint or schema changes.
2. No provisioning logic changes.
3. No broad UI redesign; focus on API compatibility/regression fix.

## Acceptance Criteria
1. Creating a template from Admin succeeds with valid input and appears in list.
2. Creating a deployment from Dashboard succeeds and appears in list.
3. Deployment cards show correct product and template identifiers.
4. Template cards/details show valid chart fields (`chart_ref/chart_version`).
5. API errors are human-readable in alerts/snackbars.
6. No regressions in:
   - product listing/selection
   - set canonical template
   - template delete
   - deployment delete

## Suggested Implementation Order
1. Update shared API types and request builders.
2. Fix create-deployment payload key mismatch.
3. Fix deployment list rendering for new nested template shape.
4. Fix create-template form and payload mapping.
5. Fix template rendering fields.
6. Fix generic API error formatting.
7. Run manual Playwright regression pass.

## Manual QA Checklist
1. Confirm Admin page loads products and product-scoped templates.
2. Create template with:
   - `chart_ref = ghcr.io/example/foo`
   - `chart_version = 1.0.2`
3. Set new template as canonical.
4. Go Dashboard, create deployment with valid domain.
5. Confirm deployment card shows:
   - correct domain
   - correct product name
   - correct template id
6. Delete deployment and confirm removal/refresh behavior.
7. Delete template and confirm list refresh.
8. Force an invalid request and confirm readable error text.

## Notes For Next Agent
1. Dev DB data is disposable for this effort; destructive operations are allowed.
2. During audit, data was mutated (templates/deployments created/deleted).
3. Reproduce against current running services:
   - API docs: `http://localhost:8000/docs`
   - OpenAPI: `http://localhost:8000/openapi.json`
   - UI: `http://localhost:5173`
