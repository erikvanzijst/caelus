## Why

A `custom` deployment has **no durable storage of any kind**. The pod's filesystem is
ephemeral, the chart mounts no PVC, and nothing survives a restart, a redeploy or a
rescheduling. A tenant who builds an app that accepts a file upload has nowhere to put it.

The platform already runs a Garage S3 instance as a `tf/deps` singleton, and Garage turns out
to carry exactly the primitives this needs — per-`(key, bucket)` permissions, per-bucket
quotas, and declarative object expiry — so the gap can be closed without adding a dependency.
This change auto-provisions a **private bucket and a dedicated access key for every
storage-enabled deployment**, and injects the credentials into the pod so that an unmodified
S3 SDK works with no configuration.

**Recorded honestly: object storage is not persistence.** It does not make a SQLite file
survive a restart, it has no POSIX semantics, no `open()`, no seek-write and no rename, and
every read is an HTTP round trip. It serves applications *written for* object storage —
uploads, generated assets, exports — and it serves them well. Applications that want a
filesystem, and applications that want records, are separate unmet needs (a PVC and a
`DATABASE_URL` respectively) and are explicitly **not** in scope here.

## What Changes

- The reconciler provisions object storage for any deployment whose product template opts in,
  as part of the existing apply path: create an access key, create a bucket, grant that key
  read+write on that bucket alone, and apply the plan's storage quota.
- Credentials are written directly to a Kubernetes Secret in the deployment's namespace and
  are **never passed through Helm values**, which are logged at INFO and persisted in the
  Helm release Secret.
- The bucket is named `dep-<deployment-id>` as a Garage **global alias**. The deployment id is
  a `uuid4` primary key: immutable, globally unique, unguessable, and already the join key the
  platform uses everywhere else.
- The `custom` chart gains an `envFrom` block projecting the Secret into the app container as
  the conventional `AWS_*` / `S3_BUCKET` variables, alongside the existing `PORT`.
- `custom` opts in via `template.system_values.objectStorage.enabled` in its catalog entry. No
  tenant-facing toggle, no user-values schema change, no deployment form field.
- The plan's `storage_bytes` becomes the bucket quota, enforced by Garage rather than by
  platform accounting code. A **platform default applies when the plan is silent**, so a
  deployment without a subscription cannot obtain an unbounded bucket.
- On deletion the reconciler revokes access synchronously (delete the key) and hands
  reclamation to Garage by setting a short object-expiry lifecycle rule on the bucket. No
  synchronous enumerate-and-delete of an unbounded object set inside the reconcile budget.
- Terraform mints a **scoped, non-expiring admin token** for the Caelus API in `tf/deps`, so
  the API never holds Garage's master token.
- An empty-bucket reaper is explicitly **out of scope**. Drained buckets are metadata-only and
  their global alias names the deployment, so a later sweep is a straightforward join against
  the deployments table.

## Capabilities

### New Capabilities

- `deployment-object-storage`: How a per-deployment bucket and access key are provisioned,
  scoped, quota-limited and reclaimed on the shared Garage instance, and what isolation
  between two deployments' buckets actually rests on.
- `object-storage-chart-contract`: The contract between the platform and a tenant image — the
  Secret the reconciler writes, the environment variables a chart projects from it, and the
  guarantee that an unmodified S3 SDK works against them without configuration.

### Modified Capabilities

None.

`plan-storage-enforcement` is deliberately **not** modified, despite object storage reading the
same `storage_bytes` field. Every requirement in that capability is about *projecting* the
plan into Helm values for a chart to consume, and every one of them remains literally true.
Object storage is enforced by the reconciler calling Garage directly, never through a chart, so
it is a second consumer of the field on a separate path rather than a change to the first. In
particular, that capability's "absent means the chart falls back to its own default" semantics
must **not** be inherited here — an absent quota cannot mean an unbounded bucket — so the
fail-closed rule is stated in `deployment-object-storage`, where the bucket lives.

## Impact

- **`api/app/services/`** — a new Garage admin API client, and a new system-override
  contributor in `DeploymentReconciler._build_system_overrides`.
- **`api/app/provisioner.py`** — a method to upsert a Secret into a tenant namespace, built on
  the existing `KubeAdapter.apply_manifest`.
- **`api/app/config.py`** — Garage admin URL, scoped admin token, public S3 endpoint, default
  quota settings.
- **`products/custom/chart/`** — `envFrom` on the app container, plus `caelus.objectStorage.*` in
  `values.yaml` and `values.schema.json`.
- **`products/catalog/custom.yaml`** — the opt-in flag.
- **`tf/deps/garage/`** — mint and output the scoped admin token; **`tf/app/`** — consume it.
- **Not affected: `deployment-network-isolation`.** Verified empirically rather than assumed —
  a live tenant pod under the current baseline NetworkPolicy already reaches
  `https://blob.freepod.eu` and receives a Garage S3 response. The in-cluster ClusterIP is
  blocked (it falls under the `10.0.0.0/8` egress exclusion) and stays blocked. No policy
  change is required by this proposal.
- **Capacity.** The Garage data PVC is 20 GiB and is shared with the `dev` and `prod` artifact
  buckets. Garage enforces quotas per bucket and does not prevent the sum of quotas from
  exceeding the disk, so the number of storage-enabled deployments is bounded by operator
  attention until that PVC grows.
