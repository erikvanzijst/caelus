# ssh-sidecar

The SSH server for the **`dev` access profile**. It rides in a tenant's app pod
and serves three different intentions on one daemon: a shell in the tenant's own
application container, the platform's PostgreSQL tooling, and a port forward to
the database pooler that opens no session at all.

`atmoz/sftp` — which the `sftp` profile still uses, unchanged — can be none of
them. It hardcodes `AllowTcpForwarding no`, forces `internal-sftp`, chroots every
session, and carries no toolbox. Two of those are not configuration problems:
chroot is incompatible with port forwarding at all, because the process that
opens a forwarded connection inherits it and has no resolver configuration
there. See [`var/ssh_access.md`](../../../var/ssh_access.md) D2–D4, D6, D14 and
D17 for the access design this implements.

## Architecture in one line

`client → sshpiper (routes by username, authenticates the user's key) → this
sidecar in the app pod → a shell in the app container, psql here, or a forward
to the pooler`.

## Runtime configuration contract

Everything per-deployment arrives as an environment variable. None of it is
secret from the pod — the trusted key is a *public* key, and the database
details are already in the application container's environment — so there is
nothing here that wants a mounted file.

**All of these are required. The container validates them and exits non-zero
naming the offending variable if any is missing or malformed**, rather than
starting a server that refuses every connection: that failure is
indistinguishable from a network fault and gets diagnosed as one.

| Variable                                             | Meaning                                                                                                                                                                                                                                          |
|------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `FREEPOD_AUTHORIZED_KEYS`                            | The public keys the server trusts, one per line. In normal operation this is the single public key of the platform's SSH edge — the tenant's own keys are checked by sshpiper on the downstream leg, never here. Validated with `ssh-keygen -l`. |
| `FREEPOD_PERMIT_OPEN`                                | The forward allowlist: whitespace- or comma-separated `host:port`. Rendered as sshd's `PermitOpen`. See *Spelling the allowlist* below.                                                                                                          |
| `FREEPOD_RELEASE_ID`                                 | The release the pod belongs to, reported by the session banner. The chart projects `caelus.dev/release-id` here through the Downward API (D17).                                                                                                  |
| `FREEPOD_LOGIN_USER`                                 | The account the SSH edge authenticates the upstream leg as: the **deployment name**. Added as a second uid-0 account at startup. See *The login account* below.                                                                                  |
| `PGHOST` `PGPORT` `PGUSER` `PGPASSWORD` `PGDATABASE` | The deployment's database, in libpq's own variable names so that a bare `psql` connects with no wrapper and no arguments. `PGSSLMODE` and `PGAPPNAME` are passed through if set.                                                                 |

The server listens on **2222**, the platform's sidecar-port convention that the
tenant NetworkPolicy admits from the SSH edge.

### The login account

The edge authenticates the upstream leg as the **deployment name**, not as
`root`. It has exactly one username convention, because on the `sftp` profile the
account `atmoz/sftp` creates *is* the release name, and the edge is deliberately
ignorant of which access profile it is addressing (see
[`ssh-auth/README.md`](../../../ssh-auth/README.md) § *Coupling*).

This server needs uid 0 — the dispatcher reads another container's process
filesystem and enters it — so rather than teaching the edge a second convention,
the entrypoint adds `FREEPOD_LOGIN_USER` as a **second uid-0 account**. `root`
stays first in `/etc/passwd`, so `getpwuid(0)` still resolves to `root` and
`whoami`, `ls -l` and friends are unchanged; the name exists only to be logged in
as, and `root` still works.

Its password field is `*`, not `!`. That distinction is load-bearing and easy to
get wrong: `!` is the *locked* marker `useradd` writes by default, and with
`UsePAM no` sshd's `allowed_user()` refuses a locked account **before it looks at
a key**, so the account would exist and every publickey attempt would still be
denied. Both mean "no password login"; only one of them permits keys.

Without this variable the container exits at startup. Getting it wrong instead —
the account absent while the server runs — produces `Invalid user <deployment>` in
this log and `Permission denied (publickey)` at the client, which reads as an
authorization problem rather than a missing account.

### Spelling the allowlist

`PermitOpen` matches the destination **as the client wrote it**, and the sidecar
resolves that name afterwards. So the value rendered here and the value the CLI
passes to `ssh -L` must agree byte for byte: `pooler.caelus.svc:6432` and
`pooler.caelus.svc.cluster.local:6432` are not interchangeable, and a mismatch
produces a refusal that reads like an authorization failure rather than a typo.
Wildcard ports are rejected — an entry that opens every port on a host is not an
allowlist.

