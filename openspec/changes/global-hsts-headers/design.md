## Context

freepod emits no HSTS header on any app response today. This was verified end
to end across the full request path:

- **Homelab HAProxy edge** (`github.com/erikvanzijst/homelab`,
  `helm/haproxy/haproxy.cfg`): `frontend fe_https` runs `mode tcp` — pure L4 TLS
  passthrough. It holds no certificates, inspects only the ClientHello SNI, and
  forwards the still-encrypted stream to the freepod node
  (`default_backend be_freepod`). It never sees plaintext HTTP, so it
  physically cannot inject a response header.
- **freepod Traefik** (`tf/deps/system/helm/traefik/values.yaml.tftpl`)
  terminates TLS but has no `headers` middleware and no default middleware on
  the `websecure` entrypoint. Its only middleware today is the `redirect-https`
  redirectScheme on the `web` entrypoint (`tf/deps/system/redirect_https.tf`).

Net: in `client -> HAProxy(mode tcp) -> Traefik(terminate, no headers mw) ->
app`, nothing adds HSTS. Nextcloud self-emits HSTS in-app, but only to satisfy
its own setup self-check — it is not the platform providing the header.

The fix must live where TLS is terminated and where a header can actually be
added on the response: freepod's Traefik. This is a planning-only OpenSpec
change; the Terraform implementation is future work described by `tasks.md`.

## Goals / Non-Goals

**Goals:**
- Every freepod app served over HTTPS returns
  `strict-transport-security: max-age=31536000; includeSubDomains; preload`
  with no per-app configuration.
- Do it once, at the platform layer, via a shared Traefik middleware attached
  as a default on the `websecure` entrypoint.
- Leave the `web` (:80) path fully intact so ACME HTTP-01 and the HTTP->HTTPS
  redirect keep working.

**Non-Goals:**
- Removing Nextcloud's in-app HSTS. Nextcloud's setup self-check inspects its
  own pod response, so it needs its own header regardless of edge/platform
  behavior. Out of scope.
- Editing the in-flight `add-monitoring-stack` change (see Decisions for the
  interaction note).
- Changing the HAProxy edge, which cannot inject headers in `mode tcp` and does
  not need to.
- Per-app or per-route HSTS tuning; this is a single uniform cluster policy.

## Decisions

### Decision: `headers` Middleware in `kube-system`, styled after `redirect_https.tf`

Define a `kubernetes_manifest` resource
(`apiVersion: traefik.io/v1alpha1`, `kind: Middleware`) named `headers-hsts` in
the `kube-system` namespace, with:

```
spec:
  headers:
    stsSeconds: 31536000
    stsIncludeSubdomains: true
    stsPreload: true
    forceSTSHeader: true
```

`forceSTSHeader` makes Traefik emit the header even for requests it forwards as
plain HTTP after terminating TLS, which is the correct behavior here since TLS
is terminated at Traefik. `stsSeconds = 31536000` is one year — the standard
value required for HSTS preload-list eligibility, together with
`includeSubDomains` and `preload`.

Placing the manifest in `kube-system` and following the exact style of the
existing `redirect_https.tf` (including `depends_on = [module.traefik]`) keeps
it consistent with the one other Traefik CRD object in the codebase.

**Alternative considered — per-app chart middleware annotation.** Rejected:
every product chart would need to opt in and stay in sync, which is exactly the
fragility a cluster-wide default avoids. A single entrypoint default is DRY and
cannot be forgotten on a new app.

### Decision: Attach on the `websecure` entrypoint ONLY

Attach the middleware as a default middleware via the Traefik Helm values:

```
ports:
  websecure:
    http:
      middlewares:
        - "kube-system-headers-hsts@kubernetescrd"
```

`websecure`-only is deliberate and load-bearing. HSTS is meaningless (and
counterproductive) on plain HTTP, and the `web` (:80) entrypoint carries two
things that must not be disturbed:

