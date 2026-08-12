## Context

See `proposal.md` § Why for motivation and for the MinIO / RustFS comparison. This document
covers only how Garage gets built into the existing infrastructure.

The constraints that actually shape the design:

- **`tf/deps` is a workspace-less shared singleton** (`AGENTS.md` § Terraform,
  `tf/deps/README.md`). One Garage, two environments.
- **The two Terraform root modules are deliberately not coupled** with `terraform_remote_state`.
  Credentials cross the boundary by an operator pasting a `terraform output` into
  `tf/app/secrets.auto.tfvars` — the established ritual for the Keycloak client secrets.
- **One k3s node, and a stressed one.** A libvirt VM whose RAM went 16→24 GB after OOM events,
  with an OOM hook and a swap fence, plus a history of disk pressure. Everything runs here.
- **The edge is Traefik, self-managed** (`tf/deps/system/helm/traefik/`), reached across
  clusters by a homelab HAProxy over PROXY protocol. `websecure` (:443) is the only default
  entrypoint; :80 falls through to a cluster-wide HTTP→HTTPS redirect IngressRoute. Traefik's
  default certificate store serves the `*.freepod.eu` wildcard for any otherwise-unmatched SNI.
- **Verified against upstream while writing this** (Garage v2.3.0): path-style S3 addressing is
  always enabled and vhost-style is opt-in via `root_domain`; lifecycle supports exactly
  `Expiration` and `AbortIncompleteMultipartUpload`; `PostObject`, presigned URLs and the full
  multipart API are implemented; there is no versioning, no IAM, no bucket policies, no ACLs.

## Goals / Non-Goals

**Goals:**

- A general-purpose platform object store, usable by any future consumer.
- External S3 access with native SigV4 / presigned-URL authentication, structurally separated
  from the oauth2-proxy session layer.
- Provisioning that survives `terraform apply` being re-run, and that an operator can reason
  about six months from now.
- Blast radius bounded by construction: CPU, memory and disk all capped.

**Non-Goals:**

- Durability guarantees beyond "one node, one replica, backed by a PVC". This is a transfer
  buffer, not a system of record. Nothing that matters should be *only* in Garage.
- Multi-node, multi-zone, or any geo-distribution — Garage's actual specialty, unused here.
- Object versioning or point-in-time recovery. Garage does not implement versioning at all.
- Any consumer of the store, including the presigned-URL endpoints themselves.

## Decisions

### D1. Hand-written Terraform resources rather than the upstream Helm chart

The finding that prompted it: Garage's Helm chart is **not published to a Helm repository or an
OCI registry**. It lives in-tree at `script/helm/garage` in the Deuxfleurs forge. Neither
existing pattern in this repo therefore applies — not `helm_release` with a `repository` URL
(Traefik) and not `helm_release` with a release-tarball URL (Loki). Consuming it means vendoring
a copy of somebody else's templates into this repo and reconciling them by hand on every bump.
The repo already carries that tax once, and says so out loud: the forked Prometheus
`scrape_configs.yaml` is annotated *"reconcile it when bumping the chart version."*

Two further observations argue the same way. The chart's `values.yaml` still exposes
`garage.replicationMode`, the pre-v1 spelling — Garage v2 configures `replication_factor` — so
the chart trails the release we would pin. And its `persistence.data.size` default is `100Mi`,
which is not a usable default for object storage; every value that matters would be overridden
anyway.

Against that, Garage is a single static binary with a TOML config. The resources are a
ConfigMap, a StatefulSet with two `volumeClaimTemplates`, and a ClusterIP Service — comfortably
under 200 lines, and the same shape as the hand-written `keycloak/` and `mailer/` modules that
are already the dominant idiom in `tf/deps`.

- *Alternative: vendor the chart under `tf/deps/garage/helm/garage/` and use
  `chart = "${path.module}/helm/garage"`.* Viable, and the right answer if the chart later gets
  published — the switch is contained. Rejected for now: it imports third-party templates that
  must be diffed on every upgrade, to render resources we can write directly and understand
  completely.
- *Alternative: the third-party `garage-operator`.* An extra controller running permanently on
  the node, and another dependency to keep current, in exchange for CRDs we would use once.

The specs are written chart-agnostically, so this decision is genuinely reversible.

### D2. Provisioning by an idempotent bootstrap Job, with the Keycloak-style manual handoff

Garage has no IAM, so there is no S3-policy-shaped Terraform resource. Worse for the obvious
design: **`garage key import` rejects keys Garage did not generate** (the access key ID carries
a checksum), so the tidy pattern of "Terraform generates the credential with `random_password`,
tells Garage about it, writes the Secret from state" is not available. Garage must mint the key,
and something has to read it back out.

The chosen shape:

1. Terraform manages a **Kubernetes Job** in the `garage` namespace, plus a ConfigMap holding
   its script and a ServiceAccount with RBAC scoped to one Secret in that namespace.
