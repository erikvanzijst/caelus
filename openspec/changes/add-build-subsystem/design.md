## Context

See `proposal.md` — Why. Requirements live in `specs/`; this document covers the choices
behind them.

Constraints that shaped the approach:

- **The cluster is a single k3s node** — a 4-thread Intel i3-8109U VM with 23 GiB RAM, no
  swap, and a 58 GB disk, which also runs Postgres, Keycloak, Traefik, and every tenant
  workload. Anything long-running and heavyweight competes directly with tenant traffic.
- **Build input and build steps are tenant-controlled.** A project's dependency install
  hooks and build commands execute during a build. Everything downstream of the upload
  must treat that code as hostile.
- **Garage is already deployed** as a `tf/deps` singleton, with per-environment buckets,
  access keys, and a lifecycle expiration rule already provisioned.
- **The internal registry is already trusted by containerd** on the node, and the API's
  ServiceAccount already holds broad cluster permissions.
- **The `custom` product already exists**, consuming an `image` user value of the form
  `{user_id}@{digest}` and asserting in its chart that the prefix matches the
  reconciler-injected `caelus.owner.id`.

The mechanics below were validated end to end on the cluster before this was written:
rootless BuildKit starting and executing a real build, `railpack prepare` plus a gateway
build pushing to the registry, and the kubelet pulling and running the result.

## Goals / Non-Goals

**Goals:**

- A build is a standalone transformation from project archive to container image, usable
  without reference to any deployment.
- No credential reachable by tenant code.
- Failure modes are recoverable by a subsequent worker pass, not only by human
  intervention.
- No new long-lived infrastructure component.

**Non-Goals:**

- Automatically deploying a successful build. The client wires build output to a
  deployment itself.
- Retrying failed builds, superseding queued ones, or capping per-user concurrency.
- Cancellation. The state exists; nothing reaches it.
- Multi-architecture images.
- Build caching between builds.

## Decisions

### D1: Builds are a standalone subsystem, not a sub-resource of deployments

Builds are owned by a user and carry no deployment reference. The client submits a
successful build's image to the deployment update endpoint itself.

*Alternative considered:* nesting builds under deployments (`/deployments/{id}/builds`)
and having a successful build automatically enqueue a reconcile.

Rejected because the relationship is not one-to-one in either direction. Most products —
every curated one — never build anything, and a single deployment may need several images
(a UI and an API). Nesting would encode a cardinality that is wrong from the outset, and
auto-deploying would hard-wire a relationship that is genuinely a composition made by the
client.

The cost is that the client performs the final update itself, and therefore handles the
deployment's own preconditions. That is acceptable; the alternative embeds build-specific
behavior in the generic deployment path.

### D2: Railpack on BuildKit

*Alternatives considered:* Kaniko, Cloud Native Buildpacks via kpack, Nixpacks.

**Kaniko** is out twice over: its upstream repository was archived in June 2025, and more
fundamentally it cannot execute a Railpack build at all. Railpack emits BuildKit LLB
directly rather than a Dockerfile — a deliberate departure from its Nixpacks predecessor —
so there is no Dockerfile artifact for a Dockerfile interpreter to consume.

**kpack** is the strongest alternative and builds with unprivileged Kubernetes primitives,
which is a better isolation story than anything BuildKit offers. It was rejected because
it wants to own the build lifecycle through its own controller and CRDs, duplicating an
orchestrator this codebase already has, and because its automatic rebuild-on-base-image-
change would move tenant images outside the reconcile queue's control. Worth revisiting if
fleet-wide rebuilds against a patched base image ever become a requirement.

**Nixpacks** would restore builder freedom by generating a Dockerfile, at the cost of
adopting the superseded predecessor and materially larger images.

### D3: BuildKit runs inside each build's own pod, not as a shared daemon

Each Job pod runs its own rootless `buildkitd` for the duration of one build.

*Alternative considered:* a long-lived rootless `buildkitd` StatefulSet in `tf/deps`, with
builds connecting to it as clients.

