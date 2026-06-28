## Why

Freepod deploys user apps as Helm charts and assigns each a hostname — either a free
`*.freepod.eu` subdomain or a user-supplied **custom domain** CNAMEd to `freepod.eu`
(validated in `api/app/services/hostnames.py`). Today **all** TLS is terminated upstream at the
homelab cluster's Traefik using a `*.freepod.eu` wildcard cert, which then forwards plaintext
HTTP to the freepod node. That works for `*.freepod.eu` but is impossible for custom domains:
the homelab holds no certificate for an arbitrary user domain, so those apps can never serve
HTTPS.

The fix is to stop terminating freepod traffic upstream and have **freepod terminate its own
TLS per app**. The paired homelab change (`haproxy-sni-edge` in the `erikvanzijst/homelab`
repo) puts an HAProxy SNI router at the edge that TLS-**passes-through** any hostname it doesn't
recognize as a homelab service to the freepod node (the SNI travels in the cleartext
`ClientHello`, so HAProxy can route the still-encrypted stream by hostname). This change is the
freepod half: cert-manager, issuers, Traefik termination config, and per-app TLS wiring so that
both `*.freepod.eu` and custom-domain apps obtain and serve valid certificates.

> **Paired change:** `erikvanzijst/homelab` → `openspec/changes/haproxy-sni-edge`. That change
> delivers the HAProxy edge (SNI passthrough + PROXY protocol) and removes the homelab's freepod
> TLS termination. **This change must be deployed and validated on freepod _before_ the homelab
> removes its freepod termination** (passthrough target must exist before the old path is torn
> down).

## What Changes

- **Add cert-manager to freepod** (`tf/deps/`), with two Let's Encrypt ClusterIssuers:
  - a **DNS-01** issuer (Cloudflare) that issues the `*.freepod.eu` + `*.dev.freepod.eu`
    wildcard — mirroring the homelab's existing `letsencrypt-wildcard` pattern; and
  - an **HTTP-01** issuer used per-app for **custom domains** (the user owns their domain's
    DNS, so DNS-01 is not possible per-domain).
- **Configure freepod Traefik** (`tf/deps/system/traefik.tf`) to terminate TLS itself:
  - set the `*.freepod.eu` wildcard as Traefik's **default certificate store**, so every
    `*.freepod.eu` app is served the wildcard with no per-app cert;
  - replace the blanket `forwardedheaders.insecure=true` trust with **PROXY protocol** trust of
    the HAProxy edge IP, and set `externalTrafficPolicy: Local` so klipper preserves the edge
    source IP (else the PROXY header isn't trusted) — apps still see the real client IP;
  - use **no entrypoint-level HTTP→HTTPS redirect** (it shadows the ACME solver); a low-priority
    web-only catch-all `IngressRoute` + `redirectScheme` Middleware does the redirect instead.
- **Inject per-app TLS centrally in the reconciler** (`api/app/services/reconcile.py`),
  mirroring the existing `_build_plan_overrides`/`merge_values_scoped` pattern: a `caelus.tls`
  values block is computed from the deployment hostname (classified wildcard vs custom) so charts
  never hardcode issuer names. Custom-domain apps get a `cert-manager.io/cluster-issuer`
  annotation + a per-app `tls:` secret (HTTP-01); `*.freepod.eu` apps are served the default
  wildcard cert store (no per-app cert).
- **Wire TLS into the product charts** (`products/*/chart/`): app Ingresses are marked
  `websecure`-only (so their `:80` falls through to the cluster-wide redirect) and, for custom
  hosts, gain the cert-manager annotation + `tls:` block. `caelus.tls` is added to every
  `values.schema.json` (`additionalProperties:false` requires it); chart versions bumped and
  `.tgz` repackaged. Wrapper charts (immich, nextcloud, vaultwarden) carry their own Ingress.
- **ACME HTTP-01 + redirect coexistence:** the redirect is a low-priority web-only catch-all
  router, so cert-manager's exact `/.well-known/acme-challenge/...` solver rule out-ranks it and
  the challenge is served as plain HTTP on `:80` (otherwise issuance deadlocks).

## Capabilities

### New Capabilities

- `freepod-cert-manager`: cert-manager on the freepod cluster — Helm install, Cloudflare DNS-01
  ClusterIssuer + `*.freepod.eu` wildcard Certificate, and an HTTP-01 ClusterIssuer for custom
  domains. Staging issuers for verification.
- `freepod-tls-termination`: freepod Traefik terminates TLS — default cert store (wildcard),
  PROXY-protocol trust of the HAProxy edge (client-IP preservation), no global redirect, and the
  HTTP-01 ACME solver served on `:80`.
- `app-tls-injection`: the reconciler injects a system-controlled `caelus.tls` values block per
  deployment (wildcard vs custom classification); product charts mark Ingresses `websecure`-only
  and, for custom domains, add the cert-manager annotation + `tls:` block (no per-chart redirect).

### Modified Capabilities

<!-- None: this change adds TLS termination on freepod; it does not alter existing capability specs. -->

## Impact

- **Terraform (deps):** new `tf/deps/certmanager/` module; `tf/deps/main.tf` wiring; `helm`
  provider added to `tf/deps/providers.tf`; `tf/deps/system/traefik.tf` (default cert store,
  PROXY-protocol trust, drop blanket forwarded-headers trust, `externalTrafficPolicy: Local`);
  new `tf/deps/system/redirect_https.tf` (web-only catch-all redirect IngressRoute + Middleware).
- **Backend:** `api/app/services/reconcile.py` (`_build_tls_overrides` + `_build_system_overrides`),
  `api/app/config.py` (`tls_cluster_issuer` only).
- **Charts:** native charts (helloworld, matrix, mattermost, naas) edit
  `templates/ingress.yaml`; the wrapper charts (immich, nextcloud, and a **new
  `vaultwarden-wrapper`**) provide their own Ingress (upstream ingress disabled), since static
  subchart values can't carry per-deployment TLS; every chart's `values.schema.json`/`values.yaml`
  gains the `caelus.tls` block; chart versions bumped and repackaged. nextcloud + vaultwarden also
  gain a `title: hostname` field so the reconciler derives their hostname.
- **Secrets/config:** a Cloudflare API token (scoped to the `freepod.eu` zone) must exist in the
  freepod cluster for DNS-01; ACME account email.
- **External:** Let's Encrypt account + rate limits (use staging first). DNS for `freepod.eu` is
  on Cloudflare (existing).
- **Cross-repo:** paired with `erikvanzijst/homelab` `haproxy-sni-edge`; deploy ordering matters
  (this change first).
- **No application/runtime behavior change for users** beyond apps now serving valid HTTPS on
  custom domains; `*.freepod.eu` apps are unaffected functionally.
