## Context

See `proposal.md` § Why, and `var/ssh_access.md` D3, D4, D6, D14 and D17 for the access
design this image implements.

Four facts, each measured rather than assumed, shape the build.

1. **Neither distribution ships PostgreSQL 18 in a pinnable release.** Alpine 3.22 offers
   `postgresql17-client` and no 18; Debian trixie's own `postgresql-client` resolves to
   `17+278`. The PostgreSQL project's own apt repository does provide it for trixie, at
   `18.6-1.pgdg13+2` — the same 18.6 the tenant cluster is pinned to.
2. **The dispatcher is fully testable without a cluster.** `docker run
   --pid=container:<name>` reproduces the shared process namespace, and from an Alpine
   container so joined, `chroot /proc/<pid>/root` yields the target's filesystem and
   executables. Verified end to end.
3. **`chroot` is the mechanism for entering the application container**, needing only
   `CAP_SYS_CHROOT` from the default capability set. `nsenter` and `CAP_SYS_ADMIN` were
   considered and rejected in `var/ssh_access.md` D4.
4. **Chroot on the SSH server itself is incompatible with forwarding**, because the
   forwarding process inherits it and loses its resolver configuration. Measured; see
   `var/ssh_access.md` D3.

## Goals / Non-Goals

**Goals:**

- One artifact that a chart can adopt with no further behavior decisions.
- Every behavior in the two specs demonstrable with `docker` and `ssh` alone, so this
  change is verifiable in CI and by a reviewer with no cluster access.
- Failure modes that name their cause, because every one of them will be met by someone
  whose application is already broken.

**Non-Goals:**

- Any chart, `Pipe`, pod spec, or cluster wiring. The pod-level facilities this image
  uses — a shared process namespace and `CAP_SYS_PTRACE` — are granted elsewhere.
- The `sftp` profile. It keeps `atmoz/sftp` and is untouched.
- Making `pg_dump` work through the connection pooler. Shipping the correct client
  version removes one of the two obstacles; the other is the pooler's transaction mode
  and is addressed separately (`var/ssh_access.md` D15).

## Decisions

### Debian base with the PostgreSQL project's apt repository

Alpine would be smaller, and it is not available: no pinnable Alpine release carries a
PostgreSQL 18 client. Debian trixie plus PGDG yields exactly 18.6, matching the server.

The repository must be pinned by its signing key and the package by version, so a rebuild
does not silently move to 19 when it is released. Tracking the server's major version is
a deliberate, visible bump, not something that happens because a build ran on a Tuesday.

**amd64 only**, as `builder` already is: the cluster node is amd64 and multi-arch is an
explicit non-goal. The build declares the platform rather than inheriting the builder's,
so a build on a developer's arm64 machine produces the image the cluster will run.

### The dispatcher is a POSIX shell script that never evaluates the request

The dispatcher runs as `ForceCommand`, so it sees the requested command in the
environment. It must never `eval` that string or interpolate it into another command
line: it is attacker-influenced input arriving at an authenticated boundary.

What it does instead is what `sshd` itself would do — hand the string to a shell **in the
target**, quoted, as a single argument. That is how `ssh host 'ls | wc -l'` is expected to
behave, so the pipeline still works; the difference is that it is the application
container's shell that interprets it, never the sidecar's dispatcher.

A shell script is chosen over a compiled program because the logic is a handful of
branches and the image needs no additional runtime to host it. That choice is only safe
with the no-`eval` discipline above, so the tests must include command strings full of
metacharacters and assert that the dispatcher did not act on them.

### The application container is identified by cgroup, not by process order

Candidate processes are grouped by their cgroup. The dispatcher's own cgroup and the
cgroup of the pod's infrastructure process are excluded. If exactly one cgroup remains,
its lowest-numbered process is the application; otherwise the dispatcher reports
ambiguity and enters nothing.

Simpler heuristics — "the lowest PID that is not ours", "the first process that is not
`pause`" — are wrong in ways that matter. Under Kubernetes with a shared process
namespace, PID 1 is the pod's infrastructure container; under the docker test harness
there is no such process and the application *is* PID 1. A cgroup-based rule is correct
in both, which is what lets the test harness prove the production behavior rather than an
approximation of it.