2. Step one of the Job runs in the Garage image and, **guarding every step on a read first** so
   a re-run is a no-op:
   - creates two **buckets**, `dev` and `prod`;
   - creates two **access keys**, `caelus-api-dev` and `caelus-api-prod`, if absent;
   - grants each key read+write on **only** its own environment's bucket
     (`caelus-api-dev` → `dev`, `caelus-api-prod` → `prod`);
   - writes the generated key material into a `garage-keys` Secret in the `garage` namespace.
3. Step two runs in an S3 client image and applies the lifecycle configuration to each bucket
   (see D4). Lifecycle is an S3-API operation — `PutBucketLifecycleConfiguration` — not a
   `garage` CLI one, which is why this is a second step with a different image rather than more
   lines in the first script.
4. Terraform reads `garage-keys` back through a `kubernetes_secret` **data source** and exposes
   the values as outputs, so the operator runs
   `terraform output -raw garage_access_key_id_dev` exactly as they already run
   `terraform output -raw freepod_dev_client_secret`, and pastes into
   `tf/app/secrets.auto.tfvars`. `tf/app` then builds the `caelus-s3` Secret and mounts it with
   `env_from`, the `caelus-db` pattern.

The tfvars entries are **maps keyed by workspace**, like `oauth2_proxy_client_ids` — `tf/app`
auto-loads `*.auto.tfvars` in every workspace, so a scalar cannot carry two per-environment
values. `tf/README.md` already documents that trap.

Re-running the Job on each apply is deliberate: it makes the provisioning declarative in effect
even though Garage offers no declarative surface, and it repairs hand-made drift.

- *Alternative: a purely manual runbook (`kubectl exec ... garage bucket create`).* Fewer moving
  parts, and it matches how the cluster layout is handled. Rejected for buckets and keys because
  those are six commands across two environments with a permission model that is easy to get
  subtly wrong (granting a dev key on the prod bucket produces no error, just a hole), and
  because nothing would then re-assert them.
- *Alternative: the `restapi` Terraform provider against Garage's admin API.* True Terraform
  state for buckets and keys — genuinely the nicest model. Rejected on dependencies: a
  third-party provider, plus the admin API is intentionally not exposed outside the cluster
  (see D6), so `terraform apply` would need a live port-forward to work at all.
- *Alternative: have the Job write the Secret straight into the `caelus` namespaces.* Removes
  the manual paste, but needs cross-namespace write RBAC from `tf/deps` into `tf/app`'s
  namespaces, quietly inverting the ownership boundary between the two root modules.

Where the admin API is used rather than the CLI, use a **scoped, expirable admin token**
(Garage v2 supports `garage admin-token create` with an operation scope), not the master
`admin_token`.

### D3. `blob.freepod.eu`, path-style addressing, `root_domain` left unset

Single-label host, so Traefik's default wildcard certificate covers it with no cert-manager
`Certificate` and no ACME challenge — the same reasoning `api/app/config.py` records against
`tls_cluster_issuer`.

The consequence worth stating explicitly, because it is easy to get wrong later: Garage's
`root_domain` (vhost-style addressing, `bucket.blob.freepod.eu`) **must be left unset**. Turning
it on would put bucket names in the hostname, and `bucket.blob.freepod.eu` is two labels deep —
outside `*.freepod.eu`, so every bucket would need its own certificate. Path-style requests are
always enabled in Garage regardless, so this costs nothing; it just means the Caelus API's S3
client must be configured for **path-style** addressing (`addressing_style: path` in botocore),
or it will generate presigned URLs against a hostname with no certificate and no DNS record.

`s3_region` is set to Garage's default, `garage`, and surfaced to the API as a setting so the
signing region matches on both sides.

### D4. Expiry as bucket configuration, not as a job

Both lifecycle actions Garage implements get used, and they cover different failures:

- `Expiration` after N days reclaims completed objects.
- `AbortIncompleteMultipartUpload` after N days reclaims the parts of uploads that never
  completed. These consume disk while never appearing in a bucket listing — precisely the kind
  of invisible growth that produced the earlier disk-pressure incident.

N is a Terraform variable; ~2 days suits a ~24h object lifetime with slack.

- *Alternative: a reaper CronJob.* More code, another workload on the node, and it can be
  skipped, fail silently, or be forgotten during a refactor. Expiry as a property of the bucket
  cannot be.

### D5. Sizing

Starting points, all module variables:

| | value | reasoning |
|---|---|---|
| `requests` | `100m` / `256Mi` | idle Garage is cheap; do not over-reserve on a full node |
| `limits` | `1` CPU / `1Gi` | caps a multipart-upload burst; an upload slows or fails instead of the node OOMing |
| meta PVC | `2Gi` | LMDB metadata; small but must not be starved |
| data PVC | `20Gi` | the hard ceiling on this dependency's contribution to disk pressure |

