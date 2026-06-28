## Context

The `nextcloud-wrapper` chart (`products/nextcloud/chart/`, version `1.0.1`, depending on upstream
`nextcloud` `8.9.1`) was given its own `templates/ingress.yaml` in the `app-tls-termination`
change, with the upstream ingress disabled (`nextcloud.ingress.enabled: false`) so the wrapper can
carry per-deployment TLS from `caelus.tls` (issuer/secret/host). The wrapper Ingress today has a
single catch-all rule:

```yaml
rules:
  - host: {{ .Values.caelus.tls.host }}
    http:
      paths:
        - path: /
          pathType: Prefix
          backend:
            service:
              name: {{ $svc }}      # nextcloud.fullname (= .Release.Name in the Caelus case)
              port:
                number: {{ .Values.nextcloud.service.port | default 8080 }}
```

The upstream nextcloud chart's `values.yaml` documents the **nginx** `server-snippet` rewrites it
used to attach to its ingress (commented out, for nginx ingress controllers):

```
rewrite ^/.well-known/webfinger /index.php/.well-known/webfinger last;
rewrite ^/.well-known/nodeinfo  /index.php/.well-known/nodeinfo  last;
rewrite ^/.well-known/host-meta /public.php?service=host-meta last;
rewrite ^/.well-known/host-meta.json /public.php?service=host-meta-json;
location = /.well-known/carddav { return 301 $scheme://$host/remote.php/dav; }
location = /.well-known/caldav  { return 301 $scheme://$host/remote.php/dav; }
```

The platform ingress is **Traefik v3** (k3s-bundled, amended via `HelmChartConfig` in
`tf/deps/system/traefik.tf`). nginx `server-snippet` annotations have **no effect** on Traefik, so
these rewrites are simply absent — Nextcloud's admin "Setup warnings" flag the missing
caldav/carddav redirects and DAV auto-discovery fails.

Relevant platform constraints established in `app-tls-termination`:
- The cluster-wide HTTP→HTTPS redirect is a **web-only** (`:80`) catch-all `IngressRoute`
  (`PathPrefix(/)`, `priority: 1`) + a `redirectScheme` Middleware in `kube-system`
  (`tf/deps/system/redirect_https.tf`). App Ingresses are annotated
  `traefik.ingress.kubernetes.io/router.entrypoints: websecure` so their `:80` falls through to
  that redirect.
- cert-manager's HTTP-01 solver serves `/.well-known/acme-challenge/<token>` as **plain HTTP on
  :80**; its exact-path rule out-ranks the catch-all redirect. There is **no** entrypoint-level
  redirect (it would shadow the solver).
- This Traefik does **not** have `allowCrossNamespace` enabled, so a `router.middlewares`
  annotation may only reference a Middleware in the **same namespace** as the Ingress. The wrapper
  renders into the deployment's own namespace, so a Middleware created by the chart in that
  namespace is the safe pattern.

## Goals / Non-Goals

**Goals:**
- Reproduce the Nextcloud `.well-known` service-discovery behaviour with **Traefik-native**
  mechanisms so CalDAV/CardDAV (and webfinger/nodeinfo/host-meta) auto-discovery works and the
  admin "Setup warnings" for the missing caldav/carddav redirects are cleared.
- Keep everything **per-namespace**: Middlewares created by the chart in the app's own namespace,
  referenced by same-namespace name (no cross-namespace refs, since `allowCrossNamespace` is off).
- Do **not** conflict with the cluster-wide HTTP→HTTPS redirect or cert-manager's ACME HTTP-01
  solver path.
- Keep the wrapper Ingress's existing TLS contract (`caelus.tls`, websecure-only) intact.

**Non-Goals:**
- Reproducing the upstream snippet's **security `deny` rules** (`/build|tests|config|lib|3rdparty|
  templates|data` deny, `robots.txt`, `server_tokens off`) — those are nginx hardening, served
  correctly by the Nextcloud app itself / out of scope for discovery. Only the discovery rewrites
  are in scope.
- Any change to the reconciler / `caelus.tls` injection (`api/`).
- Any change to the cluster-wide Traefik config or the redirect/ACME Terraform.
- Adding `.well-known` discovery to other products (immich/vaultwarden wrappers) — nextcloud only.

## Decisions

### D1: Reproduce the rewrites with Traefik Middlewares, not nginx annotations

**Decision:** Implement the discovery rewrites as two Traefik `Middleware` (CRD,
`traefik.io/v1alpha1`) objects rendered by the wrapper chart:

- **`<release>-wellknown-dav`** — a `redirectRegex` Middleware that 301-redirects
  `^https?://([^/]+)/\.well-known/(card|cal)dav/?$` → `https://${1}/remote.php/dav` (permanent).
  This matches Nextcloud's recommended caldav/carddav behaviour and is what clears the admin
  "Setup warnings".
