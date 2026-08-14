## Why

`freepod-cli` can authenticate and manage deployments, but there is no way to turn a
user's local project directory into a runnable container image. The `custom` product
accepts a tenant-supplied image reference, and nothing in the platform produces one.

This change adds the missing half: a build subsystem that accepts an uploaded project
archive and emits a digest-pinned image in the internal registry.

## What Changes

- **New `build` table and state machine** (`queued → running → succeeded | failed`,
  with `canceled` reserved but unreachable for now). Builds belong to a **user**, not
  to a deployment.
- **New `POST /api/artifacts`** — a stateless endpoint minting a presigned S3 POST slot
  on Garage. The server derives the object key from the authenticated caller, so an
  artifact is bound to its uploader by construction.
- **New `POST /api/builds`**, `GET /api/builds`, `GET /api/builds/{id}`,
  `GET /api/builds/{id}/log` — build creation from an uploaded artifact, listing a user's
  own builds, status polling, and incremental log retrieval via HTTP Range.
- **New build worker** — a separate worker process that claims queued builds, creates a
  per-build Kubernetes Job, mirrors its output into the database, adopts the Job's
  outcome, and recovers builds whose worker died or whose Job exceeded its deadline.
- **New builder image** — `railpack` + `buildctl` + rootless `buildkitd`, executing
  `railpack prepare` followed by a BuildKit gateway build against the pinned Railpack
  frontend, pushing the result to the internal registry.
- **New per-environment builds namespace** (`caelus-builds`, `caelus-builds-dev`) with a minimal ServiceAccount and NetworkPolicy: the
  build pod runs untrusted tenant code and is granted egress only to Garage, the
  registry, and DNS. It holds no database or Kubernetes credentials.
- **New configuration** for the builder image, build namespace, registry host, log cap,
  and build deadline.

Builds are deliberately **not** coupled to deployments. Nothing here triggers a rollout:
the client takes a successful build's `image` value and submits it to the existing
`PUT /api/users/{user_id}/deployments/{deployment_id}` endpoint itself. A deployment may
consume several images (for example a UI and an API), and most products consume none.

No existing endpoint, table, or behavior changes.

## Capabilities

### New Capabilities

- `build-data-model`: The `build` table, its state machine, ownership rules, and the
  identifiers linking a build to its artifact, its Kubernetes Job, and its resulting image.
- `build-artifact-upload`: The `POST /api/artifacts` slot-minting endpoint, server-side
  key derivation, and the presigned POST policy that bounds upload size.
- `build-api`: Build creation, retrieval, and the incremental log endpoint, including
  authorization and the response contract the CLI depends on.
- `build-worker`: Claiming, Kubernetes Job creation, log capture, outcome adoption, and
  recovery of builds whose worker or Job did not finish cleanly.
- `build-execution`: The contract the build container honors — artifact retrieval,
  Railpack build, image push, and how it reports its result without credentials.

### Modified Capabilities

None. The subsystem is additive: no existing requirement changes.

## Impact

**New code**
- `api/app/models/` — `BuildORM` and its read schemas
- `api/app/api/artifacts.py`, `api/app/api/builds.py` — new routers
- `api/app/services/artifacts.py`, `api/app/services/builds.py` — S3 presigning and build
  lifecycle
- `api/app/build_worker.py` — the non-blocking claim/advance/recover pass
- `api/app/cli.py` — a `build-worker` command mirroring the existing `worker` command, and
  a `caelus build` group keeping CLI and REST in lockstep
- `products/custom/builder/` — the builder image and its entrypoint script

**Modified code**
- `api/app/config.py` — build-related settings alongside the existing S3 settings
- `api/app/main.py` — router registration
- `api/alembic/versions/` — a migration for the `build` table

**Infrastructure**
- `tf/app/caelus/` — build worker Deployment, per-environment builds namespace, ServiceAccount,
  RBAC, and NetworkPolicy

**Dependencies**
- An S3 client (`boto3` or equivalent) for presigning, new to the API
- Garage, already deployed as a `tf/deps` singleton, with buckets and a lifecycle
  expiration rule already provisioned
- The internal registry, already trusted by containerd on the cluster node

**Node prerequisites (not captured by Terraform)**
- `/etc/sysctl.d/99-buildkit-userns.conf` — `kernel.apparmor_restrict_unprivileged_userns=0`,
  required for rootless BuildKit on Ubuntu 24.04
- `/etc/rancher/k3s/registries.yaml` — `insecure_skip_verify` for the internal registry

Both must be documented in a README, since a rebuilt node would fail at two separate
points with unrelated-looking errors.
