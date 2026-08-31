## Context

See `proposal.md` § Why. `var/ssh_access.md` D2, D3, D4, D6 and D11 describe the profile
split and the `dev` profile's behavior; the sidecar image and the resolver are both
shipped.

**Two artifacts, one of each kind, and their names now say so.** `products/_lib/caelus-sftp`
is a Helm library chart — `Chart.yaml` and named templates that consumer charts render.
`products/_lib/ssh-sidecar` is a container image build context — a `Dockerfile`, an
entrypoint, a dispatcher and a test harness. The chart renders a container spec; the image
is what that spec's `image:` field points at. Nothing is merged and there is one of each.

They become `ssh-sidecar-chart` and `ssh-sidecar-image`. Naming them for what they *are*
rather than for what they relate to is the point: the previous pairing left a reader unable
to tell a chart from a Dockerfile by its directory name, which is how a maintainer who
wrote both came to ask whether they were duplicates. The image's published name and tag do
not change — only the directory holding its build context.

Five facts were read from the merged code rather than assumed, and each removed work this
change would otherwise have had to do.

1. **The reconciler already projects everything the `dev` profile needs.**
   `caelus.sftp.platformPublicKey` is injected for *every* deployment unconditionally;
   `caelus.database.host` and `.port` are already **the pooler's**, not the server's;
   `caelus.database.secretName` names the Secret carrying the `PG*` variables; and
   `caelus.releaseId` is already both a value and a pod label. **No reconciler change is
   required.**
2. **`custom`'s `caelus` values block is `additionalProperties: true`**, so it already
   accepts the platform public key it currently ignores. Adopting the profile is not
   blocked on a schema change, though the new keys should be declared rather than left to
   the permissive default.
3. **The edge derives the upstream address by string convention**, `-sftp` appended to the
   deployment name, with the port from a single fleet-wide setting. There is no per-
   deployment stored address and no profile awareness.
4. **The reachability allowlist already admits `error`.** A deployment whose application
   is broken is still reachable, deliberately, for the same reason the Service publishes
   not-ready addresses. The `dev` profile needs no change here — the behavior it depends
   on most is already correct.
5. **The current rendering trigger excludes `custom` by construction.** The chart contract
   requires that a product with no exposable PVC render no sidecar, no Secret and no
   Service. `custom` has no PVC, so the trigger has to change before it can have a
   sidecar at all.

## Goals / Non-Goals

**Goals:**

- A `custom` deployment's owner can open a shell in their application container, attach a
  debugger to their process, and forward a local port to their database, using stock
  `ssh`.
- The `sftp` profile's behavior is unchanged for the six products on it.
- The edge remains ignorant of profiles.

**Non-Goals:**

- `freepod` commands. Access works over plain `ssh` from the moment this lands; the client
  wraps it next.
- Making `pg_dump` work through the pooler, which is a pooler-mode question tracked
  separately.
- Any second profile-selection mechanism. A product declares one profile; there is no
  per-connection or per-user choice.
- Preserving access across the cutover.

## Decisions

### The naming convention moves to `-ssh`, in one coordinated release

The convention is `-sftp` today, embedded in the resolver's SQL and in every chart's
Service name. It stops being true the moment a sidecar offers a shell and a tunnel, and
the confusion is permanent if left.

Moving it is a hard cutover: a chart rendering `-ssh` while the resolver expects `-sftp`
produces a deployment that authenticates and then reaches nothing, and the reverse is
identically broken. A fallback in the resolver — try `-ssh`, then `-sftp` — would work and
is exactly the moving part built to be deleted that this line of work has been removing.
So there is no fallback, and the fleet moves in a window.

Doing it now rather than later is the cheap moment: every chart is being republished for
the profile change anyway, so the rename rides an existing fan-out instead of buying its
own.

**It also fixes a wart for free.** The previous change left every SFTP credentials Secret
carrying an inert `password` key that Helm's three-way merge cannot remove, because the
API server folds `stringData` into `data` and the merge computes a removal against a field
that no longer exists. That was recorded as not worth a six-product fan-out to fix. The
rename changes the Secret's name, which is the one fix that does work, and this change is
already paying the fan-out.

### The profile is which helpers a chart calls, not a parameter it passes

There is no `profile` string. The library exposes two helper sets — `ssh-sidecar.sftp.*`
and `ssh-sidecar.dev.*` — over one shared `ssh-sidecar.service` helper, and a product chart
calls the set it was written for.

