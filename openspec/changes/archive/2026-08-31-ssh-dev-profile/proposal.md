## Why

The `dev` sidecar image is built and published: an SSH server that forwards to the
database pooler, opens a shell in the application container, and carries PostgreSQL 18
tooling. Nothing runs it. `custom` — the product it exists for — has no sidecar at all,
because the library chart that renders one is written for read-only SFTP over a data PVC
and `custom` has no PVC.

This change puts the two together. It makes the library chart profile-aware, gives
`custom` the `dev` profile, and thereby delivers what the whole SSH line of work has been
for: a developer can open a shell in their own application container, attach a debugger to
their running process, and forward a local port to their database.

It also settles a naming problem while the fleet is small. The SSH edge derives a
deployment's upstream address from its Service name, and that convention is currently
`-sftp` — a name that stops being true the moment a sidecar offers a shell and a tunnel.
The convention moves to `-ssh` across the resolver and every chart.

## What Changes

- **The library chart gains a second profile**, renamed `ssh-sidecar-chart`, offering
  `sftp` (today's `atmoz/sftp` behavior, unchanged) and `dev` (the platform sidecar image)
  as two helper sets a product chart chooses between. A product is written for one; no
  deployment ever runs both, and a tenant cannot change which.
- **`custom` adopts the `dev` profile**: the sidecar, a shared process namespace, and the
  Service the edge reaches. `CAP_SYS_PTRACE` is *not* granted — Pod Security `baseline`
  refuses every non-default capability at admission, so `strace`, `gdb` and `py-spy` are
  deferred and everything else the profile offers is unaffected.
- **The naming convention moves from `-sftp` to `-ssh`** in the resolver's upstream
  address and in every rendered resource name.
- **The rendering trigger changes.** A chart renders SSH resources because its product
  opts into a profile, not because it has a user-visible PVC — otherwise `custom`, which
  has no PVC, could never have one.
- **The profile does not require its product to have a database.** The toolbox and the
  forward are facilities it offers, not preconditions it imposes: with no relational
  storage the chart renders no allowlist and no `PG*` environment, the image writes
  `PermitOpen none`, and the dispatcher declines the database tools by name. `custom` has
  a database today, but that is a property of the product, and coupling the two would have
  surfaced as a pod that never starts for the first product to adopt `dev` without one.
- **A stale Secret key is cleaned up as a side effect.** The previous change left every
  SFTP credentials Secret carrying an inert `password` key that Helm's three-way merge
  cannot remove; renaming the Secret is the one fix that works, and this change renames it
  anyway.

**Rolled out in a maintenance window, and disruptive by choice.** The resolver's address
convention and the charts' Service names must agree, so there is no configuration in which
old and new coexist: a deployment whose chart still renders `-sftp` is unroutable the
moment the resolver expects `-ssh`, and the reverse. A compatibility fallback in the
resolver would be a moving part built to be deleted, so there is none.

## Capabilities

### New Capabilities

- `ssh-dev-profile`: what the `dev` profile renders and requires — the sidecar, the
  pod-level facilities it depends on, the runtime inputs the chart supplies it, and what
  it deliberately does not offer.

### Modified Capabilities

- `sftp-chart-contract`: SSH resources are rendered on a product's declared profile rather
  than on the presence of a PVC, and the Service naming convention becomes `-ssh`.
- `ssh-auth-resolver`: the upstream address convention is stated as a contract shared with
  the charts, so neither side can move alone.
- `ssh-sidecar-image`: the forward allowlist and the database connection details become
  optional inputs — absent, forwarding is refused explicitly and the toolbox is
  unavailable; incomplete, the container still fails fast.
- `ssh-session-dispatcher`: a platform command on a deployment with no database is
  declined by name rather than run and left to fail as a connection error.

## Impact

**Charts**

- `products/_lib/caelus-sftp` → `ssh-sidecar-chart`, split into per-profile helper sets
  over one shared Service helper. Rendered resource names move to `-ssh`, including the
  credentials Secret and the scripts ConfigMap.
- `products/_lib/ssh-sidecar` → `ssh-sidecar-image` in the same pass, so a directory name
  says which kind of artifact it holds. The image's published name and tag are unchanged.
- All six existing consumers re-vendor and republish on the `sftp` profile, with their
  recorded chart versions repointed — the same fan-out as previous chart changes, and the
  same trap that three of them are updated by operator action rather than a repository
  edit.
- `products/custom` gains the sidecar, the pod-level settings, and the values its schema
  must accept.

**SSH edge**

- `ssh-auth`: the upstream address expression moves to `-ssh`. Version bump and publish.

**Reconciler**

- None required. Everything the `dev` profile needs is already projected into chart values:
  the platform public key, the pooler host and port, the database Secret's name, and the
  release identity. This was verified rather than assumed.

**Not affected**

- The `freepod` client, which gains its commands in the next change. Access works over
  plain `ssh` from the moment this lands.
- The database, the pooler, quota enforcement, and the tenant NetworkPolicy, which already
  admits the edge to the sidecar port and the pod to the pooler.

**Depends on**

- The published `dev` sidecar image and the account key store, both shipped.
