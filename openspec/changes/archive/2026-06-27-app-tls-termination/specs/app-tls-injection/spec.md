## ADDED Requirements

### Requirement: The reconciler injects a system-controlled caelus.tls values block
The deployment reconciler (`api/app/services/reconcile.py`) SHALL compute a `caelus.tls` Helm
values block per deployment and merge it as a system override (highest precedence, via
`merge_values_scoped`), mirroring the existing `_build_plan_overrides` pattern. The block SHALL
classify the deployment hostname as **wildcard** (ends with a configured
`settings.wildcard_domains` entry) or **custom**, reusing the classification logic shape from
`hostnames.py`. Issuer and secret names SHALL come from settings
(`api/app/config.py`: `tls_cluster_issuer`, `acme_email`, `wildcard_tls_secret`), never hardcoded
in chart sources.

#### Scenario: Wildcard host injection
- **WHEN** a deployment hostname ends with a configured wildcard domain (e.g. `hw.freepod.eu`)
- **THEN** `caelus.tls` has `enabled: true`, `wildcard: true`, and `host` set
- **AND** no per-app issuer or TLS secret is required (the host is served by Traefik's default
  cert store)

#### Scenario: Custom-domain host injection
- **WHEN** a deployment hostname is a custom domain (e.g. `app.example.com`)
- **THEN** `caelus.tls` has `enabled: true`, `wildcard: false`, `host` set, `issuer` set to the
  HTTP-01 ClusterIssuer name, and `secretName` set to `<release-name>-tls`

### Requirement: Application Ingresses are websecure-only; redirect is cluster-wide
When `caelus.tls.enabled` is true, product chart Ingresses SHALL be annotated
`traefik.ingress.kubernetes.io/router.entrypoints: websecure` (HTTPS-only at Traefik), so their
plain-HTTP `:80` traffic falls through to a single cluster-wide redirect. Charts SHALL NOT render
any per-app redirect (no `redirectScheme` middleware, no redirect-only Ingress). The HTTP→HTTPS
redirect is a low-priority web-only catch-all IngressRoute + `redirectScheme` Middleware on freepod
Traefik (see `freepod-tls-termination`), which cert-manager's longer solver rule out-ranks.

#### Scenario: TLS-enabled app Ingress is websecure-only
- **WHEN** a chart is rendered with `caelus.tls.enabled: true` (wildcard or custom host)
- **THEN** the Ingress carries `traefik.ingress.kubernetes.io/router.entrypoints: websecure`
- **AND** it contains no `redirectScheme` middleware or redirect-only Ingress

#### Scenario: Plain-HTTP app traffic is redirected by the cluster-wide route
- **WHEN** a request hits an app host on `:80`
- **THEN** the web-only catch-all IngressRoute redirects it to `https://host` (no internal port)
- **AND** an exact ACME challenge path on `:80` is still served (its rule out-ranks the catch-all)

### Requirement: Custom-domain Ingresses request and serve a per-app certificate
The system SHALL render, for custom-domain deployments (where `caelus.tls.enabled` is true and
`caelus.tls.wildcard` is false), a chart Ingress carrying the `cert-manager.io/cluster-issuer`
annotation (issuer from `caelus.tls.issuer`) and a `tls:` block referencing
`caelus.tls.secretName` for the host, so cert-manager (ingress-shim) provisions an HTTP-01
certificate. Wildcard-host Ingresses SHALL NOT carry the issuer annotation or a per-app `tls:`
secret, because the default cert store serves them.

#### Scenario: Custom-domain chart renders cert-manager wiring
- **WHEN** a chart is rendered with `caelus.tls.wildcard: false`
- **THEN** the Ingress has `cert-manager.io/cluster-issuer: <issuer>` and a `tls:` entry with
  the host and `secretName`
- **AND** cert-manager issues and stores the certificate in the deployment namespace

#### Scenario: Wildcard-host chart omits per-app cert wiring
- **WHEN** a chart is rendered with `caelus.tls.wildcard: true`
- **THEN** the Ingress has no cert-manager issuer annotation and no per-app `tls:` secret

### Requirement: Chart schemas and packages accept the caelus.tls block
Every product chart's `values.schema.json` SHALL declare the `caelus.tls` object (so the
`additionalProperties: false` schemas accept it and `validate_user_values` passes), each
`values.yaml` SHALL provide a safe default (`caelus.tls.enabled: false`) so charts render
standalone, and each chart version SHALL be bumped and its `.tgz` repackaged for the reconciler
to install.

#### Scenario: Standalone render without the reconciler
- **WHEN** `helm template` is run on a chart without reconciler-injected values
- **THEN** the chart renders successfully using `caelus.tls.enabled: false` defaults (no TLS
  block, no redirect middleware)

#### Scenario: Schema accepts injected values
- **WHEN** the reconciler injects a populated `caelus.tls` block
- **THEN** `validate_user_values` and Helm accept it against the chart's `values.schema.json`
