## 1. Module scaffolding and wiring

- [ ] 1.1 Create `tf/deps/garage/` with `variables.tf` declaring: `namespace`, `garage_image`
      (pinned to `dxflrs/garage:v2.3.0`), `domain`, `meta_pvc_size` (default `2Gi`),
      `data_pvc_size` (default `20Gi`), `cpu_request`/`cpu_limit`/`memory_request`/`memory_limit`
      (defaults `100m` / `1` / `256Mi` / `1Gi` per design D5), `object_expiry_days` (default `2`),
      `admin_token` and `rpc_secret` (both `sensitive = true`).
- [ ] 1.2 Add a `garage` namespace resource and a `module "garage"` block to `tf/deps/main.tf`,
      alongside the existing singletons. No `depends_on` is needed on Keycloak — Garage does not
      authenticate against it.
- [ ] 1.3 Add `garage_admin_token` and `garage_rpc_secret` to `tf/deps/variables.tf` and document
      them in the `tf/deps/README.md` § Configuration `secrets.auto.tfvars` block. Generate the
      RPC secret with `openssl rand -hex 32` (Garage requires 32 bytes hex).
- [ ] 1.4 Confirm neither value is committed: they exist only in the gitignored
      `tf/deps/secrets.auto.tfvars`.

## 2. Garage workload (design D1 — hand-written resources, not the upstream chart)

- [ ] 2.1 Add a Kubernetes Secret holding `admin_token` and `rpc_secret`, and a ConfigMap
      rendering `garage.toml` via `templatefile()` with: `replication_factor = 1`,
      `db_engine = "lmdb"`, `metadata_dir`/`data_dir` pointing at the two mounts,
      `[s3_api] api_bind_addr = "[::]:3900"` and `s3_region = "garage"`, and
      `[admin] api_bind_addr = "[::]:3903"`. **Leave `root_domain` unset** — vhost-style
      addressing would need a `*.blob.freepod.eu` certificate outside the wildcard (design D3).
      Inject the secrets by env var reference rather than baking them into the ConfigMap.
- [ ] 2.2 Add the StatefulSet: `replicas = 1`, the pinned image, the `garage.toml` mount, and
      **two separate `volume_claim_template` blocks** — `meta` and `data` — sized from the
      variables. Do not use a single shared volume.
- [ ] 2.3 Set `resources.requests` **and** `resources.limits` for CPU and memory from the
      variables. Leaving any of the four unset fails the `garage-object-store` spec.
- [ ] 2.4 Add readiness and liveness probes against the admin endpoint's health path, and a
      ClusterIP Service exposing the S3 port (3900) and the admin port (3903).
- [ ] 2.5 `terraform apply` in `tf/deps`; confirm the pod reaches `Running` and both PVCs are
      `Bound` (`kubectl get pvc -n garage`).

## 3. Cluster layout bootstrap (one-time, operator-run)

- [ ] 3.1 Read the node ID: `kubectl exec -n garage garage-0 -- /garage status`.
- [ ] 3.2 Assign and commit the layout, capacity matched to `data_pvc_size`:
      `/garage layout assign -z dc1 -c 20G <node_id>` then `/garage layout apply --version 1`.
- [ ] 3.3 Verify `garage status` shows the node with assigned capacity and `garage layout show`
      reports no pending changes.
- [ ] 3.4 Document the procedure in `tf/deps/README.md`, including that it must be repeated if
      the node identity changes (for example if the metadata PVC is recreated), and that S3
      requests fail until it is done — this is the first thing to check when a fresh install
      returns errors.

## 4. Ingress — external S3 endpoint

- [ ] 4.1 Add a `kubernetes_ingress_v1` for host `blob.${var.domain}` (`blob.freepod.eu`) routing
      `/` to the Service's S3 port 3900. No `router.entrypoints` annotation is needed:
      `websecure` is the only default entrypoint and :80 falls through to the cluster-wide
      HTTP→HTTPS redirect IngressRoute (design D7).