- **`<release>-wellknown-rewrite`** — a `replacePathRegex` Middleware that rewrites the
  webfinger/nodeinfo/host-meta paths to the PHP front-controller targets:
  - `^/\.well-known/webfinger` → `/index.php/.well-known/webfinger`
  - `^/\.well-known/nodeinfo`  → `/index.php/.well-known/nodeinfo`
  - `^/\.well-known/host-meta` → `/public.php?service=host-meta`
  (host-meta.json maps to the json service variant). `replacePathRegex` preserves the rest of the
  request, mirroring nginx `rewrite ... last`.

**Rationale:** Traefik has no `server-snippet`. `redirectRegex` is the native equivalent of the
nginx `return 301`, and `replacePathRegex` is the native equivalent of `rewrite ... last`. Two
Middlewares (one redirect, one rewrite) keep the redirect and the path-rewrite concerns separate
and let each be attached only to the paths it serves.

### D2: Same-namespace Middlewares referenced from the wrapper Ingress (no cross-namespace)

**Decision:** Render both Middlewares into the **release namespace** (the deployment's own
namespace) and reference them from the wrapper Ingress via the
`traefik.ingress.kubernetes.io/router.middlewares` annotation using the
`<namespace>-<middleware-name>@kubernetescrd` form **scoped to the same namespace**. Add explicit
`.well-known/*` path rules to `templates/ingress.yaml` (more specific than the existing `/`
catch-all) so Traefik matches the discovery paths to the middleware-bearing router.

**Rationale:** This Traefik does **not** enable `allowCrossNamespace`, so a router may only
reference Middlewares in its own namespace. The chart already renders into the deployment
namespace, so co-locating the Middlewares there is the safe, self-contained pattern — no shared
`kube-system` object, no reflection. Per-path annotation on the Ingress lets the catch-all `/`
rule stay free of the rewrites (the rewrites must only apply to the `.well-known` paths).

### D3: Ingress path rules (annotation form) over a separate IngressRoute

**Decision:** Keep using the **Kubernetes `Ingress`** the wrapper already renders, adding the
`.well-known` path rules and the `router.middlewares` annotation, rather than introducing a
parallel Traefik `IngressRoute`.

**Rationale:** The wrapper's TLS contract (cert-manager annotation, `tls:` block, websecure-only
entrypoint) is already expressed as an `Ingress`; reusing it keeps a single routing object and one
TLS path. A `IngressRoute` would duplicate the host/TLS/entrypoint wiring and risk diverging from
the `caelus.tls` contract. The Traefik Ingress provider honours the `router.middlewares`
annotation on the Ingress, applying the middlewares to all of that Ingress's routers; to scope the
rewrites to only the `.well-known` paths, the discovery paths are split into their **own Ingress**
(`<release>-wellknown`) that carries the middleware annotation, leaving the primary `/` Ingress
unannotated. Both Ingresses share the same host and TLS secret. (If a future need arises for
per-path middleware on a single Ingress, an `IngressRoute` remains the fallback — noted as an open
option, not chosen here.)

### D4: Coexistence with the cluster-wide redirect and the ACME solver

**Decision:** Scope the discovery Ingress/router to the **`websecure` entrypoint only** (same as
the primary wrapper Ingress) and match only `/.well-known/webfinger`, `/.well-known/nodeinfo`,
`/.well-known/host-meta`, `/.well-known/caldav`, `/.well-known/carddav` (exact/prefix), **never**
`/.well-known/acme-challenge`.

**Rationale:**
- The ACME HTTP-01 solver runs on **`:80` (web)**; the discovery router is `websecure`-only and
  never claims `acme-challenge`, so it cannot shadow issuance.
- The cluster-wide HTTP→HTTPS redirect is a **web-only** catch-all; the discovery rules are on
  `websecure`, so they are orthogonal — a `:80` request to `/.well-known/caldav` still hits the
  redirect first (→ `https://host/.well-known/caldav`), then the discovery router applies on
  `:443`. No loop, no double-handling.
- Because the discovery paths are more specific than the catch-all `/`, Traefik routes them to the
  middleware-bearing router before the plain backend router.

### D5: A `wellKnown.enabled` toggle (default on)

**Decision:** Gate the Middlewares + extra Ingress on `nextcloud.wellKnown.enabled`
(default `true`), added to `values.yaml` and `values.schema.json`
(`additionalProperties: false`, so the key must be declared).

**Rationale:** Lets the behaviour be disabled if a deployment ever needs the bare upstream routing
(or a different discovery strategy), and makes the schema accept the new key. Default-on so the
warnings are cleared without operator action on redeploy. Chart version bump + `.tgz`/OCI
repackage are mandatory (the reconciler installs by version and Helm validates the new key).
