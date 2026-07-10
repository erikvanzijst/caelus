# caelus-sftp library chart

Adds read-only SFTP access to a Caelus deployment's **data** PVCs, in the
PikaPods style: the deployment gets an auto-generated username (= Helm release
name) and password, shown in the Caelus UI. Users log in with any SFTP client
to the platform endpoint (`freepod.eu:22` / `dev.freepod.eu:23`) and browse or
download their app's data. No shell, no writes.

It is a Helm **library chart** — it renders no resources on its own. A product
wrapper chart depends on it and calls its named templates.

## Architecture in one line

`client → sshpiper (routes by username) → this deployment's atmoz/sftp sidecar
→ read-only mount of the data PVC(s)`.

The sidecar rides **inside the app pod** because RWO PVCs can only be shared by
containers in the same pod. sshpiper (platform-owned, one per environment)
reaches the sidecar via a per-deployment Service on port 2222, which the tenant
NetworkPolicy admits.

## What it renders

`caelus-sftp.resources` emits four objects, identical for every product:

| Object | Purpose |
|--------|---------|
| Secret `<release>-sftp-credentials` | username + `lookup`-stable password + `users.conf` |
| ConfigMap `<release>-sftp-scripts` | sshd init: force `internal-sftp -R`, move to port 2222 |
| Service `<release>-sftp` | routes sshpiper → sidecar on 2222 |
| Pipe `<release>` | sshpiper route: username → the Service |

`caelus-sftp.sidecar` and `caelus-sftp.volumes` emit the atmoz/sftp container
and its supporting volumes, to splice into the app pod.

## Wiring it into a product

### 1. Add the dependency (`Chart.yaml`)

```yaml
dependencies:
  - name: caelus-sftp
    version: "0.1.0"
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
  do not add the dependency or the templates. No sidecar, no Secret, no Pipe,
  no Service — and consequently the release name is not routable and the UI
  shows no SFTP panel. This is correct and expected.
- **Multiple PVCs** become sibling subdirectories: pass several `mounts`
  entries with distinct `path`s.
- **Match the sidecar uid to the data owner.** If the app locks its data dir to
  its own uid (nextcloud → `0770 www-data=33`), a default uid-1000 sftp user
  gets "Permission denied" on `ls` despite a good login. Pass `internalUid` (and
  `internalGid` if different) equal to the uid that owns the files. When the
  data is world-readable (or root-owned `0777`), the default 1000 is fine.
- **SFTP needs the pod `Ready`.** The Service only routes to a ready pod, so SFTP
  is unreachable while the app is still initializing or if it is crashlooping.
  This is expected in v1.
- **subPath for shared PVCs.** If the exposable data lives in a subdirectory of a
  PVC that also holds app source or secrets (nextcloud's `config/config.php` has
  DB credentials), mount only that subdir via `subPath`. Never expose a PVC root
  that contains credentials.
- **Mount paths must not be pre-created in the user spec.** The user spec lives
  in `users.conf` with no directory list, precisely because atmoz/sftp would
  `mkdir`/`chown` any listed dir and fail against a read-only mount.
