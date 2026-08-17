## 1. Terraform: the scoped provisioning credential

- [x] 1.1 In `tf/deps/garage/`, mint a non-expiring admin token scoped to exactly the
      operations provisioning performs (`ListBuckets`, `CreateBucket`, `GetBucketInfo`,
      `UpdateBucket`, `ListKeys`, `CreateKey`, `GetKeyInfo`, `DeleteKey`, `AllowBucketKey`),
      write it into the `garage-keys` Secret, and expose it as a sensitive output. Scope
      excludes `CreateAdminToken`/`UpdateAdminToken`.
      **Correction to this task's original premise:** the token canNOT be "read back the same
      way the existing S3 credentials are". `CreateAdminToken` returns `secretToken` once and
      `GetAdminTokenInfo` has no field for it, so the Secret is the only store of record. The
      script reads the Secret first and re-mints only when the value is missing, which keeps a
      re-run a no-op and self-heals a lost Secret by rotating.
- [x] 1.2 Add a `tf/app` variable for the token plus the public S3 endpoint and region, and
      wire them into the **reconcile worker's** environment. Document the deps → app handoff
      in `tf/deps/README.md` alongside the existing credential-reading instructions.
      **Correction:** this task originally said "the API deployment's environment", and that
      is where the wiring first went — wrongly. `DeploymentReconciler` runs in
      `caelus-worker`, which had never needed `caelus-s3` because before this change only the
      API (presigned URLs) and the build worker (artifact fetch) used S3. Caught at rollout,
      not by any test: it is Terraform wiring with no code-level seam.

## 2. Garage admin API client

- [x] 2.1 Add a Garage admin client under `api/app/services/` covering the operations in 1.1.
      Keep it a thin transport over the admin API — no deployment or reconcile concepts.
- [x] 2.2 Give every call read-before-write semantics: bucket lookup by global alias, key
      lookup by name, each returning absence rather than raising.
- [x] 2.3 Unit-test the client against a stubbed transport, including the case where a lookup
      finds nothing and the case where the store returns a non-2xx body.

## 3. Configuration

- [x] 3.1 Add settings for the admin API URL, the scoped admin token, the public S3 endpoint,
      the region, the `maxObjects` cap, and the delete expiry window (1 day). Deliberately **no
      default quota setting** — the quota comes from the plan and an unresolvable one is an
      error, not a fallback.
- [x] 3.2 Ensure absent settings fail only on the path that needs them, following the
      precedent set by `builder_image` — migrations, tests and the local CLI must still be
      able to construct settings.

## 4. Provisioning service

- [x] 4.1 Add a service that, given a deployment, ensures its key, bucket, permission grant
      and quota exist, and returns the values the reconciler needs. Verify each of the four
      steps independently so an interrupted run resumes rather than concluding it is done.
- [x] 4.2 Name the bucket `dep-<deployment-id>` as a global alias; never create a local alias.
- [x] 4.3 Resolve the quota from the plan, fail-closed: raise a clear error when the allowance
      is absent or zero, or the deployment has no subscription. No fallback value. Set
      `maxSize` and `maxObjects` together, as the store requires.
- [x] 4.4 In the same `UpdateBucket` call, set permissive `corsRules` with `ExposeHeader`
      including `ETag`. Note the request body is the store's XML-derived PascalCase shape
      (`AllowedOrigin`, `AllowedMethod`, `AllowedHeader`, `ExposeHeader`), not camelCase.
- [x] 4.5 Add the teardown path: delete the key **first**, then set the object-expiry lifecycle
      rule on the bucket. Do not delete the bucket and do not enumerate its objects.
- [x] 4.6 Unit-test provisioning idempotency (a second run rotates nothing), resumption from a
      key-without-bucket state, grant repair, quota re-assertion after a plan change, the
      fail-closed error for all three unresolvable-quota cases, and that teardown deletes the
      key before it sets the expiry rule.

## 5. Secret delivery

- [x] 5.1 Add a provisioner method that upserts a Secret into a tenant namespace, built on the
      existing `KubeAdapter.apply_manifest`.
- [x] 5.2 Test that the secret access key appears in the Secret and appears nowhere in the
      merged Helm values or in emitted log records.

## 6. Reconciler integration

- [x] 6.1 Call the provisioning service from `_reconcile_apply`, after
      `ensure_tenant_isolation` and before `helm_upgrade_install`, gated on the product
      template's `system_values.objectStorage.enabled`.
