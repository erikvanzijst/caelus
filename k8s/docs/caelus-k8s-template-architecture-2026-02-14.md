# Caelus Kubernetes Provisioning Template Architecture

Date: 2026-02-14

## Scope and objective

This document designs how `ProductTemplateVersion` should evolve from a simple image URL into a full, immutable deployment definition for Kubernetes applications (Nextcloud, Mattermost, etc.), while keeping Caelus simple and scalable.

You asked for at most two approaches; this report provides two:

1. Approach A (recommended): Caelus-native reconciler + Helm SDK (no extra in-cluster GitOps stack)
2. Approach B: Caelus projects DB state into Flux `OCIRepository` + `HelmRelease`

Both approaches satisfy per-instance namespace isolation, immutable template versions, upgradeability, and drift convergence from Caelus DB to Kubernetes.

---

## Design principles derived from requirements

1. Per-instance independence: work queue keys are per deployment ID; no global plan/apply.
2. Namespace isolation: one namespace per deployment; namespace is lifecycle boundary.
3. Keep moving parts low: reuse Helm charts and Kubernetes reconciliation primitives.
4. Full deployment description: template must represent all K8s objects (PVCs, CronJobs, ingress, etc.).
5. Immutability: once published, template content is content-addressed and frozen.
6. Safe versioning: new app release => new template version; no implicit upgrades.
7. Controlled upgrades: explicit user/admin action, with preflight and rollback strategy.
8. Data durability: PVC persistence across chart upgrades.
9. Domain mutability: domain is mutable config, not identity.
10. DB is source of truth: Kubernetes is continuously reconciled from DB desired state.
11. Leverage ecosystem artifacts: Helm/OCI first; optionally Compose conversion only as onboarding tooling.

---

## State of the art (relevant to Caelus)

### Why Helm as template payload

Helm remains the most practical packaging format for multi-resource Kubernetes apps. It supports:

- Structured chart versioning and dependencies
- Values schema validation (`values.schema.json`)
- Install/upgrade/rollback/uninstall workflows
- OCI artifact distribution and digest pinning

This aligns strongly with immutable `ProductTemplateVersion` and reproducible deployments.

### Why DB-driven reconciliation (not Terraform)

Terraform-style global state/plans can couple operation cost to estate size and introduce serialization bottlenecks. Caelus needs per-instance operations with latency independent from total instance count. Controller-style per-resource reconciliation is the better fit.

### Drift handling mechanisms available today

Two practical patterns:

- Caelus performs reconciliation directly (Helm SDK + server-side apply semantics where needed)
- Flux Helm Controller performs reconciliation when Caelus projects desired state as CRs

Both are viable. Main tradeoff: fewer components (A) vs stronger in-cluster declarative reconciliation engine (B).

---

## Common template model (applies to both approaches)

Current model (`docker_image_url`) is not enough. Evolve `ProductTemplateVersion` into an immutable artifact reference + constraints + defaults.

### Proposed `ProductTemplateVersion` conceptual fields

- `id` (immutable primary key)
- `product_id`
- `version_label` (admin-facing label, e.g. `nextcloud-29.0.4`)
- `package_type` (`helm-chart` initially)
- `chart_ref` (OCI URL or repo/chart)
- `chart_version` (optional if using digest)
- `chart_digest` (strongly preferred for immutability)
- `values_schema` (JSON Schema snapshot used by Caelus API validation)
- `default_values` (frozen baseline values)
- `system_overrides` (reserved map injected by Caelus: namespace, domain, storage class aliases, ingress class)
- `capabilities`:
  - `supports_domain_change` (bool)
  - `supports_inplace_upgrade` (bool)
  - `requires_admin_upgrade` (bool)
  - `requires_maintenance_mode` (bool)
- `health_checks` (readiness selectors/timeouts)
- `created_at`, `deleted_at`

Immutability rule: after creation, only soft-delete metadata can change.

### Proposed `Deployment` conceptual additions

