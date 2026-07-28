# Immich — Freepod chart

A self-contained Helm chart for [Immich](https://immich.app/), a self-hosted
photo and video library. The chart renders the entire deployment directly; its
only dependency is Freepod's own `caelus-sftp` library chart (which provides the
read-only SFTP sidecar and its supporting objects).

## What it deploys

| Component | Object(s) |
|-----------|-----------|
| Server (web/API) | Deployment `<release>-server` (+ read-only SFTP sidecar), Service `:2283` |
| Machine learning | Deployment `<release>-machine-learning`, Service `:3003` |
| Valkey (queue) | Deployment + PVC `<release>-valkey` + Service `:6379` |
| PostgreSQL (vectorchord) | Secret + PVC `postgresql-data` + Service + Deployment |
| Library | PVC `library` (plan-sized) |
| Config | ConfigMap `<release>-config` (external URL + SMTP) |
| Ingress | `<release>-ingress` (per-deployment TLS via `caelus.ingress.tls`) |
| SFTP | Secret + ConfigMap + Service + sshpiper Pipe (`caelus-sftp`) |

PostgreSQL uses Immich's own `ghcr.io/immich-app/postgres` image (the
`vectorchord`/`pgvecto.rs` build); stock PostgreSQL will not work because Immich
requires the vector extension. The `library` and `postgresql-data` PVCs use
fixed names (not release-prefixed) so that an existing volume in the namespace
is re-adopted on upgrade rather than replaced by a fresh, empty one.

## Manual install

```bash
helm dependency build products/immich2/chart
helm upgrade --install immich products/immich2/chart \
  --namespace immich --create-namespace \
  --set host=photos.example.com
```

`image.tag` defaults to the chart `appVersion`; override it to pin an Immich
release. Set `smtp.host`/`smtp.from` to enable notification email.

## Build and publish

Caelus deploys charts by OCI reference, so the chart must be packaged and pushed
to the registry before a product template can point at it. `helm dependency
build` vendors the `caelus-sftp` library into `charts/`; skipping it fails the
package with a missing-dependency error.

```bash
cd products/immich2/chart
helm dependency build .        # vendor caelus-sftp-*.tgz into charts/
helm lint .
helm package .                 # -> immich-0.1.1.tgz (named from Chart.yaml)
helm push immich-0.1.1.tgz oci://registry.home/helm --insecure-skip-tls-verify
```

Optionally verify the push:

```bash
helm pull oci://registry.home/helm/immich --version 0.1.1 \
  --insecure-skip-tls-verify --destination /tmp
```

The published chart is then referenced from a Caelus product template:

| Field | Value                                                                               |
|---|-------------------------------------------------------------------------------------|
| Chart ref | `oci://registry.home/helm/immich`                                                   |
| Chart version | `0.1.2`                                                                             |
| User values schema | see [Caelus product template](#caelus-product-template) below                       |
| Default Helm values | see [Default values (system_values_json)](#default-values-system_values_json) below |

## Caelus product template

The **user values schema** defines the form fields on the user-facing deployment
dialog — i.e. the only values a tenant may override when creating an Immich
instance. Everything else (images, storage sizing, DB credentials, TLS) is
operator- or plan-controlled and is deliberately *not* exposed here. It is a
narrow projection of the chart's full `values.schema.json`, not the same file.
The single field is the hostname, which maps to the chart's top-level `host`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "host": {
      "title": "Hostname",
      "type": "string",
      "minLength": 1,
      "description": "The hostname for your Immich instance"
    }
  },
  "required": ["host"],
  "additionalProperties": false
}
```

## Default values (system_values_json)

Separate from the user schema, the admin configures a static **default values**
blob (`system_values_json`) on the product template. It is merged over the
chart's `values.yaml` for *every* deployment created from that template, and is
where operator-wide settings live — SMTP and a pinned image tag. It is **not**
where per-tenant values (the domain name) or plan-injected values (storage
sizing) go.

```json
{
  "image": {
    "tag": "v2.7.0"
  },
  "smtp": {
    "host": "smtp.mailer.svc.cluster.local",
    "port": 25,
    "from": "immich@freepod.eu"
  }
}
```

`image.tag` pins the Immich release (otherwise it floats on the chart
`appVersion`); leave `smtp.host` empty to disable notification email.