Two alternatives were considered and both model something that does not vary. Passing
`profile` at each include site, or reading an `ssh.profile` value, gives every chart a
parameter whose domain is one value: a product chart is authored for exactly one profile
and cannot render the other, because its pod template either shares its process namespace
or does not, and either mounts data volumes into a sidecar or does not. Neither collapses
the three existing call sites — `resources`, `sidecar`, `volumes` — into one; each must
still be written consistently, and the pod-level settings are a fourth place to agree.

The value form has a further problem. Which profile a deployment runs is security-relevant:
`dev` grants the tracing capability and a shell into the application container. Values are
the tenant-influenced channel, so keeping that decision out of values entirely is stronger
than admitting it and then defending it with a schema.

What this costs is that a chart's call sites must agree — calling `sftp.resources` beside
`dev.sidecar` renders an incoherent chart. That is caught by rendering each product and
asserting the emitted set is one profile's, which the before-and-after diff over the six
existing consumers already does.

The Service is deliberately *not* duplicated per profile. It is the one object the edge
depends on, and it must be identical for both; a single shared helper enforces that where
a per-profile copy would only ask two authors to keep agreeing.

### The rendering trigger becomes the declared profile

A chart renders SSH resources because its product declares a profile. The old rule — key
it on exposable PVCs — was right for a profile that exists to serve files and wrong as a
general rule.

The `sftp` profile keeps a PVC precondition of its own: a product on that profile with
nothing to expose renders nothing, because its sidecar would offer an empty session. That
is a property of the profile, not of the chart contract, which is where it now lives.

### Pod Security `baseline` refuses `CAP_SYS_PTRACE`, so the debugger is deferred

**Found during implementation, and it invalidates part of what follows.** Every tenant
namespace carries `pod-security.kubernetes.io/enforce: baseline`, applied by the
reconciler (`api/app/network_policy.py`). `baseline` forbids *every* non-default
capability, so a pod requesting `CAP_SYS_PTRACE` is refused at admission —
`violates PodSecurity "baseline:latest"` — and never schedules. The Helm upgrade then
fails on a readiness timeout that names nothing about capabilities.

Nothing in the analysis below is wrong about what the capability does or how it is
bounded; the gap is that it was never checked against admission. D5 examined AppArmor
and concluded no node configuration was needed, which is one layer below this.

So the profile ships **without the capability**. What that costs is exactly `strace`,
`gdb` and `py-spy`. It costs nothing else: entering the application container chroots
into `/proc/<pid>/root`, which the default set already permits via `CAP_SYS_CHROOT`, and
`shareProcessNamespace` is itself permitted under `baseline`. The shell, file copy, the
PostgreSQL toolbox and port forwarding all work.

Granting it later means raising the namespace's enforcement level to `privileged` for
products on this profile — a reconciler change, and a change to what the platform
guarantees about tenant pods, so it is decided on its own rather than folded in here.
Worth noting when that is picked up: PSS constrains *who may create pods*, and on this
platform only the reconciler does, from platform-authored charts. A tenant never submits
a pod spec — `custom`'s values schema admits `hostname` and `image` and nothing else.

### The pod would grant `CAP_SYS_PTRACE` and shares its process namespace, and nothing else

`shareProcessNamespace` makes the application's filesystem reachable at `/proc/<pid>/root`
and its environment at `/proc/<pid>/environ`. `CAP_SYS_PTRACE` is what `strace`, `gdb` and
`py-spy` need. Together they are the debugging feature.

`CAP_SYS_ADMIN` is not taken, and neither is `hostPID`. Process identifiers resolve within
the namespace that shares them, so a pod-scoped shared namespace bounds tracing to the
tenant's own containers running the tenant's own code. Every warning that treats
`CAP_SYS_PTRACE` as a container breakout vector assumes the node's namespace is shared;
that distinction is the whole reason this is acceptable, and it should survive review.

The capability goes on the sidecar alone. The application container gains nothing.

An earlier draft expected AppArmor to block intra-pod tracing and budgeted a custom node
profile for it. Measured on the cluster, both containers run the default containerd profile
under enforcement and tracing succeeds, because the profile's peer clause matches when
tracer and tracee carry the same profile name. The invariant that follows is worth
carrying into review: **both containers must keep the same AppArmor profile.** Giving the
application container its own would break tracing with a permission error that mentions
nothing about AppArmor.

### The sidecar image is a system value, pinned exactly

Same category as the placeholder image: platform-supplied, tenant-unsettable, referenced by
an exact version. A tenant-settable reference here would let a tenant substitute the
container that holds the platform's trusted key and enters their application container.

A moving tag is refused for the reason the image's own contract already gives — the version
a pod runs would become a function of when it last restarted and what its node had cached.