- Stable identifiers:
  - `deployment_uid` (UUID, immutable identity used in names and labels)
  - `namespace_name` (immutable once created)
  - `release_name` (immutable)
- Mutable runtime config:
  - `domainname` (mutable)
  - `user_values` (validated against template schema)
- Lifecycle:
  - `status` (`pending`, `provisioning`, `ready`, `upgrading`, `deleting`, `error`)
  - `desired_template_id`
  - `applied_template_id`
  - `last_reconcile_at`
  - `last_error`
  - `generation` (increment on desired-state change)

Identity rule: never key by domain.

---

## Approach A (recommended): Caelus-native reconciler + Helm SDK

## Summary

Caelus itself runs a reconciliation worker. DB is the desired-state source; worker continuously converges one deployment at a time by calling Kubernetes and Helm APIs.

No Flux/Argo dependency.

## Architecture

```text
+-------------------+          +---------------------------+
| Caelus API / CLI  | writes   | Caelus DB (source truth) |
+-------------------+--------->+---------------------------+
          |                                |
          | enqueue deployment_id          | poll / events
          v                                v
+----------------------------------------------------------+
| Caelus Reconciler Worker                                 |
| - per-deployment queue key                               |
| - renders desired values                                 |
| - helm install/upgrade/uninstall via SDK                |
| - namespace lifecycle + safety finalizer handling        |
+-------------------------------+--------------------------+
                                |
                                v
                     +----------------------+
                     | Kubernetes API Server|
                     +----------------------+
```

## Reconciliation contract

Desired state (from DB):

- Deployment exists and not deleted => namespace + Helm release must exist and match desired template + values
- Deployment deleted => release removed and namespace deleted

Actual state: queried from Kubernetes/Helm release metadata.

Convergence loop:

1. Load deployment row with lock or optimistic generation check.
2. Compute desired namespace/release names from `deployment_uid`.
3. Ensure namespace exists (create if missing).
4. Ensure chart artifact is available and pinned (`chart_digest` preferred).
5. Reconcile release:
   - New deployment: install.
   - Existing deployment with same template: upgrade only if drift/values mismatch.
   - Desired template differs: explicit upgrade path.
6. Update `applied_template_id`, status, timestamps.

### Key operational behavior

- Queue sharding by deployment ID gives O(1) per operation independent of total instances.
- Retries are per deployment with backoff and dead-letter status, not global blocking.
- A failing Nextcloud instance does not block Mattermost instance provisioning.

## Delete flow

1. Mark deployment deleted in DB.
2. Reconciler sees tombstone desired state.
3. Uninstall Helm release.
4. Delete namespace.
5. If namespace stuck in `Terminating`, surface blocking finalizers explicitly; only allow force-finalize as privileged admin runbook.

PVC behavior is controlled by StorageClass reclaim policy and chart uninstall behavior. For normal instance deletion, volumes are expected to be deleted with namespace unless explicit retention policy is configured.

## Upgrade flow

Trigger: admin or user requests upgrade `deployment.desired_template_id = new_template_id`.

Steps:

1. Preflight:
   - Validate compatibility policy (`supports_inplace_upgrade`, admin-only flags).
   - Validate values against new schema.
2. Helm upgrade with safe flags/policies.
3. Wait for health checks.
4. On success: set `applied_template_id = desired_template_id`.
5. On failure: rollback (Helm history) or keep failed state for admin intervention (policy driven).

PVCs survive because namespace/release identity remains constant and PVC templates/claims are not deleted on regular upgrade.

## Template ingestion process

Admin flow for new product version:

1. Select upstream Helm chart version or OCI digest.
2. Create frozen `default_values` profile for Caelus.
3. Define exposed end-user value subset (safe knobs only).
4. Attach operational metadata (health checks, upgrade policy).
5. Publish immutable `ProductTemplateVersion`.

Optional helper tooling can import from existing chart defaults and produce an admin draft; publication freezes the record.

## Strengths

