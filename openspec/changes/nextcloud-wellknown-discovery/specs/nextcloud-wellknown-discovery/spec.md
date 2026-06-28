## ADDED Requirements

### Requirement: The nextcloud wrapper reproduces .well-known discovery rewrites with Traefik Middlewares
The `nextcloud-wrapper` chart (`products/nextcloud/chart/`) SHALL reproduce Nextcloud's
service-discovery `.well-known` rewrites — which the disabled upstream nginx ingress provided via
`server-snippet` — using **Traefik-native** mechanisms, because the platform ingress is Traefik v3
and nginx `server-snippet` annotations have no effect. The chart SHALL render, when enabled, a
`redirectRegex` Middleware that **301-redirects** `/.well-known/carddav` and `/.well-known/caldav`
to `/remote.php/dav`, and a `replacePathRegex` Middleware that rewrites `/.well-known/webfinger`,
`/.well-known/nodeinfo`, and `/.well-known/host-meta(.json)` to the Nextcloud PHP front-controller
targets (`/index.php/.well-known/...` and `/public.php?service=host-meta[-json]`).

#### Scenario: CalDAV/CardDAV discovery redirect
- **WHEN** a client requests `https://<nextcloud-host>/.well-known/caldav` (or `/.well-known/carddav`)
- **THEN** Traefik returns a `301` redirect to `/remote.php/dav` produced by the chart's
  `redirectRegex` Middleware
- **AND** the Nextcloud admin "Setup warnings" for the missing caldav/carddav redirects are cleared

#### Scenario: Webfinger / nodeinfo / host-meta rewrite
- **WHEN** a client requests `https://<nextcloud-host>/.well-known/webfinger` (or `/nodeinfo`, or
  `/host-meta`)
- **THEN** the chart's `replacePathRegex` Middleware rewrites the path to the PHP front-controller
  target (`/index.php/.well-known/webfinger`, `/index.php/.well-known/nodeinfo`, or
  `/public.php?service=host-meta`)
- **AND** the request is served by the Nextcloud app rather than returning `404`

### Requirement: Discovery Middlewares are namespace-scoped (no cross-namespace references)
The chart SHALL render the discovery Middlewares into the **deployment's own namespace** and the
wrapper Ingress SHALL reference them via the
`traefik.ingress.kubernetes.io/router.middlewares` annotation using **same-namespace** names only.
The chart MUST NOT reference a Middleware in another namespace, because the platform Traefik does
not have `allowCrossNamespace` enabled.

#### Scenario: Same-namespace middleware reference
- **WHEN** the wrapper chart is installed into a deployment namespace and the discovery Ingress is
  rendered
- **THEN** the `router.middlewares` annotation references the Middlewares by their
  `<namespace>-<name>@kubernetescrd` form within that same namespace
- **AND** no Middleware reference points at `kube-system` or any other namespace

#### Scenario: No cross-namespace dependency
- **WHEN** the rendered Middlewares are inspected
- **THEN** they live in the release namespace alongside the wrapper Ingress
- **AND** they require no shared cluster-wide object and no secret/CRD reflection across namespaces

### Requirement: Discovery rewrites do not conflict with the HTTPS redirect or the ACME solver
The discovery routing SHALL be scoped to the **`websecure`** entrypoint and SHALL match only the
`/.well-known/webfinger`, `/.well-known/nodeinfo`, `/.well-known/host-meta`, `/.well-known/caldav`,
and `/.well-known/carddav` paths. It MUST NOT match `/.well-known/acme-challenge`, so it does not
shadow cert-manager's HTTP-01 solver (served as plain HTTP on `:80`), and it MUST NOT interfere
with the cluster-wide web-only HTTP→HTTPS `redirectScheme` redirect.

#### Scenario: ACME challenge unaffected
- **WHEN** a request for `http://<nextcloud-host>/.well-known/acme-challenge/<token>` arrives on `:80`
- **THEN** the discovery routing does not match it (it is `websecure`-only and never claims
  `acme-challenge`)
- **AND** cert-manager's HTTP-01 solver serves the challenge plain on `:80` and certificate
  issuance is unaffected

#### Scenario: Cluster-wide HTTPS redirect unaffected
- **WHEN** a `:80` request for `/.well-known/caldav` arrives
- **THEN** the cluster-wide web-only catch-all redirect first sends it to `https://<host>/.well-known/caldav`
- **AND** on `:443` the discovery `redirectRegex` Middleware then redirects it to `/remote.php/dav`,
  with no redirect loop and no double-handling

### Requirement: The discovery behaviour is toggleable and the chart is repackaged
The discovery Middlewares and Ingress path rules SHALL be gated on a
`nextcloud.wellKnown.enabled` value (default `true`) declared in the wrapper chart's
`values.yaml` and `values.schema.json`. The wrapper `Chart.yaml` version SHALL be bumped and the
chart artifact repackaged/republished so the reconciler installs the new version.

#### Scenario: Toggle disables discovery routing
- **WHEN** `nextcloud.wellKnown.enabled` is set to `false`
- **THEN** the chart renders neither the discovery Middlewares nor the discovery Ingress path rules
- **AND** the primary `/` catch-all Ingress (and its `caelus.tls` contract) is unchanged

#### Scenario: Schema accepts the new key and the chart version is bumped
- **WHEN** the wrapper chart is rendered or installed with `nextcloud.wellKnown.enabled` set
- **THEN** Helm schema validation accepts the key (it is declared in `values.schema.json`)
- **AND** `Chart.yaml` carries a bumped version and a repackaged artifact is published for the
  reconciler to install
