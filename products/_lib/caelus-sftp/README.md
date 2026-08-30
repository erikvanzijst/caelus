# caelus-sftp library chart

Adds read-only SFTP access to a Caelus deployment's **data** PVCs: the
deployment gets a username (= Helm release name), and the user authenticates
with an SSH key registered on their account. Users log in with any SFTP client
to the platform endpoint (`freepod.eu:22` / `dev.freepod.eu:23`) and browse or
download their app's data. No shell, no writes, no password.

It is a Helm **library chart** — it renders no resources on its own. A product
wrapper chart depends on it and calls its named templates.

Spec: [sftp-chart-contract](../../../openspec/specs/sftp-chart-contract/spec.md),
[sftp-edge-routing](../../../openspec/specs/sftp-edge-routing/spec.md) ·
Rationale: [ssh-grpc-auth-plugin](../../../openspec/changes/ssh-grpc-auth-plugin/design.md)

## Architecture in one line

`client → sshpiper (asks the SSH auth resolver who this is and where it goes)
→ this deployment's atmoz/sftp sidecar → read-only mount of the data PVC(s)`.

The chart renders no routing object: the edge resolves the route and the user's
key from the platform database on every connection (`ssh-auth/`).

The sidecar rides **inside the app pod** because RWO PVCs can only be shared by
containers in the same pod. sshpiper (platform-owned, one per environment)
reaches the sidecar via a per-deployment Service on port 2222, which the tenant
NetworkPolicy admits.

## What it renders

`caelus-sftp.resources` emits three objects, identical for every product:

| Object                              | Purpose                                                             |
|-------------------------------------|---------------------------------------------------------------------|
| Secret `<release>-sftp-credentials` | username, `users.conf` (no password), and the platform's public key |
| ConfigMap `<release>-sftp-scripts`  | sshd init: force `internal-sftp -R`, port 2222, no password auth    |
| Service `<release>-sftp`            | routes sshpiper → sidecar on 2222, publishing not-ready addresses   |

Nothing in the Secret is secret: a username, a uid/gid line, and a public key.

**Required value.** `caelus.sftp.platformPublicKey` is the SSH edge's public
key, the only key the sidecar trusts.

`caelus-sftp.sidecar` and `caelus-sftp.volumes` emit the atmoz/sftp container
and its supporting volumes, to splice into the app pod.

## Wiring it into a product

### 1. Add the dependency (`Chart.yaml`)

```yaml
dependencies:
  - name: caelus-sftp
    version: "0.3.0"
    repository: "file://../../_lib/caelus-sftp"
```

Then `helm dependency build ./chart` (vendors it into `charts/`).

### 2. Standalone resources (always the same)

Create `templates/sftp.yaml`:

```yaml
{{ include "caelus-sftp.resources" (dict "root" .) }}
```

### 3. The sidecar — depends on who owns the pod

**Wrapper owns the pod** (e.g. helloworld, matrix, mattermost): splice the
sidecar and its volumes directly into your Deployment/StatefulSet template.

```yaml
      containers:
        # ... app containers ...
        {{- include "caelus-sftp.sidecar" (dict "root" . "mounts" (list
             (dict "volume" "data" "path" "data"))) | nindent 8 }}
      volumes:
        # ... app volumes (incl. the `data` PVC volume) ...
        {{- include "caelus-sftp.volumes" (dict "root" .) | nindent 8 }}
```

**Upstream subchart owns the pod** (e.g. nextcloud, immich, vaultwarden): you
cannot edit its pod template. Use the upstream chart's `extraContainers` /
`extraVolumes` values instead, and set the Service selector to the upstream
pod's labels. Because those values want plain YAML (not an `include`), render
the same helpers under a `sftp` block in your wrapper `values.yaml` and feed
them through — or inline the equivalent container. Pass `selector` to
`caelus-sftp.resources` so the Service finds the upstream pod:

```yaml
{{ include "caelus-sftp.resources" (dict "root" . "selector"
     (dict "app.kubernetes.io/instance" .Release.Name
           "app.kubernetes.io/name" "nextcloud")) }}
```

If an upstream chart supports neither `extraContainers` nor a sidecar hook, SFTP
is not offered for that product in v1 (document it and move on).

## Rules (do not skip)

- **Never expose a database PVC.** Only mount PVCs holding user-visible data
  (uploads, media, config the user should see). Postgres/MariaDB/Valkey data
  dirs are off-limits — mounting a live DB data dir over SFTP is a corruption
  and data-exfiltration footgun. When in doubt, expose nothing.
- **Zero-PVC products render nothing.** If a product has no user-visible data,
  do not add the dependency or the templates. No sidecar, no Secret,
  no Service — and consequently the release name is not routable and the UI
  shows no SFTP panel. This is correct and expected.
- **Multiple PVCs** become sibling subdirectories: pass several `mounts`
  entries with distinct `path`s.
- **Match the sidecar uid to the data owner.** If the app locks its data dir to
  its own uid (nextcloud → `0770 www-data=33`), a default uid-1000 sftp user
  gets "Permission denied" on `ls` despite a good login. Pass `internalUid` (and
  `internalGid` if different) equal to the uid that owns the files. When the
  data is world-readable (or root-owned `0777`), the default 1000 is fine.
- **SFTP reachability is deliberately independent of application health.** The
  Service sets `publishNotReadyAddresses: true`, so its endpoints include the
  deployment's pod whenever that pod exists, ready or not. This is not an
  oversight to tidy up in a refactor: the Service fronts an administrative
  sidecar, not the application, and a tenant whose app is crash-looping is
  exactly the tenant who needs to get at their files. Dropping the flag is
  silent — everything works until an app crash-loops, which is when nobody is
  looking at the Service. The application's own Service is untouched and still
  excludes unready pods.
- **The sidecar is liveness-probed, and that is now load-bearing.** With
  readiness no longer gating routing, the sidecar's `livenessProbe` (a
  `tcpSocket` check on 2222) is the only thing that stops connections being
  routed to a wedged `sshd`; a sidecar that has stopped serving is restarted
  rather than left in place. A `startupProbe` on the same port holds liveness
  off while atmoz/sftp generates host keys, which it does on **every** start
  because nothing persists `/etc/ssh`. Neither probe may reference the
  application container, the exposed PVCs, or any credential — a sidecar whose
  PVC mount is unhappy is still worth reaching, since that may be the thing
  being debugged.
- **subPath for shared PVCs.** If the exposable data lives in a subdirectory of a
  PVC that also holds app source or secrets (nextcloud's `config/config.php` has
  DB credentials), mount only that subdir via `subPath`. Never expose a PVC root
  that contains credentials.
- **Mount paths must not be pre-created in the user spec.** The user spec lives
  in `users.conf` with no directory list, precisely because atmoz/sftp would
  `mkdir`/`chown` any listed dir and fail against a read-only mount.
