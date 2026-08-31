# ssh-sidecar library chart

Adds SSH access to a Caelus deployment. The deployment gets a username (= Helm
release name), and its owner authenticates with an SSH key registered on their
account, connecting to the platform endpoint (`freepod.eu:22` /
`dev.freepod.eu:23`).

**What that access consists of depends on the product's access profile.** There
are two, and a product is authored for exactly one:

| | `sftp` | `dev` |
|---|---|---|
| Server | `atmoz/sftp` | the platform's own [ssh-sidecar image](../ssh-sidecar-image/README.md) |
| For | products with user-visible data PVCs | `custom`, which has no PVC at all |
| Session | SFTP only — **no shell, no writes** | a login shell **in the application container** |
| Forwarding | refused (`AllowTcpForwarding no`) | to the deployment's database if it has one, allowlisted; otherwise refused |
| Tooling | none | PostgreSQL 18 client |
| Pod needs | nothing | `shareProcessNamespace` on the pod |
| Renders | Secret, ConfigMap, sidecar, Service | sidecar, Service |

It is a Helm **library chart** — it renders no resources on its own. A product
wrapper chart depends on it and calls its named templates.

Spec: [sftp-chart-contract](../../../openspec/specs/sftp-chart-contract/spec.md),
[ssh-dev-profile](../../../openspec/specs/ssh-dev-profile/spec.md),
[sftp-edge-routing](../../../openspec/specs/sftp-edge-routing/spec.md) ·
Rationale: [ssh-grpc-auth-plugin](../../../openspec/changes/archive/2026-08-30-ssh-grpc-auth-plugin/design.md)

## The profile is which helpers you call

There is **no `profile` value and no profile string anywhere.** The library
exposes two helper sets over one shared Service helper, and a product chart calls
the set it was written for:

```
ssh-sidecar.service        ← shared; both profiles emit the Service through it
ssh-sidecar.podSelector
ssh-sidecar.labels

ssh-sidecar.sftp.resources     ssh-sidecar.dev.resources
ssh-sidecar.sftp.sidecar       ssh-sidecar.dev.sidecar
ssh-sidecar.sftp.volumes       (none — the dev profile mounts nothing)
```

A profile parameter would model something that does not vary. A product chart
cannot render the other profile: its pod template either shares its process
namespace or does not, and either mounts data PVCs into a sidecar or does not.
And which profile a deployment runs is security-relevant — `dev` grants a shell
in the application container and the ability to trace its processes — so keeping
that decision out of values entirely beats admitting it there and defending it
with a schema.

The cost is that a chart's call sites must agree: `sftp.resources` beside
`dev.sidecar` renders an incoherent chart. Nothing in Helm catches that, so the
render assertions in `api/tests/` do.

## Architecture in one line

`client → sshpiper (asks the SSH auth resolver who this is and where it goes)
→ this deployment's sidecar → its PVC (sftp) or its application container (dev)`.

The chart renders no routing object: the edge resolves the route and the user's
key from the platform database on every connection (`ssh-auth/`).

The sidecar rides **inside the app pod** — on `sftp` because RWO PVCs can only be
shared by containers in the same pod, and on `dev` because a shared process
namespace is what lets it reach the application at all.

## The `-ssh` naming convention is shared with the resolver