- Fewest moving parts.
- Strong alignment with "DB is only source of truth".
- Easy to reason about API/CLI parity.
- Fine-grained scaling control in application code.

## Weaknesses

- You own reconciliation correctness and edge-case handling.
- More custom controller code than Approach B.
- Need strong observability and idempotency tests.

---

## Approach B: Caelus + Flux Helm Controller projection

## Summary

Caelus remains source-of-truth in DB, but instead of running Helm actions directly, it projects desired state into Kubernetes CRs (`OCIRepository`, `HelmRelease`, Namespace). Flux controllers do reconciliation/drift correction.

This adds components but offloads much controller complexity.

## Architecture

```text
+-------------------+          +---------------------------+
| Caelus API / CLI  | writes   | Caelus DB (source truth) |
+-------------------+--------->+---------------------------+
          |                                |
          | project desired CRs            |
          v                                v
+----------------------------------------------------------+
| Caelus Projector/Reconciler                              |
| - renders Namespace + OCIRepository + HelmRelease specs  |
| - applies specs continuously from DB                     |
+-------------------------------+--------------------------+
                                |
                                v
                  +-------------------------------+
                  | Kubernetes + Flux controllers |
                  | source-controller             |
                  | helm-controller               |
                  +---------------+---------------+
                                  |
                                  v
                           Tenant namespaces
```

## How DB remains source of truth

Important: do not let Git become authoritative. Flux CRs are treated as projected cache of DB desired state.

Rules:

- Caelus continuously applies CR specs from DB.
- Any manual CR edits are overwritten by Caelus projector.
- Deployment lifecycle and template selection are only in Caelus DB.

## Per-deployment resources

For each deployment instance:

- `Namespace` (unique)
- Shared or per-product `OCIRepository` (chart source)
- `HelmRelease` in control namespace with:
  - `targetNamespace`: tenant namespace
  - `releaseName`: stable from `deployment_uid`
  - chart reference pinned by digest/version policy
  - values from projected inline values or referenced ConfigMap/Secret
  - remediation and drift detection policy

## Upgrade flow

- Update deployment desired template in DB.
- Caelus projector patches `HelmRelease` chart ref + values.
- Flux performs upgrade and remediation.
- Caelus reads `HelmRelease` status and records deployment status.

## Delete flow

- Mark deployment deleted in DB.
- Caelus deletes projected `HelmRelease` and namespace (or sets policy and allows owner chain).
- Flux/Helm handles uninstall retries.
- Namespace deletion completes after dependents/finalizers clear.

## Strengths

- Uses mature Kubernetes-native reconciliation for Helm lifecycle and drift correction.
- Strong visibility via standard CR status/events.
- Less custom upgrade/remediation logic to write.

## Weaknesses

- More moving parts (Flux controllers CRDs + ops overhead).
- Extra control-plane complexity for debugging ownership boundaries (Caelus vs Flux).
- Need strict discipline so DB remains authoritative over projected CRs.

---

## Detailed requirement mapping

1. Scalable provisioning:
- A: per-deployment queue workers; no global plan.
- B: per-HelmRelease reconciliation in Flux.

2. Unique namespace per instance:
- Both: deterministic namespace from immutable deployment UID.

3. Simplicity / few moving parts:
- A wins (no extra controllers).
- B acceptable if team already runs Flux.

4. Template fully describes k8s deployment:
- Both use Helm charts + values profiles (supports PVC, CronJob, ingress, jobs, etc.).

5. Immutable template versions:
- Both enforce immutable DB rows and digest-pinned artifacts.

6. New releases as new templates, no auto-upgrade:
- Both set explicit desired template; no automatic template bumping.

7. Upgrade existing instance possible:
- Both support explicit desired template change and reconciliation.

8. Data survives upgrade:
- Both preserve namespace/release identity and PVCs across upgrade.

9. Domain not immutable identifier:
- Both use deployment UUID for naming; domain is mutable desired config.

10. DB only source of truth, K8s converges:
- A direct by design.
- B via strict projection discipline from DB to CRs.