Refusing on ambiguity rather than picking is deliberate. A developer placed in the wrong
container would debug something that is not their application and draw conclusions from
it; a refusal costs them a question, and a wrong container costs them an afternoon.

### Configuration arrives as environment variables, validated by the entrypoint

Everything per-deployment — the trusted public key, the permitted forward destinations,
the release identity, and the database connection details — is supplied as environment
variables. The entrypoint validates them, renders the server configuration, and only then
starts the server.

Environment variables rather than mounted files because none of this is secret from the
pod: the trusted key is a *public* key, and the database connection details are already in
the application container's environment. Reusing the ordinary PostgreSQL environment
variables means the client tools need no wrapper — invoked bare, they connect to the right
database.

The database details must reach the **sidecar's own** environment rather than being read
from the application process, because a developer connects precisely when the application
is broken, and details read from a crash-looping process would be unavailable exactly
then.

The platform's own inputs take a `FREEPOD_` prefix — `FREEPOD_AUTHORIZED_KEYS`,
`FREEPOD_PERMIT_OPEN`, `FREEPOD_RELEASE_ID` — following the product's rename from Caelus.
The `CAELUS_` prefix elsewhere in the platform is legacy and is renamed separately; new
surfaces do not extend it. Note this supersedes the literal `CAELUS_RELEASE_ID` shown in
`var/ssh_access.md` D17, which names the variable and not the pod label
`caelus.dev/release-id` that feeds it — the label is an existing projection and is
unchanged.

The database details keep their ordinary libpq names (`PGHOST`, `PGPORT`, `PGUSER`,
`PGPASSWORD`, `PGDATABASE`) rather than taking a prefix, because that is what makes a bare
`psql` connect with no wrapper.

Validation happens before the server starts so that a misconfiguration is a container that
exits with an explanation, not a container that runs and refuses every connection. The
second is indistinguishable from a network fault and will be diagnosed as one.

### An Ed25519 host key, generated per container, never persisted

Baking a host key into the image would give every deployment the same one. Persisting it
would need a volume for no benefit. Generating one per start is right, and generating
*only* an Ed25519 key is what keeps the port opening promptly — the `atmoz/sftp` image
generates an RSA 4096 key on every start, which is seconds of delay before anything
listens.

This is safe because the client never pins this key: the identity a developer verifies is
the platform edge's, which is stable, and the hop from the edge to this server does not
pin the sidecar's key.

### The banner goes to standard error, and only with a terminal

Standard output is a protocol channel for file transfer and for dump streams. A banner
written there corrupts the transfer and produces a data error far from its cause — the
kind of bug that costs a day. So the banner is written to standard error, and suppressed
entirely when no terminal was allocated.

The release identity it reports comes from configuration, not from the pod's name or from
timing, because the pod name says nothing about which release it belongs to during a
rollout — which is the situation the banner exists for.

### A shell-less application container is a failure, not a fallback

An earlier draft placed the user in a sidecar session when the application image had no
shell, with the application filesystem reachable underneath. That is rejected.

The session would land in a container that is not the user's, and the one line explaining
so is read once and forgotten; everything after it — `ls`, the package manager, the
absent process — describes the sidecar. A developer who misses that line debugs the wrong
image. `docker exec` and `kubectl exec` both fail outright here for the same reason, so
the failure is also the behavior a developer already expects, and the fix is entirely
theirs: add a shell to the image.

So the dispatcher detects the condition, names it, and exits. The sidecar remains
reachable only through the platform command allowlist, which is what that allowlist is
for.

### The image version is its own, and the chart pins it exactly

`atmoz/sftp:alpine` is not the precedent to follow here. It is a mutable third-party tag,
and the sidecar template sets no `imagePullPolicy`, so a non-`latest` tag defaults to
`IfNotPresent` — the version a tenant runs is whichever one that node cached first. Two
nodes can differ, and nothing converges them. That is survivable for an upstream that
pushes rarely and serves read-only SFTP; the failure rate of a mutable tag scales with how
often it is written, and this is an image the platform expects to push often.

