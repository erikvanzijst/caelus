## Context

See `proposal.md` § Why for the motivation, and `var/ssh_access.md` D17 for the
measurement and the wider SSH work this unblocks.

Three existing facts shape the approach.

1. **The sidecar cannot move out of the pod.** `products/_lib/caelus-sftp/README.md`
   records why: the exposed PVCs are RWO, and an RWO PVC can only be shared by
   containers in the same pod. So "give the sidecar its own pod with its own readiness"
   is not available.
2. **One library edit reaches every product.** All six consuming charts — `helloworld`,
   `immich`, `lemmy`, `mattermost`, `nextcloud`, `vaultwarden` — call
   `caelus-sftp.resources` and `caelus-sftp.sidecar` from their own templates. There is
   no product that inlines its own copy of the sidecar container spec, so no per-product
   template edit is needed.
3. **Charts are versioned artifacts in an OCI registry.** Products are installed from
   `oci://registry.home/helm/<name>` at a recorded `chart_version`. An existing version
   is never re-pushed; a change means a new version and repointing the reference.

## Goals / Non-Goals

**Goals:**

- SFTP reachability becomes independent of application-container health.
- A sidecar that has stopped serving is restarted rather than left to accept
  connections it cannot service.
- The change is invisible to every tenant whose deployment is healthy.

**Non-Goals:**

- Changing which pod a connection lands on during a rollout. Both ReplicaSets already
  match the Service selector and kube-proxy already picks between them at random; this
  change widens the window slightly but does not create the behavior. It is recorded in
  `var/ssh_access.md` D17 and addressed there, not here.
- Any change to credentials, the `Pipe`, the edge, the tenant NetworkPolicy, or the API.
- Backfilling deployments pinned to older chart versions. See *Open Questions*.

## Decisions

### Publish not-ready addresses rather than reshaping readiness

`publishNotReadyAddresses: true` on the SFTP Service is a per-Service statement that
readiness is not a routing precondition. That is precisely and narrowly true here: the
Service fronts an administrative sidecar, not the application, and the sidecar's
usefulness is at its highest when the application is at its worst.

Alternatives considered:

- **Move the sidecar to its own pod** so it has its own readiness. Blocked by the RWO
  PVC constraint above.
- **Remove or relax the application's readiness signal** so the pod stays Ready. Wrong
  layer, and actively harmful: pod readiness gates the *application's* Service and
  ingress, so a crash-looping app would start receiving user traffic.
- **A readiness gate or custom condition.** More machinery for the same outcome, and it
  would still have to encode "ignore the app container", which is what the flag already
  says.

The flag's scope is the SFTP Service alone. The application's own Service is untouched
and continues to exclude unready pods.

### The liveness probe is a TCP check on the SSH port

`tcpSocket` on the sidecar's port, not an `exec` probe and not an SFTP session.

Rationale: the probe must answer exactly one question — *is `sshd` accepting
connections?* A TCP connect answers it. An `exec` probe would need a shell in the
sidecar and could be affected by the container's own state; an SFTP-session probe would
need credentials and would couple liveness to authentication, so a credentials Secret
problem would present as a crash-looping sidecar.

The probe must not reference the application container or the exposed PVCs. A sidecar
whose PVC mount is unhappy is still worth reaching — that may be the thing being
debugged.

### The probe must tolerate host-key generation on start

`atmoz/sftp` generates SSH host keys at container start when none are present, and
nothing persists `/etc/ssh` across restarts, so this happens on **every** start. The
spike's pod log shows it generating an RSA 4096 key pair before `sshd` binds.

A liveness probe with a short initial delay would therefore kill the container during
key generation and loop forever. The probe needs either a `startupProbe` that gates
liveness until the port first opens, or a conservative `initialDelaySeconds` plus
`failureThreshold`. A `startupProbe` is preferred: it expresses "slow to start, then
expected to be responsive" directly, rather than encoding a guess about key-generation
time into the steady-state probe.

Incidental consequence, already true and unchanged: because host keys are regenerated on
every start, the sidecar's host key is not stable. This is why the `Pipe` sets
`ignore_hostkey: true` for the upstream leg. The client-facing host key is the edge's,
which is stable and lives in Terraform state.

### Version bump, re-vendor, republish — per product, independently

The library chart version is bumped once; each consuming chart re-vendors it and gets
its own version bump and push. There is no shared artifact beyond the library source, so
the six products can be rolled out one at a time and a partially rolled-out fleet is
coherent: each deployment either has the fix or does not, and none is broken by the
difference.

Recorded chart versions move in two different places, and both must be done or the new
chart is never installed:

- **Curated** (`immich`, `nextcloud`, `vaultwarden`): `chart_version` in
  `products/catalog/<slug>.yaml`, reconciled into the database on rollout.
- **Non-curated** (`helloworld`, `lemmy`, `mattermost`): a `ProductTemplateVersion`
  record, updated by an operator through the admin UI or CLI. This is not a repository
  edit and will not appear in the diff.

## Risks / Trade-offs

- **A connection can now reach a sidecar that is still starting** → previously the pod
  was simply absent from the endpoints; now the client may get a connection refused
  during the sidecar's first seconds. This is a better failure than "no route" and is
  bounded by the startup probe. No mitigation beyond the probe.
- **A terminating pod stays in the endpoints slightly longer** → during a rollout, a
  session can land on the outgoing pod and be cut when it terminates. Pre-existing
  behavior (both ReplicaSets already match the selector); this change widens the window
  rather than introducing the failure. Tracked in `var/ssh_access.md` D17.
- **Six charts to republish** → a partial rollout leaves a mixed fleet. Acceptable
  because the products are independent; the order does not matter and no product depends
  on another's version.
- **The non-curated version updates are manual** → they can be forgotten, leaving those
  three products on the old chart with no signal in the repository. Mitigated by making
  them explicit, per-product task items rather than one collective step.
- **`publishNotReadyAddresses` is easy to lose** in a future chart refactor, and its
  loss is silent: everything works until an application crash-loops, which is exactly
  when nobody is looking at the Service. Mitigated by the spec requirement and by a
  render assertion in the chart tests.

## Migration Plan

1. Library chart: Service flag, sidecar probes, version bump, README.
2. Per product, independently: `helm dependency build`, render check, chart version
   bump, package, push.
3. Per product: repoint the recorded chart version (catalog file for curated, operator
   action for non-curated).
4. Verify on dev against a deliberately crash-looping deployment.

**Rollback**: repoint the recorded chart version back to the previous release. The old
chart is still in the registry and is unmodified, so rollback is a version change with
no chart edit. Deployments already reconciled to the new version return to the previous
behavior on their next reconcile.

## Open Questions

- **Should existing deployments be actively moved to the new chart version, or left to
  pick it up on their next reconcile?** Deferrable: it changes neither the specs nor the
  implementation, only the operational rollout. The conservative default is to let them
  drift forward naturally and move a deployment deliberately if a tenant reports the
  problem.