Rejected on isolation. Rootless BuildKit under Kubernetes requires
`--oci-worker-no-process-sandbox`, whose documented consequence is that build containers
can kill and potentially trace processes in the daemon's namespace. With a shared daemon
that reach spans concurrent tenants' builds. With a per-build daemon, the only thing a
tenant can reach is a daemon already executing their own code on their own behalf — the
same flag, a completely different blast radius, determined entirely by lifetime.

Three further consequences fall out: there is no shared build cache to poison across
tenants, a runaway build's resource use dies with its Job, and the change introduces no
new `tf/deps` component at all.

The cost is a cold cache per build. Accepted for now; a per-owner registry cache is the
natural remedy if build times become a problem, and it is deliberately excluded here.

### D4: `railpack prepare` plus the BuildKit gateway frontend, not `railpack build`

The container runs `railpack prepare` to emit a build plan, then invokes a BuildKit
gateway build against the Railpack frontend image, exporting directly to the registry.

This is not a preference. Railpack's `build` subcommand can only export a filesystem to a
local directory — it cannot push — so the two-phase form is the only route to a registry.
It is also what upstream documents for production.

The frontend image is pinned by digest and must be version-matched to the `railpack`
binary in the builder image, because the build plan is a contract between them. Pinning
here is about that coupling, not about supply chain: mirroring the frontend into the
internal registry was considered and rejected, since a digest is content-addressed and the
project already consumes public images by tag elsewhere.

### D5: Upload is three phases, and the artifact endpoint is stateless

Mint a slot, upload directly to Garage, then create the build.

*Alternative considered:* creating the build first in an `awaiting_upload` state and
returning its upload credentials.

Rejected because it produces rows for uploads that never complete — a user who closes
their laptop mid-push leaves state to reap. Creating the build only after a successful
upload means an abandoned upload leaves nothing behind but an object that the bucket
lifecycle rule expires on its own. The extra round trip buys the absence of a whole state
branch and its cleanup path.

*Alternative also considered:* proxying the upload through the API. Rejected — it puts
hundreds of megabytes through a single-replica API pod for no benefit.

### D6: Presigned POST, not presigned PUT

*Alternative considered:* a presigned PUT URL, which collapses the credential into a single
string and would let the response be a bare `Location` header.

Rejected because only POST carries a policy document, and only a policy can express
`content-length-range`. Without it there is no way to bound upload size at the store;
enforcement would fall to the client, or to a proxy body limit that is easy to
misconfigure and invisible when absent. The ergonomic cost — the credential is a set of
form fields rather than a URL — is worth an abuse limit that actually holds.

### D7: The client sends an artifact identifier, never a URL or key

The server composes the object key from the authenticated caller and the artifact
identifier.

*Alternative considered:* the client submits the artifact URL it uploaded to, and the
server validates that the URL's path carries the caller's own prefix.

Rejected because it makes URL parsing load-bearing for authorization, which then has to
withstand traversal sequences, percent-encoded traversal, userinfo-based host confusion, a
wholly substituted host, and prefix collisions between numeric identifiers such as `123`
and `1234`. Deriving the key server-side removes the check entirely rather than hardening
it: the caller's identity is in the key by construction. There is nothing to bypass
because there is nothing to validate.

### D8: One `build` table, no separate job table

Build state lives on the build row; there is no analogue of `deployment_reconcile_job`.

The reconcile job table exists for retry accounting, deduplication, and lease re-claiming.
Builds need none of these: a failed build is terminal, concurrent builds are expected, and
a stranded build is failed rather than retried. `job_id` doubles as the lease token, and
`started_at` as the lease clock.

This is still a lease, just a simpler one — worth naming plainly so its behavior is not a
surprise later.

### D9: The build container has no credentials and reports through its termination status

The container receives only a time-limited artifact credential. It reports its produced
image via the pod termination message; the worker performs every database write.

*Alternative considered:* the build script updating the build row directly.

