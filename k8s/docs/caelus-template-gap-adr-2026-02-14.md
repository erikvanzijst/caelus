# ADR: Filling Caelus ProductTemplateVersion Deployment Gap

Date: 2026-02-14
Status: Proposed

## Context

Caelus currently stores template versions with only `docker_image_url` and has a stub provisioner. We need a production architecture that:

- supports namespace-per-instance isolation
- is scalable per deployment operation
- preserves immutable template version semantics
- supports safe explicit upgrades with persistent data continuity
- keeps Caelus DB as sole source of truth
- uses minimal moving parts while leveraging existing Kubernetes packaging/reconciliation patterns

## Decision drivers

1. Simplicity of operations
2. Drift convergence from DB to cluster
3. Per-instance scalability and fault isolation
4. Upgrade safety and observability
5. Ecosystem leverage for onboarding new products

## Options considered

### Option A: Caelus-native reconciler + Helm SDK

- Caelus worker reconciles each deployment directly against Kubernetes.
- Desired state lives only in Caelus DB.
- Helm SDK used for install/upgrade/uninstall.

### Option B: Caelus projects desired state to Flux HelmRelease

- Caelus DB is still source of truth.
- Caelus applies Namespace + `OCIRepository` + `HelmRelease` resources.
- Flux controllers perform reconciliation/drift correction.

## Decision matrix

| Criterion | Option A | Option B |
|---|---|---|
| Moving parts | Lowest | Medium (Flux CRDs/controllers) |
| DB-as-source-of-truth clarity | Strongest | Strong if projection discipline is strict |
| Reconciliation logic burden | Higher in app code | Lower in app code |
| Operational debugging | App logs + K8s | App + Flux status/events |
| Time to first robust V1 | Fast (single control plane) | Moderate (install/operate Flux) |
| Long-term extensibility | High, custom | High, Kubernetes-native patterns |

## Decision

Choose **Option A** for V1.

Rationale:

- Best fit for explicit requirement of "few moving parts".
- Strongest source-of-truth boundary.
- Simpler early operations while preserving migration path to Option B later.

## Consequences

### Positive

- Minimal platform components.
- Straightforward ownership model (Caelus owns all lifecycle).
- Easy to enforce API/CLI parity around provisioning and upgrades.

### Negative

- Caelus must own idempotent reconcile logic and edge cases.
- Need stronger internal observability and retry semantics.

## Non-goals for V1

- Auto-upgrade all deployments on template release
- Multi-cluster placement orchestration
- Arbitrary user-level chart value editing without allowlist

## V1 shape

1. Immutable Helm-backed `ProductTemplateVersion` using OCI digest.
2. Deployment identity fields (`deployment_uid`, `namespace_name`, `release_name`) independent of domain.
3. Reconciliation loop with per-deployment queue and retries.
4. Explicit upgrade endpoint/CLI command with policy checks.
5. Status model persisted in DB and shown in API/UI.

## Migration path to Option B later

If operational burden grows, introduce Flux as a reconciliation backend while preserving DB as source-of-truth:

1. Keep DB schema and lifecycle semantics unchanged.
2. Replace direct Helm actions with CR projection adapter.
3. Continue status mapping into deployment status fields.

## Risks and mitigations

1. Helm chart quality varies by upstream.
- Mitigation: template certification checklist and canary deployment before publish.

2. Stuck namespace deletion due to finalizers.
- Mitigation: explicit admin runbook and visibility in deployment status.

3. Unsafe upgrades for certain apps.
- Mitigation: per-template capability flags; enforce admin-only upgrades where needed.

## References

- Main report: `ai/architecture/caelus-k8s-template-architecture-2026-02-14.md`
- Kubernetes namespaces: https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/
- Kubernetes finalizers: https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/
- Helm upgrade: https://helm.sh/docs/helm/helm_upgrade/
- Helm SDK: https://pkg.go.dev/helm.sh/helm/v3/pkg/action
- Flux HelmRelease: https://fluxcd.io/flux/components/helm/helmreleases/
