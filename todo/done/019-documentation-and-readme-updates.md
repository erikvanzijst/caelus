# Issue 019: Documentation Updates (API, UI, Architecture Links)

## Goal
Update developer-facing docs so implementation matches architecture and operator workflows.

## Depends On
`018-api-and-cli-integration-regression-suite.md`

## Scope
1. Update `api/README.md` with:
   - new template fields
   - new deployment fields and statuses
   - new API endpoints
   - new CLI commands
2. Update `ui/README.md` with:
   - dynamic values form behavior from `values_schema_json.properties.user`
   - status display behavior
3. Cross-link `k8s/architecture.md` and `k8s/hello-static-chart/README.md`.
4. Add troubleshooting section for ingress class mismatch (`traefik` vs `nginx`).

## Acceptance Criteria
1. New commands/endpoints are documented with examples.
2. Manual validation checklist is discoverable from README files.
3. Docs mention V1 constraints and non-goals clearly.