Rejected outright. Tenant code executes in that container with full access to its
environment — a `DATABASE_URL` there is a Postgres connection handed to every tenant, no
subversion of the build script required. It would also require egress to Postgres,
dismantling the network restriction the Job design depends on.

The termination message is purpose-built for this: a small structured result from a
terminating container, surfaced through pod status, requiring no credential and capped at
4 KiB — ample for one image reference.

*Alternative also considered:* a log sentinel parsed by the worker. Workable, but couples
result extraction to log formatting, and tenant build output could forge the sentinel.

### D10: One non-blocking worker pass mirrors logs and advances every running build

The worker is a single repeating pass. Each iteration claims queued builds up to an
in-flight limit, then for every `running` build re-reads its Job's output into the log
column, checks the Job's state, and finalizes or recovers it.

*Alternative considered:* a sidecar container, or a companion pod, shipping logs into the
database. A sidecar is worse than it appears: containers in a pod share a network
namespace, so a sidecar able to reach Postgres implies the tenant's build container can too
— NetworkPolicy is per-pod and cannot separate them. A companion pod avoids that but costs
a second pod per build plus its own credentials and RBAC.

*Alternative also considered, and initially chosen:* having the worker **follow** the Job's
log stream, so that log capture, completion detection, and result collection happened in
one flow — the stream ends exactly when the container exits.

That was rejected on reflection because blocking on a stream for the duration of a build
makes the worker unable to do anything else. Recovery of stranded builds (D11) then has to
run somewhere else — a thread, a companion process, a CronJob — and every one of those
options introduces a *second writer* to the same build row, racing the follower over
whether a build is `succeeded` or unrecoverable. At an in-flight limit of 1, a single long
build would suspend recovery entirely, which is exactly when it is most needed.

Polling is less elegant and strictly more robust: one loop, one writer, no concurrency
primitives, and liveness by construction rather than by scheduling discipline.

Two consequences are accepted deliberately. Captured output lags by the poll interval,
which is immaterial when the client polls the API on a similar cadence. And the log column
is a **mirror** of the Job's current output rather than an appended stream — re-read in
full each pass, which is idempotent, needs no offset bookkeeping, and lets a restarted
worker resume with no notion of its own position. Because a container runtime may rotate
older output away, a shorter read must never shorten what is stored.

A useful by-product: concurrency becomes a configured in-flight count rather than a worker
process count, which is a better knob for a single constrained node.

### D11: Every running build is reconciled on every pass, not only overdue ones

*Alternative considered:* examining only builds whose `started_at` exceeds the deadline.

Rejected as both less correct and no simpler. A worker restart mid-build would otherwise
strand a build that is succeeding perfectly well in Kubernetes, and the narrow rule would
eventually fail it despite its image sitting in the registry. Since the pass must query
the Job either way, widening the selection turns a worker redeploy into a gap in captured
output recovered on the next pass, instead of a lost build.

With D10's non-blocking pass this needs no separate scheduling: visiting every `running`
build *is* the pass, so recovery cannot be starved by work the worker is otherwise doing.

### D15: The build deadline is enforced by Kubernetes, with the worker as backstop

The Job carries `activeDeadlineSeconds`; the worker only intervenes for a Job still active
past the deadline plus a grace period.

*Alternative considered:* making the worker the sole enforcer — detecting an over-running
build during reconciliation and deleting its Job.

Rejected because it only works when a worker is alive and reconciling. Kubernetes is the
one participant guaranteed to be present, so it should hold the authoritative deadline; a
build whose worker died still gets terminated on time rather than running until something
notices.

This also answers what the worker does when a healthy build over-runs: nothing special.
The Job terminates, and the next pass records the failure through the ordinary outcome
path — the same code path as any other failed build.

### D12: The log is a capped `bytea` column in Postgres

Range-based polling requires random access into a resource that is still growing, which a
Kubernetes log stream cannot provide — something must accumulate it.

