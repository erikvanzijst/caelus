# Nextcloud Helm Chart

Wrapper chart around the official Nextcloud Helm chart from
https://github.com/nextcloud/helm/tree/main/charts/nextcloud

The wrapper manages its own PVC for Nextcloud data storage,
allowing Caelus to enforce plan-level storage limits via
`.Values.caelus.plan.storageSize`. The upstream chart is
configured with `persistence.existingClaim` to use the
wrapper's PVC instead of creating its own.

## Building

```bash
cd products/nextcloud/chart
helm dependency update
helm package .
```

This produces `nextcloud-wrapper-1.0.0.tgz`. Create a new
Nextcloud product in the Admin UI and add a template
pointing to the packaged chart.

## Default values (system_values_json)

The wrapper's `values.yaml` contains sensible defaults.
When creating a product template in Caelus, the
`system_values_json` can be left empty if the defaults
suffice, or it can override specific fields.

Note that upstream chart values are nested under the
`nextcloud` key (the Helm dependency name):

```json
{
  "nextcloud": {
    "ingress": {
      "enabled": true,
      "className": "traefik"
    },
    "phpClientHttpsFix": {
      "enabled": true,
      "protocol": "https"
    },
    "internalDatabase": {
      "enabled": false
    },
    "postgresql": {
      "enabled": true,
      "primary": {
        "persistence": {
          "enabled": true
        }
      }
    },
    "nextcloud": {
      "host": "nextcloud.local",
      "mail": {
        "enabled": true,
        "fromAddress": "nextcloud",
        "domain": "deprutser.be",
        "smtp": {
          "host": "smtp.mailer.svc.cluster.local",
          "port": 25,
          "secure": "",
          "authtype": "",
          "name": "",
          "password": ""
        }
      }
    },
    "persistence": {
      "enabled": true,
      "existingClaim": "nextcloud-data"
    },
    "cronjob": {
      "enabled": false
    },
    "startupProbe": {
      "enabled": true
    }
  }
}
```

### Why these defaults matter

**Ingress** (`nextcloud.ingress.enabled`,
`nextcloud.ingress.className`): The upstream chart ships
with ingress disabled. Without these, the Nextcloud pod
runs but is not reachable from outside the cluster. We use
`traefik` as our ingress class.

**HTTPS fix** (`nextcloud.phpClientHttpsFix`): Nextcloud
sits behind a TLS-terminating reverse proxy (Traefik).
Without this fix, Nextcloud thinks it's being served over
plain HTTP and generates incorrect URLs, redirect loops,
and mixed-content warnings.

**PostgreSQL sidecar** (`nextcloud.postgresql.enabled`,
`nextcloud.internalDatabase.enabled`): By default the
upstream chart uses an embedded SQLite database. SQLite is
single-writer and not suitable for production. Setting
`postgresql.enabled: true` deploys a PostgreSQL pod
alongside Nextcloud as a subchart (Bitnami PostgreSQL).
This automatically configures Nextcloud to connect to
it — no manual database credentials or connection strings
are needed. We explicitly set `internalDatabase.enabled:
false` to disable SQLite.

**PostgreSQL persistence**
(`nextcloud.postgresql.primary.persistence.enabled`): The
bundled PostgreSQL subchart defaults to ephemeral storage.
Without persistence enabled, all database contents are lost
when the PostgreSQL pod restarts. This creates a PVC for
the PostgreSQL data directory.

**Mail** (`nextcloud.nextcloud.mail`): Preconfigures
Nextcloud to send email through the cluster-internal SMTP
relay at `smtp.mailer.svc.cluster.local:25`. This enables
notifications, password resets, and sharing invitations
out of the box without requiring users to configure mail
settings themselves.

**Nextcloud persistence** (`nextcloud.persistence`): The
wrapper creates its own PVC (`nextcloud-data`) whose size
is controlled by `caelus.plan.storageSize` (falling back
to `storage.data.size`). The upstream chart is told to use
this PVC via `persistence.existingClaim: nextcloud-data`.

## User values schema

Because upstream chart values are nested under the
`nextcloud` dependency key, the user schema uses
`nextcloud.nextcloud.host`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "nextcloud": {
      "type": "object",
      "properties": {
        "nextcloud": {
          "type": "object",
          "properties": {
            "host": {
              "title": "Hostname",
              "type": "string",
              "minLength": 1,
              "description": "The hostname for your Nextcloud instance"
            }
          },
          "required": ["host"],
          "additionalProperties": false
        }
      },
      "required": ["nextcloud"],
      "additionalProperties": false
    }
  },
  "required": ["nextcloud"],
  "additionalProperties": false
}
```
