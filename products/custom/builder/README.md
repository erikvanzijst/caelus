# builder

The image that turns a tenant's uploaded project archive into a container
image. One instance runs per build, as a Kubernetes Job in that environment's
builds namespace (`caelus-builds` in prod, `caelus-builds-dev` in dev), and it
is the only place in the platform where **tenant-supplied code executes**: a
project's dependency install hooks and build commands run inside it.

Everything about its shape follows from that.

## What it does

```
presigned artifact URL
        │
        ▼
  stream + extract (filtered, bounded, never staged on disk)  →  railpack prepare
        │                                                    │
        │                                              railpack-plan.json
        ▼                                                    ▼
   ephemeral rootless buildkitd  ←──  buildctl gateway build against
                                       the pinned Railpack frontend
        │
        ▼
  push {registry}/{user_id}:{build_id}   →   digest from --metadata-file
        │
        ▼
  /dev/termination-log:  {"image": "{user_id}@{digest}"}
```

The container holds **no database, Kubernetes, or long-lived registry
credential**. The only credential it receives is a presigned URL that grants
read on exactly one object and expires. It reports its result through the pod's
termination message, so it never needs write access to anything — a
`DATABASE_URL` here would be a Postgres connection handed to every tenant, no
subversion of this script required.

## Environment contract

The build worker sets all of these on the Job.

| Variable                     | Required | Meaning                                                                                                                    |
|------------------------------|----------|----------------------------------------------------------------------------------------------------------------------------|
| `CAELUS_ARTIFACT_URL`        | yes      | Presigned GET for the project archive. Expiring, single-object.                                                            |
| `CAELUS_USER_ID`             | yes      | The build's owner. Becomes the repository name and the frontend cache key.                                                 |
| `CAELUS_BUILD_ID`            | yes      | The build's id. Becomes the anchor tag.                                                                                    |
| `CAELUS_REGISTRY`            | yes      | Registry host, e.g. `registry.home`. Must match `registry` in the chart's `values.yaml`.                                   |
| `CAELUS_WORKDIR`             | no       | Working tree. Default `/home/user/work`; the Job mounts an emptyDir here.                                                  |
| `CAELUS_MAX_ARTIFACT_BYTES`  | no       | Ceiling on the *compressed* stream. Default 100 MiB, matching the API's upload cap.                                        |
| `CAELUS_MAX_EXTRACTED_BYTES` | no       | Ceiling on the *extracted* tree. Default 800 MiB. This is the bound that matters: a 741-byte archive can expand to 500 KB. |
| `CAELUS_MAX_ENTRIES`         | no       | Archive entry ceiling. Default 100,000.                                                                                    |
| `CAELUS_TERMINATION_LOG`     | no       | Default `/dev/termination-log`.                                                                                            |

## Untrusted input handling

The archive is tenant-supplied and is treated as hostile regardless of the
sandbox around it. Extraction runs through Python's `tarfile` **`data` filter**
— the standard library's purpose-built answer for untrusted archives — plus
explicit bounds applied *before* each member is written:

| Attack                                              | Outcome                                  |
|-----------------------------------------------------|------------------------------------------|
| `../escape.txt`, `../../escape.txt`                 | rejected                                 |
| absolute path `/tmp/escape.txt`                     | rejected                                 |
| symlink or hardlink pointing outside the tree       | rejected                                 |
| entry-count bomb                                    | rejected at `CAELUS_MAX_ENTRIES`         |
| decompression bomb, single or spread across members | rejected at `CAELUS_MAX_EXTRACTED_BYTES` |

The absolute-path rejection is ours rather than the filter's: `data` *rewrites*
an absolute path to a relative one instead of refusing it, which is safe but
would surface much later as an unexplained "no project detected". The size and
entry bounds are checked before extracting each member, so the member that
would breach a limit is never written at all.

## Build output

What this container emits is plain text with no terminal control sequences.

**Tenant build output is a different matter and is deliberately not
sanitized.** BuildKit runs the tenant's build steps in containers of its own,
with the environment coming from the build plan, so nothing set on this
container reaches them — a real build shows `dpkg` emitting bare CR progress
redraws (`Reading database ... 5%\r10%\r…`). A tenant can print arbitrary
bytes, and the platform stores them faithfully rather than rewriting them,
which is why the `build.log` column is `bytea`. Rendering is the reader's
choice; a client that wants a tidy transcript can collapse CR runs itself.

## The two pinned versions must move together

`railpack` (Dockerfile `ARG RAILPACK_VERSION`) and the frontend image
(`FRONTEND_IMAGE` in `build.py`) are a **version-matched pair**. The build plan
`railpack prepare` emits is a contract between them, so bumping one without the
other hands a plan to a frontend that cannot read it.

Currently both are v0.36.4:

```
railpack                     0.36.4
ghcr.io/railwayapp/railpack-frontend@sha256:282e3d0e542c9299c9fc4f938c9a5c45f0666d954264deaea59d13281121a91a
```

To bump: pick the new railpack release, update `RAILPACK_VERSION` and
`RAILPACK_SHA256` from that release's `checksums.txt`, then resolve the
matching frontend digest and update `FRONTEND_IMAGE`:

```bash
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository%3Arailwayapp%2Frailpack-frontend%3Apull" | jq -r .token)
curl -sI -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json" \
  "https://ghcr.io/v2/railwayapp/railpack-frontend/manifests/v<NEW_VERSION>" |
  grep -i docker-content-digest
```

Pinning by digest here is about that coupling, not supply chain — a digest is
content-addressed, and the project already consumes public images by tag
elsewhere.

## Build and publish

**amd64 only.** The cluster node is amd64 and multi-arch is an explicit
non-goal, so the Dockerfile fails the build on any other architecture rather
than producing an image whose `railpack` binary cannot exec.

```bash
cd products/custom/builder
docker build --platform linux/amd64 -t registry.home/caelus/builder:0.1.1 .
docker push registry.home/caelus/builder:0.1.1
```

Then point `builder_image` in `api/app/config.py` (env
`CAELUS_BUILDER_IMAGE`) at the pushed digest, keeping the tag for readability:

## Node prerequisites

Node-level settings are required and **neither is captured by Terraform**;
a rebuilt node fails at two separate points with unrelated-looking errors.

1. `/etc/sysctl.d/99-buildkit-userns.conf` — `kernel.apparmor_restrict_unprivileged_userns=0`.
   Ubuntu 24.04 ships this at `1`, which transitions any unconfined process
   calling `userns_create` into a restrictive AppArmor profile that then denies
   `CAP_SYS_ADMIN` in the new namespace. Setting the pod to
   `appArmorProfile: Unconfined` does **not** help — the transition fires *from*
   the unconfined profile.

The Job additionally needs both `seccompProfile: Unconfined` and
`appArmorProfile: Unconfined` — these cover the *container* profile blocking
`mount`/`unshare`, which is a separate mechanism from the host sysctl above.