Postgres is the right home despite blob storage being available: this is bounded output
queried by substring, not a large binary object. Keeping it in one place also avoids an
offset discontinuity at the moment a build finishes, which a "stream while running,
persisted once terminal" split would introduce exactly while a client is mid-poll.

Appends are batched rather than per-line.

The column is **`bytea`, not `text`**. Container output is a byte stream produced by
tenant-controlled code, and this subsystem must not assume anything about its contents:

- Postgres `text` cannot hold a NUL byte at all. A build that writes one to stdout — any
  build that emits binary, which is a one-line change for a tenant — would fail its log
  `UPDATE` on *every* worker pass, wedging itself permanently. This is the decisive
  argument: it is a tenant-triggerable, unrecoverable stuck build.
- Storing text would otherwise force a decode at ingest, and every option there is bad.
  Strict decoding turns malformed output into a worker crash; replacement is lossy *and
  changes the byte length*, which silently shifts the Range offsets clients poll with and
  muddles D10's rule that a shorter read must never shorten the stored log.
- The cap is a byte count, so truncation is an exact slice rather than
  encode/slice/decode around a character straddling the boundary.

The endpoint still serves `text/plain; charset=utf-8`: UTF-8 is what a client should
assume when decoding, not something the server verifies or enforces. Nothing in the API
layer encodes or decodes the log — HTTP's byte offsets and the column's own length are
the same number.

### D13: The image is a flat digest reference; the tag exists only as an anchor

A successful build exposes `image` as the flat string `{user_id}@{digest}`.

*Alternative considered:* a structured `{tag, digest}` object.

Rejected because the flat string is byte-identical to what the client must submit as the
product's `image` user value. Any structure forces client-side reassembly, and reassembly
is where the two subsystems drift apart on format — which already happened once during
design, when the separator moved from `/` to `@`.

The push still uses a tag derived from the build identifier, which is never exposed. Its
purpose is to anchor the manifest: an untagged manifest is removable by a registry garbage
collection pass run with `--delete-untagged`, which would silently break every deployment
referencing it by digest. It also keeps images enumerable through the registry's tag
listing and records which build produced which image.

### D14: Ownership of an image is enforced by the consuming chart

The `custom` product's schema constrains the shape of `image` with a pattern, and its chart
asserts that the prefix matches the reconciler-injected `caelus.owner.id`.

*Alternative considered:* validating in `update_deployment` by looking up a build owned by
the caller whose image matches.

The lookup is the more robust check — it proves the platform produced the reference rather
than merely where it sits — but it puts build-specific knowledge into the generic
deployment path that every product shares. The chart-side assertion keeps that path
untouched, and is sound because system overrides are merged last and cannot be shadowed by
tenant values. The cost is that a forged reference fails late, as a deployment error rather
than a rejected request. Since malformed values fail the schema pattern immediately, the
late path is reached essentially only by a deliberate attempt.

This decision is already implemented in the `custom` product and is recorded here because
it is why this subsystem performs no image authorization of its own.

### D16: The builds namespace is per environment, not shared

Each environment gets its own: `caelus-builds` in prod, `caelus-builds-dev` in dev —
asymmetric, matching the existing scheme (`caelus`/`caelus-dev`, `login`/`login-dev`,
`sshpiper`/`sshpiper-dev`).

*Alternative considered:* one shared `caelus-builds` namespace for both environments, on
the grounds that a build Job is ephemeral and environment-agnostic.

Rejected for three reasons, the weakest of which is the one that prompted the question.

**A shared namespace has no Terraform owner.** `tf/app` uses workspaces with separate
state per environment. Declaring the same namespace in both means the second `apply`
collides with an existing object and a `terraform destroy` in dev deletes prod's build
namespace. A workspace-per-environment layout has no way to express "this resource is
shared", which is presumably why every other app-level namespace is already split.

