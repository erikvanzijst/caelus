## 1. Prerequisites & coordination

- [x] 1.1 Confirm the paired homelab change `haproxy-sni-edge` is planned/agreed; record the
      **HAProxy edge IP** (the source IP freepod will see for passthrough traffic) — needed for
      `proxyProtocol.trustedIPs`. It is the homelab node running HAProxy. — homelab change created,
      pushed, PR opened by user. Edge IP defaults to `192.168.0.12/32` (`var.haproxy_edge_ip`).
- [x] 1.2 Provision a Cloudflare API token scoped to **edit DNS for the `freepod.eu` zone**;
      decide where it is sourced (tfvars/secret), mirroring homelab `certs/variables.tf`. — user
      added `cloudflare_api_token` (+ `cloudflare_email`) to `tf/deps/secrets.auto.tfvars`.
- [x] 1.3 Confirm the ACME account email (`acme_email`) for the Let's Encrypt issuers. — user
      added `letsencrypt_email` to `tf/deps/secrets.auto.tfvars`.
- [x] 1.4 Deploy order: this change is applied & validated on freepod **before** the homelab
      removes its freepod TLS termination. — documented here and in both proposals/specs.

## 2. cert-manager + issuers (tf/deps/certmanager/ — new module)

- [x] 2.1 Add the `helm` provider to `tf/deps/providers.tf` (only `kubernetes` exists today).
- [x] 2.2 Create `tf/deps/certmanager/certmanager.tf`: `helm_release` for cert-manager (Jetstack
      `https://charts.jetstack.io`) into namespace `cert-manager`, CRDs enabled. Pin a version.
      — pinned **`v1.17.2`** via `var.chart_version` (matches homelab); `installCRDs=true`.
      **NOTE:** v1.16.2 was tried first and wedged on the Cloudflare DNS-01 cleanup DELETE
      (empty zone id → CF error 7003); v1.17.2 (homelab's proven version) issues cleanly.
- [x] 2.3 Create the Cloudflare API token `Secret` in the `cert-manager` namespace (mirror
      homelab `certs/issuer.tf`). — in `tf/deps/certmanager/issuers.tf`.
- [x] 2.4 Create `tf/deps/certmanager/issuers.tf`:
      - `ClusterIssuer` `letsencrypt-dns` (ACME prod, **DNS-01** Cloudflare solver, selector
        `dnsZones: [freepod.eu]`);
      - `ClusterIssuer` `letsencrypt-http` (ACME prod, **HTTP-01** solver via ingress class
        `traefik`);
      - staging variants (`letsencrypt-dns-staging`, `letsencrypt-http-staging`) for rollout.
- [x] 2.5 Create `tf/deps/certmanager/wildcard.tf`: a `Certificate` for `*.freepod.eu` +
      `*.dev.freepod.eu` (+ apex `freepod.eu`) issued by `letsencrypt-dns`, secret stored where
      Traefik reads its default cert (Traefik's namespace, e.g. `kube-system`). — secret
      `wildcard-freepod-eu-tls` in `var.traefik_namespace` (default `kube-system`).
- [x] 2.6 Wire `module "certmanager"` into `tf/deps/main.tf`; ensure it applies before apps need
      certs. — added; `module.system` now `depends_on = [module.certmanager]`.
- [x] 2.7 `terraform apply` (deps) — **APPLIED to dev** (two-pass: helm_release first for CRDs,
      then issuers/secret/wildcard). All 4 ClusterIssuers Ready; `wildcard-freepod-eu` Certificate
      **Ready** (prod DNS-01); secret `kube-system/wildcard-freepod-eu-tls` present. Used the prod
      DNS issuer directly (one wildcard cert, low rate-limit risk).

## 3. freepod Traefik termination (tf/deps/system/traefik.tf)

- [x] 3.1 Set `tlsStore.default.defaultCertificate.secretName` to the `*.freepod.eu` wildcard
      secret from 2.5. — `wildcard-freepod-eu-tls`.
- [x] 3.2 Replace `--entrypoints.websecure.forwardedheaders.insecure=true` with PROXY-protocol
      trust: `--entrypoints.websecure.proxyProtocol.trustedIPs=<HAProxy edge IP>` (and the same
      on `web`); remove/disable the blanket forwarded-headers trust. — uses
      `var.haproxy_edge_ip`; both `forwardedheaders.insecure` args removed.
- [x] 3.3 **Decision C was WRONG and is reverted.** A global `entrypoints.web.http.redirections`
      redirect is applied *before* router matching, so it shadows cert-manager's HTTP-01 solver
      Ingress and deadlocks custom-domain issuance (verified live: the exact ACME token path
      returned `301 → https://…:8443`). Removed it from `traefik.tf`; the freepod solver then
      served the ACME path (`200` + key auth) and the cert issued. **Follow-up (5.8 below):**
      re-add HTTP→HTTPS redirect as a low-priority web-only IngressRoute + `redirectScheme`
      Middleware that the solver out-ranks. Until then apps are reachable on plain HTTP too.
- [x] 3.4 `terraform apply` (`module.system`) — **APPLIED to dev**. Traefik rolled out with the
      new args (`proxyProtocol.trustedIPs` on web+websecure, global redirect; `forwardedheaders`
      gone). **Verified in-cluster**: `openssl s_client` to the Traefik ClusterIP with SNI
      `app.dev.freepod.eu` returns the Let's Encrypt `CN=*.freepod.eu` default-store cert →
      freepod terminates its own TLS. (External path awaits the homelab HAProxy edge.)
- [x] 3.5 **Set `service.spec.externalTrafficPolicy: Local` on freepod Traefik** (found during
      §6 client-IP verification). With the default `Cluster`, klipper/kube-proxy SNATs the source
      to the node CNI gateway (`10.42.0.1`) before Traefik sees it, so `proxyProtocol.trustedIPs`
      never matched and the PROXY header was ignored — apps saw `10.42.0.1`, not the real client.
      `Local` preserves the edge IP as the TCP source → PROXY header trusted/parsed. **Verified
      live:** freepod Traefik access log now logs the real external client IP.

## 4. Reconciler `caelus.tls` injection (api/)

- [x] 4.1 `api/app/config.py`: add settings `tls_cluster_issuer` (default the HTTP-01 issuer
      name), `acme_email`, `wildcard_tls_secret`. — **DEVIATION:** only `tls_cluster_issuer` is an
      API concern (used by the reconciler). `acme_email` and the wildcard secret name are
      Terraform-side (`var.letsencrypt_email`, the Traefik `tlsStore` secret) and would be dead
      config in the API, so they were intentionally NOT added to `config.py`.
- [x] 4.2 `api/app/services/reconcile.py`: add `_build_tls_overrides(deployment)` returning
      `{"caelus": {"tls": {...}}}` with `enabled/host/wildcard/issuer/secretName`; classify
      `wildcard` by `settings.wildcard_domains` (reuse the logic shape from
      `hostnames.py::_check_cname`). Merge it into `_build_merged_values` alongside
      `_build_plan_overrides` (highest precedence via `merge_values_scoped`). — added
      `_build_tls_overrides` + `_build_system_overrides` (deep-merges plan + tls under `caelus`).
- [x] 4.3 Unit tests: wildcard host → `wildcard:true`, no issuer/secret usage; custom host →
      `wildcard:false` with issuer + `<release>-tls` secret; both → `enabled:true`. — added 4 unit
      tests for `_build_tls_overrides` + updated 3 existing integration tests; all pass.

## 5. Product chart TLS wiring (products/*/chart/)

> **Decision C (chosen):** the HTTP→HTTPS redirect is a single global entrypoint redirect on
> freepod Traefik (§3.3). Charts therefore carry **no** redirect logic — only custom-domain
> Ingresses add a cert-manager annotation + `tls:` secret. Wildcard apps need no TLS chart change
> (Traefik's default cert store serves them).

- [x] 5.1 Redirect mechanism decided (Decision C): global entrypoint redirect on freepod Traefik
      (implemented in §3.3). No per-app `redirectScheme` middleware in any chart.
- [x] 5.2 Native charts — edited `templates/ingress.yaml` for `helloworld`, `matrix`,
      `mattermost`, `naas`: when `caelus.tls.enabled && not caelus.tls.wildcard`, add
      `cert-manager.io/cluster-issuer` annotation (merged into a fresh annotations map so empty
      `{}` stays valid) + a `tls:` block (`hosts: [caelus.tls.host]`, `secretName:
      caelus.tls.secretName`). No redirect logic. **Verified** with `helm template` for custom
      (cert + tls), wildcard (neither), and standalone-default (neither) cases.
- [x] 5.3 `immich` wrapper — same custom-domain cert block applied in
      `products/immich/chart/templates/ingress.yaml`; verified with `helm template`.
- [x] 5.4 `nextcloud` (no wrapper ingress) — wire `caelus.tls` into the upstream
      `nextcloud.ingress.tls` / `nextcloud.ingress.annotations` values in
      `products/nextcloud/chart/values.yaml`. **Confirmed supported:** the vendored upstream
      chart `nextcloud-8.9.1` renders both (`{{- with .Values.ingress.annotations }}` and
      `{{- with .Values.ingress.tls }}` in its `templates/ingress.yaml`), and its `values.yaml`
      documents the exact `cert-manager.io/cluster-issuer` annotation + `tls: [{secretName,
      hosts}]` shape. For custom domains inject the cluster-issuer annotation via
      `nextcloud.ingress.annotations` and the `tls:` list via `nextcloud.ingress.tls`. No redirect.
      **DONE (immich pattern, not upstream-values).** Static `nextcloud.ingress.*` can't carry the
      per-deployment issuer/secret/host, so instead: (1) disabled the upstream ingress
      (`nextcloud.ingress.enabled: false`); (2) added a wrapper `templates/ingress.yaml` reading
      `caelus.tls` (websecure-only + cert-manager annotation/`tls:` for custom, host from
      `caelus.tls.host`) routing to the upstream Service (`nextcloud.fullname` = `.Release.Name` in
      the Caelus case, port 8080); (3) completed nextcloud's hostname wiring — added a
      `title: hostname` field at `nextcloud.nextcloud.host` in the schema so the reconciler derives
      `deployment.hostname` (verified: `normalize_and_return_hostname` returns it lowercased).
      Render-verified custom + wildcard; exactly one Ingress (upstream gone). Pushed
      `oci://registry.home/helm/nextcloud-wrapper:1.0.1`
      (`sha256:79366a61eba06108c11e623d68406addc705a2abf7f54a118d093aca3b394578`). Live deploy
      (heavy: postgres+app) left to the operator; the TLS mechanism is identical to the
      live-validated immich/helloworld pattern. NOTE: nextcloud `.well-known` (caldav/carddav)
      discovery rewrites the old nginx ingress did are not reproduced — separate enhancement.
- [x] 5.5 Added a `caelus.tls` object (`enabled`,`host`,`wildcard`,`issuer`,`secretName`) to
      `helloworld`, `matrix`, `naas`, `immich`, `nextcloud` `values.schema.json` (JSON validated).
      `mattermost`/`vaultwarden` have no Helm `values.schema.json` (only `user.schema.json`), so
      Helm does not validate them and no change is needed there.
- [x] 5.6 Added `caelus:\n  tls:\n    enabled: false` defaults to `helloworld`, `matrix`,
      `mattermost`, `naas`, `immich` `values.yaml` (standalone renders verified).
- [x] 5.7 Bumped chart versions, packaged, and **pushed to `oci://registry.home/helm`** (no auth):
      helloworld `0.1.5`, matrix `0.1.1`, mattermost `1.0.8`, naas `0.1.2`, immich `2.5.6`
      (pull round-trip verified). nextcloud intentionally not bumped/pushed (5.4 deferred).
      Operator updates the ProductTemplateVersions to the new versions/digests via the admin UI.
      NOTE: `registry.home` SNI initially mis-routed to the freepod default backend (`.home` not in
      the HAProxy homelab-apex list) — fixed on the homelab edge before the push succeeded.
- [x] 5.8 **HTTP→HTTPS redirect — DONE & validated live.** Added `tf/deps/system/redirect_https.tf`:
      a `redirect-https` `redirectScheme` Middleware + a web-only, `priority: 1` catch-all
      IngressRoute (`PathPrefix(/)`) in `kube-system` (applied). Charts now annotate app Ingresses
      `traefik.ingress.kubernetes.io/router.entrypoints: websecure` when `caelus.tls.enabled` (both
      classes), so their `:80` falls through to the catch-all. Re-bumped + pushed: helloworld
      `0.1.6`, matrix `0.1.2`, mattermost `1.0.9`, naas `0.1.3`, immich `2.5.7`.
      **Validated** (test install of helloworld 0.1.6 on a wildcard host): `:80`→`301
      https://host` (no `:8443` leak), `:443`→`200` (no loop), and a solver-style exact ACME path
      on `:80` is NOT redirected (out-ranks the catch-all) — no ACME regression. Existing
      deployments pick this up when redeployed on the new chart versions.
- [x] 5.9 **vaultwarden wrapper — DONE.** vaultwarden was deployed wrapper-less (gissilabs chart
      direct), so it had the same gap as nextcloud: static subchart values can't carry per-app TLS.
      Built a `vaultwarden-wrapper` chart (depends on gissilabs `vaultwarden` **1.4.0**, upgraded
      from 1.3.0): disabled the upstream ingress, added a wrapper `templates/ingress.yaml` reading
      `caelus.tls` (websecure-only + cert-manager/`tls:` for custom) routing to the upstream
      Service (`<release>` : `httpPort` 80); added a `host` `title: hostname` field to the user
      schema (reconciler derives `deployment.hostname` — verified) and a Helm `values.schema.json`
      with the `caelus` block. Render-verified custom + wildcard; full render = exactly one
      Ingress. Pushed `oci://registry.home/helm/vaultwarden-wrapper:1.0.0`
      (`sha256:501136523d61f1520b0608e041348e2d9cd7680097610e03422511b08cdbcabb`). Live deploy left
      to the operator. **KNOWN LIMITATION:** vaultwarden `DOMAIN` (full https URL) is not set —
      per-deployment, can't be static — matching prior behaviour; admin/email/WebAuthn want it
      (follow-up). `default_values.json` is now `{}` (chart `values.yaml` holds the defaults).

## 6. End-to-end verification (staging issuers first)

- [x] 6.1 Edge passthrough + freepod termination — **VERIFIED LIVE**. The homelab `haproxy-sni-edge`
      change is deployed (no longer terminates freepod). External `openssl s_client` to
      `no.erikvanzijst.com:443` presents freepod's per-app cert; an arbitrary `*.dev.freepod.eu`
      SNI presents freepod's default-store wildcard (`CN=*.freepod.eu`) — both terminated on freepod,
      confirming SNI passthrough.
- [x] 6.2 `*.freepod.eu`-class app — **VERIFIED LIVE** via a wildcard-host test install
      (`redirtest.dev.freepod.eu`, helloworld 0.1.6): `https` → `200` served by the wildcard
      default-store cert; `http` → `301`→https; and the **real client IP is preserved**
      (freepod Traefik logs `45.86.93.16`, the external client, after the 3.5 `etp: Local` fix —
      not the edge or CNI IP). (Used the dev wildcard rather than a literal `hw.freepod.eu` apex app.)
- [x] 6.3 Custom domain — **VERIFIED LIVE** on prod with `no.erikvanzijst.com` (CNAME→`freepod.eu`,
      helloworld 0.1.5). App Ingress rendered the `letsencrypt-http` annotation + `tls:` secret;
      cert-manager issued `hello-world-l6ju3p-tls` via HTTP-01 (after the 3.3 redirect fix);
      `openssl`/`curl https://no.erikvanzijst.com` → `subject=CN=no.erikvanzijst.com` LE cert + app
      `200`. NOTE: required removing `erikvanzijst.com` from the homelab HAProxy apex list (it's a
      homelab-owned apex) — see the custom-domain-vs-homelab-apex caveat below.
- [x] 6.4 ACME solver path on `:80` vs redirect — **VERIFIED LIVE**. With the §5.8 catch-all redirect
      in place: a solver-style exact `/.well-known/acme-challenge/...` path on `:80` is **not**
      redirected (its rule out-ranks the priority-1 catch-all), while a normal `:80` path returns
      `301`→`https://host`. Also confirmed during 6.3 — the real HTTP-01 challenge for
      `no.erikvanzijst.com` completed and the cert issued.
- [x] 6.5 Trusted prod certs both classes — **ACHIEVED**. Issuers were pointed at Let's Encrypt
      **prod** directly (staging step skipped); both the `*.freepod.eu` default-store wildcard and
      the per-app custom-domain cert (`no.erikvanzijst.com`) are browser-trusted LE certs (user
      confirmed apps working in the browser). NOTE: the staging→prod dry-run was not exercised.

## 7. Cutover coordination

- [x] 7.1 Signal the homelab `haproxy-sni-edge` change that freepod termination is live and
      validated, so it can remove the homelab freepod TLS termination (`apps/freepod/`).
- [x] 7.2 Post-cutover re-verification through the live HAProxy edge — **DONE**: 6.1/6.2/6.3/6.4
      were all verified against the deployed edge (custom-domain cert issued + served, wildcard
      default-store served, redirect + ACME path, real client IP preserved).
