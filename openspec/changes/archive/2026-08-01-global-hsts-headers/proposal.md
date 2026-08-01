## Why

freepod currently emits **no HSTS header** on any app response, so browsers are
never instructed to pin future visits to HTTPS. This was verified end to end:
the homelab HAProxy edge runs `mode tcp` (L4 SNI passthrough) and never sees
plaintext HTTP, so it physically cannot inject response headers; and freepod's
self-managed Traefik terminates TLS but has no `headers` middleware and no
default middleware on the `websecure` entrypoint. Nothing in the path
`client -> HAProxy(tcp) -> Traefik(terminate) -> app` adds HSTS. We want every
freepod app protected by HSTS by default, at the platform layer, without each
app having to opt in.

## What Changes

- Add a Traefik `headers` **Middleware** named `headers-hsts` in the
  `kube-system` namespace (a `kubernetes_manifest`, `traefik.io/v1alpha1`,
  `kind: Middleware`) that sets a one-year HSTS policy with
  `includeSubDomains`, `preload`, and `forceSTSHeader`.
- Attach that middleware as a **default middleware on the `websecure`
  entrypoint only**, via the Traefik Helm values, so every app served over
  :443 gets the header without per-app configuration.
- Deliberately do **not** attach it to the `web` (:80) entrypoint, keeping
  cert-manager's ACME HTTP-01 challenge path and the HTTP->HTTPS redirect
  untouched.
- Follow-up (interaction only, **not** part of this change): once the
  cluster-wide header lands, the per-app Grafana HSTS added by the in-flight
  `add-monitoring-stack` change becomes redundant and can be dropped later.

## Capabilities

### New Capabilities
- `cluster-hsts`: Emit a Strict-Transport-Security response header on every
  HTTPS (`websecure`) app response cluster-wide via a Traefik headers
  middleware, while leaving the plain-HTTP (`web`) entrypoint untouched so ACME
  HTTP-01 and the HTTP->HTTPS redirect keep working.

### Modified Capabilities
<!-- None. No existing spec's requirements change. The redundancy of the
     monitoring change's per-app Grafana HSTS is noted as a follow-up
     interaction only; that change is not edited here. -->

## Impact

- **New Terraform (future work, described by tasks — not implemented here)**: a
  `kubernetes_manifest` `headers-hsts` Middleware in `tf/deps/system/` (styled
  after the existing `redirect_https.tf`), plus a one-line addition to
  `tf/deps/system/helm/traefik/values.yaml.tftpl`
  (`ports.websecure.http.middlewares`).
- **Docs**: `tf/deps/README.md` note on the cluster-wide HSTS middleware.
- **No app or chart changes**: apps inherit the header from the entrypoint
  default; none opt in individually.
- **Interaction**: overlaps with `add-monitoring-stack`, which gives Grafana
  app-level HSTS via `grafana.ini`; that becomes redundant once this lands
  (follow-up, not changed here).
- **Non-goal**: Nextcloud's in-app HSTS stays; it self-checks its own pod
  response and needs its own header regardless of edge/platform behavior.