`db_engine = "lmdb"` (the Garage default) rather than `sqlite`.

Under-sizing here fails loudly (uploads fail) while over-sizing fails quietly and takes tenant
workloads with it, so these start conservative and are meant to be tuned from observed usage.

### D6. Admin surface stays inside the cluster

Only the S3 port is routed by an Ingress. The admin API keeps a ClusterIP-only Service, reached
via `kubectl port-forward` or `kubectl exec`. The admin token and the `rpc_secret` come from
`tf/deps/secrets.auto.tfvars` (gitignored) into a Kubernetes Secret. Publishing an admin
endpoint that can mint access keys, behind no session layer, next to a deliberately auth-free S3
ingress, is not a combination worth having.

### D7. Which middleware the ingress may carry

The spec's prohibition is on **request**-mutating middleware. The cluster-wide
`kube-system-headers-hsts@kubernetescrd` default middleware on the `websecure` entrypoint sets a
response header only, touches nothing inside SigV4's signed scope, and is therefore fine — worth
recording so a future reader does not "fix" the ingress by trying to exclude it.

The `web` entrypoint is deliberately untouched, so the existing HTTP→HTTPS redirect
IngressRoute applies to `blob.freepod.eu` for free and no `router.entrypoints` annotation is
needed.

## Risks / Trade-offs

- **A public hostname with no edge authentication.** → The security boundary moves wholly into
  Garage's SigV4 verification and the API's control over who gets a presigned URL and for how
  long. Mitigated by keeping presigned TTLs short, scoping each key to one bucket, keeping the
  admin API off the internet, and — critically — the in-line comment that stops a future
  reviewer from "fixing" the missing middleware and silently breaking every upload.
- **Client-declared upload size is not trustworthy.** → `PostObject` with a
  `content-length-range` policy enforces the cap in Garage. A plain presigned PUT cannot enforce
  one, so any consumer that needs a hard cap must use `PostObject`. This is the specific reason
  `PostObject` is a spec requirement and not an optional extra.
- **Single node, single replica, no versioning.** → Losing the PVC loses the objects, and an
  overwrite is unrecoverable. Acceptable only for write-once/read-once ephemeral blobs; it must
  be re-evaluated before anything durable (backups, user content) is put here. Recorded in the
  proposal as a known limit rather than buried.
- **Disk pressure on a node with a history of it.** → Capped data PVC, both lifecycle rules, and
  short expiry. The PVC size is a real ceiling: Garage fails writes rather than filling the
  node's root filesystem.
- **The homelab HAProxy edge sits in front of Traefik and is not in this repo.** → A large
  upload over a slow uplink can be severed by an HAProxy timeout that no amount of Terraform
  here will fix. Verify with a real large upload from outside the network, not with an
  in-cluster `curl`; multipart upload with retries is the mitigation if a timeout turns up.
- **AGPLv3 in the deployment.** → Unmodified, run as a separate network service, not linked and
  not distributed. No effect on Caelus. Worth revisiting only if Garage is ever patched locally.
- **Hand-written resources mean owning the upgrade path (D1).** → Garage's config is a small
  stable TOML and the version is pinned, so upgrades are a version bump plus a changelog read.
  The escape hatch, if the chart is ever published, is to switch `tf/deps/garage/` to a
  `helm_release`; the specs do not constrain the mechanism.
- **Two provisioning paths for the same instance** — Terraform for buckets and keys, an operator
  runbook for the cluster layout. → Genuinely unavoidable: layout assignment depends on a node
  ID that does not exist until the pod runs, and a wrong layout is not cheaply reversible. Kept
  explicit in `tf/deps/README.md` rather than hidden in a script.

## Migration Plan

No migration: nothing exists to move. Deployment order:

1. `terraform apply` in `tf/deps` — namespace, config, StatefulSet, PVCs, Service, Ingress. The
   pod comes up **with no layout** and refuses S3 requests. This is expected.
2. Operator assigns and commits the cluster layout (`garage layout assign` / `garage layout
   apply`) via `kubectl exec`. One time, and again only if the node identity changes.
3. Re-run `terraform apply` (or let the bootstrap Job run) to create buckets, keys, permissions
   and lifecycle rules.
4. `terraform output` the credentials, paste into `tf/app/secrets.auto.tfvars` as
   workspace-keyed maps.
5. `terraform apply` in `tf/app` for each workspace to create the `caelus-s3` Secret and mount
   it on the API.

**Rollback.** No consumer exists yet, so rollback is `terraform destroy -target=module.garage`
plus removing the `tf/app` Secret — nothing else breaks. Once a consumer exists this stops being
true, which is an argument for landing this change on its own. Note that destroying the module
deletes the PVCs and the objects with them; there is no backup by design.
