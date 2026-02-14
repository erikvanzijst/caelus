# Issue 015: UI Dynamic User Values Forms And Deployment Status Visibility

## Goal
Update frontend to render user-editable template fields from `values_schema_json.properties.user`, submit `user_values`, and show reconcile status.

## Depends On
`014-api-endpoints-for-deployment-update-upgrade-and-status.md`

## Scope
Update `ui/src` components/pages/api types:
1. Extend API types for template schema/default values and deployment status fields.
2. In deployment creation form (`Dashboard.tsx`):
   - derive fields from `template.values_schema_json.properties.user`.
   - render controls for scalar/enum safe subset.
   - collect `user_values` payload.
3. In deployment cards:
   - display reconcile status and last error.
   - display desired/applied template ids.
4. In admin flows:
   - allow creating template with new Helm metadata and schema/default values (if admin UX scope includes this in V1).

## UI Rules
1. If `properties.user` missing, no dynamic fields shown.
2. Domain remains explicit separate field.
3. System-managed values are not user-editable.

## Acceptance Criteria
1. Dynamic field rendering works for `hello-static` (`user.message`).
2. Form validation errors are understandable.
3. Deployment status visibility added without breaking existing UI flows.

## Test Requirements
1. Add at least component-level logic tests if test setup is introduced.
2. If no test framework is introduced, provide manual QA checklist in `ui/README.md`.