An allowlist is required rather than recommended: tenant egress reaches the
public internet on every port, so an unconstrained forwarder would be an
authenticated open TCP relay originating from the platform's own address.

## Where a session lands

The dispatcher runs as sshd's `ForceCommand`, so every session passes through it
and no session can avoid it. Port forwarding is a `direct-tcpip` channel, opens
no session, and therefore never reaches it — which is also why the dispatcher
cannot break forwarding, and why the `sftp` profile has to disable forwarding
explicitly rather than relying on `ForceCommand` to do it.

| The client runs                      | Lands in                                                        |
|--------------------------------------|-----------------------------------------------------------------|
| `ssh <deployment>`                   | a login shell in the **application container**                  |
| `ssh <deployment> psql …`            | the **sidecar**, where the tools and the connection details are |
| `ssh <deployment> '<anything else>'` | the **application container**                                   |
| `scp` / `sftp`                       | the application container's own `sftp-server`                   |
| `ssh -N -L …`                        | nowhere — the dispatcher is not involved                        |

The platform allowlist is `psql`, `pg_dump`, `pg_dumpall`, `pg_restore` and
`pg_isready`, decided on the **command** and never on arguments a client
controls: `ssh <deployment> '/bin/echo psql'` runs `/bin/echo` in the
application container.

The allowlist routes; it does not confine. A developer who reaches this server
is authenticated and gets a root shell in the application container, which
already shares the pod's network namespace — so the sidecar is not a boundary
they are being held outside of, and `PermitOpen` constrains forwarding rather
than egress in general.

### Identifying the application container

Candidate processes are grouped by cgroup. The dispatcher's own cgroup is
excluded, and so is the pod's infrastructure process — the `pause` binary every
CRI runs. Exactly one cgroup must remain, and its lowest-numbered process is the
application.

Simpler rules are wrong in ways that matter. Under Kubernetes with a shared
process namespace PID 1 is the infrastructure container; under the test harness
there is none and the application *is* PID 1. A cgroup rule is correct in both,
which is what lets the harness prove the production behavior rather than an
approximation of it.

**Ambiguity is refused, not resolved.** More than one candidate, or none, ends
the session with a message naming the likely cause. A developer placed in the
wrong container would debug something that is not their application and draw
conclusions from it; a refusal costs them a question, and a wrong container costs
them an afternoon. Multi-container products are consequently not supported on
this profile.

### What the application image has to provide

The session runs in the tenant's own image, so what it can do is a property of
that image:

- **No shell, no session.** A distroless image ends the session with a message
  saying so. `docker exec` and `kubectl exec` fail here too; the image is the
  user's own and adding a shell to it is a change they can make. The session is
  *not* redirected into the sidecar, which would have them debugging a container
  that is not theirs.
- **File transfer needs its helper on the remote side**, exactly as `kubectl cp`
  needs `tar`: `sftp-server` for `scp` and `sftp`, `rsync` for rsync. Absent, the
  dispatcher says which one is missing.

### The banner

Interactive sessions print `freepod: release <id>` on **standard error**.

Standard output is a protocol channel for file transfer and dump streams, so a
banner written there corrupts the transfer and produces a data error far from its
cause. It is suppressed entirely when no terminal was allocated.

The release identity comes from configuration rather than from the pod's name or
from timing: during a rollout two releases' pods both serve and the connection
lands on one of them at random, so someone running `freepod shell` to find out
why their new release is broken has roughly even odds of landing in the previous,
working one and concluding nothing is wrong.

## What is in the image, and what is not

- **Debian trixie** with **`postgresql-client-18`** pinned to `18.6-1.pgdg13+2`
  from the PostgreSQL project's own apt repository, whose signing key is vendored
  here as `pgdg-archive-key.asc`. Neither distribution ships 18 in a pinnable
  release: Alpine 3.22 offers 17, and trixie's own `postgresql-client` resolves
  to `17+278`. The client must not be older than the tenant cluster's server or
  `pg_dump` aborts outright, which is not fixable from the client — which is the
  whole reason the toolbox is here rather than on the developer's laptop.
- **OpenSSH server**, configured at startup: public key only, no chroot,
  `AllowTcpForwarding local` with the allowlist, no remote forwarding, no agent
  forwarding, no X11, no gateway ports, and the dispatcher as `ForceCommand`.
