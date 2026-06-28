## ADDED Requirements

### Requirement: Websecure is the default entrypoint for unannotated routers
Freepod Traefik SHALL mark `websecure` as the default entrypoint and `web` as non-default
(`ports.websecure.asDefault: true`, `ports.web.asDefault: false`), so any Ingress or router without
an explicit `traefik.ingress.kubernetes.io/router.entrypoints` annotation binds `websecure` (`:443`)
only. Application Ingresses SHALL therefore be HTTPS-only without any per-app entrypoint annotation,
and their plain-HTTP `:80` traffic falls through to the cluster-wide redirect. Routers that must
serve `:80` (the catch-all redirect IngressRoute, the OAuth2 endpoints, the webhook receiver) SHALL
continue to declare their entrypoints explicitly and are unaffected by the default.

#### Scenario: An app Ingress without an entrypoint annotation is HTTPS-only
- **WHEN** an Ingress with no `router.entrypoints` annotation is reconciled on freepod Traefik
- **THEN** it binds the `websecure` entrypoint only
- **AND** its `:80` traffic is handled by the cluster-wide HTTP→HTTPS redirect

#### Scenario: Explicitly-annotated routers still bind web
- **WHEN** a router declares `web` explicitly (e.g. the redirect IngressRoute or the OAuth2 endpoints)
- **THEN** it continues to bind `:80` regardless of the `websecure` default

### Requirement: The HTTP-01 solver Ingress is pinned to the web entrypoint
The cert-manager HTTP-01 solver Ingress SHALL be pinned to the `web` entrypoint via the issuer
solver's `ingressTemplate` annotation `traefik.ingress.kubernetes.io/router.entrypoints: web`, on
both the production and staging HTTP-01 ClusterIssuers. This is required because `web` is no longer
a default entrypoint, and the solver Ingress otherwise carries no entrypoint annotation of its own.
Pinning it keeps the ACME challenge reachable as plain HTTP on `:80`, where its exact
`/.well-known/acme-challenge/<token>` rule out-ranks the low-priority catch-all redirect.

#### Scenario: Solver Ingress serves the challenge on :80 despite the websecure default
- **WHEN** cert-manager creates an HTTP-01 solver Ingress from a configured issuer
- **THEN** the solver Ingress carries `router.entrypoints: web` and binds `:80`
- **AND** `http://<custom-domain>/.well-known/acme-challenge/<token>` is served as plain HTTP and the
  certificate can be issued
