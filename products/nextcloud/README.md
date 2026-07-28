# Nextcloud

A self-contained Nextcloud chart: it renders the Nextcloud application and a
bundled PostgreSQL database directly, on the official `nextcloud` and `postgres`
images. Its only dependency is Freepod's `caelus-sftp` library chart, which adds
read-only SFTP access to the data volume.

## What it deploys

| Component | Object(s) |
|-----------|-----------|
| Nextcloud | Deployment `<release>-nextcloud` (+ read-only SFTP sidecar, + wait-for-DB init), Service `<release>-nextcloud` `:8080→80` |
| PostgreSQL | StatefulSet `<release>-postgresql` on `postgres:17-alpine` + headless Service + Secret `<release>-db` (auto-generated password); data on PVC `data-<release>-postgresql-0` |
| Data | PVC `<release>-data` (plan-sized), mounted into the app via subPaths (`html`, `data`, `config`, `custom_apps`, `themes`, `tmp`) |
| App secrets | Secret `<release>-app` (admin bootstrap + SMTP) |
| Ingress | `<release>-ingress` (per-deployment TLS via `caelus.ingress.tls`) |
| SFTP | Secret + ConfigMap + Service + sshpiper Pipe (`caelus-sftp`, uid 33 to match Nextcloud's `www-data`) |

The bundled PostgreSQL password is generated on first install and reused from the
`<release>-db` Secret on upgrade, so it never rotates a live credential. Set
`postgresql.auth.password` to pin an explicit value instead.

## Manual install

```bash
helm dependency build products/nextcloud/chart
helm upgrade --install nextcloud products/nextcloud/chart \
  --namespace nextcloud --create-namespace \
  --set host=cloud.example.com
```

`image.tag` defaults to `<appVersion>-apache`. Set `admin.password` and the
`smtp.*` values for a real deployment (defaults are dev-only).

## Build and publish

Caelus deploys charts by OCI reference, so the chart must be packaged and pushed
to the registry before a product template can point at it. `helm dependency
build` vendors the `caelus-sftp` library into `charts/`; skipping it fails the
package with a missing-dependency error.

```bash
cd products/nextcloud/chart
helm dependency build .        # vendor caelus-sftp-*.tgz into charts/
helm lint .
helm package .                 # -> nextcloud-0.1.4.tgz
helm push nextcloud-0.1.4.tgz oci://registry.home/helm --insecure-skip-tls-verify
```

Optionally verify the push:

```bash
helm pull oci://registry.home/helm/nextcloud --version 0.1.4 \
  --insecure-skip-tls-verify --destination /tmp
```

The published chart is then referenced from a Caelus product template:

| Field | Value |
|---|---|
| Chart ref | `oci://registry.home/helm/nextcloud` |
| Chart version | `0.1.4` |
| User values schema | see [User values schema](#user-values-schema) below |
| Default Helm values | see [Default values (system_values_json)](#default-values-system_values_json) below |

## User values schema

Defines the form fields on the user-facing deployment dialog — the only values a
tenant may override when creating a Nextcloud instance. Everything else (images,
storage sizing, DB credentials, admin/SMTP secrets, TLS) is operator- or
plan-controlled and is not exposed here. The one tenant-chosen value is the
hostname:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "host": {
      "title": "domainname",
      "type": "string",
      "minLength": 1,
      "description": "The hostname for your Nextcloud instance"
    }
  },
  "required": ["host"],
  "additionalProperties": false
}
```

## Default values (system_values_json)

The admin configures a static default-values blob (`system_values_json`) on the
product template. It is merged over the chart's `values.yaml` for every
deployment created from that template, and is where operator-wide settings live —
SMTP, the admin bootstrap account, and a pinned image tag. It is not where
per-tenant values (the hostname), plan-injected values (storage sizing), or the
auto-generated DB password go.

```json
{
  "image": {
    "tag": "32.0.6-apache"
  },
  "admin": {
    "username": "admin",
    "password": "<set-a-strong-password>"
  },
  "smtp": {
    "host": "smtp.mailer.svc.cluster.local",
    "port": 25,
    "fromAddress": "nextcloud",
    "domain": "deprutser.be"
  }
}
```

`image.tag` pins the Nextcloud release, including the `-apache` suffix (otherwise
it floats on `<appVersion>-apache`); leave `smtp.host` empty to disable mail.
`admin.password` seeds the first-run admin account and is shared by every
deployment created from the template.