- [ ] 4.2 **Attach no `forward-auth` middleware, and no request-mutating middleware at all.**
      Write the in-line comment explaining why — S3 SigV4 and presigned-URL signatures are
      incompatible with oauth2-proxy, which both 401s the request and rewrites what was signed.
      Model the comment on the webhooks ingress in `tf/app/caelus/ingress.tf`. This comment is a
      deliverable, not a nicety: it is what stops the next reviewer from "fixing" the gap.
- [ ] 4.3 Add no cert-manager `Certificate` and no TLS secret — `blob.freepod.eu` is one label deep
      and is served by Traefik's default wildcard store (`wildcard-freepod-eu-tls`).
- [ ] 4.4 Confirm the admin port is **not** routed by this or any other Ingress/IngressRoute.
- [ ] 4.5 Re-verify no `buffering` middleware and no `maxRequestBodyBytes` exists on the router,
      the entrypoint, or in `tf/deps/system/helm/traefik/values.yaml.tftpl`
      (`grep -rn 'buffering\|maxRequestBodyBytes' tf/` currently returns nothing — keep it that
      way). Note that the HSTS default middleware is a *response*-header middleware and is fine.
- [ ] 4.6 Verify externally: `curl -sv https://blob.freepod.eu/` returns an S3-formatted error from
      Garage over a valid certificate — not an oauth2-proxy redirect, not a TLS error — and
      `curl -sI http://blob.freepod.eu/` returns a redirect to HTTPS.

## 5. Bucket, key and lifecycle provisioning (design D2)

- [ ] 5.1 Add a ServiceAccount, Role and RoleBinding in the `garage` namespace scoped to
      get/create/update on the single `garage-keys` Secret. No cross-namespace permissions.
- [ ] 5.2 Write the provisioning script into a ConfigMap. It MUST be idempotent — read before
      every write — so re-running never rotates an existing key: for each environment `<env>` in
      `dev` and `prod`, create the bucket named `<env>`, create the access key
      `caelus-api-<env>` if absent, and
      `garage bucket allow --read --write <env> --key caelus-api-<env>`. Grant **only** that
      environment's bucket; do not pass `--owner`.
- [ ] 5.3 Have the script write the generated access key IDs and secrets into the `garage-keys`
      Secret. Note that Terraform cannot pre-generate these: `garage key import` rejects keys
      Garage did not generate, so Garage must mint them and they are read back afterwards.
- [ ] 5.4 Add a second Job step, in an S3-client image, applying the lifecycle configuration to
      each bucket via `PutBucketLifecycleConfiguration`: an `Expiration` rule at
      `var.object_expiry_days` **and** an `AbortIncompleteMultipartUpload` rule. Both are
      required — abandoned multipart parts consume disk without appearing in a listing.
      Lifecycle is an S3-API operation, not a `garage` CLI one, hence the separate image.
- [ ] 5.5 Add the Kubernetes Job wiring both steps, triggered on install and re-run when the
      script ConfigMap changes.
- [ ] 5.6 Where the admin API is used instead of the CLI, create a **scoped, expirable** admin
      token (`garage admin-token create` with an operation scope) rather than using the master
      `admin_token`.
- [ ] 5.7 Run the Job twice and confirm the second run is a no-op: same access key IDs, no
      error, no rotation.
- [ ] 5.8 Verify the permission boundary: `caelus-api-dev` is denied read, write and list on the
      `prod` bucket, and `caelus-api-prod` likewise on `dev`.
- [ ] 5.9 Verify the lifecycle configuration is readable back from each bucket and contains both
      rules.

## 6. Credential handoff to the Caelus API

- [ ] 6.1 Add a `kubernetes_secret` **data source** for `garage-keys` and expose per-environment
      `sensitive` outputs from `tf/deps` (`garage_access_key_id_dev`,
      `garage_secret_access_key_dev`, and the `prod` pair), mirroring the existing
      `freepod_*_client_secret` outputs.
- [ ] 6.2 In `tf/app`, add **workspace-keyed map** variables for the S3 access key ID and secret
      and the bucket name — a scalar cannot express two per-environment values because
      `*.auto.tfvars` is auto-loaded in every workspace (`tf/README.md` documents this for
      `oauth2_proxy_client_ids`).
