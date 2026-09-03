## Why

A deployment's SSH access is served by two different servers. Curated products run
`atmoz/sftp`, which forces a chroot, hardcodes forwarding off, carries no tooling, and takes
its configuration by having a ConfigMap `sed` its `sshd_config` at startup. `custom` runs the
platform's own sidecar, which opens a shell in the application container, carries the
PostgreSQL toolbox and forwards to the database. The two share a Service name and nothing
else: two images, two configuration mechanisms, two startup contracts, two sets of failure
modes, and a library chart split into two helper sets to keep them apart.

They do not need to be two. The difference that matters between a Nextcloud owner and a
`custom` owner is not which SSH implementation answers — it is **what the session is rooted
at**: a read-only mount of the data the product exposes, or the filesystem of the container
the tenant's own code runs in. Everything else follows from that one fact.

One server also closes a gap. `scp` and `sftp` against a `custom` deployment fail today,
because both need a helper in the tenant's image and the image the platform builds carries
none. The sidecar has shipped `/usr/lib/openssh/sftp-server` since it was created; it is
simply never used, because file transfer is looked for in the tenant's filesystem instead of
served from the sidecar's own.

## What Changes

- **One sidecar image serves every deployment**, and `atmoz/sftp` is removed. The library
  chart offers one helper set rather than two, and the six curated products move onto the
  platform image.
- **A product declares one thing: its session root.** `volume:<path>` roots the session at a
  read-only mount of what the product exposes. `app-container` roots it at the filesystem of
  the application container. There is no default and no fallback; a product that declares
  nothing renders no sidecar, no Service, and is not routable.
- **File transfer is always served by the sidecar's own `sftp-server`**, chrooted into the
  session root, never by a binary looked up in the tenant's image. `scp`, `sftp` and any
  client that speaks the protocol work against every deployment that has a sidecar,
  including one built from a minimal image.
- **What a session may do follows from the declared session root**, checked against that
  declaration rather than inferred from what the pod happens to expose. A volume-rooted
  session serves file transfer and nothing else — no shell, no remote commands, no database
  tooling. An application-rooted session serves all of them.
- **Sessions run as root, and read-only comes from the mount.** The per-product uid that
  today has to match the uid inside an upstream image disappears; a volume-rooted session
  reads what it is given regardless of the modes the application wrote, and cannot write to
  it because the mount is read-only and the container holds no capability to remount it.
- **`freepod cp`** copies files and directories between the local machine and a deployment,
  in both directions, over SFTP.
- **BREAKING for curated deployments' pods**: the sidecar container, its image, and its
  configuration mechanism all change. The Service name, port and username convention do not,
  so nothing at the edge or in the resolver is touched and no deployment becomes unroutable.

## Capabilities

### New Capabilities

- `ssh-chart-contract`: what a product chart declares to get SSH access, what a deployment
  renders for each declaration, the pod-level facilities each requires, and the runtime
  inputs the chart supplies — one contract covering every product.

### Modified Capabilities

- `ssh-sidecar-image`: the session root becomes a required input; the image serves file
  transfer with its own tooling; a session's permitted operations follow the declared root;
  read-only is taken from the filesystem rather than from a flag.
- `ssh-session-dispatcher`: routing is decided by the declared session root first — the
  shell, remote commands and the database toolbox are served only under an
  application-rooted session — and file transfer is served from the sidecar.
- `cli-ssh-access`: the client gains a command that copies files and directories between the
  local machine and the deployment.

### Removed Capabilities

- `sftp-chart-contract` and `ssh-dev-profile`: two chart-side contracts for two profiles,
  replaced by the single contract in `ssh-chart-contract`.

## Impact

- **`products/_lib/ssh-sidecar-chart`** — one helper set replaces two; the credentials Secret
  and the sshd-init ConfigMap are no longer rendered by anything.
- **`products/_lib/ssh-sidecar-image`** — the session root, the dispatcher's routing, and
  serving `sftp-server` from the sidecar.
- **Six curated product charts** — `helloworld`, `immich`, `lemmy`, `mattermost`,
  `nextcloud`, `vaultwarden`: call the single helper, declare a volume session root, drop
  `internalUid`/`internalGid`.
- **`products/custom/chart`** — declares `app-container`.
- **`cli/`** — the `cp` command and its tests.
- **`api/tests/`** — the render assertions become an exhaustive classification of every
  product chart.
- **`api/app/provisioner.py`** — the lookup that decides whether a deployment has file
  access to report. It keyed on the sshd-init ConfigMap, which nothing renders any more, so
  it moves to the Service: the one object the contract guarantees for every session root,
  and the only one left once a deployment holds no credential.
- **Unaffected** — the SSH edge, the auth resolver, the Service naming convention, the
  username convention, and the reachability rules.

Deliberately **not** in scope: the deployment view's file-access panel states that access is
read-only for every deployment that has any SSH access. That is inaccurate for `custom`
today and stays inaccurate after this change; correcting it means the API reporting what a
deployment's file access permits, which is a separable change to the API and the UI.
