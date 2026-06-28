# freepod-tls-termination Specification

## Purpose
Terminate TLS on freepod Traefik itself — default wildcard cert store, PROXY-protocol client-IP preservation, and an ACME-safe HTTP→HTTPS redirect.

## Requirements
### Requirement: Freepod Traefik terminates TLS using the wildcard as the default certificate
Freepod Traefik SHALL terminate TLS itself (rather than receiving plaintext HTTP from upstream),
and SHALL serve the `*.freepod.eu` wildcard secret as its **default certificate store**
(`tlsStore.default.defaultCertificate`). `*.freepod.eu` application Ingresses SHALL therefore
require no per-app TLS secret.

#### Scenario: Wildcard app served by the default certificate
- **WHEN** a TLS connection arrives at freepod Traefik with SNI `<app>.freepod.eu` and the app's
  Ingress has no explicit `tls:` secret
- **THEN** Traefik serves the default-store wildcard certificate and routes to the app
- **AND** no per-namespace certificate or secret reflection is needed for `*.freepod.eu` apps

#### Scenario: Custom-domain app served by its own certificate
- **WHEN** a TLS connection arrives with SNI for a custom domain whose Ingress references a
  per-app `tls:` secret
- **THEN** Traefik serves that per-app certificate (issued by the HTTP-01 issuer) for the
  custom domain

### Requirement: Client IP is preserved via PROXY protocol from the HAProxy edge
Freepod Traefik's `web` and `websecure` entrypoints SHALL trust **PROXY protocol** only from the
HAProxy edge IP (`proxyProtocol.trustedIPs`), and the blanket
`forwardedheaders.insecure=true` trust SHALL be removed. The Traefik Service SHALL set
`externalTrafficPolicy: Local` so klipper/kube-proxy does not SNAT the source to the node CNI
gateway before Traefik sees it (otherwise the source is not the trusted edge IP and the PROXY
header is ignored). The real client IP carried by the edge's `send-proxy-v2` SHALL be surfaced to
applications via `X-Forwarded-For`.

#### Scenario: App sees the real client IP
- **WHEN** an external client connects through the HAProxy edge and Traefik terminates TLS
- **THEN** Traefik reads the client IP from the PROXY-protocol header sent by the edge
- **AND** the application receives that client IP in `X-Forwarded-For`, not the edge or CNI-gateway IP

#### Scenario: Forwarded headers are not blanket-trusted
- **WHEN** freepod Traefik configuration is inspected
- **THEN** `--entrypoints.websecure.forwardedheaders.insecure=true` is not present
- **AND** PROXY-protocol trust is scoped to the HAProxy edge IP

### Requirement: No entrypoint-level redirect (it deadlocks HTTP-01)
Freepod Traefik SHALL NOT use an entrypoint-level HTTP→HTTPS redirect
(`entrypoints.web.http.redirections`). That redirect is applied *before* router matching, so it
shadows cert-manager's HTTP-01 solver Ingress and deadlocks custom-domain issuance (and leaks the
internal `:8443` port). The HTTP-01 solver SHALL therefore be reachable as plain HTTP on `:80`.
Any HTTP→HTTPS redirect SHALL instead be a router-level redirect (a low-priority web-only
IngressRoute + `redirectScheme` Middleware) that cert-manager's longer solver rule out-ranks.

#### Scenario: ACME challenge is served on plain :80
- **WHEN** a request for `http://<custom-domain>/.well-known/acme-challenge/<token>` arrives on :80
- **THEN** the cert-manager solver serves it as plain HTTP (no redirect to HTTPS)
- **AND** the certificate can be issued even though no HTTPS certificate yet exists

#### Scenario: A router-level redirect does not shadow the solver
- **WHEN** an HTTP→HTTPS redirect is configured as a low-priority web-only IngressRoute
- **THEN** non-ACME `:80` traffic is redirected to HTTPS (to `https://host`, no internal port)
- **AND** the exact ACME challenge path still reaches the solver (its rule out-ranks the redirect)

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

