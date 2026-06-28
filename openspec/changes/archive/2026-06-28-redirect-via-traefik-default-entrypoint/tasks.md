## 1. Traefik default entrypoint (live-impacting)

- [x] 1.1 In `tf/deps/system/traefik.tf`, add a `ports` block to the `HelmChartConfig`
  `valuesContent` with `web = { asDefault = false }` and `websecure = { asDefault = true }`.
- [x] 1.2 Update the entrypoint `NOTE:` comment in `traefik.tf` to explain the default is now
  `websecure`-only, so app Ingresses need no per-chart entrypoint annotation.
- [x] 1.3 Confirm the deployed bundled Traefik chart renders `ports.*.asDefault` — done: live cluster
  runs k3s `traefik-38.0.201+up38.0.2` (upstream Helm v38.0.2), which supports the key natively.
  (`--entrypoints.websecure.asDefault=true` in `additionalArguments` remains a fallback only.)

## 2. Keep ACME HTTP-01 on :80

- [x] 2.1 In `tf/deps/certmanager/issuers.tf`, add a solver `ingressTemplate` with annotation
  `traefik.ingress.kubernetes.io/router.entrypoints: web` to the `letsencrypt-http` ClusterIssuer.
- [x] 2.2 Add the same `ingressTemplate` annotation to the `letsencrypt-http-staging` ClusterIssuer.

## 3. Remove the websecure annotation from product charts

- [x] 3.1 Delete the `caelus.tls.enabled`-gated `router.entrypoints "websecure"` annotation line from
  `products/helloworld/chart/templates/ingress.yaml`.
- [x] 3.2 Same for `products/matrix/chart/templates/ingress.yaml`.
- [x] 3.3 Same for `products/mattermost/chart/templates/ingress.yaml`.
- [x] 3.4 Same for `products/naas/chart/templates/ingress.yaml`.
- [x] 3.5 Same for `products/immich/chart/templates/ingress.yaml`.
- [x] 3.6 In `products/vaultwarden/chart/templates/ingress.yaml`, remove the hardcoded `websecure`
  annotation and restructure so the `annotations:` block renders only when `$tlsCustom` is true.
- [x] 3.7 In `products/nextcloud/chart/templates/ingress.yaml`, apply the same restructure.

## 4. Repackage and version-bump charts

- [x] 4.1 Bump `Chart.yaml` `version` for each of the seven modified charts.
- [x] 4.2 Repackaged and pushed all seven charts to `oci://registry.home/helm` (confirmed retrievable
  via `helm show chart`). Digests:
  - helloworld:0.1.7 — `sha256:24f458a36df0c9bdbfcc62a080736360b6e5ff44e5097a79b1923c8d39f3f5d1`
  - matrix:0.1.3 — `sha256:9374f76494035b13b8fe7286fcf79a1e531d499077bc80ef937620adf4b89ae1`
  - naas:0.1.4 — `sha256:4298f22481bddfbb04bd562c175ab6f570d03f2219edac594889d510f3b9e356`
  - immich:2.5.8 — `sha256:f88eb7f62b01ad4c0f7b45126ef319ec8f53f7494c57399b4195f81e91edb271`
  - mattermost:1.0.10 — `sha256:8e03ceef1a0890bc6611912d98b012493ccfeb0fb472aa2dcf272f05fca7cc6b`
  - nextcloud-wrapper:1.0.2 — `sha256:8cf5757811f89c8b1c3ccd80322a854f9cbe78767f5653bca6934d897eb6e960`
  - vaultwarden-wrapper:1.0.1 — `sha256:75dc003c3e37a22195b4011bc962b060630fa0f2747f12ad5c7ef20332e2c7ad`

## 5. Verify

- [x] 5.1 `helm template` each chart for wildcard / custom / standalone and assert: no
  `router.entrypoints` annotation; the custom-domain `tls:` + `cert-manager.io/cluster-issuer` still
  render; wrapper YAML is valid when `annotations:` would be empty.
- [x] 5.2 Run the API test suite (`uv run --no-sync pytest`) and confirm reconcile tests stay green.
- [x] 5.3 Live: operator ran `terraform apply tf/deps/` and rolled out; the `no.freepod.eu`
  helloworld (wildcard) app deploys and is served by the default wildcard cert store with a clean
  Ingress (no per-app cert wiring). Remaining live probes (staging custom-domain re-issue on `:80`,
  `keycloak.freepod.eu:80` redirect) optional.

## 6. Operator handoff

- [x] 6.1 Update the affected `ProductTemplateVersion` rows to the **final** chart versions (section
  7 re-bumped them): helloworld `0.1.8`, matrix `0.1.4`, naas `0.1.5`, immich `2.5.9`, mattermost
  `1.0.11`, nextcloud-wrapper `1.0.3`, vaultwarden-wrapper `1.0.2`.

## 7. Rename values namespace caelus.tls → caelus.ingress

- [x] 7.1 Reconciler: `_build_tls_overrides` → `_build_ingress_overrides`, emit
  `caelus.ingress.{enabled, host, tls.{wildcard, issuer, secretName}}`; update `_build_system_overrides`
  caller/docstring (`api/app/services/reconcile.py`).
- [x] 7.2 Repoint all 7 `templates/ingress.yaml` and 6 `values.schema.json` from `caelus.tls.*` to
  `caelus.ingress.*` (mattermost has no schema); re-nest the 7 `values.yaml` defaults to
  `caelus.ingress: {enabled: false, tls: {}}` (nil-safe standalone). Update stale `caelus.tls`
  comments.
- [x] 7.3 Update `api/tests/test_reconcile_service.py` to the new structure (unit tests renamed
  `test_build_ingress_overrides_*`).
- [x] 7.4 Re-verify (`helm template` × 14 modes + standalone nil-safety, `pytest`), re-bump versions,
  repackage and push. Digests:
  - helloworld:0.1.8 — `sha256:1ab9656445812a737f8da2526df0df93daeb7b929fc6b383eb08859775cc5a67`
  - matrix:0.1.4 — `sha256:dfe7b2b5bec565162d521808cbc977f5b12534c4a1c903b0d259b5c3637d7ea7`
  - naas:0.1.5 — `sha256:fb11f10a80c6df614bae7c64700ab964b291451e28da17282e9332d9b8ac2be6`
  - immich:2.5.9 — `sha256:59bc93b62e0455eb8586fe728a2d82161470cc3c86b64f5be5fe038c12310efc`
  - mattermost:1.0.11 — `sha256:30a98cec48a2bbf0962a552e6d402dea4276e722c9c94ac6e50ca9cda167ac23`
  - nextcloud-wrapper:1.0.3 — `sha256:aabf53fdf2cd45793189538042f56fd1be5ee5d0c13a1d5dd21f504d652f7ab3`
  - vaultwarden-wrapper:1.0.2 — `sha256:5d408192432dec83aadcceccd30e0dfdf059ef81317c42f29c034e7c296038f8`
