## 1. Capture current state (parity baseline)

- [x] 1.1 Record the live bundled-Traefik values to reproduce: image/app version (`3.6.10`), the
      full arg/value surface (`proxyProtocol.trustedIPs=<haproxy_edge_ip>` on web+websecure,
      `tlsStore.default` → `wildcard-freepod-eu-tls`, `ports.websecure.asDefault=true` /
      `ports.web.asDefault=false`, `providers.kubernetesIngress.allowExternalNameServices=true`,
      `providers.kubernetesIngressNginx.enabled=true`, `service externalTrafficPolicy=Local`,
      `accesslog=true`, ingressClass `traefik`), and the `svclb-traefik` host-port ownership.
- [x] 1.2 Confirm `wildcard-freepod-eu-tls` secret exists in `kube-system` and the
      `traefik.io/v1alpha1` CRDs are installed (they must survive the bundled-chart uninstall).
- [x] 1.3 Confirm the `helm` Terraform provider is (or can be) configured for the freepod cluster.
      (Already configured in `tf/deps/providers.tf`, `~> 2.13`.)

## 2. New Traefik Helm-release module (Terraform)

- [x] 2.1 Create `tf/deps/system/helm/traefik/main.tf` with a `helm_release "traefik"` (namespace
      `kube-system`, repo `https://traefik.github.io/charts`, chart `traefik`,
      `version = var.traefik_chart_version`, `values = [templatefile(".../values.yaml.tftpl", …)]`).
- [x] 2.2 Create `tf/deps/system/helm/traefik/variables.tf` with `traefik_chart_version` (default
      **`39.0.5`** = Traefik app **v3.6.10**, parity) and `haproxy_edge_ip`.
- [x] 2.3 Create `tf/deps/system/helm/traefik/values.yaml.tftpl` porting the full surface from D3:
      `service.type: LoadBalancer` + `service.spec.externalTrafficPolicy: Local`;
      `ports.web.asDefault: false` + `ports.websecure.asDefault: true`;
      `ports.{web,websecure}.proxyProtocol.trustedIPs: [<haproxy_edge_ip>]` (no
      `forwardedheaders.insecure`); `tlsStore.default.defaultCertificate.secretName:
      wildcard-freepod-eu-tls`; `providers.kubernetesIngress.allowExternalNameServices: true`;
      `providers.kubernetesIngressNginx.enabled: true`; `ingressClass` name `traefik` as default;
      `logs.access.enabled: true`; and **no** `ports.web.http.redirections`.
- [x] 2.4 Wire `module "traefik"` into `tf/deps/system` (passing `haproxy_edge_ip`) and remove the
      old `tf/deps/system/traefik.tf` `HelmChartConfig` (`kubernetes_manifest.traefik_config`);
      add `depends_on = [module.traefik]` to the `redirect_https.tf` CRs. `terraform validate` passes
      and a targeted module plan renders the chart + values correctly.
- [x] 2.5 At cutover, run the full `terraform plan` and confirm: the new `helm_release` is created,
      `kubernetes_manifest.traefik_config` is dropped from state (destroy), and no unexpected
      changes to `redirect_https.tf` / issuer / solver resources. (Pass-2 apply: `2 added, 1 destroyed`.)

## 3. Disable the k3s-bundled Traefik (host — outside the tf repo)

- [x] 3.1 Create `/etc/rancher/k3s/config.yaml` on `192.168.0.159` with `disable: [traefik]`.
- [x] 3.2 Remove the stale `/var/lib/rancher/k3s/server/manifests/traefik-config.yaml`.
- [x] 3.3 `sudo systemctl restart k3s`; k3s uninstalled the bundled Traefik `HelmChart` +
      `svclb-traefik` and freed host `:80/:443`. NOTE (corrects D4): the `--disable=traefik` addon
      removal **also removed the bundled `traefik-crd` addon**, so the `traefik.io` CRDs (and the
      `redirect_https.tf` CRs) were deleted — the Helm release reinstalls the CRDs, which is why the
      two-pass apply in §4 was **mandatory**, not optional. Also: no `traefik.yaml.skip` is written
      when disabling via the `config.yaml` list; k3s simply never renders the addon (verified: no
      traefik manifests in the dir after restart).

## 4. Cutover — bring up the self-managed Traefik

- [x] 4.1 `terraform apply` the new module, **two-pass** (required — see 3.3):
      `terraform apply -target=module.system.module.traefik` (release + CRDs), then
      `terraform apply` (recreates the `redirect_https.tf` CRs, drops the old `HelmChartConfig`).
- [x] 4.2 New Traefik `LoadBalancer` Service is `Local`, `svclb-traefik` owns host `:80/:443`,
      pod runs `traefik:3.6.10` with `proxyProtocol.trustedIPs=192.168.0.12/32` on both entrypoints,
      and serves the `*.freepod.eu` wildcard (not `TRAEFIK DEFAULT CERT`).
- [x] 4.3 **Cutover fallout — restore ALL Traefik CRs, not just `tf/deps`'s.** Dropping the CRDs in
      §3.3 deleted every `traefik.io` CR **cluster-wide**, including `tf/app`'s `login`/`login-dev`
      CRs (the `forward-auth` + `oauth-errors` Middlewares and the `oauth2-endpoints` IngressRoute).
      Symptom: Traefik logs `middleware "login[-dev]-forward-auth@kubernetescrd" does not exist` and
      auth/oauth2 routing breaks. Fix: re-apply `tf/app` for **both** workspaces —
      `terraform apply -target=module.oauth2-proxy` on `default` (→ `login-dev`) and on `prod`
      (→ `login`). Verified: 0 Traefik errors, prod+dev `/api/me` → clean 401, `/oauth2/start` → 302.

## 5. Verification

- [x] 5.1 External: `https://freepod.eu` and `https://dev.freepod.eu` → `200`, valid `*.freepod.eu`
      Let's Encrypt cert (through the homelab HAProxy edge).
- [x] 5.2 Client IP: verify an app behind Traefik logs the **real** client IP via `X-Forwarded-For`
      (from the edge's PROXY header). Strongly implied (TLS terminates correctly, which requires the
      PROXY header to be parsed/stripped) but not yet confirmed against an app's access log.
- [x] 5.3 ACME-safe `:80` handling verified (mechanism, not a live issuance): a `:80`
      `/.well-known/acme-challenge/<token>` request is served **plain** on the `web` entrypoint
      (access log: status 200 from the apex UI backend, **no** 301) — proving no entrypoint-level
      redirect deadlocks ACME. Plus: the `ClusterIssuer` solver `ingressTemplate` pins
      `router.entrypoints: web`, and Traefik args carry **no** `entrypoints.web.http.redirections`.
      A full end-to-end custom-domain cert *issuance* was not separately exercised, but every
      mechanism it relies on is confirmed intact (unchanged from the pre-migration, live-validated
      design). (Apex `*.freepod.eu` hosts bind `web,websecure` and serve `:80` directly; the
      HTTP→HTTPS redirect applies only to `websecure`-only routers.)
- [x] 5.4 **Resilience (the point of this change):** `sudo systemctl restart k3s`, then re-checked —
      config **persists**: Traefik unchanged (`3.6.10`, proxyProtocol), no bundled Traefik or
      `HelmChartConfig/traefik` recreated, no traefik manifest on disk, `https://freepod.eu` → 200.
- [x] 5.5 Reversibility: removing `disable: [traefik]` + restoring the module/HelmChartConfig (git
      history) returns to the bundled Traefik if ever needed.
