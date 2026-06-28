# Vaultwarden Wrapper Chart

A Caelus wrapper around the unofficial gissilabs Vaultwarden chart
(https://github.com/gissilabs/charts/tree/master/vaultwarden). The wrapper exists so the app
can carry **per-deployment TLS** (`caelus.tls`): it disables the upstream Ingress and provides
its own (`templates/ingress.yaml`) that is `websecure`-only and, for custom domains, adds the
`cert-manager` annotation + `tls:` secret. Static subchart values cannot express that
(wildcard vs custom is per-deployment).

- Upstream chart: `vaultwarden` `1.4.0` (appVersion `1.35.4`), repo `https://gissilabs.github.io/charts/`
- Wrapper chart pushed to: `oci://registry.home/helm/vaultwarden-wrapper`

## Caelus product template

- **Chart:** `oci://registry.home/helm/vaultwarden-wrapper`
- **Tag:** `1.0.0`
- **Default values (system) json:** `{}` — the wrapper `values.yaml` provides the defaults
  (upstream ingress disabled, persistence, SMTP via the in-cluster mailer). Override here only if
  an environment needs different infra values.

User values schema (paste into the template's values schema):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "host": {
      "type": "string",
      "title": "Hostname",
      "description": "The fully qualified domain name used to access Vaultwarden (e.g. vw.example.com)"
    },
    "vaultwarden": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "vaultwarden": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "allowSignups": {
              "type": "boolean",
              "title": "Allow open registration",
              "description": "Allow anyone to create an account. When disabled, only users who receive an invitation can sign up."
            },
            "allowInvitation": {
              "type": "boolean",
              "title": "Allow invited users to register",
              "description": "Allow users who have been invited by an admin to create an account, even when open registration is disabled.",
              "default": true
            },
            "admin": {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "enabled": {
                  "type": "boolean",
                  "title": "Enable admin portal",
                  "description": "Activate the /admin web interface for server management, user invitations, and configuration."
                },
                "token": {
                  "type": "string",
                  "title": "Admin token",
                  "description": "Password required to access the admin portal. Auto-generated if left empty."
                }
              }
            }
          }
        }
      }
    }
  }
}
```

## Known limitation

The vaultwarden `DOMAIN` env (`vaultwarden.vaultwarden.domain`, the full `https://host` URL) is
**not** set — it varies per deployment and static subchart values can't express it (same
constraint as the per-deployment TLS). This matches the previous wrapper-less behaviour. The
vault works; admin-portal links, email invitations, and WebAuthn 2FA want `DOMAIN` — wiring it
(e.g. reconciler-injected) is a follow-up.
