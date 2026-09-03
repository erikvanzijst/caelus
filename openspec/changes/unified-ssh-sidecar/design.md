## Context

See [proposal.md](proposal.md) § *Why*. The facts that shape the approach:

- **The sidecar image already carries `/usr/lib/openssh/sftp-server`.** `openssh-sftp-server`
  is a hard `Depends:` of `openssh-server` on Debian trixie, so `--no-install-recommends`
  does not drop it. Confirmed in the published image (`ssh-sidecar:0.4.0`, OpenSSH 10.0p2).
  No Dockerfile change is needed to serve file transfer.
- **The image the platform builds for `custom` carries no transfer helper at all.**
  `ghcr.io/railwayapp/railpack-runtime:mise-2026.8.4` — the tag
  `scripts/mirror-railpack-images.sh` pins — has `sh`, `bash`, `tar`, `cat` and `gzip`, and
  no `scp`, `sftp`, `sftp-server` or `rsync`. Anything that looks for a helper in the tenant
  image fails on the default product.
- **`/proc/<pid>/root` reaches the application container's filesystem, writable.** A sibling
  container running as root reads and writes there subject to each path's own mount flags:
  the application's rootfs is writable, a volume the application mounted read-only is `EROFS`
  even to root. This is what an application-container session root is, and its writability is
  the point — it is what an owner's upload into their own deployment writes to.
- **A volume session root never goes through `/proc`.** The sidecar mounts the volume into
  *itself*, read-only, and the session is chrooted there. The same volume is mounted
  read-write in the application container, and the two mounts are independent. This is what
  keeps file access serving while the application container is broken, and it is where
  read-only is enforced.
- **A chrooted `sftp-server` needs four things inside the new root**, because `chroot(2)`
  runs before `execvp` and every path is resolved afterwards: its loader, its libraries,
  `/dev/null` (opened unconditionally by `sanitise_stdfd`), and a `passwd` entry for uid 0
  (`getpwuid` is fatal on failure). An application container supplies all four — the runtime
  mounts `/dev` and `/proc` in every container, and the image the platform builds carries
  `/etc/passwd`. A bare volume mount supplies none, so the image ships them.
- **Root cannot defeat a read-only mount.** A write is `EROFS` regardless of uid, and
  `mount -o remount,rw` is `EPERM` without `CAP_SYS_ADMIN`, which Pod Security `baseline`
  refuses at admission. This is the whole of the read-only guarantee; nothing inside the
  container is trusted to provide it.
- **The six curated charts own their own pod specs.** Each declares `ssh-sidecar` as its
  only chart dependency and splices the sidecar into a pod template it writes, so pod-level
  fields are reachable. `lemmy`'s sidecar rides in the pict-rs pod, and `immich`'s in the
  server pod; both already pass an explicit Service selector.
- **System values win and tenants cannot reach them.** `merge_values_scoped` applies system
  overrides last (`reconcile.py:531`), and user values validate against the chart projection
  of the template schema, whose `additionalProperties` rejects anything the template did not
  declare. A platform-projected value is not tenant-settable.

## Goals / Non-Goals

**Goals:**

- One SSH server image, one configuration mechanism, one startup contract, one dispatcher.
- The capability a session has follows from one declared value, checked against that
  declaration.
- File transfer that works on every deployment with a sidecar, including one built from an
  image containing nothing but the application.
- No change at the edge, the resolver, or the naming conventions they share with the charts.

**Non-Goals:**

- Read-write file access for a curated product. The mounts stay read-only; enabling writes
  later is a chart change per product, and brings back a uid question this change removes.
- Any resolver change. A product with no sidecar is denied by a failed upstream dial rather
  than by a refusal at authentication; improving that means the resolver knowing which
  deployments offer SSH, which is a database column and an auth branch this change
  deliberately does not add.
- Debugger and profiler access, which needs `CAP_SYS_PTRACE` and a Pod Security decision.

## Decisions

### D1: One parameter — the session root

A product chart declares `sessionRoot`, whose value is either a path the sidecar mounts or
the application container. Everything else follows:

| | `volume:<path>` | `app-container` |
|---|---|---|
| what the session is chrooted into | the jail holding the sidecar's own mount | `/proc/<app pid>/root` |
| `shareProcessNamespace` on the pod | not set | required |
| writable | no — the mount is read-only | as the app's own mounts allow |
| shell, remote commands, database tooling | refused | served |
| forwarding | per allowlist (none supplied ⇒ refused) | per allowlist |