**Shared would let the dev worker delete prod's build Jobs.** The build worker's Role is
namespaced, and it *deletes* Jobs — that is how the deadline backstop (D15) works. One
namespace means dev's RoleBinding grants Job deletion over prod's builds, so a dev worker
pointed at the wrong database, or a bug in the deadline arithmetic, reaches production.
Splitting makes that impossible by construction rather than by care. This repo already met
the same shape once: `rbac_name = "caelus-api-${local.ns_caelus}"` carries the comment
"Cluster-scoped RBAC object names must be unique per deployment."

**Troubleshooting.** Build Jobs are named `build-{build_id}` from a UUID, so a shared
namespace interleaves both environments' Jobs with nothing in the name to tell them apart,
and `kubectl delete jobs --all` during a dev debugging session would take prod's with it.

The cost is a second namespace, ServiceAccount, and NetworkPolicy — all generated from the
same workspace-parameterized code, so no duplication in source. `builds_namespace` keeps
the prod name as its code default and is overridden per environment through the ConfigMap,
exactly as `sshpiper_namespace` already is.

### D17: All builds share their environment's namespace, rather than one namespace per build

Concurrent builds — including builds belonging to *different tenants* — run as pods in the
same namespace.

*Alternative considered:* a dedicated namespace per build, created by the worker before the
Job and torn down after, on the grounds that build pods run adversarial code and should not
share anything.

Rejected, but the reasoning is not "namespaces are enough" — it is that **a namespace is
not the thing providing the isolation here**. Kubernetes namespaces are not a network
boundary: pods in different namespaces reach each other freely unless a NetworkPolicy says
otherwise. What actually separates two concurrent builds is:

- **no ingress rule at all**, so nothing can connect to a build pod;
- **no intra-namespace egress rule** — deliberately unlike the tenant baseline policy,
  which does allow it — so a build pod cannot connect *out* to another build pod either;
- **`automountServiceAccountToken: false`** plus a ServiceAccount with no Role anywhere, so
  there is no Kubernetes credential to enumerate or manipulate anything with;
- **separate pods**, so separate PID namespaces and separate emptyDirs, which is what keeps
  `--oci-worker-no-process-sandbox` (D3) confined to a tenant's own build.

Verified by probe from one build pod to another in the shared namespace: the peer pod, the
API server, Postgres, and the Caelus API are all unreachable, while the registry remains
reachable.

Per-build namespaces would add almost nothing to that list, and would cost something real:
the NetworkPolicy would stop being a Terraform artifact — reviewed, drift-detected, and
already present — and become a runtime object the worker mints moments before each build.
That introduces a **fail-open window** that does not exist today: a Job whose namespace
policy failed or lagged would start unfenced. Namespace teardown is also asynchronous and
can wedge on finalizers, which on a single node is real operational noise, where
`ttlSecondsAfterFinished` currently handles all cleanup.

Two things would change this decision, and both are worth naming so the trigger is
recognized rather than rediscovered:

- **Per-build Secrets.** If builds ever need mounted credentials — private dependency
  registries, deploy keys — a shared namespace puts every tenant's secret in one place, and
  namespace-scoped Secrets become the natural boundary. This is the likely trigger.
- **Any RBAC grant to build pods.** A Role in this namespace applies to every build in it.
  D9 refuses to grant build pods anything, so this is only a risk if that is revisited.

Neither approach addresses kernel-level container escape: both pods share the node kernel,
and a Kubernetes namespace is not a boundary against that. The mitigation there is rootless
BuildKit (already), and a sandboxed runtime or a dedicated build node if it ever matters
more.

## Data model

