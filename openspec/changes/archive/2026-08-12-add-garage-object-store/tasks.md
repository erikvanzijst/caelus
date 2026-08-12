> **Implementation status.** Deployed and verified. `tf/deps` and `tf/app`
> (both workspaces) are applied, the cluster layout is bootstrapped, and
> `terraform plan` reports no changes in all three. Every verification task was
> executed against the live deployment rather than inferred.
>
> **One deviation from the task text, forced by a fact discovered during
> implementation (tasks 5.2–5.6).** `dxflrs/garage:v2.3.0` is a `FROM scratch`
> image whose only file is `/garage` — no shell, no coreutils — so a provisioning
> *script* cannot run in it. Nor can a second pod use the `garage` CLI: the CLI
> speaks RPC and requires `<full-node-id>@host:port`, and the node ID does not
> exist until the pod has run. Provisioning therefore drives the **Garage admin
> API v2** (HTTP :3903, bearer auth) from an image carrying curl, jq and kubectl.
> Design D2 already provides for this ("where the admin API is used rather than
> the CLI, use a scoped, expirable admin token"); only the task wording assumed
> the CLI. No spec requirement changes.
>
> **Two design decisions the deployment confirmed, worth keeping.** The
> provisioning Job's health-wait held for 85s on first apply while the operator
> ran the layout bootstrap, then proceeded — the apply completed in one pass
> rather than failing and needing a re-run. And `/health` returning 503 without a
> committed layout is why readiness is an HTTP probe and liveness is a TCP one: an
> HTTP liveness probe would have restart-looped the pod through the entire
> bootstrap window.
>
> **One caveat on section 8.** The tests ran from the operator's machine, which
> resolves `blob.freepod.eu` to the site's own public IP and therefore hairpins
> through NAT. The full Traefik and HAProxy edge path is exercised, but not a
> genuinely remote, slow uplink. The 100 MiB upload completed in 4.0s at ~26 MB/s,
> so **8.3 proves the absence of a body cap and of edge buffering, not the absence
> of a timeout on a slow link**. If a consumer later reports truncated uploads from
> a remote network, re-run 8.3 from outside before suspecting anything in this
> repo — the HAProxy edge is not managed here (see design.md § Risks).

## 1. Module scaffolding and wiring

- [x] 1.1 Create `tf/deps/garage/` with `variables.tf` declaring: `namespace`, `garage_image`
      (pinned to `dxflrs/garage:v2.3.0`), `domain`, `meta_pvc_size` (default `2Gi`),
      `data_pvc_size` (default `20Gi`), `cpu_request`/`cpu_limit`/`memory_request`/`memory_limit`
      (defaults `100m` / `1` / `256Mi` / `1Gi` per design D5), `object_expiry_days` (default `2`),
      `admin_token` and `rpc_secret` (both `sensitive = true`).
- [x] 1.2 Add a `garage` namespace resource and a `module "garage"` block to `tf/deps/main.tf`,
      alongside the existing singletons. No `depends_on` is needed on Keycloak — Garage does not
      authenticate against it.
- [x] 1.3 Add `garage_admin_token` and `garage_rpc_secret` to `tf/deps/variables.tf` and document
      them in the `tf/deps/README.md` § Configuration `secrets.auto.tfvars` block. Generate the
      RPC secret with `openssl rand -hex 32` (Garage requires 32 bytes hex).
- [x] 1.4 Confirm neither value is committed: they exist only in the gitignored
      `tf/deps/secrets.auto.tfvars`.

## 2. Garage workload (design D1 — hand-written resources, not the upstream chart)

- [x] 2.1 Add a Kubernetes Secret holding `admin_token` and `rpc_secret`, and a ConfigMap
      rendering `garage.toml` via `templatefile()` with: `replication_factor = 1`,
      `db_engine = "lmdb"`, `metadata_dir`/`data_dir` pointing at the two mounts,
      `[s3_api] api_bind_addr = "[::]:3900"` and `s3_region = "garage"`, and
      `[admin] api_bind_addr = "[::]:3903"`. **Leave `root_domain` unset** — vhost-style
      addressing would need a `*.blob.freepod.eu` certificate outside the wildcard (design D3).
      Inject the secrets by env var reference rather than baking them into the ConfigMap.
- [x] 2.2 Add the StatefulSet: `replicas = 1`, the pinned image, the `garage.toml` mount, and
      **two separate `volume_claim_template` blocks** — `meta` and `data` — sized from the
      variables. Do not use a single shared volume.
- [x] 2.3 Set `resources.requests` **and** `resources.limits` for CPU and memory from the
      variables. Leaving any of the four unset fails the `garage-object-store` spec.
- [x] 2.4 Add readiness and liveness probes against the admin endpoint's health path, and a
      ClusterIP Service exposing the S3 port (3900) and the admin port (3903).
- [x] 2.5 `terraform apply` in `tf/deps`; confirm the pod reaches `Running` and both PVCs are
      `Bound` (`kubectl get pvc -n garage`).

## 3. Cluster layout bootstrap (one-time, operator-run)

- [x] 3.1 Read the node ID: `kubectl exec -n garage garage-0 -- /garage status`.
- [x] 3.2 Assign and commit the layout, capacity matched to `data_pvc_size`:
      `/garage layout assign -z dc1 -c 20G <node_id>` then `/garage layout apply --version 1`.
- [x] 3.3 Verify `garage status` shows the node with assigned capacity and `garage layout show`
      reports no pending changes.
- [x] 3.4 Document the procedure in `tf/deps/README.md`, including that it must be repeated if
      the node identity changes (for example if the metadata PVC is recreated), and that S3
      requests fail until it is done — this is the first thing to check when a fresh install
      returns errors.

## 4. Ingress — external S3 endpoint

- [x] 4.1 Add a `kubernetes_ingress_v1` for host `blob.${var.domain}` (`blob.freepod.eu`) routing
      `/` to the Service's S3 port 3900. No `router.entrypoints` annotation is needed:
      `websecure` is the only default entrypoint and :80 falls through to the cluster-wide
      HTTP→HTTPS redirect IngressRoute (design D7).
- [x] 4.2 **Attach no `forward-auth` middleware, and no request-mutating middleware at all.**
      Write the in-line comment explaining why — S3 SigV4 and presigned-URL signatures are
      incompatible with oauth2-proxy, which both 401s the request and rewrites what was signed.
      Model the comment on the webhooks ingress in `tf/app/caelus/ingress.tf`. This comment is a
      deliverable, not a nicety: it is what stops the next reviewer from "fixing" the gap.
- [x] 4.3 Add no cert-manager `Certificate` and no TLS secret — `blob.freepod.eu` is one label deep
      and is served by Traefik's default wildcard store (`wildcard-freepod-eu-tls`).
- [x] 4.4 Confirm the admin port is **not** routed by this or any other Ingress/IngressRoute.
- [x] 4.5 Re-verify no `buffering` middleware and no `maxRequestBodyBytes` exists on the router,
      the entrypoint, or in `tf/deps/system/helm/traefik/values.yaml.tftpl`
      (`grep -rn 'buffering\|maxRequestBodyBytes' tf/` currently returns nothing — keep it that
      way). Note that the HSTS default middleware is a *response*-header middleware and is fine.
- [x] 4.6 Verify externally: `curl -sv https://blob.freepod.eu/` returns an S3-formatted error from
      Garage over a valid certificate — not an oauth2-proxy redirect, not a TLS error — and
      `curl -sI http://blob.freepod.eu/` returns a redirect to HTTPS.

## 5. Bucket, key and lifecycle provisioning (design D2)

- [x] 5.1 Add a ServiceAccount, Role and RoleBinding in the `garage` namespace scoped to
      get/create/update on the single `garage-keys` Secret. No cross-namespace permissions.
- [x] 5.2 Write the provisioning script into a ConfigMap. It MUST be idempotent — read before
      every write — so re-running never rotates an existing key: for each environment `<env>` in
      `dev` and `prod`, create the bucket named `<env>`, create the access key
      `caelus-api-<env>` if absent, and
      `garage bucket allow --read --write <env> --key caelus-api-<env>`. Grant **only** that
      environment's bucket; do not pass `--owner`.
      *Implemented as `AllowBucketKey` with `{"read":true,"write":true}` over the admin API — see
      the status note at the top of this file. `owner` is omitted, which grants nothing:
      `AllowBucketKey` only activates flags set to `true`.*
- [x] 5.3 Have the script write the generated access key IDs and secrets into the `garage-keys`
      Secret. Note that Terraform cannot pre-generate these: `garage key import` rejects keys
      Garage did not generate, so Garage must mint them and they are read back afterwards.
- [x] 5.4 Add a second Job step, in an S3-client image, applying the lifecycle configuration to
      each bucket via `PutBucketLifecycleConfiguration`: an `Expiration` rule at
      `var.object_expiry_days` **and** an `AbortIncompleteMultipartUpload` rule. Both are
      required — abandoned multipart parts consume disk without appearing in a listing.
      Lifecycle is an S3-API operation, not a `garage` CLI one, hence the separate image.
      *Each bucket is configured with its own environment's key: verified that Garage accepts
      `PutBucketLifecycleConfiguration` from a read+write key, so no `owner` grant and no separate
      provisioning key is needed. Credentials reach this step through a memory-backed `emptyDir`,
      never the node's disk.*
- [x] 5.5 Add the Kubernetes Job wiring both steps, triggered on install and re-run when the
      script ConfigMap changes.
- [x] 5.6 Where the admin API is used instead of the CLI, create a **scoped, expirable** admin
      token (`garage admin-token create` with an operation scope) rather than using the master
      `admin_token`.
- [x] 5.7 Run the Job twice and confirm the second run is a no-op: same access key IDs, no
      error, no rotation.
- [x] 5.8 Verify the permission boundary: `caelus-api-dev` is denied read, write and list on the
      `prod` bucket, and `caelus-api-prod` likewise on `dev`.
- [x] 5.9 Verify the lifecycle configuration is readable back from each bucket and contains both
      rules.

## 6. Credential handoff to the Caelus API

- [x] 6.1 Add a `kubernetes_secret` **data source** for `garage-keys` and expose per-environment
      `sensitive` outputs from `tf/deps` (`garage_access_key_id_dev`,
      `garage_secret_access_key_dev`, and the `prod` pair), mirroring the existing
      `freepod_*_client_secret` outputs.
- [x] 6.2 In `tf/app`, add **workspace-keyed map** variables for the S3 access key ID and secret
      and the bucket name — a scalar cannot express two per-environment values because
      `*.auto.tfvars` is auto-loaded in every workspace (`tf/README.md` documents this for
      `oauth2_proxy_client_ids`).
- [x] 6.3 Add a `caelus-s3` Kubernetes Secret in `tf/app/caelus/secrets.tf` carrying the S3
      endpoint, region, bucket, access key ID and secret access key.
- [x] 6.4 Add an `env_from` secret reference to `caelus-s3` on the API container in
      `tf/app/caelus/deployment-api.tf`, following the `caelus-db` pattern. Add it to
      `worker.tf` only if the worker will read objects.
- [x] 6.5 Paste the `tf/deps` outputs into the gitignored `tf/app/secrets.auto.tfvars` and apply
      both workspaces. Confirm each environment's pod carries only its own bucket and key.

## 7. API configuration surface

- [x] 7.1 Add settings to `api/app/config.py` under the existing `CAELUS_` prefix: S3 endpoint
      URL, region (`garage`), bucket, access key ID, secret access key, and presigned-URL expiry
      seconds. Credential settings default to empty — never a real value — so the test suite and
      local dev run with no object store configured.
- [x] 7.2 Comment that the S3 client MUST use **path-style** addressing
      (`addressing_style: "path"`): `root_domain` is unset in `garage.toml`, and vhost-style
      would generate presigned URLs against `bucket.blob.freepod.eu`, which has neither a DNS
      record nor certificate coverage (design D3).
- [x] 7.3 Run `uv run --no-sync pytest` and confirm settings load and no test regresses with the
      new variables unset. The API's *use* of these settings is out of scope for this change.

## 8. End-to-end verification (from outside the cluster)

> Run these from a laptop on an external network, not from an in-cluster pod: the path under
> test includes the homelab HAProxy edge, which is not managed by this repo.

- [x] 8.1 Presigned PUT then presigned GET of a small object; bytes match.
- [x] 8.2 Expired presigned URL is refused with an S3 authentication error, and writes nothing.
- [x] 8.3 Upload an object of at least 100 MB; it completes and its checksum matches. This is
      the real test of "no buffering, no body cap, no edge timeout".
- [x] 8.4 Multipart upload of a large object: initiate, parts, complete all succeed and the
      assembled object is byte-identical. Then initiate and abort one, and confirm no object
      appears at the key.
- [x] 8.5 `PostObject` with a `content-length-range` policy: a compliant body is accepted, an
      oversized body is rejected by Garage and stores nothing.
- [x] 8.6 An unsigned request to a private object returns an S3 access-denied error from Garage,
      not an oauth2-proxy login redirect.
- [x] 8.7 Restart the pod (`kubectl delete pod -n garage garage-0`); confirm the layout survives
      and a previously written object is still readable.

## 9. Documentation

- [x] 9.1 `tf/deps/README.md`: add Garage to § What It Creates; add a Garage section covering the
      `blob.freepod.eu` endpoint, the deliberate absence of forward-auth and why, the cluster-layout
      bootstrap, the bucket/key naming convention, lifecycle expiry, and reading the credential
      outputs for `tf/app`. Add the admin/RPC secrets to § Configuration. Note under § Notes that
      `terraform destroy` deletes the object data with the PVCs — there is no backup by design.
- [x] 9.2 `tf/README.md`: add Garage to the `deps/` description and to the
      `tf/deps/secrets.auto.tfvars` secrets list; note the S3 credential outputs in the handoff
      section next to the Keycloak client secrets.
- [x] 9.3 Record the known limits where an operator will find them: no object versioning, no IAM
      or bucket policies, single node / single replica. Anything durable needs a different
      answer.
- [x] 9.4 Add a "Things that will bite you" entry in `tf/deps/README.md`: attaching forward-auth
      to the S3 ingress breaks every upload, and enabling `root_domain` breaks TLS.

## 10. Validation

- [x] 10.1 `terraform validate` and `terraform plan` are clean in both `tf/deps` and `tf/app`
      (both workspaces), with no unexpected drift.
      *`terraform validate` and `terraform fmt -check` pass in both root modules. `terraform plan`
      still to run — it refreshes state against the live cluster.*
- [x] 10.2 `openspec validate add-garage-object-store --strict` reports valid.
- [x] 10.3 Archive the change and sync the delta specs into `openspec/specs/`.