`shareProcessNamespace` is not a second input: it is a precondition of one value of this one.
The product chart still sets the pod field itself — no container helper can render a
pod-level field — and a mismatch (declaring `app-container` on a pod that does not share)
fails at the first session with the message the dispatcher already has, naming the cause.

**Rejected: keeping two profiles as two helper sets.** The differences reduce to this one
parameter plus the pod field, and maintaining two images to express one boolean costs a
third-party dependency, a second configuration mechanism, and a second startup contract.

**Rejected: chrooting every session into `/proc/<app pid>/root`, a volume root at a
subpath of it.** It looks like one code path instead of two, but both are the same two-branch
resolution of one string into one chroot target — the branch moves, it does not disappear.
What it would really remove is the sidecar's `mounts` parameter, and that is paid for by
adding `shareProcessNamespace: true` to six curated pods that do not have it. Three things
follow, and none is worth a parameter: every curated sidecar gains root-level reach into the
container holding its tenants' data, leaving one string comparison in the dispatcher as the
whole separation between read-only files and a shell in there; read-only collapses from a
kernel mount plus a flag to the flag alone, which also stops being derivable because
`statvfs` on the app's own mount reports it writable; and file access disappears exactly when
a deployment is crash-looping or cannot pull its image, which is when it is the tenant's only
route to their own data.

**Rejected: deriving the value.** Neither "has a volume" nor "has no volume" selects it.
`matrix` owns a volume and offers no SSH; `naas` owns none and offers none. A product that
declares nothing renders nothing, and that is reached by omission rather than by a third
enum value, so the safe outcome is the one requiring no thought.

### D2: The dispatcher branches on the declaration, never on what it can find

Routing reads `sessionRoot` first. It does not decide that a shell is unavailable *because*
no application process was found — a pod that gained a shared process namespace for an
unrelated reason would then silently grant a shell in the application container to every
tenant of that product. The same applies to the database tooling, which today is gated on
`PGHOST` being set (`dispatch.sh:70`): that conflates "may this deployment have a database
shell" with "does this deployment have a database". The two separate, and the declaration is
checked first.

### D3: File transfer is always served by the sidecar's own `sftp-server`

`dispatch.sh` currently searches `$app_root` for a helper and dies when there is none. It
instead always runs its own, chrooted into the session root. A chrooted process cannot exec
a binary outside the new root by path, so the loader is invoked through a prefix that is
reachable from inside:

```
chroot "$root" $P/lib64/ld-linux-x86-64.so.2 \
       --library-path $P/lib/x86_64-linux-gnu \
       $P/usr/lib/openssh/sftp-server [-R] [-d start]
```

`$P` is the only thing that differs between the two session roots, and the loader, library
and server paths under it are resolved from `ldd` at build time rather than written out here.

- **An application-container root** takes `$P=/proc/<a sidecar pid>/root`, which stays
  resolvable from inside the chroot because the runtime mounts `/proc` in every container.
  `/dev/null` and `/etc/passwd` come from the tenant's own image. Verified end to end: a
  Debian sidecar's `sftp-server` runs inside an Alpine target and reads that target's
  filesystem.
- **A volume root** takes `$P=/.freepod`, a directory the image ships inside the session
  jail at `/srv/session`, holding a copy of the loader, the libraries and the server under
  their own paths. The jail also carries `dev/null` and a one-line `etc/passwd`, and the
  chart mounts the product's volume inside it. A session is chrooted into the jail and
  started in the mount, so its paths are the ones the product already documents.

The jail is the price of one file-transfer implementation. What a curated tenant sees beside
their data directory is two directories holding a device node and a line of `passwd`, plus a
hidden `.freepod`; today they see a `.ssh` that `atmoz/sftp` leaves there.

- **Not a static build.** The loader indirection needs no change to the image and no second
  copy of the binary to keep current with the base image's OpenSSH. It would not help
  either: `/dev/null` and `/etc/passwd` are needed whatever the binary is linked against.
