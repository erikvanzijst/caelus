## Why

The `nextcloud-wrapper` chart (`products/nextcloud/chart/`) provides its own
`templates/ingress.yaml` (a Traefik Ingress carrying per-deployment TLS from `caelus.tls`) and
disables the upstream nextcloud chart's ingress (`nextcloud.ingress.enabled: false`). This was
done in the `app-tls-termination` change so the wrapper can inject issuer/secret/host that static
subchart values cannot.

The upstream nextcloud chart's ingress historically attached **nginx `server-snippet` rewrites**
for Nextcloud's service-discovery endpoints — `/.well-known/webfinger`, `/.well-known/nodeinfo`,
`/.well-known/caldav`, `/.well-known/carddav`, `/.well-known/host-meta` (documented in the
vendored upstream `nextcloud-8.9.1/values.yaml`). The wrapper's hand-written Ingress does **not**
reproduce these. As a result Nextcloud's own admin **"Setup warnings"** flag the missing
`.well-known/caldav` and `.well-known/carddav` redirects, and CalDAV/CardDAV client
auto-discovery (the standard way clients find the DAV endpoint from a bare hostname) does not
work. This was recorded as a known limitation in the archived `app-tls-termination` change
("the old nginx `.well-known` (caldav/carddav) discovery rewrites are not reproduced — a separate
enhancement").

The platform ingress is **Traefik v3**, not nginx, so the upstream `server-snippet` annotations do
not apply at all. The rewrites must be reproduced with Traefik-native mechanisms.

## What Changes

- **Add Traefik `Middleware` resources** to the wrapper chart (a new
  `products/nextcloud/chart/templates/wellknown-middleware.yaml`), created in the **app's own
  namespace** (no cross-namespace references — this Traefik does **not** have
  `allowCrossNamespace` enabled):
  - a `redirectRegex` Middleware that 301-redirects `/.well-known/carddav` and
    `/.well-known/caldav` to `/remote.php/dav` (Nextcloud's recommended behaviour);
  - a `replacePathRegex` Middleware that rewrites `/.well-known/webfinger`,
    `/.well-known/nodeinfo`, and `/.well-known/host-meta(.json)?` to the
    `/index.php/.well-known/...` (and `/public.php?service=...`) targets the Nextcloud PHP
    front-controller serves.
- **Add explicit Ingress path rules** to the wrapper `templates/ingress.yaml` for the
  `/.well-known/*` discovery paths, each referencing the same-namespace Middleware(s) via the
  `traefik.ingress.kubernetes.io/router.middlewares` annotation (or, alternatively, an
  `IngressRoute` — see `design.md` for the decision). The catch-all `/` rule is preserved and the
  discovery rules are ordered so they take precedence.
- **Coexistence guarantees:** the `.well-known/*` rules only match the discovery sub-paths under
  the app host on the `websecure` entrypoint, so they do **not** intercept
  `/.well-known/acme-challenge/...` (cert-manager's HTTP-01 solver, served plain on `:80`) and do
  **not** conflict with the cluster-wide HTTP→HTTPS `redirectScheme` redirect (a web-only
  catch-all on `:80`).
- **Bump the wrapper chart version** and repackage/push the `.tgz`/OCI artifact (the reconciler
  installs by `chart_ref`/`chart_version`), and extend `values.yaml`/`values.schema.json` with any
  toggle introduced (e.g. `nextcloud.wellKnown.enabled`).

## Capabilities

### New Capabilities

- `nextcloud-wellknown-discovery`: the nextcloud wrapper chart reproduces the Nextcloud
  service-discovery `.well-known` rewrites using Traefik-native Middlewares (`redirectRegex` /
  `replacePathRegex`) plus wrapper Ingress path rules, scoped to the app's own namespace, so
  CalDAV/CardDAV (and webfinger/nodeinfo/host-meta) auto-discovery works and the Nextcloud admin
  "Setup warnings" for the missing caldav/carddav redirects are cleared — without conflicting with
  the cluster-wide HTTPS redirect or the ACME HTTP-01 solver.

### Modified Capabilities

<!-- None: this change adds a new discovery capability to the nextcloud wrapper chart; it does not
     alter the existing app-tls-termination capability specs (the TLS Ingress contract is reused,
     not changed). -->

## Impact

- **Charts:** `products/nextcloud/chart/templates/` gains a `wellknown-middleware.yaml`
  (Traefik `Middleware` objects) and `templates/ingress.yaml` gains the `.well-known/*` path
  rules + middleware annotation; `values.yaml`/`values.schema.json` gain a `wellKnown` toggle;
  `Chart.yaml` version bumped; the `.tgz`/OCI artifact repackaged and pushed. The operator updates
  the nextcloud `ProductTemplateVersion` to the new chart version/digest.
- **No backend/reconciler change:** `caelus.tls` injection is unchanged; the Middlewares are
  rendered entirely from chart templates into the deployment's namespace.
- **No Terraform change:** the cluster-wide redirect Middleware and cert-manager solver are
  untouched; the new Middlewares are app-namespace-scoped and self-contained.
- **User-visible:** the Nextcloud admin "Setup warnings" for `.well-known/caldav` and
  `.well-known/carddav` are cleared; CalDAV/CardDAV clients (and Fediverse webfinger/nodeinfo)
  resolve from the bare hostname. Applies to nextcloud deployments redeployed on the new chart
  version.
