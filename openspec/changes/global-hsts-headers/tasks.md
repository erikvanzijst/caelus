## 1. Define the HSTS middleware

- [ ] 1.1 Add a `kubernetes_manifest` resource in `tf/deps/system/` (a new
      `hsts.tf`, or alongside `redirect_https.tf`) for a Traefik
      `apiVersion: traefik.io/v1alpha1`, `kind: Middleware` named
      `headers-hsts` in the `kube-system` namespace, styled exactly after the
      existing `redirect_https_middleware`.
- [ ] 1.2 Set the middleware spec to
      `headers: { stsSeconds = 31536000, stsIncludeSubdomains = true,
      stsPreload = true, forceSTSHeader = true }`.
- [ ] 1.3 Add `depends_on = [module.traefik]` so the `traefik.io/v1alpha1` CRDs
      (installed by the Traefik Helm release) exist before this
      `kubernetes_manifest` is planned.

## 2. Attach to the websecure entrypoint

- [ ] 2.1 In `tf/deps/system/helm/traefik/values.yaml.tftpl`, add
      `ports.websecure.http.middlewares: ["kube-system-headers-hsts@kubernetescrd"]`.
- [ ] 2.2 Confirm the middleware is NOT added to `ports.web` — the `web` (:80)
      entrypoint must stay untouched so ACME HTTP-01 and the HTTP->HTTPS
      redirect are unaffected.

## 3. Documentation

- [ ] 3.1 Add a note to `tf/deps/README.md` describing the cluster-wide HSTS
      middleware, its `websecure`-only attachment, and the rationale.
- [ ] 3.2 Record the follow-up: once this lands, the per-app Grafana HSTS in the
      `add-monitoring-stack` change's `grafana.ini` is redundant and can be
      dropped (do not edit that change as part of this work).

## 4. Deploy and verify

- [ ] 4.1 `terraform plan` / `apply` in `tf/deps/` (Traefik release applied
      first on a cold cluster so the CRDs exist at plan time).
- [ ] 4.2 Verify HSTS is present:
      `curl -sI https://keycloak.freepod.eu` (or another app) shows
      `strict-transport-security: max-age=31536000; includeSubDomains; preload`.
- [ ] 4.3 Verify the `web` entrypoint is unaffected: an ACME HTTP-01 challenge
      on :80 still succeeds (custom-domain cert issuance works) and the
      HTTP->HTTPS redirect still returns 301.