- **Not sshd's `ChrootDirectory` with `internal-sftp`.** It is the one mechanism that needs
  nothing inside the root — sshd chroots after loading and after resolving the user — and it
  cannot serve an application-container root, because `ChrootDirectory` expands only `%%`,
  `%h`, `%u` and `%U` and so cannot name `/proc/<app pid>/root`, which is not knowable at
  render time and changes whenever the application restarts. Adopting it for volume roots
  alone would mean two file-transfer implementations, two server configurations and two sets
  of failure modes to serve one facility.

  Its other costs were measured rather than assumed. It confines port forwarding: on one
  server with both spellings allowlisted, a forward to `192.168.48.2:8080` carried traffic
  and a forward to `fp-target:8080` failed silently, because the forwarding process inherits
  the chroot and has no resolver configuration there. That is fatal for the only deployments
  that forward, which are application-rooted. Its ownership rule, by contrast, is not an
  obstacle: `safely_chroot()` checks the chroot directory and its parents, never its
  contents, so an image-owned jail holding tenant-owned data satisfies it — pointed straight
  at a `33:33` `0770` directory sshd refuses with `bad ownership or modes for chroot
  directory`, and pointed at a `root:root 0755` parent of the same data it serves it.
- **Not the tenant's own helper, even when present.** One path exercised by every session on
  every deployment, rather than a fallback that is rarely taken and therefore rarely known to
  work. It also removes a way for a tenant's image to change what the platform serves.

The dependence is on `/proc` being mounted in the target container, which is a property of
the container runtime rather than of the image, and on the loader and library paths of the
sidecar's own base image — which the image owns, resolves at build time, and proves with a
build-time transfer into the jail.

### D4: Sessions run as root; read-only comes from the mount

The per-product `internalUid`/`internalGid` disappears. It exists today to solve a *read*
problem — data written `0770` by a uid the sidecar must match — which couples four charts to
uid conventions inside upstream images and fails as a permission error when an upstream base
image renumbers its user. Root reads it regardless.

This is sound only because nothing writes: `EROFS` binds root, and remounting needs a
capability `baseline` refuses. **If a curated product is ever given read-write access, the
uid comes back** — uploads would land root-owned in a tree the application owns as another
user and cannot modify.

Whether a session may write is read from the filesystem rather than passed as a flag, so the
setting inside the container cannot disagree with the mount outside it. It is read from the
*declared path* — the mount — and not from the chroot root, which for a volume session is the
jail and therefore part of the container's own writable layer.

### D5: `freepod cp` drives `sftp`, and reuses the existing connection assembly

With transfer served by the platform, the client has no reason to implement one.
`_connection_setup()` (`cli.py:617`) already yields the deployment, the verified edge, and
the one key to offer; `cp` adds argument parsing and an `sftp` invocation carrying the same
options `build_args` produces. Traversal containment, mode preservation and tree recursion
come from the protocol rather than from code here.

A path is remote iff it starts with `:` or `<this deployment>:` — a prefix rule, so a local
file named `notes:draft.txt` is never mistaken for a remote path, which `scp`'s "colon before
the first slash" cannot manage. The long form is accepted from habit and refused when it
names a different deployment. No `-r`: the protocol recurses, and `kubectl cp` — one
container you own — has no such flag either.

### D6: Cut over in one release

Both sides of every coupling move together. The Service name, port, username convention and
the resolver are untouched, so no deployment becomes unroutable and there is no window in
which old and new disagree. The curated charts change image, drop two objects and gain a
`sessionRoot` in one upgrade each; a rollback is the previous chart version.

## Risks / Trade-offs

- **The loader path is base-image-specific** → an image whose base changes architecture or
  library layout breaks every session at once. Mitigated by resolving the loader at build
  time into a known location, by staging the jail from that same resolution, by a build-time
  transfer through the jail, and by the image's own test harness exercising a real transfer
  against both session roots — so the failure lands in the build or in CI rather than in a
  tenant's pod.
- **An application image carrying no `/etc/passwd`** → a session rooted at a `scratch` image
  with no user database fails `getpwuid`, so file transfer is refused there while a shell
  still works. The image the platform's own build pipeline produces carries one, so this
  reaches only a hand-built minimal image; the dispatcher names the cause rather than letting
  it surface as a protocol error.
- **`sessionRoot` is a string where the split used to be two helper sets** → a chart author
  can type the wrong one. Mitigated by the exhaustive classification assertion over
  `products/*/chart`: the dangerous value has to be written in the chart *and* in the
  expectation table, and a product nobody classified fails the suite.
- **One image is a single point of failure across the fleet** → a regression now reaches
  every product rather than one. Against that: one image is also one thing to patch, and
  today's floating `atmoz/sftp:alpine` tag already changes underneath six products with no
  release of ours involved.
- **A stateless curated product has no file access at all** → intended. There is nothing to
  retrieve, application output is served by the log pipeline, and the alternative is granting
  a shell into code the tenant did not write.