- **An Ed25519 host key generated per container start**, never persisted and
  never baked in. Only Ed25519: `atmoz/sftp` generates an RSA 4096 key on every
  start, which is seconds before anything listens, and buys nothing here — the
  identity a developer verifies is the platform edge's, and the hop from the edge
  to this server does not pin this key.
- **No credential, key, password or tenant data of any kind.** Everything needed
  to authenticate a session arrives at runtime.

It runs as **root**, which is what reading and entering another container's
process filesystem requires. It takes no capability beyond what the pod grants,
mounts nothing, and needs no privileged mode. `CAP_SYS_CHROOT` is in the default
set; the pod supplies `shareProcessNamespace: true` and `CAP_SYS_PTRACE`. When
those are absent the container still starts and serves — forwarding and the
database toolbox work — and says so when a session depends on them.

## Testing

No cluster. `docker run --pid=container:<name>` reproduces the shared process
namespace, and the harness needs only docker, ssh and bash:

```bash
./test/run-tests.sh                  # build from this context and test it
./test/run-tests.sh --image REF      # test an already-built or pulled image
```

It stands up a PostgreSQL server, two forward targets, an ordinary application
container, a distroless one, and a sidecar with no application beside it at all,
then asserts every behavior above. The negative cases are each a security
property rather than a feature, so they are asserted rather than assumed:
password authentication refused, unknown key refused, unlisted forward
destination refused, remote and agent forwarding refused, a command's
metacharacters never expanded by the dispatcher, and startup aborted for each
missing or malformed input.

If the harness runs inside a container on the same docker daemon — a devcontainer
— published ports land on the daemon's host and are unreachable from it, so it
joins the test network and addresses containers directly instead. That is
detected, not configured.

## Build and publish

**amd64 only**, as [`products/custom/builder`](../../custom/builder/) is: the
cluster node is amd64 and multi-arch is an explicit non-goal, so the Dockerfile
fails the build on any other architecture rather than producing an image whose
PostgreSQL client cannot exec.

The version lives in [`VERSION`](./VERSION) and nowhere else. It is the single
input the publish target reads:

```bash
./scripts/build-images.sh --ssh-sidecar
```

**A published tag is never overwritten.** A change to the image is a new version:
bump `VERSION`, publish, and repoint the chart that names it. The script enforces
this rather than trusting anyone to remember — it refuses to push a version the
registry already holds.

**CI publishes it on merge to master**, running the same target with
`--skip-if-published`, which turns that refusal into "nothing to do". So a push
happens exactly when `VERSION` names a version the registry does not have, and
every other merge is a no-op rather than a red build. Publishing by hand is still
the right move when you want to get an image out ahead of a merge — and the bare
`--ssh-sidecar` keeps failing loudly there, which is what you want when you
thought you had bumped the version and had not.

The sidecar is deliberately *not* in `--all`. The images that target covers are
platform Deployments on moving tags, re-pushed on every merge and picked up by
restarting their pods; an immutable tag in that set would fail every merge that
did not bump it.

**The image's version is its own, independent of the chart's.** The coupling runs
one way: the image reference lives in the chart, so no new image reaches a
deployment except through a chart upgrade — but charts change constantly for
reasons that never touch the image. Making the two numbers agree would mean
either rebuilding a byte-identical image on every chart edit or letting them
drift while still claiming to agree, and a promise that holds most of the time is
worse than no promise.

Publishing does not roll anything out. `./scripts/rollout.sh` restarts the
platform's own Deployments and knows nothing about tenant pods; this image
reaches them through a chart version bump fanned out by the reconciler.

### First publish

The first publish is a manual one: the GHCR package is created by its first push
**at GHCR's default visibility, which is private**, and CI's `GITHUB_TOKEN`
cannot change that. Nothing in this platform configures an `imagePullSecret`
(see [`tf/app/README.md`](../../../tf/app/README.md) § *Non-secret variables*, which
documents the same trap for the API and UI images), so a private package fails
the pull tenant-side with an `ImagePullBackOff` that names no cause. Set the
package to public after the first push and confirm with an unauthenticated pull.

## Two obligations this places on the chart that adopts it

1. **A render assertion tying the chart's referenced tag to `VERSION`**, in the
   shape of `api/tests/test_sftp_service_reachability.py`. Without it a chart can
   reference a version nobody built.
2. **`imagePullPolicy: IfNotPresent` on the sidecar container**, stated
   explicitly. With an immutable tag, tag and content are one to one, which makes
   caching correct rather than accidental — today's `caelus-sftp` sets no policy
   at all, and on `atmoz/sftp:alpine` that means the version a tenant runs is
   whichever one their node cached first.
