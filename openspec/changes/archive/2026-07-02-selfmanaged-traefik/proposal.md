## Why

On 2026-07-01 ~06:30 UTC, `https://freepod.eu` (and every `*.freepod.eu` app) began failing TLS
with `record overflow` / `packet length too long`. Root cause was a **silent configuration
reversion of freepod Traefik**, not a code or edge change:

- Freepod's only ingress controller is the **k3s-bundled Traefik**. Its config (from
  `app-tls-termination`) is applied by *amending* the bundled chart via a `HelmChartConfig`
  managed in `tf/deps/system/traefik.tf` (`kubernetes_manifest.traefik_config`).
- A **stale, hand-created host file** `/var/lib/rancher/k3s/server/manifests/traefik-config.yaml`
  (created 2026-03-07, `0644`, containing the *old* `forwardedheaders.insecure=true` config)
  defines the **same** `HelmChartConfig/traefik` object. Anything in
  `/var/lib/rancher/k3s/server/manifests/` is owned by k3s's `deploy` addon controller and
  **re-applied on every k3s (re)start**. So two sources of truth fight over one object: Terraform
  wins on `apply`; k3s wins on restart.
- That restart happened via **Ubuntu unattended-upgrades + needrestart**: a routine security
  upgrade of shared libraries (`curl`, `libcurl*`, `libnss3`, `libsqlite3`) caused needrestart to
  bounce `k3s.service` in the 06:30 apt window (no host reboot, no k3s upgrade — binary/version
  unchanged). On restart, the `deploy` controller replayed the stale file, reverting the live
  `HelmChartConfig` back to `forwardedheaders.insecure` and dropping `proxyProtocol.trustedIPs`,
  the wildcard `tlsStore`, `externalTrafficPolicy: Local`, and the pinned image.
- With `proxyProtocol.trustedIPs` gone, Traefik no longer strips the HAProxy edge's `send-proxy-v2`
  PROXY-protocol preamble; it feeds those bytes into the TLS parser and replies with a plaintext
  error, which the client sees as non-TLS garbage on `:443` (`record overflow`). Traefik also fell
  back to the self-signed `TRAEFIK DEFAULT CERT` instead of the `*.freepod.eu` wildcard.

An interim `terraform apply -target=module.system.kubernetes_manifest.traefik_config` restored
service, but it is **fragile by design**: the stale file remains, so the next k3s restart (next
library security upgrade, reboot, or `systemctl restart k3s`) will silently revert it again.

The durable fix is to remove the dual ownership. This mirrors the **homelab** cluster, which
disables the k3s-bundled Traefik (`--disable=traefik`) and manages Traefik as its own Helm release
— explicitly avoiding the "amend the bundled chart via HelmChartConfig" pattern freepod is on.

## What Changes

- **Add a self-managed Traefik Helm release** as a new `tf/deps/system/helm/traefik/` module
  (`helm_release` + `values.yaml`), mirroring homelab's `helm/traefik/` but with freepod-specific
  values (see below), pinned to a chart version providing **Traefik v3.6.x** (parity with the
  current `3.6.10`).
- **Port every freepod-specific setting** from the retired `HelmChartConfig` into the release's
  `values.yaml`, with **no behavioural change**:
  - `service.type: LoadBalancer` + `externalTrafficPolicy: Local` + host ports 80/443 (so klipper
    binds the node's `:80/:443` and the HAProxy edge IP survives to match `proxyProtocol.trustedIPs`).
    *(This is the key divergence from homelab, whose Traefik is `ClusterIP` behind an in-cluster HAProxy.)*
  - `ports.websecure.asDefault: true`, `ports.web.asDefault: false`.
  - `proxyProtocol.trustedIPs: [<haproxy_edge_ip>]` on `web` and `websecure`; **no**
    `forwardedheaders.insecure`.
  - `tlsStore.default.defaultCertificate.secretName: wildcard-freepod-eu-tls`.
  - `providers.kubernetesIngress.allowExternalNameServices: true` and
    `providers.kubernetesIngressNginx.enabled: true`.
  - **No** entrypoint-level HTTP→HTTPS redirect (it deadlocks the HTTP-01 solver); the existing
    low-priority web-only redirect IngressRoute (`redirect_https.tf`) is retained.
  - `ingressClass` name `traefik` kept as the default class so existing app Ingresses match.
  - `accesslog: true`.
- **Disable the k3s-bundled Traefik** (host change, outside the tf repo, like homelab): create
  `/etc/rancher/k3s/config.yaml` with `disable: [traefik]` and remove the stale
  `traefik-config.yaml`, then restart k3s so it uninstalls the bundled chart and frees `:80/:443`.
- **Retire** `tf/deps/system/traefik.tf` (the `HelmChartConfig` amend resource) — replaced by the
  Helm release module.

## Capabilities

### Modified Capabilities

- `freepod-tls-termination`: the same TLS-termination behaviour (wildcard default cert, PROXY-protocol
  client-IP preservation, ACME-safe redirect, websecure-default entrypoint) is now delivered by a
  **Terraform-managed Traefik Helm release** with the k3s-bundled Traefik **disabled**, rather than by
  amending the bundled chart via a `HelmChartConfig`. This makes Terraform the single source of truth
  and immune to the k3s `deploy` addon controller replaying a host manifest on restart.

## Impact

- **Terraform:** new `tf/deps/system/helm/traefik/` module (`helm_release` + `values.yaml`);
  `tf/deps/system/traefik.tf` removed; module wired into `tf/deps/system`. The `helm` provider must
  be configured for the freepod cluster. Dependent resources (`redirect_https.tf` redirect
  IngressRoute/Middleware, the HTTP-01 solver `ingressTemplate` pinning) are unchanged and continue
  to rely on the `traefik.io/v1alpha1` CRDs (which Helm does not delete on the bundled chart's
  uninstall, so they persist across the cutover).
- **k3s host (outside repo):** `/etc/rancher/k3s/config.yaml` gains `disable: [traefik]`; the stale
  `/var/lib/rancher/k3s/server/manifests/traefik-config.yaml` is removed; k3s writes a
  `traefik.yaml.skip` marker and stops managing the bundled Traefik.
- **Cutover:** a **brief ingress outage** while the bundled Traefik is torn down and the new
  `LoadBalancer` Traefik claims `:80/:443` (done in a maintenance window; no zero-downtime dance).
- **No app / API / chart change:** app Ingresses keep the same `traefik` IngressClass, `websecure`
  default, and per-app TLS contract; nothing in `api/` or `products/` changes.
- **Resilience:** after the migration, a k3s restart (unattended-upgrade, reboot, manual) no longer
  reverts Traefik config — closing the failure mode entirely.
