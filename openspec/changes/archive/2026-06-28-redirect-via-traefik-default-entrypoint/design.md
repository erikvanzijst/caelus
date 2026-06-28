## Context

Freepod terminates its own TLS on the k3s-bundled Traefik (amended via the `HelmChartConfig` in
`tf/deps/system/traefik.tf`). The HTTP→HTTPS redirect is already a cluster-wide, web-only,
lowest-priority catch-all IngressRoute + `redirectScheme` Middleware (`tf/deps/system/redirect_https.tf`).
For an app's `:80` traffic to reach that redirect rather than the app, the app must not bind the
`web` entrypoint — today each product chart enforces this by injecting a
`traefik.ingress.kubernetes.io/router.entrypoints: websecure` annotation onto its Ingress (gated on
`caelus.tls.enabled`; the vaultwarden/nextcloud wrappers hardcode it). That makes a cluster-routing
concern a per-chart obligation and commits every future app to carry it.

A default k3s Traefik Ingress binds **both** `web` (`:80`) and `websecure` (`:443`). The app's `:80`
router is an exact `Host(...)` match that out-ranks the redirect's priority-1 `PathPrefix(/)` rule,
so without the annotation the app would serve plaintext on `:80`. Traefik v3 lets an entrypoint be
flagged `asDefault`: a router with no explicit entrypoints binds only the entrypoints flagged
default. Flipping the default to `websecure` reproduces the annotation's effect cluster-wide.

One coupling: cert-manager's HTTP-01 solver Ingress also carries no entrypoint annotation, so the
flip would pull it off `:80` and deadlock issuance. cert-manager supports stamping annotations onto
that auto-created Ingress via the issuer solver's `ingressTemplate`.

## Goals / Non-Goals

**Goals:**
- Remove the redirect-routing concern (`websecure` annotation) from every product chart.
- Make HTTPS-only the cluster default so new apps need no per-app redirect wiring.
- Preserve ACME HTTP-01 on `:80` after the default flip.
- Be behavior-preserving for already-deployed apps (no flag-day, no forced redeploy).

**Non-Goals:**
- The `caelus-ingress` apex redirect — it explicitly binds `web` and is intentionally left unredirected.
- The wildcard-vs-custom certificate split ("Ask 2") — deferred pending a Public Suffix List decision.
- Any change to the reconciler's `caelus.tls` injection or to hostname classification.

## Decisions

### D1: Flip the Traefik default entrypoint to `websecure` (chart `ports.*.asDefault`)
Set `ports.websecure.asDefault: true` and `ports.web.asDefault: false` in the Traefik
`HelmChartConfig` `valuesContent`. Unannotated Ingresses then bind `websecure` only — exactly what
the per-chart annotation does today, but as one cluster property.

- **Alternative — entrypoint-level redirect** (`entrypoints.web.http.redirections`): rejected and
  already documented in `freepod-tls-termination`; it is applied before router matching, shadows the
  HTTP-01 solver, and deadlocks custom-domain issuance (leaking `:8443`).
- **Alternative — `additionalArguments=["--entrypoints.websecure.asDefault=true"]`**: equivalent, but
  mixing manual entrypoint args with the chart-rendered `ports` entrypoints risks "entrypoint already
  defined" conflicts. The `ports.*.asDefault` value is the chart-native lever and is **confirmed
  supported** by the deployed chart (k3s `traefik-38.0.201+up38.0.2`, upstream Traefik Helm v38.0.2,
  image `traefik:3.6.10`) — its `values.yaml` documents `asDefault` per port ("When a service doesn't
  explicitly set an entrypoint it will only use this entrypoint") and even shows `websecure.asDefault:
  true` as the example. The `additionalArguments` form is unnecessary.

### D2: Pin the HTTP-01 solver Ingress to `web` via the issuer `ingressTemplate`
Add `solvers[].http01.ingress.ingressTemplate.metadata.annotations` with
`traefik.ingress.kubernetes.io/router.entrypoints: web` to both `letsencrypt-http` and
`letsencrypt-http-staging` in `tf/deps/certmanager/issuers.tf`. The solver Ingress then binds `:80`
despite the new default, and its exact challenge-path rule still out-ranks the catch-all redirect.

- **Alternative — keep `web` as a default just for the solver**: not possible; `asDefault` is
  per-entrypoint and global, not per-Ingress. `ingressTemplate` is cert-manager's supported
  mechanism for exactly this.

### D3: Remove the annotation from charts; keep `caelus.tls` cert wiring intact
Delete the `websecure` annotation line from the five native/conditional charts. For the two wrappers
(vaultwarden, nextcloud), the annotation sits under a bare `annotations:` key whose only other entry
is a conditional `cert-manager` annotation; restructure so the `annotations:` block renders **only**
when `$tlsCustom` is true, otherwise the wildcard case would emit an empty mapping (invalid YAML).
`caelus.tls.enabled` continues to gate the custom-domain `cert-manager.io/cluster-issuer` + `tls:`
block, so the reconciler (`_build_tls_overrides`) is unchanged. Each modified chart bumps its
`Chart.yaml` version and repackages its `.tgz`.

### D4: Rollout order decouples the live change from the chart churn
Apply the Traefik default (D1) + solver pin (D2) first. At that moment every app — including
already-deployed ones still carrying the annotation — is `websecure`-only, because the annotation and
the default produce identical routing. The chart edits (D3) are then pure cleanup picked up lazily on
each app's next upgrade; no forced redeploy.

## Risks / Trade-offs

- **The default flip affects every Ingress on the cluster** → Audited: `caelus-ingress`,
  `caelus-webhooks-ingress`, and the `oauth2-endpoints` IngressRoute all declare entrypoints
  explicitly (unaffected); the redirect IngressRoute explicitly binds `web` (unaffected). Only
  `keycloak` relies on the implicit default — it drops to `websecure`-only and gains the redirect,
  which is benign (served HTTPS by the wildcard default store, no `:80` dependency).
- **Bundled Traefik chart support for `ports.*.asDefault`** → Resolved: confirmed against the live
  cluster (k3s `traefik-38.0.201+up38.0.2` / upstream Helm v38.0.2), which supports the key natively.
  The `--entrypoints.websecure.asDefault=true` argument remains a defensive fallback only.
- **Solver pin typo silently re-deadlocks HTTP-01** → Validate by issuing a staging certificate for a
  custom domain and confirming the challenge is answered as plain HTTP on `:80` before trusting prod.
- **Empty `annotations:` map in the wrappers breaks `helm template`** → Covered by the D3
  restructure; verified by templating each wrapper in the wildcard (no-cert) case.

## Migration Plan

1. `terraform apply tf/deps/` — Traefik `ports.*.asDefault` (`module.system`) and the HTTP-01 solver
   `ingressTemplate` (`certmanager`).
2. Validate live: a wildcard app `:80`→`301`→`https` with no `:8443` leak; a staging custom-domain
   re-issue answered on `:80`; `keycloak.freepod.eu:80` now redirects and `:443` still serves.
3. Land the chart edits + version bumps, repackage and push the `.tgz`, and update the affected
   `ProductTemplateVersion` rows.
- **Rollback:** revert the Traefik `HelmChartConfig` change (restores `web` as a default); deployed
  apps still carrying the annotation remain correct, and reverted charts re-add it.

## Open Questions

- None. (Whether to also redirect the Caelus apex is deferred by explicit decision, not an open
  question for this change.)
