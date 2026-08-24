## Why

The `freepod` CLI has no way to pass environment variables or secrets to a running pod.
The only channel today is `deployment.user_values_json`, and it cannot carry a secret:
every value in it is readable back through the API, is written into
`deployment_release.values_json` forever, and reaches the Helm values — which the
provisioner logs in full at INFO and which Helm persists into a Secret in the tenant's
own namespace.

Fly, Railway, Vercel and Heroku all treat runtime configuration as a first-class
resource with CRUD, where secret values are write-only and never echoed. Adding that as
a second channel without a story for the first would leave two ways to get state into a
pod. This change introduces one channel, and gives `user_values_json` a narrower and
genuinely different job: configuring the chart, not the process environment.

## What Changes

- **A `vars` sub-resource on every deployment**, addressed by deployment, **phase** and
  key: `GET`/`PATCH`/`PUT` on
  `/api/users/{user_id}/deployments/{deployment_id}/vars/{phase}` and `GET`/`DELETE` on
  `.../vars/{phase}/{key}`. The only phase is `runtime`; the segment exists because
  `(deployment, phase, key)` is a var's identity rather than a filter over a set, so a
  second phase can be added without reshaping the resource. A var marked `sensitive` is
  write-only: reads **omit** the `value` field entirely rather than masking or nulling it.
- **Two new tables.** `deployment_var` is append-only and immutable, with NULL
  `value_encrypted` as a deletion tombstone; `release_var` binds a frozen snapshot of
  the effective vars to each release at creation time, which is what makes a release
  reproducible.
- **Values are encrypted at rest**, including non-sensitive ones, under a rotatable
  Fernet keyring. Each row records the *fingerprint* of the key that encrypted it, so
  rotation never invalidates history.
- **Routing lives in the existing schema, as a per-property marker.**
  `values_schema_json` gains `x-caelus-target: chart | runtime`, `x-caelus-sensitive`,
  and a root-level `x-caelus-vars-additional`. The server derives a chart projection
  and a vars projection by partitioning the schema's top-level `properties`. There is
  **no second schema** to author and no second namespace to police.
- **A product that does not opt in accepts no vars**, with no per-product boilerplate:
  the derived vars projection of a schema with no runtime-marked properties is a closed
  empty object, and a template with no schema at all rejects vars outright.
- **`vars` is accepted, write-only, on deployment create and update**, so a first
  release can run with vars rather than necessarily running without them.
- **The reconciler materializes a release's snapshot into one Kubernetes Secret** per
  deployment and passes only the Secret's *name* to Helm under `caelus.vars.secretName`.
  Values never travel through the Helm values document.
- **CLI: `freepod var list|get|set|rm`**, applying by default and staging with
  `--stage`, built on a new `freepod deploy --no-build` that mints a release from the
  deployment's current image.
- Vars deliberately **do not** auto-apply on write to a deployment the caller did not
  ask to deploy; `DeploymentRead.pending` reports when head differs from what is
  running.

Not breaking. `user_values_json` keeps its current behavior and every existing catalog
schema keeps working unchanged, because `x-caelus-target` defaults to `chart`.

## Capabilities

### New Capabilities

- `deployment-vars-data-model`: the append-only `deployment_var` table, the
  `release_var` snapshot, head resolution, per-deployment write serialization,
  encryption at rest, key identity by fingerprint, rotation, and startup verification
  of the keyring.
- `deployment-vars-schema-routing`: the `x-caelus-target` / `x-caelus-sensitive` /
  `x-caelus-vars-additional` markers, derivation of the chart and vars projections,
  the rules a marked property must satisfy, and closed-by-default behavior.
- `deployment-vars-api`: the `vars` sub-resource, the wire shape, omission of sensitive
  values on read, merge/replace/delete semantics, `pending`, limits, reserved names,
  admin visibility, and validation errors that do not echo the offending value.
- `deployment-vars-reconciliation`: materializing a release's snapshot into a
  Kubernetes Secret, projecting only its name into the Helm values, `envFrom` ordering
  against platform-injected variables, and emitting nothing when a deployment has no
  vars.
- `cli-vars`: `freepod var list|get|set|rm`, apply-by-default with `--stage`, sensitive
  handling in output, and round-trippable `--json`.

### Modified Capabilities

- `deployment-create-contract`: deployment create and update accept a write-only `vars`
  field, merged rather than replaced, and `DeploymentRead` gains `vars` (head) and
  `pending`.
- `deployment-release-ledger`: creating a release also freezes the deployment's
  effective vars into `release_var`, in the same transaction as the release row.
- `deployment-release-api`: a release read reports the vars it ran with, under the same
  omission rule for sensitive values.
- `product-catalog-format`: a catalog file's `template.values_schema` may carry the
  routing markers, and their legality is checked when the catalog is loaded.
- `cli-deploy`: `freepod deploy --no-build` mints a release from the deployment's
  current image, carrying the applied release's `build_id` and image forward.

## Impact

- **Data:** two new tables (`deployment_var`, `release_var`) and one Alembic migration.
  No existing table changes. No data migration: nothing moves off `user_values_json`.
- **Backend:** new `api/app/services/vars.py` (head resolution, encryption, validation)
  and `api/app/api/` routes; `api/app/services/deployments.py` (accept `vars`, bind the
  snapshot); `api/app/services/template_values.py` (projection derivation, non-echoing
  validation errors); `api/app/services/reconcile.py` (Secret materialization and the
  `caelus.vars` override); `api/app/services/catalog.py` and `templates.py` (marker
  meta-validation); `api/app/config.py` (`CAELUS_VAR_ENCRYPTION_KEYS`).
- **New dependency:** `cryptography` (Fernet).
- **Deployment:** the encryption keyring is rendered from `secrets.auto.tfvars` into a
  Kubernetes Secret and mounted into **both** the API and `caelus worker`; the worker
  decrypts a snapshot to build the tenant Secret. Introducing a key is a two-phase
  rollout (distribute, then promote) — see `design.md` § 5.5.
- **Charts:** the `custom` chart consumes `caelus.vars.secretName` via `envFrom`, with
  the vars Secret ordered *before* platform-injected sources. Curated charts are
  untouched.
- **CLI:** new `freepod var` command group; `freepod deploy` gains `--no-build`.
- **UI:** `UserValuesForm` carries the markers through `flattenSchema` and partitions
  its submission into `user_values_json` and `vars`. Sensitive fields render as
  password inputs that submit *no* `value` when untouched.
- **Depends on a separate change:** the server-side rule that an update omitting
  `build_id` inherits it from the applied release when the image is unchanged. Today
  `update_deployment` writes `build_id=update.build_id` unconditionally
  (`api/app/services/deployments.py:580`), so any client that omits it drops the build
  link. This change's CLI passes `build_id` explicitly and so is correct on its own;
  the general fix is out of scope here because it changes behavior for existing
  clients. See `design.md` § 8.4.
- **Out of scope, tracked in `design.md` § 14:** retention/hard deletion of rotated
  ciphertext (GDPR/DPA); `caelus.releaseId` adoption in curated charts, which is a
  prerequisite for any curated product later moving to vars; migrating curated products
  off `user_values_json`; rollback to a previous release.
