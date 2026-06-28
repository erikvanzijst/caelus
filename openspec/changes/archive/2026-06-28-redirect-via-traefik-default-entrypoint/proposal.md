## Why

The current TLS work makes every product chart's Ingress carry a
`traefik.ingress.kubernetes.io/router.entrypoints: websecure` annotation so its plain-HTTP `:80`
traffic falls through to the cluster-wide redirect. That annotation is purely a redirect-routing
concern, yet it taints every chart and commits us to wiring it into every future app (and into
each wrapper chart). The redirect can instead be a single cluster property: flip freepod Traefik's
default entrypoint to `websecure`, so any Ingress without an explicit entrypoint is HTTPS-only by
default and needs no per-app annotation at all.

## What Changes

- **Flip the freepod Traefik global entrypoint default** so routers without an explicit entrypoint
  bind `websecure` only (`ports.websecure.asDefault: true`, `ports.web.asDefault: false`). The
  existing web-only catch-all redirect IngressRoute keeps owning `:80` for every app host.
- **Keep ACME HTTP-01 reachable on `:80`** after the flip by stamping
  `traefik.ingress.kubernetes.io/router.entrypoints: web` onto the cert-manager solver Ingress via
  the HTTP-01 issuers' solver `ingressTemplate` (both `letsencrypt-http` and
  `letsencrypt-http-staging`). The solver's exact challenge-path rule still out-ranks the redirect.
- **Remove the `websecure` annotation from all seven product charts.** Five native/conditional
  charts (helloworld, matrix, mattermost, naas, immich) drop the annotation line; the two wrapper
  charts (vaultwarden, nextcloud) hardcode it under a bare `annotations:` key, so those are
  restructured to render the `annotations:` block only when a custom-domain cert annotation exists
  (avoiding an empty-map YAML error). Each chart's version is bumped and its `.tgz` repackaged.
- **Rename the system values namespace `caelus.tls` → `caelus.ingress`** to fix the misleading name:
  `enabled` is an *ingress* fact (the platform exposes this deployment), not a TLS one. The new shape
  is `caelus.ingress.{enabled, host, tls.{wildcard, issuer, secretName}}`. The reconciler emits the
  new structure (`_build_tls_overrides` → `_build_ingress_overrides`); all seven chart templates,
  six `values.schema.json`, and seven `values.yaml` defaults are repointed; the standalone default
  carries `caelus.ingress.tls: {}` so the `not .tls.wildcard` access stays nil-safe. Pure
  values-contract change, no behavior change.
- **Out of scope:** the `caelus-ingress` apex (it explicitly binds `web` and is intentionally not
  redirected); the wildcard-vs-custom cert split ("Ask 2", deferred pending a Public Suffix List
  decision).

## Capabilities

### New Capabilities
<!-- None: this change moves an existing redirect mechanism; it introduces no new capability. -->

### Modified Capabilities
- `freepod-tls-termination`: the "no entrypoint-level redirect" requirement gains the mechanism that
  realizes it — `websecure` as the default entrypoint (`asDefault`) so apps are HTTPS-only without
  per-app annotation, plus the HTTP-01 solver `ingressTemplate` carve-out that keeps the ACME
  challenge on `:80`.
- `app-tls-injection`: two changes. (1) The "Application Ingresses are websecure-only" requirement —
  charts SHALL NOT carry the `websecure` entrypoint annotation; HTTPS-only routing is now a cluster
  default, not a per-chart annotation. (2) The injected values namespace is renamed `caelus.tls` →
  `caelus.ingress` (with nested `tls`) across the reconciler-injection, custom-domain-cert, and
  chart-schema requirements. Chart `.tgz` packages are re-bumped.

## Impact

- **Terraform (deps):** `tf/deps/system/traefik.tf` (add `ports.web.asDefault=false` /
  `ports.websecure.asDefault=true`; update the entrypoint comment); `tf/deps/certmanager/issuers.tf`
  (solver `ingressTemplate` entrypoint annotation on both HTTP-01 issuers).
- **Charts:** `products/{helloworld,matrix,mattermost,naas,immich}/chart/templates/ingress.yaml`
  drop the annotation line; `products/{vaultwarden,nextcloud}/chart/templates/ingress.yaml` are
  restructured to omit the `annotations:` block when empty; every modified chart bumps `Chart.yaml`
  `version` and repackages its `.tgz`.
- **Backend:** `api/app/services/reconcile.py` renames `_build_tls_overrides` → `_build_ingress_overrides`
  and emits the `caelus.ingress` shape; `api/tests/test_reconcile_service.py` updated to assert the new
  structure (unit tests renamed accordingly).
- **Chart values contract:** all 7 `templates/ingress.yaml`, 6 `values.schema.json`, and 7 `values.yaml`
  repointed from `caelus.tls.*` to `caelus.ingress.*` (mattermost has no schema file).
- **Operator actions:** `terraform apply tf/deps/` (Traefik default + solver annotation), then bump
  the affected `ProductTemplateVersion` rows to the new chart versions. No forced app redeploy — the
  Traefik default flip applies to existing deployments immediately; chart edits are picked up lazily.
- **Behavioral note:** behavior-preserving for apps (they already fall through to the redirect via
  the annotation today). `keycloak` is the only resource relying on the implicit `web+websecure`
  default; it gains the HTTP→HTTPS redirect (benign — it is served HTTPS by the wildcard default
  store and has no `:80` dependency).
