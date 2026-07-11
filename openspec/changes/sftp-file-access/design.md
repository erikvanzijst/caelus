## Context

Freepod deployments run as Helm releases in per-user namespaces on k3s (single node today, multi-node planned; storage is `local-path` today, CephFS likely later). Each product wrapper chart declares zero or more PVCs; some (e.g., Postgres data dirs) must never be user-visible. The platform has one public IPv4 address (`freepod.eu`), fronted by a home router that port-forwards to a homelab HAProxy doing TCP passthrough into the cluster. Public port 22 is available for forwarding at the router, but both the homelab host and the cluster node keep their own system OpenSSH on their local port 22, so all internal hops must use non-22 ports. Tenant namespaces are locked down by a platform-owned baseline NetworkPolicy (ingress only from Traefik and same-namespace) and PSA `baseline` enforcement.

We want PikaPods-style file access: each deployment gets auto-generated SFTP credentials shown in the UI, and logging in shows that deployment's data — read-only, SFTP/SCP only, no shell.

Hard constraints that shaped the architecture (from the exploration session):

1. Kubernetes cannot hot-attach volumes to a running pod, so a central sshd that mounts PVCs directly would need a restart per deploy — unacceptable (running sessions must survive deploys).
2. RWO PVCs can only be shared by containers in the same pod, so the SFTP server for a deployment must live in the app pod (until RWX storage exists).
3. Storage-coupled tricks (hostPath over the `local-path` directory tree) die on multi-node, so they are ruled out.
4. Declarative chart templating is preferred over runtime reconciler logic and external state.

## Goals / Non-Goals

**Goals:**

- A single SSH entry point per environment on the shared public IP: prod at `freepod.eu:22`, dev at `dev.freepod.eu:23`, with the internal ports as Terraform variables.
- Per-deployment credentials generated at deploy time, stable across upgrades, readable by the UI.
- Read-only SFTP/SCP access to exactly the PVCs each chart chooses to expose; no shell.
- New deployments become reachable without restarting or disturbing any shared component.
- No custom SSH server code; only off-the-shelf components wired together by charts and Terraform.
- Storage- and topology-agnostic: works unchanged on single-node/local-path and multi-node/CephFS.

**Non-Goals:**

- Write access over SFTP (avoids the file-ownership/UID problem entirely for v1).
- Public-key authentication (awkward through an SSH MITM proxy; password-only matches PikaPods).
- rsync/rclone/borg custom commands (future extension on top of the same entry point).
- Per-user logins aggregating multiple deployments (requires a central-filesystem design).
- Standalone per-namespace SFTP pods decoupled from app pod lifecycle (revisit after CephFS/RWX).

## Decisions

### D1: Username-routed SSH reverse proxy (sshpiperd) as the single listener

`sshpiperd` with its Kubernetes plugin terminates all SSH on one Service and routes each connection to an upstream by username — SSH's only routable handshake field (there is no SNI equivalent). Routes are `Pipe` custom resources watched live (`SSHPIPERD_KUBERNETES_ALL_NAMESPACES=true`), so adding a deployment adds a Pipe and nothing restarts.

*Alternatives considered:*
- **Central SFTPGo mounting all PVCs**: no restart-free way to gain new volumes; virtual-user registration requires REST calls or login hooks (runtime machinery, second user database); the hostPath variant is single-node-only. Rejected.
- **Storage migration to RWX + central mount**: large blast radius, storage-coupled, and still needs runtime user registration. Rejected for v1.
- **Custom Go sshd**: ruled out by requirement.

Trade-off accepted: sshpiper is the least battle-tested component in the chain and sits on the critical path of port 22 — hence the spike (task 1) and its stateless, replicable deployment.

### D1a: One sshpiperd instance per environment, public port as a Terraform variable

Dev (`dev.freepod.eu`) and prod (`freepod.eu`) run on the same cluster behind the same public IP. SSH has no SNI, so hostname-based separation on port 22 is impossible — distinct environments require distinct public ports. Each `tf/app` workspace therefore deploys its own sshpiperd (Deployment, host-key Secret, RBAC, node exposure), with its ports as Terraform variables. HAProxy gets one TCP frontend per environment. Only the cluster-scoped Pipe CRD is a shared singleton and lives in `tf/deps/`.

The port chain, tier by tier (both the homelab host and the cluster node keep their system sshd on their own port 22, so internal hops avoid 22):

```
                       prod                          dev
user-facing       freepod.eu:22               dev.freepod.eu:23
                       │ home router port-forward     │
homelab edge      HAProxy :2222               HAProxy :2223
                       │ TCP passthrough              │
cluster node      node :2222 ──▶ prod sshpiperd  node :2223 ──▶ dev sshpiperd
                       │ Pipe routing                 │
tenant pod        <release>-sftp Service :2222 ──▶ atmoz/sftp sidecar :2222 (hardwired)
```