`ssh-sidecar.service` names the Service `<release>-ssh`. That name is **not this
chart's to choose**: the SSH edge derives a deployment's upstream address from
it by string convention, in
[`ssh-auth/resolve.go`](../../../ssh-auth/README.md#the--ssh-naming-convention-is-shared-with-the-charts).
**Neither side may change it alone.**

The coupling is invisible in both directions — the resolver names a Service it
never validates, and this chart names a Service nothing in its own release
consults — so a unilateral change breaks nothing at build time and produces
deployments that authenticate successfully and then reach nothing.
`ssh-auth/convention_test.go` renders both a `sftp` and a `dev` product and
asserts the name matches what the resolver derives.

The **port** (2222) is shared the same way. Both profiles listen on it, so the
edge never has to know which profile a deployment runs.

## What each profile renders

### `sftp`

`ssh-sidecar.sftp.resources` emits:

| Object                             | Purpose                                                             |
|------------------------------------|---------------------------------------------------------------------|
| Secret `<release>-ssh-credentials` | username, `users.conf` (no password), and the platform's public key |
| ConfigMap `<release>-ssh-scripts`  | sshd init: force `internal-sftp -R`, port 2222, no password auth    |
| Service `<release>-ssh`            | routes sshpiper → sidecar on 2222, publishing not-ready addresses   |

Nothing in the Secret is secret: a username, a uid/gid line, and a public key.

`ssh-sidecar.sftp.sidecar` and `ssh-sidecar.sftp.volumes` emit the atmoz/sftp
container and its supporting volumes, to splice into the app pod.

### `dev`

`ssh-sidecar.dev.resources` emits the Service and **nothing else**;
`ssh-sidecar.dev.sidecar` emits the container.

There is no Secret and no ConfigMap, because the platform sidecar takes every
input as an environment variable and writes its own `authorized_keys`,
`sshd_config` and host key at startup. `sftp` needs both objects only because
`atmoz/sftp` reads its user list and startup script off disk. There are two call
sites rather than three: this profile has no supporting volumes.

**Required value.** `caelus.ssh.platformPublicKey` is the SSH edge's public key,
the only key either profile's sidecar trusts. The reconciler injects it for
every deployment.

**Required param.** `dev.sidecar` takes `image`, pinned to an exact version and
supplied as a **system** value — a tenant-settable reference would let a tenant
substitute the container that holds the platform's trusted key and enters their
application. See [the image's README](../ssh-sidecar-image/README.md).

## Wiring it into a product

### 1. Add the dependency (`Chart.yaml`)

```yaml
dependencies:
  - name: ssh-sidecar
    version: "0.4.2"
    repository: "file://../../_lib/ssh-sidecar-chart"
```

Then `helm dependency build ./chart` (vendors it into `charts/`).

If your chart has a `.helmignore` ignoring `*.tgz`, **anchor it** (`/*.tgz`) —
unanchored it also strips the vendored dependency out of `charts/`.

### 2. On the `sftp` profile

`templates/sftp.yaml`:

```yaml
{{ include "ssh-sidecar.sftp.resources" (dict "root" .) }}
```

**Wrapper owns the pod** (helloworld, mattermost): splice the sidecar and its
volumes into your Deployment/StatefulSet template.

```yaml
      containers:
        # ... app containers ...
        {{- include "ssh-sidecar.sftp.sidecar" (dict "root" . "mounts" (list
             (dict "volume" "data" "path" "data"))) | nindent 8 }}
      volumes:
        # ... app volumes (incl. the `data` PVC volume) ...
        {{- include "ssh-sidecar.sftp.volumes" (dict "root" .) | nindent 8 }}
```

**Upstream subchart owns the pod** (nextcloud, immich, vaultwarden): you cannot
edit its pod template. Use the upstream chart's `extraContainers` /
`extraVolumes` values, and pass `selector` so the Service finds the upstream pod:

```yaml
{{ include "ssh-sidecar.sftp.resources" (dict "root" . "selector"
     (dict "app.kubernetes.io/instance" .Release.Name
           "app.kubernetes.io/name" "nextcloud")) }}
```

If an upstream chart supports neither `extraContainers` nor a sidecar hook, SSH
is not offered for that product (document it and move on).

### 3. On the `dev` profile

`templates/ssh.yaml`:

```yaml
{{ include "ssh-sidecar.dev.resources" (dict "root" .) }}
```

and in the pod template — note `shareProcessNamespace`, which no container
helper can set for you:

```yaml
    spec:
      shareProcessNamespace: true
      containers:
        # ... app container ...
        {{- include "ssh-sidecar.dev.sidecar"
             (dict "root" . "image" .Values.sshSidecarImage) | nindent 8 }}
```

## Rules (do not skip)

### Both profiles

- **The Service name and port are not yours to change.** See *The `-ssh` naming
  convention* above. Overriding `serviceName` makes the deployment unroutable.
- **Reachability is deliberately independent of application health.** The
  Service sets `publishNotReadyAddresses: true`, so its endpoints include the
  deployment's pod whenever that pod exists, ready or not. This is not an
  oversight to tidy up in a refactor: the Service fronts an administrative
  sidecar, not the application, and a tenant whose app is crash-looping is
  exactly the tenant who needs to get in. Dropping the flag is silent —
  everything works until an app crash-loops, which is when nobody is looking at
  the Service. The application's own Service is untouched and still excludes
  unready pods.
- **The sidecar is liveness-probed, and that is load-bearing.** With readiness
  no longer gating routing, the `livenessProbe` (a `tcpSocket` check on 2222) is
  the only thing that stops connections being routed to a wedged `sshd`. Neither
  probe may reference the application container, the exposed PVCs, or any
  credential — a sidecar whose PVC mount is unhappy is still worth reaching,
  since that may be the thing being debugged.

### `sftp` only

- **Never expose a database PVC.** Only mount PVCs holding user-visible data
  (uploads, media, config the user should see). Postgres/MariaDB/Valkey data
  dirs are off-limits — mounting a live DB data dir over SFTP is a corruption
  and data-exfiltration footgun. When in doubt, expose nothing.
- **Nothing to expose renders nothing.** A product on this profile with no
  user-visible data must not call these helpers at all: its sidecar would offer
  an empty session. `ssh-sidecar.sftp.sidecar` fails the render on empty
  `mounts` rather than letting that happen quietly. This is a property of *this
  profile*, not of the chart contract — `dev` mounts no tenant volume at all and
  is correct doing so.
- **Multiple PVCs** become sibling subdirectories: pass several `mounts` entries
  with distinct `path`s.
- **Match the sidecar uid to the data owner.** If the app locks its data dir to
  its own uid (nextcloud → `0770 www-data=33`), a default uid-1000 sftp user
  gets "Permission denied" on `ls` despite a good login. Pass `internalUid` (and
  `internalGid` if different) equal to the uid that owns the files.
- **subPath for shared PVCs.** If the exposable data lives in a subdirectory of
  a PVC that also holds app source or secrets (nextcloud's `config/config.php`
  has DB credentials), mount only that subdir via `subPath`.
- **Mount paths must not be pre-created in the user spec.** The user spec lives
  in `users.conf` with no directory list, precisely because atmoz/sftp would
  `mkdir`/`chown` any listed dir and fail against a read-only mount.
- **If you override `credsSecret` or `scriptsConfigMap`, pass the same value to
  `sftp.volumes`.** Those volumes name the objects `sftp.resources` renders, and
  a mismatch is a pod referencing a Secret nobody emitted.

### `dev` only

- **The pod must set `shareProcessNamespace: true`,** and must **not** set
  `hostPID`. The shared namespace is what lets the sidecar reach the
  application; that it is the *pod's* and not the *node's* is what bounds
  `CAP_SYS_PTRACE` to this tenant's own containers. Every warning treating that
  capability as a container-breakout vector assumes the node's namespace.
- **`CAP_SYS_PTRACE` is not granted yet, so the template requests no
  capability.** Tenant namespaces enforce Pod Security `baseline`, which refuses
  every non-default capability at admission; a pod asking for one never
  schedules. `strace`, `gdb` and `py-spy` are consequently unavailable, and
  nothing else is: entering the application container needs `CAP_SYS_CHROOT`,
  which is in the default set. The bullets around this one are the invariants
  that must hold when the capability is granted.
- **Both containers must keep the same AppArmor profile.** Neither declares one,
  so both run the node default under enforcement, and its peer clause matches
  when tracer and tracee carry the same profile name. Giving the application
  container a profile of its own breaks tracing with a permission error that
  mentions nothing about AppArmor.
- **The capability goes on the sidecar alone.** The application container gains
  nothing from this profile.
- **Nothing secret may ever be mounted into the sidecar.** The shared process
  namespace is symmetric: the application container can see the sidecar's
  processes and files. That is safe only because the sidecar holds one public
  key and its own generated host key.
- **The image reference is a system value, pinned to an exact version.** Never a
  moving tag: the version a pod runs would become a function of when it last
  restarted and what its node had cached.
- **The database is optional, and its absence costs only the database.** A
  product with no relational storage renders this profile with no allowlist and
  no `PG*` environment; the image writes `PermitOpen none` and declines the
  database tools by name, and the shell, file transfer and session paths are
  unchanged. The toolbox is a facility the profile offers, not a precondition it
  imposes — `custom` has a database today, but that is a property of the product
  and it will not stay the only one on this profile.
