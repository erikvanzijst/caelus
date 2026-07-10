# SFTP file access architecture

Date: 2026-07-07
Status: Implemented (dev); prod edge pending router/HAProxy rollout

Read-only SFTP access to each deployment's user-visible data, PikaPods-style:
every deployment with exposable PVCs gets an auto-generated username/password
(shown in the Caelus UI); users log in with any SFTP client to browse and
download their files. No shell, no writes.

See the OpenSpec change `sftp-file-access` for the full proposal, design
decisions, and specs.

## Data path

```
                        prod                          dev
user-facing        freepod.eu:22               dev.freepod.eu:23
                        │ home router port-forward     │
homelab edge       HAProxy :2222               HAProxy :2223   (TCP passthrough)
                        │                             │
cluster node       node :2222 ─▶ prod sshpiperd  node :2223 ─▶ dev sshpiperd
                        │ routes by SSH username via Pipe CRs
tenant pod         <release>-sftp Service :2222 ─▶ atmoz/sftp sidecar :2222
                        │ read-only mount
                   deployment's data PVC
```

Both the homelab host and the k3s node keep their own system OpenSSH on port 22,
so every internal hop uses 2222 (prod) / 2223 (dev). SSH has no SNI, so the two
environments are separated purely by port; a single public IPv4 address serves
both.

## Components

- **sshpiperd** (per environment, `tf/app` `sshpiper` module): a stateless SSH
  reverse proxy that terminates all tenant SFTP and routes each connection to a
  per-deployment upstream by username. Routes are `Pipe` custom resources
  (`sshpiper.com/v1beta1`) watched cluster-wide; adding/removing a deployment
  adds/removes a Pipe with no proxy restart and no disruption to live sessions.
  Presents a stable host key from a Secret so client `known_hosts` survive
  redeploys. Exposed on the node via k3s klipper ServiceLB (binds the low port
  directly; no NodePort-range change).
- **Pipe CRD** (`tf/deps` `sshpiper` module): cluster-scoped singleton, installed
  once, pinned to the sshpiperd image version.
- **atmoz/sftp sidecar** (per deployment, in the app pod): stock OpenSSH forced
  to `internal-sftp -R` (read-only, no shell/exec/forwarding). Mounts the app's
  data PVC read-only. Rides in the app pod because RWO PVCs can only be shared
  within a pod.
- **caelus-sftp library chart** (`products/_lib/caelus-sftp`): renders the
  credentials Secret, sshd init ConfigMap, Service, and Pipe, plus the sidecar
  container/volumes for wrapper-owned pods. Consumed by each product that
  exposes files.
- **Credentials API/UI**: `GET /users/{id}/deployments/{id}/sftp` reads the
  credentials Secret live (never persisted in the DB); the UI shows host, port,
  username, and a revealable/copyable password, hidden entirely for products
  with no file access (404).

## Key design points

- **Per-deployment credentials, stable across upgrades.** Username = release
  name (globally unique). Password is generated once and reused on upgrades via
  the Helm `lookup` pattern; the reconciler always performs real installs, so it
  never spuriously rotates.
- **Only user-visible data is exposed.** Database/state PVCs are never mounted.
  Products with no user-visible PVCs (matrix, vaultwarden) render no SFTP at all.
- **UID must match the data owner.** The sidecar user's uid/gid must equal the
  uid that owns the data (nextcloud → 33 www-data; mattermost → 2000), or reads
  fail with "Permission denied" despite a good login. Set per product via the
  library's `internalUid`/`internalGid`.
- **subPath for mixed PVCs.** When the data lives in a subdirectory of a PVC that
  also holds secrets (nextcloud's `config/config.php`), only that subdir is
  mounted.
- **Environment separation** relies on the per-environment tenant NetworkPolicy,
  which admits only that environment's sshpiper pods on port 2222 — the
  sshpiperd plugin cannot scope its cluster-wide Pipe watch by namespace, so
  cross-environment routes are denied at the network layer instead.
- **SFTP tracks pod readiness.** The Service routes only to a ready pod, so SFTP
  is unavailable while the app initializes or if it crashloops.

## Future extensions (out of scope for v1)

- **rsync / rclone / borg** as additional forced commands on the same entry
  point (v1 is SFTP/SCP only).
- **Public-key auth** (v1 is password-only; keys are awkward through the SSH
  reverse proxy).
- **Standalone per-namespace SFTP pods** decoupled from the app pod lifecycle —
  becomes attractive once storage moves to CephFS/RWX, giving a "rescue my data
  from a broken app" path. The Pipe/Service/Secret contract is unchanged.
- **Per-user logins** aggregating a user's deployments (requires a central
  filesystem; the current model is one login per deployment).
