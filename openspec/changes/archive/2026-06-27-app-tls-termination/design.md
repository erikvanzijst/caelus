## Context

Freepod runs on its own k3s cluster (a NAT'd VM, node IP `192.168.0.159`), separate from the
homelab k3s cluster that owns the public IPv4 80/443 port-forward. Freepod's Traefik is the
k3s-bundled Traefik, amended via a `HelmChartConfig` in `tf/deps/system/traefik.tf` (today:
`forwardedheaders.insecure=true` on both entrypoints, because the homelab forwards plaintext
HTTP after terminating TLS). Freepod deploys user apps as Helm charts under `products/*/chart/`;
the reconciler (`api/app/services/reconcile.py`) renders Helm values by merging template
defaults + user values + system overrides (`merge_values_scoped`) and runs `helm upgrade
--install`. Hostnames are assigned per deployment (`DeploymentORM.hostname`) and classified by
`settings.wildcard_domains` / `settings.domain` in `api/app/config.py` and validated in
`api/app/services/hostnames.py` (custom domains must CNAME to `freepod.eu`).

The paired homelab change replaces the upstream TLS termination with an **HAProxy SNI edge**
that passes through (raw TLS, by SNI) any hostname not recognized as a homelab service to
`192.168.0.159:443`, prepending **PROXY protocol** to preserve the client IP. Port 80 is routed
by HTTP `Host` header (no SNI on `:80`) to `192.168.0.159:80` for ACME and redirects. After this
change, **freepod terminates all its own TLS**.

`freepod.eu` DNS is on Cloudflare; the homelab already issues the `*.freepod.eu` wildcard via a
Cloudflare DNS-01 ClusterIssuer (`certs/issuer.tf` in the homelab repo). Freepod reproduces that
pattern locally so it is self-contained.

## Goals / Non-Goals

**Goals:**
- Freepod terminates TLS for both `*.freepod.eu` (wildcard) and arbitrary custom domains.
- Preserve the real client IP end-to-end (PROXY protocol → `X-Forwarded-For`), unchanged from an
  app's perspective.
- Reuse the existing reconciler value-injection pattern so issuer/secret names are
  system-controlled, not hardcoded per chart.
- Minimal per-chart change: `*.freepod.eu` apps need no per-app cert (default store).

**Non-Goals:**
- Changing the homelab edge (that is the paired `haproxy-sni-edge` change).
- Per-app certs for `*.freepod.eu` (the shared wildcard via DNS-01 avoids Let's Encrypt
  rate-limit pressure on the `freepod.eu` registered domain).
- Migrating cert-manager / Traefik versions beyond what install requires.
- Any change to hostname validation (`hostnames.py`) — its wildcard-vs-custom classification is
  reused, not modified.

## Decisions

### D1: cert-manager on freepod with split issuers (DNS-01 wildcard, HTTP-01 custom)

**Decision:** Install cert-manager (Jetstack Helm) into a `cert-manager` namespace. Define a
Cloudflare **DNS-01** ClusterIssuer that issues a single `*.freepod.eu` + `*.dev.freepod.eu`
wildcard Certificate, and a separate **HTTP-01** ClusterIssuer used per-app for custom domains.

**Rationale:** Custom domains are owned by users — we cannot run DNS-01 for them, so HTTP-01 is
the only option, and it requires `:80` reachability (provided by the HAProxy `:80` route). The
`*.freepod.eu` wildcard, by contrast, *can* use DNS-01 (we control `freepod.eu` on Cloudflare),
which (a) avoids per-app ACME round-trips and (b) keeps the shared `freepod.eu` registered domain
off the Let's Encrypt HTTP-01 rate-limit path (50 certs/registered-domain/week). This mirrors the
homelab's proven `letsencrypt-wildcard` issuer. Use Let's Encrypt **staging** issuers during
verification, then switch to prod.

### D2: `*.freepod.eu` wildcard as Traefik default cert store

**Decision:** Set `tlsStore.default.defaultCertificate.secretName` on freepod Traefik to the
wildcard secret (issued by cert-manager). `*.freepod.eu` app Ingresses then need **no** `tls:`
block — Traefik serves the default cert for their SNI.

**Rationale:** Exactly the homelab pattern (`helm/traefik/values.yaml` serves `*.deprutser.be`
as the default store). It collapses the per-chart change for wildcard apps to nothing TLS-cert
related, leaving only the HTTP→HTTPS redirect. Secret-reflection across app namespaces is avoided
because the default store lives in Traefik's namespace.

### D3: Client IP via PROXY protocol, not forwarded-headers trust

**Decision:** On freepod Traefik's `web` and `websecure` entrypoints, set
`proxyProtocol.trustedIPs = [<HAProxy edge IP>]` and **remove**
`--entrypoints.websecure.forwardedheaders.insecure=true`.

**Rationale:** With SNI passthrough, freepod terminates TLS itself and the TCP source is the
HAProxy node, not a trusted header-injecting HTTP proxy. HAProxy `send-proxy-v2` conveys the real
client IP at L4; Traefik reads PROXY protocol and derives `X-Forwarded-For` for apps — so apps
see the same client IP they do today. Blanket `forwardedheaders.insecure` would now be wrong
(any LAN peer could spoof headers); PROXY-protocol trust scoped to the edge IP is correct.
Keep/scope `web` trust consistently (HAProxy `send-proxy-v2` on `:80` too).

### D4: No entrypoint redirect (it deadlocks HTTP-01); redirect is a router, deferred

**Decision:** Freepod Traefik uses **no** entrypoint-level redirect
(`entrypoints.web.http.redirections`). Product charts carry no redirect logic. An HTTP→HTTPS
redirect, if wanted, is a low-priority **web-only IngressRoute + `redirectScheme` Middleware**
(deferred follow-up, task 5.8).

**Rationale (corrected — the original assumption was wrong and was caught in live testing):** an
entrypoint-level redirect is applied **before router matching**, so cert-manager's HTTP-01 solver
Ingress can **not** out-prioritize it — it shadows the solver and deadlocks issuance for custom
domains (verified live: the exact `/.well-known/acme-challenge/<token>` path returned
`301 → https://…:8443`, also leaking the internal port). Removing it let the solver serve the
challenge (`200`) and the cert issued. A *router-level* redirect (the deferred IngressRoute) is a
normal router and **is** overridable by the solver's longer rule, so it is ACME-safe; redirecting
to `https://host` (no port) also avoids the `:8443` leak. The homelab never hit this because it
issues via DNS-01 (no `:80` challenge), so its entrypoint redirect is fine there.

### D5: Central `caelus.tls` injection in the reconciler (not per-chart hardcoding)

**Decision:** Add `_build_tls_overrides(deployment)` to `reconcile.py`, merged into the same
`{"caelus": {...}}` values namespace as `_build_plan_overrides`, producing:

```
caelus.tls = {
  "enabled":    true,
  "host":       <deployment.hostname>,
  "wildcard":   <host endswith any settings.wildcard_domains>,   # classify like hostnames._check_cname
  "issuer":     <settings.tls_cluster_issuer>,    # HTTP-01 issuer; only used when wildcard == false
  "secretName": "<release-name>-tls",             # only used when wildcard == false
}
```

Charts gate on these:
- `traefik.ingress.kubernetes.io/router.entrypoints: websecure` annotation: when
  `caelus.tls.enabled` (both classes), so the app's `:80` falls through to the cluster-wide
  redirect rather than being served plain HTTP by the app's own web router;
- `cert-manager.io/cluster-issuer` annotation + `tls:` block: only when
  `caelus.tls.enabled && not caelus.tls.wildcard`.

`config.py` gains **`tls_cluster_issuer`** only — `acme_email` and the wildcard secret name are
Terraform-side (`var.letsencrypt_email`, the Traefik `tlsStore` secret), so adding them to the API
would be dead config.

**Rationale:** Mirrors how storage/plan limits are injected (system-controlled, highest
precedence via `merge_values_scoped`). Issuer/secret names stay out of chart source. Wildcard
classification reuses the same logic shape as `hostnames.py::_check_cname` (no behavior change to
validation).

### D6: Chart wiring + schema/packaging

**Decision:** Each chart's Ingress template renders the redirect-middleware annotation and the
conditional `tls:`/cert-manager annotation from `caelus.tls`. Add a `caelus.tls` object to every
`values.schema.json` (all use `additionalProperties:false`), add `caelus.tls.enabled:false`
defaults to `values.yaml` (so charts render standalone in `helm template`/tests), bump chart
versions, and repackage the `.tgz` (the reconciler installs by `chart_ref`/`chart_version`).
Native charts (helloworld, matrix, mattermost, naas) edit `templates/ingress.yaml`; the immich
and nextcloud wrappers each get their **own** `templates/ingress.yaml` reading `caelus.tls` (with
the upstream ingress disabled), because static subchart values cannot carry per-deployment
issuer/secret/host. nextcloud additionally gains a `title: hostname` schema field at
`nextcloud.nextcloud.host` so the reconciler derives `deployment.hostname`.

**Rationale:** Keeps the TLS contract uniform across charts while respecting each chart's ingress
shape. Schema + packaging changes are mandatory or `validate_user_values`/Helm reject the new key.

## Risks / Open Questions

- **HTTP-01 timing:** a custom-domain cert can only issue once the HAProxy `:80` route to freepod
  is live (paired change). First-issuance latency is the ACME round-trip; cert-manager retries.
- **Cloudflare token scope:** the freepod DNS-01 issuer needs a token with edit rights on the
  `freepod.eu` zone, stored as a Secret in the freepod cluster.
- **Rate limits:** use staging issuers during rollout; the wildcard (DNS-01) keeps `*.freepod.eu`
  off the HTTP-01 per-registered-domain ceiling.
- **Migration ordering:** deploy + validate this change before the homelab removes its freepod
  termination, so traffic is never black-holed.
- **nextcloud upstream ingress:** RESOLVED via the immich pattern — static subchart values can't
  carry per-deployment TLS, so the upstream ingress is disabled and the wrapper provides its own
  `templates/ingress.yaml` (reads `caelus.tls`, routes to the upstream Service). Its hostname
  wiring was completed (schema `title: hostname` at `nextcloud.nextcloud.host`). The old nginx
  `.well-known` (caldav/carddav) discovery rewrites are not reproduced — a separate enhancement.