1. cert-manager's ACME HTTP-01 solver Ingress (a longer, exact
   `/.well-known/acme-challenge/<token>` rule), served as plain HTTP on :80.
2. The low-priority HTTP->HTTPS redirect IngressRoute in `redirect_https.tf`.

Adding a header middleware to `web` risks interfering with those flows for no
benefit, so it must not be attached there. The middleware reference uses
Traefik's `<namespace>-<name>@kubernetescrd` provider-qualified naming, matching
how the Kubernetes CRD provider exposes the resource.

### Decision: Accept the `kubernetes_manifest` CRD-at-plan-time constraint

`kubernetes_manifest` resolves its manifest schema against the **live cluster**
at plan time, so the `traefik.io/v1alpha1` CRDs (installed by the Traefik Helm
release) must already exist when this resource is planned. This is the same
constraint the existing `redirect_https.tf` lives with, and it handles it with
`depends_on = [module.traefik]`. We adopt the identical pattern here, so this is
an established, manageable approach rather than new risk. On a first-ever apply
into an empty cluster the CRDs may not yet exist at plan time; the mitigation
(same as today) is that the Traefik release is applied first — see Risks.

### Decision: Treat the monitoring change's Grafana HSTS as a follow-up, not an edit

The in-flight `add-monitoring-stack` change gives Grafana app-level HSTS via
`grafana.ini`, precisely because nothing else emitted the header. Once this
cluster-wide middleware lands, that per-app Grafana HSTS becomes **redundant**
and could be dropped. We record this as a follow-up/interaction note and do
**not** edit the monitoring change here — the two changes are independent and
should not be coupled at proposal time.

## Risks / Trade-offs

- **HSTS is sticky by design** → A one-year `max-age` with `includeSubDomains`
  means a broken TLS setup can lock clients out of `*.freepod.eu` for up to a
  year. Mitigation: freepod already serves a valid wildcard cert and forces
  HTTPS; roll out and verify (`curl -sI`) before considering `preload`
  submission to the browser preload list.
- **`preload` implies a hard commitment** → Setting `preload` signals intent to
  join the browser preload list (which is effectively irreversible on that
  timescale). Mitigation: the flag only advertises eligibility; actual list
  submission is a separate manual step and is out of scope for this change.
- **CRD-at-plan-time ordering** → If the Traefik CRDs are absent at plan time
  the `kubernetes_manifest` plan fails. Mitigation: `depends_on =
  [module.traefik]`, matching the working `redirect_https.tf`; apply Traefik
  first on a cold cluster.
- **Missing default middleware → transient 500s on `websecure`** → The Traefik
  Helm static config references `kube-system-headers-hsts@kubernetescrd` as a
  default middleware on the `websecure` entrypoint, but the `Middleware` object
  is created *after* the Traefik release (`depends_on = [module.traefik]`).
  While that object is absent — the first-apply window before it is created, or
  a Traefik restart that re-reads config before it exists — Traefik cannot
  resolve the entrypoint default and returns 500 for **all** :443 traffic
  (`websecure` is `asDefault: true`). This is distinct from the
  `redirect_https.tf` pattern despite the shared `depends_on`: that middleware
  backs only the low-priority `web` catch-all, so its absence never breaks
  primary HTTPS. Mitigation: the same `terraform apply` creates the object
  moments later and the condition self-heals; on a cold cluster let the apply
  finish before relying on :443. If the window is ever unacceptable, split the
  apply so the `Middleware` object exists before the Helm values reference it.
- **Wrong entrypoint attachment** → Accidentally attaching to `web` could
  interfere with ACME HTTP-01 / the redirect. Mitigation: the spec and tasks
  make `websecure`-only explicit and the verification step includes an HTTP-01
  challenge check on :80.
- **Double HSTS header on Nextcloud** → Nextcloud still self-emits HSTS, so its
  responses may carry the header from both the app and the middleware.
  Mitigation: acceptable — browsers honor a single consistent policy; the
  values match, and removing Nextcloud's in-app header is an explicit non-goal.