11. Leverage existing compose/helm ecosystems:
- Both are Helm-first and compatible with existing chart ecosystem.

---

## Recommendation

Recommend Approach A first.

Reasoning:

- Best match for your "few moving parts" priority.
- Strongest guarantee that DB is sole source of truth (no second declarative control plane to govern).
- Easier operational boundary for an early-stage platform.

Adopt Approach B only if you explicitly want to outsource Helm reconciliation/remediation complexity to Flux and are comfortable operating extra controllers.

---

## Operational policies to define early (both approaches)

1. Namespace naming policy:
- Example: `c-{deployment_uid_short}` (never include domain).

2. Value exposure policy:
- Allowlist only safe end-user knobs; keep dangerous values admin-only.

3. Upgrade policy per template:
- In-place allowed?
- Maintenance window required?
- Admin approval required?

4. Storage policy:
- Explicit StorageClass and backup/restore expectations per product.

5. Deletion policy:
- Default delete everything with namespace.
- Optional retention tier for paid plans (retain PVC snapshot before delete).

6. Drift policy:
- What fields are user-mutable in-cluster (ideally none).
- How aggressive auto-correction should be.

---

## Suggested DB schema evolution (high level)

`product_template_version`:

- add: `version_label`, `package_type`, `chart_ref`, `chart_version`, `chart_digest`, `default_values_json`, `values_schema_json`, `capabilities_json`, `health_checks_json`
- enforce immutability with service-level guardrails and DB constraints/triggers where possible

`deployment`:

- add: `deployment_uid`, `namespace_name`, `release_name`, `desired_template_id`, `applied_template_id`, `user_values_json`, `status`, `generation`, `last_error`, `last_reconcile_at`
- keep `domainname` mutable and uniquely constrained per active deployment if business requires uniqueness

---

## Migration strategy from current codebase

1. Introduce schema fields without changing current API behavior.
2. Add template validation and immutable publish semantics.
3. Implement reconciliation worker (Approach A) behind feature flag.
4. Backfill existing deployments with deterministic namespace/release IDs.
5. Enable create/delete reconciliation.
6. Add explicit upgrade endpoint/CLI command.
7. Add periodic drift reconciliation and status reporting.

---

## Clarifying questions for next iteration

1. Do you want to support only Helm-based templates in V1, or also raw manifest bundles/Kustomize from day one?
2. For user-initiated upgrades, do you want a per-product policy switch (`admin-only`, `user-allowed`, `user-allowed-with-guardrails`)?
3. On deletion, should default behavior be hard delete (namespace + PVC gone) or soft-retain data for a grace period?
4. Do you expect one shared ingress controller/cert-manager stack, or must templates be able to bring their own ingress/cert resources?
5. Is cross-cluster deployment in scope soon, or can we optimize design for a single cluster first?

---

## Sources

- Kubernetes namespaces: https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/
- Kubernetes finalizers: https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/
- Kubernetes persistent volumes: https://kubernetes.io/docs/concepts/storage/persistent-volumes/
- Kubernetes CronJob behavior: https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/
- Kubernetes server-side apply: https://kubernetes.io/docs/reference/using-api/server-side-apply
- Kubernetes garbage collection and owner references: https://kubernetes.io/docs/concepts/workloads/controllers/garbage-collection/
- Helm charts and schema files: https://helm.sh/docs/topics/charts/
- Helm OCI registries: https://helm.sh/docs/topics/registries
- Helm upgrade command reference: https://helm.sh/docs/helm/helm_upgrade/
- Helm uninstall command reference: https://helm.sh/docs/helm/helm_uninstall/
- Helm Go SDK (`pkg/action`): https://pkg.go.dev/helm.sh/helm/v3/pkg/action
- Flux HelmRelease docs: https://fluxcd.io/flux/components/helm/helmreleases/
- Flux OCIRepository docs: https://fluxcd.io/flux/components/source/ocirepositories/
