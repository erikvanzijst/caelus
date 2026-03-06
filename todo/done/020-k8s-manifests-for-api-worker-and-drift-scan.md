# Issue 020: Kubernetes Runtime Manifests For API, Worker, And Drift Scan

## Goal
Provide deployable Kubernetes manifests/examples for running API and worker as separate runtimes from the same image.

## Depends On
`016-worker-runtime-entrypoint-and-process-model.md`
`019-documentation-and-readme-updates.md`

## Scope
Add manifests under `k8s/` (or `k8s/manifests/`):
1. `caelus-api-deployment.yaml` with API command.
2. `caelus-worker-deployment.yaml` with worker loop command.
3. Optional `caelus-drift-scan-cronjob.yaml` with scan command.
4. Shared ConfigMap/Secret references for `DATABASE_URL` and cluster config.

## Requirements
1. Same container image for API and worker.
2. Distinct command/args and health checks.
3. Reasonable resource requests/limits placeholders.
4. Labeling/selector conventions documented.

## Acceptance Criteria
1. Manifests are syntactically valid.
2. Commands match CLI introduced in Issue 013.
3. Docs explain how manifests map to architecture runtime topology.

## Test Requirements
1. `kubectl apply --dry-run=client -f ...` passes for each manifest.
