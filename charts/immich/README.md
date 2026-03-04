# Immich Self-Contained Wrapper Chart

This chart wraps the official Immich chart and adds resources the upstream chart no longer bundles:

- PostgreSQL deployment + PVC
- Upstream Valkey enabled and configured for persistence
- Immich library PVC
- Wrapper-managed Ingress

## Upstream Dependency

- Chart: `oci://ghcr.io/immich-app/immich-charts/immich`
- Version: `0.10.3`

## Notes

- Upstream ingress is disabled; wrapper ingress is used instead.
- Upstream `valkey` dependency is enabled and used directly.
- Immich library claim is auto-created as `library` and injected into upstream values.
- This chart is intended for namespace-per-deployment usage (as in Caelus).

## Manual Install (Helm)

Minimal install (only required override is `ingress.host`):

```bash
helm dependency build charts/immich
helm upgrade --install immich charts/immich \
  --namespace immich \
  --create-namespace \
  --set ingress.host=photos.example.com
```

Uninstall:

```bash
helm uninstall immich --namespace immich
```

## Package and Push (OCI)

Build dependencies, package the chart, and push to the Caelus OCI registry:

```bash
cd charts/immich
helm dependency build
helm package .
helm registry login registry.home:80
helm push immich-2.0.0.tgz oci://registry.home:80/helm --plain-http
```

Pull test:

```bash
helm pull oci://registry.home:80/helm/immich --version 2.0.0 --plain-http
```

## Caelus product template

For the Caelus Admin product template, use the following values schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "ingress": {
      "type": "object",
      "properties": {
        "host": {
          "title": "domainname",
          "type": "string",
          "minLength": 1,
          "maxLength": 64,
          "pattern": "^((?!-)(xn--)?[a-z0-9][a-z0-9-_]{0,61}[a-z0-9]?\\.)+(xn--)?[a-z0-9-]{2,}$",
          "description": "The domainname for your Immich instance"
        }
      },
      "required": [
        "host"
      ],
      "additionalProperties": false
    }
  },
  "required": [
    "ingress"
  ],
  "additionalProperties": false
}
```