### The release identity comes from the pod label, not from the value

`caelus.releaseId` is available directly as a Helm value, which would be one fewer
indirection. The sidecar's published contract instead takes it from the `caelus.dev/release-id`
pod label through the Downward API, and this follows that.

The label is what the log pipeline already relabels into the release stream, so taking the
banner's value from the same place guarantees a session and the logs of the pod it landed
on agree. Two independent projections of the same fact can disagree; one cannot.

### The forward allowlist is rendered from the database values already present

`caelus.database.host` and `.port` are the pooler's, so the allowlist is rendered from
values the chart already receives, with no new projection.

The spelling matters more than it looks: the allowlist is matched against the destination
as the client wrote it, so the value the chart renders and the address the platform tells
users to forward to must be byte-identical. That makes the documented address and the
rendered value one fact with two readers, which is a thing to state rather than to leave
to coincidence.

### The database is optional, and its absence costs only the database

An earlier draft of this design made the sidecar's `PG*` variables required and noted the
resulting coupling as a stated precondition rather than defending it in code. That was
wrong: a shell in the application container is worth having with or without a database,
and the coupling would have surfaced as a pod that never starts for the first product to
adopt the profile without relational storage — a failure with nothing in it to point at
the cause.

So the toolbox and the forward are facilities the profile offers, not preconditions it
imposes. The variables are optional **as a set**: absent, the chart renders no allowlist
and no database environment, the image writes `PermitOpen none`, and the dispatcher
declines `psql` and its siblings by name. Every other session path is untouched.

A *partial* set still aborts startup, and that asymmetry is the point. Nothing supplied
means a product without a database; something supplied means the projection that should
have supplied the rest is broken, and a container that started anyway would surface that
inside `psql`, at the moment someone needed the database and furthest from the cause.

`custom` has relational storage today, but that is a property of the product rather than
of the profile, and it will not stay the only product on it.

## Risks / Trade-offs

- **The rename is a hard cutover with no fallback** → the fleet is unroutable between the
  resolver's release and the last chart repoint. Accepted deliberately; a fallback is the
  moving part this change would otherwise have to carry forever.
- **Six charts republished and repointed, three by operator action** → the recurring trap
  in this codebase: nothing in the diff reveals a forgotten `ProductTemplateVersion`
  update. Mitigated only by making them separate, explicit tasks.
- **`CAP_SYS_PTRACE` on a tenant pod** → bounded to the pod by the shared namespace being
  pod-scoped. The residual risk is a future change to `hostPID` or to the AppArmor profile
  quietly widening or breaking it, which is why both are stated as invariants rather than
  as configuration.
- **A shared process namespace is symmetric** → the application container can also see the
  sidecar's processes and files. The sidecar holds one public key and its own generated
  host key, so there is nothing there to take; that remains true only while no secret is
  ever mounted into it.
- **`deployment.name` is treated as globally unique by the resolver** while the schema
  guarantees uniqueness only per namespace. This change adds every `custom` deployment to
  the routable set and so widens the surface. It is an availability bug, not a
  confidentiality one: the resolver joins keys on the *selected* row's owner, so a
  mis-selected deployment refuses the connecting user rather than admitting them to
  someone else's. Worth fixing at the source, and not in this change.

## Migration Plan

1. **Directory names**: image build context to `ssh-sidecar-image`, library chart to
   `ssh-sidecar-chart`, so each says which kind of artifact it is.
2. **Library chart**: split into the two helper sets over a shared Service helper, move
   rendered names to `-ssh`, keep the `sftp` profile's behavior byte-identical apart from
   names.
3. **`custom`**: adopt the `dev` profile — sidecar, pod-level settings, values and schema.
4. **Resolver**: upstream address convention to `-ssh`; version bump and publish. Not yet
   deployed.
5. **In the window**: deploy the resolver, then republish and repoint all seven charts.
   Between those two steps the fleet is unroutable, which is what the window is for.

**Rollback**: revert the resolver to the previous version and repoint every chart to its
previous version. Whole-fleet, in a window, like the rollout — and it depends on old chart
and image versions never having been overwritten.

## Open Questions

- **Whether the `caelus.sftp.*` values key should be renamed to `caelus.ssh.*` in the same
  window.** It is one reconciler line and seven chart schemas, and leaving it means a key
  named `sftp` feeds a profile named `dev`. It changes no behavior, so it can ride this
  window or a later one.
- **Whether the `sftp` profile should eventually move onto the platform image too.** It
  would end the two-image maintenance burden; it is a capability-neutral consolidation and
  a poor thing to attempt in the same change that introduces the second profile.