The 2222/2223 internal ports and the router's 22→2222 / 23→2223 translation are convention; only the internal ports are Terraform variables (defaults 2222 prod, 2223 dev). The router forwarding is manual home-router configuration, outside Terraform. The user-facing host/port pairs (`freepod.eu:22`, `dev.freepod.eu:23`) are what the API settings advertise (D6) — they are the router-facing values, not the internal ones. The sidecar's port 2222 is hardwired in the chart contract; it never collides with the node-level 2222 (different network scopes).

Implementation note: Kubernetes NodePorts are normally restricted to 30000–32767, so binding 2222/2223 on the cluster node needs either k3s's built-in ServiceLB (a `LoadBalancer` Service binds the requested port directly on the node) or a widened `--service-node-port-range`. Decided in the spike; ServiceLB is the expected default since it requires no cluster reconfiguration.

This also gives dev its proper role: sshpiper upgrades and config changes are exercised on the dev instance without touching the prod listener.

Cross-talk containment: both instances watch Pipes cluster-wide, so the dev proxy would match prod usernames (and vice versa). Two layers scope this:
1. The baseline NetworkPolicy carve-out is rendered per environment from that environment's settings (D5), selecting only that environment's sshpiper pods — the dev proxy cannot reach prod sidecars at the network layer, and vice versa.
2. If the kubernetes plugin supports namespace/label filtering of Pipes, each instance additionally watches only its environment's namespaces (spike question); if not, layer 1 alone is sufficient — a cross-environment route exists in the proxy's table but every connection through it is denied.

*Alternative considered:* one shared sshpiperd in `tf/deps` serving both environments (usernames are globally unique, so routing works). Rejected: no isolated dev testing path for the one component that owns the public SSH surface, and no way to give dev a distinct endpoint at all.

*Alternative considered:* IPv6-only dev endpoint on port 22. Rejected: many user networks remain IPv4-only, and dev should mirror prod's access path.

Known quirk, accepted: public port 23 is the historical telnet port, which some ISPs and corporate networks filter. Dev-only exposure, so the risk is confined to inconvenience for developers, and the port is trivially changeable at the router + settings level.

### D2: `atmoz/sftp` sidecar in the app pod, rendered by the wrapper chart

Each product chart that has user-visible PVCs adds an `atmoz/sftp` container to the app pod, mounting exactly those PVCs `readOnly: true` under `/home/<username>/<volume-name>`. This dissolves the "auto-discover PVCs" requirement: the chart already knows its PVCs and simply never mounts DB volumes. Zero-PVC products render no sidecar, Service, Pipe, or Secret — and consequently no UI panel.

- Read-only is enforced twice: kernel-level via `readOnly` volumeMounts, and in sshd via `internal-sftp -R`.
- No shell: `ForceCommand internal-sftp` (atmoz/sftp default). Note: classic `scp` protocol is unavailable; OpenSSH ≥ 9 `scp` uses the SFTP protocol and works.
- The sidecar runs in-container as root for OpenSSH's chroot + privilege separation; PSA `baseline` (already enforced on tenant namespaces) permits this; `restricted` would not.
- The chroot home is root-owned (atmoz/sftp convention), so the top folder is read-only by construction and PVC contents appear as subdirectories — the PikaPods UX.

*Alternative considered:* `linuxserver/openssh-server` — equivalent capability, but the user has operational familiarity with `atmoz/sftp`. Chosen: `atmoz/sftp`.

### D3: Credentials are a chart-templated Secret using the Helm `lookup` pattern

The chart renders a Secret (e.g., `<release>-sftp-credentials`) containing the username and a `randAlphaNum` password. To keep the password stable across `helm upgrade`, the template first `lookup`s the existing Secret and reuses its value; generation happens only on first install. The same value feeds the sidecar's `users.conf` (atmoz/sftp user spec) so the Secret and the sshd config can never diverge.

- Username = Helm release name (`deployment.name`), already a unique immutable slug per the platform naming contract, and a valid SSH username (`[a-z0-9-]`).
- `lookup` requires a real cluster connection; the reconciler drives actual Helm SDK installs, never `helm template`, so this holds. Documented as a chart constraint.

*Alternative considered:* reconciler generates the password and injects it as a system value — stable and testable, but adds runtime logic and stores a secret in the Caelus DB. Rejected per the declarative-first preference.

### D4: Pipe targets a per-deployment Service

The chart renders a `Service` (port 2222 → sidecar) and a `Pipe` CR: `from.username: <release-name>` → `to.host: <release>-sftp.<namespace>.svc:2222` with password passthrough (sshpiper relays the client's password; the sidecar's OpenSSH validates it). `ignore_hostkey: true` for the upstream leg — sidecar host keys may churn freely; clients only ever see sshpiper's host key, which lives in a stable Secret in the platform namespace so `known_hosts` entries survive redeploys.