- [ ] 6.3 Add a `caelus-s3` Kubernetes Secret in `tf/app/caelus/secrets.tf` carrying the S3
      endpoint, region, bucket, access key ID and secret access key.
- [ ] 6.4 Add an `env_from` secret reference to `caelus-s3` on the API container in
      `tf/app/caelus/deployment-api.tf`, following the `caelus-db` pattern. Add it to
      `worker.tf` only if the worker will read objects.
- [ ] 6.5 Paste the `tf/deps` outputs into the gitignored `tf/app/secrets.auto.tfvars` and apply
      both workspaces. Confirm each environment's pod carries only its own bucket and key.

## 7. API configuration surface

- [ ] 7.1 Add settings to `api/app/config.py` under the existing `CAELUS_` prefix: S3 endpoint
      URL, region (`garage`), bucket, access key ID, secret access key, and presigned-URL expiry
      seconds. Credential settings default to empty — never a real value — so the test suite and
      local dev run with no object store configured.
- [ ] 7.2 Comment that the S3 client MUST use **path-style** addressing
      (`addressing_style: "path"`): `root_domain` is unset in `garage.toml`, and vhost-style
      would generate presigned URLs against `bucket.blob.freepod.eu`, which has neither a DNS
      record nor certificate coverage (design D3).
- [ ] 7.3 Run `uv run --no-sync pytest` and confirm settings load and no test regresses with the
      new variables unset. The API's *use* of these settings is out of scope for this change.

## 8. End-to-end verification (from outside the cluster)

> Run these from a laptop on an external network, not from an in-cluster pod: the path under
> test includes the homelab HAProxy edge, which is not managed by this repo.

- [ ] 8.1 Presigned PUT then presigned GET of a small object; bytes match.
- [ ] 8.2 Expired presigned URL is refused with an S3 authentication error, and writes nothing.
- [ ] 8.3 Upload an object of at least 100 MB; it completes and its checksum matches. This is
      the real test of "no buffering, no body cap, no edge timeout".
- [ ] 8.4 Multipart upload of a large object: initiate, parts, complete all succeed and the
      assembled object is byte-identical. Then initiate and abort one, and confirm no object
      appears at the key.
- [ ] 8.5 `PostObject` with a `content-length-range` policy: a compliant body is accepted, an
      oversized body is rejected by Garage and stores nothing.
- [ ] 8.6 An unsigned request to a private object returns an S3 access-denied error from Garage,
      not an oauth2-proxy login redirect.
- [ ] 8.7 Restart the pod (`kubectl delete pod -n garage garage-0`); confirm the layout survives
      and a previously written object is still readable.

## 9. Documentation

- [ ] 9.1 `tf/deps/README.md`: add Garage to § What It Creates; add a Garage section covering the
      `blob.freepod.eu` endpoint, the deliberate absence of forward-auth and why, the cluster-layout
      bootstrap, the bucket/key naming convention, lifecycle expiry, and reading the credential
      outputs for `tf/app`. Add the admin/RPC secrets to § Configuration. Note under § Notes that
      `terraform destroy` deletes the object data with the PVCs — there is no backup by design.
- [ ] 9.2 `tf/README.md`: add Garage to the `deps/` description and to the
      `tf/deps/secrets.auto.tfvars` secrets list; note the S3 credential outputs in the handoff
      section next to the Keycloak client secrets.
- [ ] 9.3 Record the known limits where an operator will find them: no object versioning, no IAM
      or bucket policies, single node / single replica. Anything durable needs a different
      answer.
- [ ] 9.4 Add a "Things that will bite you" entry in `tf/deps/README.md`: attaching forward-auth
      to the S3 ingress breaks every upload, and enabling `root_domain` breaks TLS.

## 10. Validation

- [ ] 10.1 `terraform validate` and `terraform plan` are clean in both `tf/deps` and `tf/app`
      (both workspaces), with no unexpected drift.
- [ ] 10.2 `openspec validate add-garage-object-store --strict` reports valid.
- [ ] 10.3 Archive the change and sync the delta specs into `openspec/specs/`.
