## Why

The SSH access design (`var/ssh_access.md`) gives `custom` deployments a sidecar that is
three things at once: a port-forward endpoint for a developer's database client, a shell
into their own application container, and a place the platform's PostgreSQL tooling
already lives. `atmoz/sftp` cannot be any of them — it hardcodes `AllowTcpForwarding no`,
forces `internal-sftp`, chroots every session, and carries no toolbox.

Two of those are not configuration problems. Chroot is incompatible with port forwarding
at all: a spike measured `connect_to <host>: unknown host (Try again)` because the process
that opens a forwarded connection runs inside the chroot, where there is no resolver
configuration. And a local `pg_dump` older than the tenant cluster's PostgreSQL 18 aborts
outright, so the dump has to run server-side, which means shipping the client here.

This change builds that image and nothing else. It is a self-contained artifact,
buildable and testable with `docker` and a local `ssh` client, with no cluster involved —
which is exactly why it is separated from the chart work that will consume it.

## What Changes

- A new platform-owned container image providing an OpenSSH server configured for the
  `dev` profile: public-key authentication only, local port forwarding constrained by an
  explicit allowlist, no chroot, and a forced dispatcher.
- A **session dispatcher** that decides where each session lands: a shell in the
  application container, a command in the sidecar's toolbox, or a plain forwarded
  connection that never reaches it at all.
- **PostgreSQL client tooling at the tenant cluster's major version**, so `psql` and
  `pg_dump` run server-side and are never subject to a developer's local client version.
- A **runtime configuration contract** — what the image accepts on startup and what it
  refuses to start without — which is the interface the chart change will target.
- Build and publish documentation matching the existing platform-image convention.

**This change wires nothing up.** No chart references the image, no deployment runs it,
and no `Pipe` routes to it. It is an artifact in a registry plus its contract.

## Capabilities

### New Capabilities

- `ssh-sidecar-image`: what the image contains, how its SSH server is configured, what
  configuration it accepts at startup, and what it refuses to run without.
- `ssh-session-dispatcher`: where a session lands and why — application container, sidecar
  toolbox, or neither — plus the session banner and the plain failure when the application
  container cannot host the session.

### Modified Capabilities

None. The `sftp` profile, its image, and its chart contract are untouched.

## Impact

**New**

- An image build context at `products/_lib/ssh-sidecar/`, beside the library chart that
  will consume it, published to GHCR alongside the platform's other images under an
  immutable version tag and intended to be referenced later as a chart **system** value
  rather than a tenant-settable one.
- A dispatcher program in that build context, and its tests.
- A target in `scripts/build-images.sh` that builds and pushes it, run by CI on merge to
  master under `--skip-if-published` so a push happens exactly when `VERSION` names a
  version the registry does not already hold. Only the publish: the image reaches tenant
  pods through a chart version bump fanned out by the reconciler, so `scripts/rollout.sh`
  — which restarts the platform's own Deployments — does not apply and is not touched.

**Not affected**

- No Helm chart, no `Pipe`, no reconciler, no NetworkPolicy, no Terraform, no API, no CLI,
  no UI.
- `atmoz/sftp` and every product currently using it continue unchanged. The two profiles
  are per-product and no product adopts this image in this change.

**Downstream**

- The chart change that adopts this image depends on the runtime configuration contract
  specified here, and on the pod providing `shareProcessNamespace` and `CAP_SYS_PTRACE`.
  Those are pod-level settings and are out of scope here; this image must behave
  correctly, and say so clearly, when they are absent.
