## Why

Caelus has no object store. Everything durable today is either Postgres rows or a
per-workload PVC, and neither can absorb a large binary blob uploaded **from outside the
cluster** by a client that must not be handed cluster credentials. The concrete need is a
write-once / read-once transfer channel: an external CLI on a developer's laptop PUTs a
compressed archive (tens to low hundreds of MB) straight to storage via a **presigned URL
minted by the Caelus API**, and an in-cluster job later GETs it back via a second presigned
URL. The object is garbage within ~24h.

A presigned URL is exactly the primitive that makes this safe — the API stays the only holder
of the S3 credentials, the bytes never transit the API pod, and the grant is scoped to one
object and expires on its own. Nothing in the current stack can mint one. This change adds
**Garage** (https://garagehq.deuxfleurs.fr/) as a shared `tf/deps` singleton to provide it.

Garage is written as a **general-purpose platform object store**, not tailored to the first
consumer. The consumer's shape only fixes the hard requirements (external reachability, native
S3 auth, big bodies, declarative expiry).

**Why Garage, and not the obvious alternatives:**

- **MinIO is not a candidate.** It went into maintenance mode in December 2025 and the
  community-edition repository was archived in February 2026. Adopting an archived storage
  engine for a new dependency is not defensible.
- **RustFS was considered and rejected.** It is still pre-1.0 — the newest tags are
  `1.0.0-beta.12` / `1.0.0-rc.1`, with no GA — and it shipped IAM privilege-escalation bugs
  that were patched during alpha. Not a foundation for a credential-minting path.
- **Garage is v2.3.0 (April 2026), a stable release**, AGPLv3, maintained by the Deuxfleurs
  non-profit association, which self-hosts on it. It is designed for exactly this deployment
  class: small, self-hosted, low node count, commodity disks.

**On the AGPL.** It is a non-issue as deployed. Garage runs unmodified, as a separate internal
network service reached over its own S3 API; we distribute nothing and link nothing. No Freepod
user interacts with Garage directly — the only public surface is a presigned URL.

**Known Garage limits, recorded honestly.** Garage implements **no object versioning** and
**no IAM, bucket policies or ACLs**. Neither blocks the ephemeral-blob use case (single-writer,
single-reader, discard). Both matter if the store is later repurposed to hold backups or
anything needing point-in-time recovery or multi-tenant policy — that would be a new
evaluation, not an extension of this one.

## What Changes

- **New `tf/deps/garage/` module.** A Garage StatefulSet in its own `garage` namespace,
  alongside `keycloak` and `mailer`. Single-node k3s → `replicaCount: 1`,
  replication factor `1`. Separate `meta` and `data` PVCs (Garage wants metadata on the faster
  disk should that ever become a choice here).
- **External S3 endpoint at `blob.freepod.eu`, TLS-terminated by Traefik.** A single-label
  subdomain deliberately: `*.freepod.eu` is served by Traefik's default certificate store
  (`wildcard-freepod-eu-tls`, `tf/deps/system/helm/traefik/values.yaml.tftpl`), so `blob.freepod.eu`
  needs **no per-app cert-manager Certificate** — the same reasoning `api/app/config.py`
  records for `tls_cluster_issuer`. A two-label name like `blob.objects.freepod.eu` would fall
  outside the wildcard and force a per-app cert for no benefit.
- **The Garage ingress deliberately omits the `forward-auth` middleware.** This is the load-
  bearing decision of the change, not an oversight. Garage authenticates with native S3 SigV4
  access keys and presigned-URL signatures; routing it through oauth2-proxy would reject every
  request as unauthenticated *and* mutate the signed request so the signature no longer
  verifies. The omission is modeled on — and must be commented like — the webhooks ingress in
  `tf/app/caelus/ingress.tf`, which bypasses oauth2-proxy for the same class of reason. An
  auth-less ingress is a landmine unless the justification sits next to it in the code.
- **Large request bodies pass the edge unbuffered and uncapped.** No `buffering` middleware and
  no body-size limit anywhere in the Traefik path (verified: there is none in `tf/` today).
  This becomes a stated, testable expectation rather than an accident of current config.
- **Presigned URLs, `PostObject` and multipart upload all work end-to-end through the ingress.**
  All three are implemented by Garage (verified against its S3 compatibility reference).
  `PostObject` matters specifically because its policy document supports
  `content-length-range`, which is how an upload size cap gets enforced **server-side** instead
  of being trusted from the client.
- **Bucket lifecycle expiration is part of provisioning, not an afterthought.** Garage
  implements exactly two lifecycle actions — `Expiration` and `AbortIncompleteMultipartUpload`
  — which is precisely what an ephemeral-object bucket needs. Declarative expiry means no
  reaper CronJob and no cleanup code to maintain.