*Alternative considered:* sshpiper's kubectl-exec mode piping into the pod directly — clever but exotic; a Service is boring and debuggable.

### D5: Network isolation carve-out scoped to the sidecar port

The baseline tenant NetworkPolicy gains one ingress rule: from the sshpiper pods (selected by namespace + pod label, mirroring the existing Traefik rule) to port 2222/TCP only. Unlike the Traefik rule (any port, by design), this one is port-scoped: sshpiper has no business reaching app ports, and a compromised router should not become a bridge into tenant workloads.

### D6: API/UI read the Secret at request time

A deployment-scoped endpoint (`GET /users/{user_id}/deployments/{id}/sftp`) reads the credentials Secret from the deployment's namespace via the Kubernetes API and returns host and port (from per-environment settings, the user-facing router values: `freepod.eu:22` in prod, `dev.freepod.eu:23` in dev), username, and password; 404/absent semantics when the product exposes no files. CLI gets a parity command. No credentials are persisted in the Caelus DB — the Secret is the single source of truth.

## Per-product exposure decisions

Not every product exposes SFTP. Applying the "user-visible data only" rule to
each product's PVCs (surfaced during rollout, task 4.4):

| Product | Exposable PVC | Pod ownership | Internal uid | Notes |
|---------|---------------|---------------|--------------|-------|
| helloworld | data | wrapper Deployment | 1000 (root-owned data) | reference; live-tested |
| nextcloud | data (subPath of `nextcloud-main`) | upstream subchart | 33 (www-data) | live-tested; subPath hides `config.php` |
| mattermost | data (uploads) | wrapper Deployment | 2000 (image user) | postgres/plugins PVCs excluded |
| immich | library (photos) | upstream (bjw-s common lib) | — | deferred: distinct `advancedMounts` injection |
| matrix | none | — | — | only PVC is the tuwunel DB store → no SFTP |
| vaultwarden | none | — | — | only PVC is `db.sqlite3` + RSA signing key → no SFTP |

Two implementation mechanisms emerged: wrapper-owned pods inject the sidecar
directly (`caelus-sftp.sidecar`); subchart-owned pods inject via the upstream
chart's `extraSidecarContainers`/`extraVolumes` values, which are static YAML
(no `.Release.Name`), so the Pipe maps the unique external username to a fixed
internal user (`sftp`) and resources use fixed per-namespace names.

## Spike/rollout findings that shaped the contract

- **UID ownership is the sleeper issue** (predicted in the exploration, hit live
  on nextcloud): apps that lock their data dir to their own uid (nextcloud →
  `0770 www-data=33`) are unreadable by a default uid-1000 sidecar despite a
  successful login — `ls` returns "Permission denied". The sidecar user's
  uid/gid MUST match the data-owning uid (atmoz `user:pass:uid:gid`); this is a
  per-product `internalUid`/`internalGid` parameter.
- **Service readiness gating**: the per-deployment SFTP Service only routes when
  the whole pod is `Ready`. A slow-initializing app (nextcloud first-run) makes
  SFTP briefly unreachable ("connection refused" at sshpiper) until the app
  container passes readiness — and a crashlooping app makes it unreachable
  entirely. Acceptable for v1 (consistent with the sidecar/pod-lifecycle
  coupling already noted); `publishNotReadyAddresses` on the Service is the lever
  if we later want SFTP to survive an unhealthy app.
- **Password-lookup name coupling**: the `lookup` for password stability must key
  on the *actual* Secret name. Subchart products use a fixed Secret name, so the
  password helper takes the name as a parameter — otherwise it looks up a
  nonexistent `<release>-sftp-credentials` and rotates the password every
  upgrade. Caught by a live two-upgrade stability check.

## Risks / Trade-offs

- [sshpiper maturity: password passthrough, Pipe hot-reload, many-Pipe scale, SFTP subsystem behavior] → De-risk with the spike task before any chart work; keep sshpiperd stateless and horizontally replicable; failure domain is limited to file access, never app traffic.
- [SFTP availability is coupled to the app pod lifecycle (sidecar model): crashlooping app = no file rescue] → Accepted for v1; the Pipe/Service/Secret contract is unchanged if sidecars later graduate to standalone per-namespace SFTP pods once RWX storage (CephFS) lands.
- [Per-deployment memory overhead (~10–20 MiB idle OpenSSH per app with exposed PVCs)] → Accepted; bounded, and only paid by products that expose files.
- [Helm `lookup` returns empty under `helm template`/`--dry-run`, which would render a new password] → Reconciler always performs real installs; add a chart-testing note; the sidecar and Secret derive from the same value so they cannot diverge even if regenerated.
- [Password rotation rotates only on Secret deletion, not on demand] → Acceptable v1 semantics: "regenerate credentials" = delete Secret + reconcile; can become an explicit API action later.
- [Username collisions: release-name uniqueness is enforced per (namespace, name), not globally] → The 6-char random suffix makes collisions negligible; Pipe creation would fail loudly (duplicate `from.username`) rather than silently misroute. Usernames are also shared across environments (both watch all Pipes), but the same suffix argument applies.
- [Cross-environment routing: each environment's proxy matches the other environment's Pipes] → Per-environment NetworkPolicy carve-out denies cross-environment connections regardless of the proxy's routing table (D1a); plugin-side Pipe filtering investigated in the spike as a second layer.
- [Client source IPs lost through HAProxy TCP passthrough + NodePort] → Accepted for v1; fail2ban-style abuse controls would need PROXY-protocol support investigation later.
- [Plaintext password stored in the Secret (needed for UI display)] → Scoped to the tenant namespace; equivalent to PikaPods' model; read access guarded by existing deployment authorization.