- [x] 6.2 Write the credentials Secret, then add a `_build_object_storage_overrides` contributor to
      `_build_system_overrides` emitting only `caelus.objectStorage.{enabled,bucket,endpoint,region,
      secretName}` — never the secret access key.
- [x] 6.3 Call the teardown path from `_reconcile_delete`, before the namespace is removed.
      Make it tolerant of a deployment that never had storage.
- [x] 6.4 Test that a non-opted-in product provisions nothing and emits no storage block, and
      that a tenant cannot enable storage through user values.

## 7. Chart contract

- [x] 7.1 Add `caelus.objectStorage` to `products/custom/chart/values.yaml` and
      `values.schema.json` as optional properties, so the chart renders both with and without
      them.
- [x] 7.2 Project the Secret into the app container with `envFrom`, exposing the conventional
      `AWS_*` names plus the endpoint variables and the bucket name, alongside the existing
      `PORT`. Render nothing when storage is absent.
- [x] 7.3 Set `automountServiceAccountToken: false` on the pod spec.
- [x] 7.4 Published `custom-0.3.0` to `oci://registry.home/helm`
      (`sha256:c46edf43b172db9bbee9b2c100a707f52823cd796d96a06938884555f82a7ef9`); the catalog
      points at 0.3.0. 0.1.0 and 0.2.0 are untouched — 0.2.0 was published first and
      superseded when the opt-in flag moved from `caelus.objectStorage.enabled` to a
      first-class top-level `objectStorage.enabled`, which changed the chart's interface.
      Added a `.helmignore` along the way: without it `helm package` swept the previous
      release's own `.tgz` into the new one.
- [x] 7.5 Add `helm template` cases covering render with storage, render without storage, and
      schema validation for both.

## 8. Product opt-in

- [x] 8.1 Add `objectStorage.enabled: true` and the new chart version to
      `products/catalog/custom.yaml`, and run the catalog linter.

## 9. End-to-end verification

Run against production Garage through the public endpoint, driving the real shipped
`ensure_object_storage` / `teardown_object_storage` with a throwaway deployment id, plus direct
inspection of the one live `custom` deployment's provisioned state. The probe bucket and key
were removed afterwards.

- [x] 9.1 `boto3.client("s3")` with **no arguments**, only the injected environment: put/get/list
      round-tripped against the deployment's own bucket.
- [x] 9.2 Denied on another deployment's bucket by global alias **and** by raw internal
      identifier, and on the platform's `dev` artifact bucket; `ListBuckets` returned only its
      own bucket, so other deployments' ids are not discoverable through the S3 API.
- [x] 9.3 Anonymous GET of a presigned URL returned the object. Cross-origin preflight returned
      **HTTP 200** with `Access-Control-Allow-Origin: *`, the five methods, and
      `Access-Control-Expose-Headers: ETag` — so browser-direct multipart uploads work.
- [x] 9.4 A 2 MiB write against a 1 MiB quota was refused by the store with `AccessDenied`; no
      platform code participated.
- [x] 9.5 Teardown deleted the key, the bucket kept its `dep-<id>` alias, both lifecycle rules
      were applied at 1 day, and the revoked key was denied. Objects were still readable by an
      operator granting a fresh key to the alias, confirming the expiry-window recovery path.
- [x] 9.6 Reconciler-driven delete, on a real dev deployment (`custom-user-app-4mvl7s`) with a
      non-empty bucket (2 objects / 4163 bytes), triggered through the tenant `freepod delete`
      flow. Worker log confirms the ordering the design depends on:
      `Revoked object storage key` at 22:59:53, then `Set expiry … days=1` at 22:59:53, then
      `Deleted namespace` at 23:00:36 — revoke first, so no live key could strip the rule off.
      Whole delete reconcile took 44s against a 300s budget despite the bucket being non-empty.
      Afterwards: key gone, namespace and credentials Secret gone, bucket retained its
      `dep-<id>` alias with **no keys at all**, both lifecycle rules present at 1 day, and the
      objects were still recoverable by granting a fresh key to the alias.

## 10. Documentation

- [x] 10.1 Document the environment contract for tenants in `products/custom/README.md`,
      including the path-style note for SDKs that do not select it automatically.
- [x] 10.2 Record in `api/README.md` how provisioning fits into the reconcile path, and state
      the provisioning credential's blast radius explicitly rather than leaving it implied.
- [x] 10.3 Note in `tf/deps/README.md` that tenant buckets are named `dep-<deployment-id>`,
      that drained buckets are expected residue, and that a future reaper needs a database
      session rather than only an admin token.