- **Bucket and access-key provisioning is Garage-native.** Garage has no IAM, so there is no
  S3-policy-shaped Terraform resource to use. Provisioning goes through the Garage admin API /
  `garage` CLI and its per-access-key-per-bucket permission model. The change names an explicit
  bootstrap mechanism rather than leaving it implicit.
- **Per-environment separation by naming, not by instance.** `tf/deps/` is a workspace-less
  shared singleton (see `AGENTS.md` § Terraform and `tf/deps/README.md`), so one Garage serves
  both environments and separation lives in bucket + key names (`…-dev` / `…-prod`), mirroring
  how Keycloak splits `freepod-dev` / `freepod-prod`.
- **Hard resource bounds — a first-class requirement here.** The k3s node is a single libvirt VM
  (RAM raised 16→24 GB after OOM events, with an OOM hook and a swap fence) that also runs
  Postgres, Keycloak, Traefik, the monitoring stack and every tenant workload, and it has a
  history of disk pressure. Garage gets explicit CPU/memory requests **and** limits and a
  size-capped data PVC.
- **Credential delivery to the Caelus API.** A Kubernetes Secret holding the S3 endpoint,
  region, bucket and access key/secret, consumed via `env_from` exactly like `caelus-db` in
  `tf/app/caelus/`, plus the matching `CAELUS_*` settings in `api/app/config.py`. The settings
  are in scope; the API's *use* of them (minting URLs) is not.
- **Manual cluster-layout bootstrap.** A fresh Garage node holds no layout until one is assigned
  and committed. This is a documented one-time step, covered in the task list.
- **Docs.** `tf/README.md` and `tf/deps/README.md` updated to list Garage as a shared singleton,
  with its bootstrap steps and the auth-bypass rationale.

Not in scope: any consumer of the store, the presigned-URL endpoints themselves, and any
`tf/app/` workload change beyond wiring the credentials Secret.

## Capabilities

### New Capabilities

- `garage-object-store`: the deployment shape of the shared Garage singleton — namespace,
  StatefulSet, replication factor, the separate `meta`/`data` PVCs and their size caps, the
  mandatory CPU/memory requests and limits, and the one-time cluster-layout bootstrap that
  makes a fresh node serviceable.
- `garage-s3-edge`: external exposure of the S3 API at `blob.freepod.eu` — TLS from Traefik's
  default wildcard store, the **deliberate absence** of the `forward-auth` middleware and its
  in-line justification, unbuffered and uncapped request bodies, and the requirement that
  presigned GET/PUT, `PostObject` and multipart upload all function through the edge.
- `garage-bucket-provisioning`: Garage-native bucket and access-key provisioning — the
  per-access-key-per-bucket permission grants, per-environment `-dev`/`-prod` naming, the
  lifecycle `Expiration` rule applied at bucket-creation time, and delivery of the resulting
  credentials to the Caelus API as a Secret plus `CAELUS_*` settings.

### Modified Capabilities

<!-- None. No existing spec's requirements change: this adds a new dependency and its own
     edge routing. `freepod-tls-termination` is relied upon as-is (the wildcard default
     certificate store), not altered. -->

## Impact

- **Terraform (`tf/deps/`):** new `garage/` module; new `garage` namespace and `module "garage"`
  wiring in `tf/deps/main.tf`; new variables (data/meta PVC sizes, resource bounds, chart or
  image version, admin token) and a new `secrets.auto.tfvars` entry for the Garage admin token /
  RPC secret. New outputs for the per-environment access keys, to be pasted into
  `tf/app/secrets.auto.tfvars` — the two root modules are deliberately not coupled with
  `terraform_remote_state`, matching the existing Keycloak client-secret handoff.
- **Terraform (`tf/app/`):** a `caelus-s3` Kubernetes Secret and an `env_from` reference on the
  API (and worker, if it will read objects), following the `caelus-db` pattern in
  `tf/app/caelus/`.
- **API (`api/app/config.py`):** new `CAELUS_*` settings for the S3 endpoint, region, bucket,
  access key and secret, and the presigned-URL TTL. No endpoint or service code in this change.
- **Cluster resources:** one additional StatefulSet pod and two PVCs on an already-constrained
  single node. Capped by explicit requests/limits; the data PVC size is the hard ceiling on
  what this dependency can do to node disk pressure.
- **Operational:** one new manual bootstrap step (assign + commit the cluster layout) on first
  install and on any node-ID change. Documented, not automated, because it is genuinely
  one-time and layout mistakes are not cheaply reversible.
- **Security posture:** a new *unauthenticated-at-the-edge* public hostname. The security
  boundary moves entirely into Garage's SigV4 verification and into the API's control over who
  gets a presigned URL and for how long. This is a deliberate trade, and the reason the
  middleware omission must be documented in-line.
- **Licensing:** AGPLv3 enters the deployment as an unmodified network service. No effect on
  Caelus's own licensing.