One new table. Types follow `DeploymentORM` and `DeploymentReconcileJobORM` in
`api/app/models/core.py` — a UUID primary key via `sa_column=Column(Uuid, primary_key=True)`,
and status as a plain indexed `str` backed by module constants rather than a database enum,
matching how deployment and job statuses are already stored.

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| `id` | `UUID` | no | Primary key, `default_factory=uuid4` |
| `user_id` | `int` | no | FK `user.id`, indexed. The owner; never accepted as request input |
| `artifact_id` | `str` | no | Identifier issued when the upload slot was minted. The object key is derived from `user_id` + this, never stored as a URL |
| `status` | `str` | no | Indexed. `queued` \| `running` \| `succeeded` \| `failed` \| `canceled` |
| `created_at` | `datetime` | no | `default_factory=_utcnow` |
| `started_at` | `datetime` | yes | Set by the **worker** when it claims the build |
| `finished_at` | `datetime` | yes | Set by the **worker** when it records a terminal status |
| `job_id` | `str` | yes | Kubernetes Job name. Written only *after* the Job exists, so a null here on a `running` build is unambiguously recoverable |
| `image` | `str` | yes | Set by the **worker** on success, to `{user_id}@{digest}`. Flat string, never a structured object (D13) |
| `log` | `bytes` (BYTEA) | no | Defaults to empty. A mirror of the Job's output, rewritten each pass (D10), capped per `build-api`. Bytes rather than text so tenant output cannot wedge the write (D12) |

Indexes and constraints:

- Partial unique index on `artifact_id` where `status in ('queued','running')`, declaring
  **both** `sqlite_where` and `postgresql_where`. This mirrors
  `uq_open_reconcile_job_per_deployment`; the dual declaration is required because tests run
  on SQLite and production on Postgres, and this repo has already had to fix that asymmetry
  once (`cross-database-partial-index-parity`).
- Index on `status`, which every worker pass filters on.

## Risks / Trade-offs

**Build load competes with tenant workloads on a single node** → Builds are bounded by
resource limits, an activeDeadlineSeconds, and the build worker's process count, which
should start at 1. This is a real limitation rather than a solved problem: a dependency
install can saturate the node's four threads for minutes.

**A worker restart interrupts output capture** → The build itself survives and is advanced
by the next pass (D11), and because the log is re-read in full rather than appended, the
stored output self-heals. The only loss is freshness during the gap.

**Node prerequisites are not captured in version control** → Two node-level settings are
required — the userns sysctl for rootless BuildKit and containerd's registry trust — and a
rebuilt node would fail at two separate points with unrelated-looking errors. Mitigated by
documenting both in a README as part of this change; not fully solved, since nothing
enforces them.

**A 10 MiB log column is compressed out-of-line by Postgres, so each poll decompresses the
whole value** → Tolerable at one client polling one build. If log polling becomes slow,
chunk the log into rows rather than tuning around it.

**Registry pulls use `insecure_skip_verify`** → The registry presents a valid certificate
for a name it is not addressed by. Out of scope here and tracked separately; giving the
registry a certificate-valid, internally resolving name would retire both this and the
node-level configuration it requires.

**Untrusted archives are extracted inside the build pod** → The pod is the sandbox, but
extraction is still constrained (traversal rejected, size and entry count bounded) rather
than relying on the sandbox alone.

**The build container can trace processes in its own pod** → A documented consequence of
`--oci-worker-no-process-sandbox`. Contained by D3: the only processes in reach belong to
that tenant's own build.

## Migration Plan

Purely additive — a new table, new endpoints, a new worker, and a new namespace. No
existing table, endpoint, or behavior changes, so there is no data migration and no
compatibility window.

Deployment order:

1. Apply the `build` table migration.
2. Publish the builder image to the internal registry.
3. Apply infrastructure: the environment's builds namespace, ServiceAccount, NetworkPolicy, and
   the build worker Deployment.
4. Roll out the API with the new endpoints and settings.

Rollback: scale the build worker to zero and remove the routers. Queued and running builds
stop being processed; nothing else is affected, since no other subsystem reads build state.
The table can be left in place.

## Open Questions

- **Build worker concurrency.** Starting at 1 is clearly right for the current node. The
  correct steady-state value depends on observed build durations and node headroom, and can
  be tuned without touching the specs or the task breakdown.
- **Extracted-size and entry-count limits for archive extraction.** The requirement that
  they exist is specified; the numbers can be chosen during implementation from the
  configured upload cap.