So the tag is immutable, and the chain is pinned twice over: a product pins the library
chart's version, and the library chart pins the image's version in its values.

The two version numbers are deliberately **not** the same number. The coupling runs one
way — the image reference lives in the chart, so no new image reaches a deployment except
through a chart upgrade — but the reverse is not true at all: charts change constantly for
reasons that never touch the image. Lockstep would mean either rebuilding a byte-identical
image under a new tag on every chart edit, or letting the two drift apart in practice
while still claiming to agree. A promise that holds most of the time is worse than no
promise, because someone will read the chart version and infer the image.

A `VERSION` file in the build context is the single input the publish target reads. It is
not read out of the chart: that would invert the dependency and make the chart the source
of truth for what to build. Never-overwrite is enforced by the target refusing to push a
tag the registry already holds, not by a README asking people to remember.

That refusal is also what keeps the image out of the `--all` target CI runs on every
merge, since an immutable tag there would fail every merge that did not bump `VERSION`.
CI publishes it as a separate step under `--skip-if-published`, which turns the refusal
into a no-op, so a push happens exactly when the version is new. The alternative — leaving
the publish entirely manual — has one failure mode with no detector: a bumped `VERSION`
merges, nobody pushes, and the chart that later pins it fails tenant-side with an
`ImagePullBackOff`. The render assertion below catches a chart pointing at the wrong
version; nothing catches a version that was never pushed.

What that leaves is drift in the other direction — a chart referencing a version nobody
built. That belongs to the chart change, and the repo already has the pattern for it:
`api/tests/test_sftp_service_reachability.py` holds a render assertion across all six
consumers, and the equivalent here asserts the rendered sidecar image tag equals this
`VERSION` file. The chart change should also set `imagePullPolicy: IfNotPresent`
explicitly, which with an immutable tag makes caching correct rather than accidental.

## Risks / Trade-offs

- **A new image the platform must patch** → `atmoz/sftp` is tracked upstream; this one is
  not, and it carries an SSH server and a PostgreSQL client, both of which get security
  updates. Mitigated only by pinning explicitly so that a rebuild is a deliberate,
  reviewable act. This cost was accepted when the two profiles were split.
- **PGDG pins the image to a third-party apt repository** → a build now depends on
  `apt.postgresql.org` being reachable and its signing key being current. Mitigated by
  pinning the key and the package version; the failure is a build failure, not a runtime
  one.
- **The dispatcher is shell code in the authentication path** → quoting mistakes here are
  command injection. Mitigated by the no-`eval` rule, by keeping the script small, and by
  tests that specifically attack it with metacharacters rather than only exercising the
  happy path.
- **The docker test harness differs from the cluster in one way** → there is no
  infrastructure container at PID 1. The cgroup rule is correct in both, but a rule that
  accidentally depended on that difference would pass the tests and fail in production.
  Mitigated by testing the exclusion of the infrastructure cgroup explicitly rather than
  inferring it from a passing shell.
- **Running as root** → required to read another container's process filesystem and enter
  it. Bounded by taking no capability beyond what the pod grants, requiring no privileged
  mode, and never mounting anything.

## Migration Plan

1. Build context and entrypoint: base, pinned PGDG client, server configuration rendering,
   startup validation.
2. Dispatcher and its tests, driven entirely by `docker` and a local `ssh` client.
3. Documentation of the runtime configuration contract — the interface the chart change
   will target.
4. Build and publish the first version to the platform registry.

**Rollback**: nothing consumes the image, so rollback is not publishing it, or publishing
a corrected version under a new tag. No deployment is affected either way.

## Open Questions

- **Should the image also carry a small set of general debugging tools** beyond the
  PostgreSQL client — a process inspector, a network tool? Purely additive: it changes no
  requirement here and can be decided when the first real debugging session shows what is
  missing. Note that with no sidecar fallback, such tools are reachable only through the
  platform command allowlist, so adding one is also a decision to widen that list.