## Migration Plan

1. Spike sshpiperd on the dev cluster (hand-written Pipe + helloworld sidecar) before committing to chart work.
2. Land the Pipe CRD in `tf/deps/` and the per-environment sshpiper module in `tf/app/` (deployment, host-key Secret, RBAC, node exposure; ports as workspace variables, 2222 prod / 2223 dev) — inert until Pipes exist. Apply to the dev workspace first.
3. Add HAProxy TCP frontends (external edge config) and router port-forwards: dev first (router :23 → HAProxy :2223 → node :2223), prod (router :22 → HAProxy :2222 → node :2222) once dev is validated.
4. Update the baseline NetworkPolicy template + run the fleet-wide policy sync (non-disruptive by design).
5. Roll out chart changes product-by-product starting with helloworld; each is an ordinary Helm upgrade via the reconciler.
6. Ship API endpoint, then UI panel.

Rollback: remove Pipes/sidecars via chart downgrade; sshpiper deployment can be deleted independently; NetworkPolicy carve-out is additive and safe to leave.

## Open Questions

All resolved by the 2026-07-06 spike (a throwaway sshpiperd + hand-written Pipe + atmoz/sftp sidecar on a manual helloworld install; full path validated: workspace → node :2223 → sshpiperd → Pipe → atmoz/sftp sidecar → read-only PVC). The findings below are the durable output; the scratch manifests were not kept.

- **Password passthrough**: default plugin behavior, no configuration needed. One catch: released sshpiperd images still require `ignore_hostkey: true` on the Pipe's `to` — without it, connections fail with `knownhosts: key is unknown`, even though the master-branch CRD marks the field deprecated. The chart contract must set it (and Terraform should pin the sshpiperd image version, since this semantic is in flux upstream).
- **Per-environment Pipe filtering**: not supported — the kubernetes plugin has exactly two flags (`all-namespaces`, `kubeconfig`), no namespace/label selector. Environment separation therefore rests entirely on the per-environment NetworkPolicy carve-out (D1a layer 1), which the spec already mandates.
- **Sidecar resources**: measured idle 3Mi (atmoz/sftp) and 14Mi/2m CPU (sshpiperd). Chosen: sidecar `requests 10m/16Mi, limit 64Mi`; sshpiperd `requests 10m/32Mi, limit 128Mi`.
- **users.conf**: mount the credentials Secret as `/etc/sftp/users.conf` (`<user>:<password>:1000`) rather than passing the user spec as container args — args are visible in the pod spec to anything that can read pods. Plaintext in the conf is acceptable: the plaintext already lives in the same Secret for UI display, so the `:e` crypt-hash variant adds no real protection.

Additional spike findings that bind the chart contract:

- atmoz/sftp's generated `sshd_config` has no `Port` directive (sshd defaults to 22); the pod-port-2222 convention requires an `/etc/sftp.d/` init script that appends `Port 2222`. The same script rewrites `ForceCommand internal-sftp` to `internal-sftp -R` for read-only enforcement — both verified working.
- The atmoz user spec must not list directories: the entrypoint `mkdir`/`chown`s listed dirs, which fails on read-only mounts. Mount PVCs at `/home/<username>/<name>` and they appear in the chroot with no entrypoint involvement.
- Denial behavior verified end-to-end: uploads/deletes/mkdirs rejected (`internal-sftp -R` + `readOnly` mounts), shell/exec answered with "This service allows sftp connections only.", TCP forwarding "administratively prohibited", wrong password and unknown/deleted usernames rejected.
- Hot-reload verified: Pipe add/edit/delete effective on the next connection with zero proxy restarts and an open session undisturbed. `scp` (OpenSSH ≥ 9 SFTP mode) works.
- Low-port binding: k3s klipper ServiceLB binds a `LoadBalancer` Service's port (2223) directly on the node — no NodePort-range change needed. This is the mechanism for D1a's node exposure.
