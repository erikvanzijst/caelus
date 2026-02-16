# Issue 007: Deployment Service Identity, Desired State Tracking, And Job Enqueue

## Goal
Update deployment service so create/update/delete operations drive reconciliation through queue jobs.

## Depends On
`002-sqlmodel-models-and-read-write-schemas.md`
`006-template-service-v2-and-immutability.md`

## Scope
Update `api/app/services/deployments.py`:
1. On create:
   - generate `deployment_uid` as `{product_slug}-{user_slug}-{suffix6}` with DNS-label truncation rules.
   - set `desired_template_id` from requested/canonical template.
   - set status `pending`.
   - enqueue reconcile job (`reason=create`).
2. On domain/user_values update:
   - increment `generation`.
   - set status `provisioning` or `upgrading` as appropriate.
   - enqueue `reason=update`.
3. On delete (soft delete):
   - set status `deleting`.
   - enqueue `reason=delete`.
4. Add service method for admin upgrade request:
   - set `desired_template_id` to new template.
   - enqueue `reason=update`.
   - add cli command `upgrade-deployment`.
   - add api endpoint `PUT /users/{uid}/deployments/{deployment_uid}`.
   - enforce upgrade-only path by only allowing desired_template_id to increase, never decrease.

## Additional Requirements
1. Remove direct `provisioner.provision(...)` call from create path.
2. Ensure all writes happen in one transaction with enqueue where possible.

## Acceptance Criteria
1. Deployment create no longer performs immediate provisioning side effects.
2. Queue jobs are created reliably for create/update/delete/upgrade.
3. Existing list/get responses show new deployment status fields.

## Test Requirements
1. Service tests verify enqueue side effects.
2. API tests verify status transitions and job creation.
3. CLI tests verify create/delete/upgrade paths.
4. Naming tests verify generated ids are unique, DNS-label valid, and stable for stored rows.
