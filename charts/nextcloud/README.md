# Nextcloud Helm Chart

We're using the official Nextcloud Helm chart from
https://github.com/nextcloud/helm/tree/main/charts/nextcloud

Create a new Nextcloud product in the Admin UI and add a
template with the following values:

- Chart: https://github.com/nextcloud/helm/releases/download/nextcloud-8.9.1/nextcloud-8.9.1.tgz
- Tag: 8.9.1

## Default values

```json
{
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
    "enabled": true
  },
  "cronjob": {
    "enabled": false
  },
  "startupProbe": {
    "enabled": true
  }
}
```

### Why these defaults matter

**Ingress** (`ingress.enabled`, `ingress.className`): The
chart ships with ingress disabled. Without these, the
Nextcloud pod runs but is not reachable from outside the
cluster. We use `traefik` as our ingress class.

**HTTPS fix** (`phpClientHttpsFix`): Nextcloud sits behind
a TLS-terminating reverse proxy (Traefik). Without this
fix, Nextcloud thinks it's being served over plain HTTP and
generates incorrect URLs, redirect loops, and
mixed-content warnings.

**PostgreSQL sidecar** (`postgresql.enabled`,
`internalDatabase.enabled`): By default the chart uses an
embedded SQLite database. SQLite is single-writer and not
suitable for production. Setting `postgresql.enabled: true`
deploys a PostgreSQL pod alongside Nextcloud as a subchart
(Bitnami PostgreSQL). This automatically configures
Nextcloud to connect to it — no manual database credentials
or connection strings are needed. We explicitly set
`internalDatabase.enabled: false` to disable SQLite.

**PostgreSQL persistence**
(`postgresql.primary.persistence.enabled`): The bundled
PostgreSQL subchart defaults to ephemeral storage. Without
persistence enabled, all database contents are lost when
the PostgreSQL pod restarts. This creates a PVC for the
PostgreSQL data directory.

**Mail** (`nextcloud.mail`): Preconfigures Nextcloud to
send email through the cluster-internal SMTP relay at
`smtp.mailer.svc.cluster.local:25`. This enables
notifications, password resets, and sharing invitations
out of the box without requiring users to configure mail
settings themselves.

**Nextcloud persistence** (`persistence.enabled`): Stores
the Nextcloud application data (`/var/www/html`) on a
persistent volume. Without this, uploaded files, installed
apps, and configuration are lost on pod restart.

## User values schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
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
```
