## 1. Confirm the upstream rewrite targets

- [ ] 1.1 Re-read the vendored upstream `nextcloud-8.9.1/values.yaml` `server-snippet` block
      (extract `products/nextcloud/chart/charts/nextcloud-8.9.1.tgz`) and record the exact rewrite
      targets: webfinger/nodeinfo → `/index.php/.well-known/...`; host-meta(.json) →
      `/public.php?service=host-meta[-json]`; caldav/carddav → `301 → $scheme://$host/remote.php/dav`.
- [ ] 1.2 Confirm the upstream Service name/port the wrapper Ingress targets
      (`nextcloud.fullname` = `.Release.Name` in the Caelus case; port `nextcloud.service.port`
      default `8080`) so the new discovery Ingress backends match the primary Ingress.

## 2. Traefik Middlewares (chart)

- [ ] 2.1 Add `products/nextcloud/chart/templates/wellknown-middleware.yaml` rendering, when
      `nextcloud.wellKnown.enabled` (default true) **and** `caelus.tls.enabled`:
      - a `redirectRegex` Middleware `<release>-wellknown-dav` (CRD `traefik.io/v1alpha1`) that
        301-redirects `^https?://([^/]+)/\.well-known/(card|cal)dav/?$` → `https://${1}/remote.php/dav`
        (`permanent: true`);
      - a `replacePathRegex` Middleware `<release>-wellknown-rewrite` mapping
        `^/\.well-known/webfinger` → `/index.php/.well-known/webfinger`,
        `^/\.well-known/nodeinfo` → `/index.php/.well-known/nodeinfo`,
        `^/\.well-known/host-meta(\.json)?` → `/public.php?service=host-meta[-json]`.
- [ ] 2.2 Ensure both Middlewares render into the **release namespace** (no explicit cross-namespace
      `namespace:` field; rely on the install namespace) so `router.middlewares` can reference them
      same-namespace (this Traefik has `allowCrossNamespace` **off**).
- [ ] 2.3 Apply the wrapper chart's standard labels (`nextcloud-wrapper.labels`) to both Middlewares.

## 3. Wrapper Ingress path rules (chart)

- [ ] 3.1 In `products/nextcloud/chart/templates/ingress.yaml`, add a **second Ingress**
      `<release>-wellknown` (or path rules carrying the middleware annotation) for the discovery
      paths `/.well-known/webfinger`, `/.well-known/nodeinfo`, `/.well-known/host-meta`,
      `/.well-known/caldav`, `/.well-known/carddav`, backending the same upstream Service/port,
      on the **`websecure`** entrypoint, sharing the same host + `caelus.tls` secret as the primary
      Ingress. Keep the primary `/` catch-all Ingress unchanged (and unannotated).
- [ ] 3.2 Annotate the discovery Ingress with
      `traefik.ingress.kubernetes.io/router.middlewares: "<namespace>-<release>-wellknown-rewrite@kubernetescrd,<namespace>-<release>-wellknown-dav@kubernetescrd"`
      (same-namespace refs only). Verify the `@kubernetescrd` provider suffix and namespace prefix
      are correct for this Traefik.
- [ ] 3.3 Ensure the discovery paths are more specific than `/` so Traefik routes them to the
      middleware-bearing router first; **never** match `/.well-known/acme-challenge`.

## 4. Values + schema

- [ ] 4.1 Add `nextcloud.wellKnown.enabled: true` default to `products/nextcloud/chart/values.yaml`.
- [ ] 4.2 Add the `wellKnown` object to `products/nextcloud/chart/values.schema.json` under the
      `nextcloud` pass-through (respecting the existing `additionalProperties` rules), so Helm
      accepts the new key.

## 5. Package + publish

- [ ] 5.1 Bump `products/nextcloud/chart/Chart.yaml` `version` (e.g. `1.0.2`).
- [ ] 5.2 `helm template` render-checks: (a) custom-domain host — primary `/` Ingress + discovery
      Ingress + both Middlewares present, middleware annotation correct; (b) wildcard host — same
      (TLS secret differs); (c) `wellKnown.enabled: false` — no Middlewares, no discovery Ingress,
      primary Ingress unchanged; (d) `caelus.tls.enabled: false` standalone — renders cleanly.
- [ ] 5.3 Repackage and push the wrapper `.tgz`/OCI artifact
      (`oci://registry.home/helm/nextcloud-wrapper:<new-version>`), record the digest.
- [ ] 5.4 Operator updates the nextcloud `ProductTemplateVersion` to the new chart version/digest
      via the admin UI.

## 6. Verification

- [ ] 6.1 On a redeployed nextcloud instance, confirm `GET https://<host>/.well-known/caldav` and
      `/.well-known/carddav` return **301 → /remote.php/dav** and the Nextcloud admin
      **"Setup warnings"** for the missing caldav/carddav redirects are **cleared**.
- [ ] 6.2 Confirm `GET https://<host>/.well-known/webfinger?resource=...` and
      `/.well-known/nodeinfo` are served (rewritten to the PHP front controller, not 404).
- [ ] 6.3 Confirm a CalDAV/CardDAV client auto-discovers the DAV endpoint from the bare hostname.
- [ ] 6.4 Confirm **no regression**: `http://<host>/.well-known/acme-challenge/<token>` on `:80`
      is still served plain by the cert-manager solver (not redirected/rewritten), and a normal
      `:80` request still `301`s to `https://host` (cluster-wide redirect intact).
